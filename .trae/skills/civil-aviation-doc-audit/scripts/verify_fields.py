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
        force_path: 手动指定路径（"agent"/"api"）

    Returns:
        "agent" / "api"
    """
    if force_path:
        return force_path

    # 路径 B：智能体复核（默认首选——零成本、高精度、全自动）
    if has_agent:
        return "agent"

    # 路径 A：API 复核
    if has_api:
        return "api"

    # 无 agent 且无 API 时，回退到 API 路径
    return "api"


# ========== 图片裁剪 ==========

# 字段中文名 → 行键：直接复用 rule_engine.FIELD_ALIAS_MAP（单一真相源，避免双写分叉；
# rule_engine 仅依赖标准库，无循环导入风险）
try:
    from rule_engine import FIELD_ALIAS_MAP as _FIELD_ALIAS
except ImportError:  # 独立分发场景兜底：rule_engine 不在同目录时退回最小别名表
    _FIELD_ALIAS = {
        "实长": "actual_length", "实际桩长": "actual_length", "实际长度": "actual_length",
        "桩顶高程": "top_elev", "顶高程": "top_elev",
        "桩底高程": "bottom_elev", "底高程": "bottom_elev",
        "桩号": "pile_no", "设计桩长": "design_length", "设计长度": "design_length",
        "桩径": "diameter", "直径": "diameter",
        "密实电流": "current", "电流": "current",
        "反插次数": "re_penetration", "反插": "re_penetration",
        "灌入量": "volume", "灌入": "volume",
        "充盈系数": "filling_coeff", "竖直度": "verticality", "垂直度": "verticality",
        "沉管时间": "sink_time", "拔管时间": "pull_time",
        "施工部位": "loc", "部位": "loc", "施工日期": "date_raw", "日期": "date_raw",
    }


def _field_to_row_key(field: str) -> str:
    """字段名归一到行键：中文别名 → 英文键；未命中原样返回（本身是英文键时直通）。"""
    return _FIELD_ALIAS.get(str(field).strip(), str(field).strip())


# 英文行键 → 标准中文名（field_label 展示用）：v9.7.1 行级 pending 项的 field
# 是英文键（build_foundation._DOCX_NUMERIC_FIELDS 产出），读图问答用中文提示更友好
_ROW_KEY_TO_CN = {
    "actual_length": "实长", "top_elev": "桩顶高程", "bottom_elev": "桩底高程",
    "pile_no": "桩号", "design_length": "设计桩长", "diameter": "桩径",
    "current": "密实电流", "re_penetration": "反插次数", "volume": "灌入量",
    "filling_coeff": "充盈系数", "verticality": "竖直度",
    "sink_time": "沉管时间", "pull_time": "拔管时间",
    "loc": "施工部位", "date_raw": "施工日期",
}


def _row_key_label(field: str, field_cn: str) -> str:
    """任务 field_label：优先中文原名，其次英文键反查标准中文名，末路原样。

    pending 行级项的 field 本身就是英文键（field_cn==field），此时反查中文。
    """
    if field_cn and field_cn != field:
        return field_cn
    return _ROW_KEY_TO_CN.get(field, field_cn or field)


# docx 内嵌图提取缓存：{docx绝对路径: [按文档顺序的图片路径]}
_DOCX_MEDIA_CACHE: dict = {}


def _extract_docx_media(docx_path: str) -> list:
    """解压 docx，按 document.xml 引用顺序返回 word/media 图片路径列表。

    扫描转化电子文档（WPS 扫描件转 docx）的每页就是一张内嵌图：
    图片引用顺序 = 页序 = 表格序（表 t 对应第 t+1 张图）。
    提取结果缓存到临时目录，重复裁图不重复解压。
    """
    import zipfile
    import re as _re

    key = str(Path(docx_path).resolve())
    if key in _DOCX_MEDIA_CACHE:
        return _DOCX_MEDIA_CACHE[key]

    with zipfile.ZipFile(docx_path) as zf:
        names = set(zf.namelist())
        rels_xml = zf.read("word/_rels/document.xml.rels").decode("utf-8") if "word/_rels/document.xml.rels" in names else ""
        # 属性顺序不定，逐个 Relationship 抓 Id + Target
        rid2target = {}
        for m in _re.finditer(r"<Relationship\b[^>]*/?>", rels_xml):
            seg = m.group(0)
            rid = _re.search(r'Id="(rId\d+)"', seg)
            tgt = _re.search(r'Target="([^"]+)"', seg)
            if rid and tgt and "media/" in tgt.group(1):
                rid2target[rid.group(1)] = tgt.group(1).lstrip("/").split("word/")[-1] \
                    if tgt.group(1).startswith("word/") else tgt.group(1).lstrip("/")
        doc_xml = zf.read("word/document.xml").decode("utf-8") if "word/document.xml" in names else ""
        rids = _re.findall(r'r:embed="(rId\d+)"', doc_xml)

        cache_dir = Path(tempfile.gettempdir()) / "trae_docx_media" / (Path(docx_path).stem + "_" + str(abs(hash(key)))[:8])
        cache_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, rid in enumerate(rids, 1):
            target = rid2target.get(rid)
            if not target:
                continue
            src = f"word/{target}" if not target.startswith("word/") else target
            if src not in names:
                continue
            dst = cache_dir / f"page_{i:03d}{Path(target).suffix or '.png'}"
            if not dst.exists():
                with zf.open(src) as s, open(dst, "wb") as d:
                    d.write(s.read())
            paths.append(str(dst))

    _DOCX_MEDIA_CACHE[key] = paths
    return paths


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
    elif suffix == ".docx":
        # v9.7：扫描转化电子文档——页 = docx 内嵌图（表 t → 第 t+1 张图）
        media = _extract_docx_media(source_file)
        if not (1 <= page_num <= len(media)):
            raise ValueError(f"docx 仅含 {len(media)} 张内嵌图，页码 {page_num} 超范围")
        img = Image.open(media[page_num - 1])
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


# v9.7.1 修复①：表级字段白名单——整表同值的字段才允许 scope=table 整表写。
# 行级数值字段（actual_length/current/volume 等）各行本不相同，若被表级化，
# merge 整表覆写会把同行正确值冲掉（独立复核 R-1 高危项实证的数据污染路径）。
_TABLE_SCOPE_FIELDS = {"loc", "date_raw"}


def suspects_from_pending(data: dict, suggestions: Optional[dict] = None) -> list:
    """v9.7 A2：pending_verification 存疑清单 → 复核 suspects（v9.7.1 行级/表级分流）。

    分流规则（v9.7.1 修复①②）：
      - 带 pile_no 的行级项（数值不可解析等）→ scope=row：按 (表, 桩号) 定位
        全局行号，merge 只写该行，不整表覆写；
      - 无 pile_no 且字段在表级白名单（施工部位/施工日期，整表同值）→ scope=table：
        page = 表序+1（docx 内嵌图序），merge 写整表；
      - field=「整行」（表头不可靠的整行核对项）→ 跳过：读图无法单值作答，
        且经 _field_to_row_key 会新建中文键错位落库，留给 Chat-Verify；
      - 无 pile_no 且不在白名单 → 跳过（无法安全定位，保守不落库）。

    推荐值优先取 suggestions（infer_values 现算，含 suggested_only 文本建议——
    展示给 AI 读图对照，与 Chat-Verify 展示同语义，不落库），退回行内 persisted inferred。
    输出与 confusion suspects 同构，供 prepare_verify_tasks 合流。
    """
    pending = data.get("pending_verification") or []
    rows = data.get("structured_rows") or data.get("rows") or []
    if not isinstance(pending, list) or not rows:
        return []
    out = []
    seen = set()

    def _lookup_inferred(row_no: int, r: dict, field: str) -> str:
        # 优先：完整建议集（含文本 suggested_only，仅展示不落库）
        if suggestions:
            inf = (suggestions.get(str(row_no)) or {}).get(field) or {}
            if isinstance(inf, dict):
                v = str(inf.get("value", "") or "")
                if v:
                    return v
        # 退回：已落库的数学链推断值
        inf = (r.get("inferred") or {}).get(field) or {}
        if isinstance(inf, dict):
            return str(inf.get("value", "") or "")
        return ""

    for it in pending:
        if not isinstance(it, dict):
            continue
        field_cn = str(it.get("field", "")).strip()
        # v9.7.1 修复②：「整行」项不是具体字段，跳过防中文键错位落库
        if field_cn == "整行":
            continue
        field = _field_to_row_key(field_cn)
        if not field:
            continue
        table_idx = it.get("table")
        pile_no = str(it.get("pile_no", "") or "").strip()

        if pile_no:
            # 行级数值存疑项 → scope=row：定位到 (表, 桩号) 对应的具体行
            row_no = None
            rec = ""
            for i, r in enumerate(rows):
                if (isinstance(r, dict) and r.get("table") == table_idx
                        and str(r.get("pile_no", "") or "").strip() == pile_no):
                    row_no = i + 1
                    rec = _lookup_inferred(row_no, r, field)
                    break
            if row_no is None:
                continue  # 桩号对不上现有行（数据已变）→ 跳过
            key = (table_idx, field, pile_no)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "code": f"PENDING-{field}",
                "field": field,
                "field_label": _row_key_label(field, field_cn),
                "row": row_no,
                "table": table_idx,
                "scope": "row",
                "page": (table_idx + 1) if isinstance(table_idx, int) else 1,
                "ocr_value": str(it.get("raw", "") or ""),
                "suspected_value": rec,
                "reason": str(it.get("reason", "") or ""),
                "confidence": "low",
                "action": f"行级字段：读该行（桩号 {pile_no}）图，给出该值",
            })
        else:
            # 表级字段（整表同值）→ scope=table；白名单外无法安全落库 → 跳过
            if field not in _TABLE_SCOPE_FIELDS:
                continue
            key = (table_idx, field)
            if key in seen:
                continue
            seen.add(key)
            # 该表首行全局行号（1-based，与 confusion row 语义一致）+ 推荐值
            row_no = None
            rec = ""
            for i, r in enumerate(rows):
                if isinstance(r, dict) and r.get("table") == table_idx:
                    row_no = i + 1
                    rec = _lookup_inferred(row_no, r, field)
                    break
            out.append({
                "code": f"PENDING-{field}",
                "field": field,
                "field_label": _row_key_label(field, field_cn),
                "row": row_no or 1,
                "table": table_idx,
                "scope": "table",
                "page": (table_idx + 1) if isinstance(table_idx, int) else 1,
                "ocr_value": str(it.get("raw", "") or ""),
                "suspected_value": rec,
                "reason": str(it.get("reason", "") or ""),
                "confidence": "low",
                "action": "表级字段：读整页图，给出整表统一值",
            })
    return out


def prepare_verify_tasks(
    source_file: str,
    confusion_result: dict,
    data: dict,
    out_dir: str,
    dpi: int = 300,
    with_pending: bool = True,
) -> dict:
    """
    准备复核任务：裁剪存疑字段对应的原图区域，输出任务清单。

    Args:
        source_file: 原始 PDF / 图片 / docx（扫描转化电子文档）路径
        confusion_result: ocr_confusion_check.py 的输出结果
        data: 原始数据 JSON（含 rows / structured_rows / pending_verification）
        out_dir: 输出目录
        dpi: PDF 转图 DPI
        with_pending: 是否把 pending_verification 表级存疑合流进任务（默认开）

    Returns:
        verify_tasks dict（同时写入 <out_dir>/verify_tasks.json）
    """
    suspects = [s for s in confusion_result.get("suspects", []) if isinstance(s, dict)]
    # v9.7 A2：合流 pending 表级存疑（部位/日期乱码是它登记的，confusion 只查易混字）
    if with_pending:
        existing = {(s.get("field"), s.get("row")) for s in suspects}
        suggestions = None
        try:
            from data_quality_check import infer_values
            suggestions = (infer_values(data) or {}).get("row_inferred") or {}
        except ImportError:
            try:
                from .data_quality_check import infer_values
                suggestions = (infer_values(data) or {}).get("row_inferred") or {}
            except ImportError:
                suggestions = None
        except Exception:
            suggestions = None
        for s in suspects_from_pending(data, suggestions):
            if (s.get("field"), s.get("row")) not in existing:
                suspects.append(s)
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
        # v9.7 页码修正（H-8 复核①）：docx 场景下 confusion 产的 page 读自行内 _page 键，
        # 而 docx 解析行没有 _page（恒默认 1），跨表行级任务会系统性裁错页。
        # 修正：docx 源按行所在表号推导页码（表 t ↔ 第 t+1 张内嵌图），
        # 与 suspects_from_pending 的表级页码推导同法；行无表号时退回原 page。
        if str(source_file).lower().endswith(".docx"):
            _row_list = data.get("structured_rows")
            if not isinstance(_row_list, list):
                _row_list = data.get("rows")
            if isinstance(_row_list, list) and isinstance(row, int) and 1 <= row <= len(_row_list):
                _r = _row_list[row - 1]
                if isinstance(_r, dict) and _r.get("table") not in (None, ""):
                    try:
                        page_num = int(_r["table"]) + 1
                    except (TypeError, ValueError):
                        pass

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
            "field": _field_to_row_key(field),
            "field_label": suspect.get("field_label") or field,
            "row": row,
            # JSON 落盘禁 None（项目铁律）：行级任务无表号 / docx 整页裁图无 bbox → 统一空串
            "table": suspect.get("table") if suspect.get("table") is not None else "",
            "scope": suspect.get("scope") or "row",
            "page": page_num,
            "ocr_value": str(ocr_value),
            "suspected_value": str(suspected_value) if suspected_value else "",
            "reason": reason,
            "code": code,
            "confidence": confidence,
            "bbox": bbox if bbox is not None else "",
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
        "loc": "施工部位",
        "date_raw": "施工日期",
    }
    field_label = field_names.get(field, field)

    if isinstance(suspected_value, list):
        suspected_str = " 或 ".join(str(v) for v in suspected_value)
    else:
        suspected_str = str(suspected_value) if suspected_value else "未知"

    return (
        f"请识别图片中「{field_label}」的内容。"
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
            "field_label": task.get("field_label") or task["field"],
            "row": task["row"],
            "table": task.get("table"),
            "scope": task.get("scope") or "row",
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
                        "verified_value": "Z370",
                        "confidence": "high",
                        "note": "图片清晰可见 Z 前缀"
                    }
                ]
            },
            "note": "只需 task_id + verified_value + confidence(+note)；row/field/scope 由 merge 按 task_id 回查任务清单，勿手抄",
        },
        "merge_command": (
            "python verify_fields.py merge <verify_results.json> "
            "--tasks <verify_tasks.json> --data <原始数据JSON> --out <修正后数据JSON>"
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


# ========== 步骤 3：合并复核结果 ==========

def merge_results(
    verify_results: dict,
    data: dict,
    out_path: Optional[str] = None,
    tasks: Optional[dict] = None,
) -> dict:
    """
    将复核结果合并回原始数据。

    v9.7 修复三点：
      1. 字段名归一：confusion 产中文字段（如"桩号"），行键是英文（pile_no）——
         统一经 _field_to_row_key 映射后落库，不再新建中文键；
      2. 定位以 tasks 回查为准：row/field/scope 从 verify_tasks.json 按 task_id 取，
         不依赖 AI 在结果里手抄（抄错一行就写错一行）；
      3. 双份同步写：structured_rows 与 rows 同时更新（防 H-6 双份分叉），
         scope=table 的表级任务写整表所有行。

    Args:
        verify_results: verify_results.json 的内容
        data: 原始数据 JSON
        out_path: 输出路径。None 则原地修改
        tasks: prepare_verify_tasks 的输出（推荐传入）

    Returns:
        修正后的数据 JSON
    """
    results = verify_results.get("results", [])

    srows = data.get("structured_rows")
    rows = data.get("rows")
    if srows is None and rows is None:
        return data

    # task_id → task 映射（定位的权威来源）
    task_map: dict = {}
    if tasks:
        for t in tasks.get("tasks", []):
            if isinstance(t, dict) and t.get("task_id"):
                task_map[t["task_id"]] = t

    def _row_lists() -> list:
        # 同一 list 对象去重：调用方传 structured_rows 与 rows 同引用时，
        # 不重复写两遍（避免 _verify_notes 双份留痕）
        out, seen = [], set()
        for lst in (srows, rows):
            if isinstance(lst, list) and id(lst) not in seen:
                seen.add(id(lst))
                out.append(lst)
        return out

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

        task = task_map.get(task_id) or {}
        field = _field_to_row_key(task.get("field") or result.get("field") or "")
        if not field:
            continue
        scope = task.get("scope") or "row"

        # 目标行索引集合（0-based）；表号兼容 None/空串两种缺省形态（v9.7 起落盘统一空串）
        if scope == "table" and task.get("table") not in (None, ""):
            base = srows if isinstance(srows, list) else rows
            target_idxs = [
                i for i, r in enumerate(base)
                if isinstance(r, dict) and r.get("table") == task.get("table")
            ]
        else:
            row_num = task.get("row", result.get("row"))
            if row_num is None:
                continue
            target_idxs = [row_num - 1]

        wrote = False
        for lst in _row_lists():
            for idx in target_idxs:
                if not (0 <= idx < len(lst)) or not isinstance(lst[idx], dict):
                    continue
                old_value = lst[idx].get(field)
                new_value = _try_convert_type(verified_value, old_value)
                lst[idx][field] = new_value
                lst[idx].setdefault("_verify_notes", []).append({
                    "field": field,
                    "old_value": old_value,
                    "new_value": new_value,
                    "confidence": confidence,
                    "note": result.get("note", ""),
                })
                wrote = True
        if wrote:
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
        force_path: 强制指定路径（"agent"/"api"）
        provider: 强制指定 API Provider

    Returns:
        路径 B: {"path": "agent", "tasks": {...}, "agent_action": {...}}
        路径 A: {"path": "api", "verify_results": {...}, "merged_data": {...}}
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
        # 步骤 3：合并结果（v9.7：传 tasks，定位按 task_id 回查）
        merged_data = merge_results(verify_results, data, out_path=str(Path(out_dir) / "verified_data.json"), tasks=tasks)
        return {"path": "api", "verify_results": verify_results, "merged_data": merged_data}


# ========== CLI ==========

def main():
    parser = argparse.ArgumentParser(
        description="字段级复核编排器 — 混合 OCR 架构 v3.0 核心组件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # prepare：准备复核任务
    p_prepare = subparsers.add_parser("prepare", help="准备复核任务（裁剪图片+输出任务清单）")
    p_prepare.add_argument("source", help="原始 PDF / 图片 / docx（扫描转化电子文档）路径")
    p_prepare.add_argument("confusion", help="ocr_confusion_check.py 的输出 JSON 文件")
    p_prepare.add_argument("--data", required=True, help="原始数据 JSON 文件")
    p_prepare.add_argument("--out", "-o", default="./verify_output", help="输出目录（默认 ./verify_output）")
    p_prepare.add_argument("--dpi", type=int, default=300, help="裁剪 DPI（默认 300）")
    p_prepare.add_argument("--no-pending", action="store_true", help="不合流 pending_verification 表级存疑（默认合流）")

    # verify-api：API 复核
    p_api = subparsers.add_parser("verify-api", help="用 Vision API 自动复核（路径 A）")
    p_api.add_argument("tasks", help="verify_tasks.json 文件路径")
    p_api.add_argument("--provider", "-p", default=None, help="指定 Provider")

    # merge：合并复核结果
    p_merge = subparsers.add_parser("merge", help="合并复核结果到原始数据")
    p_merge.add_argument("results", help="verify_results.json 文件路径")
    p_merge.add_argument("--data", required=True, help="原始数据 JSON 文件")
    p_merge.add_argument("--tasks", "-t", default=None, help="verify_tasks.json（推荐传入：定位按 task_id 回查，不依赖结果手抄）")
    p_merge.add_argument("--out", "-o", help="输出路径（默认修改原始文件）")

    # auto：自动模式
    p_auto = subparsers.add_parser("auto", help="自动检测资源并执行复核")
    p_auto.add_argument("source", help="原始 PDF 或图片路径")
    p_auto.add_argument("confusion", help="ocr_confusion_check.py 的输出 JSON 文件")
    p_auto.add_argument("--data", required=True, help="原始数据 JSON 文件")
    p_auto.add_argument("--out", "-o", default="./verify_output", help="输出目录")
    p_auto.add_argument("--verify-path", choices=["agent", "api"], default=None)
    p_auto.add_argument("--provider", "-p", default=None)

    args = parser.parse_args()

    if args.command == "prepare":
        confusion = json.loads(Path(args.confusion).read_text(encoding="utf-8"))
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
        prepare_verify_tasks(args.source, confusion, data, args.out, args.dpi,
                             with_pending=not args.no_pending)

    elif args.command == "verify-api":
        tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
        results = api_verify(tasks, provider=args.provider)
        out_file = Path(args.tasks).parent / "verify_results.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  [i] 复核结果已写入: {out_file}", file=sys.stderr)

    elif args.command == "merge":
        results = json.loads(Path(args.results).read_text(encoding="utf-8"))
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
        tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8")) if args.tasks else None
        out_path = args.out or args.data
        merge_results(results, data, out_path, tasks=tasks)

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
