# 2026-08-25 工作台跨平台安装 + verify_plan_v2 移植性修复 · 复核留痕

## ① 自检闸门
| 项 | 结果 |
|---|---|
| 改动范围是否明确 | YES — 新增工作台部署、修复 1 处脚本判断 |
| 是否先查现成模块/等价实现 | YES — 复用部署 bat 与 verify 脚本，未重复造轮子 |
| 是否覆盖所有关联位置 | YES — 三处副本（项目版源/安装版/WorkBuddy）同步打补丁 |
| 纯 ASCII bat 编码约束 | YES — bat 全 ASCII 落盘，实测无 >127 字节 |
| 是否全流程验证 | YES — 三处 verify_plan_v2 语法 OK + 实测全量测试 |

## ② 独立复核
- 部署到 WorkBuddy 后触发 `方案验收` 红，复核定位到 `verify_plan_v2.py` 第 21 行硬编码 `.trae-cn` 判定安装副本。
- 判定为**移植性缺陷**（非数据问题）：WorkBuddy 路径为 `.workbuddy`，被判为开发工作区，从而去查仅项目根才有的 `同步内部路由到安装版.bat`，误报失败。
- 同模型复核，置信度降档标注。

## ③ 全路径回归证据
| 命令 | 结果 |
|---|---|
| `workbuddy\scripts\run_all_tests.py` | ✅ 9/9 |
| `trae-cn\scripts\run_all_tests.py` | ✅ 9/9 |
| `项目版 verify_plan_v2.py` 回归 | ✅ 7/7（含工作台 v10 任务） |
| 三处 `verify_plan_v2.py` ast 语法检查 | ✅ OK |
| 安装版/WorkBuddy 的 `启动工作台.bat`、`workbench/index.html`、`workbench/index.json` 哈希一致 | ✅ True |

## ④ 修复内容
`verify_plan_v2.py` 安装副本判定由 `.trae-cn` 硬编码改为按路径是否含 `\.trae\skills\` 判定开发工作区副本：
```python
_ws_copy = "\\.trae\\skills\\" in str(SKILL_DIR).lower()
IN_INSTALLED_COPY = not _ws_copy
```
三处同步修改，双端一致性验证通过。

## 处置记录
- 修复项：verify_plan_v2.py 移植性缺陷 → 已改并验证
- 未改项：bat 中文注释逻辑未动；合规