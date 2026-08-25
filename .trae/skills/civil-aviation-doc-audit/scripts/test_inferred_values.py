# -*- coding: utf-8 -*-
"""
测试：推断建议值生成（test_inferred_values.py）
=============================================
测试 data_quality_check.py 的 infer_values 功能，覆盖所有 7 条规则。

用法：
    pytest scripts/test_inferred_values.py -v
"""

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from data_quality_check import infer_values


def _make_row(**kwargs):
    """辅助函数：创建行数据"""
    row = {
        "pile_no": "Z001",
        "top_elev": None,
        "bottom_elev": None,
        "actual_length": None,
        "diameter": None,
        "volume": None,
        "filling_coeff": None,
        "sink_time": None,
        "pull_time": None,
        "duration": None,
        "thickness": None,  # INF-007 垫层厚度
    }
    row.update(kwargs)
    return row


def test_inf001_actual_length_from_elev():
    """INF-001: 实长 = 桩顶高程 - 桩底高程"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _make_row(top_elev=2103.72, bottom_elev=2089.98, actual_length=None)
    ]}
    result = infer_values(data)
    row_inf = result["row_inferred"].get("1", {})
    assert "actual_length" in row_inf
    assert row_inf["actual_length"]["value"] == 13.74
    assert row_inf["actual_length"]["confidence"] >= 0.90


def test_inf002_top_elev_from_bottom_length():
    """INF-002: 桩顶高程 = 桩底高程 + 实长"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _make_row(top_elev=None, bottom_elev=2089.98, actual_length=13.74)
    ]}
    result = infer_values(data)
    row_inf = result["row_inferred"].get("1", {})
    assert "top_elev" in row_inf
    assert row_inf["top_elev"]["value"] == 2103.72


def test_inf003_bottom_elev_from_top_length():
    """INF-003: 桩底高程 = 桩顶高程 - 实长"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _make_row(top_elev=2103.72, bottom_elev=None, actual_length=13.74)
    ]}
    result = infer_values(data)
    row_inf = result["row_inferred"].get("1", {})
    assert "bottom_elev" in row_inf
    assert row_inf["bottom_elev"]["value"] == 2089.98


def test_inf004_filling_coeff():
    """INF-004: 充盈系数 = 灌入量 / (π × (桩径/2)² × 实长)"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _make_row(top_elev=2103.72, bottom_elev=2089.98, actual_length=13.74,
                  diameter=0.8, volume=2.5, filling_coeff=None)
    ]}
    result = infer_values(data)
    row_inf = result["row_inferred"].get("1", {})
    assert "filling_coeff" in row_inf


def test_inf005_volume():
    """INF-005: 灌入量 = 充盈系数 × π × (桩径/2)² × 实长"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _make_row(top_elev=2103.72, bottom_elev=2089.98, actual_length=13.74,
                  diameter=0.8, filling_coeff=1.15, volume=None)
    ]}
    result = infer_values(data)
    row_inf = result["row_inferred"].get("1", {})
    assert "volume" in row_inf


def test_inf006_duration():
    """INF-006: 单根桩施工时长 = 拔管时间 - 沉管时间"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _make_row(sink_time=80, pull_time=125, duration=None)
    ]}
    result = infer_values(data)
    row_inf = result["row_inferred"].get("1", {})
    assert "duration" in row_inf
    assert row_inf["duration"]["value"] == 45


def test_inf007_cushion_thickness():
    """INF-007: 垫层厚度 = 顶面高程 - 底面高程"""
    data = {"doc_type": "垫层", "rows": [
        {"pile_no": "C01", "top_elev": 2105.00, "bottom_elev": 2103.50, "thickness": None}
    ]}
    result = infer_values(data)
    row_inf = result["row_inferred"].get("1", {})
    assert "thickness" in row_inf
    assert row_inf["thickness"]["value"] == 1.50


