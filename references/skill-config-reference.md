# Skill 配置参考

> 本文件包含 SKILL.md 正文引用的配置数据和参考表。AI 仅在需要确认具体参数时读取。

## 前置信息确认（6 项）

### 第 1 项 · 资料阶段（`stage`）

| 选项 | 含义 | 影响 |
|---|---|---|
| `施工过程` | 正在施工 | 签字完整性按过程资料松标准 |
| `分部分项验收` | 子项完工报验（默认） | 标准验收判定 |
| `竣工移交归档` | 全部完工 | 按 MH/T 5078 严格标准 |
| `不清楚` | 拿不准 | 按分部分项验收处理 |

### 第 2 项 · 资料形式（`nature`）

| 选项 | 含义 |
|---|---|
| `电子版` | Word/Excel/电子 PDF，无需 OCR |
| `扫描件` | 图片/扫描 PDF，需 OCR |
| `扫描转化电子文档` | 用户已用 WPS 等工具把扫描件转成 Word(.docx)，走**电子表解析**（真实表格结构），无需 OCR |
| `混合` | 既有电子版又有扫描件 |
| `图纸` | 施工图/CAD 截图 |

> **`扫描转化电子文档` 说明**：优先推荐此路径——扫描件先用 WPS「PDF 转 Word」转成带真实表格的 .docx，识别准确率显著高于本地 OCR。这些 .docx 按电子表解析，第 4 项 OCR 引擎选择自动置灰/跳过，不设 OCR 优先级路由。因仍源自手写扫描，`human_verified` 人工核对闸门照常保留。

### 第 3 项 · 审核范围（`scope`，默认 `全量审核`）

| 选项 | 含义 |
|---|---|
| `全量审核` | 文件夹里所有资料都审 |
| `指定文件` | 只审用户点名的文件 |
| `指定分部分项` | 只审某个分部分项 |
| `指定专业` | 只审某个专业（场道/空管/助航/弱电/供油） |

### 第 4 项 · OCR 引擎（`ocr_engine`，默认 `auto`）

| 选项 | 说明 |
|---|---|
| `auto`（推荐） | 印刷体走本地 rapidocr，手写体自动转 VLM |
| `rapidocr` | 纯本地、零 token、离线可用；手写体识别率低 |
| `vision` | 云端 API，手写体识别率最高，需配 Key |
| `agent` | AI 读图，零安装；页数不限，但很慢费 token |

**引擎选择权交使用者（强制流程）**：AI 必须把上表 4 引擎作为卡片选项主动摆给使用者选，逐项说明代价，默认推荐 `auto`；使用者明确选一个后才落盘 `preconditions.json`。**严禁 AI 静默使用默认值**。

**来源留痕字段 `ocr_engine_source`**：与 `ocr_engine` 一并写回 preconditions，取值 `user_chosen`（使用者显式选择 / 提供了前置信息文件）或 `default`（全默认）。满足"审核过程留痕"铁律。

### 第 5 项 · 特殊说明（`special_notes`，可空）

有特殊情况才填：「电子版和扫描件是同一份资料的不同版本」「这批是补资料」「某文件请重点查运算」。无则填"无"。

### 第 6 项 · 要查签字吗？（`check_signatures`，默认 `false`）

| 选项 | 含义 |
|---|---|
| `否`（默认） | 不查签字，更快 |
| `是` | 校验签字完整性+一致性，报告内嵌对比图 |

## Vision API Provider 配置

| Provider | 名称 | 环境变量 | 默认模型 | 价格（元/千token） |
|:---:|:---|:---|:---|:---:|
| doubao | 豆包（推荐） | `ARK_API_KEY` | doubao-vision-pro-32k | **0.003** |
| silicon | 硅基流动 | `SILICONFLOW_API_KEY` | Qwen2-VL-72B-Instruct | 0.004 |
| qwen | 通义千问 | `DASHSCOPE_API_KEY` | qwen-vl-max | 0.008 |
| baidu | 百度千帆 | `BAIDU_API_KEY` | ernie-4.5-vl-preview | 0.008 |
| glm | 智谱 | `ZHIPU_API_KEY` | glm-4v-plus | 0.010 |
| kimi | Kimi | `MOONSHOT_API_KEY` | moonshot-v1-8k-vision | 0.012 |
| openai | OpenAI | `OPENAI_API_KEY` | gpt-4o | 0.015 |

```powershell
# 推荐：豆包 Vision Pro（最便宜，中文OCR最准）
$env:ARK_API_KEY = "你的火山引擎 API Key"
# 验证可用 Provider
python scripts/vision_providers.py --list
```

## index.json 项目总索引结构

