# -*- coding: utf-8 -*-
"""
test_regression_hazards.py — 隐患销号回归套件（Hazards Regression Suite）
==========================================================================
背景：v9.5 长会话多轮诊断查实的根因，逐条固化为测试（隐患登记）。
约定：本套件**先红后绿** —— 红表示隐患存在，修复后变绿（销号），
     测试永久保留防复发。任何代码改动必须保证本套件全绿。

测试数据形态对齐真实管道：字段值为字符串（含空串 ""），
而非手工构造的 None —— 旧套件只测 None 形态导致空串类 bug 长期漏网。

隐患清单（Hazard Registry）：
  H-1 日期标点归一化：顿号/逗号/句点变体日期（如 `2026、4.22`）不得悬空
      （值在库、build 未标疑、推断/展示判非法显示空 —— 三层打架）
  H-2 部位关键词漏网：乱码部位含"碎石/桩"关键字不得因子串命中而免检
      H-2a 跨表互斥：同文档互异部位过多即矛盾信号，应产出存疑
      H-2b 白名单判定：is_legal_loc 必须按区名白名单判，不按子串
  H-3 空串类缺失：空串必须与 None 同等触发数学链推断（类缺失谓词）
  H-4 表级字段邻表推断：部位/日期整表同值、表内无参考时走邻表通道
      （门控：日期相近 + 桩号区段连续）
  H-5 pending 完整性重算：recalc_pending 全量重扫生成应疑清单
  H-6 双份 rows 一致性守卫：structured_rows 与 rows 并存时必须同步
  H-7 干净数据零误报（golden 守卫）：合法数据经规则后不得新增存疑/建议
  H-8 视觉复核断链（v9.7）：第二类资料（扫描转化电子文档）存疑清单
      从未接入 verify_fields 复核器；merge 中文字段错位新建键；
      merge 只写 rows 单份造成双份分叉；docx 无裁图能力

用法：
    pytest scripts/test_regression_hazards.py -v
"""

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import data_quality_check as dqc


# ========== 公共 fixture ==========

ZONE_WHITELIST = ["碎石桩边一区", "碎石桩边二区", "碎石桩边三区",
                  "碎石桩边四区", "碎石桩边五区"]


def _pile_row(table, pile_no, **kwargs):
    """构造一行真实管道形态的碎石桩数据（全字符串）"""
    row = {
        "table": table,
        "loc": "碎石桩边三区",
        "date_raw": "2026.4.20",
        "pile_no": str(pile_no),
        "design_length": "20.0",
        "diameter": "0.6",
        "bottom_elev": "2083.70",
        "top_elev": "2103.70",
        "actual_length": "20.0",
        "current": "160",
        "re_penetration": "27",
        "volume": "8.06",
        "filling_coeff": "1.46",
        "verticality": "0.3",
    }
    row.update(kwargs)
    return row


# ========== H-1 日期标点归一化 ==========

class TestH1DatePunctNormalization:
    """隐患 H-1：WPS OCR 产出顿号/逗号/句点日期变体，三层判定打架成悬空态"""

    def test_normalize_dunhao(self):
        """顿号 → 点：`2026、4.22` 归一为 `2026.4.22`"""
        assert dqc.normalize_date_punct("2026、4.22") == "2026.4.22"

    def test_normalize_fullwidth_comma(self):
        """全角逗号 → 点"""
        assert dqc.normalize_date_punct("2026，4.22") == "2026.4.22"

    def test_normalize_period_tail(self):
        """句点尾缀 → 点"""
        assert dqc.normalize_date_punct("2026。4.22") == "2026.4.22"

    def test_normalize_keeps_legal_date(self):
        """合法日期原样返回，不被破坏"""
        assert dqc.normalize_date_punct("2026.4.22") == "2026.4.22"

    def test_infer_triggers_on_dunhao_date(self):
        """顿号日期归一后自身合法 → 不再需要邻行补齐建议（不得静默丢信息，
        也不得把能自证的值降级为建议值）。悬空态守卫由 H-5 recalc 承接：
        归一后合法 → 不进应疑清单。"""
        data = {"doc_type": "碎石桩施工记录", "structured_rows": [
            _pile_row(0, 500, date_raw="2026、4.22"),
            _pile_row(0, 501, date_raw="2026.4.22"),
        ]}
        result = dqc.infer_values(data)
        row_inf = result["row_inferred"].get("1", {})
        assert "date_raw" not in row_inf, (
            "归一化后 `2026、4.22` 自身合法，不应产出补齐建议"
            "（修复前是判非法→邻行补齐的权宜行为）")


