---
name: "civil-aviation-doc-audit"
description: "民航建设施工资料合规审核大师。审核资料是否符合MH/T 5078等民航行业规范、验证结构运算是否符合运算规范、支持OCR识别扫描件、多Agent并行批量审核、三级输出格式（Fatal/Sanity Check/Best Practice）、知识分区红线防幻觉、可自动生成审核报告和整改通知。专门针对民航运输机场专业工程（场道/空管/助航/弱电/供油）五大专业的施工资料合规性审核场景。当用户要求审核民航施工资料、检查资料合规性、验证运算规范、识别扫描件资料、生成审核报告或整改通知时触发。"
---

# 民航建设施工资料合规审核大师（civil-aviation-doc-audit）v6.0

> 面向民航运输机场专业工程建设项目，基于 MH/T 5078.1~5078.6-2024 资料管理规程体系，提供"建数据底座 → 人工核对 → 正式审核 → 生成报告"四阶段流水线审核能力，集成 OCR 扫描件识别、跨资料逻辑一致性检查、多 Agent 并行审核（按专业/分部/分项三级粒度拆分）、Web 数据编辑器、项目总览仪表盘等能力。五大专业全覆盖，每条审核意见有据可查。

## 技能定位

| 维度 | 内容 |
|------|------|
| 英文名 | `civil-aviation-doc-audit` |
| 中文名 | 民航建设施工资料合规审核大师 |
| 版本 | v6.0（四阶段流水线 + 数据底座 + Web 编辑器） |
| 适用领域 | 民航运输机场专业工程（场道/空管/助航/弱电/供油）五大专业全覆盖 |
| 核心规范 | MH/T 5078.1~5078.6-2024 系列 + 各专业技术规范（MH 5004/5007/5012/5034/4006 等） |
| 知识库 | 主引擎：`references/` 专项审核文件（16 个，已固化条款+参数阈值）；增强源：Obsidian（`H:\Obsidian notes\溜哥笔记\wiki\sources\`），按需查询原文，非硬依赖 |
| 处理能力 | 电子文档/PDF/扫描件（OCR）/图片/批量/精准定位/项目维度数据底座/人工核对/多Agent并行 |
| 数据底座 | JSON（机器读写）+ MD（人工只读预览）双格式，纯文件系统存储，零数据库依赖，支持跨机器迁移和 git 版本追踪 |
| 多Agent拆分粒度 | professional（专业级）/ sub（分部级）/ item（分项级），与人工分部分项划分一致 |

---

## Obsidian 连接检测与引导（首次使用自动触发）

> 本 Skill 不依赖 Obsidian 也能正常工作。但接上 Obsidian 后，遇到 references 未覆盖的条款可以直接读规范原文，审核结论更扎实。

### 检测机制

Skill 首次加载时，自动执行一次 `obsidian search query="MH/T 5078" limit=1`：

**✅ 连接成功**：
- 输出 Obsidian 中已有规范清单（如 MH/T 4006.2/4006.3、MH/T 6049 等）
- 标注哪些专业可享原文增强（当前：场道工程）
- 标注哪些专业以 references 为主（空管/助航/弱电/供油，因 MH/T 5078.3~5078.6 原文不在 Obsidian 中）

**❌ 连接失败**（Obsidian 未运行 / CLI 未安装 / vault 路径不对）：
- 显示以下引导信息：

```
⚠️ 未检测到 Obsidian 连接。不影响使用——本 Skill 的 13 个 references 文件已固化五大专业
   100+ 条检查项和 200+ 个技术参数阈值，可以直接审核。

📌 建议接上 Obsidian，好处是：
   - 遇到 references 未覆盖的条款时，可以读规范原文补充
   - 审核结论可以引用规范原文逐字印证（而不只是条款号）
   - 你的 Obsidian 里有 MH/T 4006.2/4006.3、MH/T 6049、MH/T 6010 等设备技术规范

🔧 接法：确保 Obsidian 已打开，vault 路径为：
   H:\Obsidian notes\溜哥笔记\
   然后说"检测 Obsidian"即可重新检测。
```

### 后续行为

- 检测结果**仅首次加载时显示一次**，不重复打扰
- 未接 Obsidian 时，审核照常进行，来源标注为"references 缓存层"
- 用户随时说"检测 Obsidian"或"连接 Obsidian"可重新触发检测
- 用户说"不用 Obsidian"则永久跳过检测

---

## 首次安装（首次使用自动触发）

> 当用户说「安装」「安装这个skill」「安装依赖」「设置环境」「部署」「初始化」等任一语句时，自动执行 `install.ps1`。

`install.ps1` 一键完成全部部署：

| 步骤 | 内容 | 说明 |
|------|------|------|
| 1 | Python 依赖 | `pip install -r requirements.txt`（含 PyMuPDF、pdf2image、python-docx、openpyxl、requests） |
| 2 | Poppler | 自动下载 Windows 便携版（~30MB）到 `tools/poppler/` |
| 3 | Tesseract OCR | 自动下载安装（~50MB），含中文语言包（显式备选引擎） |
| 4 | PaddleOCR | 自动安装 `paddleocr==2.8.1` + `paddlepaddle==2.6.2` + `opencv-python>=4.8.0` |
| 5 | 系统 PATH | 自动配置，无需手动 |
| 6 | 验证 | 逐一检查所有组件可用 |

安装完成后直接可用，无需任何手动操作。如果组件已安装则自动跳过。

### 首次加载环境检测（自动触发）

Skill 首次加载时（无论用户是否说"安装"），自动执行以下快速检测：

1. `python --version` → 确认 Python 可用
2. `python -c "import fitz; import openpyxl; import pdf2image"` → 确认核心依赖
3. `python -c "import shutil; print(shutil.which('pdftoppm'))"` 或检查 `tools/poppler/` → 确认 Poppler 可用
4. `python scripts/vision_providers.py --list` → 确认至少一个 Vision API Provider 可用（环境变量已设置）

**输出格式**：

```
✅ 民航建设施工资料合规审核大师 v6.0 已加载

环境检测：
  Python：3.11.4 ✅
  PyMuPDF：1.24.5 ✅
  openpyxl：3.1.2 ✅
  pdf2image：1.17.0 ✅
  Poppler：C:\...\pdftoppm.exe ✅（系统 PATH）
  Vision API：豆包 Vision Pro ✅ / 可用 Providers：doubao, qwen, glm

连接检测：
  Obsidian：未连接（不影响使用）

当前可用工作模式：
  1. v6.0 四阶段流水线（默认，推荐）
  2. v5.0 单文件审核（附录，仅限单份资料预览）
  3. 规则管理子系统（可选）

快速开始（四阶段流水线）：
  1. 把项目资料放进一个文件夹
  2. 说"建数据底座" → 自动 OCR + 结构化
  3. 打开 data-editor.html 人工核对
  4. 说"正式审核" → 生成审核日志
  5. 说"出报告" → 生成 HTML 审核报告
```

任一检测失败时，输出：

```
⚠️ 检测到依赖缺失，建议运行 install.ps1 完成安装。
缺失项：
  - openpyxl 未安装
  - Poppler 未检测到
是否现在安装？（确认后执行 install.ps1）
```

---

## OCR 引擎策略（v5.0 API-First）

v5.0 全面重构为 **API-First 策略**：Vision API 优先 → PaddleOCR 本地备选 → Tesseract 兜底。
默认 auto 模式自动选择最佳可用引擎，无需手动选择。

```
PDF / 图片
   │
   ▼
auto 模式自动检测可用引擎
   │
   ├─ 检测到 Vision API Key → 优先使用 Vision API（云端，按量付费）
   │   ├─ 自动选择最便宜可用 Provider（Doubao > SiliconFlow > Qwen > ...）
   │   ├─ 支持 7 家：doubao / qwen / glm / kimi / silicon / baidu / openai
   │   ├─ 设置任一环境变量即可使用（详见 vision_providers.py）
   │   └─ 推荐：Doubao Vision Pro（0.003元/千token，中文OCR最准最快）
   │
   ├─ 无 API Key → 降级为 PaddleOCR（本地，零成本）
   │   ├─ PP-OCRv4 模型，需安装 paddleocr + paddlepaddle
   │   ├─ enable_mkldnn=True, cpu_threads=10
   │   ├─ 桩号列检测 + Z/2 混淆自动修正
   │   └─ 桩号序列推断：按同行有效桩号趋势补全漏识别
   │
   └─ 无 PaddleOCR → 降级为 Tesseract（本地，需安装）
```

### 引擎选择指南

| 场景 | 推荐引擎 | 命令 |
|------|---------|------|
| 有 API Key（默认） | auto | `ocr_image.py "<文件>" --out out.txt` |
| 纯 API，不装本地依赖 | vision | `ocr_image.py "<文件>" --engine vision --out out.txt` |
| 离线/内网，零成本 | paddle | `ocr_image.py "<文件>" --engine paddle --out out.txt` |
| 关键数据复核（不惜成本） | vision | `ocr_image.py "<文件>" --engine vision --out out.txt` |
| 一键审核（默认 API 优先） | auto | `run_audit.py audit "<文件>" --data <JSON> --out <目录>` |

### 首次使用：设置 API Key

```powershell
# 推荐：豆包 Vision Pro（最便宜，中文OCR最准）
$env:ARK_API_KEY = "你的火山引擎 API Key"

# 或：通义千问 VL Max（阿里云）
$env:DASHSCOPE_API_KEY = "你的阿里云 API Key"

# 或：智谱 GLM-4V（国内合规）
$env:ZHIPU_API_KEY = "你的智谱 API Key"

# 验证可用 Provider
python scripts/vision_providers.py --list
```

### 离线场景：安装 PaddleOCR

```powershell
# 如果需要在无网络环境使用，手动安装 PaddleOCR
pip install paddleocr==2.8.1 paddlepaddle==2.6.2 opencv-python
# 首次运行会自动下载 PP-OCRv4 模型（~30MB）
```

---

## 四阶段流水线（v6.0 核心工作流）

> **🔴 强制规则：任何包含 2 份及以上资料的审核，必须走四阶段流水线。禁止走 v5.0 单文件模式，禁止跳过阶段 2 人工核对。**
> **🔴 强制规则：阶段 2 的 `human_verified` 未全部为 `true` 时，AI 不得生成任何审核报告。**

> **设计意图**：v5.0 之前是"一份资料走一遍 9 步"的线性流程，遇到大项目（几万页资料、多专业）会上下文溢出、人工核对无处落地、重复 OCR 浪费时间。v6.0 重构为四阶段流水线，每阶段有明确输入、输出和硬闸门，阶段间通过 `index.json` 的 `stage` 字段衔接。**默认走四阶段流水线**。

```
┌────────────────────────────────────────────────────────────────┐
│ 阶段 1：建数据底座（全自动）                                    │
│   输入：项目文件夹路径 + 5 项前置信息                           │
│   处理：文件扫描分类 → OCR 提取 → 结构化 JSON+MD → 质量检测 →   │
│         混淆检测 → 断档检测 → index.json 总索引 → 复制 Web 模板 │
│   输出：数据底座/（JSON + MD + index.json + 质量告警 + 混淆     │
│         检测 + 断档清单）+ 项目总览.html + data-editor.html     │
│   闸门：index.json 中所有文件 ocr_status = "completed"          │
│   铁律执行：R-10（数据质量先于规范合规）、R-11（全列提取）、     │
│             R-16（提取-验证-重试）                              │
│                                                                │
│   ↓ 人机闸门：数据未经人工确认，不进审核（铁律 R-02/R-20）      │
│                                                                │
│ 阶段 2：人工核对（人机交互，零对话 token）                      │
│   输入：数据底座/ + Web 数据编辑器（data-editor.html）          │
│   处理：左图右表对照 → 逐条确认告警 → 修正 OCR 误读 →           │
│         双视图编辑（结构化视图 + 原始文本视图均可编辑）→        │
│         点击"保存"导出 corrected_data.json →                    │
│         点击"确认完成"生成 corrections.json 并更新 human_verified │
│   输出：修正记录/corrections.json + 各文件 corrected_data.json  │
│   闸门：用户在 Web 编辑器中点击"确认完成"并导出修正数据         │
│   铁律执行：R-02（OCR 人工复核）、R-20（OCR 存疑项核实）        │
│                                                                │
│   ↓ 确认完成后，AI 读取修正后数据                              │
│                                                                │
│ 阶段 3：正式审核（全自动，支持多 Agent 并行）                   │
│   输入：修正后的 corrected_data.json + 前置信息                 │
│   处理：审核前置检查（human_verified 闸门）→                    │
│         任务拆分（专业/分部/分项三级粒度）→                     │
│         规范逐条对账 + 逻辑一致性检查（10 子项）+               │
│         运算规范审核（按需）→ 生成审核日志 JSON                 │
│   输出：审核日志/AU-{日期}-{序号}_审核日志.json                 │
│   铁律执行：R-01/R-03/R-04/R-05/R-06/R-09/R-15/R-17             │
│                                                                │
│   ↓                                                             │
│                                                                │
│ 阶段 4：生成报告（全自动）                                     │
│   输入：审核日志                                                │
│   处理：汇总发现 → 四级置信度标注 → 三级分类（Fatal/Sanity/     │
│         Best Practice）→ 套用 HTML 模板 → 生成 SVG 图表         │
│   输出：审核报告.html（统一交付物，9 章节强制）                 │
│   铁律执行：R-07/R-08/R-18/R-19                                 │
└────────────────────────────────────────────────────────────────┘
```

### 阶段间硬闸门

| 闸门 | 判定字段 | 通过条件 | 未通过的处理 |
|:---:|:---|:---|:---|
| 阶段 1 → 阶段 2 | `index.json` 中所有 `documents[].ocr_status` | 全部为 `"completed"` | 重新执行 build，或检查 OCR 引擎是否可用 |
| 阶段 2 → 阶段 3 | `index.json` 中所有 `documents[].human_verified` | 全部为 `true` | 阻断审核，提示用户打开 data-editor.html 完成核对 |
| 阶段 3 → 阶段 4 | `审核日志/` 目录下存在最新 `AU-*.json` | 审核日志完整生成 | 重新执行 review |

> **铁律 R-02 落地机制**：阶段 2 是 OCR 数据人工核对的硬闸门，未完成核对前 `human_verified=false`，阶段 3 的 `review_audit.py` 会拒绝执行（除非加 `--force`，仅测试用）。

### 阶段 1 CLI：建立数据底座

```powershell
# 基本用法
python {SKILL_DIR}/scripts/run_audit.py build "<项目文件夹路径>"

