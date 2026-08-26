# -*- coding: utf-8 -*-
"""
报告生成器回归套件（scripts/test_report_builder.py）
=====================================================
v10.4 方案 B 组（报告结构重构）的 TDD 契约。
红 = 功能缺口，实现后变绿，永久留套防复发。

背景断点（2026-08-26 测试26 实测）：
  R1  报告渲染内嵌在 run_audit._generate_html_report 巨型函数里
      （数据建模+渲染混杂 ~450 行），任何 agent 装此 skill 出的报告
      结构漂移无从约束 —— 需抽 report_builder.py（build_model/render_html 分离）
  R2  findings 的 remediation（整改建议）字段有数据但报告不渲染 ——
      审核人看不到"怎么改"
  R3  rule_execution_stats（A4 产出 matched_docs/hits）报告零消费 ——
      规则静默失效在报告端不可见（又一个"产出无人消费"断点）
  R4  页脚版本号硬编码 v7.0 与 SKILL.md 实际版本漂移
  R5  verify_report 对账闸门不含 ledgers.certificates —— 合格证台账
      记录数与报告声称无对账（铁律：报告对账闸门需扩展 certificates 表）

覆盖用例：
  D1  report_builder.build_model / render_html 存在且被 run_audit 消费
  D2  问题清单必须渲染"整改建议"列（remediation）
  D3  报告必须含规则执行统计（0 匹配规则标 ⚠）
  D4  页脚版本号与 SKILL.md 一致（读 version 元数据，不硬编码）
  D5  golden：固定 audit_log → 报告关键锚点稳定（三层结构齐全）
  D6  verify_report 支持 certificates 台账对账
"""

from pathlib import Path
import re
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

SKILL_DIR = SCRIPT_DIR.parent


# 固定最小 audit_log（golden 输入）：1 份文档 1 条问题 + 规则执行统计
def _golden_audit_log() -> dict:
    return {
        "project_name": "回归测试项目",
        "audit_id": "AU-TEST-001",
        "audit_completed_at": "2026-08-26T10:00:00",
        "preconditions": {"stage": "资料审核", "nature": "施工资料", "scope": "场道工程"},
        "summary": {
            "documents_audited": 1, "total_findings": 2,
            "pass": 1, "fail": 1, "suspicious": 0, "needs_ai": 0, "not_applicable": 0,
        },
        "conclusion": {
            "overall": "资料存在不符合项，建议整改后复核",
            "recommendations": ["补填合格证编号"],
        },
        "tasks": [{
            "sub_label": "土方工程", "item_label": "碎石桩",
            "documents": [{"id": "DOC-001", "original_file": "表C2-9检验记录.docx"}],
        }],
        "findings": [
            {
                "result": "pass", "severity": "low", "checklist_id": "CK-01",
                "category": "完整性", "check_item": "表头齐全", "doc_id": "DOC-001",
                "finding": "表头完整", "spec": "MH/T 5078.1-2024 第 6.2.7 条",
                "evidence_type": "spec", "evidence_source": "references/obsidian",
                "remediation": "无需整改",
            },
            {
                "result": "fail", "severity": "high", "checklist_id": "LG-110",
                "category": "追溯性", "check_item": "合格证追溯链", "doc_id": "DOC-001",
                "finding": "检验记录行未引用合格证编号", "spec": "",
                "evidence_type": "engineering_practice", "evidence_source": "missing",
                "remediation": "补填合格证编号，建立检验记录→质证书→合格证关联",
            },
        ],
        "logic_consistency_findings": [],
        "tasks_detail": [],
        "signature_anomalies": [],
        "rule_execution_stats": [
            {"rule_id": "LG-110", "name": "合格证追溯链", "level": "L2-LOGIC",
             "scope": "CROSS_DOC", "status": "active", "matched_docs": 1, "hits": 1},
            {"rule_id": "CU-002", "name": "开工令对账", "level": "L3-BUSINESS",
             "scope": "CROSS_UNIT", "status": "active", "matched_docs": 0, "hits": 0},
        ],
    }


def _render_golden() -> str:
    import report_builder as rb
    model = rb.build_model(_golden_audit_log(), Path("D:/golden"))
    return rb.render_html(model)


