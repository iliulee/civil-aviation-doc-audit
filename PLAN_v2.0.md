# 全面优化方案 v2.0

> 版本：v2.0 | 日期：2026-08-11 | 基于 v9.5 现状 | 三大阶段，6 项核心任务优先执行

---

## 一、现状摘要

| 项目 | 状态 | 问题 |
|:---|:---:|:---|
| 四阶段流水线（步骤 1~7） | ✅ 完成 | 进度条展示，闸门齐备 |
| 推荐值生成（inferred） | ⚠️ 部分完成 | 仅桩基 5 条规则硬编码在代码里，非桩基工程缺，文本型缺；置信度<0.5 不输出导致空值 |
| 手写体识别 | ⚠️ 可用但半吊子 | 混合型文档（印刷表头+手写数据）无分级策略，不是全自动就是全手动 |
| 同步脚本 | ❌ 混乱 | 12 个 .ps1 + 2 个 .bat 历史残留 |
| 增量路径 | ⚠️ 可用但缺保护 | 新增文件可能覆盖旧文件的 human_verified 状态 |
| 测试体系 | ❌ 分散 | 无统一入口，改代码后不知道有没有搞坏别处 |
| 规则管理步骤 3~4 | ⏸️ 延期 | 等主审核流程跑通再弄 |
| 版本号 | ❌ 不一致 | SKILL.md 标题写 v9.4，内容实际是 v9.5 |

---

## 二、Phase 1：核心功能完善（立即执行，6 项任务）

### 任务 1：推荐值规则独立化 + 扩展

#### 1.1 问题

- 推荐值规则硬编码在 `data_quality_check.py` 的 `infer_values()` 方法里，不可配置
- 只覆盖**桩基工程**5 条数学链（实长=顶-底、桩顶=底+实长、桩底=顶-实长、充盈系数=灌入量/πr²L、灌入量=充盈系数×πr²L）
- 非桩基工程（碎石桩、垫层、土方）无推荐值
- 置信度 < 0.5 不输出 → 导致空值，比给个不准的值更糟糕

#### 1.2 改造方案

**① 新建 `rules/inference_rules.json`（推荐值规则配置文件）**

```json
{
  "schema_version": "1.0",
  "rules": [
    {
      "id": "INF-001",
      "name": "实长 = 桩顶高程 - 桩底高程",
      "type": "numeric",
      "condition": "actual_length为空，且top_elev和bottom_elev都存在",
      "formula": "actual_length = top_elev - bottom_elev",
      "base_confidence": 0.95,
      "cascade_penalty": 0.35,
      "applicable_to": ["桩基", "碎石桩", "CFG桩"]
    },
    {
      "id": "INF-002",
      "name": "桩顶高程 = 桩底高程 + 实长",
      "type": "numeric",
      "condition": "top_elev为空，且bottom_elev和actual_length都存在",
      "formula": "top_elev = bottom_elev + actual_length",
      "base_confidence": 0.95,
      "cascade_penalty": 0.35,
      "applicable_to": ["桩基", "碎石桩", "CFG桩"]
    },
    {
      "id": "INF-003",
      "name": "桩底高程 = 桩顶高程 - 实长",
      "type": "numeric",
      "condition": "bottom_elev为空，且top_elev和actual_length都存在",
      "formula": "bottom_elev = top_elev - actual_length",
      "base_confidence": 0.95,
      "cascade_penalty": 0.35,
      "applicable_to": ["桩基", "碎石桩", "CFG桩"]
    },
    {
      "id": "INF-004",
      "name": "充盈系数 = 灌入量 / (π × (桩径/2)² × 实长)",
      "type": "numeric",
      "condition": "filling_coeff为空，且volume、diameter、actual_length都存在",
      "formula": "filling_coeff = volume / (π × (diameter/2)² × actual_length)",
      "base_confidence": 0.85,
      "cascade_penalty": 0.30,
      "applicable_to": ["桩基", "碎石桩"]
    },
    {
      "id": "INF-005",
      "name": "灌入量 = 充盈系数 × π × (桩径/2)² × 实长",
      "type": "numeric",
      "condition": "volume为空，且filling_coeff、diameter、actual_length都存在",
      "formula": "volume = filling_coeff × π × (diameter/2)² × actual_length",
      "base_confidence": 0.85,
      "cascade_penalty": 0.30,
      "applicable_to": ["桩基", "碎石桩"]
    },
    {
      "id": "INF-006",
      "name": "单根桩施工时长 = 拔管时间 - 沉管时间",
      "type": "numeric",
      "condition": "duration为空，且sink_time和pull_time都存在",
      "formula": "duration = pull_time - sink_time",
      "base_confidence": 0.90,
      "cascade_penalty": 0.30,
      "applicable_to": ["碎石桩", "桩基"]
    },
    {
      "id": "INF-007",
      "name": "垫层厚度 = 顶面高程 - 底面高程",
      "type": "numeric",
      "condition": "thickness为空，且top_elev和bottom_elev都存在",
      "formula": "thickness = top_elev - bottom_elev",
      "base_confidence": 0.95,
      "cascade_penalty": 0.35,
      "applicable_to": ["垫层", "土方"]
    }
  ],
  "confidence_color_map": {
    "0.95-1.00": "深绿",
    "0.80-0.94": "浅绿",
    "0.50-0.79": "黄色",
    "0.30-0.49": "橙色",
    "0.00-0.29": "红色"
  }
}
```

