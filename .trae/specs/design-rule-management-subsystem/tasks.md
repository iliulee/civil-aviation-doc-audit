# Tasks — 规则管理子系统

> 本任务清单对应 spec.md 第 9 节实施路径，按 Phase A → E 顺序执行。
> 每条任务设计为可独立验证的工作单元，同一 Phase 内无依赖的任务可并行。

---

## Phase A：规则重构与形式化（基础，必须先完成）

- [ ] **A-1**: 设计并固化规则 JSON Schema
  - [ ] A-1.1: 编写 `rules/schema/rule-schema.json`（JSON Schema 定义文件，覆盖 L1/L2/L3 + 跨单位规则）
  - [ ] A-1.2: 编写 `rules/schema/registry-schema.json`（注册表 Schema）
  - [ ] A-1.3: 编写 `scripts/rule_schema_validator.py` 校验工具
  - 验证：用 spec.md 第 5.1/5.2 节示例 JSON 通过校验

- [ ] **A-2**: 编写规则引擎核心 `scripts/rule_engine.py`
  - [ ] A-2.1: 实现 `RuleLoader` — 从 `rules/` 加载 active 规则到内存
  - [ ] A-2.2: 实现 `RuleMatcher` — 按 doc_type/professional/scope 匹配规则
  - [ ] A-2.3: 实现 `ExpressionEvaluator` — 支持 jinja-expr 与 python_eval 表达式
  - [ ] A-2.4: 实现 `SingleDocChecker` — 单资料规则执行器
  - [ ] A-2.5: 实现 `CrossDocChecker` — 跨资料规则执行器
  - [ ] A-2.6: 实现 `CrossUnitChecker` — 跨单位规则执行器（含 join 逻辑）
  - [ ] A-2.7: 实现 `ViolationReporter` — 输出标准化违规发现
  - 验证：单元测试覆盖三类 Checker，样例数据通过

- [ ] **A-3**: 现有规则迁移到结构化 JSON
  - [ ] A-3.1: 迁移 `references/logic-conflict-patterns.md` 9.1~9.9（约 40 条）到 `rules/L2-logic/`
  - [ ] A-3.2: 迁移 `references/logic-conflict-patterns.md` 9.10（17 条）到 `rules/cross-unit/`
  - [ ] A-3.3: 迁移 `references/data-quality-patterns.md` DQ-REPEAT/JUMP/ALTER 到 `rules/L3-business/`
  - [ ] A-3.4: 迁移 `references/data-quality-patterns.md` DQ-SELF（自洽校验）到 `rules/L2-logic/`
  - [ ] A-3.5: 从 SKILL.md 铁律 R-01/R-03/R-04/R-05/R-06/R-07/R-08/R-10/R-11/R-15/R-16/R-17/R-18/R-19/R-02/R-20 迁移到 `rules/L1-iron/`（共 16 条）
  - [ ] A-3.6: **修正层级错位**：R-12 高程自洽、R-13 缺合计行、R-14 多参数联检 → `rules/L2-logic/`
  - 验证：迁移后规则总数 ≥ 73 条（16 L1 + 40 L2 + 17 跨单位），registry.json 计数一致

- [x] **A-4**: 生成 `rules/registry.json` 全量注册表
  - [x] A-4.1: 编写 `scripts/rule_registry_builder.py` 扫描 `rules/` 生成注册表
  - [x] A-4.2: 包含 by_level / by_scope / by_status 统计
  - 验证：注册表统计数与文件实际数一致（total_rules=91，与磁盘 91 个规则文件一致）

- [x] **A-5**: 改造 `scripts/review_audit.py` 接入规则引擎
  - [x] A-5.1: 移除现有硬编码规则调用逻辑
  - [x] A-5.2: 改为通过 `RuleLoader` 加载规则
  - [x] A-5.3: 审核结果中输出 `rule_id`、`level`、`scope` 字段
  - 验证：现有测试项目审核结果不回归，且每条发现都关联 rule_id

