#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检索质量回归评估 verify_retrieval —— 用黄金用例集量化 retriever 的检索命中率。

对应 检索提效(E)：
  - 黄金集 = 一组 (query, 期望规范号片段)，来自真实 252 份规范库
  - 断言 P@K：期望规范在 retriever 返回的 Top-K 文件名中出现（默认 K=3）
  - 含一个负例（不存在的规范号），校验检索不产生幻觉命中
  - 输出通过数 / 总数 / P@3

运行：python verify_retrieval.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))
from retriever import retrieve_fulltext  # noqa: E402

VAULT = SCRIPTS.parent / "data" / "regulations" / "sources"

# 黄金集：查询 → 期望命中文件名中含有的规范号片段
GOLD = [
    ("施工日志", "5078.1"),
    ("碎石桩", "5007"),
    ("建筑信息模型 MH-T5073", "5073"),
    ("飞行区排水", "5005"),
    ("水泥混凝土道面", "5004"),
    ("助航灯光", "5079"),
    ("土石方与道面基垫层", "5014"),
    ("沥青道面施工", "5011"),
]
# 负例：不应命中任何规范（防幻觉）
NEGATIVE = "MH-T9999-9999 不存在的规范"

K = 3

passed = 0
failed = 0
print(f"== 检索质量回归评估（P@{K}）== vault={VAULT.resolve()}")
print(f"  正例 {len(GOLD)} 条 / 负例 1 条\n")

if not VAULT.is_dir():
    print(f"[X] 规范库目录不存在: {VAULT}")
    sys.exit(1)

for query, marker in GOLD:
    hits = retrieve_fulltext(query, VAULT, top_k=K)
    names = [f.name for f, _ in hits]
    ok = any(marker in n for n in names)
    if ok:
        passed += 1
        print(f"  [PASS] {query!r} -> 命中 {marker}")
    else:
        failed += 1
        print(f"  [FAIL] {query!r} -> 期望 {marker}，实际 top{K}: {names}")

# 负例
neg_hits = retrieve_fulltext(NEGATIVE, VAULT, top_k=K)
if not neg_hits:
    passed += 1
    print(f"  [PASS] 负例 {NEGATIVE!r} -> 无命中（防幻觉 OK）")
else:
    failed += 1
    print(f"  [FAIL] 负例 {NEGATIVE!r} -> 误命中 {[f.name for f, _ in neg_hits]}")

print("\n======== 汇总 ========")
print(f"  PASS: {passed}   FAIL: {failed}")
sys.exit(1 if failed else 0)