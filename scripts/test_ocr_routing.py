# -*- coding: utf-8 -*-
"""
OCR 手写体前置路由测试（test_ocr_routing.py）
==============================================
模拟测试"手写体"与"印刷体"的路由逻辑，并打印最终引擎选择结果。

依赖：
    python scripts/test_ocr_routing.py

覆盖：
    - resolve_ocr_engine() 手写体/印刷体路由判定
    - detect_is_handwritten() 文件名启发式判定
    - DISABLE_HANDWRITING_ROUTE 配置开关
    - logger 是否在关键节点输出 [路由判定]/[引擎选择] 日志
"""

import logging
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from ocr_image import (  # noqa: E402
    resolve_ocr_engine,
    detect_is_handwritten,
    DISABLE_HANDWRITING_ROUTE,
)

logger = logging.getLogger("test_ocr_routing")
logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

# ═══════════════════════════════════════════
# 断言工具
# ═══════════════════════════════════════════
_PASS = 0
_FAIL = 0


def check(name: str, cond: bool, detail: str = ""):
    global _PASS, _FAIL
    status = "✅ PASS" if cond else "❌ FAIL"
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
    print(f"  {status}  {name}" + (f"  ({detail})" if detail else ""))


# ═══════════════════════════════════════════
# 用例 1：手写体前置路由
# ═══════════════════════════════════════════
def test_handwritten_routes_to_vision():
    print("\n[m] 手写体前置路由：手写资料应首选 vision，跳过本地 rapidocr")
    got = resolve_ocr_engine(
        engine="auto",
        is_handwritten=True,
        has_rapidocr=True,   # 即便本地可用，手写体也应跳过
        has_vision=True,
        has_tesseract=True,
        disable_handwriting_route=False,
    )
    check("手写体+有vision → vision", got == "vision", f"got={got}")


def test_handwritten_no_vision_routes_to_agent():
    print("\n[m] 手写体无 vision → agent（交由 AI 读图）")
    got = resolve_ocr_engine(
        engine="auto", is_handwritten=True,
        has_rapidocr=True, has_vision=False, has_tesseract=True,
        disable_handwriting_route=False,
    )
    check("手写体+无vision → agent", got == "agent", f"got={got}")


# ═══════════════════════════════════════════
# 用例 2：印刷体路由
# ═══════════════════════════════════════════
def test_printed_routes_to_rapidocr():
    print("\n[m] 印刷体路由：首选本地 rapidocr")
    got = resolve_ocr_engine(
        engine="auto", is_handwritten=False,
        has_rapidocr=True, has_vision=True, has_tesseract=True,
        disable_handwriting_route=False,
    )
    check("印刷体+有rapidocr → rapidocr", got == "rapidocr", f"got={got}")


def test_printed_no_rapidocr_routes_to_vision():
    print("\n[m] 印刷体无 rapidocr → vision")
    got = resolve_ocr_engine(
        engine="auto", is_handwritten=False,
        has_rapidocr=False, has_vision=True, has_tesseract=True,
        disable_handwriting_route=False,
    )
    check("印刷体+无rapidocr+有vision → vision", got == "vision", f"got={got}")


def test_printed_no_rapidocr_no_vision_routes_to_tesseract():
    print("\n[m] 印刷体无 rapidocr 无 vision → tesseract")
    got = resolve_ocr_engine(
        engine="auto", is_handwritten=False,
        has_rapidocr=False, has_vision=False, has_tesseract=True,
        disable_handwriting_route=False,
    )
    check("印刷体兜底 → tesseract", got == "tesseract", f"got={got}")


def test_printed_no_engine_routes_to_none():
    print("\n[m] 无任何可用引擎 → none")
    got = resolve_ocr_engine(
        engine="auto", is_handwritten=False,
        has_rapidocr=False, has_vision=False, has_tesseract=False,
        disable_handwriting_route=False,
    )
    check("无引擎 → none", got == "none", f"got={got}")


