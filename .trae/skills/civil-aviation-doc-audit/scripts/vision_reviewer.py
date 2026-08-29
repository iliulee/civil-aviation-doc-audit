# -*- coding: utf-8 -*-
"""
视觉复核调度器（vision_reviewer.py）— v10.6 线2
====================================================
定位：**薄调度层**——只做"能力探测 + 档位选择"，不实现读图协议、
不搬运 verify_fields / vision_providers 的既有逻辑（方案 §4 铁律：
三文件协议是被 G-1.9 闸门引用的资产，原样保留）。

为什么需要它（bug 根因）：
  verify_fields.select_verify_path 原来把 has_agent=True 硬编码——
  在 WorkBuddy 等无视觉模型的宿主上，读图任务写出来永远没人读，
  形成"任务空等"。本模块把"宿主有没有视觉"从拍脑袋默认值变成
  证据驱动的探测结果，并给出四档降级决策：

  1. host_agent —— 宿主 AI 自带视觉（TRAE/豆包/Kimi 等）
                  → 走 verify_fields 既有 agent 三文件协议
  2. api       —— 配了 Vision API Key
                  → 走 vision_providers.py 既有调用
  3. rule      —— 两者皆无 → 本地规则兜底（免费，覆盖有限）
  4. noop      —— 连规则兜底也显式关闭 → 原样返回 + needs_review

探测哲学（"人是决策者"）：
  进程内无法可靠探测宿主模型是否带视觉（子进程看不到宿主模型配置），
  因此采用**显式声明制**——操作者通过 AGENT_VISION 环境变量声明：
    AGENT_VISION=1  宿主带视觉（如 TRAE 选了 Seed-2.1-Turbo 等视觉模型）
    AGENT_VISION=0  宿主无视觉（WorkBuddy 等纯文本模型场景）
    未设置         保守视为无视觉（宁可走规则兜底也不让任务空等）
  探测结果写进 SKILL.md 引擎选择卡片，**让操作者主动选带视觉的模型**。

NOOP 档与 G-1.9 的关系：AI 复核是"减负"不是"放行"（SKILL.md 既有铁律），
NOOP 落下的存疑项全部进 Chat-Verify 人工核对清单，闸门照常生效。

用法：
    from vision_reviewer import confirm_vision_capability, resolve_review_level
    cap = confirm_vision_capability()   # {"host_agent_vision":..., "api":..., "level":..., "source":...}
    level = cap["level"]                # "host_agent" / "api" / "rule" / "noop"

    # CLI 快速自查（供 SKILL.md 引擎选择步骤展示）：
    python vision_reviewer.py probe
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# ═══════════════════════════════════════════════════
# 环境变量约定
# ═══════════════════════════════════════════════════

# 宿主视觉显式声明：1=宿主带视觉模型；0=宿主无视觉；未设置=保守视为无
AGENT_VISION_ENV = "AGENT_VISION"

# 规则兜底开关：0=显式关闭规则兜底（此时无视觉无API会落 noop 档，全交人工）
RULE_FALLBACK_ENV = "OCR_RULE_FALLBACK"


def _env_tristate(name: str) -> Optional[bool]:
    """读三态环境变量：未设置→None；设置→按真值解析。"""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return None
    return raw in ("1", "true", "yes", "on")


# ═══════════════════════════════════════════════════
# 能力探测
# ═══════════════════════════════════════════════════

def probe_host_agent_vision() -> Tuple[bool, bool, str]:
    """探测宿主 AI 视觉能力（证据驱动，不拍脑袋）。

    Returns:
        (has_vision, declared, source):
        has_vision: 探测结论（未声明时保守 False）
        declared:   操作者是否显式声明过（AGENT_VISION 已设置）——
                    下游用它区分"未声明走默认"与"显式降级跳任务"
        source:     证据来源说明（写进探测结果，让人看得懂）
    """
    v = _env_tristate(AGENT_VISION_ENV)
    if v is True:
        return True, True, f"env {AGENT_VISION_ENV}=1（操作者显式声明宿主带视觉）"
    if v is False:
        return False, True, f"env {AGENT_VISION_ENV}=0（操作者显式声明宿主无视觉）"
    return (
        False,
        False,
        f"未声明（保守视为无视觉；建议选用带视觉模型并设 {AGENT_VISION_ENV}=1）",
    )


def probe_api() -> Tuple[bool, str]:
    """探测 Vision API 可用性。

    复用 vision_providers.detect_available_providers()（单一真相源，
    避免探测说有 API、实际 provider 认不到 key 的两层打架）。
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from vision_providers import detect_available_providers
        available = detect_available_providers()
    except Exception as e:
        return False, f"vision_providers 探测异常：{e}"
    if available:
        names = "、".join(p["provider"] for p in available)
        return True, f"vision_providers 探测到 {len(available)} 个可用 Key（{names}）"
    return False, "vision_providers 探测到 0 个可用 Key"


def confirm_vision_capability() -> Dict[str, Any]:
    """汇总探测当前环境的视觉复核能力，给出档位。

    Returns:
        {
            "host_agent_vision": bool,   # 宿主视觉探测结论（未声明保守 False）
            "host_vision_declared": bool,# 操作者是否显式声明过 AGENT_VISION
            "api": bool,                 # 是否有可用 Vision API Key
            "level": "host_agent"|"api"|"rule"|"noop",
            "source": {...},             # 各项证据来源（供引擎选择卡片展示）
        }
    """
    host_vision, declared, host_src = probe_host_agent_vision()
    api_ok, api_src = probe_api()
    cap = {
        "host_agent_vision": host_vision,
        "host_vision_declared": declared,
        "api": api_ok,
        "level": None,
        "source": {
            "host_agent_vision": host_src,
            "api": api_src,
        },
    }
    cap["level"] = resolve_review_level(cap)
    return cap


# ═══════════════════════════════════════════════════
# 档位选择（纯函数）
# ═══════════════════════════════════════════════════

def resolve_review_level(cap: Dict[str, Any]) -> str:
    """按能力组合选档（纯函数，降级顺序固定）。

    host_agent_vision=True            → "host_agent"（宿主视觉最优：零积分、高精度）
    api=True                          → "api"（Vision API 花积分但可靠）
    两者皆无、规则兜底未显式关闭      → "rule"（本地免费兜底，优先于 noop）
    规则兜底也显式关闭(OCR_RULE_FALLBACK=0) → "noop"（全交 Chat-Verify 人工核对）

    Args:
        cap: 能力字典，至少含 host_agent_vision / api 两个布尔键
    """
    if cap.get("host_agent_vision"):
        return "host_agent"
    if cap.get("api"):
        return "api"
    # 规则兜底默认开启；显式关闭才落 noop
    rule_enabled = _env_tristate(RULE_FALLBACK_ENV)
    if rule_enabled is False:
        return "noop"
    return "rule"


# ═══════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="视觉复核调度器 — 能力探测与档位选择（v10.6 线2）",
    )
    subparsers = parser.add_subparsers(dest="command")

    p_probe = subparsers.add_parser("probe", help="探测当前环境视觉复核能力（输出 JSON）")

    args = parser.parse_args()
    if args.command == "probe":
        cap = confirm_vision_capability()
        print(json.dumps(cap, ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
