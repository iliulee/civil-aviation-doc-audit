# -*- coding: utf-8 -*-
"""
test_unguarded_doc_types.py — 「无规则覆盖文档类型」运行时闸门回归测试（v10.5）
=================================================================================

背景（Why）：
    规则引擎的 SINGLE_DOC 规则靠 trigger_when.doc_type 声明适用类型。声明式
    触发有天生的盲区：生产环境出现规则库从未声明的 doc_type（如施工日志、
    设计变更文件）时，规则引擎对它们完全静默——不报错、不告警、直接跳过。
    AI 审核员也无从得知"这个类型从来没有规则管过"。

    v10.5 修复：审核运行时自动侦测本轮所有 doc_type 中没有任何 active
    SINGLE_DOC 规则匹配的类型，写入 summary.unguarded_doc_types，
    报告端渲染「无规则覆盖提醒」节，SKILL.md 编码 AI 强制提醒协议。

钉住的根因（失败即说明闸门失效，禁止"修复"测试来变绿）：
    G1  run_rule_engine 的 summary 必须含 unguarded_doc_types 字段
    G2  无覆盖类型必须被点名（施工日志 → 出现在列表里，含份数）
    G3  有覆盖类型不得误报（碎石桩有规则 → 不出现在列表里）
    G4  纯 CROSS_DOC 兜底的类型不算"无覆盖"（材料检验记录走 LG-110，
        不得因为无 SINGLE_DOC 规则而误报）
    G5  全部有覆盖时列表为空（不硬造提醒）
    G6  report_builder 必须渲染该提醒（报告里看不到 = 白干）
"""

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

RULES_DIR = SCRIPT_DIR.parent / "rules"


def _make_docs(*doc_types, doc_role="audited"):
    """构造 docs 元数据列表：每个 doc_type 一份文档。"""
    return [
        {"id": f"DOC-{i+1:03d}", "doc_type": dt, "professional": "场道",
         "doc_role": doc_role}
        for i, dt in enumerate(doc_types)
    ]


def _run_rule_engine(docs, all_data=None):
    """薄封装：调用 review_audit.run_rule_engine，统一参数。"""
    from review_audit import run_rule_engine
    if all_data is None:
        all_data = {d["id"]: {"rows": []} for d in docs}
    return run_rule_engine(docs, all_data, RULES_DIR)


def test_summary_has_unguarded_doc_types_field():
    """G1：summary 必须含 unguarded_doc_types 字段（闸门本体）。"""
    docs = _make_docs("碎石桩施工记录")
    _, summary = _run_rule_engine(docs)
    assert "unguarded_doc_types" in summary, (
        "summary 缺少 unguarded_doc_types 字段——运行时无规则覆盖闸门未接入"
    )


def test_unguarded_doc_type_is_named():
    """G2：虚构类型「天气记录」无任何规则覆盖 → 必须被点名，含份数。

    注：不用"施工日志"做反例——实测它有 CROSS_DOC 通配规则（IR-017 等 8 条）
    + CROSS_UNIT 联动（CU-009/011）覆盖，属"有覆盖"。
    """
    docs = _make_docs("天气记录", "天气记录")
    _, summary = _run_rule_engine(docs)
    unguarded = {u["doc_type"]: u for u in summary.get("unguarded_doc_types", [])}
    assert "天气记录" in unguarded, (
        "「天气记录」无任何规则覆盖，必须出现在 unguarded_doc_types——"
        "否则该类型文档在规则引擎里静默裸检"
    )
    assert unguarded["天气记录"]["doc_count"] == 2, "份数必须等于该类型文档数"


def test_guarded_doc_type_not_flagged():
    """G3：碎石桩有大量 SINGLE_DOC 规则 → 不得误报进无覆盖列表。"""
    docs = _make_docs("碎石桩施工记录")
    _, summary = _run_rule_engine(docs)
    unguarded = [u["doc_type"] for u in summary.get("unguarded_doc_types", [])]
    assert "碎石桩施工记录" not in unguarded, (
        "碎石桩施工记录有多条 SINGLE_DOC 规则，出现在无覆盖列表 = 误报"
    )


