# -*- coding: utf-8 -*-
"""
v7.2 V-70 自成长导入脚本（import_corrections.py）
===================================================

功能：
    读取 data-editor 导出的人工修正记录 JSON，将分类修正和表头映射修正
    回流为候选词条，写入 classification-terms.json candidates 和
    header-aliases.json，供下次 build 自动命中。

用法：
    python scripts/import_corrections.py <修正记录JSON路径>

修正记录 JSON 格式（data-editor 导出）：
    {
        "classification_corrections": [
            {
                "file": "某文件名.xlsx",
                "original_professional": "通用资料",
                "corrected_professional": "01_场道工程",
                "corrected_doc_type": "CFG桩施工记录",
                "keyword_pattern": "CFG桩",
                "corrected_at": "2026-08-01T10:00:00"
            }
        ],
        "header_corrections": [
            {
                "file": "碎石桩施工记录.pdf",
                "original_header": "灌入量",
                "corrected_slot": "volume",
                "sync_to_global": true,
                "corrected_at": "2026-08-01T10:05:00"
            }
        ]
    }

约束：
    - 候选词条 status=candidate，需人工在分类确认面板确认后变 active
    - 表头别名同步需 sync_to_global=true 才写入，防污染
    - 不覆盖已有词条，仅追加
"""

import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TERMS_FILE = SKILL_DIR / "references" / "classification-terms.json"
HEADER_ALIASES_FILE = SKILL_DIR / "references" / "header-aliases.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def import_classification_corrections(corrections: list) -> tuple:
    """将分类修正写入 classification-terms.json candidates。
    返回 (新增数, 跳过数)。
    """
    terms_data = load_json(TERMS_FILE)
    if not terms_data:
        print(f"[!] 未找到 {TERMS_FILE}，请先运行 build_foundation.py 初始化", file=sys.stderr)
        return 0, 0

    candidates = terms_data.setdefault("candidates", [])
    existing_keys = {
        (c.get("keyword", ""), c.get("prof", ""))
        for c in candidates
    }

    added = 0
    skipped = 0
    for corr in corrections:
        prof = corr.get("corrected_professional", "")
        keyword = corr.get("keyword_pattern", "")
        if not prof or not keyword:
            skipped += 1
            continue
        key = (keyword, prof)
        if key in existing_keys:
            skipped += 1
            continue
        candidates.append({
            "keyword": keyword,
            "prof": prof,
            "doc_type": corr.get("corrected_doc_type", ""),
            "source_file": corr.get("file", ""),
            "status": "candidate",
            "created_at": corr.get("corrected_at", datetime.now().isoformat(timespec="seconds")),
            "confirmed_by": None,
            "confirmed_at": None,
        })
        existing_keys.add(key)
        added += 1
        print(f"  + 候选词条: '{keyword}' → {prof}", file=sys.stderr)

    if added > 0:
        terms_data["version"] = terms_data.get("version", "1.0.0")
        save_json(TERMS_FILE, terms_data)

    return added, skipped


def import_header_corrections(corrections: list) -> tuple:
    """将表头映射修正写入 header-aliases.json。
    返回 (新增数, 跳过数)。
    """
    aliases_data = load_json(HEADER_ALIASES_FILE)
    if not aliases_data:
        aliases_data = {
            "version": "1.0.0",
            "description": "v7.2 V-70 表头别名自成长存储——人工确认的表头映射回流",
            "slots": {},
        }

    slots = aliases_data.setdefault("slots", {})
    added = 0
    skipped = 0

    for corr in corrections:
        if not corr.get("sync_to_global", False):
            skipped += 1
            continue
        header = corr.get("original_header", "").strip()
        slot = corr.get("corrected_slot", "").strip()
        if not header or not slot:
            skipped += 1
            continue
        slot_entry = slots.setdefault(slot, {"aliases": [], "candidates": []})
        if header in slot_entry["aliases"] or header in slot_entry.get("candidates", []):
            skipped += 1
            continue
        slot_entry.setdefault("candidates", []).append({
            "alias": header,
            "source_file": corr.get("file", ""),
            "status": "candidate",
            "created_at": corr.get("corrected_at", datetime.now().isoformat(timespec="seconds")),
        })
        added += 1
        print(f"  + 表头别名候选: '{header}' → {slot}", file=sys.stderr)

    if added > 0:
        save_json(HEADER_ALIASES_FILE, aliases_data)

    return added, skipped


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/import_corrections.py <修正记录JSON路径>", file=sys.stderr)
        sys.exit(1)

    corrections_file = Path(sys.argv[1])
    if not corrections_file.exists():
        print(f"[!] 修正记录文件不存在: {corrections_file}", file=sys.stderr)
        sys.exit(1)

    data = load_json(corrections_file)
    if not data:
        print(f"[!] 修正记录文件为空或格式错误: {corrections_file}", file=sys.stderr)
        sys.exit(1)

    class_corrs = data.get("classification_corrections", [])
    header_corrs = data.get("header_corrections", [])

    print(f"=== v7.2 V-70 自成长导入 ===", file=sys.stderr)
    print(f"修正记录: {corrections_file.name}", file=sys.stderr)
    print(f"  分类修正: {len(class_corrs)} 条", file=sys.stderr)
    print(f"  表头修正: {len(header_corrs)} 条", file=sys.stderr)
    print(file=sys.stderr)

    if class_corrs:
        print(f"--- 分类候选词条导入 ---", file=sys.stderr)
        cls_added, cls_skipped = import_classification_corrections(class_corrs)
        print(f"  新增 {cls_added} 条，跳过 {cls_skipped} 条", file=sys.stderr)
        print(file=sys.stderr)

    if header_corrs:
        print(f"--- 表头别名候选导入 ---", file=sys.stderr)
        hdr_added, hdr_skipped = import_header_corrections(header_corrs)
        print(f"  新增 {hdr_added} 条，跳过 {hdr_skipped} 条", file=sys.stderr)
        print(file=sys.stderr)

    print(f"=== 导入完成 ===", file=sys.stderr)
    print(f"分类候选词条请在前置信息确认面板中确认后变 active", file=sys.stderr)
    print(f"表头别名候选请在 data-editor 表头映射 Tab 中确认后变 alias", file=sys.stderr)


if __name__ == "__main__":
    main()
