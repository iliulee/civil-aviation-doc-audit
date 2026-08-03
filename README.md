# 民航建设施工资料合规审核大师 (civil-aviation-doc-audit)

> 民航工程施工资料合规性审核 Skill v7.2
> 适用：MH/T 5078.1~5078.6-2024 系列 + CCAR-165-R1 + MH 5031-2025 等民航规范
> 五大专业全覆盖：场道 / 空管 / 助航 / 弱电 / 供油
> v7.2 核心特性：数据底座基础能力增强（关键词聚合分类 + 图纸角色解耦 + 电子表状态语义 + 文档级置信度存疑降级 + 表头三路融合识别 + 规格自洁）

---

## 目录结构

```
civil-aviation-doc-audit/
├── SKILL.md                          # 主 Skill 文件（必读，v7.2）
├── README.md                         # 本文件
├── requirements.txt                  # Python 依赖
├── install.ps1                       # 一键安装脚本（Python+Tesseract，PDF转图由PyMuPDF处理）
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
├── scripts/                          # 27 个脚本
│   ├── run_audit.py                  # Skill 入口（含 build/review/report/audit 子命令）
│   ├── build_foundation.py           # 【v6.0】数据底座建立脚本（阶段 1）
│   ├── review_audit.py               # 【v6.0】正式审核流水线脚本（阶段 3，多 Agent 并行）
│   ├── audit_config.py               # 【v6.0】分部分项配置（5 专业 / 48 分部 / 115 分项）
│   ├── signature_check.py             # 【v7.0】签字一致性检测（pHash + SSIM 双指标）
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
│   ├── llm_client.py                 # 【v7.2】LLM 公共客户端（分类语义辅助，复用 LLM_API_URL/KEY/MODEL）
│   ├── import_corrections.py         # 【v7.2】自成长导入（人工修正记录 → 分类/表头候选词条回流）
│   ├── audit_memory.py               # 【v6.0】审核记忆流（JSONL 事件日志）
│   ├── test_rule_engine.py           # 【v6.0】规则引擎单元测试（6/6 通过）
│   ├── test_cross_unit_perf.py       # 【v6.0】跨单位性能测试（4/4 通过）
│   └── test_rule_subsystem_integration.py  # 【v6.0】子系统全链路集成测试（7/7 通过）
│
├── templates/                        # HTML 模板层
│   ├── audit-scope-template.html     # 审核范围清单模板（v1.9）
│   ├── data-editor.html              # 【v7.2】Web 数据编辑器（精密仪表盘+文档属性/表头映射面板）
│   ├── project-dashboard.html        # 【v6.0】项目总览仪表盘
│   ├── rule-editor.html              # 【v6.0】离线规则编辑器（小白友好）
│   ├── rule-manager.html             # 【v6.0】规则管理面板（4 标签页，可视化编辑器）
│   ├── feedback-collector.html       # 【v6.0】反馈收集组件（漏审/误报）
│   ├── alignment-view.html           # 【v6.0】跨单位数据对齐视图
│   ├── pdf.min.js                    # 【v6.0】PDF.js 离线预下载
│   └── pdf.worker.min.js             # 【v6.0】PDF.js worker
│
├── rules/                            # 【v6.0】规则文件库（93 条）
│   ├── L1-iron/                      # L1 铁律（17 条）
│   ├── L2-logic/                     # L2 逻辑一致性（72 个文件，71 条 active + 1 条 deprecated，含 IR-012/013/014、CU-001~018、LG-006/007）
│   ├── L3-business/                  # L3 业务合理性（5 条）
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
└── tools/                              # 工具目录（poppler 已移除，PyMuPDF 替代）
```

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **数据底座基础能力增强**（v7.2） | 关键词聚合分类 + 图纸角色解耦 + 电子表状态语义 + 文档级置信度存疑降级 + 表头三路融合识别 + 规格自洁 |
| **data-editor 精密仪表盘**（v7.1） | 诊断面板 + 文档树优化 + 状态分级 + 问题视图 + 批量应用建议值 + 精密仪表盘视觉 |
| **四阶段流水线** | 建数据底座 → 人工核对 → 正式审核 → 生成报告，阶段间硬闸门 |
| **三层JSON数据底座**（v7.0） | structured_rows + full_text + page_map 三层结构，差异提取 |
| **文档关联图谱**（v7.0） | link_graph.json 自动构建，审核时精准加载关联文档 |
| **签字一致性检测**（v7.0） | pHash + SSIM 双指标，可选前置条件，报告内嵌对比图 |
| **Web 数据编辑器**（v6.0） | 纯 HTML，左图右表对照，双视图编辑，零对话 token |
| **三级粒度多 Agent 并行**（v6.0） | professional/sub/item，与人工分部分项划分一致，最多 115 个独立任务 |
| **增量更新**（v6.0） | 基于 SHA256 哈希对比，仅处理新增/变更文件 |
| **断档检测**（v6.0） | 桩号/日期/编号连续性检查，自动标记缺漏 |
| OCR 识别扫描件 | API-First：Vision API（7 家）→ PaddleOCR → Tesseract |
| 规范逐条对账 | 对着 MH/T 5078 系列逐条比对，每条引规范编号和条款号 |
| 数据质量检测 | 自动识别造假、涂改、异常模式（DQ-REPEAT/JUMP/ALTER/SELF） |
| 逻辑一致性检查 | 10 个子项 71 条规则，含监理-施工方跨单位日期对照（9.10，18 条 CU 规则） |
| 运算规范审核 | 只做规范性检查，不做数值复算 |
| 自动生成审核报告 | 三级输出：🔴Fatal / 🟡Sanity Check / 🔵Best Practice，含 SVG 图表 |
| 知识分区红线 | 三条红线防幻觉，推理边界决策树，输出前自检清单 |