# 完整参数
python {SKILL_DIR}/scripts/run_audit.py build "<项目文件夹路径>" \
    --engine <auto|vision|paddle> \
    --incremental \
    --out "<数据底座目录名，默认'数据底座'>" \
    --preconditions "<前置信息JSON文件路径>" \
    --expected-rows "<预期行数JSON文件路径>"
```

**`--preconditions` JSON 文件格式**（5 项前置信息）：
```json
{
  "stage": "分部分项验收",
  "nature": "扫描件",
  "scope": "全量审核",
  "ocr_engine": "PaddleOCR",
  "special_notes": "电子版与扫描件为同一份资料的不同版本",
  "excluded_files": ["测试文档.pdf"],
  "expected_rows": {"碎石桩施工记录": 33}
}
```

**`--incremental` 增量模式**：基于文件 SHA256 哈希对比，仅处理新增或变更文件，已 OCR 过的文件不重复处理（NF-05）。

**自动产物**（生成到 `<项目文件夹>/数据底座/`）：
```
数据底座/
├── index.json                          ← 项目总索引（唯一真相源）
├── 01_场道工程/
│   └── 施工记录/
│       ├── 碎石桩施工记录.json          ← 结构化数据（机器读写）
│       ├── 碎石桩施工记录.md            ← 只读预览（人工查阅）
│       ├── 碎石桩施工记录_ocr.json      ← OCR 原始输出（追溯用）
│       ├── 碎石桩施工记录_quality.json  ← 质量检测结果
│       └── 碎石桩施工记录_confusion.json ← 混淆检测结果
├── 02_空管工程/
├── 03_助航设施/
├── 04_弱电系统/
├── 05_供油工程/
├── 通用资料/
├── 修正记录/                            ← 阶段 2 生成
└── 审核日志/                            ← 阶段 3 生成
```

同时复制 `templates/data-editor.html` 和 `templates/project-dashboard.html` 到项目文件夹根目录。

### 阶段 2：人工核对（Web 数据编辑器）

**零对话 token**：用户在浏览器中完成所有核对操作，不消耗 AI 对话 token（NF-01）。

**打开方式**：用户双击项目文件夹根目录下的 `data-editor.html`，浏览器自动加载 `数据底座/index.json`。

**编辑器核心功能**：
1. **文件列表导航**：下拉选择项目中的不同文件，切换时自动保存当前文件修改
2. **左图右表**：左侧 PDF.js 渲染原始扫描图（含放大镜），右侧可编辑表格
3. **翻页同步**：切页时左侧图片和右侧表格同步切换
4. **双视图模式**：结构化视图按字段分列展示；原始文本视图保留原始排版便于对比，**两种视图下均可直接编辑单元格**
5. **字段编辑**：点击单元格直接修改，修改时记录原值和新值
6. **质量告警逐条确认**：每条告警可"确认"（标记为已知问题）或"修正"（跳转到对应行）
7. **OCR 存疑项高亮**：混淆检测的存疑字段黄色标记，点击可看 OCR 原始值和建议值
8. **桩号导航**：输入桩号快速跳转
9. **列宽拖拽**：表头可拖拽调整列宽，固定列（行号）宽度锁定，翻页后列宽持久化
10. **保存**：点击"保存"生成 `corrected_data.json` 到对应文件目录
11. **确认完成**：点击"确认完成"生成 `修正记录/corrections.json` 并更新 `index.json` 的 `human_verified` 字段为 `true`

**MD 文件定位**：MD 是"工作台副本"——JSON 给机器读，MD 给人读，支持离线查看、Git diff、人工核改参考。**MD 不可编辑**，编辑走 Web 编辑器（避免双写冲突）。

### 阶段 3 CLI：正式审核

```powershell
# 单 Agent 模式（默认按分部级拆分，但串行执行）
python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹路径>"

# 完整参数
python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹路径>" \
    --out "<数据底座目录名，默认'数据底座'>" \
    --split-by <professional|sub|item> \
    --task-id "<任务ID>" \
    --tasks-file "<任务包JSON文件路径>" \
    --dry-run \
    --force
```

**`--split-by` 拆分粒度**（v6.0 新增，与人工分部分项划分一致）：
| 粒度 | 说明 | 典型场景 |
|:---:|:---|:---|
| `professional` | 按专业拆分（5 大专业） | 跨专业项目快速并行 |
| `sub`（默认） | 按分部工程拆分（48 个分部） | 常规项目，平衡并行度和任务开销 |
| `item` | 按分项工程拆分（115 个分项） | 大型项目，最大化并行度 |

**多 Agent 并行工作流**（v6.0 新增）：
```powershell
# 步骤 1：主 Agent 生成任务包（不执行审核）
python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹路径>" --split-by item --dry-run
# 产物：数据底座/审核日志/audit_tasks.json

# 步骤 2：每个子 Agent 执行一个任务（可并行）
python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹路径>" --task-id AU-20260730-001-001 --tasks-file "数据底座/审核日志/audit_tasks.json"
python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹路径>" --task-id AU-20260730-001-002 --tasks-file "数据底座/审核日志/audit_tasks.json"
# ... 每个 task-id 独立进程，可并行调度

# 步骤 3：主 Agent 汇总（执行无 task-id 的 review，自动合并所有子任务结果）
python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹路径>"
```

**`--force` 跳过闸门**：仅测试用，正式审核必须经过阶段 2 人工核对。

### 阶段 4 CLI：生成审核报告

```powershell
python {SKILL_DIR}/scripts/run_audit.py report "<项目文件夹路径>" \
    --out "<数据底座目录名，默认'数据底座'>"
```

**产物**：`<项目文件夹>/审核报告.html`（统一交付物，9 章节强制，含 SVG 环形图和水平条形图）。

### index.json 项目总索引（唯一真相源）

```json
{
  "schema_version": "1.0",
  "project_name": "项目名称",
  "project_path": "项目文件夹绝对路径",
  "created_at": "2026-07-29T10:00:00",
  "updated_at": "2026-07-30T15:30:00",
  "stage": "foundation_built | human_verified | reviewed | reported",
  "preconditions": {
    "stage": "分部分项验收",
    "nature": "扫描件",
    "scope": "全量审核",
    "ocr_engine": "PaddleOCR",
    "special_notes": ""
  },
  "file_classification": {
    "audited_files": ["扫描件.pdf"],
    "reference_files": ["设计变更通知单.pdf"],
    "excluded_files": ["测试文档.pdf"]
  },
  "documents": [
    {
      "id": "DOC-001",
      "original_file": "扫描件.pdf",
      "doc_type": "碎石桩施工记录",
      "professional": "01_场道工程",
      "subdivision_code": "01-03",
      "subdivision_label": "场道工程 → 特殊土处理",
      "subcategory": "施工记录",
      "pages": 49,
      "ocr_status": "completed",
      "ocr_engine": "PaddleOCR",
      "ocr_confidence": 0.833,
      "content_hash": "sha256...",
      "data_file": "01_场道工程/施工记录/碎石桩施工记录.json",
      "data_md": "01_场道工程/施工记录/碎石桩施工记录.md",
      "quality_file": "...",
      "confusion_file": "...",
      "quality_alerts": 3,
      "confusion_suspects": 5,
      "human_verified": false,
      "corrected_file": null,
      "audit_status": "pending",
      "last_updated": "2026-07-29T10:15:00"
    }
  ],
  "corrections": {"total": 0, "file": "修正记录/corrections.json"},
  "gaps": [
    {"type": "pile_no_gap", "professional": "01_场道工程", "description": "Z420→Z418 缺 Z419", "detected_at": "..."}
  ],
  "audit_logs": []
}
```

**关键字段说明**：
- `stage`：流水线阶段状态，阶段间闸门的依据
- `documents[].ocr_status`：阶段 1 → 阶段 2 闸门
- `documents[].human_verified`：阶段 2 → 阶段 3 闸门
- `documents[].content_hash`：增量更新对比依据（SHA256）
- `documents[].subdivision_code`：多 Agent 拆分依据（如 `01-03` = 场道工程-特殊土处理）
- `gaps[]`：断档检测结果（桩号/日期/编号连续性问题）

### 断档检测（v6.0 新增，铁律 R-16 扩展）

阶段 1 建底座时自动执行，写入 `index.json` 的 `gaps[]` 数组：

| 检测类型 | 说明 | 示例 |
|:---|:---|:---|
| `pile_no_gap` | 桩号不连续 | Z420→Z418 缺 Z419 |
| `date_gap` | 日期不连续 | 4-15→4-17 缺 4-16 |
| `sequence_no_gap` | 编号不连续 | 001→003 缺 002 |

断档不阻塞阶段 1 完成，但在项目总览仪表盘中标红提示，并在阶段 3 审核时作为逻辑一致性检查的输入。

---

## 规则管理子系统（v6.0 新增）

> 91 条规则三层分级、形式化存储、可视化管理、反馈闭环、LLM 自成长。规则不再散落在文档叙述中，而是以结构化 JSON 形式集中管理，支持全生命周期流转、效力自监控、定时反思优化。

### 规则分级体系

| 层级 | 代号 | 判定标准 | 违反后果 | 示例 |
|:---:|:---:|:---|:---|:---|
| L1 铁律 | L1-IRON | 不可商榷的合规底线 | 🔴 Fatal，直接判不合格，不可降级 | R-01 规范可追溯、R-06 拒为伪证背书 |
| L2 逻辑一致性 | L2-LOGIC | 数学/几何/时序/引用自洽 | 🟡 Sanity Check，须人工复核 | 实长=桩顶高程-桩底高程（原 R-12，已修正层级错位） |
| L3 业务合理性 | L3-BUSINESS | 阈值/经验/行业惯例 | 🔵 Best Practice，提示性警告 | 突变率≥30% 警告 |
| 跨单位对照 | SCOPE-CROSS_UNIT | 监理-施工方跨单位对照 | 按 L1/L2/L3 分级 | 混凝土量偏差>5% |

### 规则形式化存储

91 条规则已从文档叙述迁移至 `rules/` 目录，以 JSON 文件形式按层级分子目录存储：

```
rules/
├── L1-iron/                  # L1 铁律（17 条）
├── L2-logic/                 # L2 逻辑一致性（71 条，含 IR-012/013/014 几何/合计/多参数联检）
├── L3-business/              # L3 业务合理性（3 条）
├── cross-unit/               # 跨单位对照（18 条）
├── custom/
│   ├── draft/                # 用户草稿
│   └── incubator/            # 孵化区候选规则
├── reflections/              # 反思报告
├── schema/                   # JSON Schema
└── registry.json             # 全量注册表（91 条）
```

每条规则包含字段：`rule_id`、`name`、`level`、`scope`、`trigger_when`、`check_expr`、`error_template`、`status`、`source`、`version`、`changelog`、`stats`、`alignment` 等。

### 规则管理面板

`templates/rule-manager.html` 提供可视化管理界面，含 4 个标签页：

| 标签页 | 功能 |
|--------|------|
| 规则列表 | 多维度筛选（层级/状态/作用域）、查看详情、状态流转、协同确认 |
| 新建规则 | 可视化规则编辑器，支持触发条件、检查表达式、错误模板的字段化编辑 |
| 统计仪表盘 | 规则总数、各层级分布、命中率/误报率 Top 10、状态分布 |
| 反思报告 | 历次 LLM 反思报告列表，含优化建议和候选规则 |

### 规则生命周期

```
draft（草稿）→ testing（测试）→ incubating（孵化）→ active（生效）
                            ↘ deprecated（停用）

