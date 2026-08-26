# 民航建设施工资料合规审核大师 (civil-aviation-doc-audit)

> 民航工程施工资料合规性审核 Skill v10.5
> 适用：MH/T 5078.1~5078.6-2024 系列 + CCAR-165-R1 + MH 5031-2025 等民航规范
> 五大专业全覆盖：场道 / 空管 / 助航 / 弱电 / 供油

> v10.5 核心特性：**无规则覆盖运行时闸门——声明式触发的静默盲区显形**。规则引擎只对 `trigger_when.doc_type` 声明过的类型干活，从未声明的类型（如施工日志）会静默跳过、无人知晓。v10.5 新增 `build_unguarded_doc_types`：审核运行时自动识别本批受审文档中无任何 active 规则覆盖的 doc_type 写入 `summary.unguarded_doc_types`（SINGLE_DOC/CROSS_DOC/CROSS_UNIT 三类 scope 综合判定任一命中即视为有覆盖；仅统计 `doc_role='audited'` 受审文档，reference 审核参照不进提醒防噪音）；报告新增「八、无规则覆盖提醒」节（非空才渲染，警示框+明细表）；SKILL.md 编码 AI 强制提醒协议（出报告前必检查该字段，非空须向用户显式说明）。修复 IR-010/IR-011/LG-905 三条零交集规则（触发词「施工记录」与生产「场道施工记录」失配导致静默失效），补触发词后扫描零交集 3→0。新增回归套件 test_unguarded_doc_types.py（8 条）注册进 run_all_tests.py，全量 18/18 全绿。
> v10.4 核心特性：**规则→审核→报告全链路贯通 + 报告三层结构重构**。修复 LG-110 触发词与生产 doc_type 失配导致的规则静默失效；审核期基于 corrected 数据重算 S-04（消除陈旧结果复报）；规则执行统计（matched_docs/hits）进报告，0 匹配规则标 ⚠ 显形；报告生成拆分 `report_builder.py`（build_model/render_html 建模渲染分离），三层结构（结论层/问题层/行动层）+ 问题清单新增「整改建议」列；页脚版本号从 SKILL.md frontmatter 单一真相源动态读取；verify_report 新增合格证台账对账闸门；新增规则覆盖扫描工具 `scan_rule_coverage.py`；验证脚本版本识别去硬编码行号。新增回归套件 test_rule_to_report_chain.py（10 条）+ test_report_builder.py（6 条）注册进 run_all_tests.py。
> v10.3 核心特性：**材料/合格证数据链沉淀（验收 S-01~S-04 专项）**。材料类文档（合格证/质量证明书/进场检验）信号路由强制排除桩基解析，杜绝"材料文档含碎石桩字样被桩内容感知劫持"；OCR 仅含空框结果判 `needs_review` 而非 `completed`（E1）；材料类 `schema_status="material"` 跳过桩基领域检查（E3）；新增 `extract_certificates.py` 从检验记录/合格证行提取结构化记录并落库 `ledgers.certificates`（A2/A4）；新增 LG-110（S-04 追溯链检查）+ 底座构建期 `certificates_linkage` 落盘（A5）；规则注册表与校验器对齐（仅收 L1/L2/L3 子目录）。新增回归套件 test_material_certificate_chain.py（13 条），run_all_tests 15/15 全绿。
> v10.0 核心特性：**资料员工作台（Web Workbench）——九页合一，一次加载、模块共享**。合并原来 9 个零散的审核 HTML 入口为单一工作台外壳，hash 路由 + 动态 import 按需加载；一次性加载 index.json，_index 内存共享避免跨页重复读取；IndexedDB 存 FileSystemDirectoryHandle 实现"一键恢复上次项目"；规则管理内嵌进工作台「规则与反馈」模块，替代旧 rule-manager 单独入口；一键启动脚本同时拉起规则 API + 前端服务 + 浏览器。
> v9.7.1 核心特性：**视觉复核任务行级/表级分流（独立复核 R-1/R-2 高危处置）**。带桩号的行级数值存疑项（实长/电流/充盈系数等各行本不相同）生成 `scope=row` 任务、merge 只写该桩号所在行，不再表级化整表覆写污染同行正确值；施工部位/施工日期等整表同值字段走 `scope=table`；「整行」核对项（表头不可靠）不进视觉复核、留给 Chat-Verify；任务 field_label 统一中文显示。
> v9.7 核心特性：**AI 视觉复核链贯通（H-8 隐患销号）+ 视觉复核协议平台无关化**。扫描转化电子文档（WPS 扫描件转 docx）建底座时自动产出视觉复核任务（verify_output/：任务清单+裁图），宿主 AI 读图回写高/中置信度修正值，OCR 乱码项（如 `2026、4.22`、`砰石松三飞`）重新有 AI 自证通道；任务清单（JSON）+ 裁图（PNG）+ 结果（JSON）三文件协议不绑定任何平台，TRAE / WorkBuddy / CodeBuddy 等任何具备读图能力的智能体均可执行，无视觉能力平台自动降级 Chat-Verify 人工核对；merge 落库按 task_id 回查定位、中文字段自动映射英文行键、双份 rows 同步写；vision_providers 新增腾讯混元。
> v9.5 核心特性：**审核流水线步骤 1~7 线性编号 + 前置信息表迁移共享基础设施 + 推断值生成规则 + 闸门用户动作说明 + 规则管理步骤化工作流**。审核流水线统一为步骤 1~7 线性编号，每次 AI 回复顶部展示进度条，用户一眼可知当前走到哪一步；前置信息确认（6 项）表移至共享基础设施，审核流水线与规则管理场景共用；新增推断值生成规则，明确定义数值型/文本型/签名类的推断逻辑、置信度标定和审核使用规则；强制闸门表新增「用户动作」和「AI 恢复条件」两列，人工确认节点清晰可见；规则管理场景改为步骤化工作流（第一步规则浏览→第二步规则操作→第三步反馈闭环🚧→第四步反思触发🚧），步进步度条直观展示。
> v9.4 核心特性：**表格式样导入导出 + 苹果浅色界面优化 + SKILL.md 内部路由重构**。data-editor 新增「表格式样」面板，拆分**前缀区**（表格上方固定内容，用于定位表体，支持行增删改）与**数字区**（每列定义格式样式，支持多格式用 `/` 或 `，` 分隔、列名可编辑、列增删改、备注）；新增 `scripts/import_template.py` 从电子版（Excel/Word）表格一键导入表格式样，自动识别表头行、生成 JSON 模板；data-editor 支持「导入 JSON」加载模板、「保存样式定义」写回。界面由深墨蓝改为**苹果浅色风格**（白底、浅灰描边、浅蓝点缀），去除大片蓝色背景。
> v9.1 核心特性：**RapidTable(SLANetPlus) 表格结构识别 3.14 原生**，取代旧 TableStructureRec 双环境 subprocess；**方式二对话式核对四条纪律**（默认批量 / 条件补扫 / 落盘强制 / 推断标记+禁子代理）。v9.0 核心特性：本地 OCR 主力从原生 paddleocr 替换为 **rapidocr（RapidOCR）**，跨平台轻量稳定、无需 PaddlePaddle；新增**手写体前置路由**（手写资料直接走 VLM，印刷资料走本地 OCR）；VLM 手写体专用 Prompt 优化；`FORCE_USE_PADDLE` / `DISABLE_HANDWRITING_ROUTE` 配置开关；关键节点日志（路由判定/引擎选择/识别结果）。v8.8 PaddleOCR 3.x + PP-OCRv6 Tiny + ONNX Runtime；v8.7 OCR 全流程加固（表头检测优化+跨页表头继承+内容感知分类+分词修复）；模板统一存放数据底座目录+中文命名；data-editor 自动加载数据底座；launcher 三步指引 UI（核对数据→查看报告→其他工具）；rule-manager.bat 自动定位 skill 目录
---

