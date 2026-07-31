# -*- coding: utf-8 -*-
"""
test_rule_engine.py — 规则引擎测试脚本
=======================================

覆盖 Phase A-2 的 6 个核心测试用例：
  1. RuleLoader          加载 rules/ 目录，断言至少 2 条规则
  2. RuleMatcher         match_by_doc_type("碎石桩施工记录") 返回 LG-001
  3. ExpressionEvaluator 表达式求值 + 模板渲染
  4. SingleDocChecker    LG-001 校验样例数据（1 通过 + 1 违规）
  5. CrossUnitChecker    CU-001 校验监理方/施工方数据（1 个偏差超 5%）
  6. ViolationReporter   汇总统计正确

用法：
    python scripts/test_rule_engine.py
"""

import sys
from pathlib import Path

# 允许 import 同目录下的 rule_engine
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from rule_engine import (  # noqa: E402
    CrossUnitChecker,
    ExpressionEvaluator,
    Rule,
    RuleLoader,
    RuleMatcher,
    SingleDocChecker,
    ViolationReporter,
    LEVEL_L2,
    SCOPE_CROSS_UNIT,
    SCOPE_SINGLE_DOC,
    SEVERITY_SANITY,
)

RULES_DIR = SKILL_DIR / "rules"


# ========== 测试工具 ==========
def _assert(condition: bool, msg: str) -> None:
    """断言辅助：失败时抛 AssertionError 并打印消息。"""
    if not condition:
        raise AssertionError(f"断言失败: {msg}")
    print(f"  ✓ {msg}")


def _assert_eq(actual, expected, msg: str) -> None:
    """断言相等。"""
    if actual != expected:
        raise AssertionError(f"断言失败: {msg}\n  期望: {expected!r}\n  实际: {actual!r}")
    print(f"  ✓ {msg}")


# ========== 测试 1：RuleLoader ==========
def test_rule_loader() -> None:
    print("\n[测试 1] RuleLoader")
    loader = RuleLoader()
    rules = loader.load_all(RULES_DIR)
    _assert(len(rules) >= 2, f"加载规则数 ≥ 2（实际 {len(rules)}）")

    rule_ids = {r.rule_id for r in rules}
    _assert("LG-001" in rule_ids, "包含 LG-001")
    _assert("CU-001" in rule_ids, "包含 CU-001")

    # active 规则过滤
    active = loader.load_active(RULES_DIR)
    _assert(len(active) >= 2, f"active 规则数 ≥ 2（实际 {len(active)}）")
    _assert(all(r.status == "active" for r in active), "所有 active 规则 status='active'")

    # 按 ID 加载
    lg001 = loader.load_by_id(RULES_DIR, "LG-001")
    _assert(lg001 is not None, "load_by_id('LG-001') 返回非空")
    _assert(isinstance(lg001, Rule), "load_by_id 返回 Rule 实例")
    _assert_eq(lg001.level, LEVEL_L2, "LG-001 层级 = L2-LOGIC")
    _assert_eq(lg001.scope, SCOPE_SINGLE_DOC, "LG-001 作用域 = SINGLE_DOC")

    not_found = loader.load_by_id(RULES_DIR, "NOT-EXIST-999")
    _assert(not_found is None, "load_by_id('NOT-EXIST-999') 返回 None")


# ========== 测试 2：RuleMatcher ==========
def test_rule_matcher() -> None:
    print("\n[测试 2] RuleMatcher")
    loader = RuleLoader()
    rules = loader.load_all(RULES_DIR)
    matcher = RuleMatcher()

    # 按资料类型匹配
    matched = matcher.match_by_doc_type(rules, "碎石桩施工记录")
    _assert(len(matched) >= 1, f"match_by_doc_type('碎石桩施工记录') 返回 ≥ 1（实际 {len(matched)}）")
    matched_ids = {r.rule_id for r in matched}
    _assert("LG-001" in matched_ids, "匹配结果包含 LG-001")

    # 按专业匹配
    by_prof = matcher.match_by_professional(rules, "01_场道工程")
    _assert(len(by_prof) >= 1, f"match_by_professional('01_场道工程') 返回 ≥ 1（实际 {len(by_prof)}）")
    _assert("LG-001" in {r.rule_id for r in by_prof}, "专业匹配结果包含 LG-001")

    # 跨单位匹配
    cross_unit = matcher.match_cross_unit(rules, ["监理旁站记录", "碎石桩施工记录"])
    _assert(len(cross_unit) >= 1, f"match_cross_unit 返回 ≥ 1（实际 {len(cross_unit)}）")
    _assert("CU-001" in {r.rule_id for r in cross_unit}, "跨单位匹配结果包含 CU-001")

    # 跨单位匹配（缺一方，不应匹配）
    cross_unit_partial = matcher.match_cross_unit(rules, ["监理旁站记录"])
    _assert_eq(len(cross_unit_partial), 0, "仅提供一方资料类型时跨单位匹配返回 0")

    # 按作用域匹配
    single_doc_rules = matcher.match_by_scope(rules, SCOPE_SINGLE_DOC)
    _assert(len(single_doc_rules) >= 1, f"match_by_scope(SINGLE_DOC) 返回 ≥ 1（实际 {len(single_doc_rules)}）")
    cross_unit_rules = matcher.match_by_scope(rules, SCOPE_CROSS_UNIT)
    _assert(len(cross_unit_rules) >= 1, f"match_by_scope(CROSS_UNIT) 返回 ≥ 1（实际 {len(cross_unit_rules)}）")


