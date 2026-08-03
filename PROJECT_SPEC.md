# PROJECT_SPEC — 民航施工资料合规审核 Skill v7.2

> 文档版本：v2.6 | 创建日期：2026-07-29 | 最后更新：2026-08-03 | 状态：v7.1 已实施 · v7.2 规格制定中（C7 通用表格提取已实现）
>
> 本文档是项目的唯一权威规格说明，覆盖全部已有功能（v5.0）、v7.0 三层JSON数据底座 + 文档关联图谱 + 签字一致性检测、v7.1 data-editor 精密仪表盘升级、v7.2 数据底座基础能力增强（分类聚合/图纸角色/状态语义/置信度降级/表头识别/通用表格提取/规格自洁）。

---

## 一、项目概述

### 1.1 项目定位

面向民航运输机场专业工程建设项目，基于 MH/T 5078.1~5078.6-2024 资料管理规程体系，提供从"OCR 识别 → 数据底座建立 → 人工核对 → 规范对账 → 逻辑一致性检查 → 审核报告生成"的全链路施工资料合规审核能力。

五大专业全覆盖：场道工程、空管工程、目视助航设施、弱电系统、供油工程。

### 1.2 版本演进

| 版本 | 核心能力 | 驱动来源 |
|:---|:---|:---|
| v1.0~v1.4 | 20 条铁律体系 + 基础 OCR + 规范对账 | 实际审核问题逐条沉淀 |
| v1.5 | 五专业全覆盖 + Obsidian 集成 | 用户要求全面审查 |
| v1.7~v1.9 | 前置信息 + OCR 存疑核实 + 三级输出 + 多 Agent 并行 + 知识分区红线 | 用户反馈 + 对标分析 |
| v4.1 | PaddleOCR 单层主引擎 + Vision API 兜底 | OCR 性能优化 |
| v5.0 | API-First 策略 + 7 家 Vision API | 成本与准确性平衡 |
| **v6.0** | **数据底座 + Web 编辑器 + 项目总览 + 四阶段流水线** | **上下文管理 + 人工核对 + 增量更新** |
| **v6.1** | **规则管理子系统（93 条规则三层分级 + 反馈闭环 + LLM 自成长 + 跨单位对齐）** | **规则形式化存储 + 可视化管理 + 自成长机制** |
| **v6.1.1** | **审核闸门强化 + 字段别名映射 + 沉管/拔管时间规则** | **修复 OCR 后跳过人工核对、规则字段名不匹配、缺少时间计算三大问题** |
| **v7.0** | **三层JSON数据底座 + 文档关联图谱 + 签字一致性检测 + data-editor三栏升级** | **数据完整性 + 签字审核 + 精准上下文加载** |
| **v7.1** | **data-editor 精密仪表盘升级：诊断面板、文档树优化、状态分级、问题视图、批量应用建议值、精密仪表盘视觉** | **UI/UX 全面重做，提升核对效率和视觉专业度** |
| **v7.2** | **数据底座基础能力增强：关键词聚合分类、图纸角色解耦、电子表状态语义、文档级置信度存疑、表头三路融合识别、通用表格提取、规格自洁** | **从"能跑"到"稳"——解决分类硬编码、图纸角色硬判、状态语义误导、低置信卡流程、表头识别脆弱、非桩基类表格不结构化七大基础问题** |

### 1.3 v7.0 核心变更

v7.0 不是对现有功能的推倒重来，而是在 v6.0 四阶段流水线基础上，对数据底座进行三层重构，新增签字审核和文档关联能力：

1. **三层JSON数据底座**：structured_rows（规则引擎）+ full_text（LLM 审核）+ page_map（人工定位），取消 MD 生成
2. **差异化提取**：非扫描PDF直接文本提取（秒级），Excel仅记元数据，含图PDF自动截图
3. **文档关联图谱**：link_graph.json 自动构建，审核时按关联精准加载文档，控制上下文
4. **签字一致性检测**：pHash + SSIM 双指标，可选前置条件，报告内嵌base64对比图
5. **data-editor 三栏升级**：文档树 + 表格/原文/图纸三Tab，图纸预览、快捷键确认
6. **human_verified 分层闸门**：非扫描件自动通过，扫描件强制人工核对

### 1.3.1 v6.1 核心变更（规则管理子系统）

v6.1 在 v6.0 基础上新增规则管理子系统，将原本散落在 markdown 文档中的规则重构为形式化、可管理、可自成长的子系统（当前共 93 条规则）：

1. **三层规则分级**：L1 铁律（17 条）/ L2 逻辑一致性（71 条 active + 1 条 deprecated）/ L3 业务合理性（5 条），共 93 条规则
2. **规则形式化存储**：每条规则以独立 JSON 文件存储，含完整元数据（trigger_when/check_expr/error_template/changelog/stats）
3. **规则管理面板**：Web UI，多维度筛选、可视化规则编辑器、统计仪表盘、反思报告
4. **规则生命周期**：draft → testing → incubating → active，支持项目级/全局生效
5. **反馈闭环**：漏审/误报反馈 → LLM 聚类分析 → 候选规则 → 管理员审批
6. **LLM 自成长**：定时反思调度器生成优化建议，规则效力自监控，低质量规则自动降级
7. **跨单位对照增强**：监理-施工方数据对齐视图，哈希索引 + 分块处理（1000 桩位 join < 50ms）

### 1.3.2 v6.1.1 核心变更（审核闸门与字段别名映射修复）

v6.1.1 修复用户重新安装 skill 后测试发现的 3 个严重问题：

1. **OCR 后人工核对闸门强化**（`run_audit.py` 的 `cmd_report` 函数）
   - 问题：OCR 完成后可直接生成审核报告，跳过阶段 2 人工核对
   - 修复：在 `report` 子命令中增加 `human_verified` 闸门检查，未全部为 `true` 且非 `--force` 时拒绝生成报告
   - 铁律落地：R-02（OCR 必复核）、R-20（OCR 存疑核实）

2. **规则字段别名映射**（`rule_engine.py` 的 `FIELD_ALIAS_MAP`）
   - 问题：规则文件用中文字段名（如"实长"），数据底座用英文字段名（如"actual_length"），导致规则无法命中数据，桩长计算缺失
   - 修复：新增 `FIELD_ALIAS_MAP` 映射表（28 组中英文对照），在 `SingleDocChecker.check_single_doc` 构造 context 时自动注入中文别名
   - 影响规则：LG-001（高程自洽）、IR-012（高程自洽）、LG-1002（充盈系数自洽）等涉及桩长/高程计算的规则

3. **沉管/拔管时间规则**（`LG-006.json` + `LG-007.json` + `build_foundation.py`）
   - 问题：审核结果缺少沉管时间、拔管时间的完整性检查
   - 修复：新增 LG-006（沉管时间完整性校验）和 LG-007（拔管时间完整性校验）两条 L2 规则；在 `build_foundation.py` 的 `PILE_HEADER_KEYWORDS` 和 `PILE_FIELDS` 中增加 `sink_time`/`pull_time` 字段映射

