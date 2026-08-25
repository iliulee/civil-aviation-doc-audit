# -*- coding: utf-8 -*-
"""跨单位规则匹配性能基准测试（E-2.3）

验证目标：
  1. 1000 桩位 join 耗时 < 1 秒（E-2.3 性能基准）
  2. 5000 桩位场景分块处理正常工作（E-2.2）
  3. 分块路径与非分块路径产出结果一致（正确性回归）

用法：
    python scripts/test_cross_unit_perf.py
"""

import random
import sys
import time
from pathlib import Path

# 允许 import 同目录下的 rule_engine
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from rule_engine import (  # noqa: E402
    CrossUnitChecker,
    LEVEL_L2,
    Rule,
    SCOPE_CROSS_UNIT,
    SEVERITY_SANITY,
)


# ========== 测试工具 ==========
def make_test_rule() -> Rule:
    """构造测试用跨单位规则（自包含，不依赖 rules/ 目录）。

    校验逻辑：abs(field_a - field_b) / max(field_a, field_b) <= 0.05
    即双方数据偏差不超过 5%。
    """
    return Rule(
        rule_id="TEST-CU-PERF",
        name="性能测试-双方数量偏差校验",
        level=LEVEL_L2,
        scope=SCOPE_CROSS_UNIT,
        trigger_when={"doc_type_a": "甲方记录", "doc_type_b": "乙方记录"},
        check_expr={
            "type": "cross_compare",
            "expr": "abs(field_a - field_b) / max(field_a, field_b) <= 0.05",
            "language": "jinja-expr",
        },
        error_template="桩号 {pile_no} 偏差 {deviation}% 超过 5% 阈值",
        status="active",
        source="test",
        version="1.0.0",
        created_at="2026-07-30T10:00:00",
        updated_at="2026-07-30T10:00:00",
        changelog=[],
        severity_on_violation=SEVERITY_SANITY,
        remediation="核查双方记录原始数据，确认是否存在抄写错误或计量口径不一致",
        alignment={
            "join_key": ["pile_no"],
            "field_a": "甲方量",
            "field_b": "乙方量",
        },
    )


def generate_test_data(n_rows=1000, violation_rate=0.05, seed=42):
    """生成测试数据。

    Args:
        n_rows: 桩位数量
        violation_rate: 制造偏差（违规）的桩位比例
        seed: 随机种子（保证可重复）

    Returns:
        (party_a_data, party_b_data, expected_violation_count)
    """
    rng = random.Random(seed)
    party_a_rows = []
    party_b_rows = []
    expected_violations = 0
    for i in range(n_rows):
        pile_no = f"Z{i:05d}"
        base = round(rng.uniform(10.0, 20.0), 2)
        if rng.random() < violation_rate:
            # 制造偏差 > 5%（约 20% 偏差）
            b_value = round(base * 0.8, 2)
            expected_violations += 1
        else:
            # 一致或微小偏差
            b_value = base
        party_a_rows.append({"pile_no": pile_no, "甲方量": base})
        party_b_rows.append({"pile_no": pile_no, "乙方量": b_value})

    party_a_data = {"doc_type": "甲方记录", "rows": party_a_rows}
    party_b_data = {"doc_type": "乙方记录", "rows": party_b_rows}
    return party_a_data, party_b_data, expected_violations


def _assert(condition: bool, msg: str) -> None:
    """断言辅助。"""
    if not condition:
        raise AssertionError(msg)
    print(f"  ✓ {msg}")


# ========== 性能测试 1：1000 桩位 join < 1 秒 ==========
def test_1000_piles_join():
    """1000 桩位 join 性能测试（目标 < 1 秒，E-2.3）"""
    print("\n[性能测试 1] 1000 桩位 join（目标 < 1 秒）")
    rule = make_test_rule()
    party_a_data, party_b_data, expected_violations = generate_test_data(n_rows=1000)

    checker = CrossUnitChecker()
    t0 = time.perf_counter()
    violations = checker.check(rule, party_a_data, party_b_data)
    elapsed = time.perf_counter() - t0

    print(f"  数据量：party_a={len(party_a_data['rows'])}, party_b={len(party_b_data['rows'])}")
    print(f"  违规数：{len(violations)}（期望约 {expected_violations}）")
    print(f"  耗时：{elapsed * 1000:.2f} ms")

    _assert(len(violations) > 0, "应检测到至少 1 个违规")
    _assert(elapsed < 1.0, f"1000 桩位 join 耗时应 < 1 秒，实际 {elapsed:.3f}s")
    print(f"  → 通过：耗时 {elapsed:.3f}s < 1.0s，违规检测正常")


# ========== 性能测试 2：5000 桩位场景（不分块） ==========
def test_5000_piles_no_chunk():
    """5000 桩位场景：行数 == CHUNK_THRESHOLD，不触发分块，验证基准行为"""
    print("\n[性能测试 2] 5000 桩位（行数 == CHUNK_THRESHOLD，不分块）")
    rule = make_test_rule()
    party_a_data, party_b_data, _ = generate_test_data(n_rows=5000, violation_rate=0.05)

    progress_log = []

    def chunk_progress(processed, total):
        progress_log.append((processed, total))

    checker = CrossUnitChecker()
    t0 = time.perf_counter()
    violations = checker.check(rule, party_a_data, party_b_data, chunk_progress=chunk_progress)
    elapsed = time.perf_counter() - t0

    print(f"  数据量：party_a={len(party_a_data['rows'])}")
    print(f"  违规数：{len(violations)}")
    print(f"  耗时：{elapsed * 1000:.2f} ms")
    print(f"  进度回调次数：{len(progress_log)}（不分块时应为 0）")

    _assert(len(violations) > 0, "应检测到违规")
    _assert(len(progress_log) == 0,
            f"行数 == CHUNK_THRESHOLD 时不触发分块，进度回调应为 0 次（实际 {len(progress_log)}）")
    print(f"  → 通过：未触发分块，违规检测正常，耗时 {elapsed:.3f}s")