跨单位规则变更：pending_confirmation（待确认）→ active
```

| 状态 | 含义 | 生效范围 |
|:---:|:---|:---|
| draft | 用户草稿，未验证 | 不生效 |
| testing | 沙箱测试中 | 仅测试用例 |
| incubating | 孵化区候选，待审批 | 不生效 |
| active | 正式生效 | 项目级/全局 |
| deprecated | 停用 | 不生效 |

### 反馈闭环

`templates/feedback-collector.html` 嵌入审核报告，收集两类反馈：

- **漏审反馈**：审核未发现但实际存在的问题 → 触发规则补全流程
- **误报反馈**：规则误判 → 触发规则优化或降级流程

反馈处理流程：反馈收集 → `feedback_analyzer.py` LLM 聚类分析 → 模式提取 → 候选规则生成 → 写入 `rules/custom/incubator/` → 管理员审批 → 提升为 active。

### LLM 自成长

| 组件 | 脚本 | 职责 |
|------|------|------|
| 反思调度器 | `rule_reflector.py` | 定时触发 LLM 生成优化建议报告，候选规则写入 incubator |
| 规则效力监控 | `rule_monitor.py` | 统计命中率/误报率，低质量规则自动降级（L1 豁免） |
| 反馈分析管道 | `feedback_analyzer.py` | LLM 聚类、模式提取、候选规则生成 |
| 审核记忆流 | `audit_memory.py` | JSONL 事件日志，记录审核过程供反思使用 |

### 跨单位对照

`templates/alignment-view.html` 提供监理-施工方数据对齐视图：

- 左右分栏对照监理方与施工方资料数据
- 自动标注偏差项（如混凝土量偏差>5%）
- 跨单位规则变更需协同确认（`pending_confirmation` → `active`）
- 支持管理员强制确认（`force_confirm`）

### 规则管理 API

`scripts/rule_admin.py` 提供 20+ REST API 端点：

| 类别 | 端点 |
|------|------|
| 规则管理 | GET/POST/PUT/DELETE `/api/rules`、`/api/rules/{id}/transition`、`/api/rules/{id}/confirm`、`/api/rules/{id}/force_confirm`、`/api/rules/{id}/stats`、`/api/rules/{id}/changelog`、`/api/rules/{id}/test` |
| 反馈管理 | GET/POST `/api/feedbacks`、`/api/feedbacks/{id}`、`/api/feedbacks/stats`、`/api/feedbacks/analyze` |
| 反思与自成长 | GET `/api/reflections`、`/api/reflections/{date}`、POST `/api/reflections/trigger`、GET `/api/incubator`、`/api/incubator/{id}`、POST `/api/incubator/{id}/promote`、`/api/incubator/{id}/reject` |

启动 API 服务：

```powershell
python {SKILL_DIR}/scripts/rule_admin.py --port 8765
```

打开管理面板：浏览器访问 `templates/rule-manager.html`。

> 规则文件存储在 **skill 目录** 的 `rules/` 下（跟着 skill 走，不跟着项目走），所有项目共用同一套规则。

### 编辑方式（推荐：离线版，无需启动服务）

**小白方式**：直接双击 `templates/rule-editor.html`，点击「选择 rules 文件夹」，在弹出的窗口中选择 skill 目录下的 `rules/` 文件夹。即可在浏览器中浏览、编辑、新建和删除规则。无需安装任何东西，无需启动 Python 服务。

**高级方式**：如果要用完整版管理面板（含生命周期管理、incubator 孵化器、反思报告、命中率统计等高级功能），需要先启动 API 服务再打开 `rule-manager.html`：
```powershell
python {SKILL_DIR}/scripts/rule_admin.py --port 8765
# 然后打开 templates/rule-manager.html
```

**硬核方式**：直接用文本编辑器修改 `rules/L1-iron/`、`rules/L2-logic/`、`rules/L3-business/` 下的 JSON 文件。

---

## 触发语句

### v6.0 四阶段流水线触发语句（默认走流水线）

- "建数据底座" / "建立项目数据底座" / "建底座"
- "审核这个项目的资料" / "审一下整个项目" / "审这批资料"
- "人工核对" / "打开数据编辑器" / "对一下 OCR 结果"
- "启动审核" / "正式审核" / "开始审核"
- "生成审核报告" / "出报告"
- "增量更新" / "补充资料" / "更新数据底座"
- "看一下项目总览" / "项目进度" / "审核进度"
- "并行审核" / "多 Agent 审核" / "拆分审核任务"
- "按分部审核" / "按分项审核" / "按专业审核"

### 规则管理子系统触发语句（v6.0 新增）

- "打开规则管理" / "管理规则" / "规则面板"
- "新建规则" / "创建规则" / "添加规则"
- "规则反馈" / "漏审反馈" / "误报反馈"
- "启动反思" / "触发反思" / "规则反思"
- "查看候选规则" / "孵化区" / "提升候选规则"
- "跨单位对齐" / "对齐视图"

---

## v6.0 流水线执行规则（AI 必须遵守）

> **关键规则**：v6.0 默认走四阶段流水线，**不要把单文件 9 步流程套到项目级审核上**。识别到"项目""这批""整个"等关键词时，自动进入流水线模式。

### 触发判断

| 用户输入特征 | 走哪条路径 |
|:---|:---|
| 提到"项目""这批""整个""建底座""人工核对" | **四阶段流水线** |
| 只提单份资料（如"这份施工日志""这个检验批"） | **v5.0 单文件审核模式**（9 步流程） |
| 模糊（如"审一下这些资料"） | 默认走**四阶段流水线**，并提示用户 |

> ⚠️ **v5.0 单文件模式已降级到附录区域。任何包含 2 份及以上资料的审核，禁止走 v5.0 单文件模式。**

### 阶段 1 执行规则（建数据底座）

1. **必须先收集 5 项前置信息**（铁律 v1.7+）：阶段、性质、审核范围、OCR 引擎、特殊说明
2. **必须先做文件分类确认**：列出所有文件，分为被审核资料/依据文件/排除文件，请用户确认
3. **前置信息和文件分类可合并为一次确认**（减少打断）
4. 用户确认后，执行 `run_audit.py build` 命令
5. **build 命令执行期间不要打断**：脚本会输出进度到 stderr，等待完成
6. **build 完成后，主动打开项目总览 HTML**：用 OpenPreview 工具展示 `项目总览.html`
7. **提示用户进入阶段 2**：明确告知"请在浏览器中打开 data-editor.html 完成人工核对，核对完成后告诉我"

### 阶段 2 执行规则（人工核对）

1. **AI 不参与编辑**：用户在浏览器中自行核对，AI 不读取数据、不修改 JSON
2. **零 token 消耗**：阶段 2 全程不消耗 AI 对话 token
3. **用户说"核对完成"后**：AI 必须先验证 `index.json` 中所有 `human_verified=true`，再进入阶段 3
4. **AI 不得在 `human_verified` 未全部为 `true` 时生成任何审核报告**。如果用户要求"先出报告看看""不用核对直接审""直接生成报告"，AI 必须明确拒绝并引导用户先完成人工核对
5. **如发现遗漏文件**：用户可补充文件后执行 `run_audit.py build --incremental`，增量更新不重复 OCR

### 阶段 3 执行规则（正式审核）

1. **前置检查**：执行 `run_audit.py review` 时脚本自动检查 `human_verified` 闸门
2. **闸门未通过**：脚本会拒绝执行，AI 不要绕过（除非用户明确说"--force"，仅测试用）
3. **多 Agent 并行**：资料量大（≥500 页或 ≥3 专业）时，主动建议用户走多 Agent 并行
4. **拆分粒度推荐**：
   - 默认 `--split-by sub`（48 个分部级）
   - 大型项目用 `--split-by item`（115 个分项级）
   - 小项目用 `--split-by professional`（5 个专业级）
5. **审核期间不修改数据**：审核是只读操作，只生成审核日志 JSON

### 阶段 4 执行规则（生成报告）

1. **强制套用 HTML 模板**：基于 `references/html-report-template.html` 生成，9 章节强制
2. **含 SVG 图表**：环形图（不符合项分布）+ 水平条形图（各专业问题数），零外部依赖
3. **报告生成后主动打开**：用 OpenPreview 工具展示 `审核报告.html`
4. **报告是终态产物**：如需更新，重新走阶段 3+4

### 阶段间切换规则

| 切换 | 触发条件 | AI 行为 |
|:---:|:---|:---|
| 阶段 1 → 阶段 2 | build 命令执行完成 | 提示用户打开 data-editor.html |
| 阶段 2 → 阶段 3 | 用户说"核对完成" | 验证 `human_verified` 后执行 review |
| 阶段 3 → 阶段 4 | review 命令执行完成 | 自动执行 report |
| 跨阶段回退 | 用户说"重新 OCR"或"补充资料" | 增量模式重新 build，不丢失已核对数据 |

---

## 脚本执行指南（AI 必须用命令行调用，不要 import）

> **关键规则**：审核过程中需要 OCR、PDF 提取、数据质量检测时，**必须用 RunCommand 执行以下命令**，不要尝试 import Python 模块或自己写代码实现。

| 场景 | 执行命令 | 说明 |
|------|---------|------|
| **【v6.0】建立数据底座** | `python {SKILL_DIR}/scripts/run_audit.py build "<项目文件夹>" --engine auto --preconditions "<前置.json>"` | 阶段 1：扫描分类 → OCR → JSON+MD → 质量检测 → 混淆检测 → 断档检测 → index.json |
| **【v6.0】增量更新数据底座** | `python {SKILL_DIR}/scripts/run_audit.py build "<项目文件夹>" --incremental` | 阶段 1 增量：基于 SHA256 哈希对比，仅处理新增/变更文件 |
| **【v6.0】生成审核任务包** | `python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹>" --split-by item --dry-run` | 阶段 3 准备：生成任务包，不执行审核 |
| **【v6.0】执行单个审核任务** | `python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹>" --task-id <id> --tasks-file "<任务包.json>"` | 阶段 3 多 Agent：子 Agent 执行单个任务 |
| **【v6.0】执行正式审核** | `python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹>" --split-by sub` | 阶段 3：规范对账 + 逻辑一致性检查 + 运算审核 |
| **【v6.0】生成审核报告** | `python {SKILL_DIR}/scripts/run_audit.py report "<项目文件夹>"` | 阶段 4：套用 HTML 模板，生成 SVG 图表，输出 审核报告.html |
| 识别资料类型 | `python {SKILL_DIR}/scripts/run_audit.py info "<文件路径>"` | 返回格式、页数、是否扫描件 |
| 提取 PDF 文字 | `python {SKILL_DIR}/scripts/extract_pdf.py "<文件路径>" --out "<输出.txt>"` | 电子档 PDF 用 PyMuPDF 提取 |
| OCR 扫描件（默认 auto：API 优先） | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --out "<输出.txt>"` | 默认 auto 模式：检测 API Key → Vision API；无 API → PaddleOCR；无 Paddle → Tesseract |
| OCR 扫描件（表格结构感知） | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --use-table --out "<输出.txt>"` | --use-table 已废弃，保留兼容性 |
| OCR 扫描件（Tesseract 备选） | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --engine tesseract --out "<输出.txt>"` | 显式启用 Tesseract 备选 |
| OCR 扫描件（增强预处理） | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --preprocess binarize --out "<输出.txt>"` | 自适应二值化，适合褪色/模糊手写件 |
| OCR 扫描件（视觉优先） | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --engine vision --out "<输出.txt>"` | AI 视觉模型直接识别（需 API Key） |
| OCR 复核指定页 | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --engine vision --page 5 --out "<输出.txt>"` | 用 AI 视觉复核第 5 页 |
| 一键审核（v5.0 单文件） | `python {SKILL_DIR}/scripts/run_audit.py audit "<文件路径>" --data "<结构化JSON>" --out "<输出目录>"` | OCR + 混淆检测 + Vision复核，一步完成（单文件，不走流水线） |
| Excel 提取 | `python {SKILL_DIR}/scripts/run_audit.py info "<文件路径>.xlsx"` | 自动识别为 Excel，build 阶段用 openpyxl 提取 |
| 批量识别目录 | `python {SKILL_DIR}/scripts/run_audit.py batch "<目录路径>"` | 遍历目录所有文件 |
| OCR 混淆检测 | `python {SKILL_DIR}/scripts/ocr_confusion_check.py "<JSON文件>" --pretty` | 检测 Z→2、4→0 等常见 OCR 误读，生成待核实清单 |
| 存疑字段自动复核 | `python {SKILL_DIR}/scripts/verify_fields.py auto "<原始文件>" "<混淆检测JSON>" --data "<数据JSON>" --out "<输出目录>"` | 默认路径 B：裁剪图片+输出任务清单，AI 智能体自动读图验证 |
| 合并复核结果 | `python {SKILL_DIR}/scripts/verify_fields.py merge "<verify_results.json>" --data "<数据JSON>" --out "<修正后JSON>"` | 将 AI 智能体验证结果合并回原始数据 |
| 数据质量检测 | `python {SKILL_DIR}/scripts/data_quality_check.py "<JSON文件>" --expected-pile-total 999` | 四类检测+致岩豁免+桩号总数校验 |
| 文本后处理 | `python {SKILL_DIR}/scripts/postprocess.py "<文本文件>"` | 全角转半角、PUA 替换 |

**`{SKILL_DIR}` 替换为本 Skill 的实际安装路径**（即 `SKILL.md` 所在目录）。

### 执行规则

1. **先识别再处理**：收到文件后，先跑 `run_audit.py info` 判断是否扫描件
2. **电子档**：`is_scanned: False` → 用 `extract_pdf.py` 提取文字
3. **扫描件**：`is_scanned: True` → 用 `ocr_image.py` 做 OCR
   - **默认 `auto` 模式（API-First）**：优先检测 Vision API Key → 使用 Vision API；无 API → 降级 PaddleOCR；无 Paddle → 降级 Tesseract
   - **显式 `--engine vision`**：AI 视觉模型对手写中文识别率约 95%（需 API Key）
   - **显式 `--engine paddle`**：本地 PaddleOCR，零成本，离线可用
   - **显式 `--engine tesseract`**：Tesseract 备选，无 API 且无 Paddle 时兜底
   - 可附加 `--preprocess enhance` 或 `--preprocess binarize` 提升手写体识别率
   - 可附加 `--json-out` 输出结构化结果（含每个字框的坐标和置信度）
4. **OCR 结果必须输出到文件**：用 `--out` 参数，方便后续读取
5. **读取 OCR 结果**：OCR 完成后用 Read 工具读取输出文件
6. **OCR 混淆检测**（扫描件必做）：将 OCR 提取的表格数据整理为 JSON，跑 `ocr_confusion_check.py`，生成待核实清单
7. **存疑字段自动复核**（扫描件且有存疑字段时执行）：
   - 执行：`python {SKILL_DIR}/scripts/verify_fields.py auto "<原始文件>" "<混淆检测JSON>" --data "<数据JSON>" --out "<输出目录>"`
   - 默认路径 B（智能体复核）：脚本自动裁剪存疑字段对应的原图区域，输出结构化任务清单
   - **AI 智能体自动读图验证**（无需用户参与）：
     - 读取 `agent_verify_tasks.json` 获取任务清单
     - 逐个读取 task 中的 `image_path` 图片（用 Read 工具读取图片文件）
     - 用自身 Vision 能力识别图片中的字段值，判断 OCR 结果是否正确
     - 输出 `verify_results.json`（格式：`{"results": [{"task_id": "VERIFY-001", "field": "pile_no", "row": 5, "verified_value": "Z370", "confidence": "high", "note": "..."}]}`）
   - 执行合并：`python {SKILL_DIR}/scripts/verify_fields.py merge "<verify_results.json>" --data "<数据JSON>" --out "<修正后JSON>"`
   - 无存疑字段时跳过此步骤
8. **数据质量检测**：跑 `data_quality_check.py`，如知道设计总桩数用 `--expected-pile-total` 参数

### 安装命令

用户说"安装""安装依赖""初始化"时，执行：
```powershell
powershell -ExecutionPolicy Bypass -File "{SKILL_DIR}/install.ps1"
```

---

## 知识库查询策略（Obsidian 优先，分层兜底）

> **核心原则**：审核必须全面、专业、有章可循。每个数据、每个判定都要能追溯到规范原文的具体条款。Obsidian 知识库是规范原文的第一来源，Skill 的 references 文件是固化知识的缓存层。

