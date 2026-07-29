"""
扫描件 OCR 脚本（v5.0：API-First 策略，Vision API 优先 → PaddleOCR 备选 → Tesseract 兜底）
============================================================================================

用途：对扫描件图片或 PDF 进行 OCR 识别。
策略（v5.0 API-First）：
- 默认 --engine auto：Vision API 优先（自动选择最便宜可用Provider）→ PaddleOCR 本地备选 → Tesseract 兜底
- 显式 --engine vision：纯 API 模式，只用 Vision API（需 API Key）
- 显式 --engine paddle：纯本地模式，只用 PaddleOCR（离线可用，需安装）
- 显式 --engine tesseract：Tesseract 紧急备选

v5.0 核心变更：
- 默认引擎从 PaddleOCR 改为 auto（API 优先）
- auto 模式自动降级：Vision API 不可用 → PaddleOCR → Tesseract
- PaddleOCR 不再是硬依赖，仅在无 API Key 或无网络时作为本地备选
- 如果只想用 API，设置环境变量后可直接运行，无需安装 PaddleOCR
- 领域后处理（桩号序列推断、Z/2 修正）保留，但仅对 PaddleOCR 结果生效

Vision API 支持 7 家 Provider（详见 vision_providers.py）：
    doubao(豆包) / qwen(通义千问) / glm(智谱) / kimi / silicon(硅基流动) / baidu(百度千帆) / openai
    设置任一环境变量即可使用，auto 模式自动选最便宜的。

使用方式：
    python scripts/ocr_image.py <文件> --out <输出>              # 默认 API 优先
    python scripts/ocr_image.py <文件> --engine vision --out <输出>  # 纯 API
    python scripts/ocr_image.py <文件> --engine paddle --out <输出>  # 纯本地
    python scripts/ocr_image.py <文件> --engine tesseract --out <输出>  # Tesseract

前置依赖：
    pip install Pillow pdf2image requests opencv-python
    # API 模式：只需设置环境变量，无需安装 PaddleOCR
    # 本地模式（--engine paddle）：需额外 pip install paddleocr==2.8.1 paddlepaddle==2.6.2
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


# ═══════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════
MAX_IMAGE_SIDE = 2400
MIN_IMAGE_SIDE = 800
PILE_NUMBER_PREFIXES = ["Z", "2"]  # 2 是 Z 的 OCR 误识别


def _ensure_paddleocr_installed() -> bool:
    """尝试自动安装 PaddleOCR + PaddlePaddle（固定经 Windows 验证的稳定版本）。返回是否成功。"""
    global HAS_PADDLEOCR
    if HAS_PADDLEOCR:
        return True
    print("  [!] PaddleOCR 未安装，尝试自动安装稳定版本...", file=sys.stderr)
    try:
        import subprocess
        # Windows 实测 PaddleOCR 3.x 有 oneDNN 兼容问题，固定 2.8.1 + PaddlePaddle 2.6.2
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

    # PaddleOCR 内部有自己的 resize 和归一化，外部缩放会丢失手写细节
    # 对 paddle 模式跳过外部 resize
    if mode != "paddle":
        img = _resize_for_ocr(img)

    if mode == "raw" or mode == "paddle":
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
_paddleocr_engine = None


def _get_paddleocr_engine():
    """初始化 PaddleOCR 引擎（v4.1 官方最优配置）。

    参数依据：
    - PaddleOCR release/2.8 官方文档（whl.md / inference_args.md）
    - 民航高 DPI 扫描件 + 手写桩号场景实测调优

    关键优化参数：
    - enable_mkldnn=True: Intel CPU 深度神经网络加速（whl 包默认 False，必须显式开启）
    - cpu_threads=10: 官方默认线程数
    - ocr_version="PP-OCRv4": release/2.8 默认模型，精度优于 PP-OCRv3
    - det_max_side_len=1920: 适配高 DPI 扫描件，避免小字丢失
    - det_db_thresh=0.2: 比官方 0.3 低，提高手写弱笔画召回，同时避免 0.1 引入过多噪声框
    - det_db_box_thresh=0.4: 比官方 0.5/0.6 低，保留更多候选框
    - drop_score=0.35: 降低识别过滤阈值，保留低置信度手写结果
    - rec_batch_num=6 / cls_batch_num=6: 调低官方默认 30，降低单页峰值内存与卡顿
    """
    global _paddleocr_engine
    if _paddleocr_engine is None:
        try:
            print("  [i] 正在初始化 PaddleOCR（首次使用需下载模型，约 30MB，请耐心等待）...", file=sys.stderr)
            _paddleocr_engine = PaddleOCR(
                use_angle_cls=True,           # 方向分类器：修正扫描件方向偏差
                lang="ch",                    # 中文模型
                ocr_version="PP-OCRv4",       # release/2.8 官方默认模型，精度最优
                use_gpu=False,                # CPU 运行
                show_log=False,               # 减少日志噪声
                enable_mkldnn=True,           # Intel MKL-DNN 加速（CPU 关键优化，whl 包必须显式 True）
                cpu_threads=10,               # 官方默认线程数
                # 检测模型参数
                det_max_side_len=1920,        # 最大边长从 960 提升到 1920，适配扫描件
                det_db_thresh=0.2,            # 从 0.3 降到 0.2，提高手写弱笔画检出，控制噪声
                det_db_box_thresh=0.4,        # 从 0.5/0.6 降到 0.4，保留更多候选框
                det_db_unclip_ratio=1.6,      # 框扩张比例（官方 1.5~2.0 之间）
                use_dilation=False,           # 官方默认值
                # 识别模型参数
                drop_score=0.35,              # 从 0.5 降到 0.35，保留低分手写结果
                rec_batch_num=6,              # 调低官方默认 30，降低峰值内存与卡顿
                max_text_length=25,           # 最大文字长度
                # 分类器参数
                cls_batch_num=6,              # 调低官方默认 30，降低峰值内存与卡顿
            )
            print("  [OK] PaddleOCR 初始化完成", file=sys.stderr)
        except Exception as e:
            print(f"  [!] PaddleOCR 初始化失败: {e}", file=sys.stderr)
            _paddleocr_engine = None
    return _paddleocr_engine


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
def _paddleocr_result_to_struct(result, page: Optional[int] = None, img_width: int = 1000) -> List[Dict[str, Any]]:
    """将 PaddleOCR 结果解析为结构化 items。

    兼容两种输入：
    - 单页结果：[[[box], (text, score)], ...]
    - 多页结果：[[[[box], (text, score)], ...], ...]（自动取第一页或逐页展开）
    """
    items = []
    if not result:
        return items

    lines = []
    if isinstance(result, list):
        if len(result) == 0:
            return items
        first = result[0]
        # 判断 result 是单页 lines 还是多页 pages
        # 单页 line 结构：[box, (text, score)]，其中 box 是 4 个点的 list
        if isinstance(first, list) and len(first) == 2 and isinstance(first[0], list) and len(first[0]) == 4:
            lines = result
        elif isinstance(first, list) and len(first) > 0 and isinstance(first[0], list) and len(first[0]) == 2:
            # 多页：first 是 page = [line1, line2, ...]
            for page_idx, page_lines in enumerate(result):
                if not page_lines:
                    continue
                for line in page_lines:
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
                # 目前调用方已按页传入，多页场景暂不继续
                break
        else:
            lines = result

    for line in lines:
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

    # 应用领域后处理
    items = _apply_domain_postprocess(items, img_width)
    return items


# ═══════════════════════════════════════════════════
# 表格布局自恢复（v4.1：基于 PaddleOCR 结果）
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
    merged.sort(key=lambda x: ((x.get("bbox") or [0, 0, 0, 0])[1], (x.get("bbox") or [0, 0, 0, 0])[0]))
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
            current_row.sort(key=lambda x: (x.get("bbox") or [0, 0, 0, 0])[0])
            rows.append(current_row)
            current_row = [it]
            current_y = cy

    if current_row:
        current_row.sort(key=lambda x: (x.get("bbox") or [0, 0, 0, 0])[0])
        rows.append(current_row)
    return rows


def _detect_pile_column(items: List[Dict[str, Any]], img_width: int) -> Optional[Tuple[float, float]]:
    """
    基于表头关键词定位桩号列的 x 范围。
    返回 (x_min, x_max) 或 None。
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
            matches.sort(key=lambda x: (x.get("bbox") or [img_width, 0, 0, 0])[0])
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
        fallback.sort(key=lambda x: (x.get("bbox") or [img_width, 0, 0, 0])[0])
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
    return bool(re.match(r"^[Z2][\.\,\;\:\-]?[4-9]\d{1,2}[A-DI-Z0Oo]?$", t))


