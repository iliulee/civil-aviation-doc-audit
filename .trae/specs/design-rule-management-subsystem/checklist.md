# Checklist — 规则管理子系统验证清单

> 验证 spec.md 中所有需求是否落地。每项验证通过后勾选。
> 验证顺序按 Phase A → F 推进。

---

## Phase A：规则分级与形式化

### 三层分级体系
- [ ] A-C1: 系统中存在 `L1-IRON` / `L2-LOGIC` / `L3-BUSINESS` 三种层级枚举，无其他值
- [ ] A-C2: R-12 高程自洽在 `rules/L2-logic/` 目录下（修正层级错位）
- [ ] A-C3: R-13 缺合计行、R-14 多参数联检在 `rules/L2-logic/` 目录下
- [ ] A-C4: R-01 规范可追溯、R-06 拒为伪证背书在 `rules/L1-iron/` 目录下
- [ ] A-C5: DQ-REPEAT/JUMP/ALTER 在 `rules/L3-business/` 目录下
- [ ] A-C6: 9.10 监理-施工方对照规则在 `rules/cross-unit/` 目录下，且每条 `scope=CROSS_UNIT`

### 跨单位对照特殊作用域
- [ ] A-C7: 跨单位规则 JSON 包含 `alignment` 对象
- [ ] A-C8: `alignment` 包含 `party_a` / `party_b` / `join_key` / `doc_type_a` / `doc_type_b`
- [ ] A-C9: 跨单位规则的 `confirmation_required` 字段为 `true`

### 规则形式化存储
- [ ] A-C10: 每条规则 JSON 包含 spec.md 第 5.1 节定义的所有必填字段（rule_id/name/level/scope/trigger_when/check_expr/error_template/status/source/version/created_at/updated_at/changelog）
- [ ] A-C11: `rule_id` 全局唯一，无重复
- [ ] A-C12: `version` 符合语义化版本号（X.Y.Z 格式）
- [ ] A-C13: `registry.json` 的 by_level / by_scope / by_status 统计数与文件实际数一致
- [ ] A-C14: `rule_schema_validator.py` 对所有规则文件校验通过

### 规则引擎集成
- [ ] A-C15: `rule_engine.py` 的 `RuleLoader` 能从 `rules/` 加载所有 `status=active` 规则
- [ ] A-C16: `RuleMatcher` 能按 doc_type / professional 正确匹配规则
- [ ] A-C17: `SingleDocChecker` 对单资料规则执行通过
- [ ] A-C18: `CrossDocChecker` 对跨资料规则执行通过
- [ ] A-C19: `CrossUnitChecker` 对跨单位规则执行通过（含 join 逻辑）
- [ ] A-C20: `review_audit.py` 改造后审核结果中每条发现都关联 `rule_id`、`level`、`scope`
- [ ] A-C21: 现有测试项目审核结果不回归（与改造前对比，发现项一致或更全）

---

## Phase B：规则管理子系统

### 规则管理面板
- [ ] B-C1: `rule-manager.html` 在浏览器中正常打开
- [ ] B-C2: 多维度筛选栏可按层级筛选
- [ ] B-C3: 多维度筛选栏可按作用域筛选
- [ ] B-C4: 多维度筛选栏可按状态筛选
- [ ] B-C5: 多维度筛选栏可按来源筛选
- [ ] B-C6: 多维度筛选栏可按专业筛选
- [ ] B-C7: 多维度筛选栏可按关键词搜索
- [ ] B-C8: 支持组合筛选（如"L2 + 跨单位 + active"）
- [ ] B-C9: 规则列表显示 ID/名称/层级/作用域/状态/版本/命中率
- [ ] B-C10: 点击规则可查看详情（含 changelog 时间线）
- [ ] B-C11: 管理员可点击"停用"将规则变为 `deprecated`
- [ ] B-C12: 启停操作写入 changelog（含操作人/时间/原因）

### 可视化规则编辑器
- [ ] B-C13: 编辑器引导用户依次选择层级/作用域/资料类型/字段/关系/比较对象/容差/错误模板
- [ ] B-C14: 字段字典按资料类型加载可选字段
- [ ] B-C15: 关系运算符下拉包含 =、≠、>、<、≥、≤、within、between
- [ ] B-C16: 编辑器实时预览生成的 JSON
- [ ] B-C17: 用户可在测试沙箱中用样例数据验证规则
- [ ] B-C18: 选择"跨单位"作用域时，编辑器额外要求配置 alignment
- [ ] B-C19: 跨单位规则编辑时提示"须经协同确认方可生效"
- [ ] B-C20: 非技术用户（无编程背景）可独立创建一条可执行规则

