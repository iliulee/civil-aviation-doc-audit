# -*- coding: utf-8 -*-
"""
测试：数据底座构建（test_data_foundation.py）
===========================================
测试 build_foundation.py 的核心功能：文件分类、OCR、结构化提取、index.json 生成。

用法：
    pytest scripts/test_data_foundation.py -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# 添加 scripts 目录到路径
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

# 测试用临时目录
TEST_DATA = SCRIPT_DIR / "test_data"


def test_import_build_foundation():
    """测试 build_foundation 模块可导入"""
    try:
        import build_foundation
        assert hasattr(build_foundation, "main")
    except ImportError as e:
        assert False, f"导入 build_foundation 失败: {e}"


def test_import_data_quality_check():
    """测试 data_quality_check 模块可导入"""
    try:
        import data_quality_check
        assert hasattr(data_quality_check, "check")
        assert hasattr(data_quality_check, "infer_values")
    except ImportError as e:
        assert False, f"导入 data_quality_check 失败: {e}"


def test_inference_rules_json_exists():
    """测试 inference_rules.json 存在且格式正确"""
    rules_path = SKILL_DIR / "rules" / "inference_rules.json"
    assert rules_path.exists(), f"inference_rules.json 不存在: {rules_path}"
    with open(rules_path, "r", encoding="utf-8") as f:
        rules = json.load(f)
    assert "rules" in rules, "inference_rules.json 缺少 rules 字段"
    assert len(rules["rules"]) >= 7, f"规则数量不足 7 条（当前 {len(rules['rules'])} 条）"
    assert "confidence_color_map" in rules, "缺少 confidence_color_map"


def test_infer_values_empty():
    """测试 infer_values 空数据"""
    from data_quality_check import infer_values
    data = {"doc_type": "test", "rows": []}
    result = infer_values(data)
    assert "row_inferred" in result
    assert "summary" in result
    assert result["summary"]["total_inferred_fields"] == 0


def test_infer_values_with_data():
    """测试 infer_values 有数据"""
    from data_quality_check import infer_values
    data = {
        "doc_type": "碎石桩施工记录",
        "rows": [
            {
                "pile_no": "Z420",
                "top_elev": 2103.72,
                "bottom_elev": 2089.98,
                "actual_length": None,  # 缺失，应推断
                "diameter": 0.8,
                "volume": 2.5,
                "filling_coeff": None,  # 缺失，应推断
                "thickness": 1.50,  # 提供，避免 INF-007 干扰
            }
        ]
    }
    result = infer_values(data)
    assert result["summary"]["total_inferred_fields"] == 2, f"预期 2 个推断值，实际 {result['summary']['total_inferred_fields']}"
    row_inferred = result.get("row_inferred", {})
    assert "1" in row_inferred, "第 1 行应有推断值"
    assert "actual_length" in row_inferred["1"], "应推断 actual_length"


def test_infer_values_cascade_confidence():
    """测试级联推断置信度降低：源字段含推断值时，级联推断置信度应降低"""
    from data_quality_check import infer_values
    # bottom_elev 缺失，actual_length 来自行内已有推断值 → 级联场景
    data = {
        "doc_type": "碎石桩施工记录",
        "rows": [
            {
                "pile_no": "Z420",
                "top_elev": 2103.72,
                "bottom_elev": None,  # 缺失，目标字段
                "actual_length": None,  # 缺失，但行内已有推断值
                "diameter": 0.8,
                "inferred": {
                    "actual_length": {"value": 13.74, "confidence": 0.60},  # 源字段来自推断
                },
            }
        ]
    }
    result = infer_values(data)
    row_inferred = result.get("row_inferred", {})
    # 应有 bottom_elev 推断（INF-003: bottom_elev = top_elev - actual_length）
    # actual_length 来自 row_inferred，所以 cascade 应触发，置信度 < 0.95
    assert "1" in row_inferred, "第 1 行应有推断值"
    assert "bottom_elev" in row_inferred["1"], "应推断 bottom_elev"
    assert row_inferred["1"]["bottom_elev"]["confidence"] < 0.95, \
        f"级联推断置信度应 < 0.95，当前 {row_inferred['1']['bottom_elev']['confidence']}"