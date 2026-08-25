#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v8.9 自我测试：验证空结果拦截 + 列错位检测 + 时间列锚点在两个脚本中的行为。"""
import sys
import json
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bf = load_module("bf", SCRIPTS / "build_foundation.py")
dq = load_module("dq", SCRIPTS / "data_quality_check.py")
tm = load_module("tm", SCRIPTS / "template_miner.py")

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}  {detail}")


print("== 1) 空结果拦截 assess_ocr_result ==")
r_empty = {"text": "", "engine": "paddle", "confidence": 0.0, "items": []}
st, reason = bf.assess_ocr_result(r_empty)
check("空结果判定 needs_review", st == "needs_review", f"got {st}")
r_some = {"text": "碎石桩施工记录", "engine": "paddle", "confidence": 0.8, "items": [{"text": "x"}]}
st2, _ = bf.assess_ocr_result(r_some)
check("非空结果判定 completed", st2 == "completed", f"got {st2}")

print("== 2) 单行列校验 validate_pile_row ==")
good = {"pile_no": "12385", "diameter": 6, "bottom_elev": 2089.98,
        "top_elev": 2103.68, "actual_length": 13.7, "current": 160,
        "sink_time": "07:00", "pull_time": "07:15"}
check("正常行无问题", bf.validate_pile_row(good) == [], f"got {bf.validate_pile_row(good)}")
bad = {"pile_no": "12385", "diameter": 6, "bottom_elev": 2089.98,
       "top_elev": 2103.68, "actual_length": "07:00", "current": 7257,
       "sink_time": 7257, "pull_time": "07:07"}
issues = bf.validate_pile_row(bad)
check("错位行发现问题", len(issues) >= 2, f"got {issues}")

print("== 3) 整表列错位 validate_structured_rows ==")
rows_shifted = [
    {"pile_no": "1", "diameter": 6, "bottom_elev": 2089.98, "top_elev": 2103.68,
     "actual_length": "07:00", "current": 7257, "sink_time": 7257, "pull_time": "07:07"},
    {"pile_no": "2", "diameter": 6, "bottom_elev": 2089.98, "top_elev": 2103.68,
     "actual_length": 13.7, "current": 160, "sink_time": "07:00", "pull_time": "07:15"},
    {"pile_no": "3", "diameter": 6, "bottom_elev": 2089.98, "top_elev": 2103.68,
     "actual_length": "08:00", "current": 7260, "sink_time": 7260, "pull_time": "08:08"},
]
res = bf.validate_structured_rows(rows_shifted, "碎石桩施工记录")
check("整表错位率计算", res["applied"] and res["suspect_count"] == 2 and res["total_rows"] == 3, f"got {res}")
check("错位率高→needs_review(risk=high)", res["shift_risk"] == "high", f"got {res['shift_risk']}")
res_nopile = bf.validate_structured_rows(rows_shifted, "其他资料")
check("非桩基不应用", res_nopile["applied"] is False, f"got {res_nopile}")

print("== 4) 审核阶段列级兜底 check_column_shift ==")
data = {
    "doc_type": "碎石桩施工记录",
    "structured_rows": [
        {"桩号": "1", "桩径": 6, "桩底高程": 2089.98, "桩顶高程": 2103.68,
         "实长": "07:00", "密实电流": 7257, "沉管时间": 7257, "拔管时间": "07:07"},
        {"桩号": "2", "桩径": 6, "桩底高程": 2089.98, "桩顶高程": 2103.68,
         "实长": 13.7, "密实电流": 160, "沉管时间": "07:00", "拔管时间": "07:15"},
    ],
}
dqc = dq.DataQualityChecker(data)
w = dqc.check_column_shift()
shift_rows = [x for x in w if x["code"] == "DQ-SHIFT-01"]
check("兜底检测到错位行", len(shift_rows) == 1, f"got {len(shift_rows)}")
summaries = [x for x in w if x["code"] == "DQ-SHIFT-SUM"]
check("兜底产出汇总(错位率50%→high)", summaries and summaries[0]["risk"] == "high", f"got {summaries}")

print("== 5) template_miner 时间列锚点 ==")
cols = [
    {"col": 1, "main_type": "pile_no", "dist": {}},
    {"col": 2, "main_type": "decimal", "dist": {}},
    {"col": 3, "main_type": "time", "dist": {}},
    {"col": 4, "main_type": "time", "dist": {}},
    {"col": 5, "main_type": "elev", "dist": {}},
    {"col": 6, "main_type": "elev", "dist": {}},
    {"col": 7, "main_type": "decimal", "dist": {}},
    {"col": 8, "main_type": "current", "dist": {}},
]
anchors = tm.identify_anchor_columns(cols)
check("桩号锚点 col0", anchors.get("pile_no") == 0, f"got {anchors}")
check("沉管时间锚点 col2", anchors.get("sink_time") == 2, f"got {anchors}")
check("拔管时间锚点 col3", anchors.get("pull_time") == 3, f"got {anchors}")
check("桩底高程 col4", anchors.get("bottom_elev") == 4, f"got {anchors}")
check("桩顶高程 col5", anchors.get("top_elev") == 5, f"got {anchors}")
check("电流锚点 col7", anchors.get("current") == 7, f"got {anchors}")

print(f"\n====== 结果: {passed} 通过, {failed} 失败 ======")
sys.exit(1 if failed else 0)