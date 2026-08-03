"""
字段级复核编排器（verify_fields.py）
======================================

混合 OCR 架构 v3.0 的核心组件。接收 OCR 混淆检测结果（存疑字段清单），
裁剪存疑区域图片，输出结构化任务清单，由 AI 智能体自动读图验证，最后合并结果。

三条复核路径（自动选择，也可 --verify-path 手动指定）：
  ┌────────┬──────────────┬────────────────────────────────────────────┐
  │ 路径   │ 名称         │ 触发条件                                    │
  ├────────┼──────────────┼────────────────────────────────────────────┤
  │ B(默认)│ 智能体复核    │ 在智能体中运行（TRAE/豆包/Kimi 等）          │
  │        │              │ 脚本裁剪图片+输出任务清单，智能体自动读图验证 │
  │        │              │ 全自动，零成本，无需用户参与                  │
  │ A      │ API 复核      │ 用户配置了 Vision API Key                    │
  │        │              │ 脚本自动调用 API，只发存疑字段               │
  │ C      │ 增强重跑      │ 无 API 且智能体无 Vision 能力                │
  │        │              │ 高 DPI + 图像预处理，只重跑存疑页             │
  └────────┴──────────────┴────────────────────────────────────────────┘

路径 B（智能体复核）是默认路径，工作流程：
  1. 脚本裁剪存疑字段对应的原图区域 → PNG 文件
  2. 脚本输出结构化任务清单 → verify_tasks.json
  3. AI 智能体读取任务清单，逐个读取裁剪图片，用自身 Vision 能力验证字段
  4. AI 智能体输出验证结果 → verify_results.json
  5. 脚本合并结果 → verified_data.json
  全程自动，用户无需拖动文件或人工参与。

使用方式：

  # 一键自动（默认路径 B：智能体自动复核）
  python verify_fields.py auto <原始文件> <混淆检测结果.json> --data <数据JSON> --out <输出目录>
  # → 输出 verify_tasks.json + crops/ 目录，AI 智能体自动读图验证后输出 verify_results.json
  # → AI 智能体执行: python verify_fields.py merge <verify_results.json> --data <数据JSON>

  # 手动指定路径
  python verify_fields.py auto <原始文件> <混淆检测结果.json> --data <数据JSON> --verify-path api --provider qwen

  # 分步执行
  python verify_fields.py prepare <原始文件> <混淆检测结果.json> --data <数据JSON> --out <输出目录>
  python verify_fields.py verify-api <verify_tasks.json> --provider qwen
  python verify_fields.py verify-enhance <原始文件> <verify_tasks.json>
  python verify_fields.py merge <verify_results.json> --data <数据JSON> --out <修正后数据JSON>
"""

import sys
import json
import os
import argparse
import tempfile
from pathlib import Path
from typing import Optional
from PIL import Image


# ========== 路径选择逻辑 ==========

def select_verify_path(
    has_api: bool = False,
    has_agent: bool = True,
    force_path: Optional[str] = None,
) -> str:
    """
    根据可用资源自动选择复核路径。

    默认选择路径 B（智能体复核）：skill 运行在 AI 智能体中，
    智能体自身具备 Vision 能力，直接读图验证，零成本、全自动。

    Args:
        has_api: 是否有可用的 Vision API Key
        has_agent: 是否在智能体环境中运行（默认 True）
        force_path: 手动指定路径（"agent"/"api"/"enhance"）

    Returns:
        "agent" / "api" / "enhance"
    """
    if force_path:
        return force_path

    # 路径 B：智能体复核（默认首选——零成本、高精度、全自动）
    if has_agent:
        return "agent"

    # 路径 A：API 复核
    if has_api:
        return "api"

    # 路径 C：增强重跑
    return "enhance"


# ========== 图片裁剪 ==========

def _safe_convert_pdf_page(pdf_path: str, page_num: int, dpi: int = 300):
    """用 PyMuPDF 转换 PDF 指定页为 PIL 图片（替代 poppler/pdf2image）。"""
    import fitz

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_num - 1]  # 0-based index
        pix = page.get_pixmap(matrix=matrix)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    finally:
        doc.close()


