#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_report.py — 审核报告质检工具（"验钞机"）

对任何一份审核报告做独立质检，不依赖报告是谁生成的：
  1. 对账校验：报告中声称的记录数 / 审核文件数 vs 数据底座 index.json
  2. 依据校验：报告中每条问题是否带"规范号+条款"引用（如 MH/T 5078.1-2024 第 6.2.7 条）
  3. 可选：HTML 报告中的统计数字 vs index.json documents 记录数

用法：
  python verify_report.py <项目路径> [--report <报告文件路径>] [--out <数据底座目录名>]

退出码：0=通过  1=不通过（有具体问题清单）
"""

import argparse
import json
import re
import sys
from pathlib import Path

# 规范引用模式：标准号（GB/MH/JGJ/MH-T 等）+ 可选条款号
SPEC_PATTERNS = [
    re.compile(r"(?:GB|MH|JGJ|JC|CCAR|JT|TB)[/\s]?[·]?[\d.]+[—-]\d+"),          # MH/T 5078.1-2024 / GB 50202-2018
    re.compile(r"MH/T\s*[\d.]+"),                                               # MH/T 5078
    re.compile(r"CCAR[-\s]?\d+"),                                               # CCAR-165
    re.compile(r"第\s*[\d.]+\s*条"),                                             # 第 6.2.7 条
    re.compile(r"[\d]+\.[\d]+\.[\d]+\s*条"),                                     # 6.2.7 条
]
# 判定为"有依据"的最少命中数（一条规范号 或 一条条款号）
MIN_HITS = 1


def load_index(project_path: Path, out_dir: str) -> dict:
    for cand in (project_path / out_dir / "index.json", project_path / "index.json"):
        if cand.exists():
            return json.loads(cand.read_text(encoding="utf-8"))
    return {}


def extract_text(report_file: Path) -> str:
    text = report_file.read_text(encoding="utf-8", errors="replace")
    if report_file.suffix.lower() == ".html":
        # 去标签，保留文字内容（统计数字、引用都在正文里）
        text = re.sub(r"<[^>]+>", " ", text)
    return text


def check_references(findings: list) -> tuple:
    """检查每条 finding 是否带规范引用。返回 (缺依据的条目, 总条数)。"""
    missing = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        blob = json.dumps(f, ensure_ascii=False)
        hits = sum(1 for p in SPEC_PATTERNS if p.search(blob))
        if hits < MIN_HITS:
            missing.append(f.get("id", f.get("rule", "?")))
    return missing, len(findings)


def check_stats_alignment(text: str, index: dict) -> list:
    """HTML 报告正文中的'共 N 条记录/共 M 份资料'与底座对账。"""
    problems = []
    docs = audited_docs(index)
    if not docs:
        return problems
    n_docs = len(docs)
    # 报告里写"共 X 份资料/审核了 X 份"
    m = re.search(r"共\s*(\d+)\s*份", text)
    if m:
        claimed = int(m.group(1))
        if claimed != n_docs:
            problems.append(
                f"报告称审核 {claimed} 份资料，数据底座实际 {n_docs} 份（差 {abs(claimed-n_docs)}）")
    # 每份资料的记录数（底座 data_file 的 rows 长度）vs 报告中同名表的记录数
    for doc in docs:
        name = Path(doc.get("original_file", "")).stem
        if not name:
            continue
        data_file = doc.get("data_file")
        if not data_file:
            continue
        df = None
        for base in (index.get("project_path", ""),):
            if base:
                cand = Path(base) / data_file
                if cand.exists():
                    df = cand
                    break
        if df is None:
            # 相对底座目录找
            idx_path = project_path / out_dir_name / "index.json"
            if idx_path.exists():
                df = idx_path.parent / data_file
        if df is None or not df.exists():
            continue
        try:
            data = json.loads(df.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows = data.get("rows") or data.get("structured_rows") or []
        if not isinstance(rows, list) or not rows:
            continue
        n_rows = len(rows)
        # 报告中该表名的记录数声称，如 "NB(X1-X3) 共 494 条" / "施工日志：894 条记录"
        for m2 in re.finditer(
                re.escape(name[:12]) + r"[^。\n]{0,40}?共?\s*(\d+)\s*(?:条|行|根|记录)", text):
            claimed = int(m2.group(1))
            # 允许 10% 容差（报告可能只统计合格/异常子集）
            if abs(claimed - n_rows) > max(3, n_rows * 0.1):
                problems.append(
                    f"报告称 {name[:20]}… 有 {claimed} 条，数据底座实际 {n_rows} 条（差 {abs(claimed-n_rows)}）")
            break
    return problems


def audited_docs(index: dict) -> list:
    """底座中被审核文件（排除图纸/依据类 reference 文档）。"""
    return [d for d in index.get("documents", [])
            if d.get("doc_role") != "reference" and d.get("original_file")]


def check_certificates_alignment(text: str, index: dict) -> list:
    """v10.4 B3：报告声称的合格证台账记录数 vs 底座 ledgers.certificates 实际数。

    Why：合格证台账是审核期刷新的活数据（review_audit 步骤 5.6 原子刷新），
    报告若引用旧底数或手写台账数，追溯链对不上 —— 必须对账。
    底座无 certificates 台账时跳过（非材料类项目不强制）。
    """
    problems = []
    certs = (index.get("ledgers") or {}).get("certificates") or []
    if not certs:
        return problems
    n = len(certs)
    for m in re.finditer(
            r"合格证台账[^\n。]{0,30}?共?\s*(\d+)\s*(?:条|项|份|记录)", text):
        claimed = int(m.group(1))
        if claimed != n:
            problems.append(
                f"报告称合格证台账 {claimed} 条，数据底座实际 {n} 条（差 {abs(claimed - n)}）")
        break  # 只对第一处声称对账
    return problems


def main():
    global project_path, out_dir_name
    parser = argparse.ArgumentParser(description="审核报告质检（对账+依据）")
    parser.add_argument("project_path", help="项目文件夹路径")
    parser.add_argument("--report", help="报告文件路径（默认自动在项目根目录找 审核报告.html/md）")
    parser.add_argument("--out", default="数据底座", help="数据底座目录名")
    args = parser.parse_args()

    project_path = Path(args.project_path).resolve()
    out_dir_name = args.out
    index = load_index(project_path, args.out)
    if not index:
        print("⛔ 质检失败：未找到数据底座 index.json（报告无法对账）")
        return 1

    # 定位报告
    report_file = Path(args.report) if args.report else None
    if report_file is None or not report_file.exists():
        for cand in (project_path / "审核报告.html", project_path / "审核报告.md"):
            if cand.exists():
                report_file = cand
                break
    if report_file is None or not report_file.exists():
        print(f"⛔ 质检失败：未找到报告文件（{project_path}\\审核报告.html / .md）")
        return 1

    text = extract_text(report_file)
    problems = []

    # 1. 审核文件数对账（排除图纸依据类 reference 文档）
    docs = audited_docs(index)
    n_docs = len(docs)
    m = re.search(r"共\s*(\d+)\s*份", text)
    if m and int(m.group(1)) != n_docs:
        problems.append(f"报告称 {m.group(1)} 份资料，底座实际 {n_docs} 份")

    # 2. 记录数对账
    problems.extend(check_stats_alignment(text, index))

    # 2.5 合格证台账对账（v10.4 B3：ledgers.certificates）
    problems.extend(check_certificates_alignment(text, index))

    # 3. 依据校验：优先从审核日志 findings 检查；HTML 报告正文兜底
    audit_dir = project_path / args.out / "审核日志"
    findings = []
    log_files = sorted(audit_dir.glob("AU-*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True) if audit_dir.exists() else []
    if log_files:
        log = json.loads(log_files[0].read_text(encoding="utf-8"))
        findings = log.get("findings", [])
    if findings:
        missing, total = check_references(findings)
        if missing:
            problems.append(
                f"审核日志 {total} 条问题中 {len(missing)} 条无规范依据：{missing[:10]}")
    else:
        # 无日志时，从报告正文数问题条目与依据出现次数（粗检）
        n_findings = len(re.findall(r"(?:FATAL|致命|Sanity|待核实|Best Practice|建议)[^。\n]{0,80}", text))
        n_refs = sum(1 for p in SPEC_PATTERNS for _ in p.finditer(text))
        if n_findings > 3 and n_refs < n_findings * 0.5:
            problems.append(
                f"报告约 {n_findings} 条问题，但规范引用仅 {n_refs} 处（依据不足一半）")

    # ===== 输出 =====
    print("=" * 60)
    print(f"📋 报告质检：{report_file.name}")
    print(f"   数据底座：{n_docs} 份资料")
    if not problems:
        print("✅ 质检通过：文件数/记录数对账一致，问题条目均有规范依据")
        return 0
    print(f"⛔ 质检不通过（{len(problems)} 项）：")
    for p in problems:
        print(f"   - {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
