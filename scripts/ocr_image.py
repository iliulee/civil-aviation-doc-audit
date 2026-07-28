"""
扫描件 OCR 脚本（RapidOCR 主力，Tesseract 备选，HTTP API 兜底）
================================================================

用途：对扫描件图片或 PDF 进行 OCR 识别。
策略（v3.0 三级降级 + AI视觉模式 + 多API支持）：
- 第一层：RapidOCR（ONNX Runtime 后端）— pip 一条命令，跨平台
  内存优化：限制图片长边≤1280px、限制线程数、逐页处理+gc回收
- 第二层：Tesseract — 备选，当 RapidOCR 不可用时降级使用
- 第三层：通用 HTTP API — 兜底，不依赖任何平台特有工具

v3.0 更新：
- vision 模式改用 vision_providers.py，统一支持 7 家 Vision API
  （通义千问/豆包/智谱/Kimi/硅基流动/百度千帆/OpenAI）
- --mode vision：AI 视觉模型直接处理（手写施工资料推荐）
  对于手写中文施工记录，AI 视觉模型识别准确率显著高于 RapidOCR（~95% vs ~85%）
- --page N：只处理指定页码，用于视觉复核特定页
- 默认 DPI 200，提升手写文字识别精度
- API prompt 针对施工资料优化：强调保留字母前缀、区分易混淆数字

使用方式：
    python scripts/ocr_image.py <图片或PDF路径> [--lang chi_sim+eng] [--out <输出>] [--dpi 200]
    python scripts/ocr_image.py <PDF路径> --mode vision --out <输出>  # 手写件推荐
    python scripts/ocr_image.py <PDF路径> --mode vision --page 5 --out <输出>  # 复核第5页

前置依赖：
    pip install rapidocr-onnxruntime Pillow pdf2image requests
    （vision 模式需设置环境变量，详见 vision_providers.py）
"""

import sys
import argparse
import base64
import os
import gc
from pathlib import Path

# ═══════════════════════════════════════════════════
# 第一层：RapidOCR（主力）
# ═══════════════════════════════════════════════════
try:
    from rapidocr_onnxruntime import RapidOCR
    _rapidocr_engine = None  # 延迟初始化
    HAS_RAPIDOCR = True
except ImportError:
    HAS_RAPIDOCR = False

# ═══════════════════════════════════════════════════
# 第二层：Tesseract（备选）
# ═══════════════════════════════════════════════════
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
    ]
    for _cand in _TESSERACT_CANDIDATES:
        if _cand and Path(_cand).exists():
            pytesseract.pytesseract.tesseract_cmd = str(_cand)
            break

# ═══════════════════════════════════════════════════
# PDF 转图片（pdf2image + poppler）
# ═══════════════════════════════════════════════════
try:
    from pdf2image import convert_from_path
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False


# ── 内存优化：图片预处理 ──
MAX_IMAGE_SIDE = 1280  # OCR 前限制图片长边，防止内存爆炸


def _resize_for_ocr(img):
    """将 PIL 图片长边限制在 MAX_IMAGE_SIDE 以内，减少内存占用。"""
    if not hasattr(img, 'size'):
        return img
    w, h = img.size
    long_side = max(w, h)
    if long_side <= MAX_IMAGE_SIDE:
        return img
    scale = MAX_IMAGE_SIDE / long_side
    new_w = int(w * scale)
    new_h = int(h * scale)
    return img.resize((new_w, new_h), Image.LANCZOS)


def _get_rapidocr_engine():
    """延迟初始化 RapidOCR 引擎，配置内存优化参数。"""
    global _rapidocr_engine
    if _rapidocr_engine is None:
        # RapidOCR 构造参数（v1.x rapidocr-onnxruntime）
        # 限制检测图片长边，限制线程数，防止内存爆炸
        try:
            _rapidocr_engine = RapidOCR(
                # 检测阶段图片长边限制（默认736，降到960平衡精度和内存）
                det_limit_side_len=960,
                det_limit_type="max",
                # 线程数限制（-1=自动用全部核心，容易爆内存；固定为2更稳定）
                intra_op_num_threads=2,
                inter_op_num_threads=2,
            )
        except TypeError:
            # 某些版本不支持这些参数，用默认配置
            _rapidocr_engine = RapidOCR()
    return _rapidocr_engine


def _get_poppler_path():
    """定位 Skill 自带的 poppler bin 目录。"""
    p = Path(__file__).parent.parent / "tools" / "poppler"
    if p.exists():
        for bin_dir in p.rglob("pdftoppm.exe"):
            return str(bin_dir.parent)
    return None


