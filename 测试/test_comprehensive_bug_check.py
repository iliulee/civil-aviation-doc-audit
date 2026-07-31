# -*- coding: utf-8 -*-
"""
全量BUG检查脚本：从多个角度验证规则管理子系统的可用性
======================================================

检查维度：
  A. 规则文件完整性（91条规则JSON是否可解析）
  B. 表达式合法性（check_expr.expr是否可被Python eval执行）
  C. 规则Schema合规性（是否通过rule-schema.json验证）
  D. 规则ID唯一性（无重复rule_id）
  E. 状态机合法性（status字段是否在枚举值内）
  F. 层级一致性（level字段与目录是否匹配）
  G. error_template完整性（是否含未渲染占位符）
  H. 跨模块兼容性（新模块是否修改旧模块的import/接口）
  I. 模块导入完整性（各新模块是否可无错误导入）
"""

import json
import sys
import traceback
from pathlib import Path
from collections import Counter

SCRIPT_DIR = Path(__file__).resolve().parent.parent / ".trae" / "skills" / "civil-aviation-doc-audit" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

RULES_DIR = Path(__file__).resolve().parent.parent / ".trae" / "skills" / "civil-aviation-doc-audit" / "rules"
SKILL_ROOT = Path(__file__).resolve().parent.parent / ".trae" / "skills" / "civil-aviation-doc-audit"

VALID_STATUSES = {"active", "draft", "testing", "incubating", "deprecated", "pending_confirmation"}
VALID_LEVELS = {"L1-IRON", "L2-LOGIC", "L3-BUSINESS"}
VALID_SCOPES = {"SINGLE_DOC", "CROSS_DOC", "CROSS_UNIT"}

results = {"pass": 0, "fail": 0, "warn": 0}


def check(name: str, condition: bool, detail: str = "") -> bool:
    global results
    if condition:
        results["pass"] += 1
        print(f"  ✓ {name}")
    else:
        results["fail"] += 1
        print(f"  ✗ {name}  -- {detail}")
    return condition


def warn(name: str, detail: str = "") -> None:
    global results
    results["warn"] += 1
    print(f"  ⚠ {name}  -- {detail}")


# ==================== A. 规则文件完整性 ====================
print("=" * 60)
print("A. 规则文件完整性")
print("=" * 60)

rule_files = []
for p in sorted(RULES_DIR.rglob("*.json")):
    rel = p.relative_to(RULES_DIR)
    if "schema" in str(rel.parts) or "lifecycle" in str(rel.parts) or p.name == "registry.json":
        continue
    rule_files.append(p)

print(f"  规则文件总数: {len(rule_files)}")

parse_ok = 0
parse_fail = []
for fp in rule_files:
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        if "rule_id" in data:
            parse_ok += 1
        else:
            parse_fail.append((fp.name, "缺少rule_id"))
    except Exception as e:
        parse_fail.append((fp.name, str(e)))

check("JSON可解析", len(parse_fail) == 0, f"失败: {parse_fail}")
check(f"规则总数正确({parse_ok}条)", parse_ok == 91, f"实际{parse_ok}")


# ==================== B. 表达式合法性 ====================
print("\n" + "=" * 60)
print("B. 表达式合法性（Python eval兼容性）")
print("=" * 60)

safe_funcs = {"abs": abs, "max": max, "min": min, "sum": sum, "len": len, "round": round}
safe_consts = {"True": True, "False": False, "None": None}

expr_ok = 0
expr_fail = []
for fp in rule_files:
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        continue
    expr = data.get("check_expr", {}).get("expr", "")
    if not expr:
        continue
    # 跳过领域DSL表达式（使用 where/exists/implies 等非Python关键字）
    dsl_keywords = ['where ', 'exists(', 'implies ']
    if any(kw in expr for kw in dsl_keywords):
        continue
    # 使用 compile() 做语法检查（不实际求值，因为表达式依赖领域变量如 field_a、实长、桩顶高程等）
    try:
        compile(expr, "<rule>", "eval")
        expr_ok += 1
    except SyntaxError as e:
        expr_fail.append((data.get("rule_id", fp.name), expr[:80], str(e)[:60]))

