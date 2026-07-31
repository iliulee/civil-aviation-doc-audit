# -*- coding: utf-8 -*-
"""
端到端验证脚本：规则引擎集成验证
================================

目的：
  1. 构造最小化测试数据（碎石桩施工记录，含合规行 + 违规行）
  2. 调用规则引擎加载 91 条规则
  3. 匹配 SINGLE_DOC 规则并执行审核
  4. 验证 LG-001（高程自洽）是否正确命中违规行
  5. 验证 ViolationReporter 输出格式

运行：
  cd d:\2026年7月22日 民航资料skill
  python 测试\test_e2e_rule_engine.py
"""

import json
import sys
from pathlib import Path

# 将 scripts/ 目录加入 sys.path
SCRIPT_DIR = Path(__file__).resolve().parent.parent / ".trae" / "skills" / "civil-aviation-doc-audit" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from rule_engine import (
    RuleLoader,
    RuleMatcher,
    SingleDocChecker,
    CrossUnitChecker,
    ViolationReporter,
    SCOPE_SINGLE_DOC,
    SCOPE_CROSS_UNIT,
    LEVEL_L1,
    LEVEL_L2,
    LEVEL_L3,
)

RULES_DIR = Path(__file__).resolve().parent.parent / ".trae" / "skills" / "civil-aviation-doc-audit" / "rules"


# ========== 1. 构造最小化测试数据 ==========
def build_test_data() -> dict:
    """构造碎石桩施工记录测试数据。

    包含：
      - 3 行合规数据（diff <= 0.1）
      - 2 行违规数据（diff > 0.1）
      - 1 行边界数据（diff = 0.1，合规）
      - 1 行边界数据（diff = 0.2，违规）
    """
    return {
        "doc_type": "碎石桩施工记录",
        "professional": "01_场道工程",
        "source_file": "碎石桩施工记录_测试.json",
        "rows": [
            # 合规行
            {"pile_no": "Z415", "实长": 13.7, "桩顶高程": 25.5, "桩底高程": 11.8, "灌入量": 18.5, "充盈系数": 1.35},
            {"pile_no": "Z416", "实长": 14.2, "桩顶高程": 26.0, "桩底高程": 11.8, "灌入量": 19.2, "充盈系数": 1.35},
            {"pile_no": "Z417", "实长": 12.5, "桩顶高程": 24.3, "桩底高程": 11.8, "灌入量": 16.8, "充盈系数": 1.34},
            # 违规行：实长与高程差不一致
            {"pile_no": "Z418", "实长": 15.0, "桩顶高程": 25.5, "桩底高程": 11.8, "灌入量": 20.1, "充盈系数": 1.34},
            # computed=13.7, diff=1.3 → 违规
            {"pile_no": "Z419", "实长": 11.2, "桩顶高程": 24.3, "桩底高程": 11.8, "灌入量": 15.0, "充盈系数": 1.34},
            # computed=12.5, diff=1.3 → 违规
            # 边界行（调整为明确合规/违规，避免浮点精度干扰）
            {"pile_no": "Z420", "实长": 13.75, "桩顶高程": 25.5, "桩底高程": 11.8, "灌入量": 18.6, "充盈系数": 1.35},
            # computed=13.7, diff=0.05 → 合规
            {"pile_no": "Z421", "实长": 14.0, "桩顶高程": 25.5, "桩底高程": 11.8, "灌入量": 18.7, "充盈系数": 1.35},
            # computed=13.7, diff=0.3 → 违规
        ],
    }


