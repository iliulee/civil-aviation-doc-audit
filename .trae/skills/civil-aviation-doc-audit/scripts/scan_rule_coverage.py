#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_rule_coverage.py — 规则覆盖扫描（v10.4 A1 诊断工具）
==========================================================

检查"规则声明的 doc_type 触发词"与"生产环境实际产出的 doc_type"是否对得上，
找出静默失效高危规则（写了但永远不会执行）。

产出三类报告：
  1. 零交集规则：规则声明了一批 doc_type，生产环境一个都产不出来 → 永不执行
  2. 生产覆盖缺口：生产环境真实存在的 doc_type，没有任何 SINGLE_DOC 规则匹配
  3. 每条规则命中的生产文档数（matched_docs 的事前版本）

用法：
  python scripts/scan_rule_coverage.py            # 扫 skill 同级的项目根
  python scripts/scan_rule_coverage.py <项目根>   # 指定项目根目录

退出码：0=正常输出报告（诊断工具，发现问题不算失败）
        1=运行错误（规则库加载失败等）
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rule_engine import RuleLoader, RuleMatcher, build_unguarded_doc_types

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
RULES_DIR = SKILL_DIR / "rules"


def load_production_doc_types(root: Path) -> dict:
    """P1: 扫历史数据底座 index.json 的真实 doc_type。

    v10.5：仅统计受审文档（doc_role == 'audited'，缺省 None 视为受审）。
    reference 角色（如设计变更文件）是审核参照，不进规则引擎审核流，
    混进覆盖统计会制造伪缺口。
    """
    import glob as globmod

    vals: dict = {}
    patterns = [
        str(root / "测试*" / "数据底座" / "index.json"),
        str(root / "测试*" / "数据底座_备份*" / "index.json"),
        str(root / "audit_output" / "**" / "index.json"),
    ]
    seen = set()
    for pat in patterns:
        for idx in globmod.glob(pat, recursive=True):
            p = Path(idx)
            if p in seen:
                continue
            seen.add(p)
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for doc in d.get("documents", []):
                role = doc.get("doc_role") or "audited"
                if role != "audited":
                    continue
                dt = (doc.get("doc_type") or "").strip()
                if dt:
                    vals[dt] = vals.get(dt, 0) + 1
    return vals


def load_active_single_doc_rules() -> list:
    """加载全部 active 规则（v10.5：覆盖判定需含 CROSS 类，不再只看 SINGLE_DOC）。"""
    loader = RuleLoader()
    rules = [r for r in loader.load_all(RULES_DIR)
             if r.status == "active"]
    return rules


def match_rule_doc_type(rule, doc_type: str) -> bool:
    """与 RuleMatcher.match_by_doc_type 同语义的单条判定。"""
    matcher = RuleMatcher()
    return matcher.match_by_doc_type([rule], doc_type)


def main() -> int:
    # 默认项目根 = scripts/ → skill/ → .trae/skills/ → 项目根
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else SKILL_DIR.parent.parent.parent
    print("=" * 60)
    print("规则覆盖扫描（规则 doc_type 触发词 vs 生产实际产出）")
    print("=" * 60)
    print(f"项目根: {root}")
    print(f"规则库: {RULES_DIR}")
    print()

    # 1. 生产 doc_type
    prod = load_production_doc_types(root)
    print(f"[1] 生产环境实际 doc_type：{len(prod)} 种")
    for dt, n in sorted(prod.items(), key=lambda kv: -kv[1]):
        print(f"      {n:>3} 份  {dt}")
    if not prod:
        print("      （未扫到任何历史数据底座，仅做规则侧自检）")
    print()

    # 2. 规则加载
    try:
        rules = load_active_single_doc_rules()
    except Exception as e:
        print(f"[2] 规则库加载失败：{e}")
        return 1
    n_single = sum(1 for r in rules if r.scope == "SINGLE_DOC")
    print(f"[2] active 规则：{len(rules)} 条（其中 SINGLE_DOC {n_single} 条）")
    print()

    # 3. 零交集规则（高危静默失效，SINGLE_DOC 视角）
    #    声明 '*' 通配的规则单独归类：铁律类全局约束不走 doc_type 精确匹配，
    #    混进零交集清单会误导排查方向
    single_rules = [r for r in rules if r.scope == "SINGLE_DOC"]
    zero_rules = []
    wildcard_rules = []
    for r in single_rules:
        trig = (getattr(r, "trigger_when", None) or {})
        declared = [d for d in (trig.get("doc_type") or []) if d]
        if not declared:
            continue  # 无 doc_type 触发词的规则走其他触发方式，不在本扫描范围
        if "*" in declared:
            wildcard_rules.append((r.rule_id, r.name))
            continue
        matched = [d for d in prod if match_rule_doc_type(r, d)]
        if prod and not matched:
            zero_rules.append((r.rule_id, r.name, declared))
    print(f"[3] 零交集规则（声明了具体 doc_type 但生产一种都产不出 → 永不执行）："
          f"{len(zero_rules)} 条")
    for rid, name, declared in zero_rules:
        print(f"      ⚠ {rid}  {name}")
        print(f"         声明: {declared}")
    print(f"    （另有 {len(wildcard_rules)} 条声明 '*' 通配的全局规则，"
          f"按引擎语义另行核查，不计入零交集）")
    print()

    # 4. 生产覆盖缺口（v10.5 修正：与审核运行时 build_unguarded_doc_types 同口径，
    #    SINGLE_DOC/CROSS_DOC/CROSS_UNIT 任一命中即算覆盖。旧版只看 SINGLE_DOC，
    #    把 CROSS 类兜底的类型（如施工日志被 CU-009/011 联动）误报成缺口）
    gaps = []
    if rules and prod:
        # 用真实份数构造虚拟 docs（每种类型 doc_count 才准，不是恒 1）
        prod_docs = []
        for i, (dt, n) in enumerate(prod.items()):
            prod_docs.extend(
                {"id": f"SCAN-{i}-{j}", "doc_type": dt}
                for j in range(n)
            )
        for u in build_unguarded_doc_types(rules, prod_docs):
            gaps.append((u["doc_type"], u["doc_count"]))
    print(f"[4] 生产覆盖缺口（真实 doc_type 无任何 active 规则覆盖——"
          f"SINGLE_DOC/CROSS_DOC/CROSS_UNIT 全维度判定）："
          f"{len(gaps)} 种")
    for dt, n in sorted(gaps, key=lambda kv: -kv[1]):
        print(f"      ⚠ {n:>3} 份  {dt}")
    print()

    # 5. 每条规则命中的生产文档数（SINGLE_DOC 视角；通配 '*' 规则已单独归类，此处跳过）
    print("[5] SINGLE_DOC 规则命中生产文档数（matched ≥1 才真正在干活）：")
    for r in single_rules:
        trig = (getattr(r, "trigger_when", None) or {})
        declared = [d for d in (trig.get("doc_type") or []) if d]
        if not declared or "*" in declared:
            continue
        docs = [d for d in prod if match_rule_doc_type(r, d)]
        total = sum(prod[d] for d in docs)
        flag = "" if total else "  ← 0 匹配"
        print(f"      {r.rule_id:<8} {total:>4} 份文档{flag}")

    print()
    print("=" * 60)
    print(f"扫描完成：零交集规则 {len(zero_rules)} 条，"
          f"生产覆盖缺口 {len(gaps)} 种")
    print("提示：零交集规则应核对 trigger_when.doc_type 是否写错/过窄；")
    print("      覆盖缺口 doc_type 若是常见资料类型，考虑补通用规则。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
