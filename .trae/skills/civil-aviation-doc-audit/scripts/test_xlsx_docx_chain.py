# -*- coding: utf-8 -*-
"""
Excel/docx 建底座链路回归（scripts/test_xlsx_docx_chain.py）
============================================================
针对专项审查发现的问题做回归锁定：
  X1  break 整表截断 → 数据行含「监理/审核」不得丢后续行（P1）
  X2  合计行单行跳过、合计后数据行保留（P1）
  X3  row_index 行级定位键存在且递增（P5）
  X4  列语义对齐：桩位编号→pile_no、有效桩长(m)→actual_length（P4）
  X5  双行表头单位子行不拼「·m」（P2）
  X6  数字格式日期列转日期串（P6）
  X7  表头在第 20 行之后仍可解析（P7）
  W1  docx 行带 row_index（Word 必需项）
"""

import re
from pathlib import Path

import openpyxl
import pytest

import build_foundation as bf


def _make_xlsx(path: Path, header_row: int = 1, rows: list = None, sheets: dict = None):
    """构造测试 xlsx。sheets: {sheet_name: [ [行..], ... ]}（自动在 header_row 前补空行）。"""
    wb = openpyxl.Workbook()
    if sheets is None:
        sheets = {"记录": rows or []}
    for sn, data in sheets.items():
        ws = wb.active if sn == list(sheets)[0] else wb.create_sheet(sn)
        ws.title = sn
        for _ in range(header_row - 1):
            ws.append(["占位" + str(_)] * 2 + [""] * 6)
        for r in data:
            ws.append(r)
    wb.save(path)
    wb.close()
    return path


# ===== X1 / X2：行过滤不得截断 =====
def test_data_line_with_supervisor_word_keeps_following(tmp_path):
    p = _make_xlsx(tmp_path / "t.xlsx", rows=[
        ["序号", "桩位编号", "施工日期", "实长"],
        [1, "Z001", "2026-04-01", 6.1],
        [2, "Z002", "2026-04-02", "监理旁站时长2h"],   # 数据行含「监理」
        [3, "Z003", "2026-04-03", 6.3],
        [4, "Z004", "2026-04-04", "审核人签字：李明"],  # 数据行含「审核」
        [5, "Z005", "2026-04-05", 6.5],
    ])
    rows = bf.parse_excel_workbook_rows(p)
    piles = [r.get("桩位编号") for r in rows]
    assert piles == ["Z001", "Z003", "Z005"], f"后续行被截断: {piles}"


def test_total_row_skipped_and_following_kept(tmp_path):
    p = _make_xlsx(tmp_path / "t.xlsx", rows=[
        ["序号", "桩位编号", "施工日期", "实长"],
        [1, "Z001", "2026-04-01", 6.1],
        [2, "Z002", "2026-04-02", 6.2],
        ["合计", "", "", ""],
        [3, "Z003", "2026-04-03", 6.3],
    ])
    rows = bf.parse_excel_workbook_rows(p)
    piles = [r.get("桩位编号") for r in rows]
    assert "合计" not in piles
    assert "Z003" in piles, f"合计后数据行被截断: {piles}"


# ===== X3：行级定位键 =====
def test_row_index_present_and_increasing(tmp_path):
    p = _make_xlsx(tmp_path / "t.xlsx", rows=[
        ["序号", "桩位编号", "施工日期"],
        [1, "Z001", "2026-04-01"],
        [2, "Z002", "2026-04-02"],
        [3, "Z003", "2026-04-03"],
    ])
    rows = bf.parse_excel_workbook_rows(p)
    assert rows and "row_index" in rows[0], f"缺少 row_index: {list(rows[0].keys()) if rows else 'rows=0'}"
    rids = [r["row_index"] for r in rows]
    assert rids == sorted(rids) and len(set(rids)) == len(rids), f"row_index 非递增唯一: {rids}"


# ===== X4：列语义对齐（英文标准槽位投影） =====
def test_excel_field_projection_to_english_slots(tmp_path):
    p = _make_xlsx(tmp_path / "t.xlsx", rows=[
        ["序号", "桩位编号", "施工日期", "有效桩长（m）"],
        [1, "Z001", "2026-04-01", 6.2],
    ])
    rows = bf.parse_excel_workbook_rows(p)
    assert rows, "rows=0"
    r = rows[0]
    assert r.get("pile_no") == "Z001", f"桩位编号未投影 pile_no: {r}"
    assert r.get("actual_length") == "6.2", f"有效桩长未投影 actual_length: {r}"


# ===== X5：单位子行不拼「·m」 =====
def test_unit_sub_header_not_concatenated(tmp_path):
    p = _make_xlsx(tmp_path / "t.xlsx", rows=[
        ["序号", "桩位编号", "实长", "桩顶高程"],
        ["", "", "m", "m"],
        [1, "Z001", 6.2, 100.5],
    ])
    rows = bf.parse_excel_workbook_rows(p)
    assert rows, "rows=0"
    keys = list(rows[0].keys())
    assert "实长" in keys, f"单位子行被拼进列名: {keys}"
    assert "桩顶高程" in keys, f"单位子行被拼进列名: {keys}"