---

## Phase B：规则管理界面

- [x] **B-1**: 开发 `scripts/rule_admin.py` 管理 API
  - [x] B-1.1: 实现 GET /api/rules（支持 level/scope/status/q 组合筛选）
  - [x] B-1.2: 实现 GET /api/rules/{id}（详情含 changelog）
  - [x] B-1.3: 实现 POST /api/rules（创建草稿）
  - [x] B-1.4: 实现 PUT /api/rules/{id}（更新并自动写 changelog）
  - [x] B-1.5: 实现 POST /api/rules/{id}/transition（状态流转）
  - [x] B-1.6: 实现 POST /api/rules/{id}/confirm（协同确认）
  - [x] B-1.7: 实现 GET /api/rules/{id}/stats（命中率/误报率）
  - [x] B-1.8: 实现 POST /api/rules/{id}/test（沙箱测试）
  - [x] B-1.9: 实现 DELETE /api/rules/{id}（仅 draft 可删）
  - 验证：每个端点通过 curl/Postman 测试

- [x] **B-2**: 开发 `templates/rule-manager.html` 规则管理面板
  - [x] B-2.1: 顶部多维度筛选栏（层级/作用域/状态/来源/专业/关键词）
  - [x] B-2.2: 规则列表表格（ID/名称/层级/作用域/状态/版本/命中率）
  - [x] B-2.3: 规则详情抽屉（含 changelog 时间线）
  - [x] B-2.4: 启用/停用/删除操作按钮
  - [x] B-2.5: 跨单位规则"协同确认"待办区域
  - [x] B-2.6: 统计仪表盘（按层级/状态分布的 SVG 图）
  - 验证：浏览器打开可筛选、查看、启停规则

- [x] **B-3**: 开发可视化规则编辑器（嵌入 rule-manager.html）
  - [x] B-3.1: 分步引导（层级 → 作用域 → 资料类型 → 字段 → 关系 → 比较对象 → 容差 → 错误模板）
  - [x] B-3.2: 字段字典维护（按资料类型加载可选字段）
  - [x] B-3.3: 关系运算符下拉（=、≠、>、<、≥、≤、within、between）
  - [x] B-3.4: 实时预览生成的 JSON
  - [x] B-3.5: 跨单位规则额外配置 alignment（双方角色/对齐键/资料类型）
  - [x] B-3.6: 测试沙箱（用样例数据验证规则）
  - 验证：非技术用户可无代码创建一条可执行规则

- [x] **B-4**: 实现规则生命周期流转
  - [x] B-4.1: 状态机定义（draft→testing→incubating→active / deprecated）
  - [x] B-4.2: 测试期自动统计误报率
  - [x] B-4.3: 测试期通过（误报率<10%，3 个项目）自动进入 incubating
  - [x] B-4.4: 管理员审批通过后可选"项目级"或"全局"生效
  - 验证：完整跑通一条规则从草稿到全局生效的生命周期

- [x] **B-5**: 实现跨单位规则协同确认机制
  - [x] B-5.1: pending_confirmation 状态与待办列表
  - [x] B-5.2: 确认/驳回 API 与 UI
  - [x] B-5.3: 管理员强制确认权限（须填理由，写入 changelog）
  - 验证：跨单位规则无确认时不生效，确认后变为 active

---

## Phase C：反馈闭环

- [x] **C-1**: 设计反馈数据结构
  - [x] C-1.1: 编写 `feedbacks/schema/feedback-schema.json`
  - [x] C-1.2: 字段覆盖 spec.md 第 7.1 节定义
  - 验证：Schema 通过校验

