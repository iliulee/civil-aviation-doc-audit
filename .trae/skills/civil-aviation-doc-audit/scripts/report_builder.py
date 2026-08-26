# -*- coding: utf-8 -*-
"""
report_builder.py — 审核报告生成器（v10.4 B1/B2）
====================================================
从 run_audit._generate_html_report 巨型函数拆出（断点 R1）：
建模与渲染分离，任何 agent 装此 skill 出的报告结构由本模块统一约束。

  build_model(audit_log, project_path) -> dict   纯数据变换（分组/统计/图表数据）
  render_html(model) -> str                      纯渲染（model → HTML）

v10.4 B2 三层报告结构（方便审核人快速找问题和依据）：
  第一层·结论    审核概要 + 总体结论（看一眼知道结果）
  第二层·问题    规范对账发现（每条带严重度/规范依据/依据类型/整改建议）
  第三层·行动    规则执行统计（规则覆盖透明，0 匹配 ⚠ 显形）+ 整改建议

Why 拆分：原 ~450 行巨型函数里数据建模与 HTML 渲染混杂，改结构必踩回归；
拆分后 build_model 可单测，render_html 的结构由 test_report_builder.py 锚定。
"""

from datetime import datetime
from pathlib import Path
import re

# 模块内约定：不 import run_audit（run_audit 单向依赖本模块，防循环导入）

_SKILL_DIR = Path(__file__).resolve().parent.parent


def _skill_version() -> str:
    """读 SKILL.md 版本号（单一真相源，报告页脚不硬编码）。

    优先 frontmatter `version:` 字段；缺失时从标题 `# ... vN.N` 提取；
    均无则返回 "0.0"（报告仍可生成，测试 D4 会锁 frontmatter 字段存在）。
    """
    skill_md = _SKILL_DIR / "SKILL.md"
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return "0.0"
    m = re.search(r'^version:\s*"?(\d[\d.]*)"?', text, re.M)
    if m:
        return m.group(1)
    m = re.search(r"^#.*?\bv(\d[\d.]*)", text, re.M)
    if m:
        return m.group(1)
    return "0.0"


def render_spec_cell(f: dict) -> str:
    """报告"规范"列渲染（v10.1）：依据缺失/未核验不得留白。

    配套 review_audit._backfill_evidence_source 回填的 evidence_source：
      - spec 空 + evidence_source=missing → ⚠️ 依据缺失（未检索到规范原文）
      - spec 空 + 无回填标记（legacy 日志） → ⚠️ 依据未标注
      - spec 有 + evidence_source=missing → 条款保留 + ⚠️ 未经原文核验（防幻觉条款）
      - spec 有 + 已核验来源（references/obsidian）→ 原样渲染
    """
    spec = str(f.get("spec", "") or "").strip()
    src = str(f.get("evidence_source", "") or "").strip()
    if not spec:
        if src == "missing":
            return ('<span style="color:#B45309;font-size:12px;">'
                    '⚠️ 依据缺失（未检索到规范原文）</span>')
        return ('<span style="color:#B45309;font-size:12px;">'
                '⚠️ 依据未标注</span>')
    if src == "missing":
        return (f'{spec}<br><span style="color:#B45309;font-size:12px;">'
                f'⚠️ 未经原文核验</span>')
    return spec


# ============================================================
# SVG 图表（从 run_audit 平移，逻辑零改动）
# ============================================================

def _cos_deg(deg: float) -> float:
    """cos(角度)"""
    import math
    return math.cos(deg * math.pi / 180)


def _sin_deg(deg: float) -> float:
    """sin(角度)"""
    import math
    return math.sin(deg * math.pi / 180)


def _svg_arc_path(cx: float, cy: float, outer_r: float, inner_r: float, start_deg: float, end_deg: float) -> str:
    """生成 SVG 环形/扇形路径。"""
    x1 = cx + outer_r * _cos_deg(start_deg)
    y1 = cy + outer_r * _sin_deg(start_deg)
    x2 = cx + outer_r * _cos_deg(end_deg)
    y2 = cy + outer_r * _sin_deg(end_deg)
    x3 = cx + inner_r * _cos_deg(end_deg)
    y3 = cy + inner_r * _sin_deg(end_deg)
    x4 = cx + inner_r * _cos_deg(start_deg)
    y4 = cy + inner_r * _sin_deg(start_deg)

    large_arc = 1 if (end_deg - start_deg) > 180 else 0

    return (
        f"M {x1:.1f} {y1:.1f} "
        f"A {outer_r:.1f} {outer_r:.1f} 0 {large_arc} 1 {x2:.1f} {y2:.1f} "
        f"L {x3:.1f} {y3:.1f} "
        f"A {inner_r:.1f} {inner_r:.1f} 0 {large_arc} 0 {x4:.1f} {y4:.1f} Z"
    )


