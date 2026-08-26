# -*- coding: utf-8 -*-
"""
合格证/材料类表格数据沉淀（scripts/extract_certificates.py，v10.3 A2/A4/A5）
==========================================================================
背景：检验记录（表C2-9）等材料类表格本质上是"证件台账"——
     合格证号 / 生产厂家 / 材料名称 / 规格 / 数量 / 质证书编号。
     v10.3 之前这些行只躺在结构化 rows 里，没有任何台账视图，
     导致 S-01（合格证号列空白无感知）、S-04（检验记录↔质证书↔合格证无法关联）反复出现。

本模块职责（单一职责，纯函数，不依赖 OCR/网络）：
  extract_records             —— 检验记录/合格证打印型表格的 rows → 结构化证书记录
  attach_certificates_ledger  —— 证书记录落 index["ledgers"]["certificates"] 并回写文档关联
  build_certificate_linkage   —— S-04 追溯链检查（检验记录行 ↔ 质证书编号 ↔ 合格证号）

Why 不并入 build_foundation：build_foundation 已 4000+ 行，材料链是独立领域，
拆模块便于测试锁定与后续视觉复核通道复用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 材料类文档 doc_type 判定词（build_foundation 与 build_rows 共用导入）
MATERIAL_DOC_TERMS = (
    "合格证", "质量证明书", "进场检验记录", "材料进场", "检验记录",
    "出厂合格证", "材料报审", "质证书",
)

# 中文列名 → 证书记录标准键（长词优先，防止"合格证号"被"合格证"前缀误吃）
_FIELD_ALIASES: List[tuple] = [
    ("出厂合格证编号", "certificate_no"),
    ("合格证编号", "certificate_no"),
    ("合格证号", "certificate_no"),
    ("合格证", "certificate_no"),
    ("质量证明书编号", "quality_cert_no"),
    ("质证书编号", "quality_cert_no"),
    ("质证书号", "quality_cert_no"),
    ("生产厂家", "factory"),
    ("制造商", "factory"),
    ("厂家", "factory"),
    ("材料名称", "material"),
    ("品名", "material"),
    ("材料", "material"),
    ("规格型号", "spec"),
    ("规格", "spec"),
    ("型号", "spec"),
    ("单位", "unit"),
    ("进场数量", "quantity"),
    ("数量", "quantity"),
    ("进场日期", "arrival_date"),
    ("进场时间", "arrival_date"),
    ("使用部位", "location"),
    ("备注", "location"),          # S-02：最右列名为"备注"实填使用部位，内容不得丢
]

_META_KEYS = {"page", "line_no", "issues", "raw_text", "inferred",
              "parsed", "unparsed_fields", "table", "_sheet", "row_index"}


def _match_field(row: Dict[str, Any], aliases: List[str]) -> Optional[str]:
    """在行内按别名表查值（长词优先匹配表头键，避免子串误撞）。"""
    for alias in aliases:
        for key, val in row.items():
            if key in _META_KEYS:
                continue
            if alias == key:
                v = str(val).strip() if val is not None else ""
                if v:
                    return v
    for alias in aliases:
        for key, val in row.items():
            if key in _META_KEYS:
                continue
            if alias in key and alias:
                v = str(val).strip() if val is not None else ""
                if v:
                    return v
    return None


def _alias_for(field: str) -> List[str]:
    return [cn for cn, fn in _FIELD_ALIASES if fn == field]


def extract_records(
    rows: List[Dict[str, Any]],
    doc_meta: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """把检验记录/合格证表格的行提取为结构化证书记录。

    Args:
        rows: 数据底座结构化行（含 row_index/table 定位键）
        doc_meta: {"doc_id", "doc_name", "original_file"}

    Returns:
        证书记录列表，每条：
        {doc_id, doc_name, row_index, table, certificate_no, quality_cert_no,
         factory, material, spec, unit, quantity, location, arrival_date,
         source, verified_status}
        verified_status: ok | missing_hg_no
    Why: 合格证号列空白是 S-01 常态——空白行也必须沉淀并显式标记，
        绝不静默丢弃（否则台账视图里又"看不到"问题）。
    """
    records: List[Dict[str, Any]] = []
    seen_no: set = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        cert_no = _match_field(r, _alias_for("certificate_no")) or ""
        # 去重：同一份文件里合格证号不得重复沉淀（打印型表格偶发一行多行重复）
        if cert_no and cert_no in seen_no:
            continue
        if cert_no:
            seen_no.add(cert_no)
        factory = _match_field(r, _alias_for("factory")) or ""
        material = _match_field(r, _alias_for("material")) or ""
        spec = _match_field(r, _alias_for("spec")) or ""
        unit = _match_field(r, _alias_for("unit")) or ""
        quantity = _match_field(r, _alias_for("quantity")) or ""
        location = _match_field(r, _alias_for("location")) or ""
        qc_no = _match_field(r, _alias_for("quality_cert_no")) or ""
        arrival = _match_field(r, _alias_for("arrival_date")) or ""
        # 空行（无任何材料字段）不沉淀
        if not any((cert_no, factory, material, spec, quantity, qc_no)):
            continue
        records.append({
            "doc_id": doc_meta.get("doc_id", ""),
            "doc_name": doc_meta.get("doc_name", ""),
            "original_file": doc_meta.get("original_file", ""),
            "row_index": r.get("row_index"),
            "table": r.get("table", r.get("_sheet", "")),
            "certificate_no": cert_no,
            "quality_cert_no": qc_no,
            "factory": factory,
            "material": material,
            "spec": spec,
            "unit": unit,
            "quantity": quantity,
            "location": location,
            "arrival_date": arrival,
            "source": "ledger_extract",
            "verified_status": "ok" if cert_no else "missing_hg_no",
        })
    return records


def attach_certificates_ledger(
    index: Dict[str, Any],
    certs_by_doc: Dict[str, List[Dict[str, Any]]],
    ledger_file: Optional[Path] = None,
) -> None:
    """把证书记录落 index["ledgers"]["certificates"]，并按 doc_id 回写文档关联。

    Why: 台账是"数据底座"的一等公民（与 quality/confusion 平级），
    报告/工作台/后续追溯只认 index 内视图，不逐文件翻 JSON。
    """
    ledger: List[Dict[str, Any]] = []
    for doc_id, records in certs_by_doc.items():
        missing = sum(1 for rec in records if rec["verified_status"] == "missing_hg_no")
        ok = len(records) - missing
        for rec in records:
            rec["doc_id"] = doc_id
            ledger.append(rec)
        # 回写文档关联元信息
        # Why: 生产底座主键是 id；部分历史/手改底座可能用 doc_id——都认，找到再写。
        for d in index.get("documents", []):
            if (d.get("id") or d.get("doc_id")) == doc_id:
                d["certificates"] = {
                    "count": len(records),
                    "ok": ok,
                    "missing_hg_no": missing,
                    "ledger_file": "ledgers/certificates.json",
                }
                break
    index.setdefault("ledgers", {})["certificates"] = ledger
    if ledger_file is not None:
        ledger_file.parent.mkdir(parents=True, exist_ok=True)
        # 原子写：先写临时文件再替换，保证 JSON 半截写入不会破坏底座
        tmp = ledger_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(ledger_file)


def build_certificate_linkage(index: Dict[str, Any]) -> List[Dict[str, Any]]:
    """S-04 追溯链检查：检验记录行 ↔ 质证书编号 ↔ 合格证号 关联完整性。

    产出缺链项（code=S-04）。Why: 检验记录填了生产厂家却不填合格证号
    时，无法从"检验记录行 → 质量证明书 → 合格证"建立追溯链路——
    这正是 DOC-001/DOC-002 反复出现的问题，必须行级感知不可静默。
    """
    issues: List[Dict[str, Any]] = []
    # Why: 追溯链的事实源是 ledgers.certificates（attach 落库处），
    # documents[].certificates 只是 {count, ok, missing_hg_no} 元信息视图，不可当记录读。
    ledger = index.get("ledgers", {}).get("certificates", [])
    if not isinstance(ledger, list) or not ledger:
        return issues
    for rec in ledger:
        if rec.get("verified_status") != "missing_hg_no":
            continue
        doc = next(
            (d for d in index.get("documents", [])
             if (d.get("id") or d.get("doc_id")) == rec.get("doc_id")),
            None,
        )
        issues.append(_missing_hg_no_issue(rec, doc))
    return issues


def _missing_hg_no_issue(rec: Dict[str, Any],
                         doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把一条 missing_hg_no 台账记录构造成 S-04 缺链 issue（内部复用）。"""
    return {
        "code": "S-04",
        "severity": "best-practice",
        "doc_id": rec.get("doc_id", ""),
        "doc_name": rec.get("doc_name") or ((doc or {}).get("doc_type") or ""),
        "row_index": rec.get("row_index"),
        "message": "检验记录行未引用合格证编号，无法建立「检验记录→质量证明书→合格证」追溯链",
        "detail": ("质证书编号" if rec.get("quality_cert_no") else "生产厂家")
                  + f"已填（{rec.get('quality_cert_no') or rec.get('factory') or '?'}），"
                    "建议补填合格证号以便台账关联。"
    }