def test_no_inferred_on_complete_row():
    """完整行不应生成推断值"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _make_row(top_elev=2103.72, bottom_elev=2089.98, actual_length=13.74,
                  diameter=0.8, volume=2.5, filling_coeff=1.15,
                  sink_time=80, pull_time=125, duration=45, thickness=1.50)
    ]}
    result = infer_values(data)
    assert result["summary"]["total_inferred_fields"] == 0


def test_inferred_count():
    """推断值统计计数正确"""
    # 每行缺失 1 个字段，且提供 thickness 避免 INF-007 干扰
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _make_row(top_elev=2103.72, bottom_elev=2089.98, actual_length=None,
                  thickness=1.50),  # 1个推断（actual_length）
        _make_row(top_elev=None, bottom_elev=2089.98, actual_length=13.74,
                  thickness=1.50),  # 1个推断（top_elev）
        _make_row(top_elev=2103.72, bottom_elev=None, actual_length=13.74,
                  thickness=1.50),  # 1个推断（bottom_elev）
    ]}
    result = infer_values(data)
    assert result["summary"]["rows_with_inferred"] == 3
    assert result["summary"]["total_inferred_fields"] == 3


# ========== 文本规则（INF-008 施工部位 / INF-009 施工日期）==========
# 只建议不入库：产出带 suggested_only=True，绝不自动写回 raw；绝不参与审核判定。

def _loc_row(pile_no, loc, date_raw="2026.4.20", **kw):
    """构造含施工部位/日期的最小行（数值字段留空避免干扰数值链规则）。"""
    row = {"pile_no": pile_no, "loc": loc, "date_raw": date_raw}
    row.update(kw)
    return row


def test_inf008_same_table_mode_single_location():
    """INF-008: 同表部位唯一值仅 1 种 → 全表众数建议，其余乱码行照此推断。"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _loc_row("1", "碎石桩边三区"),
        _loc_row("2", "碎石桩边三区"),
        _loc_row("3", "乱码部位"),   # 无『碎石/桩』→ 视为乱码，触发推断
    ]}
    result = infer_values(data)
    r1 = result["row_inferred"].get("1", {})
    r3 = result["row_inferred"].get("3", {})
    # 合法行不推断；乱码行建议同表众数
    assert "loc" not in r1
    assert r3["loc"]["value"] == "碎石桩边三区"
    assert r3["loc"]["confidence"] == 0.70  # 同表模式置信度封顶 0.70
    assert r3["loc"]["suggested_only"] is True  # 只建议不入库


def test_inf008_type_text_not_auto_persist():
    """建议值绝不写回 raw 行字段（lock：不入库）"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _loc_row("1", "碎石桩边三区"),
        _loc_row("2", "碎石桩边三区"),
        _loc_row("3", "乱码部位"),
    ]}
    result = infer_values(data)
    # raw 原值不被修改（乱码仍为乱码）
    assert data["rows"][2]["loc"] == "乱码部位"
    # 产出带 suggested_only 标记，消费方必须据此门控，不得当确认值入库
    assert result["row_inferred"]["3"]["loc"]["suggested_only"] is True


def test_inf008_neighbor_lookup_when_multi_location():
    """INF-008: 同表部位唯一值≥2 → 禁用全表众数，改用邻行检索。"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _loc_row("1", "碎石桩边三区"),
        _loc_row("2", "碎石桩边三区"),
        _loc_row("3", "碎石桩边四区"),
        _loc_row("4", "乱码"),          # 邻行 row3 合法 → 建议『碎石桩边四区』
        _loc_row("5", "碎石桩边四区"),
    ]}
    result = infer_values(data)
    r4 = result["row_inferred"].get("4", {})
    assert r4["loc"]["value"] == "碎石桩边四区"
    assert r4["loc"]["suggested_only"] is True
    assert r4["loc"]["confidence"] == 0.70


