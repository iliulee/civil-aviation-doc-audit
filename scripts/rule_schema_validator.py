#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rule_schema_validator.py
========================
民航施工资料审核 Skill — 规则文件 Schema 校验工具（Phase A-1.3）

用法:
  python rule_schema_validator.py --rules-dir rules/
      校验整个 rules/ 目录下的所有规则文件（排除 registry.json 与 schema/）

  python rule_schema_validator.py --file rules/L2-logic/LG-001.json
      校验单个规则 JSON 文件

  python rule_schema_validator.py --registry rules/registry.json
      校验注册表文件

退出码:
  0 — 全部通过
  1 — 存在校验失败或运行错误

依赖:
  优先使用 jsonschema 库（Draft 2020-12）；若环境未安装则回退到内置字段检查。
  两种模式下校验逻辑等价，确保在无第三方依赖的环境中仍可运行。
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
RULE_SCHEMA_PATH = SKILL_ROOT / "rules" / "schema" / "rule-schema.json"
REGISTRY_SCHEMA_PATH = SKILL_ROOT / "rules" / "schema" / "registry-schema.json"

# 枚举值（与 schema 保持一致）
LEVEL_ENUM = {"L1-IRON", "L2-LOGIC", "L3-BUSINESS"}
SCOPE_ENUM = {"SINGLE_DOC", "CROSS_DOC", "CROSS_UNIT"}
STATUS_ENUM = {"draft", "testing", "active", "incubating", "deprecated", "pending_confirmation"}
SOURCE_ENUM = {"system", "custom", "incubated"}
SEVERITY_ENUM = {"Fatal", "Sanity Check", "Best Practice"}
CHECK_TYPE_ENUM = {"expression", "cross_compare", "aggregation"}

# 正则
RULE_ID_RE = re.compile(r"^[A-Z]+-[A-Z0-9-]+$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?(Z|[+-]\d{2}:\d{2})?$")

RULE_REQUIRED_FIELDS = [
    "rule_id", "name", "level", "scope", "trigger_when", "check_expr",
    "error_template", "status", "source", "version", "created_at",
    "updated_at", "changelog",
]

# jsonschema 可用性检测
try:
    import jsonschema
    from jsonschema import Draft202012Validator
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


