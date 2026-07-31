# 民航建设施工资料合规审核大师 (civil-aviation-doc-audit)

> 民航工程施工资料合规性审核 Skill v6.0
> 适用：MH/T 5078.1~5078.6-2024 系列 + CCAR-165-R1 + MH 5031-2025 等民航规范
> 五大专业全覆盖：场道 / 空管 / 助航 / 弱电 / 供油
> v6.0 核心特性：四阶段流水线 + 数据底座 + Web 编辑器 + 三级粒度多 Agent 并行

---

## 目录结构

```
civil-aviation-doc-audit/
├── SKILL.md                          # 主 Skill 文件（必读，v6.0）
├── README.md                         # 本文件
├── requirements.txt                  # Python 依赖
├── install.ps1                       # 一键安装脚本（Python+PaddleOCR+Poppler+Tesseract）
├── audit.bat                         # Windows 快捷入口
├── .gitignore
│
├── references/                       # 16 个参考文件
│   ├── audit-checklists.md           # 分专业审核检查清单
│   ├── specification-mapping.md      # 资料类型→规范条款映射
│   ├── specification-quick-reference.md  # 规范条款速查表
│   ├── calculation-standards.md      # 运算规范性审核
│   ├── airfield-engineering-audit.md # 场道工程专项审核要点
│   ├── atc-engineering-audit.md      # 空管工程专项审核要点
│   ├── visual-aids-audit.md          # 目视助航设施专项审核要点
│   ├── weak-electricity-audit.md     # 弱电系统专项审核要点
│   ├── fuel-supply-audit.md          # 供油工程专项审核要点
│   ├── high-frequency-errors.md      # 高频错误模式库
│   ├── logic-conflict-patterns.md    # 逻辑矛盾识别模式库（铁律 9，含 9.10 监理-施工方对照）
│   ├── data-quality-patterns.md      # 数据质量检测模式库（铁律 10）
│   ├── ocr-confusion-correction.md   # OCR 混淆修正规则
│   ├── ocr-hybrid-architecture.md    # OCR 混合架构说明
│   ├── document-templates.md         # 审核报告/日志模板
│   └── html-report-template.html     # HTML 报告标准模板
│
├── scripts/                          # 21 个脚本
│   ├── run_audit.py                  # Skill 入口（含 build/review/report/audit 子命令）
│   ├── build_foundation.py           # 【v6.0】数据底座建立脚本（阶段 1）
│   ├── review_audit.py               # 【v6.0】正式审核流水线脚本（阶段 3，多 Agent 并行）
│   ├── audit_config.py               # 【v6.0】分部分项配置（5 专业 / 48 分部 / 115 分项）
│   ├── extract_pdf.py                # PDF 文字提取（PyMuPDF）
│   ├── ocr_image.py                  # 扫描件 OCR（API-First：Vision API → PaddleOCR → Tesseract）
│   ├── postprocess.py                # 文本后处理（全角转半角、PUA 替换）
│   ├── data_quality_check.py         # 数据质量检测（铁律 10 配套）
│   ├── ocr_confusion_check.py        # OCR 混淆检测（Z→2、4→0 等）
│   ├── verify_fields.py              # 存疑字段自动复核（裁剪+AI 视觉验证）
│   ├── vision_providers.py           # Vision API 统一配置层（7 家 Provider）
│   ├── rule_engine.py                # 【v6.0】规则引擎核心（加载/匹配/求值/检查/报告）
│   ├── rule_admin.py                 # 【v6.0】规则管理 API 服务（20+ 端点）
│   ├── rule_lifecycle.py             # 【v6.0】规则生命周期管理（draft→active）
│   ├── rule_monitor.py               # 【v6.0】规则效力自监控（命中率/误报率/自动降级）
│   ├── rule_reflector.py             # 【v6.0】定时反思调度器（LLM 生成优化建议）
│   ├── rule_registry_builder.py      # 【v6.0】规则注册表生成工具
│   ├── rule_schema_validator.py      # 【v6.0】规则 JSON Schema 校验工具
│   ├── feedback_store.py             # 【v6.0】反馈存储管理
│   ├── feedback_analyzer.py          # 【v6.0】LLM 反馈分析管道（聚类/模式提取/候选规则）
│   └── audit_memory.py               # 【v6.0】审核记忆流（JSONL 事件日志）
│
├── templates/                        # HTML 模板层
│   ├── audit-scope-template.html     # 审核范围清单模板（v1.9）
│   ├── data-editor.html              # 【v6.0】Web 数据编辑器（双视图，左图右表）
│   ├── project-dashboard.html        # 【v6.0】项目总览仪表盘
│   ├── pdf.min.js                    # 【v6.0】PDF.js 离线预下载
│   ├── rule-manager.html             # 【v6.0】规则管理面板（4 标签页，可视化编辑器）
│   ├── feedback-collector.html       # 【v6.0】反馈收集组件（漏审/误报）
│   └── alignment-view.html           # 【v6.0】跨单位数据对齐视图
│
├── rules/                            # 【v6.0】规则文件库（93 条）
│   ├── L1-iron/                      # L1 铁律（17 条）
│   ├── L2-logic/                     # L2 逻辑一致性（73 条，含 IR-012/013/014 三条迁移自原铁律的几何/合计/多参数联检规则，LG-006/007 沉管/拔管时间完整性校验）
│   ├── L3-business/                  # L3 业务合理性（5 条）
│   ├── cross-unit/                   # 跨单位对照（18 条）
│   ├── custom/draft/                 # 用户草稿
│   ├── custom/incubator/             # 孵化区候选规则
│   ├── reflections/                  # 反思报告
│   ├── schema/                       # JSON Schema
│   └── registry.json                 # 全量注册表
│
├── feedbacks/                        # 【v6.0】反馈存储
│   └── schema/feedback-schema.json   # 反馈 JSON Schema
│
├── audit_memory/                     # 【v6.0】审核记忆流日志
│
└── tools/
    └── poppler/                      # PDF 转图工具
```

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **四阶段流水线**（v6.0） | 建数据底座 → 人工核对 → 正式审核 → 生成报告，阶段间硬闸门 |
| **数据底座**（v6.0） | 按项目维度建立结构化中间数据，JSON+MD 双格式，纯文件系统存储 |
| **Web 数据编辑器**（v6.0） | 纯 HTML，左图右表对照，双视图编辑，零对话 token |
| **三级粒度多 Agent 并行**（v6.0） | professional/sub/item，与人工分部分项划分一致，最多 115 个独立任务 |
| **增量更新**（v6.0） | 基于 SHA256 哈希对比，仅处理新增/变更文件 |
| **断档检测**（v6.0） | 桩号/日期/编号连续性检查，自动标记缺漏 |
| OCR 识别扫描件 | API-First：Vision API（7 家）→ PaddleOCR → Tesseract |
| 规范逐条对账 | 对着 MH/T 5078 系列逐条比对，每条引规范编号和条款号 |
| 数据质量检测 | 自动识别造假、涂改、异常模式（DQ-REPEAT/JUMP/ALTER/SELF） |
| 逻辑一致性检查 | 10 个子项 57+ 条规则，含监理-施工方跨单位日期对照（9.10，17 条规则） |
| 运算规范审核 | 只做规范性检查，不做数值复算 |
| 自动生成审核报告 | 三级输出：🔴Fatal / 🟡Sanity Check / 🔵Best Practice，含 SVG 图表 |
| 知识分区红线 | 三条红线防幻觉，推理边界决策树，输出前自检清单 |

