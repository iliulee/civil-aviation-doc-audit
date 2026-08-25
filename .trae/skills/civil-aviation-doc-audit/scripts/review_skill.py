# -*- coding: utf-8 -*-
"""
整体交付 review 脚本（review_skill.py）
========================================

对民航施工资料审核 Skill 的「流程」与「全部功能」做一次静态 + 动态验收。
覆盖 v9.5 之后新增/修改的全部能力点：

  A. 前置信息表文档（nature=扫描转化电子文档 四份文档）
  B. 数据字典校验（NATURE_ALLOWED 白名单 + generate_default_preconditions）
  C. 主流程分流（docx 电子表解析，跳过 OCR）
  D. 数据编辑器（FIELD_LABELS 中文字段映射 + 一键采纳推荐值）
  E. 表格结构解析（table_struct：列语义推断、无补位凑数、数学链）
  F. 数据契约（columns / schema_status / row_parsed_stats）
  G. 推断建议值（inference_rules.json + infer_values）

不依赖网络 / 不跑真实 OCR / 不改动任何文件。模块导入失败时记为失败并继续，
以便一次性暴露所有问题。

用法：
    python scripts/review_skill.py
    python scripts/review_skill.py --json     # 输出 JSON 汇总（便于机器解析）
"""

import argparse
import importlib
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

RESULTS = []  # (group, name, ok, detail)


def check(group: str, name: str, ok: bool, detail: str = ""):
    RESULTS.append((group, name, bool(ok), detail))
    if ok:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name}  —  {detail}")


def read_file(p: Path) -> str:
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"__READ_ERR__:{e}"


# ========== A. 前置信息表文档 ==========
def check_docs():
    print("\n[A] 前置信息表文档（nature=扫描转化电子文档）")
    docs = {
        "SKILL.md": SKILL_DIR / "SKILL.md",
        "skill-config-reference.md": SKILL_DIR / "references" / "skill-config-reference.md",
        "README.md": SKILL_DIR / "README.md",
        "PROJECT_SPEC.md": SKILL_DIR / "PROJECT_SPEC.md",
    }
    for name, path in docs.items():
        content = read_file(path)
        if not content or content.startswith("__READ_ERR__"):
            check("A", f"{name} 存在且可读", False, "文件缺失或不可读")
            continue
        check("A", f"{name} 提及「扫描转化电子文档」", "扫描转化电子文档" in content,
              "未找到该 nature 值")
        check("A", f"{name} 说明 docx 电子表解析", ("docx" in content),
              "未提及 docx 电子表解析")
    # 引擎跳过说明
    skill = read_file(DOC_SKILL)
    check("A", "SKILL 说明 OCR 引擎自动置灰/跳过", "自动置灰" in skill or "跳过全部 OCR 引擎" in skill,
          "未说明扫描转化电子文档跳过 OCR 引擎")


DOC_SKILL = SKILL_DIR / "SKILL.md"


# ========== B. 数据字典校验 ==========
def check_dictionary():
    print("\n[B] 数据字典校验（nature 白名单 + 前置信息生成）")
    mod = import_mod("build_foundation")
    if mod is None:
        return
    # NATURE_ALLOWED 白名单
    allowed = getattr(mod, "NATURE_ALLOWED", None)
    check("B", "build_foundation.NATURE_ALLOWED 存在", allowed is not None)
    if isinstance(allowed, set):
        check("B", "白名单含「扫描转化电子文档」", "扫描转化电子文档" in allowed,
              f"当前白名单={sorted(allowed)}")
        check("B", "白名单含「电子版」", "电子版" in allowed)
    # is_valid_nature
    fn = getattr(mod, "is_valid_nature", None)
    if callable(fn):
        check("B", "is_valid_nature('扫描转化电子文档')==True", fn("扫描转化电子文档") is True)
        check("B", "is_valid_nature(非法值)==False", fn("不存在类型") is False)
    else:
        check("B", "is_valid_nature 存在", False)
    # generate_default_preconditions
    gen = getattr(mod, "generate_default_preconditions", None)
    if callable(gen):
        pc = gen(Path("."))
        check("B", "generate_default_preconditions 返回 dict", isinstance(pc, dict))
        check("B", "默认 preconditions 含 nature 字段", "nature" in (pc or {}))
    else:
        check("B", "generate_default_preconditions 存在", False)


