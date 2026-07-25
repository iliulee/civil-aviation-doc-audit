# 民航建设施工资料合规审核大师 (civil-aviation-doc-audit)

> 民航工程施工资料合规性审核 Skill v1
> 适用：MH/T 5078.1~5078.6-2024 系列 + CCAR-165-R1 等民航规范

---

## 目录结构

```
civil-aviation-doc-audit/
├── SKILL.md                       # 主 Skill 文件（必读）
├── requirements.txt               # Python 依赖
├── references/                    # 8 个参考文件
│   ├── audit-checklists.md        # 分专业审核检查清单
│   ├── specification-mapping.md   # 资料类型→规范条款映射
│   ├── specification-quick-reference.md  # 规范条款速查表
│   ├── calculation-standards.md   # 运算规范性审核（不替设计复算）
│   ├── airfield-engineering-audit.md  # 场道工程专项要点
│   ├── high-frequency-errors.md   # 高频错误模式库
│   ├── logic-conflict-patterns.md # 逻辑矛盾识别模式库（铁律 9）
│   └── document-templates.md      # 审核报告/整改通知/日志模板
└── scripts/                       # 4 个集成脚本
    ├── run_audit.py               # Skill 入口（一键启动审核）
    ├── extract_pdf.py             # PDF 文字提取（PyMuPDF）
    ├── ocr_image.py               # 扫描件 OCR（Tesseract）
    └── postprocess.py             # 文本后处理（全角转半角、PUA 替换）
```

---

## 快速使用

### 1. 安装依赖

```bash
pip install -r requirements.txt

# Windows 还需要单独安装 Tesseract 引擎本体
# https://github.com/UB-Mannheim/tesseract/wiki
# 安装时勾选 Chinese (Simplified) + English
```

### 2. 验证 Skill 可用

```bash
# 识别单份资料
python scripts/run_audit.py info "H:\path\to\检验批.pdf"

# 批量识别目录下所有资料
python scripts/run_audit.py batch "H:\path\to\资料目录"

# 提取文字（自动判断是否扫描件）
python scripts/run_audit.py extract "H:\path\to\检验批.pdf" --out 检验批.txt

# 清洗乱码文本
python scripts/run_audit.py postprocess 检验批.txt
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

---

## 19 条铁律速查

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
| 9 | **逻辑矛盾专项** | ⭐ ≥2 份资料必查 9 维一致性 |
| 10 | **数据质量前置** | 规范对账前先做 4 类数据质量检测 |
| 11 | **全列提取** | 结果列+计算列一起读，不读计算列不得跨资料对比 |
| 12 | **高程自洽** | 实长 = 桩顶高程 − 桩底高程，误差 > 2m = 数据被修改 |
| 13 | **缺合计行判定** | 无合计行 = 资料非原始记录，可能是誊抄件 |
| 14 | **多参数联检** | 实长/灌入量/充盈系数同时校验，造假者只改一个会漏其他 |
| 15 | **原始底稿追溯** | 多资料矛盾时，按"三个一致"原则追溯原始记录 |
| 16 | **提取-验证-重试** | 提取后先做行数校验，不通过自动触发生成提取 |
| 17 | **合计值反向验证** | 施工日志有合计值 → 与施工记录逐项核对 |
| 18 | **置信度分级** | 审核结论分四级：高/中/低/存疑，存疑不下确定性结论 |
| 19 | **用户标记闭环** | 用户标记的问题必须追溯AI为什么没发现，补充检测规则 |

---

## 触发逻辑矛盾专项检查的情形（铁律 9）

满足任一即触发：

- 多份资料时间轴需对齐（施工日志 vs 监理日志 vs 检验批 vs 材料报审）
- 工程量累计需吻合（材料报审 vs 施工记录 vs 检验批 vs 结算）
- 同一工序多专业人员签字
- 同一对象多份报告（材料复试 vs 施工配合比 vs 施工记录）
- 前后资料引用同一规范/图纸版本
- 试验/检测数据需与施工工况匹配
- 隐蔽/签认需与后续工序时间匹配
- 整改前后资料需闭环

详见 `references/logic-conflict-patterns.md`。

---

## 8 维度输入兼容

| 输入形式 | 入口 |
|---------|------|
| 单份 PDF 资料 | 从第 1 步格式识别开始 |
| 扫描件图片 | 从第 1 步→触发 OCR |
| 多份资料成批 | 从第 1 步→批量识别→批量审核 |
| 指定条款/分部分项 | 跳到第 3 步精准定位 |
| 资料 + 计算书 | 启动运算审核（仅规范性） |
| 仅做合规性核对 | 输出合规性检查清单（不生成整改通知） |
| 资料 + 历史审核记录 | 触发复查 / 整改闭环验证 |
| 资料 + 飞书/MCP 集成 | 通过 lark-cli 上传/通知 |

---

## 输出物

| 模板 | 编号 | 触发条件 | 归档路径 |
|------|------|---------|---------|
| 审核报告 | AU-YYYYMMDD-XXX | 单次审核完成 | `d:\2026年7月22日 民航资料skill\reports\` |
| 整改通知书 | ZG-YYYYMMDD-XXX | 发现不符合项 | 同上 |
| 合规性检查清单 | CL-YYYYMMDD-XXX | 仅做合规核对 | 同上 |
| 批量审核汇总报告 | BAT-YYYYMMDD-XXX | 批量审核 | 同上 |
| 审核日志 | LOG-YYYYMMDD-HHMMSS | 每次审核 | 同上 |
| 中间产物 | — | 全过程 | `c:\Users\Administrator\.trae-cn\work\...\audit_YYYYMMDD\` |

详见 `references/document-templates.md`。

---

## GitHub 仓库

```bash
# 仓库地址（私有）
https://github.com/iliulee/civil-aviation-doc-audit

