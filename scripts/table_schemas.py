# -*- coding: utf-8 -*-
"""
table_schemas.py — 表格 schema 注册表（自成长）v1.0

负责未知表格（AI 第一次见）的列角色沉淀与复用：
- 值格式锚点（table_struct.infer_column_roles）无法判列时，按表头文字匹配已知 schema。
- 匹配成功 → 直接用 schema 的列别名映射出列角色，执行完整审核。
- 匹配失败 → 标记 schema_status=unknown_domain，仅执行通用检查；人工确认后 register_schema 沉淀复用。

与 table_struct 分层：table_struct 是"值格式指纹"主引擎；本模块是"表头文字"兜底 + 自成长存储。
纯函数 + 文件读写，无业务副作用，可独立单测。
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCHEMAS_FILE = Path(__file__).resolve().parent.parent / "rules" / "table-schemas.json"


def _norm(t: str) -> str:
    """表头文字规范化：去括号注释、去空白、小写化。"""
    return re.sub(r"[（(].*?[)）]", "", str(t or "")).replace(" ", "").replace("\n", "").lower()


def load_schemas() -> List[Dict[str, Any]]:
    """读取 table-schemas.json 全部 schema。"""
    if not _SCHEMAS_FILE.exists():
        return []
    try:
        with open(_SCHEMAS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("schemas", [])
    except (json.JSONDecodeError, OSError):
        return []


def match_schema(doc_type: str = "", header_texts: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """按 doc_type 关键词 + 表头文字匹配最合适的已知 schema。

    匹配规则：
    1. doc_type 命中 schema.doc_type_keywords 任一 → 候选。
    2. 候选按表头文字覆盖度排序（header_aliases 里命中别名最多的）取最高。
    3. 无候选或表头覆盖度 < 阈值 → 返回 None（交由 unknown_domain 流程）。
    """
    schemas = load_schemas()
    if not schemas:
        return None

    lower_doc = (doc_type or "").lower()
    header_texts = [_norm(h) for h in (header_texts or []) if h]

    candidates: List[Dict[str, Any]] = []
    for sch in schemas:
        hit = False
        if lower_doc and any(kw in lower_doc for kw in sch.get("doc_type_keywords", [])):
            hit = True
        aliases = sch.get("header_aliases", {})
        if not hit and header_texts:
            # 表头覆盖度：别名扁平化后，被当前表头命中的别名数
            flat = [a.lower() for vals in aliases.values() for a in vals]
            coverage = sum(1 for a in flat if any(a in ht for ht in header_texts))
            if coverage >= 2:
                hit = True
        if hit:
            candidates.append(sch)

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # 多候选：取表头别名覆盖度最高者
    def _coverage(sch: Dict[str, Any]) -> int:
        flat = [a.lower() for vals in sch.get("header_aliases", {}).values() for a in vals]
        return sum(1 for a in flat if any(a in ht for ht in header_texts))
    return max(candidates, key=_coverage)


def column_roles_from_schema(schema: Optional[Dict[str, Any]], header_texts: Optional[List[str]]) -> Dict[str, str]:
    """由 schema 的 header_aliases 把"表头文字 → 字段名"映射出来。

    返回 {规范化的表头文字: 字段名}。仅用于 unknown 表格的列角色兜底，
    与 table_struct 的值格式锚点互补；返回空 dict 表示无可用映射。
    """
    if not schema:
        return {}
    aliases = schema.get("header_aliases", {})
    result: Dict[str, str] = {}
    for field, alias_list in aliases.items():
        for a in alias_list:
            result[a.lower()] = field
    return result


def register_schema(
    name: str,
    doc_type_keywords: List[str],
    header_aliases: Dict[str, List[str]],
    confirmed_by: str,
    source: str = "manual_confirmation",
) -> Dict[str, Any]:
    """人工/AI 确认未知表格的列语义后，沉淀为新 schema 写入注册表。

    返回新 schema dict；若同名 schema 已存在则追加别名（增量自成长）。
    """
    schemas = load_schemas()
    norm_name = _norm(name)
    existing = next((s for s in schemas if _norm(s.get("name", "")) == norm_name), None)

    if existing:
        # 增量：合并 doc_type 关键词与别名
        for kw in doc_type_keywords:
            if kw.lower() not in [k.lower() for k in existing.get("doc_type_keywords", [])]:
                existing.setdefault("doc_type_keywords", []).append(kw)
        for field, aliases in header_aliases.items():
            existing.setdefault("header_aliases", {}).setdefault(field, [])
            for a in aliases:
                if a.lower() not in [x.lower() for x in existing["header_aliases"][field]]:
                    existing["header_aliases"][field].append(a)
        existing["status"] = "known_domain"
        existing["confirmed_by"] = confirmed_by
        existing["confirmed_at"] = _now_iso()
        existing["source"] = source
        new_schema = existing
    else:
        new_schema = {
            "schema_id": _next_id(schemas),
            "name": name,
            "status": "known_domain",
            "doc_type_keywords": list(doc_type_keywords),
            "header_aliases": header_aliases,
            "confirmed_by": confirmed_by,
            "confirmed_at": _now_iso(),
            "source": source,
        }
        schemas.append(new_schema)

    _write(schemas)
    return new_schema


def _next_id(schemas: List[Dict[str, Any]]) -> str:
    n = len(schemas) + 1
    while any(s.get("schema_id") == f"SCHEMA-{n:03d}" for s in schemas):
        n += 1
    return f"SCHEMA-{n:03d}"


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().astimezone().isoformat()


def _write(schemas: List[Dict[str, Any]]) -> None:
    payload = {
        "schema_version": "1.0",
        "description": "表格 schema 注册表（自成长）。",
        "schemas": schemas,
    }
    _SCHEMAS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_SCHEMAS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        for s in load_schemas():
            print(f"{s.get('schema_id')}\t{s.get('status')}\t{s.get('name')}")