### 查询优先级（预加载 + 按需回源）

> **核心思路**：references 文件已经把 80% 以上的审核用的条款和参数阈值固化好了。审核时直接用 references 做高速比对，只在需要确认原文精确措辞或遇到 references 未覆盖的条款时才回源 Obsidian。这样一次审核的 Obsidian 调用控制在 3~5 次以内。

```
审核启动（一次性预加载，~3s）：
  ① 加载 references/ 专项审核文件（本地读取，瞬时）
  ② 加载 references/audit-checklists.md（本地读取，瞬时）
  ③ obsidian search 1 次，确认 Obsidian 中是否有该专业的补充规范
    ↓
逐项比对（纯推理，无 I/O）：
  直接用 references 中已固化的条款+参数阈值做比对
    ↓ 遇到 references 中未覆盖的条款
  按需回源：obsidian read 读取具体条款原文（1~2s/次）
    ↓ 上下文已满 或 Obsidian 无对应规范
  降级到 references 现有条款（标注"条款 X.X 待 Obsidian 原文验证"）
    ↓ 前两级均无覆盖
  标注"该条款无规范原文支撑，判定依据为工程惯例"（禁止 WebSearch 兜底）
```

### 执行规则（性能优先）

1. **预加载优先**（审核启动时，一次性完成）：
   - 按工程类别加载对应的专项审核文件（`references/xxx-audit.md`）
   - 专项文件中的条款和参数阈值直接作为审核依据，**不逐条回源 Obsidian**
   - 仅对专项文件中标注"待 Obsidian 原文验证"或条款号不够精确的项，做 1 次 `obsidian search` 批量确认
2. **逐项审核时不做 Obsidian 调用**：除非遇到以下三种情况才回源：
   - 被审资料中的数值在 references 阈值边界 ±10% 以内（需要原文精确确认）
   - 发现 references 中未覆盖的新资料类型
   - 用户明确要求"对照规范原文"
3. **上下文管理**：审核资料 ≥ 5 份时，Obsidian 调用上限为 5 次/审核任务，超出则全部使用 references 缓存层
4. **兜底机制**：Obsidian 无对应规范 + references 无覆盖 → 标注"该条款无规范原文支撑，判定依据为工程惯例"

### 单次审核预估耗时

| 步骤 | 耗时 | 说明 |
|------|------|------|
| 预加载 references | < 1s | 本地文件读取 |
| 预加载 Obsidian search | ~2s | 1 次搜索，确认补充规范 |
| OCR 提取（扫描件） | 10~60s | 最慢的环节，取决于页数 |
| 数据质量检测 | ~2s | Python 脚本 |
| 逐项规范比对 | 纯推理 | 无 I/O，数秒内完成 |
| 按需 Obsidian read | 1~2s/次 | 仅 3~5 次，总计 < 10s |
| 逻辑一致性检查 | 纯推理 | 无 I/O |
| 文档生成 | < 1s | 纯输出 |
| **总计（电子档）** | **< 15s** | 不含 OCR |
| **总计（扫描件）** | **15~75s** | 含 OCR，取决于页数 |

### 各专业规范在 Obsidian 中的覆盖情况

| 专业 | 资料管理规程 | 技术规范（Obsidian 中已确认存在） |
|------|------------|----------------------------------|
| 场道工程 | MH/T 5078.2-2024 | MH 5007-2017、MH 5004-2025、MH/T 5010-2025、MH/T 5005-2021 等 |
| 空管工程 | MH/T 5078.3-2024 | MH/T 4006.2-1998（VOR）、MH/T 4006.3-1998（DME） |
| 目视助航 | MH/T 5078.4-2024 | MH/T 6049-2020（电缆）、MH/T 6010-2017（调光器）、MH/T 6011-2015（标记牌）、MH/T 6008-2016（隔离变压器）、MH/T 6009-2016（插头插座） |
| 弱电系统 | MH/T 5078.5-2024 | MH/T 5103-2020（信息集成）、MH/T 7003-2017（安保） |
| 供油工程 | MH/T 5078.6-2024 | GB 50074-2014（石油库设计规范）、GB 50128-2014（立式圆筒形钢制焊接储罐施工规范）、GB 50341-2014（立式圆筒形钢制焊接油罐设计规范）、MH 5008-2017（供油工程设计规范）、MH 5034-2017（供油工程施工及验收规范） |

> **注意**：MH/T 5078.2~5078.6 资料管理规程原文均已纳入 Obsidian 知识库（2026-07-26 补充）。供油工程的石化国标（GB 50074/50128/50341）也于 2026-07-27 纳入 Obsidian。审核五大专业时，资料管理要求和技术规范均可直接回源 Obsidian 读规范原文。

---

## 知识分区红线（v1.9 新增）

> **设计意图**：AI 审核最容易踩的坑，是把"推理"和"事实"混在一起。明明规范里没写，AI 根据自己的常识推断出一个结论，然后当确定性结论写进报告——这就是"幻觉"。知识分区红线的作用是给 AI 的推理过程划一条硬边界——什么可以推理、什么必须查原文、推理不出来怎么办。

### 三条红线

| 红线 | 规则 | 违规后果 |
|:---:|:---|:---|
| **红线 1** | 规范条文编号（如"MH/T 5078.2 第 4.3.2 条"）必须来自 Obsidian 原文或 references 缓存，**禁止凭记忆编造** | 编造的条文编号会导致审核结论失去法律效力 |
| **红线 2** | 技术参数阈值（如"压实度 ≥ 96%"）必须来自规范原文，**禁止用"一般工程经验"替代** | 经验值可能不适用于民航专业工程的特殊要求 |
| **红线 3** | 推理推断出的结论（如"签字不全可能是过程资料"），**必须标注"推断"而非"判定"**，且必须提供可验证的验证路径 | 推断当判定，会把"可能"变成"确定"，误导整改方向 |

### 推理边界决策树

```
审核中遇到一个判断 → 查规范原文有明确条款？
  ├─ 有 → 直接引用规范编号+条款原文 → 结论标注"高置信度"
  ├─ 没有明确条款，但 references 缓存层有对应阈值？
  │   └─ 引用 references 来源，标注"中置信度，待 Obsidian 原文验证"
  ├─ 规范无明确条款，但工程逻辑可推导？
  │   ├─ 能推导出一个明确结论 → 标注"推断"，说明推理链
  │   └─ 推导不出来 → 标注"存疑"，不下结论，建议现场验证
  └─ 纯粹凭经验感觉？
      └─ 禁止写入报告 → 标记为"待查"，记录到审核日志
```

### 红线自检清单（每次输出前必查）

在审核报告生成前，对每条不符合项做以下检查：

- [ ] 本条结论引用的规范编号是否在 Obsidian 或 references 中确认存在？
- [ ] 本条引用的技术参数阈值是否有规范原文支撑？
- [ ] 本条结论是"判定"还是"推断"？如果是推断，是否已标注？
- [ ] 本条结论是否有可能被读者解读为"确定结论"但实际上只是推测？
- [ ] 如果本条结论被质疑，能否在 30 秒内找到原始出处？

> **核心原则**：宁可标注"存疑"、少下一个结论，也不要把推测当事实写进报告。审核报告的法律效力取决于每一条结论的可追溯性。

---

## 三级输出格式体系（v1.9 新增）

> **设计意图**：v1.8 之前用 P1/P2/P3 分级，但对实际整改的指导意义不够——收到报告的人不知道"P1"到底是有生命危险还是只是格式问题。三级输出格式直接对应整改动作，一看就懂。

### 三级分类

| 级别 | 标识 | 含义 | 典型场景 | 对应整改动作 |
|:---:|:---|:---|:---|:---|
| 🔴 **Fatal** | 致命 | 资料造假、数据矛盾无法解释、关键参数严重偏离设计 | 桩长与高程差对不上超过2m、签字全空白、施工记录缺合计行且来源不明 | 暂停归档，追溯原始底稿，必要时现场取芯 |
| 🟡 **Sanity Check** | 待核实 | 数据异常但可能合理解释、OCR 存疑、签字不完整但可能是过程资料 | 桩长突变 0.5~2m、手写日期 OCR 存疑、过程资料签字不全 | 人工核实后确认，补充说明或补齐签字 |
| 🔵 **Best Practice** | 建议 | 格式不规范、填写不完整但不影响数据可信度、归档整理建议 | 表格边框缺失、单位未标注、页码不连续、组卷分类建议 | 下次修改时补充，不阻塞当前归档 |

### 与旧版 P1/P2/P3 的对应关系

| 旧版 | 新版 | 变化说明 |
|:---|:---|:---|
| P1（严重不符合项） | 🔴 Fatal | 名称从"等级"变成"判断"，直接告诉整改人做什么 |
| P2（中等不符合项） | 🟡 Sanity Check | 从"不合格"变成"待核实"——不直接扣帽子，给施工方解释机会 |
| P3（轻微不符合项） | 🔵 Best Practice | 从"整改"变成"建议"——不阻塞归档，但也记录在案 |

### 使用规则

1. **一次审核中，Fatal ≥ 1 条 → 审核结论为"不予通过，暂停归档"**
2. **Sanity Check 项必须附带"人工核实路径"**（找谁核实、核实什么）
3. **Best Practice 项不阻塞归档通过，但必须在报告中列出**
4. **同一份资料中，不同项可以分属不同级别**
5. **审核报告的第七章（审核结论与整改要求）按三级分组展示，先列 Fatal、再列 Sanity Check、最后列 Best Practice**
6. **依据列必须写规范条文号+条文摘要**（如"MH/T 5078.2 第4.3.2条：施工记录应包含合计行"），**禁止写"铁律X"**——"铁律"是 Skill 内部规则编号，用户看不懂
7. **大问题不拆子项**——如果主问题已列（如"竖直度交替规律"），不再重复列其下属的小问题（如"0.2/0.3交替""0.1/0.2交替"），避免报告冗余

---


> **设计意图**：大项目可能有几万页资料，单 Agent 串行审核耗时太长。v1.9 仅支持按专业拆分（最多 6 个 Agent），v6.0 扩展为**专业/分部/分项三级粒度拆分**，与人工分部分项划分完全一致，最多可拆分 115 个独立任务。适用于资料量 ≥ 500 页或涉及 ≥ 3 个专业的场景。

### 触发条件

| 条件 | 阈值 | 自动触发 |
|:---|:---|:---|
| 资料总页数 | ≥ 500 页 | 是 |
| 涉及专业数 | ≥ 3 个专业 | 是 |
| 涉及分部分项数 | ≥ 10 个分部 | 建议走 `--split-by sub` |
| 涉及分部分项数 | ≥ 30 个分项 | 建议走 `--split-by item` |
| 用户明确要求 | "批量审核""并行审核""多agent""拆分审核" | 是 |
| 用户手动拆分 | 指定了分专业/分部分项审核范围 | 是 |

### 三级拆分粒度（v6.0 新增）

| 粒度 | `--split-by` 值 | 最大任务数 | 典型场景 | 任务开销 |
|:---:|:---:|:---:|:---|:---:|
| 专业级 | `professional` | 6 | 跨专业项目快速并行 | 低 |
| 分部级（默认） | `sub` | 48 | 常规项目，平衡并行度和任务开销 | 中 |
| 分项级 | `item` | 115 | 大型项目，最大化并行度 | 高 |

> **拆分依据**：`scripts/audit_config.py` 中的 `SUBDIVISION_HIERARCHY`，源自 `references/` 下 5 个规范文件，覆盖 5 大专业、48 分部、115 分项，每个分部分项都有唯一 code（如 `01-03` = 场道工程-特殊土处理）。

### 拆分策略

#### professional 级（5 大专业 + 通用）

```
审核资料 → 按专业分流（基于 index.json 的 professional 字段）
  ├─ 01_场道工程 → Agent A（加载 airfield-engineering-audit.md）
  ├─ 02_空管工程 → Agent B（加载 atc-engineering-audit.md）
  ├─ 03_助航设施 → Agent C（加载 visual-aids-audit.md）
  ├─ 04_弱电系统 → Agent D（加载 weak-electricity-audit.md）
  ├─ 05_供油工程 → Agent E（加载 fuel-supply-audit.md）
  └─ 通用资料 → Agent F（加载 audit-checklists.md）
```

#### sub 级（48 个分部，默认推荐）

```
审核资料 → 按 subdivision_code 分流
  ├─ 01-01 场道工程-土方工程 → Agent 01-01
  ├─ 01-02 场道工程-基层 → Agent 01-02
  ├─ 01-03 场道工程-特殊土处理 → Agent 01-03
  ├─ 02-01 空管工程-导航系统 → Agent 02-01
  ├─ ...（共 48 个分部）
  └─ 通用-施工日志 → Agent GEN-01
```

#### item 级（115 个分项，大型项目）

```
审核资料 → 按 subdivision_code + item_code 分流
  ├─ 01-03-01 场道工程-特殊土处理-碎石桩 → Agent 01-03-01
  ├─ 01-03-02 场道工程-特殊土处理-换填 → Agent 01-03-02
  ├─ ...（共 115 个分项）
  └─ 单个分项下资料数 ≤ 5 份时，自动合并到上级分部
```

### 执行流程（v6.0 集成到四阶段流水线）

```
阶段 1 build（主 Agent 完成）
  └─ 扫描分类 → OCR → index.json（含 subdivision_code）
      ↓
阶段 2 人工核对（用户完成）
  └─ data-editor.html → corrected_data.json → human_verified=true
      ↓
阶段 3 review（主 Agent + N 个子 Agent 并行）
  ├─ 主 Agent：run_audit.py review --split-by item --dry-run
  │   └─ 生成 audit_tasks.json（含 N 个任务包）
  ├─ 子 Agent 1：run_audit.py review --task-id AU-...-001 --tasks-file audit_tasks.json
  ├─ 子 Agent 2：run_audit.py review --task-id AU-...-002 --tasks-file audit_tasks.json
  ├─ ...（N 个子 Agent 同时执行，每个独立进程）
  └─ 主 Agent：run_audit.py review（汇总所有子任务结果 + 跨任务逻辑一致性检查）
      ↓
阶段 4 report（主 Agent 完成）
  └─ run_audit.py report → 审核报告.html
```

