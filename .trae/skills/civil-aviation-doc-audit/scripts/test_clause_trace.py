# -*- coding: utf-8 -*-
"""
A4 溯源测试：审核规则引用的规范条款号，必须在条款总索引 clause_index.json 中反查命中。
铁律：引用溯源必须可验证，找不到的条款号标 ⚠️ 疑似，不得硬编。此测试永久防幻觉。

用法：
    python scripts/test_clause_trace.py        # 直接运行，失败退出码 1
    pytest scripts/test_clause_trace.py -v     # 并入 pytest 套件
"""
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
CFG = SKILL_DIR / "scripts" / "audit_config.py"
INDEX = SKILL_DIR / "data" / "regulations" / "clause_index" / "clause_index.json"
CATALOG_JSON = SKILL_DIR / "data" / "regulations" / "catalog_index.json"
CATALOG_MD = SKILL_DIR / "references" / "specification-catalog.md"
SOURCES_CLEAN = SKILL_DIR / "data" / "regulations" / "sources_clean"

# 加载 audit_config（含各清单）
sys.path.insert(0, str(SCRIPT_DIR))
import audit_config as cfg  # noqa: E402


def load_index():
    with open(INDEX, encoding="utf-8") as f:
        return json.load(f)["by_file"]
    # by_file: {filename: {"clauses": {num: {...}}, "chapters": {...}}}


def collect_rule_specs():
    """收集所有含条款号的规则 spec。spec 格式形如 'MH/T 5078.1 第5.0.4条'、
    'MH/T 5078.2 第6.1.1条'、'附录A'；不含条款号的（如 'MH/T 5078.2 + MH 5007'、
    'MH/T 5078.2-2024'）暂不判定。"""
    spec_lists = {
        "GENERAL_CHECKLIST": cfg.GENERAL_CHECKLIST,
        "AIRFIELD_CHECKLIST": getattr(cfg, "AIRFIELD_CHECKLIST", []),
        "ATC_CHECKLIST": getattr(cfg, "ATC_CHECKLIST", []),
        "VISUAL_AIDS_CHECKLIST": getattr(cfg, "VISUAL_AIDS_CHECKLIST", []),
        "WEAK_ELECTRICITY_CHECKLIST": getattr(cfg, "WEAK_ELECTRICITY_CHECKLIST", []),
        "FUEL_SUPPLY_CHECKLIST": getattr(cfg, "FUEL_SUPPLY_CHECKLIST", []),
    }
    lists = [lst for _name, lst in spec_lists.items()]
    specs = {}
    for lst in lists:
        for r in lst:
            for part in str(r.get("spec", "")).split("+"):
                part = part.strip()
                m = re.search(r"([A-Z]{1,3}(\s?/T)?\s?(\d+)(\.\d+)*)(?:-20\d\d)?\s*(第[\d.]+条|附录[A-Z])", part)
                if m:
                    spec_num = m.group(1).replace(" ", "")
                    clause = (m.group(5) or "").replace("第", "").replace("条", "")
                    specs.setdefault(spec_num, set()).add(clause)
    return specs


def resolve_spec_file(spec_num):
    """按精确规范号在 by_file 的 key 里定位文件。
    处理可能命中多分部（5078.1 vs 5078.10）的歧义：用正则锚定。"""
    # spec_num 形如 "MH/T5078.1"；key 是全文件名
    digits = re.search(r"(\d+(?:\.\d+)*)", spec_num)
    core = ".".join(digits.group(1).split(".")[:2])  # 保留分部号如 5078.1
    pat = re.compile(r"(?<!\d)" + re.escape(core) + r"(?!\d)")
    return [k for k in index if pat.search(k)]


index = load_index()
RULE_SPECS = collect_rule_specs()


def test_all_clause_refs_resolve():
    """每条含条款号的 spec 必须能在总索引中反查到对应文件+条款。"""
    failures = []
    for spec_num, clauses in sorted(RULE_SPECS.items()):
        files = resolve_spec_file(spec_num)
        if not files:
            failures.append(f"规范 [{spec_num}] 未在索引定位到文件")
            continue
        for cl in sorted(clauses):
            hit = False
            for f in files:
                rec = index.get(f, {}).get("clauses", {}).get(cl)
                if rec:
                    hit = True
                    break
            if not hit:
                failures.append(f"[{spec_num}] 第{cl}条 未在 [{', '.join(files)}] 中找到原文，疑似幻觉")
    assert not failures, "\n" + "\n".join(failures)


# ---- B 提速：条款索引缓存（缓存生效 + mtime 失效重载） ----

# 专业清单 ↔ 分部分项树 映射
PRO_CHECKLIST_TREE = {
    "AIRFIELD_CHECKLIST": "01_场道工程",
    "ATC_CHECKLIST": "02_空管工程",
    "VISUAL_AIDS_CHECKLIST": "03_助航灯光工程",
    "WEAK_ELECTRICITY_CHECKLIST": "04_弱电工程",
    "FUEL_SUPPLY_CHECKLIST": "05_供油工程",
}


