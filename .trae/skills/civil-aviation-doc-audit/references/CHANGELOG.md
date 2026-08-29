# 更新日志

> 本文件记录 civil-aviation-doc-audit Skill 各版本的核心变更。SKILL.md 正文仅保留最新版本概要。

## v10.6（2026-08-29）

**OCR 复核升级 + 跨平台视觉调度 + 文本层体检路由（三线改造）**

起因：RapidOCR 置信度造假（`0:8` 报 0.99997、"m²"读成 m2），旧 `crop_and_verify` 是空壳（直接返回原值、假抬置信度 ≥0.70、标记未修改）；且宿主视觉硬编码 `has_agent=True`，WorkBuddy 等无视觉宿主上读图任务永远空等。核心决策「不引入 pdfium / 不搬 pdf-inspector」（实测 pdfium 表格串位，引入 6 个新错识）。

- **线1 裁图复核做真**（`ocr_image.py`）：`crop_and_verify` 重写——裁图真实落盘 + 任务清单（`CV-` 任务 ID）+ 读回合并；未读回时置信压 0.55 待读（不假通过）。双闸门 `_needs_review`：置信 < 0.985 或语义可疑（`数字:数字`、`m2/m3`）即使 1.0 置信也强制复核。批级锚点：任务 ID 基于 PDF 内容哈希（跨进程可匹配）。主流程接线 + 缓存补复核（H-12 盲区修复）。PDF 裁图坐标系对齐（H-13：渲染 DPI 与 bbox 一致，原固定 2x/144dpi 渲染把 200dpi bbox 当 PDF 点 → 区域塌缩 → 裁图静默全空）
- **线2 视觉调度降级**（`vision_reviewer.py` 新增 + `verify_fields.py`）：`confirm_vision_capability` 能力探测（AGENT_VISION 显式声明制）+ `resolve_review_level` 四档纯函数（host_agent → api → rule → noop）；`select_verify_path` 默认参数 `has_agent=True → None`（走探测），显式传参兼容不变；`ocr_image._cropverify_level` 档位闸门——显式无视觉时跳过任务生成、压置信待人工下核对
- **线3 文本层体检路由**（`extract_pdf.py`）：`probe_text_layer` 全页密度双阈值（非空页占比 ≥0.6 且非空页均字 ≥10）判定 text/scanned；`detect_scanned` 改薄包装（旧签名兼容）；`--probe` CLI 输出路由决策 JSON。吸收 pdf-inspector 思想但不吸收其 pdfium 引擎
- **回归锁定**：新增 `scripts/test_ocr_verify_upgrade.py`（H-9~H-13 共 15 条：双闸门/读回合并/接线守卫/文本层路由/视觉降级/缓存补复核/坐标系对齐）注册进 `run_all_tests.py`；run_all_tests 19/19 全绿
- **验收**：样例回归（碎石桩记录样例 p0）9 错全修口径 PASS——`0:8→0.8`×3、`8:03→8.03`×3、`1:15→1.15`×2、`灌入量(m²)→(m³)`×1，全部 `ai_reviewed=True`、零待读残留，与 4way 基线一致；双端同步 7 文件哈希一致 + pycache 清理

## v10.5（2026-08-26）

**无规则覆盖运行时闸门——声明式触发的静默盲区显形**

- **运行时侦测（核心）**：`rule_engine.py` 新增 `build_unguarded_doc_types`——审核运行时自动识别本批受审文档中无任何 active 规则覆盖的 doc_type，写入 `summary.unguarded_doc_types`（含 doc_type/份数/说明）。此前这类类型被规则引擎静默跳过，AI 与用户均不知情
- **判定口径（防误报）**：SINGLE_DOC/CROSS_DOC 按 `trigger_when.doc_type` 名单（`'*'` 通配生效）、CROSS_UNIT 按 `doc_type_a/b` 双侧匹配，三类 scope 任一命中即视为有覆盖；仅统计 `doc_role == 'audited'` 的受审文档（缺省 None 视为受审），reference 角色（审核参照）不进提醒防噪音
- **报告端渲染**：`report_builder.py` 行动层新增「八、无规则覆盖提醒」节——非空时输出醒目警示框（类型数/份数/说明表），全部有覆盖时整节不出现（不硬造提醒）；取数兼容 `rule_engine_summary` 子 dict 与顶层两种结构
- **SKILL.md 强制协议**：AI 生成报告前必须检查 `unguarded_doc_types`，非空时须向用户显式说明"以下类型无规则引擎兜底"，禁止静默跳过
- **扫描工具口径校准**：`scan_rule_coverage.py` 复用 `build_unguarded_doc_types` 同一套判定逻辑（工具与运行时不打架），仅统计受审文档，修复"设计变更文件 30 份伪缺口"误报
- **零交集规则修复**：IR-010/IR-011/LG-905 的 `trigger_when.doc_type` 补「场道施工记录」触发词——修复因触发词与生产 doc_type 失配导致的三条规则静默失效；扫描确认零交集规则 3 → 0
- **回归锁定**：新增 `scripts/test_unguarded_doc_types.py`（8 条：字段存在/无覆盖点名/有覆盖不误报/CROSS 兜底不算裸检/全覆盖为空/报告渲染/真实链路取数/reference 过滤）注册进 `run_all_tests.py`；run_all_tests 18/18 全绿

