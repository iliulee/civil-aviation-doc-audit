# -*- coding: utf-8 -*-
"""
统一测试入口（run_all_tests.py）
=============================
按顺序执行单元测试、集成测试、性能测试、结构验证。

用法：
    python scripts/run_all_tests.py
    python scripts/run_all_tests.py --skip-perf    # 跳过性能测试
    python scripts/run_all_tests.py --only unit     # 仅运行单元测试
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
PYTHON = sys.executable


def print_header(msg: str):
    print(f"\n{'=' * 60}")
    print(f"  {msg}")
    print(f"{'=' * 60}")


def run_pytest(args: list, label: str) -> bool:
    print_header(f"🧪 {label}")
    start = time.time()
    cmd = [PYTHON, "-m", "pytest"] + args + ["-v"]
    result = subprocess.run(cmd, cwd=SKILL_DIR, capture_output=False)
    elapsed = time.time() - start
    print(f"\n  ⏱ 耗时: {elapsed:.1f}s")
    return result.returncode == 0


def run_script(script_name: str, label: str) -> bool:
    print_header(f"🔧 {label}")
    start = time.time()
    cmd = [PYTHON, str(SCRIPT_DIR / script_name)]
    result = subprocess.run(cmd, capture_output=False)
    elapsed = time.time() - start
    print(f"\n  ⏱ 耗时: {elapsed:.1f}s")
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="统一测试入口")
    parser.add_argument("--skip-perf", action="store_true", help="跳过性能测试")
    parser.add_argument("--only", choices=["unit", "integration", "perf", "verify"],
                        help="仅运行指定类别的测试")
    args = parser.parse_args()

    results = []
    only = args.only

    # 1. 单元测试
    if only is None or only == "unit":
        results.append(("单元测试: 推断规则", run_pytest(
            ["scripts/test_inferred_values.py"], "推断规则测试")))
        # v9.6 隐患销号套件：每个已查实根因一条测试，红=复发，改完必须全绿
        results.append(("单元测试: 隐患销号", run_pytest(
            ["scripts/test_regression_hazards.py"], "隐患销号回归（H-1~H-8）")))
        # v10.6 OCR 复核升级回归（H-9 裁图复核真实现/H-10 文本层体检路由/H-11 视觉调度降级
        # /H-12 缓存补复核/H-13 PDF 裁图坐标系对齐）
        results.append(("单元测试: OCR 复核升级", run_pytest(
            ["scripts/test_ocr_verify_upgrade.py"], "OCR 复核升级（H-9~H-13）")))
        # v10.0 出口闸门+纯电子表场景：G-0/对账/force禁用/电子表行数/验钞机
        results.append(("单元测试: 闸门与电子表", run_pytest(
            ["scripts/test_gate_and_ledger.py"], "G-0/对账闸门/force禁用/电子表行数/报告质检")))
        # v10.0 skill 前端资源一致性断言（模板源齐全 + 工作台产物存在 + 文档 G-1.5 一致性）
        # 仅开发源副本(src/ + package.json)运行；安装副本为已构建部署、不含 src/，改由 test_skill_assets 校验构建产物
        if (SKILL_DIR / "src").is_dir() and (SKILL_DIR / "package.json").exists():
            results.append(("单元测试: 工作台结构", run_pytest(
                ["scripts/test_workbench.py"], "工作台结构断言（依赖/构建/manifest）")))
        # v10.0 skill 前端资源一致性断言（模板源齐全 + 工作台产物存在 + 文档 G-1.5 一致性）
        results.append(("单元测试: 前端资源一致性", run_pytest(
            ["scripts/test_skill_assets.py"], "skill 前端资源一致性（templates/工作台/SKILL.md闸门）")))
        # v10.1 三重一致性/依据渲染/registry 对齐（B+C+E2）
        results.append(("单元测试: 三重一致性", run_pytest(
            ["scripts/test_design_zone.py"], "设计值三重一致性/依据缺失渲染/registry对齐")))
        # v10.2 Excel/docx 建底座链路回归（break截断/row_index/列对齐/P10 误报）
        results.append(("单元测试: Excel/docx 链路", run_pytest(
            ["scripts/test_xlsx_docx_chain.py"], "Excel/docx 建底座链路（截断/定位/对齐/误报）")))
        # v10.3 材料/合格证数据链回归（A1路由/E1零产出/E3 schema契约/A2提取/A4台账/A5关联/G3双端部署）
        results.append(("单元测试: 材料合格证链", run_pytest(
            ["scripts/test_material_certificate_chain.py"], "材料/合格证数据链（路由/提取/台账/关联/契约）")))
        # v10.4 规则→审核→报告链路回归（LG-110触发/S-04审核期重算/执行统计/CFG覆盖/registry计数）
        results.append(("单元测试: 规则报告链", run_pytest(
            ["scripts/test_rule_to_report_chain.py"], "规则→审核→报告链路（触发/重算/统计/覆盖/计数）")))
        # v10.4 报告生成器回归（建模渲染分离/整改建议列/规则执行统计/版本号/golden锚点/证书对账）
        results.append(("单元测试: 报告生成器", run_pytest(
            ["scripts/test_report_builder.py"], "报告生成器（三层结构/整改建议/统计/版本/对账）")))
        # v10.5 无规则覆盖运行时闸门（unguarded_doc_types 侦测/渲染/reference过滤）
        results.append(("单元测试: 无规则覆盖闸门", run_pytest(
            ["scripts/test_unguarded_doc_types.py"], "无规则覆盖侦测（点名/不误报/渲染/角色过滤）")))

    # 2. 集成测试（数据底座）
    if only is None or only == "integration":
        results.append(("集成测试: 数据底座", run_pytest(
            ["scripts/test_data_foundation.py"], "数据底座测试")))

    # 3. 已有测试
    if only is None or only == "integration":
        results.append(("集成测试: 规则引擎", run_pytest(
            ["scripts/test_rule_engine.py"], "规则引擎测试")))
        results.append(("集成测试: OCR 路由", run_pytest(
            ["scripts/test_ocr_routing.py"], "OCR 路由测试")))

    # 4. 性能测试
    if only is None or only == "perf":
        if not args.skip_perf:
            results.append(("性能测试: 跨单元", run_pytest(
                ["scripts/test_cross_unit_perf.py"], "跨单元性能测试")))
        else:
            print("\n  ⏭ 跳过性能测试")

    # 5. 结构验证
    if only is None or only == "verify":
        results.append(("结构验证", run_script("verify_skill_structure.py", "SKILL 结构验证")))
        results.append(("方案验收", run_script("verify_plan_v2.py", "PLAN v2.0 验收")))
        results.append(("条款溯源", run_script("test_clause_trace.py", "条款溯源验证")))

    # 汇总
    print_header("测试汇总")
    passed = sum(1 for _, r in results if r)
    failed = sum(1 for _, r in results if not r)
    for name, r in results:
        status = "✅" if r else "❌"
        print(f"  {status} {name}")
    print(f"\n  通过: {passed}, 失败: {failed}, 总计: {len(results)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())