### 子 Agent 任务包格式（v6.0）

`audit_tasks.json` 中每个任务包包含以下字段：

```json
{
  "task_id": "AU-20260730-001-001",
  "professional": "01_场道工程",
  "subdivision_code": "01-03",
  "sub_label": "场道工程 → 特殊土处理",
  "item_label": "碎石桩",
  "split_by": "item",
  "doc_count": 3,
  "documents": [
    {
      "id": "DOC-001",
      "original_file": "碎石桩施工记录.pdf",
      "doc_type": "碎石桩施工记录",
      "data_file": "01_场道工程/施工记录/碎石桩施工记录.json",
      "corrected_file": "01_场道工程/施工记录/碎石桩施工记录_corrected.json",
      "human_verified": true
    }
  ],
  "checklist_source": "airfield-engineering-audit.md",
  "preconditions": {
    "stage": "分部分项验收",
    "nature": "扫描件",
    "scope": "全量审核",
    "special_notes": ""
  }
}
```

### 汇总规则（v6.0）

1. **同类项合并**：各子 Agent 输出的不符合项按三级分类（🔴Fatal/🟡Sanity Check/🔵Best Practice）汇总
2. **跨任务逻辑一致性检查**：主 Agent 在汇总阶段执行 10 子项逻辑检查，覆盖跨分部分项的交叉验证（如场道与助航的电缆预埋、供油与弱电的管线交叉）
3. **置信度统一标注**：各子 Agent 的置信度标注按统一标准复核
4. **断档整合**：阶段 1 检测到的 `gaps[]` 与阶段 3 各子 Agent 的 findings 合并，避免重复告警
5. **汇总报告**：一份总报告，按专业/分部分项分章节，末尾附跨专业综合结论

### 性能预估

| 资料规模 | 拆分粒度 | 任务数 | 串行耗时 | 并行耗时 | 加速比 |
|:---|:---:|:---:|:---|:---|:---:|
| 500 页 / 2 专业 | professional | 3 | ~10 min | ~6 min | 1.7x |
| 2000 页 / 3 专业 | sub | 12 | ~40 min | ~8 min | 5.0x |
| 10000 页 / 5 专业 | item | 48 | ~3 h | ~25 min | 7.2x |
| 50000 页 / 5 专业 | item | 115 | ~15 h | ~90 min | 10.0x |

> **注意**：v6.0 流水线下，OCR 在阶段 1 已统一完成，阶段 3 多 Agent 并行主要加速规范比对和逻辑一致性检查，加速比比 v1.9 显著提升（OCR 不再是并行瓶颈）。

### 多 Agent 调度示例

**场景**：某机场扩建项目，5 专业全覆盖，2000 页资料，48 个分部分项。

```powershell
# 步骤 1：阶段 1 建数据底座（主 Agent，串行）
python {SKILL_DIR}/scripts/run_audit.py build "D:\机场扩建项目" --engine auto

# 步骤 2：阶段 2 人工核对（用户在浏览器中完成，AI 不参与）

# 步骤 3：阶段 3 生成任务包（主 Agent）
python {SKILL_DIR}/scripts/run_audit.py review "D:\机场扩建项目" --split-by sub --dry-run
# 产物：D:\机场扩建项目\数据底座\审核日志\audit_tasks.json（12 个任务）

# 步骤 4：并行执行 12 个子 Agent（每个独立进程，可分布到多台机器）
for $i in 1..12 {
    python {SKILL_DIR}/scripts/run_audit.py review "D:\机场扩建项目" `
        --task-id "AU-20260730-001-$($i.ToString('000'))" `
        --tasks-file "D:\机场扩建项目\数据底座\审核日志\audit_tasks.json"
}

# 步骤 5：主 Agent 汇总（执行无 task-id 的 review）
python {SKILL_DIR}/scripts/run_audit.py review "D:\机场扩建项目"

# 步骤 6：阶段 4 生成报告
python {SKILL_DIR}/scripts/run_audit.py report "D:\机场扩建项目"
```

---

## 项目审核范围清单（v1.9 新增）

> **设计意图**：民航专业工程一个大项目里面可能有若干小项目、多个分部分项，资料多且杂。审核前先生成一份"审核范围清单"，把每个分部分项的审核状态可视化，避免遗漏。模板文件：`templates/audit-scope-template.html`。

### 触发时机

1. 用户提供的资料涉及 ≥ 3 个分部分项时，自动生成
2. 用户说"看一下项目范围""有哪些分部分项"时，立即生成
3. 多Agent并行审核时，作为 Step 0 的标准输出

### 清单内容

| 字段 | 说明 |
|:---|:---|
| 分部工程 | 如"场道工程-土方""空管工程-VOR台" |
| 分项工程 | 如"碎石桩""换填""混凝土浇筑" |
| 资料类型 | 施工记录 / 检验批 / 隐蔽 / 检测报告 / 施工日志 / 竣工图 |
| 资料份数 | 该分项下的资料数量 |
| 审核状态 | 待审核 / 审核中 / 已通过 / 有条件通过 / 不予通过 |
| 不符合项数 | 🔴Fatal / 🟡Sanity Check / 🔵Best Practice 各多少 |
| 审核日期 | 最近一次审核时间 |

### 使用方式

1. Agent 读取 `templates/audit-scope-template.html`，替换 `{{占位符}}` 为实际项目信息
2. 根据 Step 1 的专业分流结果，自动填充各分部分项
3. 生成后保存为 `audit_output/项目审核范围清单.html`
4. 每次审核完成后自动更新对应行的审核状态
5. 用户随时打开该 HTML 文件，能看到整个项目的审核进度

---

## 规则三层分级体系（v6.0 新增）

> v6.0 前，20 条铁律以扁平编号（R-01~R-20）形式散落在文档叙述中，层级边界模糊（如原 R-12 高程自洽实为 L2 逻辑一致性，却被列为"铁律"）。v6.0 将全部规则重构为三层分级 + 跨单位特殊作用域，共 91 条规则迁移至 `rules/` 目录以结构化 JSON 存储。

| 层级 | 代号 | 判定标准 | 违反后果 | 不可降级 | 典型规则 |
|:---:|:---:|:---|:---|:---:|:---|
| L1 铁律 | L1-IRON | 不可商榷的合规底线 | 🔴 Fatal，直接判不合格 | 是 | R-01 规范可追溯、R-06 拒为伪证背书、R-07 审核留痕 |
| L2 逻辑一致性 | L2-LOGIC | 数学/几何/时序/引用自洽 | 🟡 Sanity Check，须人工复核 | 否 | 实长=桩顶高程-桩底高程（原 R-12，已修正层级错位）、合计值反向验证（原 R-17） |
| L3 业务合理性 | L3-BUSINESS | 阈值/经验/行业惯例 | 🔵 Best Practice，提示性警告 | 否 | 突变率≥30% 警告、签字完整性阈值 |
| 跨单位对照 | SCOPE-CROSS_UNIT | 监理-施工方跨单位对照 | 按 L1/L2/L3 分级 | 视内容 | 混凝土量偏差>5%、监理-施工方日期对照（原 9.10） |

**层级说明**：

- **L1 铁律（17 条）**：合规底线，不可商榷，违反即判 Fatal，不可降级。规则效力监控（`rule_monitor.py`）对 L1 规则豁免自动降级
- **L2 逻辑一致性（71 条）**：数学、几何、时序、引用关系的自洽性检查。违反标记为 Sanity Check，须人工复核。原铁律 12（高程自洽）曾存在层级错位，v6.0 已修正归入此层；原铁律 13（缺合计行判定）、14（多参数联检）也属 L2 几何/数学自洽范畴，已一并迁入
- **L3 业务合理性（3 条）**：基于阈值、经验、行业惯例的合理性判断。违反为提示性警告，不阻塞归档
- **跨单位对照（18 条，SCOPE-CROSS_UNIT）**：监理-施工方跨单位规则的特殊作用域，需双方协同确认，按 L1/L2/L3 分级

> 91 条规则的形式化存储、生命周期管理、反馈闭环、LLM 自成长机制详见前文「规则管理子系统」章节。以下保留 20 条核心铁律的详述，作为 L1 铁律的历史沉淀和执行细则参考。

## 核心铁律（20 条，精华）

### 铁律 1：规范来源必须可追溯
每条审核意见必须引用具体规范编号和条款号。严禁凭感觉判断。所有规范通过 Obsidian 知识库实时查询。

### 铁律 2：OCR 结果必须人工复核
扫描件 OCR 识别结果仅辅助参考。涉及数据、参数、签章的必须提示人工复核。

### 铁律 3：运算审核只做规范性检查
不做数值复算，只检查：计算方法、参数取值、安全系数、边界条件、计算简图。

### 铁律 4：审核结论必须有据可依
每条不符合项必须含：问题描述 + 违反条款 + 整改建议。禁止"可能不合规""建议确认"等模糊表述。

### 铁律 5：资料标准是"移交归档"
按 MH/T 5078.1-2024，资料不是收集齐全就行，必须达到分类组卷编目、可移交归档的标准。

### 铁律 6：拒绝为伪造资料背书
发现资料有伪造嫌疑（时间倒签、代签字、数据雷同），必须明确指出，不得回避或淡化。

### 铁律 7：审核过程留痕
每次审核生成可追溯的日志：审核时间、依据规范版本、OCR 置信度、人工复核标记、审核结论、审核人。

### 铁律 8：未发现问题 ≠ 全部合格
"未发现不符合项"必须明确写出来，不得简化为"全部合格"。沉默式放行等于失职。

### 铁律 9：逻辑一致性专项检查（重头戏 - 精华）

**9 个子项检查**（详见 `references/logic-conflict-patterns.md`）：
- 9.1 时间轴一致性
- 9.2 数量累计一致性
- 9.3 人员交叉一致性
- 9.4 状态描述一致性
- 9.5 签字一致性
- 9.6 因果逻辑一致性
- 9.7 规范引用一致性
- 9.8 试验检测逻辑一致性
- 9.9 跨资料合计值反向验证

**9.10 监理-施工方跨单位日期对照（主流检查方式，自动触发）**：

当审核资料中包含监理方资料（监理日志、旁站记录、巡视记录、监理通知单/回复单、工程暂停令/复工令、各类报审表 B.10/B.16/B.21/B.22/B.23/B.26/B.27/B.28、见证记录、平行检测报告、会议纪要）时，**自动启动 9.10 全部 17 条规则**，逐条核对监理方与施工方资料的日期逻辑关系。这是当前民航施工资料审核的主流方式——监理资料是施工资料的独立见证方，两边日期对不上，要么流程倒签、要么资料造假。

**铁律进化机制**：审核过程中如发现高频错误类型/用户反馈/新规范发布，必须主动提醒用户增补铁律。

### 铁律 10：数据质量先于规范合规（前置硬门槛）

在规范对账之前，必须先对 OCR 提取的表格数据做 4 类数据质量检测（详见 `references/data-quality-patterns.md`）：

- **DQ-REPEAT**：重复值模式 — 仅 2 个值交替出现 = 数据造假嫌疑
- **DQ-JUMP**：突变检测 — 桩长/灌入量等关键参数断崖式下跌 ≥30% = 需说明原因
- **DQ-ALTER**：涂改痕迹 — 充盈系数自洽失败、桩长≠高程差 = 数据被修改
- **DQ-SELF**：数据自洽 — 行数、桩号连续性、工程计算自洽校验

**判定逻辑**：
- 有 error → 数据不可靠，停止后续审核，要求重新提取
- 有 high → 数据造假嫌疑，在审核报告中重点标注，建议现场验证
- 已被交替模式标记的列，不再重复报告突变（避免冗余告警）

**脚本**：`scripts/data_quality_check.py`

### 铁律 11：表格数据必须全列提取（关键教训）

**问题来源**：DOC-B 碎石桩施工记录审核时，AI 初始只提取了"实长"列，没读"桩底高程"和"桩顶高程"列，导致 Z418 实长 9.0m 与高程差 13.19m 的矛盾未被发现。

**执行规则**：
1. 提取表格时必须**逐列读取表头**，确认所有列都被覆盖
2. 不能只读"结果列"（如实长、充盈系数），必须同时读"计算列"（桩底高程、桩顶高程、灌入量）
3. 读完后对每一对"可推导关系"的列做自洽校验（见铁律 12）
4. 自洽校验通过前，不得进入跨资料对比

**典型场景**：施工记录表、检验批表、检测报告等含数值计算的表格，必须全列读取。

### 铁律 12：桩长与高程差交叉校验（单表内部逻辑）

**问题来源**：DOC-B 的 Z418 桩，实长写 9.0m，但桩底高程 2090.53 - 桩顶高程 2103.72 = 13.19m，差额 4.19m。实长被人改过但桩底高程没同步改，说明单表内部交叉校验是检测造假的第一道防线。

**执行规则**：
1. 任何含高程列的表格，**必须**做"实长 = 桩顶高程 − 桩底高程"校验
2. 允许误差 ±0.1m（读数取整误差）
3. 超过误差的，标记为 DQ-ALTER（涂改/数据异常），在审核报告中重点标注
4. 桩长与高程差交叉校验是**所有交叉校验中最基础的一项**，优先级最高

**判定逻辑**：
| 误差 | 判定 | 严重度 |
|------|------|--------|
| ≤ 0.1m | 通过 | — |
| 0.1~0.5m | 微小偏差，可能读数取整误差 | 警告 |
| 0.5~2m | 可能数据被修改 | 中 |
| > 2m | 数据被修改，需追溯原始记录 | 高 |

### 铁律 13：缺合计行 = 资料非原始记录

**问题来源**：DOC-B 6 页碎石桩施工记录全部没有底部合计行（小计桩数、小计米数），但施工日志中却有合计值 489.9m/33根。说明 DOC-B 是事后誊抄件而非现场原始记录。

**执行规则**：
1. 逐页检查表格底部是否有合计行（小计/总计/Σ）
2. 所有页都缺合计行 → 高度怀疑该资料不是原始记录，是誊抄件
3. 如果施工日志有合计值但施工记录无合计行 → 形成"合计值来源不明"的审计线索
4. 在审核报告中标注"缺合计行，无法确认该资料是现场原始记录"
5. 缺合计行 + 其他数据异常（桩号不连续、签字空白等）→ 触发铁律 6（拒绝为伪造背书）