def _generate_pie_chart_svg(
    values: dict,
    width: int = 280,
    height: int = 280,
    inner_radius: float = 0.55,
) -> str:
    """生成 SVG 环形图（Donut Chart）。

    Args:
        values: {标签: 数值} 字典，如 {"通过": 45, "不通过": 12, "存疑": 8}
        width: SVG 宽度
        height: SVG 高度
        inner_radius: 内圆半径比例（0 为饼图，0.55 为环形图）

    Returns:
        SVG 字符串
    """
    COLORS = {
        "通过": "#34a853",
        "不通过": "#d93025",
        "存疑": "#e37400",
        "待AI": "#9334e6",
        "不适用": "#9aa0a6",
    }
    items = [(k, v) for k, v in values.items() if v > 0]
    if not items:
        return ""

    total = sum(v for _, v in items)
    cx, cy = width / 2, height / 2
    outer_r = min(cx, cy) - 10
    inner_r = outer_r * inner_radius

    arcs = []
    legend_items = []
    start_angle = -90  # 从顶部开始

    for i, (label, count) in enumerate(items):
        pct = count / total
        angle = pct * 360
        end_angle = start_angle + angle

        color = COLORS.get(label, "#9aa0a6")
        # 单项100%时拆分为两段半圆弧，避免起点终点重合导致无法绘制
        if angle >= 359.99:
            mid_angle = start_angle + 180
            arc1 = _svg_arc_path(cx, cy, outer_r, inner_r, start_angle, mid_angle)
            arc2 = _svg_arc_path(cx, cy, outer_r, inner_r, mid_angle, end_angle)
            arcs.append(f'<path d="{arc1}" fill="{color}" stroke="#fff" stroke-width="1"/>')
            arcs.append(f'<path d="{arc2}" fill="{color}" stroke="#fff" stroke-width="1"/>')
        else:
            arc_path = _svg_arc_path(cx, cy, outer_r, inner_r, start_angle, end_angle)
            arcs.append(f'<path d="{arc_path}" fill="{color}" stroke="#fff" stroke-width="1"/>')

        # 标签线（仅当占比 > 5%）
        if pct > 0.05:
            mid_angle = (start_angle + end_angle) / 2
            label_r = outer_r + 8
            label_x = cx + label_r * _cos_deg(mid_angle)
            label_y = cy + label_r * _sin_deg(mid_angle)
            text_anchor = "start" if -90 <= mid_angle < 90 else "end"
            pct_text = f"{count}项 ({pct:.0%})"
            arcs.append(
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" font-size="11" fill="#555" '
                f'text-anchor="{text_anchor}" dominant-baseline="middle">{pct_text}</text>'
            )

        legend_items.append(
            f'<div class="chart-legend-item">'
            f'<span class="chart-legend-dot" style="background:{color}"></span>'
            f'{label}：{count} 项'
            f'</div>'
        )

        start_angle = end_angle

    center_text = f'<text x="{cx}" y="{cy - 8}" font-size="22" font-weight="bold" fill="#333" text-anchor="middle">{total}</text>'
    center_text += f'<text x="{cx}" y="{cy + 14}" font-size="12" fill="#666" text-anchor="middle">总检查项</text>'

    svg = f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
    {center_text}
    {"".join(arcs)}
  </svg>'''

    legend_html = "".join(legend_items)

    return f'<div class="chart-container"><div class="chart-svg">{svg}</div><div class="chart-legend">{legend_html}</div></div>'


def _generate_bar_chart_svg(
    data: list,
    width: int = 600,
    height: int = 0,
    bar_height: int = 28,
    gap: int = 6,
) -> str:
    """生成 SVG 水平条形图。

    Args:
        data: [(标签, 不通过数, 存疑数), ...] 按不通过数降序排列
        width: SVG 宽度
        height: 自动计算（0 表示自动）
        bar_height: 每个条形的高度
        gap: 条形间距

    Returns:
        SVG 字符串
    """
    if not data:
        return ""

    data = [(label, fail, susp) for label, fail, susp in data if fail + susp > 0]
    if not data:
        return '<p style="color:#999;text-align:center;">所有分部分项均通过审核</p>'

    max_val = max(fail + susp for _, fail, susp in data)
    if max_val == 0:
        return ""

    n = len(data)
    if height == 0:
        height = n * (bar_height + gap) + 40

    label_width = 160
    bar_area_width = width - label_width - 20
    chart_height = n * (bar_height + gap)

    bars = []
    for i, (label, fail, susp) in enumerate(data):
        y = 20 + i * (bar_height + gap)
        total = fail + susp
        fail_w = (fail / max_val) * bar_area_width if max_val > 0 else 0
        susp_w = (susp / max_val) * bar_area_width if max_val > 0 else 0

        display_label = label if len(label) <= 12 else label[:11] + "…"
        bars.append(
            f'<text x="0" y="{y + bar_height / 2 + 4}" font-size="12" fill="#333" '
            f'text-anchor="start" dominant-baseline="middle">{display_label}</text>'
        )

        if fail_w > 0:
            bars.append(
                f'<rect x="{label_width}" y="{y}" width="{fail_w}" height="{bar_height}" '
                f'fill="#d93025" rx="3"/>'
            )
            if fail_w > 30:
                bars.append(
                    f'<text x="{label_width + fail_w / 2}" y="{y + bar_height / 2 + 4}" '
                    f'font-size="11" fill="#fff" text-anchor="middle" dominant-baseline="middle">{fail}</text>'
                )

        if susp_w > 0:
            bars.append(
                f'<rect x="{label_width + fail_w}" y="{y}" width="{susp_w}" height="{bar_height}" '
                f'fill="#e37400" rx="3"/>'
            )
            if susp_w > 30:
                bars.append(
                    f'<text x="{label_width + fail_w + susp_w / 2}" y="{y + bar_height / 2 + 4}" '
                    f'font-size="11" fill="#fff" text-anchor="middle" dominant-baseline="middle">{susp}</text>'
                )

        if total > 0:
            bars.append(
                f'<text x="{label_width + fail_w + susp_w + 6}" y="{y + bar_height / 2 + 4}" '
                f'font-size="11" fill="#666" dominant-baseline="middle">{total}项</text>'
            )

    svg = f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
    {"".join(bars)}
  </svg>'''

    return f'<div class="chart-container"><div class="chart-svg" style="overflow-x:auto;">{svg}</div></div>'


