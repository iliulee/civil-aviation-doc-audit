"""
扫描件 OCR 脚本（RapidOCR 主力，Tesseract 备选，HTTP API 兜底）
================================================================

用途：对扫描件图片或 PDF 进行 OCR 识别。
策略（v2.0 三级降级）：
- 第一层：RapidOCR（ONNX Runtime 后端）— pip 一条命令，跨平台，
  基于PaddleOCR模型，中文手写体 85%+，表格识别输出 HTML 结构
- 第二层：Tesseract — 备选，当 RapidOCR 不可用时降级使用
- 第三层：通用 HTTP API — 兜底，不依赖任何平台特有工具
  支持 OpenAI GPT-4o / Claude Vision / Gemini / 硅基流动等

使用方式：
    python scripts/ocr_image.py <图片或PDF路径> [--lang chi_sim+eng] [--out <输出>]

前置依赖：
    pip install rapidocr-onnxruntime Pillow pdf2image
    # 备选 OCR：
    pip install pytesseract  +  安装 Tesseract-OCR 引擎
"""

import sys
import argparse
import base64
import os
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


def _get_rapidocr_engine():
    """延迟初始化 RapidOCR 引擎（首次调用时加载模型）。"""
    global _rapidocr_engine
    if _rapidocr_engine is None:
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


def ocr_pdf_rapidocr(pdf_path: str, dpi: int = 200) -> tuple:
    """用 RapidOCR 识别 PDF 每页，返回 (文本, 置信度)。"""
    poppler_path = _get_poppler_path()
    kwargs = {"dpi": dpi}
    if poppler_path:
        kwargs["poppler_path"] = poppler_path
    images = convert_from_path(pdf_path, **kwargs)
    parts = []
    all_scores = []
    for i, img in enumerate(images, 1):
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        engine = _get_rapidocr_engine()
        result, elapse = engine(buf)
        if result:
            lines = [text for box, text, score in result]
            scores = [score for box, text, score in result]
            parts.append(f"=== 第 {i} 页 ===\n" + "\n".join(lines) + "\n")
            all_scores.extend(scores)
        else:
            parts.append(f"=== 第 {i} 页 ===\n（识别为空）\n")
    text = "\n".join(parts)
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
    return (text, avg_score)


# ═══════════════════════════════════════════════════
# 第二层：Tesseract 识别（备选）
# ═══════════════════════════════════════════════════
def ocr_image_tesseract(image_path: str, lang: str = "chi_sim+eng") -> str:
    """用 Tesseract 识别单张图片。"""
    img = Image.open(image_path)
    return pytesseract.image_to_string(img, lang=lang)


def ocr_pdf_tesseract(pdf_path: str, lang: str = "chi_sim+eng", dpi: int = 200) -> str:
    """用 Tesseract 识别 PDF 每页。"""
    poppler_path = _get_poppler_path()
    kwargs = {"dpi": dpi}
    if poppler_path:
        kwargs["poppler_path"] = poppler_path
    images = convert_from_path(pdf_path, **kwargs)
    parts = []
    for i, img in enumerate(images, 1):
        text = pytesseract.image_to_string(img, lang=lang)
        parts.append(f"=== 第 {i} 页 ===\n{text}\n")
    return "\n".join(parts)


# ═══════════════════════════════════════════════════
# 第三层：通用 HTTP API 兜底（跨平台，不依赖任何 Agent 平台）
# ═══════════════════════════════════════════════════
def ocr_image_api(image_path: str, api_type: str = None, api_key: str = None) -> str:
    """
    用云端视觉 API 识别图片，不依赖任何平台特有工具。
    
    支持的 api_type：
    - "openai"   — GPT-4o Vision（需 OPENAI_API_KEY）
    - "gemini"   — Google Gemini（需 GEMINI_API_KEY）
    - "siliconflow" — 硅基流动（需 SILICONFLOW_API_KEY）
    
    api_key 参数优先于环境变量。
    """
    import requests

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    # 自动选择 API
    if not api_type:
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if api_key:
            api_type = "openai"
        else:
            api_key = os.environ.get("GEMINI_API_KEY")
            if api_key:
                api_type = "gemini"
            else:
                api_key = os.environ.get("SILICONFLOW_API_KEY")
                if api_key:
                    api_type = "siliconflow"

    if not api_type or not api_key:
        return ""

    prompt = "请识别图片中所有文字内容，保持原有格式和表格结构，只输出识别到的文字。"

    if api_type == "openai":
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                    ]
                }]
            },
            timeout=60
        )
        return resp.json()["choices"][0]["message"]["content"]

    elif api_type == "gemini":
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
            json={
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/png", "data": img_b64}}
                    ]
                }]
            },
            timeout=60
        )
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    elif api_type == "siliconflow":
        resp = requests.post(
            "https://api.siliconflow.cn/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "Qwen/Qwen2-VL-72B-Instruct",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                    ]
                }]
            },
            timeout=60
        )
        return resp.json()["choices"][0]["message"]["content"]

    return ""