## 目录结构

```
civil-aviation-doc-audit/
├── SKILL.md                          # 主 Skill 文件（必读，v10.5，按场景路由组织，步骤 1~7 线性编号）
├── README.md                         # 本文件（v10.5）
├── PROJECT_SPEC.md                   # 项目规格说明（v10.5）
├── requirements.txt                  # Python 依赖
├── install.ps1                       # 一键安装脚本（Python 依赖 + Vision API 配置 + RapidOCR 强烈推荐）
├── rule-manager.bat                  # 【v8.7】规则管理面板启动器（自动定位 skill 目录）
├── .gitignore
│
├── 同步内部路由到安装版.bat     # 【唯一同步入口】将项目版文件同步到安装版
│
├── references/                       # 18 个参考文件
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
│   ├── html-report-template.html     # HTML 报告标准模板
│   ├── native-mode-checklist.md       # 【v8.1】原生模式审核检查清单（34 项）
│   └── native-mode-stage1-checklist.md # 【v8.4】原生模式阶段 1 机械化步骤清单（8 步骤）
│
├── scripts/                          # 运行脚本（【核心】/【工具】/【测试】分类）
│   ├── run_audit.py                  # 【核心】Skill 入口（含 build/review/report/audit 子命令）
│   ├── build_foundation.py           # 【核心】数据底座建立脚本（v8.7，表头检测优化+跨页表头继承+内容感知分类+模板复制）
│   ├── review_audit.py               # 【核心】正式审核流水线脚本（v6.0，阶段 3，多 Agent 并行）
│   ├── audit_config.py               # 【核心】分部分项配置（v6.0，5 专业 / 48 分部 / 115 分项）
│   ├── signature_check.py             # 【核心】签字一致性检测（v7.0，pHash + SSIM 双指标）
│   ├── extract_pdf.py                # 【核心】PDF 文字提取（PyMuPDF）
│   ├── ocr_image.py                  # 【核心】扫描件 OCR（v9.0，RapidOCR 本地主力 + 手写体前置 VLM 路由 + Vision API / Tesseract 降级 + AGENT Vision 复核）
│   ├── postprocess.py                # 【核心】文本后处理（全角转半角、PUA 替换）
│   ├── data_quality_check.py         # 【核心】数据质量检测（铁律 10 配套）
│   ├── ocr_confusion_check.py        # 【核心】OCR 混淆检测（Z→2、4→0 等）
│   ├── verify_fields.py              # 【核心】存疑字段自动复核（裁剪+AI 视觉验证）
│   ├── vision_providers.py           # 【核心】Vision API 统一配置层（7 家 Provider）
│   ├── rule_engine.py                # 【核心】规则引擎核心（v10.5，加载/匹配/求值/检查/报告 + 执行统计 matched_docs/hits + unguarded_doc_types 侦测）
│   ├── report_builder.py             # 【核心】审核报告生成器（v10.5，build_model/render_html 建模渲染分离 + 三层报告结构 + 无规则覆盖提醒节）
│   ├── extract_certificates.py       # 【核心】合格证提取与 S-04 追溯链（v10.3，审核期 collect_certificate_findings 基于修正数据重算）
│   ├── scan_rule_coverage.py         # 【工具】规则覆盖扫描（v10.5，复用 build_unguarded_doc_types 判定口径，仅统计受审文档，揪静默失效）
│   ├── rule_admin.py                 # 【工具】规则管理 API 服务（v6.0，20+ 端点）
│   ├── rule_lifecycle.py             # 【工具】规则生命周期管理（v6.0，draft→active）
│   ├── rule_monitor.py               # 【工具】规则效力自监控（v6.0，命中率/误报率/自动降级）
│   ├── rule_reflector.py             # 【工具】定时反思调度器（v6.0，LLM 生成优化建议）
│   ├── rule_registry_builder.py      # 【工具】规则注册表生成工具（v6.0）
│   ├── rule_schema_validator.py      # 【工具】规则 JSON Schema 校验工具（v6.0）
│   ├── feedback_store.py             # 【工具】反馈存储管理（v6.0）
│   ├── feedback_analyzer.py          # 【工具】LLM 反馈分析管道（v6.0，聚类/模式提取/候选规则）
│   ├── llm_client.py                 # 【工具】LLM 公共客户端（v7.2，分类语义辅助，复用 LLM_API_URL/KEY/MODEL）
│   ├── import_corrections.py         # 【核心】自成长导入（v7.2，人工修正记录 → 分类/表头候选词条回流）
│   ├── import_template.py            # 【核心】表格式样导入（v9.4，Excel/Word 电子表 → 前缀区+数字区 JSON 模板）
│   ├── audit_memory.py               # 【核心】审核记忆流（v6.0，JSONL 事件日志）
│   ├── test_rule_engine.py           # 【测试】规则引擎单元测试（v6.0，6/6 通过）
│   ├── test_cross_unit_perf.py       # 【测试】跨单位性能测试（v6.0，4/4 通过）
│   ├── test_ocr_routing.py           # 【测试】OCR 手写体/印刷体路由测试（v9.0，21/21 通过）
│   ├── test_rule_subsystem_integration.py  # 【测试】子系统全链路集成测试（v6.0，7/7 通过）
│   ├── test_unguarded_doc_types.py   # 【测试】无规则覆盖侦测回归（v10.5，8/8 通过：字段存在/点名/不误报/CROSS兜底/空列表/渲染/取数/reference过滤）
│   └── verify_skill_structure.py     # 【测试】SKILL.md 结构验证（v9.4，路由重构校验）
│
├── templates/                        # HTML 模板层（v8.7 模板清单统一管理）
│   ├── template-manifest.json        # 【v8.7】模板清单文件 v1.3（统一管理模板复制规则）
│   ├── audit-scope-template.html     # 审核范围清单模板（v1.9）
│   ├── data-editor.html              # 【v8.7】Web 数据编辑器（自动加载+中文按钮+精密仪表盘；v9.4 新增表格式样面板+苹果浅色风格）
│   ├── launcher.html                 # 【v8.7】三步指引入口页（核对数据→查看报告→其他工具）
│   ├── project-dashboard.html        # 【v6.0】项目总览仪表盘
│   ├── rule-editor.html              # 【v6.0】离线规则编辑器（小白友好）
│   ├── rule-manager.html             # 【v6.0】规则管理面板（4 标签页，可视化编辑器）
│   ├── feedback-collector.html       # 【v6.0】反馈收集组件（漏审/误报）
│   ├── alignment-view.html           # 【v6.0】跨单位数据对齐视图
│   ├── tokens.css                    # 【v8.7】统一设计令牌（颜色/字体/间距）
│   ├── pdf.min.js                    # 【v6.0】PDF.js 离线预下载
│   └── pdf.worker.min.js             # 【v6.0】PDF.js worker
│
├── rules/                            # 【v6.0】规则文件库（94 条）
│   ├── L1-iron/                      # L1 铁律（16 条）
│   ├── L2-logic/                     # L2 逻辑一致性（73 条，72 条 active + 1 条 deprecated，含 IR-012/013/014、CU-001~018、LG-006/007/110）
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
└── audit_memory/                     # 【v6.0】审核记忆流日志
```

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **OCR 全流程加固**（v8.7） | 表头检测（超长token过滤+列名关键词）+ 表头续行合并 + 跨页表头继承 + 内容感知分类（桩基关键词自动路由）+ 分词修复（_tokenize_table_line 替代 re.split） |
| **模板目录重构**（v8.7） | 所有 Web 模板统一复制到 `数据底座/` 目录，中文命名（数据核对编辑器.html/项目总览.html/打开审核工具.html），精简非必要模板 |
| **data-editor 自动加载**（v8.7） | 打开即自动加载同级 index.json，localStorage 记忆上次项目，按钮文案全中文化 |
| **launcher 三步指引 UI**（v8.7） | 核对数据 → 查看报告 → 其他工具，流程化导航，动态显示项目状态（审核时间/资料数/问题统计） |
| **rule-manager.bat 自动定位**（v8.7） | 自动查找 skill 安装目录（当前→上级→全局），中文界面，复制到数据底座方便用户访问 |
| **OCR 引擎四选一前置**（v8.7） | auto（自动最优）/ vision（云端API）/ rapidocr（本地批量）/ agent（AGENT Vision复核），作为 6 项前置信息第 4 项收集 |
| **双模式运行架构**（v8.1） | 引擎模式（Python 可用，四阶段流水线）+ 原生模式（无 Python，三阶段简化流水线），适配 WorkBuddy/Codex/Hermes |
| **原生模式检查清单**（v8.1） | 34 项检查（DQ×4 + IR×15 + LG×10 + BG×5），低智商模型按清单机械执行 |
| **OCR 策略重定位**（v8.0） | PaddleOCR 强烈推荐 + AGENT Vision 复核定位 + 安装引导 token 消耗警告 |
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
| OCR 识别扫描件 | 【v9.0】印刷体→RapidOCR 本地主力（零 token）→ Vision API → Tesseract；手写体→前置路由 VLM（识别率最高）→ AGENT 内置 Vision 复核（页数不限） |
| 规范逐条对账 | 对着 MH/T 5078 系列逐条比对，每条引规范编号和条款号 |
| 数据质量检测 | 自动识别造假、涂改、异常模式（DQ-REPEAT/JUMP/ALTER/SELF） |
| **数据验证闸门 + 闭环**（v8.10） | `validate_rows` 六类校验（类型/格式/范围/完整性/一致性/跨字段数学链）+ 表头消歧定列落地于数据底座写入前，脏行标 `needs_review` 不直接进库，行级 `issues` 写入 `structured_rows`；data-editor 层3 闭环（行标红⚠+内联原因 → 问题视图 → 精准跳转橙闪 → 确认门禁阻止未处理 issues 放行） |
| 逻辑一致性检查 | 10 个子项 71 条规则，含监理-施工方跨单位日期对照（9.10，18 条 CU 规则） |
| 运算规范审核 | 只做规范性检查，不做数值复算 |
| 自动生成审核报告 | 三级输出：🔴Fatal / 🟡Sanity Check / 🔵Best Practice，含 SVG 图表 |
| 知识分区红线 | 三条红线防幻觉，推理边界决策树，输出前自检清单 |