---

## 功能特性

### v7.2 新增
- 🔑 **关键词聚合分类（无硬编码副本）**：从 references/classification-terms.json + 91 条规则 trigger_when.doc_type + FIELD_ALIAS_MAP 三真相源运行时聚合，带来源标注可追溯
- 🧭 **三级判定 + 人工闸门 + 简化自成长**：关键词快筛 → LLM 语义（弱/多专业/无命中才上）→ 确认；C-01 闸门强制检查（分类未确认不进入审核，--force 可跳过）；人工改分类自动追加 candidate 词条，data-editor 文档属性 Tab 确认，`import_corrections.py --from-index` 回流全局词表
- 🖼️ **图纸角色解耦**：is_drawing 标签与 C-01 三分法角色正交，施工阶段图纸默认依据，竣工阶段默认审核，build 阶段终端高亮提示
- 🧾 **电子表状态语义修正**：xlsx/非扫描 PDF 在 editor+dashboard 统一显示"无需OCR"确定态，不谎报 OCR%
- ⚠️ **文档级置信度存疑降级**：糊件照常可审核，规则结论 severity 自动标存疑入 R-20 清单；总览建议重扫 TOP 10 纯文字不强制
- 🔀 **表头三路融合**：别名匹配 + 列特征+桩基数学链（实长=桩顶-桩底）联合约束 + 人工确认，OCR 烂/列顺序颠倒也能对上
- 🧼 **规格自洁**：JSON Schema 示例统一、验收编号补齐、C-15 表述修正、模板文件名对齐真实目录

### v7.1 新增
- 🎛️ **诊断面板**：可折叠，实时显示加载过程、文档结构、数据问题，辅助调试与问题定位
- 📂 **文档树优化**：非文档文件自动进入折叠区，主树仅显示有效审核文档，进度计数准确
- 🎯 **状态语义分级**：五种 CSS 绘制状态图标（已核对/待核对/需重扫/非文档/加载失败），tooltip 说明原因
- ⚠️ **问题视图 + 批量操作**：按区域/类型/风险聚合质量告警，支持逐条修正、批量应用建议值、标记已处理
- 🔗 **四种加载方式**：File System Access API（首选）→ 拖拽加载（次选）→ 手动选择（兜底）→ HTTP 测试模式
- 🔒 **安全闸门强化**：确认按钮在非文档/无数据时禁用并显示原因，快捷键 Ctrl+Enter
- 🎨 **精密仪表盘视觉**：深墨蓝/炭灰骨架色、工程网格底纹、等宽数字、双字体系统、微动效反馈
- 🔄 **数据结构兼容层**：自动检测 structured_rows 和旧版 rows 格式，确保向后兼容

### v7.0 新增
- 📊 **三层 JSON 数据底座**：structured_rows（规则引擎）+ full_text（LLM 审核）+ page_map（人工定位）
- 🔗 **文档关联图谱**：自动构建 link_graph.json，审核时精准加载关联文档
- 🖋️ **签字一致性检测**：pHash + SSIM 双指标，检测代签/笔迹异常（可选）
- 📋 **data-editor 升级**：三栏式界面，表格编辑 + 原文预览 + 图纸截图
- ⚡ **差异化提取**：非扫描 PDF 直接文本提取（秒级），Excel 仅记元数据
- 🚪 **human_verified 分层闸门**：非扫描件自动通过，扫描件强制人工核对
- 🖼️ **图纸截图**：含图 PDF 自动截图存 `_images/`，data-editor 可预览

---

