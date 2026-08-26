# -*- coding: utf-8 -*-
"""
规则→审核→报告 链路回归套件（scripts/test_rule_to_report_chain.py）
=====================================================================
v10.4 方案 A 组（规则链路修复）的 TDD 契约。
红 = 链路断点（规则加了但审核/报告不吸收），实现后变绿，永久留套防复发。

锁定的断点（2026-08-26 测试26 实测）：
  B1  引擎执行 93 条规则 0 命中 —— 材料类规则 doc_type 与生产真实值
      "材料、构配件进场检验记录" 不匹配，静默落空
  B2  build_foundation 检出 10 条 S-04 写入 index.ledgers.certificates_linkage，
      但审核（review_audit）/报告（run_audit）零读取 —— 死数据
  B3  审核读的是 corrected（人工核对后）数据，若直接读建底座时的
      certificates_linkage 会报"已修好的旧问题" —— 陈旧结果 bug
  B4  规则执行无可视性：跑没跑、匹配几份文档、命中几条，无处可查
  B5  registry 计数 94 与 SKILL.md 宣称 93 漂移

覆盖用例：
  C1  collect_certificate_findings：审核期基于 corrected 数据重算 S-04，
      产出 rule_engine_findings 兼容格式（rule_id=LG-110）
  C2  人工补齐合格证号后重审 → S-04 消失（锁死陈旧结果 bug）
  C3  审核后台账与 corrected 数据一致（missing_hg_no 归零）
  C4  review_audit 接线静态断言（防删防漏接）
  C5  规则执行统计 build_execution_stats：matched_docs/hits，0 匹配可见
  C6  LG-110 触发词必须覆盖生产真实 doc_type
  C7  registry 计数 = 规则文件数 = SKILL.md 宣称数
  C8  引擎侧不重复执行 LG-110（占位 expr=True 恒通过，防双跑）
"""

from pathlib import Path
import json
import re
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

RULES_DIR = SCRIPT_DIR.parent / "rules"

# 生产底座真实 doc_type（测试26 / DOC-001/002 实测值）——
# 规则与检查必须认这个值，不得只认"材料进场检验记录"这类理想化名称
PRODUCTION_MATERIAL_DOC_TYPE = "材料、构配件进场检验记录"

# 未修正行：合格证号空白（S-01/S-04 场景，模拟 OCR 建底座原始产出）
_UNCORRECTED_ROWS = [
    {"row_index": 1, "table": "记录", "材料名称": "钢筋", "规格型号": "HRB400E Φ25",
     "数量": "12.56", "生产厂家": "云南玉溪玉昆钢铁集团有限公司",
     "合格证号": "", "质证书编号": "YKG/A20260704052", "parsed": True},
    {"row_index": 2, "table": "记录", "材料名称": "钢筋", "规格型号": "HRB400E Φ22",
     "数量": "8.32", "生产厂家": "云南玉溪玉昆钢铁集团有限公司",
     "合格证号": "", "质证书编号": "YKG/A20260704053", "parsed": True},
]

# 修正行：人工核对后补齐合格证号（阶段2 产物，审核阶段实际读取的数据）
_CORRECTED_ROWS = [
    {"row_index": 1, "table": "记录", "材料名称": "钢筋", "规格型号": "HRB400E Φ25",
     "数量": "12.56", "生产厂家": "云南玉溪玉昆钢铁集团有限公司",
     "合格证号": "HG20260701001", "质证书编号": "YKG/A20260704052", "parsed": True},
    {"row_index": 2, "table": "记录", "材料名称": "钢筋", "规格型号": "HRB400E Φ22",
     "数量": "8.32", "生产厂家": "云南玉溪玉昆钢铁集团有限公司",
     "合格证号": "HG20260701002", "质证书编号": "YKG/A20260704053", "parsed": True},
]


def _material_docs(rows):
    """构造审核入口的 (docs, all_data)：doc_type 用生产真实值。"""
    docs = [{
        "id": "DOC-001",
        "doc_type": PRODUCTION_MATERIAL_DOC_TYPE,
        "doc_role": "audited",
        "original_file": "表C2-9材料进场检验记录.docx",
    }]
    all_data = {
        "DOC-001": {
            "doc_type": PRODUCTION_MATERIAL_DOC_TYPE,
            "schema_status": "material",
            "structured_rows": rows,
        },
    }
    return docs, all_data