### 铁律 14：多参数工程逻辑链联检

**问题来源**：造假者通常只改一个参数（如实长），但会漏掉关联参数（如桩底高程、灌入量、充盈系数）。桩长、灌入量、充盈系数三者之间存在确定的工程计算关系，同时校验才能发现造假。

**执行规则**：
1. 对每行数据，同时校验以下工程逻辑链（以碎石桩为例）：
   - `实长 = 桩顶高程 − 桩底高程`（铁律 12）
   - `充盈系数 = 灌入量 / (π × (桩径/2)² × 实长)`
   - `灌入量 ≈ 理论体积 × 充盈系数`（反向验证）
2. 三条链中任意一条不通过 → 标记 DQ-ALTER
3. 三条链中两条及以上不通过 → 数据造假嫌疑，建议现场取芯验证
4. 修改后的数据与原数据的偏差方向 → 推断修改意图（如改大实长/改小灌入量）

**适用范围**：所有含工程参数计算关系的表格。

### 铁律 15：原始底稿追溯（多资料矛盾时的处理原则）

**问题来源**：Z418 在 DOC-A 中实长 13.2m，DOC-B 中实长 9.0m，两份资料数据矛盾。不能简单判断哪份更像真的，必须调取原始底稿或现场取芯验证。

**执行规则**：
1. 同一桩号/同一条目在多份资料中数据矛盾 → 不盲目采信任何一份
2. 优先追溯**原始记录**（现场手写底稿、监理旁站记录、原始测量记录）
3. 原始记录不可获取时 → 按"三个一致"原则判断：
   - 与工程逻辑一致（铁律 12、14 的自洽结果）
   - 与时间顺序一致（早的记录更接近真实）
   - 与多资料交叉验证一致（多数资料支持的值更可信）
4. 争议数据做**标注**，不在审核报告中下"确定"结论，改为"数据存疑，建议现场验证"
5. 涉及争议数据的后续整改，必须包含原始底稿调取或现场取芯方案

### 铁律 16：提取-验证-重试循环（提取完整性保障）

**问题来源**：初始审核时，AI 只提取了 5 行数据（漏 Z415），且只读了"实长"列未读"桩底高程"和"桩顶高程"列。用户发现行数不对后，通过 AI 视觉重新提取才补全。说明"提取一次通过"不可靠，必须建立提取-验证-重试的闭环。

**执行规则**：
1. 提取完成后，必须先做**行数校验**：预期行数 vs 实际提取行数
2. 行数校验不通过 → 自动触发 AI 视觉重新提取（换读取方式，不修改 OCR 参数）
3. 重试仍失败 → 标记为"提取不完整，数据不可靠"，停止后续审核
4. 行数校验通过后，再做**桩号连续性校验**：不能跳号（如 Z420→Z418 缺 Z419）
5. 所有提取操作必须记录版本号（提取方式、时间、置信度），方便追溯

**典型场景**：扫描件 PDF 表格提取、多页施工记录表提取、手写体施工记录提取。

### 铁律 17：跨资料合计值反向验证

**问题来源**：DOC-C 施工日志精确记录"33根，489.9m"，但 DOC-B 6页全部缺合计行。合计值来源不是施工记录本身，导致"合计值来源不明"的审计线索。如果只看施工日志，合计值有模有样；但回头看施工记录，发现原始记录根本没有合计行。

**执行规则**：
1. 当施工日志/汇总表有合计值时，必须与施工记录的实际数据逐项核对
2. 核对方法：逐页计算施工记录的实际合计（桩数、米数、灌入量等），与施工日志的合计值对比
3. 对比结果分类：
   - 一致 → 合计值可信
   - 不一致 → 标记为"合计值存疑"，记录差异值
   - 施工记录无合计行 → 标记为"合计值来源不明"
4. 合计值来源不明的资料，在审核结论中不下"数据合格"结论
5. 当缺合计行 + 有合计值同时出现时，形成最高优先级审计线索

**适用范围**：所有涉及数量汇总的资料对（施工记录 vs 施工日志、检验批 vs 分项汇总、检测报告 vs 汇总表）。

### 铁律 18：审核结论置信度分级与表述规范

**问题来源**：Z418 在 DOC-A 中实长 13.2m，DOC-B 中实长 9.0m，两份资料数据矛盾。直接下结论说"资料不合格"或"数据正确"都不严谨——你没法确定哪份资料是真的。必须标注置信度，让读者知道结论的可信度。

**执行规则**：
1. 所有审核结论必须标注置信度，分四级：

   | 置信度 | 判定条件 | 审核结论表述 |
   |--------|---------|-------------|
   | 高 | 有原始记录支撑，多份资料一致 | "确定" |
   | 中 | 有原始记录，但仅单份资料 | "基本确定" |
   | 低 | 无原始记录，仅誊抄件 | "初步判断" |
   | 存疑 | 多份资料数据矛盾 / 数据自洽失败 | "数据存疑，建议现场验证" |

2. 存疑数据不下确定性结论，必须标注"建议现场验证"
3. 审核报告中每个不符合项都必须标注置信度
4. 置信度低的项，整改建议必须包含"追溯原始记录"或"现场验证"要求
5. 同一资料中，不同项的置信度可以不同（如实长存疑、充盈系数高）

**应用时机**：第 8 步文档生成时，对所有不符合项逐项标注置信度。

### 铁律 19：用户标记问题的闭环追溯（人机协同持续改进）

**问题来源**：用户人工标记了竖直度交替、充盈系数涂改、桩长突变等问题，但 AI 需要被追问才知道。用户问了好几次"为什么一开始没发现"——根因是 AI 提取表格时不够主动，且缺乏"提取-验证-再提取"的循环。每次用户发现 AI 遗漏的问题，都应该成为技能改进的契机。

**执行规则**：
1. 用户标记/指出的问题，处理优先级最高（高于常规审核流程）
2. 用户标记的问题必须追溯 AI 为什么没发现，按四类原因归类：

   | 原因分类 | 典型表现 | 改进动作 |
   |---------|---------|---------|
   | 提取不完整 | 只读了部分列/行 | 补充铁律 16（提取-验证-重试） |
   | 缺乏检测规则 | 有异常但无对应规则 | 补充到 data-quality-patterns.md |
   | 规则覆盖不全 | 规则存在但未覆盖该场景 | 补充到 logic-conflict-patterns.md |
   | 知识库缺失 | 知识库无该错误模式 | 补充到 high-frequency-errors.md |

3. 追溯结果必须记录到审核日志的"改进建议"字段
4. 每次审核完成后，做一次**自检**：是否有明显异常但未被主动识别
5. 用户标记问题 → 补充规则 → 下次审核自动覆盖，形成闭环

**铁律进化机制**：铁律 19 是"元铁律"——它不直接审核资料，而是确保铁律体系本身持续进化。每次审核都是铁律体系的训练数据。

### 铁律 20：OCR 存疑项人工核实机制（v1.7 新增）

**问题来源**：本次审核中，AI 视觉模型对 49 页扫描件中的手写施工日期反复判读为 2016/2018/2020/2021，但用户人工确认全部是 2026 年——手写潦草导致 AI 系统性地误读年份。如果审核报告直接采用 AI 的误读结果，会产生"扫描件跨 20 年混装"的严重误判。

**执行规则**：
1. OCR/AI 视觉识别完成后，对每个识别结果标注置信度（高/中/低/存疑），标注规则：
   - 打印体文字：默认高置信度
   - 手写体数字/日期：默认中置信度
   - 手写体潦草/涂改/模糊：默认低置信度
   - 识别结果与预期不符（如年份与项目时间线矛盾）：标记为存疑
2. 将所有低置信度和存疑项汇总为 **"OCR 待核实清单"**（HTML 报告第八章），逐项列出：
   - 页码/位置、识别结果、置信度、存疑原因
   - 提供"预期值"列（根据项目时间线推算），供人工对照
3. 人工核实有两种模式：
   - **即时核实**：审核过程中，遇到存疑项立即弹出，用户逐项确认后继续
   - **批量核实**：审核完成后，用户在"OCR 待核实清单"中统一确认，AI 根据确认结果修正报告
4. **默认采用批量核实模式**，除非用户明确要求即时核实
5. 人工核实前，所有低置信度/存疑项在审核结论中**不下确定性结论**，统一标注为"OCR 识别存疑，待人工核实"
6. 人工核实后的数据视为可信数据，更新到审核报告和中间产物中

**典型场景**：
- 手写"2026"被 AI 读成"2018"→ 标记为存疑（项目时间线为 2025-2026，2018 与项目时间线矛盾）
- 手写"4.20"被 AI 读成"4.28"→ 标记为低置信度（手写潦草）
- 打印体"MH/T 5078.1-2024"→ 高置信度，不需核实

**与铁律 2 的关系**：铁律 2 要求"OCR 结果必须人工复核"，铁律 20 是将铁律 2 具体化——明确了哪些需要复核、怎么复核、复核后怎么处理。铁律 20 是铁律 2 的执行细则。

---

## 对话总结：铁律体系的演进脉络

> 以下总结记录了 v1.0 → v1.4 的演进过程中，**每轮对话如何推动铁律体系的完善**。这份总结本身就是铁律 19（用户标记闭环）的实践案例。

### 第 1 轮：基础框架搭建（v1.0→v1.1）

**用户需求**：审核一份碎石桩施工记录扫描件，判断是否合规。
**发现的问题**：6 根桩实长（8.5~13.7m）全部远小于设计桩长 20m，无持力层确认记录、无变更、无签证。
**能力缺口**：OCR 对表格数据提取效果差，只识别了 5 行（漏 1 行），且只读了结果列。
**推动的铁律**：铁律 2（OCR 必须复核）→ 强化为"行数校验 + 桩号锚定"；铁律 11（全列提取）→ 初步提出。

### 第 2 轮：数据质量审查机制（v1.1→v1.2）

**用户提问**：*"我才扫描一张你就这样，如果扫描多了会不会出现什么问题？"*
**用户反馈**：在扫描件上人工标记了竖直度交替、充盈系数涂改、桩长突变等 5 类问题。
**能力缺口**：缺乏数据造假检测机制，只做规范对账会漏掉数据层问题。
**推动的铁律**：铁律 10（数据质量前置）+ 4 类检测规则（DQ-REPEAT/JUMP/ALTER/SELF）。

### 第 3 轮：跨资料逻辑一致性检查（v1.2→v1.3）

**用户需求**：*"用两份资料（施工记录 + 施工日志）完整走一遍 skill。"*
**发现的问题**：
1. Z418 同一桩号两份资料实长差 4.19m（13.2m vs 9.0m）
2. DOC-B 6 页全部缺合计行，但施工日志有精确合计值
3. 高程自洽失败：实长 9.0m ≠ 高程差 13.19m
**推动的铁律**：铁律 12（高程自洽）、铁律 13（缺合计行判定）、铁律 14（多参数联检）、铁律 15（原始底稿追溯）。

### 第 4 轮：提取完整性 + 置信度 + 持续改进（v1.3→v1.4）

**用户追问**：*"为什么一开始你的分析没有发现这个点？"*、*"合计米数呢？"*
**能力缺口**：
1. 提取时不够主动——只读了结果列，没读计算列
2. 跨资料合计值没有自动验证
3. 数据矛盾时审核结论不够严谨
4. 用户标记的问题没有追溯机制
**推动的铁律**：铁律 16（提取-验证-重试）、铁律 17（合计值反向验证）、铁律 18（置信度分级）、铁律 19（用户标记闭环）。

### 演进总结

| 版本 | 铁律范围 | 核心能力 | 驱动来源 |
|------|---------|---------|---------|
| v1.0 | 1~9 | 规范对账 + 逻辑一致性 | 初始设计 |
| v1.1 | +10 | 数据质量四类检测 | 用户担心扫描件问题 |
| v1.2 | +11~15 | 高程自洽/缺合计行/多参数联检/原始追溯 | 跨资料对比发现 Z418 矛盾 |
| **v1.4** | **+16~19** | **提取-重试/合计值验证/置信度分级/用户标记闭环** | **用户追问"为什么没发现"** |
| **v1.7** | **+0步/+20** | **前置信息收集/OCR存疑人工核实/统一HTML交付物/输出完整性自检** | **用户反馈 OCR 年份误读 + 过程资料误判 + 输出不完整** |

**核心启示**：每次用户指出 AI 遗漏的问题，都是铁律体系升级的契机。铁律 19 将这个过程正式化——用户标记问题 → 追溯根因 → 补充规则 → 下次审核自动覆盖。

### v1.7 升级详情（2026-07-25）

**触发问题**：
1. 用户人工确认资料全部为 2026 年，但 AI 视觉模型将手写"26"系统性误读为 2016/2018/2020/2021
2. 资料为分部分项验收过程资料，签字不完整属正常，但 AI 按归档标准判为严重不符合项
3. 实际只生成了 HTML 报告，SKILL 要求的审核日志 JSON、中间产物等未生成

**升级内容**：
- **新增第 0 步**：审核前收集 5 项前置信息（阶段/性质/依据/范围/特殊说明），动态调整判定标准
- **新增铁律 20**：OCR 存疑项人工核实机制——低置信度项不下确定性结论，汇总为"待核实清单"
- **第 8 步重构**：统一交付物改为 HTML（三合一），补全必存独立文件和中间产物清单，新增输出完整性自检清单
- **铁律从 19 条增至 20 条**

---

---

## 附录：旧版兼容模式（v5.0 单文件审核）

> ⚠️ **警告：本模式仅限单份资料快速预览使用。任何包含 2 份及以上资料的审核，禁止走本流程，必须走 v6.0 四阶段流水线。**

> ⚠️ **警告：v5.0 单文件模式不支持人工核对闸门，仅用于临时查看单份资料。项目级审核若使用本流程，审核结果不可作为正式依据。**


> v1.8 将原有线性 9 步重组为三个层次，每层有明确的关卡。步骤内容不变，组织结构更清晰，Agent 执行时不易漏步骤。