# ========== H-2 部位关键词漏网 ==========

class TestH2LocKeywordLeak:
    """隐患 H-2：乱码部位含"碎石/桩"关键字，因子串命中 legal_pattern 免检，
    会当真值流进审核报告（pending 漏网 → G-1.9 闸门失守）"""

    def test_h2a_cross_table_mutex(self):
        """跨表互斥：同文档互异部位远超合理分区数 → 应产出部位存疑"""
        # 8 张表 8 种互异"看似合法"部位 —— 真实工程一个分项不会有 8 个区
        rows = []
        fake_locs = ["碎石机区", "碎石说区", "碎石柱飞", "碎石推证",
                     "研石桩区", "碎石桩边三区", "碎石边区", "碎石桩区"]
        for t, loc in enumerate(fake_locs):
            for p in range(3):
                rows.append(_pile_row(t, 500 + t * 3 + p, loc=loc))
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows}
        pending = dqc.recalc_pending(data)
        loc_pending = [p for p in pending if p.get("field") in ("施工部位", "loc")]
        assert loc_pending, "8 种互异部位应触发跨表互斥存疑，当前漏网"

    def test_h2b_whitelist_rejects_lookalike(self):
        """白名单判定：`碎石机区` 不在白名单 → 非法（旧子串逻辑会放行）"""
        assert dqc.is_legal_loc("碎石机区", whitelist=ZONE_WHITELIST) is False

    def test_h2b_whitelist_accepts_real(self):
        """白名单判定：真实区名 → 合法"""
        assert dqc.is_legal_loc("碎石桩边三区", whitelist=ZONE_WHITELIST) is True

    def test_h2b_whitelist_none_degrades_to_pattern(self):
        """白名单缺失时退化为子串判定（向后兼容，但 recalc 须用互斥兜底）"""
        # 退化行为本身允许（防 DOC-001 类存量误伤），但函数必须存在且不炸
        assert dqc.is_legal_loc("碎石桩边三区", whitelist=None) in (True, False)


# ========== H-3 空串类缺失 ==========

class TestH3EmptyStringMissing:
    """隐患 H-3：`"" is not None` 为 True，空串被当"有值"，数学链推断全灭。
    真实管道缺失形态是空串（见 Hard Constraints：None 统一替换为 ''）"""

    def test_empty_string_bottom_elev_infers(self):
        """bottom_elev="" 且 top/length 在 → INF-003 应产出推断"""
        data = {"doc_type": "碎石桩施工记录", "structured_rows": [
            _pile_row(0, 500, bottom_elev="", top_elev="2103.70", actual_length="20.0"),
        ]}
        result = dqc.infer_values(data)
        row_inf = result["row_inferred"].get("1", {})
        assert "bottom_elev" in row_inf, (
            "空串 bottom_elev 应触发 INF-003 数学链推断，当前被 is not None 挡死")

    def test_empty_string_filling_coeff_infers(self):
        """filling_coeff="" 且 volume/diameter/length 在 → INF-004 应产出推断"""
        data = {"doc_type": "碎石桩施工记录", "structured_rows": [
            _pile_row(0, 500, filling_coeff=""),
        ]}
        result = dqc.infer_values(data)
        row_inf = result["row_inferred"].get("1", {})
        assert "filling_coeff" in row_inf, "空串 filling_coeff 应触发 INF-004"

    def test_pure_symbol_value_infers(self):
        """纯符号值（如 fill=","）等同缺失 → 应触发推断"""
        data = {"doc_type": "碎石桩施工记录", "structured_rows": [
            _pile_row(0, 500, filling_coeff=","),
        ]}
        result = dqc.infer_values(data)
        row_inf = result["row_inferred"].get("1", {})
        assert "filling_coeff" in row_inf, "纯符号 `,` 应按类缺失触发推断"

    def test_is_missing_predicate(self):
        """统一类缺失谓词：None/空串/纯符号 → True；正常值 → False"""
        assert dqc.is_missing(None) is True
        assert dqc.is_missing("") is True
        assert dqc.is_missing("  ") is True
        assert dqc.is_missing(",") is True
        assert dqc.is_missing("了") is True   # 单个无法解析的乱字
        assert dqc.is_missing("2083.70") is False
        assert dqc.is_missing("碎石桩边三区") is False