## v10.4（2026-08-26）

**规则→审核→报告全链路贯通 + 报告三层结构重构（A/B 两组专项）**

- **LG-110 静默失效修复（A 组根因）**：LG-110 `trigger_when.doc_type` 与生产环境真实材料类文档类型「材料、构配件进场检验记录」失配 → 规则写了但从未执行。补触发词后规则真正进审核链路
- **审核期 S-04 重算（陈旧结果销号）**：`review_audit.py` 新增步骤 5.6 调用 `extract_certificates.collect_certificate_findings`，基于人工修正后的 corrected 数据重算 S-04 并原子刷新台账——修复"用户改完数据重审仍报旧问题"
- **规则执行统计（静默失效显形）**：`rule_engine.py` 新增 `build_execution_stats`（每条规则的 matched_docs/hits），`review_audit` summary 注入 `rule_execution_stats`；报告端渲染统计表，0 匹配规则标 ⚠
- **规则覆盖扫描工具**：新增 `scripts/scan_rule_coverage.py`，扫历史数据底座真实 doc_type 与规则触发词对账，一次性揪出 18 条零交集规则与 6 个覆盖缺口；CFG 桩施工记录（历史生产 3 份文档）补齐 9 条通用桩类规则覆盖，测试锁定防复发
- **报告生成建模渲染分离（B 组结构）**：run_audit 内嵌 ~450 行巨型报告函数拆出 `report_builder.py`（`build_model` 纯数据建模 + `render_html` 纯渲染），run_audit 改薄包装调用；任何 agent 装此 skill 出的报告结构由测试锁定一致
- **三层报告结构**：结论层（审核概要+总体结论）→ 问题层（规范对账发现，新增「整改建议」列渲染 remediation）→ 行动层（规则执行统计+整改建议）；依据缺失/未标注警示渲染不回退
- **页脚版本号单一真相源**：报告页脚版本从 SKILL.md frontmatter `version:` 动态读取，不硬编码（修复页脚 v7.0 与实际版本漂移）；SKILL.md 补 `version: "10.4"` 元数据
- **verify_report 合格证台账对账闸门**：新增 `check_certificates_alignment`——报告声称的合格证台账记录数 vs 底座 `ledgers.certificates` 实际数对账，不一致即红
- **验证脚本健壮性**：`verify_plan_v2.py` 版本号识别由硬编码行号（frontmatter 加字段即错位）改为 H1 标题正则全文搜索
- **回归锁定**：新增 `test_rule_to_report_chain.py`（10 条：LG-110 触发/审核期重算/台账刷新/接线/执行统计/0 匹配标记/registry 计数/不重复执行/CFG 覆盖）+ `test_report_builder.py`（6 条：模块消费/整改建议列/统计渲染/版本号一致/golden 三层锚点/证书对账）注册进 `run_all_tests.py`

## v10.3（2026-08-25）

**材料/合格证数据链沉淀（验收 S-01~S-04 专项）**

- **A1 材料类文档信号路由**：`build_foundation` 识别 doc_type / 文本含「合格证/质量证明书/进场检验/检验记录/质证书编号/出厂合格证」时强制排除桩基解析，杜绝"材料文档含碎石桩字样被桩内容感知劫持 → 产出空行或混入桩槽位"
- **E1 OCR 零产出判定**：`assess_ocr_result` 识别"仅有 bbox 无文字"的空框结果为零产出，`ocr_status` 判 `needs_review` 而非 `completed`，禁止空结果进入结构化流程
- **E3 材料 schema 契约**：材料类文档 `schema_status="material"`，DQ 质检跳过桩基领域规则、不再误报"表格 schema 未确认"
- **A2/A4 合格证提取与台账落库**：新增 `extract_certificates.py`，从检验记录/合格证行提取结构化证书记录（合格证号/质证书编号/厂家/材料/规格/单位/数量/部位/进场日期），按合格证号去重，落库 `index["ledgers"]["certificates"]` 并回写 `documents[].certificates` 关联元信息；原子写避免半截 JSON
- **A5 S-04 追溯链检查**：`build_certificate_linkage` 从台账检出 `verified_status=missing_hg_no`（合格证号为空）记录，落为 S-04 问题写入 `index["ledgers"]["certificates_linkage"]`，报告/审核直接读取，口径一致
- **LG-110 新规则**：新增 L2 规则「材料进场检验记录合格证追溯链」，描述/触发/校验/S-04 对齐，注册进 `registry.json`
- **规则注册表与校验器对齐**：`rule_registry_builder.py` 与 `rule_schema_validator.py` 的 `collect_rule_files` 仅收集 L1-iron/L2-logic/L3-business 子目录，排除根目录 `inference_rules.json`、`table-schemas.json`，registry 计数与实际文件一致
- **回归锁定**：新增 `scripts/test_material_certificate_chain.py`（13 条：材料路由/OCR 零产出/schema 跳过桩检查/提取/去重/台账落库/JSON 往返/S-04 检出/同步双端部署/列错位保留）注册进 `run_all_tests.py`；run_all_tests 15/15 全绿

