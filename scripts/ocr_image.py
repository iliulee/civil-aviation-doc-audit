"""
扫描件 OCR 脚本（v3.4.2：RapidOCR 优化版，桩号序列自恢复）
====================================================================

用途：对扫描件图片或 PDF 进行 OCR 识别。
策略（v3.4.2）：
- 默认：只跑 RapidOCR，多策略重试 + 去重合并 + 自恢复表格布局
- 显式 --engine paddle：跑 PaddleOCR（需已安装，install.ps1 自动装）
- 显式 --engine auto：RapidOCR 优先，结果极差时才 fallback PaddleOCR
- 显式 --engine vision：AI 视觉模型（推荐手写件，需 API Key）
- 显式 --engine tesseract：Tesseract 备选

v3.4.2 核心改进：
- 把 PaddleOCR 从默认自动降级链中移除，避免"默认换引擎"的隐藏行为
- RapidOCR 参数针对手写表格继续调优（det_limit_side_len=1920, det_db_thresh=0.22）
- 多尺度/多预处理重试：同一页用 default / enhance / binarize 多次识别后去重合并
- 自恢复表格布局：不依赖 rapid-table，基于 RapidOCR 文本框 bbox 做行聚类 + 列对齐
- 可选 rapid_table：作为表格结构检测备选（--use-table）
- 输出每个字的 bbox，用于后续字段级 Vision 复核的精确定位裁剪
- 领域后处理：自动定位桩号列，修正 Z/2、D/0 等混淆
- 桩号序列推断：根据同行有效桩号趋势，自动补全漏识别的末位数字（如 Z41 → Z419）

使用方式：
    python scripts/ocr_image.py <图片或PDF路径> [--out <输出>]
    python scripts/ocr_image.py <PDF路径> --engine paddle --out <输出>
    python scripts/ocr_image.py <PDF路径> --engine vision --out <输出>
    python scripts/ocr_image.py <PDF路径> --engine rapid --preprocess binarize --out <输出>
    python scripts/ocr_image.py <PDF路径> --engine rapid --use-table --out <输出>

前置依赖：
    pip install rapidocr-onnxruntime Pillow pdf2image requests
    pip install rapid-table  # 可选，表格结构检测备选
    pip install paddleocr==2.8.1 paddlepaddle==2.6.2 opencv-python  # install.ps1 自动安装，--engine paddle 用
"""

import sys
import argparse
import base64
import os
import gc
import tempfile
import shutil
import re
import json
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

# ═══════════════════════════════════════════════════
# 引擎可用性检测
# ═══════════════════════════════════════════════════
try:
    from rapidocr_onnxruntime import RapidOCR
    _rapidocr_engine = None
    HAS_RAPIDOCR = True
except ImportError:
    HAS_RAPIDOCR = False

try:
    from paddleocr import PaddleOCR
    _paddleocr_engine = None
    HAS_PADDLEOCR = True
except ImportError:
    HAS_PADDLEOCR = False

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT_DEPS = True
except ImportError:
    HAS_TESSERACT_DEPS = False