# ============================================================
# 审核期专用检查（v10.4 A2）：S-04 进 rule_engine_findings
# ============================================================
def _is_material_doc(doc: Dict[str, Any]) -> bool:
    """按 doc_type 关键词判定材料类文档（与 build_foundation 同口径）。"""
    doc_type = str(doc.get("doc_type") or "")
    return any(t in doc_type for t in MATERIAL_DOC_TERMS)


def collect_certificate_findings(
    docs: List[Dict[str, Any]],
    all_data: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """审核期执行：基于 corrected（人工核对后）数据重算 S-04。

    Why 必须审核期重算而不是读建底座时的 certificates_linkage：
    审核读取的是 corrected_file（阶段2 人工修正产物）。若直接读建底座
    时的预计算结果，用户补填合格证号后重审仍会报旧问题（陈旧结果 bug）。

    Args:
        docs: 文档元数据列表（含 id / doc_type / original_file）
        all_data: {doc_id: corrected_data}，data 含 structured_rows

    Returns:
        (findings, certs_by_doc)：
        findings —— rule_engine_findings 兼容格式（rule_id=LG-110），
                    schema 与 ViolationReporter.to_audit_findings 对齐，
                    报告端可与其他引擎产出统一渲染；
        certs_by_doc —— {doc_id: 证书记录}，供调用方原子刷新台账（口径一致）。
    """
    findings: List[Dict[str, Any]] = []
    certs_by_doc: Dict[str, List[Dict[str, Any]]] = {}
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        if doc.get("doc_role", "audited") != "audited":
            continue
        if not _is_material_doc(doc):
            continue
        doc_id = doc.get("id") or doc.get("doc_id") or ""
        data = all_data.get(doc_id, {}) if doc_id else {}
        rows = (data.get("structured_rows") or data.get("rows", [])) \
            if isinstance(data, dict) else []
        if not isinstance(rows, list) or not rows:
            continue
        doc_meta = {
            "doc_id": doc_id,
            "doc_name": doc.get("doc_type", "") or doc.get("doc_name", ""),
            "original_file": doc.get("original_file", ""),
        }
        records = extract_records(rows, doc_meta)
        if records:
            certs_by_doc[doc_id] = records
        for rec in records:
            if rec.get("verified_status") != "missing_hg_no":
                continue
            findings.append({
                "rule_id": "LG-110",
                "rule_name": "材料进场检验记录合格证追溯链（检验记录行 ↔ 质证书编号 ↔ 合格证号）",
                "level": "L2-LOGIC",
                "scope": "CROSS_DOC",
                "severity": "Best Practice",
                "result": "pass",           # Best Practice → pass（提示级，不阻塞合规判定）
                "row_index": rec.get("row_index"),
                "doc_id": doc_id,
                "doc_name": doc_meta["doc_name"],
                "finding": "检验记录行未引用合格证编号，无法建立「检验记录→质量证明书→合格证」追溯链",
                "evidence": {
                    "doc_id": doc_id,
                    "original_file": doc_meta["original_file"],
                    "row_index": rec.get("row_index"),
                    "material": rec.get("material", ""),
                    "spec": rec.get("spec", ""),
                    "factory": rec.get("factory", ""),
                    "quality_cert_no": rec.get("quality_cert_no", ""),
                },
                "remediation": "在检验记录对应行补填合格证编号，或按其已填的质证书编号/生产厂家在台账中补充关联，确保可回溯",
                "spec": "",
                "evidence_source": "missing",
            })
    return findings, certs_by_doc