# 铁律与逻辑规则管理子系统 设计规范

> **Change-ID**: `design-rule-management-subsystem`
> **目标**: 将现有散落在 markdown 文件中的 57+ 条规则重构为三层分级、形式化存储、可管理、可反馈、可自成长的规则管理子系统。
> **状态**: 设计阶段（Spec Mode）

---

## 1. Why（问题与机会）

### 1.1 现状混乱

当前系统已有 57+ 条规则，但存在严重的工程化缺陷：

1. **层级错位**：铁律（R-12 高程自洽）实际是数学自洽逻辑，被错误归入"绝对底线"。铁律应该是"不可商榷的合规底线"（如 R-01 规范可追溯、R-06 拒为伪证背书），而不是具体的计算校验。
2. **形式非结构化**：规则以 markdown 散文形式存在于 `references/logic-conflict-patterns.md`、`data-quality-patterns.md` 等文件中，无 ID、无触发条件表达式、无版本、无状态字段，无法被规则引擎统一调度。
3. **无生命周期**：规则一旦写入就永久存在，无法停用、无法迭代、无法区分"全局生效"与"项目级"。
4. **无反馈闭环**：审核中"漏审""误报"无捕获入口，用户标记的问题无法回流为规则改进。
5. **无自成长**：系统不会从审核历史中学习，新出现的矛盾模式无法自动沉淀为规则。
6. **跨单位对照未独立**：监理-施工方对照（9.10，17 条规则）逻辑独立、数据对齐方式特殊（需要跨资料 join），但当前与其他 9.x 规则混排。

### 1.2 机会

将规则系统重构后，可支持：
- 非技术用户通过可视化编辑器自定义规则
- 审核反馈自动回流，规则库随项目积累进化
- LLM 反思调度器定期生成规则优化建议
- 规则效力自监控（命中率/误报率），低质量规则自动降级

---

## 2. What Changes（变更内容）

### 2.1 规则分级体系重构 **BREAKING**

将现有"铁律 + 逻辑矛盾专项"两级重构为**三层 + 一个特殊作用域**：

| 层级 | 代号 | 判定标准 | 违反后果 | 典型示例 |
|:---:|:---:|:---|:---|:---|
| **L1 铁律** | `L1-IRON` | 不可商榷的合规底线、流程刚性要求、伦理红线 | 🔴 Fatal，直接判不合格，不可降级 | R-01 规范可追溯、R-06 拒为伪证背书、R-07 留痕 |
| **L2 逻辑一致性** | `L2-LOGIC` | 数学/几何/时序/引用自洽，可形式化为表达式 | 🟡 Sanity Check，标记为"逻辑矛盾"，必须人工复核 | 实长=桩顶高程−桩底高程、检验批日期≥进场日期、累计工程量闭合 |
| **L3 业务合理性** | `L3-BUSINESS` | 阈值/经验/行业惯例，可警告但不可定罪 | 🔵 Best Practice，提示性警告 | 突变率≥30%、充盈系数波动、节假日施工 |

**迁移映射**（现有规则 → 新层级）：
- R-01, R-03, R-04, R-05, R-06, R-07, R-08, R-15, R-17, R-19 → L1 铁律
- R-12 高程自洽、R-13 缺合计行、R-14 多参数联检、9.1~9.9 全部 → **L2 逻辑一致性**（**修正原错归**）
- R-10 数据质量、R-11 全列提取、R-16 提取重试 → L1 铁律（流程刚性）
- R-02 OCR 复核、R-20 存疑核实 → L1 铁律（流程刚性）
- R-09 逻辑矛盾专项 → L2 容器规则
- R-18 置信度分级 → L1 铁律（输出规范）
- data-quality-patterns.md 中的 DQ-REPEAT/JUMP/ALTER/SELF → L3 业务合理性（含部分 L2 自洽校验）
- 9.10 监理-施工方对照 → **特殊作用域 `SCOPE-CROSS-UNIT`**

### 2.2 跨单位对照特殊作用域 `SCOPE-CROSS-UNIT`