# ============================================================
# 建模（build_model）：纯数据变换，无 HTML
# ============================================================

def build_model(audit_log: dict, project_path: Path) -> dict:
    """从审核日志构建报告数据模型（纯数据变换）。

    Returns:
        {
          "audit_log": 原始日志,
          "doc_id_to_file": {doc_id: 文件名},
          "by_doc": {doc_id: [findings]},
          "by_subdivision": {分部分项: [findings]},
          "pie_values": {标签: 数值},
          "bar_data": [(标签, fail, susp)],
          "rule_execution_stats": [规则统计行],   # B2：断点 R3 消费
          "skill_version": "N.N",                  # B2：断点 R4 单一真相源
        }
    """
    summary = audit_log.get("summary", {})
    findings = audit_log.get("findings", [])
    tasks = audit_log.get("tasks", [])

    # 构建 doc_id → 文件名 映射
    doc_id_to_file: dict = {}
    for task in tasks:
        for doc in task.get("documents", []):
            doc_id_to_file[doc.get("id", "")] = doc.get("original_file", doc.get("id", ""))

    # 按文档分组
    by_doc: dict = {}
    for f in findings:
        by_doc.setdefault(f.get("doc_id", ""), []).append(f)

    # 按分部分项分组
    by_subdivision: dict = {}
    for f in findings:
        for task in tasks:
            if f.get("doc_id") in [d.get("id") for d in task.get("documents", [])]:
                key = task.get("sub_label", "未分类")
                if task.get("item_label"):
                    key += f" → {task['item_label']}"
                by_subdivision.setdefault(key, []).append(f)
                break

    pie_values = {
        "通过": summary.get("pass", 0),
        "不通过": summary.get("fail", 0),
        "存疑": summary.get("suspicious", 0),
        "待AI": summary.get("needs_ai", 0),
        "不适用": summary.get("not_applicable", 0),
    }

    bar_data = []
    for key, fs in by_subdivision.items():
        fl = sum(1 for f in fs if f.get("result", "") == "fail")
        s = sum(1 for f in fs if f.get("result", "") == "suspicious")
        bar_data.append((key, fl, s))
    bar_data.sort(key=lambda x: x[1] + x[2], reverse=True)

    return {
        "audit_log": audit_log,
        "doc_id_to_file": doc_id_to_file,
        "by_doc": by_doc,
        "by_subdivision": by_subdivision,
        "pie_values": pie_values,
        "bar_data": bar_data,
        # v10.4 B2：规则执行统计进报告（断点 R3：产出无人消费）
        # v10.5 修正链路断点：review_audit 把统计放在 rule_engine_summary
        # 子 dict，旧取数只读顶层导致报告该节永远为空。两处兼容。
        "rule_execution_stats": (
            audit_log.get("rule_execution_stats")
            or (audit_log.get("rule_engine_summary", {}) or {}).get(
                "rule_execution_stats", [])
            or []),
        # v10.5：无规则覆盖文档类型（本批资料里规则引擎静默跳过的类型，
        # review_audit 注入 rule_engine_summary.unguarded_doc_types）
        "unguarded_doc_types": (
            (audit_log.get("rule_engine_summary", {}) or {}).get(
                "unguarded_doc_types", [])
            or (audit_log.get("summary", {}) or {}).get(
                "unguarded_doc_types", [])
            or []),
        # v10.4 B2：版本号单一真相源（断点 R4：页脚硬编码 v7.0 漂移）
        "skill_version": _skill_version(),
    }