def crop_field_region(
    source_file: str,
    page_num: int,
    bbox: Optional[list] = None,
    out_path: Optional[str] = None,
    dpi: int = 300,
) -> str:
    """
    从原始文件中裁剪指定区域的图片。

    Args:
        source_file: 原始 PDF 或图片路径
        page_num: 页码（从 1 开始）
        bbox: 裁剪区域 [x1, y1, x2, y2]（像素坐标，相对于转换后的图片）。None=整页
        out_path: 输出图片路径。None 则自动生成
        dpi: PDF 转图 DPI

    Returns:
        裁剪后的图片路径
    """
    from PIL import Image

    suffix = Path(source_file).suffix.lower()

    if suffix == ".pdf":
        img = _safe_convert_pdf_page(source_file, page_num, dpi=dpi)
    else:
        img = Image.open(source_file)

    # 裁剪指定区域
    if bbox and len(bbox) == 4:
        x1, y1, x2, y2 = bbox
        # 确保坐标在图片范围内
        w, h = img.size
        x1 = max(0, min(int(x1), w))
        y1 = max(0, min(int(y1), h))
        x2 = max(0, min(int(x2), w))
        y2 = max(0, min(int(y2), h))
        if x2 > x1 and y2 > y1:
            img = img.crop((x1, y1, x2, y2))
    # 否则用整页

    # 生成输出路径
    if out_path is None:
        out_dir = Path(tempfile.gettempdir()) / "trae_verify_crops"
        out_dir.mkdir(exist_ok=True)
        out_path = str(out_dir / f"crop_p{page_num}_r{bbox[1] if bbox else 0}.png")

    # 确保输出目录存在
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


# ========== 步骤 1：准备复核任务 ==========

def _find_bbox_for_suspect(suspect: dict, ocr_items: list, padding: int = 20) -> Optional[list]:
    """
    根据 suspect 的 ocr_value 在 OCR items 中查找匹配的 bbox。

    Returns:
        [x1-pad, y1-pad, x2+pad, y2+pad] 或 None
    """
    if not ocr_items:
        return None
    ocr_value = str(suspect.get("ocr_value", "")).strip()
    if not ocr_value:
        return None

    for item in ocr_items:
        text = str(item.get("text", "")).strip()
        bbox = item.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        # 文本包含关系：OCR 结果包含 suspect 值，或 suspect 值包含 OCR 结果
        if ocr_value in text or text in ocr_value:
            x1, y1, x2, y2 = [float(v) for v in bbox]
            return [x1 - padding, y1 - padding, x2 + padding, y2 + padding]
    return None


