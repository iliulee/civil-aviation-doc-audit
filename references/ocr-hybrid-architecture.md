# 混合 OCR 架构 v3.0

> 核心思路：RapidOCR 做全量提取（快、免费）→ 混淆检测筛出存疑字段 → AI 智能体自动读图复核存疑字段（准、零成本）→ 合并结果。只在存疑字段上花精力，不做整页重复识别。

## 架构总览

```
原始扫描件
    │
    ▼
┌─────────────────────────────────────┐
│ Layer 1: RapidOCR 全量提取          │
│ ocr_image.py --out output.txt       │
│ 三级降级：RapidOCR→Tesseract→API    │
└──────────────┬──────────────────────┘
               │ 结构化 JSON
               ▼
┌─────────────────────────────────────┐
│ Layer 2: OCR 混淆检测               │
│ ocr_confusion_check.py data.json    │
│ 检测 Z→2、4→0、3→8 等常见误读       │
│ 输出：存疑字段清单                   │
└──────────────┬──────────────────────┘
               │ 存疑字段清单
               ▼
┌─────────────────────────────────────┐
│ Layer 3: 存疑字段自动复核            │
│ verify_fields.py auto               │
│                                     │
│ ┌─ 路径 B（默认）: 智能体复核 ─────┐ │
│ │ 1. 脚本裁剪存疑字段原图区域→PNG │ │
│ │ 2. 输出 agent_verify_tasks.json │ │
│ │ 3. AI 智能体自动读图验证        │ │
│ │ 4. 输出 verify_results.json     │ │
│ │ 5. 脚本合并结果                 │ │
│ │ 全自动，零成本，无需用户参与     │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─ 路径 A: API 复核 ───────────────┐ │
│ │ 脚本自动调用 Vision API          │ │
│ │ 只发存疑字段，省成本             │ │
│ │ 需配置 API Key                   │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─ 路径 C: 增强重跑 ───────────────┐ │
│ │ 高 DPI + 图像预处理              │ │
│ │ 只重跑存疑页                     │ │
│ │ 无 API 无智能体时使用            │ │
│ └─────────────────────────────────┘ │
└──────────────┬──────────────────────┘
               │ 修正后数据
               ▼
┌─────────────────────────────────────┐
│ Layer 4: 数据质量检测               │
│ data_quality_check.py               │
│ 四类检测 + 致岩豁免 + 桩号总数校验  │
└─────────────────────────────────────┘
```

## 路径 B：智能体复核（默认，推荐）

### 设计原则

**skill 运行在 AI 智能体中，智能体自身具备 Vision 能力。不需要用户拖动文件到外部工具，不需要人工参与。**

### 工作流程

```
Step 1: 脚本裁剪图片 + 输出任务清单
  python verify_fields.py auto <原始文件> <混淆检测JSON> --data <数据JSON> --out <输出目录>
  → 输出 agent_verify_tasks.json
  → 输出 crops/ 目录（裁剪后的 PNG 图片）

Step 2: AI 智能体自动读图验证（全自动）
  AI 智能体读取 agent_verify_tasks.json
  对每个 task：
    - 读取 task.image_path 指向的 PNG 图片（用 Read 工具）
    - 用 Vision 能力识别图片中的字段值
    - 判断 OCR 结果是否正确，给出修正值
  输出 verify_results.json

Step 3: 脚本合并结果
  python verify_fields.py merge <verify_results.json> --data <数据JSON> --out <修正后JSON>
  → 输出 verified_data.json
```

### agent_verify_tasks.json 格式

```json
{
  "status": "prepared",
  "next_action": "agent_verify",
  "total_tasks": 3,
  "tasks": [
    {
      "task_id": "VERIFY-001",
      "image_path": "/path/to/crops/task_1_p1.png",
      "field": "pile_no",
      "row": 5,
      "page": 1,
      "ocr_value": "2370",
      "suspected_value": "Z370",
      "reason": "桩号前缀 Z→2 混淆（48/50 桩号以 Z 开头，本行以 2 开头）",
      "question": "请识别图片中第 桩号 列的数值。OCR 初步识别为「2370」，但可能有误。疑似正确值为「Z370」。请仔细看图，给出正确值。"
    }
  ],
  "output_format": {
    "file": "verify_results.json",
    "structure": {
      "results": [
        {
          "task_id": "VERIFY-001",
          "field": "pile_no",
          "row": 5,
          "verified_value": "Z370",
          "confidence": "high",
          "note": "图片清晰可见 Z 前缀"
        }
      ]
    }
  },
  "merge_command": "python verify_fields.py merge <verify_results.json> --data <原始数据JSON> --out <修正后数据JSON>"
}
```

### verify_results.json 格式（AI 智能体输出）