独立于三层分级之外的作用域标记，用于监理-施工方跨单位对照规则。

**特殊性**：
1. **数据对齐**：需要在两类资料（监理方、施工方）间按对齐键 join，而非单资料内校验
2. **协同确认**：此类规则的新增/修改须双方或管理员共同确认方可生效
3. **触发条件**：当审核资料集中同时存在监理方资料与施工方资料时自动激活
4. **层级归属**：跨单位对照规则本身仍分 L1/L2/L3，`SCOPE-CROSS-UNIT` 是附加维度

**示例**：
- `L2-LOGIC` + `SCOPE-CROSS-UNIT`：同一桩号监理记录混凝土量与施工方记录偏差 > 5%
- `L1-IRON` + `SCOPE-CROSS-UNIT`：监理验收日期早于施工自检日期（流程倒签）

### 2.3 规则形式化存储

每条规则以 JSON 文件存储于 `rules/` 目录，按层级分子目录：
```
rules/
├── L1-iron/           # 铁律
│   ├── R-001.json
│   └── R-006.json
├── L2-logic/          # 逻辑一致性
│   ├── LG-001.json
│   └── LG-002.json
├── L3-business/       # 业务合理性
│   ├── BZ-001.json
│   └── BZ-002.json
├── cross-unit/        # 跨单位对照（按层级标签二次分类）
│   └── CU-001.json
├── custom/            # 用户自定义（项目级）
│   └── draft/         # 草稿区
│   └── incubator/     # 孵化区（待审核）
└── registry.json      # 规则注册表（全量索引）
```

### 2.4 规则管理子系统

新增 `rule-manager.html` 前端面板 + `rule_engine.py` 后端引擎 + `rule_admin.py` 管理 API。

### 2.5 反馈闭环与自成长

新增 `feedback-collector.html`（嵌入审核报告）+ `feedback-analyzer.py`（LLM 反思管道）+ `rule-reflector.py`（定时反思调度器）。

---

## 3. Impact（影响范围）

### 3.1 受影响规范

- `references/logic-conflict-patterns.md` — 全部 9.x 规则迁移到结构化 JSON
- `references/data-quality-patterns.md` — DQ-* 规则迁移并拆分为 L2/L3
- `SKILL.md` — 铁律章节重构为三层分级
- `README.md` — 更新规则体系说明

### 3.2 受影响代码

- `scripts/review_audit.py` — 审核引擎改造为从规则注册表加载规则
- `scripts/audit_config.py` — 新增规则层级配置
- `scripts/build_foundation.py` — 复制规则管理面板到项目
- 新增 `scripts/rule_engine.py` — 规则引擎核心
- 新增 `scripts/rule_admin.py` — 规则管理 API
- 新增 `scripts/feedback_analyzer.py` — 反馈分析管道
- 新增 `scripts/rule_reflector.py` — 反思调度器
- 新增 `templates/rule-manager.html` — 规则管理面板
- 新增 `templates/feedback-collector.html` — 反馈收集组件

---

## 4. ADDED Requirements（新增需求）

### Requirement: 三层规则分级体系

系统 SHALL 提供三层规则分级（L1 铁律 / L2 逻辑一致性 / L3 业务合理性），每条规则必须明确归属一层，跨单位对照规则附加 `SCOPE-CROSS-UNIT` 作用域标记。

#### Scenario: 规则层级判定
- **WHEN** 创建或迁移一条规则
- **THEN** 系统要求选择层级（L1/L2/L3）和作用域（单资料/跨资料/跨单位）
- **AND** 层级一旦确定，L1 不可降级为 L2/L3，L2/L3 可在管理员审批后调整

#### Scenario: 违反后果分级
- **WHEN** 审核命中 L1 铁律
- **THEN** 报告中标记为 🔴 Fatal，直接判定资料不合格
- **WHEN** 审核命中 L2 逻辑一致性
- **THEN** 报告中标记为 🟡 Sanity Check，必须人工复核后定论
- **WHEN** 审核命中 L3 业务合理性
- **THEN** 报告中标记为 🔵 Best Practice，提示性警告，不影响合规判定

