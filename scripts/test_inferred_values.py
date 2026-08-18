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