```json
{
  "results": [
    {
      "task_id": "VERIFY-001",
      "field": "pile_no",
      "row": 5,
      "verified_value": "Z370",
      "confidence": "high",
      "note": "图片清晰可见 Z 前缀，OCR 误读为 2"
    },
    {
      "task_id": "VERIFY-002",
      "field": "filling_coeff",
      "row": 12,
      "verified_value": "1.46",
      "confidence": "high",
      "note": "原图为 1.46，OCR 误读 4→0 为 1.06"
    }
  ]
}
```

### 置信度说明

| 置信度 | 含义 | 合并策略 |
|--------|------|----------|
| high | 图片清晰，识别确定 | 自动替换 OCR 值 |
| medium | 图片可辨认但有不确定性 | 自动替换，标注"需复核" |
| low | 图片模糊无法确认 | 不替换，保留 OCR 原值，标注"存疑" |
| error | 图片不存在或无法读取 | 不替换，标注错误 |

## 路径 A：API 复核

### 适用场景

用户配置了 Vision API Key，希望脚本自动调用 API 复核。

### 支持的 Provider

| Provider | 名称 | 环境变量 | 默认模型 |
|----------|------|----------|----------|
| qwen | 通义千问 | DASHSCOPE_API_KEY | qwen-vl-max |
| doubao | 豆包 | ARK_API_KEY | doubao-vision-pro-32k |
| glm | 智谱 | ZHIPU_API_KEY | glm-4v-plus |
| kimi | Kimi | MOONSHOT_API_KEY | moonshot-v1-8k-vision-preview |
| silicon | 硅基流动 | SILICONFLOW_API_KEY | Qwen/Qwen2-VL-72B-Instruct |
| baidu | 百度千帆 | BAIDU_API_KEY | ernie-4.5-vl-preview |
| openai | OpenAI | OPENAI_API_KEY | gpt-4o |

### 使用方式

```bash
# 自动检测最便宜的可用 Provider
python verify_fields.py auto <原始文件> <混淆检测JSON> --data <数据JSON> --verify-path api

# 指定 Provider
python verify_fields.py auto <原始文件> <混淆检测JSON> --data <数据JSON> --verify-path api --provider qwen
```

### 成本优化

- 只发存疑字段对应的裁剪图片，不发整页
- 每张裁剪图片通常 < 50KB，API 调用成本极低
- 一次审核通常 3~10 个存疑字段，总成本 < 0.01 元

## 路径 C：增强重跑

### 适用场景

无 API Key 且智能体无 Vision 能力时的兜底方案。

### 工作方式

- DPI 提升至 300（默认 200）
- det_limit_side_len 提升至 1280
- 图像预处理：灰度 → 中值滤波去噪 → 对比度增强 1.5x
- 只重跑存疑字段所在的页，不整本重跑

### 使用方式

```bash
python verify_fields.py auto <原始文件> <混淆检测JSON> --data <数据JSON> --verify-path enhance
```

## 路径选择逻辑

```
默认 → 路径 B（智能体复核）
  │
  ├─ 智能体有 Vision 能力（TRAE/豆包/Kimi 等）
  │  → 裁剪图片 + 输出任务清单
  │  → AI 智能体自动读图验证
  │  → 零成本、全自动
  │
  ├─ 用户手动指定 --verify-path api
  │  → 脚本自动调用 Vision API
  │  → 只发存疑字段，省成本
  │
  └─ 用户手动指定 --verify-path enhance
     → 增强参数重跑 RapidOCR
     → 免费但精度有限
```

## 与旧版（v2.2）的区别

| 维度 | v2.2 | v3.0 |
|------|------|------|
| OCR 复核方式 | 手动用 `--mode vision --page N` 逐页重读 | 自动裁剪存疑字段 + 智能体读图验证 |
| 用户参与度 | 需要用户判断哪页哪字段需要复核 | 全自动，脚本检测存疑字段并裁剪 |
| 成本 | 整页发送给 API | 只发存疑字段的裁剪图片 |
| 复核精度 | 依赖 RapidOCR 二次识别或整页 API | 智能体 Vision 精准识别裁剪区域 |
| 多 API 支持 | 仅硅基流动 | 7 家主流 Vision API |
| 智能体集成 | 无 | 默认路径，零成本全自动 |

## 相关文件

| 文件 | 作用 |
|------|------|
| `scripts/ocr_image.py` | Layer 1: RapidOCR 全量提取 |
| `scripts/ocr_confusion_check.py` | Layer 2: OCR 混淆检测 |
| `scripts/verify_fields.py` | Layer 3: 存疑字段自动复核编排 |
| `scripts/vision_providers.py` | 路径 A: Vision API 统一配置层 |
| `scripts/data_quality_check.py` | Layer 4: 数据质量检测 |
| `references/ocr-confusion-correction.md` | OCR 混淆校正规则库 |
