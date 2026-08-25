#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""依据查找工具 lookup_source —— 把「查规范找依据」从 AI 自觉变成机制强制。

对应 依据查询机制_方案设计.md：
  ① references 命中 → source="references"
  ② obsidian 兜底   → source="obsidian"
  ③ 依据缺失       → source="missing"，found=False
  ④ 来源留痕       → 每命中带 file / spec / clause / snippet / searched_at

防幻觉铁律：本模块只读 references/ + 规范全文目录（本地），绝不联网搜索或发送网络请求。
不再依赖 Obsidian 进程 —— 规范全文直接按本地文件读取（包内 data/regulations 优先，
回落本地 Obsidian vault 存量路径），Obsidian 未启动也能读全文。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# 全文检索增强（C）：标题加权 / RRF 融合 / 条款提取
from retriever import best_hit as _retriever_best_hit
from retriever import spec_core_num as _retriever_spec_core

# 规范全文目录（可被调用方覆盖）
# 优先级：包内清洗版 sources_clean（A1 产出，带章节/条款结构化，可反查条款原文）
#  > 包内原始 sources（随 skill 打包，同事免装 Obsidian）
#  > 本地 Obsidian vault（改动前的路径，兼容存量环境）。
_DEFAULT_VAULT_DIR = Path(r"H:\Obsidian notes\溜哥笔记\wiki\sources")
_PACKAGE_SOURCES_DIR = Path(__file__).resolve().parent.parent / "data" / "regulations" / "sources"
_PACKAGE_SOURCES_CLEAN_DIR = Path(__file__).resolve().parent.parent / "data" / "regulations" / "sources_clean"


def resolve_vault_dir(vault_dir: Optional[str] = None) -> Optional[Path]:
    """解析规范全文目录：显式传入 > 包内清洗版 > 包内原始版 > 本地 Obsidian 存量路径。

    返回 None 表示当前环境没有任何规范全文目录可用（lookup 将走 missing）。

    清洗版（sources_clean）优先：其条款以 `**5.0.4**　正文` 结构展开，
    使 `_clause_snippet` 能逐字命中具体条款原文，支撑报告「深化到具体条款」。
    若清洗版缺失（如全新环境尚未跑 A1 清洗），自动回落原始 sources。
    """
    if vault_dir:
        p = Path(vault_dir)
        return p if p.is_dir() else None
    for cand in (_PACKAGE_SOURCES_CLEAN_DIR, _PACKAGE_SOURCES_DIR, _DEFAULT_VAULT_DIR):
        if cand.is_dir():
            return cand
    return None


# 兼容外部引用（保持 DEFAULT_VAULT_DIR 名称语义不变）
DEFAULT_VAULT_DIR = _DEFAULT_VAULT_DIR

# 规范号正则：MH/T 5078.1-2024 / MH-T5078.1 / JGJ 120 / GB 50007 / CCAR-165-R1
_SPEC_RE = re.compile(
    r"(?P<prefix>[A-Z]{1,4})\s*[-/]?\s*(?P<sub>[A-Z]{0,2})\s*"
    r"(?P<num>\d{3,4}(?:\.\d{1,2})*)"
    r"(?:\s*[-/]\s*(?P<year>\d{4}))?",
    re.IGNORECASE,
)
# 条款号正则：第 5.2.3 条 / 5.2.3 / 第 6 章
_CLAUSE_RE = re.compile(r"(第\s*)?(?P<clause>\d+(?:\.\d+){0,2})\s*(条|章)?")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _empty_hit() -> Dict:
    return {
        "found": False,
        "source": "missing",
        "spec": "",
        "clause": "",
        "snippet": "",
        "file": "",
        "quality": "low",
        "searched_at": _now(),
    }


# ============ references 层 ============

def _extract_specs(text: str) -> List[str]:
    """从一行文本提取所有规范号（保留原始写法）。"""
    specs = []
    for m in _SPEC_RE.finditer(text):
        prefix = m.group("prefix")
        sub = m.group("sub") or ""
        num = m.group("num")
        year = m.group("year")
        joined = f"{prefix}/{sub}{num}" if sub else f"{prefix}/{num}"
        joined = joined.replace("//", "/")
        if year:
            joined = f"{joined}-{year}"
        specs.append(joined)
    return specs


def _split_bare_spec(query: str) -> str:
    """把查询串里的规范号转成紧凑形式用于比对。"""
    for m in _SPEC_RE.finditer(query):
        prefix = m.group("prefix")
        num = m.group("num")
        return f"{prefix}{num}".upper().replace("MH", "MH").replace("/", "").replace(".", "")
    return query