---

## 规则管理子系统（v6.0 新增）

93 条规则三层分级（L1铁律/L2逻辑一致性/L3业务合理性）+ 跨单位对照特殊作用域，形式化 JSON 存储，支持可视化管理、反馈闭环、LLM 自成长。

### 核心能力

| 能力 | 说明 |
|------|------|
| **三层规则分级**（v6.0） | L1铁律(17)/L2逻辑一致性(73)/L3业务合理性(5)/跨单位对照(18)，共 93 条 |
| **规则管理面板**（v6.0） | Web UI，多维度筛选、可视化规则编辑器、统计仪表盘、反思报告 |
| **规则生命周期**（v6.0） | draft→testing→incubating→active，项目级/全局生效 |
| **反馈闭环**（v6.0） | 漏审/误报反馈→LLM聚类分析→候选规则→管理员审批 |
| **LLM 自成长**（v6.0） | 定时反思调度器生成优化建议，规则效力自监控，低质量规则自动降级 |
| **跨单位对照**（v6.0） | 监理-施工方数据对齐视图，协同确认机制 |

### 规则编辑器

**方式一（推荐，小白专用）**：双击 `templates/rule-editor.html` → 点击「选择 rules 文件夹」→ 选择 skill 目录下的 `rules/` 文件夹 → 即可浏览、编辑、新建和删除规则。**无需启动任何服务**。