**② 改造 `data_quality_check.py`**

- 从硬编码公式改为读取 `inference_rules.json`
- 新增 `_load_inference_rules()` 加载规则配置
- 新增 `_apply_rule(rule, row)` 执行单条规则
- 保留原有 5 条规则的逻辑，迁移到配置文件

**③ 改造 `build_foundation.py` 的 `call_inference()`**

- 置信度 < 0.5 也输出推荐值，但打上 `low_confidence: true` 标记

**④ 置信度标定规则（修正版）**

| 最终置信度 | 颜色 | 含义 | 审核是否使用 |
|:---:|:---:|:---|:---:|
| ≥ 0.95 | 深绿 | 源数据全是 OCR 确认值，数学关系直接 | ✅ 是 |
| 0.80~0.94 | 浅绿 | 源数据全是确认值，但涉及 π 含入误差 | ✅ 是 |
| 0.50~0.79 | 黄色 | 源数据混有推断值（级联），仅供参考 | ✅ 是 |
| 0.30~0.49 | 橙色 | 源数据 OCR 置信度低，数字可能不准 | ❌ 否，标记存疑 |
| < 0.30 | 红色 | 基本是瞎猜的，但占位提醒"这里需要填" | ❌ 否，标记存疑 |

**最终置信度计算公式：**
```
base_confidence = 规则的基础置信度（如 0.95）
如果源数据中有任何字段是推断值（非 OCR 确认值）：
    final_confidence = base_confidence - cascade_penalty
否则：
    final_confidence = base_confidence
如果源数据某字段的 OCR text_score < 0.5：
    final_confidence = final_confidence - 0.10（每有一个低置信字段）
```

**⑤ 涉及文件**

| 文件 | 操作 |
|:---|:---|
| `rules/inference_rules.json` | 新建 |
| `scripts/data_quality_check.py` | 修改：从硬编码改为读取配置 |
| `scripts/build_foundation.py` | 修改：call_inference() 增加低置信输出 |
| `SKILL.md` | 修改：更新推荐值规则描述 |
| `PROJECT_SPEC.md` | 修改：同步更新 |
| `references/CHANGELOG.md` | 修改：补充变更记录 |

---

### 任务 2：手写体混合型文档优化

#### 2.1 问题

- auto 模式下混合型文档（印刷表头+手写数据）无分级策略
- 要么全 RapidOCR（手写部分认不出来），要么全 AI 读图（浪费 token）
- 没有中间状态：对低置信字段单独裁剪+AI 读图复核

#### 2.2 改造方案

**① 置信度分级决策表**

| 字段 OCR text_score | 处理策略 | token 消耗 |
|:---:|:---|:---:|
| ≥ 0.9 | 直接使用，不处理 | 0 |
| 0.7~0.9 | 直接使用，标记"review recommended" | 0 |
| 0.5~0.7 | 数学推算能补则补，不能补则标记"需人工确认" | 0 |
| < 0.5 | 裁剪对应单元格 → AI 读图复核 | 每字段 ~1 张图 |

**② 实现：在 `build_foundation.py` 中新增"低置信字段复核"步骤**

- 在 OCR 完成 + 结构化解析完成后
- 遍历 `structured_rows` 中所有字段
- 对 text_score < 0.5 的字段，记录其 `page` + `bbox`（来自 OCR items）
- 调用 `ocr_image.py` 的 `crop_and_verify()` 函数裁剪对应区域，传给 AI 读图
- AI 返回修正值 → 更新到 `structured_rows` 中，标记 `ai_reviewed: true`

**③ 涉及文件**

| 文件 | 操作 |
|:---|:---|
| `scripts/ocr_image.py` | 新增 `crop_and_verify()` 函数 |
| `scripts/build_foundation.py` | 新增低置信字段复核步骤 |
| `references/ocr-hybrid-architecture.md` | 更新路由链说明 |
| `SKILL.md` | 更新 OCR 引擎策略描述 |