### 规则生命周期
- [x] B-C21: 新建规则初始状态为 `draft`
- [ ] B-C22: draft 状态规则仅创建者可见
- [x] B-C23: 用户可提交规则进入 `testing` 状态
- [x] B-C24: testing 状态规则在指定项目范围内试运行
- [x] B-C25: 测试期（默认 3 个项目）内误报率 < 10% 自动进入 `incubating`
- [x] B-C26: 管理员审批通过后状态变为 `active`
- [x] B-C27: active 规则可选择"项目级生效"或"全局生效"
- [x] B-C28: 仅 `draft` 状态规则可删除

### 跨单位协同确认
- [x] B-C29: 跨单位规则变更后状态变为 `pending_confirmation`
- [x] B-C30: 另一方在面板看到待确认标记
- [x] B-C31: 确认方点击"确认"后状态变为 `active`
- [x] B-C32: 确认方点击"驳回"后回退至 `incubating`
- [x] B-C33: 管理员强制确认须填写理由，记入 changelog
- [x] B-C34: 跨单位规则无确认时不生效（审核时不加载）

### 管理 API
- [x] B-C35: GET /api/rules 支持 level/scope/status/q 组合筛选
- [x] B-C36: GET /api/rules/{id} 返回详情含 changelog
- [x] B-C37: POST /api/rules 创建草稿成功
- [x] B-C38: PUT /api/rules/{id} 更新并自动写 changelog
- [x] B-C39: POST /api/rules/{id}/transition 状态流转正确
- [x] B-C40: POST /api/rules/{id}/confirm 协同确认成功
- [x] B-C41: GET /api/rules/{id}/stats 返回命中率/误报率
- [x] B-C42: POST /api/rules/{id}/test 沙箱测试返回结果
- [x] B-C43: DELETE /api/rules/{id} 仅 draft 状态可删，其他状态拒绝

---

## Phase C：反馈闭环

### 反馈收集入口
- [ ] C-C1: 审核报告中有"漏审反馈"按钮
- [ ] C-C2: 审核报告中有"误报"标记（每条规则命中项旁）
- [ ] C-C3: 漏审反馈表单包含：问题摘要/涉及资料/期望规则类型/严重度
- [ ] C-C4: 提交反馈时自动捕获上下文（审核 ID/资料快照/命中规则/时间）
- [ ] C-C5: 误报反馈捕获规则 ID/命中数据/用户说明
- [ ] C-C6: 反馈写入 `feedbacks/` 目录，文件名包含时间戳

### 反馈数据结构
- [ ] C-C7: 反馈 JSON 包含 spec.md 第 7.1 节所有字段
- [ ] C-C8: 反馈 Schema 校验通过

### LLM 反馈分析管道
- [ ] C-C9: `feedback_analyzer.py` 能加载 status=new 的反馈
- [ ] C-C10: 反馈向量化（embedding）成功
- [ ] C-C11: DBSCAN 聚类（eps=0.3, min_samples=3）输出聚类结果
- [ ] C-C12: 每类调用 LLM 提取共性模式
- [ ] C-C13: 生成候选规则 JSON（status=incubating）写入 `rules/custom/incubator/`
- [ ] C-C14: 候选规则不直接生效（审核时不加载）
- [ ] C-C15: 反馈 status 更新为 analyzed，cluster_id 写入
- [ ] C-C16: 分析报告输出到 `rules/reflections/feedback-analysis-{日期}.md`
- [ ] C-C17: 用 20 条样例反馈跑通完整管道，生成至少 1 条候选规则

### 触发机制
- [ ] C-C18: 累积 20 条反馈自动触发分析
- [ ] C-C19: 每周一次自动触发（与反思调度器联动）
- [ ] C-C20: POST /api/feedbacks/analyze 手动触发成功

---

## Phase D：自成长机制

### 规则效力自监控
- [ ] D-C1: `rule_monitor.py` 能统计每条规则的命中率（total_hits / total_reviews）
- [ ] D-C2: 能统计误报率（false_positive_count / total_hits）
- [ ] D-C3: 能追踪最近命中时间（last_hit_at）
- [ ] D-C4: 50 次审核命中率 < 5% 自动标记"低活跃"
- [ ] D-C5: 误报率 > 30% 自动降级（L2→L3 或 L3→deprecated）
- [ ] D-C6: L1 铁律不被自动降级
- [ ] D-C7: 自动降级操作写入 changelog

