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
import json
import argparse
from pathlib import Path
from typing import Optional

# 允许 scripts/ 内部相互 import
sys.path.insert(0, str(Path(__file__).parent))

from postprocess import clean_text

# v3.1：引入混淆检测与字段复核模块（延迟导入，避免循环依赖）
from ocr_confusion_check import check as ocr_confusion_check
from verify_fields import auto_verify as _verify_fields_auto
from verify_fields import merge_results as _verify_fields_merge

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
def extract_text(
    file_path: str,
    lang: str = "chi_sim+eng",
    dpi: int = 200,
    verbose: bool = True,
    engine: str = "auto",
    use_table: bool = False,
) -> dict:
    """
    根据 sniff_document 结果自动选择提取策略。

    Args:
        engine: OCR 引擎，默认 auto（API 优先 → PaddleOCR 备选 → Tesseract 兜底）。
                可选：auto / vision / paddle / tesseract。
        use_table: 已废弃，保留兼容性（v4.1 移除 rapid-table）。

    Returns:
        {
            "text": 提取到的文本,
            "engine": 使用的引擎,
            "confidence": 平均置信度,
        }
    """
    info = sniff_document(file_path)
    method = info["extraction_method"]

    if method == "pymupdf" and HAS_PYMUPDF:
        doc = fitz.open(file_path)
        parts = []
        for i in range(len(doc)):
            parts.append(f"=== 第 {i + 1} 页 ===\n{doc[i].get_text('text')}\n")
        doc.close()
        return {"text": clean_text("\n".join(parts)), "engine": "PyMuPDF", "confidence": 1.0}

    if method == "ocr":
        # v4.1：默认 PaddleOCR 单层主引擎
        import ocr_image as _ocr
        if info["suffix"] == ".pdf":
            result = _ocr.ocr_pdf(file_path, lang=lang, dpi=dpi, engine=engine)
        else:
            result = _ocr.ocr_image(file_path, lang=lang, engine=engine)

        if verbose:
            print(
                f"  [i] OCR 引擎: {result.get('engine', 'unknown')} | "
                f"置信度: {result.get('confidence', 0):.1%} | "
                f"字符数: {len(result.get('text', ''))}",
                file=sys.stderr,
            )
        return result

    if method == "text":
        return {"text": clean_text(Path(file_path).read_text(encoding="utf-8")), "engine": "text", "confidence": 1.0}

    if method == "docx":
        try:
            from docx import Document
        except ImportError:
            raise RuntimeError("docx 依赖未安装：pip install python-docx")
        doc = Document(file_path)
        text = "\n".join(p.text for p in doc.paragraphs)
        return {"text": clean_text(text), "engine": "docx", "confidence": 1.0}

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
    result = extract_text(
        args.file, lang=args.lang, dpi=args.dpi,
        engine=args.engine, use_table=args.use_table,
    )
    text = result["text"]
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(
            f"✅ 已提取到 {args.out}（{len(text)} 字符）\n"
            f"   引擎: {result.get('engine', 'unknown')}\n"
            f"   置信度: {result.get('confidence', 0):.1%}",
            file=sys.stderr,
        )
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


# ========== 4. 一键审核（v3.1 新增） ==========
def _parse_rows_from_text(text: str) -> list:
    """
    从 OCR 文本中粗解析施工记录表格行。
    这是一个轻量级解析器，把 "=== 第 N 页 ===" 后的非空行作为候选行返回。
    真正的结构化抽取由 AI（基于 references/ 的规范）完成。
    """
    rows = []
    current_page = 1
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("=== 第") and line.endswith("页 ==="):
            try:
                current_page = int(line.replace("=== 第", "").replace("页 ===", "").strip())
            except ValueError:
                pass
            continue
        # 跳过页眉页脚常见噪声
        if line in ("（识别为空）", "（识别失败）", "（转换失败）"):
            continue
        rows.append({"_page": current_page, "_raw": line})
    return rows