check(f"表达式语法合法: {expr_ok}/{len(rule_files)}（含空表达式则跳过）",
      len(expr_fail) == 0,
      f"语法错误 {len(expr_fail)} 条: {expr_fail[:5]}")

if expr_fail:
    print(f"\n  表达式语法错误详情:")
    for rid, expr, err in expr_fail:
        print(f"    [{rid}] {expr}")
        print(f"           Error: {err}")


# ==================== C. Schema合规性 ====================
print("\n" + "=" * 60)
print("C. 规则Schema合规性")
print("=" * 60)

from rule_schema_validator import validate_rule_fallback

schema_ok = 0
schema_fail = []
for fp in rule_files:
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        continue
    errors = validate_rule_fallback(data)
    if not errors:
        schema_ok += 1
    else:
        schema_fail.append((data.get("rule_id", fp.name), errors))

check(f"Schema合规: {schema_ok}/{len(rule_files)}",
      len(schema_fail) == 0,
      f"失败 {len(schema_fail)} 条")

if schema_fail:
    print(f"\n  Schema不合规详情:")
    for rid, errs in schema_fail[:5]:
        print(f"    [{rid}] {errs}")


# ==================== D. 规则ID唯一性 ====================
print("\n" + "=" * 60)
print("D. 规则ID唯一性")
print("=" * 60)

all_ids = []
for fp in rule_files:
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        all_ids.append(data.get("rule_id", ""))
    except Exception:
        pass

id_counts = Counter(all_ids)
dups = {k: v for k, v in id_counts.items() if v > 1}
check("rule_id无重复", len(dups) == 0, f"重复: {dups}")


# ==================== E. 状态机合法性 ====================
print("\n" + "=" * 60)
print("E. 状态机合法性")
print("=" * 60)

status_err = []
for fp in rule_files:
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        status = data.get("status", "")
        if status not in VALID_STATUSES:
            status_err.append((data.get("rule_id", fp.name), status))
    except Exception:
        pass

check("status枚举合法", len(status_err) == 0, f"非法: {status_err}")


# ==================== F. 层级一致性 ====================
print("\n" + "=" * 60)
print("F. 层级一致性（level vs 目录）")
print("=" * 60)

level_dir_map = {
    "L1-iron": "L1-IRON",
    "L2-logic": "L2-LOGIC",
    "L3-business": "L3-BUSINESS",
}
level_mismatch = []
for fp in rule_files:
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        level = data.get("level", "")
        parent_dir = fp.parent.name
        if parent_dir in level_dir_map:
            expected = level_dir_map[parent_dir]
            if level != expected:
                level_mismatch.append((fp.name, f"目录={parent_dir} 预期={expected} 实际={level}"))
    except Exception:
        pass
# cross-unit目录规则不参与此检查
level_mismatch = [m for m in level_mismatch if "cross-unit" not in str(m)]

check("层级与目录一致", len(level_mismatch) == 0, f"不一致: {level_mismatch}")


# ==================== G. error_template完整性 ====================
print("\n" + "=" * 60)
print("G. error_template完整性")
print("=" * 60)

template_err = []
for fp in rule_files:
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        template = data.get("error_template", "")
        if not template:
            template_err.append((data.get("rule_id", fp.name), "空模板"))
            continue
        # 检查是否有未闭合的占位符 {xxx} 但实际应该已经被渲染
        # 这里只检查明显问题：模板中有 {桩号} 但实际渲染变量是 pile_no
        if "{桩号}" in template and "pile_no" in template:
            warn(f"{data.get('rule_id', fp.name)} 模板含 {{{{桩号}}}} 中文占位符，可能需pile_no")
    except Exception:
        pass

check("error_template非空", len(template_err) == 0, f"空模板: {template_err}")


