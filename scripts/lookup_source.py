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
# 优先读包内 data/regulations/sources（随 skill 打包，同事免装 Obsidian）；
# 回落本地 Obsidian vault（改动前的路径，兼容存量环境）。
_DEFAULT_VAULT_DIR = Path(r"H:\Obsidian notes\溜哥笔记\wiki\sources")
_PACKAGE_SOURCES_DIR = Path(__file__).resolve().parent.parent / "data" / "regulations" / "sources"


def resolve_vault_dir(vault_dir: Optional[str] = None) -> Optional[Path]:
    """解析规范全文目录：显式传入 > 包内自带 > 本地 Obsidian 库存量路径。

    返回 None 表示当前环境没有任何规范全文目录可用（lookup 将走 missing）。
    """
    if vault_dir:
        p = Path(vault_dir)
        return p if p.is_dir() else None
    for cand in (_PACKAGE_SOURCES_DIR, _DEFAULT_VAULT_DIR):
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
    """提取规范号核心数字段，用于文件名 glob（如 MH-T5073 → 5073）。"""
    for m in _SPEC_RE.finditer(query):
        return m.group("num").split(".")[0]
    return ""


def _glob_vault(query: str, vault_dir: Optional[str]) -> Optional[Path]:
    """glob 兜底：按规范号核心数字在规范目录文件名中定位（规避 search 多词失配）。"""
    vd = resolve_vault_dir(vault_dir)
    if vd is None:
        return None
    core = _spec_core(query)
    if not core:
        return None
    for f in sorted(vd.glob(f"*{core}*")):
        if f.is_file() and f.suffix.lower() == ".md":
            return f
    return None


def _read_text_direct(path: str) -> str:
    """直接读本地文件全文（替代 obsidian read CLI，无需 Obsidian 进程）。"""
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


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
        raw = _read_text_direct(str(f))
        snippet = _clause_snippet(raw, content_snippet or query)
        return {
            "found": True,
            "source": "obsidian",
            "spec": spec,
            "clause": "",
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