---

### 任务 3：同步脚本清理

#### 3.1 问题

根目录下 12 个 .ps1 + 2 个 .bat，历史版本残留，无法区分哪个是当前可用的。

#### 3.2 改造方案

**① 删除 12 个 .ps1 文件**

| 文件名 | 操作 |
|:---|:---:|
| `同步内部路由到安装版.ps1` | 删除 |
| `同步缺失文件到安装版.ps1` | 删除 |
| `同步run_audit到安装版.ps1` | 删除 |
| `同步SKILL引擎选择到安装版.ps1` | 删除 |
| `同步bug修复到安装版.ps1` | 删除 |
| `同步引擎选择到安装版.ps1` | 删除 |
| `同步修复build_foundation到安装版.ps1` | 删除 |
| `同步优化3项到安装版.ps1` | 删除 |
| `同步精简SKILL到安装版.ps1` | 删除 |
| `同步到安装版.ps1` | 删除 |
| `_同步3个差异文件.ps1` | 删除 |
| `install.ps1` | 删除 |

**② 保留 2 个文件**

| 文件名 | 操作 |
|:---|:---|
| `同步内部路由到安装版.bat` | 保留，加文件头注释 |
| `rule-manager.bat` | 保留（不属于同步脚本） |

**③ 在 `同步内部路由到安装版.bat` 文件头加注释**

```batch
@echo off
REM ============================================================
REM  【唯一同步入口】将项目版 Skill 文件同步到安装版
REM  
REM  用法：在项目根目录下运行
REM     & "D:\2026年7月22日 民航资料skill\同步内部路由到安装版.bat"
REM  
REM  说明：
REM     - 同步文件：SKILL.md、scripts/*.py、templates/*、rules/*、references/* 等
REM     - 自动清理 __pycache__ 缓存
REM     - 自动执行 verify_skill_structure.py 验证
REM     - 此脚本是唯一受支持的同步方式，其他 .ps1 脚本已废弃
REM ============================================================
```

**④ 涉及文件**

| 文件 | 操作 |
|:---|:---|
| 12 个 .ps1 文件 | 删除 |
| `同步内部路由到安装版.bat` | 修改：加文件头注释 |
| `README.md` | 修改：注明唯一同步入口 |

---

### 任务 4：增量对比清单 + 保护机制

#### 4.1 问题

- 增量更新时，AI 直接执行，用户不知道加了哪些文件、老文件会不会被重新 OCR
- 新增文件时可能覆盖旧文件的 human_verified 状态

#### 4.2 改造方案

**① 增量对比清单（AI 在步骤 2→3 之间展示）**

```
📋 已有文件（3 份）：
   ✅ 施工日志.xlsx（已核对，human_verified=true）
   ✅ 设计变更通知单.pdf（依据文件，无需核对）
   ⚠️ 扫描件.pdf（已核对，human_verified=true）
📋 新增文件（2 份）：
   🆕 补充记录1.pdf（需 OCR）
   🆕 补充记录2.pdf（需 OCR）
────────────────────────────────────
请确认：是否只处理这 2 份新增文件？(是/否)
```

**② 保护机制（在 `build_foundation.py` 增量模式中）**

- 增量模式下，`update_index_for_doc()` 保留已有文档的 `human_verified`、`corrected_file`、`audit_status` 字段
- 新增 `"incremental_added_at"` 时间戳
- 新增 `"incremental_from"` 标记（值为 `"new"` 或 `"existing"`）

**③ 涉及文件**

| 文件 | 操作 |
|:---|:---|
| `scripts/build_foundation.py` | 修改：增量保护逻辑 |
| `SKILL.md` | 修改：更新增量路径描述 |
| `PROJECT_SPEC.md` | 修改：同步更新 |

---

### 任务 5：统一测试体系

#### 5.1 问题

- 测试脚本分散在 `scripts/` 下，无统一入口
- `测试18/test_build_and_verify.py` 是临时脚本，未纳入正式体系
- 改代码后无法快速验证是否影响其他功能

#### 5.2 改造方案

**① 新建 `scripts/run_all_tests.py`（统一测试入口）**

```python
"""
一键运行所有测试。

用法：
    python scripts/run_all_tests.py [--skip-慢测试]

按顺序执行：
    1. test_rule_engine.py          — 规则引擎单元测试
    2. test_ocr_routing.py          — OCR 路由测试
    3. test_rule_subsystem_integration.py — 规则子系统集成测试
    4. test_cross_unit_perf.py      — 跨单位性能测试
    5. verify_skill_structure.py    — SKILL.md 结构验证
    6. test_data_foundation.py      — 数据底座重建测试（新增）
    7. test_inferred_values.py      — 推荐值生成测试（新增）
"""
```

