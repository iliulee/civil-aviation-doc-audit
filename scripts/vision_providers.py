"""
Vision API 统一配置层（vision_providers.py）
==============================================

支持 7 家主流 Vision API（6 家国产 + OpenAI），全部走 OpenAI 兼容接口。
用户只需设置对应环境变量，脚本自动检测可用 Provider 并推荐最便宜的。

支持的 Provider：
  ┌──────────┬──────────┬──────────────────────┬────────────────────────┐
  │ provider │ 名称     │ 环境变量              │ 默认模型               │
  ├──────────┼──────────┼──────────────────────┼────────────────────────┤
  │ qwen     │ 通义千问  │ DASHSCOPE_API_KEY    │ qwen-vl-max            │
  │ doubao   │ 豆包     │ ARK_API_KEY          │ doubao-vision-pro-32k  │
  │ glm      │ 智谱     │ ZHIPU_API_KEY        │ glm-4v-plus            │
  │ kimi     │ Kimi     │ MOONSHOT_API_KEY     │ moonshot-v1-8k-vision  │
  │ silicon  │ 硅基流动  │ SILICONFLOW_API_KEY  │ Qwen/Qwen2-VL-72B      │
  │ baidu    │ 百度千帆  │ BAIDU_API_KEY        │ ernie-4.5-vl-preview   │
  │ openai   │ OpenAI   │ OPENAI_API_KEY       │ gpt-4o                 │
  └──────────┴──────────┴──────────────────────┴────────────────────────┘

使用方式：
    from vision_providers import verify_field_with_api, detect_available_providers

    # 自动检测可用 Provider
    providers = detect_available_providers()

    # 用 API 复核单个字段
    result = verify_field_with_api(image_path, "请识别图中的桩号")

也可以命令行调用：
    python vision_providers.py --list           # 列出可用 Provider
    python vision_providers.py --test <图片路径> # 测试 API 调用
"""

import os
import base64
import json
import argparse
from pathlib import Path
from typing import Optional


# ========== Provider 配置表 ==========

PROVIDERS = {
    "qwen": {
        "name": "通义千问",
        "env_key": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "model": "qwen-vl-max",
        "price_per_1k": 0.008,  # 元/千token（大致）
        "is_openai_compat": True,
    },
    "doubao": {
        "name": "豆包",
        "env_key": "ARK_API_KEY",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "model": "doubao-vision-pro-32k",
        "price_per_1k": 0.003,
        "is_openai_compat": True,
    },
    "glm": {
        "name": "智谱",
        "env_key": "ZHIPU_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "model": "glm-4v-plus",
        "price_per_1k": 0.01,
        "is_openai_compat": True,
    },
    "kimi": {
        "name": "Kimi",
        "env_key": "MOONSHOT_API_KEY",
        "base_url": "https://api.moonshot.cn/v1/chat/completions",
        "model": "moonshot-v1-8k-vision-preview",
        "price_per_1k": 0.012,
        "is_openai_compat": True,
    },
    "silicon": {
        "name": "硅基流动",
        "env_key": "SILICONFLOW_API_KEY",
        "base_url": "https://api.siliconflow.cn/v1/chat/completions",
        "model": "Qwen/Qwen2-VL-72B-Instruct",
        "price_per_1k": 0.004,
        "is_openai_compat": True,
    },
    "baidu": {
        "name": "百度千帆",
        "env_key": "BAIDU_API_KEY",
        "base_url": "https://qianfan.baidubce.com/v2/chat/completions",
        "model": "ernie-4.5-vl-preview",
        "price_per_1k": 0.008,
        "is_openai_compat": True,
    },
    "openai": {
        "name": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o",
        "price_per_1k": 0.015,
        "is_openai_compat": True,
    },
}

# 旧版兼容：GEMINI_API_KEY 也支持
LEGACY_KEYS = {
    "GEMINI_API_KEY": "gemini",  # Gemini 走独立接口，标记为 legacy
    "SILICONFLOW_API_KEY": "silicon",  # 旧名映射
}


# ========== 施工资料专用 Prompt ==========

CONSTRUCTION_OCR_PROMPT = (
    "你是民航施工资料审核助手。请仔细识别图片中的文字内容。\n"
    "特别注意以下施工资料常见 OCR 误读：\n"
    "1. 桩号列以字母开头的（如 Z、PH、CFG），请保留字母前缀，不要将 Z 识别为 2\n"
    "2. 充盈系数等小数值，请仔细区分 0 和 4、0 和 6、3 和 8 等易混淆数字\n"
    "3. 手写数字请尽量准确识别，不确定的标注[存疑]\n"
    "4. 保持表格的行列对应关系\n"
    "5. 只输出识别到的文字内容，不要添加解释\n"
)