### Requirement: 规则形式化存储结构

每条规则 SHALL 以独立 JSON 文件存储，包含完整元数据。

#### Scenario: 规则数据结构
- **WHEN** 读取或写入一条规则
- **THEN** JSON 结构必须包含以下字段（见第 5 节完整定义）：
  - `rule_id`：全局唯一 ID（如 `LG-001`、`CU-001`、`BZ-CUSTOM-001`）
  - `name`：规则名称
  - `level`：层级（`L1-IRON` / `L2-LOGIC` / `L3-BUSINESS`）
  - `scope`：作用域（`SINGLE_DOC` / `CROSS_DOC` / `CROSS_UNIT`）
  - `trigger_when`：触发条件表达式
  - `check_expr`：校验表达式
  - `error_template`：错误消息模板
  - `status`：状态（`draft` / `testing` / `active` / `incubating` / `deprecated`）
  - `source`：来源（`system` / `custom` / `incubated`）
  - `version`：语义化版本号
  - `created_at` / `updated_at` / `changelog`

### Requirement: 跨单位对照规则的数据对齐

跨单位对照规则 SHALL 在 `alignment` 字段中声明对齐键和对照双方角色。

#### Scenario: 跨单位规则对齐
- **WHEN** 创建一条 `SCOPE-CROSS-UNIT` 规则
- **THEN** JSON 必须包含 `alignment` 对象：
  - `party_a`：甲方角色（如 `supervisor` 监理方）
  - `party_b`：乙方角色（如 `contractor` 施工方）
  - `join_key`：对齐键数组（如 `["pile_no"]` 桩号）
  - `doc_type_a` / `doc_type_b`：双方资料类型
- **AND** 规则生效前须经双方或管理员协同确认

### Requirement: 规则管理面板

系统 SHALL 提供 Web 规则管理面板，支持多维度筛选、查看、编辑、启用停用、变更历史。

#### Scenario: 多维度筛选
- **WHEN** 用户打开规则管理面板
- **THEN** 可按层级（L1/L2/L3）、作用域、状态、来源、专业、关键词筛选
- **AND** 支持组合筛选（如"L2 + 跨单位 + active"）

#### Scenario: 规则启停
- **WHEN** 管理员点击"停用"按钮
- **THEN** 规则状态变为 `deprecated`，审核时不再加载
- **AND** 变更记录写入 `changelog`，记录操作人、时间、原因

### Requirement: 可视化规则编辑器

系统 SHALL 提供可视化规则编辑器，非技术用户可通过选择字段、关系、条件创建规则。

#### Scenario: 无代码规则创建
- **WHEN** 用户点击"新建规则"
- **THEN** 编辑器引导用户依次选择：
  1. 层级（L1/L2/L3）
  2. 作用域（单资料/跨资料/跨单位）
  3. 资料类型（如"碎石桩施工记录"）
  4. 触发字段（从字段字典选择，如"实长"、"桩顶高程"）
  5. 关系运算符（=、≠、>、<、≥、≤、within、between）
  6. 比较对象（另一字段、常量、聚合值）
  7. 容差（如 ±0.1m）
  8. 错误消息模板
- **AND** 编辑器实时预览生成的 JSON 结构
- **AND** 用户可在"测试沙箱"中用样例数据验证规则

#### Scenario: 跨单位规则编辑
- **WHEN** 用户选择作用域为"跨单位"
- **THEN** 编辑器额外要求配置 `alignment`（双方角色、对齐键、资料类型）
- **AND** 提示"此规则须经协同确认方可生效"

### Requirement: 用户自定义规则生命周期

用户自定义规则 SHALL 经历完整生命周期：个人草稿 → 测试 → 提交审核 → 项目级/全局发布。

#### Scenario: 生命周期流转
- **WHEN** 用户创建自定义规则
- **THEN** 初始状态为 `draft`，仅创建者可见
- **WHEN** 用户在测试沙箱验证通过后点击"提交测试"
- **THEN** 状态变为 `testing`，在指定项目范围内试运行
- **WHEN** 测试期（默认 3 个项目）内误报率 < 10%
- **THEN** 自动进入 `incubating` 状态，提交管理员审核
- **WHEN** 管理员审批通过
- **THEN** 状态变为 `active`，可选择"项目级生效"或"全局生效"