def _extract_pile_core(text: str) -> Optional[str]:
    """从桩号文本中提取核心数字部分，如 Z42D -> 42D，Z418 -> 418。"""
    if not text:
        return None
    t = text.strip()
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
    """
    if not items:
        return items

    rows = _cluster_items_into_rows(items)
    pile_rows = []
    for row in rows:
        if not row:
            continue
        first = min(row, key=lambda x: (x.get("bbox") or [float('inf'), 0, 0, 0])[0])
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
                prv, nxt = None, None
                for j in range(idx - 1, -1, -1):
                    t = pile_rows[j][0].get("text", "")
                    if _is_valid_pile_number(t):
                        prv = t
                        break
                for j in range(idx + 1, len(pile_rows)):
                    t = pile_rows[j][0].get("text", "")
                    if _is_valid_pile_number(t):
                        nxt = t
                        break
                if prv and nxt:
                    exp = _expected_between(prv, nxt)
                else:
                    exp = None
                if exp:
                    exp_info = _pile_numeric_info(exp)
                    if exp_info and _digits_match(raw_info["digits"], exp_info["digits"]):
                        needs_infer = True
                elif nxt and raw_info:
                    nxt_info = _pile_numeric_info(nxt)
                    if nxt_info and trend != 0:
                        cand = nxt_info["num"] + (1 if trend == -1 else -1)
                        if _digits_match(raw_info["digits"], str(cand)):
                            needs_infer = True

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
    engine,
    img: Image.Image,
    items: List[Dict[str, Any]],
    pile_col: Optional[Tuple[float, float]],
    page: Optional[int] = None,
    conf_threshold: float = 0.75,
    max_retries: int = 10,
) -> List[Dict[str, Any]]:
    """
    对桩号列内识别不完整或低置信度的文本框做局部放大重识别（PaddleOCR 版本）。
    v4.1：由 RapidOCR 局部重试改为 PaddleOCR 单单元格重识别；限制每页重试次数，避免极端慢。
    """
    if pile_col is None or engine is None:
        return items

    retried = []
    retry_count = 0

    for it in items:
        text = it.get("text", "")
        bbox = it.get("bbox")
        conf = it.get("confidence", 0.0)
        cx = _center_x(it)

        # 只对桩号列内、疑似不完整的文本框重试
        if not (pile_col[0] <= cx <= pile_col[1]) or not bbox:
            retried.append(it)
            continue

        # 序列推断已修正的桩号跳过重试，只处理极低置信度或极短文本
        needs_retry = False
        if conf < conf_threshold:
            needs_retry = True
        if text and len(text.strip()) <= 2 and re.match(r"^[\dA-Za-z]+$", text.strip()):
            needs_retry = True

        if not needs_retry:
            retried.append(it)
            continue

        retry_count += 1
        if retry_count > max_retries:
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
            cell_proc = _enhance_cell_image(cell_img, scale=1.3)
            tmp_dir = Path(tempfile.gettempdir()) / "trae_paddleocr"
            tmp_dir.mkdir(exist_ok=True)
            tmp_path = tmp_dir / f"paddle_retry_{os.getpid()}_{id(cell_proc)}.png"
            cell_proc.save(tmp_path, "PNG")
            try:
                result = _paddleocr_predict(engine, str(tmp_path))
                cell_items = _paddleocr_result_to_struct(
                    result[0] if result and isinstance(result, list) else result,
                    page=page,
                    img_width=cell_proc.size[0],
                )
                if cell_items:
                    # 合并同一单元格内多个文本框
                    new_text = "".join(cit.get("text", "").replace(" ", "") for cit in cell_items)
                    new_conf = sum(cit.get("confidence", 0.0) for cit in cell_items) / len(cell_items)
                    if new_text:
                        it = dict(it)
                        it["text"] = new_text
                        it["confidence"] = max(conf, new_conf)
                        it["engine"] = "PaddleOCR(local-retry)"
                        it["local_retry"] = True
            finally:
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
        except Exception as e:
            print(f"  [!] 桩号局部重识别失败: {e}", file=sys.stderr)

        retried.append(it)

    return retried


# ═══════════════════════════════════════════════════
# 单元格图像增强
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


def _ocr_single_image_paddleocr(
    img: Image.Image,
    engine,
    page: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """对单张图片用 PaddleOCR 识别，并应用领域后处理与序列推断。"""
    from PIL import Image

    if engine is None:
        return []

    img_width = img.size[0] if hasattr(img, "size") else 1000

    tmp_dir = Path(tempfile.gettempdir()) / "trae_paddleocr"
    tmp_dir.mkdir(exist_ok=True)
    tmp_path = tmp_dir / f"paddle_page_{page or 0}_{os.getpid()}.png"

    try:
        img.save(tmp_path, "PNG")
        result = _paddleocr_predict(engine, str(tmp_path))
        items = _paddleocr_result_to_struct(
            result[0] if result and isinstance(result, list) else result,
            page=page,
            img_width=img_width,
        )
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass

    # 合并去重
    items = _merge_overlapping_items(items, iou_threshold=0.45)
    items.sort(key=lambda it: ((it.get("bbox") or [0, 0, 0, 0])[1], (it.get("bbox") or [0, 0, 0, 0])[0]))

    # 序列推断
    pile_col = _detect_pile_column(items, img_width)
    pile_mode = _detect_pile_number_mode(items) or pile_col is not None
    if pile_mode:
        items = _infer_pile_by_sequence(items)

    # 局部重试：对序列推断后仍低置信度的桩号框做局部放大重识别
    if pile_col is not None:
        items = _local_retry_pile_items(engine, img, items, pile_col, page=page, conf_threshold=0.55)

    return items


def ocr_image_paddleocr(image_path: str) -> Tuple[List[Dict[str, Any]], float]:
    if not HAS_PADDLEOCR:
        if not _ensure_paddleocr_installed():
            return [], 0.0
    engine = _get_paddleocr_engine()
    if engine is None:
        return [], 0.0

    from PIL import Image
    img = Image.open(image_path)
    img = _preprocess_for_ocr(img, mode="paddle")

    items = _ocr_single_image_paddleocr(img, engine)
    avg_score = sum(it["confidence"] for it in items) / len(items) if items else 0.0
    return items, avg_score


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

    total_pages = len(page_nums)
    for idx, page_num in enumerate(page_nums):
        print(f"  [i] OCR 第 {page_num} 页 / 共 {total_pages} 页 ...", file=sys.stderr)
        images = _safe_convert_pdf(
            pdf_path, dpi=dpi, first_page=page_num, last_page=page_num,
            preprocess_mode="raw",
        )
        if not images:
            print(f"  [!] 第 {page_num} 页 PDF 转图失败", file=sys.stderr)
            continue
        img = _preprocess_for_ocr(images[0], mode="paddle")
        density = _detect_text_density(img)
        try:
            items = _ocr_single_image_paddleocr(img, engine, page=page_num)

            # 空页但文本密度高：尝试 300 DPI 重跑
            if not items and density > 0.02:
                print(f"  [!] 第 {page_num} 页 PaddleOCR 未检出文本且密度较高，尝试 300 DPI 重跑...", file=sys.stderr)
                retry_images = _safe_convert_pdf(
                    pdf_path, dpi=300, first_page=page_num, last_page=page_num,
                    preprocess_mode="raw",
                )
                if retry_images:
                    retry_img = _preprocess_for_ocr(retry_images[0], mode="paddle")
                    items = _ocr_single_image_paddleocr(retry_img, engine, page=page_num)
                    for it in items:
                        it["dpi"] = 300
                    del retry_img, retry_images

            all_items.extend(items)
            if items:
                all_scores.extend([it["confidence"] for it in items])
        except Exception as e:
            import traceback
            print(f"  [!] PaddleOCR 第 {page_num} 页失败: {e}", file=sys.stderr)
            traceback.print_exc()
        finally:
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
# Vision API 识别（第三层兜底）
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
def _has_api_provider() -> bool:
    """检测是否有可用的 Vision API Provider。"""
    try:
        from vision_providers import detect_available_providers
        return len(detect_available_providers()) > 0
    except Exception:
        return False


def ocr_image(
    image_path: str,
    lang: str = "chi_sim+eng",
    engine: str = "auto",
    use_table: bool = False,
) -> dict:
    """OCR 识别单张图片（v5.0 API-First：auto=Vision API 优先 → PaddleOCR 备选 → Tesseract 兜底）。"""
    items = []
    engine_used = "none"
    score = 0.0

    if engine == "auto":
        # auto 模式：Vision API 优先 → PaddleOCR 备选 → Tesseract 兜底
        if _has_api_provider():
            print("  [i] auto 模式：检测到 Vision API，优先使用", file=sys.stderr)
            engine = "vision"
        elif HAS_PADDLEOCR or _ensure_paddleocr_installed():
            print("  [i] auto 模式：无 Vision API，降级为 PaddleOCR", file=sys.stderr)
            engine = "paddle"
        elif HAS_TESSERACT_DEPS:
            print("  [i] auto 模式：无 Vision API 也无 PaddleOCR，降级为 Tesseract", file=sys.stderr)
            engine = "tesseract"
        else:
            print("  [X] auto 模式：无可用 OCR 引擎", file=sys.stderr)
            engine = "none"

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
    engine: str = "auto",
    use_table: bool = False,
    page: Optional[int] = None,
) -> dict:
    """OCR 识别 PDF（v5.0 API-First：auto=Vision API 优先 → PaddleOCR 备选 → Tesseract 兜底）。

    Args:
        page: 仅处理指定页码（从1开始）。None 则处理全部页。
    """
    items = []
    engine_used = "none"
    score = 0.0

    if not HAS_PDF2IMAGE:
        return {"text": "", "engine": "none", "confidence": 0.0, "items": [], "error": "pdf2image 未安装"}

    if engine == "auto":
        if _has_api_provider():
            print("  [i] auto 模式：检测到 Vision API，优先使用", file=sys.stderr)
            engine = "vision"
        elif HAS_PADDLEOCR or _ensure_paddleocr_installed():
            print("  [i] auto 模式：无 Vision API，降级为 PaddleOCR", file=sys.stderr)
            engine = "paddle"
        elif HAS_TESSERACT_DEPS:
            print("  [i] auto 模式：无 Vision API 也无 PaddleOCR，降级为 Tesseract", file=sys.stderr)
            engine = "tesseract"
        else:
            print("  [X] auto 模式：无可用 OCR 引擎", file=sys.stderr)
            engine = "none"

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
        description="扫描件 OCR（v5.0 API-First：Vision API 优先 → PaddleOCR 备选 → Tesseract 兜底）\n"
                    "默认 auto 模式自动选择最佳可用引擎。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file", help="图片或 PDF 文件路径")
    parser.add_argument("--lang", default="chi_sim+eng", help="Tesseract 备选用语言")
    parser.add_argument("--out", help="输出文本文件路径（默认 stdout）")
    parser.add_argument("--json-out", help="输出结构化 JSON 文件路径（可选）")
    parser.add_argument("--dpi", type=int, default=200, help="PDF 转图 DPI，默认 200")
    parser.add_argument(
        "--engine", choices=["paddle", "tesseract", "vision", "auto"], default="auto",
        help="OCR 引擎：auto(默认，API优先)/vision(纯API)/paddle(纯本地)/tesseract(备选)"
    )
    parser.add_argument(
        "--use-table", action="store_true",
        help="启用表格结构感知（已废弃，保留兼容性）",
    )
    parser.add_argument(
        "--preprocess", choices=["default", "enhance", "binarize", "gray", "raw", "paddle"], default="paddle",
        help="图像预处理模式（PaddleOCR 模式跳过外部 resize）",
    )
    parser.add_argument(
        "--page", type=int, default=None,
        help="只处理指定页码（从1开始）",
    )
    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"❌ 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(1)

    engines = []
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
            "   pip install paddleocr==2.8.1 paddlepaddle==2.6.2 opencv-python Pillow pdf2image requests\n"
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
