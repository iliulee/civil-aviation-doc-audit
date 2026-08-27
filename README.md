# 🛫 民航施工资料合规审核大师

> **civil-aviation-doc-audit** · v10.5
> 面向民航专业工程施工资料的自动化合规审核引擎，覆盖场道 / 空管 / 助航 / 弱电 / 供油五大专业，按 MH/T 5078 规范逐条对账，输出可追溯的三级审核结论。

---

## 这个项目解决什么问题

民航专业工程施工资料（检验批、施工记录、试验检测报告、物资进场检验等）移交归档前，需要逐条核对规范要求。人工核对量大、易漏、结论难追溯。

本 skill 把这一过程做成**半自动、可验证、可追溯**的流水线：

- 自动解析 PDF / 扫描件 / Excel / Word 资料，识别字段并沉淀为结构化数据底座；
- 按 MH/T 5078 系列规范对数据逐条**规范对账**，引用条款号可回溯原文；
- 跨资料做**逻辑一致性专项检查**（时间轴、数量累计、人员交叉、签字、因果、规范引用、试验检测）；
- 输出三级结论（**高 / 中 / 低 / 存疑**），每条意见都带"规范号 + 条款号 + 原文关键要求"完整依据；
- 证据不实、备案造假嫌疑的，**拒绝背书并明确指出**。

## 核心特性

| 能力 | 说明 |
| --- | --- |
| 🛡️ 规范逐条对账 | 按 MH/T 5078 各分部精确匹配条款，引用可回溯原文，杜绝条款号幻觉 |
| 🔍 OCR 混合识别 | 扫描件 OCR + 表格结构解析，识别结果强制人工复核，`human_verified` 未全绿不出报告 |
| 🧩 规则引擎 | 三层规则库（L1 铁律 / L2 逻辑 / L3 业务），SINGLE_DOC / CROSS_DOC / CROSS_UNIT 立体判定 |
| 🚦 无规则覆盖闸门 | 运行时自动侦测无规则兜底的文档类型并显式提醒，杜绝"静默裸检" |
| ✅ 三级结论分级 | 高 / 中 / 低 / 存疑，存疑项不下确定性结论，标注"建议现场验证" |
| 🔁 数据质量先于合规 | 先做数据真实性审查，再做规范对账；逻辑一致性在 ≥2 份资料时自动启动 |
| 📝 全程留痕 | 每次审核生成可追溯日志 + 独立只读复核意见落盘 |
| 🧪 隐患销号测试体系 | 每个已查实根因固化为一条回归测试，一条命令全量验收，防复发 |

## 目录结构

```
civil-aviation-doc-audit/
├── SKILL.md               # 技能装载入口（Trae 装载路径固定于此，不可挪动）
├── README.md              # skill 内部说明文档
├── PROJECT_SPEC.md        # 项目规格与实施记录
├── scripts/               # 核心引擎：解析 / 规则对账 / 报告生成 / 测试套件
├── rules/                 # 三层规则库（L1-iron / L2-logic / L3-business）+ registry
├── references/            # 五大专业审核指引、规范目录、报告模板
├── templates/             # 工作台 HTML 模板（数据编辑器 / 规则管理 / 项目总览等）
├── data/                  # 规范条款索引（clause_index / catalog_index）
├── src/ + workbench/      # 资料员工作台前端源码与构建产物
├── evals/                 # 行为评测用例（evidence / safety 边界）
└── 启动工作台.bat          # 工作台启动脚本
```

> 技能正主唯一来源为 `.trae/skills/civil-aviation-doc-audit/`（Trae 装载路径），部署与 Git 均以此为单一事实源。

## 快速开始

```powershell
# 1. 安装依赖（Python 3.12+）
pip install -r requirements.txt

# 2. 一键验收（全绿 = 可交付）
python scripts/run_all_tests.py

# 3. 运行一次完整审核（四阶段流水线，含人工核对闸门）
python scripts/run_audit.py --input <资料目录或数据底座>
```

> 生产环境禁止 `--force`，防止绕过人工核对闸门。任何包含 ≥2 份资料的审核，强制走四阶段流水线。

## 一键验收

```powershell
python scripts/run_all_tests.py
```

任何改动后跑一遍：全绿 = 可交付，哪条红 = 问题一眼看到。测试套件固化每个已查实根因，防复发。

## 文档

- 项目规格与实施记录：[`PROJECT_SPEC.md`](.trae/skills/civil-aviation-doc-audit/PROJECT_SPEC.md)
- 变更日志：[`references/CHANGELOG.md`](.trae/skills/civil-aviation-doc-audit/references/CHANGELOG.md)
- 技能装载说明：[`SKILL.md`](.trae/skills/civil-aviation-doc-audit/SKILL.md)

## 版本历史

- **v10.5** — 无规则覆盖运行时闸门 + 文档升版
- **v10.4** — 规则—报告链路贯通与报告构建器修复
- **v10.0** — 资料员工作台（数据编辑器 / 项目总览 / 规则管理）
- **v5.0** — 四阶段流水线与人工核对闸门落地

## 许可证

遵循民航专业工程资料管理相关规范与项目自有约定。