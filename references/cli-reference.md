# CLI 命令参考（引擎模式）

> 审核过程中需要 OCR、PDF 提取、数据质量检测时，**必须用 RunCommand 执行以下命令**，不要尝试 import Python 模块或自己写代码实现。
>
> `{SKILL_DIR}` 替换为本 Skill 的实际安装路径（即 SKILL.md 所在目录）。

## 核心流水线命令

| 场景 | 执行命令 |
|------|---------|
| **建立数据底座** | `python {SKILL_DIR}/scripts/run_audit.py build "<项目文件夹>" --engine auto --preconditions "<前置.json>"` |
| **增量更新数据底座** | `python {SKILL_DIR}/scripts/run_audit.py build "<项目文件夹>" --incremental` |
| **生成审核任务包** | `python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹>" --split-by item --dry-run` |
| **执行单个审核任务** | `python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹>" --task-id <id> --tasks-file "<任务包.json>"` |
| **执行正式审核** | `python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹>" --split-by sub` |
| **生成审核报告** | `python {SKILL_DIR}/scripts/run_audit.py report "<项目文件夹>"` |
| **一键审核（v5.0 单文件）** | `python {SKILL_DIR}/scripts/run_audit.py audit "<文件路径>" --data "<结构化JSON>" --out "<输出目录>"` |

## 文档识别与提取

| 场景 | 执行命令 |
|------|---------|
| 识别资料类型 | `python {SKILL_DIR}/scripts/run_audit.py info "<文件路径>"` |
| 提取 PDF 文字 | `python {SKILL_DIR}/scripts/extract_pdf.py "<文件路径>" --out "<输出.txt>"` |
| 批量识别目录 | `python {SKILL_DIR}/scripts/run_audit.py batch "<目录路径>"` |

## OCR 扫描件

### 基本用法

| 场景 | 执行命令 |
|------|---------|
| 默认 auto 路由 | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --out "<输出.txt>"` |
| 手写体显式标记 | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --handwritten --out "<输出.txt>"` |
| 纯本地 RapidOCR | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --engine rapidocr --out "<输出.txt>"` |
| AI 视觉模型 | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --engine vision --out "<输出.txt>"` |
| Tesseract 备选 | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --engine tesseract --out "<输出.txt>"` |
| 增强预处理 | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --preprocess binarize --out "<输出.txt>"` |
| 复核指定页 | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --engine vision --page 5 --out "<输出.txt>"` |
| 表格结构感知 | `python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" --use-table --out "<输出.txt>"`（已废弃，保留兼容） |

### 完整参数说明

```powershell
python {SKILL_DIR}/scripts/ocr_image.py "<文件路径>" \
    --engine <auto|vision|rapidocr|tesseract|agent> \
    --handwritten \
    --page <页码> \
    --preprocess <none|enhance|binarize> \
    --dpi <200|300|400> \
    --out "<输出文件路径>" \
    --json-out "<JSON输出路径>" \
    --use-table
```

## 数据质量与混淆检测

| 场景 | 执行命令 |
|------|---------|
| OCR 混淆检测 | `python {SKILL_DIR}/scripts/ocr_confusion_check.py "<JSON文件>" --pretty` |
| 存疑字段自动复核（裁剪+智能体） | `python {SKILL_DIR}/scripts/verify_fields.py auto "<原始文件>" "<混淆检测JSON>" --data "<数据JSON>" --out "<输出目录>"` |
| 合并复核结果 | `python {SKILL_DIR}/scripts/verify_fields.py merge "<verify_results.json>" --data "<数据JSON>" --out "<修正后JSON>"` |
| 数据质量检测 | `python {SKILL_DIR}/scripts/data_quality_check.py "<JSON文件>" --expected-pile-total 999` |
| 文本后处理 | `python {SKILL_DIR}/scripts/postprocess.py "<文本文件>"` |
| OCR 路由自测 | `python {SKILL_DIR}/scripts/test_ocr_routing.py` |

## 多 Agent 并行工作流

```powershell
# 步骤 1：主 Agent 生成任务包（不执行审核）
python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹>" --split-by item --dry-run
# 产物：数据底座/审核日志/audit_tasks.json

# 步骤 2：每个子 Agent 执行一个任务（可并行）
python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹>" --task-id AU-20260730-001-001 --tasks-file "数据底座/审核日志/audit_tasks.json"
python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹>" --task-id AU-20260730-001-002 --tasks-file "数据底座/审核日志/audit_tasks.json"

# 步骤 3：主 Agent 汇总（执行无 task-id 的 review，自动合并所有子任务结果）
python {SKILL_DIR}/scripts/run_audit.py review "<项目文件夹>"
```

## 安装命令

用户说"安装""安装依赖""初始化"时，执行：
```powershell
powershell -ExecutionPolicy Bypass -File "{SKILL_DIR}/install.ps1"
```

## 执行规则

1. **先识别再处理**：收到文件后，先跑 `run_audit.py info` 判断是否扫描件
2. **电子档**（`is_scanned: False`）→ 用 `extract_pdf.py`
3. **扫描件**（`is_scanned: True`）→ 用 `ocr_image.py`：
   - 默认 `auto` 模式：印刷体 → RapidOCR；手写体 → Vision VLM；无 RapidOCR 无 Vision → Tesseract
   - 可附加 `--handwritten` 强制走 VLM
   - 可附加 `--json-out` 输出结构化结果
4. **OCR 结果必须输出到文件**：用 `--out` 参数
5. **OCR 混淆检测**（扫描件必做）：将 OCR 提取的表格数据整理为 JSON，跑 `ocr_confusion_check.py`
6. **存疑字段自动复核**（扫描件且有存疑字段时执行）：`verify_fields.py auto` → AI 读图验证 → `verify_fields.py merge`
7. **数据质量检测**：跑 `data_quality_check.py`，如知道设计总桩数用 `--expected-pile-total` 参数