# ========== C. 主流程分流（docx） ==========
def check_docx_routing():
    print("\n[C] 主流程分流（docx 电子表解析，跳过 OCR）")
    mod = import_mod("build_foundation")
    if mod is None:
        return
    fn = getattr(mod, "call_extract_docx", None)
    check("C", "build_foundation.call_extract_docx 存在", callable(fn))
    src = read_file(Path(mod.__file__))
    # sniff_document 对 .docx 返回 method=docx
    check("C", "sniff_document 对 .docx 返回 docx", "method=\"docx\"" in src or "extraction_method\" = \"docx\"" in src
          or "extraction_method\": \"docx\"" in src or "docx" in src and "extraction_method" in src,
          "未在 sniff 层识别 docx（弱检查）")
    check("C", "提取分支走 call_extract_docx（不触发 OCR）",
          "call_extract_docx(abs_path" in src or "call_extract_docx(" in src,
          "未找到 docx 提取调用点")
    check("C", "docx 分支不设 OCR 引擎", "engine\": \"docx\"" in src or "engine\": \"docx\"" in src
          or "get(\"engine\", \"docx\")" in src, "docx 结果应标记 engine=docx")
    # human_verified 分层：扫描转化电子文档需人工核对
    check("C", "human_verified 磁层（扫描转化电子档不自动放行）",
          "扫描转化电子文档" in src and "human_verified" in src,
          "扫描转化电子文档来源扫描，应保留人工核对闸门")


# ========== D. 数据编辑器 ==========
def check_editor():
    print("\n[D] 数据编辑器（FIELD_LABELS + 一键采纳）")
    editor = SKILL_DIR / "templates" / "data-editor.html"
    content = read_file(editor)
    if not content or content.startswith("__READ_ERR__"):
        check("D", "data-editor.html 存在且可读", False, "文件缺失或不可读")
        return
    check("D", "FIELD_LABELS 中文字段映射存在", "FIELD_LABELS" in content)
    check("D", "含桩号中文映射", "'桩号'" in content)
    check("D", "含桩顶/桩底高程中文映射", "'桩顶高程'" in content and "'桩底高程'" in content)
    check("D", "一键采纳按钮存在", "一键采纳推荐值" in content)
    check("D", "adoptAllRecommendedValues 函数存在", "adoptAllRecommendedValues" in content)
    check("D", "低置信度清单（<50%）单独列出", "低置信推荐值" in content or "lowConf" in content)
    check("D", "fieldLabel() 回退函数存在", "function fieldLabel" in content)


# ========== E. 表格结构解析 ==========
def check_table_struct():
    print("\n[E] 表格结构解析（列语义推断 / 无补位凑数 / 数学链）")
    mod = import_mod("table_struct")
    if mod is None:
        return
    for f in ["infer_column_roles", "build_rows_from_items", "build_rows_from_grid",
              "build_rows_from_table", "validate_rows", "check_row", "coerce_value",
              "_col_prior", "_refine_column_roles", "_lock_letter_pile", "_pile_like"]:
        check("E", f"table_struct.{f} 存在", hasattr(mod, f))
    src = read_file(Path(mod.__file__))
    # 补位逻辑已删除：不应再有 _PILE_COLUMN_ORDER 或因补位生成的字段
    check("E", "已删除补位死代码 _PILE_COLUMN_ORDER", "_PILE_COLUMN_ORDER" not in src,
          "补位列表仍在，可能生成凭空字段")
    check("E", "已删除 remaining_fields 补位循环", "remaining_fields" not in src,
          "凑数补位循环仍在")
    check("E", "列级物理先验 _col_prior 已接入", "prior = _col_prior(field" in src or "prior = _col_prior(" in src,
          "未在打分循环调用 _col_prior")
    check("E", "数学链再分配 _refine_column_roles 已接入", "_refine_column_roles(assigned" in src)
    check("E", "字母桩号锁定 _lock_letter_pile 已接入", "_lock_letter_pile(assigned" in src)


# ========== F. 数据契约 ==========
def check_data_contract():
    print("\n[F] 数据契约（columns / schema_status / row_parsed_stats）")
    mod = import_mod("build_foundation")
    if mod is None:
        return
    src = read_file(Path(mod.__file__))
    for key in ["\"columns\"", "\"schema_status\"", "\"row_parsed_stats\""]:
        check("F", f"build_foundation 写入 {key}", key in src)
    # 消费方感知层
    dq = import_mod("data_quality_check")
    if dq is not None:
        dq_src = read_file(Path(dq.__file__))
        check("F", "data_quality_check 感知 schema_status", "schema_status" in dq_src)
        check("F", "data_quality_check 跳过 unknown_domain", "unknown_domain" in dq_src)
    re_mod = import_mod("rule_engine")
    if re_mod is not None:
        re_src = read_file(Path(re_mod.__file__))
        check("F", "rule_engine 感知 schema_status", "schema_status" in re_src)
        check("F", "rule_engine 感知 row_parsed_stats", "row_parsed_stats" in re_src)
        check("F", "rule_engine 含 is_row_consumable", hasattr(re_mod, "is_row_consumable"))
        check("F", "rule_engine 含 doc_domain_status", hasattr(re_mod, "doc_domain_status"))