**方式二（完整版）**：启动 `rule_admin.py` API 服务，打开 `templates/rule-manager.html`：
```powershell
python scripts/rule_admin.py --port 8765
# 浏览器打开 templates/rule-manager.html
```

**方式三（硬核版）**：直接用文本编辑器修改 `rules/` 下的 JSON 文件。规则文件存储在 skill 目录的 `rules/` 下，跟着 skill 走，所有项目共用同一套规则。

---

## 快速使用

### 1. 安装依赖

```powershell
# 一键安装（Python 依赖 + Poppler + Tesseract）
.\install.ps1
```

或手动安装：

```bash
pip install -r requirements.txt
```

### 2. v6.0 四阶段流水线（推荐，项目级审核）

```powershell
# 阶段 1：建立数据底座（全自动）
python scripts/run_audit.py build "D:\你的项目文件夹" --engine auto

# 阶段 2：人工核对（浏览器中打开 data-editor.html，零 token）

# 阶段 3：正式审核（全自动，支持多 Agent 并行）
python scripts/run_audit.py review "D:\你的项目文件夹" --split-by sub

# 阶段 4：生成审核报告
python scripts/run_audit.py report "D:\你的项目文件夹"
```

### 3. v5.0 单文件审核（保留兼容，快速审核单份资料）

```powershell
# 识别单份资料
python scripts/run_audit.py info "H:\path\to\检验批.pdf"

# 一键审核（OCR + 混淆检测 + Vision 复核）
python scripts/run_audit.py audit "H:\path\to\扫描件.pdf" --out audit_output
```

### 4. 多 Agent 并行审核（大型项目）

```powershell
# 步骤 1：生成任务包
python scripts/run_audit.py review "D:\你的项目文件夹" --split-by item --dry-run

# 步骤 2：并行执行各任务（每个独立进程，可分布到多台机器）
python scripts/run_audit.py review "D:\你的项目文件夹" --task-id TASK-001 --tasks-file "数据底座\审核日志\audit_tasks.json"
python scripts/run_audit.py review "D:\你的项目文件夹" --task-id TASK-002 --tasks-file "数据底座\审核日志\audit_tasks.json"

# 步骤 3：主 Agent 汇总
python scripts/run_audit.py review "D:\你的项目文件夹"

# 步骤 4：生成报告
python scripts/run_audit.py report "D:\你的项目文件夹"
```

### 5. 在 AI 对话中触发

v6.0 流水线触发语句：
- "建数据底座" / "建立项目数据底座"
- "审核这个项目的资料" / "审一下整个项目"
- "人工核对" / "打开数据编辑器"
- "启动审核" / "正式审核"
- "生成审核报告"
- "增量更新" / "补充资料"
- "并行审核" / "多 Agent 审核"
- "按分部审核" / "按分项审核"

v5.0 单文件触发语句：
- "审核这份检验批 / 监理通知单 / 施工日志 / 竣工图"
- "看看这份资料有没有逻辑矛盾"
- "这是扫描件，做 OCR 后审核"

安装触发语句：
- "安装这个skill" / "安装依赖" / "初始化"

---

## 四阶段流水线详解（v6.0）

```
┌──────────────────────────────────────────────────────────┐
│ 阶段 1：建数据底座（全自动）                              │
│   输入：项目文件夹 + 5 项前置信息                         │
│   处理：扫描分类 → OCR → JSON+MD → 质量检测 → 混淆检测 →  │
│         断档检测 → index.json → 复制 Web 模板             │
│   闸门：所有文件 ocr_status = "completed"                │
│   铁律：R-10（数据质量前置）、R-11（全列提取）、R-16      │
├──────────────────────────────────────────────────────────┤
│ 阶段 2：人工核对（人机交互，零 token）                    │
│   输入：数据底座 + Web 数据编辑器                         │
│   处理：左图右表对照 → 逐条确认告警 → 修正 OCR 误读 →     │
│         双视图编辑 → 保存 → 确认完成                      │
│   闸门：所有文件 human_verified = true                   │
│   铁律：R-02（OCR 必复核）、R-20（存疑项核实）            │
├──────────────────────────────────────────────────────────┤
│ 阶段 3：正式审核（全自动，支持多 Agent 并行）             │
│   输入：修正后数据 + 前置信息                             │
│   处理：前置检查 → 任务拆分 → 规范对账 + 逻辑一致性 +     │
│         运算审核 → 审核日志 JSON                          │
│   铁律：R-01/R-03/R-04/R-05/R-06/R-09/R-15/R-17           │
├──────────────────────────────────────────────────────────┤
│ 阶段 4：生成报告（全自动）                                │
│   输入：审核日志                                          │
│   处理：汇总发现 → 四级置信度 → 三级分类 → HTML 模板 →    │
│         SVG 图表                                          │
│   输出：审核报告.html（9 章节强制）                       │
│   铁律：R-07/R-08/R-18/R-19                               │
└──────────────────────────────────────────────────────────┘
```