```
┌─────────────────────────────────────────────────────────────┐
│ 第一层：信息收集（搞清楚"审什么、用什么审"）                  │
│                                                             │
│  Step 0 前置信息收集 ──→ Step 1 格式识别+专业分流            │
│  Step 2 OCR提取+完整性校验                                   │
│  Step 4 规范匹配+审核项建立（加载references+Obsidian）        │
│                                                             │
│  关卡：资料分类已确认、审核范围已明确、规范依据已加载         │
├─────────────────────────────────────────────────────────────┤
│ 第二层：实质审核（逐项对账，发现问题）                        │
│                                                             │
│  Step 3 数据质量审查（前置硬门槛）                            │
│  Step 5 逐项规范比对                                         │
│  Step 6 逻辑一致性专项检查（跨资料交叉验证）                  │
│  Step 7 运算规范审核（按需触发）                              │
│                                                             │
│  关卡：数据质量不过关不能进入规范比对                         │
├─────────────────────────────────────────────────────────────┤
│ 第三层：结果输出（汇总、分级、生成报告）                      │
│                                                             │
│  Step 8 文档生成 ──→ 置信度标注 ──→ OCR存疑汇总             │
│  ──→ 输出前自检 ──→ 套用标准模板生成HTML报告 + 中间产物      │
│                                                             │
│  关卡：自检清单全部打勾才能交付；报告格式强制套用标准模板      │
└─────────────────────────────────────────────────────────────┘
```

---

### 第 0 步：审核前置信息收集（一次性确认）

> **设计意图**：审核前必须了解资料的背景上下文，避免因信息不对称导致误判。文件分类和上下文信息合并为一次确认，减少打断用户的次数。全流程仅两次人工确认：本步骤（开始时）+ OCR后（扫描件核对）。

**硬性执行规则**：
- 第 0 步（本次确认）后，才开始走第 1~6 步
- 第 6 步 OCR 完成后，**必须停下**，输出"OCR 校对确认表"，等用户确认或修正
- 用户未确认前，**禁止进入第 7 步（数据质量检测）和第 8 步（报告生成）**
- 这条规则不因对话上下文已加载而豁免——即使 AI 觉得自己"知道"OCR 结果是对的，也必须让用户确认一遍

**输入**：用户触发审核请求
**处理**：审核启动时，一次性完成文件分类和前置信息收集。

#### 文件分类 + 前置信息（合并确认）

**执行方式**：列出用户提供的所有文件，逐项标注分类，同时收集前置信息，请用户一次性确认：

```
📂 发现以下文件，请确认分类：

【被审核资料】— 以下文件将逐页审核合规性：
  ✅ 2026年4月 施工日志.xlsx — 施工日志
  ✅ 扫描件.pdf — 碎石桩施工记录（49页）

【依据文件】— 以下文件作为审核依据，不逐页审核：
  📎 设计变更通知单（施工图审查后）-签名20251223.pdf — 设计变更
  📎 场基施II-02~04变更图纸（3份） — 变更图纸
  📎 总施-01~04变更土方图纸（4份） — 土方图纸

【排除文件】— 以下文件不参与审核：
  ❌ 未命名1.pdf — 测试文档

是否确认？(确认/调整)
```

**规则**：
1. 所有文件必须明确分类，不能有"未分类"状态
2. 用户说"确认"则进入审核执行，说"调整"则重新分类
3. 分类结果写入审核日志

#### 前置信息（与文件分类同时收集）

| 序号 | 问题 | 选项/示例 | 用途 |
|:---:|:---|:---|:---|
| 1 | **资料所处阶段** | 施工过程 / 分部分项验收 / 预验收 / 正式竣工验收 / 移交归档 | 决定签字完整性、资料齐全性的判定标准 |
| 2 | **资料性质** | 原始记录 / 誊抄件 / 电子版 / 扫描件 / 复印件 | 决定数据真实性审查的严格程度 |
| 3 | **审核范围** | 全量审核 / 按规范 / 按条款 / 按分部分项 / 仅逻辑一致性 | 决定审核深度和范围 |
| 4 | **OCR 引擎** | Vision API / PaddleOCR 本地 | 决定 OCR 识别方式 |
| 5 | **特殊说明** | 用户已知的资料问题、电子版辅助说明、历史背景等 | 避免 AI 误判、提供上下文 |

**执行规则**：
1. **必须全部展示**：5 项问题必须全部列出，每个选项必须完整呈现，`<font color=red>`严禁使用默认值跳过 `</font>`
2. **用户必须逐项回复**：不能"全部默认"，必须对每一项给出明确选择
3. **信息记录**：收集结果写入审核日志的"前置信息"字段
4. **判定标准调整**：根据阶段和性质动态调整判定标准——
   - 过程资料：签字完整性不强制要求，重点审数据真实性
   - 分部分项验收：签字应基本齐全，允许少量补齐
   - 竣工验收/移交归档：签字必须齐全，缺一不可
5. **OCR 引擎选择说明**：
   - Vision API：调用云端视觉模型（Doubao/通义千问/智谱等），需设置环境变量，按量付费，约 ¥0.02/页，中文手写识别最准
   - PaddleOCR 本地：本地推理，零成本，离线可用，需安装 `paddleocr + paddlepaddle`，约 10 秒/页
   - 如果用户未设置 API Key，则该项自动锁定为"PaddleOCR 本地"
6. **输出**：`{被审资料列表, 依据文件列表, 排除文件列表, 阶段, 性质, 审核范围, OCR引擎, 特殊说明}`

**典型场景**：
- 用户说"审一下这份施工日志" → 先弹出文件分类确认框，再问 5 项前置信息（全部列出，不跳过）
- 用户提供的电子版和扫描件是同一份资料的不同版本 → 用户在第 5 项说明，避免被误判为"两份矛盾资料"

---

### 第 1 步：资料格式识别 + 专业分流

**输入**：用户提供的资料（文件路径或文字描述）
**处理**：
1. 判断文件格式：Word(.docx) / Excel(.xlsx) / PDF(电子档) / PDF(扫描件) / 图片 / 文字
2. 若是 PDF，使用 `pdf2image` 抽样检测是否含文本层：
   - 有文本层 → 电子档
   - 无文本层 → 扫描件（需 OCR）
3. **识别工程类别**（五大专业分流）：
   - 场道工程 → 加载 `references/airfield-engineering-audit.md`
   - 空管工程 → 加载 `references/atc-engineering-audit.md`
   - 目视助航 → 加载 `references/visual-aids-audit.md`
   - 弱电系统 → 加载 `references/weak-electricity-audit.md`
   - 供油工程 → 加载 `references/fuel-supply-audit.md`
4. 识别资料类型（检验批/隐蔽/施工日志/材料报审/竣工图/计算书/监理文件/竣工验收）；**施工日志在存在正式施工记录/检验批时自动归类为依据文件**
5. 若用户指定范围（条款/分部分项），记录精准定位信息
6. **输出**：`{格式类型, 工程类别, 资料类型, 定位范围, 专项审核文件, 任务ID}`

### 第 2 步：OCR 文字提取 + 提取完整性校验（铁律 16）

**输入**：第 1 步判定的非电子档文件
**处理**（v4.1 混合 OCR 架构：PaddleOCR 提取 → 混淆检测 → 智能体自动复核）：

> **执行方式**：必须用 RunCommand 调用脚本，不要自己写 Python 代码。

1. **优先 PyMuPDF 提取**（电子档 PDF，`is_scanned: False`）：
   - 执行：`python {SKILL_DIR}/scripts/extract_pdf.py "<文件路径>" --out "<输出.txt>"`
   - 准确率 100%（中文部分），全自动，无需 OCR
2. **扫描件 OCR**（`is_scanned: True`）：
   - **手写施工资料推荐用 vision 模式**：
     `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --engine vision --out "<输出.txt>"`
     AI 视觉模型（Doubao/Qwen/GLM 等）对手写中文识别率约 95%
   - **无 API Key 时降级为 paddle 模式**：
     `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --out "<输出.txt>"`
     跑 PaddleOCR（本地，手写中文 90%+），官方参数优化 + 桩号列检测 + 桩号序列推断
   - **显式启用 Tesseract 备选**：
     `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --engine tesseract --out "<输出.txt>"`
3. **文字后处理**：
   - 执行：`python {SKILL_DIR}/scripts/postprocess.py "<提取的文本文件>"`
   - 全角英文 → 半角英文（`ＭＨ` → `MH`）、私有区字符替换、中文标点规范化
4. **OCR 混淆校正**（扫描件必做，参考 `references/ocr-confusion-correction.md`）：
   - 将 OCR 提取的表格数据整理为 JSON，执行：
     `python {SKILL_DIR}/scripts/ocr_confusion_check.py "<JSON文件>" --pretty`
   - 自动检测高频混淆对（Z→2、4→0、3→8、7→1 等）和上下文异常
   - 命中混淆对 → 标注"OCR 存疑"，列入待核实清单，**不自动替换**
5. **存疑字段自动复核**（有存疑字段时执行，参考 `references/ocr-hybrid-architecture.md`）：
   - 执行：`python {SKILL_DIR}/scripts/verify_fields.py auto "<原始文件>" "<混淆检测JSON>" --data "<数据JSON>" --out "<输出目录>"`
   - 默认路径 B（智能体复核）：脚本自动裁剪存疑字段对应的原图区域为 PNG，输出 `agent_verify_tasks.json`
   - **AI 智能体自动读图验证**（全自动，无需用户参与）：
     - 读取 `agent_verify_tasks.json`，逐个读取 `image_path` 指向的裁剪图片
     - 用自身 Vision 能力识别图片中的字段值，判断 OCR 结果是否正确
     - 输出 `verify_results.json`
   - 执行合并：`python {SKILL_DIR}/scripts/verify_fields.py merge "<verify_results.json>" --data "<数据JSON>" --out "<修正后JSON>"`
6. **读取提取结果**：用 Read 工具读取 `--out` 指定的输出文件
7. **提取完整性校验**（铁律 16）：
   - 行数校验：预期行数 vs 实际提取行数
   - 不通过 → 自动触发重新提取（换引擎，`ocr_image.py` 会自动降级）
   - 重试仍失败 → 标记"提取不完整"，停止后续审核
8. **输出**：结构化文字 + 置信度标记 + 使用引擎 + 提取校验结果 + OCR 待核实清单 + 复核修正记录

### 第 3 步：数据质量审查（铁律 10，前置硬门槛）

**输入**：第 2 步提取的结构化数据（JSON 格式）
**触发条件**：资料中含表格数据（施工记录、检验批、检测报告等）
**处理**：
1. **数据集构建**：将 OCR/AI 提取的表格数据整理为 JSON 格式（含 `records` 数组，每条记录含桩号、桩长、灌入量、充盈系数等字段）
2. **四类检测**（执行命令）：
   - 执行：`python {SKILL_DIR}/scripts/data_quality_check.py "<JSON文件路径>" --expected-pile-total <设计总桩数>`
   - DQ-REPEAT — 重复值模式（造假检测：交替循环、值分布集中）
   - DQ-JUMP — 突变检测（断崖下跌：桩长、灌入量、充盈系数等关键参数，**含致岩豁免**）
   - DQ-ALTER — 涂改痕迹检测（逻辑层面：充盈系数自洽失败、桩长自洽失败）
   - DQ-SELF — 数据自洽校验（行数、**桩号总数校验（不强制连号）**、桩长=高程差、充盈系数=灌入量/理论体积）
3. **AI 视觉复核**（扫描件表格）：OCR 表格提取失败时，使用 TRAE Read 工具逐格判读
4. **判定逻辑**：
   - 有 error → 停止后续审核，要求重新提取数据
   - 有 high → 数据造假嫌疑，在审核报告中重点标注，建议现场取芯验证
   - 有 medium/warning → 记录告警，后续规范审核中重点关注
5. **输出**：数据质量告警清单（嵌入审核报告），含告警代码、严重度、具体行号和数值

**参考文件**：`references/data-quality-patterns.md`（检测规则库）、`scripts/data_quality_check.py`（检测脚本）

### 第 4 步：规范匹配与审核项建立（三级瀑布查询）

**输入**：资料类别 + 定位范围 + 工程类别
**处理**：
1. **第 1 级 — Obsidian 原文查询**（优先）：
   - `obsidian search` 按规范编号/资料类型/工程类别搜索
   - `obsidian read` 读取规范原文，逐条提取审核要点
   - 命中 → 直接使用原文条款
2. **第 2 级 — references 缓存层**（Obsidian 未命中或上下文已满时）：
   - 按工程类别加载专项审核文件（如 `references/atc-engineering-audit.md`）
   - 使用文件中已固化的条款+参数阈值
   - 按 `references/specification-mapping.md` 的映射关系建立审核检查清单
3. **第 3 级 — 工程惯例标注**（前两级均未覆盖）：
   - 标注"该条款无规范原文支撑，判定依据为工程惯例"
   - **禁止使用 WebSearch 兜底**（知识分区红线 1）
4. 如用户指定分部分项，精准定位到对应规范章节
5. **输出**：审核检查清单（含每项检查内容、判定标准、对应条款、来源层级标记）

### 第 5 步：逐项审核

**输入**：资料内容 + 审核检查清单
**处理**：
1. 将资料内容与审核清单逐项比对
2. 每项判定：✅ 符合 / ❌ 不符合 / ⚠️ 缺失 / ➖ 不适用
3. 不符合项标注：问题描述、违反条款、严重程度、整改建议
4. **输出**：审核结果（含逐项判定和不符合项清单）

### 第 6 步：逻辑一致性专项检查（铁律 9，重头戏）

**输入**：当前资料 + 历史资料（若有多份）
**触发条件**：
- 资料 ≥ 2 份：自动启动跨资料逻辑矛盾检查
- 单份资料：执行内部逻辑自洽检查