def prepare_verify_tasks(
    source_file: str,
    confusion_result: dict,
    data: dict,
    out_dir: str,
    dpi: int = 300,
) -> dict:
    """
    准备复核任务：裁剪存疑字段对应的原图区域，输出任务清单。

    Args:
        source_file: 原始 PDF 或图片路径
        confusion_result: ocr_confusion_check.py 的输出结果
        data: 原始数据 JSON（含 rows，v3.3 起可能含 _ocr_items）
        out_dir: 输出目录
        dpi: PDF 转图 DPI

    Returns:
        verify_tasks dict（同时写入 <out_dir>/verify_tasks.json）
    """
    suspects = confusion_result.get("suspects", [])
    if not suspects:
        return {"status": "no_suspects", "tasks": [], "message": "无存疑字段，无需复核"}

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = out_dir / "crops"
    crops_dir.mkdir(exist_ok=True)

    ocr_items = data.get("_ocr_items", [])

    tasks = []
    for i, suspect in enumerate(suspects):
        field = suspect.get("field", "")
        row = suspect.get("row", 0)
        ocr_value = suspect.get("ocr_value", "")
        suspected_value = suspect.get("suspected_value", "")
        reason = suspect.get("reason", "")
        code = suspect.get("code", "")
        confidence = suspect.get("confidence", "")

        page_num = suspect.get("page", 1)

        # v3.3：尝试用 OCR items 中的 bbox 做精确裁剪
        bbox = _find_bbox_for_suspect(suspect, ocr_items)
        if bbox:
            print(f"  [i] task {i+1} 使用 bbox 精确裁剪: {bbox}", file=sys.stderr)

        crop_path = None
        try:
            crop_path = crop_field_region(
                source_file, page_num, bbox=bbox,
                out_path=str(crops_dir / f"task_{i+1}_p{page_num}.png"),
                dpi=dpi,
            )
        except Exception as e:
            print(f"  [!] 裁剪失败 (task {i+1}): {e}", file=sys.stderr)

        # 构造复核问题
        question = _build_question(field, ocr_value, suspected_value, reason)

        task = {
            "task_id": f"VERIFY-{i+1:03d}",
            "field": field,
            "row": row,
            "page": page_num,
            "ocr_value": str(ocr_value),
            "suspected_value": str(suspected_value) if suspected_value else "",
            "reason": reason,
            "code": code,
            "confidence": confidence,
            "bbox": bbox,
            "image_path": crop_path or "",
            "question": question,
        }
        tasks.append(task)

    result = {
        "status": "prepared",
        "source_file": source_file,
        "total_tasks": len(tasks),
        "tasks": tasks,
    }

    # 写入文件
    tasks_file = out_dir / "verify_tasks.json"
    with open(tasks_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  [i] 准备了 {len(tasks)} 个复核任务", file=sys.stderr)
    print(f"  [i] 任务清单: {tasks_file}", file=sys.stderr)
    print(f"  [i] 裁剪图片目录: {crops_dir}", file=sys.stderr)

    return result


def _build_question(field: str, ocr_value: str, suspected_value, reason: str) -> str:
    """根据存疑字段构造复核问题。"""
    field_names = {
        "pile_no": "桩号",
        "filling_coeff": "充盈系数",
        "actual_length": "桩长",
        "verticality": "竖直度",
        "volume": "灌入量",
        "top_elev": "桩顶高程",
        "bottom_elev": "桩底高程",
    }
    field_label = field_names.get(field, field)

    if isinstance(suspected_value, list):
        suspected_str = " 或 ".join(str(v) for v in suspected_value)
    else:
        suspected_str = str(suspected_value) if suspected_value else "未知"

    return (
        f"请识别图片中第 {field_label} 列的数值。"
        f"OCR 初步识别为「{ocr_value}」，但可能有误。"
        f"疑似正确值为「{suspected_str}」。"
        f"请仔细看图，给出正确值。"
    )


# ========== 步骤 2A：智能体复核（路径 B，默认） ==========

def agent_verify(tasks: dict) -> dict:
    """
    生成智能体复核任务清单（路径 B）。

    这个函数不执行实际验证，而是输出结构化任务清单。
    AI 智能体（运行本 skill 的 TRAE/豆包/Kimi 等）读取清单后，
    自动用自身 Vision 能力逐个读图验证，输出 verify_results.json。

    全自动流程，无需用户参与：
      1. 本函数输出任务清单（含裁剪图片路径 + 验证问题）
      2. AI 智能体读取每个 task 的 image_path 图片
      3. AI 智能体用 Vision 能力识别图片中的字段值
      4. AI 智能体输出 verify_results.json
      5. 调用 merge_results 合并结果

    Args:
        tasks: prepare_verify_tasks 的输出

    Returns:
        结构化任务清单 dict，供 AI 智能体直接消费
    """
    task_list = tasks.get("tasks", [])
    if not task_list:
        return {"status": "no_tasks", "tasks": [], "message": "无复核任务"}

    # 构造精简的任务清单，只包含 AI 智能体需要的信息
    agent_tasks = []
    for task in task_list:
        agent_tasks.append({
            "task_id": task["task_id"],
            "image_path": task["image_path"],
            "field": task["field"],
            "row": task["row"],
            "page": task["page"],
            "ocr_value": task["ocr_value"],
            "suspected_value": task["suspected_value"],
            "reason": task["reason"],
            "question": task["question"],
        })

    return {
        "status": "prepared",
        "next_action": "agent_verify",
        "total_tasks": len(agent_tasks),
        "tasks": agent_tasks,
        "output_format": {
            "file": "verify_results.json",
            "structure": {
                "results": [
                    {
                        "task_id": "VERIFY-001",
                        "field": "pile_no",
                        "row": 5,
                        "verified_value": "Z370",
                        "confidence": "high",
                        "note": "图片清晰可见 Z 前缀"
                    }
                ]
            }
        },
        "merge_command": (
            "python verify_fields.py merge <verify_results.json> "
            "--data <原始数据JSON> --out <修正后数据JSON>"
        ),
    }


# ========== 步骤 2B：API 复核（路径 A） ==========

def api_verify(tasks: dict, provider: Optional[str] = None) -> dict:
    """
    用 Vision API 自动复核所有存疑字段（路径 A）。

    Args:
        tasks: prepare_verify_tasks 的输出
        provider: 指定 Provider。None 则自动选择最便宜的

    Returns:
        verify_results dict
    """
    # 导入 vision_providers
    sys.path.insert(0, str(Path(__file__).parent))
    from vision_providers import verify_field_with_api, get_best_provider, detect_available_providers

    task_list = tasks.get("tasks", [])
    if not task_list:
        return {"status": "no_tasks", "results": []}

    # 检测可用 Provider
    if provider is None:
        provider = get_best_provider()
    if provider is None:
        providers = detect_available_providers()
        return {
            "status": "no_api",
            "results": [],
            "error": "未检测到可用的 Vision API Provider",
            "available_providers": providers,
        }

    print(f"  [i] 使用 Provider: {provider}", file=sys.stderr)
    print(f"  [i] 共 {len(task_list)} 个待复核字段", file=sys.stderr)

    results = []
    for i, task in enumerate(task_list):
        task_id = task["task_id"]
        image_path = task["image_path"]
        question = task["question"]
        ocr_value = task["ocr_value"]
        suspected_value = task["suspected_value"]

        if not image_path or not Path(image_path).exists():
            results.append({
                "task_id": task_id,
                "verified_value": "",
                "confidence": "error",
                "note": f"图片文件不存在: {image_path}",
            })
            continue

        print(f"  [{i+1}/{len(task_list)}] 复核 {task_id} ({task['field']})...", file=sys.stderr)

        result = verify_field_with_api(
            image_path=image_path,
            question=question,
            ocr_value=ocr_value,
            suspected_value=suspected_value,
            provider=provider,
        )
        result["task_id"] = task_id
        results.append(result)

    return {
        "status": "completed",
        "provider": provider,
        "total": len(task_list),
        "results": results,
    }


# ========== 步骤 2C：增强重跑（路径 C） ==========

def enhance_verify(
    source_file: str,
    tasks: dict,
    dpi: int = 300,
) -> dict:
    """
    用增强参数重新跑 PaddleOCR（路径 C）。

    增强参数：DPI 300、det_max_side_len=2560、二值化+去噪+对比度增强。
    只重跑存疑字段所在的页，不整本重跑。

    Args:
        source_file: 原始文件路径
        tasks: prepare_verify_tasks 的输出
        dpi: 增强模式 DPI

    Returns:
        verify_results dict
    """
    import tempfile
    import os
    import gc
    from pathlib import Path
    task_list = tasks.get("tasks", [])
    if not task_list:
        return {"status": "no_tasks", "results": []}

    try:
        from paddleocr import PaddleOCR
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError:
        return {
            "status": "error",
            "results": [],
            "error": "PaddleOCR 或 Pillow 未安装",
        }

    # 初始化增强引擎
    try:
        engine = PaddleOCR(
            use_angle_cls=True,
            lang="ch",
            ocr_version="PP-OCRv3",
            use_gpu=False,
            show_log=False,
            enable_mkldnn=True,
            cpu_threads=4,
            det_max_side_len=2560,
            det_db_thresh=0.1,
            det_db_box_thresh=0.3,
            drop_score=0.3,
            rec_batch_num=1,
            cls_batch_num=1,
        )
    except Exception as e:
        print(f"  [!] PaddleOCR 增强引擎初始化失败: {e}", file=sys.stderr)
        return {
            "status": "error",
            "results": [],
            "error": f"PaddleOCR 增强引擎初始化失败: {e}",
        }

    # 收集需要重跑的页码（去重）
    pages_to_rerun = sorted(set(t.get("page", 1) for t in task_list))
    print(f"  [i] 增强重跑：DPI={dpi}, det_max_side_len=2560, 预处理=二值化+去噪+对比度", file=sys.stderr)
    print(f"  [i] 需重跑页: {pages_to_rerun}", file=sys.stderr)

    # 逐页增强重跑
    page_results = {}
    tmp_dir = Path(tempfile.gettempdir()) / "trae_paddleocr_verify"
    tmp_dir.mkdir(exist_ok=True)

    for page_num in pages_to_rerun:
        try:
            img = _safe_convert_pdf_page(source_file, page_num, dpi=dpi)
        except Exception as e:
            print(f"  [!] 第 {page_num} 页转换失败: {e}", file=sys.stderr)
            continue

        # 图像增强预处理
        img = img.convert("L")  # 转灰度
        img = img.filter(ImageFilter.MedianFilter(size=3))  # 去噪
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)  # 提升对比度

        tmp_path = tmp_dir / f"verify_p{page_num}_{os.getpid()}.png"
        try:
            img.save(tmp_path, "PNG")
            result = engine.ocr(str(tmp_path), cls=True)
            lines = []
            if result and isinstance(result, list):
                page_res = result[0] if result and isinstance(result[0], list) else result
                for line in page_res:
                    if isinstance(line, (list, tuple)) and len(line) >= 2:
                        text_info = line[1]
                        if isinstance(text_info, (list, tuple)) and len(text_info) >= 1:
                            lines.append(str(text_info[0]))
            page_results[page_num] = lines
            print(f"  [i] 第 {page_num} 页增强重跑：{len(lines)} 行", file=sys.stderr)
        except Exception as e:
            print(f"  [!] 第 {page_num} 页增强重跑失败: {e}", file=sys.stderr)
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass
            gc.collect()

    # 将增强重跑结果与存疑字段匹配
    results = []
    for task in task_list:
        task_id = task["task_id"]
        page_num = task.get("page", 1)
        field = task.get("field", "")
        ocr_value = task.get("ocr_value", "")

        page_lines = page_results.get(page_num, [])
        # 简单匹配：在重跑结果中搜索是否还包含 OCR 原始值
        found_original = any(ocr_value in line for line in page_lines)
        found_suspected = False
        suspected = task.get("suspected_value", "")
        if isinstance(suspected, list):
            found_suspected = any(
                any(str(s) in line for s in suspected)
                for line in page_lines
            )
        elif suspected:
            found_suspected = any(str(suspected) in line for line in page_lines)

        if found_suspected and not found_original:
            verified = str(suspected if not isinstance(suspected, list) else suspected[0])
            confidence = "medium"
            note = "增强重跑结果支持疑似值，未找到 OCR 原始值"
        elif found_original:
            verified = ocr_value
            confidence = "low"
            note = "增强重跑结果仍包含 OCR 原始值，无法确认是否有误"
        else:
            verified = ""
            confidence = "low"
            note = "增强重跑结果中未找到相关值"

        results.append({
            "task_id": task_id,
            "verified_value": verified,
            "confidence": confidence,
            "note": note,
        })

    return {
        "status": "completed",
        "method": "paddleocr_enhance_rerun",
        "total": len(task_list),
        "results": results,
    }