if HAS_TESSERACT_DEPS:
    import shutil as _shutil
    _TESSERACT_CANDIDATES = [
        _shutil.which("tesseract"),
        str(Path(__file__).parent.parent / "tools" / "tesseract" / "tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\app\tesseract\tesseract.exe",
    ]
    for _cand in _TESSERACT_CANDIDATES:
        if _cand and Path(_cand).exists():
            pytesseract.pytesseract.tesseract_cmd = str(_cand)
            break

try:
    from pdf2image import convert_from_path, pdfinfo_from_path
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

try:
    from rapid_table import RapidTable
    _rapid_table_engine = None
    HAS_RAPID_TABLE = True
except ImportError:
    HAS_RAPID_TABLE = False


# ═══════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════
MAX_IMAGE_SIDE = 2400
MIN_IMAGE_SIDE = 800
RAPIDOCR_RETRY_MODES = ["default", "enhance", "binarize"]
PILE_NUMBER_PREFIXES = ["Z", "2"]  # 2 是 Z 的 OCR 误识别


def _ensure_paddleocr_installed() -> bool:
    """尝试自动安装 PaddleOCR + PaddlePaddle（固定稳定版本）。返回是否成功。"""
    global HAS_PADDLEOCR
    if HAS_PADDLEOCR:
        return True
    print("  [!] PaddleOCR 未安装，尝试自动安装稳定版本...", file=sys.stderr)
    try:
        import subprocess
        # Windows 实测 3.x 有 oneDNN 兼容问题，固定 2.8.1 + PaddlePaddle 2.6.2
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "paddleocr==2.8.1", "paddlepaddle==2.6.2", "opencv-python>=4.8.0",
            "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"
        ])
        from paddleocr import PaddleOCR
        HAS_PADDLEOCR = True
        print("  [OK] PaddleOCR 安装完成", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  [X] PaddleOCR 自动安装失败: {e}", file=sys.stderr)
        return False


def _ensure_rapid_table_installed() -> bool:
    """尝试自动安装 rapid-table（表格结构检测备选）。"""
    global HAS_RAPID_TABLE, _rapid_table_engine
    if HAS_RAPID_TABLE:
        return True
    print("  [!] rapid-table 未安装，尝试自动安装...", file=sys.stderr)
    try:
        import subprocess
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "rapid-table", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"
        ])
        from rapid_table import RapidTable
        HAS_RAPID_TABLE = True
        _rapid_table_engine = None
        print("  [OK] rapid-table 安装完成", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  [X] rapid-table 自动安装失败: {e}", file=sys.stderr)
        return False


# ═══════════════════════════════════════════════════
# 图片预处理
# ═══════════════════════════════════════════════════
def _pil_to_cv2(img):
    import cv2
    import numpy as np
    if img.mode != "RGB":
        img = img.convert("RGB")
    arr = np.array(img)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _cv2_to_pil(arr):
    import cv2
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def _resize_for_ocr(img: Image.Image) -> Image.Image:
    if not hasattr(img, "size"):
        return img
    w, h = img.size
    long_side = max(w, h)
    short_side = min(w, h)
    if long_side <= MAX_IMAGE_SIDE and short_side >= MIN_IMAGE_SIDE:
        return img
    if long_side > MAX_IMAGE_SIDE:
        scale = MAX_IMAGE_SIDE / long_side
        return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    if short_side < MIN_IMAGE_SIDE:
        scale = MIN_IMAGE_SIDE / short_side
        new_w = min(int(w * scale), MAX_IMAGE_SIDE)
        new_h = min(int(h * scale), MAX_IMAGE_SIDE)
        return img.resize((new_w, new_h), Image.LANCZOS)
    return img


def _preprocess_for_ocr(
    img: Image.Image,
    mode: str = "default",
) -> Image.Image:
    from PIL import ImageEnhance, ImageFilter

    img = _resize_for_ocr(img)

    if mode == "raw":
        return img

    if mode == "default":
        enhancer = ImageEnhance.Contrast(img.convert("RGB") if img.mode != "RGB" else img)
        return enhancer.enhance(1.15)

    gray = img.convert("L")

    if mode == "gray":
        return gray

    if mode == "enhance":
        gray = gray.filter(ImageFilter.MedianFilter(size=3))
        enhancer = ImageEnhance.Contrast(gray)
        gray = enhancer.enhance(1.5)
        enhancer = ImageEnhance.Sharpness(gray)
        gray = enhancer.enhance(1.6)
        return gray

    if mode == "binarize":
        try:
            import cv2
            import numpy as np
            arr = np.array(gray)
            arr = cv2.GaussianBlur(arr, (3, 3), 0)
            binary = cv2.adaptiveThreshold(
                arr, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                11, 2
            )
            return Image.fromarray(binary)
        except Exception as e:
            print(f"  [!] 二值化失败，回退到增强模式: {e}", file=sys.stderr)
            return _preprocess_for_ocr(img, mode="enhance")

    return img


def _detect_text_density(img: Image.Image) -> float:
    try:
        import numpy as np
        gray = img.convert("L")
        arr = np.array(gray)
        non_white = np.sum(arr < 240)
        return float(non_white) / arr.size
    except Exception:
        return 0.0


# ═══════════════════════════════════════════════════
# 引擎初始化
# ═══════════════════════════════════════════════════
def _get_rapidocr_engine(preprocess_mode: str = "default"):
    """延迟初始化 RapidOCR 引擎。不同预处理模式可能需要不同参数。"""
    global _rapidocr_engine
    # binarize 模式图片已经是二值化，阈值可以稍高；其他模式用低阈值多检
    if preprocess_mode == "binarize":
        db_thresh, box_thresh = 0.30, 0.50
    else:
        db_thresh, box_thresh = 0.22, 0.42

    kwargs = {
        "det_limit_side_len": 1920,
        "det_limit_type": "min",
        "det_db_thresh": db_thresh,
        "det_db_box_thresh": box_thresh,
        "det_db_unclip_ratio": 1.8,
        "use_dilation": True,
        "intra_op_num_threads": 4,
        "inter_op_num_threads": 4,
    }

    while True:
        try:
            return RapidOCR(**kwargs)
        except TypeError as e:
            msg = str(e)
            removed = None
            for key in list(kwargs.keys()):
                if key in msg:
                    removed = key
                    break
            if removed and removed in kwargs:
                print(f"  [i] RapidOCR 不支持参数 {removed}，已移除", file=sys.stderr)
                del kwargs[removed]
            else:
                print(f"  [!] RapidOCR 初始化失败，使用默认配置: {e}", file=sys.stderr)
                return RapidOCR()


def _get_paddleocr_engine():
    global _paddleocr_engine
    if _paddleocr_engine is None:
        try:
            import paddleocr as _paddleocr_mod
            version = getattr(_paddleocr_mod, "__version__", "0.0.0")
            major = int(version.split(".")[0]) if version else 0
            if major >= 3:
                _paddleocr_engine = PaddleOCR(lang="ch")
            else:
                _paddleocr_engine = PaddleOCR(
                    use_angle_cls=True,
                    lang="ch",
                    show_log=False,
                    use_gpu=False,
                )
        except Exception as e:
            print(f"  [!] PaddleOCR 初始化失败: {e}", file=sys.stderr)
            _paddleocr_engine = None
    return _paddleocr_engine


def _get_rapid_table_engine():
    global _rapid_table_engine
    if _rapid_table_engine is None and HAS_RAPID_TABLE:
        try:
            from rapid_table.utils.typings import RapidTableInput
            cfg = RapidTableInput(use_ocr=False)
            _rapid_table_engine = RapidTable(cfg=cfg)
        except Exception as e:
            print(f"  [!] RapidTable 初始化失败: {e}", file=sys.stderr)
            _rapid_table_engine = None
    return _rapid_table_engine


def _get_poppler_path():
    p = Path(__file__).parent.parent / "tools" / "poppler"
    if p.exists():
        for bin_dir in p.rglob("pdftoppm.exe"):
            return str(bin_dir.parent)
    return None


# ═══════════════════════════════════════════════════
# PDF 安全转换
# ═══════════════════════════════════════════════════
def _safe_convert_pdf(
    pdf_path: str,
    dpi: int = 200,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None,
    preprocess_mode: str = "default",
):
    has_non_ascii = bool(re.search(r'[^\x00-\x7F]', str(pdf_path)))
    poppler_path = _get_poppler_path()
    kwargs = {"dpi": dpi}
    if poppler_path:
        kwargs["poppler_path"] = poppler_path
    if first_page:
        kwargs["first_page"] = first_page
    if last_page:
        kwargs["last_page"] = last_page

    source = pdf_path
    tmp_pdf = None
    if has_non_ascii:
        tmp_dir = Path(tempfile.gettempdir()) / "trae_ocr_tmp"
        tmp_dir.mkdir(exist_ok=True)
        tmp_pdf = tmp_dir / "input.pdf"
        shutil.copy2(pdf_path, tmp_pdf)
        source = str(tmp_pdf)

    try:
        images = convert_from_path(source, **kwargs)
        if preprocess_mode != "raw":
            images = [_preprocess_for_ocr(img, mode=preprocess_mode) for img in images]
        return images
    finally:
        if tmp_pdf and Path(tmp_pdf).exists():
            try:
                Path(tmp_pdf).unlink()
            except Exception:
                pass


# ═══════════════════════════════════════════════════
# 结构化结果转换
# ═══════════════════════════════════════════════════
def _rapidocr_result_to_struct(result, page: Optional[int] = None) -> List[Dict[str, Any]]:
    items = []
    if not result:
        return items
    for item in result:
        if isinstance(item, (list, tuple)) and len(item) == 3:
            box, text, score = item
        else:
            continue
        bbox = None
        try:
            if isinstance(box, (list, tuple)) and len(box) == 4:
                if all(isinstance(b, (list, tuple)) and len(b) == 2 for b in box):
                    xs = [b[0] for b in box]
                    ys = [b[1] for b in box]
                    bbox = [min(xs), min(ys), max(xs), max(ys)]
                else:
                    bbox = [float(box[0]), float(box[1]), float(box[2]), float(box[3])]
        except Exception:
            bbox = None
        it = {
            "text": str(text),
            "confidence": float(score) if isinstance(score, (int, float)) else 0.0,
            "bbox": bbox,
            "engine": "RapidOCR",
        }
        if page is not None:
            it["page"] = page
        items.append(it)
    return items


def _apply_domain_postprocess(items: List[Dict[str, Any]], img_width: int) -> List[Dict[str, Any]]:
    """对 OCR 结果应用领域后处理（桩号列检测与 Z/2 修正）。"""
    pile_col = _detect_pile_column(items, img_width)
    pile_mode = _detect_pile_number_mode(items) or pile_col is not None

    if pile_mode:
        print(f"  [i] 检测到桩号列模式 (bbox={pile_col})，对 Z/2 混淆进行后处理修正", file=sys.stderr)

    for it in items:
        is_pile = _is_in_pile_column(it, pile_col)
        it["text"] = _domain_correct_text(it["text"], is_pile_column=is_pile, pile_mode_detected=pile_mode)

    return items


def _paddleocr_result_to_struct(result, page: Optional[int] = None, img_width: int = 1000) -> List[Dict[str, Any]]:
    items = []
    if not result:
        return items
    for line in result:
        if not isinstance(line, (list, tuple)) or len(line) < 2:
            continue
        box_info = line[0]
        text_info = line[1]
        if isinstance(text_info, (list, tuple)) and len(text_info) == 2:
            text, score = text_info
        else:
            text, score = str(text_info), 0.0
        bbox = None
        try:
            if isinstance(box_info, (list, tuple)) and len(box_info) == 4:
                xs = [float(b[0]) for b in box_info]
                ys = [float(b[1]) for b in box_info]
                bbox = [min(xs), min(ys), max(xs), max(ys)]
        except Exception:
            bbox = None
        it = {
            "text": str(text),
            "confidence": float(score),
            "bbox": bbox,
            "engine": "PaddleOCR",
        }
        if page is not None:
            it["page"] = page
        items.append(it)

    # PaddleOCR 也应用领域后处理
    items = _apply_domain_postprocess(items, img_width)
    return items


# ═══════════════════════════════════════════════════
# 表格布局自恢复（v3.4 核心）
# ═══════════════════════════════════════════════════
def _bbox_iou(a: List[float], b: List[float]) -> float:
    """计算两个 bbox 的交并比（IoU）。"""
    if not a or not b or len(a) != 4 or len(b) != 4:
        return 0.0
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _bbox_min_overlap(a: List[float], b: List[float]) -> float:
    """计算重叠面积占较小框面积的比例（适合小框被大框包含的情况）。"""
    if not a or not b or len(a) != 4 or len(b) != 4:
        return 0.0
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / min(area_a, area_b) if area_a > 0 and area_b > 0 else 0.0


def _merge_bboxes(a: List[float], b: List[float]) -> List[float]:
    """合并两个 bbox。"""
    return [
        min(a[0], b[0]),
        min(a[1], b[1]),
        max(a[2], b[2]),
        max(a[3], b[3]),
    ]


def _merge_overlapping_items(items: List[Dict[str, Any]], iou_threshold: float = 0.5) -> List[Dict[str, Any]]:
    """
    合并 IOU 高的重复文本框，保留置信度最高的文本。
    多策略重试时同一文字会被多次检出，合并可减少后续行聚类噪声。
    """
    if not items:
        return []

    # 按置信度降序，优先保留高质量框
    sorted_items = sorted(items, key=lambda x: x.get("confidence", 0), reverse=True)
    merged = []

    for it in sorted_items:
        bbox = it.get("bbox")
        if not bbox:
            merged.append(it)
            continue

        found = False
        for m in merged:
            mbbox = m.get("bbox")
            if not mbbox:
                continue
            if _bbox_iou(bbox, mbbox) > iou_threshold or _bbox_min_overlap(bbox, mbbox) > 0.8:
                # 如果当前框置信度更高，更新文本和 bbox
                if it.get("confidence", 0) > m.get("confidence", 0):
                    m["text"] = it.get("text", m.get("text"))
                    m["confidence"] = it.get("confidence", m.get("confidence"))
                    m["bbox"] = _merge_bboxes(bbox, mbbox)
                    m["engine"] = it.get("engine", m.get("engine"))
                found = True
                break

        if not found:
            merged.append(dict(it))

    # 按位置排序
    merged.sort(key=lambda x: (x.get("bbox", [0, 0, 0, 0])[1], x.get("bbox", [0, 0, 0, 0])[0]))
    return merged


def _center_y(it: Dict[str, Any]) -> float:
    bbox = it.get("bbox")
    if bbox:
        return (bbox[1] + bbox[3]) / 2
    return 0.0


def _center_x(it: Dict[str, Any]) -> float:
    bbox = it.get("bbox")
    if bbox:
        return (bbox[0] + bbox[2]) / 2
    return 0.0


def _cluster_items_into_rows(items: List[Dict[str, Any]], y_threshold: float = 0.5) -> List[List[Dict[str, Any]]]:
    """
    按 bbox 纵坐标把识别框聚类成表格行。
    y_threshold：行高差异阈值（相对中位行高的比例，默认 0.5）
    """
    if not items:
        return []

    valid_items = [it for it in items if it.get("bbox")]
    if not valid_items:
        return []

    heights = []
    for it in valid_items:
        bbox = it.get("bbox")
        if bbox:
            heights.append(bbox[3] - bbox[1])
    heights.sort()
    median_height = heights[len(heights) // 2] if heights else 20.0

    sorted_items = sorted(valid_items, key=_center_y)
    rows = []
    current_row = []
    current_y = None

    # 阈值：中位高度 * 0.5，最小 8 像素
    threshold = max(median_height * y_threshold, 8.0)

    for it in sorted_items:
        cy = _center_y(it)
        if current_y is None or abs(cy - current_y) <= threshold:
            current_row.append(it)
            if current_y is None:
                current_y = cy
            else:
                current_y = (current_y * (len(current_row) - 1) + cy) / len(current_row)
        else:
            current_row.sort(key=lambda x: x.get("bbox", [0, 0, 0, 0])[0])
            rows.append(current_row)
            current_row = [it]
            current_y = cy

    if current_row:
        current_row.sort(key=lambda x: x.get("bbox", [0, 0, 0, 0])[0])
        rows.append(current_row)
    return rows


def _detect_pile_column(items: List[Dict[str, Any]], img_width: int) -> Optional[Tuple[float, float]]:
    """
    基于表头关键词定位桩号列的 x 范围。
    返回 (x_min, x_max) 或 None。

    v3.4.1 改进：
    - 严格限制范围，避免把相邻的"设计桩长"列（如 290/220）误判进来
    - 用表头 bbox 宽度作为列宽基准，x_max 不再向右大幅扩展
    """
    if not items or img_width <= 0:
        return None

    # 表头关键词，按优先级排序（越精确越优先）
    header_patterns = [
        r"^(序号\s*/\s*桩|序号/桩|序\s*号\s*/\s*桩)$",
        r"^桩\s*号$",
        r"桩\s*号",
        r"序号\s*/\s*桩",
        r"^桩$",
        r"^序号$",
    ]

    # 第一阶段：按精确模式匹配
    for pat in header_patterns:
        matches = [it for it in items if re.search(pat, it.get("text", ""))]
        if matches:
            # 优先选最靠左的匹配项（桩号列通常在表格左侧）
            matches.sort(key=lambda x: x.get("bbox", [img_width, 0, 0, 0])[0])
            best = matches[0]
            bbox = best.get("bbox")
            if bbox:
                col_width = bbox[2] - bbox[0]
                # 表头可能比实际数据列窄，给少量容错；但不要覆盖到设计桩长列
                x_min = max(0, bbox[0] - col_width * 0.2)
                x_max = min(img_width, bbox[2] + col_width * 0.4)
                return (x_min, x_max)

    # 第二阶段：兜底，找包含"桩"字且较短的文本，并要求在页面左半部分
    fallback = []
    for it in items:
        text = it.get("text", "")
        bbox = it.get("bbox")
        if not bbox or not text:
            continue
        if "桩" in text and len(text.replace(" ", "")) <= 4:
            cx = (bbox[0] + bbox[2]) / 2
            if cx < img_width * 0.5:
                fallback.append(it)

    if fallback:
        fallback.sort(key=lambda x: x.get("bbox", [img_width, 0, 0, 0])[0])
        bbox = fallback[0].get("bbox")
        col_width = bbox[2] - bbox[0]
        x_min = max(0, bbox[0] - col_width * 0.2)
        x_max = min(img_width, bbox[2] + col_width * 0.4)
        return (x_min, x_max)

    return None


def _is_in_pile_column(it: Dict[str, Any], pile_col: Optional[Tuple[float, float]]) -> bool:
    """判断文本框是否在桩号列范围内。"""
    if pile_col is None:
        return False
    bbox = it.get("bbox")
    if not bbox:
        return False
    cx = _center_x(it)
    return pile_col[0] <= cx <= pile_col[1]


def _detect_pile_number_mode(items: List[Dict[str, Any]]) -> bool:
    """
    检测当前页面是否处于'桩号列'模式：
    如果一页中有多个文本符合 2xxx/2xxx[A-D] 模式（4 位字符），很可能是桩号列被 OCR 错把 Z 识别成 2。
    """
    pattern = re.compile(r"^2[4-9]\d{2}[A-D]?$")
    count = sum(1 for it in items if pattern.match(it.get("text", "").strip()))
    return count >= 2


def _edit_distance(a: str, b: str) -> int:
    """计算两个字符串的编辑距离。"""
    if len(a) < len(b):
        return _edit_distance(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[-1] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def _looks_like_pile_number(text: str) -> bool:
    """判断文本是否符合桩号模式（Z 或 2 开头 + 3~4 位数字，可选 A-D 后缀）。"""
    if not text:
        return False
    t = text.strip()
    # Zxxx / ZxxD / 2xxx / 2xxD / 2.xxx
    return bool(re.match(r"^[Z2][\.\,\;\:\-]?[4-9]\d{1,2}[A-DI-Z0Oo]?$", t))


def _extract_pile_core(text: str) -> Optional[str]:
    """从桩号文本中提取核心数字部分，如 Z42D -> 42D，Z418 -> 418。"""
    if not text:
        return None
    t = text.strip()
    # 去掉前导 Z/2 和分隔符
    m = re.match(r"^[Z2][\.\,\;\:\-]?([4-9]\d{1,2}[A-DI-Z0Oo]?)$", t)
    if m:
        core = m.group(1)
        # 统一 D/0/O
        if core.endswith(("0", "O", "o")):
            core = core[:-1] + "D"
        return core
    return None


def _is_valid_pile_number(text: str) -> bool:
    """判断是否为已补全的有效桩号（Z 开头）。"""
    if not text:
        return False
    return bool(re.match(r"^Z[4-9]\d{1,2}[A-D]?$", text.strip()))


def _domain_correct_text(
    text: str,
    is_pile_column: bool = False,
    pile_mode_detected: bool = False,
) -> str:
    """
    基于民航碎石桩施工记录领域的后处理规则，修正常见 OCR 混淆。

    v3.4.1 变化：
    - 只有在明确桩号列范围内才做 Z/2 替换，避免误伤设计桩长、高程等
    - 对整页桩号模式仍做兜底，但要求文本本身看起来像桩号
    """
    if not text:
        return text

    original = text.strip()
    corrected = original

    # 规则 1：桩号列内的 Z/2 混淆
    if is_pile_column:
        # 2xxx / 2xx[A-D] / 2xxx0 -> Zxxx / ZxxD
        m = re.match(r"^2([4-9]\d{1,2})([A-DI-Z0Oo])?$", corrected)
        if m:
            core = m.group(1)
            suffix = m.group(2) if m.group(2) else ""
            suffix_map = {"O": "D", "0": "D", "o": "D", "I": "", "l": ""}
            suffix = suffix_map.get(suffix, suffix)
            corrected = f"Z{core}{suffix}"

        # OCR 把 Z 识别成 2 的同时，还在数字间插入了小数点：2.415 -> Z415
        m = re.match(r"^2[\.\,\;\:\-]([4-9]\d{1,2})([A-DI-Z0Oo]?)$", corrected)
        if m:
            core = m.group(1)
            suffix = m.group(2) if m.group(2) else ""
            suffix_map = {"O": "D", "0": "D", "o": "D"}
            suffix = suffix_map.get(suffix, suffix)
            corrected = f"Z{core}{suffix}"

        # Zxxx0/O -> ZxxxD（Z42D 被 OCR 错认为 Z420 时的修复）
        if re.match(r"^Z[4-9]\d{1,2}[0Oo]$", corrected):
            corrected = corrected[:-1] + "D"

        # 长度 2~3 的短数字，且在桩号列，很可能是桩号中间部分被截断
        # 例如 41 可能是 Z419 的一部分（Z 和 9 漏识别）
        # 这里只修正那些明显像截断的：2~3 位数字，首位 4~9
        if re.match(r"^[4-9]\d{1,2}$", corrected):
            corrected = f"Z{corrected}"

    # 规则 2：高程 2xxx.xx 格式，修正 l/I->1, S->5 等
    if re.match(r"^2[\dIlSBO]{3}[\.\,][\dIlSBO]{1,3}$", corrected):
        corrected = corrected.replace("l", "1").replace("I", "1").replace("S", "5")
        corrected = corrected.replace("B", "8").replace("O", "0").replace(",", ".")
        corrected = re.sub(r"\.(\d)\s+(\d)", r".\1\2", corrected)

    # 规则 3：时间 HH:MM，修正常见混淆
    time_pattern = re.compile(r"^(\d{2})[:;\.\-](\d{2})$")
    m = time_pattern.match(corrected)
    if m:
        hh = m.group(1).replace("l", "1").replace("I", "1").replace("O", "0").replace("S", "5")
        mm = m.group(2).replace("l", "1").replace("I", "1").replace("O", "0").replace("S", "5")
        corrected = f"{hh}:{mm}"

    return corrected


def _items_to_table_text(items: List[Dict[str, Any]], sep: str = "  ") -> str:
    """把按行聚类后的识别框输出为表格文本。"""
    rows = _cluster_items_into_rows(items)
    lines = []
    for row in rows:
        texts = [it.get("text", "") for it in row]
        lines.append(sep.join(texts))
    return "\n".join(lines)


def _pile_numeric_info(text: str) -> Optional[Dict[str, Any]]:
    """从桩号文本中提取数字信息：数值、后缀、数字字符串。"""
    core = _extract_pile_core(text)
    if not core:
        return None
    m = re.match(r"^(\d+)([A-Da-d]?)$", core)
    if not m:
        return None
    num = int(m.group(1))
    suffix = m.group(2).upper()
    return {"num": num, "suffix": suffix, "digits": str(num)}


def _infer_pile_by_sequence(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    基于同行上下文对桩号列缺失/不完整的文本做序列推断。
    v3.4.2：重点解决"Z41"这类短桩号在 Z418/Z417 等长桩号序列中的补全。

    核心策略：
    1. 先根据已识别的有效桩号判断整列是递增还是递减；
    2. 对当前短/缺项，优先用下一个有效桩号 + 趋势推断；
    3. 推断结果必须满足 OCR 原始数字子串匹配或编辑距离<=1，避免凭空生成。
    推断结果会带有 inferred=True 标记，便于后续人工复核。
    """
    if not items:
        return items

    rows = _cluster_items_into_rows(items)
    pile_rows = []
    for row in rows:
        if not row:
            continue
        first = min(row, key=lambda x: x.get("bbox", [float('inf'), 0, 0, 0])[0])
        pile_rows.append((first, row))

    def _expected_between(prev: str, next: str) -> Optional[str]:
        """根据前后桩号推断中间桩号（仅适用于相邻差 1 的情况）。"""
        prev_info = _pile_numeric_info(prev)
        next_info = _pile_numeric_info(next)
        if not prev_info or not next_info:
            return None
        if next_info["num"] - prev_info["num"] == 2 and prev_info["suffix"] == next_info["suffix"]:
            return f"Z{prev_info['num'] + 1}{prev_info['suffix']}"
        return None

    # 收集所有有效桩号的位置与数字信息
    valid_infos = []
    for idx, (first, _) in enumerate(pile_rows):
        text = first.get("text", "")
        if _is_valid_pile_number(text):
            info = _pile_numeric_info(text)
            if info:
                info["idx"] = idx
                valid_infos.append(info)

    if len(valid_infos) < 2:
        return items

    # 判断序列趋势：-1 递减，1 递增，0 不确定
    diffs = []
    for i in range(len(valid_infos) - 1):
        a, b = valid_infos[i], valid_infos[i + 1]
        if a["suffix"] == b["suffix"] and len(a["digits"]) == len(b["digits"]):
            d = b["num"] - a["num"]
            if abs(d) == 1:
                diffs.append(d)
    trend = 0
    if diffs:
        trend = 1 if sum(1 for d in diffs if d > 0) >= len(diffs) / 2 else -1
    if trend == 0:
        longs = [v for v in valid_infos if len(v["digits"]) >= 3]
        if len(longs) >= 2:
            trend = 1 if longs[-1]["num"] > longs[0]["num"] else -1
        else:
            trend = 1 if valid_infos[-1]["num"] > valid_infos[0]["num"] else -1

    def _digits_match(raw_digits: str, inferred_digits: str) -> bool:
        if not raw_digits:
            return True
        if raw_digits in inferred_digits or inferred_digits in raw_digits:
            return True
        if len(inferred_digits) > 1 and (
            raw_digits == inferred_digits[1:] or raw_digits == inferred_digits[:-1]
        ):
            return True
        return _edit_distance(raw_digits, inferred_digits) <= 1

    for idx, (first, _) in enumerate(pile_rows):
        text = first.get("text", "")
        raw = text.strip() if text else ""

        # 只处理桩号相关文本
        if raw and not re.match(r"^[Z2\d\.\,\;\:\-A-Da-d]+$", raw):
            continue

        raw_info = _pile_numeric_info(raw) if raw else None

        # 判断是否需要推断：空、无效、或有效但位数明显比邻居短
        needs_infer = False
        if not raw or not _is_valid_pile_number(raw):
            needs_infer = True
        elif raw_info and len(raw_info["digits"]) < 3:
            for v in valid_infos:
                if v["idx"] != idx and len(v["digits"]) > len(raw_info["digits"]) and raw_info["digits"] in v["digits"]:
                    needs_infer = True
                    break

        if not needs_infer:
            continue

        # 找前后最近的两个有效桩号
        prev_valid = None
        next_valid = None
        for j in range(idx - 1, -1, -1):
            t = pile_rows[j][0].get("text", "")
            if _is_valid_pile_number(t):
                prev_valid = t
                break
        for j in range(idx + 1, len(pile_rows)):
            t = pile_rows[j][0].get("text", "")
            if _is_valid_pile_number(t):
                next_valid = t
                break

        if not prev_valid and not next_valid:
            continue

        inferred = None

        # 情况 1：前后都有效且正好差一个
        if prev_valid and next_valid:
            inferred = _expected_between(prev_valid, next_valid)

        # 情况 2：根据趋势用下一个有效桩号推断
        if not inferred and next_valid:
            nxt = _pile_numeric_info(next_valid)
            if nxt:
                if trend == -1:
                    cand_num = nxt["num"] + 1
                elif trend == 1:
                    cand_num = nxt["num"] - 1
                else:
                    cand_num = nxt["num"] + 1
                inferred = f"Z{cand_num}{nxt['suffix']}"
                raw_digits = raw_info["digits"] if raw_info else re.sub(r"[^0-9]", "", raw)
                if not _digits_match(raw_digits, str(cand_num)):
                    inferred = None

        # 情况 3：根据趋势用上一个有效桩号推断
        if not inferred and prev_valid:
            prv = _pile_numeric_info(prev_valid)
            if prv:
                if trend == -1:
                    cand_num = prv["num"] - 1
                elif trend == 1:
                    cand_num = prv["num"] + 1
                else:
                    cand_num = prv["num"] - 1
                inferred = f"Z{cand_num}{prv['suffix']}"
                raw_digits = raw_info["digits"] if raw_info else re.sub(r"[^0-9]", "", raw)
                if not _digits_match(raw_digits, str(cand_num)):
                    inferred = None

        if inferred:
            first["text"] = inferred
            first["inferred"] = True
            first["inferred_from"] = f"{prev_valid or '?'},{next_valid or '?'},raw={raw}"
            print(
                f"  [i] 桩号序列推断: {raw or '(空)'} -> {inferred} (趋势={'递减' if trend == -1 else '递增' if trend == 1 else '不确定'}, 参考 {prev_valid or '?'} / {next_valid or '?'})",
                file=sys.stderr,
            )

    return items

def _local_retry_pile_items(
    img: Image.Image,
    items: List[Dict[str, Any]],
    pile_col: Optional[Tuple[float, float]],
    page: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    对桩号列内识别不完整或低置信度的文本框做局部放大重识别。
    v3.4.1：专门解决手写桩号 Z 和末位数字漏识别问题（如 Z419 -> 41）。
    """
    if pile_col is None:
        return items

    retried = []
    engine = _get_rapidocr_engine(preprocess_mode="enhance")

    for it in items:
        text = it.get("text", "")
        bbox = it.get("bbox")
        conf = it.get("confidence", 0.0)
        cx = _center_x(it)

        # 只对桩号列内、疑似不完整的文本框重试
        if not (pile_col[0] <= cx <= pile_col[1]) or not bbox:
            retried.append(it)
            continue

        needs_retry = False
        # 置信度低 或 文本长度明显不足（正常桩号 Z42D/Z418 至少 3~4 字符）
        if conf < 0.80:
            needs_retry = True
        if text and len(text.strip()) <= 3 and re.match(r"^[\dA-Za-z\.\,\;\:\-]+$", text.strip()):
            needs_retry = True
        if text and not _looks_like_pile_number(text):
            needs_retry = True

        if not needs_retry:
            retried.append(it)
            continue

        x1, y1, x2, y2 = [int(v) for v in bbox]
        # 给一定边距，确保字符完整
        margin_x = int((x2 - x1) * 0.25)
        margin_y = int((y2 - y1) * 0.25)
        x1 = max(0, x1 - margin_x)
        y1 = max(0, y1 - margin_y)
        x2 = min(img.size[0], x2 + margin_x)
        y2 = min(img.size[1], y2 + margin_y)

        if x2 <= x1 or y2 <= y1:
            retried.append(it)
            continue

        try:
            cell_img = img.crop((x1, y1, x2, y2))
            cell_proc = _enhance_cell_image(cell_img, scale=2.2)
            result, _ = engine(cell_proc)
            cell_items = _rapidocr_result_to_struct(result, page=page)
            if cell_items:
                # 合并同一单元格内多个文本框
                new_text = "".join(cit.get("text", "").replace(" ", "") for cit in cell_items)
                new_conf = sum(cit.get("confidence", 0.0) for cit in cell_items) / len(cell_items)
                if new_text:
                    it = dict(it)
                    it["text"] = new_text
                    it["confidence"] = max(conf, new_conf)
                    it["engine"] = "RapidOCR(local-retry)"
                    it["local_retry"] = True
        except Exception as e:
            print(f"  [!] 桩号局部重识别失败: {e}", file=sys.stderr)

        retried.append(it)

    return retried


# ═══════════════════════════════════════════════════
# RapidOCR 单图/单页识别（含多策略重试）
# ═══════════════════════════════════════════════════
def _ocr_single_image_rapidocr(
    img: Image.Image,
    page: Optional[int] = None,
    preprocess_modes: List[str] = None,
) -> List[Dict[str, Any]]:
    """对单张图片用 RapidOCR 多策略识别，合并去重。"""
    if preprocess_modes is None:
        preprocess_modes = ["default", "enhance", "binarize"]

    all_items = []

    for mode in preprocess_modes:
        try:
            proc_img = _preprocess_for_ocr(img, mode=mode)
            engine = _get_rapidocr_engine(preprocess_mode=mode)
            result, _ = engine(proc_img)
            items = _rapidocr_result_to_struct(result, page=page)
            for it in items:
                it["preprocess"] = mode
                all_items.append(it)
        except Exception as e:
            print(f"  [!] RapidOCR {mode} 模式失败: {e}", file=sys.stderr)

    # 合并重复框
    all_items = _merge_overlapping_items(all_items, iou_threshold=0.45)

    # 按 bbox 重新排序
    all_items.sort(key=lambda it: (it.get("bbox", [0, 0, 0, 0])[1], it.get("bbox", [0, 0, 0, 0])[0]))

    # 检测桩号列位置
    img_width = img.size[0] if hasattr(img, "size") else 1000
    pile_col = _detect_pile_column(all_items, img_width)
    pile_mode = _detect_pile_number_mode(all_items) or pile_col is not None

    if pile_mode:
        print(f"  [i] 检测到桩号列模式 (bbox={pile_col})，对 Z/2 混淆进行后处理修正", file=sys.stderr)

    # 对桩号列内不完整/低置信度文本做局部放大重识别
    if pile_col is not None:
        all_items = _local_retry_pile_items(img, all_items, pile_col, page=page)

    # 应用领域后处理
    for it in all_items:
        is_pile = _is_in_pile_column(it, pile_col)
        it["text"] = _domain_correct_text(it["text"], is_pile_column=is_pile, pile_mode_detected=pile_mode)

    # 基于同行上下文推断缺失桩号（仅对桩号模式页面）
    if pile_mode:
        all_items = _infer_pile_by_sequence(all_items)

    return all_items


def ocr_image_rapidocr(image_path: str, use_table: bool = False) -> Tuple[List[Dict[str, Any]], float]:
    """用 RapidOCR 识别单张图片。"""
    from PIL import Image
    img = Image.open(image_path)

    if use_table:
        return _ocr_with_table(img, page=None)

    items = _ocr_single_image_rapidocr(img)
    avg_score = sum(it["confidence"] for it in items) / len(items) if items else 0.0
    return items, avg_score


def ocr_pdf_rapidocr(
    pdf_path: str,
    dpi: int = 200,
    use_table: bool = False,
    page: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], float]:
    """用 RapidOCR 识别 PDF 每页（逐页处理，内存优化）。

    Args:
        page: 仅处理指定页码（从1开始）。None 则处理全部页。
    """
    all_items = []
    all_scores = []

    info = pdfinfo_from_path(pdf_path, poppler_path=_get_poppler_path() or None)
    total_pages = info.get("Pages", 1)

    if page is not None:
        page_nums = [page]
    else:
        page_nums = range(1, total_pages + 1)

    for page_num in page_nums:
        images = _safe_convert_pdf(
            pdf_path, dpi=dpi, first_page=page_num, last_page=page_num,
            preprocess_mode="raw",
        )
        if not images:
            all_items.append({
                "text": "（转换失败）",
                "confidence": 0.0,
                "bbox": None,
                "engine": "RapidOCR",
                "page": page_num,
            })
            continue

        img = images[0]
        density = _detect_text_density(img)
        try:
            if use_table:
                items, _ = _ocr_with_table(img, page=page_num)
            else:
                items = _ocr_single_image_rapidocr(img, page=page_num)

            # 空页但文本密度高：尝试表格模式补救
            if not items and density > 0.02 and use_table is False:
                print(f"  [!] 第 {page_num} 页 RapidOCR 未检出文本，尝试表格结构检测...", file=sys.stderr)
                items, _ = _ocr_with_table(img, page=page_num)

            # 仍然空页：尝试更高 DPI
            if not items and density > 0.02:
                print(f"  [!] 第 {page_num} 页仍为空，尝试 300 DPI 重跑...", file=sys.stderr)
                retry_images = _safe_convert_pdf(
                    pdf_path, dpi=300, first_page=page_num, last_page=page_num,
                    preprocess_mode="raw",
                )
                if retry_images:
                    items = _ocr_single_image_rapidocr(retry_images[0], page=page_num)
                    for it in items:
                        it["dpi"] = 300
                    del retry_images

            all_items.extend(items)
            if items:
                all_scores.extend([it["confidence"] for it in items])
        except Exception as e:
            all_items.append({
                "text": f"（识别失败: {e}）",
                "confidence": 0.0,
                "bbox": None,
                "engine": "RapidOCR",
                "page": page_num,
            })

        del img, images
        gc.collect()

    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
    return all_items, avg_score


# ═══════════════════════════════════════════════════
# 表格结构感知 OCR（rapid_table + 自恢复布局）
# ═══════════════════════════════════════════════════
def _ocr_with_table(img: Image.Image, page: Optional[int] = None) -> Tuple[List[Dict[str, Any]], float]:
    """
    表格结构感知 OCR（v3.4 混合策略）：
    1. 先做整页 RapidOCR（快）
    2. 基于文本框 bbox 自恢复表格行和列
    3. 用 RapidTable 检测单元格 bbox 作为备选/校验
    4. 对未覆盖到的单元格做局部放大 OCR 补全
    5. 应用领域后处理规则修正 Z/2 等混淆
    """
    from PIL import Image
    if img.mode != "RGB":
        img_rgb = img.convert("RGB")
    else:
        img_rgb = img

    img_width, img_height = img.size

    # 1. 整页 OCR 一次
    page_items = _ocr_single_image_rapidocr(img, page=page)

    # 2. 自恢复表格布局
    rows = _cluster_items_into_rows(page_items)
    print(f"  [i] 自恢复表格布局：{len(rows)} 行", file=sys.stderr)

    # 3. 尝试用 RapidTable 获取更精确的单元格 bbox
    table_cells = []
    table_engine = _get_rapid_table_engine()
    if table_engine is not None:
        try:
            result = table_engine(img_rgb)
            table_cells = _parse_rapid_table_output(result)
            print(f"  [i] RapidTable 检测到 {len(table_cells)} 个单元格", file=sys.stderr)
        except Exception as e:
            print(f"  [!] RapidTable 检测失败: {e}", file=sys.stderr)

    # 如果 RapidTable 只返回 1 个或 0 个单元格，说明它把整个页面当成了一个单元格，弃用
    if len(table_cells) <= 1:
        table_cells = []

    # 4. 构造带 cell 信息的 items
    cell_results = []

    if table_cells:
        # 用 RapidTable 的单元格 bbox 来分配文本
        cols = set(c.get("col", 0) for c in table_cells)
        first_col = min(cols) if cols else 0
        matched_ids = set()

        for cell in table_cells:
            bbox = cell.get("bbox")
            col = cell.get("col", 0)
            row = cell.get("row", 0)
            if not bbox or len(bbox) != 4:
                continue

            # 找与该单元格重叠度最大的文本框
            best_item = None
            best_score = 0.3
            for it in page_items:
                it_bbox = it.get("bbox")
                if not it_bbox or id(it) in matched_ids:
                    continue
                score = _bbox_min_overlap(bbox, it_bbox)
                if score > best_score:
                    best_score = score
                    best_item = it

            if best_item:
                matched_ids.add(id(best_item))
                cell_results.append({
                    "text": best_item["text"],
                    "confidence": best_item["confidence"],
                    "bbox": bbox,
                    "engine": "RapidOCR+Table",
                    "page": page,
                    "cell": {"row": row, "col": col},
                })
            else:
                # 局部补全：先快速判断单元格是否有内容，避免对所有空单元格都跑 OCR
                local_text = ""
                if _cell_likely_has_content(img, bbox):
                    local_text = _ocr_cell_local(img, bbox, page=page)
                cell_results.append({
                    "text": local_text,
                    "confidence": 0.6 if local_text else 0.0,
                    "bbox": bbox,
                    "engine": "RapidOCR+Table(local)",
                    "page": page,
                    "cell": {"row": row, "col": col},
                })

        # 未匹配到单元格的文本框也保留
        for it in page_items:
            if id(it) not in matched_ids:
                cell_results.append(it)
    else:
        # 没有 RapidTable 结果时，用自恢复的行 + 列分配
        # 估算列中心
        col_centers = _estimate_column_centers(page_items, img_width)

        for row_idx, row in enumerate(rows):
            for it in row:
                col_idx = _assign_column(it, col_centers)
                cell_results.append({
                    "text": it["text"],
                    "confidence": it["confidence"],
                    "bbox": it.get("bbox"),
                    "engine": "RapidOCR+Layout",
                    "page": page,
                    "cell": {"row": row_idx, "col": col_idx},
                })

    avg_score = sum(it["confidence"] for it in cell_results if it.get("confidence", 0) > 0) / max(
        1, sum(1 for it in cell_results if it.get("confidence", 0) > 0)
    )
    return cell_results, avg_score


def _estimate_column_centers(items: List[Dict[str, Any]], img_width: int) -> List[float]:
    """基于文本框 x 坐标估计列中心。"""
    if not items:
        return []

    centers = [_center_x(it) for it in items if it.get("bbox")]
    if not centers:
        return []

    centers.sort()
    gaps = [centers[i] - centers[i - 1] for i in range(1, len(centers))]
    if not gaps:
        return centers

    gaps_sorted = sorted(gaps)
    median_gap = gaps_sorted[len(gaps_sorted) // 2]
    q3 = gaps_sorted[3 * len(gaps_sorted) // 4] if len(gaps_sorted) >= 4 else median_gap * 2
    gap_threshold = max(median_gap * 2.5, q3 * 1.5, img_width * 0.035)

    col_centers = [centers[0]]
    current_sum = centers[0]
    current_count = 1

    for i in range(1, len(centers)):
        if gaps[i - 1] > gap_threshold:
            col_centers.append(current_sum / current_count)
            current_sum = centers[i]
            current_count = 1
        else:
            current_sum += centers[i]
            current_count += 1

    if current_count > 0:
        col_centers.append(current_sum / current_count)

    return col_centers


def _assign_column(it: Dict[str, Any], col_centers: List[float]) -> int:
    """把文本框分配到最近的列。"""
    if not col_centers:
        return 0
    cx = _center_x(it)
    best_col = 0
    best_dist = float('inf')
    col_width = (col_centers[-1] - col_centers[0]) / len(col_centers) if len(col_centers) > 1 else 100
    for idx, center in enumerate(col_centers):
        dist = abs(cx - center)
        if dist < best_dist and dist < col_width * 0.8:
            best_dist = dist
            best_col = idx
    return best_col


def _cell_likely_has_content(img: Image.Image, bbox: List[float]) -> bool:
    """快速判断单元格内是否可能有文字（基于非白像素比例）。"""
    if not bbox or len(bbox) != 4:
        return False
    x1, y1, x2, y2 = [int(v) for v in bbox]
    if x2 <= x1 or y2 <= y1:
        return False
    try:
        import numpy as np
        cell = img.crop((x1, y1, x2, y2)).convert("L")
        arr = np.array(cell)
        non_white = np.sum(arr < 240)
        ratio = float(non_white) / arr.size
        return ratio > 0.03
    except Exception:
        return True


def _ocr_cell_local(img: Image.Image, bbox: List[float], page: Optional[int] = None) -> str:
    """对单个单元格 bbox 做局部放大 OCR。"""
    if not bbox or len(bbox) != 4:
        return ""
    x1, y1, x2, y2 = [int(v) for v in bbox]
    if x2 <= x1 or y2 <= y1:
        return ""
    try:
        cell_img = img.crop((x1, y1, x2, y2))
        cell_proc = _enhance_cell_image(cell_img, scale=1.5)
        engine = _get_rapidocr_engine(preprocess_mode="enhance")
        result, _ = engine(cell_proc)
        cell_items = _rapidocr_result_to_struct(result, page=page)
        if cell_items:
            return " ".join(it["text"] for it in cell_items)
    except Exception as e:
        print(f"  [!] 单元格局部 OCR 失败: {e}", file=sys.stderr)
    return ""


def _looks_like_valid_cell(text: str) -> bool:
    """判断单元格内容是否像是有效数据（非空且不是乱码）。"""
    if not text or not text.strip():
        return False
    t = text.strip()
    if re.search(r"[\d\u4e00-\u9fa5a-zA-Z]", t):
        return True
    return False


def _parse_table_html(html: str) -> List[Dict[str, Any]]:
    """从 RapidTable 返回的 HTML 中简单提取 td 单元格。"""
    cells = []
    row_idx = 0
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        for col_idx, td in enumerate(tds):
            text = re.sub(r"<[^>]+>", "", td).strip()
            cells.append({"row": row_idx, "col": col_idx, "text": text, "bbox": None})
        row_idx += 1
    return cells


def _parse_rapid_table_output(result) -> List[Dict[str, Any]]:
    """
    兼容 RapidTable 多种返回格式：
    - dict: {'cells': [...], 'html': ...}
    - RapidTableOutput: 有 cell_bboxes / logic_points / pred_htmls 等属性
    - list: 直接是 cell 列表
    """
    cells = []

    if isinstance(result, list):
        return result

    if isinstance(result, dict):
        if "cells" in result and isinstance(result["cells"], list):
            return result["cells"]
        if "html" in result:
            return _parse_table_html(result["html"])
        return cells

    try:
        bboxes = getattr(result, "cell_bboxes", None)
        logic = getattr(result, "logic_points", None)
        pred_htmls = getattr(result, "pred_htmls", None)

        if bboxes is not None and logic is not None:
            try:
                import numpy as np
                bboxes_arr = np.asarray(bboxes)
                logic_arr = np.asarray(logic)

                if bboxes_arr.ndim == 3 and bboxes_arr.shape[0] == 1:
                    bboxes_arr = bboxes_arr[0]
                if logic_arr.ndim == 3 and logic_arr.shape[0] == 1:
                    logic_arr = logic_arr[0]

                n = min(len(bboxes_arr), len(logic_arr))
                for idx in range(n):
                    box = bboxes_arr[idx]
                    lp = logic_arr[idx]

                    box_arr = [float(v) for v in np.asarray(box).flatten().tolist()]
                    if len(box_arr) >= 8:
                        xs = box_arr[0::2]
                        ys = box_arr[1::2]
                        bbox = [min(xs), min(ys), max(xs), max(ys)]
                    elif len(box_arr) == 4:
                        bbox = box_arr
                    else:
                        bbox = None

                    lp_arr = [int(v) for v in np.asarray(lp).flatten().tolist()]
                    if len(lp_arr) >= 4:
                        row_start, row_end, col_start, col_end = lp_arr[:4]
                    else:
                        row_start = row_end = col_start = col_end = idx

                    cells.append({
                        "row": row_start,
                        "col": col_start,
                        "row_end": row_end,
                        "col_end": col_end,
                        "bbox": bbox,
                        "text": "",
                    })
                return cells
            except Exception as e:
                print(f"  [!] 解析 RapidTableOutput cell_bboxes/logic_points 失败: {e}", file=sys.stderr)

        if pred_htmls:
            html = pred_htmls[0] if isinstance(pred_htmls, list) else str(pred_htmls)
            return _parse_table_html(html)
    except Exception as e:
        print(f"  [!] 解析 RapidTableOutput 失败: {e}", file=sys.stderr)

    return cells


# ═══════════════════════════════════════════════════
# 单元格图像增强与领域后处理
# ═══════════════════════════════════════════════════
def _enhance_cell_image(cell_img: Image.Image, scale: float = 2.0) -> Image.Image:
    """对表格单元格做针对性增强：轻微放大 + 锐化 + 对比度。"""
    from PIL import ImageEnhance, ImageFilter

    w, h = cell_img.size
    if w <= 0 or h <= 0:
        return cell_img

    gray = cell_img.convert("L")
    bbox = gray.getbbox()
    if bbox and bbox[2] - bbox[0] > 5 and bbox[3] - bbox[1] > 5:
        cell_img = cell_img.crop(bbox)

    if scale != 1.0:
        new_size = (int(cell_img.width * scale), int(cell_img.height * scale))
        cell_img = cell_img.resize(new_size, Image.LANCZOS)

    enhancer = ImageEnhance.Contrast(cell_img.convert("RGB") if cell_img.mode != "RGB" else cell_img)
    cell_img = enhancer.enhance(1.3)
    enhancer = ImageEnhance.Sharpness(cell_img)
    cell_img = enhancer.enhance(1.5)

    pad = 8
    new_w, new_h = cell_img.width + pad * 2, cell_img.height + pad * 2
    padded = Image.new(cell_img.mode, (new_w, new_h), "white")
    padded.paste(cell_img, (pad, pad))
    return padded


# ═══════════════════════════════════════════════════
# PaddleOCR 识别
# ═══════════════════════════════════════════════════
def _paddleocr_predict(engine, image_path: str):
    """兼容 PaddleOCR 2.x (ocr) 与 3.x (predict)。"""
    if hasattr(engine, "predict") and callable(getattr(engine, "predict")):
        try:
            return list(engine.predict(image_path))
        except TypeError:
            pass
    return engine.ocr(str(image_path), cls=True)


def ocr_image_paddleocr(image_path: str) -> Tuple[List[Dict[str, Any]], float]:
    if not HAS_PADDLEOCR:
        if not _ensure_paddleocr_installed():
            return [], 0.0
    engine = _get_paddleocr_engine()
    if engine is None:
        return [], 0.0

    from PIL import Image
    img = Image.open(image_path)
    img = _preprocess_for_ocr(img, mode="default")
    tmp_dir = Path(tempfile.gettempdir()) / "trae_paddleocr"
    tmp_dir.mkdir(exist_ok=True)
    tmp_path = tmp_dir / f"paddle_{os.getpid()}.png"
    img.save(tmp_path, "PNG")
    try:
        result = _paddleocr_predict(engine, str(tmp_path))
        items = _paddleocr_result_to_struct(result[0] if result and isinstance(result, list) else result)
        avg_score = sum(it["confidence"] for it in items) / len(items) if items else 0.0
        return items, avg_score
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass


def ocr_pdf_paddleocr(
    pdf_path: str, dpi: int = 200, page: Optional[int] = None
) -> Tuple[List[Dict[str, Any]], float]:
    if not HAS_PADDLEOCR:
        if not _ensure_paddleocr_installed():
            return [], 0.0
    engine = _get_paddleocr_engine()
    if engine is None:
        return [], 0.0

    all_items = []
    all_scores = []

    info = pdfinfo_from_path(pdf_path, poppler_path=_get_poppler_path() or None)
    total_pages = info.get("Pages", 1)

    if page is not None:
        page_nums = [page]
    else:
        page_nums = range(1, total_pages + 1)

    tmp_dir = Path(tempfile.gettempdir()) / "trae_paddleocr"
    tmp_dir.mkdir(exist_ok=True)

    for page_num in page_nums:
        images = _safe_convert_pdf(
            pdf_path, dpi=dpi, first_page=page_num, last_page=page_num,
            preprocess_mode="raw",
        )
        if not images:
            continue
        img = _preprocess_for_ocr(images[0], mode="default")
        tmp_path = tmp_dir / f"paddle_p{page_num}_{os.getpid()}.png"
        img.save(tmp_path, "PNG")
        try:
            result = _paddleocr_predict(engine, str(tmp_path))
            items = _paddleocr_result_to_struct(
                result[0] if result and isinstance(result, list) else result,
                page=page_num,
            )
            all_items.extend(items)
            if items:
                all_scores.extend([it["confidence"] for it in items])
        except Exception as e:
            print(f"  [!] PaddleOCR 第 {page_num} 页失败: {e}", file=sys.stderr)
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass
        del img, images
        gc.collect()

    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
    return all_items, avg_score


# ═══════════════════════════════════════════════════
# Tesseract 识别
# ═══════════════════════════════════════════════════
def ocr_image_tesseract(image_path: str, lang: str = "chi_sim+eng") -> str:
    img = Image.open(image_path)
    img = _preprocess_for_ocr(img, mode="enhance")
    return pytesseract.image_to_string(img, lang=lang)


def ocr_pdf_tesseract(pdf_path: str, lang: str = "chi_sim+eng", dpi: int = 200) -> str:
    info = pdfinfo_from_path(pdf_path, poppler_path=_get_poppler_path() or None)
    total_pages = info.get("Pages", 1)

    parts = []
    for page_num in range(1, total_pages + 1):
        images = _safe_convert_pdf(
            pdf_path, dpi=dpi, first_page=page_num, last_page=page_num,
            preprocess_mode="enhance",
        )
        if not images:
            parts.append(f"=== 第 {page_num} 页 ===\n（转换失败）\n")
            continue
        img = images[0]
        try:
            text = pytesseract.image_to_string(img, lang=lang)
            parts.append(f"=== 第 {page_num} 页 ===\n{text}\n")
        except Exception as e:
            parts.append(f"=== 第 {page_num} 页 ===\n（识别失败: {e}）\n")
        del img, images
        gc.collect()
    return "\n".join(parts)


# ═══════════════════════════════════════════════════
# Vision API 识别
# ═══════════════════════════════════════════════════
def ocr_image_api(image_path: str, api_type: str = None, api_key: str = None) -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    from vision_providers import ocr_with_api, get_best_provider, detect_available_providers

    provider = api_type or get_best_provider()
    if not provider:
        return ""

    result = ocr_with_api(image_path, provider=provider)
    if result.get("error"):
        print(f"  [!] Vision API 调用失败 ({provider}): {result['error']}", file=sys.stderr)
        return ""
    return result.get("text", "")


# ═══════════════════════════════════════════════════
# 结构化结果后处理
# ═══════════════════════════════════════════════════
def _struct_to_text(items: List[Dict[str, Any]]) -> str:
    """将结构化 OCR 结果按页面组织为文本。优先使用表格行聚类输出。"""
    if not items:
        return ""

    has_cell = any(it.get("cell") for it in items)
    if has_cell:
        pages = {}
        for it in items:
            page = it.get("page", 1)
            cell = it.get("cell", {})
            row = cell.get("row", 0)
            col = cell.get("col", 0)
            pages.setdefault(page, {}).setdefault(row, {})[col] = it.get("text", "")
        parts = []
        for page in sorted(pages.keys()):
            parts.append(f"=== 第 {page} 页 ===")
            rows = pages[page]
            for row in sorted(rows.keys()):
                cols = rows[row]
                texts = [cols.get(c, "") for c in sorted(cols.keys())]
                parts.append("  ".join(texts))
            parts.append("")
        return "\n".join(parts)

    pages = {}
    no_page_items = []
    for it in items:
        page = it.get("page")
        if page is None:
            no_page_items.append(it)
        else:
            pages.setdefault(page, []).append(it)

    parts = []
    for page in sorted(pages.keys()):
        parts.append(f"=== 第 {page} 页 ===")
        rows = _cluster_items_into_rows(pages[page])
        for row in rows:
            texts = [it.get("text", "") for it in row]
            parts.append("  ".join(texts))
        parts.append("")

    if no_page_items:
        parts.append("=== 未分页 ===")
        rows = _cluster_items_into_rows(no_page_items)
        for row in rows:
            texts = [it.get("text", "") for it in row]
            parts.append("  ".join(texts))
    return "\n".join(parts)


# ═══════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════
def ocr_image(
    image_path: str,
    lang: str = "chi_sim+eng",
    engine: str = "rapid",
    use_table: bool = False,
) -> dict:
    """OCR 识别单张图片。"""
    items = []
    engine_used = "none"
    score = 0.0

    if engine in ("rapid", "auto") and HAS_RAPIDOCR:
        try:
            items, score = ocr_image_rapidocr(image_path, use_table=use_table)
            if items:
                engine_used = "RapidOCR" if not use_table else "RapidOCR+Table"
        except Exception as e:
            print(f"  [!] RapidOCR 失败: {e}", file=sys.stderr)
        finally:
            gc.collect()

    if engine == "auto" and HAS_PADDLEOCR and (not items or score < 0.55 or len(items) < 3):
        print("  [!] RapidOCR 结果不理想，尝试 PaddleOCR...", file=sys.stderr)
        try:
            paddle_items, paddle_score = ocr_image_paddleocr(image_path)
            if paddle_items and paddle_score > score:
                items = paddle_items
                engine_used = "PaddleOCR(auto-fallback)"
                score = paddle_score
        except Exception as e:
            print(f"  [!] PaddleOCR 失败: {e}", file=sys.stderr)
        finally:
            gc.collect()

    if engine == "paddle":
        if not HAS_PADDLEOCR:
            _ensure_paddleocr_installed()
        try:
            items, score = ocr_image_paddleocr(image_path)
            if items:
                engine_used = "PaddleOCR"
        except Exception as e:
            print(f"  [!] PaddleOCR 失败: {e}", file=sys.stderr)
        finally:
            gc.collect()

    if engine == "tesseract" and HAS_TESSERACT_DEPS:
        try:
            text = ocr_image_tesseract(image_path, lang)
            if text.strip():
                items = [{"text": text, "confidence": 0.7, "bbox": None, "engine": "Tesseract"}]
                engine_used = "Tesseract"
                score = 0.7
        except Exception as e:
            print(f"  [!] Tesseract 失败: {e}", file=sys.stderr)
        finally:
            gc.collect()

    if engine == "vision":
        try:
            text = ocr_image_api(image_path)
            if text.strip():
                items = [{"text": text, "confidence": 0.92, "bbox": None, "engine": "AI Vision"}]
                engine_used = "AI Vision"
                score = 0.92
        except Exception as e:
            print(f"  [!] Vision API 失败: {e}", file=sys.stderr)

    text = _struct_to_text(items)
    return {
        "text": text,
        "engine": engine_used,
        "confidence": score,
        "items": items,
    }


def ocr_pdf(
    pdf_path: str,
    lang: str = "chi_sim+eng",
    dpi: int = 200,
    engine: str = "rapid",
    use_table: bool = False,
    page: Optional[int] = None,
) -> dict:
    """OCR 识别 PDF。

    Args:
        page: 仅处理指定页码（从1开始）。None 则处理全部页。
    """
    items = []
    engine_used = "none"
    score = 0.0

    if not HAS_PDF2IMAGE:
        return {"text": "", "engine": "none", "confidence": 0.0, "items": [], "error": "pdf2image 未安装"}

    if engine in ("rapid", "auto") and HAS_RAPIDOCR:
        try:
            items, score = ocr_pdf_rapidocr(pdf_path, dpi=dpi, use_table=use_table, page=page)
            if items:
                engine_used = "RapidOCR" if not use_table else "RapidOCR+Table"
        except Exception as e:
            print(f"  [!] RapidOCR PDF 失败: {e}", file=sys.stderr)
        finally:
            gc.collect()

    if engine == "auto" and HAS_PADDLEOCR and (not items or score < 0.50 or len(items) < 10):
        print("  [!] RapidOCR 结果不理想，尝试 PaddleOCR...", file=sys.stderr)
        try:
            paddle_items, paddle_score = ocr_pdf_paddleocr(pdf_path, dpi, page=page)
            if paddle_items and paddle_score > score:
                items = paddle_items
                engine_used = "PaddleOCR(auto-fallback)"
                score = paddle_score
        except Exception as e:
            print(f"  [!] PaddleOCR 失败: {e}", file=sys.stderr)
        finally:
            gc.collect()

    if engine == "paddle":
        if not HAS_PADDLEOCR:
            _ensure_paddleocr_installed()
        try:
            items, score = ocr_pdf_paddleocr(pdf_path, dpi, page=page)
            if items:
                engine_used = "PaddleOCR"
        except Exception as e:
            print(f"  [!] PaddleOCR PDF 失败: {e}", file=sys.stderr)
        finally:
            gc.collect()

    if engine == "tesseract" and HAS_TESSERACT_DEPS:
        try:
            text = ocr_pdf_tesseract(pdf_path, lang, dpi)
            if text.strip():
                items = [{"text": text, "confidence": 0.7, "bbox": None, "engine": "Tesseract"}]
                engine_used = "Tesseract"
                score = 0.7
        except Exception as e:
            print(f"  [!] Tesseract PDF 失败: {e}", file=sys.stderr)
        finally:
            gc.collect()

    if engine == "vision":
        try:
            info = pdfinfo_from_path(pdf_path, poppler_path=_get_poppler_path() or None)
            total_pages = info.get("Pages", 1)
            parts = []
            for page_num in range(1, total_pages + 1):
                images = _safe_convert_pdf(
                    pdf_path, dpi=dpi, first_page=page_num, last_page=page_num,
                    preprocess_mode="raw",
                )
                if not images:
                    continue
                img = images[0]
                tmp_dir = Path(tempfile.gettempdir()) / "trae_ocr_vision"
                tmp_dir.mkdir(exist_ok=True)
                tmp_path = tmp_dir / f"_tmp_page_{page_num}.png"
                img.save(tmp_path)
                try:
                    text = ocr_image_api(str(tmp_path))
                    parts.append(f"=== 第 {page_num} 页 ===\n{text}\n")
                finally:
                    tmp_path.unlink(missing_ok=True)
                del img, images
                gc.collect()
            text = "\n".join(parts)
            if text.strip():
                items = [{"text": text, "confidence": 0.92, "bbox": None, "engine": "AI Vision"}]
                engine_used = "AI Vision"
                score = 0.92
        except Exception as e:
            print(f"  [!] Vision API PDF 失败: {e}", file=sys.stderr)

    text = _struct_to_text(items)
    return {
        "text": text,
        "engine": engine_used,
        "confidence": score,
        "items": items,
    }


# ═══════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="扫描件 OCR（v3.4：RapidOCR 优化版，表格自恢复）\n"
                    "默认只用 RapidOCR；需要 PaddleOCR 时显式指定 --engine paddle。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file", help="图片或 PDF 文件路径")
    parser.add_argument("--lang", default="chi_sim+eng", help="Tesseract 备选用语言")
    parser.add_argument("--out", help="输出文本文件路径（默认 stdout）")
    parser.add_argument("--json-out", help="输出结构化 JSON 文件路径（可选）")
    parser.add_argument("--dpi", type=int, default=200, help="PDF 转图 DPI，默认 200")
    parser.add_argument(
        "--engine", choices=["rapid", "paddle", "tesseract", "vision", "auto"], default="rapid",
        help="OCR 引擎：rapid(默认)/paddle/tesseract/vision/auto"
    )
    parser.add_argument(
        "--use-table", action="store_true",
        help="启用表格结构感知（需要 rapid-table，会自动尝试安装）",
    )
    parser.add_argument(
        "--preprocess", choices=["default", "enhance", "binarize", "gray", "raw"], default="default",
        help="图像预处理模式（仅影响输出显示，多策略重试内部已包含）",
    )
    parser.add_argument(
        "--page", type=int, default=None,
        help="只处理指定页码（从1开始）",
    )
    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"❌ 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(1)

    if args.use_table and not HAS_RAPID_TABLE:
        _ensure_rapid_table_installed()

    engines = []
    if HAS_RAPIDOCR:
        engines.append("RapidOCR")
    if HAS_PADDLEOCR:
        engines.append("PaddleOCR")
    if HAS_TESSERACT_DEPS:
        engines.append("Tesseract")
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from vision_providers import detect_available_providers
        available = detect_available_providers()
        if available:
            engines.append(f"Vision API ({len(available)}家)")
            has_api = True
        else:
            has_api = False
    except ImportError:
        has_api = False

    if not engines:
        print(
            "❌ 未安装任何 OCR 引擎。请运行：\n"
            "   pip install rapidocr-onnxruntime Pillow pdf2image requests\n"
            "   或设置 Vision API 环境变量（详见 vision_providers.py）",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.engine == "vision" and not has_api:
        print(
            "❌ vision 模式需要 Vision API Key。请设置以下任一环境变量：\n"
            "   DASHSCOPE_API_KEY / ARK_API_KEY / ZHIPU_API_KEY / MOONSHOT_API_KEY /\n"
            "   SILICONFLOW_API_KEY / BAIDU_API_KEY / OPENAI_API_KEY",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  [i] 可用引擎: {', '.join(engines)}", file=sys.stderr)
    print(f"  [i] 当前引擎: {args.engine} | DPI: {args.dpi} | 表格感知: {args.use_table}", file=sys.stderr)
    if args.page:
        print(f"  [i] 仅处理第 {args.page} 页", file=sys.stderr)

    suffix = Path(args.file).suffix.lower()

    if suffix == ".pdf":
        result = ocr_pdf(
            args.file, args.lang, args.dpi,
            engine=args.engine, use_table=args.use_table, page=args.page,
        )
    else:
        result = ocr_image(args.file, args.lang, engine=args.engine, use_table=args.use_table)

    if args.out:
        Path(args.out).write_text(result["text"], encoding="utf-8")
        print(
            f"✅ OCR 完成，输出 {len(result['text'])} 字符到 {args.out}\n"
            f"   引擎: {result['engine']}\n"
            f"   置信度: {result['confidence']:.1%}",
            file=sys.stderr,
        )
    else:
        print(result["text"])

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"   结构化 JSON: {args.json_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