```json
{
  "schema_version": "1.0",
  "project_name": "项目名称",
  "project_path": "项目文件夹绝对路径",
  "created_at": "2026-07-29T10:00:00",
  "updated_at": "2026-07-30T15:30:00",
  "stage": "foundation_built | human_verified | reviewed | reported",
  "preconditions": { "stage": "分部分项验收", "nature": "扫描件", "scope": "全量审核", "ocr_engine": "auto", "special_notes": "" },
  "file_classification": {
    "audited_files": ["扫描件.pdf"],
    "reference_files": ["设计变更通知单.pdf"],
    "excluded_files": ["测试文档.pdf"]
  },
  "documents": [
    {
      "id": "DOC-001", "original_file": "扫描件.pdf",
      "doc_type": "碎石桩施工记录", "professional": "01_场道工程",
      "subdivision_code": "01-03", "subdivision_label": "场道工程 → 特殊土处理",
      "subcategory": "施工记录", "pages": 49,
      "ocr_status": "completed", "ocr_engine": "auto", "ocr_confidence": 0.833,
      "content_hash": "sha256...",
      "data_file": "01_场道工程/施工记录/碎石桩施工记录.json",
      "quality_file": "...", "confusion_file": "...",
      "quality_alerts": 3, "confusion_suspects": 5,
      "human_verified": false, "corrected_file": null,
      "audit_status": "pending", "last_updated": "2026-07-29T10:15:00"
    }
  ],
  "corrections": {"total": 0, "file": "修正记录/corrections.json"},
  "gaps": [{"type": "pile_no_gap", "professional": "01_场道工程", "description": "Z420→Z418 缺 Z419", "detected_at": "..."}],
  "audit_logs": []
}
```

**关键字段**：
- `stage`：流水线阶段状态，阶段间闸门依据
- `documents[].ocr_status`：阶段 1→阶段 2 闸门
- `documents[].human_verified`：阶段 2→阶段 3 闸门
- `documents[].content_hash`：增量更新对比依据（SHA256）
- `documents[].subdivision_code`：多 Agent 拆分依据
- `gaps[]`：断档检测结果

## 输入兼容矩阵

| 输入形式 | 处理方式 | 备注 |
|---------|---------|------|
| Word .docx | markitdown / python-docx | 电子档 |
| Excel .xlsx | markitdown / openpyxl | 电子档 |
| PDF（电子档） | PyMuPDF 提取 | 中文 100% 准确 |
| PDF（扫描件·印刷体） | PyMuPDF 转图片 + RapidOCR | 90%+ 准确 |
| PDF（扫描件·手写体） | PyMuPDF 转图片 + Vision VLM | 识别率最高 |
| 图片 | RapidOCR + Tesseract + Vision API | 多层降级 |
| 文字描述 | 直接解析 | 用户口述 |
| 目录（批量） | 逐份处理 | 自动汇总报告 |
| 指定条款 | 精准审核 | 跳过部分步骤 |
| 指定分部分项 | 精准定位 | 如"场道-土方-换填" |
| 历史审核 | 调取日志 | 复查/对比 |

## 使用技术清单

| 工具 | 来源 | 用途 |
|------|------|------|
| PyMuPDF (fitz) | 开源 | PDF 电子档提取 |
| RapidOCR (rapidocr) | 开源 | 扫描件 OCR 本地主力（ONNX Runtime） |
| Vision API (VLM) | 云端 | 手写体 OCR 主力 |
| Tesseract (pytesseract) | 开源 | 扫描件 OCR 备选 |
| Pillow (PIL) | 开源 | 图片处理 |
| obsidian-cli | 已装 | 规范知识库查询 |
| lark-cli | 已装 | 飞书云盘读取 |
| markitdown | 微软开源 | 文档格式转换备选 |
| Read/Write 工具 | TRAE 内置 | AI 视觉识别兜底/文档输出 |
| data_quality_check.py | Skill 自带 | 数据质量四类检测 |

## 参考资料清单

| 文件 | 用途 |
|------|------|
| `references/classification-terms.json` | 资料分类关键词与别名映射 |
| `references/audit-checklists.md` | 五大专业通用审核清单 |
| `references/specification-mapping.md` | 资料类型↔规范条款映射 |
| `references/calculation-standards.md` | 6类运算规范参考 |
| `references/document-templates.md` | 报告/日志模板 |
| `references/airfield-engineering-audit.md` | 场道工程专项审核要点 |
| `references/atc-engineering-audit.md` | 空管工程专项审核要点 |
| `references/visual-aids-audit.md` | 目视助航设施专项审核要点 |
| `references/weak-electricity-audit.md` | 弱电系统专项审核要点 |
| `references/fuel-supply-audit.md` | 供油工程专项审核要点 |
| `references/high-frequency-errors.md` | 高频错误模式库 |
| `references/logic-conflict-patterns.md` | 逻辑矛盾识别模式库 |
| `references/data-quality-patterns.md` | 数据质量检测规则库 |
| `references/ocr-confusion-correction.md` | OCR 混淆修正规则 |
| `references/ocr-hybrid-architecture.md` | OCR 混合架构说明 |
| `references/specification-quick-reference.md` | 规范条款速查表 |
| `references/html-report-template.html` | 审核报告 HTML 标准模板 |
| `references/native-mode-checklist.md` | 原生模式审核检查清单（34 项） |
| `references/native-mode-stage1-checklist.md` | 原生模式阶段 1 机械化步骤清单 |
| `references/v5.0-legacy-mode.md` | 旧版单文件审核模式 |
| `references/CHANGELOG.md` | 版本更新历史 |
| `references/cli-reference.md` | CLI 命令参考 |
| `references/skill-config-reference.md` | 本文件（配置参考） |