# ========== 步骤 3：合并复核结果 ==========

def merge_results(
    verify_results: dict,
    data: dict,
    out_path: Optional[str] = None,
) -> dict:
    """
    将复核结果合并回原始数据。

    Args:
        verify_results: verify_results.json 的内容
        data: 原始数据 JSON
        out_path: 输出路径。None 则原地修改

    Returns:
        修正后的数据 JSON
    """
    results = verify_results.get("results", [])
    rows = data.get("rows", [])

    merged_count = 0
    for result in results:
        task_id = result.get("task_id", "")
        verified_value = result.get("verified_value", "")
        confidence = result.get("confidence", "")

        # 只合并高/中置信度的结果
        if confidence not in ("high", "medium"):
            continue

        if not verified_value:
            continue

        # 从 task_id 提取序号（VERIFY-001 → 0）
        try:
            idx = int(task_id.split("-")[-1]) - 1
        except (ValueError, IndexError):
            continue

        # 这里需要一个 task → (row, field) 的映射
        # 由于 prepare_verify_tasks 按顺序生成 task，可以用序号对应
        # 但更可靠的方式是在 verify_results 中包含 row 和 field
        row_num = result.get("row")
        field = result.get("field")

        if row_num is None or field is None:
            continue

        row_idx = row_num - 1  # row_num 从 1 开始
        if 0 <= row_idx < len(rows):
            old_value = rows[row_idx].get(field)
            # 尝试类型转换
            new_value = _try_convert_type(verified_value, old_value)
            rows[row_idx][field] = new_value
            rows[row_idx].setdefault("_verify_notes", []).append({
                "field": field,
                "old_value": old_value,
                "new_value": new_value,
                "confidence": confidence,
                "note": result.get("note", ""),
            })
            merged_count += 1

    data["verify_summary"] = {
        "total_verified": len(results),
        "total_merged": merged_count,
        "method": verify_results.get("method", verify_results.get("provider", "unknown")),
    }

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  [i] 修正后数据已写入: {out_path}", file=sys.stderr)

    print(f"  [i] 合并了 {merged_count}/{len(results)} 个复核结果", file=sys.stderr)
    return data


