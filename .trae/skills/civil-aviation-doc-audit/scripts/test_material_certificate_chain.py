# -*- coding: utf-8 -*-
"""
材料/合格证数据链回归套件（scripts/test_material_certificate_chain.py）
=====================================================================
为 v10.3 方案（合格证数据沉淀 + 材料类链路修正）定义的 TDD 契约。
红 = 功能缺口（未实现或行为不正确），实现后变绿，永久留套防复发。

覆盖：
  A1  材料类文档（质量证明书/合格证/检验记录）强制走通用解析，绝不被桩基内容感知劫持
  A2  合格证提取器 extract_certificates.extract_records（打印型表格 → 结构化证书记录）
  A4  台账落库 extract_certificates.attach_certificates_ledger（ledgers.certificates + index 关联）
  A5  S-04 追溯链 extract_certificates.build_certificate_linkage（检验记录↔质证书编号↔合格证号）
  E1  OCR 文本全空但 items 带 bbox → 必须 needs_review（不得放行 completed）
  E3  材料类 schema_status 契约：跳过桩基领域规则，且不得误报"schema 未确认"
  G3  同步脚本工作台双端部署（项目版 + 安装版），杜绝"工作台只复制了一半"
"""

from pathlib import Path
import json
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_foundation as bf
from data_quality_check import DataQualityChecker

# ============================================================
# A1 / E4：材料类文档路由 —— 绝不被桩基内容感知劫持
# ============================================================
# 材料合格证文本里出现"碎石桩""充盈系数"等桩关键词是常态
# （材料用于碎石桩区域），内容感知路由不得据此把材料类误切桩基解析。
_MATERIAL_TABLE_TEXT = """材料名称 规格型号 单位 数量 生产厂家 合格证号 质证书编号
碎石桩填筑料 5-31.5mm m3 120.0 某某砂石有限公司 HG20260701001 YKG/A20260704052
碎石桩填筑料 5-31.5mm m3 88.0 某某砂石有限公司 HG20260701002 YKG/A20260704052
碎石桩填筑料 31.5-63mm m3 96.0 某某砂石有限公司 HG20260701003 YKG/A20260704053
充盈系数复核用药剂 kg 15.0 某某检测试剂 YG20260702001 YKG/A20260704054
"""


def test_material_doc_type_not_hijacked_by_pile_content():
    # 文本含"碎石桩"×? + "充盈系数"×1，桩内容指标 ≥2 命中；
    # 但 doc_type 是材料检验/合格证类 → 必须走通用解析，产出非空行且无桩槽位键
    rows = bf.build_rows(_MATERIAL_TABLE_TEXT, "材料进场检验记录")
    assert rows, "材料类文档被桩基内容感知劫持，产出空行"
    pile_keys = {"pile_no", "actual_length", "top_elev", "bottom_elev", "current", "filling_coeff"}
    for r in rows:
        assert not (pile_keys & set(r)), f"材料类行混入桩基槽位: {sorted(pile_keys & set(r))} 行={r}"


def test_certificate_doc_type_keeps_generic_fields():
    # 质量证明书 → 行保留证书号/材料名等材料字段（field 投影 slot 键），不得出现桩键
    rows = bf.build_rows(_MATERIAL_TABLE_TEXT, "混凝土质量证明书")
    assert rows, "质量证明书被桩基内容感知劫持，产出空行"
    assert all("actual_length" not in r for r in rows)
    assert all("pile_no" not in r for r in rows)


# ============================================================
# E1：OCR 文本全空但 items 带无文字 bbox → needs_review
# ============================================================
def test_ocr_items_bbox_without_text_marks_needs_review():
    result = {
        "text": "   \n  ",
        "items": [
            {"box": [0, 0, 10, 10], "text": ""},
            {"bbox": [1, 1, 5, 5]},          # 只有坐标、无文字的垃圾框
        ],
    }
    status, reason = bf.assess_ocr_result(result)
    assert status == "needs_review", f"OCR 零产出必须 needs_review，现为 {status}（{reason}）"


def test_real_text_marks_completed():
    result = {"text": "材料名称 合格证号\n花岗岩 HG001", "items": [{"text": "材料名称"}]}
    status, _ = bf.assess_ocr_result(result)
    assert status == "completed"