VERIFY_FIELD_PROMPT = (
    "你是民航施工资料审核助手。请仔细识别图片中指定位置的文字内容。\n"
    "问题：{question}\n"
    "OCR 初步识别结果：{ocr_value}（可能有误）\n"
    "疑似正确值：{suspected_value}\n"
    "请仔细看图，判断 OCR 结果是否正确。如果 OCR 结果有误，请给出正确的值。\n"
    "输出格式（JSON）：\n"
    '{{"verified_value": "识别到的正确值", "confidence": "high/medium/low", "note": "备注说明"}}\n'
)

# 手写体专用 Prompt：在 CONSTRUCTION_OCR_PROMPT 基础上追加针对性指令
HANDWRITTEN_OCR_PROMPT = (
    "这是一张包含大量手写内容的图片。请注意：\n"
    "1. 字迹可能潦草、连笔，请结合上下文语境（如金额、日期、专业术语）进行合理推断和纠错；\n"
    "2. 如果遇到完全无法辨认的字，请用 `[?]` 标记，不要强行编造；\n"
    "3. 严格输出 JSON 格式。\n"
)


# ========== 核心函数 ==========

def detect_available_providers() -> list[dict]:
    """检测当前环境中可用的 Vision API Provider，按价格从低到高排序。"""
    available = []
    for key, config in PROVIDERS.items():
        api_key = os.environ.get(config["env_key"])
        if api_key:
            available.append({
                "provider": key,
                "name": config["name"],
                "model": config["model"],
                "price_per_1k": config["price_per_1k"],
                "env_key": config["env_key"],
            })

    # 按价格排序（最便宜的排前面）
    available.sort(key=lambda x: x["price_per_1k"])
    return available


def get_best_provider() -> Optional[str]:
    """获取最便宜的可用 Provider。无可用时返回 None。"""
    providers = detect_available_providers()
    if providers:
        return providers[0]["provider"]
    return None