# ═══════════════════════════════════════════
# 用例 3：配置开关
# ═══════════════════════════════════════════
def test_disable_handwriting_route():
    print("\n[m] DISABLE_HANDWRITING_ROUTE=True → 强制走本地 OCR（跳过 VLM 路由）")
    got = resolve_ocr_engine(
        engine="auto", is_handwritten=True,
        has_rapidocr=True, has_vision=True, has_tesseract=True,
        disable_handwriting_route=True,
    )
    check("禁用手写路由 → rapidocr", got == "rapidocr", f"got={got}")


def test_explicit_engine_untouched():
    print("\n[m] 显式指定引擎不被 auto 路由覆盖")
    got = resolve_ocr_engine(
        engine="vision", is_handwritten=True,
        has_rapidocr=True, has_vision=True, has_tesseract=True,
        disable_handwriting_route=False,
    )
    check("显式 vision → vision", got == "vision", f"got={got}")


# ═══════════════════════════════════════════
# 用例 4：文件名启发式判定
# ═══════════════════════════════════════════
def test_filename_heuristic():
    print("\n[m] 文件名启发式判定 is_handwritten")
    cases = [
        ("碎石桩施工记录", False),
        ("CFG桩施工记录", False),
        ("手写记录", True),
        ("现场笔记", True),
        ("会议草稿", True),
        ("note_scan", True),
        ("handwritten_log", True),
        ("施工日志", False),
    ]
    for fname, expect in cases:
        got = detect_is_handwritten(fname)
        check(f"detect('{fname}') → {expect}", got == expect, f"got={got}")
    # 配置字典覆盖
    got = detect_is_handwritten("施工日志", config={"is_handwritten": True})
    check("config 显式覆盖 → True", got is True, f"got={got}")


# ═══════════════════════════════════════════
# 用例 5：日志关键节点输出
# ═══════════════════════════════════════════
def test_logging_key_nodes():
    print("\n[m] 关键节点日志输出（[路由判定] / [引擎选择] / [识别结果]）")
    from ocr_image import _log_route_decision, _log_engine_choice, _log_engine_result, get_ocr_logger
    logs = []
    class _Cap(logging.Handler):
        def emit(self, record):
            logs.append(self.format(record))
    handler = _Cap()
    ocr_logger = get_ocr_logger()
    ocr_logger.addHandler(handler)
    ocr_logger.setLevel(logging.INFO)
    try:
        _log_route_decision("测试桩.xlsx", True, "vision")
        _log_engine_choice("测试桩.xlsx", "vision")
        _log_engine_result("测试桩.xlsx", "vision", 12, 0.85)
    finally:
        ocr_logger.removeHandler(handler)
    got_route = any("[路由判定]" in l for l in logs)
    got_engine = any("[引擎选择]" in l for l in logs)
    got_result = any("[识别结果]" in l for l in logs)
    check("输出 [路由判定] 日志", got_route)
    check("输出 [引擎选择] 日志", got_engine)
    check("输出 [识别结果] 日志", got_result)


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════
def main():
    print("=" * 60)
    print("OCR 手写体路由测试")
    print(f"  DISABLE_HANDWRITING_ROUTE = {DISABLE_HANDWRITING_ROUTE}")
    print("=" * 60)

    test_handwritten_routes_to_vision()
    test_handwritten_no_vision_routes_to_agent()
    test_printed_routes_to_rapidocr()
    test_printed_no_rapidocr_routes_to_vision()
    test_printed_no_rapidocr_no_vision_routes_to_tesseract()
    test_printed_no_engine_routes_to_none()
    test_disable_handwriting_route()
    test_explicit_engine_untouched()
    test_filename_heuristic()
    test_logging_key_nodes()

    print("\n" + "=" * 60)
    print(f"结果: {_PASS} 通过 / {_FAIL} 失败")
    print("=" * 60)
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())