# ===== X6：数字格式日期列 → 日期串 =====
def test_numeric_date_column_converted(tmp_path):
    p = _make_xlsx(tmp_path / "t.xlsx", rows=[
        ["序号", "桩位编号", "施工日期"],
        [1, "Z001", 46000],   # Excel 序列号（≈2025-12-24）
        [2, "Z002", "2026-04-02"],
    ])
    rows = bf.parse_excel_workbook_rows(p)
    assert rows, "rows=0"
    iso = rows[0].get("施工日期", "")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso), f"序列号日期未转日期串: {iso!r}"
    assert rows[1]["施工日期"] == "2026-04-02", "常规日期被破坏"


# ===== X7：表头在第 20 行之后仍可解析 =====
def test_header_beyond_20_rows_still_parsed(tmp_path):
    p = _make_xlsx(tmp_path / "t.xlsx", header_row=25, rows=[
        ["序号", "桩位编号", "施工日期", "实长"],
        [1, "Z001", "2026-04-01", 6.1],
        [2, "Z002", "2026-04-02", 6.2],
    ])
    rows = bf.parse_excel_workbook_rows(p)
    assert rows, "表头在第25行时解析归零"


# ===== P10：质检列错位检查对字符串数值不得误报、对乱码必须报 =====
def test_column_shift_string_numeric_no_false_positive(tmp_path):
    from data_quality_check import DataQualityChecker
    rows = [
        {"桩位编号": "1142", "实长": "5.2", "桩顶高程": "2067.423", "桩底高程": "2062.223",
         "灌入量": "1.63", "充盈系数": "1.11", "竖直度": ""},   # 竖直度缺失（空串）不算错位
        {"桩位编号": "1143", "实长": "5.1", "桩顶高程": "2067.326", "桩底高程": "2062.226",
         "灌入量": "1.59", "充盈系数": "1.12", "竖直度": "0.3"},
    ]
    d = {"doc_type": "碎石桩施工记录", "schema_status": "known_domain",
         "structured_rows": rows, "rows": rows}
    q = DataQualityChecker(d)
    ws_ = q.check_column_shift()
    shift = [w for w in ws_ if w.get("code") == "DQ-SHIFT-01"]
    assert shift == [], f"字符串数值/空值被误报列错位: {[w['message'] for w in shift[:3]]}"


def test_column_shift_catches_garbage_value(tmp_path):
    from data_quality_check import DataQualityChecker
    rows = [
        {"桩位编号": "1592", "实长": "筑业软件 4854505048515052", "桩顶高程": "2067.4",
         "桩底高程": "2062.2", "灌入量": "1.6", "充盈系数": "1.1", "竖直度": "0.3"},
    ]
    d = {"doc_type": "碎石桩施工记录", "schema_status": "known_domain",
         "structured_rows": rows, "rows": rows}
    q = DataQualityChecker(d)
    ws_ = q.check_column_shift()
    shift = [w for w in ws_ if w.get("code") == "DQ-SHIFT-01"]
    assert shift, "乱码值未被列错位检查捕获（静默失效回归）"
    assert "非数值" in shift[0]["message"]


# ===== W1：docx 行带 row_index =====
def test_docx_rows_have_row_index(tmp_path):
    pytest.importorskip("docx")
    from docx import Document
    p = tmp_path / "t.docx"
    doc = Document()
    table = doc.add_table(rows=8, cols=4)
    table.rows[0].cells[0].text = "施工部位"
    table.rows[0].cells[1].text = "场道三区"
    table.rows[2].cells[0].text = "施工日期"
    table.rows[2].cells[1].text = "2026.4.20"
    cells = table.rows[3].cells
    cells[0].text = "序号"; cells[1].text = "桩号"; cells[2].text = "设计桩长"; cells[3].text = "实长"
    table.rows[4].cells[0].text = "1"; table.rows[4].cells[1].text = "Z001"
    table.rows[4].cells[2].text = "20.0"; table.rows[4].cells[3].text = "19.5"
    table.rows[5].cells[0].text = "2"; table.rows[5].cells[1].text = "Z002"
    table.rows[5].cells[2].text = "20.0"; table.rows[5].cells[3].text = "19.4"
    table.rows[6].cells[0].text = ""; table.rows[6].cells[1].text = ""; table.rows[6].cells[2].text = ""; table.rows[6].cells[3].text = ""
    doc.save(p)

    srows, _suspects, _dt = bf.parse_docx_table_sheets(p)
    assert srows, f"docx rows=0: {_suspects[:2] if _suspects else 'no suspects'}"
    assert "row_index" in srows[0], f"docx 行缺少 row_index: {list(srows[0].keys())}"