def load_json(path):
    """以 UTF-8 读取 JSON 文件（兼容中文路径）。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 内置回退校验器（jsonschema 不可用时使用），逻辑与 schema 等价
# ---------------------------------------------------------------------------
def _is_int(value):
    """判断是否为真正的整数（排除 bool）。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    """判断是否为数值（排除 bool）。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_rule_fallback(data):
    """内置回退校验单条规则：返回错误消息列表（空列表表示通过）。"""
    errors = []

    if not isinstance(data, dict):
        return ["规则文件根节点必须是对象（object）"]

    # 1. 必填字段
    for field in RULE_REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"缺少必填字段: {field}")

    # 2. rule_id 模式
    rid = data.get("rule_id")
    if isinstance(rid, str) and not RULE_ID_RE.match(rid):
        errors.append(f"rule_id 格式不合法: {rid!r}（需匹配 ^[A-Z]+-[A-Z0-9-]+$）")

    # 3. name 非空
    if "name" in data and not (isinstance(data["name"], str) and data["name"]):
        errors.append("name 必须是非空字符串")

    # 4. level 枚举
    if "level" in data and data["level"] not in LEVEL_ENUM:
        errors.append(f"level 取值不合法: {data['level']!r}，可选 {sorted(LEVEL_ENUM)}")

    # 5. scope 枚举
    scope = data.get("scope")
    if "scope" in data and scope not in SCOPE_ENUM:
        errors.append(f"scope 取值不合法: {scope!r}，可选 {sorted(SCOPE_ENUM)}")

    # 6. trigger_when 结构 + 作用域条件
    tw = data.get("trigger_when")
    if "trigger_when" in data and not isinstance(tw, dict):
        errors.append("trigger_when 必须是对象")
    if isinstance(tw, dict):
        if scope == "CROSS_UNIT":
            for k in ("doc_type_a", "doc_type_b"):
                if k not in tw:
                    errors.append(f"scope=CROSS_UNIT 时 trigger_when 必须含 {k}")
        else:
            if "doc_type" not in tw:
                errors.append(f"scope={scope} 时 trigger_when 必须含 doc_type 数组")
            elif not isinstance(tw["doc_type"], list):
                errors.append("trigger_when.doc_type 必须是数组")

    # 7. check_expr
    ce = data.get("check_expr")
    if "check_expr" in data and not isinstance(ce, dict):
        errors.append("check_expr 必须是对象")
    if isinstance(ce, dict):
        if "type" not in ce:
            errors.append("check_expr 缺少 type 字段")
        elif ce["type"] not in CHECK_TYPE_ENUM:
            errors.append(f"check_expr.type 取值不合法: {ce['type']!r}，可选 {sorted(CHECK_TYPE_ENUM)}")
        if "expr" not in ce:
            errors.append("check_expr 缺少 expr 字段")
        elif not (isinstance(ce["expr"], str) and ce["expr"]):
            errors.append("check_expr.expr 必须是非空字符串")

    # 8. error_template 非空
    et = data.get("error_template")
    if "error_template" in data and not (isinstance(et, str) and et):
        errors.append("error_template 必须是非空字符串")

    # 9. status 枚举
    if "status" in data and data["status"] not in STATUS_ENUM:
        errors.append(f"status 取值不合法: {data['status']!r}，可选 {sorted(STATUS_ENUM)}")

    # 10. source 枚举
    if "source" in data and data["source"] not in SOURCE_ENUM:
        errors.append(f"source 取值不合法: {data['source']!r}，可选 {sorted(SOURCE_ENUM)}")

    # 11. version 语义化版本
    ver = data.get("version")
    if isinstance(ver, str) and not VERSION_RE.match(ver):
        errors.append(f"version 格式不合法: {ver!r}（需 X.Y.Z）")

    # 12. created_at / updated_at ISO 8601
    for k in ("created_at", "updated_at"):
        v = data.get(k)
        if isinstance(v, str) and not ISO8601_RE.match(v):
            errors.append(f"{k} 格式不合法: {v!r}（需 ISO 8601）")

    # 13. severity_on_violation（可选）枚举
    sev = data.get("severity_on_violation")
    if sev is not None and sev not in SEVERITY_ENUM:
        errors.append(f"severity_on_violation 取值不合法: {sev!r}，可选 {sorted(SEVERITY_ENUM)}")

    # 14. changelog 数组 + 每项必填
    cl = data.get("changelog")
    if "changelog" in data and not isinstance(cl, list):
        errors.append("changelog 必须是数组")
    if isinstance(cl, list):
        for i, item in enumerate(cl):
            if not isinstance(item, dict):
                errors.append(f"changelog[{i}] 必须是对象")
                continue
            for k in ("version", "date", "author", "change"):
                if k not in item:
                    errors.append(f"changelog[{i}] 缺少字段: {k}")

    # 15. stats（可选）数值约束
    stats = data.get("stats")
    if "stats" in data and not isinstance(stats, dict):
        errors.append("stats 必须是对象")
    if isinstance(stats, dict):
        for k in ("total_hits", "total_reviews", "false_positive_count"):
            v = stats.get(k)
            if v is not None and not (_is_int(v) and v >= 0):
                errors.append(f"stats.{k} 必须是 ≥0 的整数")
        for k in ("hit_rate", "false_positive_rate"):
            v = stats.get(k)
            if v is not None and not (_is_number(v) and v >= 0):
                errors.append(f"stats.{k} 必须是 ≥0 的数值")

    # 16. alignment + 跨单位条件约束
    alignment = data.get("alignment")
    if "alignment" in data and alignment is not None and not isinstance(alignment, dict):
        errors.append("alignment 必须是对象或 null")
    if scope == "CROSS_UNIT":
        if alignment is None:
            errors.append("scope=CROSS_UNIT 时 alignment 必填且不能为 null")
        elif isinstance(alignment, dict):
            for side in ("party_a", "party_b"):
                pa = alignment.get(side)
                if not isinstance(pa, dict):
                    errors.append(f"alignment.{side} 必须是对象")
                else:
                    for k in ("role", "doc_type"):
                        if k not in pa:
                            errors.append(f"alignment.{side} 缺少字段: {k}")
            jk = alignment.get("join_key")
            if not (isinstance(jk, list) and len(jk) >= 1 and all(isinstance(x, str) for x in jk)):
                errors.append("alignment.join_key 必须是非空字符串数组")
        # confirmation_required 应为 true
        if data.get("confirmation_required") is not True:
            errors.append("scope=CROSS_UNIT 时 confirmation_required 应为 true")

    return errors


def validate_registry_fallback(data):
    """内置回退校验 registry.json：返回错误消息列表。"""
    errors = []
    if not isinstance(data, dict):
        return ["注册表根节点必须是对象（object）"]

    for field in ("schema_version", "updated_at", "total_rules",
                  "by_level", "by_scope", "by_status", "rules"):
        if field not in data:
            errors.append(f"缺少必填字段: {field}")

    sv = data.get("schema_version")
    if "schema_version" in data and not isinstance(sv, str):
        errors.append("schema_version 必须是字符串")

    ua = data.get("updated_at")
    if isinstance(ua, str) and not ISO8601_RE.match(ua):
        errors.append(f"updated_at 格式不合法: {ua!r}（需 ISO 8601）")

    tr = data.get("total_rules")
    if tr is not None and not (_is_int(tr) and tr >= 0):
        errors.append("total_rules 必须是 ≥0 的整数")

    for grp, keys in (
        ("by_level", ["L1-IRON", "L2-LOGIC", "L3-BUSINESS"]),
        ("by_scope", ["SINGLE_DOC", "CROSS_DOC", "CROSS_UNIT"]),
        ("by_status", ["active", "draft", "testing", "incubating",
                       "deprecated", "pending_confirmation"]),
    ):
        obj = data.get(grp)
        if grp in data and not isinstance(obj, dict):
            errors.append(f"{grp} 必须是对象")
            continue
        if not isinstance(obj, dict):
            continue
        for k in keys:
            v = obj.get(k)
            if v is None:
                errors.append(f"{grp} 缺少字段: {k}")
            elif not (_is_int(v) and v >= 0):
                errors.append(f"{grp}.{k} 必须是 ≥0 的整数")

    rules = data.get("rules")
    if "rules" in data and not isinstance(rules, list):
        errors.append("rules 必须是数组")
    if isinstance(rules, list):
        for i, item in enumerate(rules):
            if not isinstance(item, dict):
                errors.append(f"rules[{i}] 必须是对象")
                continue
            for k in ("rule_id", "name", "level", "scope", "status", "version", "file"):
                if k not in item:
                    errors.append(f"rules[{i}] 缺少字段: {k}")
            rid = item.get("rule_id")
            if isinstance(rid, str) and not RULE_ID_RE.match(rid):
                errors.append(f"rules[{i}].rule_id 格式不合法: {rid!r}")
            if "level" in item and item["level"] not in LEVEL_ENUM:
                errors.append(f"rules[{i}].level 取值不合法: {item['level']!r}")
            if "scope" in item and item["scope"] not in SCOPE_ENUM:
                errors.append(f"rules[{i}].scope 取值不合法: {item['scope']!r}")
            if "status" in item and item["status"] not in STATUS_ENUM:
                errors.append(f"rules[{i}].status 取值不合法: {item['status']!r}")
            ver = item.get("version")
            if isinstance(ver, str) and not VERSION_RE.match(ver):
                errors.append(f"rules[{i}].version 格式不合法: {ver!r}")

    return errors


# ---------------------------------------------------------------------------
# jsonschema 校验（可用时）
# ---------------------------------------------------------------------------
def validate_with_jsonschema(data, schema):
    """使用 jsonschema 库校验，返回可读错误消息列表。"""
    errors = []
    validator = Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in err.path) or "(root)"
        errors.append(f"[{path}] {err.message}")
    return errors


# ---------------------------------------------------------------------------
# 校验入口
# ---------------------------------------------------------------------------
def validate_rule_file(file_path):
    """校验单个规则文件，返回 (success: bool, errors: list[str])。"""
    try:
        data = load_json(file_path)
    except json.JSONDecodeError as e:
        return False, [f"JSON 解析失败: {e}"]
    except OSError as e:
        return False, [f"文件读取失败: {e}"]

    try:
        schema = load_json(RULE_SCHEMA_PATH)
    except OSError as e:
        return False, [f"规则 schema 文件读取失败 ({RULE_SCHEMA_PATH}): {e}"]

    if HAS_JSONSCHEMA:
        errors = validate_with_jsonschema(data, schema)
    else:
        errors = validate_rule_fallback(data)
    return (len(errors) == 0), errors


def validate_registry_file(file_path):
    """校验注册表文件，返回 (success: bool, errors: list[str])。"""
    try:
        data = load_json(file_path)
    except json.JSONDecodeError as e:
        return False, [f"JSON 解析失败: {e}"]
    except OSError as e:
        return False, [f"文件读取失败: {e}"]

    try:
        schema = load_json(REGISTRY_SCHEMA_PATH)
    except OSError as e:
        return False, [f"注册表 schema 文件读取失败 ({REGISTRY_SCHEMA_PATH}): {e}"]

    if HAS_JSONSCHEMA:
        errors = validate_with_jsonschema(data, schema)
    else:
        errors = validate_registry_fallback(data)
    return (len(errors) == 0), errors


def collect_rule_files(rules_dir):
    """收集 rules/ 目录下所有规则 JSON 文件（排除 registry.json、schema/ 与 lifecycle/）。"""
    rules_dir = Path(rules_dir)
    files = []
    for p in sorted(rules_dir.rglob("*.json")):
        rel = p.relative_to(rules_dir).as_posix()
        if rel == "registry.json":
            continue
        if rel.startswith("schema/"):
            continue
        if rel.startswith("lifecycle/"):
            continue
        files.append(p)
    return files


def print_result(label, success, errors):
    if success:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}")
        for e in errors:
            print(f"           - {e}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="民航施工资料审核 Skill — 规则文件 Schema 校验工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 全部通过 / 1 存在失败",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--rules-dir", help="校验整个 rules/ 目录下的所有规则文件")
    group.add_argument("--file", help="校验单个规则 JSON 文件")
    group.add_argument("--registry", help="校验 registry.json 注册表文件")
    args = parser.parse_args(argv)

    print("=" * 70)
    print("民航施工资料审核 Skill — 规则 Schema 校验工具")
    print("=" * 70)
    if HAS_JSONSCHEMA:
        print(f"校验引擎: jsonschema {jsonschema.__version__} (Draft 2020-12)")
    else:
        print("校验引擎: 内置回退校验器（未检测到 jsonschema 库）")
    print("-" * 70)

    total = 0
    passed = 0
    failed = 0

    if args.file:
        file_path = Path(args.file)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        if not file_path.exists():
            print(f"错误: 文件不存在: {file_path}")
            return 1
        total = 1
        success, errors = validate_rule_file(file_path)
        print_result(str(file_path), success, errors)
        if success:
            passed += 1
        else:
            failed += 1

    elif args.registry:
        file_path = Path(args.registry)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        if not file_path.exists():
            print(f"错误: 文件不存在: {file_path}")
            return 1
        total = 1
        success, errors = validate_registry_file(file_path)
        print_result(str(file_path), success, errors)
        if success:
            passed += 1
        else:
            failed += 1

    elif args.rules_dir:
        rules_dir = Path(args.rules_dir)
        if not rules_dir.is_absolute():
            rules_dir = Path.cwd() / rules_dir
        if not rules_dir.exists():
            print(f"错误: 目录不存在: {rules_dir}")
            return 1
        files = collect_rule_files(rules_dir)
        if not files:
            print(f"提示: 在 {rules_dir} 下未找到任何规则 JSON 文件")
        for fp in files:
            total += 1
            success, errors = validate_rule_file(fp)
            print_result(str(fp), success, errors)
            if success:
                passed += 1
            else:
                failed += 1

    print("-" * 70)
    print(f"汇总: 共 {total} 个文件，通过 {passed}，失败 {failed}")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
