---
name: "civil-aviation-doc-audit"
version: "10.5"
description: "v10.5 民航施工资料合规审核大师：按 MH/T 5078 规范逐条对账、OCR 识别扫描件、跨资料逻辑一致性检查、三级输出（Fatal/Sanity Check/Best Practice）、自动生成审核报告与整改通知，覆盖场道/空管/助航/弱电/供油五大专业。当用户要求审核民航施工资料、检查合规性、验证运算、识别扫描件、生成报告或整改通知时触发。"
---

# 民航建设施工资料合规审核大师 v10.5

> 面向民航运输机场专业工程，基于 MH/T 5078.1~5078.6-2024 资料管理规程体系。提供"建数据底座→人工核对→正式审核→生成报告"四阶段审核流水线，以及独立的规则管理子系统。本 Skill 按**场景路由**组织，AI 根据用户输入仅加载对应场景。

## 路由表

> **收到用户消息后，先匹配下方触发词，定位到对应场景章节。匹配不到时默认走审核流水线。**

| 用户说 | → 走哪个场景 |
|:---|:---|
| "建数据底座"/"审核"/"正式审核"/"开始审核"/"审一下整个项目" | → **场景·审核流水线** |
| "审台账"/"核对 xlsx"/"电子表"/"对图纸核数据"/"审这份 Excel" | → **场景·审核流水线**（纯电子台账也走全套：建底座+前置确认+审核+模板报告，详见 `references/electronic-ledger.md`） |
| "人工核对"/"聊天核对"/"Chat-Verify"/"手机核对"/"打开数据编辑器"/"对一下 OCR 结果" | → **场景·审核流水线** |
| "生成审核报告"/"出报告" | → **场景·审核流水线** |
| "增量更新"/"补充资料"/"更新数据底座" | → **场景·审核流水线** |
| "项目总览"/"项目进度"/"审核进度" | → **场景·审核流水线** |
| "并行审核"/"多 Agent 审核" | → **场景·审核流水线** |
| "规则管理"/"管理规则"/"规则面板"/"新建规则"/"添加规则" | → **场景·规则管理** |
| "规则反馈"/"漏审反馈"/"误报反馈" | → **场景·规则管理** |
| "启动反思"/"触发反思"/"规则反思" | → **场景·规则管理** |
| "查看候选规则"/"孵化区"/"提升候选规则" | → **场景·规则管理** |

---

## 共享基础设施

> 本节内容两个场景共用，不重复定义。

### 强制闸门

| 闸门 | 规则 | 违反后果 | 用户动作 | AI 恢复条件 |
|:---|:---|:---|:---|:---|
| **G-0** | 未建立数据底座（index.json 不存在），禁止输出任何审核结论 | 输出内容无效 | — | — |
| **G-1** | 所有文件 ocr_status 必须为 "completed" | 阻断进入步骤 5 | — | — |
| **G-1.5** | 人工核对入口就绪：资料员工作台已部署（`资料员工作台/` 下有 index.html）或 `templates/` 下 `data-editor.html` 存在（原生模式/`file://` 后备）。v10 起不再要求往 `数据底座/` 复制散页模板 | 阻断进入步骤 5 | — | — |
| **G-1.9** | **步骤 4 完成 = AI 必须硬停。输出"扫描件待核实清单"后立即停止，禁止自行进入步骤 5/6/7，禁止自行把存疑项判为"没问题"** | 阻断进入步骤 5 | 经 AI 对话框（Chat-Verify）短答修正存疑项，或打开数据编辑器逐项核对；全部完成后确认 | 读取到 `human_verified=true` 后自动继续 |
| **G-2** | 所有文件 human_verified 必须为 true | 阻断进入步骤 6 | 经 AI 对话框（Chat-Verify）或数据编辑器完成所有存疑项的人工核实并确认 | 读取到 `human_verified=true` 后自动继续 |

### 强制执行协议（Anti-Omission Protocol）

> **进入步骤 4/6/7 前**，AI 必须输出 `<thought_process>` 逐项检查；任一项为 false → 立即停止并向用户说明。

