# 独立只读复核记录 · F1 接线销号（H-5/H-6 半成品 → 管道生效）（2026-08-19 第二轮）

## 复核范围
上轮复核发现的 F1 缺口（recalc_pending / check_dual_rows 仅测试调用、生产管道零消费方）本轮处置完毕：
1. `scripts/chat_verify_apply.py` — 新增 `_recalc_missing(data, doc)`：全量重扫当前数据生成应疑清单，按 `(table, 归一字段)` 键剔除存量 pending 已覆盖项。**设计决策：漏网项不持久化进 pending**（动态快照，数据修好即消失，避免僵尸条目；存量 pending 静态登记、apply 销项，两模型各自自洽）。接线两处：`cmd_confirm` 闸门前置审计（pending 清空 + 重扫干净 才放行，blocked 输出披露 `recalc_missing` 明细）；`cmd_list` 展示漏网项（并修复原 `if not items: continue` 会把"pending 空但有漏网"文档整个跳过的盲区）。
2. `scripts/data_quality_check.py` — `check_dual_rows` 挂进 `run_all`（3.6 节），产出 `DQ-SELF-DUAL-01`（severity=error）。
3. `scripts/test_regression_hazards.py` — 新增 `TestH5H6PipelineWiring` 4 条**接线型测试**（跑真实管道而非直调函数）：脏数据挡闸（场景取 DOC-002 真实形态 `026..22` 残形日期 + `砰石松三飞` 乱码部位）、干净数据放行（不误伤）、双份分叉进 run_all 告警、双份一致零告警。

## 复核结论
**F1 销号。** 30/30 全绿（26 原有 + 4 接线），项目版全套件 7/7，安装版同步后 30/30。设计要点确认：
- 漏网项动态快照语义与 G-1.9 自洽：用户 apply 修正真值后重扫即清，无需销项动作；若用户 apply 仍填垃圾值，重扫再标 → 闸门持续拦截（防"修了个寂寞"）。
- `cmd_confirm` 数据加载提前与后段"pending 清空双写"复用同一 data 变量，无重复 IO、无双写分叉。
- 顿号日期经 H-1 归一化已合法，不构成漏网形态；测试用 `026..22`（归一化救不回的残形）代表真漏网，注释已注明区别。

## 同步记录
- robocopy /MIR（首次因 `.pytest_cache\nodeids` 被锁死循环重试，改为 `/R:0 /W:0 /XD .pytest_cache __pycache__` 后成功；exit=1 为 robocopy 成功语义）。
- 4 个关键文件双端 MD5 一致：data_quality_check.py / chat_verify_apply.py / test_regression_hazards.py / run_all_tests.py。
- 安装版 `test_regression_hazards.py`：30 passed。

## 经验沉淀
- pytest 运行后 `.pytest_cache` 可能锁文件，同步脚本须 `/XD .pytest_cache` + `/R:0 /W:0`，否则 robocopy 30 秒×N 无限重试（已在本轮实际踩中）。
