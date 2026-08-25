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
            ["scripts/test_regression_hazards.py"], "隐患销号回归（H-1~H-7）")))
        # v10.0 资料员工作台结构断言（依赖/构建/manifest/数据层/外壳）
        results.append(("单元测试: 工作台结构", run_pytest(
            ["scripts/test_workbench.py"], "工作台结构断言（依赖/构建/manifest）")))

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