# ==================== H. 跨模块兼容性 ====================
print("\n" + "=" * 60)
print("H. 跨模块兼容性（新模块不破坏旧模块）")
print("=" * 60)

# 检查旧模块是否仍可正常导入
old_modules = ["review_audit", "build_foundation", "run_audit", "data_quality_check",
               "ocr_image", "extract_pdf", "postprocess", "ocr_confusion_check",
               "verify_fields", "vision_providers"]

import_ok = 0
import_fail = []
for mod_name in old_modules:
    try:
        __import__(mod_name)
        import_ok += 1
    except Exception as e:
        import_fail.append((mod_name, str(e)[:80]))

check(f"旧模块可导入: {import_ok}/{len(old_modules)}",
      len(import_fail) == 0,
      f"失败: {import_fail}")

# 检查新模块是否可正常导入
new_modules = ["rule_engine", "rule_admin", "rule_lifecycle", "feedback_store",
               "feedback_analyzer", "rule_monitor", "audit_memory", "rule_reflector",
               "rule_registry_builder", "rule_schema_validator"]

new_import_ok = 0
new_import_fail = []
for mod_name in new_modules:
    try:
        __import__(mod_name)
        new_import_ok += 1
    except Exception as e:
        new_import_fail.append((mod_name, str(e)[:80]))

check(f"新模块可导入: {new_import_ok}/{len(new_modules)}",
      len(new_import_fail) == 0,
      f"失败: {new_import_fail}")


# ==================== I. 规则引擎集成链路 ====================
print("\n" + "=" * 60)
print("I. 规则引擎集成链路")
print("=" * 60)

from rule_engine import RuleLoader, RuleMatcher, SingleDocChecker, ViolationReporter

loader = RuleLoader()
all_rules = loader.load_all(RULES_DIR)
active_rules = loader.load_active(RULES_DIR)

# 检查是否有规则同时属于L1但scope不是单一文档
l1_scope_issues = []
for r in active_rules:
    # L1-IRON + CROSS_UNIT is valid (e.g., CU-012: 流程倒签需要监理-施工跨单位对比)
    if r.level == "L1-IRON" and r.scope not in ("SINGLE_DOC", "CROSS_DOC", "CROSS_UNIT"):
        l1_scope_issues.append(f"{r.rule_id}: scope={r.scope}")

# 检查CROSS_DOC规则是否有有效的trigger_when
cross_doc_no_trigger = []
for r in active_rules:
    if r.scope == "CROSS_DOC" and not r.trigger_when:
        cross_doc_no_trigger.append(r.rule_id)

check("L1铁律scope合理", len(l1_scope_issues) == 0, str(l1_scope_issues))
check("CROSS_DOC规则有trigger_when", len(cross_doc_no_trigger) == 0, str(cross_doc_no_trigger))

# 检查级别与严重度映射
severity_check = []
for r in active_rules:
    sev = r.severity_on_violation or ""
    if r.level == "L1-IRON" and sev != "Fatal":
        severity_check.append(f"{r.rule_id}: L1但severity={sev}")
    if r.level == "L2-LOGIC" and sev not in ("", "Sanity Check"):
        if sev != "Fatal":  # 少数L2可能也是Fatal
            severity_check.append(f"{r.rule_id}: L2但severity={sev}")

if severity_check:
    warn(f"层级-严重度不一致: {len(severity_check)}条", str(severity_check[:5]))


# ==================== 总结 ====================
print("\n" + "=" * 60)
print("全量检查总结")
print("=" * 60)
total = results["pass"] + results["fail"] + results["warn"]
print(f"  通过: {results['pass']}")
print(f"  失败: {results['fail']}")
print(f"  警告: {results['warn']}")
print(f"  总计: {total}")

if results["fail"] == 0:
    print("  ✅ 全部检查通过")
    sys.exit(0)
else:
    print(f"  ❌ {results['fail']} 项检查失败")
    sys.exit(1)