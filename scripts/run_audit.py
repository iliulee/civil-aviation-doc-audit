"""
Skill 入口脚本（一键启动审核）
====================================================

这是 Skill 的 Python 端"工具调用入口"，AI 在执行审核流程时
按需调用此脚本完成具体的文件读写 / OCR / 后处理。

工作流（参见 SKILL.md）：
    1. 资料格式识别  → 本脚本 sniff_document()
    2. OCR 文字提取  → 调 extract_pdf.py 或 ocr_image.py
    3. 规范匹配审核  → AI 自行完成（基于 references/）
    4. 逐项审核      → AI 自行完成
    5. 运算审核      → AI 自行完成（基于 calculation-standards.md）
    6. 文档生成      → 调本脚本 generate_report()

使用方式（直接命令行）：
    python scripts/run_audit.py info <文件>          # 识别资料类型
    python scripts/run_audit.py extract <文件>       # 提取文字
    python scripts/run_audit.py batch <目录>         # 批量识别
    python scripts/run_audit.py postprocess <文件>   # 后处理文本

也可以被 SKILL 内的 AI 作为 Python 模块 import 使用：
    from scripts.run_audit import sniff_document, extract_text
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

# 允许 scripts/ 内部相互 import
sys.path.insert(0, str(Path(__file__).parent))

from postprocess import clean_text

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    from pdf2image import convert_from_path
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False


# ========== 1. 资料格式识别 ==========
def sniff_document(file_path: str) -> dict:
    """识别资料类型、页数、是否扫描件、文件大小。

    Returns:
        {
            "path": ...,
            "suffix": ".pdf" / ".docx" / ".png" / ...,
            "size_bytes": ...,
            "page_count": ... or None,
            "is_scanned": ... or None,
            "extraction_method": "pymupdf" / "ocr" / "docx" / "image" / "unknown",
        }
    """
    p = Path(file_path)
    info = {
        "path": str(p.absolute()),
        "suffix": p.suffix.lower(),
        "size_bytes": p.stat().st_size if p.exists() else 0,
        "page_count": None,
        "is_scanned": None,
        "extraction_method": "unknown",
    }
    if not p.exists():
        return info

    suffix = info["suffix"]

    if suffix == ".pdf" and HAS_PYMUPDF:
        doc = fitz.open(file_path)
        info["page_count"] = len(doc)
        # 抽样前 3 页判断扫描件（阈值 10 字符/页，避免误判）
        sample_n = min(3, len(doc))
        total_chars = sum(len(doc[i].get_text("text").strip()) for i in range(sample_n))
        avg_chars = total_chars / sample_n
        info["is_scanned"] = avg_chars < 10
        doc.close()
        info["extraction_method"] = "ocr" if info["is_scanned"] else "pymupdf"

    elif suffix in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"):
        info["extraction_method"] = "ocr"
        info["is_scanned"] = True

    elif suffix in (".docx", ".doc"):
        info["extraction_method"] = "docx"

    elif suffix in (".txt", ".md"):
        info["extraction_method"] = "text"

    return info


# ========== 2. 文字提取（自动选策略） ==========
def extract_text(file_path: str, lang: str = "chi_sim+eng", dpi: int = 200) -> str:
    """根据 sniff_document 结果自动选择提取策略。"""
    info = sniff_document(file_path)
    method = info["extraction_method"]

    if method == "pymupdf" and HAS_PYMUPDF:
        doc = fitz.open(file_path)
        parts = []
        for i in range(len(doc)):
            parts.append(f"=== 第 {i + 1} 页 ===\n{doc[i].get_text('text')}\n")
        doc.close()
        return clean_text("\n".join(parts))

    if method == "ocr":
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            raise RuntimeError(
                "OCR 依赖未安装，请运行：pip install pytesseract pdf2image Pillow"
            )
        # 显式定位 tesseract（按 Skill 自带 → 系统全局 → 常见默认 顺序）
        import shutil as _shutil
        _tess_candidates = [
            _shutil.which("tesseract"),
            str(Path(__file__).parent.parent / "tools" / "tesseract" / "tesseract.exe"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\app\tesseract\tesseract.exe",
        ]
        for _cand in _tess_candidates:
            if _cand and Path(_cand).exists():
                pytesseract.pytesseract.tesseract_cmd = str(_cand)
                break
        if info["suffix"] == ".pdf" and HAS_PDF2IMAGE:
            # Skill 自带 poppler，避免依赖系统 PATH
            _poppler_root = Path(__file__).parent.parent / "tools" / "poppler" / "poppler-26.02.0" / "Library"
            _poppler_bin = _poppler_root / "bin"
            if _poppler_bin.exists():
                images = convert_from_path(
                    file_path, dpi=dpi, poppler_path=str(_poppler_bin)
                )
            else:
                # 退回系统 PATH（如果用户把 poppler 装到全局）
                images = convert_from_path(file_path, dpi=dpi)
            parts = [
                f"=== 第 {i} 页 ===\n{pytesseract.image_to_string(img, lang=lang)}\n"
                for i, img in enumerate(images, 1)
            ]
            return clean_text("\n".join(parts))
        else:
            img = Image.open(file_path)
            return clean_text(pytesseract.image_to_string(img, lang=lang))

    if method == "text":
        return clean_text(Path(file_path).read_text(encoding="utf-8"))

    if method == "docx":
        try:
            from docx import Document
        except ImportError:
            raise RuntimeError("docx 依赖未安装：pip install python-docx")
        doc = Document(file_path)
        text = "\n".join(p.text for p in doc.paragraphs)
        return clean_text(text)

    raise ValueError(f"无法识别文件类型: {file_path}")


# ========== 3. 批量识别 ==========
def batch_sniff(dir_path: str) -> list:
    """对目录下所有 PDF / 图片 / docx 做格式识别。"""
    p = Path(dir_path)
    if not p.is_dir():
        raise ValueError(f"不是目录: {dir_path}")
    results = []
    for f in sorted(p.iterdir()):
        if f.is_file() and f.suffix.lower() in (
            ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".docx", ".doc"
        ):
            results.append(sniff_document(str(f)))
    return results


# ========== CLI ==========
def cmd_info(args):
    info = sniff_document(args.file)
    print("📄 资料信息")
    for k, v in info.items():
        print(f"  {k}: {v}")


def cmd_extract(args):
    text = extract_text(args.file, lang=args.lang)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"✅ 已提取到 {args.out}（{len(text)} 字符）", file=sys.stderr)
    else:
        print(text)


def cmd_batch(args):
    items = batch_sniff(args.dir)
    print(f"📁 共 {len(items)} 份资料")
    print(f"{'文件':<60} {'页数':<8} {'扫描件':<8} {'提取方式':<10}")
    print("-" * 90)
    for it in items:
        name = Path(it["path"]).name
        if len(name) > 58:
            name = name[:55] + "..."
        print(
            f"{name:<60} "
            f"{str(it['page_count'] or '-'):<8} "
            f"{'是' if it['is_scanned'] else ('否' if it['is_scanned'] is False else '-'):<8} "
            f"{it['extraction_method']:<10}"
        )


def cmd_postprocess(args):
    raw = Path(args.file).read_text(encoding="utf-8")
    cleaned = clean_text(raw)
    out = Path(args.out) if args.out else Path(args.file)
    out.write_text(cleaned, encoding="utf-8")
    print(f"✅ 已清洗 {args.file} → {out}（{len(raw)} → {len(cleaned)} 字符）")


def main():
    parser = argparse.ArgumentParser(description="民航施工资料审核 Skill 入口")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help="识别单份资料")
    p_info.add_argument("file")
    p_info.set_defaults(func=cmd_info)

    p_extract = sub.add_parser("extract", help="提取文字（自动选策略）")
    p_extract.add_argument("file")
    p_extract.add_argument("--lang", default="chi_sim+eng")
    p_extract.add_argument("--out")
    p_extract.set_defaults(func=cmd_extract)

    p_batch = sub.add_parser("batch", help="批量识别目录下资料")
    p_batch.add_argument("dir")
    p_batch.set_defaults(func=cmd_batch)

    p_post = sub.add_parser("postprocess", help="后处理文本")
    p_post.add_argument("file")
    p_post.add_argument("--out")
    p_post.set_defaults(func=cmd_postprocess)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
