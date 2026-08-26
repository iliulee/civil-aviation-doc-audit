#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rule_registry_builder.py
========================
民航施工资料审核 Skill — 规则注册表生成工具（Phase A-4）

扫描 rules/ 目录下所有规则 JSON 文件（排除 schema/ 子目录与 registry.json），
提取关键字段（rule_id / name / level / scope / status / version / category / source），
统计 by_level / by_scope / by_status，按 rule_id 字典序排序后生成 registry.json。

输出结构遵循 rules/schema/registry-schema.json（参考 spec.md 第 5.3 节）。

用法:
  python rule_registry_builder.py
      使用默认 rules/ 目录（脚本同级 ../rules）生成 registry.json

  python rule_registry_builder.py --rules-dir /path/to/rules
      指定规则目录

  python rule_registry_builder.py --validate
      生成注册表并调用 rule_schema_validator.py 校验所有规则文件与注册表

退出码:
  0 — 成功
  1 — 运行错误（目录缺失/解析失败/校验失败）
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_RULES_DIR = SKILL_ROOT / "rules"
REGISTRY_SCHEMA_PATH = DEFAULT_RULES_DIR / "schema" / "registry-schema.json"
VALIDATOR_PATH = SCRIPT_DIR / "rule_schema_validator.py"

SCHEMA_VERSION = "1.0"

# 统计维度键（与 registry-schema.json 保持一致，顺序固定）
LEVEL_KEYS = ["L1-IRON", "L2-LOGIC", "L3-BUSINESS"]
SCOPE_KEYS = ["SINGLE_DOC", "CROSS_DOC", "CROSS_UNIT"]
STATUS_KEYS = [
    "active", "draft", "testing",
    "incubating", "deprecated", "pending_confirmation",
]

# 注册表条目必填字段（registry-schema.json rules.items.required）
ENTRY_REQUIRED = ["rule_id", "name", "level", "scope", "status", "version", "file"]