# ============================================================
# 渲染（render_html）：model → HTML
# ============================================================

# 结果/严重度徽标
BADGE = {"pass": "✅", "fail": "❌", "suspicious": "⚠️", "needs_ai": "🤖", "not_applicable": "➖"}
SEV_BADGE = {"high": "🔴", "medium": "🟡", "low": "⚪", "suspicious": "⚠️", "fatal": "🔴"}
SEV_LABEL = {"fatal": "严重", "high": "高", "medium": "中", "low": "低", "suspicious": "存疑",
             "Fatal": "严重", "Sanity Check": "存疑", "Best Practice": "提示"}

# 依据类型徽标（报告"依据类型"列可视化，颜色区分类型）
EVIDENCE_TYPE_LABEL = {
    "spec": "规范", "drawing": "图纸", "design_note": "设计说明",
    "notice": "通知单", "engineering_practice": "工程惯例",
}
EVIDENCE_TYPE_COLOR = {
    "spec": "#2563EB", "drawing": "#059669", "design_note": "#7C3AED",
    "notice": "#D97706", "engineering_practice": "#6C757D",
}


def _evidence_badge(etype: str) -> str:
    """依据类型的彩色徽标 HTML（未知类型回退为灰色文本）。"""
    label = EVIDENCE_TYPE_LABEL.get(etype, etype or "")
    color = EVIDENCE_TYPE_COLOR.get(etype, "#6C757D")
    if not label:
        return ""
    return (f'<span style="display:inline-block;padding:1px 8px;border-radius:10px;'
            f'font-size:12px;color:#fff;background:{color};white-space:nowrap;">{label}</span>')


