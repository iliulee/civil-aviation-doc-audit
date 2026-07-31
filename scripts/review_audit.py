# -*- coding: utf-8 -*-
"""
review_audit.py — 正式审核流水线（Phase 3）
=============================================

职责：
  1. 审核前置检查（human_verified 闸门）
  2. 规范对账审核（逐条检查清单）
  3. 逻辑一致性检查（10 子项）
  4. 运算规范审核（按需）
  5. 生成审核日志 JSON

审核逻辑说明：
  - 每条检查项生成一个 Finding（发现），包含：code、severity、finding、evidence、spec
  - 规范对账：逐条检查清单，对每条检查项给出"通过/不通过/存疑/不适用"
  - 逻辑一致性：跨文档对比，检查时间轴、数量累计、人员交叉等
  - 结论四级分类：高/中/低/存疑（铁律 R-18）

用法：
  python scripts/review_audit.py <项目文件夹路径> [选项]

选项：
  --out <目录>              审核日志输出目录（默认 数据底座/审核日志）
  --split-by <粒度>         任务拆分粒度：professional/sub/item（默认 sub）
  --task-id <id>            只执行指定任务（多 Agent 并行模式）
  --tasks-file <path>       任务包 JSON 文件路径（多 Agent 并行模式）
  --dry-run                 仅生成任务包，不执行审核
  --force                   跳过 human_verified 闸门（仅测试用）
"""

import argparse
import collections
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 允许 import 同目录下的模块
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# SKILL 根目录（scripts/ 的上一级）
SKILL_DIR = SCRIPT_DIR.parent

from audit_config import (  # noqa: E402
    GENERAL_CHECKLIST,
    AIRFIELD_CHECKLIST,
    LOGIC_CONSISTENCY_CHECKS,
    group_documents_for_audit,
    get_checklist_for_subdivision,
    get_checklist_for_professional,
    get_subdivision_info,
    get_full_subdivision_tree,
    SUBDIVISION_HIERARCHY,
)

from rule_engine import (  # noqa: E402
    RuleLoader,
    RuleMatcher,
    SingleDocChecker,
    CrossDocChecker,
    CrossUnitChecker,
    ViolationReporter,
    SCOPE_SINGLE_DOC,
    SCOPE_CROSS_DOC,
    SCOPE_CROSS_UNIT,
)

try:  # noqa: E402
    from rule_lifecycle import RuleLifecycleManager  # noqa: E402
    _HAS_LIFECYCLE = True
except ImportError:  # pragma: no cover - 容错降级
    RuleLifecycleManager = None  # type: ignore[assignment]
    _HAS_LIFECYCLE = False

# D-1/D-2：规则效力监控 + 审核记忆流（容错降级，缺失不影响主审核流程）
try:  # noqa: E402
    from rule_monitor import RuleMonitor  # noqa: E402
    _HAS_RULE_MONITOR = True
except ImportError:  # pragma: no cover - 容错降级
    RuleMonitor = None  # type: ignore[assignment]
    _HAS_RULE_MONITOR = False

try:  # noqa: E402
    from audit_memory import AuditMemory  # noqa: E402
    _HAS_AUDIT_MEMORY = True
except ImportError:  # pragma: no cover - 容错降级
    AuditMemory = None  # type: ignore[assignment]
    _HAS_AUDIT_MEMORY = False


# ========== 工具函数 ==========
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def severity_label(level: str) -> str:
    """严重程度中文标签。"""
    return {"fatal": "严重", "high": "高", "medium": "中", "low": "低", "suspicious": "存疑"}.get(level, level)