# ============================================================
# D1：report_builder 存在 + run_audit 消费（防结构倒退回巨型函数）
# ============================================================
def test_report_builder_module_exists_and_used():
    import report_builder as rb
    for fn in ("build_model", "render_html"):
        assert hasattr(rb, fn), f"report_builder 缺少 {fn}（断点R1：建模/渲染未分离）"
    src = (SCRIPT_DIR / "run_audit.py").read_text(encoding="utf-8")
    assert "report_builder" in src, \
        "run_audit 必须消费 report_builder（断点R1：不得回退到内嵌巨型函数）"


# ============================================================
# D2：问题清单必须渲染"整改建议"列（断点R2）
# ============================================================
def test_findings_table_renders_remediation():
    html = _render_golden()
    assert "整改建议" in html, \
        "问题清单表头必须含「整改建议」列（断点R2：remediation 有数据不渲染）"
    assert "补填合格证编号" in html, \
        "问题行的 remediation 内容必须渲染进表格（审核人要看到怎么改）"


# ============================================================
# D3：报告必须含规则执行统计（断点R3）
# ============================================================
def test_report_renders_rule_execution_stats():
    html = _render_golden()
    assert "规则执行统计" in html, \
        "报告必须含「规则执行统计」节（断点R3：matched_docs/hits 产出无人消费）"
    assert "LG-110" in html, "统计表必须列出规则 ID"
    # 0 匹配规则必须带 ⚠ 可视标记（静默失效显形）
    assert "⚠" in html, "0 匹配规则必须标 ⚠（matched_docs=0 可见）"


# ============================================================
# D4：页脚版本号与 SKILL.md 一致（断点R4）
# ============================================================
def test_report_footer_version_matches_skill_md():
    skill_md = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    # 与 report_builder._skill_version 同款正则（行首锚定 + 兼容带引号/不带引号）
    m = re.search(r'^version:\s*"?([\d.]+)"?', skill_md, re.M)
    assert m, "SKILL.md 必须带 version 元数据"
    html = _render_golden()
    ver = m.group(1)
    assert f"v{ver}" in html, \
        f"页脚版本必须为 v{ver}（与 SKILL.md 一致），不得硬编码旧版本号"


# ============================================================
# D5：golden 锚点 —— 三层报告结构齐全（结论层/问题层/行动层）
# ============================================================
def test_golden_report_structure_anchors():
    html = _render_golden()
    anchors = [
        "民航施工资料合规审核报告",   # 结论层：标题
        "总体结论",                    # 结论层：结论卡
        "规范对账发现",                # 问题层：问题清单
        "整改建议",                    # 行动层：怎么改
        "规则执行统计",                # 行动层：规则覆盖透明度
    ]
    for a in anchors:
        assert a in html, f"报告缺关键锚点「{a}」（三层结构不完整）"
    # 依据缺失渲染契约（v10.1 render_spec_cell 行为不回退）
    assert "依据缺失" in html or "依据未标注" in html, \
        "spec 空 + evidence_source=missing 必须渲染「依据缺失/未标注」警示"


# ============================================================
# D6：verify_report 支持 certificates 台账对账（断点R5）
# ============================================================
def test_verify_report_supports_certificates_reconciliation():
    src = (SCRIPT_DIR / "verify_report.py").read_text(encoding="utf-8")
    assert "certificates" in src, \
        "verify_report 必须覆盖 ledgers.certificates 对账（断点R5：合格证台账无对账）"

    # 行为验证：直接传参（底座 3 条 vs 报告声称 2 条 → 必须报不一致）
    import verify_report as vr
    problems = vr.check_certificates_alignment(
        "合格证台账共 2 条记录", {"ledgers": {"certificates": [
            {"row_index": 1}, {"row_index": 2}, {"row_index": 3}]}})
    assert problems, "证书台账数 3 vs 报告声称 2 必须报不一致"
    ok = vr.check_certificates_alignment(
        "合格证台账共 3 条记录", {"ledgers": {"certificates": [
            {"row_index": 1}, {"row_index": 2}, {"row_index": 3}]}})
    assert not ok, "台账数 3 vs 报告声称 3 必须通过"