- [x] **C-2**: 在审核报告中嵌入反馈收集组件
  - [x] C-2.1: 开发 `templates/feedback-collector.html`（漏审/误报按钮 + 表单）
  - [x] C-2.2: 集成到现有审核报告 HTML 模板
  - [x] C-2.3: 自动捕获上下文（审核 ID/资料快照/命中规则/时间）
  - [x] C-2.4: 反馈写入 `feedbacks/` 目录
  - 验证：在浏览器中点击"漏审反馈"成功创建反馈文件

- [x] **C-3**: 开发 `scripts/feedback_analyzer.py` LLM 分析管道
  - [x] C-3.1: 加载 status=new 的反馈
  - [x] C-3.2: 向量化（embedding：反馈摘要 + 上下文）
  - [x] C-3.3: 聚类（DBSCAN，eps=0.3，min_samples=3）
  - [x] C-3.4: 对每类调用 LLM 提取共性模式
  - [x] C-3.5: 生成候选规则 JSON（status=incubating）写入 `rules/custom/incubator/`
  - [x] C-3.6: 更新反馈 status=analyzed, cluster_id
  - [x] C-3.7: 输出分析报告到 `rules/reflections/feedback-analysis-{日期}.md`
  - 验证：用 20 条样例反馈跑通完整管道，生成至少 1 条候选规则

- [x] **C-4**: 触发机制（手动 + 自动）
  - [x] C-4.1: 累积 20 条反馈自动触发
  - [x] C-4.2: 每周一次自动触发（与反思调度器联动）
  - [x] C-4.3: 手动触发 API（POST /api/feedbacks/analyze）
  - 验证：三种触发方式均正常工作

---

## Phase D：自成长机制

- [x] **D-1**: 开发 `scripts/rule_monitor.py` 规则效力监控
  - [x] D-1.1: 命中率统计（total_hits / total_reviews）
  - [x] D-1.2: 误报率统计（false_positive_count / total_hits）
  - [x] D-1.3: 最近命中时间追踪
  - [x] D-1.4: 低活跃标记（50 次审核命中率 < 5%）
  - [x] D-1.5: 自动降级（误报率 > 30%：L2→L3 或 L3→deprecated）
  - [x] D-1.6: L1 铁律豁免自动降级
  - [x] D-1.7: 自动降级操作写入 changelog
  - 验证：用模拟数据触发自动降级，L1 不被降级

- [x] **D-2**: 构建"审核记忆流"日志格式
  - [x] D-2.1: 定义 `audit_memory/` 事件日志 JSON 格式（审核 ID/时间/触发规则/命中/反馈）
  - [x] D-2.2: 改造 review_audit.py 写入审核记忆流
  - [x] D-2.3: 增量追加，按日期分文件
  - 验证：审核一次后能在 audit_memory/ 找到对应事件

- [x] **D-3**: 开发 `scripts/rule_reflector.py` 定时反思调度器
  - [x] D-3.1: 汇总本周审核事件/反馈/规则命中统计
  - [x] D-3.2: 调用 LLM 生成《规则优化建议报告》（新增/修改/停用/层级调整建议）
  - [x] D-3.3: 候选规则写入 `rules/custom/incubator/`
  - [x] D-3.4: 报告输出到 `rules/reflections/YYYY-MM-DD.md`
  - [x] D-3.5: 调度配置（默认每周日 02:00，可配置）
  - [x] D-3.6: 管理员手动触发接口
  - 验证：手动触发一次反思，生成报告与候选规则

- [x] **D-4**: 反思报告管理面板
  - [x] D-4.1: 规则管理面板新增"反思报告"标签页
  - [x] D-4.2: 历史报告列表
  - [x] D-4.3: 候选规则审核 UI（promote / reject）
  - 验证：可在面板中查看历史反思报告并处理候选规则

---

## Phase E：跨单位对照增强

- [x] **E-1**: 实现跨单位数据对齐视图组件
  - [x] E-1.1: 开发 `templates/alignment-view.html` 组件
  - [x] E-1.2: 左列监理方/右列施工方/中列差异值布局
  - [x] E-1.3: 差异行高亮，点击查看原始资料
  - [x] E-1.4: 缺失对齐键的告警展示
  - [x] E-1.5: 集成到审核报告 HTML 模板
  - 验证：用样例数据展示对齐视图，差异行正确高亮

