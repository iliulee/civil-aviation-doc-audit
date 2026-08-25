#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chat_verify_apply.py — Chat-Verify 人工核对应用器（阶段 2 聊天式核对后端）
====================================================================

背景
====
阶段 2（人工核对）新增"聊天式人工核对（Chat-Verify）"通道，手机也能用：
AI 在对话框内把 OCR 存疑项**按表分组、按优先级**抛给用户，用户短答修正
（如"表0部位=碎石桩边三区"），本脚本吃下修正并完成落库：

  1. 校验字段名 / 取值边界（数值字段必须可解析，越界值标失败不落库）
  2. 更新数据文件 structured_rows（原值→新值，Python None 一律空串）
  3. 写留痕 修正记录/corrections.json（来源 user_dialog、时间、原值→新值）
  4. 同步 index.json（corrections.total、对应关系、失败清单 failed、剩余存疑项）
  5. 全部必须项核对完 + 用户确认 → human_verified=true，进入阶段 3

铁律：只收集用户权威输入；OCR/推断建议值需用户确认才落库；AI 不擅自判定。
      corrections 只写 user 确认过的值，其余原样保留，不做任何猜测。

用法（直接命令行）
================
    python scripts/chat_verify_apply.py list    "<项目文件夹>" [--doc DOC-002] [--table N] [--json]
    python scripts/chat_verify_apply.py apply   "<项目文件夹>" --doc DOC-002 --corrections <修正.json> [--source user_dialog]
    python scripts/chat_verify_apply.py refresh "<项目文件夹>" [--doc DOC-002]      # 仅刷新建议值，不动核对进度
    python scripts/chat_verify_apply.py confirm "<项目文件夹>" --doc DOC-002 [--confirm-classification]
    python scripts/chat_verify_apply.py status  "<项目文件夹>"

修正.json 格式（AI 从用户聊天解析后产出，可多条，逐表一次过）
============================================================
[
  {"table": 0, "field": "施工部位", "value": "碎石桩边三区"},          # 表级：作用该表全部行
  {"table": 0, "field": "日期", "value": "2026.4.20"},                # 表级
  {"table": 2, "pile_no": "507", "field": "充盈系数", "value": "1.2"}, # 行级：按 表+桩号 定位
  {"table": 22, "row_index": 120, "field": "bottom_elev", "value": "2084.22"},  # 行级：按 1-based row_index 定位（与编辑器一致，从 1 开始）
  {"table": 3, "field": "施工部位", "accept": true}                    # 用户确认原值无误（不修改）
  {"table": 9, "pile_no": "2700", "field": "整行", "accept": true}      # 表头解析不可靠的整行项：确认整行原样保留
  {"table": 0, "row_index": 5, "field": "施工部位", "accept_recommended": true}  # 采纳建议值（零转抄：值由脚本现场算，AI 不抄录）
]
  - field 支持中文标签 / 英文字段名（见 FIELD_SYNONYMS）
  - value 空串 = 确认该处为空白
  - accept=true = 用户确认保持原样，仍写入留痕（reason=用户确认原值无误）
  - accept_recommended=true = 脚本现场取建议值落库（文本/数值链均可），reason 标注来源