### Requirement: 反馈收集入口

审核结果界面 SHALL 提供最小化反馈入口，支持"漏审"和"误报"两类反馈。

#### Scenario: 漏审反馈
- **WHEN** 用户在审核报告中发现遗漏的问题
- **THEN** 点击"漏审反馈"按钮，填写：
  - 问题摘要
  - 涉及的资料文件
  - 期望触发的规则类型（下拉选择已有规则或"无匹配规则"）
  - 严重度（L1/L2/L3）
- **AND** 系统自动捕获上下文：审核 ID、资料快照、命中的其他规则、审核时间

#### Scenario: 误报反馈
- **WHEN** 用户认为某条规则命中是误报
- **THEN** 点击该规则命中项旁的"误报"标记
- **AND** 系统捕获规则 ID、命中数据、用户说明
- **AND** 该反馈进入规则效力统计，影响命中率/误报率指标

### Requirement: LLM 反馈分析管道

系统 SHALL 提供 LLM 驱动的反馈分析管道，对反馈聚类、提取模式、生成候选规则。

#### Scenario: 反馈聚类
- **WHEN** 累积反馈达到 20 条或每周触发一次（以先到为准）
- **THEN** `feedback_analyzer.py` 启动 LLM 分析：
  1. 对反馈向量化（embedding）并聚类
  2. 提取每类的共性模式（如"多份资料中桩号 Z419 实长与高程差不一致"）
  3. 生成候选规则 JSON（状态 `incubating`）
  4. 输出分析报告到 `rules/incubator/`
- **AND** 候选规则不直接生效，待管理员评审

### Requirement: 规则自监控与自动降级

系统 SHALL 监控每条规则的命中率与误报率，对低质量规则自动降级或标记。

#### Scenario: 自动降级
- **WHEN** 某条 L3 规则在最近 50 次审核中命中率 = 0
- **THEN** 自动标记为"低活跃"，提示管理员复查
- **WHEN** 某条规则误报率 > 30%（基于反馈统计）
- **THEN** 自动降级：L2 → L3 或 L3 → `deprecated`，并通知管理员
- **AND** L1 铁律不参与自动降级（不可商榷）

### Requirement: LLM 反思调度器

系统 SHALL 提供定时反思调度器，定期生成规则优化建议报告。

#### Scenario: 周度反思
- **WHEN** 每周日凌晨 2:00（可通过配置调整）
- **THEN** `rule_reflector.py` 启动：
  1. 汇总本周审核事件日志、反馈数据、规则命中统计
  2. 调用 LLM 生成《规则优化建议报告》，包含：
     - 新增规则建议（基于漏审模式）
     - 修改规则建议（基于误报分析）
     - 停用规则建议（基于低命中率）
     - 层级调整建议（L2→L3 或反向）
  3. 报告输出到 `rules/reflections/YYYY-MM-DD.md`
  4. 候选规则写入 `rules/incubator/`
- **AND** 管理员在规则管理面板可查看历史反思报告

### Requirement: 跨单位数据对齐视图

系统 SHALL 为跨单位对照规则构建数据对齐视图，可视化呈现双方资料 join 结果。

#### Scenario: 对齐视图展示
- **WHEN** 审核命中跨单位规则
- **THEN** 报告中展示对齐视图表格：
  - 左列：监理方数据（按对齐键）
  - 右列：施工方数据（按对齐键）
  - 中列：差异值与命中规则
- **AND** 差异行高亮，点击可查看双方原始资料

---

## 5. 规则数据模型（JSON Schema）

### 5.1 完整规则结构

