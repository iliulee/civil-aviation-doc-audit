# -*- coding: utf-8 -*-
"""
规范知识库总目录生成器（build_regulation_catalog.py）
=====================================================
从实际扫描 sources_clean + clause_index + audit_config 锚定清单，
自动生成两份规范总目录，永不手工维护、永不漏改：

  1. references/specification-catalog.md    —— 人读目录（按类别/专业分区，可跳转）
  2. data/regulations/catalog_index.json     —— 机读索引（供 lookup_source 快速定位）

每条规范字段：
  filename   原文清洗文件名（sources_clean 下，可跳转定位）
  spec       规范编号（如 MH-T5078.1-2019 / AC-137-CA-2015-01；法规律条无编号则为空）
  title      规范名称
  category   类别前缀：AC/AP/CCAR/IB/MH-T/MH/GB/法规律条
  pro        专业归属（场道/空管/助航/弱电/供油/通用；未锚定时空，表示参考）
  clauses    条款数（X.X.X 点分编号，来自 clause_index；0 表示该篇无可点分条款）
  anchored   是否被审核清单锚定为「主控/可用依据」(True/False)
  granularity 引用粒度：
               X.X.X   有点分条款，可逐字反查 → 引「第X.X.X条」
               第X条    法规律条（无点分编号） → 引「第X条」
               全文/章节 设备/管理规定（无编号） → 引规范名+相关要求

用法：
    python scripts/build_regulation_catalog.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REG_DIR = SKILL_DIR / "data" / "regulations"
VAULT = REG_DIR / "sources_clean"
AGG_INDEX = REG_DIR / "clause_index" / "clause_index.json"
CATALOG_JSON = REG_DIR / "catalog_index.json"
CATALOG_MD = SKILL_DIR / "references" / "specification-catalog.md"

# ---- 专业清单 → 专业名 映射（与 test_clause_trace 保持一致）----
PRO_CHECKLIST_MAP = {
    "GENERAL_CHECKLIST": "通用",
    "AIRFIELD_CHECKLIST": "场道",
    "ATC_CHECKLIST": "空管",
    "VISUAL_AIDS_CHECKLIST": "助航",
    "WEAK_ELECTRICITY_CHECKLIST": "弱电",
    "FUEL_SUPPLY_CHECKLIST": "供油",
}

# 类别前缀 → 中文类别
CATEGORY_LABEL = {
    "AC": "咨询通告 AC",
    "AP": "管理程序 AP",
    "CCAR": "民航规章 CCAR",
    "IB": "信息通告 IB",
    "MH-T": "民航行业标准 MH-T",
    "MH": "民航行业规范 MH",
    "GB": "国家标准 GB",
    "LAW": "法律法规/条令",
}

# 未锚定规范的专业关键词启发（仅作目录浏览辅助，不作审核判定）
_PRO_KEYWORD = {
    "场道": ["场道", "道面", "土方", "排水", "机场工程", "机场飞行区", "机场场道",  # noqa
              "机场道面", "滑行道", "跑道", "机坪", "土石方", "填方", "道面混凝土",
              "民航机场工程"],
    "空管": ["空管", "空中交通", "导航", "航向信标", "下滑信标", "仪表着陆", "雷达",
              "VOR", "DME", "NDB", "ILS", "GBAS", "ADS-B", "通信导航", "航管",
              "监视", "气象"],
    "助航": ["助航", "灯光", "灯具", "风向标", "PAPI", "标记牌", "隔离", "易折",
              "机场灯", "助航设施"],
    "弱电": ["弱电", "信息", "集成", "航显", "离港", "广播", "时钟", "安防",
              "综合布线", "机房", "网络", "楼宇", "会议"],
    "供油": ["供油", "油库", "加油", "加油车", "储油", "输油", "油气回", "油罐",
              "卸油", "机坪加油"],
}


def _load_aggregate_index():
    with open(AGG_INDEX, encoding="utf-8") as f:
        return json.load(f)["by_file"]  # {filename: {clauses:{}, chapters:{}}}


def _collect_anchored_specs(cfg) -> dict:
    """收集所有审核清单 spec 里出现的规范核心号 → {专业: set(核心号)}。
    用于判定篇目是否被锚定、以及其专业归属。"""
    anchored = {}
    for attr, pro in PRO_CHECKLIST_MAP.items():
        lst = getattr(cfg, attr, []) or []
        core_set = set()
        for r in lst:
            core_set.update(_spec_cores_from_spec_field(str(r.get("spec", ""))))
        if core_set:
            anchored[pro] = core_set
    return anchored


def _spec_cores_from_spec_field(spec_field: str) -> set:
    """从 spec 字段提取全部规范核心号（按 '+' 拆分，可能引多个规范）。
    形如 'MH/T 5078.2 第6.1.1条 + MH 5007 第X条' → {'5078.2', '5007'}；
    纯方量/无规范号（如 ''）→ 空集。"""
    cores = set()
    for part in spec_field.split("+"):
        part = part.strip()
        if not part:
            continue
        m = re.search(r"[A-Z]{1,3}(\s?/T)?\s?(\d{3,4}(?:\.\d{1,2})*)(?:-\d{4})?", part)
        if m:
            cores.add(m.group(2))
    return cores


# 规范化核心号：5078.1 与 5078.10 需区分（分部歧义，见 project_memory）
def _norm_core(core: str) -> str:
    return core


def _parse_filename(stem: str) -> dict:
    """解析规范文件名 → {spec, core, category, title}。
    文件名形如：
      '2026-06-15-MH-T5078.1-2019-民用机场…（场道）'
      '2026-06-15-AC-137-CA-2015-01 易折…'
      '2026-06-15-安全生产法'
    """
    body = stem
    # 去掉日期前缀 YYYY-MM-DD-
    m_date = re.match(r"^(\d{4}-\d{2}-\d{2})-(.*)$", body)
    if m_date:
        body = m_date.group(2)

    # 识别规范前缀：AC/AP/CCAR/IB/MH-T/MH-Txx/GB 开头
    m = re.match(
        r"^(AC|AP|CCAR|IB|MH-T|MHT|MH/T|MH|GB)([\- ]?)(.*)$", body, re.IGNORECASE)
    if not m:
        # 无规范号 → 法律法规/条令类
        return {"spec": "", "core": "", "category": "LAW",
                "title": body.strip(" -")}

    raw_prefix = m.group(1).upper()
    rest = m.group(3)

    # 统一前缀：MHT / MH/T → MH-T
    if raw_prefix in ("MHT", "MH/T"):
        raw_prefix = "MH-T"
    elif raw_prefix == "MH":
        # 需区分"MH 5007"(行业规范) 与 "MHT 5087"已进上层
        raw_prefix = "MH"

    if raw_prefix in ("AC", "AP", "CCAR", "IB"):
        # 咨询通告/规章：前缀后直接是编号组，如 AC-137-CA-2015-01
        spec_match = re.match(r"[\- ]?([^\s，。;；]+)", rest)
        spec = (raw_prefix + "-" + spec_match.group(1)) if spec_match else raw_prefix
        core = raw_prefix
        title = rest[spec_match.end():].strip(" -") if spec_match else ""
        return {"spec": spec, "core": core, "category": raw_prefix, "title": title}

    # MH-T / MH / GB：规范号 = 前缀 + 数字+分部(+年份)
    m_num = re.match(r"([\-\s]?)(\d{3,4}(?:\.\d{1,2})*)(?:-(\d{4}))?", rest)
    if not m_num:
        return {"spec": raw_prefix, "core": raw_prefix, "category": raw_prefix,
                "title": rest.strip(" -")}
    spec = raw_prefix + m_num.group(2)
    if m_num.group(3):
        spec += "-" + m_num.group(3)
    core = m_num.group(2)
    title = rest[m_num.end():].strip(" -")
    return {"spec": spec, "core": core, "category": raw_prefix, "title": title}


def _pro_by_keyword(title: str) -> str:
    """未锚定篇目用关键词辅助定专业（仅浏览用）。"""
    for pro, kws in _PRO_KEYWORD.items():
        for kw in kws:
            if kw.lower() in title.lower():
                return pro
    return ""


def _granularity(has_clauses: bool, is_law: bool) -> str:
    """引用粒度判定：有点分条款→X.X.X；条文式法规律→第X条；否则全文/章节。"""
    if has_clauses:
        return "X.X.X"
    if is_law:
        return "第X条"
    return "全文/章节"


_LAW_HINT = ("法", "条例", "规章", "规则", "办法", "细则", "令", "规定", "要求")


def main() -> int:
    sys.path.insert(0, str(SCRIPT_DIR))
    import audit_config as cfg  # noqa: PLC0415

    agg = _load_aggregate_index()
    anchored = _collect_anchored_specs(cfg)

    # 核心号 → 专业集（用于判定锚定篇目的专业）
    core_pro = {}
    for pro, cores in anchored.items():
        for c in cores:
            core_pro.setdefault(c, []).append(pro)

    catalog = []
    for f in VAULT.glob("*.md"):
        stem = f.stem
        rec = agg.get(stem, {"clauses": {}, "chapters": {}})
        n_clauses = len(rec.get("clauses", {}))
        parse = _parse_filename(stem)

        core = parse["core"]
        pros = core_pro.get(core, []) if core else []
        anchored_flag = bool(pros)
        if not anchored_flag:
            kw_pro = _pro_by_keyword(parse["title"])
        else:
            kw_pro = ""

        is_law = parse["category"] == "LAW"
        gran = _granularity(n_clauses > 0, is_law)

        catalog.append({
            "filename": stem,
            "core": core,
            "spec": parse["spec"],
            "title": parse["title"],
            "category": parse["category"],
            "pro": "/".join(dict.fromkeys(pros)) if pros else kw_pro,
            "clauses": n_clauses,
            "anchored": anchored_flag,
            "granularity": gran,
        })

    # 排序：按 类别 → 核心号数字 → 名称
    def sort_key(row):
        core_num = ""
        m = re.search(r"(\d+\.?\d*)", row["core"])
        if m:
            core_num = m.group(1)
        return (CATEGORY_ORDER.index(row["category"]) if row["category"] in CATEGORY_ORDER
                else 99, core_num, row["title"])

    CATEGORY_ORDER = ["MH-T", "MH", "AC", "AP", "CCAR", "IB", "GB", "LAW"]
    catalog.sort(key=sort_key)

    # ---- 机读索引 ----
    top = {
        "_meta": {
            "count_files": len(catalog),
            "count_anchored": sum(1 for r in catalog if r["anchored"]),
            "count_clause_files": sum(1 for r in catalog if r["clauses"] > 0),
            "note": "规范知识库总目录机读索引，由 build_regulation_catalog.py 生成。",
        },
        "by_file": {r["filename"]: r for r in catalog},
    }
    CATALOG_JSON.write_text(
        json.dumps(top, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 机读索引写出 {CATALOG_JSON}（{len(catalog)} 条）")

    # ---- 人读目录 ----
    md = [_md_header(len(catalog), top["_meta"])]
    by_cat: dict = {}
    for r in catalog:
        by_cat.setdefault(r["category"], []).append(r)
    for cat in [c for c in CATEGORY_ORDER if c in by_cat]:
        rows = by_cat[cat]
        md.append(f"\n## {CATEGORY_LABEL[cat]}（{len(rows)} 部）\n")
        md.append("| 规范号 | 名称 | 专业 | 条款 | 锚定 | 引用粒度 |")
        md.append("|--------|------|------|------|------|----------|")
        for r in rows:
            anchored = "✅" if r["anchored"] else "—"
            pro = r["pro"] or "—"
            md.append(
                f"| {r['spec'] or '—'} | {r['title']} | {pro} | "
                f"{r['clauses']} | {anchored} | `{r['granularity']}` |")
    CATALOG_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"✅ 人读目录写出 {CATALOG_MD}")
    print(f"   总数={len(catalog)}  锚定={top['_meta']['count_anchored']}  "
          f"有点分条款={top['_meta']['count_clause_files']}")
    return 0


def _md_header(total: int, meta: dict) -> str:
    return (
        "# 民航规范知识库 · 总目录\n\n"
        f"> 机器生成，勿手工改动。改动规范后运行 "
        f"`python scripts/build_regulation_catalog.py` 重建。\n\n"
        f"- 规范总数：**{total}** 部\n"
        f"- 被审核清单锚定（主控依据）：**{meta['count_anchored']}** 部\n"
        f"- 有点分条款、可逐字反查（引「第X.X.X条」）：**{meta['count_clause_files']}** 部\n"
        f"- 引用粒度三档：`X.X.X`=点分条款可反查 ｜ `第X条`=条文式法规律条 ｜ "
        f"`全文/章节`=设备/管理规定无编号\n"
        f"- 「锚定 ✅」= 该规范被审核清单引用、可直接作审核依据；「—」= 库内参考\n\n"
        f"---"
    )


if __name__ == "__main__":
    sys.exit(main())