### 阶段间硬闸门

| 闸门 | 判定字段 | 通过条件 |
|:---:|:---|:---|
| 阶段 1 → 2 | `documents[].ocr_status` | 全部为 "completed" |
| 阶段 2 → 3 | `documents[].human_verified` | 全部为 true |
| 阶段 3 → 4 | `审核日志/AU-*.json` | 审核日志完整生成 |

---

## 多 Agent 并行审核（v6.0 三级粒度）

| 拆分粒度 | `--split-by` 值 | 最大任务数 | 典型场景 |
|:---:|:---:|:---:|:---|
| 专业级 | `professional` | 6 | 跨专业项目快速并行 |
| 分部级（默认） | `sub` | 48 | 常规项目，平衡并行度和任务开销 |
| 分项级 | `item` | 115 | 大型项目，最大化并行度 |

拆分依据：`scripts/audit_config.py` 中的 `SUBDIVISION_HIERARCHY`，源自 references 下 5 个规范文件，覆盖 5 大专业 / 48 分部 / 115 分项。

---

## 知识库连接

| 来源 | 角色 | 覆盖范围 |
|------|------|---------|
| `references/`（内置） | 高速缓存层 | 16 个文件，100+ 条检查项，200+ 个参数阈值 |
| Obsidian vault（外部） | 规范原文库 | 200+ 个规范 markdown 文件，MH/T 5078.1~5078.6 全覆盖 + 石化国标 + 设备规范 |

查询优先级：references 缓存（80% 条款直接覆盖）→ Obsidian 回源读原文（3~5 次/审核）→ 标注"无规范原文支撑"（禁止 WebSearch 兜底）

---

## 铁律体系（20 条，v1.4+）

| # | 铁律 | 简述 |
|---|------|------|
| 1 | 规范可追溯 | 每条意见必引规范编号 + 条款号 |
| 2 | OCR 必复核 | 扫描件识别结果仅辅助 |
| 3 | 运算只审规 | 不做数值复算 |
| 4 | 结论有据 | 不允许"可能不合规"模糊表述 |
| 5 | 标准是归档 | 非"收集齐全" |
| 6 | 拒为伪证背书 | 资料有伪造嫌疑必须明确指出 |
| 7 | 留痕 | 每次审核生成日志文件 |
| 8 | 阴 ≠ 阳 | 没发现问题需写"未发现不符合项" |
| 9 | **逻辑矛盾专项** | 10 个子项 57+ 条规则，含监理-施工方跨单位对照 |
| 10 | **数据质量前置** | 规范对账前先做 4 类数据质量检测 |
| 11 | **全列提取** | 结果列+计算列一起读 |
| 12 | **高程自洽** | 实长 = 桩顶高程 − 桩底高程 |
| 13 | **缺合计行判定** | 无合计行 = 资料非原始记录 |
| 14 | **多参数联检** | 实长/灌入量/充盈系数同时校验 |
| 15 | **原始底稿追溯** | 多资料矛盾时追溯原始记录 |
| 16 | **提取-验证-重试** | 提取后先做行数校验 |
| 17 | **合计值反向验证** | 施工日志合计值 → 与施工记录逐项核对 |
| 18 | **置信度分级** | 高/中/低/存疑，存疑不下确定性结论 |
| 19 | **用户标记闭环** | 追溯 AI 为什么没发现，补充检测规则 |
| 20 | **OCR 存疑核实** | 低置信度项不下确定性结论，汇总为待核实清单 |

---

## OCR 引擎策略（v5.0 API-First）

