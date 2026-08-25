# 原生模式阶段 1 机械化步骤清单（v8.1 新增，v8.5 增量路径，v8.7 OCR全流程加固+模板目录重构+三步指引UI）

> 本文件供**原生模式**下 AI 逐条对照执行。每条步骤提供明确的"是/否"完成标准，不依赖任何 Python 脚本。
> 低智商模型按本清单机械执行即可完成数据底座建立。
> **v8.5 新增**：增量路径（I-1~I-6），当检测到数据底座已存在时自动走增量路径，避免重复 OCR 和重复弹窗。
> **v8.7 更新（本版本关键）**：
> 1. **模板目录统一**：所有 Web 模板统一复制到「**项目文件夹/数据底座/**」子目录，**禁止模板出现在项目文件夹根目录**
> 2. **模板中文命名**：data-editor.html→**数据核对编辑器.html**、project-dashboard.html→**项目总览.html**、launcher.html→**打开审核工具.html**、alignment-view.html→**文档对齐视图.html**、rule-manager.bat→**规则管理工具.bat**
> 3. **低频工具不复制**：rule-editor.html、feedback-collector.html 仅存于 skill 根目录 templates/，不复制到每个项目数据底座
> 4. **launcher 三步指引**：打开审核工具.html 三步顺序必须是「核对数据→查看报告→其他工具」，报告入口在所有文件 human_verified=false 时**灰色禁用**+tooltip
> 5. **data-editor 自动加载**：数据核对编辑器.html 必须包含打开后 `fetch('./index.json')` 自动加载同级 index.json 的逻辑，失败才提示手动选择；localStorage 仅存 project_name（项目名记忆，不存实际审核数据）
> 6. **rule-manager 三级路径定位**：规则管理工具.bat 必须使用三级路径自动定位版（当前目录→上级目录→全局 Skill 安装路径），双击即可启动 rule-manager.html 完整版，无需用户手动找 skill 安装目录
> 7. **OCR 引擎四选一前置**：前置信息必须显式提供 `auto（推荐）/ vision（云端API）/ paddle（本地批量）/ agent（AGENT Vision复核）` 四选一，禁止隐藏选项

---

## 🔀 路由：检测是否已有数据底座（AI 收到审核请求后第一件事）

在执行任何步骤之前，AI 必须用 Read 工具检查：

```
项目文件夹/数据底座/index.json 是否存在？
```

- [ ] **存在** → 走「增量路径」（本章节 I-1~I-6），跳过下方步骤 1~8
- [ ] **不存在** → 走「新建路径」（下方步骤 1~8）

> **🔴 强制规则：index.json 存在时必须走增量路径，禁止假装没看到直接走新建路径覆盖老数据。**

---

## 增量路径（index.json 已存在时）

### 增量 I-1：文件差异对比（AI 自动执行，0 次交互）

1. 用 LS 工具列出项目文件夹中所有文件
2. 用 Read 工具读取 `数据底座/index.json`，获取已有 documents 数组
3. 对比当前文件列表 vs index.json 中记录的文件，输出差异表：

```
📂 检测到项目已有数据底座

上次审核：{index.json.created_at} ｜ 已审核 {N} 份资料 ｜ 累计 {K} 条问题

📌 本次变化：
  ➕ 新增 {X} 份：{文件名列表}
  ⏺ 不变 {Y} 份：{文件名列表}
  ✏️ 修改 0 份（SHA256 一致跳过）
  ➖ 删除 0 份
```

**文件变化判断规则**：
- 新文件（不在 index.json documents 中）→ ➕ 新增
- 已有文件（在 documents 中，且文件 SHA256 与 content_hash 一致）→ ⏺ 不变
- 已有文件（在 documents 中，但 SHA256 变了）→ ✏️ 修改
- index.json 中有但文件夹中已不存在 → ➖ 删除

- [ ] 差异表已输出，用户看到了变化 → 继续 I-2

---

### 增量 I-2：前置信息一键确认（1 次交互，不是 6 次）

从 `index.json` 的 `preconditions` 字段读取缓存值，直接展示，只问一句：

```
前置信息（沿用上次设置）：
  · 项目阶段：{stage}
  · 资料性质：{nature}
  · 审核范围：{scope}
  · OCR 引擎：{ocr_engine}
  · 特殊说明：{special_notes}
  · 签字检查：{check_signatures}

有变更吗？直接回复"没有"我就开始，或者告诉我哪项要改。
```

- [ ] 用户确认前置信息（"没有"或指定修改项）→ 继续 I-3

---

### 增量 I-3：处理方式选择（1 次交互，推荐默认高亮）

```
如何处理新增资料？

🟢 增量审核（推荐）— 只审新增的 {X} 份，单独出增量报告
   · 老文件不复审，老问题不重复报告
   · 新报告末尾附"上次审核结论摘要"作为上下文
   · 新数据追加到数据底座，index.json 增量更新

🟡 全量重审 — 新旧 {X+Y} 份一起审，出一份新报告
   · 老文件 SHA256 一致的跳过 OCR，直接复用已有数据
   · 规则引擎重新跑一遍，老问题可能被重新报告
   · 适用场景：想确认老问题整改情况

🔴 重建数据底座 — 清空旧的，全部重新来过
   · 适用场景：换了一批完全不同的资料，或上次审核结果不可信
   · ⚠️ 会删除旧数据底座，不可恢复
```

- [ ] 用户选择处理方式（🟢/🟡/🔴）→ 继续 I-4

---

### 增量 I-4：更新入口导航页（必做，不可跳过）

> **🔴 v8.7 更新：模板统一放在「项目文件夹/数据底座/」子目录，禁止出现在项目根目录；中文命名；新增文档对齐视图.html 和规则管理工具.bat。**
> **🔴 增量路径下，`数据核对编辑器.html`、`项目总览.html`、`打开审核工具.html`、`文档对齐视图.html`、`规则管理工具.bat`、`tokens.css`、`pdf.min.js`、`pdf.worker.min.js` 应在首次审核时已复制到「项目文件夹/数据底座/」。增量 I-4 只做两件事：① 检查 8 个静态资源是否存在（缺失则补拷），② 生成/更新 `打开审核工具.html`（每次必做，嵌入最新 __PROJECT_DATA__）。**

**步骤 1：检查静态模板（5 秒完成）**

用 LS 列出**「项目文件夹/数据底座/」**子目录（不是项目根目录！），确认以下文件存在：
- [ ] `数据核对编辑器.html` 存在？
- [ ] `项目总览.html` 存在？
- [ ] `打开审核工具.html` 存在？
- [ ] `文档对齐视图.html` 存在？
- [ ] `规则管理工具.bat` 存在？
- [ ] `tokens.css` 存在？
- [ ] `pdf.min.js` 存在？
- [ ] `pdf.worker.min.js` 存在？

| 检查结果 | 动作 |
|:---|:---|
| 全部存在 | 跳过拷贝，直接进入步骤 2 |
| 任一缺失 | 从技能 `templates/` 目录读取缺失文件，Write 到**「项目文件夹/数据底座/」**（不是项目根目录） |
| 任一文件出现在项目根目录 | **必须删除项目根目录下的模板文件**（v8.7 强制：模板只能在数据底座/），同时把正确版本写入数据底座/ |

> 如果这些文件全部缺失，说明首次审核时步骤 7 未执行。补齐后继续，但要在审核日志中记录 "incremental_template_backfill": true。

**低频工具检查（不计入 G-1.5，但不允许复制到项目）：**
用 LS 确认项目文件夹任何位置（含根目录和数据底座/）**不存在**以下文件：
- [ ] ✅ rule-editor.html 不存在？
- [ ] ✅ feedback-collector.html 不存在？
> 如发现上述文件，必须立即删除。它们是低频工具，仅存在于 skill 根目录 templates/，不复制到每个项目。

**步骤 2：生成 `打开审核工具.html`（每次必做，约 30 秒）**

> **🔴 为什么每次都要重新生成？** 因为报告链接变了、项目状态变了（新增资料数、累计问题数、human_verified 进度等）。这个文件是项目的"控制面板"，必须反映最新状态。
> **🔴 v8.7 更新：三步顺序必须是「核对数据→查看报告→其他工具」，且查看报告按钮在 documents[].human_verified 未全部 true 时灰色禁用 + tooltip 说明原因。**

**机械化执行流程**（AI 逐条对照，不可跳过）：

```
1. Read 数据底座/index.json → 获取 project_name, documents 数组, updated_at, created_at, audit_summary
2. 根据 documents 计算：
   · total_docs = documents.length
   · verified_count = documents.filter(d => d.human_verified === true).length
   · 按 audit_batch 分组，latest_batch = 最大批次号
   · new_count = 最新批次的文件数
   · fatal = audit_summary.fatal 或逐条统计
   · sanity_check = audit_summary.sanity_check 或逐条统计
   · best_practice = audit_summary.best_practice 或逐条统计
   · all_verified = verified_count === total_docs
3. 用 Glob 查找项目文件夹下 `审核报告_*.html`，取最新一个作为 report_file
4. Read 技能目录 templates/launcher.html → 获取模板内容
5. 将模板中的 __PROJECT_DATA_PLACEHOLDER__ 替换为以下 JSON：
   {
     "project_name": "(从 index.json 获取)",
     "skill_version": "v8.8",
     "total_docs": N,
     "verified_count": N,
     "all_verified": true/false,
     "latest_batch": N,
     "new_count": N,
     "updated_at": "(从 index.json 获取)",
     "created_at": "(从 index.json 获取)",
     "fatal": N,
     "sanity_check": N,
     "best_practice": N,
     "report_file": "审核报告_xxx.html"
   }
6. Write 替换后的内容到 项目文件夹/数据底座/打开审核工具.html  （← 不是项目根目录！）
```

**嵌入数据示例**（AI 替换 `__PROJECT_DATA_PLACEHOLDER__` 为实际 JSON）：

```json
{
  "project_name": "XX机场碎石桩施工资料",
  "skill_version": "v8.8",
  "total_docs": 5,
  "verified_count": 3,
  "all_verified": false,
  "latest_batch": 2,
  "new_count": 2,
  "updated_at": "2026-08-05T15:00:00",
  "created_at": "2026-08-01T10:00:00",
  "fatal": 2,
  "sanity_check": 5,
  "best_practice": 3,
  "report_file": "审核报告_20260805_150000.html"
}
```

> **🔴 为什么用嵌入数据而不是 fetch()？** 因为 `file://` 协议下浏览器 CORS 会拦截 `fetch('./index.json')`（launcher 场景），导致入口页打开后显示"加载中…"或空白。v8.6 起改为数据嵌入，双击即用，零网络依赖。
> **🔴 v8.7 补充：data-editor（数据核对编辑器.html）内部仍用 fetch('./index.json') 自动加载同级数据，因为两者都在 数据底座/ 同一目录下，CORS 不拦截；fetch 失败时才回退手动选择按钮。**

- [ ] 八个静态资源（数据核对编辑器.html / 项目总览.html / 文档对齐视图.html / 规则管理工具.bat / tokens.css / pdf.min.js / pdf.worker.min.js / 打开审核工具.html）全部存在于「数据底座/」目录
- [ ] 项目根目录**不存在**任何 数据核对编辑器.html/项目总览.html/tokens.css/rule-editor.html 等模板文件
- [ ] `打开审核工具.html` 已生成，`__PROJECT_DATA_PLACEHOLDER__` 已替换为实际 JSON（包含 verified_count 和 all_verified 字段）
- [ ] 三步顺序：核对数据 → 查看报告 → 其他工具，且 all_verified=false 时查看报告按钮灰色禁用
- [ ] G-1.5 闸门：8 个文件全部存在于「数据底座/」 → 继续 I-5

---

### 增量 I-5：增量 OCR — 仅处理新增/修改文件

**根据 I-3 用户选择，确定处理范围**：

| 用户选择 | OCR 范围 |
|:---|:---|
| 🟢 增量审核 | 仅 ➕ 新增文件 + ✏️ 修改文件 |
| 🟡 全量重审 | ➕ 新增 + ✏️ 修改 + ⏺ 不变（复用已有 JSON，仅重跑规则） |
| 🔴 重建 | 全部文件重新 OCR |

**对需要 OCR 的文件，按步骤 3 的方法逐页提取**（参照新建路径步骤 3a~3e）。

**增量文件 JSON 输出**：
- 新增文件的 JSON 写入 `数据底座/{专业}/{类型}/{文件名}.json`
- 在 `index.json` 的 `documents` 数组中**追加新条目**（不覆盖已有条目）
- 新条目增加 `audit_batch` 字段，标记为当前批次（如 `"audit_batch": 2`）

**index.json 更新**：
- `updated_at` 更新为当前时间
- 新增文件的 `human_verified` 设为 `false`
- 不变文件的条目保持原样不动

- [ ] 新增/修改文件 OCR 完成，JSON 已生成
- [ ] index.json 已增量更新（追加新条目，不动老条目）
- [ ] 所有新增文件 `ocr_status = "completed"` → 继续 I-6

---

### 增量 I-6：闸门检查 + 硬停（G-1.9）

与新建路径步骤 8 相同，但检查范围**仅限本次新增文件**：

- [ ] **G-0**：index.json 存在且 documents 数组非空？→ 是
- [ ] **G-1**：本次新增文件 ocr_status 均为 "completed"？→ 是
- [ ] **G-1.5**：data-editor.html / tokens.css / 项目总览.html / pdf.min.js / pdf.worker.min.js / 打开审核工具.html 存在？→ 是
- [ ] **G-1.9 硬停**：输出以下内容后**立即停止本轮回复**，等用户"核对完成"：

```
✅ 增量数据底座更新完成（阶段 1 结束）

📊 本次变化：
  · 新增资料：{X} 份（{M} 页）
  · 不变资料：{Y} 份（跳过，数据复用）
  · 数据底座总计：{N} 份文档

⚠️ 扫描件待核实清单（仅新增资料，人工逐项确认）

{逐项列出新增资料中的扫描件存疑项：年份/桩号/签字/手写体}

📌 现在请你人工核对：
  · 打开项目文件夹下的「打开审核工具.html」→ 点击"数据核对编辑器"
  · 或直接告诉我哪条对、哪条错

🔒 我现在停下来等你。在你明确说"核对完成"或"开始审核"之前，我不会进行任何审核动作。
```

**硬停规则**（与新建路径 G-1.9 完全一致）：
- ❌ AI 不得自行判存疑项为"没问题"
- ❌ AI 不得自行标记 human_verified = true
- ❌ 只有用户说"核对完成/开始审核/可以审了/进入阶段 3"才能继续

- [ ] 全部闸门通过 + 已输出待核实清单 + 已硬停 → 增量阶段 1 完成

---

## 新建路径（index.json 不存在时）

逐项向用户确认以下信息，每项都必须有明确答案：

| # | 前置信息 | 询问方式 | 完成标准 |
|:---|:---|:---|:---|
| 1 | 项目阶段 | 问："资料处于什么阶段？基础/主体/分部分项验收/竣工归档？" | 用户明确回答 |
| 2 | 资料性质 | 问："资料是电子档、扫描件还是混合？" | 用户明确回答 |
| 3 | 审核范围 | 问："审核范围是全量还是按专业/分部分项？" | 用户明确回答 |
| 4 | OCR 引擎 | 原生模式下固定为"AGENT Vision" | 自动填入 |
| 5 | 特殊说明 | 问："有没有测试文档需要排除？有没有特殊要求？" | 用户确认（无则写"无"） |
| 6 | 签字检查 | 问："是否启用签字一致性检测？"（默认关闭） | 用户明确回答 |
| 7 | 签字标准 | 如果启用签字检查，问："签字判定标准是归档标准还是过程标准？" | 用户明确回答 |

- [ ] 6 项前置信息已全部收集 → 继续步骤 2

---

## 步骤 2：文件分类（必须用户确认）

1. 列出项目文件夹中所有文件
2. 将每个文件归类为以下三类之一：
   - **被审核资料**：施工记录、检验批、隐蔽工程记录等
   - **依据文件**：设计变更、施工日志（作为依据时）、图纸等
   - **排除文件**：测试文档、临时文件、非施工资料文件
3. 以表格形式展示分类结果，请用户确认

- [ ] 用户确认文件分类 → 继续步骤 3

---

## 步骤 3：逐文件数据提取（机械执行，不允许抽样）

> **🔴 强制规则：每份被审核资料必须逐页提取，不允许抽样。如果文件有 49 页，必须读完 49 页。**

### 对每份被审核资料，按以下子步骤执行：

#### 3a. 判断文件类型

- 文件扩展名是 `.pdf` → 进入 3b
- 文件扩展名是 `.xlsx` / `.xls` → 进入 3c
- 文件扩展名是 `.docx` / `.doc` → 进入 3d
- 文件是图片（`.png` / `.jpg` / `.jpeg`）→ 进入 3e

#### 3b. PDF 文件处理

1. 用 Read 工具读取 PDF 文件，判断是否为扫描件：
   - 能直接读取到文字内容 → 电子档 PDF，直接提取 full_text
   - 只能读取到乱码或无文字 → 扫描件 PDF
2. 如果是**电子档 PDF**：
   - 提取全部文字内容作为 full_text
   - 尝试解析表格数据为 structured_rows
   - 记录 page_map（每页的起止位置）
3. 如果是**扫描件 PDF**：
   - **逐页读取**：对每一页，用 Read 工具读取该页图片
   - 从图片中识别文字和表格数据
   - 每页识别结果记录为 structured_rows 中的对应行
   - 累计 full_text（所有页的纯文本拼接）
   - 记录 page_map（每页对应的行号范围）

#### 3c. Excel 文件处理

1. 用 Read 工具读取 Excel 文件
2. 列出所有 sheet 名称
3. 对每个 sheet，读取表格数据
4. 转换为 structured_rows 数组
5. full_text 为所有 sheet 内容的文本拼接

#### 3d. Word 文件处理

1. 用 Read 工具读取 docx 文件
2. 提取全部文字内容
3. 如有表格，解析为 structured_rows
4. full_text 为全部文字内容

#### 3e. 图片文件处理

1. 用 Read 工具读取图片
2. 从图片中识别文字和表格数据
3. 转换为 structured_rows 数组
4. full_text 为识别出的所有文字

- [ ] 所有被审核资料已逐页提取完成 → 继续步骤 4

---

## 步骤 4：生成结构化 JSON 数据文件

对每份被审核资料，生成一个 JSON 文件，保存到 `数据底座/` 目录下。

### JSON 文件命名规则

`{文件名}_{页码}页.json`

### JSON 文件必须包含的字段

```json
{
  "structured_rows": [
    {"字段1": "值1", "字段2": "值2", ...},
    ...
  ],
  "full_text": "全部文字内容...",
  "page_map": [
    {"page": 1, "start_row": 0, "end_row": 5},
    ...
  ],
  "metadata": {
    "original_file": "原始文件名.pdf",
    "is_scanned": true,
    "page_count": 49,
    "extraction_mode": "ai_vision",
    "ocr_engine": "AGENT Vision",
    "ocr_confidence": 0.95,
    "extracted_at": "2026-08-04T12:00:00"
  }
}
```

### 使用 Write 工具写入文件

每份文档的 JSON 写入路径：`{项目文件夹}/数据底座/{文件名}.json`

- [ ] 所有被审核资料的 JSON 文件已生成 → 继续步骤 5

---

## 步骤 5：生成 index.json 总索引

创建 `{项目文件夹}/数据底座/index.json`，包含以下结构：

```json
{
  "project_name": "项目名称",
  "created_at": "2026-08-04T12:00:00",
  "updated_at": "2026-08-04T12:00:00",
  "mode": "native",
  "status": "stage1_completed",
  "preconditions": {
    "stage": "分部分项验收",
    "nature": "扫描件",
    "scope": "全量审核",
    "ocr_engine": "AGENT Vision",
    "special_notes": "无",
    "check_signatures": false
  },
  "documents": [
    {
      "id": "DOC-001",
      "file": "碎石桩施工记录.pdf",
      "type": "施工记录",
      "professional": "场道工程",
      "pages": 49,
      "ocr_status": "completed",
      "ocr_confidence": 0.95,
      "data_file": "碎石桩施工记录_49页.json",
      "issues_found": 3,
      "needs_review": false,
      "human_verified": false,
      "last_updated": "2026-08-04T12:00:00"
    }
  ],
  "gaps": [],
  "quality_alerts": []
}
```

### 填写规则

| 字段 | 填写规则 |
|:---|:---|
| `id` | DOC-001, DOC-002, ... 按文件顺序编号 |
| `file` | 原始文件名 |
| `type` | 施工记录 / 检验批 / 隐蔽工程 / 监理通知单 / 其他 |
| `professional` | 场道工程 / 空管工程 / 助航工程 / 弱电工程 / 供油工程 |
| `pages` | 实际页数 |
| `ocr_status` | 全部设为 "completed" |
| `ocr_confidence` | 整体置信度估算（0.0~1.0），手写多则降低 |
| `data_file` | 对应步骤 4 生成的 JSON 文件名 |
| `issues_found` | 质量告警数量（步骤 6 填充） |
| `human_verified` | 全部设为 false（阶段 2 才改为 true） |

- [ ] index.json 已生成，所有 documents 条目完整 → 继续步骤 6

---

## 步骤 6：生成质量告警

对每份文档的 structured_rows 进行以下 4 类检查，告警结果填入 index.json 的 quality_alerts 数组：

### DQ-1 重复值检测
- 检查每列的不重复值数量
- 如果某列只有 2 个值且交替出现 → 告警

### DQ-2 突变检测
- 检查相邻行数值变化
- 变化率超过 30% → 告警

### DQ-3 涂改痕迹检测
- 检查是否有明显涂改痕迹
- 如果有 → 告警

### DQ-4 数据自洽检测
- 检查相关字段是否自洽（如桩长 = 桩顶 - 桩底）
- 不自洽 → 告警

每条告警格式：
```json
{
  "alert_id": "DQ-001",
  "type": "DQ-1",
  "document_id": "DOC-001",
  "severity": "high",
  "description": "桩号列仅 2 个值交替出现，疑似造假",
  "field": "桩号",
  "rows": [1, 2, 3, 4, 5]
}
```

- [ ] 所有文件的质量告警已生成，已填入 index.json → 继续步骤 7

---

## 步骤 7：复制 Web 模板 + 生成入口导航页（必须执行，不可跳过）

> **🔴 v8.7 更新强制规则：必须将模板文件部署到「**项目文件夹/数据底座/**」子目录，禁止模板出现在项目文件夹根目录！用户入口模板必须中文命名；低频工具（rule-editor/feedback-collector）不复制。**

### 7a：复制静态模板（中文命名 + 复制到「数据底座/」）

**🔴 第一步：先检查并清理项目根目录的历史模板**（v8.7 之前版本可能漏拷在根目录）：
用 LS 列出项目文件夹根目录，如发现以下文件，**必须立即删除**（保留数据底座/ 中的正确版本）：
- data-editor.html、项目总览.html、打开审核工具.html、tokens.css、pdf.min.js、pdf.worker.min.js、rule-editor.html、feedback-collector.html

从技能的 `templates/` 目录读取以下文件，Write 到**「项目文件夹/数据底座/」子目录**（不是项目根目录！）：

| # | 源文件（技能 templates/ 目录下） | 目标文件名（写入「项目文件夹/数据底座/」） | 用途 |
|:---|:---|:---|:---|
| 1 | `data-editor.html` | **`数据核对编辑器.html`**（中文命名，v8.7） | 阶段 2 人工核对：左图右表，含自动加载同级 index.json + localStorage 项目名记忆 |
| 2 | `project-dashboard.html` | **`项目总览.html`**（中文命名，v8.7） | 项目总览仪表盘：数据进度 + 告警统计 + 文档列表 |
| 3 | `alignment-view.html` | **`文档对齐视图.html`**（中文命名，v8.7） | 监理-施工方跨单位资料对照视图（9.10 逻辑一致性检查用） |
| 4 | `tokens.css` | `tokens.css` | 统一设计令牌（所有 HTML 模板依赖） |
| 5 | `pdf.min.js` | `pdf.min.js` | PDF.js 离线主库（data-editor.html 依赖） |
| 6 | `pdf.worker.min.js` | `pdf.worker.min.js` | PDF.js 离线 Worker（data-editor.html 依赖） |
| 7 | `rule-manager.bat`（或技能根同名文件） | **`规则管理工具.bat`**（中文命名，v8.7） | 规则管理启动器：三级路径自动定位 skill 安装目录，双击打开完整版 rule-manager.html |

**低频工具白名单（必须不复制）：**
以下文件仅存在于 skill 根目录 `templates/`，**禁止复制到任何项目目录**（含根目录和数据底座/）：
- ❌ rule-editor.html（低频规则编辑，仅管理员用）
- ❌ feedback-collector.html（低频反馈收集，仅 skill 管理员用）

**执行方法**：对每个白名单文件（#1~#7），Read 源文件 → Write 到 `项目文件夹/数据底座/{中文目标名}`。

### 7b：生成 `打开审核工具.html`（三步指引 + 数据嵌入，非纯拷贝）

> **🔴 不能直接拷贝 launcher.html！** 模板中的 `__PROJECT_DATA_PLACEHOLDER__` 必须替换为实际项目数据。用嵌入数据而非 fetch()，因为 `file://` 协议下浏览器 CORS 会拦截 fetch 请求。
> **🔴 v8.7 三步指引强制顺序**：从上到下必须是「步骤 1：核对数据 → 步骤 2：查看报告 → 步骤 3：其他工具」，不允许调换或平行排列。
> **🔴 v8.7 报告按钮禁用规则**：documents[].human_verified 未全部 true 时，步骤 2「查看报告」按钮必须**灰色禁用**，并加上 tooltip：「请先完成步骤 1，核对所有资料后再查看报告」。

**机械化执行流程**：

```
1. 从步骤 5 已生成的 index.json 中提取数据：
   · project_name
   · documents 数组 → total_docs = documents.length
   · verified_count = documents.filter(d => d.human_verified === true).length
   · all_verified = verified_count === total_docs
   · 按 audit_batch 分组 → latest_batch, new_count
   · audit_summary 或 quality_alerts 统计 → fatal, sanity_check, best_practice
   · updated_at, created_at
2. 用 Glob 查找项目文件夹下 审核报告_*.html，取最新一个作为 report_file
   （首次审核此时报告尚未生成，report_file 设为 null）
3. Read 技能目录 templates/launcher.html
4. 将 __PROJECT_DATA_PLACEHOLDER__ 替换为实际 JSON：
   {
     "project_name": "...",
     "skill_version": "v8.8",
     "total_docs": N,
     "verified_count": N,
     "all_verified": true/false,
     "latest_batch": 1,
     "new_count": N,
     "updated_at": "...",
     "created_at": "...",
     "fatal": 0,
     "sanity_check": 0,
     "best_practice": 0,
     "report_file": null
   }
5. Write 替换后的内容到 项目文件夹/数据底座/打开审核工具.html  （← 是「数据底座/」，不是项目根目录！）
```

### 技能目录定位方法

- 技能目录是 `SKILL.md` 所在的文件夹
- **v8.7 规则管理工具三级路径自动定位（规则管理工具.bat 已内置）**：
  1. 第 1 级：当前目录（.bat 所在目录）查找 SKILL.md
  2. 第 2 级：上级目录（..）查找 SKILL.md
  3. 第 3 级：全局 Skill 安装路径（如 `%APPDATA%\..\Local\Trae\skills\`、`%USERPROFILE%\.trae\plugins\` 等常见位置）
  4. 找到后打开 `templates/rule-manager.html`；都找不到时红色中文报错不退出
- 如果 AI 无法确定技能目录路径，询问用户："技能安装在哪个目录？请提供 SKILL.md 所在的文件夹路径。"

### 完成验证

用 LS 列出**「项目文件夹/数据底座/」子目录**（不是根目录！），确认：
- [ ] `数据核对编辑器.html` 存在
- [ ] `项目总览.html` 存在
- [ ] `文档对齐视图.html` 存在
- [ ] `规则管理工具.bat` 存在
- [ ] `tokens.css` 存在
- [ ] `pdf.min.js` 存在
- [ ] `pdf.worker.min.js` 存在
- [ ] `打开审核工具.html` 存在（`__PROJECT_DATA_PLACEHOLDER__` 已替换为实际 JSON，含 verified_count/all_verified 字段）
- [ ] 三步指引顺序正确：核对数据 → 查看报告 → 其他工具
- [ ] all_verified=false 时，查看报告按钮灰色禁用 + tooltip 说明

**同时执行反向验证（禁止项）：**
用 LS 列出**项目文件夹根目录**，确认：
- [ ] ✅ 项目根目录**不存在** 数据核对编辑器.html / data-editor.html
- [ ] ✅ 项目根目录**不存在** 项目总览.html / tokens.css / pdf.min.js / pdf.worker.min.js / 打开审核工具.html
- [ ] ✅ 项目任何位置（根目录+数据底座/）**不存在** rule-editor.html / feedback-collector.html

- [ ] 以上 8 个文件在「数据底座/」全部就位 + 反向验证 3 项全部通过 → 继续步骤 8

---

## 步骤 8：闸门检查（G-0、G-1、G-1.5）+ 硬停输出（G-1.9）

在进入阶段 2 之前，必须通过以下检查：

- [ ] **G-0**：index.json 文件存在？→ 是
- [ ] **G-0**：index.json 中 documents 数组非空？→ 是
- [ ] **G-1**：所有 documents[].ocr_status 均为 "completed"？→ 是
- [ ] 所有 documents 的 data_file 指向的 JSON 文件都存在？→ 是
- [ ] **G-1.5**（v8.7 更新）：「项目文件夹/数据底座/」目录下 数据核对编辑器.html 存在？→ 是
- [ ] **G-1.5**（v8.7 更新）：「项目文件夹/数据底座/」目录下 项目总览.html 存在？→ 是
- [ ] **G-1.5**（v8.7 更新）：「项目文件夹/数据底座/」目录下 文档对齐视图.html 存在？→ 是
- [ ] **G-1.5**（v8.7 更新）：「项目文件夹/数据底座/」目录下 规则管理工具.bat 存在？→ 是
- [ ] **G-1.5**（v8.7 更新）：「项目文件夹/数据底座/」目录下 tokens.css 存在？→ 是
- [ ] **G-1.5**（v8.7 更新）：「项目文件夹/数据底座/」目录下 pdf.min.js 存在？→ 是
- [ ] **G-1.5**（v8.7 更新）：「项目文件夹/数据底座/」目录下 pdf.worker.min.js 存在？→ 是
- [ ] **G-1.5**（v8.7 更新）：「项目文件夹/数据底座/」目录下 打开审核工具.html 存在？→ 是
- [ ] **G-1.5 反向**（v8.7 新增）：项目文件夹根目录**不存在**任何 数据核对编辑器.html/tokens.css/项目总览.html 等模板文件？→ 是

### 如果 G-0、G-1 或 G-1.5 未通过

- G-0 或 G-1 未通过 → 回到对应步骤重新执行
- G-1.5 未通过 → 回到步骤 7 重新复制模板文件
- 三次重试仍失败 → 告知用户："数据底座建立失败，原因：XXX。建议切换到有 Python 环境的平台执行引擎模式。"

### 如果全部通过 → G-1.9 硬停（最高优先级，不可跳过）

> **🔴 强制规则：阶段 1 完成 = AI 必须立即停止输出。禁止自行进入阶段 2 展示数据、禁止自行判断"没问题"、禁止推进到阶段 3 审核或生成报告。必须输出"扫描件待核实清单"后真正停下来，等待用户逐项人工核实。**

AI 必须按以下格式输出，然后**停止本轮回复**（不得继续往下写任何审核内容）：

```
✅ 数据底座建立完成（阶段 1 结束）

📊 数据底座概览：
  · 项目文件夹：{项目文件夹路径}
  · 被审核资料：{N} 份，共 {M} 页
  · 扫描件：{S} 份（必须人工逐页核实）
  · 电子档：{E} 份
  · 质量告警：{K} 条
  · index.json：已生成
  · 打开审核工具.html：项目控制面板已就绪（双击「数据底座/打开审核工具.html」打开即用）

⚠️ 扫描件待核实清单（人工逐项确认，未确认前不进入审核）

本批资料含 {S} 份扫描件，AGENT Vision 识别结果仅供参考，以下存疑项必须人工核实：

| # | 文档 | 页码 | 字段 | AI 识别值 | 存疑原因 | 核实状态 |
|:---:|:---|:---:|:---|:---|:---|:---:|
| 1 | {文件名} | 第X页 | 年份 | 2026 | 手写体易误读（6/0/8混淆） | ⬜ 待核实 |
| 2 | {文件名} | 第X页 | 桩号 | Z360 | 手写 Z/D/4 混淆 | ⬜ 待核实 |
| 3 | {文件名} | 第X页 | 签字 | 张某 | 签字潦草难辨 | ⬜ 待核实 |
| ... | ... | ... | ... | ... | ... | ... |

【质量告警项也需人工核实】
{逐条列出 DQ-1~DQ-4 告警，标注涉及的文档和行，请用户确认是真问题还是 OCR 误读}

📌 现在请你人工核对：
  · 方式一（推荐，零 token）：双击项目文件夹下「**数据底座/打开审核工具.html**」→ 步骤 1「核对数据」大按钮，进入数据核对编辑器（已自动加载同级 index.json）
  · 方式二：直接在对话里逐份告诉我哪条对、哪条错，我帮你改

🔒 我现在停下来等你。在你明确说"核对完成"或"开始审核"之前，我不会进行任何审核动作，也不会生成报告。
```

### 硬停判定标准（G-1.9）

满足以下任一条，即视为 AI 违反硬停规则，输出无效：
- ❌ AI 没有输出上述"扫描件待核实清单"就继续往下走
- ❌ AI 自行把存疑项判定为"没问题"并标记 human_verified = true
- ❌ AI 在用户未回复"核对完成"前，就开始阶段 3 审核或生成报告
- ❌ AI 把扫描件和非扫描件混在一起，没有单独列出扫描件存疑项

### 唯一允许继续的信号

只有当用户**明确**说出以下任一指令，AI 才能离开硬停、进入阶段 3：
- "核对完成" / "已核对完" / "开始审核" / "可以审了" / "进入阶段 3"

若用户只核对了部分文件，AI 仍不得继续，必须提示："还有 {X} 份未核对，请继续核对后再开始审核。"

- [ ] 全部闸门通过 + 已输出待核实清单 + 已明确告知用户"我现在停下来等你" → 阶段 1 完成（AI 本轮结束）

---

## 附录：AI 自检清单（阶段 1 输出前必查）

在告知用户"数据底座建立完成"之前，AI 必须逐条确认：

- [ ] 我是否逐页读取了所有被审核资料？（不允许抽样）
- [ ] 每份资料的 JSON 文件是否已通过 Write 工具写入磁盘？
- [ ] index.json 是否包含所有被审核资料的条目？
- [ ] 质量告警是否已填入 index.json？
- [ ] **（v8.7）我是否已将 数据核对编辑器.html、项目总览.html、文档对齐视图.html、规则管理工具.bat、tokens.css、pdf.min.js、pdf.worker.min.js、打开审核工具.html 复制到「**项目文件夹/数据底座/**」子目录？（禁止放项目根目录）**
- [ ] **（v8.7）项目文件夹根目录是否不存在任何 data-editor.html/项目总览.html/tokens.css/rule-editor.html 等模板文件？（必须反向验证）**
- [ ] **（v8.7）打开审核工具.html 的三步顺序是否正确？核对数据 → 查看报告 → 其他工具，且 all_verified=false 时查看报告按钮灰色禁用**
- [ ] **（v8.7）OCR 引擎是否按前置信息用户选择执行？（auto/vision/paddle/agent 四选一，无可用引擎不得硬降级）**
- [ ] 我是否确认了 Python 不可用、未尝试调用任何 Python 脚本？
- [ ] **我是否单独列出了扫描件待核实清单（年份/桩号/签字等存疑项），而不是把扫描件和非扫描件混在一起？**
- [ ] **我是否在输出末尾明确告知用户"我现在停下来等你"，并且真的停下来了（没有继续写审核内容）？**
- [ ] **我是否避免了自行把存疑项判定为"没问题"并标记 human_verified = true？**