# ═══════════════════════════════════════════════════
# 第一层：RapidOCR 识别
# ═══════════════════════════════════════════════════
def ocr_image_rapidocr(image_path: str) -> tuple:
    """用 RapidOCR 识别单张图片，返回 (文本, 置信度)。"""
    engine = _get_rapidocr_engine()
    result, elapse = engine(image_path)
    if result is None:
        return ("", 0.0)
    lines = []
    scores = []
    for box, text, score in result:
        lines.append(text)
        scores.append(score)
    text = "\n".join(lines)
    avg_score = sum(scores) / len(scores) if scores else 0.0
    return (text, avg_score)


def _safe_convert_pdf(pdf_path: str, dpi: int = 150, first_page=None, last_page=None):
    """处理中文路径：poppler 不支持中文路径，自动复制到临时目录再转换。"""
    import tempfile, shutil as _shutil, re
    has_non_ascii = bool(re.search(r'[^\x00-\x7F]', str(pdf_path)))
    poppler_path = _get_poppler_path()
    kwargs = {"dpi": dpi}
    if poppler_path:
        kwargs["poppler_path"] = poppler_path
    if first_page:
        kwargs["first_page"] = first_page
    if last_page:
        kwargs["last_page"] = last_page

    if not has_non_ascii:
        return convert_from_path(pdf_path, **kwargs)

    tmp_dir = Path(tempfile.gettempdir()) / "trae_ocr_tmp"
    tmp_dir.mkdir(exist_ok=True)
    tmp_pdf = tmp_dir / "input.pdf"
    try:
        _shutil.copy2(pdf_path, tmp_pdf)
        return convert_from_path(str(tmp_pdf), **kwargs)
    finally:
        pass


def ocr_pdf_rapidocr(pdf_path: str, dpi: int = 150) -> tuple:
    """
    用 RapidOCR 识别 PDF 每页，返回 (文本, 置信度)。
    内存优化：逐页处理，每页处理完立即释放。
    """
    engine = _get_rapidocr_engine()
    parts = []
    all_scores = []

    # 逐页转换+识别，不一次性加载所有页
    from pdf2image import pdfinfo_from_path
    info = pdfinfo_from_path(pdf_path, poppler_path=_get_poppler_path() or None)
    total_pages = info.get("Pages", 1)

    for page_num in range(1, total_pages + 1):
        # 只转换当前页（1页），不是全部
        images = _safe_convert_pdf(pdf_path, dpi=dpi, first_page=page_num, last_page=page_num)
        if not images:
            parts.append(f"=== 第 {page_num} 页 ===\n（转换失败）\n")
            continue

        img = images[0]
        # 预处理：限制图片尺寸
        img = _resize_for_ocr(img)

        try:
            result, elapse = engine(img)
            if result:
                lines = [text for box, text, score in result]
                scores = [score for box, text, score in result]
                parts.append(f"=== 第 {page_num} 页 ===\n" + "\n".join(lines) + "\n")
                all_scores.extend(scores)
            else:
                parts.append(f"=== 第 {page_num} 页 ===\n（识别为空）\n")
        except Exception as e:
            parts.append(f"=== 第 {page_num} 页 ===\n（识别失败: {e}）\n")

        # 立即释放当前页内存
        del img, images
        gc.collect()

    text = "\n".join(parts)
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
    return (text, avg_score)


# ═══════════════════════════════════════════════════
# 第二层：Tesseract 识别（备选）
# ═══════════════════════════════════════════════════
def ocr_image_tesseract(image_path: str, lang: str = "chi_sim+eng") -> str:
    """用 Tesseract 识别单张图片。"""
    img = Image.open(image_path)
    img = _resize_for_ocr(img)
    return pytesseract.image_to_string(img, lang=lang)


def ocr_pdf_tesseract(pdf_path: str, lang: str = "chi_sim+eng", dpi: int = 150) -> str:
    """用 Tesseract 识别 PDF 每页（逐页处理）。"""
    from pdf2image import pdfinfo_from_path
    info = pdfinfo_from_path(pdf_path, poppler_path=_get_poppler_path() or None)
    total_pages = info.get("Pages", 1)

    parts = []
    for page_num in range(1, total_pages + 1):
        images = _safe_convert_pdf(pdf_path, dpi=dpi, first_page=page_num, last_page=page_num)
        if not images:
            parts.append(f"=== 第 {page_num} 页 ===\n（转换失败）\n")
            continue
        img = images[0]
        img = _resize_for_ocr(img)
        try:
            text = pytesseract.image_to_string(img, lang=lang)
            parts.append(f"=== 第 {page_num} 页 ===\n{text}\n")
        except Exception as e:
            parts.append(f"=== 第 {page_num} 页 ===\n（识别失败: {e}）\n")
        del img, images
        gc.collect()
    return "\n".join(parts)