# ========== H-4 表级字段邻表推断 ==========

class TestH4TableLevelFieldInference:
    """隐患 H-4：部位/日期是表级字段（一页一写、整表同值），
    表内永远无参考 → 邻行/众数推断架构性死区，应走邻表通道"""

    def test_neighbor_table_loc_suggestion(self):
        """表0 部位全乱码、表1（相邻日期+连续桩号）部位合法 → 邻表建议"""
        rows = []
        # 表0：日期 2026.4.21，桩 500-502，部位整表乱码
        for p in range(500, 503):
            rows.append(_pile_row(0, p, loc="不干就记", date_raw="2026.4.21"))
        # 表1：日期 2026.4.21（同日），桩 503-505 连续，部位合法
        for p in range(503, 506):
            rows.append(_pile_row(1, p, loc="碎石桩边三区", date_raw="2026.4.21"))
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows}
        result = dqc.infer_values(data)
        row1 = result["row_inferred"].get("1", {})
        assert "loc" in row1, (
            "表0 部位整表乱码时应从邻表（日期相近+桩号连续）取建议值")
        assert row1["loc"]["value"] == "碎石桩边三区"
        assert row1["loc"].get("suggested_only") is True

    def test_neighbor_table_gated_by_pile_gap(self):
        """桩号断档（表1 桩号 800+，与表0 500 段不连续）→ 不得跨表取值"""
        rows = []
        for p in range(500, 503):
            rows.append(_pile_row(0, p, loc="不干就记", date_raw="2026.4.21"))
        for p in range(800, 803):
            rows.append(_pile_row(1, p, loc="碎石桩边一区", date_raw="2026.4.21"))
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows}
        result = dqc.infer_values(data)
        row1 = result["row_inferred"].get("1", {})
        assert "loc" not in row1, "桩号断档时跨表取值 = 污染，必须被门控拦下"

    def test_neighbor_table_gated_by_date_jump(self):
        """日期跳变（表1 日期晚 10 天）→ 不得跨表取值"""
        rows = []
        for p in range(500, 503):
            rows.append(_pile_row(0, p, loc="不干就记", date_raw="2026.4.10"))
        for p in range(503, 506):
            rows.append(_pile_row(1, p, loc="碎石桩边一区", date_raw="2026.4.25"))
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows}
        result = dqc.infer_values(data)
        row1 = result["row_inferred"].get("1", {})
        assert "loc" not in row1, "日期跳变 10 天时跨表取值 = 污染，必须被门控拦下"


# ========== H-5 pending 完整性重算 ==========

class TestH5PendingRecalc:
    """隐患 H-5：G-1.9 闸门只认 pending 清空，但 pending 生成有漏。
    必须能全量重扫 structured_rows 生成应疑清单，供与存量 pending 比对补漏"""

    def test_recalc_pending_exists_and_returns_list(self):
        data = {"doc_type": "碎石桩施工记录", "structured_rows": [
            _pile_row(0, 500),
        ]}
        pending = dqc.recalc_pending(data)
        assert isinstance(pending, list)

    def test_recalc_flags_unparseable_number(self):
        """数值不可解析（filling_coeff=『了』）→ 应疑"""
        data = {"doc_type": "碎石桩施工记录", "structured_rows": [
            _pile_row(0, 500, filling_coeff="了"),
        ]}
        pending = dqc.recalc_pending(data)
        fields = [p.get("field") for p in pending]
        assert "filling_coeff" in fields or "充盈系数" in fields

    def test_recalc_flags_lookalike_loc(self):
        """乱码部位（含关键字蒙混型）→ 应疑"""
        data = {"doc_type": "碎石桩施工记录", "structured_rows": [
            _pile_row(0, 500, loc="碎石机区"),
        ]}
        pending = dqc.recalc_pending(data)
        fields = [p.get("field") for p in pending]
        assert any(f in ("loc", "施工部位") for f in fields), (
            "碎石机区 应被 recalc 捞出（互斥/白名单任一通道）")

    def test_recalc_flags_broken_date(self):
        """残形日期 → 应疑"""
        data = {"doc_type": "碎石桩施工记录", "structured_rows": [
            _pile_row(0, 500, date_raw="026.4.20"),
        ]}
        pending = dqc.recalc_pending(data)
        fields = [p.get("field") for p in pending]
        assert any(f in ("date_raw", "施工日期") for f in fields)

    def test_recalc_normalized_dunhao_date_not_flagged(self):
        """顿号日期归一后合法 → 不应疑（防止归一化把好数据打疑）"""
        data = {"doc_type": "碎石桩施工记录", "structured_rows": [
            _pile_row(0, 500, date_raw="2026、4.22"),
        ]}
        pending = dqc.recalc_pending(data)
        date_flags = [p for p in pending
                      if p.get("field") in ("date_raw", "施工日期")]
        assert not date_flags, "2026、4.22 归一后合法，不应进应疑清单"