def _encode_image(image_path: str) -> str:
    """将图片文件编码为 base64。"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def call_vision_api(
    image_path: str,
    prompt: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 60,
    system_prompt: Optional[str] = None,
) -> dict:
    """
    调用 Vision API 识别图片。

    Args:
        image_path: 图片文件路径
        prompt: 提示词
        provider: 指定 Provider（如 "qwen"）。None 则自动选择最便宜的
        api_key: API Key。None 则从环境变量读取
        timeout: 超时秒数
        system_prompt: 可选的 System Prompt（如手写体针对性指令）。None 则仅用 user 消息

    Returns:
        {"text": "识别结果", "provider": "qwen", "model": "qwen-vl-max"}
    """
    import requests

    # 选择 Provider
    if provider is None:
        provider = get_best_provider()
    if provider is None:
        return {"text": "", "provider": "none", "model": "", "error": "无可用的 Vision API Provider"}

    if provider not in PROVIDERS:
        return {"text": "", "provider": provider, "model": "", "error": f"未知 Provider: {provider}"}

    config = PROVIDERS[provider]

    # 获取 API Key
    if api_key is None:
        api_key = os.environ.get(config["env_key"])
    if not api_key:
        return {"text": "", "provider": provider, "model": "", "error": f"未设置环境变量 {config['env_key']}"}

    # 编码图片
    img_b64 = _encode_image(image_path)

    # 构造请求（全部走 OpenAI 兼容接口）
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 智谱 GLM 需要在 header 中传 key（部分版本）
    if provider == "glm":
        headers["Authorization"] = f"Bearer {api_key}"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
        ],
    })

    payload = {
        "model": config["model"],
        "messages": messages,
        "max_tokens": 2000,
    }

    try:
        resp = requests.post(
            config["base_url"],
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        result = resp.json()
        text = result["choices"][0]["message"]["content"]
        return {
            "text": text,
            "provider": provider,
            "model": config["model"],
        }
    except requests.exceptions.Timeout:
        return {"text": "", "provider": provider, "model": config["model"], "error": "请求超时"}
    except requests.exceptions.HTTPError as e:
        return {"text": "", "provider": provider, "model": config["model"], "error": f"HTTP {e}"}
    except (KeyError, IndexError) as e:
        return {"text": "", "provider": provider, "model": config["model"], "error": f"解析响应失败: {e}"}
    except Exception as e:
        return {"text": "", "provider": provider, "model": config["model"], "error": str(e)}


def verify_field_with_api(
    image_path: str,
    question: str,
    ocr_value: str,
    suspected_value: str,
    provider: Optional[str] = None,
) -> dict:
    """
    用 Vision API 复核单个存疑字段。

    Args:
        image_path: 裁剪后的字段图片路径
        question: 复核问题（如"请识别图中的桩号"）
        ocr_value: OCR 初步识别值
        suspected_value: 疑似正确值
        provider: 指定 Provider

    Returns:
        {"verified_value": "...", "confidence": "...", "note": "...", "provider": "..."}
    """
    prompt = VERIFY_FIELD_PROMPT.format(
        question=question,
        ocr_value=ocr_value,
        suspected_value=suspected_value,
    )

    result = call_vision_api(image_path, prompt, provider=provider)

    if result.get("error"):
        return {
            "verified_value": "",
            "confidence": "error",
            "note": result["error"],
            "provider": result.get("provider", ""),
        }

    # 尝试解析 JSON 响应
    text = result["text"].strip()
    # 去掉可能的 markdown 代码块标记
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        parsed = json.loads(text)
        parsed["provider"] = result["provider"]
        return parsed
    except json.JSONDecodeError:
        # API 没返回标准 JSON，直接取文本作为识别结果
        return {
            "verified_value": text,
            "confidence": "medium",
            "note": "API 未返回标准 JSON，取原始文本",
            "provider": result["provider"],
        }


def ocr_with_api(image_path: str, provider: Optional[str] = None, is_handwritten: bool = False) -> dict:
    """
    用 Vision API 直接做 OCR（整页识别）。

    Args:
        image_path: 图片路径
        provider: 指定 Provider
        is_handwritten: 手写体标记。为 True 时追加针对手写体的 System Prompt，
                        引导模型结合上下文推断、用 `[?]` 标记无法辨认字、严格 JSON 输出。

    Returns:
        {"text": "...", "provider": "...", "model": "..."}
    """
    system_prompt = None
    if is_handwritten:
        system_prompt = HANDWRITTEN_OCR_PROMPT
    return call_vision_api(image_path, CONSTRUCTION_OCR_PROMPT, provider=provider, system_prompt=system_prompt)


# ========== CLI ==========

def main():
    parser = argparse.ArgumentParser(
        description="Vision API 统一配置层 — 支持 7 家主流 Vision API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="列出所有可用 Provider",
    )
    parser.add_argument(
        "--test", "-t", metavar="图片路径",
        help="测试 API 调用（识别指定图片）",
    )
    parser.add_argument(
        "--provider", "-p", default=None,
        help="指定 Provider（如 qwen/doubao/glm/kimi/silicon/baidu/openai）",
    )
    args = parser.parse_args()

    if args.list:
        providers = detect_available_providers()
        if not providers:
            print("❌ 未检测到任何可用的 Vision API Provider。")
            print("   请设置以下任一环境变量：")
            for key, config in PROVIDERS.items():
                print(f"   {config['env_key']:<25} → {config['name']}")
            return

        print(f"✅ 检测到 {len(providers)} 个可用 Provider（按价格从低到高）：\n")
        print(f"{'Provider':<12} {'名称':<10} {'模型':<30} {'价格(元/千token)':<15}")
        print("-" * 70)
        for p in providers:
            print(f"{p['provider']:<12} {p['name']:<10} {p['model']:<30} {p['price_per_1k']:<15.3f}")
        return

    if args.test:
        if not Path(args.test).exists():
            print(f"❌ 文件不存在: {args.test}")
            return

        provider = args.provider or get_best_provider()
        if not provider:
            print("❌ 未检测到可用的 Vision API Provider。")
            print("   请设置环境变量后重试。运行 --list 查看支持的 Provider。")
            return

        print(f"  [i] 使用 Provider: {PROVIDERS[provider]['name']} ({provider})")
        print(f"  [i] 模型: {PROVIDERS[provider]['model']}")

        result = ocr_with_api(args.test, provider=provider)

        if result.get("error"):
            print(f"❌ 调用失败: {result['error']}")
        else:
            print(f"\n✅ 识别结果 ({len(result['text'])} 字符)：\n")
            print(result["text"])
        return

    parser.print_help()


if __name__ == "__main__":
    main()