# ========== 测试 3：ExpressionEvaluator ==========
def test_expression_evaluator() -> None:
    print("\n[测试 3] ExpressionEvaluator")
    ev = ExpressionEvaluator()

    # 高程自洽：通过
    passed = ev.evaluate(
        "abs(实长 - (桩顶高程 - 桩底高程)) <= 0.1",
        {"实长": 13.7, "桩顶高程": 2103.7, "桩底高程": 2090.0},
    )
    _assert_eq(passed, True, "高程自洽通过（13.7 vs 13.7）")

    # 高程自洽：违规
    violated = ev.evaluate(
        "abs(实长 - (桩顶高程 - 桩底高程)) <= 0.1",
        {"实长": 9.0, "桩顶高程": 2103.7, "桩底高程": 2090.0},
    )
    _assert_eq(violated, False, "高程自洽违规（9.0 vs 13.7）")

    # 跨单位偏差表达式
    dev_ok = ev.evaluate(
        "abs(field_a - field_b) / max(field_a, field_b) <= 0.05",
        {"field_a": 13.0, "field_b": 13.0},
    )
    _assert_eq(dev_ok, True, "跨单位偏差通过（0%）")

    dev_bad = ev.evaluate(
        "abs(field_a - field_b) / max(field_a, field_b) <= 0.05",
        {"field_a": 13.2, "field_b": 9.0},
    )
    _assert_eq(dev_bad, False, "跨单位偏差违规（>5%）")

    # 语法错误 → 返回 True（不违规）
    err = ev.evaluate("abs(实长 - ) <= 0.1", {"实长": 13.7})
    _assert_eq(err, True, "表达式语法错误时返回 True（避免误报）")

    # 危险关键字 → 返回 True
    danger = ev.evaluate("__import__('os').system('ls')", {})
    _assert_eq(danger, True, "危险关键字表达式返回 True")

    # 模板渲染
    rendered = ev.render_template(
        "桩号 {pile_no} 差异 {diff}m",
        {"pile_no": "Z418", "diff": 4.19},
    )
    _assert_eq(rendered, "桩号 Z418 差异 4.19m", "模板渲染正确")

    # 模板渲染：缺失字段保留占位符
    rendered_missing = ev.render_template(
        "桩号 {pile_no} 差异 {diff}m",
        {"pile_no": "Z418"},
    )
    _assert_eq(rendered_missing, "桩号 Z418 差异 {diff}m", "缺失字段保留 {diff} 占位符")