输出（apply/confirm 均返回 JSON）
================================
{"status": "ok", "applied": [...], "failed": [...], "resolved_pending": N, "remaining_pending": N}
"""

import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ========== 常量 ==========

OUT_DIR_NAME = "数据底座"  # 默认数据底座目录名（与 run_audit build 保持一致）

# 中文标签 / 别名 → 结构化字段名（与 数据核对编辑器.html 的 FIELD_LABELS 对齐 + 常用别名）
FIELD_SYNONYMS: Dict[str, str] = {
    "施工部位": "loc", "部位": "loc", "施工区域": "loc", "区域": "loc", "区": "loc",
    "施工日期": "date_raw", "日期": "date_raw",
    "桩号": "pile_no",
    "桩底高程": "bottom_elev", "桩底": "bottom_elev",
    "桩顶高程": "top_elev", "桩顶": "top_elev",
    "设计桩长": "design_length", "桩长": "design_length",
    "桩径": "diameter",
    "实长": "actual_length", "实际桩长": "actual_length",
    "密实电流": "current", "电流": "current",
    "反插次数": "re_penetration", "反插": "re_penetration", "反插深度": "re_penetration",
    "灌入量": "volume", "灌入": "volume",
    "充盈系数": "filling_coeff", "充盈": "filling_coeff",
    "竖直度": "verticality", "竖直": "verticality",
    "沉管开始": "sink_start", "沉管结束": "sink_end",
    "拔管开始": "pull_start", "拔管结束": "pull_end",
}

# 反向：英文字段名 → 展示中文标签（pending 里已用中文标签的字段）
FIELD_LABELS: Dict[str, str] = {
    "loc": "施工部位", "date_raw": "施工日期", "pile_no": "桩号",
    "bottom_elev": "桩底高程", "top_elev": "桩顶高程", "design_length": "设计桩长",
    "diameter": "桩径", "actual_length": "实长", "current": "密实电流",
    "re_penetration": "反插次数", "volume": "灌入量", "filling_coeff": "充盈系数",
    "verticality": "竖直度", "sink_start": "沉管开始", "sink_end": "沉管结束",
    "pull_start": "拔管开始", "pull_end": "拔管结束",
}

# pending_verification 里「施工部位/施工日期」等中文标签 → 结构化字段名
PENDING_FIELD_TO_NAME: Dict[str, str] = {
    "施工部位": "loc", "施工日期": "date_raw",
}

# 特殊存疑项字段：表头解析不可靠时产出「整行」，整行数值字段需人工核对
# 通过 accept=true 确认整行原样保留（销项），不逐字段改写
ROW_LEVEL_ACCEPT_FIELD = "整行"

NUMERIC_FIELDS = {
    "design_length", "diameter", "bottom_elev", "top_elev", "actual_length",
    "current", "re_penetration", "volume", "filling_coeff", "verticality",
}
TIME_FIELDS = {"sink_start", "sink_end", "pull_start", "pull_end"}
TEXT_FIELDS = {"loc", "date_raw", "pile_no"}
ALL_FIELDS = NUMERIC_FIELDS | TIME_FIELDS | TEXT_FIELDS

# 表级字段（作用于整表所有行）
TABLE_LEVEL_FIELDS = {"loc", "date_raw"}


# ========== 基础工具 ==========

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_value(v: Any) -> str:
    """把 Python None / 'None'/'null'/'nan' 统一为 ''，杜绝 None 污染 JSON。"""
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("none", "null", "nan"):
        return ""
    return s


def resolve_field(user_field: str) -> Optional[str]:
    """中文标签/别名 → 结构化字段名；已是英文字段名则原样返回。"""
    if not user_field:
        return None
    uf = str(user_field).strip()
    if uf in FIELD_SYNONYMS:
        return FIELD_SYNONYMS[uf]
    if uf == ROW_LEVEL_ACCEPT_FIELD:
        return uf
    if uf in ALL_FIELDS:
        return uf
    # 大小写归一（如 Bottom_Elev）
    low = uf.lower()
    for cand in ALL_FIELDS:
        if cand.lower() == low:
            return cand
    return None


def try_float(s: Any) -> Optional[float]:
    """宽松数值解析，失败返回 None。"""
    if s is None:
        return None
    st = str(s).replace("，", ".").replace(",", ".").strip()
    if not st:
        return None
    try:
        return float(st)
    except ValueError:
        return None


def _fmt_number(f: float) -> str:
    """浮点转规范字符串：整数去掉 .0，其余保留原始十进制（不引入科学计数）。"""
    if f == int(f):
        return str(int(f))
    return str(f)


def resolve_data_base(project_dir: Path, out_dir: Optional[str]) -> Path:
    base = project_dir / (out_dir or OUT_DIR_NAME)
    return base


def find_doc(index: Dict[str, Any], doc_id: Optional[str], original_file: Optional[str]) -> Optional[Dict[str, Any]]:
    docs = index.get("documents", [])
    if doc_id:
        for d in docs:
            if d.get("id") == doc_id:
                return d
    if original_file:
        for d in docs:
            if d.get("original_file") == original_file:
                return d
    return None


def doc_data_file(base: Path, doc: Dict[str, Any]) -> Path:
    rel = doc.get("data_file")
    if not rel:
        return base
    return base / rel


# ========== list：列出待核对存疑项（按表分组） ==========

def _pending_items(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = doc.get("pending_verification")
    if isinstance(items, list):
        return [i for i in items if isinstance(i, dict)]
    return []


# ========== H-5 接线：应疑清单重算补漏（闸门完整性审计） ==========

def _recalc_missing(data: Dict[str, Any], doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """全量重扫当前数据生成应疑清单，剔除存量 pending 已覆盖项，返回漏网项。

    存量 pending 是静态登记（apply 命中销项）；本重算是动态快照（数据修好即消失），
    故漏网项**不持久化**进 pending，只在 confirm 前审计 + list 展示，避免僵尸条目。
    闸门只认 pending 清空 —— 若漏网项非空，confirm 必须挡下（G-1.9 完整性）。
    """
    if not isinstance(data, dict) or "structured_rows" not in data:
        return []
    try:
        from data_quality_check import recalc_pending
    except ImportError:
        try:
            from .data_quality_check import recalc_pending
        except ImportError:
            return []
    try:
        suspects = recalc_pending(data)
    except Exception:
        return []
    existing = set()
    for it in _pending_items(doc):
        f = resolve_field(str(it.get("field", ""))) or str(it.get("field", ""))
        existing.add((_safe_int(it.get("table")), f))
    missing: List[Dict[str, Any]] = []
    for s in suspects:
        if not isinstance(s, dict):
            continue
        f = resolve_field(str(s.get("field", ""))) or str(s.get("field", ""))
        if (_safe_int(s.get("table")), f) in existing:
            continue
        entry = dict(s)
        entry["source"] = "recalc补漏"
        missing.append(entry)
    return missing


# ========== 建议值计算（现场重算，含文本建议值） ==========

def compute_suggestions_for_doc(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """现场重算该文档全部行的建议值，返回 { row_index(1-based): {field: {...}} }。

    复用 data_quality_check.infer_values：数值链 inferred 与文本建议值（suggested_only）
    都在 row_inferred 中；文本建议值只建议不入库，故这里必须现场重算，不能只读落库 inferred。
    """
    try:
        from data_quality_check import infer_values
    except ImportError:
        try:
            from .data_quality_check import infer_values
        except ImportError:
            return {}
    if not isinstance(data, dict) or "structured_rows" not in data:
        return {}
    try:
        result = infer_values(data)
    except Exception:
        return {}
    measured = result.get("row_inferred") or {}
    return {str(k): v for k, v in measured.items()}


def _matched_row_index(rows: List[Dict[str, Any]], item: Dict[str, Any]) -> Optional[int]:
    """把 pending 项定位到 structured_rows 中的 1-based 行号。

    优先 row_index；其次按 表+桩号 匹配第一个命中。
    """
    ri = item.get("row_index")
    if ri is not None:
        ri0 = _safe_int(ri)
        if ri0 is not None and 1 <= ri0 <= len(rows):
            return ri0
    table = _safe_int(item.get("table"))
    pile_no = item.get("pile_no")
    if pile_no:
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                continue
            if table is not None and _safe_int(r.get("table"), -1) != table:
                continue
            if sanitize_value(r.get("pile_no")) == sanitize_value(pile_no):
                return i + 1
    # 无 row_index 且无桩号：表级项，交由调用方整表扫描（此处返回 None）
    return None


def _suggestion_text(item: Dict[str, Any], suggestions: Dict[str, Dict[str, Any]],
                     rows: List[Dict[str, Any]]) -> str:
    """为 pending 项匹配建议值，返回展示文本；无则空串。

    定位策略：优先 row_index / 表+桩号命中单行；表级项（无桩号）则扫描整表所有行，
    取第一个含该字段建议值的行（典型建议足以提示用户，不必逐行）。
    """
    field_en = resolve_field(item.get("field", ""))
    if not field_en or not suggestions:
        return ""

    # 1) 精确单行：row_index 或 表+桩号
    ri = _matched_row_index(rows, item)
    if ri is not None:
        hit = suggestions.get(str(ri))
        if isinstance(hit, dict) and isinstance(hit.get(field_en), dict):
            return _fmt_suggestion(item, hit[field_en])

    # 2) 表级项：扫描该表全部行，取第一个含该字段建议值的行
    table = _safe_int(item.get("table"))
    if table is not None and not item.get("pile_no") and item.get("row_index") is None:
        for i, r in enumerate(rows):
            if not isinstance(r, dict) or _safe_int(r.get("table"), -1) != table:
                continue
            hit = suggestions.get(str(i + 1))
            if isinstance(hit, dict) and isinstance(hit.get(field_en), dict):
                return _fmt_suggestion(item, hit[field_en])
    return ""


def _fmt_suggestion(item: Dict[str, Any], val: Dict[str, Any]) -> str:
    """把单条建议值 dict 格式化为展示文本."""
    conf = round(float(val.get("confidence", 0)), 2)
    hint = "建议值" if val.get("suggested_only") else "推断值"
    return f"【{hint} {conf}】{val.get('value', '')}（{val.get('source', '')}）"


def _derive_page(doc: Dict[str, Any], rows: List[Dict[str, Any]], item: Dict[str, Any]) -> Optional[int]:
    """为 pending 项推导页码定位，便于用户在纸质/PDF 中定位。

    优先级：
      1. item 自带 page → 直接用；
      2. 命中行的 row['page'] → 用该页；
      3. docx 扫描件（每页≈一张表，表数==页数）→ page = table + 1；
    无据可依（不臆造）→ 返回 None。
    """
    p = _safe_int(item.get("page"))
    if p is not None:
        return p
    n_pages = _safe_int(doc.get("page_count")) or _safe_int(doc.get("pages"))
    ri = _matched_row_index(rows, item)
    if ri is not None and 0 <= ri - 1 < len(rows) and isinstance(rows[ri - 1], dict):
        rp = _safe_int(rows[ri - 1].get("page"))
        if rp is not None:
            return rp
    table = _safe_int(item.get("table"))
    if table is not None:
        n_tables = len({_safe_int(r.get("table")) for r in rows
                        if isinstance(r, dict) and r.get("table") is not None})
        if n_pages is not None and n_tables == n_pages:
            return table + 1
    return None


def cmd_list(args) -> int:
    project_dir = Path(args.project_dir)
    base = resolve_data_base(project_dir, args.out)
    index = load_json(base / "index.json")
    if not index:
        print(json.dumps({"status": "error", "reason": f"index.json 不存在: {base / 'index.json'}"}, ensure_ascii=False))
        return 1

    docs = index.get("documents", [])
    if args.doc:
        docs = [d for d in docs if d.get("id") == args.doc]
    elif args.original_file:
        docs = [d for d in docs if d.get("original_file") == args.original_file]

    result: Dict[str, Any] = {"status": "ok", "documents": []}
    for doc in docs:
        items = _pending_items(doc)
        # 读取数据文件并现场重算建议值（文本建议值只建议不入库，必须现场算）
        data = None
        suggestions: Dict[str, Dict[str, Any]] = {}
        data_file = doc_data_file(base, doc)
        if data_file != base:
            data = load_json(data_file)
        # H-5 接线：重扫漏网应疑项（pending 空 ≠ 数据干净，生成期规则有漏时这里兜底暴露）
        recalc_missing = _recalc_missing(data, doc) if data else []
        if not items and not recalc_missing:
            continue
        if data and "structured_rows" in data:
            suggestions = compute_suggestions_for_doc(data)
        rows = data.get("structured_rows", []) if isinstance(data, dict) else []
        # 按表分组
        tables: Dict[int, List[Dict[str, Any]]] = {}
        for it in items:
            tables.setdefault(_safe_int(it.get("table"), 0), []).append(it)
        grouped = []
        for ti in sorted(tables):
            if args.table is not None and ti != int(args.table):
                continue
            table_items = []
            for it in tables[ti]:
                out_item = dict(it)
                page = _derive_page(doc, rows, it)
                if page is not None:
                    out_item["page"] = page
                sug = _suggestion_text(it, suggestions, rows)
                if sug:
                    out_item["suggestion"] = sug
                table_items.append(out_item)
            grouped.append({"table": ti, "items": table_items})
        result["documents"].append({
            "doc_id": doc.get("id"),
            "original_file": doc.get("original_file"),
            "doc_type": doc.get("doc_type"),
            "n_pending": len(items),
            "n_recalc_missing": len(recalc_missing),
            "recalc_missing_items": recalc_missing,
            "tables": grouped,
        })

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for d in result["documents"]:
            print(f"\n=== {d['doc_id']} | {d['original_file']} | 存疑 {d['n_pending']} 条"
                  + (f" | 重扫漏网 {d['n_recalc_missing']} 条" if d.get("n_recalc_missing") else "")
                  + " ===")
            for t in d["tables"]:
                print(f"\n【表 {t['table']}】")
                for it in t["items"]:
                    line = f"  - [{it.get('field')}] 原值『{it.get('raw', '')}』 {it.get('reason', '')}"
                    if it.get("pile_no"):
                        line = f"  桩号 {it.get('pile_no')} |" + line
                    line = (f"  第{it.get('page')}页 |" if it.get("page") else "  ") + line.lstrip()
                    if it.get("suggestion"):
                        line += f"\n        -> {it.get('suggestion')}"
                    print(line)
            for it in d.get("recalc_missing_items") or []:
                tb = it.get("table")
                tb_txt = f"【表 {tb}】" if tb is not None else "【全文档】"
                print(f"\n{tb_txt} [recalc补漏] [{it.get('field')}] 原值『{it.get('raw', '')}』 {it.get('reason', '')}")
    return 0


# ========== apply：应用聊天修正 ==========

def _safe_int(v: Any, default: Optional[int] = None) -> Optional[int]:
    """安全整型转换：非数字/None 时返回默认值，杜绝 int() 崩溃（聊天解析输入不可信）。"""
    if v is None:
        return default
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def _locate_rows(rows: List[Dict[str, Any]], table: Optional[int], pile_no: Optional[str],
                 row_index: Optional[int]) -> List[int]:
    """按 表+桩号 或 row_index 定位结构化行，返回 0-based 行索引列表。

    row_index 采用 1-based（与数据编辑器/用户看到的一致，从 1 开始），内部转 0-based。
    """
    idxs: List[int] = []
    if row_index is not None:
        ri = _safe_int(row_index)
        if ri is not None:
            ri0 = ri - 1  # 1-based（用户/编辑器视角）→ 0-based 内部索引
            if 0 <= ri0 < len(rows):
                idxs.append(ri0)
        return idxs
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        if _safe_int(r.get("table"), -1) != table:
            continue
        if pile_no is not None:
            if sanitize_value(r.get("pile_no")) == sanitize_value(pile_no):
                idxs.append(i)
        else:
            idxs.append(i)
    return idxs


def _validate_field_value(field: str, value: str) -> Optional[str]:
    """取值边界校验。返回 None 表示通过；否则返回失败原因。"""
    if field in NUMERIC_FIELDS:
        if value == "":
            return None  # 确认空白合法
        if try_float(value) is None:
            return f"数值字段『{FIELD_LABELS.get(field, field)}』取值『{value}』不可解析为数字"
        return None
    # 文本/时间字段不设边界（用户为权威输入），仅限制长度防止误填
    if len(value) > 200:
        return f"字段『{FIELD_LABELS.get(field, field)}』取值过长"
    return None


def _apply_single(rows: List[Dict[str, Any]], corr: Dict[str, Any],
                  doc_id: str, source: str, failures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """应用单条修正，返回修正留痕记录列表（可能 0..n 条）。"""
    table = corr.get("table")
    field = resolve_field(corr.get("field", ""))
    if field is None:
        failures.append({"table": table, "field": corr.get("field", ""),
                         "value": corr.get("value", ""), "reason": "无法识别的字段名"})
        return []

    # 特殊「整行」项：仅接受 accept=true（确认整行原样保留），不得逐字段改写
    if field == ROW_LEVEL_ACCEPT_FIELD:
        if not bool(corr.get("accept")):
            failures.append({"table": table, "field": ROW_LEVEL_ACCEPT_FIELD,
                             "pile_no": corr.get("pile_no"), "row_index": corr.get("row_index"),
                             "value": corr.get("value", ""),
                             "reason": "『整行』存疑项仅支持 accept=true 确认整行原样保留，请勿提供改值"})
            return []
        pile_no = corr.get("pile_no")
        row_index = corr.get("row_index")
        idxs = _locate_rows(rows, _safe_int(table, -1), pile_no, row_index)
        if not idxs:
            failures.append({"table": table, "field": ROW_LEVEL_ACCEPT_FIELD,
                             "pile_no": pile_no, "row_index": row_index,
                             "reason": "未定位到匹配行（表/桩号/行号不匹配）"})
            return []
        records: List[Dict[str, Any]] = []
        for i in idxs:
            r = rows[i]
            if not isinstance(r, dict):
                continue
            records.append({
                "doc_id": doc_id,
                "table": _safe_int(table),
                "row_index": i,
                "field": ROW_LEVEL_ACCEPT_FIELD,
                "field_label": "整行",
                "original_value": sanitize_value(r.get("pile_no")),
                "corrected_value": sanitize_value(r.get("pile_no")),
                "reason": "用户确认整行原值无误",
                "source": source,
                "timestamp": now_iso(),
            })
        return records

    if field not in ALL_FIELDS:
        failures.append({"table": table, "field": corr.get("field", ""),
                         "value": corr.get("value", ""), "reason": f"字段不属于本资料支持字段（{field}）"})
        return []

    value = sanitize_value(corr.get("value"))
    accept = bool(corr.get("accept"))

    if not accept:
        err = _validate_field_value(field, value)
        if err:
            failures.append({"table": table, "field": corr.get("field", ""),
                             "value": corr.get("value", ""), "reason": err})
            return []
        # 数值字段：归一化（全角/半角逗号→小数点，如 "1，2"→"1.2"），避免下游读到脏值
        if field in NUMERIC_FIELDS and value != "":
            fv = try_float(value)
            if fv is not None:
                value = _fmt_number(fv)

    pile_no = corr.get("pile_no")
    row_index = corr.get("row_index")
    idxs = _locate_rows(rows, _safe_int(table, -1), pile_no, row_index)
    if not idxs:
        failures.append({"table": table, "field": corr.get("field", ""),
                         "pile_no": pile_no, "row_index": row_index,
                         "value": corr.get("value", ""), "reason": "未定位到匹配行（表/桩号/行号不匹配）"})
        return []

    # 表级字段：作用于该表全部行
    apply_idxs = idxs
    if field in TABLE_LEVEL_FIELDS:
        apply_idxs = [i for i in range(len(rows))
                      if isinstance(rows[i], dict) and _safe_int(rows[i].get("table"), -1) == _safe_int(table, -1)]
        if not apply_idxs:
            apply_idxs = idxs

    records: List[Dict[str, Any]] = []
    for i in apply_idxs:
        r = rows[i]
        if not isinstance(r, dict):
            continue
        orig = sanitize_value(r.get(field))
        new_val = orig if accept else value
        if accept or new_val != orig:
            r[field] = new_val
        # reason 优先级：修正里显式给出的（如『用户采纳建议值（…）』）> 默认确认语义
        reason = corr.get("reason", "")
        if not reason:
            reason = "用户确认原值无误" if accept else ""
        records.append({
            "doc_id": doc_id,
            "table": _safe_int(table),
            "row_index": i,
            "field": field,
            "field_label": FIELD_LABELS.get(field, field),
            "original_value": orig,
            "corrected_value": new_val,
            "reason": reason,
            "source": source,
            "timestamp": now_iso(),
        })
    return records


def _resolve_pending(doc: Dict[str, Any], rows: List[Dict[str, Any]],
                     applied: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """根据已应用修正，从 doc.pending_verification 里剔除已核对项，返回剩余项。

    由 applied 记录构造「已核对 (table, field, pile_no)」集合（桩号从修正行反查）：
      - 表级字段（施工部位/施工日期）：按 表+字段 命中即销项（不限桩号）
      - 行级字段（数值/时间字段）：按 表+字段+桩号 命中才销项
    """
    items = _pending_items(doc)
    if not items:
        return items

    resolved: Dict[tuple, bool] = {}
    for rec in applied:
        table = rec.get("table")
        field = rec.get("field")
        if table is None or not field:
            continue
        pile_no = ""
        ri = rec.get("row_index")
        if isinstance(ri, int) and 0 <= ri < len(rows) and isinstance(rows[ri], dict):
            pile_no = sanitize_value(rows[ri].get("pile_no"))
        resolved[(table, field, pile_no)] = True

    remaining: List[Dict[str, Any]] = []
    for it in items:
        table = it.get("table")
        field = it.get("field", "")
        field_name = PENDING_FIELD_TO_NAME.get(field, field)  # 中文标签→字段名
        pile_no = sanitize_value(it.get("pile_no"))
        if field_name in TABLE_LEVEL_FIELDS:
            matched = any(t == table and f == field_name for (t, f, _p) in resolved)
        elif field_name == ROW_LEVEL_ACCEPT_FIELD:
            # 整行项：按 表+桩号 命中（field=整行 且 桩号一致）即销项
            matched = any(t == table and f == ROW_LEVEL_ACCEPT_FIELD and p == pile_no for (t, f, p) in resolved)
        else:
            matched = (table, field_name, pile_no) in resolved
        if not matched:
            remaining.append(it)
    return remaining


def _update_index_corrections(index: Dict[str, Any], doc_id: str, n: int,
                              failed: Optional[List[Dict[str, Any]]] = None) -> None:
    corr = index.setdefault("corrections", {"total": 0, "files": []})
    corr["total"] = int(corr.get("total", 0)) + n
    files = corr.setdefault("files", [])
    for f in files:
        if f.get("doc_id") == doc_id:
            f["count"] = int(f.get("count", 0)) + n
            return
    files.append({"doc_id": doc_id, "count": n, "corrections_file": "修正记录/corrections.json"})


def cmd_apply(args) -> int:
    project_dir = Path(args.project_dir)
    base = resolve_data_base(project_dir, args.out)
    index = load_json(base / "index.json")
    if not index:
        print(json.dumps({"status": "error", "reason": f"index.json 不存在: {base / 'index.json'}"}, ensure_ascii=False))
        return 1

    doc = find_doc(index, args.doc, args.original_file)
    if not doc:
        print(json.dumps({"status": "error", "reason": f"未找到文档（--doc {args.doc}）"}, ensure_ascii=False))
        return 1

    corr_path = Path(args.corrections)
    if not corr_path.exists():
        print(json.dumps({"status": "error", "reason": f"修正文件不存在: {corr_path}"}, ensure_ascii=False))
        return 1
    corrections = load_json(corr_path)
    if not isinstance(corrections, list):
        print(json.dumps({"status": "error", "reason": "修正文件必须是 JSON 数组"}, ensure_ascii=False))
        return 1

    source = args.source or "user_dialog"
    data_file = doc_data_file(base, doc)
    data = load_json(data_file)
    if not data or "structured_rows" not in data:
        print(json.dumps({"status": "error", "reason": f"数据文件缺少 structured_rows: {data_file}"}, ensure_ascii=False))
        return 1
    rows = data["structured_rows"]
    if not isinstance(rows, list):
        print(json.dumps({"status": "error", "reason": "structured_rows 不是数组"}, ensure_ascii=False))
        return 1

    # 应用全部修正
    applied: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    doc_id = doc.get("id", "?")
    # 仅当存在「采纳建议值」（accept_recommended）时现场重算一次建议值（零转抄：AI 不抄录数值）
    suggestions: Dict[str, Dict[str, Any]] = {}
    if any(isinstance(c, dict) and c.get("accept_recommended") for c in corrections):
        suggestions = compute_suggestions_for_doc(data)
    for corr in corrections:
        if not isinstance(corr, dict):
            failed.append({"field": "", "value": "", "reason": "修正项不是对象"})
            continue
        # 零转抄：accept_recommended=true 时，由脚本现场取建议值填入，杜绝 AI 把数值抄错
        if corr.get("accept_recommended"):
            field_en = resolve_field(corr.get("field", ""))
            ri = _matched_row_index(rows, corr)
            row_sug = suggestions.get(str(ri)) if ri is not None else None
            if not field_en or not row_sug or not isinstance(row_sug.get(field_en), dict):
                failed.append({"table": corr.get("table"), "field": corr.get("field", ""),
                               "value": "",
                               "reason": "该格无可采纳的建议值（建议值计算未命中或字段无建议）"})
                continue
            corr = dict(corr)
            # 清掉 accept 语义，改用具体建议值落库，并标注来源
            corr["value"] = row_sug[field_en]["value"]
            corr["accept"] = False
            corr["reason"] = f"用户采纳建议值（{row_sug[field_en].get('source', '')}）"
        applied.extend(_apply_single(rows, corr, doc_id, source, failed))

    # 写回数据文件（structured_rows 已更新）
    data["structured_rows"] = rows
    save_json(data_file, data)

    # 留痕 corrections.json（追加，不去重）——落 修正记录/ 子目录（与 SKILL.md 输出契约一致）
    audit_file = base / "修正记录" / "corrections.json"
    audit = load_json(audit_file)
    if not isinstance(audit, dict):
        audit = {"schema_version": "1.0", "entries": []}
    audit.setdefault("schema_version", "1.0")
    entries = audit.setdefault("entries", [])
    entries.extend(applied)
    save_json(audit_file, audit)

    # 更新 index：corrections 汇总（含失败清单）+ 剩余存疑项 + 文档状态
    n_pending_before = len(_pending_items(doc))
    remaining = _resolve_pending(doc, rows, applied)
    doc["pending_verification"] = remaining
    doc["last_updated"] = now_iso()
    if remaining:
        doc["summarized_status_note"] = f"扫描转化电子文档，{len(remaining)} 条存疑项待人工核对（部位/日期/数值）"
        doc["human_verified"] = False
    _update_index_corrections(index, doc_id, len(applied), failed)
    if failed:
        # 失败清单落盘进 index.corrections（契约 D 要求同步失败清单；只保留最近一轮）
        index.setdefault("corrections", {}).setdefault("failed", [])
        index["corrections"]["failed"] = [
            dict(x, doc_id=doc_id, table=_safe_int(x.get("table")))
            for x in failed
        ]
    index["updated_at"] = now_iso()
    save_json(base / "index.json", index)

    # 同步数据文件里的 pending_verification（保持双写一致，供阶段3 消费）
    data["pending_verification"] = remaining
    save_json(data_file, data)

    print(json.dumps({
        "status": "ok",
        "doc_id": doc_id,
        "applied": applied,
        "failed": failed,
        "resolved_pending": n_pending_before - len(remaining),
        "remaining_pending": len(remaining),
        "corrections_total": index.get("corrections", {}).get("total", 0),
    }, ensure_ascii=False, indent=2))
    return 0 if not failed else 2


# ========== refresh：仅刷新建议值（不碰核对进度/存疑清单/留痕） ==========

def cmd_refresh(args) -> int:
    """仅重算并写回 inferred 建议值；文本建议值（suggested_only）不落库，也不改 pending/human_verified/corrections。

    用于在不重建底座的前提下，让结构化行拿到最新规则算出的数值链推断值。
    铁律：不外扩做任何破坏性操作，只重写每行 inferred。
    """
    project_dir = Path(args.project_dir)
    base = resolve_data_base(project_dir, args.out)
    index = load_json(base / "index.json")
    if not index:
        print(json.dumps({"status": "error", "reason": f"index.json 不存在: {base / 'index.json'}"}, ensure_ascii=False))
        return 1

    docs = index.get("documents", [])
    if args.doc:
        docs = [d for d in docs if d.get("id") == args.doc]
    elif args.original_file:
        docs = [d for d in docs if d.get("original_file") == args.original_file]

    touched = []
    for doc in docs:
        data_file = doc_data_file(base, doc)
        if data_file == base:
            continue
        data = load_json(data_file)
        if not isinstance(data, dict) or "structured_rows" not in data:
            continue
        suggestions = compute_suggestions_for_doc(data)
        rows = data["structured_rows"]
        if not isinstance(rows, list):
            continue
        # 安全写回：仅数值链 inferred（排除 suggested_only），保持其他字段不动
        updated = 0
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                continue
            row_sug = suggestions.get(str(i + 1))
            persistable = {}
            if row_sug:
                persistable = {
                    k: v for k, v in row_sug.items()
                    if isinstance(v, dict) and not v.get("suggested_only")
                }
            prev = r.get("inferred") or {}
            if prev != persistable:
                r["inferred"] = persistable
                updated += 1
        data["structured_rows"] = rows
        save_json(data_file, data)
        touched.append({"doc_id": doc.get("id"), "rows_updated": updated})

    print(json.dumps({"status": "ok", "documents": touched, "refresh": "仅重算并写回 inferred，未触碰 pending/human_verified/corrections"}, ensure_ascii=False, indent=2))
    return 0


# ========== confirm：确认核对完成 → human_verified=true ==========

def cmd_confirm(args) -> int:
    project_dir = Path(args.project_dir)
    base = resolve_data_base(project_dir, args.out)
    index = load_json(base / "index.json")
    if not index:
        print(json.dumps({"status": "error", "reason": f"index.json 不存在: {base / 'index.json'}"}, ensure_ascii=False))
        return 1

    doc = find_doc(index, args.doc, args.original_file)
    if not doc:
        print(json.dumps({"status": "error", "reason": f"未找到文档（--doc {args.doc}）"}, ensure_ascii=False))
        return 1

    remaining = _pending_items(doc)
    # H-5 接线：闸门完整性审计 —— 全量重扫当前数据，存量 pending 之外的漏网项
    # 未清不得放行（生成期扫描规则有漏时，漏网项会当真值进报告）
    data_file = doc_data_file(base, doc)
    data = load_json(data_file) if data_file != base else None
    recalc_missing = _recalc_missing(data, doc) if data else []
    if (remaining or recalc_missing) and not args.force:
        print(json.dumps({
            "status": "blocked",
            "reason": (
                f"仍有 {len(remaining)} 条存疑项未核对"
                + (f"；另重扫发现 {len(recalc_missing)} 条漏网应疑项" if recalc_missing else "")
                + "，禁止确认（G-1.9 硬停；AI 不得绕过人工核对闸门）"
            ),
            "remaining_pending": len(remaining),
            "remaining": remaining[:10],
            "recalc_missing": len(recalc_missing),
            "recalc_missing_items": recalc_missing[:10],
        }, ensure_ascii=False, indent=2))
        return 1

    doc["human_verified"] = True
    doc["last_updated"] = now_iso()
    if args.confirm_classification:
        index["file_classification_confirmed"] = True
        index["classification_pending_count"] = 0
    if index.get("stage") == "foundation_built":
        index["stage"] = "human_review"
    index["updated_at"] = now_iso()
    save_json(base / "index.json", index)

    # 同步数据文件 pending_verification 清空（data 已在闸门审计前加载，直接复用）
    if data and "pending_verification" in data:
        data["pending_verification"] = []
        save_json(data_file, data)

    print(json.dumps({
        "status": "ok",
        "doc_id": doc.get("id"),
        "human_verified": True,
        "stage": index.get("stage"),
        "classification_confirmed": index.get("file_classification_confirmed", False),
    }, ensure_ascii=False, indent=2))
    return 0


# ========== status：核对进度 ==========

def cmd_status(args) -> int:
    project_dir = Path(args.project_dir)
    base = resolve_data_base(project_dir, args.out)
    index = load_json(base / "index.json")
    if not index:
        print(json.dumps({"status": "error", "reason": f"index.json 不存在: {base / 'index.json'}"}, ensure_ascii=False))
        return 1

    docs = index.get("documents", [])
    summary = []
    for d in docs:
        if d.get("doc_role") == "excluded":
            continue
        items = _pending_items(d)
        summary.append({
            "doc_id": d.get("id"),
            "original_file": d.get("original_file"),
            "doc_type": d.get("doc_type"),
            "human_verified": d.get("human_verified", False),
            "pending": len(items),
            "audit_status": d.get("audit_status"),
        })
    all_verified = bool(summary) and all(s["human_verified"] for s in summary)
    print(json.dumps({
        "status": "ok",
        "stage": index.get("stage"),
        "documents": summary,
        "all_human_verified": all_verified,
        "classification_confirmed": index.get("file_classification_confirmed", False),
        "classification_pending_count": index.get("classification_pending_count", 0),
        "corrections_total": index.get("corrections", {}).get("total", 0),
    }, ensure_ascii=False, indent=2))
    return 0


# ========== main ==========

def main() -> int:
    parser = argparse.ArgumentParser(description="Chat-Verify 人工核对应用器（阶段2 聊天式核对后端）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出待核对存疑项（按表分组）")
    p_list.add_argument("project_dir")
    p_list.add_argument("--doc")
    p_list.add_argument("--original-file")
    p_list.add_argument("--table", type=int)
    p_list.add_argument("--out", default=OUT_DIR_NAME)
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_apply = sub.add_parser("apply", help="应用聊天修正（写 corrections.json + 更新 structured_rows + 同步 index）")
    p_apply.add_argument("project_dir")
    p_apply.add_argument("--doc")
    p_apply.add_argument("--original-file")
    p_apply.add_argument("--corrections", required=True, help="修正 JSON 数组文件路径")
    p_apply.add_argument("--source", default="user_dialog")
    p_apply.add_argument("--out", default=OUT_DIR_NAME)
    p_apply.set_defaults(func=cmd_apply)

    p_refresh = sub.add_parser("refresh", help="仅刷新建议值：重算并写回 inferred，不触碰 pending/human_verified/corrections")
    p_refresh.add_argument("project_dir")
    p_refresh.add_argument("--doc")
    p_refresh.add_argument("--original-file")
    p_refresh.add_argument("--out", default=OUT_DIR_NAME)
    p_refresh.set_defaults(func=cmd_refresh)

    p_confirm = sub.add_parser("confirm", help="确认核对完成 → human_verified=true（进阶段3）")
    p_confirm.add_argument("project_dir")
    p_confirm.add_argument("--doc")
    p_confirm.add_argument("--original-file")
    p_confirm.add_argument("--confirm-classification", action="store_true",
                           help="同时确认分类：file_classification_confirmed=true 并清空 pending")
    p_confirm.add_argument("--force", action="store_true",
                           help="仅用于人工核对确认放行；AI 禁止使用（生产环境应禁用）")
    p_confirm.add_argument("--out", default=OUT_DIR_NAME)
    p_confirm.set_defaults(func=cmd_confirm)

    p_status = sub.add_parser("status", help="查看核对进度")
    p_status.add_argument("project_dir")
    p_status.add_argument("--out", default=OUT_DIR_NAME)
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