# ============================================================
# C1：审核期专用检查 —— S-04 进 rule_engine_findings
# ============================================================
def test_collect_certificate_findings_detects_missing_hg_no():
    import extract_certificates as ec
    assert hasattr(ec, "collect_certificate_findings"), \
        "缺少审核期专用检查函数 collect_certificate_findings（断点B2：底座检出结果无人消费）"
    docs, all_data = _material_docs(_UNCORRECTED_ROWS)
    result = ec.collect_certificate_findings(docs, all_data)
    # 兼容两种返回形态，但必须能同时拿到 findings 与台账数据
    if isinstance(result, tuple):
        findings, certs_by_doc = result
    else:
        findings, certs_by_doc = result, {}
    lg110 = [f for f in findings if f.get("rule_id") == "LG-110"]
    assert lg110, "缺合格证号的行必须产出 LG-110 finding（S-04 必须进审核日志）"
    f = lg110[0]
    # schema 契约：与 ViolationReporter.to_audit_findings 完全兼容（报告统一渲染的前提）
    for key in ("rule_id", "rule_name", "level", "scope", "severity", "result",
                "row_index", "finding", "evidence", "remediation",
                "spec", "evidence_source"):
        assert key in f, f"finding 缺字段 {key}: {sorted(f)}"
    assert f.get("row_index") is not None, "S-04 必须带 row_index 行级定位"
    assert f.get("severity") == "Best Practice"


# ============================================================
# C2：陈旧结果 bug —— 修正后重审，S-04 必须消失
# ============================================================
def test_corrected_data_clears_s04_on_reaudit():
    import extract_certificates as ec
    docs, all_data = _material_docs(_CORRECTED_ROWS)
    result = ec.collect_certificate_findings(docs, all_data)
    findings = result[0] if isinstance(result, tuple) else result
    stale = [f for f in findings if f.get("rule_id") == "LG-110"]
    assert not stale, \
        f"人工补齐合格证号后重审不得再报 S-04（陈旧结果 bug）: {stale}"


# ============================================================
# C3：审核后台账与 corrected 数据一致
# ============================================================
def test_refresh_ledger_consistent_with_corrected_data():
    import extract_certificates as ec
    docs, all_data = _material_docs(_CORRECTED_ROWS)
    result = ec.collect_certificate_findings(docs, all_data)
    if isinstance(result, tuple):
        _, certs_by_doc = result
    else:
        certs_by_doc = {}
    assert certs_by_doc.get("DOC-001"), "必须同时产出台账数据供审核期刷新（口径一致）"
    idx = {"documents": [{"id": "DOC-001", "doc_type": PRODUCTION_MATERIAL_DOC_TYPE}]}
    ec.attach_certificates_ledger(idx, certs_by_doc)
    ledger = idx["ledgers"]["certificates"]
    assert all(r["verified_status"] == "ok" for r in ledger), \
        f"修正后台账不得再有 missing_hg_no: {ledger}"
    assert idx["documents"][0]["certificates"]["missing_hg_no"] == 0


# ============================================================
# C4：review_audit 接线静态断言（防删防漏接）
# ============================================================
def test_review_audit_wires_certificate_findings():
    src = (SCRIPT_DIR / "review_audit.py").read_text(encoding="utf-8")
    assert "collect_certificate_findings" in src, \
        "review_audit 必须接线审核期合格证检查（断点B2：检出了没人读）"


# ============================================================
# C5：规则执行统计 —— matched_docs / hits，0 匹配可见
# ============================================================
def test_build_execution_stats_flags_zero_match():
    from rule_engine import RuleLoader, build_execution_stats
    loader = RuleLoader()
    rules = loader.load_all(RULES_DIR)
    single = [r for r in rules
              if r.scope == "SINGLE_DOC" and r.trigger_when.get("doc_type")]
    assert single, "必须存在 SINGLE_DOC 规则供执行统计"
    rule = single[0]
    dt = rule.trigger_when["doc_type"][0]
    stats_hit = build_execution_stats([rule], [{"id": "D1", "doc_type": dt}], [])
    stats_miss = build_execution_stats(
        [rule], [{"id": "D1", "doc_type": "完全不存在的资料类型xyz"}], [])
    assert stats_hit[0]["matched_docs"] == 1
    assert stats_miss[0]["matched_docs"] == 0, \
        "0 匹配规则必须在统计中可见（报告端标 ⚠️ 的数据源）"
    assert "hits" in stats_miss[0]


def test_review_audit_summarizes_rule_execution_stats():
    src = (SCRIPT_DIR / "review_audit.py").read_text(encoding="utf-8")
    assert "rule_execution_stats" in src, \
        "run_rule_engine 汇总必须带 rule_execution_stats（断点B4：执行无可视性）"