### 审核记忆流
- [ ] D-C8: `audit_memory/` 目录存在，按日期分文件
- [ ] D-C9: 每次审核后追加事件日志（审核 ID/时间/触发规则/命中/反馈）
- [ ] D-C10: 事件日志 JSON 格式校验通过

### LLM 反思调度器
- [ ] D-C11: `rule_reflector.py` 能汇总本周审核事件/反馈/规则命中统计
- [ ] D-C12: 调用 LLM 生成《规则优化建议报告》
- [ ] D-C13: 报告包含四类建议：新增/修改/停用/层级调整
- [ ] D-C14: 候选规则写入 `rules/custom/incubator/`
- [ ] D-C15: 报告输出到 `rules/reflections/YYYY-MM-DD.md`
- [ ] D-C16: 调度配置默认每周日 02:00，可通过配置调整
- [ ] D-C17: 管理员手动触发接口（POST /api/reflections/trigger）可用
- [ ] D-C18: 手动触发一次反思，生成报告与候选规则

### 反思报告管理
- [ ] D-C19: 规则管理面板有"反思报告"标签页
- [ ] D-C20: 历史报告列表可查看
- [ ] D-C21: 候选规则可在 UI 中 promote（提升为 active）或 reject（驳回）

---

## Phase E：跨单位对照增强

### 数据对齐视图
- [ ] E-C1: `alignment-view.html` 组件存在
- [ ] E-C2: 视图左列为监理方数据，右列为施工方数据
- [ ] E-C3: 中列显示差异值与命中规则
- [ ] E-C4: 差异行高亮显示
- [ ] E-C5: 点击差异行可查看双方原始资料
- [ ] E-C6: 缺失对齐键时显示告警（如"监理方有 Z418，施工方缺失"）
- [ ] E-C7: 对齐视图集成到审核报告 HTML 模板

### 性能
- [ ] E-C8: 跨单位规则按对齐键建立索引
- [ ] E-C9: 大数据量（>1000 行）分块处理
- [ ] E-C10: 1000 桩位 join 性能 < 1 秒

### 协同确认 UX
- [ ] E-C11: 待确认规则在面板突出显示
- [ ] E-C12: 确认/驳回操作后通知发起方
- [x] E-C13: 管理员强制确认须输入理由并记录

---

## Phase F：文档与集成

### 文档
- [ ] F-C1: `SKILL.md` 铁律章节重构为三层分级
- [ ] F-C2: `SKILL.md` 新增"规则管理子系统"章节
- [ ] F-C3: `SKILL.md` 更新触发语句（规则管理/反馈/反思）
- [ ] F-C4: `README.md` 新增"规则管理子系统"章节
- [ ] F-C5: `README.md` 更新目录结构（含 rules/ feedbacks/ audit_memory/）
- [ ] F-C6: `README.md` 新增 API 端点说明

### 集成测试
- [ ] F-C7: 现有测试项目跑通四阶段流水线，不回归
- [ ] F-C8: 规则管理面板完整跑通（筛选/编辑/启停）
- [ ] F-C9: 反馈收集 → LLM 分析 → 候选规则生成链路完整
- [ ] F-C10: 反思调度器手动触发 → 报告生成
- [ ] F-C11: 跨单位规则完整流程（创建/确认/审核/对齐视图）
- [ ] F-C12: 所有 Phase A-E 的 Checklist 项全部通过

---

## 总体设计原则验证

- [ ] G-C1: 所有规则可追溯（每条规则有 source 和 changelog）
- [ ] G-C2: L1 铁律不可被自动降级（保护合规底线）
- [ ] G-C3: 用户自定义规则不直接生效（必须经测试 + 审批）
- [ ] G-C4: 候选规则不直接生效（必须经管理员 promote）
- [ ] G-C5: 跨单位规则须协同确认（单方不能擅自变更）
- [ ] G-C6: 反馈闭环完整（漏审/误报 → 分析 → 候选规则 → 审批 → 上线）
- [ ] G-C7: 自监控指标可观测（命中率/误报率/最近命中时间）
- [ ] G-C8: 反思报告可追溯（每周一份，含历史归档）
- [ ] G-C9: 系统无硬编码规则调用（全部通过规则引擎加载）
- [ ] G-C10: 规则文件可跨机器迁移（纯文件系统，零数据库依赖）