**检查 10 个子项**（参考 `references/logic-conflict-patterns.md`）：
- 6.1 时间轴一致性
- 6.2 数量累计一致性
- 6.3 人员交叉一致性
- 6.4 状态描述一致性
- 6.5 签字一致性
- 6.6 因果逻辑一致性
- 6.7 规范引用一致性
- 6.8 试验检测逻辑一致性
- **6.9 跨资料合计值反向验证（铁律 17）**：施工日志有合计值 → 与施工记录逐项核对
- **6.10 监理-施工方跨单位日期对照（主流检查方式）**：发现监理方资料时自动触发 17 条对照规则，逐条核对监理与施工方日期逻辑

**输出**：逻辑矛盾清单（嵌入审核报告）

### 第 7 步：运算规范审核（按需）

**输入**：含结构运算的资料
**触发条件**：资料中识别到"承载力""稳定性""沉降""设计""验算"等关键词
**处理**：
1. 识别运算类型
2. 查 `references/calculation-standards.md` 匹配规范
3. 通过 `obsidian search` + `obsidian read` 调取具体规范要求
4. 检查 5 个维度：方法合规性、参数取值、安全系数、边界条件、计算简图
5. **输出**：运算审核意见
**重要**：只做规范性检查，不做数值复算

### 第 8 步：文档生成与日志留痕（铁律 18/19/20）

**输入**：全部审核结果
**处理**：
1. **置信度标注**（铁律 18）：对每个不符合项逐项标注置信度（高/中/低/存疑）
2. **OCR 存疑项汇总**（铁律 20）：将 OCR/AI 视觉识别中置信度低或存疑的数据项汇总为"待核实清单"
3. **自检**（铁律 19）：审核完成前，做一次自检——是否有明显异常但未被主动识别
4. **追溯记录**：如果本次审核中有用户标记的问题，记录追溯原因和改进动作

**统一交付物（HTML）**：
> v1.7 起，审核报告、整改通知书、合规性检查清单三者合并为一个 HTML 文件。**v1.9 起强制套用标准模板**——`references/html-report-template.html`，每次审核必须基于此模板生成报告，保证格式一致。Agent 替换模板中的 `{{占位符}}` 为实际内容，保留所有 CSS 和结构。HTML 报告必须包含以下全部章节：

| 章节 | 内容 | 对应原产出物 |
|:---|:---|:---|
| 一、审核概要 | 资料清单、审核依据、审核标准 | 审核报告 |
| 二、设计依据参数提取 | 从设计变更/施工图提取的关键参数 | 审核报告 |
| 三、资料合规性审核 | 逐份资料审核、不符合项判定 | 审核报告 |
| 四、数据质量审查 | 四类数据质量检测结果（重复值/突变/涂改/自洽） | 审核报告 |
| 五、逻辑一致性专项检查 | 十项逻辑一致性检查（含监理-施工方对照） | 审核报告 |
| 六、不符合项清单汇总 | 所有不符合项表格（含置信度、三级分类） | 合规性检查清单 |
| 七、审核结论与整改要求 | 总体结论 + 🔴Fatal/🟡Sanity Check/🔵Best Practice 三级分组整改 | 整改通知书 |
| 八、OCR待核实清单 | 低置信度数据项，供人工逐项确认 | 新增 |
| 九、审核日志 | 审核时间、依据、OCR置信度、规则触发记录、知识分区红线自检结果 | 审核日志 |

**必存独立文件**（保存磁盘）：
- **审核日志.json**：`audit_output/logs/AU-{日期}-{序号}_审核日志.json`，含前置信息、审核时间、依据规范版本、OCR置信度详情、人工复核标记、审核结论、铁律触发清单、改进建议
- **资料分类结果.json**：`audit_output/intermediate/资料分类结果.json`，含格式识别、专业分流、资料类型
- **审核检查清单.json**：`audit_output/intermediate/审核检查清单.json`，含逐项检查内容、判定标准、对应条款
- **OCR识别结果.md**：`audit_output/intermediate/OCR识别结果.md`，含原始识别文本、AI视觉复核结果、置信度标注、待核实项清单
- **逻辑矛盾对照表.json**：`audit_output/intermediate/逻辑矛盾对照表.json`，含矛盾类型、涉及资料、矛盾点、判定结果

**保存位置**：
```
d:\2026年7月22日 民航资料skill\audit_output\
├── reports\           # HTML 审核报告（统一交付物）
├── logs\              # 审核日志（JSON）
├── intermediate\      # 中间产物
└── audit_history\     # 审核历史索引
```

**输出完整性自检清单**（第 8 步完成前必须逐项打勾）：
- [ ] **OCR 后人工确认已完成**（铁律 20，硬门槛）— 扫描件 OCR 完成后必须停下来等用户确认，未确认前不得进入数据质量检测
- [ ] HTML 报告已生成，含全部 9 个章节
- [ ] 审核日志 JSON 已保存
- [ ] 资料分类结果 JSON 已保存
- [ ] 审核检查清单 JSON 已保存
- [ ] OCR 识别结果 MD 已保存
- [ ] 逻辑矛盾对照表 JSON 已保存
- [ ] OCR 待核实清单（第八章）已生成，低置信度项已标注

> **硬性规则**：扫描件 OCR 完成后、进入数据质量检测前，AI 必须停下，输出"OCR 校对确认表"（或 OCR 待核实清单），等待用户确认。**未确认前，禁止调用 `data_quality_check.py`、禁止进行规范比对、禁止生成最终报告**。这一条是 v1.9 强制门槛，跳过即视为审核流程不完整。

---

## 多Agent并行审核（v6.0 三级粒度拆分）

---

## 输入兼容矩阵

| 输入形式 | 处理方式 | 备注 |
|---------|---------|------|
| Word .docx | markitdown / python-docx | 电子档 |
| Excel .xlsx | markitdown / openpyxl | 电子档 |
| PDF（电子档） | **PyMuPDF 提取** | 中文 100% 准确 |
| PDF（扫描件） | PyMuPDF转图片 + PaddleOCR | 90%+ 准确 |
| 图片 | PaddleOCR + Tesseract + Vision API | 单层主引擎 + 显式兜底 |
| 文字描述 | 直接解析 | 用户口述 |
| 目录（批量） | 逐份走 1-8 步 | 自动生成汇总报告 |
| 指定条款 | 精准审核 | 跳过部分步骤 |
| 指定分部分项 | 精准定位 | 如"场道-土方-换填" |
| 历史审核 | 调取日志 | 用于复查/对比 |

---

## 使用的现成技术（不重复造轮子）

| 工具 | 来源 | 用途 |
|------|------|------|
| **PyMuPDF (fitz)** | 开源 | PDF 电子档提取 |
| **PaddleOCR (paddleocr)** | 开源 | 扫描件 OCR 主力引擎 |
| **Tesseract (pytesseract)** | 开源 | 扫描件 OCR 显式备选引擎 |
| **Pillow (PIL)** | 开源 | 图片处理 |
| **obsidian-cli** | 已装 | 规范知识库查询 |
| **lark-cli** | 已装 | 飞书云盘读取（v1 必要）|
| **markitdown** | 微软开源 | 文档格式转换备选 |
| **Read 工具** | TRAE 内置 | AI 视觉识别兜底 |
| **Write 工具** | TRAE 内置 | 文档输出 |
| **data_quality_check.py** | Skill 自带 | 数据质量四类检测 |

**v4.1 OCR 升级**：PaddleOCR（PaddlePaddle 推理，启用 MKL-DNN，替代 RapidOCR 成为唯一默认主力引擎；Tesseract / Vision API 作为显式兜底）

---

## 参考资料（15 个模块）

| 文件 | 用途 |
|------|------|
| `references/audit-checklists.md` | 五大专业通用审核清单（分级检查项） |
| `references/specification-mapping.md` | 资料类型↔规范条款映射 |
| `references/calculation-standards.md` | 6类运算规范参考 |
| `references/document-templates.md` | 审核报告/整改通知/检查清单模板 |
| `references/airfield-engineering-audit.md` | 场道工程专项审核要点（MH/T 5078.2 + MH 5007/5004） |
| `references/atc-engineering-audit.md` | **空管工程专项审核要点**（MH/T 5078.3 + MH/T 4006 系列） |
| `references/visual-aids-audit.md` | **目视助航设施专项审核要点**（MH/T 5078.4 + MH/T 5012-2022） |
| `references/weak-electricity-audit.md` | **弱电系统专项审核要点**（MH/T 5078.5 + MH/T 5018/5017 等） |
| `references/fuel-supply-audit.md` | **供油工程专项审核要点**（MH/T 5078.6 + MH 5034-2017） |
| `references/high-frequency-errors.md` | 高频错误模式库（含 5 个真实案例） |
| `references/logic-conflict-patterns.md` | 逻辑矛盾识别模式库（铁律 9 配套） |
| `references/data-quality-patterns.md` | 数据质量检测规则库（铁律 10 配套） |
| `references/specification-quick-reference.md` | 规范条款速查表（含 Obsidian 搜索关键词） |
| `references/html-report-template.html` | **审核报告 HTML 标准模板**（v1.9 新增，强制套用） |
| `templates/audit-scope-template.html` | **项目审核范围清单模板**（v1.9 新增，大项目自动生成） |

---

## v1.9 升级详情（2026-07-25）

**触发需求**：对标 valuation-audit-reference skill 后，识别出 6 个框架级优化方向。

**升级内容**：

| 编号 | 升级项 | 说明 |
|:---:|:---|:---|
| 1 | **知识分区红线** | 三条红线 + 推理边界决策树 + 输出前自检清单，防止 AI 把推理当事实 |
| 2 | **三级输出格式** | 🔴Fatal → 🟡Sanity Check → 🔵Best Practice，替代旧版 P1/P2/P3，直接对应整改动作 |
| 3 | **多Agent并行审核** | 按专业拆分任务，最多 6 个 Agent 并行，10000 页资料从 3h 降到 40min |
| 4 | **HTML报告标准模板** | `references/html-report-template.html`，每次审核强制套用，格式一致 |
| 5 | **项目审核范围清单** | `templates/audit-scope-template.html`，大项目可视化追踪分部分项审核进度 |
| 6 | **三层工作流重组** | 信息收集→实质审核→结果输出，每层有明确关卡，Agent 不易漏步骤 |

**版本演进总览**：

| 版本 | 核心变化 | 驱动来源 |
|------|---------|---------|
| v1.0~v1.4 | 20 条铁律体系建立 | 实际审核发现的问题逐条沉淀 |
| v1.5 | 五专业审核全覆盖 + Obsidian 知识库集成 | 用户要求专业审查全面有章可循 |
| v1.7 | 前置信息收集 + OCR 存疑核实 + 统一 HTML 交付 | 用户反馈 OCR 年份误读 + 过程资料误判 |
| v1.8 | 三层工作流重组 | 对标参考 skill 后的架构优化 |
| v1.9 | 知识分区红线 + 三级输出格式 + 多Agent并行 + 标准模板 | 对标分析后的框架级全面提升 |
| v4.1 | PaddleOCR 单层主引擎 + Vision API 兜底 | OCR 性能优化 |
| v5.0 | API-First 策略 + 7 家 Vision API | 成本与准确性平衡 |
| **v6.0** | **四阶段流水线 + 数据底座 + Web 编辑器 + 三级粒度多Agent并行** | **上下文管理 + 人工核对 + 增量更新** |

---

## v6.0 升级详情（2026-07-30）

**触发需求**：v5.0 单文件 9 步流程在大项目场景下出现上下文溢出、人工核对无处落地、重复 OCR 浪费时间等问题。

**升级内容**：

| 编号 | 升级项 | 说明 |
|:---:|:---|:---|
| 1 | **四阶段流水线** | 建数据底座 → 人工核对 → 正式审核 → 生成报告，阶段间硬闸门，通过 `index.json` 的 `stage` 字段衔接 |
| 2 | **数据底座（build_foundation.py）** | 按项目维度建立结构化中间数据，JSON + MD 双格式，纯文件系统存储，零数据库依赖 |
| 3 | **Web 数据编辑器（data-editor.html）** | 纯 HTML 文件，左图右表对照，双视图编辑（结构化 + 原始文本），零对话 token |
| 4 | **项目总览仪表盘（project-dashboard.html）** | 从 index.json 读取状态，展示文件清单、OCR 进度、质量告警数、审核进度、断档检测 |
| 5 | **增量更新（N-08）** | 基于 SHA256 哈希对比，仅处理新增或变更文件，已 OCR 过的文件不重复处理 |
| 6 | **断档检测（N-09）** | 同一专业的桩号、日期、编号连续性检查，自动标记缺漏，写入 `index.json` 的 `gaps[]` |
| 7 | **三级粒度多 Agent 并行** | `--split-by professional|sub|item`，与人工分部分项划分一致，最多 115 个独立任务 |
| 8 | **多 Agent 任务包机制** | `--dry-run` 生成任务包，`--task-id` 执行单个任务，`--tasks-file` 加载任务包 |
| 9 | **run_audit.py 新增 build/review/report 子命令** | 统一入口，支持流水线全流程 |
| 10 | **SVG 图表生成** | 审核报告含环形图（不符合项分布）+ 水平条形图（各专业问题数），零外部依赖 |
| 11 | **审核前置检查闸门** | `review_audit.py` 自动检查 `human_verified`，未完成核对拒绝执行（铁律 R-02 落地） |
| 12 | **分部分项层级树** | 5 专业 / 48 分部 / 115 分项，源自 references 下 5 个规范文件，每个分部分项有唯一 code |

**新增脚本/文件**：
- `scripts/build_foundation.py` — 数据底座建立脚本
- `scripts/review_audit.py` — 正式审核流水线脚本
- `scripts/audit_config.py` — 分部分项配置（115 个 code 的层级结构）
- `templates/data-editor.html` — Web 数据编辑器
- `templates/project-dashboard.html` — 项目总览仪表盘
- `templates/pdf.min.js` — PDF.js 离线预下载（支持离线场景）

**保留的 v5.0 能力**：
- 单文件审核模式（`run_audit.py audit`）保留，用于快速审核单份资料
- 9 步流程保留，作为单文件审核的执行细则
- 所有 OCR 引擎、数据质量检测、混淆检测、字段复核脚本不变

**与 v5.0 的关系**：v6.0 不替代 v5.0，而是在其上层包装。v5.0 的 OCR、数据质量检测、规范对账能力作为 v6.0 流水线各阶段的底层能力被调用。