# ============================================================
# E3：材料类 schema_status 契约
# ============================================================
def _material_data(rows=None):
    return {
        "doc_type": "材料进场检验记录",
        "schema_status": "material",
        "structured_rows": rows or [
            {"row_index": 2, "材料名称": "碎石桩填筑料", "数量": "120.0",
             "合格证号": "HG20260701001", "parsed": True},
            {"row_index": 3, "材料名称": "碎石桩填筑料", "数量": "88.0",
             "合格证号": "HG20260701002", "parsed": True},
        ],
    }


def test_material_schema_skips_pile_domain_checks():
    r = DataQualityChecker(_material_data()).run_all()
    msgs = [w.get("message", "") for w in r.get("warnings", [])]
    pile_terms = ("桩长", "充盈系数", "密实电流", "有效长度", "实长")
    assert not any(any(t in m for t in pile_terms) for m in msgs), \
        f"材料类 schema 不应触发桩基领域规则: {msgs}"
    assert all("DQ-SCHEMA-UNKNOWN" not in w.get("code", "") for w in r.get("warnings", [])), \
        f"材料 schema 已确认，不得误报 schema 未确认: {msgs}"


# ============================================================
# A2：合格证提取器（新模块 scripts/extract_certificates.py）
# ============================================================
# 契约：把检验记录/合格证打印型表格的结构化行，提取成证书记录。
_INSPECTION_ROWS = [
    # 带 row_index/table 的底座行（模拟 build_foundation 产出）
    {"row_index": 2, "table": "记录", "材料名称": "碎石桩填筑料", "规格型号": "5-31.5mm",
     "数量": "120.0", "生产厂家": "某某砂石有限公司", "合格证号": "HG20260701001",
     "使用部位": "西陆侧通道", "质证书编号": "YKG/A20260704052"},
    {"row_index": 3, "table": "记录", "材料名称": "碎石桩填筑料", "规格型号": "5-31.5mm",
     "数量": "88.0", "生产厂家": "某某砂石有限公司", "合格证号": "",  # ← S-02 场景：空白
     "使用部位": "西陆侧通道", "质证书编号": "YKG/A20260704052"},
]


def test_extract_records_from_inspection_rows():
    import extract_certificates  # noqa: F401 —— 模块级契约，当前不存在应红
    records = extract_certificates.extract_records(
        _INSPECTION_ROWS, {"doc_id": "DOC-001", "doc_name": "表C2-9材料进场检验记录"})
    assert records, "合格证提取器必须产出记录"
    for rec in records:
        for key in ("doc_id", "certificate_no", "factory", "material", "quantity",
                    "source", "verified_status"):
            assert key in rec, f"证书记录缺字段 {key}: {rec}"
    # 第 2 行合格证号空白 → 标 missing_hg_no，绝不静默丢弃
    assert any(r["verified_status"] == "missing_hg_no" for r in records), \
        "合格证号空白的行必须标记 missing_hg_no，不得静默通过"


def test_extract_records_dedupe_by_certificate_no():
    import extract_certificates
    recs = extract_certificates.extract_records(_INSPECTION_ROWS, {"doc_id": "DOC-001", "doc_name": "x"})
    nos = [r["certificate_no"] for r in recs if r["verified_status"] == "ok"]
    assert len(nos) == len(set(nos)), f"合格证号不得重复沉淀: {nos}"


# ============================================================
# A4：台账落库（ledgers.certificates + index 关联）
# ============================================================
def _index_fixture(cert_rows=None, doc_rows=None):
    return {
        "documents": [
            {"doc_id": "DOC-001", "doc_name": "表C2-9材料进场检验记录",
             "doc_role": "audited", "schema_status": "material",
             "rows": doc_rows or [], "structured_rows": doc_rows or []},
        ],
    }


def test_attach_certificates_ledger_writes_index():
    import extract_certificates
    idx = _index_fixture()
    records = extract_certificates.extract_records(_INSPECTION_ROWS, {"doc_id": "DOC-001", "doc_name": "x"})
    extract_certificates.attach_certificates_ledger(idx, {"DOC-001": records})
    assert "ledgers" in idx and "certificates" in idx["ledgers"], "index 必须落 ledgers.certificates"
    assert isinstance(idx["ledgers"]["certificates"], list) and idx["ledgers"]["certificates"]
    doc = idx["documents"][0]
    assert doc.get("certificates"), "documents[] 必须带 certificates 关联元信息"
    assert doc["certificates"]["count"] == len(idx["ledgers"]["certificates"])