## 规则管理子系统（v6.1 新增）

93 条规则三层分级（L1铁律/L2逻辑一致性/L3业务合理性），形式化 JSON 存储，支持可视化管理、反馈闭环、LLM 自成长。

### 核心能力

| 能力 | 说明 |
|------|------|
| **三层规则分级**（v6.0） | L1铁律(17)/L2逻辑一致性(71 active + 1 deprecated)/L3业务合理性(5)，共 93 条 |
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
# 一键安装（Python 依赖 + Tesseract，PDF 转图由 PyMuPDF 处理）
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

### 签字一致性检测（可选）

```bash
# 审核时启用签字检测
python scripts/run_audit.py review "D:\项目文件夹" --check-signatures

# 或在四阶段流水线中
python scripts/review_audit.py "D:\项目文件夹" --check-signatures
```

需要额外依赖：
```bash
pip install imagehash scikit-image
```

### 规则管理

```bash
# 双击启动规则管理面板
rule-manager.bat

# 或手动启动
python scripts/rule_admin.py --port 8765
# 浏览器打开 http://127.0.0.1:8765/
```

规则文件位于 `rules/` 目录：
- `L1-iron/`：铁律（不可违反的强制性条款）
- `L2-logic/`：逻辑规则（跨文档/跨资料一致性）
- `L3-business/`：业务规则（分部分项专项要求）

规则编辑方式：
1. Web 面板：双击 `rule-manager.bat`，可视化编辑（推荐小白使用）
2. 离线编辑：浏览器打开 `templates/rule-editor.html`，选择 `rules/` 文件夹
3. 直接改 JSON：编辑 `rules/` 下对应文件

---

## 四阶段流水线详解（v6.0）

```
┌──────────────────────────────────────────────────────────┐
│ 阶段 1：建数据底座（全自动）                              │
│   输入：项目文件夹 + 5 项前置信息                         │
│   处理：扫描分类 → OCR → 三层JSON → 质量检测 → 混淆检测 →  │
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
| 9 | **逻辑矛盾专项** | 10 个子项 71 条规则，含监理-施工方跨单位对照 |
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
   │   ├─ 推荐：Doubao Vision Pro（0.003 元/千 token，中文 OCR 最准最快）
   │   └─ ⚠️ 使用前自动列出可用 Provider 供参考
   │
   ├─ 无 API Key → 降级为 PaddleOCR（本地，零成本）
   │   ├─ ⚠️ 需 Python 3.12 及以下（PaddlePaddle 最高支持 Python 3.12）
   │   ├─ PP-OCRv4 模型，enable_mkldnn=True, cpu_threads=10
   │   └─ 桩号列检测 + Z/2 混淆自动修正
   │
   ├─ 无 PaddleOCR → 降级为 Tesseract（本地，需安装）
   │
   └─ 无 Tesseract → 降级为 AGENT 内置 Vision 模型（最终兜底）
       ├─ 通过 TRAE Read 工具直接读取图片，用 AI 自身 Vision 能力识别
       ├─ 适用于单页或少页 OCR 复核，速度较慢但零依赖
       └─ 不适于大批量 OCR（>10 页建议用 Vision API 或 PaddleOCR）
```

Vision API 支持以下 7 家 Provider：

| Provider | 名称 | 环境变量 | 默认模型 | 价格（元/千token） |
|:---:|:---|:---|:---|:---:|
| doubao | 豆包（推荐） | `ARK_API_KEY` | doubao-vision-pro-32k | **0.003** |
| silicon | 硅基流动 | `SILICONFLOW_API_KEY` | Qwen2-VL-72B-Instruct | 0.004 |
| qwen | 通义千问 | `DASHSCOPE_API_KEY` | qwen-vl-max | 0.008 |
| baidu | 百度千帆 | `BAIDU_API_KEY` | ernie-4.5-vl-preview | 0.008 |
| glm | 智谱 | `ZHIPU_API_KEY` | glm-4v-plus | 0.010 |
| kimi | Kimi | `MOONSHOT_API_KEY` | moonshot-v1-8k-vision | 0.012 |
| openai | OpenAI | `OPENAI_API_KEY` | gpt-4o | 0.015 |

首次使用 Vision API：
```powershell
# 推荐：豆包 Vision Pro
$env:ARK_API_KEY = "你的火山引擎 API Key"

# 验证可用 Provider
python scripts/vision_providers.py --list
```

> **使用 Vision API 前会提醒**：系统自动执行 `python scripts/vision_providers.py --list`，列出当前可用的 Provider 及其价格，供用户参考选择。无可用 Provider 时自动降级本地引擎。

### 离线场景：安装 PaddleOCR