def test_inf008_no_recommend_from_garble_reference():
    """INF-008 安全锁：全表无合法部位（全乱码）时，绝不把乱码当推荐值。"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _loc_row("1", "研工组三区"),
        _loc_row("2", "午之区"),
        _loc_row("3", "乱码部位"),
    ]}
    result = infer_values(data)
    for i in ("1", "2", "3"):
        assert "loc" not in result["row_inferred"].get(i, {}), f"row {i} 不应产出乱码建议"


def test_inf008_legal_pattern_not_infer_valid():
    """INF-008: 匹配合法格式的施工部位绝不触发推断（对齐 build_foundation 存疑判定）。"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _loc_row("1", "碎石桩边三区"),
        _loc_row("2", "碎石桩边三区"),
    ]}
    result = infer_values(data)
    for i in ("1", "2"):
        assert "loc" not in result["row_inferred"].get(i, {})


def test_inf009_date_fill_from_neighbor():
    """INF-009: 残形日期从相邻完整日期补齐。"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _loc_row("1", "碎石桩边三区", date_raw="2026.4.21"),
        _loc_row("2", "碎石桩边三区", date_raw="2026.4.21"),
        _loc_row("3", "碎石桩边三区", date_raw="026.4.21"),  # 年份残缺 → 触发
    ]}
    result = infer_values(data)
    r3 = result["row_inferred"].get("3", {})
    assert r3["date_raw"]["value"] == "2026.4.21"
    assert r3["date_raw"]["confidence"] == 0.65
    assert r3["date_raw"]["suggested_only"] is True


def test_inf008_cross_table_not_contaminate():
    """INF-008 安全锁（v9.6 语义升级）：无据不跨表，跨表必须过双门控。

    部位邻表推断（H-4）允许"有据跨表"：日期相近（≤3天）且桩号区段衔接。
    本测试守住反面：门控不过（日期跳变 20 天 + 桩号断档 90+）时，
    即使表1 有合法部位，也不得抓来当表0 的建议值（防跨区污染）。
    有据放行的正向路径由 test_regression_hazards.py H-4 套件覆盖。
    """
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _loc_row("1", "研工组三区", date_raw="2026.4.20", table=0),   # 表0 乱码
        _loc_row("2", "研工组三区", date_raw="2026.4.20", table=0),
        _loc_row("103", "碎石桩边三区", date_raw="2026.5.10", table=1),  # 表1 合法但门控双杀
        _loc_row("104", "碎石桩边三区", date_raw="2026.5.10", table=1),
    ]}
    result = infer_values(data)
    # 表0 两行：日期跳变 + 桩号断档 → 邻表门控不过，不得产出跨表建议
    assert "loc" not in result["row_inferred"].get("1", {}), "门控不过时跨表部位建议泄漏"
    assert "loc" not in result["row_inferred"].get("2", {}), "门控不过时跨表部位建议泄漏"
    # 表1 合法行：匹配合法格式 → 不触发推断
    assert "loc" not in result["row_inferred"].get("3", {})
    assert "loc" not in result["row_inferred"].get("4", {})


def test_inf008_cross_table_date_not_contaminate():
    """INF-009 安全锁：日期补齐同样限定同表，不跨表取日期。"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _loc_row("1", "碎石桩边三区", date_raw="026.4.20", table=0),  # 表0 残形
        _loc_row("2", "碎石桩边三区", date_raw="2026.4.18", table=1),  # 表1 完整日期（不同表）
    ]}
    result = infer_values(data)
    r1 = result["row_inferred"].get("1", {})
    # 表0 无同表完整日期候选 → 不得用表1 的日期
    assert "date_raw" not in r1


def test_inf009_cross_month_penalty():
    """INF-009: 候选完整日期与残缺值跨月 → 置信度扣 0.15。"""
    data = {"doc_type": "碎石桩施工记录", "rows": [
        _loc_row("1", "碎石桩边三区", date_raw="2026.4.21"),
        _loc_row("2", "碎石桩边三区", date_raw="2026.5.2"),   # 邻行候选（跨月）
        _loc_row("3", "碎石桩边三区", date_raw="2026.4.◆"),   # 残形，年月 2026-04
    ]}
    result = infer_values(data)
    r3 = result["row_inferred"].get("3", {})
    assert r3["date_raw"]["value"] == "2026.5.2"  # 取最近完整日期
    assert r3["date_raw"]["confidence"] == 0.50    # 0.65 - 0.15 跨月
    assert r3["date_raw"]["suggested_only"] is True