# ========== H-6 双份 rows 一致性守卫 ==========

class TestH6DualRowsConsistency:
    """隐患 H-6：结构化文件同时存 structured_rows 与 rows 两份。
    消费方写落库时若只写一份 → 静默分叉。需守卫函数供写入路径调用"""

    def test_consistent_dual_rows_pass(self):
        rows = [_pile_row(0, 500), _pile_row(0, 501)]
        data = {"structured_rows": rows, "rows": [dict(r) for r in rows]}
        issues = dqc.check_dual_rows(data)
        assert issues == []

    def test_inconsistent_dual_rows_flagged(self):
        rows = [_pile_row(0, 500), _pile_row(0, 501)]
        rows2 = [dict(r) for r in rows]
        rows2[0]["loc"] = "被篡改的值"
        data = {"structured_rows": rows, "rows": rows2}
        issues = dqc.check_dual_rows(data)
        assert issues, "两份 rows 分叉必须被守卫发现"

    def test_single_rows_no_crash(self):
        """只有 structured_rows、无 rows 块 → 不报错不误报（历史文件兼容）"""
        data = {"structured_rows": [_pile_row(0, 500)]}
        issues = dqc.check_dual_rows(data)
        assert issues == []


# ========== H-7 干净数据零误报（golden 守卫） ==========

class TestH7CleanDataZeroFalsePositive:
    """隐患 H-7：新规则（归一化/互斥/邻表）上线后，
    对本来正确的数据必须零新增误报 —— 否则规则本身成了新污染源"""

    def test_clean_doc_no_pending(self):
        """干净 3 行表（区名在白名单、日期合法、数值自洽）→ 应疑清单为空"""
        rows = [_pile_row(0, 500), _pile_row(0, 501), _pile_row(0, 502)]
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows}
        pending = dqc.recalc_pending(data)
        assert pending == [], f"干净数据被误报: {pending}"

    def test_clean_doc_no_text_suggestions(self):
        """干净表（部位合法、日期合法）→ 不得产出文本建议值"""
        rows = [_pile_row(0, 500), _pile_row(0, 501)]
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows}
        result = dqc.infer_values(data)
        for _, fields in (result.get("row_inferred") or {}).items():
            assert "loc" not in fields, "合法部位被产出建议 = 误报"
            assert "date_raw" not in fields, "合法日期被产出建议 = 误报"


# ========== H-5/H-6 管道接线（wiring）==========
# 隐患登记（2026-08-19 独立复核 F1）：recalc_pending / check_dual_rows 曾只有
# 测试调用、生产管道零消费方 —— "函数已建、测试已锁、管道未接线"的半成品。
# 本组测试跑真实管道（chat_verify_apply 闸门 / run_all 全量检测）验证接线生效。