def test_checklist_vs_hierarchy():
    """五专业专项清单 code 必须与 SUBDIVISION_HIERARCHY 分项 code 一一对应。
    防错位：树里有清单缺、清单里多出来的 code 都会报错。"""
    failures = []
    tree = cfg.SUBDIVISION_HIERARCHY
    for chk_name, prof in PRO_CHECKLIST_TREE.items():
        checklist = getattr(cfg, chk_name, [])
        tree_codes = set(
            item["code"]
            for sub in tree.get(prof, {}).get("sub_items", {}).values()
            for item in sub.get("items", [])
        )
        chk_codes = {r["id"] for r in checklist}
        only_tree = tree_codes - chk_codes
        only_chk = chk_codes - tree_codes
        if only_tree or only_chk:
            failures.append(
                f"{chk_name}({prof}) 与分项树不一致："
                f"缺在清单={sorted(only_tree)} 清单多出={sorted(only_chk)}"
            )
    assert not failures, "\n" + "\n".join(failures)


def test_clause_from_query_parses():
    from lookup_source import _clause_from_query
    assert _clause_from_query("MH/T 5078.1 第5.0.4条") == "5.0.4"
    # 规范号 5078.1 不得被误判为条款（仅第X条才认）
    assert _clause_from_query("MH/T 5078.1") is None
    assert _clause_from_query("") is None


def test_load_clause_index_memoizes_and_invalidates(tmp_path, monkeypatch):
    from lookup_source import _load_clause_index, _clause_cache
    idx_dir = tmp_path / "clause_index"
    idx_dir.mkdir()
    idx_file = idx_dir / "clause_index.json"
    # 需构造 vault_dir.parent/clause_index/clause_index.json
    vault = tmp_path / "sources_clean"
    vault.mkdir()
    import json as _json
    idx_file.write_text(_json.dumps({"by_file": {"X": {"clauses": {"5.0.4": {"text": "t1"}}}}}), encoding="utf-8")
    _clause_cache.update(path=None, mtime=None, by_file=None)  # 重置为默认结构，避免 KeyError
    d1 = _load_clause_index(vault)
    assert d1 == {"X": {"clauses": {"5.0.4": {"text": "t1"}}}}
    # 未改动 → 命中缓存（mtime 相同）
    d2 = _load_clause_index(vault)
    assert d2 is d1  # 同一对象 = 缓存生效
    # 改动文件 → mtime 变化 → 重载
    import time
    time.sleep(0.01)
    idx_file.write_text(_json.dumps({"by_file": {"X": {"clauses": {"5.0.4": {"text": "t2"}}}}}), encoding="utf-8")
    d3 = _load_clause_index(vault)
    assert d3 is not d1  # 已失效重载
    assert d3["X"]["clauses"]["5.0.4"]["text"] == "t2"


def test_catalog_consistency():
    """防倒退：规范知识库目录必须与库现状一致（D 新增）。
    1) sources_clean 与 clause_index 篇目一一对应
    2) catalog_index.json 覆盖全部 sources_clean 文件
    3) 被锚定的主控规范，catalog 里都能定位到原文文件且标 anchored=true
    4) catalog_index.json 与 specification-catalog.md 均已生成非空"""
    import json as _j

    # 4) 目录双产物存在且非空
    assert CATALOG_JSON.exists(), "缺 catalog_index.json，请运行 build_regulation_catalog.py"
    assert CATALOG_MD.exists(), "缺 specification-catalog.md，请运行 build_regulation_catalog.py"
    assert CATALOG_JSON.stat().st_size > 0 and CATALOG_MD.stat().st_size > 0

    src = set(f.stem for f in SOURCES_CLEAN.glob("*.md"))
    idx = set(index.keys())
    # 1) 清洗篇目 与 条款索引 一一对应
    assert src == idx, (
        f"sources_clean({len(src)}) 与 clause_index({len(idx)}) 不一致："
        f"仅清洗={sorted(src - idx)} 仅索引={sorted(idx - src)}")

    catalog = _j.loads(CATALOG_JSON.read_text(encoding="utf-8"))["by_file"]
    # 2) 目录覆盖全部文件
    assert set(catalog.keys()) == src, (
        f"catalog({len(catalog)}) 未覆盖 sources_clean({len(src)})："
        f"目录缺={sorted(src - set(catalog))}")

    # 3) 每条锚定规范在目录+索引中都可回源
    failures = []
    for spec_num, clauses in sorted(RULE_SPECS.items()):
        for cl in clauses:
            files = resolve_spec_file(spec_num)
            for f in files:
                if f not in catalog:
                    failures.append(f"锚定规范 [{f}] 未在 catalog")
                    continue
                assert catalog[f]["anchored"], f"catalog[{f}] anchored 应为 True 实为 False"
    assert not failures, "\n".join(failures)


def test_catalog_lookup_by_name():
    """D：目录检索——写错规范号/只记得书名时能定位到原文。"""
    from lookup_source import catalog_lookup
    row = catalog_lookup("高填方")
    assert row is not None and "高填方" in row["title"], f"按书名'高填方'未定位: {row}"
    row = catalog_lookup("助航")
    assert row is not None, "按专业'助航'未定位"
    row = catalog_lookup("MH-T5078.2")
    assert row is not None and row.get("core") == "5078.2", f"按规范号未精确定位: {row}"
    row = catalog_lookup("不存在的规范名xyzzy")
    assert row is None, f"无关联想应返回 None, 实际: {row}"


if __name__ == "__main__":
    try:
        test_all_clause_refs_resolve()
        test_checklist_vs_hierarchy()
        test_clause_from_query_parses()
        test_catalog_consistency()
        test_catalog_lookup_by_name()
    except AssertionError as e:
        print("❌ 溯源失败：")
        print(str(e))
        sys.exit(1)
    print(f"✅ 溯源通过：{sum(len(v) for v in RULE_SPECS.values())} 条条款引用全部可溯源")
    sys.exit(0)