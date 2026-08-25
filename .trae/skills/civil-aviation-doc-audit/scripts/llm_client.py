# -*- coding: utf-8 -*-
"""
v7.2 C1 LLM 公共客户端（llm_client.py）
========================================

功能：
    - 分类语义辅助：LLM 看"文件名 + 前 N 行文本摘要" + RAG 上下文
      （references/classification-terms.json + specification-mapping.md 摘要），
      输出专业 + 置信度
    - 复用 feedback_analyzer.py 已有的环境变量 LLM_API_URL / LLM_API_KEY / LLM_MODEL，
      避免三处双写 API Key / 超时 / 错误处理

约束：
    - 无网络 / 无 API Key 时返回 None，调用方降级为"全部需人工确认"，不中断流程
    - 输出必须可解析为 JSON，解析失败视为调用失败
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

DEFAULT_MODEL = "gpt-4o-mini"
REQUEST_TIMEOUT = 30

# 五大专业名称（固定枚举，供 LLM 选择）
PROFESSION_ENUM = [
    "01_场道工程", "02_空管工程", "03_助航设施", "04_弱电系统", "05_供油工程",
    "通用资料",
]


def llm_available() -> bool:
    """检查 LLM API 是否可用（环境变量齐全）。"""
    return bool(
        os.environ.get("LLM_API_URL") and os.environ.get("LLM_API_KEY")
    )


def _load_terms_context() -> str:
    """从 references/classification-terms.json 加载专业→关键词摘要（RAG 上下文）。"""
    terms_file = SKILL_DIR / "references" / "classification-terms.json"
    try:
        data = json.loads(terms_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    lines: List[str] = []
    for prof, prof_data in data.get("terms", {}).items():
        core = "、".join(prof_data.get("core", []))
        weak = "、".join(prof_data.get("weak", []))
        lines.append(f"- {prof}: 核心词[{core}] 弱词[{weak}]")
    return "\n".join(lines)


def _load_spec_mapping_context() -> str:
    """加载 references/specification-mapping.md 前若干行作为 RAG 上下文。"""
    spec_file = SKILL_DIR / "references" / "specification-mapping.md"
    try:
        text = spec_file.read_text(encoding="utf-8")
    except OSError:
        return ""
    # 只取前 40 行，控制 token
    return "\n".join(text.splitlines()[:40])


def _build_prompt(filename: str, text_preview: str) -> str:
    """构造分类语义判定 prompt。"""
    terms_ctx = _load_terms_context() or "（无术语表上下文）"
    spec_ctx = _load_spec_mapping_context() or "（无规范映射上下文）"
    preview = (text_preview or "").strip() or "（无可预览文本，仅依据文件名判定）"
    if len(preview) > 300:
        preview = preview[:300] + "…"

    return f"""你是民航施工资料分类专家。请根据文件名和前几行文本摘要，判断该资料属于哪个专业类别。

可选专业（只能从中选一个）：
{", ".join(PROFESSION_ENUM)}

专业关键词参考（术语表摘要）：
{terms_ctx}

规范映射参考（specification-mapping.md 摘要）：
{spec_ctx}

待分类文件：
- 文件名：{filename}
- 文本摘要（前几行）：
{preview}

请只输出 JSON（不要任何额外文字）：
{{"professional": "01_场道工程", "confidence": 0.85, "reason": "简短原因"}}
其中 confidence 为 0~1 的小数，表示你对判定的把握。"""


def _parse_response(response: str) -> Optional[Dict[str, Any]]:
    """容错解析 LLM 返回（支持 ```json 包裹）。"""
    if not response:
        return None
    text = response.strip()
    if text.startswith("```"):
        # 去掉 ```json ... ``` 包裹
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    prof = data.get("professional", "")
    if prof not in PROFESSION_ENUM:
        return None
    conf = data.get("confidence")
    if not isinstance(conf, (int, float)):
        conf = 0.5
    return {
        "professional": prof,
        "confidence": max(0.0, min(1.0, float(conf))),
        "reason": str(data.get("reason", "")),
    }


def classify_document(filename: str, text_preview: str = "") -> Optional[Dict[str, Any]]:
    """LLM 分类判定。成功返回 {professional, confidence, reason}，失败返回 None。

    失败场景（返回 None，调用方降级）：
        - 未配置 LLM_API_URL / LLM_API_KEY
        - 网络错误 / 超时
        - 返回内容无法解析为合法专业
    """
    if not llm_available():
        return None

    api_url = os.environ.get("LLM_API_URL", "").strip()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    prompt = _build_prompt(filename, text_preview)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError, OSError):
        return None

    return _parse_response(content)


if __name__ == "__main__":
    # 自测：python scripts/llm_client.py
    print(f"LLM 可用: {llm_available()}")
    if llm_available():
        r = classify_document("水泥土搅拌桩施工记录.xlsx", "桩号 设计桩长 水泥掺量 施工日期")
        print(f"分类结果: {r}")
