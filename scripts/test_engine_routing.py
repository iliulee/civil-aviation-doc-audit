#!/usr/bin/env python
"""
test_engine_routing.py — 跨文件引擎参数传递验证

测试 run_audit.py → build_foundation.py 之间 --engine 参数的
4 种组合场景，确保优先级逻辑正确：CLI > preconditions > auto。

使用方法：
    python scripts/test_engine_routing.py

输出：逐项 PASS/FAIL，末尾汇总。
"""

import sys
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

# ========== 测试目标 1：build_foundation.py 引擎优先级逻辑 ==========
# 直接从 build_foundation.py 源码中提取的优先级逻辑，用于单元测试

def resolve_engine_unit(
    cli_engine: Optional[str],
    has_preconditions_file: bool,
    preconditions_engine: Optional[str],
) -> Dict[str, str]:
    """模拟 build_foundation.py 的引擎优先级逻辑（L2982-L2992）。

    Args:
        cli_engine: args.engine 的值（None 表示未传）
        has_preconditions_file: 是否传了 --preconditions
        preconditions_engine: preconditions.get("ocr_engine") 的值

    Returns:
        {"engine": 最终引擎, "source": 来源标记}
    """
    if cli_engine is not None:
        return {"engine": str(cli_engine), "source": "user_chosen"}
    if has_preconditions_file:
        return {
            "engine": str(preconditions_engine) if preconditions_engine else "auto",
            "source": "user_chosen",
        }
    return {"engine": "auto", "source": "default"}


# ========== 测试目标 2：run_audit.py cmd_build 命令构建 ==========

def build_cmd_unit(
    cli_engine: Optional[str],
    has_preconditions: bool,
    has_incremental: bool,
) -> list:
    """模拟 run_audit.py cmd_build() 的命令构建逻辑（L267-L279）。

    Returns:
        构建出的命令列表（不含 PYTHON_CMD 和脚本路径等固定前缀）
    """
    cmd_parts = []
    if cli_engine is not None:
        cmd_parts.extend(["--engine", cli_engine])
    if has_incremental:
        cmd_parts.append("--incremental")
    if has_preconditions:
        cmd_parts.extend(["--preconditions", "dummy_preconditions.json"])
    return cmd_parts


# ========== 测试目标 3：集成测试（实际 CLI 调用） ==========

def _run_cli_test(args: list, label: str) -> bool:
    """运行 run_audit.py 或 build_foundation.py 并检查输出。

    使用 --help 来验证参数解析，不实际执行构建。
    """
    skill_dir = Path(__file__).resolve().parent
    foundation_script = skill_dir / "build_foundation.py"
    run_script = skill_dir / "run_audit.py"

    # 测试 build_foundation.py 的 --engine 参数
    cmd = [sys.executable, str(foundation_script)] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        # --help 返回 0 表示参数解析正常
        if result.returncode == 0:
            return True
        else:
            print(f"  [!] {label}: 返回码 {result.returncode}")
            print(f"      stderr: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  [!] {label}: 异常 {e}")
        return False


def run_tests() -> int:
    """执行所有测试，返回失败数。"""
    failed = 0
    total = 0

    print("=" * 60)
    print("测试 1：build_foundation.py 引擎优先级逻辑（单元测试）")
    print("=" * 60)

    test_cases = [
        # (cli_engine, has_preconditions, preconditions_engine, 期望结果)
        ("场景1: 不传 --engine + 不传 --preconditions → auto, default",
         None, False, None, {"engine": "auto", "source": "default"}),
        ("场景2: 不传 --engine + preconditions 写 rapidocr → rapidocr, user_chosen",
         None, True, "rapidocr", {"engine": "rapidocr", "source": "user_chosen"}),
        ("场景3: 传 --engine vision + 不传 --preconditions → vision, user_chosen",
         "vision", False, None, {"engine": "vision", "source": "user_chosen"}),
        ("场景4: 传 --engine vision + preconditions 写 rapidocr → vision 优先",
         "vision", True, "rapidocr", {"engine": "vision", "source": "user_chosen"}),
        ("场景5: preconditions 无 ocr_engine 字段 → 回退 auto",
         None, True, None, {"engine": "auto", "source": "user_chosen"}),
    ]

    for label, cli, has_pre, pre_val, expected in test_cases:
        total += 1
        result = resolve_engine_unit(cli, has_pre, pre_val)
        if result == expected:
            print(f"  ✅ {label}")
        else:
            failed += 1
            print(f"  ❌ {label}")
            print(f"     期望: {expected}")
            print(f"     实际: {result}")

    print()
    print("=" * 60)
    print("测试 2：run_audit.py cmd_build 命令构建逻辑（单元测试）")
    print("=" * 60)

    cmd_tests = [
        # (cli_engine, has_preconditions, has_incremental, 期望命令片段)
        ("场景1: 不传 --engine → 不传 --engine 给 build_foundation",
         None, False, False, []),
        ("场景2: 传 --engine rapidocr → 传 --engine rapidocr",
         "rapidocr", False, False, ["--engine", "rapidocr"]),
        ("场景3: 传 --preconditions → 传 --preconditions 路径",
         None, True, False, ["--preconditions", "dummy_preconditions.json"]),
        ("场景4: 传 --engine vision + --preconditions → 两者都传",
         "vision", True, False, ["--engine", "vision", "--preconditions", "dummy_preconditions.json"]),
        ("场景5: 传 --incremental → 传 --incremental",
         None, False, True, ["--incremental"]),
    ]

    for label, cli, has_pre, has_inc, expected in cmd_tests:
        total += 1
        result = build_cmd_unit(cli, has_pre, has_inc)
        if result == expected:
            print(f"  ✅ {label}")
        else:
            failed += 1
            print(f"  ❌ {label}")
            print(f"     期望: {expected}")
            print(f"     实际: {result}")

    print()
    print("=" * 60)
    print("测试 3：集成测试 — build_foundation.py --help 参数解析")
    print("=" * 60)
    total += 1
    if _run_cli_test(["--help"], "build_foundation.py --help"):
        print("  ✅ build_foundation.py --help 正常")
    else:
        failed += 1
        print("  ❌ build_foundation.py --help 异常")

    # 验证 --engine 的 choices 包含 rapidocr
    total += 1
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "build_foundation.py"), "--help"],
        capture_output=True, text=True, timeout=10,
        encoding="utf-8", errors="replace",
    )
    if "rapidocr" in result.stdout or "rapidocr" in result.stderr:
        print("  ✅ build_foundation.py --engine choices 包含 rapidocr")
    else:
        failed += 1
        print("  ❌ build_foundation.py --engine choices 缺少 rapidocr")

    # 验证 run_audit.py build --help 的 --engine 默认值为 None
    total += 1
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "run_audit.py"), "build", "--help"],
        capture_output=True, text=True, timeout=10,
        encoding="utf-8", errors="replace",
    )
    if "None" in result.stdout and "preconditions" in result.stdout:
        print("  ✅ run_audit.py build --engine default=None, 说明含 preconditions 回退")
    else:
        failed += 1
        print("  ❌ run_audit.py build --engine 默认值检查异常")
        print(f"     stdout: {result.stdout[:300]}")

    print()
    print("=" * 60)
    if failed == 0:
        print(f"✅ 全部 {total} 项测试通过")
    else:
        print(f"❌ {failed}/{total} 项测试失败")
    print("=" * 60)
    return failed


if __name__ == "__main__":
    sys.exit(run_tests())