# ========== 测试 4：SingleDocChecker ==========
def test_single_doc_checker() -> None:
    print("\n[测试 4] SingleDocChecker")
    loader = RuleLoader()
    rule = loader.load_by_id(RULES_DIR, "LG-001")
    _assert(rule is not None, "LG-001 规则加载成功")

    checker = SingleDocChecker()
    doc_data = {
        "doc_type": "碎石桩施工记录",
        "professional": "01_场道工程",
        "rows": [
            # 通过：13.7 == 2103.7 - 2090.0
            {"pile_no": "Z415", "实长": 13.7, "桩顶高程": 2103.7, "桩底高程": 2090.0},
            # 违规：9.0 != 13.7，差异 4.7m
            {"pile_no": "Z417", "实长": 9.0, "桩顶高程": 2103.7, "桩底高程": 2090.0},
        ],
    }
    violations = checker.check(rule, doc_data)
    _assert_eq(len(violations), 1, f"SingleDocChecker 返回 1 个 Violation（实际 {len(violations)}）")

    v = violations[0]
    _assert_eq(v.rule_id, "LG-001", "Violation.rule_id = LG-001")
    _assert_eq(v.level, LEVEL_L2, "Violation.level = L2-LOGIC")
    _assert_eq(v.scope, SCOPE_SINGLE_DOC, "Violation.scope = SINGLE_DOC")
    _assert_eq(v.severity, SEVERITY_SANITY, "Violation.severity = Sanity Check")
    _assert_eq(v.row_index, 1, "Violation.row_index = 1（第二行违规）")
    _assert("Z417" in v.error_message, "error_message 含桩号 Z417")
    _assert("4.7" in v.error_message or "4.7000" in v.error_message, "error_message 含差异值 4.7")
    _assert(v.remediation is not None and len(v.remediation) > 0, "remediation 非空")

    # 测试全部通过的样例
    good_doc = {
        "doc_type": "碎石桩施工记录",
        "rows": [
            {"pile_no": "Z415", "实长": 13.7, "桩顶高程": 2103.7, "桩底高程": 2090.0},
            {"pile_no": "Z416", "实长": 13.7, "桩顶高程": 2103.7, "桩底高程": 2090.0},
        ],
    }
    no_violations = checker.check(rule, good_doc)
    _assert_eq(len(no_violations), 0, "全部通过时返回 0 个 Violation")

    # 测试必需字段缺失时跳过该行
    missing_field_doc = {
        "doc_type": "碎石桩施工记录",
        "rows": [
            {"pile_no": "Z999", "实长": 9.0},  # 缺 桩顶高程/桩底高程
        ],
    }
    skipped = checker.check(rule, missing_field_doc)
    _assert_eq(len(skipped), 0, "必需字段缺失时跳过该行，返回 0 个 Violation")

    # 把 violations 暴露给后续 reporter 测试
    test_single_doc_checker.last_violations = violations


# ========== 测试 5：CrossUnitChecker ==========
def test_cross_unit_checker() -> None:
    print("\n[测试 5] CrossUnitChecker")
    loader = RuleLoader()
    rule = loader.load_by_id(RULES_DIR, "CU-001")
    _assert(rule is not None, "CU-001 规则加载成功")

    checker = CrossUnitChecker()
    # 监理方 (party_a)：混凝土灌入量
    party_a_data = {
        "doc_type": "监理旁站记录",
        "rows": [
            {"pile_no": "Z415", "混凝土灌入量": 13.0},   # 与施工方一致 → 通过
            {"pile_no": "Z417", "混凝土灌入量": 13.2},   # 与施工方 9.0 偏差 31.8% → 违规
        ],
    }
    # 施工方 (party_b)：灌入量
    party_b_data = {
        "doc_type": "碎石桩施工记录",
        "rows": [
            {"pile_no": "Z415", "灌入量": 13.0},
            {"pile_no": "Z417", "灌入量": 9.0},
        ],
    }
    violations = checker.check(rule, party_a_data, party_b_data)
    # 期望：1 个偏差超 5% 的 Violation
    _assert_eq(len(violations), 1, f"CrossUnitChecker 返回 1 个 Violation（实际 {len(violations)}）")

    v = violations[0]
    _assert_eq(v.rule_id, "CU-001", "Violation.rule_id = CU-001")
    _assert_eq(v.level, LEVEL_L2, "Violation.level = L2-LOGIC")
    _assert_eq(v.scope, SCOPE_CROSS_UNIT, "Violation.scope = CROSS_UNIT")
    _assert_eq(v.severity, SEVERITY_SANITY, "Violation.severity = Sanity Check")
    _assert("Z417" in v.error_message, "error_message 含桩号 Z417")
    _assert("13.2" in v.error_message, "error_message 含监理方数据 13.2")
    _assert("9.0" in v.error_message or "9" in v.error_message, "error_message 含施工方数据 9.0")

    # 缺失对齐键告警测试
    party_a_partial = {
        "doc_type": "监理旁站记录",
        "rows": [
            {"pile_no": "Z415", "混凝土灌入量": 13.0},
            {"pile_no": "Z999", "混凝土灌入量": 13.0},  # 施工方缺失
        ],
    }
    party_b_partial = {
        "doc_type": "碎石桩施工记录",
        "rows": [
            {"pile_no": "Z415", "灌入量": 13.0},
        ],
    }
    missing_violations = checker.check(rule, party_a_partial, party_b_partial)
    # Z415 通过，Z999 缺失告警 → 1 个 Best Practice Violation
    _assert_eq(len(missing_violations), 1, "缺失对齐键时返回 1 个告警 Violation")
    _assert_eq(missing_violations[0].severity, "Best Practice", "缺失告警 severity = Best Practice")
    _assert("Z999" in missing_violations[0].error_message, "缺失告警含桩号 Z999")

    # 把 violations 暴露给后续 reporter 测试
    test_cross_unit_checker.last_violations = violations