# ═══════════════════════════════════════════════════
# 第三层：通用 HTTP API 兜底（通过 vision_providers.py 统一调用）
# ═══════════════════════════════════════════════════
def ocr_image_api(image_path: str, api_type: str = None, api_key: str = None) -> str:
    """用云端视觉 API 识别图片（通过 vision_providers.py 统一调用 7 家 API）。"""
    # 导入 vision_providers（同目录）
    sys.path.insert(0, str(Path(__file__).parent))
    from vision_providers import ocr_with_api, get_best_provider, detect_available_providers

    # 自动检测可用 Provider
    provider = api_type or get_best_provider()
    if not provider:
        # 无可用 API Key
        return ""

    result = ocr_with_api(image_path, provider=provider)
    if result.get("error"):
        print(f"  [!] Vision API 调用失败 ({provider}): {result['error']}", file=sys.stderr)
        return ""
    return result.get("text", "")


# ═══════════════════════════════════════════════════
# 主入口：三级降级
# ═══════════════════════════════════════════════════
def ocr_image(image_path: str, lang: str = "chi_sim+eng") -> dict:
    """三级降级 OCR 识别单张图片。"""
    # 第一层：RapidOCR
    if HAS_RAPIDOCR:
        try:
            text, score = ocr_image_rapidocr(image_path)
            if text.strip():
                return {"text": text, "engine": "RapidOCR", "confidence": score}
        except Exception as e:
            print(f"  [!] RapidOCR 失败: {e}", file=sys.stderr)
        finally:
            gc.collect()

    # 第二层：Tesseract
    if HAS_TESSERACT_DEPS:
        try:
            text = ocr_image_tesseract(image_path, lang)
            if text.strip():
                return {"text": text, "engine": "Tesseract", "confidence": 0.8}
        except Exception as e:
            print(f"  [!] Tesseract 失败: {e}", file=sys.stderr)
        finally:
            gc.collect()

    # 第三层：HTTP API
    try:
        text = ocr_image_api(image_path)
        if text.strip():
            return {"text": text, "engine": "HTTP API", "confidence": 0.9}
    except Exception as e:
        print(f"  [!] HTTP API 失败: {e}", file=sys.stderr)

    return {"text": "", "engine": "none", "confidence": 0.0}


def ocr_pdf(pdf_path: str, lang: str = "chi_sim+eng", dpi: int = 150) -> dict:
    """三级降级 OCR 识别 PDF（逐页处理，内存优化）。"""
    # 第一层：RapidOCR
    if HAS_RAPIDOCR and HAS_PDF2IMAGE:
        try:
            text, score = ocr_pdf_rapidocr(pdf_path, dpi)
            if text.strip():
                return {"text": text, "engine": "RapidOCR", "confidence": score}
        except Exception as e:
            print(f"  [!] RapidOCR PDF 失败: {e}", file=sys.stderr)
        finally:
            gc.collect()

    # 第二层：Tesseract
    if HAS_TESSERACT_DEPS and HAS_PDF2IMAGE:
        try:
            text = ocr_pdf_tesseract(pdf_path, lang, dpi)
            if text.strip():
                return {"text": text, "engine": "Tesseract", "confidence": 0.8}
        except Exception as e:
            print(f"  [!] Tesseract PDF 失败: {e}", file=sys.stderr)
        finally:
            gc.collect()

    # 第三层：HTTP API（逐页）
    if HAS_PDF2IMAGE:
        try:
            from pdf2image import pdfinfo_from_path
            info = pdfinfo_from_path(pdf_path, poppler_path=_get_poppler_path() or None)
            total_pages = info.get("Pages", 1)
            parts = []
            for page_num in range(1, total_pages + 1):
                images = _safe_convert_pdf(pdf_path, dpi=dpi, first_page=page_num, last_page=page_num)
                if not images:
                    continue
                img = images[0]
                tmp_path = Path(image_path).parent / f"_tmp_page_{page_num}.png"
                img.save(tmp_path)
                text = ocr_image_api(str(tmp_path))
                tmp_path.unlink(missing_ok=True)
                parts.append(f"=== 第 {page_num} 页 ===\n{text}\n")
                del img, images
                gc.collect()
            return {"text": "\n".join(parts), "engine": "HTTP API", "confidence": 0.9}
        except Exception as e:
            print(f"  [!] HTTP API PDF 失败: {e}", file=sys.stderr)

    return {"text": "", "engine": "none", "confidence": 0.0}


