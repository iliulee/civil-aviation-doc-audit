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
import subprocess
from datetime import datetime
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


# ========== 4. 建立数据底座（Phase 1 T-10） ==========
def cmd_build(args):
    """
    调用 build_foundation.py 建立项目数据底座。
    参数与 build_foundation.py 保持一致。
    """
    script_dir = Path(__file__).resolve().parent
    foundation_script = script_dir / "build_foundation.py"
    project_path = Path(args.project_path).resolve()
    out_dir = project_path / args.out

    cmd = [
        sys.executable, str(foundation_script),
        str(project_path),
        "--engine", args.engine,
        "--out", args.out,
    ]
    if args.incremental:
        cmd.append("--incremental")
    if args.preconditions:
        cmd.extend(["--preconditions", args.preconditions])
    if args.expected_rows:
        cmd.extend(["--expected-rows", args.expected_rows])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    # build_foundation.py 本身把过程信息输出到 stderr
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")

    if result.returncode != 0:
        sys.exit(result.returncode)

    print(f"数据底座已建立：{out_dir}")
    print('请打开 "项目总览.html" 或 "data-editor.html" 进行人工核对。')


# ========== 5. 一键审核（v3.1 新增） ==========
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


# ========== 6. 正式审核（Phase 3 T-29~T-34） ==========
def cmd_review(args):
    """
    调用 review_audit.py 执行正式审核。
    支持多 Agent 并行模式。
    """
    script_dir = Path(__file__).resolve().parent
    review_script = script_dir / "review_audit.py"
    project_path = Path(args.project_path).resolve()

    cmd = [
        sys.executable, str(review_script),
        str(project_path),
        "--out", args.out,
        "--split-by", args.split_by,
    ]
    if args.task_id:
        cmd.extend(["--task-id", args.task_id])
    if args.tasks_file:
        cmd.extend(["--tasks-file", args.tasks_file])
    if args.dry_run:
        cmd.append("--dry-run")
    if args.force:
        cmd.append("--force")

    result = subprocess.run(
        cmd,
        capture_output=False,  # 直接输出到终端，保持进度可见
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        sys.exit(result.returncode)


# ========== 7. 生成报告（Phase 3 T-35~T-38） ==========
def cmd_report(args):
    """
    生成 HTML 审核报告（从审核日志 JSON）。
    """
    project_path = Path(args.project_path).resolve()
    out_base = project_path / args.out
    
    # 自动回退：如果 {project_path}/数据底座/审核日志 不存在，
    # 尝试直接使用 {project_path}/审核日志
    audit_log_dir = out_base / "审核日志"
    if not audit_log_dir.exists():
        fallback = project_path / "审核日志"
        if fallback.exists():
            print(f"⚠️  未找到 {audit_log_dir}，自动回退到 {fallback}", file=sys.stderr)
            audit_log_dir = fallback
            out_base = project_path

    if not audit_log_dir.exists():
        print(f"❌ 未找到审核日志目录: {audit_log_dir}", file=sys.stderr)
        print("   请先执行 review 命令完成正式审核", file=sys.stderr)
        sys.exit(1)

    # 找到最新的审核日志
    log_files = sorted(audit_log_dir.glob("AU-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not log_files:
        # 也尝试从 index.json 获取
        index_path = out_base / "index.json"
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            logs = index.get("audit_logs", [])
            if logs:
                latest = logs[-1]
                file_rel = latest.get("file", "")
                if file_rel:
                    log_file = out_base / file_rel
                    if log_file.is_file():
                        log_files = [log_file]

    if not log_files:
        print(f"❌ 未找到审核日志文件", file=sys.stderr)
        sys.exit(1)

    audit_log = json.loads(log_files[0].read_text(encoding="utf-8"))
    report_html = _generate_html_report(audit_log, project_path)

    report_path = project_path / "审核报告.html"
    report_path.write_text(report_html, encoding="utf-8")
    print(f"✅ 审核报告已生成: {report_path}", file=sys.stderr)

    # 更新 index.json
    index_path = out_base / "index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["stage"] = "reported"
        index["updated_at"] = datetime.now().isoformat(timespec="seconds")
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _generate_pie_chart_svg(
    values: dict,
    width: int = 280,
    height: int = 280,
    inner_radius: float = 0.55,
) -> str:
    """生成 SVG 环形图（Donut Chart）。

    Args:
        values: {标签: 数值} 字典，如 {"通过": 45, "不通过": 12, "存疑": 8}
        width: SVG 宽度
        height: SVG 高度
        inner_radius: 内圆半径比例（0 为饼图，0.55 为环形图）

    Returns:
        SVG 字符串
    """
    COLORS = {
        "通过": "#34a853",
        "不通过": "#d93025",
        "存疑": "#e37400",
        "待AI": "#9334e6",
        "不适用": "#9aa0a6",
    }
    # 过滤掉 0 值的项
    items = [(k, v) for k, v in values.items() if v > 0]
    if not items:
        return ""

    total = sum(v for _, v in items)
    cx, cy = width / 2, height / 2
    outer_r = min(cx, cy) - 10
    inner_r = outer_r * inner_radius

    # 生成 legend 和 arcs
    arcs = []
    legend_items = []
    start_angle = -90  # 从顶部开始

    for i, (label, count) in enumerate(items):
        pct = count / total
        angle = pct * 360
        end_angle = start_angle + angle

        # 计算 SVG arc 路径
        color = COLORS.get(label, "#9aa0a6")
        # 单项100%时拆分为两段半圆弧，避免起点终点重合导致无法绘制
        if angle >= 359.99:
            mid_angle = start_angle + 180
            arc1 = _svg_arc_path(cx, cy, outer_r, inner_r, start_angle, mid_angle)
            arc2 = _svg_arc_path(cx, cy, outer_r, inner_r, mid_angle, end_angle)
            arcs.append(f'<path d="{arc1}" fill="{color}" stroke="#fff" stroke-width="1"/>')
            arcs.append(f'<path d="{arc2}" fill="{color}" stroke="#fff" stroke-width="1"/>')
        else:
            arc_path = _svg_arc_path(cx, cy, outer_r, inner_r, start_angle, end_angle)
            arcs.append(f'<path d="{arc_path}" fill="{color}" stroke="#fff" stroke-width="1"/>')

        # 标签线（仅当占比 > 5%）
        if pct > 0.05:
            mid_angle = (start_angle + end_angle) / 2
            label_r = outer_r + 8
            label_x = cx + label_r * _cos_deg(mid_angle)
            label_y = cy + label_r * _sin_deg(mid_angle)
            text_anchor = "start" if -90 <= mid_angle < 90 else "end"
            pct_text = f"{count}项 ({pct:.0%})"
            arcs.append(
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" font-size="11" fill="#555" '
                f'text-anchor="{text_anchor}" dominant-baseline="middle">{pct_text}</text>'
            )

        # Legend
        legend_items.append(
            f'<div class="chart-legend-item">'
            f'<span class="chart-legend-dot" style="background:{color}"></span>'
            f'{label}：{count} 项'
            f'</div>'
        )

        start_angle = end_angle

    # 中心文字
    center_text = f'<text x="{cx}" y="{cy - 8}" font-size="22" font-weight="bold" fill="#333" text-anchor="middle">{total}</text>'
    center_text += f'<text x="{cx}" y="{cy + 14}" font-size="12" fill="#666" text-anchor="middle">总检查项</text>'

    svg = f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
    {center_text}
    {"".join(arcs)}
  </svg>'''

    legend_html = "".join(legend_items)

    return f'<div class="chart-container"><div class="chart-svg">{svg}</div><div class="chart-legend">{legend_html}</div></div>'


def _generate_bar_chart_svg(
    data: list,
    width: int = 600,
    height: int = 0,
    bar_height: int = 28,
    gap: int = 6,
) -> str:
    """生成 SVG 水平条形图。

    Args:
        data: [(标签, 不通过数, 存疑数), ...] 按不通过数降序排列
        width: SVG 宽度
        height: 自动计算（0 表示自动）
        bar_height: 每个条形的高度
        gap: 条形间距

    Returns:
        SVG 字符串
    """
    if not data:
        return ""

    # 过滤掉全 0 的项
    data = [(label, fail, susp) for label, fail, susp in data if fail + susp > 0]
    if not data:
        return '<p style="color:#999;text-align:center;">所有分部分项均通过审核</p>'

    max_val = max(fail + susp for _, fail, susp in data)
    if max_val == 0:
        return ""

    n = len(data)
    if height == 0:
        height = n * (bar_height + gap) + 40

    label_width = 160
    bar_area_width = width - label_width - 20
    chart_height = n * (bar_height + gap)

    bars = []
    for i, (label, fail, susp) in enumerate(data):
        y = 20 + i * (bar_height + gap)
        total = fail + susp
        fail_w = (fail / max_val) * bar_area_width if max_val > 0 else 0
        susp_w = (susp / max_val) * bar_area_width if max_val > 0 else 0

        # 标签
        display_label = label if len(label) <= 12 else label[:11] + "…"
        bars.append(
            f'<text x="0" y="{y + bar_height / 2 + 4}" font-size="12" fill="#333" '
            f'text-anchor="start" dominant-baseline="middle">{display_label}</text>'
        )

        # 不通过条
        if fail_w > 0:
            bars.append(
                f'<rect x="{label_width}" y="{y}" width="{fail_w}" height="{bar_height}" '
                f'fill="#d93025" rx="3"/>'
            )
            if fail_w > 30:
                bars.append(
                    f'<text x="{label_width + fail_w / 2}" y="{y + bar_height / 2 + 4}" '
                    f'font-size="11" fill="#fff" text-anchor="middle" dominant-baseline="middle">{fail}</text>'
                )

        # 存疑条
        if susp_w > 0:
            bars.append(
                f'<rect x="{label_width + fail_w}" y="{y}" width="{susp_w}" height="{bar_height}" '
                f'fill="#e37400" rx="3"/>'
            )
            if susp_w > 30:
                bars.append(
                    f'<text x="{label_width + fail_w + susp_w / 2}" y="{y + bar_height / 2 + 4}" '
                    f'font-size="11" fill="#fff" text-anchor="middle" dominant-baseline="middle">{susp}</text>'
                )

        # 数值标注
        if total > 0:
            bars.append(
                f'<text x="{label_width + fail_w + susp_w + 6}" y="{y + bar_height / 2 + 4}" '
                f'font-size="11" fill="#666" dominant-baseline="middle">{total}项</text>'
            )

    svg = f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
    {"".join(bars)}
  </svg>'''

    return f'<div class="chart-container"><div class="chart-svg" style="overflow-x:auto;">{svg}</div></div>'


def _svg_arc_path(cx: float, cy: float, outer_r: float, inner_r: float, start_deg: float, end_deg: float) -> str:
    """生成 SVG 环形/扇形路径。"""
    start_rad = start_deg * 3.1415926535 / 180
    end_rad = end_deg * 3.1415926535 / 180

    # 外弧起点
    x1 = cx + outer_r * _cos_deg(start_deg)
    y1 = cy + outer_r * _sin_deg(start_deg)
    # 外弧终点
    x2 = cx + outer_r * _cos_deg(end_deg)
    y2 = cy + outer_r * _sin_deg(end_deg)
    # 内弧起点
    x3 = cx + inner_r * _cos_deg(end_deg)
    y3 = cy + inner_r * _sin_deg(end_deg)
    # 内弧终点
    x4 = cx + inner_r * _cos_deg(start_deg)
    y4 = cy + inner_r * _sin_deg(start_deg)

    large_arc = 1 if (end_deg - start_deg) > 180 else 0

    return (
        f"M {x1:.1f} {y1:.1f} "
        f"A {outer_r:.1f} {outer_r:.1f} 0 {large_arc} 1 {x2:.1f} {y2:.1f} "
        f"L {x3:.1f} {y3:.1f} "
        f"A {inner_r:.1f} {inner_r:.1f} 0 {large_arc} 0 {x4:.1f} {y4:.1f} Z"
    )


def _cos_deg(deg: float) -> float:
    """cos(角度)"""
    import math
    return math.cos(deg * math.pi / 180)


def _sin_deg(deg: float) -> float:
    """sin(角度)"""
    import math
    return math.sin(deg * math.pi / 180)


def _generate_html_report(audit_log: dict, project_path: Path) -> str:
    """从审核日志生成 HTML 审核报告。"""
    summary = audit_log.get("summary", {})
    conclusion = audit_log.get("conclusion", {})
    findings = audit_log.get("findings", [])
    logic_findings = audit_log.get("logic_consistency_findings", [])
    tasks = audit_log.get("tasks", [])
    
    # 构建 doc_id → 文件名 映射
    doc_id_to_file: dict = {}
    for task in tasks:
        for doc in task.get("documents", []):
            doc_id_to_file[doc.get("id", "")] = doc.get("original_file", doc.get("id", ""))

    # 按文档分组的发现
    by_doc: dict = {}
    for f in findings:
        doc_id = f.get("doc_id", "")
        by_doc.setdefault(doc_id, []).append(f)

    # 按分部分项分组的发现
    by_subdivision: dict = {}
    for f in findings:
        for task in tasks:
            if f.get("doc_id") in [d.get("id") for d in task.get("documents", [])]:
                key = task.get("sub_label", "未分类")
                if task.get("item_label"):
                    key += f" → {task['item_label']}"
                by_subdivision.setdefault(key, []).append(f)
                break

    # ===== 生成图表 =====
    # 环形图：整体审核结果分布
    pie_values = {
        "通过": summary.get("pass", 0),
        "不通过": summary.get("fail", 0),
        "存疑": summary.get("suspicious", 0),
        "待AI": summary.get("needs_ai", 0),
        "不适用": summary.get("not_applicable", 0),
    }
    pie_chart_html = _generate_pie_chart_svg(pie_values)

    # 条形图：分部分项问题分布（仅显示有问题的分部分项）
    bar_data = []
    for key, fs in by_subdivision.items():
        fl = sum(1 for f in fs if f.get("result", "") == "fail")
        s = sum(1 for f in fs if f.get("result", "") == "suspicious")
        bar_data.append((key, fl, s))
    bar_data.sort(key=lambda x: x[1] + x[2], reverse=True)
    bar_chart_html = _generate_bar_chart_svg(bar_data)

    # 生成分部分项汇总行
    subdivision_rows = ""
    for key, fs in by_subdivision.items():
        p = sum(1 for f in fs if f.get("result", "") == "pass")
        fl = sum(1 for f in fs if f.get("result", "") == "fail")
        s = sum(1 for f in fs if f.get("result", "") == "suspicious")
        ai = sum(1 for f in fs if f.get("result", "") == "needs_ai")
        status = "✅" if fl == 0 and s == 0 else ("⚠️" if s > 0 else "❌")
        subdivision_rows += f"""
        <tr>
          <td>{status}</td>
          <td>{key}</td>
          <td>{len(fs)}</td>
          <td>{p}</td>
          <td>{fl}</td>
          <td>{s}</td>
          <td>{ai}</td>
        </tr>"""

    # 生成文档级汇总行
    doc_summary_rows = ""
    for doc_id, fs in by_doc.items():
        fname = doc_id_to_file.get(doc_id, doc_id)
        p = sum(1 for f in fs if f.get("result", "") == "pass")
        fl = sum(1 for f in fs if f.get("result", "") == "fail")
        s = sum(1 for f in fs if f.get("result", "") == "suspicious")
        ai = sum(1 for f in fs if f.get("result", "") == "needs_ai")
        na = sum(1 for f in fs if f.get("result", "") == "not_applicable")
        status = "✅" if fl == 0 and s == 0 else ("⚠️" if s > 0 else "❌")
        # 截断长文件名
        display_name = fname if len(fname) <= 50 else fname[:47] + "..."
        doc_summary_rows += f"""
        <tr>
          <td>{status}</td>
          <td title="{fname}">{display_name}</td>
          <td>{len(fs)}</td>
          <td>{p}</td>
          <td>{fl}</td>
          <td>{s}</td>
          <td>{ai}</td>
          <td>{na}</td>
        </tr>"""

    # 生成发现详情行（仅显示非pass项，限制100条）
    BADGE = {"pass": "✅", "fail": "❌", "suspicious": "⚠️", "needs_ai": "🤖", "not_applicable": "➖"}
    SEV_BADGE = {"high": "🔴", "medium": "🟡", "low": "⚪"}
    
    non_pass_findings = [f for f in findings if f.get("result") != "pass" and f.get("result") != "not_applicable"]
    finding_rows = ""
    for f in non_pass_findings[:100]:
        sev = f.get("severity", "low")
        result = f.get("result", "")
        doc_id = f.get("doc_id", "")
        fname = doc_id_to_file.get(doc_id, doc_id)
        display_name = fname if len(fname) <= 30 else fname[:27] + "..."
        finding_rows += f"""
        <tr>
          <td>{BADGE.get(result, '')}</td>
          <td>{SEV_BADGE.get(sev, '')} {sev}</td>
          <td>{f.get('checklist_id', '')}</td>
          <td>{f.get('category', '')}</td>
          <td>{f.get('check_item', '')}</td>
          <td title="{fname}">{display_name}</td>
          <td>{f.get('finding', '')}</td>
          <td>{f.get('spec', '')}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>审核报告 — {audit_log.get('project_name', '')}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: "Microsoft YaHei", "PingFang SC", sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
  .header {{ background: #fff; padding: 30px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
  .header h1 {{ font-size: 24px; margin-bottom: 10px; }}
  .header .meta {{ color: #666; font-size: 14px; }}
  .section {{ background: #fff; padding: 24px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
  .section h2 {{ font-size: 18px; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #1a73e8; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-bottom: 20px; }}
  .stat {{ background: #f8f9fa; padding: 16px; border-radius: 6px; text-align: center; }}
  .stat .value {{ font-size: 28px; font-weight: bold; color: #1a73e8; }}
  .stat .label {{ font-size: 12px; color: #666; margin-top: 4px; }}
  .stat.fail .value {{ color: #d93025; }}
  .stat.suspicious .value {{ color: #e37400; }}
  .stat.ai .value {{ color: #9334e6; }}
  .stat.warn .value {{ color: #e37400; }}
  .filter-bar {{ margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap; }}
  .filter-bar button {{ padding: 6px 14px; border: 1px solid #ddd; border-radius: 20px; background: #fff; cursor: pointer; font-size: 13px; }}
  .filter-bar button:hover {{ background: #e8f0fe; border-color: #1a73e8; }}
  .filter-bar button.active {{ background: #1a73e8; color: #fff; border-color: #1a73e8; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #e8eaed; }}
  th {{ background: #f8f9fa; font-weight: 600; white-space: nowrap; position: sticky; top: 0; }}
  tr:hover {{ background: #e8f0fe; }}
  .table-wrap {{ max-height: 500px; overflow-y: auto; border: 1px solid #e8eaed; border-radius: 4px; }}
  .table-wrap table {{ border: none; }}
  .conclusion {{ padding: 20px; border-radius: 8px; margin-bottom: 16px; }}
  .conclusion.pass {{ background: #e6f4ea; border: 1px solid #34a853; }}
  .conclusion.fail {{ background: #fce8e6; border: 1px solid #d93025; }}
  .conclusion.suspicious {{ background: #fef7e0; border: 1px solid #e37400; }}
  .conclusion h3 {{ font-size: 16px; margin-bottom: 8px; }}
  .rec {{ padding: 8px 12px; background: #f8f9fa; border-left: 3px solid #1a73e8; margin-bottom: 8px; font-size: 14px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
  .badge-fail {{ background: #fce8e6; color: #d93025; }}
  .badge-suspicious {{ background: #fef7e0; color: #e37400; }}
  .badge-ai {{ background: #f3e8fd; color: #9334e6; }}
  .chart-container {{ display: flex; align-items: center; gap: 24px; margin: 16px 0; flex-wrap: wrap; }}
  .chart-svg {{ flex-shrink: 0; }}
  .chart-legend {{ display: flex; flex-direction: column; gap: 6px; }}
  .chart-legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 13px; color: #555; }}
  .chart-legend-dot {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }}
  .charts-row {{ display: flex; gap: 24px; flex-wrap: wrap; align-items: flex-start; }}
  .charts-row .chart-container {{ flex: 1; min-width: 300px; }}
  @media print {{ body {{ background: #fff; }} .section {{ box-shadow: none; border: 1px solid #ddd; }} }}
</style>
</head>
<body>
<div class="container">

  <!-- 页眉 -->
  <div class="header">
    <h1>民航施工资料合规审核报告</h1>
    <div class="meta">
      <p>项目：{audit_log.get('project_name', '')}</p>
      <p>审核编号：{audit_log.get('audit_id', '')} | 审核时间：{audit_log.get('audit_completed_at', '')}</p>
      <p>前置条件：阶段={audit_log.get('preconditions', {}).get('stage', '')} | 资料性质={audit_log.get('preconditions', {}).get('nature', '')} | 范围={audit_log.get('preconditions', {}).get('scope', '')}</p>
    </div>
  </div>

  <!-- 一、审核概要 -->
  <div class="section">
    <h2>一、审核概要</h2>
    <div class="stats">
      <div class="stat"><div class="value">{summary.get('documents_audited', 0)}</div><div class="label">审核文档数</div></div>
      <div class="stat"><div class="value">{summary.get('total_findings', 0)}</div><div class="label">总检查项</div></div>
      <div class="stat"><div class="value">{summary.get('pass', 0)}</div><div class="label">✅ 通过</div></div>
      <div class="stat fail"><div class="value">{summary.get('fail', 0)}</div><div class="label">❌ 不通过</div></div>
      <div class="stat suspicious"><div class="value">{summary.get('suspicious', 0)}</div><div class="label">⚠️ 存疑</div></div>
      <div class="stat ai"><div class="value">{summary.get('needs_ai', 0)}</div><div class="label">🤖 待AI</div></div>
      <div class="stat"><div class="value">{summary.get('not_applicable', 0)}</div><div class="label">➖ 不适用</div></div>
    </div>

    {pie_chart_html}

    <div class="conclusion {'fail' if '不合格' in conclusion.get('overall', '') else ('pass' if '合格' in conclusion.get('overall', '') else 'suspicious')}">
      <h3>总体结论</h3>
      <p>{conclusion.get('overall', '')}</p>
    </div>

    <h3>整改建议</h3>
    {"".join(f'<div class="rec">{r}</div>' for r in conclusion.get('recommendations', [])) or '<p>无</p>'}
  </div>

  <!-- 二、文档级审核汇总 -->
  <div class="section">
    <h2>二、文档审核汇总</h2>
    <p style="color:#666;font-size:13px;margin-bottom:12px;">共 {len(by_doc)} 份文档，按检查项数降序排列</p>
    <div class="table-wrap">
    <table>
      <thead>
        <tr><th>状态</th><th>文档</th><th>检查项</th><th>通过</th><th>不通过</th><th>存疑</th><th>待AI</th><th>不适用</th></tr>
      </thead>
      <tbody>
        {doc_summary_rows}
      </tbody>
    </table>
    </div>
  </div>

  <!-- 三、分部分项审核汇总 -->
  <div class="section">
    <h2>三、分部分项审核汇总</h2>
    {bar_chart_html}
    <div class="table-wrap">
    <table>
      <thead>
        <tr><th>状态</th><th>分部分项</th><th>检查项</th><th>通过</th><th>不通过</th><th>存疑</th><th>待AI</th></tr>
      </thead>
      <tbody>
        {subdivision_rows}
      </tbody>
    </table>
    </div>
  </div>

  <!-- 四、规范对账发现（仅显示需关注项） -->
  <div class="section">
    <h2>四、规范对账发现（需关注项）</h2>
    <p style="color:#666;font-size:13px;margin-bottom:12px;">
      共 <span class="badge badge-fail">{summary.get('fail', 0)} 项不通过</span>
      <span class="badge badge-suspicious">{summary.get('suspicious', 0)} 项存疑</span>
      <span class="badge badge-ai">{summary.get('needs_ai', 0)} 项待AI</span>
      {"（仅显示前 100 条，完整数据见审核日志 JSON）" if len(non_pass_findings) > 100 else ""}
    </p>
    <div class="table-wrap">
    <table>
      <thead>
        <tr><th>结果</th><th>严重</th><th>编号</th><th>类别</th><th>检查项</th><th>文档</th><th>发现</th><th>规范</th></tr>
      </thead>
      <tbody>
        {finding_rows or '<tr><td colspan="8" style="text-align:center;color:#999;">（无需要关注的问题）</td></tr>'}
      </tbody>
    </table>
    </div>
  </div>

  <!-- 五、逻辑一致性检查 -->
  <div class="section">
    <h2>五、逻辑一致性检查</h2>
    <div class="table-wrap">
    <table>
      <thead>
        <tr><th>编号</th><th>类别</th><th>检查项</th><th>规则</th><th>发现</th></tr>
      </thead>
      <tbody>
        {"".join(f'''<tr><td>{f.get('checklist_id', '')}</td><td>{f.get('category', '')}</td><td>{f.get('check_item', '')}</td><td style="max-width:300px;">{f.get('criteria', '')}</td><td>{f.get('finding', '')}</td></tr>''' for f in logic_findings)}
      </tbody>
    </table>
    </div>
  </div>

  <!-- 页脚 -->
  <div class="section" style="text-align:center;color:#999;font-size:12px;">
    <p>本报告由民航施工资料合规审核 Skill v6.0 自动生成</p>
    <p>审核编号：{audit_log.get('audit_id', '')} | 生成时间：{datetime.now().isoformat(timespec='seconds')}</p>
    <p>铁律 R-08：未发现问题的项目不代表"全部合格"，仅表示"未发现不符合项"</p>
  </div>

</div>
</body>
</html>"""
    return html


# ========== CLI 入口 ==========
def main() -> None:
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

    # Phase 1：建立数据底座
    p_build = sub.add_parser("build", help="建立数据底座（Phase 1）")
    p_build.add_argument("project_path", help="项目文件夹路径")
    p_build.add_argument(
        "--engine", choices=["auto", "vision", "paddle"], default="auto",
        help="OCR 引擎（默认 auto）"
    )
    p_build.add_argument(
        "--incremental", action="store_true",
        help="增量模式：仅处理新文件或已变更文件"
    )
    p_build.add_argument(
        "--out", default="数据底座",
        help="数据底座目录名（默认：数据底座）"
    )
    p_build.add_argument(
        "--preconditions",
        help="前置信息 JSON 文件路径（含 stage/nature/scope/ocr_engine/special_notes/excluded_files/expected_rows）"
    )
    p_build.add_argument(
        "--expected-rows",
        help="预期行数 JSON 文件路径，格式：{\"文件名模式\": 行数}"
    )
    p_build.set_defaults(func=cmd_build)

    # 一键审核（单文件 OCR + 混淆检测 + Vision复核）
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

    # Phase 3：正式审核（多Agent并行）
    p_review = sub.add_parser("review", help="正式审核（Phase 3）— 支持多Agent并行")
    p_review.add_argument("project_path", help="项目文件夹路径")
    p_review.add_argument(
        "--out", default="数据底座",
        help="数据底座目录名（默认：数据底座）"
    )
    p_review.add_argument(
        "--split-by", choices=["professional", "sub", "item"], default="sub",
        help="任务拆分粒度：professional(专业级)/sub(分部级)/item(分项级)，默认 sub"
    )
    p_review.add_argument(
        "--task-id",
        help="只执行指定任务（多 Agent 并行模式）"
    )
    p_review.add_argument(
        "--tasks-file",
        help="任务包 JSON 文件路径"
    )
    p_review.add_argument(
        "--dry-run", action="store_true",
        help="仅生成任务包，不执行审核"
    )
    p_review.add_argument(
        "--force", action="store_true",
        help="跳过 human_verified 闸门（仅测试用）"
    )
    p_review.set_defaults(func=cmd_review)

    # Phase 4：生成审核报告
    p_report = sub.add_parser("report", help="生成审核报告（Phase 4）")
    p_report.add_argument("project_path", help="项目文件夹路径")
    p_report.add_argument(
        "--out", default="数据底座",
        help="数据底座目录名（默认：数据底座）"
    )
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