```json
{
  "rule_id": "LG-001",
  "name": "高程自洽校验",
  "level": "L2-LOGIC",
  "scope": "SINGLE_DOC",
  "category": "数学自洽",
  "description": "碎石桩实长必须等于桩顶高程减桩底高程，容差 ±0.1m",

  "trigger_when": {
    "doc_type": ["碎石桩施工记录", "PHC管桩施工记录"],
    "field_required": ["实长", "桩顶高程", "桩底高程"]
  },

  "check_expr": {
    "type": "expression",
    "expr": "abs(实长 - (桩顶高程 - 桩底高程)) <= 0.1",
    "language": "jinja-expr",
    "fallback": "python_eval"
  },

  "error_template": "桩号 {pile_no} 高程自洽失败：实长 {实长}m，但桩顶高程 {桩顶高程}m − 桩底高程 {桩底高程}m = {computed}m，差异 {diff}m 超出容差 ±0.1m",

  "severity_on_violation": "Sanity Check",
  "remediation": "核查实长记录是否被涂改，或高程数据是否抄写错误",

  "status": "active",
  "source": "system",
  "version": "1.2.0",
  "created_at": "2026-07-30T10:00:00",
  "updated_at": "2026-07-30T10:00:00",
  "owner": "system",

  "applies_to": {
    "professional": ["01_场道工程"],
    "subdivision_codes": ["01-03"]
  },

  "stats": {
    "total_hits": 0,
    "total_reviews": 0,
    "hit_rate": 0.0,
    "false_positive_count": 0,
    "false_positive_rate": 0.0,
    "last_hit_at": null,
    "last_review_at": null
  },

  "alignment": null,

  "changelog": [
    {
      "version": "1.0.0",
      "date": "2026-07-24",
      "author": "system",
      "change": "初始版本，从铁律 R-12 迁移并修正层级（原错归 L1，实际为 L2 数学自洽）"
    },
    {
      "version": "1.2.0",
      "date": "2026-07-30",
      "author": "admin",
      "change": "扩展适用范围至 PHC管桩施工记录"
    }
  ]
}
```

### 5.2 跨单位对照规则结构（附加 `alignment`）

```json
{
  "rule_id": "CU-008",
  "name": "监理-施工方混凝土量偏差校验",
  "level": "L2-LOGIC",
  "scope": "CROSS_UNIT",
  "category": "跨单位数量对照",

  "trigger_when": {
    "doc_type_a": "监理旁站记录",
    "doc_type_b": "碎石桩施工记录",
    "require_both": true
  },

  "alignment": {
    "party_a": {
      "role": "supervisor",
      "label": "监理方",
      "doc_type": "监理旁站记录"
    },
    "party_b": {
      "role": "contractor",
      "label": "施工方",
      "doc_type": "碎石桩施工记录"
    },
    "join_key": ["pile_no"],
    "field_a": "混凝土灌入量",
    "field_b": "灌入量",
    "aggregation": "none"
  },

  "check_expr": {
    "type": "cross_compare",
    "expr": "abs(field_a - field_b) / max(field_a, field_b) <= 0.05",
    "language": "jinja-expr"
  },

  "error_template": "桩号 {pile_no} 监理记录混凝土量 {field_a}m³，施工方记录 {field_b}m³，偏差 {deviation}% 超过 5% 阈值",

  "severity_on_violation": "Sanity Check",
  "confirmation_required": true,
  "confirmation_scope": "both_parties_or_admin",

  "status": "active",
  "source": "system",
  "version": "1.0.0",
  "changelog": []
}
```

### 5.3 规则注册表 `registry.json`

```json
{
  "schema_version": "1.0",
  "updated_at": "2026-07-30T10:00:00",
  "total_rules": 87,
  "by_level": {
    "L1-IRON": 12,
    "L2-LOGIC": 48,
    "L3-BUSINESS": 27
  },
  "by_scope": {
    "SINGLE_DOC": 60,
    "CROSS_DOC": 12,
    "CROSS_UNIT": 15
  },
  "by_status": {
    "active": 80,
    "draft": 3,
    "testing": 2,
    "incubating": 1,
    "deprecated": 1
  },
  "rules": [
    {
      "rule_id": "LG-001",
      "name": "高程自洽校验",
      "level": "L2-LOGIC",
      "scope": "SINGLE_DOC",
      "status": "active",
      "version": "1.2.0",
      "file": "L2-logic/LG-001.json"
    }
  ]
}
```

