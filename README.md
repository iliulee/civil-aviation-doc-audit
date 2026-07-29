# 民航建设施工资料合规审核大师 (civil-aviation-doc-audit)

> 民航工程施工资料合规性审核 Skill v2.0
> 适用：MH/T 5078.1~5078.6-2024 系列 + CCAR-165-R1 + MH 5031-2025 等民航规范
> 五大专业全覆盖：场道 / 空管 / 助航 / 弱电 / 供油

---

## 目录结构

```
civil-aviation-doc-audit/
├── SKILL.md                          # 主 Skill 文件（必读）
├── README.md                         # 本文件
├── requirements.txt                  # Python 依赖
├── install.ps1                       # 一键安装脚本（Python+PaddleOCR+Poppler+Tesseract）
├── audit.bat                         # Windows 快捷入口
├── .gitignore
│
├── references/                       # 14 个参考文件
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
│   ├── document-templates.md         # 审核报告/日志模板
│   └── html-report-template.html     # HTML 报告标准模板
│
├── scripts/                          # 5 个脚本
│   ├── run_audit.py                  # Skill 入口（一键启动审核）
│   ├── extract_pdf.py                # PDF 文字提取（PyMuPDF）
│   ├── ocr_image.py                  # 扫描件 OCR（PaddleOCR 单层主引擎 + Tesseract/Vision 显式兜底）
│   ├── postprocess.py                # 文本后处理（全角转半角、PUA 替换）
│   └── data_quality_check.py         # 数据质量检测（铁律 10 配套）
│
├── templates/
│   └── audit-scope-template.html     # 审核范围模板
│
└── test/                             # 测试样本（.gitignore 排除）
    └── sample_5078_1.*
```

---

## 核心能力

| 能力 | 说明 |
|------|------|
| OCR 识别扫描件 | PaddleOCR 单层主引擎（官方参数优化，适配手写中文）→ Tesseract（显式备选）→ Vision API（第三层兜底） |
| 规范逐条对账 | 对着 MH/T 5078 系列逐条比对，每条引规范编号和条款号 |
| 数据质量检测 | 自动识别造假、涂改、异常模式（DQ-REPEAT/JUMP/ALTER/SELF） |
| 逻辑一致性检查 | 10 个子项 57+ 条规则，含监理-施工方跨单位日期对照（9.10，17 条规则） |
| 运算规范审核 | 只做规范性检查，不做数值复算 |
| 自动生成审核报告 | 三级输出：🔴Fatal / 🟡Sanity Check / 🔵Best Practice |
| 知识分区红线 | 三条红线防幻觉，推理边界决策树，输出前自检清单 |

---

## 快速使用

### 1. 安装依赖

```powershell
# 一键安装（Python 依赖 + Poppler + Tesseract）
.\install.ps1
```

或手动安装：

```bash
pip install -r requirements.txt
```

### 2. 验证 Skill 可用

```bash
# 识别单份资料
python scripts/run_audit.py info "H:\path\to\检验批.pdf"

# 批量识别目录下所有资料
python scripts/run_audit.py batch "H:\path\to\资料目录"

# 提取文字（自动判断是否扫描件）
python scripts/run_audit.py extract "H:\path\to\检验批.pdf" --out 检验批.txt
```

### 3. 在 AI 对话中触发

典型触发语句（任一即可）：

- "审核这份检验批 / 监理通知单 / 施工日志 / 竣工图"
- "看看这份资料有没有逻辑矛盾"
- "按 MH/T 5078.1 审这份技术交底"
- "场道土石方分项的检验批批量审核"
- "高填方沉降计算书运算审核"
- "生成整改通知书"
- "这是扫描件，做 OCR 后审核"
- "安装这个skill" / "安装依赖" / "初始化"

---

## 知识库连接

| 来源 | 角色 | 覆盖范围 |
|------|------|---------|
| `references/`（内置） | 高速缓存层 | 14 个文件，100+ 条检查项，200+ 个参数阈值 |
| Obsidian vault（外部） | 规范原文库 | 200+ 个规范 markdown 文件，MH/T 5078.1~5078.6 全覆盖 + 石化国标 + 设备规范 |

查询优先级：references 缓存（80%条款直接覆盖）→ Obsidian 回源读原文（3~5次/审核）→ 标注"无规范原文支撑"（禁止 WebSearch 兜底）

---

## 铁律体系（v1.9）

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
| 9 | **逻辑矛盾专项** | 10 个子项 57+ 条规则，含监理-施工方跨单位对照 |
| 10 | **数据质量前置** | 规范对账前先做 4 类数据质量检测 |
| 11 | **全列提取** | 结果列+计算列一起读 |
| 12 | **高程自洽** | 实长 = 桩顶高程 − 桩底高程 |
| 13 | **缺合计行判定** | 无合计行 = 资料非原始记录 |
| 14 | **多参数联检** | 实长/灌入量/充盈系数同时校验 |
| 15 | **原始底稿追溯** | 多资料矛盾时追溯原始记录 |
| 16 | **提取-验证-重试** | 提取后先做行数校验 |
| 17 | **合计值反向验证** | 施工日志合计值 → 与施工记录逐项核对 |
| 18 | **置信度分级** | 高/中/低/存疑，存疑不下确定性结论 |
| 19 | **用户标记闭环** | 追溯AI为什么没发现，补充检测规则 |

### 铁律 9 子项（v1.9 升级）

| 子项 | 检查内容 |
|------|---------|
| 9.1 | 时间轴一致性（8 条规则） |
| 9.2 | 数量累计一致性（6 条规则） |
| 9.3 | 人员交叉一致性（6 条规则） |
| 9.4 | 状态描述一致性（4 条规则） |
| 9.5 | 签字一致性（4 条规则） |
| 9.6 | 因果逻辑一致性（7 条规则） |
| 9.7 | 规范引用一致性（3 条规则） |
| 9.8 | 试验检测逻辑一致性（4 条规则） |
| 9.9 | 跨资料合计值反向验证（3 条规则） |
| **9.10** | **监理-施工方跨单位日期对照（17 条规则，自动触发）** |

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
| v1.0 | 2026-07-24 | 初始版本，8 步工作流 + 9 条铁律 |
| v1.1 | 2026-07-24 | 新增铁律 10（数据质量审查）+ 4 个检测脚本 |
| v1.2 | 2026-07-24 | 安装脚本 + GitHub 仓库 |
| v1.3 | 2026-07-24 | 新增铁律 11~15 |
| v1.4 | 2026-07-24 | 新增铁律 16~19 |
| v1.5 | 2026-07-25 | 五大专业专项审核文件补全（场道/空管/助航/弱电/供油） |
| v1.6 | 2026-07-25 | HTML 报告标准模板，统一交付物 |
| v1.7 | 2026-07-25 | 前置信息收集 + 文件分类确认 + 批量审核汇总 |
| v1.8 | 2026-07-26 | 三层 9 步工作流重构 |
| v1.9 | 2026-07-27 | 三级 OCR 策略（RapidOCR）、知识分区红线、三级输出格式、9.10 监理-施工方对照、Obsidian 知识库全量覆盖 |
| v2.0 | 2026-07-29 | OCR 引擎重构：PaddleOCR 单层主引擎 + Vision API 第三层兜底；彻底移除 RapidOCR；官方参数优化提速 |