def render_html(model: dict) -> str:
    """从 build_model 的产物渲染 HTML 审核报告。"""
    audit_log = model["audit_log"]
    summary = audit_log.get("summary", {})
    conclusion = audit_log.get("conclusion", {})
    findings = audit_log.get("findings", [])
    logic_findings = audit_log.get("logic_consistency_findings", [])
    force_info = audit_log.get("force_info") or {}
    force_bypass = bool(force_info.get("force_bypass_gate"))
    signature_anomalies = audit_log.get("signature_anomalies", [])
    by_doc = model["by_doc"]
    by_subdivision = model["by_subdivision"]
    doc_id_to_file = model["doc_id_to_file"]

    pie_chart_html = _generate_pie_chart_svg(model["pie_values"])
    bar_chart_html = _generate_bar_chart_svg(model["bar_data"])

    # ===== 分部分项汇总行 =====
    subdivision_rows = ""
    for key, fs in by_subdivision.items():
        p = sum(1 for f in fs if f.get("result", "") == "pass")
        fl = sum(1 for f in fs if f.get("result", "") == "fail")
        s = sum(1 for f in fs if f.get("result", "") == "suspicious")
        ai = sum(1 for f in fs if f.get("result", "") == "needs_ai")
        status = "✅" if fl == 0 and s == 0 else ("⚠️" if s > 0 else "❌")
        subdivision_rows += f"""
        <tr>
          <td>{status}</td>
          <td>{key}</td>
          <td>{len(fs)}</td>
          <td>{p}</td>
          <td>{fl}</td>
          <td>{s}</td>
          <td>{ai}</td>
        </tr>"""

    # ===== 文档级汇总行 =====
    doc_summary_rows = ""
    for doc_id, fs in by_doc.items():
        fname = doc_id_to_file.get(doc_id, doc_id)
        p = sum(1 for f in fs if f.get("result", "") == "pass")
        fl = sum(1 for f in fs if f.get("result", "") == "fail")
        s = sum(1 for f in fs if f.get("result", "") == "suspicious")
        ai = sum(1 for f in fs if f.get("result", "") == "needs_ai")
        na = sum(1 for f in fs if f.get("result", "") == "not_applicable")
        status = "✅" if fl == 0 and s == 0 else ("⚠️" if s > 0 else "❌")
        display_name = fname if len(fname) <= 50 else fname[:47] + "..."
        doc_summary_rows += f"""
        <tr>
          <td>{status}</td>
          <td title="{fname}">{display_name}</td>
          <td>{len(fs)}</td>
          <td>{p}</td>
          <td>{fl}</td>
          <td>{s}</td>
          <td>{ai}</td>
          <td>{na}</td>
        </tr>"""

    # ===== 问题清单行（v10.4 B2：新增「整改建议」列，断点 R2） =====
    non_pass_findings = [f for f in findings if f.get("result") != "pass" and f.get("result") != "not_applicable"]
    finding_rows = ""
    for f in non_pass_findings[:100]:
        sev = f.get("severity", "low")
        sev_cn = SEV_LABEL.get(sev, sev)
        result = f.get("result", "")
        doc_id = f.get("doc_id", "")
        fname = doc_id_to_file.get(doc_id, doc_id)
        display_name = fname if len(fname) <= 30 else fname[:27] + "..."
        finding_rows += f"""
        <tr>
          <td>{BADGE.get(result, '')}</td>
          <td>{SEV_BADGE.get(sev, '')} {sev_cn}</td>
          <td>{f.get('checklist_id', '')}</td>
          <td>{f.get('category', '')}</td>
          <td>{f.get('check_item', '')}</td>
          <td title="{fname}">{display_name}</td>
          <td>{f.get('finding', '')}</td>
          <td>{render_spec_cell(f)}</td>
          <td>{_evidence_badge(f.get('evidence_type', ''))}</td>
          <td style="max-width:260px;">{f.get('remediation', '') or '—'}</td>
        </tr>"""

    # ===== 规则执行统计行（v10.4 B2：断点 R3 消费） =====
    stats_rows = ""
    zero_match_count = 0
    for st in model["rule_execution_stats"]:
        matched = st.get("matched_docs", 0)
        hits = st.get("hits", 0)
        flag = "⚠️ 0 匹配" if matched == 0 else ""
        if matched == 0:
            zero_match_count += 1
        stats_rows += f"""
        <tr>
          <td>{st.get('rule_id', '')}</td>
          <td>{st.get('name', '')}</td>
          <td>{st.get('level', '')}</td>
          <td>{st.get('scope', '')}</td>
          <td>{matched}</td>
          <td>{hits}</td>
          <td>{flag or '✅'}</td>
        </tr>"""

    if model["rule_execution_stats"]:
        rule_stats_section = f"""
  <!-- 七、规则执行统计（v10.4 B2：规则覆盖透明度） -->
  <div class="section">
    <h2>七、规则执行统计</h2>
    <p style="color:#666;font-size:13px;margin-bottom:12px;">
      共加载 {len(model['rule_execution_stats'])} 条规则。
      {'<span style="color:#B45309;">⚠️ ' + str(zero_match_count) + ' 条规则 0 匹配（触发词与本次资料类型无交集，属静默失效候选，详见规则管理场景）</span>。' if zero_match_count else '全部规则均有匹配文档。'}
      matched_docs=匹配文档数，hits=命中问题数。
    </p>
    <div class="table-wrap">
    <table>
      <thead>
        <tr><th>规则ID</th><th>规则名</th><th>层级</th><th>作用域</th><th>匹配文档数</th><th>命中数</th><th>状态</th></tr>
      </thead>
      <tbody>
        {stats_rows or '<tr><td colspan="7" style="text-align:center;color:#999;">（无统计数据）</td></tr>'}
      </tbody>
    </table>
    </div>
  </div>"""
    else:
        rule_stats_section = ""

    # ===== 无规则覆盖提醒（v10.5：声明式触发的静默盲区显形） =====
    # Why: SINGLE_DOC 规则只查 trigger_when.doc_type 声明过的类型，规则库
    # 从未声明的类型（如施工日志）在规则引擎里静默跳过。审核人必须看到
    # "哪些类型本轮没有任何规则管"，否则空白永远无人知晓。
    unguarded_section = ""
    if model.get("unguarded_doc_types"):
        unguarded_rows = ""
        for u in model["unguarded_doc_types"]:
            unguarded_rows += f"""
        <tr>
          <td>{u.get('doc_type', '')}</td>
          <td>{u.get('doc_count', 0)}</td>
          <td>{u.get('note', '')}</td>
        </tr>"""
        total_ung = sum(u.get("doc_count", 0) for u in model["unguarded_doc_types"])
        unguarded_section = f"""
  <!-- 八、无规则覆盖提醒（v10.5：规则库空白显形） -->
  <div class="section">
    <h2>八、无规则覆盖提醒</h2>
    <div style="background:#fef7e0;border:1px solid #e37400;border-radius:6px;padding:12px 16px;margin-bottom:12px;color:#7c4a03;">
      <strong>⚠️ 本批资料中有 {len(model['unguarded_doc_types'])} 种文档类型（共 {total_ung} 份）没有任何规则覆盖，规则引擎对它们静默跳过。</strong><br>
      这些类型的合规性仅依赖 AI 逐条对账与人工判断，无规则引擎兜底。建议补对应规则，或确认接受裸检。
    </div>
    <div class="table-wrap">
    <table>
      <thead>
        <tr><th>文档类型</th><th>份数</th><th>说明</th></tr>
      </thead>
      <tbody>
        {unguarded_rows}
      </tbody>
    </table>
    </div>
  </div>"""

    # ===== OCR 低置信度待核实专区（v7.2 C4） =====
    ocr_review_section = ""
    ocr_review_count = summary.get("ocr_review_count", 0) or 0
    ocr_review_notice = summary.get("ocr_review_notice", "") or ""
    ocr_review_list = summary.get("ocr_review_list", []) or []
    if ocr_review_count > 0:
        ocr_rows = ""
        for item in ocr_review_list[:100]:
            orig_sev = item.get("original_severity", "") or ""
            sev_map = {"fatal": "🔴", "high": "🔴", "medium": "🟡", "low": "⚪", "suspicious": "⚠️"}
            sev_icon = sev_map.get(orig_sev.lower(), "⚪")
            rule_ref = item.get("rule_id", "") or item.get("checklist_id", "")
            ocr_rows += f"""
            <tr>
              <td title="{item.get('doc_file', '')}">{item.get('doc_file', '')}</td>
              <td>{sev_icon} {orig_sev} → ⚠️ 存疑</td>
              <td>{rule_ref}</td>
              <td>{item.get('finding', '')}</td>
              <td>{item.get('ocr_confidence', '') if item.get('ocr_confidence') is not None else ''}</td>
            </tr>"""
        ocr_review_section = f"""
  <!-- OCR 低置信度待核实专段（v7.2 C4） -->
  <div class="section">
    <h2>九、基于低置信识别需人工重点核实</h2>
    <div style="background:#fef7e0;border:1px solid #e37400;border-radius:6px;padding:12px 16px;margin-bottom:12px;color:#7c4a03;">
      <strong>⚠️ {ocr_review_notice}</strong>
    </div>
    <p style="color:#666;font-size:13px;margin-bottom:12px;">
      以下 {ocr_review_count} 项结论因源文档 OCR 置信度低于阈值已降级为「存疑」（R-18 四级结论），
      不构成确定性违规判定。请人工核实原件或重新扫描后重新审核。
    </p>
    <div class="table-wrap">
    <table>
      <thead>
        <tr><th>文档</th><th>严重度变化</th><th>规则/检查项</th><th>发现</th><th>OCR置信度</th></tr>
      </thead>
      <tbody>
        {ocr_rows or '<tr><td colspan="5" style="text-align:center;color:#999;">（无条目）</td></tr>'}
      </tbody>
    </table>
    </div>
  </div>"""

    # ===== 签字异常核查专区 =====
    signature_section = ""
    if signature_anomalies:
        sig_cards = []
        for sa in signature_anomalies:
            status = sa.get("status", "")
            severity_class = "sig-severity-high" if status == "likely_forgery" else "sig-severity-medium"
            status_label = "疑似代签" if status == "likely_forgery" else "存疑"
            status_badge = "sig-badge-high" if status == "likely_forgery" else "sig-badge-medium"
            compare_b64 = sa.get("compare_image_base64", "")
            img_html = f'<img src="data:image/png;base64,{compare_b64}" alt="签字对比图">' if compare_b64 else '<p class="sig-no-img">（对比图不可用）</p>'

            sig_cards.append(f'''
            <div class="signature-card {severity_class}">
              <div class="sig-header">
                <span class="{status_badge}">{status_label}</span>
                <span class="sig-person">签字人：{sa.get('signer', '未知')}</span>
                <span class="sim-score">相似度：{sa.get('similarity', 0):.1%}</span>
              </div>
              <div class="sig-compare">
                {img_html}
              </div>
              <div class="sig-evidence">
                <p>📄 源文件：{sa.get('doc_file', '')}</p>
                <p>📍 位置：第{sa.get('page', '?')}页</p>
                <p>🔍 规则：{sa.get('rule', '')}</p>
                <p>💡 建议：{sa.get('suggestion', '')}</p>
              </div>
            </div>
            ''')

        signature_section = f'''
  <!-- 签字异常核查专区 -->
  <div class="section">
    <h2>⚠️ 签字异常核查清单（需人工复核）</h2>
    <p style="color:#666;font-size:13px;margin-bottom:12px;">共 {len(signature_anomalies)} 个签字异常，请逐项核查</p>
    {"".join(sig_cards)}
  </div>'''

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>审核报告 — {audit_log.get('project_name', '')}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: "Microsoft YaHei", "PingFang SC", sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
  .header {{ background: #fff; padding: 30px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
  .header h1 {{ font-size: 24px; margin-bottom: 10px; }}
  .header .meta {{ color: #666; font-size: 14px; }}
  .section {{ background: #fff; padding: 24px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
  .section h2 {{ font-size: 18px; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #1a73e8; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-bottom: 20px; }}
  .stat {{ background: #f8f9fa; padding: 16px; border-radius: 6px; text-align: center; }}
  .stat .value {{ font-size: 28px; font-weight: bold; color: #1a73e8; }}
  .stat .label {{ font-size: 12px; color: #666; margin-top: 4px; }}
  .stat.fail .value {{ color: #d93025; }}
  .stat.suspicious .value {{ color: #e37400; }}
  .stat.ai .value {{ color: #9334e6; }}
  .stat.warn .value {{ color: #e37400; }}
  .filter-bar {{ margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap; }}
  .filter-bar button {{ padding: 6px 14px; border: 1px solid #ddd; border-radius: 20px; background: #fff; cursor: pointer; font-size: 13px; }}
  .filter-bar button:hover {{ background: #e8f0fe; border-color: #1a73e8; }}
  .filter-bar button.active {{ background: #1a73e8; color: #fff; border-color: #1a73e8; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #e8eaed; }}
  th {{ background: #f8f9fa; font-weight: 600; white-space: nowrap; position: sticky; top: 0; }}
  tr:hover {{ background: #e8f0fe; }}
  .table-wrap {{ max-height: 500px; overflow-y: auto; border: 1px solid #e8eaed; border-radius: 4px; }}
  .table-wrap table {{ border: none; }}
  .conclusion {{ padding: 20px; border-radius: 8px; margin-bottom: 16px; }}
  .conclusion.pass {{ background: #e6f4ea; border: 1px solid #34a853; }}
  .conclusion.fail {{ background: #fce8e6; border: 1px solid #d93025; }}
  .conclusion.suspicious {{ background: #fef7e0; border: 1px solid #e37400; }}
  .conclusion h3 {{ font-size: 16px; margin-bottom: 8px; }}
  .rec {{ padding: 8px 12px; background: #f8f9fa; border-left: 3px solid #1a73e8; margin-bottom: 8px; font-size: 14px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
  .badge-fail {{ background: #fce8e6; color: #d93025; }}
  .badge-suspicious {{ background: #fef7e0; color: #e37400; }}
  .badge-ai {{ background: #f3e8fd; color: #9334e6; }}
  .chart-container {{ display: flex; align-items: center; gap: 24px; margin: 16px 0; flex-wrap: wrap; }}
  .chart-svg {{ flex-shrink: 0; }}
  .chart-legend {{ display: flex; flex-direction: column; gap: 6px; }}
  .chart-legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 13px; color: #555; }}
  .chart-legend-dot {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }}
  .charts-row {{ display: flex; gap: 24px; flex-wrap: wrap; align-items: flex-start; }}
  .charts-row .chart-container {{ flex: 1; min-width: 300px; }}
  @media print {{ body {{ background: #fff; }} .section {{ box-shadow: none; border: 1px solid #ddd; }} }}
  .force-watermark {{ background: #fce8e6; border: 2px dashed #d93025; color: #d93025; padding: 14px 18px; border-radius: 6px; margin-bottom: 16px; font-weight: bold; text-align: center; }}
  .force-watermark .sub {{ font-weight: normal; font-size: 13px; color: #b31412; margin-top: 4px; }}
    /* 签字异常专区 */
    .signature-card {{
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
      background: #fff;
    }}
    .signature-card.sig-severity-high {{
      border-color: #dc2626;
      border-left: 4px solid #dc2626;
      background: #fef2f2;
    }}
    .signature-card.sig-severity-medium {{
      border-color: #f59e0b;
      border-left: 4px solid #f59e0b;
      background: #fffbeb;
    }}
    .sig-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .sig-badge-high {{
      background: #dc2626;
      color: #fff;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: bold;
    }}
    .sig-badge-medium {{
      background: #f59e0b;
      color: #fff;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: bold;
    }}
    .sig-person {{ font-weight: 600; }}
    .sim-score {{ color: #666; font-size: 13px; }}
    .sig-compare {{ margin: 12px 0; text-align: center; }}
    .sig-compare img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 4px; }}
    .sig-evidence {{ font-size: 13px; color: #444; line-height: 1.8; }}
    .sig-evidence p {{ margin: 2px 0; }}
    .sig-no-img {{ color: #999; font-style: italic; }}
</style>
</head>
<body>
<div class="container">

  <!-- 页眉 -->
  <div class="header">
    {f'<div class="force-watermark">⚠️ 跳过人工核对闸门生成，非正式审核结果<div class="sub">跳过时间：{force_info.get("bypassed_at", "")} | 未核对文件数：{len(force_info.get("unverified_files", []))}</div></div>' if force_bypass else ''}
    <h1>民航施工资料合规审核报告</h1>
    <div class="meta">
      <p>项目：{audit_log.get('project_name', '')}</p>
      <p>审核编号：{audit_log.get('audit_id', '')} | 审核时间：{audit_log.get('audit_completed_at', '')}</p>
      <p>前置条件：阶段={audit_log.get('preconditions', {}).get('stage', '')} | 资料性质={audit_log.get('preconditions', {}).get('nature', '')} | 范围={audit_log.get('preconditions', {}).get('scope', '')} | 签字检查={'是' if audit_log.get('signature_anomalies') is not None else '否'}</p>
    </div>
  </div>

  <!-- 一、审核概要（第一层·结论） -->
  <div class="section">
    <h2>一、审核概要</h2>
    <div class="stats">
      <div class="stat"><div class="value">{summary.get('documents_audited', 0)}</div><div class="label">审核文档数</div></div>
      <div class="stat"><div class="value">{summary.get('total_findings', 0)}</div><div class="label">总检查项</div></div>
      <div class="stat"><div class="value">{summary.get('pass', 0)}</div><div class="label">✅ 通过</div></div>
      <div class="stat fail"><div class="value">{summary.get('fail', 0)}</div><div class="label">❌ 不通过</div></div>
      <div class="stat suspicious"><div class="value">{summary.get('suspicious', 0)}</div><div class="label">⚠️ 存疑</div></div>
      <div class="stat ai"><div class="value">{summary.get('needs_ai', 0)}</div><div class="label">🤖 待AI</div></div>
      <div class="stat"><div class="value">{summary.get('not_applicable', 0)}</div><div class="label">➖ 不适用</div></div>
    </div>

    {pie_chart_html}

    <div class="conclusion {'fail' if '不合格' in conclusion.get('overall', '') else ('pass' if '合格' in conclusion.get('overall', '') else 'suspicious')}">
      <h3>总体结论</h3>
      <p>{conclusion.get('overall', '')}</p>
    </div>

    <h3>整改建议</h3>
    {"".join(f'<div class="rec">{r}</div>' for r in conclusion.get('recommendations', [])) or '<p>无</p>'}
  </div>

  <!-- 二、文档级审核汇总 -->
  <div class="section">
    <h2>二、文档审核汇总</h2>
    <p style="color:#666;font-size:13px;margin-bottom:12px;">共 {len(by_doc)} 份文档，按检查项数降序排列</p>
    <div class="table-wrap">
    <table>
      <thead>
        <tr><th>状态</th><th>文档</th><th>检查项</th><th>通过</th><th>不通过</th><th>存疑</th><th>待AI</th><th>不适用</th></tr>
      </thead>
      <tbody>
        {doc_summary_rows}
      </tbody>
    </table>
    </div>
  </div>

  <!-- 三、分部分项审核汇总 -->
  <div class="section">
    <h2>三、分部分项审核汇总</h2>
    {bar_chart_html}
    <div class="table-wrap">
    <table>
      <thead>
        <tr><th>状态</th><th>分部分项</th><th>检查项</th><th>通过</th><th>不通过</th><th>存疑</th><th>待AI</th></tr>
      </thead>
      <tbody>
        {subdivision_rows}
      </tbody>
    </table>
    </div>
  </div>

  <!-- 四、规范对账发现（第二层·问题：快速找问题和依据） -->
  <div class="section">
    <h2>四、规范对账发现（需关注项）</h2>
    <p style="color:#666;font-size:13px;margin-bottom:12px;">
      共 <span class="badge badge-fail">{summary.get('fail', 0)} 项不通过</span>
      <span class="badge badge-suspicious">{summary.get('suspicious', 0)} 项存疑</span>
      <span class="badge badge-ai">{summary.get('needs_ai', 0)} 项待AI</span>
      {"（仅显示前 100 条，完整数据见审核日志 JSON）" if len(non_pass_findings) > 100 else ""}
    </p>
    <div class="table-wrap">
    <table>
      <thead>
        <tr><th>结果</th><th>严重</th><th>编号</th><th>类别</th><th>检查项</th><th>文档</th><th>发现</th><th>规范</th><th>依据类型</th><th>整改建议</th></tr>
      </thead>
      <tbody>
        {finding_rows or '<tr><td colspan="10" style="text-align:center;color:#999;">（无需要关注的问题）</td></tr>'}
      </tbody>
    </table>
    </div>
  </div>

  <!-- 五、逻辑一致性检查 -->
  <div class="section">
    <h2>五、逻辑一致性检查</h2>
    <div class="table-wrap">
    <table>
      <thead>
        <tr><th>编号</th><th>类别</th><th>检查项</th><th>规则</th><th>发现</th></tr>
      </thead>
      <tbody>
        {"".join(f'''<tr><td>{f.get('checklist_id', '')}</td><td>{f.get('category', '')}</td><td>{f.get('check_item', '')}</td><td style="max-width:300px;">{f.get('criteria', '')}</td><td>{f.get('finding', '')}</td></tr>''' for f in logic_findings)}
      </tbody>
    </table>
    </div>
  </div>

  {rule_stats_section}

  {unguarded_section}

  {ocr_review_section}

  <!-- 页脚（第三层·行动收尾） -->
  <div class="section" style="text-align:center;color:#999;font-size:12px;">
    <p>本报告由民航施工资料合规审核 Skill v{model['skill_version']} 自动生成</p>
    <p>审核编号：{audit_log.get('audit_id', '')} | 生成时间：{datetime.now().isoformat(timespec='seconds')}</p>
    <p>铁律 R-08：未发现问题的项目不代表"全部合格"，仅表示"未发现不符合项"</p>
  </div>

  {signature_section}

</div>
</body>
</html>"""
    return html