# ========== 测试 6：ViolationReporter ==========
def test_violation_reporter() -> None:
    print("\n[测试 6] ViolationReporter")
    single_violations = getattr(test_single_doc_checker, "last_violations", [])
    cross_violations = getattr(test_cross_unit_checker, "last_violations", [])
    _assert(len(single_violations) > 0, "SingleDocChecker 已生成 Violation")
    _assert(len(cross_violations) > 0, "CrossUnitChecker 已生成 Violation")

    all_violations = single_violations + cross_violations
    reporter = ViolationReporter()
    report = reporter.report(all_violations)

    _assert_eq(report["total"], len(all_violations), f"report.total = {len(all_violations)}")
    # 两个 Violation 都是 L2-LOGIC
    _assert_eq(report["by_level"]["L2-LOGIC"], len(all_violations),
               f"by_level[L2-LOGIC] = {len(all_violations)}")
    _assert_eq(report["by_level"]["L1-IRON"], 0, "by_level[L1-IRON] = 0")
    _assert_eq(report["by_level"]["L3-BUSINESS"], 0, "by_level[L3-BUSINESS] = 0")
    # 两个 Violation 都是 Sanity Check
    _assert_eq(report["by_severity"]["Sanity Check"], len(all_violations),
               f"by_severity[Sanity Check] = {len(all_violations)}")
    _assert_eq(report["by_severity"]["Fatal"], 0, "by_severity[Fatal] = 0")
    _assert_eq(report["by_severity"]["Best Practice"], 0, "by_severity[Best Practice] = 0")
    _assert_eq(len(report["violations"]), len(all_violations),
               f"violations 列表长度 = {len(all_violations)}")

    # findings 格式转换
    findings = reporter.to_audit_findings(all_violations)
    _assert_eq(len(findings), len(all_violations), f"findings 长度 = {len(all_violations)}")
    for f in findings:
        _assert("rule_id" in f, "finding 含 rule_id 字段")
        _assert("level" in f, "finding 含 level 字段")
        _assert("scope" in f, "finding 含 scope 字段")
        _assert(f["result"] in ("fail", "pass", "suspicious"),
                f"finding.result ∈ {{fail, pass, suspicious}}（实际 {f['result']}）")
        # Sanity Check → suspicious
        if f["severity"] == SEVERITY_SANITY:
            _assert_eq(f["result"], "suspicious", "Sanity Check → result=suspicious")
    print(f"  ✓ 所有 findings 字段齐全且 result 映射正确（共 {len(findings)} 条）")


# ========== 主入口 ==========
def main() -> int:
    print("=" * 60)
    print("规则引擎测试 (Phase A-2)")
    print(f"rules_dir = {RULES_DIR}")
    print("=" * 60)

    tests = [
        ("RuleLoader", test_rule_loader),
        ("RuleMatcher", test_rule_matcher),
        ("ExpressionEvaluator", test_expression_evaluator),
        ("SingleDocChecker", test_single_doc_checker),
        ("CrossUnitChecker", test_cross_unit_checker),
        ("ViolationReporter", test_violation_reporter),
    ]

    failed = []
    for name, func in tests:
        try:
            func()
            print(f"  → {name} 测试通过 ✓")
        except AssertionError as e:
            print(f"  → {name} 测试失败 ✗: {e}")
            failed.append(name)
        except Exception as e:
            import traceback
            print(f"  → {name} 测试异常 ✗: {e}")
            traceback.print_exc()
            failed.append(name)

    print("\n" + "=" * 60)
    if failed:
        print(f"❌ 测试完成：{len(tests) - len(failed)}/{len(tests)} 通过，失败: {failed}")
        return 1
    print(f"✅ 测试完成：{len(tests)}/{len(tests)} 全部通过")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