def _try_convert_type(value_str: str, original_value):
    """尝试将字符串转换为与原始值相同的类型。"""
    if isinstance(original_value, (int, float)):
        try:
            if isinstance(original_value, int):
                return int(float(value_str))
            return float(value_str)
        except ValueError:
            return value_str
    return value_str


# ========== 自动模式 ==========

def auto_verify(
    source_file: str,
    confusion_result: dict,
    data: dict,
    out_dir: str,
    force_path: Optional[str] = None,
    provider: Optional[str] = None,
) -> dict:
    """
    自动检测可用资源，选择最佳复核路径，一步到位完成复核。

    默认路径 B（智能体复核）：脚本裁剪图片+输出任务清单，
    AI 智能体自动读图验证，全程无需用户参与。

    Args:
        source_file: 原始文件路径
        confusion_result: ocr_confusion_check.py 的输出
        data: 原始数据 JSON
        out_dir: 输出目录
        force_path: 强制指定路径（"agent"/"api"/"enhance"）
        provider: 强制指定 API Provider

    Returns:
        路径 B: {"path": "agent", "tasks": {...}, "agent_action": {...}}
        路径 A: {"path": "api", "verify_results": {...}, "merged_data": {...}}
        路径 C: {"path": "enhance", "verify_results": {...}, "merged_data": {...}}
    """
    # 检测可用 API
    sys.path.insert(0, str(Path(__file__).parent))
    from vision_providers import detect_available_providers
    has_api = len(detect_available_providers()) > 0

    # 选择路径
    path = select_verify_path(has_api=has_api, has_agent=True, force_path=force_path)

    print(f"  [i] 复核路径: {path}", file=sys.stderr)

    # 步骤 1：准备复核任务
    tasks = prepare_verify_tasks(source_file, confusion_result, data, out_dir)

    if not tasks.get("tasks"):
        return {"path": path, "verify_results": {"status": "no_suspects"}, "merged_data": data}

    # 步骤 2：执行复核
    if path == "agent":
        # 路径 B：智能体自动复核
        # 脚本输出结构化任务清单，AI 智能体自动读图验证
        agent_action = agent_verify(tasks)

        # 写入任务清单文件，供 AI 智能体读取
        out_dir_path = Path(out_dir)
        action_file = out_dir_path / "agent_verify_tasks.json"
        with open(action_file, "w", encoding="utf-8") as f:
            json.dump(agent_action, f, ensure_ascii=False, indent=2)

        print(f"  [i] 任务清单已输出: {action_file}", file=sys.stderr)
        print(f"  [i] 裁剪图片目录: {out_dir_path / 'crops'}", file=sys.stderr)
        print(f"  [i] AI 智能体将自动读取图片并验证 {agent_action['total_tasks']} 个字段", file=sys.stderr)

        return {
            "path": "agent",
            "tasks": tasks,
            "agent_action": agent_action,
            "action_file": str(action_file),
        }

    elif path == "api":
        # 路径 A：API 自动复核
        verify_results = api_verify(tasks, provider=provider)
        # 步骤 3：合并结果
        merged_data = merge_results(verify_results, data, out_path=str(Path(out_dir) / "verified_data.json"))
        return {"path": "api", "verify_results": verify_results, "merged_data": merged_data}

    else:
        # 路径 C：增强重跑
        verify_results = enhance_verify(source_file, tasks)
        # 步骤 3：合并结果
        merged_data = merge_results(verify_results, data, out_path=str(Path(out_dir) / "verified_data.json"))
        return {"path": "enhance", "verify_results": verify_results, "merged_data": merged_data}