# ═══════════════════════════════════════════════════
# 主入口：三级降级
# ═══════════════════════════════════════════════════
def ocr_image(image_path: str, lang: str = "chi_sim+eng") -> dict:
    """
    三级降级 OCR 识别单张图片。
    返回: {"text": str, "engine": str, "confidence": float}
    """
    # 第一层：RapidOCR
    if HAS_RAPIDOCR:
        try:
            text, score = ocr_image_rapidocr(image_path)
            if text.strip():
                return {"text": text, "engine": "RapidOCR", "confidence": score}
        except Exception as e:
            print(f"  [!] RapidOCR 失败: {e}", file=sys.stderr)

    # 第二层：Tesseract
    if HAS_TESSERACT_DEPS:
        try:
            text = ocr_image_tesseract(image_path, lang)
            if text.strip():
                return {"text": text, "engine": "Tesseract", "confidence": 0.8}
        except Exception as e:
            print(f"  [!] Tesseract 失败: {e}", file=sys.stderr)

    # 第三层：HTTP API
    try:
        text = ocr_image_api(image_path)
        if text.strip():
            return {"text": text, "engine": "HTTP API", "confidence": 0.9}
    except Exception as e:
        print(f"  [!] HTTP API 失败: {e}", file=sys.stderr)

    return {"text": "", "engine": "none", "confidence": 0.0}


def ocr_pdf(pdf_path: str, lang: str = "chi_sim+eng", dpi: int = 200) -> dict:
    """
    三级降级 OCR 识别 PDF。
    返回: {"text": str, "engine": str, "confidence": float}
    """
    # 第一层：RapidOCR
    if HAS_RAPIDOCR and HAS_PDF2IMAGE:
        try:
            text, score = ocr_pdf_rapidocr(pdf_path, dpi)
            if text.strip():
                return {"text": text, "engine": "RapidOCR", "confidence": score}
        except Exception as e:
            print(f"  [!] RapidOCR PDF 失败: {e}", file=sys.stderr)

    # 第二层：Tesseract
    if HAS_TESSERACT_DEPS and HAS_PDF2IMAGE:
        try:
            text = ocr_pdf_tesseract(pdf_path, lang, dpi)
            if text.strip():
                return {"text": text, "engine": "Tesseract", "confidence": 0.8}
        except Exception as e:
            print(f"  [!] Tesseract PDF 失败: {e}", file=sys.stderr)

    # 第三层：HTTP API（逐页）
    if HAS_PDF2IMAGE:
        try:
            poppler_path = _get_poppler_path()
            kwargs = {"dpi": dpi}
            if poppler_path:
                kwargs["poppler_path"] = poppler_path
            images = convert_from_path(pdf_path, **kwargs)
            import io
            parts = []
            for i, img in enumerate(images, 1):
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                tmp_path = Path(image_path).parent / f"_tmp_page_{i}.png"
                img.save(tmp_path)
                text = ocr_image_api(str(tmp_path))
                tmp_path.unlink(missing_ok=True)
                parts.append(f"=== 第 {i} 页 ===\n{text}\n")
            return {"text": "\n".join(parts), "engine": "HTTP API", "confidence": 0.9}
        except Exception as e:
            print(f"  [!] HTTP API PDF 失败: {e}", file=sys.stderr)

    return {"text": "", "engine": "none", "confidence": 0.0}


def main():
    parser = argparse.ArgumentParser(description="扫描件 OCR（RapidOCR 主力，三级降级）")
    parser.add_argument("file", help="图片或 PDF 文件路径")
    parser.add_argument("--lang", default="chi_sim+eng", help="OCR 语言（Tesseract 备选用），默认 chi_sim+eng")
    parser.add_argument("--out", help="输出文本文件路径（默认 stdout）")
    parser.add_argument("--dpi", type=int, default=200, help="PDF 转图 DPI，默认 200")
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
    has_api = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("SILICONFLOW_API_KEY"))
    if has_api:
        engines.append("HTTP API")

    if not engines:
        print(
            "❌ 未安装任何 OCR 引擎。请运行：\n"
            "   pip install rapidocr-onnxruntime Pillow pdf2image\n"
            "   或设置环境变量 OPENAI_API_KEY / GEMINI_API_KEY 使用云端 API",
            file=sys.stderr,
        )
        sys.exit(1)

    suffix = Path(args.file).suffix.lower()
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