- [x] **E-2**: 优化跨单位规则匹配性能
  - [x] E-2.1: 跨单位规则按对齐键建立索引
  - [x] E-2.2: 大数据量（>1000 行）下的分块处理
  - [x] E-2.3: 性能基准测试（目标：1000 桩位 join < 1 秒）
  - 验证：性能基准测试通过（1000 桩位 42.61 ms）

- [x] **E-3**: 完善协同确认 UX 流程
  - [x] E-3.1: 待确认规则突出显示
  - [x] E-3.2: 确认/驳回操作后通知发起方
  - [x] E-3.3: 管理员强制确认的理由输入与记录
  - 验证：跑通一次完整协同确认流程

---

## Phase F：文档与集成测试

- [ ] **F-1**: 更新 `SKILL.md`
  - [ ] F-1.1: 铁律章节重构为三层分级
  - [ ] F-1.2: 新增"规则管理子系统"章节
  - [ ] F-1.3: 更新触发语句（规则管理/反馈/反思）
  - 验证：SKILL.md 内容与实现一致

- [ ] **F-2**: 更新 `README.md`
  - [ ] F-2.1: 新增"规则管理子系统"章节
  - [ ] F-2.2: 更新目录结构（含 rules/ feedbacks/ audit_memory/）
  - [ ] F-2.3: 新增 API 端点说明
  - 验证：README 内容与实现一致

- [ ] **F-3**: 全链路集成测试
  - [ ] F-3.1: 现有测试项目跑通四阶段流水线（不回归）
  - [ ] F-3.2: 规则管理面板完整跑通（筛选/编辑/启停）
  - [ ] F-3.3: 反馈收集 → LLM 分析 → 候选规则生成链路
  - [ ] F-3.4: 反思调度器手动触发 → 报告生成
  - [ ] F-3.5: 跨单位规则完整流程（创建/确认/审核/对齐视图）
  - 验证：所有链路无回归，功能完整可用

---

# Task Dependencies

- **A 系列（A-1 → A-5）** 必须先完成，是其他所有 Phase 的基础
  - A-1 → A-2（引擎依赖 Schema）
  - A-2 → A-3（迁移依赖引擎可加载）
  - A-3 → A-4（注册表依赖规则文件）
  - A-4 → A-5（review_audit 改造依赖注册表）
- **B 系列** 依赖 A 系列完成
  - B-1 → B-2（前端依赖 API）
  - B-1 → B-3（编辑器依赖 API）
  - B-2 → B-4（生命周期面板依赖管理面板）
  - B-2 → B-5（协同确认依赖管理面板）
- **C 系列** 依赖 A 完成，可与 B 并行
  - C-1 → C-2（组件依赖 Schema）
  - C-2 → C-3（分析管道依赖反馈数据）
  - C-3 → C-4（触发机制依赖管道）
- **D 系列** 依赖 A、C 完成
  - D-1 依赖 A-4（注册表统计）
  - D-2 依赖 A-5（review_audit 改造）
  - D-3 依赖 D-1、D-2、C-3
  - D-4 依赖 B-2、D-3
- **E 系列** 依赖 B-5 完成
  - E-1、E-2、E-3 可并行
- **F 系列** 依赖 A~E 全部完成
  - F-1、F-2 可并行
  - F-3 依赖 F-1、F-2

**可并行任务**：
- A-3.1 / A-3.2 / A-3.3 / A-3.4 / A-3.5 / A-3.6（规则迁移子任务）
- B-2 / B-3（前端面板与编辑器）
- C-2 / C-3（反馈组件与分析管道）
- E-1 / E-2 / E-3（跨单位增强子任务）