def test_ledger_survives_json_roundtrip():
    # 底座稳定性：落库后 JSON 序列化无损，后续工具（verify/report/工作台）可正常读
    import extract_certificates
    idx = _index_fixture()
    records = extract_certificates.extract_records(_INSPECTION_ROWS, {"doc_id": "DOC-001", "doc_name": "x"})
    extract_certificates.attach_certificates_ledger(idx, {"DOC-001": records})
    reloaded = json.loads(json.dumps(idx, ensure_ascii=False))
    assert reloaded["ledgers"]["certificates"][0]["certificate_no"]
    assert reloaded["documents"][0]["certificates"]["count"] == 2


# ============================================================
# A5：S-04 追溯链（检验记录行 ↔ 质证书编号 ↔ 合格证号）
# ============================================================
def test_linkage_detects_blank_certificate_no():
    import extract_certificates
    idx = _index_fixture(doc_rows=_INSPECTION_ROWS)
    records = extract_certificates.extract_records(_INSPECTION_ROWS, {"doc_id": "DOC-001", "doc_name": "x"})
    extract_certificates.attach_certificates_ledger(idx, {"DOC-001": records})
    issues = extract_certificates.build_certificate_linkage(idx)
    s04 = [i for i in issues if i.get("code") == "S-04"]
    assert s04, "合格证号空白的行必须产出 S-04 缺链项"
    assert any("row_index" in i for i in s04), "S-04 必须带 row_index 行级定位"


def test_linkage_clean_when_all_filled():
    import extract_certificates
    rows = [dict(r) for r in _INSPECTION_ROWS]
    rows[1]["合格证号"] = "HG20260701002"          # 补齐合格证号
    rows[0]["质证书编号"] = "YKG/A20260704052"
    rows[1]["质证书编号"] = "YKG/A20260704052"
    idx = _index_fixture(doc_rows=rows)
    records = extract_certificates.extract_records(rows, {"doc_id": "DOC-001", "doc_name": "x"})
    extract_certificates.attach_certificates_ledger(idx, {"DOC-001": records})
    issues = extract_certificates.build_certificate_linkage(idx)
    assert not [i for i in issues if i.get("code") == "S-04"], f"补齐后不得再有 S-04: {issues}"


# ============================================================
# G3：同步脚本工作台双端部署（静态断言）
# ============================================================
def test_sync_bat_deploys_both_sides_workbench():
    # 同步脚本位于项目根（skill 的第四级上级：scripts → skill → skills → .trae → 项目根）
    bat = SCRIPT_DIR.parents[3] / "同步内部路由到安装版.bat"
    assert bat.exists(), f"缺少同步脚本: {bat}"
    text = bat.read_text(encoding="utf-8", errors="replace")
    # 安装版部署必须有
    assert '"%dest%\\dist" "%dest%\\workbench"' in text, "同步脚本必须部署安装版 workbench"
    # 项目版部署必须有（缺失=工作台只复制了一半，下次 /MIR 源端仍会把安装版 workbench 当 EXTRA 删掉）
    assert any(token in text for token in (
        '"%source%\\dist" "%source%\\workbench"',
        "source\\workbench",
        "项目版.*workbench",
    )), "同步脚本必须部署项目版 workbench（双端）"


# ============================================================
# F1：材料链回归（DOC-002 场景：合格证号列空白 + 使用部位错位）
# ============================================================
def test_s02_style_shifted_column_copy_preserved():
    # S-02：最右列为"备注"实填"使用部位" → 提取不得把该列吞掉，内容保留在 location 字段
    import extract_certificates
    rows = [
        {"row_index": 2, "表": "记录", "材料名称": "水泥", "规格型号": "P.O42.5",
         "生产厂家": "云南某厂", "合格证号": "HG001", "备注": "西陆侧通道 箱涵结构"},
        {"row_index": 3, "表": "记录", "材料名称": "钢筋", "规格型号": "HRB400",
         "生产厂家": "云南某厂", "合格证号": "HG002", "备注": "西陆侧通道 箱涵结构"},
    ]
    records = extract_certificates.extract_records(rows, {"doc_id": "DOC-002", "doc_name": "x"})
    assert records
    assert all(r.get("location") for r in records), "备注列内容必须落入 location，不得丢失"
    assert all(r["certificate_no"] for r in records)