> ⚠️ **PaddlePaddle 最高支持 Python 3.12**。如果当前 Python 版本 ≥ 3.13，需要先降级 Python 到 3.12。

```powershell
python3.12 -m pip install paddleocr==2.8.1 paddlepaddle==2.6.2 opencv-python
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
| **v7.0** | **2026-07-31** | **三层JSON数据底座 + 文档关联图谱 + 签字一致性检测 + data-editor三栏升级** |
| **v7.1** | **2026-08-01** | **data-editor 精密仪表盘升级：诊断面板 + 文档树优化 + 状态分级 + 问题视图 + 批量应用建议值 + 精密仪表盘视觉** |
| **v7.2** | **2026-08-01** | **数据底座基础能力增强：关键词聚合分类 + 图纸角色解耦 + 电子表状态语义 + 文档级置信度存疑降级 + 表头三路融合识别 + 规格自洁** |

### v7.2 核心变更

1. **关键词聚合分类（无硬编码副本）**：从 references/classification-terms.json + 91 条规则 trigger_when.doc_type + FIELD_ALIAS_MAP 三真相源运行时聚合，带来源标注可追溯
2. **三级判定 + 人工闸门 + 简化自成长**：单专业强命中直接用，弱/多专业/无命中才上 LLM；人工改分类自动追加 candidate 词条，下次确认即生效
3. **图纸角色解耦**：is_drawing 标签与 C-01 三分法角色正交，stage 决定默认角色，build 阶段终端提示竣工图纸，必过人工确认闸门
4. **电子表状态语义修正**：editor + dashboard 双端对 xlsx/非扫描 PDF 统一显示"无需OCR"确定态，不再谎报 OCR 百分号
5. **文档级置信度存疑降级**：糊件可审核，触发的规则结论 severity 自动入 R-18 存疑级 + R-20 待核实清单；总览建议重扫 TOP 10 纯文字不强制
6. **表头三路融合**：别名匹配 + 列特征（桩号/日期/范围）+ 桩基数学链（实长=桩顶−桩底）交叉约束，OCR 烂/列顺序颠倒也能正确映射
7. **规格自洁**：PROJECT_SPEC 四处内部矛盾清零（JSON Schema 示例统一、验收编号补齐、C-15 表述修正、模板文件名对齐真实目录）

### v7.1 核心变更

1. **诊断面板**：可折叠，实时显示加载过程和文档结构，辅助调试
2. **文档树优化**：非文档文件自动过滤，主树仅显示有效审核文档
3. **状态语义分级**：五种 CSS 状态图标，取代单一红叉
4. **问题视图 + 批量应用建议值**：按区域聚合质量告警，一键批量修正
5. **四种加载方式**：File System Access API / 拖拽 / 手动选择 / HTTP
6. **安全闸门强化**：确认按钮在非文档/无数据时禁用并显示原因
7. **精密仪表盘视觉**：深墨蓝/炭灰骨架色、工程网格底纹、等宽数字、双字体系统
8. **数据结构兼容层**：自动检测 structured_rows 和旧版 rows 格式

### v7.0 核心变更

1. **三层JSON数据底座**：structured_rows + full_text + page_map 三层结构，取消 MD 生成
2. **差异化提取**：非扫描 PDF 直接文本提取（秒级），Excel 仅记元数据
3. **文档关联图谱**：link_graph.json 自动构建，审核时精准加载关联文档
4. **签字一致性检测**：pHash + SSIM 双指标，可选前置条件，报告内嵌对比图
5. **data-editor 三栏升级**：文档树 + 表格/原文/图纸三 Tab，快捷键确认
6. **human_verified 分层闸门**：非扫描件自动通过，扫描件强制人工核对
7. **图纸截图**：含图 PDF 自动截图存 `_images/`，data-editor 可预览

### v6.1.1 核心变更（审核闸门与字段别名映射修复）

1. **report 子命令增加 human_verified 闸门**：OCR 完成后若未完成人工核对，拒绝生成审核报告（铁律 R-02/R-20 落地）
2. **字段别名映射（FIELD_ALIAS_MAP）**：rule_engine.py 新增 28 组中英文字段名映射（如"实长"↔"actual_length"），解决规则用中文字段名、数据底座用英文字段名导致规则无法命中问题，桩长自洽校验（LG-001）恢复正常
3. **沉管/拔管时间规则**：新增 LG-006（沉管时间完整性校验）和 LG-007（拔管时间完整性校验）；build_foundation.py 增加 sink_time/pull_time 字段映射
4. **端到端测试通过**：8/8 通过，LG-001 桩长自洽校验正确命中 3 条违规（实长 ≠ 桩顶高程 − 桩底高程）