---

## 6. 整体架构

### 6.1 模块划分（文字架构图）

```
┌─────────────────────────────────────────────────────────────────────┐
│                    规则管理子系统（Rule Management Subsystem）        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  前端层（Frontend）                                          │   │
│  │  ├── rule-manager.html      规则管理面板（多维度筛选/编辑） │   │
│  │  ├── rule-editor.html       可视化规则编辑器（无代码）      │   │
│  │  ├── feedback-collector.js  反馈收集组件（嵌入审核报告）    │   │
│  │  └── alignment-view.html    跨单位对齐视图组件              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              ↕ REST API                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  API 层（rule_admin.py）                                    │   │
│  │  ├── GET  /rules            规则列表（支持筛选）            │   │
│  │  ├── GET  /rules/{id}       规则详情                        │   │
│  │  ├── POST /rules            创建规则（草稿）                │   │
│  │  ├── PUT  /rules/{id}       更新规则（写入 changelog）      │   │
│  │  ├── POST /rules/{id}/transition  状态流转                  │   │
│  │  ├── POST /rules/{id}/confirm     协同确认（跨单位规则）    │   │
│  │  ├── GET  /rules/{id}/stats       命中率/误报率统计         │   │
│  │  ├── GET  /feedbacks         反馈列表                        │   │
│  │  └── POST /feedbacks         提交反馈                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              ↕                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  核心引擎层（rule_engine.py）                               │   │
│  │  ├── RuleLoader             从 rules/ 加载 active 规则       │   │
│  │  ├── RuleMatcher            按作用域/资料类型匹配规则        │   │
│  │  ├── RuleExecutor           执行 check_expr                  │   │
│  │  │   ├── SingleDocChecker   单资料规则                       │   │
│  │  │   ├── CrossDocChecker    跨资料规则                       │   │
│  │  │   └── CrossUnitChecker   跨单位规则（含 join）            │   │
│  │  ├── ExpressionEvaluator    表达式求值（jinja-expr/python）  │   │
│  │  └── ViolationReporter      生成违规发现                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              ↕                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  存储层（File System）                                      │   │
│  │  ├── rules/                 规则文件库（JSON）              │   │
│  │  │   ├── L1-iron/                                           │   │
│  │  │   ├── L2-logic/                                          │   │
│  │  │   ├── L3-business/                                       │   │
│  │  │   ├── cross-unit/                                        │   │
│  │  │   ├── custom/draft/       用户草稿                       │   │
│  │  │   ├── custom/incubator/   孵化区（候选规则）              │   │
│  │  │   ├── reflections/        反思报告                        │   │
│  │  │   └── registry.json       全量注册表                      │   │
│  │  ├── feedbacks/             反馈存储（JSON）                 │   │
│  │  └── audit_memory/          审核记忆流（事件日志）           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              ↕                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  自成长层（Self-Growth）                                    │   │
│  │  ├── feedback_analyzer.py   LLM 反馈分析管道                │   │
│  │  │   ├── 聚类（embedding + DBSCAN）                         │   │
│  │  │   ├── 模式提取（LLM prompt）                             │   │
│  │  │   └── 候选规则生成                                       │   │
│  │  ├── rule_reflector.py      定时反思调度器（每周）          │   │
│  │  │   ├── 审核事件汇总                                       │   │
│  │  │   ├── LLM 生成优化建议报告                               │   │
│  │  │   └── 候选规则写入 incubator                             │   │
│  │  └── rule_monitor.py        规则效力自监控                  │   │
│  │      ├── 命中率统计                                         │   │
│  │      ├── 误报率统计                                         │   │
│  │      └── 自动降级（L2→L3 或 L3→deprecated）                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↕
                    现有审核流水线
                  (review_audit.py)
```

### 6.2 与现有审核流水线的集成