def test_cross_doc_guarded_type_not_flagged():
    """G4：CROSS 类规则覆盖的类型不算"无覆盖"（防误报双用例）。"""
    docs = _make_docs(
        "材料、构配件进场检验记录",   # CROSS_DOC LG-110 名单覆盖
        "施工日志",                   # CROSS_DOC 通配 8 条 + CROSS_UNIT CU-009/011
    )
    _, summary = _run_rule_engine(docs)
    unguarded = [u["doc_type"] for u in summary.get("unguarded_doc_types", [])]
    assert "材料、构配件进场检验记录" not in unguarded, (
        "材料检验记录由 CROSS_DOC 规则 LG-110 覆盖（跨文档追溯链），"
        "无覆盖判定必须考虑 CROSS_DOC 兜底，不得误报"
    )
    assert "施工日志" not in unguarded, (
        "施工日志由 CROSS_DOC 通配规则（IR-017 等 8 条）+ CROSS_UNIT 联动"
        "（CU-009/011）覆盖，不得误报"
    )


def test_all_guarded_yields_empty_list():
    """G5：全部类型有覆盖 → 列表为空，不硬造提醒。"""
    docs = _make_docs("碎石桩施工记录")
    _, summary = _run_rule_engine(docs)
    assert summary.get("unguarded_doc_types") == [], (
        "全部类型有覆盖时 unguarded_doc_types 必须为空列表"
    )


def test_report_builder_renders_unguarded_warning():
    """G6：报告行动层必须渲染「无规则覆盖提醒」节。"""
    import report_builder as rb
    html = rb.render_html({
        "audit_log": {
            "summary": {
                "total": 0, "by_level": {}, "by_severity": {}, "by_scope": {},
                "unguarded_doc_types": [
                    {"doc_type": "施工日志", "doc_count": 15},
                ],
            },
            "documents": [],
            "findings": [],
        },
        "doc_id_to_file": {},
        "by_doc": {},
        "by_subdivision": {},
        "pie_values": {"通过": 0, "不通过": 0, "存疑": 0},
        "bar_data": [],
        "rule_execution_stats": [],
        "skill_version": "10.5-test",
        # build_model 会从 audit_log.summary 提取到顶层，此处直接给 render_html
        "unguarded_doc_types": [
            {"doc_type": "施工日志", "doc_count": 15},
        ],
    })
    assert "无规则覆盖" in html, (
        "报告必须含「无规则覆盖」提醒节——审核人看不到 = 闸门白建"
    )
    assert "施工日志" in html, "无覆盖类型名必须出现在报告里"
    assert "15" in html, "无覆盖类型的份数必须出现在报告里"


def test_real_chain_renders_unguarded_and_stats():
    """G7：真实链路——数据藏在 audit_log.rule_engine_summary 子 dict（v10.4
    断点复发教训：golden 放顶层测不出取数路径错位），报告必须仍能渲染。"""
    import report_builder as rb
    html = rb.render_html(rb.build_model({
        "summary": {"total_findings": 0},
        "documents": [],
        "findings": [],
        # 真实链路：review_audit.generate_audit_log 的结构
        "rule_engine_summary": {
            "rule_execution_stats": [
                {"rule_id": "LG-110", "name": "材料进场检验记录合格证追溯链",
                 "level": "L2-LOGIC", "scope": "CROSS_DOC",
                 "status": "active", "matched_docs": 2, "hits": 1},
            ],
            "unguarded_doc_types": [
                {"doc_type": "其他资料", "doc_count": 16,
                 "note": "无任何 active 规则覆盖此类型"},
            ],
        },
    }, None))
    assert "无规则覆盖" in html, (
        "unguarded_doc_types 在 rule_engine_summary 子 dict 时报告必须仍渲染"
        "（v10.4 rule_execution_stats 同型断点：取数只读顶层导致该节永远空）"
    )
    assert "其他资料" in html, "真实链路的无覆盖类型名必须出现"
    assert "LG-110" in html, "真实链路的规则执行统计必须出现"


def test_reference_role_not_flagged():
    """G8：reference 角色（审核参照，如设计变更文件供比对）不进提醒。

    Why: 30 份设计变更文件全是 reference——它们是审核的输入参照，
    不进规则引擎审核流。混进提醒会让每份报告都喊"设计变更文件
    30 份无覆盖"，噪音淹没真警报（audited 且无覆盖才是真裸检）。
    """
    docs = _make_docs("设计变更文件", doc_role="reference") * 30
    docs.append({"id": "DOC-999", "doc_type": "碎石桩施工记录",
                 "professional": "场道", "doc_role": "audited"})
    _, summary = _run_rule_engine(docs)
    unguarded = [u["doc_type"] for u in summary.get("unguarded_doc_types", [])]
    assert "设计变更文件" not in unguarded, (
        "reference 角色是审核参照不是受审对象，不得进无规则覆盖提醒"
    )