> 详细设计见 [第十一章 规则管理子系统 v6.1](#十一规则管理子系统-v61)

### 1.3.3 v7.1 核心变更（data-editor 精密仪表盘升级）

v7.1 在 v7.0 三栏式数据编辑器基础上，对 data-editor.html 进行 UI/UX 全面重做，将界面从"能跑就行"的后台默认风格升级为"精密仪表盘"级别，同时修复了文档树混入非文档文件、状态分级缺失、确认按钮逻辑陷阱等关键问题：

1. **诊断面板**：页面顶部可折叠诊断面板，实时显示加载过程、文档结构、数据问题，辅助调试和问题定位
2. **文档树优化**：严格的非文档判定逻辑（isNonDoc 函数），非文档文件自动进入折叠区，主树仅显示有效审核文档；进度计数仅统计有效文档
3. **状态语义分级**：五种 CSS 绘制状态图标（已核对/待核对/需重扫/非文档/加载失败），取代单一红叉，配合 tooltip 说明状态原因
4. **问题视图 + 批量应用建议值**：按类型/区域/风险等级聚合质量告警与 OCR 存疑项，支持逐条修正、批量应用建议值、标记已处理
5. **四种加载方式**：File System Access API（首选）→ 拖拽加载（次选）→ 手动选择 JSON（兜底）→ HTTP 测试模式（仅 http 协议）
6. **精密仪表盘视觉风格**：深墨蓝/炭灰骨架色、工程网格底纹、语义化信号色、等宽数字、双字体系统、微动效反馈、树节点 hover/选中动效
7. **安全闸门强化**：确认按钮仅当文档为有效文档且有结构化数据时才启用，否则禁用并显示原因；支持快捷键 Ctrl+Enter
8. **数据结构兼容层**：自动检测新版三层 JSON 结构（structured_rows）和旧版 rows 格式，优先使用 structured_rows，缺失时从 rows 重建

> 详细设计见 [4.2 Web 数据编辑器（data-editor.html）—— v7.1 升级](#42-web-数据编辑器data-editorhtml)

### 1.3.4 v7.2 核心变更（数据底座基础能力增强）

v7.2 不是引入新模块，而是把 v7.0/v7.1 已跑通的四阶段流水线在"数据底座入口"和"审核输出质量闸门"两处做加固。目标：让一份新资料进入系统后，**分类不瞎、图纸不误、状态不骗、低置信不中断流程、表头 OCR 烂也能对上、非桩基类表格也能结构化、文档内部不自相矛盾**。

每条改动明确标注落点（既有概念/既有章节 + 具体代码锚点）。

---

#### C3｜状态语义：电子表/非扫描PDF 显示"无需OCR"

| 项目 | 说明 |
|------|------|
| **问题现象** | Excel xlsx 在 data-editor 和 project-dashboard 中显示 `ocr_confidence=100% / ocr_engine=openpyxl`，语义误导——用户以为"这份电子表也走了 OCR 识别且准确率 100%"，但实际是 openpyxl 直接读单元数据，根本没走 OCR。不报错，但长期用会让用户混淆"电子表直读"和"OCR 识别"，降低输出严谨性。 |
| **落点代码** | [build_foundation.py](file:///d:/2026年7月22日%20民航资料skill/scripts/build_foundation.py) 写入 index.json 时透传 `sniff_document()` 已有的 `extraction_method`；data-editor.html 第 1586~1598 行 `statusTooltip()`；[project-dashboard.html](file:///d:/2026年7月22日%20民航资料skill/templates/project-dashboard.html#L760-L776) 第 767 行 `OCR%` 列渲染。 |
| **落点既有概念** | 复用 §4.1.2 差异化提取（pymupdf/ocr/docx/image/excel/unknown 六态）、复用 v7.1 五种状态图标，不改数据结构，只新增一字段 `extraction_mode: "ocr" | "text_pdf" | "docx" | "meta_xlsx" | "image" | "unknown"` + 两前端渲染分支。 |
| **用户看到什么** | data-editor 状态栏显示"电子表·已记元数据·无需OCR"（中性信息色，不是红）；dashboard 的 OCR% 列对 meta_xlsx/text_pdf 显示"—"或"免OCR"文字格，不显示 100%。 |
| **硬约束** | "不适用≠失败、不得用红色"——v7.1 的状态图标里没有"免OCR"的语义，这个不改 status-icon，只改文案和 tooltip，向后完全兼容。 |
| **肉眼验收** | V-67：对标杆测试3的 xlsx，editor + dashboard 均不再出现 `100%` 数字或 OCR 相关表述，改显确定态"无需OCR"文案。扫描件 PDF 仍正常显示 `OCR XX%`，未被误伤。 |

---

#### C6｜规格自洁（文档内部矛盾清零）

| 项目 | 说明 |
|------|------|
| **落点** | 本 spec 自身 §4.1、§8、§C-15、§十二 模板引用四处。 |
| **修改清单** | 1. §4.1 单文件 JSON Schema 示例：统一为三层结构（structured_rows / full_text / page_map），`rows` 保留为向后兼容 alias，示例下方新增"兼容层说明"注释。<br>2. §8.2 验收编号（原 T-53~T-72 断层）：补齐编号连续，link_graph/签字/图纸角色/整改台账四张同步矩阵纳入。<br>3. 约束 C-15"统一HTML唯一交付物"：改为"HTML为主交付物，审核报告页面支持浏览器打印导出 PDF；整改通知单、合规性检查清单作为独立 Tab 以 HTML 形式嵌入同一份报告，允许另存为附件"——保持单文件交付同时不丢真实导出需求。<br>4. 模板文件名：将所有对 `html-report-template.md` 的引用改为 `references/html-report-template.html`（真实文件名）。 |
| **肉眼验收** | 全文档 grep `"rows"` `"template"` `"T-5"` `"C-15"` 四处关键词，没有新的矛盾。 |

---

#### C2｜图纸角色：解耦"是不是图"与"审不审"

| 项目 | 说明 |
|------|------|
| **问题现象** | v7.1 中"05 地基处理平面图.pdf"被兜底归为 audited_files→通用资料→其他资料→显示 0 行 0 列。图纸能不能审，不取决于"是不是图"，而取决于"是什么阶段的什么角色的图"（施工阶段设计依据图=依据文件，不审；竣工阶段竣工图=被审对象，要审；过程示意图=依据文件）。 |
| **落点代码** | [classify_file()](file:///d:/2026年7月22日%20民航资料skill/scripts/build_foundation.py#L244-L283) 第 244~283 行；`preconditions.stage`；C-01 文件分类确认。 |
| **落点既有概念** | 复用 C-01 三分法（audited/reference/excluded）、复用 §2.2 preconditions.stage（施工过程/验收/竣工移交）。 |
| **改动内容** | 1. index.json document 增字段 `is_drawing: bool` 和 `drawing_type: null \| "design_basis" \| "as_built" \| "process_sketch"`（三细分类型由文件名模式+人工确认得出，不作硬判据；`drawing_type=null` 即非图）。<br>2. 删除"图纸→默认依据文件"的死规则（实际 v7.1 本就没这条死规则，C-01 闸门里让用户过就行），改为 stage→default_role 映射：施工阶段 is_drawing→默认 reference_files；竣工移交阶段 is_drawing→默认 audited_files；示意图（文件名含"示意/方案"）→默认 reference_files。所有默认值必过 C-01 人工分类确认闸门，`file_classification_confirmed:false` 时 Phase 2 不启动。<br>3. build 阶段终端提示：当 stage∈{竣工,移交} 且 `is_drawing=true` 时，打印高亮提示 `"检测到竣工阶段图纸 X 份，已默认纳入 audited_files，请在 C-01 确认"`。 |
| **用户看到什么** | C-01 分类确认面板中，图纸类文件有 🖼️ 图标前缀，默认角色列显示"竣工默认 audited / 施工默认 reference"，可一键切换。 |
| **硬约束** | is_drawing 标签与角色正交——同一 PDF 换 stage 后角色可以不同，但 is_drawing=true 标签不变；默认值必过人工闸门，不得自动定死。 |
| **肉眼验收** | V-66：对"地基处理平面图.pdf"，施工阶段项目 C-01 默认为 reference_files；把 stage 改成"竣工移交"重新 build，同一文件 C-01 默认为 audited_files 并弹出终端提示；两次文件 is_drawing=true 标签均为 true。 |

---

#### C1｜分类：三级分类器（关键词聚合 + LLM语义 + 人工闸门 + 简化自成长）

| 项目 | 说明 |
|------|------|
| **问题现象** | CFG桩 xlsx 因 [PROFESSIONAL_RULES 硬编码表](file:///d:/2026年7月22日%20民航资料skill/scripts/build_foundation.py#L72-L78) 里只有"碎石桩"没有"CFG/强夯/水泥土/地基处理"，被兜底进通用资料/其他，导致 LG-001/IR-012 等碎石桩桩长自洽规则触发不了——分类错=后续审核全错，是入口级 bug。根因：PROFESSIONAL_RULES 是 references 专家知识的过时副本，双写必漏。 |
| **落点代码** | build_foundation.py 第 72~112 行 PROFESSIONAL_RULES/PILE_HEADER_KEYWORDS（PILE_HEADER_KEYWORDS 保留作为解析层用，分类不再读它）；classify_file()；新建 `references/classification-terms.json`；data-editor 新增"文档属性"面板（可编辑 professional/subcategory/doc_type + 确认状态）。 |
| **落点既有概念** | 单一真相源（P-约束）：只允许 references/classification-terms.json + 91 条规则 trigger_when.doc_type + FIELD_ALIAS_MAP 三个源；人工闸门（P-约束）：自动判定带 `classification_source: "keyword" \| "llm" \| "human"` + `classification_confidence: float` + `human_confirmed: false`。 |
| **改动内容** | 1. 新建 `references/classification-terms.json`，结构 `{professional: [{term, source, weight: "core"|"weak"}]}`。首次初始化从 91 条规则的 trigger_when.doc_type 抽关键词 + 从 references/*-audit.md 各"关键资料"段标题手动摘（不做自然语言聚合，防噪音）。<br>2. 三级判定：① build 启动时从三真相源运行时聚合成内存词表（带来源标注，可追溯"CFG桩→来源于LG-006.json trigger_when.doc_type"）；② 未命中或命中≥2专业或只有 weak 词命中 → LLM 看"文件名+前 5 行文本摘要"以 references/classification-terms.json + specification-mapping.md 为 RAG 判专业，输出置信度（单专业强命中→直接用，不上 LLM，省成本）；③ 结果写 index.json。<br>3. 人工闸门：data-editor 文档树对 `human_confirmed=false` 或 `confidence<0.7` 的条目高亮标黄"AI分类·待确认"，点击文档可在属性面板一键改专业/子类/doc_type，改完 `human_confirmed=true`。<br>4. 简化版自成长（不是全管道）：人工改分类时，若改法与当前 AI 分类不同，把"文件名关键词模式 → 新专业 + 状态=candidate"追加到 classification-terms.json；下次 build 遇到相同关键词模式，AI 自动给出候选分类、C-01 面板高亮"候选分类，请确认"→确认后状态变 active。不需要"影子模式/LLM 分析聚类"等自动化管道。 |
| **LLM 后端** | 新建 `scripts/llm_client.py` 公共 client，复用 feedback_analyzer.py 已有的环境变量 `LLM_API_URL/KEY/MODEL`，避免双写。无网络/无 API Key 时降级为"全部需人工确认"，不中断流程。 |
| **肉眼验收** | V-64：build_foundation.py 中 grep 不到与 classification-terms.json 重复的死 PROFESSIONAL_RULES 表（该表改为启动时从聚合源生成的内存常量，不是源码死表）。<br>V-65：标杆项目 CFG桩 xlsx 归入 01_场道工程/施工记录/CFG桩施工记录，index.json 可见 classification_source + confidence；故意放一个 references 里没出现过的新术语文件，LLM 路给出专业+置信度，并在总览标"待确认"；断网降级→所有分类标"待确认"不报错。<br>V-70：人工把某文件从"通用"改到"场道"，classification-terms.json 多出一条 candidate 记录；下次重跑同模式文件→C-01 面板显示候选分类，确认后变 active。 |

---

#### C5｜表头识别：三路融合（模板别名 + 列特征+数学链约束 + 人工沉淀）（LLM 路 P2，v7.2 P1 不上）

| 项目 | 说明 |
|------|------|
| **问题现象** | PILE_HEADER_KEYWORDS 是固定字符串匹配，扫描件表头被印章压住/列顺序颠倒/OCR 认烂就整列废。土工程/混凝土工程的列顺序随机率更高。 |
| **落点代码** | build_foundation.py [parse_pile_table_with_headers()](file:///d:/2026年7月22日%20民航资料skill/scripts/build_foundation.py#L504-L530) / parse_pile_rows_heuristic()；FIELD_ALIAS_MAP；文件 JSON 增 `raw_headers: []` 和 `header_mapping: {original_header: {slot, source, confidence}}`；data-editor 增"表头映射"Tab（可编辑每列对应哪个标准槽位）。 |
| **落点既有概念** | 复用 FIELD_ALIAS_MAP（v6.1.1）；复用 L2 逻辑规则的数学关系链（R-12/IR-012 的 `实长 = 桩顶 - 桩底`；R-14/IR-014 的 三链联检：实长→灌入量→充盈系数），作为路2 数据特征的交叉约束，不是独立猜一列。 |
| **改动内容** | 1. 结构化槽位 schema：从 FIELD_ALIAS_MAP 反向聚合为 `{slot, aliases:[], data_type, num_range_hint}`，不存死字符串。<br>2. 三路融合（路标：四路，LLM 语义路 P2）：路1 FIELD_ALIAS_MAP 别名匹配；路2 列数据特征（桩号=全 Z+数字 / 日期=全日期串 / 数值范围=高程/长度）+ **数学链交叉约束**：哪两列差的均值≈另一列均值，锁定 实长/桩顶/桩底三槽（仅桩基类文档有此关系链，其他类型路2 仍为独立推断——此边界 spec 必须诚实写出，验收不造假）；路3（P2，v7.2 P1 不做）LLM 语义路；路4 人工闸门确认映射。<br>3. 融合策略：路1+2 一致→直接写入；不一致/低置信→上路4（v7.2 P1 无 LLM 路3）。<br>4. 按 §1.4 设计决策 D7（存储选项A）：structured_rows 继续用标准 slot 键值，独立存 raw_headers + header_mapping；审核按映射后的标准槽位取数（与现状一致，rule_engine 零改动）。用户在编辑器改映射后→重新生成 structured_rows（轻量重算，不重 OCR）。<br>5. 自成长：人工确认的映射→追加为 FIELD_ALIAS_MAP 该槽位的新别名（需用户在 data-editor 里确认"同步到全局别名库"才写，防污染）——与 C1 自成长同构但存到不同文件。 |
| **肉眼验收** | V-69：构造一张"OCR 把桩顶高程认成'桩顶程高' + 列顺序颠倒（桩底在前、桩顶在后）"的扫描件测试表，三路融合仍能正确映射三列；审核取数时 LG-001 自洽校验仍正确命中；断网时路1+2+4 仍可用（不依赖 LLM）。<br>V-70（表头部分）：人工把某认烂的列确认映射到"灌入量"，下次同类表该列的别名匹配自动命中。 |

---

#### C7｜通用表格提取：非桩基类文档结构化（检验批/隐蔽工程/混凝土施工记录等）

| 项目 | 说明 |
|------|------|
| **问题现象** | v7.2 C5 表头三路融合仅对桩基类文档生效（`is_pile` 判定），非桩基类文档（检验批、隐蔽工程验收记录、混凝土施工记录等）在 `build_rows()` 中走 `parse_generic_rows()`，只生成 `{page, line_no, raw_text}` 三字段的纯文本行，**表格结构信息全部丢失**。data-editor 表格 Tab 对这类文档只显示一列原文，无法逐单元格核对、无法批量应用建议值、规则引擎也无法按列取数——等同于"识别了但没结构化"。 |
| **落点代码** | [build_foundation.py](file:///d:/2026年7月22日%20民航资料skill/scripts/build_foundation.py) `build_rows()` 路由分支；新增 `parse_generic_table()`、`detect_generic_header()`、`detect_generic_header_from_text()`、`_is_text_token()`、`_normalize_col_name()`、`_coerce_generic_value()`；`extract_header_info()` 非桩基分支。 |
| **落点既有概念** | 复用 `_tokenize_table_line()` 分词器（与桩基解析一致）；复用三层 JSON 结构 `structured_rows` + `raw_headers` + `header_mapping`；复用 data-editor `renderStructuredTable()` 通用渲染（按 `fields_detected` 动态生成列，已支持任意字段名）。 |
| **改动内容** | 1. **表头检测** `detect_generic_header(line)`：分词后 token≥3，文本型 token（含中文或纯字母，排除字母+数字混合代码如 Z420）占比≥50% 且≥2 个，有效列名≥3（自动去重，重复列名加 `_2/_3` 后缀）；关键词加成（命中"序号/检查项目/允许偏差/实测值/检验结果"等≥2 个→置信度+0.15）。<br>2. **结构化提取** `parse_generic_table(text)`：逐行扫描，首个通过表头检测的行作为列名，后续行按列索引映射为结构化记录（含 `row_index/page/line_no` + 列名字段）；数值自动转 int/float，占位符（- / —）保留字符串；翻页重置表头重新检测；**数据行<2 行视为非表格返回空列表**，由 `build_rows` 回退到 `parse_generic_rows`。<br>3. **路由策略** `build_rows(text, doc_type)`：桩基类→`parse_pile_rows`（三路融合+数学链）；非桩基类→先 `parse_generic_table`，成功返回结构化行，失败回退 `parse_generic_rows` 纯文本行。<br>4. **表头元数据** `extract_header_info()` 非桩基分支：检测到通用表头时返回 `header_source="generic"` + `raw_headers` + `header_mapping` + `header_confidence`，供 data-editor 表头映射 Tab 展示与人工核对；未检测到表头时返回 `header_source="none"`（向后兼容）。 |
| **边界诚实声明** | 通用表格提取**不做数学链约束**（C5 第三路仅桩基类有 实长=顶-底 关系链，检验批/隐蔽工程无此关系）；**不做 slot 映射**（通用表格列名直接作字段名，无标准槽位归一化，规则引擎按原列名取数）；列对齐依赖 OCR 分词质量，扫描件列边界模糊时可能错列——此时 `header_confidence<0.7` 触发 `needs_human_confirm`，用户在 data-editor 人工核对。 |
| **硬约束** | 不破坏桩基类现有解析（`is_pile` 路由不变）；非表格文档必须回退纯文本行（不强行结构化）；数据行<2 不视为表格；向后兼容旧 JSON（`structured_rows` 缺失时 data-editor 从 `rows` 重建）。 |
| **肉眼验收** | V-71：对标杆项目的检验批验收记录 PDF，build 后 index.json 的 `structured_rows` 含≥2 行结构化数据、`fields_detected` 含中文列名（如"序号/检查项目/实测值"）；data-editor 表格 Tab 显示多列表格可逐格编辑。<br>V-72：对纯文本说明类文档（无表格结构），build 后仍走 `parse_generic_rows`，`structured_rows` 为 `{page,line_no,raw_text}` 行，data-editor 显示原文单列。<br>V-73：桩基类文档（碎石桩施工记录）路由不变，`parse_pile_rows` 仍正常工作，`header_source="keyword"` 或 `"keyword_math"`。 |

---

#### C8｜PDF 渲染引擎：PyMuPDF 替代 Poppler（去外部进程依赖 + 中文路径原生支持 + 3-5x 加速）

| 项目 | 说明 |
|------|------|
| **问题现象** | v5.0 起 OCR 子流程中所有 PDF→图片转换均依赖 `pdf2image` + 外部 `poppler`（pdftoppm.exe）。三方面问题：①**性能差**——每次 `convert_from_path()` 启动外部进程，单页固定开销 200-500ms，50 页扫描件转图耗时 5-8 秒；②**中文路径不兼容**——poppler 不支持非 ASCII 路径，需先拷贝到临时目录再处理，额外 I/O 开销；③**部署负担重**——install.ps1 需下载 30MB poppler-windows 包，PATH 配置失败是常见安装问题。 |
| **根因分析** | Poppler 通过 `pdf2image` 封装调用外部进程 `pdftoppm.exe`，每次调用都有进程创建+销毁开销。而项目已有强依赖 `PyMuPDF>=1.23.0`（fitz），其 `page.get_pixmap()` 方法在内存中直接渲染 PDF 页面为图片，零进程开销、原生支持中文路径、单页渲染 10-30ms。 |
| **落点代码** | [ocr_image.py](file:///d:/2026年7月22日%20民航资料skill/scripts/ocr_image.py) `_safe_convert_pdf()`、`_get_poppler_path()`、`pdfinfo_from_path()` 调用点；[verify_fields.py](file:///d:/2026年7月22日%20民航资料skill/scripts/verify_fields.py) `_safe_convert_pdf_page()`、`_get_poppler_path()`；[run_audit.py](file:///d:/2026年7月22日%20民航资料skill/scripts/run_audit.py) `pdf2image` 导入；[install.ps1](file:///d:/2026年7月22日%20民航资料skill/install.ps1) Poppler 下载步骤。 |
| **改动内容** | 1. **新增 `_pdf_to_images_pymupdf()`** 替代 `_safe_convert_pdf()`：用 `fitz.open()` 打开 PDF，`page.get_pixmap(dpi=dpi)` 渲染指定页为 PIL Image，一次打开逐页渲染，零进程开销、原生支持中文路径、无需临时文件拷贝。<br>2. **新增 `_pdf_page_count()`** 替代 `pdfinfo_from_path()`：用 `fitz.open()` 获取页数，去掉 poppler_path 参数。<br>3. **删除** `_get_poppler_path()` 函数（ocr_image.py + verify_fields.py 各一份）。<br>4. **移除** `pdf2image` 导入和 `HAS_PDF2IMAGE` 检测逻辑，改为 `HAS_PYMUPDF` 检测（fitz 已是项目强依赖）。<br>5. **移除** 中文路径临时文件拷贝逻辑（PyMuPDF 原生支持非 ASCII 路径）。<br>6. **install.ps1** 移除 Poppler 下载/解压/PATH 配置步骤（约 60 行代码 + 30MB 下载量）。 |
| **落点既有概念** | 复用 `_preprocess_for_ocr()` 图像预处理（PaddleOCR/Vision API 路径的预处理逻辑不变）；复用 `fitz` 导入（extract_pdf.py、build_foundation.py、signature_check.py、run_audit.py 均已 import fitz）；返回值仍为 `List[PIL.Image]`，下游无需改动。 |
| **硬约束** | 不改变 OCR 引擎选择逻辑（auto/vision/paddle/tesseract 四路不变）；不改变返回值类型（`List[PIL.Image]`）；不改变 DPI 参数语义；保留 `_preprocess_for_ocr` 预处理调用；fitz 导入失败时给出明确错误提示（PyMuPDF 是强依赖，不应缺失）。 |
| **性能预期** | 50 页扫描件：Poppler 5-8 秒 → PyMuPDF 1-2 秒（3-5x 加速）；单页：100ms → 20ms（5x 加速）；无进程启动开销；无临时文件 I/O；无中文路径拷贝。 |
| **肉眼验收** | V-80：对任意中文路径 PDF（如 `D:\测试项目\第1批\碎石桩施工记录.pdf`），OCR 全流程正常完成，无需临时文件拷贝。<br>V-81：`_pdf_to_images_pymupdf()` 返回的 PIL Image 列表，经 `_preprocess_for_ocr()` 处理后可正常被 PaddleOCR/Vision API 识别。<br>V-82：`_pdf_page_count()` 返回页数与实际 PDF 页数一致。<br>V-83：install.ps1 不再下载 Poppler，新环境安装时间减少约 30 秒。<br>V-84：verify_fields.py 的 `crop_field_region()` 使用 PyMuPDF 渲染后裁剪功能正常。 |

---

#### C4｜置信度：文档级存疑降级 + TOP N 建议重扫（field-level 置信度不进 v7.2 P1）

| 项目 | 说明 |
|------|------|
| **问题现象** | v7.1 中 `ocr_status=needs_review` 的糊件在 review 闸门里如果有多处 OCR 低置信字段，用户得重新扫——但真实工地"复印件的复印件"成千上万件，件件重扫=弃用。硬拒+硬重扫在工地不现实。 |
| **落点代码** | review_audit.py 结论输出逻辑；R-18（结论分级：高/中/低/存疑）；R-20（待核实清单）；总览 project-dashboard.html 增"建议重扫 TOP N"区。 |
| **落点既有概念** | 复用 R-18 置信度分级、R-20 存疑清单、retry_log 已有的 needs_review 原因、Vision API 兜底（F-07 已在 ocr_image.py 第三层跑了，不需要 C4 再重复做）。 |
| **改动内容** | 1. 字段级置信度染色、ROI 坐标、原件vs扫描质量区分 → **全部砍到 P2**，v7.2 不做，避免开发量=60%C4 且不改变用户实际核对操作（低置信和高置信字段，你核对时都得去看原图）。<br>2. v7.2 P1 只做三件事：① 审核阶段对"文档级 ocr_confidence<0.85 或 ocr_status=needs_review 的文件"，其所有触发了规则的结论自动降级 severity 为 R-18 "存疑"级，并批量写入 R-20 待核实清单 + 报告里专段 "以下结论基于低置信识别，需人工重点核实"。② 不硬卡流程：糊件照常进入审核、照常出报告、照常给出存疑结论。③ project-dashboard.html 增"建议重扫 TOP 10"卡片，按 `(1 - ocr_confidence) × 该文件会被触发的 Fatal 规则条数估算值` 排序，纯文字描述"文件X、糊、估算可消除 Y 个 Fatal 存疑"，不强制、不挡流程。 |
| **硬约束** | 不得硬卡流程；重扫只能是建议；必须有非重扫兜底（人工核实+存疑标签通过）。 |
| **肉眼验收** | V-68：构造一个 ocr_confidence=0.6 的糊件测试文档，跑 review 不被拒绝，报告该件所有规则触发项 severity 标"存疑"、出现在 R-20 待核实清单；总览 TOP N 卡片按分数正确排序；对"没有 Fatal 规则关联的纯文本资料"不会错误出现在重扫建议前列（score=0 即不建议）。 |

### 1.4 设计决策记录

| 决策点 | 决策 | 理由 |
|:---|:---|:---|
| 数据底座建完后是否自动启动审核 | **否**，设人工核对闸门 | OCR 数据必须经人工确认才能进入审核（铁律 2/20） |
| MD 文件是否可编辑并反向更新 JSON | **不适用**，v7.0 取消 MD 生成 | 三层 JSON 结构（structured_rows + full_text + page_map）取代 MD 预览，Web 编辑器是唯一编辑入口 |
| 是否使用数据库 | **否**，纯文件系统 | 零依赖、跨机器迁移、git 版本追踪 |
| Web 编辑器同步方式 | 手动刷新，非实时 | 纯 HTML 无后端，手动刷新足够 |
| 审核报告是否可更新 | **否**，终态产物 | 如需更新则重新审核 |
| 字段级置信度存储方式（v7.2 D5） | **独立表**：`field_confidence: {field: [{row_index, confidence}]}` | structured_rows 改 `{value, confidence}` 嵌套需要全链路 8 处兼容层，漏一处审核中断（P-向后兼容约束） |
| 分类/表头自成长存储位置（v7.2 D2） | **独立存储**：`config/classification-priors.json` / 追加 FIELD_ALIAS_MAP，不塞 feedbacks/ | feedbacks/ 是"规则漏审/误报"，结构不同，混放污染 |
| LLM 分类触发条件（v7.2 D3） | **弱命中/多专业命中/无命中**才上 LLM；单专业 core 强命中直接用 | 平衡成本与准确率，core 强命中准确率已>95%，不上 LLM 省成本 |
| 竣工图角色确认时机（v7.2 D4） | **build 阶段终端交互**，`--auto` 参数跳过交互直接用默认值 | 角色确认是"分类阶段"的事，C-01 闸门内做；放 data-editor 等核对阶段就晚了，OCR 白跑 |
| C4 field-level 置信度是否进 v7.2 P1 | **砍到 P2** | 开发量占 C4 60%+，但不改变用户核对操作（低/高置信都要看原图），投入产出比低 |
| C1 自成长是否全管道 | **简化版**：候选→人工确认两步，不做 LLM 聚类 | 月度改分类次数<5，全管道成本不划算；候选→确认两步+主动提醒已足够 |
| LLM 调用是否公共化 | **抽公共 `scripts/llm_client.py`** | 避免 build_foundation.py、feedback_analyzer.py、review_audit.py 三处双写 API_KEY/超时/错误处理 |

---

## 二、完整需求分解

### 2.1 功能需求 — 现有已实现（v5.0）

| 编号 | 功能模块 | 实现脚本/文件 | 状态 |
|:---:|:---|:---|:---:|
| F-01 | 资料格式识别（PDF/Word/Excel/图片/扫描件） | `run_audit.py info` | ✅ |
| F-02 | PDF 电子档文字提取 | `extract_pdf.py` | ✅ |
| F-03 | 扫描件 OCR（PaddleOCR / Vision API / Tesseract） | `ocr_image.py` | ✅ |
| F-04 | 文本后处理（全角转半角、PUA 替换） | `postprocess.py` | ✅ |
| F-05 | OCR 字符混淆检测（Z→2、4→0 等） | `ocr_confusion_check.py` | ✅ |
| F-06 | 字段级复核编排（裁剪→任务清单→合并） | `verify_fields.py` | ✅ |
| F-07 | Vision API 统一配置层（7 家 Provider） | `vision_providers.py` | ✅ |
| F-08 | 数据质量四类检测（DQ-REPEAT/JUMP/ALTER/SELF） | `data_quality_check.py` | ✅ |
| F-09 | 一键审核流程编排（OCR + 混淆检测 + Vision 复核） | `run_audit.py audit` | ✅ |
| F-10 | 批量目录识别 | `run_audit.py batch` | ✅ |
| F-11 | HTML 审核报告标准模板（9 章节强制套用） | `run_audit.py` 内嵌模板 | ✅ |
| F-12 | 项目审核范围清单模板 | `templates/audit-scope-template.html` | ✅ |
| F-13 | 5 项前置信息收集（阶段/性质/范围/OCR引擎/特殊说明） | `SKILL.md` Step 0 | ✅ |
| F-14 | 20 条铁律体系 | `SKILL.md` | ✅ |
| F-15 | 16 个 references 参考文件 | `references/` | ✅ |
| F-16 | 多 Agent 并行审核（按专业拆分，最多 6 Agent） | `SKILL.md` | ✅ |
| F-17 | 知识分区红线（3 条红线 + 推理边界决策树） | `SKILL.md` | ✅ |
| F-18 | 三级输出格式（Fatal / Sanity Check / Best Practice） | `SKILL.md` | ✅ |
| F-19 | Obsidian 知识库集成（首次探测 + 按需回源） | `SKILL.md` | ✅ |
| F-20 | OCR 引擎选择开关（Vision API / PaddleOCR 本地） | `SKILL.md` Step 0 | ✅ |

### 2.2 功能需求 — v6.0 新增

| 编号 | 需求名称 | 需求描述 | 优先级 |
|:---:|:---|:---|:---:|
| N-01 | 数据底座建立 | 指定项目文件夹路径，自动扫描分类所有文件，OCR 提取后按专业分类存储结构化 JSON | P0 |
| N-02 | index.json 项目总索引 | 记录每个文件的 OCR 状态、数据文件路径、审核进度、断档信息、前置信息 | P0 |
| N-03 | JSON 三层结构存储 | JSON 文件含 structured_rows（规则引擎）+ full_text（LLM 审核）+ page_map（人工定位），取消 MD 生成 | P0 |
| N-04 | Web 数据编辑器（三栏式） | 纯 HTML 文件，文档树 + 表格/原文/图纸三 Tab，逐条确认质量告警，支持图纸截图预览 | P0 |
| N-05 | 项目总览 HTML | 从 index.json 读取状态，展示文件清单、OCR 进度、质量告警数、审核进度、断档检测 | P0 |
| N-06 | 文档关联图谱 | link_graph.json 自动构建，审核时按 same_pile / same_date_log 关联精准加载文档 | P0 |
| N-07 | 签字一致性检测 | pHash + SSIM 双指标，可选前置条件，报告内嵌 base64 对比图 | P1 |
| N-08 | 四阶段流水线 | 建数据底座 → 人工核对 → 正式审核 → 生成报告，阶段间硬闸门 | P0 |
| N-09 | 增量更新 | 补充资料时自动对比已有文件，新文件 OCR 入底座，同文件更新替换 | P1 |
| N-10 | 断档检测 | 同一专业的桩号、日期、编号连续性检查，自动标记缺漏 | P1 |

### 2.3 铁律体系需求（20 条，v5.0 已实现，v6.0 保留并集成）

| 编号 | 铁律 | 核心要求 | v6.0 集成点 |
|:---:|:---|:---|:---|
| R-01 | 规范来源可追溯 | 每条意见引规范编号+条款号，禁止凭记忆编造 | 阶段 3 审核时执行 |
| R-02 | OCR 结果人工复核 | 扫描件 OCR 识别结果仅辅助参考，数据/参数/签章必须人工复核 | 阶段 2 人工核对闸门 |
| R-03 | 运算审核只做规范性检查 | 不做数值复算，只检查方法/参数/安全系数/边界条件/计算简图 | 阶段 3 审核时执行 |
| R-04 | 审核结论必须有据可依 | 禁止"可能不合规""建议确认"等模糊表述 | 阶段 3 审核时执行 |
| R-05 | 资料标准是"移交归档" | 按 MH/T 5078.1 要求，不是收集齐全就行 | 阶段 3 审核时执行 |
| R-06 | 拒绝为伪造资料背书 | 发现伪造嫌疑必须明确指出 | 阶段 3 审核时执行 |
| R-07 | 审核过程留痕 | 每次审核生成可追溯日志 | 阶段 4 生成审核日志 |
| R-08 | 未发现问题 ≠ 全部合格 | "未发现不符合项"必须明确写出 | 阶段 4 报告生成 |
| R-09 | 逻辑一致性专项检查 | 10 个子项检查（含监理-施工方对照） | 阶段 3 审核时执行 |
| R-10 | 数据质量先于规范合规 | 4 类检测（REPEAT/JUMP/ALTER/SELF）是前置硬门槛 | 阶段 1 建底座时执行 |
| R-11 | 表格数据全列提取 | 逐列读取表头，不能只读结果列 | 阶段 1 OCR 提取时执行 |
| R-12 | 桩长与高程差交叉校验 | 实长 = 桩顶高程 − 桩底高程，±0.1m 容差 | 阶段 1 数据质量检测 |
| R-13 | 缺合计行 = 资料非原始记录 | 逐页检查底部合计行 | 阶段 1 数据质量检测 |
| R-14 | 多参数工程逻辑链联检 | 桩长/灌入量/充盈系数三条链同时校验 | 阶段 1 数据质量检测 |
| R-15 | 原始底稿追溯 | 多资料矛盾时不盲目采信，追溯原始记录 | 阶段 3 审核时执行 |
| R-16 | 提取-验证-重试循环 | 提取后先做行数校验，不通过自动重试 | 阶段 1 OCR 提取时执行 |
| R-17 | 跨资料合计值反向验证 | 施工日志有合计值 → 与施工记录逐项核对 | 阶段 3 逻辑一致性检查 |
| R-18 | 审核结论置信度分级 | 高/中/低/存疑四级，存疑不下确定性结论 | 阶段 4 报告生成 |
| R-19 | 用户标记问题闭环追溯 | 追溯 AI 为什么没发现，按四类原因归类补充规则 | 阶段 4 审核日志 |
| R-20 | OCR 存疑项人工核实 | 低置信度/存疑项汇总为待核实清单，人工核实前不下确定性结论 | 阶段 2 人工核对 |

### 2.4 约束需求（来自项目记忆，v6.0 必须遵守）

| 编号 | 约束 | 说明 |
|:---:|:---|:---|
| C-01 | 审核前必须进行文件分类确认 | 区分被审核资料、依据文件和排除文件 |
| C-02 | 前置信息确认时必须提供完整选项 | 禁止使用"默认信息"，5 项必须全部展示 |
| C-03 | OCR 引擎需提供切换开关 | 支持在前置信息确认中选择 Vision API 或 PaddleOCR |
| C-04 | 设计变更文件自动归类为依据文件 | 不与施工资料混同审核 |
| C-05 | 排除文件需在审核前明确声明 | 如测试文档不参与审核 |
| C-06 | 资料文件夹中所有文件默认纳入审核 | 需通过特殊说明排除 |
| C-07 | 过程资料不按归档标准判定签字完整性 | 根据资料所处阶段动态调整判定标准 |
| C-08 | OCR 存疑项不下确定性结论 | 汇总为"待核实清单"供人工确认 |
| C-09 | 手写潦草内容识别需特别标注 | 如施工日期年份可能被误读 |
| C-10 | OCR 识别结果需单独输出 | 用于人工核实识别数据情况 |
| C-11 | 审核报告需包含 OCR 待核实清单 | 列出年份、签字等存疑项及核实状态 |
| C-12 | 过程资料上下文需在报告开头标注 | 说明签字判定降级、OCR 年份存疑等情况 |
| C-13 | 数据质量检测脚本强制运行 | OCR 后必须执行 data_quality_check.py |
| C-14 | 数据质量告警精准去重 | 避免同一问题多重复告 |
| C-15 | 统一 HTML 为唯一交付物 | 取消独立的 Markdown 审核报告、整改通知书和合规性检查清单 |
| C-16 | 输出完整性强制校验 | 必须包含 HTML 审核报告、审核日志 JSON 及中间产物 |
| C-17 | 批量模式自动生成汇总报告 | 支持按规范/按条款/按分部分项限定审核范围 |
| C-18 | 首次加载 Skill 时自动执行 Obsidian 探测 | 结果仅显示一次；用户说"不用 Obsidian"则永久跳过 |
| C-19 | 根目录必须包含 .gitignore 文件 | 排除与 skill 无关的文件 |
| C-20 | 数据底座存储采用 JSON 三层结构 | JSON 用于机器读写（structured_rows + full_text + page_map），Web 编辑器用于人工查阅 |
| C-21 | 数据底座支持跨机器迁移 | 纯文件形式，无数据库依赖 |
| C-22 | 数据底座支持 git 版本追踪 | 通过文件变更实现版本控制 |
| C-23 | 数据底座需记录 OCR 原始输出 | 用于追溯识别过程 |
| C-24 | 数据底座需生成修正记录日志 | 记录所有人工修正操作 |
| C-25 | 数据底座需生成审核日志 | 记录每次审核的完整过程 |

### 2.5 非功能需求

| 编号 | 需求 | 说明 |
|:---:|:---|:---|
| NF-01 | 零对话 token | 人工核对阶段在浏览器完成，不消耗 AI 对话 token |
| NF-02 | 零依赖 | Web 编辑器和项目总览是纯 HTML+JS，不需要后端服务器 |
| NF-03 | 跨机器迁移 | 整个项目文件夹拷走即可，无数据库依赖 |
| NF-04 | 向后兼容 | v5.0 脚本功能全部保留，v6.0 在其上层包装 |
| NF-05 | 增量不重复 OCR | 已 OCR 过的文件不重复处理 |
| NF-06 | Python 3.10+ | 使用 match 语法 |
| NF-07 | 浏览器兼容 | Chrome 86+ / Edge 86+（File System Access API），降级方案用下载覆盖 |
| NF-08 | 纯 HTML | Web 编辑器和项目总览是单 HTML 文件，不依赖后端服务器 |
| NF-09 | 离线可用 | PDF.js 预下载放入 templates/，支持离线场景 |

---

## 三、系统架构

### 3.1 四阶段流水线

```
阶段 1：建数据底座（全自动）
  输入：项目文件夹路径 + 5 项前置信息
  处理：文件扫描分类 → OCR 提取 → 三层结构化 JSON → 数据质量检测 → 混淆检测
  输出：数据底座/（JSON + index.json + 质量告警 + 混淆检测）
  闸门：index.json 中所有文件 ocr_status = "completed"
  铁律执行：R-10（数据质量先于规范合规）、R-11（全列提取）、R-16（提取-验证-重试）

      ↓ 人机闸门：数据未经确认，不进审核（铁律 R-02/R-20）

阶段 2：人工核对（人机交互，零 token）
  输入：数据底座/ + Web 数据编辑器
  处理：左图右表对照 → 逐条确认告警 → 修正 OCR 误读 → 导出 JSON
  输出：修正记录/corrections.json + 各文件 corrected_data.json
  闸门：用户在 Web 编辑器中点击"确认完成"并导出
  铁律执行：R-02（OCR 人工复核）、R-20（OCR 存疑项核实）

      ↓ 确认完成后，AI 读取修正后数据

阶段 3：正式审核（全自动，支持多 Agent 并行）
  输入：修正后的 corrected_data.json + 前置信息
  处理：规范逐条对账 + 逻辑一致性检查（10 子项）+ 运算规范审核（按需）
  输出：审核日志/AU-{日期}-{序号}_审核日志.json
  铁律执行：R-01/R-03/R-04/R-05/R-06/R-09/R-15/R-17

      ↓

阶段 4：生成报告（全自动）
  输入：审核日志
  处理：汇总发现 → 四级置信度标注 → 三级分类 → 套用 HTML 模板
  输出：审核报告.html（统一交付物，9 章节强制）
  铁律执行：R-07/R-08/R-18/R-19
```

### 3.2 模块划分

```
civil-aviation-doc-audit/
├── SKILL.md                           # Skill 主指令（v7.1 更新）
├── rule-manager.bat                   # 规则管理面板启动脚本
├── install.ps1                        # 安装脚本
├── requirements.txt                   # Python 依赖
├── README.md                          # 说明文档
├── .gitignore
│
├── scripts/                           # Python 脚本层
│   ├── run_audit.py                   # 主入口，build/review/report/audit 子命令
│   ├── build_foundation.py            # 数据底座建立（含link_graph构建）
│   ├── review_audit.py                # 正式审核（含human_verified闸门）
│   ├── signature_check.py             # 签字一致性检测（v7.0新增）
│   ├── extract_pdf.py                 # PDF 文字提取
│   ├── ocr_image.py                   # OCR 引擎
│   ├── postprocess.py                 # 文本后处理
│   ├── data_quality_check.py          # 数据质量检测
│   ├── ocr_confusion_check.py         # OCR 混淆检测
│   ├── verify_fields.py               # 字段复核
│   ├── vision_providers.py            # Vision API 配置
│   ├── rule_engine.py                 # 规则引擎（含FIELD_ALIAS_MAP）
│   ├── rule_admin.py                  # 规则管理 API 服务
│   ├── rule_lifecycle.py              # 规则生命周期管理
│   ├── rule_monitor.py                # 规则效力自监控
│   ├── rule_reflector.py              # 反思调度器
│   ├── rule_registry_builder.py       # 规则注册表生成
│   ├── rule_schema_validator.py       # 规则 Schema 校验
│   ├── feedback_store.py              # 反馈存储
│   ├── feedback_analyzer.py           # 反馈分析
│   ├── audit_memory.py                # 审核记忆流
│   ├── audit_config.py                # 分部分项配置
│   ├── test_rule_engine.py            # 规则引擎测试
│   ├── test_cross_unit_perf.py        # 跨单位性能测试
│   └── test_rule_subsystem_integration.py  # 集成测试
│
├── templates/                         # HTML 模板层
│   ├── data-editor.html               # Web 数据编辑器（三栏式，v7.0升级）
│   ├── rule-editor.html               # 离线规则编辑器
│   ├── rule-manager.html              # 规则管理面板
│   ├── project-dashboard.html         # 项目总览仪表盘
│   ├── feedback-collector.html        # 反馈收集组件
│   ├── alignment-view.html            # 跨单位数据对齐视图
│   ├── audit-scope-template.html      # 审核范围清单模板
│   ├── pdf.min.js                     # PDF.js 离线预下载
│   └── pdf.worker.min.js              # PDF.js worker
│
├── rules/                             # 规则文件库（93 条）
│   ├── registry.json                  # 规则注册表
│   ├── L1-iron/                       # 铁律（16 个文件，17 条规则，CU-012 存放在 L2-logic/）
│   ├── L2-logic/                      # 逻辑一致性（72 个文件，71 条 active + 1 条 deprecated，含跨单位规则）
│   ├── L3-business/                   # 业务规则（5 条）
│   └── schema/                        # JSON Schema 校验文件
│
├── feedbacks/                         # 【v6.0】反馈存储
│   └── schema/feedback-schema.json    # 反馈 JSON Schema
│
├── audit_memory/                      # 【v6.0】审核记忆流日志（JSONL）
│
├── references/                        # 知识库层（16 个文件，不变）
│   ├── airfield-engineering-audit.md  # 场道工程专项审核
│   ├── atc-engineering-audit.md       # 空管工程专项审核
│   ├── visual-aids-audit.md           # 目视助航专项审核
│   ├── weak-electricity-audit.md      # 弱电系统专项审核
│   ├── fuel-supply-audit.md           # 供油工程专项审核
│   ├── audit-checklists.md            # 五大专业通用审核清单
│   ├── specification-mapping.md       # 资料类型↔规范条款映射
│   ├── specification-quick-reference.md # 规范条款速查表
│   ├── calculation-standards.md       # 运算规范参考
│   ├── data-quality-patterns.md       # 数据质量检测规则库
│   ├── logic-conflict-patterns.md     # 逻辑矛盾识别模式库
│   ├── high-frequency-errors.md       # 高频错误模式库
│   ├── ocr-confusion-correction.md    # OCR 混淆修正规则
│   ├── ocr-hybrid-architecture.md     # OCR 混合架构说明
│   ├── document-templates.md          # 文档模板
│   └── html-report-template.html       # HTML 审核报告标准模板参考
│
└── tools/                              # 工具目录（poppler 已移除，PDF 转图由 PyMuPDF 替代）
```

### 3.3 项目文件夹结构（运行时生成）

```
用户项目文件夹/                          ← 用户指定的路径
├── 扫描件.pdf                           ← 用户放进去的原始资料
├── 施工日志.xlsx
├── 设计变更通知单.pdf
│
├── 数据底座/                            ← 阶段 1 自动生成
│   ├── index.json                      ← 项目总索引（唯一真相源）
│   ├── 01_场道工程/
│   │   └── 施工记录/
│   │       ├── 碎石桩施工记录.json      ← 结构化数据（机器读写）
│   │       ├── 碎石桩施工记录_ocr.json  ← OCR 原始输出（追溯用）
│   │       ├── 碎石桩施工记录_quality.json ← 质量检测结果
│   │       └── 碎石桩施工记录_confusion.json ← 混淆检测结果
│   ├── 02_空管工程/
│   ├── 03_助航设施/
│   ├── 04_弱电系统/
│   ├── 05_供油工程/
│   ├── 通用资料/
│   ├── 修正记录/                        ← 阶段 2 生成
│   │   └── corrections.json            ← 人工核对操作日志
│   └── 审核日志/                        ← 阶段 3 生成
│       └── AU-20260729-001.json        ← 每次审核的完整日志
│
├── 审核报告.html                        ← 阶段 4 生成（最终交付物）
├── 项目总览.html                        ← 从 templates/ 复制，可随时打开
└── data-editor.html                    ← 从 templates/ 复制，人工核对用
```

---

## 四、详细设计

### 4.1 数据底座建立脚本（build_foundation.py）【新增】

**职责**：扫描项目文件夹 → 分类文件 → OCR 提取 → 生成结构化 JSON（三层结构）→ 质量检测 + 混淆检测 → 更新 index.json → 复制 Web 模板

**CLI 接口**：
```
python build_foundation.py <项目文件夹路径> [选项]

选项：
  --engine <auto|vision|paddle>    OCR 引擎选择（默认 auto）
  --professional <专业>             指定专业分类（默认自动识别）
  --incremental                     增量模式（仅处理新文件）
  --out <输出目录>                  数据底座目录名（默认"数据底座"）
```

**执行流程**：
1. 扫描项目文件夹，列出所有文件
2. 调用 `run_audit.py info` 识别每个文件格式（PDF/Word/Excel/图片/扫描件）
3. 按文件名关键词自动分类专业（场道/空管/助航/弱电/供油/通用）
4. 设计变更文件自动归类为依据文件（约束 C-04）
5. 对每个被审核文件执行 OCR 提取（调用 `ocr_image.py` 或 `extract_pdf.py`）
6. 将 OCR 结果整理为结构化 JSON（rows 数组，全列提取，铁律 R-11）
7. 提取后做行数校验，不通过自动重试（铁律 R-16）
8. 运行 `data_quality_check.py` 生成质量检测 JSON（铁律 R-10，约束 C-13）
9. 运行 `ocr_confusion_check.py` 生成混淆检测 JSON
10. 创建/更新 `index.json`（含前置信息、文件状态、质量告警数）
11. 复制 Web 编辑器和项目总览模板到项目文件夹

**自动分类规则**：
| 文件名关键词 | 专业分类 |
|:---|:---|
| 场道、土方、碎石桩、换填、混凝土、跑道、滑行道 | 01_场道工程 |
| 空管、雷达、VOR、DME、ILS、航向 | 02_空管工程 |
| 助航、灯光、灯箱、标记牌、调光器、PAPI | 03_助航设施 |
| 弱电、监控、安防、网络、信息集成 | 04_弱电系统 |
| 供油、储油、管线、油罐、加油 | 05_供油工程 |
| 施工日志、监理、会议纪要、联系单 | 通用资料 |
| 设计变更、变更通知、变更图纸 | 依据文件（不逐页审核） |

**index.json Schema**：
```json
{
  "schema_version": "1.0",
  "project_name": "项目名称",
  "project_path": "项目文件夹绝对路径",
  "created_at": "2026-07-29T10:00:00",
  "updated_at": "2026-07-29T15:30:00",
  "stage": "foundation_built",
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
      "file_type": "PDF",
      "is_scanned": true,
      "doc_type": "碎石桩施工记录",
      "professional": "01_场道工程",
      "subcategory": "施工记录",
      "pages": 49,
      "ocr_status": "completed",
      "ocr_engine": "PaddleOCR",
      "ocr_confidence": 0.833,
      "ocr_completed_at": "2026-07-29T10:15:00",
      "data_file": "01_场道工程/施工记录/碎石桩施工记录.json",
      "ocr_raw_file": "01_场道工程/施工记录/碎石桩施工记录_ocr.json",
      "quality_file": "01_场道工程/施工记录/碎石桩施工记录_quality.json",
      "confusion_file": "01_场道工程/施工记录/碎石桩施工记录_confusion.json",
      "quality_alerts": 3,
      "confusion_suspects": 5,
      "human_verified": false,
      "corrected_file": null,
      "audit_status": "pending",
      "last_updated": "2026-07-29T10:15:00"
    }
  ],
  "corrections": {
    "total": 0,
    "file": "修正记录/corrections.json"
  },
  "gaps": [],
  "audit_logs": []
}
```

**单文件 JSON Schema（{文件名}.json）**：
```json
{
  "schema_version": "1.0",
  "doc_id": "DOC-001",
  "doc_type": "碎石桩施工记录",
  "source_file": "扫描件.pdf",
  "professional": "01_场道工程",
  "ocr_engine": "PaddleOCR",
  "ocr_confidence": 0.833,
  "ocr_completed_at": "2026-07-29T10:15:00",

  // ===== v7.2 新增字段 =====
  "extraction_mode": "ocr",          // 提取方式: "ocr"|"text_pdf"|"docx"|"meta_xlsx"|"image"|"unknown"|"reference_skip"
  "is_drawing": false,               // 是否为图纸类文件（与角色正交，不随 stage 变化）
  "drawing_type": null,              // 图纸细分: null|"design_basis"|"as_built"|"process_sketch"
  "human_confirmed": false,          // 人工核对闸门: false 时 Phase 2 不启动
  "classification_source": "keyword", // 分类来源: "keyword"|"llm"|"human"|"generic_keywords"|"reference_keywords"
  "classification_confidence": 1.0,  // 分类置信度: 0.0~1.0
  "raw_headers": ["桩号", "实长", "灌入量"],  // OCR 原始表头（未映射）
  "header_mapping": {                // 表头映射: original_header → {slot, source, confidence}
    "桩号": {"slot": "pile_no", "source": "alias", "confidence": 1.0},
    "实长": {"slot": "actual_length", "source": "alias", "confidence": 1.0}
  },

  // ===== 三层结构（v7.0+） =====
  "structured_rows": [               // 第一层：规则引擎用结构化行
    {
      "row_index": 1,
      "page": 1,
      "pile_no": "Z420",
      "design_length": 20.0,
      "diameter": 0.6,
      "bottom_elev": 2089.98,
      "top_elev": 2103.68,
      "actual_length": 13.7,
      "current": 160,
      "re_penetration": 19,
      "volume": 5.30,
      "filling_coeff": 1.37,
      "verticality": 0.2,
      "start_time": "00:00",
      "end_time": "00:39",
      "remark": ""
    }
  ],
  "full_text": "第1页\n桩号 实长 灌入量...",  // 第二层：LLM 审核用全文文本
  "page_map": [                      // 第三层：人工定位用页码映射
    {"page": 1, "text": "第1页内容...", "image": "page_001.png"}
  ],

  // ===== 向后兼容 =====
  "rows": [],                        // structured_rows 的别名（向后兼容，优先读 structured_rows）

  // ===== 质量检测结果 =====
  "quality_result": {},
  "confusion_result": {},
  "corrections_applied": []
}
```

### 4.2 Web 数据编辑器（data-editor.html）【v7.1 精密仪表盘升级】

**职责**：浏览器中完成 OCR 数据的人工核对和修正，零对话 token。v7.1 将界面从"能跑就行"重构为精密仪表盘级别，修复了文档树混入非文档文件、状态分级缺失、确认按钮逻辑陷阱等问题。

**加载方式**（四种，按优先级）：
- 方式 A（首选）：File System Access API，选择项目文件夹，自动读取 `数据底座/index.json`
- 方式 B（次选）：拖拽 JSON 文件到网页（File System Access API 不支持时）
- 方式 C（兜底）：手动选择文件，通过 `<input type="file">` 加载
- 方式 D（HTTP 测试）：仅 http 协议下可用，基于 `location.pathname` 推算站点根路径

**界面布局**：
```
┌──────────────────────────────────────────────────────────────────┐
│  DIAGNOSTICS 未运行 — 点击「选择项目文件夹」开始诊断  [▼]        │ ← 可折叠诊断面板
├──────────────────────────────────────────────────────────────────┤
│  [选择项目文件夹] [拖拽 JSON 至此处]   快捷键：Ctrl+Enter 确认  │
├──────────┬───────────────────────────────────────────────────────┤
│  📁 文档  │  📊 表格  📄 原文  ⚠️ 问题（3）                     │ ← 三 Tab
│  树       │                                                      │
│           │  桩号   实长   灌入量  充盈系数  桩顶高程  桩底高程   │
│  ✅ 已核对 │  Z420  13.7   5.30   1.37     2103.68  2089.98     │
│  ├─ 碎石桩 │  Z419  12.5   4.80   1.28     2102.44  2089.94     │
│  ⏳ 待核对 │  Z418  ⚠️9.0   3.20   1.12     2103.72  2090.53     │ ← 标红=质量告警
│  ├─ 施工日 │  ...                                               │
│  ⚠️ 需重扫 │                                                      │
│  ├─ 检验批 │  (可编辑单元格，双击修改)                           │
│  ⊖ 非文档  │                                                      │
│  └─ 原始   │  进度：3/5 已核对  告警：2 未处理  存疑：1 项      │
│            │                                                      │
│  进度 3/5  │  [保存]  [确认此文档数据无误] (Ctrl+Enter)          │ ← 安全闸门
├──────────┴───────────────────────────────────────────────────────┤
│  ⚠️ 问题清单（按区域分组）                                       │
│  ┌─ 桩号 Z418 ──────────────────────────────────────────────┐   │
│  │  🟡 DQ-SELF-LEN-01: 第3行桩长自洽失败                     │   │
│  │     记录值 9.0m ≠ 计算值 (2103.72 - 2090.53) = 13.19m    │   │
│  │     [建议: 13.2] [批量应用建议值] [逐条修正] [标记已处理]  │   │
│  │  🟡 DQ-ALTER-01: 充盈系数自洽失败                         │   │
│  │     记录值 1.12 ≠ 计算值 1.17                             │   │
│  │     [建议: 1.17] [批量应用建议值] [逐条修正] [标记已处理]  │   │
│  └───────────────────────────────────────────────────────────┘   │
│  ┌─ 全表 ──────────────────────────────────────────────────────┐ │
│  │  🟠 DQ-REPEAT-01: 竖直度交替模式（0.2/0.3 交替）           │ │
│  │     [确认] [标记已处理]                                     │ │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

**核心功能**（v7.1 新增/升级）：

1. **诊断面板**（可折叠）：页面顶部实时显示加载过程、文档结构、数据问题，输出逐步日志：
   - index.json 加载方式与结果
   - documents.length 及每个 document 的元数据（id / doc_type / data_file / ocr_status / human_verified / is_scanned）
   - 标记非文档文件（扩展名为 png/jpg/txt/md，或 doc_type 为空，或 data_file 不指向 .json），统计污染数量
   - 逐个加载 data_file，打印顶层 keys，确认是 rows 还是 structured_rows

2. **文档树优化**（信息架构重定义）：
   - 严格的非文档判定逻辑（`isNonDoc()` 函数），根据文件扩展名、file_type、data_file 路径综合判断
   - 非文档文件（OCR 中间产物/调试截图/测试 txt/旧 MD）自动进入「原始文件/调试产物」折叠区，灰色弱样式 + 中性图标
   - 主树仅展示有效审核文档，进度计数仅统计有效文档

3. **状态语义分级**（五种 CSS 绘制状态图标，不用 emoji）：
   - ✅ 已核对（teal 实心圆 + 勾号）：human_verified=true
   - ⏳ 待核对（amber 实心圆）：human_verified=false，有结构化数据
   - ⚠️ 需重扫（amber 实心圆 + 橙色边框）：human_verified=false，无结构化数据
   - ⊖ 非文档（透明边框）：被判定为非文档文件
   - ❌ 加载失败（red 实心圆）：data_file 加载出错
   - 每种状态配合 tooltip 说明原因

4. **问题视图 + 批量操作**（⚠️ Tab）：
   - 按类型/区域/风险等级聚合质量告警与 OCR 存疑项
   - 支持逐条修正（applySuggest 函数）
   - 支持批量应用建议值（对同一区域多条问题一键修正）
   - 支持标记已处理
   - 问题编号与表格行联动，点击定位到对应行

5. **安全闸门**（updateConfirmGate 函数）：
   - 确认按钮仅当文档为有效文档且有结构化数据时才启用
   - 无结构化数据或非文档状态时，按钮禁用并显示禁用原因
   - 快捷键 Ctrl+Enter 确认当前文档

6. **精密仪表盘视觉风格**：
   - 深墨蓝/炭灰骨架色（--skel-bg, --skel-surface）
   - 工程网格底纹（CSS 网格背景，象征工程图纸）
   - 语义化信号色（teal=已确认, amber=待处理, red=错误）
   - 等宽数字（monospace 字体，便于数据列对齐）
   - 双字体系统（sans-serif 标题 + 正文，monospace 数据）
   - 微动效反馈（树节点 hover/选中过渡、Tab 切换渐变、告警行呼吸高亮）
   - 禁止清单：无 emoji 状态图标、无模糊阴影、无过度渐变、无卡通风格

7. **数据结构兼容层**：
   - 实现数据访问层（getRows / getFullText / getPageMap）
   - 优先使用 structured_rows + full_text + page_map（v7.0 三层结构）
   - 缺失时从旧版 rows 数组重建，确保向后兼容

8. **快捷键**：
   - Ctrl+Enter：确认当前文档（等同点击"确认此文档数据无误"）

**导出的 corrections.json Schema**：
```json
{
  "doc_id": "DOC-001",
  "doc_type": "碎石桩施工记录",
  "verified_at": "2026-07-29T15:30:00",
  "total_corrections": 5,
  "corrections": [
    {
      "row_index": 3,
      "page": 1,
      "field": "actual_length",
      "original_value": 9.0,
      "corrected_value": 13.2,
      "reason": "人工核对原图，9.0 为 OCR 误读",
      "verified_by": "user"
    }
  ],
  "alerts_resolved": [
    {
      "code": "DQ-SELF-LEN-01",
      "row_index": 3,
      "action": "corrected",
      "note": "已修正实长"
    },
    {
      "code": "DQ-REPEAT-01",
      "row_index": null,
      "action": "confirmed",
      "note": "竖直度交替为实际施工情况"
    }
  ]
}
```

### 4.3 项目总览 HTML（project-dashboard.html）【新增】

**职责**：从 `index.json` 读取状态，展示项目全貌

**加载方式**：双击打开，自动读取同目录 `数据底座/index.json`

**界面布局**：
```
┌─────────────────────────────────────────────┐
│  🏠 XX机场 场道工程 — 项目总览               │
│  最后更新：2026-07-29 15:30  [刷新]          │
├─────────────────────────────────────────────┤
│  📊 总览                                     │
│  文件总数：5  OCR完成：5  待核对：3  已审核：0│
│  质量告警：8  OCR存疑：12  断档：1            │
├─────────────────────────────────────────────┤
│  📁 文件清单                                 │
│  DOC-001  碎石桩施工记录.pdf  49页  场道     │
│    OCR✅ 置信度83%  告警3  存疑5  待核对      │
│  DOC-002  施工日志.xlsx  3页  通用           │
│    提取✅  告警0  存疑0  待核对               │
│  ...                                        │
├─────────────────────────────────────────────┤
│  ⚠️ 断档检测                                 │
│  桩号 Z360-Z420 缺少施工记录（检测于15:30）  │
├─────────────────────────────────────────────┤
│  📋 审核进度                                 │
│  阶段1✅  阶段2⏳  阶段3⏸  阶段4⏸           │
│  [打开数据编辑器]  [查看审核报告]             │
└─────────────────────────────────────────────┘
```

**数据刷新策略**：
- 打开时读取 `index.json`
- 页面提供"刷新"按钮，重新读取
- 不做实时 WebSocket（纯 HTML 无法实现），靠手动刷新

### 4.4 数据同步策略（核心：解决"更新了数据但网页没更新"）

**单一数据源原则**：

所有数据的唯一真相来源是 `index.json`。三个 HTML 文件都是 `index.json` 的视图：

```
index.json（唯一真相源）
  ├── 项目总览.html        ← 只读视图，读取 index.json 展示
  ├── data-editor.html     ← 读取 {文件}.json，写入 corrected_data.json + 更新 index.json
  └── 审核报告.html         ← 读取 corrected_data.json + 审核日志生成
```

**同步规则**：

| 事件 | 更新 index.json | 更新其他文件 |
|:---|:---|:---|
| OCR 完成 | `ocr_status` → `completed`，写入各文件路径 | 生成 JSON + quality.json + confusion.json |
| 质量检测完成 | `quality_alerts` 更新告警数 | — |
| 混淆检测完成 | `confusion_suspects` 更新存疑数 | — |
| 人工修改字段 | `human_verified` → `true` | 生成 corrected_data.json + 追加 corrections.json |
| 人工确认完成 | `stage` → `human_review` | — |
| 正式审核完成 | `audit_status` → `completed` | 生成审核日志 JSON |
| 报告生成完成 | `stage` → `reported` | 生成 审核报告.html |
| 增量更新 | 新文件加入 `documents` 数组 | 新文件 OCR + JSON |

**Web 编辑器的同步机制**：
1. Web 编辑器打开时读取 `数据底座/01_场道工程/施工记录/碎石桩施工记录.json`
2. 人工修改后，导出 `corrected_data.json` 到同目录
3. 同时更新 `index.json` 中该文件的 `human_verified` 和 `corrected_file` 字段
4. 项目总览刷新时读取更新后的 `index.json`，自然看到最新状态

**关键约束**：
- Web 编辑器**直接修改** index.json 中的字段（通过 File System Access API 或下载覆盖）
- v7.0 已取消 MD 生成，JSON 三层结构（structured_rows + full_text + page_map）取代 MD 预览，Web 编辑器是唯一编辑入口
- 如果用户想看修正后的数据，打开 Web 编辑器或直接看 corrected_data.json
- `审核报告.html` 是终态产物，生成后不再更新（如需更新则重新审核）

### 4.5 run_audit.py 改造

新增三个子命令，保留原有命令（info/extract/batch/postprocess/audit）不变：

```
# 新增：建立数据底座
python run_audit.py build <项目文件夹> --engine <auto|vision|paddle>

# 新增：启动正式审核（读取修正后数据）
python run_audit.py review <项目文件夹>

# 新增：生成报告
python run_audit.py report <项目文件夹>
```

**`build` 子命令**：
1. 调用 `build_foundation.py` 的核心逻辑
2. 完成后输出"数据底座已建立，请打开 Web 编辑器进行人工核对"

**`review` 子命令**：
1. 读取 `index.json`，检查所有文件 `human_verified == true`
2. 有未核对文件 → 拒绝执行，提示"请先完成人工核对"
3. 全部核对完成 → 读取 `corrected_data.json`，执行规范对账 + 逻辑一致性检查
4. 输出审核日志 JSON
5. 支持多 Agent 并行：资料 ≥ 500 页或 ≥ 3 个专业时，按专业拆分并行审核

**`report` 子命令**：
1. 读取审核日志
2. 套用 `html-report-template.html` 生成报告（9 章节强制，约束 C-15）
3. 更新 `index.json` 的 `stage` 为 `reported`

### 4.6 SKILL.md 改造要点

v7.0 对 SKILL.md 的核心修改：

1. **Step 0 不变**：5 项前置信息收集（含 OCR 引擎选择），禁止使用默认值（约束 C-02）
2. **Step 0 新增文件分类**：审核前必须进行文件分类确认（约束 C-01）
3. **Step 1~2 改为阶段 1**：文件分类 + OCR → 建立数据底座（调用 `build` 子命令）
4. **新增人机闸门**：阶段 1 完成后停下，提示用户打开 Web 编辑器
5. **Step 3~7 改为阶段 3**：读取修正后数据 → 规范对账 + 逻辑一致性 + 运算审核
6. **Step 8 改为阶段 4**：生成报告（调用 `report` 子命令）
7. **多 Agent 并行**：阶段 3 支持按专业拆分并行审核

**新增触发语句**：
- "建立数据底座" / "建数据底座" / "开始审阅"
- "更新数据底座" / "增量更新"
- "开始审核" / "正式审核"
- "生成报告"

### 4.7 多 Agent 并行审核集成

v5.0 多 Agent 并行审核能力在 v6.0 中的集成方式：

**触发条件不变**：资料 ≥ 500 页 或 ≥ 3 个专业 或 用户明确要求

**执行流程调整**：
```
阶段 1（主 Agent）：建数据底座 → 生成 index.json
    ↓ 人机闸门
阶段 2（人工）：Web 编辑器核对
    ↓ 确认完成
阶段 3（多 Agent 并行）：
  主 Agent 读取 index.json → 按专业拆分任务包
  ├─ Agent A：读取场道 corrected_data.json → 规范对账 + 逻辑一致性
  ├─ Agent B：读取空管 corrected_data.json → 规范对账 + 逻辑一致性
  ├─ ...
  └─ 全部完成后 → 主 Agent 汇总 + 跨专业交叉验证
    ↓
阶段 4（主 Agent）：生成总报告
```

**关键变化**：v6.0 中子 Agent 不再自己做 OCR，而是读取已核对的 `corrected_data.json`，OCR 和人工核对在阶段 1~2 统一完成。

---

## 五、数据流图

```
用户指定项目文件夹 + 5 项前置信息
        │
        ▼
┌───────────────────────────┐
│  阶段1: build_foundation  │
│                           │
│  文件扫描 → 分类 → OCR    │
│  → 行数校验(R-16)         │
│  → 全列提取(R-11)         │
│  → 数据质量检测(R-10)     │
│  → 混淆检测               │
│        │                  │
│        ├──→ {文件}.json │ ← 三层结构化数据（structured_rows + full_text + page_map）
│        ├──→ {文件}_ocr.json ← OCR原始输出(C-23)
│        ├──→ {文件}_quality.json ← 质量检测(C-13)
│        ├──→ {文件}_confusion.json ← 混淆检测
│        └──→ index.json    │ ← 总索引更新
│                           │
│  复制 Web 模板到项目文件夹  │
└───────────┬───────────────┘
            │
            ▼
     用户打开 data-editor.html
            │
┌───────────────────────────┐
│  阶段2: 人工核对 (Web)    │
│                           │
│  读取 {文件}.json         │
│  + {文件}_quality.json    │
│  + {文件}_confusion.json  │
│        │                  │
│  人工修改 → 导出           │
│        ├──→ corrected_data.json ← 修正后数据
│        ├──→ corrections.json ← 操作日志(C-24)
│        └──→ index.json    │ ← 更新 human_verified
│                           │
│  用户点击"确认完成"        │
└───────────┬───────────────┘
            │
            ▼
     AI 读取 index.json，确认全部 verified
            │
┌───────────────────────────┐
│  阶段3: 正式审核 (AI)     │
│                           │
│  读取 corrected_data.json │
│        │                  │
│  规范对账(R-01/R-04/R-05) │
│  逻辑一致性(R-09/R-17)    │
│  运算审核(R-03)           │
│  伪造检测(R-06)           │
│  底稿追溯(R-15)           │
│  签字一致性检测(可选)      │
│  (按link_graph精准加载)   │
│        │                  │
│  [多Agent并行: 按专业拆分] │
│        │                  │
│        └──→ AU-{日期}.json ← 审核日志(C-25)
│             index.json    │ ← 更新 audit_status
└───────────┬───────────────┘
            │
┌───────────────────────────┐
│  阶段4: 生成报告 (AI)     │
│                           │
│  读取审核日志              │
│  置信度标注(R-18)          │
│  三级分类(Fatal/Sanity/BP)│
│  自检(R-08/R-19)          │
│  套用 HTML 模板(C-15)     │
│        │                  │
│        └──→ 审核报告.html  ← 最终交付物
│             index.json    │ ← 更新 stage=reported
└───────────────────────────┘
```

---

## 六、数据同步矩阵

> 用户核心关切："不要出现更新了一个数据，某一个网页没有更新的情况"

| 数据变更事件 | index.json | {文件}.json | corrected_data.json | corrections.json | 审核日志.json | 审核报告.html | 项目总览.html |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| OCR 完成 | ✅ 写入 | ✅ 生成 | — | — | — | — | ✅ 刷新可见 |
| 质量检测完成 | ✅ 更新 alerts 数 | — | — | — | — | — | ✅ 刷新可见 |
| 混淆检测完成 | ✅ 更新 suspects 数 | — | — | — | — | — | ✅ 刷新可见 |
| 人工修改字段 | ✅ 更新 verified | — | ✅ 生成 | ✅ 追加 | — | — | ✅ 刷新可见 |
| 人工确认完成 | ✅ 更新 stage | — | — | — | — | — | ✅ 刷新可见 |
| 审核完成 | ✅ 更新 audit_status | — | — | — | ✅ 生成 | — | ✅ 刷新可见 |
| 报告生成 | ✅ 更新 stage | — | — | — | — | ✅ 生成 | ✅ 刷新可见 |
| 增量更新 | ✅ 追加新文件 | ✅ 新文件生成 | — | — | — | — | ✅ 刷新可见 |
| 断档检测 | ✅ 更新 gaps | — | — | — | — | — | ✅ 刷新可见 |

**关键设计决策**：
- v7.0 已取消 MD 生成，JSON 三层结构（structured_rows + full_text + page_map）取代 MD 预览，Web 编辑器是唯一编辑入口。
- `项目总览.html` 和 `data-editor.html` 都是 `index.json` 的只读视图，通过手动刷新获取最新状态。
- `审核报告.html` 是终态产物，生成后不再更新（如需更新则重新审核）。
- 所有数据变更都必须更新 `index.json`，这是唯一的同步保证机制。

---

## 七、实现任务分解

### Phase 1：数据底座核心（P0）

| 任务编号 | 任务名称 | 产出物 | 依赖 | 颗粒度 |
|:---:|:---|:---|:---:|:---|
| T-01 | 编写 `build_foundation.py` 脚本骨架（CLI 参数、主流程框架） | 脚本文件 | — | 中 |
| T-02 | 实现文件扫描 + 格式识别（调用 `run_audit.py info`） | build_foundation.py 内函数 | T-01 | 中 |
| T-03 | 实现文件自动分类逻辑（关键词匹配 + 设计变更识别） | build_foundation.py 内函数 | T-02 | 中 |
| T-04 | 实现 OCR 调用 + 结果 → 结构化 JSON 转换 | build_foundation.py 内函数 | T-03 | 高 |
| T-05 | 实现行数校验 + 自动重试（铁律 R-16） | build_foundation.py 内函数 | T-04 | 中 |
| T-06 | 实现 JSON 三层结构（structured_rows + full_text + page_map）组装 | build_foundation.py 内函数 | T-04 | 低 |
| T-07 | 实现质量检测 + 混淆检测集成 | build_foundation.py 内函数 | T-04 | 中 |
| T-08 | 实现 index.json 创建和更新（含前置信息、文件分类） | build_foundation.py 内函数 | T-04 | 中 |
| T-09 | 实现 Web 模板复制到项目文件夹 | build_foundation.py 内函数 | T-08 | 低 |
| T-10 | `run_audit.py` 新增 `build` 子命令 | run_audit.py 修改 | T-01~T-09 | 低 |
| T-11 | 端到端测试：指定文件夹 → 建底座 | 测试报告 | T-10 | 中 |

### Phase 2：Web 数据编辑器（P0）

| 任务编号 | 任务名称 | 产出物 | 依赖 | 颗粒度 |
|:---:|:---|:---|:---:|:---|
| T-12 | 设计 data-editor.html 界面骨架（布局 + CSS） | HTML 文件 | — | 中 |
| T-13 | 实现 JSON 文件加载（File System Access API + 降级方案） | JS 逻辑 | T-12 | 高 |
| T-14 | 实现文件列表导航（下拉选择 + 切换保存） | JS 逻辑 | T-13 | 中 |
| T-15 | 实现左图右表对照（PDF.js 渲染 + 表格渲染 + 翻页同步） | JS 逻辑 | T-14 | 高 |
| T-16 | 实现字段编辑 + 修正记录 | JS 逻辑 | T-15 | 中 |
| T-17 | 实现质量告警逐条确认（确认/修正动作） | JS 逻辑 | T-16 | 中 |
| T-18 | 实现 OCR 存疑项高亮 + 建议值展示 | JS 逻辑 | T-17 | 中 |
| T-19 | 实现桩号导航 | JS 逻辑 | T-15 | 低 |
| T-20 | 实现导出 corrected_data.json + corrections.json | JS 逻辑 | T-16 | 中 |
| T-21 | 实现更新 index.json（File System Access API 写入） | JS 逻辑 | T-20 | 高 |
| T-22 | 端到端测试：打开编辑器 → 修改 → 导出 → index.json 更新 | 测试报告 | T-21 | 中 |

### Phase 3：项目总览仪表盘（P0）

| 任务编号 | 任务名称 | 产出物 | 依赖 | 颗粒度 |
|:---:|:---|:---|:---:|:---|
| T-23 | 设计 project-dashboard.html 界面骨架 | HTML 文件 | — | 中 |
| T-24 | 实现 index.json 读取和展示 | JS 逻辑 | T-23 | 中 |
| T-25 | 实现文件清单 + OCR 进度展示 | JS 逻辑 | T-24 | 中 |
| T-26 | 实现质量告警统计 + 断档检测展示 | JS 逻辑 | T-24 | 中 |
| T-27 | 实现审核进度条 + 快捷入口链接 | JS 逻辑 | T-24 | 低 |
| T-28 | 端到端测试：建底座后打开总览 → 数据正确 | 测试报告 | T-26 | 中 |

### Phase 4：正式审核 + 报告生成（P0）

| 任务编号 | 任务名称 | 产出物 | 依赖 | 颗粒度 |
|:---:|:---|:---|:---:|:---|
| T-29 | `run_audit.py` 新增 `review` 子命令骨架 | run_audit.py 修改 | T-10 | 中 |
| T-30 | 实现审核前置检查（human_verified 校验 + 闸门） | review 子命令逻辑 | T-29 | 中 |
| T-31 | 实现读取 corrected_data.json → 规范对账（铁律 R-01/R-04/R-05） | review 子命令逻辑 | T-30 | 高 |
| T-32 | 实现逻辑一致性检查（10 子项，铁律 R-09/R-17） | review 子命令逻辑 | T-31 | 高 |
| T-33 | 实现运算规范审核（按需，铁律 R-03） | review 子命令逻辑 | T-31 | 中 |
| T-34 | 实现伪造检测 + 底稿追溯（铁律 R-06/R-15） | review 子命令逻辑 | T-31 | 中 |
| T-35 | `run_audit.py` 新增 `report` 子命令 | run_audit.py 修改 | T-29 | 中 |
| T-36 | 实现审核日志 → HTML 报告生成（9 章节强制，约束 C-15） | report 子命令逻辑 | T-35 | 高 |
| T-37 | 实现置信度标注 + 三级分类 + 自检（铁律 R-08/R-18/R-19） | report 子命令逻辑 | T-36 | 中 |
| T-38 | 端到端测试：核对完成 → 审核 → 报告 | 测试报告 | T-37 | 中 |

### Phase 5：多 Agent 并行集成（P1）

| 任务编号 | 任务名称 | 产出物 | 依赖 | 颗粒度 |
|:---:|:---|:---|:---:|:---|
| T-39 | 实现阶段 3 多 Agent 拆分逻辑（按专业） | review 子命令逻辑 | T-32 | 中 |
| T-40 | 实现子 Agent 任务包生成（读取 corrected_data.json） | review 子命令逻辑 | T-39 | 中 |
| T-41 | 实现子 Agent 结果汇总 + 跨专业交叉验证 | review 子命令逻辑 | T-40 | 中 |
| T-42 | 端到端测试：多专业 → 并行审核 → 汇总报告 | 测试报告 | T-41 | 中 |

### Phase 6：增量更新 + 断档检测（P1）

| 任务编号 | 任务名称 | 产出物 | 依赖 | 颗粒度 |
|:---:|:---|:---|:---:|:---|
| T-43 | 实现 `--incremental` 增量模式（对比已有文件） | build_foundation.py 修改 | T-10 | 中 |
| T-44 | 实现断档检测逻辑（桩号/日期/编号连续性） | build_foundation.py 内函数 | T-43 | 中 |
| T-45 | 实现断档结果写入 index.json + 项目总览展示 | 联动修改 | T-44 | 低 |
| T-46 | 端到端测试：补充文件 → 增量更新 → 断档检测 | 测试报告 | T-45 | 中 |

### Phase 7：SKILL.md 更新 + 集成测试（P0）

| 任务编号 | 任务名称 | 产出物 | 依赖 | 颗粒度 |
|:---:|:---|:---|:---:|:---|
| T-47 | SKILL.md 更新四阶段流水线描述 | SKILL.md 修改 | T-11, T-22, T-28, T-38 | 中 |
| T-48 | SKILL.md 新增触发语句和执行规则 | SKILL.md 修改 | T-47 | 低 |
| T-49 | SKILL.md 更新多 Agent 并行审核集成描述 | SKILL.md 修改 | T-42 | 低 |
| T-50 | 全链路集成测试（阶段 1→2→3→4） | 测试报告 | T-47~T-49 | 高 |
| T-51 | README.md 更新 | README.md 修改 | T-50 | 低 |
| T-52 | PDF.js 离线预下载到 templates/ | pdf.min.js | — | 低 |

---

## 八、验收标准

### 8.1 功能验收

| 编号 | 验收项 | 验收方法 |
|:---:|:---|:---|
| V-01 | 指定文件夹路径 → 自动建立数据底座 | `run_audit.py build <路径>` 成功执行，生成完整目录结构 |
| V-02 | index.json 内容完整 | 所有文件都有对应记录，字段无空值，含前置信息和文件分类 |
| V-03 | 文件自动分类正确 | 场道/空管/助航/弱电/供油/通用/依据文件分类正确 |
| V-04 | 数据质量检测自动执行 | 每个文件都有 quality.json，告警数写入 index.json |
| V-05 | 混淆检测自动执行 | 每个文件都有 confusion.json，存疑数写入 index.json |
| V-06 | Web 编辑器可打开 | 双击 data-editor.html 能加载 JSON 数据 |
| V-07 | Web 编辑器可修改导出 | 修改字段 → 导出 → corrected_data.json 内容正确 |
| V-08 | Web 编辑器更新 index.json | 导出后 index.json 的 human_verified 更新为 true |
| V-09 | 项目总览展示正确 | 打开 project-dashboard.html，数据与 index.json 一致 |
| V-10 | 人工核对闸门有效 | 未核对完成时，`review` 子命令拒绝执行 |
| V-11 | 正式审核正常执行 | 核对完成后，`review` 成功执行，生成审核日志 |
| V-12 | 报告生成正确 | `report` 生成 HTML 报告，9 章节完整 |
| V-13 | 增量更新有效 | 补充文件后 `build --incremental` 只处理新文件 |
| V-14 | 断档检测有效 | 缺少桩号时 index.json 的 gaps 数组有记录 |
| V-15 | 多 Agent 并行有效 | 多专业资料并行审核，结果正确汇总 |
| V-16 | OCR 引擎选择贯穿 | 前置信息选择的引擎传递到 build_foundation.py |
| V-17 | 铁律 R-16 行数校验 | OCR 提取后自动做行数校验，不通过自动重试 |
| V-18 | 铁律 R-10 数据质量前置 | 数据质量检测在规范对账之前执行 |

### 8.2 数据同步验收

| 编号 | 验收项 |
|:---:|:---|
| V-19 | OCR 完成后，项目总览刷新能看到新文件 |
| V-20 | 质量检测完成后，项目总览刷新能看到告警数 |
| V-21 | 人工核对完成后，项目总览刷新能看到 verified 状态 |
| V-22 | 审核完成后，项目总览刷新能看到 audit_status 更新 |
| V-23 | 报告生成后，项目总览刷新能看到 stage=reported |
| V-24 | 增量更新后，项目总览刷新能看到新追加的文件 |
| V-25 | 断档检测后，项目总览刷新能看到 gaps 信息 |

### 8.2 v7.0 新增验收项

| 编号 | 验收项 | 验收方法 |
|:---:|:---|:---|
| V-46 | 三层 JSON 结构正确生成 | build 后每个被审核文件的 JSON 含 structured_rows + full_text + page_map 三层 |
| V-47 | 文档关联图谱自动构建 | build 后数据底座/ 下存在 link_graph.json，含 same_pile / same_date_log 边 |
| V-48 | 签字一致性检测可执行 | review --check-signatures 成功执行，生成签字异常报告 |
| V-49 | 签字对比图内嵌 | 审核报告中签字异常章节含 base64 内嵌对比图 |
| V-50 | human_verified 分层正确 | 非扫描件自动 human_verified=true，扫描件为 false |
| V-51 | data-editor 三栏式布局 | 打开 data-editor.html 可见左侧文档树 + 右侧三 Tab（表格/原文/图纸） |
| V-52 | 差异化提取正确 | 非扫描 PDF 直接文本提取（秒级），Excel 仅记元数据不逐行 OCR |
| V-53 | 图纸截图自动生成 | 含图 PDF 的 _images/ 目录下有截图文件，page_map 中 image_ref 正确指向截图路径 |

### 8.3 v7.1 新增验收项

| 编号 | 验收项 | 验收方法 |
|:---:|:---|:---|
| V-54 | 诊断面板可折叠/展开 | 页面顶部诊断面板可点击折叠/展开，日志内容逐步追加 |
| V-55 | 非文档文件自动过滤 | 打开含 PNG/TXT/MD 的 index.json，非文档文件进入折叠区，主树仅显示有效文档 |
| V-56 | 进度计数正确 | 进度显示 (已核对/有效文档总数)，非文档不计入 |
| V-57 | 状态图标语义正确 | 五种状态（已核对/待核对/需重扫/非文档/加载失败）CSS 绘制，tooltip 说明原因 |
| V-58 | 确认按钮安全闸门有效 | 非文档/无结构化数据时按钮禁用并显示原因，有效文档时启用 |
| V-59 | 问题视图加载正确 | ⚠️ Tab 显示质量告警和 OCR 存疑项，按区域分组，可批量应用建议值 |
| V-60 | 四种加载方式可用 | File System Access API / 拖拽 / 手动选择 / HTTP 模式四种方式均能加载数据 |
| V-61 | 数据结构兼容层有效 | 同时支持 structured_rows 和旧版 rows 格式，自动检测并适配 |
| V-62 | 快捷键 Ctrl+Enter 确认 | 点击确认按钮时按下 Ctrl+Enter 触发确认操作 |
| V-63 | 精密仪表盘视觉风格 | 深墨蓝/炭灰骨架色、工程网格底纹、等宽数字、双字体系统、微动效反馈 |

### 8.4 v7.2 新增验收项

| 编号 | 验收项 | 验收方法 |
|:---:|:---|:---|
| V-64 | 分类关键词无硬编码副本 | `grep -n "PROFESSIONAL_RULES" scripts/build_foundation.py` 搜索结果仅保留内存常量生成函数，源码内无与 references/classification-terms.json 重复的死关键词表；build 时从三真相源（classification-terms.json + rules trigger_when.doc_type + FIELD_ALIAS_MAP）运行时聚合生成 |
| V-65 | 三级分类生效 | 标杆项目 CFG桩 xlsx 归入"01_场道工程/施工记录/CFG桩施工记录"，index.json 每条 document 含 classification_source 与 classification_confidence 字段；故意放 references 未出现的新术语文件（如"水泥土搅拌桩记录.xlsx"），LLM 路给出专业+置信度，并在 data-editor 标黄"AI分类·待确认"；断网/无 LLM_API_KEY 时，所有分类仍能落至合理专业或标待确认，不报错 |
| V-66 | 图纸角色正交 | 同一文件"地基处理平面图.pdf"，施工阶段项目 C-01 默认为 reference_files；仅把 preconditions.stage 改成"竣工移交"重新 build，同一文件 C-01 默认为 audited_files 并在 build 终端输出竣工图纸高亮提示；两次 index.json 的 document.is_drawing 标签均为 true |
| V-67 | 电子表语义正确 | 标杆测试3的 xlsx 文件：data-editor 状态栏不显示"OCR XX%"，改显"电子表·已记元数据·无需OCR"；project-dashboard.html 的 OCR% 列对该文件显示"免OCR"而非数字百分号；扫描件 PDF 的 OCR% 渲染未被误伤 |
| V-68 | 拒识不卡流程 | 构造一个 ocr_confidence=0.6 的糊件测试文档，跑 review 不被闸门拒绝；报告中该件所有规则触发项 severity 标为"存疑"（R-18 四级），且批量出现在 R-20 待核实清单 + 报告专段"基于低置信识别需人工核实"；总览建议重扫 TOP 10 卡片按 `(1 - ocr_confidence) × Fatal估算` 正确排序；无 Fatal 关联的纯文本资料不会错误出现在重扫建议前列 |
| V-69 | 表头三路融合有效 | 构造"OCR把'桩顶高程'认成'桩顶程高' + 列顺序颠倒（桩底在前、桩顶在后）"的桩基类扫描件测试表，仍能正确映射至 actual_length/top_elev/bottom_elev 三标准槽位；审核时 LG-001 桩长自洽校验正确命中不命中；断网时路1别名+路2特征+路4人工三路仍可用，不依赖 LLM；土方/混凝土类文档（无数学链）在 spec 中明确标注"路2无数学约束，为独立推断"——此为边界声明，不视为失败 |
| V-70 | 自成长可见（分类+表头两处） | 分类：data-editor 人工把某文件从"通用资料/其他"改为"01_场道工程/施工记录"，references/classification-terms.json 多出一条 status=candidate 的同文件名模式新词条；下次重跑同模式文件，C-01 分类确认面板高亮"候选分类，请确认"，确认后 status=active；表头：人工把某认烂列确认映射到"灌入量"，下次同类表该别名自动命中，不需要再人工改 |

### 8.5 约束验收

| 编号 | 验收项 |
|:---:|:---|
| V-26 | 前置信息 5 项全部展示，无默认值跳过（约束 C-02） |
| V-27 | 文件分类确认在审核前执行（约束 C-01） |
| V-28 | 设计变更文件自动归类为依据文件（约束 C-04） |
| V-29 | 排除文件在审核前明确声明（约束 C-05） |
| V-30 | 审核报告为统一 HTML，无独立 MD 报告（约束 C-15） |
| V-31 | 审核报告包含 OCR 待核实清单（约束 C-11） |
| V-32 | 数据底座纯文件存储，无数据库（约束 C-21） |

---

## 九、自审计

### 9.1 需求覆盖审计

| 需求类别 | 需求编号 | 覆盖状态 | 实现任务 |
|:---|:---|:---:|:---|
| 现有功能 F-01~F-20 | F-01~F-20 | ✅ 已实现 | v5.0 保留，不改动 |
| 新增功能 N-01 | 数据底座建立 | ✅ 覆盖 | T-01~T-11 |
| 新增功能 N-02 | index.json 总索引 | ✅ 覆盖 | T-08 |
| 新增功能 N-03 | JSON 三层结构存储 | ✅ 覆盖 | T-04, T-06 |
| 新增功能 N-04 | Web 数据编辑器 | ✅ 覆盖 | T-12~T-22 |
| 新增功能 N-05 | 项目总览 HTML | ✅ 覆盖 | T-23~T-28 |
| 新增功能 N-06 | 文档关联图谱 | ✅ 覆盖 | build_foundation.py build_link_graph() |
| 新增功能 N-07 | 签字一致性检测 | ✅ 覆盖 | signature_check.py |
| 新增功能 N-08 | 四阶段流水线 | ✅ 覆盖 | T-10, T-29~T-38 |
| 新增功能 N-09 | 增量更新 | ✅ 覆盖 | T-43 |
| 新增功能 N-10 | 断档检测 | ✅ 覆盖 | T-44, T-45 |
| 铁律 R-01~R-20 | 20 条铁律 | ✅ 覆盖 | §2.3 铁律集成点列表明示每条铁律在哪个阶段执行 |
| 约束 C-01~C-25 | 25 条约束 | ✅ 覆盖 | §2.4 约束需求表 + 散落在各设计章节 |
| 非功能 NF-01~NF-09 | 9 条非功能需求 | ✅ 覆盖 | §2.5 非功能需求表 + §八 约束验收 |

### 9.2 现有功能兼容审计

| 现有功能 | v6.0 影响 | 兼容措施 |
|:---|:---|:---|
| F-01~F-10（脚本功能） | 无影响，脚本保留 | `run_audit.py` 原有子命令（info/extract/batch/postprocess/audit）不变 |
| F-11（HTML 报告模板） | 无影响 | `report` 子命令复用此模板 |
| F-12（审核范围清单模板） | 无影响 | 保留，项目总览可替代但其仍可用于多 Agent 场景 |
| F-13（前置信息收集） | 无影响 | Step 0 保留，OCR 引擎选择已加入 |
| F-14~F-18（铁律/红线/三级输出） | 无影响 | 审核逻辑不变，数据来源从直接 OCR 变为 corrected_data.json |
| F-19（Obsidian 集成） | 无影响 | 阶段 3 审核时按需回源 |
| F-20（OCR 引擎选择） | 无影响 | 前置信息选择传递到 build_foundation.py |
| F-16（多 Agent 并行） | 集成调整 | 子 Agent 不再自己做 OCR，读取 corrected_data.json |

### 9.3 数据流闭环审计

| 阶段 | 输入 | 输出 | 下游消费 | 闭环状态 |
|:---|:---|:---|:---|:---:|
| 阶段1 | 项目文件夹 + 前置信息 | index.json + JSON（三层结构）+ quality.json + confusion.json | 阶段2 Web 编辑器 | ✅ |
| 阶段2 | {文件}.json + quality.json + confusion.json | corrected_data.json + corrections.json | 阶段3 审核脚本 | ✅ |
| 阶段3 | corrected_data.json | 审核日志.json | 阶段4 报告生成 | ✅ |
| 阶段4 | 审核日志.json | 审核报告.html | 用户 | ✅ |

### 9.4 落地可行性审计

| 风险点 | 风险描述 | 应对措施 | 可行性 |
|:---|:---|:---|:---:|
| File System Access API 兼容性 | 仅 Chrome/Edge 支持，Firefox/Safari 不支持 | 降级方案：下载 JSON 文件，手动覆盖到项目文件夹 | ✅ 可落地 |
| PDF.js CDN 依赖 | 离线环境无法加载 CDN | 预下载 pdf.min.js 放入 templates/ 目录（T-52） | ✅ 可落地 |
| 大文件 JSON 加载 | 49 页扫描件可能有数百行数据 | 分页加载，每次只渲染当前页的表格行 | ✅ 可落地 |
| build_foundation.py 与现有 OCR 脚本集成 | 需要调用 ocr_image.py 但不能 import | 使用 subprocess 调用 CLI 命令 | ✅ 可落地 |
| index.json 并发写入 | Web 编辑器和脚本同时写 index.json | 单人场景，不会并发；Web 编辑器导出时写完整文件 | ✅ 可落地 |
| OCR 结果到结构化 JSON 的转换 | 不同资料类型字段不同 | 先支持碎石桩施工记录，其他类型逐步扩展 | ✅ 可落地（分步） |
| Web 编辑器跨文件导航 | 一个项目可能有多个文件需要核对 | 文件列表下拉选择，切换时保存当前文件修改（T-14） | ✅ 可落地 |
| 多 Agent 读取 corrected_data.json | 子 Agent 需要读取不同专业的数据 | 按专业拆分，每个 Agent 只读自己专业的文件 | ✅ 可落地 |
| 增量更新时旧数据保留 | 旧文件不重新 OCR，只处理新文件 | 对比 index.json 中已有文件，跳过已处理 | ✅ 可落地 |

### 9.5 遗漏检查

| 检查项 | 状态 | 说明 |
|:---|:---:|:---|
| 前置信息是否传入 index.json | ✅ | index.json 的 preconditions 字段记录 |
| OCR 引擎选择是否贯穿全流程 | ✅ | build 子命令的 --engine 参数，记录到 index.json |
| 文件分类是否在审核前确认 | ✅ | index.json 的 file_classification 字段记录 |
| 设计变更文件是否自动归类 | ✅ | 分类规则表中明确（约束 C-04） |
| 多 Agent 并行审核是否兼容 | ✅ | 阶段 3 执行，读取 corrected_data.json，不冲突 |
| 审核历史是否可追溯 | ✅ | index.json 的 audit_logs 数组记录每次审核 |
| 项目总览如何打开数据编辑器 | ✅ | 总览页面提供链接（相对路径 `data-editor.html`） |
| 修正记录是否可追溯 | ✅ | corrections.json 记录每次修改的原值、新值、时间 |
| 断档检测结果在哪展示 | ✅ | index.json 的 gaps 数组 + 项目总览页面展示 |
| 增量更新时旧数据是否保留 | ✅ | 旧文件不重新 OCR，只处理新文件 |
| 审核范围清单模板是否还需要 | ✅ | 保留，多 Agent 场景仍使用 |
| 铁律 R-20 OCR 存疑项在 v6.0 中如何执行 | ✅ | 阶段 1 混淆检测生成存疑清单，阶段 2 Web 编辑器中逐条确认 |
| 约束 C-07 过程资料签字判定 | ✅ | 前置信息中阶段决定判定标准，SKILL.md 已有规则 |
| 约束 C-12 过程资料上下文标注 | ✅ | 审核报告第一章（审核概要）中标注 |
| 约束 C-14 数据质量告警去重 | ✅ | data_quality_check.py 已实现交替模式去重逻辑 |
| 约束 C-16 输出完整性校验 | ✅ | 阶段 4 自检清单强制校验 |
| 约束 C-18 Obsidian 首次探测 | ✅ | SKILL.md 已有，v6.0 不改动 |
| 约束 C-22 git 版本追踪 | ✅ | 纯文件存储，天然支持 git |
| 约束 C-23 OCR 原始输出 | ✅ | {文件}_ocr.json 保存原始输出 |
| 约束 C-24 修正记录日志 | ✅ | corrections.json 记录所有人工修正 |
| 约束 C-25 审核日志 | ✅ | 审核日志/AU-{日期}-{序号}.json |
| v7.0 三层 JSON 结构 | ✅ | build_foundation.py 输出 structured_rows + full_text + page_map |
| v7.0 文档关联图谱 | ✅ | build_foundation.py 自动构建 link_graph.json |
| v7.0 签字一致性检测 | ✅ | signature_check.py，pHash + SSIM 双指标 |
| v7.0 human_verified 分层 | ✅ | 非扫描件自动 true，扫描件强制人工核对 |
| v7.0 差异化提取 | ✅ | 非扫描 PDF 直接文本提取，Excel 仅记元数据 |
| v7.0 图纸截图 | ✅ | 含图 PDF 自动截图存 _images/ |
| v7.0 data-editor 三栏升级 | ✅ | 文档树 + 表格/原文/图纸三 Tab |
| v7.1 诊断面板 | ✅ | 可折叠，实时显示加载过程和文档结构 |
| v7.1 文档树优化 | ✅ | isNonDoc 过滤非文档文件，主树仅显示有效文档 |
| v7.1 状态语义分级 | ✅ | 五种 CSS 绘制状态图标，tooltip 说明原因 |
| v7.1 问题视图 + 批量应用建议值 | ✅ | 按区域分组，支持批量修正和标记已处理 |
| v7.1 安全闸门强化 | ✅ | 确认按钮在非文档/无数据时禁用并显示原因 |
| v7.1 精密仪表盘视觉 | ✅ | 深墨蓝/炭灰骨架色、工程网格底纹、等宽数字、双字体系统 |

### 9.6 颗粒度对齐审计

| 层级 | 颗粒度 | 对齐状态 | 说明 |
|:---|:---|:---:|:---|
| 需求 → 任务 | 每个需求都有对应任务 | ✅ | N-01→T-01~T-11, N-04→T-12~T-22, N-05→T-23~T-28, N-07→T-29~T-38 |
| 任务 → 产出物 | 每个任务都有明确产出物 | ✅ | 每个任务标注了产出物（脚本文件/HTML 文件/JS 逻辑/测试报告） |
| 产出物 → 验收标准 | 每个产出物都有验收项 | ✅ | V-01~V-32 + V-46~V-63 覆盖所有关键产出物 |
| 数据流 → 文件 | 每个数据流都有明确的文件载体 | ✅ | JSON（三层结构）/quality/confusion/corrected/corrections/审核日志/审核报告 |
| 同步矩阵 → 事件 | 每个数据变更事件都覆盖了所有受影响文件 | ✅ | §六 同步矩阵覆盖 9 个事件 × 8 个文件 |
| 铁律 → 阶段 | 每条铁律都标注了在哪个阶段执行 | ✅ | §2.3 铁律表的"v6.0 集成点"列 |
| 约束 → 设计 | 每条约束都在设计章节有对应措施 | ✅ | §4.x 详细设计中引用了对应约束编号 |

### 9.7 设计决策冲突审计

| 冲突点 | 项目记忆中的旧设计 | PROJECT_SPEC 中的新设计 | 决议 |
|:---|:---|:---|:---|
| 数据底座建完后是否自动审核 | "数据底座需在建立完成后自动启动审核" | 设人工核对闸门 | **采用新设计**：铁律 R-02/R-20 要求 OCR 结果必须人工复核，不能跳过 |
| MD 文件是否可编辑并反向更新 JSON | "数据底座需支持人工核改后反向更新JSON" | v7.0 取消 MD 生成，Web 编辑器是唯一编辑入口 | **采用新设计**：三层 JSON 结构（structured_rows + full_text + page_map）取代 MD，避免双写冲突 |
| 文档生成模块产出物 | "文档生成模块仅产出三类文件" | 统一 HTML 为唯一交付物 | **采用新设计**：约束 C-15 已明确统一为 HTML |

---

## 十、实施顺序

严格按以下顺序执行，每个 Phase 完成后验证再进入下一个：

```
Phase 1（T-01~T-11）：数据底座核心
    ↓ 验证：指定文件夹 → 生成完整数据底座（V-01~V-05, V-16~V-18）

Phase 2（T-12~T-22）：Web 数据编辑器
    ↓ 验证：打开编辑器 → 修改 → 导出 → index.json 更新（V-06~V-08）

Phase 3（T-23~T-28）：项目总览仪表盘
    ↓ 验证：建底座后 → 总览数据正确（V-09, V-19~V-20）

Phase 4（T-29~T-38）：正式审核 + 报告
    ↓ 验证：核对完成 → 审核 → 报告（V-10~V-12, V-21~V-23）

Phase 5（T-39~T-42）：多 Agent 并行集成
    ↓ 验证：多专业 → 并行审核 → 汇总（V-15）

Phase 6（T-43~T-46）：增量更新 + 断档
    ↓ 验证：补充文件 → 增量更新 → 断档检测（V-13~V-14, V-24~V-25）

Phase 7（T-47~T-52）：SKILL.md + 集成
    ↓ 验证：全链路测试通过（V-26~V-32）

Phase 8（T-53~T-72）：规则管理子系统 v6.1（详见第十一章）
    ↓ 验证：93 条规则全部通过 Schema 校验 + 子系统 7/7 集成测试通过（V-33~V-45）

Phase 9（v6.1.1）：审核闸门强化 + 字段别名映射 + 沉管/拔管时间规则
    ↓ 验证：端到端测试 8/8 通过（规则加载 93 条 + LG-001 桩长自洽命中 3 条违规）

Phase 10（v7.0）：三层JSON数据底座 + 文档关联图谱 + 签字一致性检测 + data-editor三栏升级
    ↓ 验证：V-46~V-53 全部通过（三层JSON结构 + link_graph + 签字检测 + human_verified分层）

Phase 11（v7.1）：data-editor 精密仪表盘升级
    ↓ 验证：V-54~V-63 全部通过（诊断面板 + 文档树优化 + 状态分级 + 问题视图 + 安全闸门 + 视觉风格）

Phase 12（v7.2）：数据底座基础能力增强
    ├─ 12.1（C3+C6，1天）：状态语义修正（电子表/非扫描PDF 显示"无需OCR"）+ 规格自洁文档内部矛盾清零
    │   ↓ 验证：V-67（C3）+ C6 四处 grep 无矛盾
    ├─ 12.2（C2，1-2天）：图纸角色解耦 is_drawing 标签 + stage→默认角色映射 + build 阶段竣工图终端提示
    │   ↓ 验证：V-66
    ├─ 12.3（C1，2天）：三真相源聚合分类词表 + 三级判定 + 人工闸门 + 简化自成长候选→确认
    │   ↓ 验证：V-64 + V-65 + V-70（分类部分）
    ├─ 12.4（C5，2天）：表头三路融合（别名+列特征+数学链约束+人工）+ header_mapping 独立表存储
    │   ↓ 验证：V-69 + V-70（表头部分）
    └─ 12.5（C4，1天）：文档级置信度→R-18存疑降级→R-20待核实批量入 + 总览建议重扫 TOP 10
        ↓ 验证：V-68
    ↓ 总验证：V-64~V-70 全部通过
```

---

## 十一、规则管理子系统 v6.1

> **Change-ID**: `design-rule-management-subsystem`
> **状态**: 已实施（2026-07-31）
> **详细设计文档**: `.trae/specs/design-rule-management-subsystem/spec.md`
> **测试覆盖**: 规则引擎 6/6 + 跨单位性能 4/4 + Schema 93/93 + 子系统集成 7/7 + 端到端 8/8

### 11.1 子系统定位

将原本散落在 `references/logic-conflict-patterns.md`、`references/data-quality-patterns.md` 等 markdown 文档中的规则，重构为形式化存储、可视化管理、可自成长的独立子系统（当前共 93 条规则）。解决原有规则体系的层级错位（如原 R-12 高程自洽实为 L2 逻辑一致性却被列为"铁律"）、非结构化存储、无生命周期管理、无反馈闭环等问题。

### 11.2 核心能力

| 能力 | 说明 |
|------|------|
| **三层规则分级** | L1 铁律(17)/L2 逻辑一致性(71)/L3 业务合理性(5)，共 93 条（含 1 条 deprecated） |
| **规则形式化存储** | 每条规则独立 JSON 文件，含 trigger_when/check_expr/error_template/changelog/stats |
| **规则管理面板** | Web UI（`rule-manager.html`），4 标签页：规则列表/新建规则/统计仪表盘/反思报告 |
| **可视化规则编辑器** | 非技术用户友好的无代码规则创建，实时预览 JSON 结构 |
| **规则生命周期** | draft → testing → incubating → active，含自动提升（≥3 项目 + 误报率<10%） |
| **反馈闭环** | 漏审/误报反馈 → LLM 聚类分析（DBSCAN + embedding）→ 候选规则 → 管理员审批 |
| **LLM 自成长** | 定时反思调度器（每周），汇总审核事件 + 反馈 + 规则统计，生成优化建议报告 |
| **规则效力自监控** | 命中率/误报率统计，低活跃规则检测，高误报规则自动降级（L2→L3 或 L3→deprecated） |
| **跨单位对照** | 监理-施工方数据对齐视图（`alignment-view.html`），哈希索引 + 分块处理 |
| **协同确认机制** | 跨单位规则须经双方或管理员确认方可生效 |

### 11.3 规则数据模型（JSON Schema 摘要）

每条规则以独立 JSON 文件存储，完整 Schema 见 `rules/schema/rule-schema.json`。核心字段：

```json
{
  "rule_id": "LG-001",                    // 全局唯一 ID
  "name": "高程自洽校验",
  "level": "L2-LOGIC",                    // L1-IRON / L2-LOGIC / L3-BUSINESS
  "scope": "SINGLE_DOC",                  // SINGLE_DOC / CROSS_DOC / CROSS_UNIT
  "category": "数学自洽",
  "description": "碎石桩实长必须等于桩顶高程减桩底高程，容差 ±0.1m",
  "trigger_when": {                       // 触发条件
    "doc_type": ["碎石桩施工记录", "PHC管桩施工记录"],
    "field_required": ["实长", "桩顶高程", "桩底高程"]
  },
  "check_expr": {                         // 校验表达式
    "type": "expression",
    "expr": "abs(实长 - (桩顶高程 - 桩底高程)) <= 0.1",
    "language": "jinja-expr",
    "fallback": "python_eval"
  },
  "error_template": "桩号 {pile_no} 高程自洽失败：实长 {实长}m，...",
  "severity_on_violation": "Sanity Check",  // Fatal / Sanity Check / Best Practice
  "remediation": "核查实长记录是否被涂改，或高程数据是否抄写错误",
  "status": "active",                      // draft/testing/incubating/active/deprecated
  "source": "system",                      // system/custom/incubated
  "version": "1.2.0",                      // 语义化版本号
  "created_at": "2026-07-30T10:00:00",
  "updated_at": "2026-07-30T10:00:00",
  "owner": "system",
  "applies_to": {                          // 适用范围
    "professional": ["01_场道工程"],
    "subdivision_codes": ["01-03"]
  },
  "effective_scope": "global",             // global / project（v6.1 新增）
  "project_scope": null,                   // project 时填项目名
  "stats": {                               // 效力统计（rule_monitor 维护）
    "total_hits": 0, "total_reviews": 0,
    "hit_rate": 0.0, "false_positive_count": 0, "false_positive_rate": 0.0,
    "last_hit_at": null, "last_review_at": null
  },
  "alignment": null,                       // 跨单位规则的对齐配置（仅 CROSS_UNIT）
  "changelog": [                           // 变更历史
    {
      "version": "1.0.0", "date": "2026-07-24", "author": "system",
      "change": "初始版本，从铁律 R-12 迁移并修正层级（原错归 L1，实际为 L2 数学自洽）"
    }
  ]
}
```

**跨单位规则额外字段 `alignment`**：

```json
{
  "alignment": {
    "party_a": "supervisor",               // 监理方
    "party_b": "contractor",               // 施工方
    "join_key": ["pile_no"],               // 对齐键（如桩号）
    "field_a": "实长",                      // 甲方对照字段
    "field_b": "实长",                      // 乙方对照字段
    "doc_type_a": "监理抽测记录",
    "doc_type_b": "施工记录"
  }
}
```

### 11.4 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    规则管理子系统（Rule Management Subsystem）        │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  前端层（Frontend）                                          │   │
│  │  ├── rule-manager.html      规则管理面板（4 标签页）        │   │
│  │  ├── feedback-collector.html 反馈收集组件（嵌入审核报告）   │   │
│  │  └── alignment-view.html    跨单位对齐视图组件              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              ↕ REST API                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  API 层（rule_admin.py，RuleAdminServer）                   │   │
│  │  ├── /api/rules             规则 CRUD + 状态流转 + 协同确认 │   │
│  │  ├── /api/feedbacks         反馈 CRUD + 分析触发            │   │
│  │  ├── /api/reflections       反思报告列表 + 手动触发         │   │
│  │  └── /api/incubator         候选规则提升/驳回               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              ↕                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  核心引擎层（rule_engine.py）                               │   │
│  │  ├── RuleLoader             从 rules/ 加载 active 规则       │   │
│  │  ├── RuleMatcher            按作用域/资料类型匹配规则        │   │
│  │  ├── SingleDocChecker       单资料规则执行                   │   │
│  │  ├── CrossDocChecker        跨资料规则执行                   │   │
│  │  ├── CrossUnitChecker       跨单位规则执行（哈希索引+分块）  │   │
│  │  ├── ExpressionEvaluator    表达式求值（jinja-expr/python）  │   │
│  │  └── ViolationReporter      生成违规发现                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              ↕                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  存储层（File System，零数据库依赖）                        │   │
│  │  ├── rules/                 规则文件库（93 个 JSON）         │   │
│  │  │   ├── L1-iron/ (17) / L2-logic/ (71+1 deprecated) / L3-business/ (5)  │   │
│  │  │   ├── custom/draft/ / custom/incubator/│   │
│  │  │   ├── reflections/ / schema/ / registry.json              │   │
│  │  ├── feedbacks/             反馈存储（JSON）                 │   │
│  │  └── audit_memory/          审核记忆流（JSONL 事件日志）     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              ↕                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  自成长层（Self-Growth）                                    │   │
│  │  ├── feedback_analyzer.py   LLM 反馈分析管道                │   │
│  │  │   ├── 向量化（sentence-transformers / sklearn-tfidf / jaccard）│
│  │  │   ├── 聚类（DBSCAN / greedy 降级）                       │   │
│  │  │   └── 候选规则生成（LLM / template 降级）                │   │
│  │  ├── rule_reflector.py      定时反思调度器（每周）          │   │
│  │  │   ├── 审核事件汇总 + 反馈聚类 + 规则统计                 │   │
│  │  │   ├── LLM 生成优化建议报告                               │   │
│  │  │   └── 候选规则写入 incubator                             │   │
│  │  ├── rule_monitor.py        规则效力自监控                  │   │
│  │  │   ├── 命中率/误报率统计 + 低活跃检测 + 休眠检测          │   │
│  │  │   └── 自动降级（L2→L3 或 L3→deprecated，L1 豁免）       │   │
│  │  ├── rule_lifecycle.py      规则生命周期管理                │   │
│  │  │   └── record_audit_result + promote_to_incubating        │   │
│  │  └── audit_memory.py        审核记忆流（JSONL 事件日志）    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              ↕
                    现有审核流水线
                  (review_audit.py)
```

### 11.5 API 端点（rule_admin.py）

启动方式：`python scripts/rule_admin.py --port 8765`

| 方法 | 端点 | 说明 |
|:---:|:---|:---|
| GET | `/api/rules` | 规则列表（支持 ?level=&scope=&status=&q=） |
| GET | `/api/rules/{id}` | 规则详情 |
| POST | `/api/rules` | 创建规则（草稿） |
| PUT | `/api/rules/{id}` | 更新规则（自动写 changelog） |
| DELETE | `/api/rules/{id}` | 删除规则（仅 draft 状态） |
| POST | `/api/rules/{id}/transition` | 状态流转 |
| POST | `/api/rules/{id}/confirm` | 协同确认（跨单位规则） |
| POST | `/api/rules/{id}/force_confirm` | 管理员强制确认 |
| POST | `/api/rules/{id}/test` | 在沙箱中测试规则 |
| GET | `/api/rules/{id}/stats` | 命中率/误报率统计 |
| GET | `/api/rules/{id}/changelog` | 变更历史 |
| GET | `/api/feedbacks` | 反馈列表 |
| GET | `/api/feedbacks/{id}` | 反馈详情 |
| GET | `/api/feedbacks/stats` | 反馈统计 |
| POST | `/api/feedbacks` | 提交反馈 |
| POST | `/api/feedbacks/analyze` | 触发 LLM 分析管道 |
| POST | `/api/feedbacks/{id}/transition` | 更新反馈状态 |
| GET | `/api/reflections` | 反思报告列表 |
| GET | `/api/reflections/{date}` | 指定日期反思报告 |
| POST | `/api/reflections/trigger` | 手动触发反思 |
| GET | `/api/incubator` | 孵化区候选规则列表 |
| GET | `/api/incubator/{id}` | 候选规则详情 |
| POST | `/api/incubator/{id}/promote` | 提升候选规则为 active |
| POST | `/api/incubator/{id}/reject` | 驳回候选规则 |
| GET | `/registry` | 全量注册表 |
| GET | `/stats` | 总览统计 |

### 11.6 反馈闭环与 LLM 自成长

**反馈数据结构**（`feedbacks/schema/feedback-schema.json`）：
- `feedback_id`：FB-YYYY-MM-DD-NNN
- `type`：missed（漏审）/ false_positive（误报）
- `audit_id` / `rule_id` / `user_id` / `context` / `user_input`
- `status`：new → analyzed → clustered → resolved

**LLM 反馈分析管道**（`feedback_analyzer.py`）：
1. 加载 status=new 的反馈
2. 向量化（sentence-transformers → sklearn-tfidf → jaccard 三级降级）
3. 聚类（DBSCAN → greedy 相似度聚类降级）
4. 对每类调用 LLM 或规则化模板提取共性模式
5. 生成候选规则 JSON（status=incubating）写入 `rules/custom/incubator/`
6. 更新反馈 status=analyzed, cluster_id
7. 输出分析报告到 `rules/reflections/feedback-analysis-{日期}.md`

**定时反思调度器**（`rule_reflector.py`）：
- 每周一次，汇总审核事件 + 反馈聚类 + 规则统计
- 调用 LLM 生成优化建议报告（无 LLM 时降级为 template 模板分析）
- 候选规则写入 `rules/custom/incubator/`
- 报告输出到 `rules/reflections/rule-monitor-{日期}.md`

**规则效力自监控**（`rule_monitor.py`）：
- 命中率 = total_hits / total_reviews
- 误报率 = false_positive_count / total_hits
- 低活跃检测：total_reviews ≥ 阈值 且 hit_rate = 0
- 高误报检测：false_positive_rate > 30%
- 休眠检测：last_hit_at 距今 > 90 天
- 自动降级：L2 → L3（误报率 > 50%），L3 → deprecated（休眠 > 180 天），**L1 豁免降级**

### 11.7 跨单位对照专项设计

**性能优化**（`rule_engine.py` 的 `CrossUnitChecker`）：
- 按 `join_key` 建立哈希索引，将 O(n*m) 降为 O(n+m)
- 大数据量分块处理（CHUNK_THRESHOLD=5000，CHUNK_SIZE=2000）
- 性能基准：1000 桩位 join = 31.80ms，5000 桩位 = 161.03ms，5001 桩位分块 = 160.99ms
- 分块与非分块路径结果完全一致（581 个违规集合相同）

**数据对齐视图**（`alignment-view.html`）：
- 左列监理方 / 中列差异 / 右列施工方
- 差异行高亮（红色 = 偏差超阈值，黄色 = 一方缺失）
- 支持查看原始资料跳转

**协同确认机制**：
- 跨单位规则创建后状态为 `pending_confirmation`
- 须经双方或管理员确认方可生效
- `rule-manager.html` 突出显示待确认规则
- 确认/驳回后通知发起方

### 11.8 实施任务（Phase A-F，已全部完成）

| Phase | 任务范围 | 状态 |
|:---:|:---|:---:|
| **Phase A** | 规则重构与形式化（Schema + 引擎 + 93 条迁移） | ✅ |
| **Phase B** | 规则管理界面（rule-manager.html + rule_admin.py API） | ✅ |
| **Phase C** | 反馈闭环（feedback_store + feedback_analyzer + feedback-collector.html） | ✅ |
| **Phase D** | 自成长机制（rule_monitor + rule_reflector + audit_memory） | ✅ |
| **Phase E** | 跨单位对照增强（CrossUnitChecker 性能优化 + alignment-view.html + 协同确认 UX） | ✅ |
| **Phase F** | SKILL.md/README.md 更新 + 全链路集成测试 | ✅ |

**关键产出物**：
- `rules/schema/rule-schema.json` + `registry-schema.json` — JSON Schema 定义
- `scripts/rule_engine.py` — 规则引擎核心（RuleLoader/Matcher/Checker/Reporter）
- `scripts/rule_admin.py` — 管理 API 服务（RuleAdminServer，26 个端点）
- `scripts/rule_lifecycle.py` — 生命周期管理（RuleLifecycleManager）
- `scripts/rule_monitor.py` — 效力自监控（RuleMonitor）
- `scripts/rule_reflector.py` — 定时反思调度器（RuleReflector）
- `scripts/feedback_store.py` — 反馈存储（FeedbackStore）
- `scripts/feedback_analyzer.py` — LLM 反馈分析管道（FeedbackAnalyzer）
- `scripts/audit_memory.py` — 审核记忆流（AuditMemory，JSONL 事件日志）
- `scripts/rule_schema_validator.py` — Schema 校验工具
- `scripts/rule_registry_builder.py` — 注册表生成工具
- `templates/rule-manager.html` — 规则管理面板（4 标签页）
- `templates/feedback-collector.html` — 反馈收集组件
- `templates/alignment-view.html` — 跨单位数据对齐视图
- `rules/` — 93 条规则 JSON 文件（L1-iron/L2-logic/L3-business）
- `rules/registry.json` — 全量注册表
- `feedbacks/schema/feedback-schema.json` — 反馈 Schema
- `scripts/test_rule_engine.py` — 规则引擎测试（6/6 通过）
- `scripts/test_cross_unit_perf.py` — 跨单位性能测试（4/4 通过）
- `scripts/test_rule_subsystem_integration.py` — 子系统全链路集成测试（7/7 通过）

### 11.9 验收标准（V-33~V-45）

| 编号 | 验收项 | 验收方法 | 状态 |
|:---:|:---|:---|:---:|
| V-33 | 规则 Schema 校验通过 | `python scripts/rule_schema_validator.py --rules-dir rules` 输出 93/93 PASS | ✅ |
| V-34 | 规则注册表生成正确 | `python scripts/rule_registry_builder.py --validate` 输出 total_rules=93 | ✅ |
| V-35 | 规则引擎核心功能正常 | `python scripts/test_rule_engine.py` 6/6 通过 | ✅ |
| V-36 | 跨单位性能达标 | `python scripts/test_cross_unit_perf.py` 1000 桩位 join < 1s | ✅ |
| V-37 | 反馈存储 CRUD 正常 | 集成测试 test_feedback_store 通过（create/get/list_new/update_status/count） | ✅ |
| V-38 | LLM 反馈分析管道正常 | 集成测试 test_feedback_analyzer 通过（聚类 + 候选规则生成 + 状态流转） | ✅ |
| V-39 | 规则效力监控正常 | 集成测试 test_rule_monitor 通过（detect_low_activity + generate_report） | ✅ |
| V-40 | 审核记忆流正常 | 集成测试 test_audit_memory 通过（append_event + query_by_audit/rule） | ✅ |
| V-41 | 定时反思调度器正常 | 集成测试 test_rule_reflector 通过（reflect + 报告生成） | ✅ |
| V-42 | 规则生命周期正常 | 集成测试 test_rule_lifecycle 通过（record_audit_result + promote_to_incubating） | ✅ |
| V-43 | 管理 API 端点齐全 | 集成测试 test_rule_admin_endpoints 通过（26 个 _handle_xxx 方法存在） | ✅ |
| V-44 | 子系统全链路集成测试 | `python scripts/test_rule_subsystem_integration.py` 7/7 通过 | ✅ |
| V-45 | SKILL.md / README.md 更新 | 规则管理子系统章节已添加，规则数量与 registry.json 一致 | ✅ |

### 11.10 与现有审核流水线的集成

```
阶段 3 正式审核（review_audit.py）
    ↓
读取 corrected_data.json
    ↓
RuleLoader.load_active(rules/)        ← 加载 92 条 active 规则（含 1 条 deprecated 不加载）
    ↓
RuleMatcher.match_by_doc_type(...)    ← 按资料类型匹配规则
    ↓
SingleDocChecker / CrossDocChecker / CrossUnitChecker  ← 执行检查
    ↓
ViolationReporter.generate()          ← 生成违规发现
    ↓
RuleMonitor.update_stats_from_audit_log()  ← 更新规则效力统计
    ↓
AuditMemory.append_audit_completed()  ← 记录审核事件到记忆流
    ↓
RuleLifecycleManager.record_audit_result()  ← 更新 testing 规则的跟踪记录
```

**关键集成点**：
- 规则引擎替代原有的 markdown 规则文档查询
- 审核完成后自动更新规则效力统计（命中率/误报率）
- 审核事件自动写入审核记忆流，供反思调度器汇总
- testing 状态规则的审核结果自动记录到 tracking.json，满足条件自动提升

### 11.11 设计决策记录

| 决策点 | 决策 | 理由 |
|:---|:---|:---|
| 规则存储方式 | 纯 JSON 文件，每条规则一个文件 | 与数据底座保持一致，零数据库依赖，支持 git 版本追踪 |
| LLM 后端 | 优先 OpenAI 风格 API，不可用时降级为 template 模板 | 保证离线/内网环境可用 |
| 聚类算法 | 优先 sklearn DBSCAN，不可用时降级为 greedy 相似度聚类 | 保证无 sklearn 环境可用 |
| 向量化方式 | sentence-transformers > sklearn-tfidf > jaccard 三级降级 | 平衡精度与依赖 |
| L1 铁律是否可降级 | 否，豁免自动降级 | L1 是合规底线，不可削弱 |
| 跨单位规则匹配算法 | 哈希索引 + 分块处理 | 1000 桩位 join < 50ms，5000+ 桩位自动分块 |
| 反思调度周期 | 每周一次 | 平衡时效性与 LLM 成本 |
| 候选规则审批 | 管理员手动提升 | 防止 LLM 误生成规则直接生效 |

---

*文档结束 — v7.1 已实施，v7.0 三层JSON数据底座与文档关联图谱已实施，v6.1 规则管理子系统已实施，v6.1.1 审核闸门与字段别名映射修复已实施，全部测试通过*

---

## v7.0 变更日志（已合并至 1.3 节）

### 数据底座架构重构
1. **三层 JSON 结构**：structured_rows + full_text + page_map
2. **差异化提取**：非扫描 PDF 直接文本提取，Excel 仅记元数据，取消 MD 生成
3. **文档关联图谱**：link_graph.json，支持 same_pile / same_date_log 边类型
4. **图纸截图**：含图 PDF 自动截图存 `_images/`，page_map 记录路径
5. **human_verified 分层**：非扫描件自动通过，扫描件强制人工核对

### 签字一致性检测
1. **可选前置条件**：前置信息确认时选择，默认关闭
2. **检测算法**：pHash + SSIM 双指标
3. **签字特征库**：`_signatures/gallery.json`，baseline + suspects 目录
4. **报告呈现**：签字异常核查专区，base64 内嵌对比图

### data-editor 升级
1. **三栏式界面**：文档树 + 表格/原文/图纸三 Tab
2. **图纸预览**：支持 PDF 页面截图预览
3. **原文预览**：full_text + page_map 分页显示
4. **快捷键**：Ctrl+Enter 确认当前文档

### 分块审核机制
1. **link_graph 精准加载**：按关联图谱加载 depth=1 关联文档
2. **上下文控制**：单块数据量 < 80K tokens
3. **跨分项逻辑检查**：最后单独执行一轮

---

## v7.1 变更日志（data-editor 精密仪表盘升级）

### 诊断面板
1. **可折叠诊断面板**：页面顶部，点击标题折叠/展开
2. **逐步日志输出**：显示 index.json 加载方式、文档元数据、非文档标记、数据结构检测
3. **调试辅助**：console 同步打印，方便开发调试

### 文档树优化
1. **非文档判定逻辑**：isNonDoc() 函数根据扩展名、file_type、data_file 综合判断
2. **折叠区管理**：非文档文件进入「原始文件/调试产物」折叠区，灰色弱样式
3. **进度计数修正**：仅统计有效文档，非文档不计入待核对总数

### 状态语义分级
1. **五种 CSS 状态图标**：已核对(teal)、待核对(amber)、需重扫(amber+orange)、非文档(transparent)、加载失败(red)
2. **tooltip 说明**：每种状态悬停显示原因
3. **纯 CSS 绘制**：不用 emoji，确保跨平台一致性

### 问题视图与批量操作
1. **按区域分组**：问题按桩号/区域聚合，支持折叠/展开
2. **批量应用建议值**：对同一区域多条问题一键修正
3. **逐条修正**：单条问题独立修正
4. **标记已处理**：问题处理后标记状态，不再重复显示

### 加载链路
1. **File System Access API**：首选方式，选择项目文件夹自动加载
2. **拖拽加载**：次选方式，拖拽 JSON 文件到页面
3. **手动选择**：兜底方式，通过文件选择器加载
4. **HTTP 测试模式**：仅 http 协议，基于 location.pathname 推算路径

### 安全闸门
1. **updateConfirmGate 函数**：确认按钮在非文档/无数据时禁用
2. **禁用原因提示**：按钮禁用时显示具体原因
3. **快捷键 Ctrl+Enter**：确认当前文档

### 精密仪表盘视觉
1. **深墨蓝/炭灰骨架色**：--skel-bg=#0f172a, --skel-surface=#1e293b
2. **工程网格底纹**：CSS 网格背景，象征工程图纸
3. **语义化信号色**：teal=已确认, amber=待处理, red=错误
4. **等宽数字**：monospace 字体，便于数据列对齐
5. **双字体系统**：sans-serif 标题 + 正文，monospace 数据
6. **微动效反馈**：树节点 hover/选中过渡、Tab 切换渐变、告警行呼吸高亮

---

## v7.2 变更日志（数据底座基础能力增强）

### C3 状态语义：电子表/非扫描PDF 显示"无需OCR"
1. **新字段 extraction_mode**：index.json document 增 `extraction_mode: "ocr" | "text_pdf" | "docx" | "meta_xlsx" | "image" | "unknown"`，透传 `sniff_document()` 已有 `extraction_method`
2. **data-editor 渲染分支**：meta_xlsx / text_pdf 不显示 OCR%，状态栏显示确定态"电子表·已记元数据·无需OCR"或"电子档·已抽文本·无需OCR"，中性信息色
3. **project-dashboard 同步渲染**：OCR% 列对非 OCR 文件显示"免OCR"文字格，不显示百分号
4. **扫描件未误伤**：仅 `extraction_mode="ocr"` 且 `is_scanned=true` 才显示 OCR% 与需重扫/存疑

### C6 规格自洁（文档内部矛盾清零）
1. **§4.1 JSON Schema 示例统一**：所有单文件示例写为三层结构（structured_rows + full_text + page_map），`rows` 保留作向后兼容 alias，并加"兼容层说明"注释
2. **§8.2 验收编号补齐**：T-53~T-72 断层连续编号，link_graph / 签字检测 / 图纸角色 / 整改台账 四张同步矩阵纳入覆盖
3. **约束 C-15 文字修正**：从"统一HTML唯一交付物"改为"HTML为主交付物，报告页面支持浏览器打印导出 PDF；整改通知单、合规性检查清单以 HTML Tab 嵌入同一份报告，允许另存为附件"
4. **模板文件名统一**：`html-report-template.md` → `references/html-report-template.html`（真实文件名）

### C2 图纸角色：解耦"是不是图"与"审不审"
1. **is_drawing 标签独立**：index.json document 增 `is_drawing: bool` 与 `drawing_type: null | "design_basis" | "as_built" | "process_sketch"`（细分类型仅作默认推断辅助，不作硬判据）
2. **stage→default_role 映射**：施工阶段 is_drawing→默认 reference_files；竣工移交阶段 is_drawing→默认 audited_files；文件名含"示意/方案"→默认 reference_files。所有默认值必过 C-01 人工分类确认闸门（`file_classification_confirmed=false` 时 Phase 2 不启动）
3. **build 阶段终端提示**：stage∈{竣工,移交} 且检测到图纸，打印高亮"检测到竣工阶段图纸 X 份，已默认纳入 audited_files，请在 C-01 确认"；`--auto` 参数跳过交互
4. **C-01 分类面板提示**：图纸类文件前缀 🖼️ 图标，默认角色列明示"竣工默认 audited / 施工默认 reference"，一键切换

### C1 分类：三级分类器（关键词聚合 + LLM语义 + 人工闸门 + 简化自成长）
1. **单一真相源三聚合**：`references/classification-terms.json`（手动维护结构化专业→关键词→来源+权重）+ 91 条规则 `trigger_when.doc_type` + `FIELD_ALIAS_MAP`；build 时运行时聚合成内存词表，带来源标注可追溯
2. **新真相源 references/classification-terms.json**：结构 `{professional: [{term, source, weight: "core"|"weak"}]}`，首次初始化从规则 doc_type 抽取+ 从 references/*-audit.md "关键资料"段标题手动摘，不做自然语言聚合防噪音
3. **三级判定**：① 关键词快筛（单专业 core 强命中→直接用）；② 无命中 / 命中≥2专业 / 只有 weak 词命中 → LLM 看"文件名+前 5 行文本摘要"，RAG 喂入 classification-terms + specification-mapping.md，输出置信度；③ 写 index.json：`classification_source: "keyword"|"llm"|"human"` + `classification_confidence: float` + `human_confirmed: false`
4. **人工闸门 UI**：data-editor 文档树对 `human_confirmed=false` 或 `confidence<0.7` 条目高亮标黄"AI分类·待确认"，新增文档属性面板可改 professional/subcategory/doc_type，改完 `human_confirmed=true`
5. **简化版自成长（候选→确认两步）**：人工改分类且改法≠AI原分类 → 自动追加"文件名关键词模式→新专业 status=candidate" 到 classification-terms.json；下次 build 同模式文件 → C-01 面板高亮"候选分类，请确认"→确认后变 active。不做影子模式/LLM聚类等自动化管道
6. **scripts/llm_client.py 公共 client**：复用 feedback_analyzer 已有 `LLM_API_URL / KEY / MODEL` 环境变量，避免三处双写 API Key / 超时 / 错误处理

### C5 表头识别：三路融合（模板别名 + 列特征+数学链约束 + 人工沉淀）（LLM 路标 P2，v7.2 P1 不上）
1. **槽位 schema 不存死字符串**：从 FIELD_ALIAS_MAP 反向聚合成 `{slot, aliases:[], data_type, num_range_hint}`，别名集合为单一真相源
2. **三路融合（v7.2 P1）**：路1 FIELD_ALIAS_MAP 别名匹配；路2 列数据特征（桩号=全 Z+数字 / 日期=全日期串 / 数值范围=高程/长度）+ **数学链交叉约束**：哪两列差均值≈另一列均值→锁定 实长/桩顶/桩底三标准槽（仅桩基类文档有此关系链，土方/混凝土/排水/助航类文档路2 为独立推断——此边界在 spec 中诚实声明，验收不造假）；路4 人工闸门确认映射。路3 LLM 语义路标 P2
3. **融合策略**：路1+2 一致→直接写；不一致 / 低置信→上路4 人工改
4. **存储选项 A（零破坏 rule_engine）**：structured_rows 继续用标准 slot 键值写，独立存 `raw_headers: []` 与 `header_mapping: {original_header: {slot, source, confidence}}`。用户在 data-editor 表头映射 Tab 改映射 → 轻量重算 structured_rows（不重 OCR）
5. **表头自成长**：人工确认的映射→追加到 FIELD_ALIAS_MAP 对应槽位（data-editor 需勾选"同步到全局别名库"才写，防污染）

### C4 置信度：文档级存疑降级 + TOP N 建议重扫（field-level 置信度砍到 P2，不进 v7.2）
1. **field-level 置信度染色 / ROI 坐标重扫 / 原件糊 vs 扫描糊区分**：全部标 P2，v7.2 P1 不做——开发量占 C4 60% 且不改变用户核对操作（低置信和高置信字段都要去看原图），投入产出比低
2. **v7.2 P1 只做三件事**：① 糊件（`ocr_confidence<0.85` 或 `ocr_status="needs_review"`）触发的所有规则结论 severity 自动降级为 R-18 "存疑"级，批量写入 R-20 待核实清单 + 报告专段"以下结论基于低置信识别，需人工重点核实"；② 不硬卡流程——糊件照常审、照常出报告、照常给出存疑结论；③ project-dashboard.html 新增"建议重扫 TOP 10"卡片，按 `(1 - ocr_confidence) × 该文件关联 Fatal 规则条数估算值` 排序，纯文字提示不强制
3. **复用现有资产**：R-18 存疑分级、R-20 待核实清单、retry_log needs_review 原因、Vision API 兜底（F-07 已在 ocr_image.py 第三层，不重复造）

---

## C9 数据编辑器优化方案（data-editor 分屏+原文预览+PDF/Excel分离渲染）

> 注意：本方案编号为 C9，以区别于 §1.3.4 和 v7.2 变更日志中已使用的 C8（PDF 渲染引擎：PyMuPDF 替代 Poppler）。C9 是 data-editor 用户界面层的独立优化，不涉及 v7.2 数据底座基础能力。

### 9.1 问题描述

用户通过实际使用 data-editor.html 提出三个互相关联的问题：

| 问题 | 现象 | 复现步骤 | 严重程度 |
|:---|:---|:---|:---:|
| **Q1 确认按钮灰化** | 保存→确认→再改→保存后，确认按钮保持灰色不可点击，显示"已确认" | ① 打开文档核对数据 ② 点击「确认此文档数据无误」(human_verified=true) ③ 继续修改单元格 ④ 点击「保存修改」 ⑤ 确认按钮灰色不可用 | P0 — 阻断核对流程，用户无法完成二次确认 |
| **Q2 原文预览优化** | 原文预览 Tab 仅显示纯文本，无表格列对齐、不可编辑、翻页与原文页码不对应 | ① 点击「原文预览」Tab ② 看到的是 OCR 全文文本，无表格结构 ③ 无法直接修改错字 ④ 切换到「表格数据」Tab 再切回，页码不持久 | P1 — 降低核对效率，需要来回切换 Tab |
| **Q3 扫描件PDF与Excel分开预览** | 扫描件PDF和Excel.xlsx 在「原文预览」Tab 中均显示纯文本，未区分渲染方式 | ① 加载扫描件PDF ② 原文预览显示 OCR 文本，无原图对照 ③ 加载 Excel xlsx ④ 原文预览显示拼接文本，无原始表格样式 | P1 — 扫描件看不到原图，Excel 看不到原始表格结构 |

### 9.2 方案概述（P0-P5）

```
P0 修复确认按钮灰化 ─── 2 处改动，约 5 行
P1 分屏布局 ────────── 左侧原文面板 40% + 右侧数据面板 60%
P2 扫描件PDF渲染器 ─── 图片 + OCR 文本叠加 + 置信度着色
P3 Excel 渲染器 ─────── Sheet 标签 + 电子表格网格
P4 双向数据同步 ─────── 原文编辑 → 表格联动，表格修改 → 原文高亮
P5 页码/Sheet 联动导航 ─ 翻页同步 + 页码映射
```

#### P0｜确认按钮灰化修复（2 处改动，约 5 行）

**代码锚点**：`templates/data-editor.html` 第 3362 行 `updateConfirmGate()` 函数 + 第 2557 行 `saveTableChanges()` 函数。

**根因分析**：

```
确认流程：
  saveTableChanges() → 写 data_file JSON，清 state.modified = false
  confirmCurrentDoc() → 设 human_verified = true，写 index.json
  再修改 → state.modified = true，state.corrections.push(...)
  再保存 → saveTableChanges() 写 JSON，清 state.modified
  updateConfirmGate() 检查：doc.human_verified === true → 按钮 disabled ← 这里卡死
```

`updateConfirmGate()` 第 3390 行 `if (doc.human_verified === true)` 是只读检查，没有任何分支允许已确认文档被修改后重新启用确认按钮。`saveTableChanges()` 在保存后不重置 `human_verified`。

**改动内容**：

1. **saveTableChanges() 末尾追加**：在写 JSON 成功后，若 `state.corrections.length > 0`（即本次保存包含修正记录），且 `doc.human_verified === true`，则自动将 `human_verified` 重置为 `false`，并更新 `index.json` 中对应条目。这样用户修改保存后，确认按钮自动恢复可用。

2. **updateConfirmGate() 文字调整**：当 `human_verified === true` 时，检查 `state.corrections.length > 0` 或 `state.modified === true`，若有则显示"已修改·需重新确认"（按钮仍可点击），而非直接禁用。

**硬约束**：不破坏正常确认流程（第一次确认照常工作）；不引入自动保存循环（重置 `human_verified` 只在主动点保存时触发，不在单元格 blur 时触发）。

#### P1｜分屏布局（左侧原文面板 40% + 右侧数据面板 60%）

**代码锚点**：`templates/data-editor.html` 第 1427~1479 行 `<main class="content-panel">` 及内部 Tab 结构。

**当前布局**：
```
┌─文档树──┐┌─────────── 内容区（Tab 切换）────────────┐
│         ││  [表格数据] [原文预览] [图纸] [问题] [属性] │
│         ││  仅一个 Tab 可见，切换才能看到另一个       │
└─────────┘└──────────────────────────────────────────┘
```

**目标布局**：
```
┌─文档树──┐┌── 左侧原文面板（40%）──┐┌── 右侧数据面板（60%）──┐
│         ││  [原文渲染]             ││  [表格数据] [问题] [属性] │
│         ││  PDF/Excel/Text 按类型  ││  Tab 切换，保留当前 Tab  │
│         ││  分派渲染器             ││  状态独立                │
└─────────┘└─────────────────────────┘└─────────────────────────┘
```

**改动内容**：

1. **HTML 结构重构**：`<main class="content-panel">` 改为 flex 行容器，内部两个子容器：
   - `<div class="preview-panel" style="width:40%;">` — 左侧原文面板
   - `<div class="data-panel" style="width:60%;">` — 右侧数据面板

2. **Tab 栏拆分**：
   - 原文面板不显示 Tab 栏，只显示文档类型切换器（PDF/Excel/Text 自动选择渲染器）
   - 数据面板保留 Tab 栏：`[表格数据] [问题视图] [文档属性] [表头映射]`，去掉「原文预览」和「图纸」Tab
   - 「图纸」Tab 内容并入左侧原文面板，作为 PDF 渲染器的子模式（在原图/OCR文本叠加/纯文本之间切换）

3. **分屏拖拽**：在两个面板之间增加一个拖拽分隔条 `<div class="splitter">`，支持拖拽调整比例（40:60 ~ 20:80），默认 40:60。分隔条样式：炭灰色细条 4px，hover 时变亮蓝 2px，拖拽时 cursor: col-resize。

4. **响应式降级**：窗口宽度 < 900px 时，自动降级为上下排布（原文在上，数据在下），或切换为 Tab 式（保留一个关闭按钮，可隐藏原文面板）。

**数据流**：左侧原文面板的渲染依赖 `state.currentDoc` 和 `state.currentData`，与右侧数据面板共享同一数据源，不需要额外加载。

#### P2｜扫描件PDF渲染器（图片 + OCR 文本叠加 + 置信度着色）

**代码锚点**：`templates/data-editor.html` 第 2653 行 `renderImagesTab()` 函数（当前图纸Tab的图片渲染逻辑可作为基础设施复用）。

**改动内容**：

1. **PDF 页面渲染器 `renderPdfPage(pageNum)`**：
   - 优先使用 `page_map[pageNum].image_ref` 加载原图（复用现有 `readImageObjectUrl` 和 `getDataDirHandle`）
   - 图片加载后，在 canvas 上叠加 OCR 文本层：使用 `page_map[pageNum].text` 或 `structured_rows` 中该页的行数据，按行坐标叠加 `<span>` 元素
   - 置信度着色：`confidence < 0.6` → 红色背景高亮，`0.6 ≤ confidence < 0.85` → 黄色背景，`≥ 0.85` → 不处理
   - 右上角提供切换按钮：`[原图] [OCR叠加] [纯文本]` 三种模式
   - 原图模式下，点击文本区域弹出编辑气泡（inline editor），修改后即时写回 `state.currentData`

2. **OCR 文本定位**（坐标来源）：
   - 优先使用 `page_map[pageNum].ocr_boxes`（若存在，PaddleOCR 的输出包含坐标）
   - 若不存在，则回退为按行号估算行高，在 canvas 上等距排列文本行
   - 坐标格式：`{x, y, w, h}` 相对于图片尺寸的百分比坐标

3. **翻页控件**：复用现有 `renderTextTab()` 的翻页 UI（上一页/下一页 + 页码指示器），但渲染的是图片+文本叠加，而非纯文本。

4. **性能优化**：使用 `requestAnimationFrame` 控制渲染频率，翻页时先显示 loading骨架，异步加载图片；仅渲染当前页和相邻页（prefetch 前/后一页）。

#### P3｜Excel 渲染器（Sheet 标签 + 电子表格网格）

**代码锚点**：`templates/data-editor.html` 现有 `renderStructuredTable()`（第 2410 行）可作为基础。

**改动内容**：

1. **Sheet 检测**：新增 `detectExcelSheets(data)` 函数，从 `structured_rows` 中检测 `sheet_name` 字段（若存在）来区分不同 Sheet。若不存在，则整个文档视为单 Sheet。

2. **Sheet 标签栏**：在左侧原文面板顶部渲染 `<div class="sheet-tabs">`，每个 Sheet 一个标签，点击切换；多 Sheet 时标签栏可横向滚动。

3. **电子表格网格渲染 `renderExcelGrid(sheetName)`**：
   - 复用 `renderStructuredTable()` 的表格渲染逻辑，但增加列宽自适应（根据内容长度自动调整最小列宽）
   - 增加行号列（固定列），左侧灰色背景，不可编辑
   - 空单元格显示灰色占位符 `—`
   - 合并单元格：若 `structured_rows` 中有 `rowspan`/`colspan` 属性，按合并方式渲染（当前数据底座不产生合并信息，此功能为预留扩展）

4. **编辑与保存**：单元格可编辑（contenteditable），编辑后高亮标记，与 `saveTableChanges()` 共享同一修正记录管道。

#### P4｜双向数据同步

**代码锚点**：`templates/data-editor.html` 第 2557 行 `saveTableChanges()` + 第 2506 行 `bindCellEditEvents()`。

**当前机制**（单向：表格编辑 → 保存 → 刷新）：
```
表格编辑 → state.corrections.push → saveTableChanges() → 写 JSON
```

**目标机制**（双向：原文编辑 ↔ 表格编辑，自动同步渲染）：

1. **修改事件统一**：无论是左侧原文面板还是右侧表格面板的编辑操作，统一写入 `state.currentData` 的同一份数据，共用 `state.corrections` 修正记录管道。

2. **变更通知**：新增 `notifyDataChange(source, rowIndex, field, newValue)` 函数，在编辑完一个单元格后调用：
   - 更新 `state.currentData.rows` / `state.currentData.structured_rows` 中的对应值
   - 若右侧数据面板当前显示的是表格 Tab，则调用 `renderStructuredTable()` 刷新对应行（不重新渲染整个表格，仅更新该行 DOM）
   - 若左侧原文面板当前显示的是 OCR 叠加模式，刷新对应文本块的置信度着色

3. **冲突避免**：两个面板同时编辑同一单元格时，以最后编辑为准，不做合并（data-editor 是单人编辑场景，不存在并发冲突）。

4. **保存合并**：`saveTableChanges()` 保持不变，一次性将所有 `state.corrections` 写入 JSON 文件。

#### P5｜页码/Sheet 联动导航

**代码锚点**：`templates/data-editor.html` 第 2638 行 `changePage()` 函数 + 现有 `state.currentPage`/`state.totalPages` 状态。

**改动内容**：

1. **统一页码状态**：原文面板的页码 `state.previewPage` 与数据面板的 `state.tablePage` 默认联动（`state.currentPage` 作为共享页码）。数据面板表格 Tab 的 `renderStructuredTable()` 新增 `filterByPage` 参数，只渲染 `page === state.currentPage` 的行。

2. **页码映射关系**：
   ```
   page_map[pageNum].page    ← PDF 物理页码（从 1 开始）
   structured_rows[].page     ← OCR 识别的页码（可能不连续或有偏移）
   ```
   - 翻页时，先根据 `structured_rows` 中所有不重复的 `page` 值建立索引 `{pageNum: [rowIndex, ...]}`
   - 翻到第 N 页 → 左侧加载 `page_map` 第 N 页 → 右侧只显示 `page === N` 的行
   - 若 `structured_rows` 中没有 `page` 字段（旧版格式），则回退为按行数均分估算

3. **Sheet 联动**：Excel 文档翻页时，Sheet 标签自动切换；切换 Sheet 时，页码重置为 1。

4. **导航栏增强**：在原文面板底部增加页码输入框（直接输入页码跳转）+ 快速跳转按钮（首页/末页）。

### 9.3 自我审核结果

#### 9.3.1 完整性审核

| 审核项 | 结论 | 说明 |
|:---|:---:|:---|
| Q1 确认按钮灰化 | ✅ 覆盖 | P0 修复方案直接定位到 2 处代码改动，根因分析完整 |
| Q2 原文预览优化 | ✅ 覆盖 | P1 分屏布局 + P2 PDF渲染器 + P4 双向同步共同解决 |
| Q3 扫描件/Excel 分开预览 | ✅ 覆盖 | P2 扫描件PDF渲染器 + P3 Excel渲染器 |

#### 9.3.2 技术可行性审核

| 方案组件 | 可行性 | 依据 |
|:---|:---:|:---|
| **P0 确认按钮修复** | ✅ 可行 | 改动量极小（2 处，~5 行），不改变现有架构；`saveTableChanges()` 已有 `state.modified` 和 `state.corrections` 跟踪，追加 `human_verified` 重置逻辑即可 |
| **P1 分屏布局** | ⚠️ 可行但需注意 | 当前布局是 `<aside.tree-panel> + <main.content-panel>` 的 Flex 布局，将 `<main>` 改为 `<main.preview-panel> + <main.data-panel>` 的 Flex 布局，不改变外部容器结构。需注意：分屏后右侧面板的 Tab 切换逻辑需要重新关联 DOM 元素（`tabTable`/`tabProblems`/`tabProps`/`tabHeaderMap` 的显示/隐藏） |
| **P2 扫描件PDF渲染器** | ✅ 可行 | 现有 `renderImagesTab()` 已实现 PDF 图片加载（`readImageObjectUrl` + `page_map.image_ref`），复用该基础设施即可。新增 OCR 文本叠加层需要 canvas 上的坐标定位，若 `page_map` 无坐标数据则回退等距排列 |
| **P3 Excel 渲染器** | ⚠️ 可行但需注意 | 现有 `renderStructuredTable()` 可渲染表格，但 Sheet 标签栏和列宽自适应需要新实现。关键依赖：`structured_rows` 中需要有 `sheet_name` 字段来区分 Sheet（当前数据底座不生成此字段，需在 build_foundation.py 中追加） |
| **P4 双向数据同步** | ✅ 可行 | 两个面板共享同一 `state.currentData` 和 `state.corrections`，不存在跨实例同步问题。变更通知只需触发局部 DOM 更新而非全量重渲染 |
| **P5 页码/Sheet联动** | ✅ 可行 | 现有 `state.currentPage` 和 `changePage()` 函数可以直接扩展，`structured_rows[].page` 字段已存在 |

#### 9.3.3 架构一致性审核

| 现有架构特征 | P1 分屏方案 | 兼容性 |
|:---|:---|:---:|
| **Tab 式架构**（6 个 Tab：表格/原文/图纸/问题/属性/表头映射） | 原文和图纸 Tab 合并到左侧面板，右侧保留 4 个 Tab | ⚠️ 需要迁移：原文 Tab 的渲染函数 `renderTextTab()` 和图纸 Tab 的 `renderImagesTab()` 要合并为 `renderPreviewPanel()`，但内部逻辑不变 |
| **state 对象**（`state.currentDoc`, `state.currentData`, `state.modified` 等） | state 新增 `state.previewPage` 和 `state.previewMode`（"image"/"overlay"/"text"），其余不变 | ✅ 兼容，新增字段不影响现有逻辑 |
| **事件绑定模式**（`document.querySelectorAll` + `addEventListener`，全局函数式） | 分屏后事件绑定仍用同一模式，原文面板内的事件在 `renderPreviewPanel()` 中绑定 | ✅ 兼容，不改变事件绑定模式 |
| **数据获取层**（`getRows()`, `getPageMap()`, `getFullText()`） | 原文面板和右侧面板共用同一套数据获取层 | ✅ 兼容，无需改动 |
| **保存/确认流程**（`saveTableChanges()`, `confirmCurrentDoc()`, `updateConfirmGate()`） | 保存和确认流程不变，原文面板编辑触发同一套管道 | ✅ 兼容，P0 修复仅追加数行 |

#### 9.3.4 遗漏项清单（审核发现，补充入方案）

| 遗漏项 | 说明 | 补充状态 |
|:---|:---|:---|
| **① 原文预览数据来源未明确** | 方案描述中"原文预览"的数据来源不明确。审核结论：**page_map.text 为主**（按页分段的 OCR 原始文本），**structured_rows 为辅**（在表格列对齐模式下展示结构化数据）。当 page_map 存在时优先使用 page_map.text（含分页信息），page_map 缺失时从 structured_rows 按 page 字段重建 | ✅ 已在本节 §9.2 P2 中明确 |
| **② 页码映射机制未明确** | 翻页时"原文页码"和"表格数据页码"的对应关系需要明确。审核结论：**page_map.page 是物理页码，structured_rows[].page 是 OCR 识别页码**，两者可能不一致（OCR 可能漏页或合并页）。映射策略：以 page_map 为锚点，structured_rows 中 `page` 值相同的行归入该页。若 structured_rows 无 page 字段，则按行数 ÷ page_map.length 均分估算 | ✅ 已在本节 §9.2 P5 中明确 |
| **③ 排版细节未指定** | 字体大小、行高、列宽等排版细节。审核结论：原文面板采用等宽字体（`--font-mono`），行高 1.6，字号 13px 用于文本、12px 用于表格叠加层。列宽在叠加模式下按 OCR 坐标比例还原，在纯文本模式下默认 100% 宽度。可分一条验收标准 | ✅ 新增 V-90 |
| **④ 滚动同步 vs 手动翻页** | 原文面板的双栏模式（长文档）是否支持滚动同步。审核结论：**不做滚动同步**，统一使用翻页控件（上一页/下一页/页码输入框）。理由：① 原文面板是一页一页渲染的，不是连续滚动布局；② 页码同步比滚动同步更精确（页码是离散的，滚动是连续的）；③ 数据面板的表格也是按页过滤的，不是连续滚动 | ✅ 已在本节 §9.2 P5 中明确 |
| **⑤ 问题视图和图纸 Tab 在分屏模式下的处理** | 分屏后「图纸」Tab 内容并入左侧原文面板的 PDF 渲染器子模式。「问题视图」「文档属性」「表头映射」保留在右侧面板 Tab 栏，因为它们是数据操作面板，需要与表格数据同侧。问题视图与表格数据共享同一数据面板，交互上用户需要先看问题再定位到表格行，同侧更合理 | ✅ 已在本节 §9.2 P1 中明确 |
| **⑥ 分屏模式的小屏幕适配** | 窗口宽度 < 900px 时降级方案。审核结论：降级为上下排布（原文在上，数据在下），或可选隐藏原文面板（保留一个浮动按钮「显示原文」）。不做响应式 Tab 切换（复杂度高，收益低） | ✅ 已在本节 §9.2 P1 中补充 |

#### 9.3.5 风险识别

| 风险 | 等级 | 说明 | 缓解措施 |
|:---|:---:|:---|:---|
| **R1 分屏布局重构量低估** | 中 | 虽然理论上是 Flex 嵌套，但现有 Tab 切换逻辑（`switchTab()` + 6 个 `tab-content` 的显示/隐藏）与 DOM 结构强耦合，拆分为两个面板后需要重新组织 6 个 Tab 的归属 | 分步实施：P0 先做（不改布局），P1 只改布局不改渲染逻辑，P2-P5 逐步迁移渲染器 |
| **R2 PDF 渲染性能** | 中 | 扫描件 PDF 每页一张图片，50 页文档加载 50 张图片（每张 200-500KB），内存占用可能达到 25MB+ | ① 只加载当前页 + 预加载前后各 1 页；② 翻页时释放非可见页的 ObjectURL；③ 图片加载期间显示 skeleton 骨架 |
| **R3 OCR 坐标数据缺失** | 高 | 当前数据底座不保证 `page_map` 中有 `ocr_boxes`（坐标信息）。PaddleOCR 输出有坐标，但 Vision API 的返回可能没有。无坐标时 OCR 叠加层只能等距排列，失去"在原图对应位置显示文本"的意义 | ① 检测到坐标缺失时自动降级为纯文本模式或原图模式；② 在原文面板右上方显示"无坐标数据·已降级"提示 |
| **R4 Excel 多 Sheet 依赖数据结构** | 高 | 当前 `build_foundation.py` 的 `parse_generic_table()` 和 `parse_pile_rows()` 不生成 `sheet_name` 字段。Excel xlsx 的 openpyxl 提取虽然能区分 Sheet，但数据结构中未保留 | 在 build_foundation.py 的 Excel 处理分支中追加 `sheet_name` 字段，回退兼容旧数据（无 sheet_name 时视为单 Sheet） |
| **R5 双向同步的循环更新** | 低 | 原文面板编辑 → 更新数据 → 触发表格重渲染 → 若表格重渲染又触发事件绑定，可能产生循环 | 使用 `state._updating` 标志位防止重入：更新前设 `state._updating = true`，渲染完成后设回 `false`；编辑事件中当 `state._updating === true` 时跳过 |
| **R6 分屏下「问题视图」交互** | 低 | 分屏后问题视图在右侧面板，用户点击问题定位到表格行时，表格渲染范围是按页过滤的 row。如果问题所在行在当前页之外，需要自动翻页 | 点击问题定位时，检查 `row.page` 是否等于 `state.currentPage`，不等则自动翻页到该页再定位 |

### 9.4 实施计划表

| 优先级 | 组件 | 估算工时 | 依赖 | 验收标准 |
|:---:|:---|:---:|:---|:---|
| **P0** | 确认按钮灰化修复 | 0.5h | 无 | V-90：保存→确认→再改→保存后，确认按钮可用，显示"已修改·需重新确认"；点击确认后恢复"已确认" |
| **P1** | 分屏布局（HTML+CSS 重构） | 4h | 无 | V-91：左侧原文面板 40% + 右侧数据面板 60%，中间分隔条可拖拽调整比例；窗口 < 900px 自动降级为上下排布 |
| **P1a** | Tab 栏迁移（原文/图纸→左侧，其余→右侧） | 2h | P1 | V-92：右侧面板 Tab 栏为「表格数据」「问题视图」「文档属性」「表头映射」四项；原文预览和图纸不再作为独立 Tab |
| **P2** | 扫描件PDF渲染器（图片+OCR叠加+置信度着色） | 6h | P1 | V-93：扫描件PDF原文面板显示原图，OCR 文本叠加在原图上，低置信度字段红色/黄色高亮；支持 [原图/OCR叠加/纯文本] 三种模式切换 |
| **P3** | Excel 渲染器（Sheet标签+电子表格网格） | 4h | P1 + build_foundation.py 追加 sheet_name | V-94：Excel 文档左侧面板显示 Sheet 标签栏，切换 Sheet 显示对应表格网格；列宽自适应内容长度 |
| **P4** | 双向数据同步 | 3h | P1 + P2 + P3 | V-95：在原文叠加模式下编辑文本值 → 右侧表格对应单元格自动更新，modified 标记显示；在表格编辑 → 原文叠加层对应文本块高亮 |
| **P5** | 页码/Sheet 联动导航 | 2h | P1 + P4 | V-96：翻页时左侧原文面板和右侧表格面板同步过滤；页码映射正确处理 page_map 与 structured_rows 的页码差异；Excel 切换 Sheet 自动重置页码 |
| **集成测试** | 全流程回归测试 | 2h | P0-P5 | V-97：三个用户问题全部解决；现有 v7.1/v7.2 功能（确认闸门、问题视图、文档属性、表头映射）不受影响 |

**总计估算工时**：23.5h（约 3 人天）

**建议实施顺序**：P0 → P1 → P1a → P2 → P3 → P4 → P5 → 集成测试。P0 可独立先行修复，P1+P1a 是后续所有改动的基础，P2/P3 可并行开发（共享 P1 的布局框架但渲染器互不依赖），P4/P5 在 P2/P3 完成后增量添加。

### 9.5 新增验收标准

| 编号 | 验收项 | 类型 | 对应 P |
|:---:|:---|:---:|:---:|
| V-90 | 确认按钮灰化修复：保存→确认→再改→保存→确认按钮可用 | 功能 | P0 |
| V-91 | 分屏布局：默认 40:60，分隔条拖拽，<900px 降级 | UI | P1 |
| V-92 | Tab 迁移：右侧 4 Tab，原文/图纸不再独立 Tab | UI | P1a |
| V-93 | 扫描件PDF 三种渲染模式均正常，置信度着色正确 | 功能 | P2 |
| V-94 | Excel 多 Sheet 渲染，列宽自适应 | 功能 | P3 |
| V-95 | 双向同步：原文编辑→表格更新，表格编辑→原文高亮 | 功能 | P4 |
| V-96 | 页码联动翻页，Sheet 切换重置页码 | 功能 | P5 |
| V-97 | 全流程回归：v7.1/v7.2 现有功能不受影响 | 回归 | 集成 |
| V-98 | 原文面板字体等宽、行高 1.6、字号 13px 文本 / 12px 叠加层 | 排版 | P2 |
| V-99 | 无坐标数据时自动降级为纯文本模式，提示"无坐标数据·已降级" | 降级 | P2 |