# 克隆到本地
git clone https://github.com/iliulee/civil-aviation-doc-audit.git
```

## 更新 Skill

### 日常更新流程

```bash
# 1. 修改文件后，查看变动
git status

# 2. 暂存改动
git add -A

# 3. 提交（用中文写清楚改了啥）
git commit -m "feat: 新增XXX功能 / fix: 修复XXX问题"

# 4. 推送
git push
```

### 版本号规则

- **v1.0.x**：初始版本，小修小补
- **v1.1.x**：新增功能（PaddleOCR、自动复查、飞书集成等）
- **v2.x**：模板生成、AI 自学习等大版本

### 更新什么内容

以下内容应纳入版本管理：

| 应提交 | 不应提交 |
|--------|---------|
| `SKILL.md` / `README.md` | `audit_output/`（审核报告，每次生成不同）|
| `references/` 下所有 .md | `tools/poppler/`（二进制，手动下载）|
| `scripts/` 下所有 .py | `__pycache__/` |
| `requirements.txt` | `_scanned.*`（测试临时文件）|
| `.gitignore` | |

## 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-07-24 | 初始版本，8 步工作流 + 9 条铁律 |
| v1.1 | 2026-07-24 | 新增铁律 10（数据质量审查）+ 4 个检测脚本 |
| v1.2 | 2026-07-24 | 安装脚本 + GitHub 仓库 + 更新工作流 |
| v1.3 | 2026-07-24 | 新增铁律 11~15（高程自洽/全列提取/缺合计行判定/多参数联检/原始底稿追溯），补充 Z418 和缺合计行真实案例 |
| **v1.4** | **2026-07-24** | **新增铁律 16~19（提取-验证-重试/跨资料合计值验证/置信度分级/用户标记闭环），补充对应参考文件，更新工作流** |

## v1 vs v1.1 能力边界

| 能力 | v1 | v1.1 |
|------|-----|------|
| 中文 PDF 文字提取 | ✅ PyMuPDF | + PaddleOCR |
| 扫描件 OCR | ✅ Tesseract | + PaddleOCR |
| 逻辑矛盾 8 维检查 | ✅ | + |
| 运算规范性审核 | ✅ | + |
| 批量审核汇总 | ✅ | + |
| 整改闭环跟踪 | ✅ | + |
| 历史审核查询 | ✅ | + |
| 自动复查 | ⬜ | ✅ |
| 飞书集成 | ⬜ | ✅ |
| 模板生成新资料 | ⬜ | ⬜ 留待 v2 |
| AI 自学习 | ⬜ | ⬜ |