```
现有流水线：
  阶段1 建   → 阶段2 核   → 阶段3 审              → 阶段4 报
                              ↓
                    接入规则引擎
                              ↓
              RuleLoader 加载 active 规则
                              ↓
              RuleMatcher 按资料类型匹配
                              ↓
              RuleExecutor 逐条执行 check_expr
                              ↓
              ViolationReporter 输出发现
                              ↓
              报告中嵌入反馈收集组件
                              ↓
              反馈写入 feedbacks/
                              ↓
              周度反思调度器处理
```

---

## 7. 反馈闭环详细设计

### 7.1 反馈数据结构

```json
{
  "feedback_id": "FB-2026-07-30-001",
  "audit_id": "AU-2026-07-30-001",
  "type": "missed",
  "rule_id": null,
  "user_id": "admin",
  "timestamp": "2026-07-30T15:30:00",

  "context": {
    "doc_id": "DOC-018",
    "doc_file": "碎石桩施工记录.pdf",
    "page": 14,
    "row_index": 8,
    "field": "实长",
    "field_value": "9.0",
    "other_hit_rules": ["LG-001"]
  },

  "user_input": {
    "summary": "Z417 桩长从 13.5m 断崖跌至 9.0m，但未触发任何突变规则",
    "expected_rule_type": "L3-BUSINESS",
    "expected_severity": "Sanity Check",
    "suggested_rule_description": "相邻桩实长变化率 ≥ 30% 应触发突变警告"
  },

  "status": "new",
  "analyzed_at": null,
  "cluster_id": null
}
```

### 7.2 LLM 反馈分析管道流程

```
feedbacks/*.json
      │
      ▼
  1. 加载所有 status=new 的反馈
      │
      ▼
  2. 向量化（embedding：将反馈摘要 + 上下文向量化）
      │
      ▼
  3. 聚类（DBSCAN，eps=0.3，min_samples=3）
      │
      ▼
  4. 对每个聚类调用 LLM：
     Prompt: "以下是 N 条相似反馈，请提取共性模式，生成一条候选规则 JSON..."
      │
      ▼
  5. LLM 输出候选规则 JSON（status=incubating）
      │
      ▼
  6. 写入 rules/custom/incubator/CU-INC-{日期}-{序号}.json
      │
      ▼
  7. 更新反馈 status=analyzed, cluster_id=CL-{编号}
      │
      ▼
  8. 输出分析报告 rules/reflections/feedback-analysis-{日期}.md
```

### 7.3 规则效力自监控指标

| 指标 | 计算方式 | 阈值 | 触发动作 |
|:---|:---|:---|:---|
| 命中率 | total_hits / total_reviews | < 5%（50 次审核） | 标记"低活跃" |
| 误报率 | false_positive_count / total_hits | > 30% | L2→L3 或 L3→deprecated |
| 最近命中 | last_hit_at | > 90 天未命中 | 标记"休眠" |
| 反馈集中度 | 单规则反馈数 / 总反馈数 | > 20% | 优先反思 |

---

## 8. 跨单位对照专项设计

### 8.1 数据对齐视图构建

```
监理旁站记录 (party_a)              施工方施工记录 (party_b)
┌──────────────────────┐           ┌──────────────────────┐
│ pile_no │ 灌入量     │           │ pile_no │ 灌入量     │
│ Z415    │ 12.5       │           │ Z415    │ 12.8       │
│ Z416    │ 13.0       │           │ Z416    │ 13.0       │
│ Z417    │ 13.2       │           │ Z417    │ 9.0  ← 异常│
│ Z418    │ 13.5       │           │ Z419    │ 13.7       │
└──────────────────────┘           └──────────────────────┘
              │                              │
              └───────── join on pile_no ────┘
                          │
                          ▼
              ┌─────────────────────────────────────┐
              │ 对齐视图                             │
              │ pile_no │ 监理方 │ 施工方 │ 偏差%   │
              │ Z415    │ 12.5   │ 12.8   │ 2.4% ✓ │
              │ Z416    │ 13.0   │ 13.0   │ 0.0% ✓ │
              │ Z417    │ 13.2   │ 9.0    │ 31.8%🔴│ ← 命中 CU-008
              │ Z418    │ 13.5   │ (缺失) │  —     │ ← 缺失告警
              │ Z419    │ (缺失) │ 13.7   │  —     │ ← 缺失告警
              └─────────────────────────────────────┘
```