```
PDF / 图片
   │
   ▼
auto 模式自动检测可用引擎
   │
   ├─ 检测到 Vision API Key → 优先使用 Vision API（云端，按量付费）
   │   ├─ 7 家 Provider：doubao / qwen / glm / kimi / silicon / baidu / openai
   │   └─ 推荐：Doubao Vision Pro（0.003 元/千 token，中文 OCR 最准最快）
   │
   ├─ 无 API Key → 降级为 PaddleOCR（本地，零成本）
   │   ├─ PP-OCRv4 模型，enable_mkldnn=True, cpu_threads=10
   │   └─ 桩号列检测 + Z/2 混淆自动修正
   │
   └─ 无 PaddleOCR → 降级为 Tesseract（本地，需安装）
```

首次使用 Vision API：
```powershell
# 推荐：豆包 Vision Pro
$env:ARK_API_KEY = "你的火山引擎 API Key"

# 验证可用 Provider
python scripts/vision_providers.py --list
```

---

## GitHub 仓库

```bash
# 仓库地址
https://github.com/iliulee/civil-aviation-doc-audit

# 克隆到本地
git clone https://github.com/iliulee/civil-aviation-doc-audit.git
```

---

## 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0~v1.4 | 2026-07-24 | 20 条铁律体系建立，8 步工作流 |
| v1.5 | 2026-07-25 | 五大专业专项审核文件补全（场道/空管/助航/弱电/供油） |
| v1.7 | 2026-07-25 | 前置信息收集 + 文件分类确认 + 批量审核汇总 |
| v1.8 | 2026-07-26 | 三层 9 步工作流重构 |
| v1.9 | 2026-07-27 | 知识分区红线、三级输出格式、9.10 监理-施工方对照、Obsidian 知识库全量覆盖 |
| v4.1 | 2026-07-28 | PaddleOCR 单层主引擎 + Vision API 第三层兜底 |
| v5.0 | 2026-07-29 | API-First 策略 + 7 家 Vision API，彻底移除 RapidOCR |
| **v6.0** | **2026-07-30** | **四阶段流水线 + 数据底座 + Web 编辑器 + 三级粒度多 Agent 并行 + 增量更新 + 断档检测** |
| **v6.1** | **2026-07-31** | **规则管理子系统：93 条规则三层分级 + 反馈闭环 + LLM 自成长 + 跨单位对齐** |
| **v6.1.1** | **2026-07-31** | **审核闸门强化（report 子命令增加 human_verified 检查）+ 字段别名映射（FIELD_ALIAS_MAP 解决中英文字段名不匹配）+ 沉管/拔管时间规则（LG-006/LG-007）** |

### v6.0 核心变更

1. **四阶段流水线**：建数据底座 → 人工核对 → 正式审核 → 生成报告，阶段间硬闸门
2. **数据底座（build_foundation.py）**：JSON+MD 双格式，纯文件系统存储，零数据库依赖
3. **Web 数据编辑器（data-editor.html）**：纯 HTML，左图右表，双视图编辑，零对话 token
4. **项目总览仪表盘（project-dashboard.html）**：从 index.json 读取状态，可视化展示进度
5. **三级粒度多 Agent 并行**：professional/sub/item，与人工分部分项划分一致
6. **增量更新（N-08）**：基于 SHA256 哈希对比，仅处理新增/变更文件
7. **断档检测（N-09）**：桩号/日期/编号连续性检查
8. **run_audit.py 新增 build/review/report 子命令**：统一入口，支持流水线全流程
9. **SVG 图表生成**：审核报告含环形图 + 水平条形图，零外部依赖
10. **审核前置检查闸门**：review_audit.py 自动检查 human_verified，铁律 R-02 落地

### v6.1.1 核心变更（审核闸门与字段别名映射修复）

1. **report 子命令增加 human_verified 闸门**：OCR 完成后若未完成人工核对，拒绝生成审核报告（铁律 R-02/R-20 落地）
2. **字段别名映射（FIELD_ALIAS_MAP）**：rule_engine.py 新增 28 组中英文字段名映射（如"实长"↔"actual_length"），解决规则用中文字段名、数据底座用英文字段名导致规则无法命中问题，桩长自洽校验（LG-001）恢复正常
3. **沉管/拔管时间规则**：新增 LG-006（沉管时间完整性校验）和 LG-007（拔管时间完整性校验）；build_foundation.py 增加 sink_time/pull_time 字段映射
4. **端到端测试通过**：8/8 通过，LG-001 桩长自洽校验正确命中 3 条违规（实长 ≠ 桩顶高程 − 桩底高程）