class TestH5H6PipelineWiring:
    """接线型测试：不直调函数，跑管道验证补漏/守卫真的发生"""

    def _make_base(self, tmp_path, pending_items, rows_mutator=None):
        """搭最小数据底座：index.json + 单文档数据文件，返回路径"""
        import json as _json
        import chat_verify_apply as cva
        base = tmp_path / "数据底座"
        rel = "通用资料/碎石桩施工记录/wiring_test.json"
        rows = [_pile_row(0, 500), _pile_row(0, 501)]
        if rows_mutator:
            rows_mutator(rows)
        data = {
            "doc_type": "碎石桩施工记录",
            "structured_rows": rows,
            "rows": [dict(r) for r in rows],
            "pending_verification": list(pending_items),
        }
        data_file = base / rel
        data_file.parent.mkdir(parents=True, exist_ok=True)
        data_file.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        index = {"documents": [{
            "id": "DOC-W1", "original_file": "wiring_test", "doc_type": "碎石桩施工记录",
            "data_file": rel, "pending_verification": list(pending_items),
            "human_verified": False,
        }]}
        (base / "index.json").write_text(_json.dumps(index, ensure_ascii=False), encoding="utf-8")
        return tmp_path, base, cva

    def test_confirm_blocks_on_recalc_leak(self, tmp_path, capsys, monkeypatch):
        """H-5 接线：pending 已清空但数据仍有烂值（生成期漏登）→ confirm 必须挡下。

        场景取 DOC-002 真实漏网形态：OCR 残形日期（归一化后仍非法）+ 乱码部位，
        旧生成期规则未登入 pending —— 闸门若只认 pending 清空，漏网项当真值进报告。
        （注：顿号日期 `2026、4.20` 经 H-1 归一化已合法，不再是漏网形态，故不用于本测试）
        """
        def mutate(rows):
            for r in rows:
                r["date_raw"] = "026..22"      # OCR 残形日期（年首字丢失，归一化救不回）
                r["loc"] = "砰石松三飞"         # 乱码部位（旧子串判定漏网）
        project_dir, base, cva = self._make_base(tmp_path, pending_items=[], rows_mutator=mutate)
        monkeypatch.chdir(project_dir)
        import argparse as _ap
        rc = cva.cmd_confirm(_ap.Namespace(
            project_dir=str(project_dir), out=None, doc="DOC-W1",
            original_file=None, force=False, confirm_classification=False))
        out = capsys.readouterr().out
        assert rc == 1, "漏网项存在时 confirm 放行 = G-1.9 闸门失效"
        assert "recalc_missing" in out and "漏网" in out, "blocked 输出未披露漏网项"

    def test_confirm_passes_when_data_clean(self, tmp_path, capsys, monkeypatch):
        """H-5 接线反向：pending 空 + 重扫也干净 → confirm 正常放行（不误伤）"""
        project_dir, base, cva = self._make_base(tmp_path, pending_items=[])
        monkeypatch.chdir(project_dir)
        import argparse as _ap
        rc = cva.cmd_confirm(_ap.Namespace(
            project_dir=str(project_dir), out=None, doc="DOC-W1",
            original_file=None, force=False, confirm_classification=False))
        out = capsys.readouterr().out
        assert rc == 0, f"干净数据被误挡: {out}"
        assert '"human_verified": true' in out

    def test_run_all_reports_dual_rows_divergence(self):
        """H-6 接线：structured_rows 与 rows 分叉 → run_all 必须产出 DQ-SELF-DUAL-01"""
        rows = [_pile_row(0, 500), _pile_row(0, 501)]
        rows2 = [dict(r) for r in rows]
        rows2[0]["top_elev"] = "9999.99"   # 篡改一份
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows, "rows": rows2}
        checker = dqc.DataQualityChecker(data)
        result = checker.run_all()
        codes = [w["code"] for w in result["warnings"]]
        assert "DQ-SELF-DUAL-01" in codes, "双份分叉未进 run_all 告警 = 接线失效"

    def test_run_all_clean_dual_rows_no_warning(self):
        """H-6 接线反向：双份一致 → 不产出 DQ-SELF-DUAL-01（零误报）"""
        rows = [_pile_row(0, 500), _pile_row(0, 501)]
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows,
                "rows": [dict(r) for r in rows]}
        checker = dqc.DataQualityChecker(data)
        result = checker.run_all()
        codes = [w["code"] for w in result["warnings"]]
        assert "DQ-SELF-DUAL-01" not in codes, "双份一致仍告警 = 误报"


# ========== H-8 视觉复核断链（v9.7）==========
# 隐患登记：第二类资料（扫描转化电子文档）的存疑清单（confusion+pending）
# 从未接入 verify_fields 复核器（断链）；merge_results 中文字段错位新建键、
# 只写 rows 单份（H-6 分叉活体）；crop 不支持 docx 内嵌图。

