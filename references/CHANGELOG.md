# 更新日志

> 本文件记录 civil-aviation-doc-audit Skill 各版本的核心变更。SKILL.md 正文仅保留最新版本概要。

## v9.5（2026-08-11）

- **推荐值规则独立化**：新建 `rules/inference_rules.json`，推荐值规则从 `data_quality_check.py` 硬编码改为配置文件驱动，支持 7 条规则（桩基 5 条 + 碎石桩时长 1 条 + 垫层厚度 1 条），置信度 < 0.5 也输出并标记颜色
- **手写体混合型文档优化**：新增 `ocr_image.py::crop_and_verify()` 对低置信字段裁剪+AI 读图复核，按置信度分级决策，避免全量读图浪费 token
- **同步脚本清理**：删除 12 个旧 .ps1 同步脚本，保留唯一同步入口 `同步内部路由到安装版.bat`，加文件头注释说明用法
- **增量保护机制**：`build_foundation.py` 增量模式下保留已有文档的 `human_verified`/`corrected_file`/`audit_status`，新增 `incremental_added_at` 和 `incremental_from` 标记
- **统一测试体系**：新建 `scripts/run_all_tests.py`（一键入口）、`test_data_foundation.py`（数据底座测试）、`test_inferred_values.py`（推荐值测试）
- **版本号统一**：各文档版本号统一至 v9.5

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