# ============================================================
# C6：LG-110 触发词覆盖生产真实 doc_type（断点B1）
# ============================================================
def test_lg110_trigger_covers_production_doc_type():
    rule = json.loads(
        (RULES_DIR / "L2-logic" / "LG-110.json").read_text(encoding="utf-8"))
    dts = rule["trigger_when"]["doc_type"]
    assert PRODUCTION_MATERIAL_DOC_TYPE in dts, \
        f"LG-110 触发词必须覆盖生产真实 doc_type「{PRODUCTION_MATERIAL_DOC_TYPE}」，当前: {dts}"


# ============================================================
# C7：registry 计数 = 规则文件数 = SKILL.md 宣称数（断点B5）
# ============================================================
def test_registry_counts_match_files_and_skill_md():
    files = [p for p in RULES_DIR.rglob("*.json")
             if p.relative_to(RULES_DIR).parts[0] in ("L1-iron", "L2-logic", "L3-business")]
    reg = json.loads((RULES_DIR / "registry.json").read_text(encoding="utf-8"))
    assert reg.get("total_rules") == len(files), \
        f"registry total_rules={reg.get('total_rules')} != 规则文件数 {len(files)}"
    skill_md = (SCRIPT_DIR.parent / "SKILL.md").read_text(encoding="utf-8")
    # 锁定总数宣称行（"N 条规则三层分级"），避开 L1-IRON "17 条规则文件" 的分层数
    m = re.search(r"(\d+)\s*条规则三层分级", skill_md)
    assert m, "SKILL.md 必须宣称规则总数（「N 条规则三层分级」）"
    assert int(m.group(1)) == reg["total_rules"], \
        f"SKILL.md 宣称 {m.group(1)} 条 != registry {reg['total_rules']} 条"


# ============================================================
# C8：引擎侧不重复执行 LG-110（防双跑）
# ============================================================
def test_engine_does_not_double_execute_lg110():
    from rule_engine import RuleLoader, CrossDocChecker
    loader = RuleLoader()
    rule = loader.load_by_id(RULES_DIR, "LG-110")
    assert rule is not None, "LG-110 规则文件必须可加载"
    checker = CrossDocChecker()
    docs_data = [{"rows": [dict(r) for r in _UNCORRECTED_ROWS]}]
    vs = checker.check(rule, docs_data)
    assert not vs, \
        "LG-110 引擎路径必须 0 命中（占位 expr=True；专用检查走 collect_certificate_findings，防双跑）"


# ============================================================
# C9：A1 规则覆盖扫描 —— CFG 桩生产文档必须被通用桩类规则匹配
# ============================================================
# 历史数据底座实测："CFG桩施工记录"出现 3 份文档，但桩类/数据质量规则
# 只声明了碎石桩/PHC/DDC —— 精确匹配下 CFG 文档零规则覆盖（静默失效）。
# 仅要求"通用"桩检查覆盖 CFG；沉管/拔管类（LG-006/007）与充盈系数
# （LG-1002）是沉管工艺专属，CFG 为钻孔灌注工艺，明确不要求。
CFG_PILE_DOC_TYPE = "CFG桩施工记录"
CFG_EXPECTED_RULES = (
    "LG-904",   # 高程自洽
    "LG-906",   # 多参数联检
    "LG-1001",  # 桩长自洽
    "LG-1003",  # 行数自洽
    "LG-1004",  # 桩号连续性
    "LG-1005",  # 时间连续性
    "BZ-001",   # 重复值模式
    "BZ-002",   # 突变检测
    "BZ-003",   # 涂改痕迹
)


def test_cfg_pile_docs_match_generic_pile_rules():
    from rule_engine import RuleLoader, RuleMatcher
    loader = RuleLoader()
    rules = [r for r in loader.load_all(RULES_DIR)
             if r.scope == "SINGLE_DOC"]
    matcher = RuleMatcher()
    matched = matcher.match_by_doc_type(rules, CFG_PILE_DOC_TYPE)
    matched_ids = {r.rule_id for r in matched}
    missing = [rid for rid in CFG_EXPECTED_RULES if rid not in matched_ids]
    assert not missing, \
        (f"CFG桩施工记录（历史生产 3 份文档）未被通用桩类规则覆盖: {missing}。"
         "精确匹配下这些文档将零规则执行（A1 扫描发现的静默失效）。")
