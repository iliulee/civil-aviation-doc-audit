# 混合 OCR 架构 v9.4

> 核心思路：**印刷体走本地 RapidOCR（轻量、零 token）→ 手写体自动前置路由 VLM（识别率最高）→ 存疑字段进混淆检测 + 数据质量检测 → 人工核对兜底**。只在真正存疑的字段上花精力，不做整页重复识别。
>
> 本文件描述 v9.4 实际落地的 OCR 引擎与路由架构。旧版（v4.1）以 PaddleOCR 为主引擎的架构已随 v9.0 重写彻底移除，不再适用。

## 引擎总览

| 引擎 | 角色 | 说明 | 命令 |
|------|------|------|------|
| `auto`（默认） | 自动路由 | 按手写体/印刷体 + 各引擎可用性自动选择 | `ocr_image.py "<文件>" --out out.txt` |
| `rapidocr` | 本地主力 | RapidOCR（PP-OCRv6 Small），零 token，跨平台 | `ocr_image.py "<文件>" --engine rapidocr --out out.txt` |
| `vision` | 手写体主力 | 云端 VLM（豆包/通义等），识别率最高 | `ocr_image.py "<文件>" --engine vision --out out.txt` |
| `agent` | 复核工具 | AI 内置 Vision，不限页数，仅提醒 token 消耗 | `ocr_image.py "<文件>" --engine agent --out out.txt` |
| `tesseract` | 最终兜底 | OCR 全部不可用时的备选 | `ocr_image.py "<文件>" --engine tesseract --out out.txt` |

> `--handwritten` 全局标记：手写资料强制走 `vision`/`agent`，跳过本地 OCR。`--page N` 只处理指定页。

## 手写体前置路由

手写体与印刷体的识别策略完全不同，必须在进入 OCR 前完成判定，避免本地 RapidOCR 硬啃手写稿产生垃圾结果。

```
is_handwritten 判定优先级：
  --handwritten 全局标记 > config.is_handwritten > 内容级判定 > 文件名启发式
```

- **前置硬路由**（三管齐下，优先级最高）：
  1. 文件名/目录含"手写/笔记/草稿/note"关键词 → 直接判手写
  2. 内容级判定：桩号段重复/跳号、数值越界、时间列非法值、同一值大面积重复等结构异常信号
  3. 低置信度局部复核：confidence 低于阈值的项调用 crop_and_verify() 裁剪单元格后送 vision 复核
- **路由结果**：
  - `is_handwritten=True` → `vision`（首选）→ `agent`（次选，无 API Key 时）
  - `is_handwritten=False` → `rapidocr` → `vision` → `tesseract`

## auto 模式路由优先级链

```
手写体 + 有 Vision          → vision
手写体 + 无 Vision          → agent
印刷体 + 有 RapidOCR        → rapidocr
印刷体 + 无 RapidOCR + Vision → vision
印刷体 兜底                  → tesseract
```

配置开关 `DISABLE_HANDWRITING_ROUTE=1` 可禁用 VLM 路由，强制所有资料走本地 OCR。

## 图像预处理

仅保留**灰度化**。在 v9.2 已删除 CLAHE、高斯模糊、锐化核——这些增强在树桩/表格识别场景会引入噪声而非提升精度。

- PDF 转图 DPI 固定 `200`（dpi=72 实测 0 行识别；dpi=300 体积 2.5x 且速度慢 1.8x）

## 表格识别（几何重建主导）

表格结构识别采用**几何重建**为主，RapidTable 仅作候选网格交叉校验：

- `table_struct.build_rows_from_items()` 用 OCR items 的 bbox 做几何网格列对齐
- 值格式锚点定列 + 表头消歧 + 六类校验（类型/格式/范围/完整性/一致性/跨字段数学链）
- 内容感知分类：OCR 文本命中桩基表头关键词（碎石桩/沉管时间/拔管时间/充盈系数/密实电流/桩底高程/桩顶高程等）≥2 个时，自动切桩基几何网格解析
- RapidTable(SLanetPlus) 仅作交叉校验，不主导定列（碎石桩无线表 SLanetPlus 结构识别效果差，未采用）

## 混淆检测 + 数据质量检测

OCR 结果进入数据底座前，经过两道检测：

| 层 | 脚本 | 作用 |
|----|------|------|
| OCR 混淆检测 | `ocr_confusion_check.py` | 检测 Z→2、4→0、3→8 等常见误读，输出存疑字段清单 |
| 数据质量检测 | `data_quality_check.py` | 四类检测 + 列错位（≥5% 强制 needs_review）+ 桩号/高程/数学链校验 |

存疑字段最终进入 `data-editor.html` 人工核对（左图右表），`human_verified=true` 后才能进入正式审核。

## Vision API Provider（vision_providers.py）

| Provider | 名称 | 环境变量 | 默认模型 |
|----------|------|----------|----------|
| qwen | 通义千问 | DASHSCOPE_API_KEY | qwen-vl-max |
| doubao | 豆包 | ARK_API_KEY | doubao-vision-pro-32k |
| glm | 智谱 | ZHIPU_API_KEY | glm-4v-plus |
| kimi | Kimi | MOONSHOT_API_KEY | moonshot-v1-8k-vision-preview |
| silicon | 硅基流动 | SILICONFLOW_API_KEY | Qwen/Qwen2-VL-72B-Instruct |
| baidu | 百度千帆 | BAIDU_API_KEY | ernie-4.5-vl-preview |
| openai | OpenAI | OPENAI_API_KEY | gpt-4o |

> GEMINI_API_KEY 为旧版兼容标记，走独立接口。

## 相关文件

| 文件 | 作用 |
|------|------|
| `scripts/ocr_image.py` | OCR 主入口：引擎路由（rapidocr/vision/agent/tesseract）+ 手写体前置路由 |
| `scripts/vision_providers.py` | Vision API 统一配置层（Provider 检测/调用） |
| `scripts/ocr_confusion_check.py` | OCR 混淆检测（存疑字段清单） |
| `scripts/data_quality_check.py` | 数据质量检测（列错位/数学链等） |
| `scripts/table_struct.py` | 表格几何重建 + 六类校验 + 内容感知分类 |
| `scripts/postprocess.py` | 领域后处理（桩号/高程/时间修正） |
| `references/ocr-confusion-correction.md` | OCR 混淆校正规则库 |