def _refs_index(references_dir: Optional[str]) -> List[Dict]:
    """解析 references 下 md 表格行，构建 (关键词, spec, clause) 索引。"""
    refs_dir = Path(references_dir) if references_dir else None
    if not refs_dir or not refs_dir.is_dir():
        return []
    index = []
    for md in sorted(refs_dir.glob("*.md")):
        try:
            lines = md.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in lines:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 3:
                continue
            # 取资料类型/主题列 + 规范列
            keyword = cols[0]
            spec_cell = cols[1]
            clause_cell = cols[2] if len(cols) > 2 else ""
            if not keyword or keyword in ("资料类型", "主题", "运算类型", "通用管理"):
                continue
            for spec in _extract_specs(spec_cell):
                index.append({
                    "keyword": keyword,
                    "spec": spec,
                    "clause": clause_cell,
                    "file": str(md),
                })
    # 结构化术语表（classification-terms.json）补充关键词
    jf = refs_dir / "classification-terms.json"
    if jf.exists():
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            for term in data.get("terms", {}).values():
                for core in term.get("core", []):
                    index.append({"keyword": core, "spec": "", "clause": "", "file": str(jf)})
        except Exception:
            pass
    return index


def _search_references(query: str, content_snippet: str, references_dir: Optional[str]) -> Optional[Dict]:
    """references 层：按规范号或关键词命中，返回命中或 None。"""
    index = _refs_index(references_dir)
    if not index:
        return None
    # 1) 规范号精确/紧凑匹配
    bare = _split_bare_spec(query)
    for item in index:
        item_bare = _split_bare_spec(item["spec"])
        if bare and item_bare and bare in item_bare:
            return {
                "found": True,
                "source": "references",
                "spec": item["spec"] or bare,
                "clause": item["clause"],
                "snippet": f"references 索引：类型[{item['keyword']}] 适用规范[{item['spec']}] {item['clause']}",
                "file": item["file"],
                "quality": "medium",
                "searched_at": _now(),
            }
    # 2) 关键词匹配（query 或 content_snippet 命中资料类型）
    probes = [query, content_snippet]
    for item in index:
        if not item["keyword"]:
            continue
        if any(item["keyword"] in p for p in probes if p):
            return {
                "found": True,
                "source": "references",
                "spec": item["spec"],
                "clause": item["clause"],
                "snippet": f"references 索引：类型[{item['keyword']}] 适用规范[{item['spec']}] {item['clause']}",
                "file": item["file"],
                "quality": "medium",
                "searched_at": _now(),
            }
    return None


# ============ obsidian 层（规范全文目录） ============

def _spec_core(query: str) -> str:
    """提取规范号数字段（保留分部号），用于文件名 glob（如 MH-T5078.2-2024 → 5078.2）。

    多部分规范必须携带分部号，否则 glob 定位时会把 5078.2~6 误归到 5078.1。
    例：MH-T5078.2-2024 → num="5078.2"，不得截断成 "5078"。
    """
    for m in _SPEC_RE.finditer(query):
        return m.group("num")
    return ""


def _stem_has_exact_spec(stem: str, core: str) -> bool:
    """文件名中是否存在与 core 完全相等的规范号数字段。

    防子串歧义：5078.2 不得误配 5078.20 / 5078.2x；5078 不得误配 5078.1。
    用 _SPEC_RE 提取规范号时保留分部号，逐段全等比较。
    """
    return any(m.group("num") == core for m in _SPEC_RE.finditer(stem))


def _glob_vault(query: str, vault_dir: Optional[str]) -> Optional[Path]:
    """glob 兜底：按规范号（含分部号）在规范目录文件名中定位（规避 search 多词失配）。

    多部分规范按完整分部号精确匹配（5078.2 → *5078.2*），且用 _stem_has_exact_spec
    全等校验，杜绝子串歧义（不把 5078.2 配到 5078.20）。若查询带分部号但对应分部
    文件缺失，直接返回 None（回落 miss / retriever），**绝不静默回退错定到其他分部**。
    """
    vd = resolve_vault_dir(vault_dir)
    if vd is None:
        return None
    core = _spec_core(query)
    if not core:
        return None

    has_part = "." in core
    # 完整规范号（含分部点）glob，命中后全等校验
    for f in sorted(vd.glob(f"*{core}*")):
        if f.is_file() and f.suffix.lower() == ".md" and _stem_has_exact_spec(f.stem, core):
            return f
    # 非分部查询（core 无点）且上述未命中 → 再试宽松一次（个别文件名不带 `MH-T` 前缀）
    if not has_part:
        base = core
        for f in sorted(vd.glob(f"*{core}*")):
            if f.is_file() and f.suffix.lower() == ".md":
                return f
    # 带分部查询未命中 → 分部缺失，不得回退错配，返回 None 走 missing / retriever
    return None