def _make_docx(path, n_images=2):
    """构造最小 docx：n 张 PNG 内嵌图按序引用（模拟 WPS 扫描件转 docx）"""
    import io
    import zipfile
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (80, 40), color=(180, 180, 180)).save(buf, format="PNG")
    png = buf.getvalue()

    rels_items, doc_parts = [], []
    for i in range(1, n_images + 1):
        rels_items.append(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/image" Target="media/image{i}.png"/>')
        doc_parts.append(f'<w:r><w:drawing><a:blip r:embed="rId{i}"/></w:drawing></w:r>')
    ct = ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
          'package/2006/content-types"><Default Extension="png" ContentType="image/png"/></Types>')
    rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships">' + "".join(rels_items) + "</Relationships>")
    doc = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           'wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
           'officeDocument/2006/relationships"><w:body>'
           + "".join(doc_parts) + "</w:body></w:document>")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", ct)
        zf.writestr("word/document.xml", doc)
        zf.writestr("word/_rels/document.xml.rels", rels)
        for i in range(1, n_images + 1):
            zf.writestr(f"word/media/image{i}.png", png)
    return str(path)


class TestH8VisionVerifyChain:
    """H-8：第二类资料的视觉复核全链（docx裁图→合流→merge落库）"""

    def test_extract_docx_media_in_document_order(self, tmp_path):
        """docx 内嵌图按 document.xml 引用顺序提取（页序=图序）"""
        import verify_fields as vf
        docx = _make_docx(tmp_path / "scan.docx", n_images=3)
        vf._DOCX_MEDIA_CACHE.clear()
        media = vf._extract_docx_media(docx)
        assert len(media) == 3, "内嵌图数量不符"
        assert all(Path(p).exists() for p in media), "提取文件缺失"

    def test_crop_docx_page(self, tmp_path):
        """crop_field_region 支持 docx：表 t → 第 t+1 张整页图"""
        import verify_fields as vf
        docx = _make_docx(tmp_path / "scan2.docx", n_images=2)
        vf._DOCX_MEDIA_CACHE.clear()
        out = vf.crop_field_region(docx, page_num=2, out_path=str(tmp_path / "p2.png"))
        assert Path(out).exists() and Path(out).stat().st_size > 0
        with pytest.raises(ValueError):
            vf.crop_field_region(docx, page_num=3, out_path=str(tmp_path / "p3.png"))

    def test_suspects_from_pending_maps_fields(self):
        """pending 表级存疑 → suspects：中文字段映射行键、page=表序+1、带推荐值"""
        import verify_fields as vf
        rows = [
            _pile_row(0, 500, loc="研工组三区", date_raw="026.4.20"),
            _pile_row(0, 501, loc="研工组三区", date_raw="026.4.20"),
            _pile_row(1, 502, loc="午之区", date_raw="2026.4.21"),
        ]
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows,
                "pending_verification": [
                    {"table": 0, "field": "施工部位", "raw": "研工组三区", "reason": "乱码"},
                    {"table": 0, "field": "施工日期", "raw": "026.4.20", "reason": "残形"},
                    {"table": 1, "field": "施工部位", "raw": "午之区", "reason": "乱码"},
                ]}
        suggestions = {"1": {"loc": {"value": "碎石桩边三区", "confidence": 0.6}}}
        out = vf.suspects_from_pending(data, suggestions)
        assert len(out) == 3
        by_key = {(s["table"], s["field"]): s for s in out}
        assert (0, "loc") in by_key and (0, "date_raw") in by_key, "中文字段未映射为行键"
        assert by_key[(0, "loc")]["page"] == 1 and by_key[(1, "loc")]["page"] == 2, \
            "page 应为表序+1（docx 图序）"
        assert by_key[(0, "loc")]["scope"] == "table"
        assert by_key[(0, "loc")]["suspected_value"] == "碎石桩边三区", "推荐值未带上"
        assert by_key[(0, "loc")]["row"] == 1 and by_key[(1, "loc")]["row"] == 3, \
            "row 应为该表首行全局行号（1-based）"

    def test_prepare_merges_confusion_and_pending(self, tmp_path):
        """prepare 合流两套清单：confusion 行级 + pending 表级，且不重复"""
        import verify_fields as vf
        docx = _make_docx(tmp_path / "scan3.docx", n_images=2)
        vf._DOCX_MEDIA_CACHE.clear()
        rows = [_pile_row(0, 500, loc="研工组三区"), _pile_row(1, 501, loc="午之区")]
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows,
                "pending_verification": [
                    {"table": 0, "field": "施工部位", "raw": "研工组三区", "reason": "乱码"}]}
        confusion = {"suspects": [
            {"code": "OCR-Z-02", "field": "桩号", "row": 1, "ocr_value": "Z500",
             "suspected_value": "2500", "reason": "2→Z", "confidence": "medium", "page": 1}]}
        result = vf.prepare_verify_tasks(docx, confusion, data, str(tmp_path / "vo"))
        assert result["status"] == "prepared"
        fields = [(t["field"], t["scope"]) for t in result["tasks"]]
        assert ("pile_no", "row") in fields, "confusion 行级任务丢失"
        assert ("loc", "table") in fields, "pending 表级任务丢失"

    def test_merge_table_scope_writes_both_lists(self):
        """merge 表级任务：整表写入 + structured_rows/rows 双份同步（H-6 分叉活体修复）"""
        import verify_fields as vf
        rows = [_pile_row(0, 500, loc="研工组三区"), _pile_row(0, 501, loc="研工组三区"),
                _pile_row(1, 502, loc="午之区")]
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows,
                "rows": [dict(r) for r in rows]}
        tasks = {"tasks": [{"task_id": "VERIFY-001", "field": "loc", "row": 1,
                            "table": 0, "scope": "table", "page": 1}]}
        results = {"results": [{"task_id": "VERIFY-001", "verified_value": "碎石桩边三区",
                                 "confidence": "high", "note": "图清晰"}]}
        vf.merge_results(results, data, tasks=tasks)
        for lst in (data["structured_rows"], data["rows"]):
            assert lst[0]["loc"] == "碎石桩边三区" and lst[1]["loc"] == "碎石桩边三区", \
                "表级任务未写整表"
            assert lst[2]["loc"] == "午之区", "越表污染（表1被误写）"
            assert "桩号" not in lst[0] and "_verify_notes" in lst[0], "留痕缺失"

    def test_merge_field_alias_cn_to_en(self):
        """merge 中文字段（confusion 产）必须映射英文行键，不得新建中文键"""
        import verify_fields as vf
        rows = [_pile_row(0, 500)]
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows, "rows": [dict(r) for r in rows]}
        tasks = {"tasks": [{"task_id": "VERIFY-001", "field": "桩号", "row": 1,
                            "table": None, "scope": "row", "page": 1}]}
        results = {"results": [{"task_id": "VERIFY-001", "verified_value": "2500",
                                 "confidence": "high"}]}
        vf.merge_results(results, data, tasks=tasks)
        # 管道形态：旧值为字符串 → _try_convert_type 保字符串类型落库
        assert data["structured_rows"][0]["pile_no"] == "2500", "中文字段未映射，pile_no 未更新"
        assert "桩号" not in data["structured_rows"][0], "新建了中文键 = 错位落库"

    def test_merge_locates_by_tasks_not_result_copy(self):
        """merge 定位以 tasks 回查为准：结果里不抄 row/field 也能正确落库"""
        import verify_fields as vf
        rows = [_pile_row(0, 500), _pile_row(0, 501)]
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows, "rows": [dict(r) for r in rows]}
        tasks = {"tasks": [{"task_id": "VERIFY-009", "field": "filling_coeff", "row": 2,
                            "table": None, "scope": "row", "page": 1}]}
        # AI 结果故意不带 row/field（协议允许），且 task_id 与数组序号错位
        results = {"results": [{"task_id": "VERIFY-009", "verified_value": "1.30",
                                "confidence": "high"}]}
        vf.merge_results(results, data, tasks=tasks)
        assert str(data["structured_rows"][1]["filling_coeff"]) == "1.30", \
            "未按 task_id 回查定位（旧逻辑按数组序号或结果手抄定位，错行）"
        assert str(data["structured_rows"][0]["filling_coeff"]) == "1.46", \
            "task 指向第2行，第1行被误写 = 定位错行"

    def test_clean_data_prepare_no_tasks(self, tmp_path):
        """H-8 反向（零误报）：干净数据（无 confusion 无 pending）→ no_suspects"""
        import verify_fields as vf
        docx = _make_docx(tmp_path / "clean.docx", n_images=1)
        vf._DOCX_MEDIA_CACHE.clear()
        rows = [_pile_row(0, 500), _pile_row(0, 501)]
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows}
        result = vf.prepare_verify_tasks(docx, {"suspects": []}, data, str(tmp_path / "vo2"))
        assert result["status"] == "no_suspects", "干净数据产出复核任务 = 误报"

    def test_pending_row_level_not_table_scope(self):
        """v9.7.1 修复①：行级数值 pending 项（带 pile_no）→ scope=row，不得表级化整表覆写

        修复前：无字段类型过滤，actual_length 等（各行本不相同）也生成 scope=table
        任务，merge 后整表覆写，同行正确值被污染（独立复核 R-1 高危实证）。
        """
        import verify_fields as vf
        rows = [
            _pile_row(0, 500, actual_length="20.0"),
            _pile_row(0, 501, actual_length="2O.0"),   # 仅此行存疑（乱码）
            _pile_row(0, 502, actual_length="19.8"),
        ]
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows,
                "rows": [dict(r) for r in rows],
                "pending_verification": [
                    {"table": 0, "pile_no": "501", "field": "actual_length",
                     "raw": "2O.0", "reason": "数值不可解析:『2O.0』"}]}
        suspects = vf.suspects_from_pending(data)
        assert len(suspects) == 1, "行级项应生成 1 条任务"
        s = suspects[0]
        assert s["scope"] == "row", f"行级数值项被表级化（scope={s['scope']}）→ 整表覆写污染"
        assert s["row"] == 2, "行号应定位到桩号 501 所在行（全局 1-based）"
        assert s["field"] == "actual_length", "英文键应直通"

        # merge 全链验证：只写第 2 行，第 1/3 行正确值不被污染
        tasks = {"tasks": [{"task_id": "VERIFY-001", "field": "actual_length", "row": 2,
                            "table": 0, "scope": "row", "page": 1}]}
        results = {"results": [{"task_id": "VERIFY-001", "verified_value": "20.0",
                                 "confidence": "high"}]}
        vf.merge_results(results, data, tasks=tasks)
        for lst in (data["structured_rows"], data["rows"]):
            assert lst[1]["actual_length"] == "20.0", "存疑行未修正"
            assert str(lst[0]["actual_length"]) == "20.0" and str(lst[2]["actual_length"]) == "19.8", \
                "同行正确值被整表覆写污染（v9.7.1 修复①回归）"

    def test_pending_whole_row_field_skipped(self):
        """v9.7.1 修复②：field=「整行」项跳过，不生成任务、不新建中文键落库"""
        import verify_fields as vf
        rows = [_pile_row(0, 500), _pile_row(0, 501)]
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows,
                "rows": [dict(r) for r in rows],
                "pending_verification": [
                    {"table": 0, "pile_no": "500", "field": "整行",
                     "raw": "", "reason": "该表表头解析不可靠，整行数值字段需人工核对"},
                    {"table": 0, "pile_no": "501", "field": "整行",
                     "raw": "", "reason": "该表表头解析不可靠，整行数值字段需人工核对"}]}
        suspects = vf.suspects_from_pending(data)
        assert suspects == [], "「整行」项应跳过（读图无法单值作答，留给 Chat-Verify）"
        # 即便外部误传进 tasks/merge，也不得新建中文键（守卫在 field 映射层）
        assert vf._field_to_row_key("整行") == "整行"  # 未映射 → merge 层 field 校验拦不住，
        # 故入口层（suspects_from_pending）跳过是唯一闸门——上面 suspects==[] 即验证

    def test_pending_unknown_table_field_skipped(self):
        """v9.7.1：无 pile_no 且不在表级白名单的字段 → 跳过（无法安全落库）"""
        import verify_fields as vf
        rows = [_pile_row(0, 500)]
        data = {"doc_type": "碎石桩施工记录", "structured_rows": rows,
                "pending_verification": [
                    {"table": 0, "field": "充盈系数", "raw": "?.46", "reason": "存疑"}]}
        suspects = vf.suspects_from_pending(data)
        # 充盈系数是行级字段，无 pile_no 无法定位到行 → 不生成任务（保守不落库）
        assert all(s["field"] != "filling_coeff" for s in suspects), \
            "行级字段无 pile_no 却生成了任务 = 无法安全落库的盲写"