# ========== 审核前置检查 ==========
def check_human_verified(index: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    检查所有被审核文件是否已完成人工核对。
    返回 (全部通过, 未通过文件列表)。
    """
    unverified = []
    for doc in index.get("documents", []):
        if not doc.get("human_verified", False):
            unverified.append(doc.get("original_file", doc.get("id", "?")))
    return len(unverified) == 0, unverified


# ========== 规范对账 ==========
def audit_checklist_item(
    item: Dict[str, Any],
    doc_data: Dict[str, Any],
    doc_meta: Dict[str, Any],
) -> Dict[str, Any]:
    """
    对单个文档执行单条检查清单的审核。
    返回一个 Finding 字典。

    审核策略：
      - 目前使用启发式规则做初步筛查
      - 复杂判断（如"方案内容与实际施工方法吻合"）标记为需要 AI 深度审核
      - 程序能自动判断的（如签字数量、编号连续性）直接给出结论
    """
    finding = {
        "checklist_id": item["id"],
        "category": item.get("category", ""),
        "check_item": item.get("item", ""),
        "criteria": item.get("criteria", ""),
        "spec": item.get("spec", ""),
        "doc_id": doc_meta.get("id", ""),
        "doc_file": doc_meta.get("original_file", ""),
        "severity": "low",
        "result": "pass",  # pass / fail / suspicious / not_applicable / needs_ai
        "finding": "",
        "evidence": "",
        "checked_at": now_iso(),
    }

    item_id = item["id"]
    rows = doc_data.get("rows", [])
    doc_type = doc_meta.get("doc_type", "")

    # ===== 通用检查项 =====
    if item_id == "G-1.1.1":  # 施工组织设计是否已报审
        finding["result"] = "needs_ai"
        finding["finding"] = "需检查审批表、审批意见、签字盖章是否齐全"
        finding["severity"] = "high"

    elif item_id == "G-1.1.3":  # 技术交底是否覆盖各工序
        finding["result"] = "needs_ai"
        finding["finding"] = "需检查技术交底记录覆盖范围和签字情况"
        finding["severity"] = "medium"

    elif item_id == "G-1.1.5":  # 设计变更是否闭环
        finding["result"] = "needs_ai"
        finding["finding"] = "需检查变更单、审批意见、实施记录是否齐全"
        finding["severity"] = "high"

    elif item_id == "G-1.2.1":  # 施工日志是否连续
        if rows:
            # 检查是否有大段空白（连续多页无数据）
            pages = sorted(set(r.get("page", 0) for r in rows))
            gaps = []
            for i in range(1, len(pages)):
                if pages[i] - pages[i - 1] > 5:
                    gaps.append(f"第{pages[i-1]}页→第{pages[i]}页")
            if gaps:
                finding["result"] = "suspicious"
                finding["severity"] = "medium"
                finding["finding"] = f"发现页面不连续，存在大段空白：{', '.join(gaps)}"
                finding["evidence"] = f"共 {len(pages)} 个页面，{len(gaps)} 处断档"
            else:
                finding["result"] = "pass"
                finding["finding"] = "页面连续，未发现大段空白"
        else:
            finding["result"] = "not_applicable"

    elif item_id == "G-1.2.2":  # 检验批是否及时签认
        finding["result"] = "needs_ai"
        finding["finding"] = "需与施工日志工序时间对照，判断签认是否及时"
        finding["severity"] = "medium"

    elif item_id == "G-1.2.4":  # 隐蔽工程记录是否在覆盖前签认
        finding["result"] = "needs_ai"
        finding["finding"] = "需与下一道工序时间对照，判断隐蔽验收是否在覆盖前完成"
        finding["severity"] = "high"

    elif item_id == "G-1.3.1":  # 签字盖章是否齐全
        finding["result"] = "needs_ai"
        finding["finding"] = "需检查施工员、质检员、监理工程师签字是否齐全"
        finding["severity"] = "high"

    elif item_id == "G-1.3.3":  # 编号是否连续系统
        # 检查桩号连续性
        pile_nos = []
        for r in rows:
            pn = r.get("pile_no", "")
            if pn and isinstance(pn, str):
                pile_nos.append(pn)
        if pile_nos:
            # 简单检查：提取数字部分
            nums = []
            for pn in pile_nos:
                import re
                m = re.search(r"(\d+)", str(pn))
                if m:
                    nums.append(int(m.group(1)))
            if nums:
                nums_sorted = sorted(nums)
                breaks = []
                for i in range(1, len(nums_sorted)):
                    if nums_sorted[i] - nums_sorted[i - 1] > 1:
                        breaks.append(f"{nums_sorted[i-1]}→{nums_sorted[i]}")
                if breaks:
                    finding["result"] = "suspicious"
                    finding["severity"] = "medium"
                    finding["finding"] = f"桩号编号不连续，发现断号：{', '.join(breaks[:5])}"
                    finding["evidence"] = f"共 {len(nums)} 个桩号，{len(breaks)} 处断号"
                else:
                    finding["result"] = "pass"
                    finding["finding"] = f"桩号编号连续（{nums_sorted[0]}～{nums_sorted[-1]}，共 {len(nums)} 个）"
        else:
            finding["result"] = "not_applicable"

    elif item_id == "G-1.4.1":  # 项目部主要管理人员是否报审
        finding["result"] = "needs_ai"
        finding["finding"] = "需与实际签字人对照，检查报审人员是否覆盖"
        finding["severity"] = "medium"

    elif item_id == "G-1.4.2":  # 特种作业人员是否持证
        finding["result"] = "needs_ai"
        finding["finding"] = "需与特种作业记录对照，检查证件有效期"
        finding["severity"] = "high"

    # ===== 场道工程专项检查 =====
    elif item_id == "A-2.1.3":  # 填方检验批
        if "填方" in doc_type or "碾压" in doc_type:
            # 检查是否有压实度相关字段
            has_compaction = any("压实" in str(k) for k in (rows[0].keys() if rows else []))
            if has_compaction:
                finding["result"] = "pass"
                finding["finding"] = "检测到压实度相关数据字段"
            else:
                finding["result"] = "suspicious"
                finding["severity"] = "medium"
                finding["finding"] = "未检测到压实度相关字段，可能 OCR 遗漏或资料类型不匹配"
        else:
            finding["result"] = "not_applicable"

    elif item_id == "A-2.1.4":  # 强夯施工记录
        if "强夯" in doc_type or "夯击" in doc_type:
            finding["result"] = "needs_ai"
            finding["finding"] = "需检查夯击能、遍数、搭接、点距、收锤标准"
            finding["severity"] = "high"
        else:
            finding["result"] = "not_applicable"

    elif item_id == "A-2.1.5":  # 特殊地基处理记录
        if any(kw in doc_type for kw in ["碎石桩", "CFG桩", "PHC桩", "桩"]):
            # 检查桩位数据完整性
            required_fields = ["pile_no", "actual_length", "volume"]
            missing = [f for f in required_fields if f not in (rows[0].keys() if rows else [])]
            if missing:
                finding["result"] = "suspicious"
                finding["severity"] = "high"
                finding["finding"] = f"桩基施工记录缺少关键字段：{', '.join(missing)}"
                finding["evidence"] = f"现有字段：{list(rows[0].keys()) if rows else '无数据'}"
            else:
                # 检查数据完整性
                null_count = sum(1 for r in rows if r.get("pile_no") is None)
                if null_count > len(rows) * 0.1:
                    finding["result"] = "suspicious"
                    finding["severity"] = "medium"
                    finding["finding"] = f"桩号缺失率 {null_count}/{len(rows)}（{null_count/len(rows):.0%}），超过 10%"
                else:
                    finding["result"] = "pass"
                    finding["finding"] = f"桩基数据字段完整，共 {len(rows)} 条记录"
        else:
            finding["result"] = "not_applicable"

    elif item_id == "A-2.1.6":  # 高填方监测记录
        if "填方" in doc_type or "监测" in doc_type:
            finding["result"] = "needs_ai"
            finding["finding"] = "需检查沉降观测、位移观测数据的连续性和频率"
            finding["severity"] = "high"
        else:
            finding["result"] = "not_applicable"

    elif item_id == "A-2.2.2":  # 底基层/基层检验批
        if any(kw in doc_type for kw in ["基层", "底基层", "水稳"]):
            finding["result"] = "needs_ai"
            finding["finding"] = "需检查厚度、压实度、平整度、横坡、7d无侧限抗压强度"
            finding["severity"] = "high"
        else:
            finding["result"] = "not_applicable"

    elif item_id == "A-2.3.1":  # 水泥混凝土面层检验批
        if any(kw in doc_type for kw in ["混凝土", "水泥道面"]):
            finding["result"] = "needs_ai"
            finding["finding"] = "需检查抗弯拉强度、平整度、纹理深度、厚度、相邻板高差"
            finding["severity"] = "high"
        else:
            finding["result"] = "not_applicable"

    # ===== 默认：需要 AI 深度审核 =====
    else:
        finding["result"] = "needs_ai"
        finding["finding"] = "此项需 AI 结合规范原文和资料内容进行深度审核"
        finding["severity"] = "medium"

    return finding


def audit_document(
    doc_meta: Dict[str, Any],
    corrected_data: Dict[str, Any],
    checklist: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    对单个文档执行完整的规范对账审核。
    返回 Finding 列表。
    """
    findings: List[Dict[str, Any]] = []

    for item in checklist:
        finding = audit_checklist_item(item, corrected_data, doc_meta)
        findings.append(finding)

    return findings


# ========== 逻辑一致性检查 ==========
def audit_logic_consistency(
    all_docs: List[Dict[str, Any]],
    all_data: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    跨文档逻辑一致性检查（10 子项，铁律 R-09）。

    Args:
        all_docs: index.json 中所有文档的元数据列表
        all_data: {doc_id: corrected_data} 映射

    Returns:
        Finding 列表
    """
    findings: List[Dict[str, Any]] = []

    for check in LOGIC_CONSISTENCY_CHECKS:
        finding = {
            "checklist_id": check["id"],
            "category": check.get("category", ""),
            "check_item": check.get("name", ""),
            "criteria": check.get("rule", ""),
            "spec": "MH/T 5078.1（逻辑一致性铁律）",
            "doc_id": "ALL",
            "doc_file": "跨文档检查",
            "severity": "high",
            "result": "needs_ai",
            "finding": "跨文档逻辑一致性检查需 AI 综合判断",
            "evidence": "",
            "checked_at": now_iso(),
        }

        check_id = check["id"]

        # L-01: 材料报审日期 ≤ 材料进场日期 ≤ 检验批日期
        if check_id == "L-01":
            finding["finding"] = "需检查材料报审→进场→使用的日期顺序，确保时间顺向"
            finding["evidence"] = f"共 {len(all_docs)} 份文档参与交叉验证"

        # L-02: 隐蔽工程验收日期 ≤ 下道工序开工日期
        elif check_id == "L-02":
            finding["finding"] = "需检查隐蔽工程验收记录与下道工序开工日期，确保先验收后覆盖"

        # L-03: 分项 ≤ 分部 ≤ 单位工程验收日期
        elif check_id == "L-03":
            finding["finding"] = "需检查分项→分部→单位工程验收日期的时间顺序"

        # L-04: 监理通知单日期 ≤ 整改回复日期 ≤ 整改复核日期
        elif check_id == "L-04":
            finding["finding"] = "需检查监理通知→整改回复→复核的闭环时间线"

        # L-05: 设计变更日期 ≤ 实施日期
        elif check_id == "L-05":
            finding["finding"] = "需检查设计变更审批日期与实施日期，确保先审批后实施"

        # L-06: 施工日志日期 vs 检验批/隐蔽/监理日志日期
        elif check_id == "L-06":
            finding["finding"] = "需交叉比对同一工序在不同资料中的日期是否一致"

        # L-07: 检验批工程量累计 = 分项工程工程量
        elif check_id == "L-07":
            # 尝试自动计算（如果有数量字段）
            total_rows = sum(len(data.get("rows", [])) for data in all_data.values())
            finding["finding"] = f"需核对检验批工程量累计与分项工程量是否一致（共 {total_rows} 行数据）"
            finding["evidence"] = f"共 {len(all_docs)} 份文档参与累计计算"

        # L-08: 分项工程量累计 = 分部工程量
        elif check_id == "L-08":
            finding["finding"] = "需核对分项工程量累计与分部工程量是否一致"

        # L-09: 签字人 vs 人员报审名单
        elif check_id == "L-09":
            finding["finding"] = "需核对实际签字人与报审人员名单是否一致"

        # L-10: 问题处理闭环
        elif check_id == "L-10":
            finding["finding"] = "需检查监理通知/整改通知→回复→复核的闭环情况"

        findings.append(finding)

    return findings


# ========== 规则引擎执行 ==========
def run_rule_engine(
    docs: List[Dict[str, Any]],
    all_data: Dict[str, Dict[str, Any]],
    rules_dir: Path,
    project_name: Optional[str] = None,
    audit_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """执行规则引擎，返回 (rule_engine_findings, rule_engine_summary)。

    采用"增量接入"策略：独立于现有 audit_checklist_item / audit_logic_consistency
    逻辑，通过 RuleLoader 加载 active 规则，按 scope 分发到对应 Checker 执行。

    B-4.2/B-4.3 新增：审核结束后，对 testing 状态规则调用 RuleLifecycleManager
    记录命中/误报情况，命中数累计满足条件时自动流转到 incubating。

    Args:
        docs: 文档元数据列表（含 id / doc_type / professional 等）
        all_data: {doc_id: corrected_data} 映射，每份 data 含 rows 数组
        rules_dir: 规则目录路径（rules/）
        project_name: 项目名称（B-4.4 用于按 effective_scope 过滤 active 规则，
                      以及传递给 RuleLifecycleManager 记录测试项目）
        audit_id: 本次审核 ID（传递给 RuleLifecycleManager 跟踪记录）

    Returns:
        (findings, summary)
        - findings: 由 ViolationReporter.to_audit_findings() 转换的 findings 数组，
          每条含 rule_id / rule_name / level / scope / severity / result /
          row_index / finding / evidence / remediation
        - summary: 汇总统计 {total, by_level, by_severity, by_scope,
          rules_executed, single_doc_hits, cross_doc_hits, cross_unit_hits,
          testing_rules_tracked}
    """
    loader = RuleLoader()
    # B-4.4：按 project_name 过滤 active 规则（None 时加载全部，向后兼容）
    rules = loader.load_active(rules_dir, project_name=project_name)
    matcher = RuleMatcher()
    single_checker = SingleDocChecker()
    cross_doc_checker = CrossDocChecker()
    cross_unit_checker = CrossUnitChecker()
    reporter = ViolationReporter()

    all_violations: List[Any] = []
    single_doc_hits = 0
    cross_doc_hits = 0
    cross_unit_hits = 0

    # ===== SINGLE_DOC：逐份文档执行 =====
    single_doc_rules = matcher.match_by_scope(rules, SCOPE_SINGLE_DOC)
    for doc in docs:
        doc_type = doc.get("doc_type", "")
        if not doc_type:
            continue
        matched_rules = matcher.match_by_doc_type(single_doc_rules, doc_type)
        if not matched_rules:
            continue
        doc_id = doc.get("id", "")
        data = all_data.get(doc_id, {})
        doc_data = {
            "doc_type": doc_type,
            "professional": doc.get("professional", ""),
            "rows": data.get("rows", []) if isinstance(data, dict) else [],
        }
        for rule in matched_rules:
            violations = single_checker.check(rule, doc_data)
            all_violations.extend(violations)
            single_doc_hits += len(violations)

    # ===== CROSS_DOC：对整个任务包的文档集合执行 =====
    cross_doc_rules = matcher.match_by_scope(rules, SCOPE_CROSS_DOC)
    if cross_doc_rules:
        docs_data_list = [
            all_data[d.get("id", "")]
            for d in docs
            if d.get("id", "") in all_data
        ]
        for rule in cross_doc_rules:
            violations = cross_doc_checker.check(rule, docs_data_list)
            all_violations.extend(violations)
            cross_doc_hits += len(violations)

    # ===== CROSS_UNIT：按 (doc_type_a, doc_type_b) 分组执行 =====
    cross_unit_rules = matcher.match_by_scope(rules, SCOPE_CROSS_UNIT)
    if cross_unit_rules:
        # 建立 doc_type → doc 列表 映射
        doc_by_type: Dict[str, List[Dict[str, Any]]] = {}
        for doc in docs:
            dt = doc.get("doc_type", "")
            if dt:
                doc_by_type.setdefault(dt, []).append(doc)

        for rule in cross_unit_rules:
            tw = rule.trigger_when
            doc_type_a = tw.get("doc_type_a")
            doc_type_b = tw.get("doc_type_b")
            if not doc_type_a or not doc_type_b:
                continue
            party_a_docs = doc_by_type.get(doc_type_a, [])
            party_b_docs = doc_by_type.get(doc_type_b, [])
            if not party_a_docs or not party_b_docs:
                continue
            # 对每对 (party_a, party_b) 文档执行
            for a_doc in party_a_docs:
                a_data = all_data.get(a_doc.get("id", ""), {})
                a_doc_data = {
                    "doc_type": doc_type_a,
                    "professional": a_doc.get("professional", ""),
                    "rows": a_data.get("rows", []) if isinstance(a_data, dict) else [],
                }
                for b_doc in party_b_docs:
                    b_data = all_data.get(b_doc.get("id", ""), {})
                    b_doc_data = {
                        "doc_type": doc_type_b,
                        "professional": b_doc.get("professional", ""),
                        "rows": b_data.get("rows", []) if isinstance(b_data, dict) else [],
                    }
                    violations = cross_unit_checker.check(rule, a_doc_data, b_doc_data)
                    all_violations.extend(violations)
                    cross_unit_hits += len(violations)

    # 转换为 findings
    findings = reporter.to_audit_findings(all_violations)

    # 构建汇总统计
    by_level: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}
    by_scope: Dict[str, int] = {}
    for v in all_violations:
        by_level[v.level] = by_level.get(v.level, 0) + 1
        by_severity[v.severity] = by_severity.get(v.severity, 0) + 1
        by_scope[v.scope] = by_scope.get(v.scope, 0) + 1

    # ===== B-4.2/B-4.3：跟踪 testing 状态规则的表现 =====
    # active 规则已执行完毕，接下来扫描所有 testing 状态规则（不参与审核命中），
    # 统计它们在本次审核中的命中数（按 rule_id 分组），并交给 RuleLifecycleManager
    # 记录与判断是否自动提升。false_positives 暂为 0，待 C 阶段反馈闭环接入。
    testing_rules_tracked = 0
    if _HAS_LIFECYCLE:
        try:
            all_rules = loader.load_all(rules_dir)
            testing_rules = [r for r in all_rules if r.status == "testing"]
            if testing_rules:
                mgr = RuleLifecycleManager(rules_dir)
                # 按规则 ID 汇总本次命中数（testing 规则用全部 violations，不区分 scope）
                for rule in testing_rules:
                    rule_hits = sum(
                        1 for v in all_violations if v.rule_id == rule.rule_id
                    )
                    mgr.record_audit_result(
                        rule_id=rule.rule_id,
                        project=project_name or "unknown",
                        audit_id=audit_id or "",
                        hits=rule_hits,
                        false_positives=0,  # 待 C 阶段反馈系统接入
                    )
                    testing_rules_tracked += 1
        except Exception as e:
            # 失败安全：生命周期跟踪异常不影响审核主流程
            print(f"⚠️  生命周期跟踪异常（不影响审核结果）: {e}", file=sys.stderr)

    summary = {
        "total": len(findings),
        "by_level": by_level,
        "by_severity": by_severity,
        "by_scope": by_scope,
        "rules_executed": len(rules),
        "single_doc_hits": single_doc_hits,
        "cross_doc_hits": cross_doc_hits,
        "cross_unit_hits": cross_unit_hits,
        "testing_rules_tracked": testing_rules_tracked,
    }

    return findings, summary


# ========== 报告生成 ==========
def generate_audit_log(
    index: Dict[str, Any],
    tasks: List[Dict[str, Any]],
    all_findings: List[Dict[str, Any]],
    logic_findings: List[Dict[str, Any]],
    rule_engine_findings: List[Dict[str, Any]],
    rule_engine_summary: Dict[str, Any],
    out_dir: Path,
    audit_id: Optional[str] = None,
    force_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    生成审核日志 JSON。

    增量接入规则引擎后新增两个字段：
      - rule_engine_findings：规则引擎产出的 findings 数组
      - rule_engine_summary：规则引擎汇总统计
    现有 findings / logic_consistency_findings 字段保留不变（向后兼容）。

    B-4.2：新增可选 audit_id 参数，允许调用方预先指定 audit_id（与
    run_rule_engine 共享同一个 audit_id，确保生命周期跟踪记录可关联到审核日志）。

    新增 force_info 参数：记录 --force 跳过 human_verified 闸门的情况，
    包含 force_bypass_gate / unverified_files / bypassed_at 等字段。
    """
    # 统计（统一从 all_findings + logic_findings 统计，保证总数一致）
    all_results = all_findings + logic_findings
    total = len(all_results)
    pass_count = sum(1 for f in all_results if f.get("result") == "pass")
    fail_count = sum(1 for f in all_results if f.get("result") == "fail")
    suspicious_count = sum(1 for f in all_results if f.get("result") == "suspicious")
    needs_ai_count = sum(1 for f in all_results if f.get("result") == "needs_ai")
    na_count = sum(1 for f in all_results if f.get("result") == "not_applicable")

    # 按严重程度统计
    by_severity: Dict[str, int] = {}
    for f in all_findings + logic_findings:
        sev = f.get("severity", "low")
        by_severity[sev] = by_severity.get(sev, 0) + 1

    # 按分部分项统计
    by_subdivision: Dict[str, Dict[str, int]] = {}
    for task in tasks:
        key = task.get("subdivision_code") or task.get("sub_label", "未分类")
        if key not in by_subdivision:
            by_subdivision[key] = {"total": 0, "pass": 0, "fail": 0, "suspicious": 0, "needs_ai": 0}
        for f in all_findings:
            if f.get("doc_id") in [d.get("id") for d in task.get("documents", [])]:
                by_subdivision[key]["total"] += 1
                by_subdivision[key][f["result"]] = by_subdivision[key].get(f["result"], 0) + 1

    if audit_id is None:
        audit_id = f"AU-{datetime.now().strftime('%Y%m%d')}-{len(index.get('audit_logs', [])) + 1:03d}"

    audit_log = {
        "schema_version": "1.0",
        "audit_id": audit_id,
        "project_name": index.get("project_name", ""),
        "project_path": index.get("project_path", ""),
        "audit_started_at": now_iso(),
        "audit_completed_at": now_iso(),
        "stage": index.get("stage", "foundation_built"),
        "preconditions": index.get("preconditions", {}),
        "summary": {
            "total_findings": total,
            "pass": pass_count,
            "fail": fail_count,
            "suspicious": suspicious_count,
            "needs_ai": needs_ai_count,
            "not_applicable": na_count,
            "by_severity": by_severity,
            "by_subdivision": by_subdivision,
            "documents_audited": len(index.get("documents", [])),
            "tasks_count": len(tasks) if tasks else 0,
            "rule_engine_findings_count": len(rule_engine_findings),
        },
        "tasks": tasks,
        "findings": all_findings,
        "logic_consistency_findings": logic_findings,
        "rule_engine_findings": rule_engine_findings,
        "rule_engine_summary": rule_engine_summary,
        "force_info": force_info,
        "subdivision_tree": get_full_subdivision_tree(),
        "conclusion": {
            "overall": _derive_overall_conclusion(all_findings + logic_findings),
            "high_confidence": sum(1 for f in all_findings + logic_findings if f["severity"] == "high" and f["result"] != "pass"),
            "recommendations": _generate_recommendations(all_findings + logic_findings),
        },
    }

    # 保存
    audit_log_file = out_dir / f"{audit_log['audit_id']}.json"
    save_json(audit_log_file, audit_log)

    # 更新 index.json
    index["audit_logs"] = index.get("audit_logs", [])
    index["audit_logs"].append({
        "audit_id": audit_log["audit_id"],
        "file": str(audit_log_file.relative_to(out_dir.parent).as_posix()),
        "completed_at": audit_log["audit_completed_at"],
        "total_findings": total,
        "pass": pass_count,
        "fail": fail_count,
        "suspicious": suspicious_count,
    })
    index["audit_status"] = "completed"
    index["updated_at"] = now_iso()

    return audit_log


def _derive_overall_conclusion(findings: List[Dict[str, Any]]) -> str:
    """根据所有发现推导总体结论。"""
    fatal_count = sum(1 for f in findings if f.get("severity") == "fatal")
    fail_count = sum(1 for f in findings if f["result"] == "fail")
    suspicious_count = sum(1 for f in findings if f["result"] == "suspicious")
    needs_ai_count = sum(1 for f in findings if f["result"] == "needs_ai")

    if fatal_count > 0:
        return "不合格 — 存在严重问题，需立即整改"
    if fail_count > 5:
        return "不合格 — 多项检查不通过，需系统性整改"
    if suspicious_count > 10:
        return "存疑 — 大量存疑项需人工确认后重新判定"
    if needs_ai_count > len(findings) * 0.5:
        return "待深度审核 — 超过半数检查项需 AI 深度审核，请执行多 Agent 并行审核"
    if fail_count > 0:
        return "基本合格 — 存在少量不符合项，需整改后复核"
    if suspicious_count > 0:
        return "基本合格 — 存在存疑项，建议人工确认"
    return "合格 — 未发现不符合项"


def _generate_recommendations(findings: List[Dict[str, Any]]) -> List[str]:
    """根据发现生成整改建议。"""
    recommendations = []

    fail_items = [f for f in findings if f["result"] == "fail"]
    suspicious_items = [f for f in findings if f["result"] == "suspicious"]
    needs_ai_items = [f for f in findings if f["result"] == "needs_ai"]

    if fail_items:
        recommendations.append(f"共 {len(fail_items)} 项检查不通过，需逐项整改并附整改报告")
    if suspicious_items:
        recommendations.append(f"共 {len(suspicious_items)} 项存疑，建议人工现场核实后补充证据")
    if needs_ai_items:
        recommendations.append(f"共 {len(needs_ai_items)} 项需 AI 深度审核，建议执行多 Agent 并行审核模式")

    # 分类别建议
    categories = set(f.get("category", "") for f in fail_items + suspicious_items)
    if "资料完整性" in categories:
        recommendations.append("资料完整性存在问题，建议补充缺失资料后重新送审")
    if "资料时效性" in categories:
        recommendations.append("资料时效性存在问题，检查是否存在'先施工后补资料'情况")
    if "资料规范性" in categories:
        recommendations.append("资料规范性不足，建议按 MH/T 5078.1 附录表格格式统一整理")

    return recommendations


# ========== 审核记忆流 + 规则统计更新（D-1/D-2）==========
def _build_rule_details(
    rule_engine_findings: List[Dict[str, Any]],
    docs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """从规则引擎 findings 构建 rule_details 数组（用于审核记忆流）。

    每条 rule_detail 包含：
      - rule_id / rule_name / level / scope / hits
      - false_positives（待反馈系统接入，默认 0）
      - docs_affected（命中该规则的文档 ID 列表）

    Args:
        rule_engine_findings: 规则引擎产出的 findings 数组
        docs: 文档元数据列表（用于反查 doc_id）

    Returns:
        rule_details 列表，按 hits 降序
    """
    if not rule_engine_findings:
        return []

    # 按 rule_id 聚合
    by_rule: Dict[str, List[Dict[str, Any]]] = {}
    for f in rule_engine_findings:
        rid = f.get("rule_id", "")
        if not rid:
            continue
        by_rule.setdefault(rid, []).append(f)

    # 构建 doc_id 集合的查找表（finding 中无 doc_id，仅 row_index），
    # 此处 docs_affected 暂以空列表占位，待后续按 finding.doc_id 填充
    rule_details: List[Dict[str, Any]] = []
    for rid, findings in by_rule.items():
        first = findings[0] if findings else {}
        rule_details.append({
            "rule_id": rid,
            "rule_name": first.get("rule_name", ""),
            "level": first.get("level", ""),
            "scope": first.get("scope", ""),
            "hits": len(findings),
            "false_positives": 0,  # 待反馈系统接入
            "docs_affected": [],   # finding 无 doc_id 字段，暂留空
        })
    # 按 hits 降序
    rule_details.sort(key=lambda x: x["hits"], reverse=True)
    return rule_details


def _write_audit_memory_and_update_stats(
    audit_log: Dict[str, Any],
    audit_log_file: Path,
    docs: List[Dict[str, Any]],
    rule_engine_findings: List[Dict[str, Any]],
    rules_dir: Path,
    feedbacks_dir: Path,
) -> None:
    """写入审核记忆流 + 更新规则 stats（D-1/D-2）。

    失败安全：任何异常仅打印警告到 stderr，不抛出，不影响主审核流程。

    Args:
        audit_log: 审核日志 dict
        audit_log_file: 审核日志文件路径（用于 RuleMonitor 更新 stats）
        docs: 文档元数据列表
        rule_engine_findings: 规则引擎 findings
        rules_dir: 规则目录
        feedbacks_dir: 反馈目录
    """
    audit_id = audit_log.get("audit_id", "")
    project_name = audit_log.get("project_name", "")
    project_path = audit_log.get("project_path", "")
    summary_dict = audit_log.get("summary", {}) or {}

    # ===== D-2：写入审核记忆流 =====
    if _HAS_AUDIT_MEMORY:
        try:
            memory = AuditMemory(SKILL_DIR / "audit_memory")
            # 构建 rules_triggered / rules_hit_count
            rules_triggered = sorted(set(
                f.get("rule_id", "") for f in rule_engine_findings if f.get("rule_id")
            ))
            rules_hit_count = dict(collections.Counter(
                f.get("rule_id", "") for f in rule_engine_findings if f.get("rule_id")
            ))
            rule_details = _build_rule_details(rule_engine_findings, docs)

            memory.append_audit_completed(
                audit_id=audit_id,
                project_name=project_name,
                project_path=project_path,
                summary={
                    "documents_audited": summary_dict.get("documents_audited", len(docs)),
                    "total_findings": summary_dict.get("total_findings", 0),
                    "rule_engine_findings": summary_dict.get("rule_engine_findings_count",
                                                              len(rule_engine_findings)),
                    "rules_triggered": rules_triggered,
                    "rules_hit_count": rules_hit_count,
                    "feedbacks_count": 0,
                },
                rule_details=rule_details,
                feedbacks=[],
            )
            print(f"📝 审核记忆流已写入: {SKILL_DIR / 'audit_memory'}", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  审核记忆流写入失败（不影响审核结果）: {e}", file=sys.stderr)
    else:
        print("ℹ️  audit_memory 模块未加载，跳过审核记忆流写入", file=sys.stderr)

    # ===== D-1：更新规则 stats =====
    if _HAS_RULE_MONITOR:
        try:
            monitor = RuleMonitor(rules_dir, feedbacks_dir=feedbacks_dir)
            result = monitor.update_stats_from_audit_log(audit_log_file)
            if result.get("rules_updated", 0) > 0:
                print(f"📊 规则 stats 已更新: {result['rules_updated']} 条规则", file=sys.stderr)
            if result.get("errors"):
                for err in result["errors"][:3]:
                    print(f"   [!] {err}", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  规则 stats 更新失败（不影响审核结果）: {e}", file=sys.stderr)
    else:
        print("ℹ️  rule_monitor 模块未加载，跳过规则 stats 更新", file=sys.stderr)


# ========== 主流程 ==========
def run_review(
    project_path: Path,
    out_name: str = "数据底座",
    split_by: str = "sub",
    task_id: Optional[str] = None,
    tasks_file: Optional[Path] = None,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """
    执行正式审核。

    Args:
        project_path: 项目文件夹路径
        out_name: 数据底座目录名
        split_by: 任务拆分粒度 (professional/sub/item)
        task_id: 仅执行指定任务（多 Agent 并行模式）
        tasks_file: 任务包文件路径
        dry_run: 仅生成任务包
        force: 跳过 human_verified 闸门
    """
    out_base = project_path / out_name
    index_path = out_base / "index.json"
    
    # 自动回退：如果 {project_path}/数据底座/index.json 不存在，
    # 尝试直接读取 {project_path}/index.json
    if not index_path.exists():
        fallback = project_path / "index.json"
        if fallback.exists():
            print(f"⚠️  未找到 {index_path}，自动回退到 {fallback}", file=sys.stderr)
            index_path = fallback
            out_base = project_path
    
    if not index_path.exists():
        print(f"❌ 未找到 index.json: {index_path}", file=sys.stderr)
        print("   请先执行 build 命令建立数据底座", file=sys.stderr)
        return 1
    
    audit_log_dir = out_base / "审核日志"

    index = load_json(index_path)
    if not index:
        print(f"❌ 无法读取 index.json", file=sys.stderr)
        return 1

    # ===== 步骤 1：审核前置检查 =====
    all_verified, unverified = check_human_verified(index)
    force_info: Optional[Dict[str, Any]] = None
    if not force:
        if not all_verified:
            print("⛔ 审核前置检查未通过 — 以下文件尚未完成人工核对：", file=sys.stderr)
            for f in unverified:
                print(f"   - {f}", file=sys.stderr)
            print("\n当前各文件 human_verified 状态：", file=sys.stderr)
            for doc in index.get("documents", []):
                flag = "✅ true" if doc.get("human_verified") else "❌ false"
                print(f"   - {doc.get('original_file', doc.get('id', '?'))}: {flag}", file=sys.stderr)
            print("\n请先打开 data-editor.html 完成人工核对，再执行审核。", file=sys.stderr)
            print("如需跳过此检查（仅测试用），请使用 --force 参数。", file=sys.stderr)
            return 1
        print("✅ 审核前置检查通过 — 所有文件已完成人工核对\n", file=sys.stderr)
    else:
        print("⚠️  --force：跳过 human_verified 闸门\n", file=sys.stderr)
        force_info = {
            "force_bypass_gate": True,
            "unverified_files": unverified,
            "bypassed_at": now_iso(),
            "notice": "本审核日志通过 --force 生成，跳过人工核对闸门，非正式审核结果",
        }

    # ===== 步骤 2：加载文档数据 =====
    docs: List[Dict[str, Any]] = []
    all_data: Dict[str, Dict[str, Any]] = {}

    for doc in index.get("documents", []):
        doc_id = doc.get("id", "")
        professional = doc.get("professional", "")
        subdivision_code = doc.get("subdivision_code")

        # 读取 corrected_data.json（优先）或 data_file
        corrected_file = doc.get("corrected_file")
        if corrected_file:
            data_path = out_base / corrected_file
        else:
            data_file_rel = doc.get("data_file", "")
            if not data_file_rel:
                print(f"  [!] 文档无数据文件路径: {doc_id}（{doc.get('original_file', '')}）", file=sys.stderr)
                continue
            data_path = out_base / data_file_rel

        if not data_path.is_file():
            print(f"  [!] 数据文件不存在: {data_path}", file=sys.stderr)
            continue

        data = load_json(data_path)
        if not data:
            print(f"  [!] 无法加载数据文件: {data_path}", file=sys.stderr)
            continue

        all_data[doc_id] = data

        docs.append({
            "id": doc_id,
            "original_file": doc.get("original_file", ""),
            "doc_type": doc.get("doc_type", ""),
            "professional": professional,
            "subdivision_code": subdivision_code,
            "subdivision_label": doc.get("subdivision_label", ""),
            "sub_division": doc.get("sub_division", ""),
            "pages": doc.get("pages", 0),
            "human_verified": doc.get("human_verified", False),
        })

    if not docs:
        print("❌ 没有可审核的文档", file=sys.stderr)
        return 1

    print(f"📄 共加载 {len(docs)} 份文档\n", file=sys.stderr)

    # ===== 步骤 3：生成任务包 =====
    if tasks_file and tasks_file.exists():
        tasks = load_json(tasks_file)
        if not isinstance(tasks, list):
            print(f"❌ 任务包格式错误: {tasks_file}", file=sys.stderr)
            return 1
        print(f"📋 从文件加载任务包: {tasks_file}（{len(tasks)} 个任务）\n", file=sys.stderr)
    else:
        force_split = split_by == "item"
        tasks = group_documents_for_audit(docs, force_split_by_item=force_split, split_by=split_by)
        print(f"📋 生成审核任务包: {len(tasks)} 个任务\n", file=sys.stderr)

        for task in tasks:
            sub_label = task.get("sub_label", "")
            item_label = task.get("item_label", "")
            label = f"{sub_label} → {item_label}" if item_label else sub_label
            print(f"  {task['task_id']}: {label}（{task['doc_count']} 份文档）", file=sys.stderr)
        print("", file=sys.stderr)

    if dry_run:
        # 保存任务包
        tasks_out = audit_log_dir / "audit_tasks.json"
        save_json(tasks_out, tasks)
        print(f"📋 任务包已保存: {tasks_out}", file=sys.stderr)
        print(f"   共 {len(tasks)} 个任务，按 {split_by} 粒度拆分", file=sys.stderr)
        print(f"\n多 Agent 并行审核命令示例：", file=sys.stderr)
        for task in tasks[:3]:
            print(f"   python scripts/review_audit.py \"{project_path}\" --task-id {task['task_id']} --tasks-file \"{tasks_out}\"", file=sys.stderr)
        if len(tasks) > 3:
            print(f"   ... 共 {len(tasks)} 个任务", file=sys.stderr)
        return 0

    # ===== 步骤 4：执行审核 =====
    all_findings: List[Dict[str, Any]] = []

    if task_id:
        # 多 Agent 模式：只执行指定任务
        target_task = next((t for t in tasks if t["task_id"] == task_id), None)
        if not target_task:
            print(f"❌ 未找到任务: {task_id}", file=sys.stderr)
            return 1
        tasks_to_run = [target_task]
        print(f"🎯 执行指定任务: {task_id}\n", file=sys.stderr)
    else:
        tasks_to_run = tasks

    for task in tasks_to_run:
        print(f"🔍 审核 {task['task_id']}: {task.get('sub_label', '')} {task.get('item_label', '') or ''}", file=sys.stderr)

        for doc in task.get("documents", []):
            doc_id = doc["id"]
            doc_data = all_data.get(doc_id, {})
            professional = doc.get("professional", "")

            # 获取该分部分项的检查清单
            sub_code = doc.get("subdivision_code")
            if sub_code:
                checklist = get_checklist_for_subdivision(professional, sub_code)
            else:
                checklist = get_checklist_for_professional(professional)

            doc_findings = audit_document(doc, doc_data, checklist)
            all_findings.extend(doc_findings)

            # 统计
            pass_count = sum(1 for f in doc_findings if f["result"] == "pass")
            fail_count = sum(1 for f in doc_findings if f["result"] == "fail")
            susp_count = sum(1 for f in doc_findings if f["result"] == "suspicious")
            ai_count = sum(1 for f in doc_findings if f["result"] == "needs_ai")
            print(f"  {doc['original_file']}: 通过 {pass_count}, 不通过 {fail_count}, 存疑 {susp_count}, 待AI {ai_count}", file=sys.stderr)

        print("", file=sys.stderr)

    # ===== 步骤 5：逻辑一致性检查 =====
    print("🔗 执行逻辑一致性检查（10 子项）...", file=sys.stderr)
    logic_findings = audit_logic_consistency(docs, all_data)
    print(f"  共 {len(logic_findings)} 项检查（其中 {sum(1 for f in logic_findings if f['result'] == 'needs_ai')} 项需 AI 深度审核）\n", file=sys.stderr)

    # ===== 步骤 5.5：规则引擎执行 =====
    rules_dir = Path(__file__).resolve().parent.parent / "rules"
    # 预先生成 audit_id，确保 run_rule_engine 与 generate_audit_log 使用同一个 ID
    project_name = index.get("project_name", "")
    audit_id_preview = f"AU-{datetime.now().strftime('%Y%m%d')}-{len(index.get('audit_logs', [])) + 1:03d}"
    print("⚙️  执行规则引擎（加载 active 规则）...", file=sys.stderr)
    rule_engine_findings, rule_engine_summary = run_rule_engine(
        docs, all_data, rules_dir,
        project_name=project_name,
        audit_id=audit_id_preview,
    )
    print(f"  规则引擎执行 {rule_engine_summary['rules_executed']} 条 active 规则", file=sys.stderr)
    print(f"  单资料命中: {rule_engine_summary['single_doc_hits']}, "
          f"跨资料命中: {rule_engine_summary['cross_doc_hits']}, "
          f"跨单位命中: {rule_engine_summary['cross_unit_hits']}", file=sys.stderr)
    print(f"  规则引擎发现: {rule_engine_summary['total']} 项", file=sys.stderr)
    if rule_engine_summary.get("testing_rules_tracked", 0) > 0:
        print(f"  跟踪 testing 规则: {rule_engine_summary['testing_rules_tracked']} 条", file=sys.stderr)
    print("", file=sys.stderr)

    # ===== 步骤 6：生成审核日志 =====
    audit_log = generate_audit_log(
        index, tasks, all_findings, logic_findings,
        rule_engine_findings, rule_engine_summary, audit_log_dir,
        audit_id=audit_id_preview,
        force_info=force_info,
    )

    # 保存更新后的 index.json
    save_json(index_path, index)

    # ===== 步骤 7：写入审核记忆流 + 更新规则统计（D-1/D-2）=====
    # 失败安全：记忆流/规则监控异常不影响主审核流程
    audit_log_file = audit_log_dir / f"{audit_log['audit_id']}.json"
    _write_audit_memory_and_update_stats(
        audit_log=audit_log,
        audit_log_file=audit_log_file,
        docs=docs,
        rule_engine_findings=rule_engine_findings,
        rules_dir=rules_dir,
        feedbacks_dir=SKILL_DIR / "feedbacks",
    )

    # ===== 输出汇总 =====
    summary = audit_log["summary"]
    print("=" * 60, file=sys.stderr)
    print("✅ 审核完成", file=sys.stderr)
    print(f"   审核编号: {audit_log['audit_id']}", file=sys.stderr)
    print(f"   总检查项: {summary['total_findings']}", file=sys.stderr)
    print(f"   通过: {summary['pass']}", file=sys.stderr)
    print(f"   不通过: {summary['fail']}", file=sys.stderr)
    print(f"   存疑: {summary['suspicious']}", file=sys.stderr)
    print(f"   待AI深度审核: {summary['needs_ai']}", file=sys.stderr)
    print(f"   不适用: {summary['not_applicable']}", file=sys.stderr)
    print(f"   规则引擎发现: {summary['rule_engine_findings_count']} 项", file=sys.stderr)
    print(f"\n   总体结论: {audit_log['conclusion']['overall']}", file=sys.stderr)
    print(f"   审核日志: {audit_log_dir / f'{audit_log['audit_id']}.json'}", file=sys.stderr)

    for rec in audit_log["conclusion"]["recommendations"]:
        print(f"   💡 {rec}", file=sys.stderr)

    print("=" * 60, file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="民航施工资料正式审核（Phase 3）"
    )
    parser.add_argument("project_path", help="项目文件夹路径")
    parser.add_argument(
        "--out", default="数据底座",
        help="数据底座目录名（默认：数据底座）"
    )
    parser.add_argument(
        "--split-by", choices=["professional", "sub", "item"], default="sub",
        help="任务拆分粒度：professional(专业级)/sub(分部级)/item(分项级)，默认 sub"
    )
    parser.add_argument(
        "--task-id",
        help="只执行指定任务（多 Agent 并行模式）"
    )
    parser.add_argument(
        "--tasks-file",
        help="任务包 JSON 文件路径"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅生成任务包，不执行审核"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="跳过 human_verified 闸门（仅测试用）"
    )
    args = parser.parse_args()

    project_path = Path(args.project_path).resolve()
    if not project_path.is_dir():
        print(f"❌ 项目文件夹不存在: {project_path}", file=sys.stderr)
        return 1

    tasks_file = Path(args.tasks_file).resolve() if args.tasks_file else None

    return run_review(
        project_path=project_path,
        out_name=args.out,
        split_by=args.split_by,
        task_id=args.task_id,
        tasks_file=tasks_file,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    sys.exit(main())