def main():
    parser = argparse.ArgumentParser(
        description="扫描件 OCR（RapidOCR 主力，三级降级，内存优化）\n"
                    "v3.0：--mode vision 支持 7 家 Vision API（手写件推荐）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file", help="图片或 PDF 文件路径")
    parser.add_argument("--lang", default="chi_sim+eng", help="OCR 语言（Tesseract 备选用）")
    parser.add_argument("--out", help="输出文本文件路径（默认 stdout）")
    parser.add_argument("--dpi", type=int, default=200, help="PDF 转图 DPI，默认 200（v2.2 从150提升）")
    parser.add_argument(
        "--mode", choices=["auto", "vision"], default="auto",
        help="auto=三级降级(默认); vision=AI视觉模型优先(手写件推荐，需API Key)",
    )
    parser.add_argument(
        "--page", type=int, default=None,
        help="只处理指定页码（从1开始），用于视觉复核特定页",
    )
    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"❌ 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(1)

    # 检查可用引擎
    engines = []
    if HAS_RAPIDOCR:
        engines.append("RapidOCR")
    if HAS_TESSERACT_DEPS:
        engines.append("Tesseract")
    # 通过 vision_providers.py 检测可用 API
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

    # vision 模式检查
    if args.mode == "vision" and not has_api:
        print(
            "❌ vision 模式需要 Vision API Key。请设置以下任一环境变量：\n"
            "   DASHSCOPE_API_KEY    — 通义千问\n"
            "   ARK_API_KEY          — 豆包\n"
            "   ZHIPU_API_KEY        — 智谱\n"
            "   MOONSHOT_API_KEY     — Kimi\n"
            "   SILICONFLOW_API_KEY  — 硅基流动\n"
            "   BAIDU_API_KEY        — 百度千帆\n"
            "   OPENAI_API_KEY       — OpenAI",
            file=sys.stderr,
        )
        sys.exit(1)

    mode_label = "AI视觉优先" if args.mode == "vision" else "三级降级"
    print(f"  [i] 可用引擎: {', '.join(engines)}", file=sys.stderr)
    print(f"  [i] 模式: {mode_label} | DPI: {args.dpi} | 图片长边限制: {MAX_IMAGE_SIDE}px", file=sys.stderr)
    if args.page:
        print(f"  [i] 仅处理第 {args.page} 页", file=sys.stderr)

    suffix = Path(args.file).suffix.lower()

    # === vision 模式：AI 视觉模型直接处理 ===
    if args.mode == "vision":
        if suffix == ".pdf":
            if not HAS_PDF2IMAGE:
                print("❌ 缺少 pdf2image，无法处理 PDF。请运行：pip install pdf2image", file=sys.stderr)
                sys.exit(1)
            from pdf2image import pdfinfo_from_path
            info = pdfinfo_from_path(args.file, poppler_path=_get_poppler_path() or None)
            total_pages = info.get("Pages", 1)

            if args.page:
                page_range = [args.page]
            else:
                page_range = range(1, total_pages + 1)

            parts = []
            for page_num in page_range:
                images = _safe_convert_pdf(args.file, dpi=args.dpi, first_page=page_num, last_page=page_num)
                if not images:
                    parts.append(f"=== 第 {page_num} 页 ===\n（转换失败）\n")
                    continue
                img = images[0]
                # vision 模式不限制图片尺寸（AI 视觉模型可以处理高分辨率）
                tmp_path = Path(args.file).parent / f"_tmp_vision_p{page_num}.png"
                img.save(tmp_path)
                try:
                    text = ocr_image_api(str(tmp_path))
                    parts.append(f"=== 第 {page_num} 页 ===\n{text}\n")
                except Exception as e:
                    parts.append(f"=== 第 {page_num} 页 ===\n（视觉识别失败: {e}）\n")
                finally:
                    tmp_path.unlink(missing_ok=True)
                del img, images
                gc.collect()

            result = {"text": "\n".join(parts), "engine": "AI Vision", "confidence": 0.92}
        else:
            # 单张图片
            text = ocr_image_api(args.file)
            result = {"text": text, "engine": "AI Vision", "confidence": 0.92}

    # === auto 模式：三级降级（默认） ===
    else:
        if suffix == ".pdf":
            if not HAS_PDF2IMAGE:
                print("❌ 缺少 pdf2image，无法处理 PDF。请运行：pip install pdf2image", file=sys.stderr)
                sys.exit(1)
            result = ocr_pdf(args.file, args.lang, args.dpi)
        else:
            result = ocr_image(args.file, args.lang)

    if args.out:
        Path(args.out).write_text(result["text"], encoding="utf-8")
        print(
            f"✅ OCR 完成，输出 {len(result['text'])} 字符到 {args.out}\n"
            f"   引擎: {result['engine']}\n"
            f"   置信度: {result['confidence']:.1%}\n"
            f"   ⚠️ 置信度 <85% 的内容需人工复核",
            file=sys.stderr,
        )
    else:
        print(result["text"])


if __name__ == "__main__":
    main()