def load_json(path):
    """以 UTF-8 读取 JSON 文件（兼容中文路径）。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_rule_files(rules_dir):
    """收集规则子目录下的规则 JSON 文件（排除 schema/、lifecycle/、registry.json）。

    只收 L1-iron/L2-logic/L3-business 下的规则文件；rules/ 根目录的
    inference_rules.json、table-schemas.json 属推断/表schema辅助配置，非规则，一律跳过。
    口径与 test_design_zone::test_registry_counts_match_files 一致（按子目录 glob 计数）。
    """
    rules_dir = Path(rules_dir)
    RULE_LAYERS = ("L1-iron", "L2-logic", "L3-business")
    files = []
    for p in sorted(rules_dir.rglob("*.json")):
        rel = p.relative_to(rules_dir).as_posix()
        if rel == "registry.json":
            continue
        if rel.startswith("schema/"):
            continue
        if rel.startswith("lifecycle/"):
            continue
        layer = rel.split("/", 1)[0]
        if layer not in RULE_LAYERS:
            continue
        files.append(p)
    return files


def extract_rule_entry(rule_path, rules_dir):
    """从单条规则文件提取注册表条目字段。

    返回 (entry_dict, warnings: list[str])。
    entry_dict 必填字段缺失时对应值为 None，并记入 warnings。
    """
    data = load_json(rule_path)
    rel = rule_path.relative_to(rules_dir).as_posix()

    entry = {
        "rule_id": data.get("rule_id"),
        "name": data.get("name"),
        "level": data.get("level"),
        "scope": data.get("scope"),
        "status": data.get("status"),
        "version": data.get("version"),
        "file": rel,
    }
    # 可选关键字段：仅在存在时纳入（registry-schema additionalProperties=true）
    if "category" in data and data["category"] is not None:
        entry["category"] = data["category"]
    if "source" in data and data["source"] is not None:
        entry["source"] = data["source"]

    warnings = []
    for k in ("rule_id", "name", "level", "scope", "status", "version"):
        if entry[k] is None:
            warnings.append(f"{rel}: 缺少必填字段 {k}")
    return entry, warnings


def build_registry(rules_dir):
    """扫描规则目录并构建注册表数据结构。

    返回 (registry_dict, warnings)。
    """
    rules_dir = Path(rules_dir)
    files = collect_rule_files(rules_dir)

    entries = []
    warnings = []
    seen_ids = {}
    for fp in files:
        try:
            entry, w = extract_rule_entry(fp, rules_dir)
        except json.JSONDecodeError as e:
            warnings.append(f"{fp}: JSON 解析失败 - {e}")
            continue
        except OSError as e:
            warnings.append(f"{fp}: 文件读取失败 - {e}")
            continue

        warnings.extend(w)

        # 重复 rule_id 检测
        rid = entry.get("rule_id")
        if rid is not None:
            if rid in seen_ids:
                warnings.append(
                    f"{entry['file']}: rule_id 重复 {rid!r}（已见于 {seen_ids[rid]}）"
                )
            else:
                seen_ids[rid] = entry["file"]

        entries.append(entry)

    # 排序：按 rule_id 字典序（None 视作空串排最前）
    entries.sort(key=lambda e: (e.get("rule_id") or ""))

    # 统计
    by_level = {k: 0 for k in LEVEL_KEYS}
    by_scope = {k: 0 for k in SCOPE_KEYS}
    by_status = {k: 0 for k in STATUS_KEYS}
    unknown = {"level": [], "scope": [], "status": []}

    for e in entries:
        lv, sc, st = e.get("level"), e.get("scope"), e.get("status")
        if lv in by_level:
            by_level[lv] += 1
        else:
            unknown["level"].append(f"{e['file']}={lv!r}")
        if sc in by_scope:
            by_scope[sc] += 1
        else:
            unknown["scope"].append(f"{e['file']}={sc!r}")
        if st in by_status:
            by_status[st] += 1
        else:
            unknown["status"].append(f"{e['file']}={st!r}")

    for dim, items in unknown.items():
        for it in items:
            warnings.append(f"未知的 {dim} 取值: {it}")

    # 更新时间：Asia/Shanghai 时区，ISO 8601（匹配 schema pattern）
    tz = timezone(timedelta(hours=8))
    updated_at = datetime.now(tz).isoformat(timespec="seconds")

    registry = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": updated_at,
        "total_rules": len(entries),
        "by_level": by_level,
        "by_scope": by_scope,
        "by_status": by_status,
        "rules": entries,
    }
    return registry, warnings


def run_validator(rules_dir, registry_path):
    """调用 rule_schema_validator.py 校验所有规则文件与注册表。

    返回 0 表示全部通过，1 表示存在失败。
    """
    rc_all = 0
    py = sys.executable or "python"

    # 1) 校验所有规则文件
    cmd1 = [py, str(VALIDATOR_PATH), "--rules-dir", str(rules_dir)]
    print(f"\n$ {' '.join(cmd1)}")
    r1 = subprocess.run(cmd1)
    if r1.returncode != 0:
        rc_all = 1

    # 2) 校验注册表
    cmd2 = [py, str(VALIDATOR_PATH), "--registry", str(registry_path)]
    print(f"\n$ {' '.join(cmd2)}")
    r2 = subprocess.run(cmd2)
    if r2.returncode != 0:
        rc_all = 1

    return rc_all


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="民航施工资料审核 Skill — 规则注册表生成工具（Phase A-4）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 成功 / 1 存在失败",
    )
    parser.add_argument(
        "--rules-dir",
        default=str(DEFAULT_RULES_DIR),
        help=f"规则目录，默认为 {DEFAULT_RULES_DIR}",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="生成后调用 rule_schema_validator.py 校验所有规则与注册表",
    )
    args = parser.parse_args(argv)

    rules_dir = Path(args.rules_dir)
    if not rules_dir.is_absolute():
        rules_dir = Path.cwd() / rules_dir
    if not rules_dir.exists():
        print(f"错误: 规则目录不存在: {rules_dir}")
        return 1

    print("=" * 70)
    print("民航施工资料审核 Skill — 规则注册表生成工具")
    print("=" * 70)
    print(f"规则目录: {rules_dir}")

    registry, warnings = build_registry(rules_dir)

    registry_path = rules_dir / "registry.json"
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("-" * 70)
    print(f"已生成注册表: {registry_path}")
    print(f"扫描文件数: {len(registry['rules'])}")
    print(f"total_rules = {registry['total_rules']}")
    print(f"by_level   = {registry['by_level']}")
    print(f"  (L1+L2+L3 = {sum(registry['by_level'].values())})")
    print(f"by_scope   = {registry['by_scope']}")
    print(f"  (合计     = {sum(registry['by_scope'].values())})")
    print(f"by_status  = {registry['by_status']}")
    print(f"  (合计     = {sum(registry['by_status'].values())})")

    if warnings:
        print("-" * 70)
        print(f"警告 ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")

    rc = 0
    if args.validate:
        print("-" * 70)
        print("启用 --validate：调用 rule_schema_validator.py 校验")
        vrc = run_validator(rules_dir, registry_path)
        if vrc != 0:
            rc = 1

    print("=" * 70)
    if rc == 0:
        print("完成。")
    else:
        print("完成，但存在校验失败，请检查上方输出。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
