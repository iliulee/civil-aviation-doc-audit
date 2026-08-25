#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""全文检索增强器 retriever —— 把「规范全文里的关键词定位」从粗匹配提升为可排序的确定性检索。

对应 检索提效(C) 的设计：
  - 轻量分词：英文/数字 token（规范号）+ 连续中文词，不引入 jieba（避免新增依赖）
  - 标题（文件名）加权：命中文件名/规范号得分最高
  - 两级排序 + RRF 融合：文件名命中序 + 正文词频序，按 Reciprocal Rank Fusion 汇总，
    再确定性降序返回，替代原先「任一子串命中即取第一个」的粗匹配
  - 条款正则抽取：对命中文档定位目标条款号，供回源 s/quote

纯函数、可独立测试；本模块不联网、不依赖 Obsidian 进程。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

# 英文/数字词：规范号（MH/T 5078.1）、数字条款（5.2.3）
# 规范号词允许字母+数字整体连读（尾部分隔位 1-4 位，避免把 -9999 切成短数字）
_TOKEN_ALNUM = re.compile(r"[A-Za-z]{1,6}\d{3,4}(?:[.\-]\d{1,4})*|\d{1,3}(?:\.\d{1,2}){0,2}")
# 连续中文词：2 字及以上连续汉字串（粗切，不做语义分词）
_TOKEN_CJK = re.compile(r"[\u4e00-\u9fff]{2,}")
# 条款正则：章/条/条编号
CLAUSE_RE = re.compile(r"(?P<clause>\d{1,2}(?:\.\d{1,3}){1,2})\s*(条|章)")


def tokenize(text: str) -> List[str]:
    """轻量分词：英文/数字 + 连续中文词，去重保序。

    丢弃过短的孤立纯数字 token（如 "99"/"5"），避免数字噪声放大误命中；
    规范号词（含字母前缀）与条款号（含小数点）不受此限。
    """
    out: List[str] = []
    if text:
        for m in _TOKEN_ALNUM.findall(text):
            t = m.strip()
            if not t or t in out:
                continue
            if re.fullmatch(r"\d+", t) and len(t) < 3:
                continue  # 孤立短数字噪声
            out.append(t)
        for m in _TOKEN_CJK.findall(text):
            t = m.strip()
            if not t:
                continue
            if len(t) <= 6:
                if t not in out:
                    out.append(t)
                continue
            # 长中文串做 2/3 字滑窗切词，命中"土石方""道面""垫层"等规范实词
            for w in (2, 3):
                for i in range(len(t) - w + 1):
                    sub = t[i:i + w]
                    if sub not in out:
                        out.append(sub)
    return out


def spec_core_num(text: str) -> str:
    """提取规范号核心数字段（MH/T 5078.1 → 5078），用于文件名强匹配。"""
    m = re.search(r"[A-Za-z]{1,6}[\\-/]?\s*\d{3,4}(?:\.\d{1,2})*", text)
    if m:
        n = re.search(r"\d{3,4}", m.group(0))
        if n:
            return n.group(0)
    return ""


def extract_clauses(text: str) -> List[str]:
    """抽出文档中出现过的「第 X.Y.Z 条/章」条款号（去重保序）。"""
    out: List[str] = []
    for m in CLAUSE_RE.finditer(text):
        c = m.group("clause")
        if c not in out:
            out.append(c)
    return out


def _filename_tokens(stem: str) -> List[str]:
    """文件名的 token：去掉 .md，转小写按非字母数字切分。"""
    toks = re.split(r"[^A-Za-z\u4e00-\u9fff0-9]+", stem.lower())
    return [t for t in toks if t]


def _rank_by_filename(query_toks: List[str], files: List[Path]) -> List[Path]:
    """按文件名命中度排序：命中 query 词越多越靠前（标题加权）。"""
    qn = [_t for _t in query_toks if re.fullmatch(r"[A-Za-z0-9.\-]+", _t)]
    scored = []
    for f in files:
        ftoks = _filename_tokens(f.stem)
        score = 0
        for t in qn:
            if t in f.name:
                score += 3  # 规范号等数字段命中文件名，权重最高
            elif t in ftoks:
                score += 2
        if score > 0:  # 只保留实际命中文件名的文档，防无关文档掺入
            scored.append((score, f))
    scored.sort(key=lambda x: (-x[0], str(x[1])))
    return [f for _, f in scored]


def _rank_by_body(query_toks: List[str], files: List[Path]) -> List[Path]:
    """按正文词频排序：query 词在正文累计出现次数（TF 近似）。"""
    scored = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        score = 0
        for t in query_toks:
            score += text.lower().count(t.lower())
        if score > 0:  # 只保留正文实际命中文档
            scored.append((score, f))
    scored.sort(key=lambda x: (-x[0], str(x[1])))
    return [f for _, f in scored]


def _rrf_fuse(rankings: List[List[Path]], k: int = 60) -> List[Tuple[Path, float]]:
    """Reciprocal Rank Fusion：汇总多个排序，返回 (doc, rrf_score) 降序。"""
    doc_to_rank: dict = {}
    for ranking in rankings:
        for rank, f in enumerate(ranking):
            scores = doc_to_rank.setdefault(f, 0.0)
            # RRF: 1/(k + rank+1)；无命中排名（pos 靠后但仍计入）不 k 饱和
            scores += 1.0 / (k + rank + 1)
            doc_to_rank[f] = scores
    fused = sorted(doc_to_rank.items(), key=lambda x: (-x[1], str(x[0])))
    return fused


def retrieve_fulltext(query: str, vd: Path, top_k: int = 3,
                      include_all_scored: bool = True) -> List[Tuple[Path, float]]:
    """全文检索：文件名/规范号命中 + 正文词频，RRF 融合后确定性返回 Top-K。

    返回 [(Path, rrf_score), ...]，score>0 说明 query 至少有一个 token 命中；
    score 仅用于排序的相对比较，不代表绝对相关度。
    """
    q_toks = tokenize(query)
    if not q_toks or vd is None or not vd.is_dir():
        return []

    md_files = sorted([f for f in vd.glob("*.md") if f.is_file()])
    if not md_files:
        return []

    # 两级排序
    by_name = _rank_by_filename(q_toks, md_files)
    by_body = _rank_by_body(q_toks, md_files)

    fused = _rrf_fuse([by_name, by_body])
    return fused[:top_k]


def best_hit(query: str, vd: Path) -> Tuple[Path, float, List[str]]:
    """返回 (最优文档, rrf_score, 该文档条款号列表)；无命中返回 (None, 0.0, [])。"""
    if not vd or not vd.is_dir():
        return None, 0.0, []
    fused = retrieve_fulltext(query, vd, top_k=1)
    if not fused:
        return None, 0.0, []
    doc, score = fused[0]
    try:
        txt = doc.read_text(encoding="utf-8", errors="ignore")
        clauses = extract_clauses(txt)
    except Exception:
        clauses = []
    return doc, score, clauses


if __name__ == "__main__":
    import sys
    vd = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"H:\Obsidian notes\溜哥笔记\wiki\sources")
    for q in ["施工日志", "建筑信息模型 MH-T5073", "碎石桩"]:
        res = retrieve_fulltext(q, vd, top_k=3)
        print(f"query={q!r}")
        for f, s in res:
            print(f"   {s:6.3f}  {f.name}")