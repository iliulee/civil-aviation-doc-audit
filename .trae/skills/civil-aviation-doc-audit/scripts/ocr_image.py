"""
扫描件 OCR 脚本（Tesseract 主，PaddleOCR 备选）
====================================================

用途：对扫描件图片或 PDF 进行 OCR 识别。
策略：
- 主力：Tesseract（pytesseract）— 安装简单、跨平台、对中文支持稳定
- 备选：PaddleOCR — 准确率更高，但 PaddleOCR 3.x 在 Windows 上有兼容问题
  （首次安装可能报 `OSError: [WinError 473] 虚拟地址资源不足`）
  因此 v1 默认不开 PaddleOCR，v1.1 视情况启用。

使用方式：
    python scripts/ocr_image.py <图片或PDF路径> [--lang chi_sim+eng] [--out <输出>]

前置依赖：
    1. pip install pytesseract pdf2image Pillow
    2. 安装 Tesseract-OCR 引擎（Windows）：
       - 下载地址: https://github.com/UB-Mannheim/tesseract/wiki
       - 安装路径不要含中文或空格
       - 安装时勾选"中文简体 (chi_sim)"和"英文 (eng)"语言包
       - 把 tesseract.exe 路径加入 PATH 环境变量
"""

import sys
import argparse
from pathlib import Path

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT_DEPS = True
except ImportError:
    HAS_TESSERACT_DEPS = False

# 显式定位 tesseract 路径（按 Skill 自带 → 系统全局 → 常见默认 顺序查找）
import shutil as _shutil
from pathlib import Path as _Path
_TESSERACT_CANDIDATES = [
    # 1) 系统 PATH
    _shutil.which("tesseract"),
    # 2) Skill 自带（如果以后想自带 tesseract）
    str(_Path(__file__).parent.parent / "tools" / "tesseract" / "tesseract.exe"),
    # 3) 常见默认安装位置
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    # 4) TRAE 内置
    r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\app\tesseract\tesseract.exe",
]
for _cand in _TESSERACT_CANDIDATES:
    if _cand and Path(_cand).exists():
        pytesseract.pytesseract.tesseract_cmd = str(_cand)
        break

try:
    from pdf2image import convert_from_path
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False


def ocr_image(image_path: str, lang: str = "chi_sim+eng") -> str:
    """对单张图片做 OCR。"""
    img = Image.open(image_path)
    return pytesseract.image_to_string(img, lang=lang)


def ocr_pdf(pdf_path: str, lang: str = "chi_sim+eng", dpi: int = 200) -> str:
    """对 PDF 每页转图后 OCR，按页分隔输出。"""
    # 优先用 Skill 自带 poppler，避免依赖系统 PATH
    from pathlib import Path as _Path
    _poppler_bin = _Path(__file__).parent.parent / "tools" / "poppler" / "poppler-26.02.0" / "Library" / "bin"
    if _poppler_bin.exists():
        images = convert_from_path(pdf_path, dpi=dpi, poppler_path=str(_poppler_bin))
    else:
        images = convert_from_path(pdf_path, dpi=dpi)
    parts = []
    for i, img in enumerate(images, 1):
        text = pytesseract.image_to_string(img, lang=lang)
        parts.append(f"=== 第 {i} 页 ===\n{text}\n")
    return "\n".join(parts)


def get_tesseract_version() -> str:
    """获取 Tesseract 版本号，未安装时返回空。"""
    try:
        return pytesseract.get_tesseract_version()
    except Exception:
        return ""


def main():
    parser = argparse.ArgumentParser(description="扫描件 OCR（Tesseract 主力）")
    parser.add_argument("file", help="图片或 PDF 文件路径")
    parser.add_argument(
        "--lang", default="chi_sim+eng", help="OCR 语言，默认 chi_sim+eng"
    )
    parser.add_argument("--out", help="输出文本文件路径（默认 stdout）")
    parser.add_argument(
        "--dpi", type=int, default=200, help="PDF 转图 DPI，默认 200"
    )
    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"❌ 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(1)

    if not HAS_TESSERACT_DEPS:
        print(
            "❌ 未安装依赖，请运行：pip install pytesseract pdf2image Pillow",
            file=sys.stderr,
        )
        sys.exit(1)

    version = get_tesseract_version()
    if not version:
        print(
            "❌ 未检测到 Tesseract 引擎，请先安装：\n"
            "   https://github.com/UB-Mannheim/tesseract/wiki\n"
            "   并把 tesseract.exe 路径加入 PATH。",
            file=sys.stderr,
        )
        sys.exit(1)

    suffix = Path(args.file).suffix.lower()
    if suffix == ".pdf":
        if not HAS_PDF2IMAGE:
            print("❌ 缺少 pdf2image，无法处理 PDF", file=sys.stderr)
            sys.exit(1)
        text = ocr_pdf(args.file, args.lang, args.dpi)
    else:
        text = ocr_image(args.file, args.lang)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(
            f"✅ OCR 完成，输出 {len(text)} 字符到 {args.out}\n"
            f"   Tesseract 版本: {version}\n"
            f"   ⚠️ OCR 置信度 <80% 的内容需人工复核",
            file=sys.stderr,
        )
    else:
        print(text)


if __name__ == "__main__":
    main()