def _read_text_direct(path: str) -> str:
    """直接读本地文件全文（替代 obsidian read CLI，无需 Obsidian 进程）。"""
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


# ---- B 提速：条款索引内存缓存（A2 clause_index.json） ----
# 启动/首次命中时加载一次，后续靠 mtime 失效自动重载，避免逐条 glob 大规范文件。
_clause_cache = {"path": None, "mtime": None, "by_file": None}


def _load_clause_index(vault_dir: Path):
    """加载 clause_index.json 并做 mtime 失效缓存。

    返回 by_file 结构或 None（索引缺失/解析失败）。
    """
    idx_path = vault_dir.parent / "clause_index" / "clause_index.json"
    try:
        mt = idx_path.stat().st_mtime_ns
    except OSError:
        _clause_cache.update(path=None, mtime=None, by_file=None)
        return None
    c = _clause_cache
    if c["path"] == idx_path and c["mtime"] == mt:
        return c["by_file"]
    if not idx_path.exists():
        c.update(path=None, mtime=None, by_file=None)
        return None
    try:
        data = json.loads(idx_path.read_text(encoding="utf-8")).get("by_file", {})
    except Exception:
        return None
    c.update(path=idx_path, mtime=mt, by_file=data)
    return data


# ---- C：规范知识库目录（catalog_index.json）按书名/专业定位 ----
# 由 build_regulation_catalog.py 生成。用于「不知道规范号、只记得书名/专业」时的快速定位，
# 结果仍回源到对应原文文件（找文件靠文件名匹配，与 _glob_vault 一致）。
_def_catalog_path = None  # 测试可注入


def _catalog_by_file():
    """加载 catalog_index.json（mtime 缓存失效机制同 clause_index）。"""
    global _def_catalog_path
    path = _def_catalog_path or (
        Path(__file__).resolve().parent.parent / "data" / "regulations" / "catalog_index.json")
    try:
        mt = path.stat().st_mtime_ns
    except OSError:
        return {}
    return _catalog_data(path, mt)


_catalog_cache = {"path": None, "mtime": None, "data": None}


def _catalog_data(path: Path, mt: int) -> dict:
    c = _catalog_cache
    if c["path"] == path and c["mtime"] == mt:
        return c["data"] or {}
    try:
        data = json.loads(path.read_text(encoding="utf-8")).get("by_file", {})
    except Exception:
        data = {}
    c.update(path=path, mtime=mt, data=data)
    return data


def catalog_lookup(query: str) -> Optional[Dict]:
    """按书名/专业名在规范目录中定位。返回 (filename, title, spec) 或 None。

    命中策略（防误配）：
      - 规范号（含分部）→ 精确按 spec 全等
      - 书名 → 标题子串（多关键词需全部命中，避免一两个字误配）
      - 专业名 → 目录中该专业列为锚定的主控规范
    """
    if not query:
        return None
    by = _catalog_by_file()
    if not by:
        return None
    q = query.strip()

    # 1) 规范号（数字段含分部）
    core = _spec_core(q)
    if core:
        for row in by.values():
            if row.get("core") == core:
                return row
    # 2) 专业名（场道/空管/助航/弱电/供油/通用）
    if q in {r["pro"] for r in by.values() if r.get("pro")}:
        for row in by.values():
            if row.get("pro") == q and row.get("anchored"):
                return row
    # 3) 书名/关键词（同一行里 query 每个中文词都在标题或 spec 中）
    probe = re.split(r"[，。,;\s/]+", q)
    probe = [p for p in probe if p]
    if probe:
        for row in by.values():
            hay = row.get("title", "") + row.get("spec", "")
            if all(p in hay for p in probe):
                return row
    return None


# 条款号正则：只认「第5.0.4条」这类显式条款，避免把规范号 5078.1 误当条款
_CLSPEC_RE = re.compile(r"第\s*(?P<c>\d+(?:\.\d+){1,2})\s*条")


def _clause_from_query(query: str):
    """从查询串提取显式条款号（仅第X条）；无则 None。"""
    m = _CLSPEC_RE.search(query or "")
    return m.group("c") if m else None


def _clause_snippet(text: str, probe: str) -> str:
    """从原文提取目标条款所在段落，截取可逐字引用的 snippet。"""
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # 找含条款号的行
    for i, ln in enumerate(lines):
        if _CLAUSE_RE.search(ln) and (probe and any(k in ln for k in probe.split())):
            return " ".join(lines[i : i + 2])[:200]
    # 找含关键词的行
    if probe:
        for ln in lines:
            if any(k in ln for k in probe.split()):
                return ln[:200]
    return " ".join(lines[:3])[:200]


