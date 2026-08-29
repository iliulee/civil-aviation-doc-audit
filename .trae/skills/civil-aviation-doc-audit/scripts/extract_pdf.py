"""
PDF 文字提取脚本（PyMuPDF 优先，pdfplumber 兜底）
====================================================

用途：从中文字符为主的 PDF 中提取可搜索文字，输出按页分隔的文本。

为什么用 PyMuPDF：
- 实际测试对中文 PDF 的字符识别率 100%
- 比 MarkItDown / pdfplumber 更稳定
- 不需要额外的 OCR 模型

使用方式：
    python scripts/extract_pdf.py <pdf文件路径> [--out <输出文本>] [--pages 1-10]

示例：
    python scripts/extract_pdf.py "H:\\规范\\MH-T 5078.1-2024.pdf" --out 5078.1.txt
    python scripts/extract_pdf.py "scan.pdf" --pages 1-5

如果 PDF 是扫描件（无文字层），本脚本会提示需要使用 scripts/ocr_image.py。
"""

import sys
import argparse
from pathlib import Path

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

# ---- 体检路由密度阈值（v10.6）----
# page_ratio：非空页占比下限。"前 3 页有字、后面全是扫描页"的长文档靠它拦下。
# avg_chars：非空页平均字符数下限。拦"整本只有页码字"的空壳 PDF——页码字
# 每页约 3~6 字，真实内容页至少 10 字。实测教训：不能用"全文字符总量"做阈值
# （sample_5078_1.pdf 单页 74 字的真实文字版会被总量≥100 误杀成扫描件）。
TEXT_PAGE_RATIO = 0.6
MIN_AVG_CHARS_PER_PAGE = 10


def extract_with_pymupdf(pdf_path: str, page_range=None) -> str:
    """用 PyMuPDF 提取 PDF 文字，按页分隔。

    Args:
        pdf_path: PDF 文件路径
        page_range: 1-based 的 (start, end) 元组；None 表示全部

    Returns:
        包含"=== 第 N 页 ==="分隔符的全文
    """
    doc = fitz.open(pdf_path)
    parts = []
    start, end = (1, len(doc)) if page_range is None else page_range
    for i in range(start - 1, min(end, len(doc))):
        page = doc[i]
        text = page.get_text("text")
        parts.append(f"=== 第 {i + 1} 页 ===\n{text}\n")
    doc.close()
    return "\n".join(parts)


def probe_text_layer(pdf_path: str) -> dict:
    """体检路由（v10.6）：全页探测 PDF 文本层，判定走直接提取还是 OCR。

    为什么升级：旧 detect_scanned 只抽样前 3 页，长文档后面全是扫描页会漏判；
    且无密度阈值，"整本只有几页码字"的空壳 PDF 会误判文字版白跑一遍空提取。

    判定规则（密度双阈值，防两个方向的误判）：
      nonempty_pages / pages >= TEXT_PAGE_RATIO
      且 total_chars / nonempty_pages >= MIN_AVG_CHARS_PER_PAGE
      → kind=text（直接 get_text()，零 OCR）
      否则 → kind=scanned（走 ocr_image.py 渲染+OCR）
      （不能用"字符总量"做阈值：会误杀单页短小的真实文字版，见常量注释）

    Returns:
        {
            "pages": int, "nonempty_pages": int, "total_chars": int,
            "kind": "text" | "scanned",
            "action": "direct_extract" | "ocr",
            "thresholds": {"page_ratio": 0.6, "avg_chars_per_page": 10},
        }
    """
    doc = fitz.open(pdf_path)
    try:
        n_pages = len(doc)
        nonempty = 0
        total_chars = 0
        for pg in doc:
            c = len(pg.get_text("text").strip())
            total_chars += c
            if c > 0:
                nonempty += 1
    finally:
        doc.close()

    ratio = (nonempty / n_pages) if n_pages else 0.0
    avg_chars = (total_chars / nonempty) if nonempty else 0.0
    is_text = ratio >= TEXT_PAGE_RATIO and avg_chars >= MIN_AVG_CHARS_PER_PAGE
    kind = "text" if is_text else "scanned"
    return {
        "pages": n_pages,
        "nonempty_pages": nonempty,
        "total_chars": total_chars,
        "kind": kind,
        "action": "direct_extract" if is_text else "ocr",
        "thresholds": {"page_ratio": TEXT_PAGE_RATIO, "avg_chars_per_page": MIN_AVG_CHARS_PER_PAGE},
    }


def detect_scanned(pdf_path: str, sample_pages: int = 3) -> bool:
    """检测 PDF 是否为扫描件（无可搜索文字）。薄包装，兼容既有调用方。

    v10.6 起内部走 probe_text_layer 全页密度判定；sample_pages 参数保留
    但不再使用（避免破坏既有调用签名）。
    """
    return probe_text_layer(pdf_path)["kind"] == "scanned"


def main():
    parser = argparse.ArgumentParser(description="PDF 文字提取（PyMuPDF 优先）")
    parser.add_argument("pdf", help="PDF 文件路径")
    parser.add_argument("--out", help="输出文本文件路径（默认打印到 stdout）")
    parser.add_argument(
        "--pages", help="页码范围，如 '1-10'；默认全部"
    )
    parser.add_argument(
        "--probe", action="store_true",
        help="只做体检路由探测：输出 kind/action JSON（不提取文字）",
    )
    args = parser.parse_args()

    if not Path(args.pdf).exists():
        print(f"❌ 文件不存在: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    if not HAS_PYMUPDF:
        print(
            "❌ 未安装 PyMuPDF，请运行：pip install PyMuPDF",
            file=sys.stderr,
        )
        sys.exit(1)

    # 体检路由：--probe 只输出路由决策 JSON（供建底座登记，决策可追溯）
    if args.probe:
        import json
        info = probe_text_layer(args.pdf)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return

    if detect_scanned(args.pdf):
        print(
            f"⚠️ 警告：{args.pdf} 看起来是扫描件，PyMuPDF 提取结果可能为空。\n"
            "   请改用 scripts/ocr_image.py 处理扫描件图片。",
            file=sys.stderr,
        )

    page_range = None
    if args.pages:
        try:
            start, end = map(int, args.pages.split("-"))
            page_range = (start, end)
        except ValueError:
            print(
                f"❌ 页码范围格式错误: {args.pages}（应为 '1-10'）",
                file=sys.stderr,
            )
            sys.exit(1)

    text = extract_with_pymupdf(args.pdf, page_range)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(
            f"✅ 已提取 {len(text)} 字符到 {args.out}",
            file=sys.stderr,
        )
    else:
        print(text)


if __name__ == "__main__":
    main()