## v10.2（2026-08-25）

**Excel/docx 建数据底座链路修复（专项审查销号）**

- **P1 数据行过滤不再整表截断**：`parse_excel_workbook_rows` 命中「施工员/监理/合计/审核」等关键词由 `break`（其后全部丢弃）改为**单行跳过**；仅"无数字+落款词开头"的表尾才 break。实测数据行含「监理/审核」时后续数据完整保留
- **P5 行级定位键**：Excel 行补 `row_index`（sheet 内物理行号）、docx 行补 `row_index`（表内序号），对齐单文件 schema `row_index` 契约，写回/核对可定位到具体单元格行
- **P4 列语义对齐**：可识别表头列追加英文标准槽位键（桩位编号→`pile_no`、有效桩长→`actual_length`、孔底标高→`bottom_elev`…），桩列强别名优先于「序号」弱别名；规则引擎 `is_row_consumable` 与 DQ 质检不再对 Excel 行盲读
- **P7 表头扫描窗口**：20 行 → 100 行，表头靠后不再整表归零；未命中输出 stderr 告警（仅对疑似桩表 sheet）
- **P2 单位子行不拼「·m」**：双行表头子行为纯单位（m/mm/%/时分…）时列名保持主名，`实长·m` → `实长`
- **P6 数字日期转换**：Excel 日期序列号（如 46000）与 date/datetime 单元格统一转 `YYYY-MM-DD`
- **P10 质检误报修复**：`DataQualityChecker.check_column_shift._is_num` 由 `isinstance(int/float)` 改为宽松 float 判定（底座行值为字符串，原逻辑对 Excel/docx/OCR 全链路百分百误报"非数值"）；缺失值（None/空串）跳过；数学链改 `_to_float` 防 str-str 异常。修后 CFG 真实文件误报 3711→2 条，且 2 条为真题（「筑业软件」水印乱码入数据列）
- **回归锁定**：新增 `scripts/test_xlsx_docx_chain.py`（10 条：截断/行定位/列对齐/单位列/日期序列号/表头窗口/误报与捕获/docx row_index）注册进 `run_all_tests.py`；run_all_tests 项目版+安装版 14/14 全绿，H-7 干净数据零误报无倒退；四文件哈希三端一致

## v10.0（2026-08-25）

**资料员工作台（Web Workbench）——九页合一，一次加载、模块共享**

- **九页合一**：合并原来 9 个零散的审核 HTML 入口为单一工作台外壳，hash 路由 + 动态 import 按需加载；一次性加载 `index.json`，`_index` 内存共享，避免跨页重复读取
- **七个模块**：
  1. 项目总览（文档统计 + 进度总况）
  2. 数据核对（内嵌 data-editor，逐条核对 OCR 结果）
  3. 资料进度看板（8 节点轴「开检隐分竣交档」+ SortableJS 拖拽流转，localStorage 覆盖层落盘）
  4. 台账三本（检验批/隐蔽/混凝土等台账管理 + 计数）
  5. 数据概览导出（SheetJS/xlsx）
  6. 整改销号（问题登记→销号闭环循环）
  7. 规则与反馈（内嵌 iframe 加载 8765 规则面板 + 存活探测降级提示）