def _search_obsidian(query: str, content_snippet: str, vault_dir: Optional[str]) -> Optional[Dict]:
    """obsidian 层：glob 文件名 → 本地全文关键词兜底 → 直接读原文（全程不依赖 Obsidian 进程）。"""
    vd = resolve_vault_dir(vault_dir)
    if vd is None:
        return None
    # 1) glob 文件名兜底（最准）
    f = _glob_vault(query, vault_dir)
    if f is not None:
        spec = " ".join(f.stem.split("-")[1:-1]) if "-" in f.stem else f.stem
        # B 提速：带显式条款号 → 从内存索引直接取条款原文，跳过读大文件
        clause = _clause_from_query(query)
        snippet = ""
        if clause and vd is not None:
            idx = _load_clause_index(vd)
            if idx:
                rec = idx.get(f.name, {}).get("clauses", {}).get(clause)
                if rec:
                    snippet = rec.get("text", "")
        raw = snippet or _read_text_direct(str(f))
        if not snippet:
            snippet = _clause_snippet(raw, content_snippet or query)
        return {
            "found": True,
            "source": "obsidian",
            "spec": spec,
            "clause": clause or "",
            "snippet": snippet or f"obsidian 原文文件：{f.name}",
            "file": str(f),
            "quality": "high",
            "searched_at": _now(),
        }
    # 2) 全文关键词检索（C：标题加权 + RRF 融合 + 条款提取，确定性命中而非粗取首个）
    probe = content_snippet or query
    doc, score, clauses = _retriever_best_hit(probe, vd)
    if doc is not None and score > 0:
        raw = _read_text_direct(str(doc))
        snippet = _clause_snippet(raw, probe)
        return {
            "found": True,
            "source": "obsidian",
            "spec": " ".join(doc.stem.split("-")[1:-1]) if "-" in doc.stem else doc.stem,
            "clause": "、".join(clauses[:3]) or "",
            "snippet": snippet or f"obsidian 全文命中：{doc.name}",
            "file": str(doc),
            "quality": "medium",
            "searched_at": _now(),
        }
    return None


# ============ 主入口 ============

def _attach_references_check(hit: Dict, references_dir: Optional[str],
                             vault_dir: Optional[str]) -> None:
    """references 命中后的回源核对：用命中的规范号在全文目录定位原文文件。

    附加字段：
      verified      True=回源到规范原文；False=references 仅供索引，无原文背书
      verified_file 回源命中的规范原文文件路径（无则空串）
    让消费方（review_audit/rule_engine）感知 references 依据是否有全文可印证。
    """
    vd = resolve_vault_dir(vault_dir)
    src = hit.get("spec") or ""
    if vd is None:
        hit["verified"], hit["verified_file"] = False, ""
        hit["quality"] = "medium"
        return
    f = _glob_vault(src, str(vd))
    if f is not None:
        hit["verified"], hit["verified_file"] = True, str(f)
        hit["quality"] = "high"
    else:
        hit["verified"], hit["verified_file"] = False, ""
        hit["quality"] = "medium"


def lookup_source(spec_query: str, content_snippet: str = "",
                  references_dir: Optional[str] = None,
                  vault_dir: Optional[str] = None) -> Dict:
    """依据查找：references → obsidian → missing，全程不联网。

    返回 SourceHit：
      found / source(references|obsidian|missing) / spec / clause / snippet / file / searched_at
    """
    if not spec_query and not content_snippet:
        return _empty_hit()
    # ① references 层
    hit = _search_references(spec_query, content_snippet, references_dir)
    if hit:
        _attach_references_check(hit, references_dir, vault_dir)
        return hit
    # ② obsidian 层（规范全文目录）
    hit = _search_obsidian(spec_query, content_snippet, vault_dir)
    if hit:
        return hit
    # ③ 依据缺失
    h = _empty_hit()
    h["searched_at"] = _now()
    return h


if __name__ == "__main__":
    # 快速人工冒烟
    import sys
    refs = str(Path(__file__).parent.parent / "references")
    vault = str(resolve_vault_dir() or DEFAULT_VAULT_DIR)
    for q, c in [("MH/T 5078.1", ""), ("施工日志", ""),
                 ("MH-T5073 建筑信息模型", ""), ("MH-T9999-9999", "")]:
        r = lookup_source(q, c, references_dir=refs, vault_dir=vault)
        print(f"query={q!r} -> found={r['found']} source={r['source']} spec={r['spec']!r} file={r['file']!r}")
    print("--- catalog_lookup ---")
    for q in ["场道", "高填方", "助航", "供油"]:
        print(f"  {q!r} -> {catalog_lookup(q) and catalog_lookup(q)['filename']}")