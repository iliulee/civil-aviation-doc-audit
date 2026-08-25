# 独立只读复核记录 · 隐患销号体系落地（H-1~H-7 全绿 + 同步）（2026-08-19）

## 复核范围
本轮在 **civil-aviation-doc-audit** 上的改动（项目版 == 安装版，4 个关键文件双端 MD5 一致，安装版 pyc 清零）：
1. `scripts/data_quality_check.py` — L674-678 `_apply_rule` 目标跳过判定由 `is not None` 改为 `not is_missing(...)`（H-3 最后修复点：空串不再被当"已有值"挡死 INF-003/004 数学链）；L52-116 谓词层 `normalize_date_punct` / `is_missing` / `is_legal_loc`（前轮已建，本轮验证接线完整）。
2. `scripts/test_regression_hazards.py` — 隐患销号套件（26 条，H-1~H-7），本轮 26/26 全绿（自 22红4绿 起步）。
3. `scripts/test_inferred_values.py` — `test_inf008_cross_table_not_contaminate` 语义升级（原"绝不跨表" → "无据不跨表"：场景改为日期跳变 20 天 + 桩号断档 90+，断言门控不过不得产出；有据放行正向路径由 H-4 套件覆盖）。
4. `scripts/run_all_tests.py` — 挂载隐患销号套件为单元测试第 2 项。

## 复核方式
独立只读复核子任务（不带结论原文，重读 4 文件源码）+ 主会话沿链验证消费方接线。四档归类：正确 / 边界-不阻断 / 与约定不符 / 数据一致性。

## 复核结论
**三条谓词与双门控本体正确，测试真实锁住隐患（非永真断言）；但发现 1 条「与约定不符」级缺口（见 F1），建议下一轮接线后再宣告 H-5/H-6 完整销号。**

## 复核发现与处置

### 正确（抽查无问题）
- `is_missing(0)` / `is_missing(0.0)` → False（数值 0 不误判缺失，L79-80 先于字符串分支）；`is_missing("3")` → False（数字字符不算单乱字，单字判定仅对汉字 L88-89）；`is_missing("了")` → True；`is_missing(False)` → 走 str 分支 "False" 含字母 → False（bool 被 L79 排除出数值直通，但 "False" 非空非符号，判不缺失——与 None 语义无冲突，安全方向）。
- `_neighbor_table_loc`（L991-1034）：当前表日期/桩号不可解析直接拒绝（L1003-1004），日期全空不会因"同空当相近"放行；gap 用 `max(两方向区间距离)` 处理负值（L1018-1020），候选表须唯一合法部位（L1012），门控逻辑闭环。
- `_apply_rule` 目标判定（L677）与源字段判定（L702/707）现在同用 `is_missing`，"两层判定打架"（一处宽一处严）在本链路消除。
- 旧测试语义升级未丢原防线：无据跨表（日期跳变+桩号断档）仍被锁死，且 docstring 标明正向路径归 H-4 套件，两套件互补不重叠。
- 2026-08-19 复核结论"跨表不污染"与本周"有据跨表"演进自洽：前者防无据污染（仍锁），后者开有据通道（双门控），语义升级在两份测试中均有锁定。

### 边界（不阻断，知悉即可）
- B1 `run_all_tests.py` 挂载在 unit 分支（L61-66），`--only unit` 才跑隐患套件；默认全跑路径已覆盖，无实际风险。
- B2 安装版 `verify_plan_v2.py` 任务 3 红 = 已知路径反推误报（bat 在项目根，安装版目录无此文件，与 2026-08-19 先例同因），项目版跑全绿（7/7）。

### 与约定不符（需处置）
- **F1（H-5/H-6 半成品）**：`recalc_pending` / `check_dual_rows` 仅有测试调用，**生产管道零消费方**——`chat_verify_apply.py`（cmd_list L209 直接读 doc.pending_verification，未做应疑清单比对补漏）与 `DataQualityChecker.run_all` 均未接线。后果：G-1.9 闸门依据的 pending 清单仍可能漏项（H-5 只锁了函数行为，未锁管道行为）；structured_rows/rows 双份不一致不会被任何检查发现（H-6 同理）。
  - 接线点建议：① `cmd_list`/`cmd_confirm` 前置调 `recalc_pending` 比对补漏（confirm 放行前必须做，否则漏网项当真值过闸）；② `check_dual_rows` 挂 `run_all` 产出 DQ-SELF 新告警码。
  - 状态：**待用户确认后下一轮实施**（按铁律：改代码前先给方案，用户说开始才动手）。

### 数据一致性
- 双端 4 文件 MD5 一致；安装版 pyc 残留 0；项目版测试 7/7 全绿、安装版 6/7（唯一红为 B2 误报）。

## 验收门（双端执行记录）
- 项目版 `run_all_tests.py --skip-perf`：7/7 通过（推断规则 18 + 隐患销号 26 + 数据底座 + 规则引擎 + OCR 路由 + 结构验证 + 方案验收）。
- 安装版 `run_all_tests.py --skip-perf`：6/7（方案验收任务 3 为路径反推误报，见 B2）。
- 同步方式：robocopy /MIR 全量镜像（沙箱拦截 PowerShell cmdlet 写 C 盘，robocopy 可通过）+ 双端 __pycache__ 清理。