---

## 功能特性

### v9.7.1 新增（视觉复核任务行级/表级分流）

1. **行级数值存疑项不再表级化（独立复核 R-1 高危处置）**：带桩号的行级 pending 项（实长/电流/充盈系数等各行本不相同）生成 `scope=row` 任务，按表+桩号定位全局行号，merge 只写该行——修复"仅 1 行存疑、AI 复核后整表被覆写成同值"的数据污染路径
2. **表级字段白名单**：施工部位/施工日期（整表同值）才走 `scope=table` 整表写；无桩号且不在白名单的字段跳过（无法安全落库）
3. **「整行」项过滤（R-2）**：表头不可靠产的整行核对项不进视觉复核（读图无法单值作答、会新建中文键错位落库），留给 Chat-Verify 整行核对通道
4. **field_label 中文反查**：行级任务 field_label 统一中文显示（实长/充盈系数/桩径等）；H-8 回归组新增 3 条锁定用例，套件 41/41 全绿

### v9.7 新增（AI 视觉复核链贯通 + 协议平台无关化）

1. **H-8 视觉复核断链修复（`scripts/verify_fields.py`）**：
   - 🔗 扫描转化电子文档的两套存疑清单（confusion 易混字 + pending 表级乱码）此前从未接入复核器；v9.7 自动合流生成统一复核任务
   - 🖼️ docx 内嵌图提取：WPS 扫描件转 docx 每页即一张内嵌图，按 document.xml 引用顺序解压（表 t ↔ 第 t+1 张图），裁图支持 docx 来源
   - 🛡️ merge 落库三修复：中文字段自动映射英文行键（不再错位新建中文键）；定位按 task_id 回查任务清单（不依赖 AI 手抄）；structured_rows + rows 双份同步写