- **技术栈**：Vite + SortableJS + SheetJS/xlsx + ECharts + IndexedDB
- **数据层**：IndexedDB 存 FileSystemDirectoryHandle 实现「一键恢复上次项目」；写入用原子写 + 自动备份（备份到 `backups/`），不迁 SQLite
- **双模加载**：HTTP fetch（部署）/ FileSystem Access API（本地文件系统）
- **一键启动** `启动工作台.bat`：同时拉起规则 API(:8765) + 前端静态服务(:8909) + 浏览器；纯 ASCII 编码落盘，避免 cmd 代码页乱码
- **规则合并**：规则管理内嵌进工作台「规则与反馈」模块，替代旧 `rule-manager.bat` 单独入口；探测到 8765 未启动时降级提示「重新检测」
- **测试接入**：新增 `scripts/test_workbench.py`（工作台结构断言：依赖/构建/manifest/数据层/外壳/路由）并注册进 `run_all_tests.py`；`verify_plan_v2.py` 新增「工作台 v10：部署管线接入」11 项；templates 清单登记 dist 构建产物
- **移植性修复**：`verify_plan_v2.py` 安装副本判定由 `.trae-cn` 硬编码改为按路径是否含 `\.trae\skills\` 判定，修复 WorkBuddy 平台误报失败

## v9.10（2026-08-24）

**规范知识库总目录 + 按书名/专业快速检索（D）**

- **机器生成目录**：新增 `build_regulation_catalog.py`，扫描 `sources_clean`(257部) + `clause_index` + 审核锚定清单，一键生成：
  - `data/regulations/catalog_index.json`（机读索引，含每条规范的 编号/名称/年份/类别/专业/条款数/是否锚定/引用粒度）
  - `references/specification-catalog.md`（人读总目录，按 MH-T/MH/AC/AP/CCAR/IB/GB/法律法规 分区，可跳转），永不手工维护
- **按名/专业检索**：`lookup_source.py` 新增 `catalog_lookup()`，写错规范号、只记得书名（如"高填方"）或专业名（如"助航"）时也能定位原文；mtime 缓存机制同条款索引，不拖慢审核
- **引用粒度三档**（清晰回应"不编造条款号"的顾虑）：`X.X.X`=有点分条款可逐字反查（67部）；`第X条`=条文式法规律条；`全文/章节`=设备/管理规定无编号。审核照样全量对照、不符就指出——能引到什么粒度就引什么，不硬凑、不遗漏
- **防倒退测试**：`test_clause_trace.py` 新增 `test_catalog_consistency`（sources_clean↔clause_index 一一对应、catalog 全覆盖、锚定规范标 anchored=true）+ `test_catalog_lookup_by_name`。run_all_tests 8/8 全绿，双端同步完成

## v9.9（2026-08-24）

**其余四专业专项清单条款精细化（空管/助航/弱电/供油）**

- **空管工程 ATC_CHECKLIST（21 条）**：锚定 MH/T 5078.3（空管资料管理规程）。导航（ILS/VOR/DME/NDB/GBAS）、监视（PSR/SSR/SMR/ADS-B）、通信（VHF/内话/语音交换/传输）、气象（AWOS/风廓线等）、自动化、工艺管线、飞行校验七大分项全部落到 5.0.5（表格填写）等具体条款；MH/T 4006.x 系列技术规范本地无全文，**降级到 criteria 说明**，不编造条款号
- **目视助航 VISUAL_AIDS_CHECKLIST（18 条）**：锚定 MH/T 5012-2022（助航设施施工）。电缆保护管/井/接地/灯具/标记牌/隔离变/PAPI/风向标/电缆线路/控制柜/各回路调试/目视助航标志 18 项落到 3.1.1~16.2.5 具体条款；GB 50168/50169/50150、AC-137、MH 5001 本地无全文**降级到 criteria**
- **弱电工程 WEAK_ELECTRICITY_CHECKLIST（26 条）**：有独立检测规范的子系统锚定各自条款（信息集成 MH/T 5039、航显 MH/T 5032、广播 MH/T 5038、时钟 MH/T 5040、离港 MH/T 5068）；无独立规范的（安防/布线/机房/网络）锚定资料规程 MH/T 5078.5 第5.0.6条，GB 50312/50174、MH/T 5017 降级
- **供油工程 FUEL_SUPPLY_CHECKLIST（25 条）**：锚定 MH 5034-2017。油罐/管道/机坪加油管线/设备/电气仪表/消防/油气回收/土建 25 项落到 3.0.14~12.5.1 具体条款；GB 50341/50128/50057/50169、NB/T 47013、API/IP 1584 降级。**修复一处分部幻觉**：火灾报警系统原引 8.1.1 在本规范不存在，改落 8.1.2（消防系统调试/验收）
- **接线 + 溯源**：`get_checklist_for_professional` 五个专业全部接入专项清单；`test_clause_trace.py` 收集范围扩展到四专业清单，**94 条条款引用全部可在总索引反查命中，零幻觉**
- **分部分项对齐**：五专业清单 code 与 `SUBDIVISION_HIERARCHY` 逐项核对。空管 22/助航 18/供油 27 已对齐；**修复弱电 6 处 code 错位**——信息集成拆为 4 项（补回「接口开发与联调」）、航显按树 3 项重排、公共广播统一命名，弱电由 26 项对齐到树的 27 项。**场道由旧 `A-2.x.x` 格式整体重写为树 `AF-xx` 格式**：16 项扩展为 21 项并对齐六个分部（土方/基层/面层/排水/附属/测量监测），新增边坡、底基层、隔离层/防冻层、道面刻槽、胀缝填缝、盲沟、巡场路围界、施工放样等分项，全部按真实条款号落 spec（MH 5007/5006/5014/5035），无幻觉；`test_checklist_vs_hierarchy` 校验范围扩到五专业
- **回归验证**：run_all_tests 9/9 全绿，条款溯源扩至 102 条全可溯源

## v9.8（2026-08-21）

**规范库清洗 + 审核依据精确到具体条款 + 检索提速**

- **规范库净化（A1）**：新增全量清洗脚本，257 篇规范 markdown 全部产出到 `data/regulations/sources_clean/`（67 篇乱码规范清洗 + 190 篇干净文件复制）。清洗把 PDF 转置的全角编号/乱码符归整为结构化「章-节-条」：`５􀆰１􀆰２`→`5.0.2`、`ꎬ`→`，`、`U+1001BA`→`。`，并识别章节（5078.1 识别出恰好 8 章与规范一致）。修复贪捕获 `CLAUSE_RE` 命中后 `continue` 跳过 `i+=1` 的死循环 bug。**幂等验证通过**（67 篇两遍清洗哈希一致），输出仅动 `sources_clean/`，原始 `sources/` 一个不动
- **全局条款总索引（A2）**：257 文件 → `clause_index/clause_index.json`，16740 条款条目，按「规范→条款号→原文」分层，供 lookup 与溯源反查
- **审核规则精确到具体条款（A3）**：通用清单 18 条 spec 从「第X章」精确到具体条款号（如 `MH/T 5078.1 第5.0.4条`），逐条对照原文语义映射，全部可溯源。**发现并修复原配置错误**：G-1.3.4 原本写「第9章」，而 5078.1 只有 8 章（无第9章），已改落到真实存在的 6.2.7（组卷）
- **场道专项 18 条精确到具体条款**：AIRFIELD_CHECKLIST 从「MH/T 5078.2 + MH 5007」式规范组合改为精确条款引用，主依据 ROC 资料管理规程（MH/T 5078.2）、辅质量/技术规范（MH 5007/MH 5006/MH/T 5035/MH/T 5014）；土石方（A-2.1）、基层（A-2.2）、面层（A-2.3）、排水（A-2.4）、测量监测（A-2.6）全部落到具体条例。**缺失规范等效替换**：库外 JGJ 79（建筑地基处理）→ MH 5007 第4.4.5/4.4.9条，库外 GB 50026（工程测量）→ MH/T 5014 第3.2.2/3.2.3条；**库内规范名归一**：M 5004 → MH 5007 第6.2.2条 + MH 5006 第18.0.8条（水泥混凝土面层）。26 条场道条款引用经 `test_clause_trace.py` 反查总索引全部命中，零幻觉
- **条款溯源测试（A4）**：新增 `test_clause_trace.py` 并注册进 `run_all_tests.py` 结构验证段，所有 spec 引用的条款号必须在总索引反查命中，永久防幻觉；另含 B 缓存生效 + mtime 失效重载测试
- **lookup_source 切读清洗版 + 索引缓存提速（A5+B）**：`resolve_vault_dir` 优先读 `sources_clean`（条款以 `**5.0.4**　正文` 展开，可逐字引用），GENERAL 规则走 references 命中附带精确条款号；新增条款索引内存缓存（mtime 失效），带「第X条」的查询直接从内存取原文，跳过逐篇读大文件
- **回归验证**：41 套件全绿、verify_lookup_source 38/38（含 5078.2/5078.3/5078.6 分部命中）、新增条款溯源测试全绿

## v9.7.1（2026-08-20）

**视觉复核任务行级/表级分流（独立复核 R-1/R-2 高危处置）**

- **R-1（高）行级数值存疑项不再表级化**：`suspects_from_pending` 此前无字段类型过滤，带桩号的行级数值项（实长/电流/充盈系数等，各行本不相同）也被生成为 `scope=table` 任务，merge 整表覆写会把同行正确值冲掉（独立复核实证：表内三行实长 20.0/2O.0/19.8，仅第 2 行存疑，AI 回 20.0 后三行全变 20.0）。v9.7.1 按表级字段白名单（`_TABLE_SCOPE_FIELDS`：施工部位/施工日期）分流：带 pile_no 的项生成 `scope=row` 任务（按表+桩号定位全局行号，merge 只写该行）；无 pile_no 且不在白名单的字段跳过（无法安全落库，保守不生成）
- **R-2（中）「整行」项过滤**：`field=整行` 的 pending 项（表头不可靠产）不进视觉复核——读图无法单值作答，且经字段映射会新建中文键错位落库；留给 Chat-Verify 整行核对通道
- **field_label 中文反查**：pending 行级项的 field 是英文键（build_foundation `_DOCX_NUMERIC_FIELDS` 产出），新增 `_ROW_KEY_TO_CN` 反向映射，任务清单的 field_label 统一显示中文（实长/充盈系数/桩径等），读图问答提示更友好
- **回归测试**：H-8 组新增 3 条（行级项 scope=row + merge 只写该行不污染同行 /「整行」项跳过 / 行级字段无桩号跳过），套件 41/41 全绿，run_all_tests 8/8 通过
- **DOC-002 实测**：71 任务 = 37 行级 + 34 表级，整行 0 残留，71 裁图全部成功，field_label 全中文显示
- **5078 系列规范库补齐**：MH/T 5078.2~5078.6 正文（场道/空管/助航/弱电/供油）由 Obsidian 库 `raw/pdfs` 的 PDF 转 `.md` 补入 `data/regulations/sources`，离线（不连 Obsidian）审核可完整引用 5078 各分部
- **多部分规范命中错定修复（review-gate 独立复核 R-1/R-2 处置）**：`lookup_source._spec_core` 原用 `.split(".")[0]` 把 `5078.2` 截断成 `5078`，`_glob_vault` 按核心号 glob 排序命中最前文件 → 5078.2~6 全部错定到 5078.1。修复：`_spec_core` 保留分部号；新增 `_stem_has_exact_spec` 对文件名规范号数字段作全等校验（杜绝 `5078→5078.1`/`5078.2→5078.20` 子串歧义）；带分部查询未命中对应分部文件时直接回落 missing/retriever，**绝不静默回退错配到其他分部**（实测 5078.9 不再落到 5078.1~6 任一）
- **verify_lookup_source 新增 2c 分布式断言**：5078.2/5078.3/5078.6 经 `references_dir=None` 隔离，验证 obsidian 层 glob 各自命中对应分部文件；38 断言全绿（原 35 + 新增 3）

## v9.7（2026-08-20）

**AI 视觉复核链贯通（H-8 隐患销号）+ 协议平台无关化**

- **H-8 视觉复核断链修复**：第二类资料（扫描转化电子文档）的两套存疑清单（confusion 易混字 + pending 表级乱码/缺失）此前从未接入 `verify_fields.py` 复核器；v9.7 自动合流生成统一复核任务，乱码项重新有 AI 读图自证通道
- **docx 内嵌图提取与裁图**：WPS 扫描件转 docx 的每页即一张内嵌图，`_extract_docx_media()` 按 document.xml 引用顺序解压提取（表 t ↔ 第 t+1 张图），裁图支持 docx 来源，结果缓存避免重复解压
- **merge 落库三修复**：①中文字段（桩号/部位/日期等）经 FIELD_ALIAS 映射英文行键，不再新建中文键错位落库；②定位以 verify_tasks.json 按 task_id 回查为准（row/field/scope 权威来源），不依赖 AI 结果手抄；③`structured_rows` 与 `rows` 双份同步写（H-6 分叉活体修复），表级任务（scope=table）按 table 匹配写整表
- **build_foundation 自动接线**：`nature=扫描转化电子文档` 建底座时自动调用 prepare 产出 `verify_output/`（任务清单+裁图），index.json 登记 `verify_tasks_file` 字段；失败不阻塞底座构建
- **视觉复核协议平台无关化（SKILL.md 步骤 4.5）**：任务清单（JSON）+ 裁图（PNG）+ 结果（JSON）三文件协议，TRAE / WorkBuddy / CodeBuddy 等任何具备读图能力的智能体均可执行；结果只写 task_id+verified_value+confidence(+note)；high/medium 落库、low 留给 Chat-Verify；无视觉能力平台自动降级人工核对，存疑项不丢失；**不豁免 G-1.9/G-2 闸门**
- **vision_providers 新增腾讯混元**：`HUNYUAN_API_KEY`，OpenAI 兼容接口
- **rule_engine 字段别名扩充**：FIELD_ALIAS_MAP 新增 施工部位/部位→loc、施工日期/日期→date_raw、备注/说明→remark 等，规则中文别名与行键全对齐
- **回归测试**：`test_regression_hazards.py` 新增 H-8 组 8 条（docx 媒体顺序提取/裁图/pending 合流映射/任务清单生成/表级整表双份写/中文字段映射/task_id 回查定位/干净数据零误报），套件 38/38 全绿，run_all_tests 8/8 通过
- **独立复核处置（当轮）**：修复 confusion 行级任务页码恒 1 的系统性裁错页（docx 源按行所在表号推导页码，表 t ↔ 第 t+1 张图）；A3 触发条件补 nature=扫描转化电子文档 校验；_FIELD_ALIAS 改为复用 rule_engine.FIELD_ALIAS_MAP 单一真相源；merge 对同一 list 引用去重防双写留痕；confusion_result 预置空结构防 unsupported 路径 NameError；SKILL.md provider 举例修正（deepseek/moonshot → qwen/glm/hunyuan/kimi/doubao/baidu/openai）；verify_plan_v2 版本检查改为从 SKILL.md 标题提取做一致性比对（升版本不再改脚本）、安装副本跳过工作区级 bat 检查

## v9.5（2026-08-19）

- **Chat-Verify 聊天式人工核对**：新增 `scripts/chat_verify_apply.py`，支持 list/apply/confirm/status 四个子命令；AI 对话框内按表分组抛转 OCR 存疑项，用户短答修正后落库 corrections.json；支持中文标签/英文字段名、表级/行级修正、「整行」accept 销项；全部核对完 + 用户确认 → human_verified=true 进阶段 3
- **审核流水线与入口重构**：审核流水线统一为**步骤 1~7 线性编号**（每次 AI 回复顶部进度条）；前置信息确认（6 项）表迁移至共享基础设施，审核流水线与规则管理两场景共用；强制闸门表新增「用户动作」「AI 恢复条件」两列，人工确认节点清晰；规则管理场景改为**步骤化工作流**（第一步规则浏览→第二步规则操作→第三/四步反馈闭环🚧规划中）
- **SKILL.md 阶段 2 重构**：新增通道 A（聊天核对，手机可用）+ 通道 B（数据编辑器后备）；更新 G-1.9/G-2 闸门措辞；路由表补聊天核对入口
- **docx 表格解析下沉**：`build_foundation.py` 新增 `parse_docx_table_sheets()` 直接解析 docx 表格结构（替代原项目根外部脚本 enrich_docx.py），并产出结构化存疑清单供 Chat-Verify 后续消费
- **数据修复**：None 污染→空字符串；pages 失真（docx 页码=表格数）；DOC-002 路径归位到 `碎石桩施工记录/`；分类确认（file_classification_confirmed=true）；is_handwritten 去 null→false
- **推荐值规则独立化**：新建 `rules/inference_rules.json`，推荐值规则从 `data_quality_check.py` 硬编码改为配置文件驱动，支持 7 条数值链规则（桩基 5 条 + 碎石桩时长 1 条 + 垫层厚度 1 条），schema_version 升至 1.1；置信度 < 0.5 也输出并打颜色标记；调用方 `cmd_list`/`data-editor` 附「建议值 + 置信度 + 来源」
- **文本建议值（施工部位/日期补齐）**：`data_quality_check.py` 新增 `type:"text"` 规则，施工部位→同表众数、施工日期→补齐；仅对不匹配合法格式（legal_pattern）的乱码值触发推断，对齐 pending_verification 判定；文本建议值带 `suggested_only` 标记，**只建议不入库**，用户 `accept_recommended` 采纳才落库；乱码项 `cmd_list` 附页码定位
- **跨表防污染安全锁**：新增 `_row_table`/`_same_table`，候选值、邻行检索、日期补齐严格限定同表（按 `row['table']`），绝不跨表/跨页抓邻居当建议值；同表部位值 ≥2 种时禁用众数、退化为邻行推断；跨月施工日期置信度降低
- **仅刷新建议值命令（`cmd_refresh`）**：只重算并写回 `inferred` 字段，保留 corrections/存疑清单/human_verified 等核对进度；新增 test_inferred_values.py 文本规则用例 + 「建议值不进审核判定」锁定用例 + 跨表防污染用例，旧 7 条数值链回归通过
- **手写体混合型文档优化**：新增 `ocr_image.py::crop_and_verify()` 对低置信字段裁剪+AI 读图复核，按置信度分级决策，避免全量读图浪费 token
- **同步脚本清理**：删除 12 个旧 .ps1 同步脚本，保留唯一同步入口 `同步内部路由到安装版.bat`，加文件头注释说明用法
- **增量保护机制**：`build_foundation.py` 增量模式下保留已有文档的 `human_verified`/`corrected_file`/`audit_status`，新增 `incremental_added_at` 和 `incremental_from` 标记
- **统一测试体系**：新建 `scripts/run_all_tests.py`（一键入口）、`test_data_foundation.py`（数据底座测试）、`test_inferred_values.py`（推荐值测试）
- **版本号统一**：代码注释 v9.6 回归 v9.5，各文档版本号一致（SKILL/README/PROJECT_SPEC/CHANGELOG）

## v9.4（2026-08-09）

- **表格式样导入导出**：`import_template.py` 支持从 Excel/Word 电子表导入表格式样（前缀区+数字区 JSON 模板），解决"新表类型如何确认列定义"的落地问题
- **苹果浅色界面优化**：`data-editor.html` 去掉大片蓝色背景，改用苹果浅色风格
- **版本统一**：SKILL.md / README / PROJECT_SPEC 三处版本号统一至 v9.4，CHANGELOG 补齐变更记录

## v9.2（2026-08-09）

- **错位率阈值收紧**：`data_quality_check.py` 列错位高风险阈值由 30% 收紧至 5%（≥5% 强制 needs_review）
- **AGENT 复核放开页限**：页数不限，仅 token 提醒
- **data-editor.html 文本行可编辑**：增加文本行编辑功能
- **内容感知分类**：OCR 文本命中桩基关键词≥2 自动切桩基解析
- **OCR 引擎统一**：彻底删除旧包 rapidocr_onnxruntime（PP-OCRv3），统一新版 rapidocr 3.9.2（PP-OCRv6 Small）
- **表格识别定稿**：几何重建为主，RapidTable 仅交叉校验

## v9.1（2026-08-08）

- **表格识别重构**：确立"几何重建为主导"——`table_struct.build_rows_from_items()` 用 OCR items 的 bbox 做几何网格列对齐（值格式锚点+表头消歧+六类校验），取代旧 TableStructureRec 双环境 subprocess
- **RapidTable(SLANetPlus) 仅作候选网格交叉校验**，不主导定列（碎石桩无线表 SLANetPlus 识别效果差，未采用）
- **方式二对话式核对新增四条强制纪律**：默认批量 / 条件补扫 / 落盘强制 / 推断标记+禁子代理

## v9.0（2026-08-07）

- **本地 OCR 主力从 paddleocr 替换为 rapidocr（RapidOCR）**：跨平台轻量稳定、无需 PaddlePaddle
- **手写体前置路由**：手写资料直接走 VLM，印刷资料走本地 OCR
- **VLM 手写体专用 Prompt 优化**
- 配置开关：`FORCE_USE_PADDLE` / `DISABLE_HANDWRITING_ROUTE`
- 关键节点日志：路由判定/引擎选择/识别结果

## v8.10（2026-08-06）

- **数据验证闸门**：`table_struct.validate_rows()` 六类校验（类型/格式/范围/完整性/一致性/跨字段数学链）落地于数据底座写入前
- **表头消歧定列**：列角色推断改为值格式锚点为主 + 表头文字消歧/补空缺
- **数据验证闭环（data-editor 层3）**：有 issues 行整行标红 + 行首⚠ + 内联原因标签 → 问题视图 → 精准跳转 → 阻止确认

## v8.9（2026-08-06）

- 模板时间列锚点识别（sink_time/pull_time 按出现顺序钉死为锚点列）
- 数据验证闸门 validate_rows 六类校验 + 数据验证闭环（data-editor 层3）
- 审核阶段列级兜底校验（`data_quality_check.py::check_column_shift`）

## v8.8（2026-08-05）

- PaddleOCR 3.x + PP-OCRv6 Tiny + ONNX Runtime
- AGENT Vision 复核放开页数限制（不限页数，仅提醒 token 消耗）

## v8.7（2026-08-05）

- OCR 全流程加固：表头检测优化 + 跨页表头继承 + 内容感知分类 + 分词修复
- OCR 引擎四选一前置选项（auto/vision/paddle/agent）
- 模板统一存放数据底座目录，中文命名
- data-editor 自动加载数据底座；launcher 三步指引 UI
- rule-manager.bat 三级路径自动定位 skill 目录
- PaddleOCR dpi=200 渲染修复，retry 行数≥首次70%才覆盖

## v8.6（2026-08-05）

- 嵌入数据入口页：launcher.html 从 fetch() 改为 `__PROJECT_DATA__` 数据嵌入，解决 file:// CORS 拦截
- 增量 I-4 简化为只更新入口页；步骤 7 拆分 7a/7b

## v8.5（2026-08-04）

- 新增步骤 0.5 数据底座检测 + I-1~I-6 增量路径
- 解决增量审核时重复弹窗、重复 OCR、老问题重复报告、模板漏拷的问题

## v8.4（2026-08-04）

- 新增 G-1.9 硬停闸门 + 扫描件待核实清单
- 阶段 1 完成 = AI 必须停止输出等用户"核对完成"

## v8.3（2026-08-04）

- 原生模式新增步骤 7 复制 Web 模板 + G-1.5 闸门
- 解决建了数据底座但不复制模板的问题

## v8.2（2026-08-04）

- 顶部新增强制闸门节（G-0/G-1/G-2 三级硬闸门）
- 原生模式阶段 1 机械化清单（`references/native-mode-stage1-checklist.md`）
- 常见错误对照表
- **触发需求**：v8.1 部署后 AI 仍跳过数据底座直接输出结论，根因是 SKILL.md 将原生模式埋在文档第 813 行，低智商模型读到第 261 行就开始执行

## v8.1（2026-08-04）

- **双模式运行架构**：Python 可用 → 引擎模式（四阶段流水线）；Python 不可用 → 原生模式（三阶段流水线）
- **原生模式三阶段流水线**：AI 原生数据提取 → 人工核对 → AI 规则审核+报告生成
- **数据兼容性**：原生模式与引擎模式 JSON 完全兼容，支持双向迁移
- **低智商模型适配**：93 条规则简化为核心检查清单
- **触发需求**：WorkBuddy 实测中因无 Python 环境跳过数据底座直接出结果

## v8.0（2026-08-04）

- PaddleOCR 从"可选"升级为"强烈推荐"
- AGENT Vision 从"最终兜底"降级为"复核工具"
- 安装引导增加 token 消耗警告
- **触发需求**：WorkBuddy 实测中无 PaddleOCR 时 AGENT Vision 只抽样识别 6 页（49 页扫描件），大量消耗 token 且遗漏 43 页异常数据

## v7.0（2026-07-31）

- 三层 JSON 数据底座（structured_rows + full_text + page_map）
- 差异化提取（非扫描 PDF 直接文本提取，Excel 仅记元数据）
- 文档关联图谱（link_graph.json）
- 签字一致性检测（pHash + SSIM 双指标）
- data-editor 三栏升级（文档树 + 表格/原文/图纸三 Tab）
- human_verified 分层闸门（非扫描件自动通过，扫描件强制人工核对）
- 图纸截图（含图 PDF 自动截图存 `_images/`）

## v6.0（2026-07-30）

- **四阶段流水线**：建数据底座 → 人工核对 → 正式审核 → 生成报告
- **数据底座**（build_foundation.py）：按项目维度建立结构化中间数据
- **Web 数据编辑器**（data-editor.html）：纯 HTML，左图右表对照，零对话 token
- **项目总览仪表盘**（project-dashboard.html）
- **增量更新**：基于 SHA256 哈希对比
- **断档检测**：桩号/日期/编号连续性检查
- **三级粒度多 Agent 并行**：`--split-by professional|sub|item`
- **多 Agent 任务包机制**：`--dry-run` 生成任务包，`--task-id` 执行
- **run_audit.py 新增 build/review/report 子命令**
- **SVG 图表生成**：审核报告含环形图 + 水平条形图
- **触发需求**：v5.0 单文件 9 步流程在大项目场景下出现上下文溢出、人工核对无处落地、重复 OCR 浪费

## v5.0 及之前

- v5.0：API-First 策略 + 7 家 Vision API
- v4.1：PaddleOCR 单层主引擎 + Vision API 兜底
- v1.9：知识分区红线 + 三级输出格式 + 多Agent并行 + 标准模板
- v1.8：三层工作流重组
- v1.7：前置信息收集 + OCR 存疑核实 + 统一 HTML 交付
- v1.5：五专业审核全覆盖 + Obsidian 知识库集成
- v1.0~v1.4：20 条铁律体系建立