# ========== 性能测试 3：5001 桩位分块触发 ==========
def test_5001_piles_chunked():
    """5001 桩位分块触发测试（行数 > CHUNK_THRESHOLD=5000，启用分块）"""
    print("\n[性能测试 3] 5001 桩位分块处理（行数 > CHUNK_THRESHOLD）")
    rule = make_test_rule()
    party_a_data, party_b_data, _ = generate_test_data(n_rows=5001, violation_rate=0.05)

    progress_log = []

    def chunk_progress(processed, total):
        progress_log.append((processed, total))

    checker = CrossUnitChecker()
    t0 = time.perf_counter()
    violations = checker.check(rule, party_a_data, party_b_data, chunk_progress=chunk_progress)
    elapsed = time.perf_counter() - t0

    n_chunks_expected = (5001 + CrossUnitChecker.CHUNK_SIZE - 1) // CrossUnitChecker.CHUNK_SIZE
    print(f"  数据量：party_a={len(party_a_data['rows'])}")
    print(f"  违规数：{len(violations)}")
    print(f"  耗时：{elapsed * 1000:.2f} ms")
    print(f"  期望分块数：{n_chunks_expected}（CHUNK_SIZE={CrossUnitChecker.CHUNK_SIZE}）")
    print(f"  进度回调次数：{len(progress_log)}")
    if progress_log:
        print(f"  最后一次进度：{progress_log[-1]}")

    _assert(len(progress_log) == n_chunks_expected,
            f"分块进度回调应被调用 {n_chunks_expected} 次，实际 {len(progress_log)} 次")
    if progress_log:
        last_processed, last_total = progress_log[-1]
        _assert(last_processed == 5001, f"最后处理数应为 5001，实际 {last_processed}")
        _assert(last_total == 5001, f"总数应为 5001，实际 {last_total}")
    _assert(len(violations) > 0, "应检测到违规")
    print(f"  → 通过：分块正确触发，{n_chunks_expected} 块全部处理完成，耗时 {elapsed:.3f}s")


# ========== 性能测试 4：分块与不分块结果一致性 ==========
def test_chunked_vs_unchunked_consistency():
    """验证分块与非分块路径产出结果一致（正确性回归）

    策略：对同一份数据，分别在「触发分块」和「不触发分块」两种模式下运行，
    比较违规数与违规桩号集合是否一致。
    """
    print("\n[性能测试 4] 分块 vs 非分块 结果一致性")
    rule = make_test_rule()
    # 6001 行：默认会触发分块
    party_a_data, party_b_data, _ = generate_test_data(n_rows=6001, violation_rate=0.1)

    # 模式 A：默认参数（触发分块）
    checker_a = CrossUnitChecker()
    violations_chunked = checker_a.check(rule, party_a_data, party_b_data)

    # 模式 B：临时抬高阈值以禁用分块
    checker_b = CrossUnitChecker()
    original_threshold = CrossUnitChecker.CHUNK_THRESHOLD
    try:
        CrossUnitChecker.CHUNK_THRESHOLD = 10 ** 9  # 临时禁用分块
        violations_unchunked = checker_b.check(rule, party_a_data, party_b_data)
    finally:
        CrossUnitChecker.CHUNK_THRESHOLD = original_threshold  # 恢复

    # 比较：违规数应一致
    print(f"  分块模式违规数：{len(violations_chunked)}")
    print(f"  非分块模式违规数：{len(violations_unchunked)}")

    _assert(len(violations_chunked) == len(violations_unchunked),
            f"两种模式违规数应一致（分块={len(violations_chunked)}, 非分块={len(violations_unchunked)}）")

    # 比较：违规消息集合应一致（按 error_message 排序后比较）
    msgs_chunked = sorted(v.error_message for v in violations_chunked)
    msgs_unchunked = sorted(v.error_message for v in violations_unchunked)
    _assert(msgs_chunked == msgs_unchunked, "两种模式违规消息集合应一致")
    print(f"  → 通过：分块与非分块路径产出 {len(violations_chunked)} 个完全一致的违规")


# ========== 主入口 ==========
def main() -> int:
    print("=" * 60)
    print("跨单位规则匹配性能基准测试 (E-2.3)")
    print(f"CHUNK_THRESHOLD={CrossUnitChecker.CHUNK_THRESHOLD}, "
          f"CHUNK_SIZE={CrossUnitChecker.CHUNK_SIZE}")
    print("=" * 60)

    tests = [
        ("1000 桩位 join (<1s)", test_1000_piles_join),
        ("5000 桩位不分块", test_5000_piles_no_chunk),
        ("5001 桩位分块触发", test_5001_piles_chunked),
        ("分块 vs 非分块 一致性", test_chunked_vs_unchunked_consistency),
    ]

    failed = []
    for name, func in tests:
        try:
            func()
            print(f"  → {name} 测试通过 ✓")
        except AssertionError as e:
            print(f"  → {name} 测试失败 ✗: {e}")
            failed.append(name)
        except Exception as e:
            import traceback
            print(f"  → {name} 测试异常 ✗: {e}")
            traceback.print_exc()
            failed.append(name)

    print("\n" + "=" * 60)
    if failed:
        print(f"❌ 测试完成：{len(tests) - len(failed)}/{len(tests)} 通过，失败: {failed}")
        return 1
    print(f"✅ 测试完成：{len(tests)}/{len(tests)} 全部通过")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
