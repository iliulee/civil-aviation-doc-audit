#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""依据查询机制 self-test：验证 lookup_source 的三道闸门。

目标（对应 依据查询机制_方案设计.md 第 5 节 eval 用例）：
  ① 依据查找：references 命中 → source="references"
  ② Obsidian 兜底：references 未命中但 obsidian 有 → source="obsidian"
  ③ 依据缺失：references 与 obsidian 均无 → source="missing"，found=False
  ④ 来源留痕：每个命中都带 file / spec / clause / snippet，可追溯
  ⑤ 防幻觉：lookup_source 源码不得调用 WebSearch / requests 上网

TDD 顺序：本文件先写（验证程序），再实现 scripts/lookup_source.py 使本测试通过。
运行：python verify_lookup_source.py
"""
import sys
import json
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).parent
SKILL_DIR = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# 加载 lookup_source（若未实现则后续用例全部 FAIL，符合 TDD 红-绿）
try:
    ls = load_module("lookup_source", SCRIPTS / "lookup_source.py")
except Exception as e:  # 模块缺失或导入失败
    ls = None
    _LOAD_ERR = e
else:
    _LOAD_ERR = None

passed = 0
failed = 0
skipped = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}  {detail}")


def require_lookup():
    global skipped
    if ls is None:
        skipped += 1
        print(f"  [SKIP] lookup_source 未加载：{_LOAD_ERR}")
        return None
    return ls


# 用相对项目根定位 references，避免依赖具体安装路径
REFS_DIR = SKILL_DIR / "references"
# 规范全文目录：优先取 lookup_source 解析后的默认路径（包内自带 > 本地 Obsidian 库），
# 未加载或解析为空时回退到原 H: 盘路径，保证脱离 Obsidian 也能跑通场景 ②。
try:
    _resolved_vault = ls.resolve_vault_dir(None) if ls is not None else None
except Exception:
    _resolved_vault = None
VAULT_DIR = _resolved_vault or Path(r"H:\Obsidian notes\溜哥笔记\wiki\sources")


print("== 0) 加载与依赖 ==")
check("lookup_source 可加载", ls is not None, f"err={_LOAD_ERR}")
if ls is not None:
    check("lookup_source 暴露 lookup_source()", callable(getattr(ls, "lookup_source", None)))
    check("references 目录存在", REFS_DIR.is_dir(), f"path={REFS_DIR}")
    check("obsidian vault 存在", VAULT_DIR.is_dir(), f"path={VAULT_DIR}")

# ---------------- 场景 ① references 命中 ----------------
print("\n== 1) references 命中 → source=references ==")
if require_lookup() is not None:
    # 1a. 规范号直查：MH/T 5078.1 存在于 specification-mapping.md
    hit1 = ls.lookup_source("MH/T 5078.1", references_dir=str(REFS_DIR))
    check("1a 命中 references", hit1.get("found") is True,
          f"found={hit1.get('found')} source={hit1.get('source')}")
    check("1a 来源标记 references", hit1.get("source") == "references",
          f"source={hit1.get('source')}")
    check("1a 带 spec 规范号", bool(hit1.get("spec")),
          f"spec={hit1.get('spec')}")
    check("1a 带来源文件", bool(hit1.get("file")),
          f"file={hit1.get('file')}")

    # 1b. 中文资料类型关键词：施工日志 → 应命中 specification-mapping.md 第6章
    hit2 = ls.lookup_source("施工日志", references_dir=str(REFS_DIR))
    check("1b 命中 references", hit2.get("found") is True,
          f"found={hit2.get('found')} source={hit2.get('source')}")
    check("1b 来源标记 references", hit2.get("source") == "references",
          f"source={hit2.get('source')}")
    check("1b 带条款号", bool(hit2.get("clause")),
          f"clause={hit2.get('clause')} spec={hit2.get('spec')}")

# ---------------- 场景 ② Obsidian 兜底 ----------------
print("\n== 2) references 未命中 → obsidian 兜底 ==")
if require_lookup() is not None:
    # references 无 BIM/5073，obsidian 有 MH-T5073-2023
    hit3 = ls.lookup_source("MH-T5073 建筑信息模型",
                            references_dir=str(REFS_DIR),
                            vault_dir=str(VAULT_DIR))
    # 若 references 误命中则算失败；正常应落到 obsidian
    check("2a obsidian 命中", hit3.get("found") is True,
          f"found={hit3.get('found')} source={hit3.get('source')}")
    check("2a 来源标记 obsidian", hit3.get("source") == "obsidian",
          f"source={hit3.get('source')}")
    check("2a 带来源文件", bool(hit3.get("file")) and "MH-T5073" in str(hit3.get("file", "")),
          f"file={hit3.get('file')}")

    # 2b. 用规范号 glob 文件名兜底（规避 search 多词失配），应命中 MH-T5078.1 原文文件
    hit4 = ls.lookup_source("MH/T 5078.1", content_snippet="第6章",
                            references_dir=str(REFS_DIR),
                            vault_dir=str(VAULT_DIR))
    check("2b 兜底命中原文文件", hit4.get("found") is True,
          f"found={hit4.get('found')} source={hit4.get('source')} file={hit4.get('file')}")

# ---------------- 场景 ③ 依据缺失 ----------------
print("\n== 3) references 与 obsidian 均无 → missing ==")
if require_lookup() is not None:
    hit5 = ls.lookup_source("MH-T9999-9999 不存在的规范",
                            references_dir=str(REFS_DIR),
                            vault_dir=str(VAULT_DIR))
    check("3a 未找到", hit5.get("found") is False,
          f"found={hit5.get('found')}")
    check("3a 来源标记 missing", hit5.get("source") == "missing",
          f"source={hit5.get('source')}")
    check("3a 不编造 spec/clause", not hit5.get("spec") and not hit5.get("clause"),
          f"spec={hit5.get('spec')} clause={hit5.get('clause')}")

# ---------------- 场景 ④ 来源留痕 ----------------
print("\n== 4) 来源留痕（字段完整性）==")
if require_lookup() is not None:
    for label, hit in [("1a", hit1), ("1b", hit2), ("2a", hit3), ("2b", hit4)]:
        check(f"4 {label} 含 searched_at", bool(hit.get("searched_at")),
              f"searched_at={hit.get('searched_at')}")
        check(f"4 {label} 含 source 标记", hit.get("source") in ("references", "obsidian", "missing"),
              f"source={hit.get('source')}")

# ---------------- 场景 ⑤ 防幻觉（不得上网） ----------------
print("\n== 5) 防幻觉：lookup_source 不得调用 WebSearch/requests ==")
if require_lookup() is not None:
    src = (SCRIPTS / "lookup_source.py").read_text(encoding="utf-8")
    banned = ["WebSearch", "web_search", "requests.get", "httpx.get", "urllib.request"]
    hits = [b for b in banned if b in src]
    check("5 源码不含上网调用", not hits, f"发现危险调用: {hits}")

# ============ 依据查询机制：集成测试（review_audit 回填 + 结论门禁）============

try:
    ra = load_module("review_audit", SCRIPTS / "review_audit.py")
except Exception as e:
    ra = None
    _RA_ERR = e
else:
    _RA_ERR = None

print("\n== 6) review_audit 回填 + 结论门禁 ==")
if ls is not None and ra is not None:
    # 6a. spec 为空的 finding 会回填 evidence_source
    findings_a = [
        {"check_item": "施工日志", "finding": "检查施工日志连续性", "result": "suspicious", "severity": "medium"},
        {"check_item": "MH-T5073 建筑信息模型", "finding": "检查 BIM 模型", "result": "fail", "severity": "high"},
    ]
    dist = ra._backfill_evidence_source(findings_a, references_dir=str(REFS_DIR))
    check("6a 回填后每项带 evidence_source",
          all(f.get("evidence_source") for f in findings_a),
          f"={[f.get('evidence_source') for f in findings_a]}")
    check("6a 施工日志落 references", findings_a[0].get("evidence_source") == "references",
          f"={findings_a[0].get('evidence_source')}")
    check("6a BIM 落 obsidian", findings_a[1].get("evidence_source") == "obsidian",
          f"={findings_a[1].get('evidence_source')}")
    check("6a 来源分布统计", dist.get("references", 0) >= 1 and dist.get("obsidian", 0) >= 1,
          f"dist={dist}")

    # 6b. 依据缺失门禁：存在 missing 且带结论 → 结论不得为合格/不合格
    findings_missing = [
        {"spec": "", "check_item": "MH-T9999-9999", "result": "fail", "severity": "high",
         "evidence_source": "missing"},
    ]
    conc_missing = ra._derive_overall_conclusion(findings_missing)
    check("6b 依据缺失 → 结论拦截", "依据缺失" in conc_missing,
          f"结论={conc_missing!r}")
    check("6b 结论不含合格/不合格", "合格" not in conc_missing and "不合格" not in conc_missing,
          f"结论={conc_missing!r}")

    # 6c. 无依据缺失时，正常结论逻辑仍生效
    findings_ok = [
        {"spec": "MH/T 5078.1", "result": "pass", "severity": "low", "evidence_source": "references"},
    ]
    conc_ok = ra._derive_overall_conclusion(findings_ok)
    check("6c 无依据缺失 → 正常结论", conc_ok == "合格 — 未发现不符合项",
          f"结论={conc_ok!r}")

    # 6d. 回填后的 finding 记录来源文件/片段（可追溯）
    hit_file = findings_a[1].get("evidence_file", "")
    check("6d obsidian 命中带来源文件", bool(hit_file) and "MH-T5073" in str(hit_file),
          f"file={hit_file!r}")
else:
    skipped += 1
    print(f"  [SKIP] review_audit 未加载：{_RA_ERR}")

print("\n======== 汇总 ========")
print(f"  PASS: {passed}   FAIL: {failed}   SKIP: {skipped}")
if failed:
    print("结果：FAIL（存在未通过用例）")
    sys.exit(1)
if passed == 0:
    print("结果：无法验证（lookup_source 未实现）")
    sys.exit(1)
print("结果：PASS")