**② 新建 `scripts/test_data_foundation.py`（数据底座测试）**

- 吸收 `测试18/test_build_and_verify.py` 的核心逻辑
- 测试新建路径 + 增量路径
- 测试 OCR 引擎选择（rapidocr/auto）
- 测试 index.json 生成正确性

**③ 新建 `scripts/test_inferred_values.py`（推荐值测试）**

- 构造测试数据：桩基 10 行（缺实长、缺桩顶、缺充盈系数）
- 验证推荐值规则 INF-001~INF-007 是否正常触发
- 验证置信度标定是否正确
- 验证级联推断（cascade）的置信度扣减

**④ 涉及文件**

| 文件 | 操作 |
|:---|:---|
| `scripts/run_all_tests.py` | 新建 |
| `scripts/test_data_foundation.py` | 新建 |
| `scripts/test_inferred_values.py` | 新建 |
| 原 `测试18/test_build_and_verify.py` | 保留，不删除（仍可单独使用） |

---

### 任务 6：版本号统一

#### 6.1 问题

| 文件 | 当前版本 | 问题 |
|:---|:---:|:---|
| SKILL.md 标题 | v9.4 | 实际内容为 v9.5 |
| README.md | v9.5 | 一致 |
| PROJECT_SPEC.md | v9.5 | 一致 |
| CHANGELOG.md | 缺 v9.5 | 最新条目为 v9.4 |

#### 6.2 改造方案

- SKILL.md 标题：`v9.4` → `v9.5`
- CHANGELOG.md：补充 v9.5 条目（含本次 Phase 1 全部变更）
- 本次所有修改完成后，统一更新版本号

---

## 三、Phase 2：体验优化（后续执行）

### 任务 7：data-editor 颜色标记 + 悬停推荐值

**方案：** 在现有 data-editor 表格中，对有推荐值的格子：

- 按置信度区间显示不同颜色底色（深绿/浅绿/黄/橙/红）
- 鼠标悬停时弹窗显示：推荐值、置信度、推算来源（如"桩顶高程 - 桩底高程"）
- 新增"全部同意推荐值"按钮（一键接受所有置信度 ≥ 0.80 的推荐值）
- **不开发新面板，不改大结构**

**涉及文件：** `templates/data-editor.html`

### 任务 8：多 Agent 并行审核完善

**方案：** 用真实项目测试 `--dry-run` → `--task-id` → 汇总的全流程，修复字段映射问题，控制每个子 Agent 的任务量。

**涉及文件：** `scripts/review_audit.py`、`scripts/run_audit.py`

---

## 四、Phase 3：延期（等主流程跑通）

| 项目 | 延期原因 |
|:---|:---|
| 规则管理步骤 3（反馈闭环） | 用户还没想好怎么做，先跑通主审核流程 |
| 规则管理步骤 4（反思触发） | 同上 |

---

## 五、实施顺序

```
Phase 1 任务 3（同步清理）→ 任务 6（版本号）
→ 任务 1（推荐值）→ 任务 2（手写体）
→ 任务 4（增量保护）→ 任务 5（测试体系）
→ Phase 2（体验优化）→ Phase 3（延期）
```

**任务 3 和任务 6 排在最前面**，因为它们不涉及代码逻辑变动，先做完可以减少后续干扰。

---

## 六、涉及文件汇总

### 新建文件

| 文件 | 所属任务 |
|:---|:---:|
| `rules/inference_rules.json` | 任务 1 |
| `scripts/run_all_tests.py` | 任务 5 |
| `scripts/test_data_foundation.py` | 任务 5 |
| `scripts/test_inferred_values.py` | 任务 5 |

### 修改文件

| 文件 | 所属任务 |
|:---|:---:|
| `scripts/data_quality_check.py` | 任务 1 |
| `scripts/build_foundation.py` | 任务 1、2、4 |
| `scripts/ocr_image.py` | 任务 2 |
| `SKILL.md` | 任务 1、2、4、6 |
| `PROJECT_SPEC.md` | 任务 1、4、6 |
| `README.md` | 任务 3、6 |
| `references/CHANGELOG.md` | 任务 6 |
| `references/ocr-hybrid-architecture.md` | 任务 2 |
| `同步内部路由到安装版.bat` | 任务 3 |

### 删除文件

| 文件 | 数量 | 所属任务 |
|:---|:---:|:---:|
| 根目录旧 .ps1 同步脚本 | 12 | 任务 3 |