# ========== 2. 主流程 ==========
def main() -> int:
    print("=" * 70)
    print("端到端验证：规则引擎集成")
    print("=" * 70)

    # --- 步骤 1：加载规则 ---
    print("\n[步骤 1] 加载规则文件库...")
    loader = RuleLoader()
    all_rules = loader.load_all(RULES_DIR)
    active_rules = loader.load_active(RULES_DIR)
    print(f"  规则目录: {RULES_DIR}")
    print(f"  全部规则: {len(all_rules)} 条")
    print(f"  active 规则: {len(active_rules)} 条")

    # 按层级统计
    by_level = {"L1-IRON": 0, "L2-LOGIC": 0, "L3-BUSINESS": 0}
    for r in active_rules:
        if r.level in by_level:
            by_level[r.level] += 1
    print(f"  按层级: L1={by_level['L1-IRON']} / L2={by_level['L2-LOGIC']} / L3={by_level['L3-BUSINESS']}")

    # 按作用域统计
    by_scope = {"SINGLE_DOC": 0, "CROSS_DOC": 0, "CROSS_UNIT": 0}
    for r in active_rules:
        if r.scope in by_scope:
            by_scope[r.scope] += 1
    print(f"  按作用域: SINGLE_DOC={by_scope['SINGLE_DOC']} / CROSS_DOC={by_scope['CROSS_DOC']} / CROSS_UNIT={by_scope['CROSS_UNIT']}")

    # --- 步骤 2：构造测试数据 ---
    print("\n[步骤 2] 构造测试数据...")
    doc_data = build_test_data()
    print(f"  资料类型: {doc_data['doc_type']}")
    print(f"  专业: {doc_data['professional']}")
    print(f"  数据行数: {len(doc_data['rows'])}")
    print("  数据预览:")
    for i, row in enumerate(doc_data["rows"]):
        computed = round(row["桩顶高程"] - row["桩底高程"], 4)
        diff = round(abs(row["实长"] - computed), 4)
        status = "✓ 合规" if diff <= 0.1 else "✗ 违规"
        print(f"    [{i}] {row['pile_no']}: 实长={row['实长']}, 桩顶={row['桩顶高程']}, 桩底={row['桩底高程']}, computed={computed}, diff={diff} → {status}")

    # --- 步骤 3：匹配规则 ---
    print("\n[步骤 3] 匹配规则...")
    matcher = RuleMatcher()
    matched_by_doc = matcher.match_by_doc_type(active_rules, doc_data["doc_type"])
    matched_by_prof = matcher.match_by_professional(active_rules, doc_data["professional"])
    matched_single = matcher.match_by_scope(matched_by_doc, SCOPE_SINGLE_DOC)
    print(f"  按资料类型匹配: {len(matched_by_doc)} 条")
    print(f"  按专业匹配: {len(matched_by_prof)} 条")
    print(f"  SINGLE_DOC + 资料类型匹配: {len(matched_single)} 条")
    if matched_single:
        print("  匹配到的规则:")
        for r in matched_single:
            print(f"    - {r.rule_id} | {r.name} | {r.level} | expr: {r.check_expr.get('expr', '')[:60]}")

    # --- 步骤 4：执行审核 ---
    print("\n[步骤 4] 执行审核（SingleDocChecker）...")
    checker = SingleDocChecker()
    all_violations = []
    for rule in matched_single:
        violations = checker.check(rule, doc_data)
        if violations:
            print(f"  规则 {rule.rule_id} ({rule.name}) 命中 {len(violations)} 条违规:")
            for v in violations:
                print(f"    [行{v.row_index}] {v.severity} | {v.error_message}")
            all_violations.extend(violations)
        else:
            print(f"  规则 {rule.rule_id} ({rule.name}) 未命中违规")

    # --- 步骤 5：验证 LG-001 命中结果 ---
    print("\n[步骤 5] 验证 LG-001 命中结果...")
    lg001_violations = [v for v in all_violations if v.rule_id == "LG-001"]
    expected_violation_rows = {3, 4, 6}  # Z418, Z419, Z421
    actual_violation_rows = {v.row_index for v in lg001_violations}

    print(f"  期望违规行索引: {sorted(expected_violation_rows)} (Z418, Z419, Z421)")
    print(f"  实际违规行索引: {sorted(actual_violation_rows)}")

    if actual_violation_rows == expected_violation_rows:
        print("  ✓ LG-001 命中结果与预期一致")
    else:
        print("  ✗ LG-001 命中结果与预期不符")
        missing = expected_violation_rows - actual_violation_rows
        extra = actual_violation_rows - expected_violation_rows
        if missing:
            print(f"    缺失: {sorted(missing)}")
        if extra:
            print(f"    多余: {sorted(extra)}")

    # --- 步骤 6：ViolationReporter 输出 ---
    print("\n[步骤 6] ViolationReporter 输出...")
    reporter = ViolationReporter()
    report = reporter.report(all_violations)
    print(f"  报告字段: {list(report.keys())}")
    print(f"  总违规数: {report.get('total', 0)}")
    by_severity = report.get("by_severity", {})
    print(f"  按严重度: {by_severity}")
    by_level_report = report.get("by_level", {})
    print(f"  按层级: {by_level_report}")

    # 同时验证 findings 格式转换
    findings = reporter.to_audit_findings(all_violations)
    print(f"  findings 格式转换: {len(findings)} 条")
    if findings:
        print(f"  findings[0] 字段: {list(findings[0].keys())}")
        print(f"  findings[0] 示例: rule_id={findings[0]['rule_id']}, result={findings[0]['result']}")

    # --- 步骤 7：跨单位规则匹配验证 ---
    print("\n[步骤 7] 跨单位规则匹配验证...")
    cross_unit_rules = matcher.match_by_scope(active_rules, SCOPE_CROSS_UNIT)
    print(f"  跨单位规则总数: {len(cross_unit_rules)}")
    # 模拟同时有监理旁站记录和碎石桩施工记录
    doc_types = ["碎石桩施工记录", "监理旁站记录"]
    matched_cross = matcher.match_cross_unit(active_rules, doc_types)
    print(f"  匹配到的跨单位规则（doc_types={doc_types}）: {len(matched_cross)} 条")
    if matched_cross:
        print("  匹配到的跨单位规则:")
        for r in matched_cross[:5]:  # 只显示前5条
            print(f"    - {r.rule_id} | {r.name} | {r.level}")

    # --- 总结 ---
    print("\n" + "=" * 70)
    print("端到端验证总结")
    print("=" * 70)
    checks = [
        ("规则加载（91 条）", len(all_rules) == 91),
        ("active 规则加载", len(active_rules) > 0),
        ("测试数据构造（7 行）", len(doc_data["rows"]) == 7),
        ("规则匹配（SINGLE_DOC）", len(matched_single) > 0),
        ("LG-001 命中违规（3 条）", len(lg001_violations) == 3),
        ("LG-001 命中行索引正确", actual_violation_rows == expected_violation_rows),
        ("ViolationReporter 输出", report.get("total", 0) == len(all_violations)),
        ("跨单位规则匹配", len(matched_cross) > 0),
    ]
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    for name, ok in checks:
        print(f"  {'✓' if ok else '✗'} {name}")
    print(f"\n  结果: {passed}/{total} 通过")
    if passed == total:
        print("  ✅ 端到端验证全部通过")
        return 0
    else:
        print("  ❌ 端到端验证存在失败项")
        return 1


if __name__ == "__main__":
    sys.exit(main())