# ========== CLI ==========

def main():
    parser = argparse.ArgumentParser(
        description="字段级复核编排器 — 混合 OCR 架构 v3.0 核心组件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # prepare：准备复核任务
    p_prepare = subparsers.add_parser("prepare", help="准备复核任务（裁剪图片+输出任务清单）")
    p_prepare.add_argument("source", help="原始 PDF 或图片路径")
    p_prepare.add_argument("confusion", help="ocr_confusion_check.py 的输出 JSON 文件")
    p_prepare.add_argument("--data", required=True, help="原始数据 JSON 文件")
    p_prepare.add_argument("--out", "-o", default="./verify_output", help="输出目录（默认 ./verify_output）")
    p_prepare.add_argument("--dpi", type=int, default=300, help="裁剪 DPI（默认 300）")

    # verify-api：API 复核
    p_api = subparsers.add_parser("verify-api", help="用 Vision API 自动复核（路径 A）")
    p_api.add_argument("tasks", help="verify_tasks.json 文件路径")
    p_api.add_argument("--provider", "-p", default=None, help="指定 Provider")

    # verify-enhance：增强重跑
    p_enhance = subparsers.add_parser("verify-enhance", help="增强 PaddleOCR 重跑（路径 C）")
    p_enhance.add_argument("source", help="原始 PDF 或图片路径")
    p_enhance.add_argument("tasks", help="verify_tasks.json 文件路径")
    p_enhance.add_argument("--dpi", type=int, default=300, help="增强 DPI（默认 300）")

    # merge：合并复核结果
    p_merge = subparsers.add_parser("merge", help="合并复核结果到原始数据")
    p_merge.add_argument("results", help="verify_results.json 文件路径")
    p_merge.add_argument("--data", required=True, help="原始数据 JSON 文件")
    p_merge.add_argument("--out", "-o", help="输出路径（默认修改原始文件）")

    # auto：自动模式
    p_auto = subparsers.add_parser("auto", help="自动检测资源并执行复核")
    p_auto.add_argument("source", help="原始 PDF 或图片路径")
    p_auto.add_argument("confusion", help="ocr_confusion_check.py 的输出 JSON 文件")
    p_auto.add_argument("--data", required=True, help="原始数据 JSON 文件")
    p_auto.add_argument("--out", "-o", default="./verify_output", help="输出目录")
    p_auto.add_argument("--verify-path", choices=["agent", "api", "enhance"], default=None)
    p_auto.add_argument("--provider", "-p", default=None)

    args = parser.parse_args()

    if args.command == "prepare":
        confusion = json.loads(Path(args.confusion).read_text(encoding="utf-8"))
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
        prepare_verify_tasks(args.source, confusion, data, args.out, args.dpi)

    elif args.command == "verify-api":
        tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
        results = api_verify(tasks, provider=args.provider)
        out_file = Path(args.tasks).parent / "verify_results.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  [i] 复核结果已写入: {out_file}", file=sys.stderr)

    elif args.command == "verify-enhance":
        tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
        results = enhance_verify(args.source, tasks, dpi=args.dpi)
        out_file = Path(args.tasks).parent / "verify_results.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  [i] 复核结果已写入: {out_file}", file=sys.stderr)

    elif args.command == "merge":
        results = json.loads(Path(args.results).read_text(encoding="utf-8"))
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
        out_path = args.out or args.data
        merge_results(results, data, out_path)

    elif args.command == "auto":
        confusion = json.loads(Path(args.confusion).read_text(encoding="utf-8"))
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
        result = auto_verify(
            args.source, confusion, data, args.out,
            force_path=args.verify_path, provider=args.provider,
        )

        # 输出结果摘要
        path = result.get("path", "")
        if path == "agent":
            agent_action = result.get("agent_action", {})
            total = agent_action.get("total_tasks", 0)
            print(f"\n✅ 任务清单已准备：{total} 个字段待 AI 智能体自动验证", file=sys.stderr)
            print(f"   任务文件: {result.get('action_file', '')}", file=sys.stderr)
            print(f"   AI 智能体将自动读取裁剪图片，用 Vision 能力验证后输出 verify_results.json", file=sys.stderr)
        elif "verify_results" in result:
            vr = result["verify_results"]
            if vr.get("status") == "completed":
                total = vr.get("total", 0)
                results_list = vr.get("results", [])
                high = sum(1 for r in results_list if r.get("confidence") == "high")
                medium = sum(1 for r in results_list if r.get("confidence") == "medium")
                print(f"\n✅ 复核完成：{total} 个字段，高置信度 {high}，中置信度 {medium}", file=sys.stderr)
            elif vr.get("status") == "no_suspects":
                print(f"\n✅ 无存疑字段，无需复核", file=sys.stderr)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