```
<thought_process>
0. 是否已检查过 index.json 的存在性？(是/否)
1. [输入] 6 项前置信息是否已确认？(是/否)
2. [G-1] 所有文件 ocr_status 是否全部 = "completed"？(是/否)
3. [G-2] 所有文件 human_verified 是否全部 = true？(是/否)
4. [源] 每条结论是否都有规范编号+条款号出处？(是/否)
5. [格式] 是否按三级输出(Fatal/Sanity/Best)分类？(是/否)
</thought_process>
```

### 前置信息确认（6 项）

> **两个场景共用**：审核流水线在步骤 3 调用，规则管理在新建规则前调用（简化版仅需 stage + scope 两项）。

AI 按以下模板逐项询问。详细选项表见 `references/skill-config-reference.md`。

| # | 字段 | 说明 | 默认值 |
|:---:|:---|:---|:---:|
| 1 | `stage` | 资料阶段：施工过程/分部分项验收/竣工移交归档 | 分部分项验收 |
| 2 | `nature` | 资料形式：电子版/扫描件/混合/图纸/**扫描转化电子文档**。**纯电子表（xlsx）场景的步骤裁剪见 `references/electronic-ledger.md`**（6 项确认一项不少、底座必建、报告走模板） | — |
| 3 | `scope` | 审核范围：全量/指定文件/指定分部分项/指定专业 | 全量审核 |
| 4 | `ocr_engine` | ⚡ 见下方引擎选择流程 | auto |
| 5 | `special_notes` | 特殊说明（可空） | 无 |
| 6 | `check_signatures` | 是否查签字：是/否 | 否 |

**第 4 项引擎选择流程（强制）**：
1. 先执行 `python -c "import rapidocr; print('ok')"` 检测 RapidOCR 可用性
2. 将 4 引擎以卡片格式展示（含可用性+代价说明），用户选一个
3. 回显确认后落盘 preconditions（`ocr_engine_source` 记录 user_chosen/default）
> **`nature=扫描转化电子文档`**：用户已用 WPS 等工具把扫描件转成 Word(.docx)。这类文件走**电子表解析**（真实表格结构，无需 OCR），第 4 项 OCR 引擎选择自动置灰/跳过，不设 OCR 优先级路由。
> **`nature=电子版`（纯 xlsx/电子表）**：第 4 项同样置灰（注明"原生电子表格无需 OCR"），但第 5/6 项照常询问；底座必建、数据默认可信录入、异常项才人工核对。完整裁剪表见 `references/electronic-ledger.md`。

### 推断值生成规则

> 当 OCR 识别结果为空 / 置信度 < 0.5 / 数值超出正常范围时触发推断。

| 场景 | 推断逻辑 | 置信度标定 | 审核使用规则 |
|:---|:---|:---:|:---|
| 数值型 | 同文件其他行线性插值，或取前后文件同参数值 | ≥0.8 可信 / 0.5~0.8 参考 / <0.5 不输出 | 审核只用确认值，推断值仅在确认值缺失时作为参考，报告中标注 "△ 推断值" |
| 文本型 | 取上下文语义推断（如"桩号 1-1"→ 推断为"1-1#"） | 同上 | 同上 |
| 签名类 | 不推断，强制标记 "需人工核实" | — | 不输出推断值 |

### 常见错误

| ❌ 错误行为 | ✅ 正确行为 |
|:---|:---|
| 不检查 Python 可用性，直接假设引擎模式 | 先执行 python --version 判定模式 |
| 跳过数据底座，直接读取文件出"审核意见" | 必须先建数据底座，再审核 |
| 引擎模式不可用时放弃，不切原生模式 | Python 不可用 → 自动切原生模式 |
| 步骤 4 完成后不硬停，直接进步骤 6 出报告 | 触发 G-1.9：输出扫描件待核实清单后硬停 |
| AI 自行把存疑项判为"没问题"并标记 human_verified=true | human_verified 只能由用户确认后改为 true |
| index.json 已存在，AI 假装没看到走新建路径 | 触发步骤 2：自动走增量路径 |
| 增量审核时跳过 6 项前置确认 | 增量路径也必须逐项确认（任务目的可能变更） |

### OCR 引擎策略概要

| 场景 | 推荐引擎 | 路由链 |
|:---|:---|:---|
| 印刷体（默认） | auto | rapidocr → vision → tesseract |
| 手写体 | auto --handwritten | vision → agent |
| 纯本地零 token | rapidocr | 强制 RapidOCR |
| 云端 API | vision | 仅 VLM |
| 快速复核 | agent | AI 读图，页数不限 |
| **扫描转化电子文档** | 无需 OCR | 走 docx 电子表解析，跳过全部 OCR 引擎 |

详细路由链、手写体判定、图像预处理、表格识别见 `references/ocr-hybrid-architecture.md`。Vision API 配置见 `references/skill-config-reference.md`。

### 三级输出格式

| 级别 | 含义 | 对应整改动作 |
|:---|:---|:---|
| 🔴 **Fatal** | 致命——资料造假、数据矛盾、关键参数严重偏离 | 暂停归档，追溯原始底稿 |
| 🟡 **Sanity Check** | 待核实——数据异常但可能合理解释 | 人工核实后确认 |
| 🔵 **Best Practice** | 建议——格式不规范、填写不完整 | 下次修改时补充 |

Fatal ≥ 1 条 → 不予通过。依据必须写规范条文号+摘要，禁止写"铁律X"。

### 知识库查询与红线

查询优先级：`references/` 专项审核文件（本地，已固化 80%+ 条款）→ Obsidian `wiki/sources/` 回源 → 标注"判定依据为工程惯例"。

| 红线 | 规则 |
|:---:|:---|
| **红线 1** | 规范条文编号必须来自 Obsidian 原文或 references 缓存，**禁止凭记忆编造** |
| **红线 2** | 技术参数阈值必须来自规范原文，**禁止用"一般工程经验"替代** |
| **红线 3** | 推理推断出的结论必须标注"推断"而非"判定"，且提供验证路径 |

### 核心铁律概要（20 条）

详见 `rules/registry.json`。其中铁律 9/12/13/14 由 L2 逻辑规则承载，L1-IRON 实际 16 条规则文件。

| # | 摘要 |
|:---:|:---|
| 1 | 规范来源必须可追溯 |
| 2 | OCR 结果必须人工复核 |
| 3 | 运算审核只做规范性检查 |
| 4 | 审核结论必须有据可依 |
| 5 | 资料标准是"移交归档" |
| 6 | 拒绝为伪造资料背书 |
| 7 | 审核过程留痕 |
| 8 | 未发现问题 ≠ 全部合格 |
| 9 | 逻辑一致性专项检查（10 子项） |
| 10 | 数据质量先于规范合规 |
| 11 | 表格数据必须全列提取 |
| 12 | 桩长与高程差交叉校验（±0.1m） |
| 13 | 缺合计行=资料非原始记录 |
| 14 | 多参数工程逻辑链联检 |
| 15 | 原始底稿追溯 |
| 16 | 提取-验证-重试循环 |
| 17 | 跨资料合计值反向验证 |
| 18 | 审核结论置信度分级（高/中/低/存疑） |
| 19 | 用户标记问题的闭环追溯 |
| 20 | OCR 存疑项人工核实机制 |

---

## 场景·审核流水线

> **🔴 强制规则：任何包含 2 份及以上资料的审核，必须走流水线。禁止跳过人工核对。**
> **🔴 强制规则：`human_verified` 未全部为 true 时，AI 不得生成任何审核报告。**

### 步骤 1：判定运行模式

```
【硬锚点 = 当前解释器能 import rapidocr】查找顺序：
  1. 先测当前解释器：python -c "import rapidocr; print('ok')"
     ├─ ok → 引擎模式，PYTHON_CMD = 当前解释器（sys.executable），就用它，别再找别处
     └─ 失败 → 继续步骤 2
  2. 再测 C:\Python314\python.exe -c "import rapidocr; print('ok')"
     ├─ ok → 引擎模式，PYTHON_CMD = C:\Python314\python.exe
     └─ 失败 → 提示："当前解释器与 3.14 均无 rapidocr，请先 pip install rapidocr"
               —— 除非用户明确要求，**不得**回退到 PaddleOCR / Tesseract
  ⚠️ 铁律：OCR 引擎只认 rapidocr（或用户显式选的 vision/agent）。
     禁止让 AI 因 rapidocr 不可用就擅自改走 PaddleOCR 或 Tesseract。
```

### 步骤 2：检测是否已有数据底座（分支：新建/增量）

```
项目文件夹/数据底座/index.json 是否存在？
  ├─ 存在 → 增量路径：先重新确认 6 项前置信息（任务目的可能变更），再走增量
  └─ 不存在 → 新建路径，走完整新建流程
```

### 步骤 3：前置信息确认（6 项）

> 6 项前置信息表见「共享基础设施 → 前置信息确认（6 项）」。AI 按模板逐项询问，确认后落盘 preconditions。

### 步骤 4~7：四阶段流水线

```
步骤 4 — 阶段 1：建数据底座（全自动） → 数据底座/（JSON三层+index.json）；视图由 v10 资料员工作台承载（不再往 数据底座/ 复制散页）
  推断：build_foundation.py 自动读取 rules/inference_rules.json 生成推荐值
  对比清单：增量路径展示已有文件 vs 新增文件清单，用户确认后执行
  闸门：ocr_status = "completed" + G-1.5 人工核对入口就绪 → G-1.9 硬停
步骤 4.5 — AI 视觉复核（扫描转化电子文档自动触发） → verify_output/（任务清单+裁图，AI 读图修正 OCR 乱码）
  触发：nature=扫描转化电子文档 且存在存疑项（易混字+表级乱码）
  闸门：不豁免 G-1.9/G-2，只减少人工核对量，不替代人工确认
步骤 5 — 阶段 2：人工核对（零 token） → 修正记录/corrections.json（+ 通道 B 的 corrected_data.json）
  通道：AI 对话框（Chat-Verify）为主（手机可用），HTML 数据编辑器为批量精修后备
  闸门：human_verified = true → 确认完成后 AI 读取修正后数据
步骤 6 — 阶段 3：正式审核 → 审核日志/AU-{日期}-{序号}_审核日志.json
  处理：规范对账+逻辑一致性+运算审核
步骤 7 — 阶段 4：生成报告 → 审核报告.html（9 章节强制，含 SVG 图表）
```

**阶段间判定**：步骤 4→5 看 `documents[].ocr_status`（全为 `"completed"`）；步骤 5→6 看 `documents[].human_verified`（全为 `true`）；步骤 6→7 看审核日志目录存在最新 `AU-*.json`。

#### 步骤 4 CLI：建数据底座（阶段 1）

```powershell
python {SKILL_DIR}/scripts/run_audit.py build "<项目文件夹>" \
    --engine <auto|vision|rapidocr|agent> \
    --incremental \
    --out "<数据底座目录名，默认'数据底座'>" \
    --preconditions "<前置信息JSON文件路径>"
```

**自动产物**：`数据底座/` → index.json + 五专业目录 + 修正记录/ + 审核日志/
**v9.7 起附加产物**：`nature=扫描转化电子文档` 且有存疑项时，自动产出 `verify_output/`（视觉复核任务清单 + 裁图），登记进 index.json 的 `verify_tasks_file` 字段。

#### 步骤 4.5：AI 视觉复核（扫描转化电子文档自动触发）

> **背景**：WPS 扫描件转 docx 的表格虽走电子表解析，但单元格内文字仍是 OCR 产物，乱码/易混字（`2026、4.22`、`砰石松三飞`）落在数据里。此步让**当前宿主 AI**（任何具备读图能力的智能体）读原图自证修正，减少人工核对量。

**视觉复核协议（平台无关）**——任务清单（JSON）+ 裁图（PNG）+ 结果（JSON）三文件交互，不绑定任何平台特性：

```
1. 读任务清单  <doc目录>/verify_output/verify_tasks.json
   每条任务：task_id / field / field_label / row / table / scope / page /
            image_path（裁图路径）/ ocr_value（OCR 原值）/
            suspected_value（规则建议值）/ reason / question（复核问题）
2. 逐条读裁图  verify_output/crops/*.png（docx 内嵌图已按页序解压，表 t ↔ 第 t+1 张图）
   用智能体自身视觉能力识别图上真实值
3. 写结果文件  verify_output/verify_results.json（与任务清单同目录）
   {"results": [{"task_id": "VERIFY-001", "verified_value": "2500",
                  "confidence": "high", "note": "图上清晰为 2500"}]}
4. 合并落库
   python {SKILL_DIR}/scripts/verify_fields.py merge <verify_results.json> \
       --tasks <verify_tasks.json> --data <原始数据JSON> [--out <修正后路径>]
```

**协议铁律**：

- 结果**只写 `task_id + verified_value + confidence(+note)`**——row/field/scope 由 merge 按 task_id 回查任务清单，AI 不得手抄（抄错一行就写错一行）
- 置信度只认 `high / medium / low`：**high/medium 自动落库；low 或图不清 → `verified_value` 留空**，该项自动留给步骤 5 人工核对
- 落库自动双份同步（`structured_rows` + `rows`），中文字段名（桩号/部位等）自动映射英文行键，逐格留痕 `_verify_notes`（原值→新值+置信度）
- **任务分两档（v10.0）**：`scope=table`（施工部位/施工日期等整表同值字段，落库写整表）；`scope=row`（实长/电流/充盈系数等行级数值字段，落库只写该桩号所在行）。「整行」核对项（表头不可靠）不进视觉复核，留给 Chat-Verify 人工核对
- **视觉复核不豁免人工核对闸门**：G-1.9/G-2 照常生效。AI 复核是"减负"不是"放行"，复核后仍需用户对剩余存疑项完成 Chat-Verify 确认

**平台适配**：

| 宿主平台 | 执行方式 | 无视觉能力时 |
|:---|:---|:---|
| TRAE / WorkBuddy / CodeBuddy 等任意 Agent | 用平台自身读图工具逐张读 `crops/*.png`，按协议写回 `verify_results.json` | 存疑项不丢失，全部走步骤 5 Chat-Verify 人工核对 |
| Vision API（可选，路径 A） | `python {SKILL_DIR}/scripts/verify_fields.py verify-api <verify_tasks.json> --provider <名>`，支持 qwen / glm / hunyuan / kimi / doubao / baidu / openai 等 | 未配置 API Key 时静默跳过，不报错 |

#### 步骤 5：人工核对（阶段 2）

**通道 A · 聊天核对（Chat-Verify，推荐，手机可用）**：AI 把 OCR 存疑项**按表分组、按优先级**在对话框逐项抛转（如「表 0 · 施工部位 = ? 原值『研工组三区』，疑似乱码」），用户短答修正（如「表0部位=碎石桩边三区」）。AI 解析用户回答 → 生成修正 JSON → 调用 `chat_verify_apply.py` 校验并落库：

```powershell
# 列出待核对存疑项（按表分组，附页码定位与建议值，AI 据此在对话框抛转）
python {SKILL_DIR}/scripts/chat_verify_apply.py list "<项目文件夹>" --doc DOC-002

# 应用聊天修正（AI 从用户回答解析出修正 JSON，支持表级/行级、中文标签/英文字段名）
python {SKILL_DIR}/scripts/chat_verify_apply.py apply "<项目文件夹>" --doc DOC-002 --corrections <修正.json>

# 仅刷新建议值（重算并写回 inferred，不触碰核对进度/存疑清单/留痕）
python {SKILL_DIR}/scripts/chat_verify_apply.py refresh "<项目文件夹>" --doc DOC-002

# 查看核对进度（剩余存疑数 / 是否全部已核）
python {SKILL_DIR}/scripts/chat_verify_apply.py status "<项目文件夹>"

# 全部存疑项核对完 + 用户明确确认后放行 → human_verified=true（仅用户确认后调用，AI 禁止擅自调用）
python {SKILL_DIR}/scripts/chat_verify_apply.py confirm "<项目文件夹>" --doc DOC-002 --confirm-classification
```

建议值说明：数值链推断值（`inferred`）与文本建议值（如施工部位/日期，带 `suggested_only`）由规则引擎在 `rules/inference_rules.json` 中统一定义；文本建议值**只建议不入库**，级别低于权威输入，`list` 输出附「建议值 + 置信度 + 来源」与页码定位，用户确认采纳后（`accept_recommended`）才落库。建议值为纯规则引擎产出、离线可用，**默认不依赖任何模型**。视觉层面的核验由**步骤 4.5 视觉复核协议**承载（v9.7 起贯通）：扫描转化电子文档建底座时自动产出复核任务，宿主 AI 读图回写高/中置信度修正值；未执行或低置信度的项仍回到本步骤 Chat-Verify 交用户裁决。

铁律：只收集用户权威输入；OCR/推断建议值需用户确认才落库；AI 不擅自判定、不替用户确认；每次修正写入 `修正记录/corrections.json` 留痕（来源 user_dialog、时间、原值→新值）；失败的修正写入 index.json 的 `corrections.failed` 供追溯。聊天通道不产出 corrected_data.json（该文件仅通道 B 数据编辑器生成）。

**通道 B · 数据编辑器（后备，批量精修）**：用户在浏览器中打开 `data-editor.html` 完成所有核对操作：左图右表 → 翻页同步 → 双视图编辑 → 字段编辑记录原值/新值 → 质量告警逐条确认 → OCR 存疑项高亮 → 保存生成 `corrected_data.json` → 确认完成更新 `human_verified=true`。

**JSON 三层结构**：structured_rows（规则引擎）+ full_text（LLM 审核）+ page_map（人工定位）。详见 `references/skill-config-reference.md`。

#### 步骤 6 CLI：正式审核（阶段 3）

```powershell
# 单 Agent 模式（默认按分部级拆分）
python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹>" --split-by sub

# 多 Agent 并行：--dry-run 生成任务包 → 各子 Agent 执行 --task-id → 主 Agent 汇总
```

#### 步骤 7 CLI：生成报告（阶段 4）

```powershell
python {SKILL_DIR}/scripts/run_audit.py report "<项目文件夹>"
```

**无规则覆盖提醒（v10.5 强制协议）**：审核 summary 含 `unguarded_doc_types`（本批受审文档中无任何 active 规则覆盖的类型，由规则引擎自动侦测，含 doc_type/份数）。报告第八节自动渲染该清单。**AI 在生成报告前必须检查此字段**：非空时须向用户显式说明"以下类型无规则引擎兜底，仅依赖 AI 逐条对账与人工判断"，并建议补规则或确认接受裸检——禁止在用户不知情下跳过。reference 角色（审核参照）不参与此判定。

#### 数据质量与结构提取

建底座自动：OCR 空结果拦截、整表列错位检测（错位率≥5% 标 `needs_review`）、内容感知分类。已落地四件套：①结构化 rows ②行级门禁结论 ③存疑项清单 ④AI 推断建议值（`inferred`+置信度，审核只用确认值）。详情见 `references/data-quality-patterns.md`。

#### 签字一致性检测（可选）

启用方式：前置信息确认时选择"签字检查"，或审核时加 `--check-signatures`。pHash + SSIM 双指标比对，相似度<70% 标记"疑似代签"。

### 原生模式替代（Python 不可用时）

> **引擎模式不可用时自动切原生模式。原生模式与引擎模式数据完全兼容，可双向迁移。**

```
原生步骤 4 — AI 逐页读图（禁止抽样）→ 结构化 JSON + index.json + Web模板
  闸门：ocr_status="completed" + G-1.9 硬停
原生步骤 5 — 人工核对 → 更新 JSON → human_verified=true
  闸门：human_verified=true（G-2）
原生步骤 6~7 — AI 规则审核 + 报告生成 → 审核报告.html
```

详细 34 项检查清单见 `references/native-mode-checklist.md`，步骤 4 机械化步骤见 `references/native-mode-stage1-checklist.md`。

### 多 Agent 并行审核

资料量 ≥500 页或 ≥3 专业时自动触发。拆分粒度：`professional`（5 专业）/ `sub`（48 分部，默认）/ `item`（115 分项）。工作流：主 Agent `--dry-run` 生成任务包 → 子 Agent 各执行一个 `--task-id` → 主 Agent 汇总。详见 `references/cli-reference.md`。

### 运行时进度展示（强制）

> 每次正式审核运行中，AI 必须在每条回复顶部固定展示步骤 1~7 进度清单。

```
📋 审核进度（当前：步骤 3/7）
✅ 步骤 1 · 判定运行模式          —— 完成
✅ 步骤 2 · 检测数据底座          —— 完成
⬜ 步骤 3 · 前置信息确认          —— 进行中…
⬜ 步骤 4 · 建数据底座            —— 未开始
⬜ 步骤 5 · 人工核对              —— 未开始
⬜ 步骤 6 · 正式审核              —— 未开始
⬜ 步骤 7 · 生成报告              —— 未开始
```

---

## 场景·规则管理

> 规则文件位于 `rules/` 目录，94 条规则三层分级。

### 步骤化工作流

```
📋 规则管理进度（当前：第 1 步）
⬜ 第一步 · 规则浏览    —— 进行中…
⬜ 第二步 · 规则操作    —— 未开始
⬜ 第三步 · 反馈闭环    —— 🚧 规划中
⬜ 第四步 · 反思触发    —— 🚧 规划中
```

#### 第一步：规则浏览

AI 读取 `rules/registry.json`，展示当前规则状态（按层级/类别/状态聚合）。用户可查看任意规则文件的完整内容。

#### 第二步：规则操作（新建/编辑/删除）

AI 输出 JSON 变更预览，用户确认后执行落盘，更新 registry.json。

#### 第三步：反馈闭环（🚧 规划中）

> 用户反馈漏审/误报 → AI 分析 → 候选规则写入孵化区 → 用户审批后提升为正式规则。目录 `rules/custom/incubator/` 待建。

#### 第四步：反思触发（🚧 规划中）

> 触发后 AI 读取历史反思报告 → 分析规则命中率/误报率模式 → 生成优化建议。目录 `rules/reflections/` 待建。

### 三层分级体系

| 层级 | 代号 | 判定标准 | 违反后果 |
|:---:|:---:|:---|:---:|
| L1 铁律 | L1-IRON | 不可商榷的合规底线（17 条） | 🔴 Fatal |
| L2 逻辑一致性 | L2-LOGIC | 数学/几何/时序/引用自洽（71 条 active） | 🟡 Sanity Check |
| L3 业务合理性 | L3-BUSINESS | 阈值/经验/行业惯例（5 条） | 🔵 Best Practice |
| 跨单位对照 | SCOPE-CROSS_UNIT | 监理-施工方对照 | 按 L1/L2/L3 分级 |

### 编辑方式（三选一）

1. **离线版**：双击 `templates/rule-editor.html` → 选择 `rules/` 文件夹
2. **Web 面板**：双击 `rule-manager.bat` 启动服务并自动打开浏览器
3. **直接改 JSON**：编辑 `rules/L1-iron/`、`rules/L2-logic/`、`rules/L3-business/` 下的文件

---

## 附录

### A. v5.0 旧版单文件审核模式

> ⚠️ 仅限单份资料快速预览。2 份及以上资料禁止走本流程，必须走四阶段流水线。

详见 `references/v5.0-legacy-mode.md`。

### B. 参考资料清单

详见 `references/README.md` 场景导读（23 个参考文件按场景分类，建议先匹配场景再读对应文件）。

### C. CLI 命令参考

详见 `references/cli-reference.md`（30+ 个命令完整用法和执行规则）。

### D. 版本更新历史

详见 `references/CHANGELOG.md`（v1.0~v9.5 完整变更记录）。