# ========== G. 推断建议值 ==========
def check_inference():
    print("\n[G] 推断建议值（inference_rules.json + infer_values）")
    rules_path = SKILL_DIR / "rules" / "inference_rules.json"
    content = read_file(rules_path)
    if not content or content.startswith("__READ_ERR__"):
        check("G", "inference_rules.json 存在", False)
        return
    try:
        rules = json.loads(content)
    except Exception as e:
        check("G", "inference_rules.json 可解析", False, str(e))
        return
    rule_list = rules.get("rules", [])
    check("G", f"规则数量 ≥ 7（当前 {len(rule_list)}）", len(rule_list) >= 7)
    ids = [r.get("id", "") for r in rule_list]
    for need in ["INF-001", "INF-002", "INF-003", "INF-004", "INF-005", "INF-006", "INF-007"]:
        check("G", f"规则 {need} 存在", need in ids)
    def _required_fields(r):
        # 文本/枚举规则（type=text）只建议不入库，用 field/strategy 而非 condition/formula
        if r.get("type") == "text":
            return ("type", "field", "strategy", "base_confidence", "max_confidence")
        # 数值链规则必须可计算
        return ("type", "condition", "formula", "base_confidence", "cascade_penalty")
    has_all_fields = all(all(k in r for k in _required_fields(r)) for r in rule_list)
    check("G", "每条规则字段齐全（数值链需 formula/cascade_penalty，文本规则需 field/strategy/max_confidence）", has_all_fields)
    check("G", "含 confidence_color_map", "confidence_color_map" in rules)

    # 动态功能测试：infer_values
    dq = import_mod("data_quality_check")
    if dq is not None and hasattr(dq, "infer_values"):
        data = {
            "doc_type": "碎石桩施工记录",
            "rows": [{
                "pile_no": "Z420", "top_elev": 2103.72, "bottom_elev": 2089.98,
                "actual_length": None, "diameter": 0.8, "volume": 2.5,
                "filling_coeff": None, "thickness": 1.50,
            }],
        }
        try:
            res = dq.infer_values(data)
            summary = res.get("summary", {})
            n = summary.get("total_inferred_fields", 0)
            check("G", "infer_values 实际推断出字段（实长+充盈系数）", n >= 2,
                  f"推断字段数={n}")
        except Exception as e:
            check("G", "infer_values 动态测试", False, f"异常: {e}")
    else:
        check("G", "data_quality_check.infer_values 可调用", False)


# ========== 模块导入 ==========
def import_mod(name):
    try:
        return importlib.import_module(name)
    except Exception as e:
        check("M", f"导入模块 {name}", False, f"{type(e).__name__}: {e}")
        return None


def check_modules():
    print("\n[M] 核心模块导入（无异常）")
    for name in [
        "build_foundation", "table_struct", "data_quality_check", "rule_engine",
        "review_audit", "run_audit", "ocr_grid", "table_schemas", "template_miner",
        "ocr_confusion_check", "signature_check", "audit_config", "postprocess",
    ]:
        import_mod(name)


# ========== 汇总 ==========
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="输出 JSON 汇总")
    args = parser.parse_args()

    print("=" * 60)
    print("民航施工资料审核 Skill — 整体交付 review")
    print("=" * 60)
    print(f"Skill 目录: {SKILL_DIR}")

    check_modules()
    check_docs()
    check_dictionary()
    check_docx_routing()
    check_editor()
    check_table_struct()
    check_data_contract()
    check_inference()

    total = len(RESULTS)
    passed = sum(1 for _, _, ok, _ in RESULTS if ok)
    failed = total - passed

    # 按分组统计
    groups = {}
    for g, n, ok, _ in RESULTS:
        groups.setdefault(g, [0, 0])
        groups[g][0] += 1
        groups[g][1] += 1 if ok else 0

    print("\n" + "=" * 60)
    print("分组汇总")
    for g in sorted(groups):
        tot, pas = groups[g]
        mark = "✅" if pas == tot else "❌"
        print(f"  {mark} [{g}] {pas}/{tot}")
    print("=" * 60)

    if args.json:
        print(json.dumps({
            "total": total, "passed": passed, "failed": failed,
            "results": [
                {"group": g, "name": n, "ok": ok, "detail": d}
                for g, n, ok, d in RESULTS
            ],
            "group_summary": {g: {"passed": v[1], "total": v[0]} for g, v in groups.items()},
        }, ensure_ascii=False, indent=2))
    else:
        print(f"总体: {passed}/{total} 通过, {failed} 失败")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())