def cmd_audit(args):
    """
    一键审核完整流程：
      1. 提取文字（OCR/PyMuPDF）
      2. 运行 OCR 混淆检测
      3. 字段级 Vision 复核（agent/api/enhance 自动选择）
      4. 输出审核产物

    说明：
      - 如果提供了 --data，直接使用其中的结构化 rows 进行混淆检测和复核。
      - 如果没有 --data，只提取文字并保存候选行，需要后续提供结构化数据再跑复核。
    """
    source_file = Path(args.file)
    if not source_file.exists():
        print(f"❌ 文件不存在: {source_file}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60, file=sys.stderr)
    print("🚀 开始一键审核", file=sys.stderr)
    print(f"   文件: {source_file}", file=sys.stderr)
    print(f"   输出: {out_dir}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # 步骤 1：提取文字
    print("\n[1/4] 提取文字...", file=sys.stderr)
    extract_result = extract_text(
        str(source_file), lang=args.lang, dpi=args.dpi, verbose=True,
        engine=args.engine, use_table=args.use_table,
    )
    raw_text = extract_result.get("text", "")
    if not raw_text.strip():
        print("❌ 未提取到任何文字", file=sys.stderr)
        sys.exit(1)

    raw_text_file = out_dir / "extracted_text.txt"
    raw_text_file.write_text(raw_text, encoding="utf-8")
    print(f"   ✓ 已保存: {raw_text_file}", file=sys.stderr)

    # 步骤 2：准备数据（优先用 --data，否则用原始行）
    print("\n[2/4] 准备数据...", file=sys.stderr)
    structured_data = None
    if args.data and Path(args.data).exists():
        try:
            structured_data = json.loads(Path(args.data).read_text(encoding="utf-8"))
            print(f"   ✓ 已加载结构化数据: {args.data}（{len(structured_data.get('rows', []))} 行）", file=sys.stderr)
        except Exception as e:
            print(f"   [!] 加载 --data 失败: {e}，将使用原始行", file=sys.stderr)

    if structured_data is None:
        rows = _parse_rows_from_text(raw_text)
        data = {
            "doc_type": args.doc_type or "施工记录",
            "source_file": str(source_file),
            "rows": rows,
            "engine": extract_result.get("engine", "unknown"),
            "confidence": extract_result.get("confidence", 0.0),
        }
        # 保存原始行，供 AI 后续解析
        raw_rows_file = out_dir / "raw_rows.json"
        raw_rows_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"   ⚠ 未提供 --data，已保存原始候选行: {raw_rows_file}", file=sys.stderr)
        print("   提示：将 OCR 文本解析为结构化 rows 后，重新运行：", file=sys.stderr)
        print(f"     python scripts/run_audit.py audit \"{source_file}\" --data <结构化JSON> --out {out_dir}", file=sys.stderr)
    else:
        data = structured_data
        data.setdefault("source_file", str(source_file))
        data.setdefault("engine", extract_result.get("engine", "unknown"))
        data.setdefault("confidence", extract_result.get("confidence", 0.0))
        # v3.3：保存 OCR items（含 bbox），供字段级 Vision 复核精确定位
        data["_ocr_items"] = extract_result.get("items", [])

    # 步骤 3：OCR 混淆检测
    print("\n[3/4] OCR 混淆检测...", file=sys.stderr)
    confusion_result = ocr_confusion_check(data)

    confusion_file = out_dir / "ocr_confusion_result.json"
    confusion_file.write_text(
        json.dumps(confusion_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = confusion_result.get("summary", {})
    print(
        f"   ✓ 总候选行: {summary.get('total_rows', 0)} | "
        f"存疑: {summary.get('total_suspects', 0)} | "
        f"高置信: {summary.get('high_confidence', 0)} | "
        f"中置信: {summary.get('medium_confidence', 0)}",
        file=sys.stderr,
    )
    print(f"   ✓ 已保存: {confusion_file}", file=sys.stderr)

    # 步骤 4：字段级 Vision 复核（仅当有结构化 rows 时）
    print("\n[4/4] 字段级 Vision 复核...", file=sys.stderr)
    verify_result = {"path": "skipped", "message": "未提供结构化数据，跳过复核"}
    if structured_data is not None:
        verify_out_dir = out_dir / "verify_output"
        verify_out_dir.mkdir(exist_ok=True)
        verify_result = _verify_fields_auto(
            str(source_file),
            confusion_result,
            data,
            str(verify_out_dir),
            force_path=args.verify_path,
            provider=args.provider,
        )
    else:
        print("   ⚠ 未提供 --data，跳过 Vision 复核", file=sys.stderr)

    # 步骤 5：保存最终产物
    print("\n[5/5] 保存审核产物...", file=sys.stderr)
    final_data_file = out_dir / "audit_data.json"
    final_data_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 汇总
    print("\n" + "=" * 60, file=sys.stderr)
    print("✅ 一键审核完成", file=sys.stderr)
    print(f"   提取引擎: {extract_result.get('engine', 'unknown')}", file=sys.stderr)
    print(f"   提取置信度: {extract_result.get('confidence', 0):.1%}", file=sys.stderr)
    print(f"   OCR 存疑字段: {summary.get('total_suspects', 0)}", file=sys.stderr)
    path = verify_result.get("path", "unknown")
    print(f"   复核路径: {path}", file=sys.stderr)
    if path == "agent":
        action_file = verify_result.get("action_file", "")
        print(f"   任务清单: {action_file}", file=sys.stderr)
        print(
            "   AI 智能体将自动读取裁剪图片并验证字段，"
            "输出 verify_results.json 后调用 merge 合并结果。",
            file=sys.stderr,
        )
    elif path == "completed":
        vr = verify_result.get("verify_results", {})
        if vr.get("status") == "completed":
            merged = verify_result.get("merged_data", data)
            final_data_file.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results = vr.get("results", [])
            high = sum(1 for r in results if r.get("confidence") == "high")
            medium = sum(1 for r in results if r.get("confidence") == "medium")
            print(f"   复核完成: {len(results)} 个字段，高置信 {high}，中置信 {medium}", file=sys.stderr)
    print(f"   数据文件: {final_data_file}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="民航施工资料审核 Skill 入口")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help="识别单份资料")
    p_info.add_argument("file")
    p_info.set_defaults(func=cmd_info)

    p_extract = sub.add_parser("extract", help="提取文字（自动选策略）")
    p_extract.add_argument("file")
    p_extract.add_argument("--lang", default="chi_sim+eng")
    p_extract.add_argument("--dpi", type=int, default=200)
    p_extract.add_argument("--out")
    p_extract.add_argument(
        "--engine", choices=["paddle", "tesseract", "vision", "auto"], default="paddle",
        help="OCR 引擎：paddle(默认)/tesseract/vision/auto"
    )
    p_extract.add_argument(
        "--use-table", action="store_true",
        help="已废弃，保留兼容性（v4.1 移除 rapid-table）"
    )
    p_extract.set_defaults(func=cmd_extract)

    p_batch = sub.add_parser("batch", help="批量识别目录下资料")
    p_batch.add_argument("dir")
    p_batch.set_defaults(func=cmd_batch)

    p_post = sub.add_parser("postprocess", help="后处理文本")
    p_post.add_argument("file")
    p_post.add_argument("--out")
    p_post.set_defaults(func=cmd_postprocess)

    # v3.3：新增一键审核子命令
    p_audit = sub.add_parser("audit", help="一键审核（OCR + 混淆检测 + Vision复核）")
    p_audit.add_argument("file")
    p_audit.add_argument("--out", default="audit_output", help="输出目录")
    p_audit.add_argument("--data", default=None, help="预解析的结构化数据 JSON（含 rows）")
    p_audit.add_argument("--doc-type", default="施工记录", help="资料类型")
    p_audit.add_argument("--lang", default="chi_sim+eng")
    p_audit.add_argument("--dpi", type=int, default=200)
    p_audit.add_argument(
        "--engine", choices=["paddle", "tesseract", "vision", "auto"], default="paddle",
        help="OCR 引擎：paddle(默认)/tesseract/vision/auto"
    )
    p_audit.add_argument(
        "--use-table", action="store_true",
        help="已废弃，保留兼容性（v4.1 移除 rapid-table）"
    )
    p_audit.add_argument("--verify-path", default=None, choices=["agent", "api", "enhance"])
    p_audit.add_argument("--provider", default=None)
    p_audit.set_defaults(func=cmd_audit)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