2. **视觉复核协议平台无关化（SKILL.md 步骤 4.5）**：
   - 📋 任务清单（JSON）+ 裁图（PNG）+ 结果（JSON）三文件协议，不绑定任何平台特性
   - 🤖 TRAE / WorkBuddy / CodeBuddy 等任何具备读图能力的智能体均可执行：读 verify_tasks.json → 逐张读 crops/*.png → 写 verify_results.json → merge 落库
   - 🚦 置信度分级：high/medium 自动落库，low/图不清留给 Chat-Verify 人工核对；无视觉能力平台自动降级，存疑项不丢失
   - 🔒 不豁免 G-1.9/G-2 人工核对闸门——AI 复核是"减负"不是"放行"

3. **build_foundation 自动接线**：`nature=扫描转化电子文档` 建底座时自动产出 `verify_output/`，index.json 登记 `verify_tasks_file`；失败不阻塞底座构建

4. **vision_providers 新增腾讯混元**：`HUNYUAN_API_KEY`，OpenAI 兼容接口；vision API 复核路径 A 可选

5. **回归测试扩充**：`test_regression_hazards.py` 新增 H-8 组 8 条，套件 38/38 全绿；独立复核当轮处置：docx 行级任务页码按行所在表号推导（修复裁错页）、A3 触发条件补 nature 校验、字段别名复用 rule_engine 单一真相源

### v9.5 新增（Chat-Verify 聊天核对 + 推荐值独立化 + 文本建议值）

1. **Chat-Verify 聊天式人工核对（`scripts/chat_verify_apply.py`）**：
   - 💬 阶段 2 第一通道，AI 对话框内按表分组抛转 OCR 存疑项，用户短答修正即落库，手机可用；数据编辑器降级为后备通道 B
   - 🧩 子命令：`list`（按表分组，附建议值+置信度+来源+**页码定位**）/ `apply`（含 `accept_recommended` 零转抄落库）/ `refresh` / `confirm`（核对完→human_verified=true 进阶段 3）/ `status`
   - ✅ 全部核对完 + 用户确认 → `human_verified=true`，通过 G-1.9 硬停闸门

2. **推荐值规则独立化（`rules/inference_rules.json`，schema 1.1）**：
   - 📐 数值链规则 7 条（桩基/垫层）由配置文件驱动，置信度 < 0.5 也输出并打颜色标记
   - 🗂️ 新增**文本/枚举规则**：施工部位→同表众数、施工日期→补齐；文本建议值带 `suggested_only` 标记，**只建议不入库**（级别低于权威输入），用户 `accept_recommended` 采纳后才落库
   - 🔒 **跨表防污染安全锁**：候选值与邻行检索严格限定同表（按 `row['table']`），绝不跨表/跨页抓邻居当建议值；同表部位值 ≥2 种时禁用众数，退化邻行推断；跨月施工日期置信度降低

3. **docx 表格解析下沉 + 数据底座修复**：
   - 📥 `build_foundation.py` `parse_docx_table_sheets()` 直接解析 docx 表格，替代外部 enrich_docx.py 补丁，产出结构化存疑清单供 Chat-Verify 消费
   - 🔧 None 污染→空字符串；pages 失真（docx 页码=表格数）；DOC-002 路径归位 `碎石桩施工记录/`；分类确认；is_handwritten 去 null→false

4. **仅刷新建议值命令（`cmd_refresh`）**：只重算并写回 `inferred` 字段，**不碰**核对进度/存疑清单/corrections/`human_verified`，便于规则升级后补建议值而保留用户核对进度

### v9.4 新增（表格式样导入导出 + 苹果浅色界面优化）

1. **表格式样面板（data-editor 新增标签页）**：
   - 🧱 **前缀区**：表格上方固定内容（如工程名称、表号、施工单位），仅用于定位表体，不定义格式样式；支持**添加 / 删除 / 编辑 / 上下移动**行
   - 🔢 **数字区**：定义每列填写的格式样式，列名可直接编辑；支持**添加 / 删除列**；每列可写**多种格式样式**（用 `/` 或 `，` 分隔，如 `2026年/2026-01-01`）；附带**备注**列供说明
   - 🎯 **格式样式作用**：填写样式后，核对时按该样式校验扫描件的值（如日期列写 `2026年`，则非 2026 年的值标需核实）

2. **从电子表导入表格式样（`scripts/import_template.py`）**：
   - 📥 解析电子版表格（`.xlsx` / `.docx`），自动识别表头行，提取前缀区固定行与数字区列定义（列名 / 样例值），生成 JSON 模板
   - 📄 用法：`python scripts/import_template.py 表格.xlsx [--header-row 行号] [--out 输出.json]`
   - 🖱️ data-editor 提供「导入 JSON」按钮加载模板，「保存样式定义」写回 `index.json`

3. **苹果浅色界面优化（表格式样面板）**：
   - ✨ 去除大片蓝色背景，改为白底 / 浅灰描边 / 浅蓝点缀的苹果风格，与编辑器其余面板风格统一
   - 🎨 表头浅灰底深灰字、可编辑区聚焦浅蓝描边 + 淡蓝光晕、操作按钮浅灰底悬停变色

4. **与几何重建联动**：导入的表格式样作为**值格式锚点的补充**，数字区格式样式用于校验列值所属格式，前缀区用于定位表体，与 `table_struct.validate_rows()` 六类校验互补。

### v9.0 新增（RapidOCR 本地主力 + 手写体前置 VLM 路由）

1. **本地 OCR 引擎替换为 RapidOCR（rapidocr）**：
   - 🚀 已彻底替代原生 paddleocr：Windows 下环境依赖轻、跨平台稳定，**无需安装 PaddlePaddle**，规避 PaddlePaddle 3.x PIR 引擎 Windows 兼容性问题
   - 🧠 模型选择：使用 rapidocr>=3.9 统一包，默认加载 PP-OCRv6 Small 模型（`ModelType.SMALL`）；通过 `RapidOCR(params=...)` 的 `ModelType` 和 `OCRVersion` 参数配置
   - ⚡ **引擎单例化**：`_get_rapidocr_engine()` 全局单例，批量图片只加载一次模型，严禁 for 循环内重复实例化
   - 🖼️ **图像预处理**：`_preprocess_for_rapidocr()` **仅保留灰度化**，已删除 CLAHE/高斯模糊/锐化核（实测对印刷体 OCR 无提升且拖慢速度）

2. **手写体前置路由（is_handwritten）**：
   - 📝 手写资料（`is_handwritten=True`）：**直接跳过本地 OCR**，首选 `vision`（VLM，识别率最高），次选 `agent`（AI 读图）
   - 🖨️ 印刷资料（`is_handwritten=False`）：首选本地 `rapidocr`，失败再降级 `vision` → `tesseract`
   - 🎯 文件名启发式判定：`detect_is_handwritten()` 匹配"手写/笔记/草稿/note"等关键词；可用 `--handwritten` 参数或前置信息 `config.is_handwritten` 显式指定

3. **配置开关（调试）**：
   - `DISABLE_HANDWRITING_ROUTE=1`：强制所有资料走本地 OCR，跳过 VLM 路由
   - `FORCE_USE_PADDLE` 已彻底移除：原生 PaddleOCR 不再可用，无回滚备份

4. **VLM 手写体专用 Prompt**：
   - `HANDWRITTEN_OCR_PROMPT`：当路由走 vision 且资料为手写体时，追加 System Prompt 指令——结合上下文语境推断纠错、无法辨认用 `[?]` 标记、严格 JSON 输出

5. **关键节点日志监控**：
   - `[路由判定]` 文件名及 is_handwritten 状态
   - `[引擎选择]` 最终决定调用的引擎（rapidocr / vision / tesseract）
   - `[识别结果]` 识别出的文本行数及平均置信度

6. **路由测试**：`test_ocr_routing.py` 独立测试脚本，21/21 通过，覆盖手写/印刷路由、配置开关、文件名启发式判定、关键日志节点

7. **运行时进度展示（强制）**：正式审核运行中，AI 每条回复固定展示"第一/第二/第三/第四"四阶段运行进度清单，完成一条打勾一条（✅/⬜），闸门硬停时写明卡住原因与等待用户操作，用户无需看终端日志即可掌握审核进度

### v8.7 新增（OCR 全流程加固 + 模板目录重构 + 用户体验全面升级）

1. **OCR 全流程加固（四项核心修复）**：
   - 🛡️ **表头检测优化**：`detect_generic_header()` 新增超长 token 过滤（排除>10字符的公司名/标题）和列名关键词命中要求（至少1个列名型关键词如"序号/桩号/日期/高程"），解决施工单位名称被误判为表头列名的问题
   - 📐 **表头续行合并**：`parse_pile_rows()` 和 `parse_generic_table()` 检测到表头后，自动检查紧接的1-2行是否也是表头续行（如"桩/设计/桩径..."+"号/长/(m)/..."），合并字段映射并跳过续行，解决表头拆分导致数据错位
   - 📄 **跨页表头继承优化**：翻页后重新检测表头，未检测到但遇到桩号格式数据行时才继承首页表头，解决跨页表头行被当作数据行的问题
   - 🎯 **内容感知分类**：`build_rows()` 新增桩基内容关键词检测（碎石桩/沉管时间/拔管时间/充盈系数等≥2个命中），即使文件名是"扫描件.pdf"也能自动走桩基解析逻辑，解决通用文件名分类遗漏

2. **模板目录重构（集中存放 + 中文命名）**：
   - 📂 所有 Web 模板统一复制到项目文件夹 `数据底座/` 目录下，不再与审核资料混放
   - 🏷️ 中文命名：data-editor.html→**数据核对编辑器.html**、project-dashboard.html→**项目总览.html**、launcher.html→**打开审核工具.html**
   - ✂️ 精简非必要模板：移除 rule-editor.html、feedback-collector.html 等低频工具
   - 📋 `template-manifest.json` 升级至 v1.3，统一管理 src/dst/required/category，跨模式可靠复制

3. **data-editor 自动加载与中文化**：
   - 🚀 新增 `autoLoad()` 函数，打开即自动尝试 `fetch('./index.json')`，无需用户每次手动选择文件夹
   - 💾 localStorage 记住上次加载项目名称，下次打开自动提示"上次项目：XXX"
   - 🀄 按钮文案全中文化："选择项目文件夹"→"**加载数据底座**"，降低小白用户理解门槛

4. **launcher 三步指引 UI（流程化导航）**：
   - 1️⃣ **核对数据**：大按钮直链「数据核对编辑器.html」，附说明"逐份核对 OCR 识别结果，确认无误后标记已核对"
   - 2️⃣ **查看报告**：审核报告入口 + 「项目总览」仪表盘，动态显示项目状态（审核时间、资料数量、问题统计）
   - 3️⃣ **其他工具**：文档对齐视图、规则管理工具.bat 等次级入口
   - 顶部设计令牌 tokens.css 统一视觉风格

5. **rule-manager.bat 自动定位（小白零配置）**：
   - 📍 三级路径自动查找：当前目录 → 上级目录 → `%USERPROFILE%\.trae-cn\skills\civil-aviation-doc-audit\`
   - 🀄 全中文界面提示，明确显示"当前规则路径：%SKILL_DIR%rules\"
   - 📋 自动复制到 `数据底座/` 目录，用户双击即可启动，不需到 skill 安装目录找文件

6. **OCR 引擎四选一前置（用户明确选择）**：
   - 🔧 6 项前置信息第 4 项新增：**OCR 引擎**（auto / vision / rapidocr / agent 四选一）
   - 默认 **auto**：自动路由（印刷体 RapidOCR，手写体 vision，均不可用降级 tesseract）
   - **rapidocr**：强制使用本地 RapidOCR（PP-OCRv6 Small，批量零 token，推荐离线场景）
   - **agent**：强制使用 AGENT 内置 Vision（页数不限，逐页读图，不装依赖也能用）

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
# 一键安装（Python 依赖 + Vision API 配置 + RapidOCR 强烈推荐）
.\install.ps1
```

或手动安装：

```bash
pip install -r requirements.txt
```

### 2. v6.0 四阶段流水线（推荐，项目级审核）

```powershell
# 阶段 1：建立数据底座（全自动）
# --engine 参数：auto（默认）/ vision / rapidocr / agent（v9.2 OCR引擎四选一）
python scripts/run_audit.py build "D:\你的项目文件夹" --engine auto

# 阶段 2：人工核对（浏览器中打开「数据底座/打开审核工具.html」→ 点「核对数据」，零 token）
# v8.7 模板已复制到「数据底座/」目录，中文命名：
#   数据核对编辑器.html / 项目总览.html / 打开审核工具.html / 规则管理工具.bat

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

SKILL.md 顶部设有**路由表**，AI 根据用户输入自动定位到对应场景。详见 SKILL.md「路由表」章节。

**审核流水线场景**：
- "建数据底座" / "审核这个项目的资料" / "正式审核" / "开始审核"
- "人工核对" / "打开数据编辑器"
- "生成审核报告" / "出报告"
- "增量更新" / "补充资料"
- "并行审核" / "多 Agent 审核"

**规则管理场景**：
- "规则管理" / "管理规则" / "规则面板"
- "新建规则" / "添加规则"
- "规则反馈" / "漏审反馈" / "误报反馈"
- "启动反思" / "触发反思"

**v5.0 单文件触发语句**：
- "审核这份检验批 / 监理通知单 / 施工日志 / 竣工图"
- "看看这份资料有没有逻辑矛盾"
- "这是扫描件，做 OCR 后审核"

**安装触发语句**：
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
# 方式一（v8.7 推荐，零配置）：在项目「数据底座/」目录下双击「规则管理工具.bat」
# （已自动复制到数据底座，自动定位 skill 安装目录，中文界面）

# 方式二：双击 skill 根目录的 rule-manager.bat
.\rule-manager.bat

# 方式三（手动启动）：
python scripts/rule_admin.py --port 8765
# 浏览器打开 http://127.0.0.1:8765/
```

规则文件位于 `rules/` 目录（跟着 skill 走，所有项目共用一套规则）：
- `L1-iron/`：铁律（不可违反的强制性条款）
- `L2-logic/`：逻辑规则（跨文档/跨资料一致性）
- `L3-business/`：业务规则（分部分项专项要求）

规则编辑方式：
1. **Web 面板**（推荐小白）：双击「规则管理工具.bat」，4 标签页可视化编辑（规则浏览/新建/统计/反思）
2. **离线编辑**：浏览器打开 `templates/rule-editor.html`，选择 skill 目录下的 `rules/` 文件夹（无需启动服务）
3. **硬核方式**：直接用文本编辑器修改 `rules/` 下对应 JSON 文件

> **v8.7 重要说明**：`rule-manager.bat` 支持三级路径自动定位（当前目录→上级目录→全局 skill 安装路径），无论在哪个目录双击都能正确找到 rules/ 目录。

---

## 四阶段流水线详解（v6.0，引擎/原生模式统一）

> 引擎模式（Python 可用）和原生模式（Python 不可用）的流程差异见 SKILL.md「场景·审核流水线」章节。此处仅展示统一流程。**引擎模式与原生模式数据完全兼容，可双向迁移**。

```
┌──────────────────────────────────────────────────────────┐
│ 阶段 1：建数据底座（全自动）                              │
│   输入：项目文件夹 + 6 项前置信息                         │
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

## OCR 引擎策略（v9.2 更新：RapidOCR 轻量本地主力 + 手写体前置路由）

v9.2 重新定位 OCR 引擎角色：**印刷体 → RapidOCR（rapidocr，轻量跨平台本地主力，零 token）→ Vision API 辅助 → Tesseract 兜底**；**手写体 → 自动前置路由 Vision API（VLM，识别率最高）→ AGENT 内置 Vision 复核工具（非批量引擎）**。默认 auto 模式自动路由。

> **🍀 推荐路径：`扫描转化电子文档`**：扫描件先用 WPS「PDF 转 Word」转成带真实表格的 .docx，走**电子表解析**（`extraction_mode="docx"`），识别准确率显著高于本地 OCR，且**不设 OCR 引擎优先级**。前置信息 `nature=扫描转化电子文档` 时，OCR 引擎选择自动跳过。因仍源自手写扫描，`human_verified` 人工核对闸门照常保留。

```
PDF / 图片
   │
   ▼
判定 is_handwritten（手写体前置路由）
   │
   ├─ 手写体 = True（文件名含"手写/笔记/草稿/note"，或 --handwritten 显式指定）
   │   ├─ 首选 vision（VLM，识别率最高）★ 追加手写体专用 Prompt
   │   └─ 次选 agent（AI 读图，页数不限，仅提醒 token 消耗）
   │
   └─ 手写体 = False（印刷体）
       ├─ 首选 rapidocr（本地，零 token 消耗）★ RapidOCR 单例 + 图像预处理
       │   └─ 失败 → vision（VLM）→ tesseract（本地兜底）
       └─ 无任何可用引擎 → agent（AI 读图，页数不限）
```

### auto 模式优先级链（v9.2）

| is_handwritten | 引擎优先级 | 说明 |
|:---:|:---|:---|
| True | vision → agent | 手写体直接走 VLM，跳过本地 OCR |
| False | rapidocr → vision → tesseract | 印刷体先本地 OCR，降级 VLM / Tesseract |

### 配置开关（v9.2 调试）

| 环境变量 | 取值 | 作用 |
|:---|:---:|:---|
| `DISABLE_HANDWRITING_ROUTE` | `1` | 强制所有资料走本地 OCR，跳过 VLM 路由 |

> `FORCE_USE_PADDLE` 已彻底移除：原生 PaddleOCR 不再可用，无回滚备份。

### RapidOCR 模型指定（PP-OCRv6 Small）

默认加载 PP-OCRv6 **Small** 模型（`ModelType.SMALL`，rapidocr>=3.9 统一包）；如需指定模型，通过 `RapidOCR(params=...)` 的 `ModelType`（SMALL/MEDIUM 等）和 `OCRVersion` 参数配置。

### 离线场景：安装 RapidOCR（强烈推荐 ★）

```powershell
pip install rapidocr opencv-python
```

> ⚠️ **为什么强烈推荐安装？** 不安装 RapidOCR 且无 Vision API Key 时，多页扫描件将使用 AGENT 内置 Vision 模型逐页读图，大量消耗 token 且识别速度慢。

### Vision API 支持的 7 家 Provider

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
| **v8.0** | **2026-08-04** | **OCR 策略重定位：PaddleOCR 从"可选"升级为"强烈推荐"、AGENT Vision 从"最终兜底"降级为"复核工具（≤5 页）"、安装引导强化 token 消耗警告** |
| **v8.1** | **2026-08-04** | **双模式运行架构：引擎模式（Python 可用，四阶段流水线）+ 原生模式（无 Python，三阶段简化流水线），适配 WorkBuddy/Codex/Hermes，低智商模型适配（34 项检查清单）** |
| **v8.2** | **2026-08-04** | **强制闸门修复：顶部新增 G-0/G-1/G-2 硬闸门 + 原生模式阶段 1 机械化步骤清单（7 步骤），修复 WorkBuddy 中 AI 跳过数据底座直接输出审核结论的问题** |
| **v8.3** | **2026-08-04** | **模板复制修复：原生模式新增步骤 7 复制 Web 模板 + G-1.5 闸门，修复 WorkBuddy 建了数据底座但不复制 data-editor.html 等模板文件的问题** |
| **v8.4** | **2026-08-04** | **人工核实硬停修复：原生模式新增 G-1.9 硬停闸门 + 扫描件待核实清单，阶段 1 完成 = AI 必须停下来等用户人工核实扫描件，修复 AI 不等人工核实直接出审核结论的问题** |
| **v8.5** | **2026-08-04** | **增量路径：新增步骤 0.5 数据底座检测 + I-1~I-6 增量路径（文件 diff → 一键确认 → 三选一 → 模板智能拷贝 → 增量 OCR → 硬停），解决增量审核时重复弹窗、重复 OCR、老问题重复报告、模板漏拷的问题** |
| **v8.6** | **2026-08-04** | **嵌入数据入口页：launcher.html 改为数据嵌入（`__PROJECT_DATA__` 占位符）替代 fetch()，解决 file:// CORS 拦截导致入口页无法加载数据的问题；增量 I-4 只更新入口页不重拷静态模板；步骤 7 拆分 7a/7b** |
| **v8.7** | **2026-08-05** | **OCR 全流程加固 + 模板目录重构 + 用户体验全面升级：表头检测优化（超长token过滤+列名关键词）+ 表头续行合并 + 跨页表头继承优化 + 内容感知分类 + 分词修复；模板统一存放数据底座目录+中文命名；data-editor自动加载+localStorage记忆项目；launcher三步指引UI；rule-manager.bat三级路径自动定位；OCR引擎四选一前置；PaddleOCR dpi=72→200修复；OCR retry行数比较回退保护；Excel continue链路修复；copy_templates.py独立脚本** |
| **v8.8** | **2026-08-05** | **PaddleOCR 引擎升级：从 PaddleOCR 2.8.1 + PaddlePaddle 2.6.2 升级为 PaddleOCR 3.x + PP-OCRv6 Tiny + ONNX Runtime；使用 engine=onnxruntime 绕过 PaddlePaddle 3.x PIR 引擎 Windows 兼容性问题；模型体积从 ~30MB 缩小到 ~3MB；无需安装 PaddlePaddle；auto 模式优先级改为 PaddleOCR 优先；agent 模式支持修复（run_audit.py/build_foundation.py/ocr_image.py 三处 --engine 参数补齐 agent 选项）** |
| **v8.10** | **2026-08-08** | **数据验证闸门 + 表头消歧定列 + 数据验证闭环：`table_struct.validate_rows()` 六类校验（类型/格式/范围/完整性/一致性/跨字段数学链）落地于数据底座写入前，脏行标 `needs_review` 不直接进库，行级 `issues` 写入 `structured_rows[i].issues`；列角色推断改为值格式锚点为主 + 表头文字消歧/补空缺，修复列错位（pile_no='28'、actual_length='2401'）；data-editor 层3 闭环（有 issues 行标红⚠+内联原因 → 问题视图接入六类校验条目 → 精准跳转橙闪 → 确认门禁阻止未处理 issues 放行，人工修正/忽略后放行），形成"闸门→呈现→人工核对→放行"闭环** |
| **v9.0** | **2026-08-07** | **OCR 模块重构：本地主力从原生 paddleocr 替换为 rapidocr（RapidOCR，跨平台轻量稳定、无需 PaddlePaddle）；RapidOCR 引擎单例化 + 图像预处理（灰度化+CLAHE+去噪）；新增手写体前置路由（is_handwritten=True 直接走 vision/agent，False 走 rapidocr→vision→tesseract）；VLM 手写体专用 Prompt（HANDWRITTEN_OCR_PROMPT）；配置开关 FORCE_USE_PADDLE / DISABLE_HANDWRITING_ROUTE；关键节点日志（路由判定/引擎选择/识别结果）；test_ocr_routing.py 路由测试 21/21 通过；requirements.txt 更新（快速依赖 rapidocr，注释 paddle 依赖）** |
| **v9.1** | **2026-08-08** | **RapidTable(SLANetPlus) 表格结构识别 3.14 原生，取代旧 TableStructureRec（仅 Python≤3.12）双环境 subprocess，单一环境完成表格还原；方式二对话式核对四条强制纪律——默认批量 / 条件补扫（提DPI→换预处理→换VLM，无解标存疑回原图严禁硬猜）/ 落盘强制（写回 data_file + index.json 四项）/ 推断标记+禁子代理（inferred:true+置信度，禁 Explore Agent）** | **实测：对话式核对逐条确认不落盘致 data-editor 显老数据；Z516 充盈系数 1.89/1.29 推断值标注不清污染审核；逐条渲染读图上下文膨胀越核越慢；Explore Agent 后台空转** |
| **v9.2** | **2026-08-08** | **错位率阈值收紧 + AGENT 复核放开页限 + 数据编辑器文本行可编辑** | **用户要求：错位率阈值设为 5%；放开 AGENT 复核页数限制；实测文本行表格只有 3 列且无法修改** |
| **v9.4** | **2026-08-10** | **表格式样导入导出 + 苹果浅色界面优化 + SKILL.md 内部路由重构** | **用户要求：实现从电子表格导入表格式样；去掉大片蓝色背景，改用苹果浅色风格；SKILL.md 按场景路由重构** |
| **v9.5** | **2026-08-19** | **Chat-Verify 聊天式人工核对 + 推荐值规则独立化 + docx 表格解析下沉 + 数据底座修复 + 文本建议值（施工部位/日期补齐，只建议不入库）+ 跨表防污染安全锁 + 存疑项页码定位 + 仅刷新建议值命令** | **用户要求：AI 对话框即可核对（手机可用）；乱码文本域出建议值；推荐值只建议不自动入库；同表≠跨表防污染；刷新不动核对进度** |
| **v9.7** | **2026-08-20** | **AI 视觉复核链贯通（H-8 隐患销号）：confusion+pending 存疑自动合流生成复核任务 + docx 内嵌图提取裁图 + merge 按 task_id 回查定位/中文字段映射英文行键/双份 rows 同步写 + build_foundation 自动接线 verify_output + 视觉复核协议平台无关化（JSON+PNG 三文件协议，WorkBuddy 等任意智能体可执行）+ vision_providers 新增腾讯混元** | **用户要求：第二类资料（扫描转化电子文档）识别要发挥 AI 视觉优势；skill 要能在 WorkBuddy 等其他平台跑** |
| **v10.0** | **2026-08-25** | **资料员工作台（Web Workbench）九页合一：一次加载 index.json + Seven 模块（总览/核对/看板/台账/概览导出/销号/规则反馈）+ Vite+SortableJS+SheetJS+xlsx+ECharts+IndexedDB + 一键启动 bat + 部署管线接入（dist→workbench）** | **用户要求：资料管理从零散 HTML 页升级为一体化工作台；跨端可用** |
| **v10.2** | **2026-08-25** | **Excel/docx 建数据底座链路修复（专项审查销号）：xlsx 解析不再整表截断（break→单行跳过）+ row_index 行级定位键（三链路统一）+ 列语义对齐（中文字段投影英文标准槽位）+ 表头扫描窗口 20→100 + 日期序列号转日期串 + 质检 _is_num 误报修复（全字符串数据百分百误报→精准报告）** | **审查结论：Excel 链路"丢数据不报警"；Word/PDF 链路弱化点修复** |

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

---

## 铁律体系演进脉络

> 本节记录铁律体系从 v1.0 到 v1.7 的演进历史，供理解设计思路参考。

| 阶段 | 版本 | 核心变化 | 驱动来源 |
|:---:|:---|:---|:---|
| 第一轮 | v1.0~v1.4 | 20 条铁律体系建立 | 实际审核发现的问题逐条沉淀 |
| 第二轮 | v1.5 | 五专业审核全覆盖 + Obsidian 知识库集成 | 用户要求专业审查全面有章可循 |
| 第三轮 | v1.7 | 前置信息收集 + OCR 存疑核实 + 统一 HTML 交付 | 用户反馈 OCR 年份误读 + 过程资料误判 |
| 第四轮 | v1.8~v1.9 | 三层工作流重组 + 知识分区红线 + 三级输出格式 + 多Agent并行 + 标准模板 | 对标分析后的框架级全面提升 |

### 演进要点

- **铁律 1~8**（v1.0~v1.4）：从实际审核中逐条沉淀的基础规则
- **铁律 9**（v1.5）：逻辑一致性专项检查，10 个子项 + 监理-施工方跨单位对照 17 条
- **铁律 10**（v1.5）：数据质量四类检测（DQ-REPEAT/JUMP/ALTER/SELF）
- **铁律 11~15**（v1.5）：桩基工程专项检查规则
- **铁律 16~20**（v1.7）：OCR 提取-验证-重试循环 + 人工核实机制