### 8.2 协同确认机制

跨单位规则的新增、修改、停用 SHALL 经协同确认：

1. **发起方**提交变更，状态变为 `pending_confirmation`
2. **另一方**（或管理员）在规则管理面板看到待确认标记
3. **确认方**点击"确认"或"驳回"
4. 确认后状态变为 `active`，驳回则回退至 `incubating`
5. 管理员拥有强制确认权限（须填写理由，记入 changelog）

---

## 9. 实施路径（分阶段）

### Phase A：规则重构与形式化（基础）

1. 设计规则 JSON Schema（本文档第 5 节）
2. 编写 `scripts/rule_engine.py` 核心引擎（RuleLoader/Matcher/Executor）
3. 将现有 57+ 条规则从 markdown 迁移到结构化 JSON
4. 修正层级错位（如 R-12 高程自洽 → L2-LOGIC）
5. 生成 `registry.json` 全量注册表
6. 改造 `review_audit.py` 从规则引擎加载规则

### Phase B：规则管理界面

7. 开发 `templates/rule-manager.html` 规则管理面板
8. 开发可视化规则编辑器（无代码创建）
9. 开发 `scripts/rule_admin.py` 管理 API
10. 实现规则生命周期流转（draft→testing→incubating→active）
11. 实现跨单位规则协同确认机制

### Phase C：反馈闭环

12. 在审核报告中嵌入反馈收集组件
13. 开发 `feedbacks/` 存储与查询
14. 实现"漏审""误报"两类反馈捕获
15. 开发 `scripts/feedback_analyzer.py` LLM 分析管道
16. 实现反馈聚类与候选规则生成

### Phase D：自成长机制

17. 开发 `scripts/rule_monitor.py` 规则效力监控
18. 实现命中率/误报率统计与自动降级
19. 开发 `scripts/rule_reflector.py` 定时反思调度器
20. 构建"审核记忆流"日志格式
21. 实现 LLM 周度反思报告生成

### Phase E：跨单位对照增强

22. 实现跨单位数据对齐视图组件
23. 优化跨单位规则匹配性能（join 索引）
24. 完善协同确认 UX 流程

---

## 10. API 草案（核心端点）

### 10.1 规则管理

```
GET    /api/rules                     列表（支持 ?level=&scope=&status=&q=）
GET    /api/rules/{rule_id}           详情
POST   /api/rules                     创建（草稿）
PUT    /api/rules/{rule_id}           更新（自动写 changelog）
DELETE /api/rules/{rule_id}           删除（仅 draft 状态可删）

POST   /api/rules/{rule_id}/transition    状态流转
       body: { "to": "testing", "project_scope": "项目A" }

POST   /api/rules/{rule_id}/confirm        协同确认（跨单位规则）
       body: { "confirmor": "supervisor_zhang", "decision": "approve" }

GET    /api/rules/{rule_id}/stats          命中率/误报率
GET    /api/rules/{rule_id}/changelog      变更历史
POST   /api/rules/{rule_id}/test           在沙箱中测试规则
       body: { "sample_data": {...} }
```

### 10.2 反馈管理

```
POST   /api/feedbacks                   提交反馈
GET    /api/feedbacks                   列表（支持 ?type=&status=&audit_id=）
GET    /api/feedbacks/{feedback_id}     详情
POST   /api/feedbacks/analyze           触发 LLM 分析管道
GET    /api/feedbacks/clusters          查看聚类结果
```

### 10.3 反思与自成长

```
POST   /api/reflections/trigger         手动触发反思
GET    /api/reflections                 反思报告列表
GET    /api/reflections/{date}          指定日期的反思报告
GET    /api/incubator                   孵化区候选规则
POST   /api/incubator/{rule_id}/promote 提升候选规则为 active
POST   /api/incubator/{rule_id}/reject  驳回候选规则
```
