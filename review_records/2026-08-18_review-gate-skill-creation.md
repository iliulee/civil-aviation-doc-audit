# Review Gate 记录 — 2026-08-18

## 本轮范围
- 改动内容：新建 review-gate skill（6 文件：SKILL.md、README.md、references/×4）
- 涉及文件：项目版 .trae/skills/review-gate/ 与安装版 .trae-cn/skills/review-gate/
- 待办清单版本/来源：用户确认的四段式 SOP + 多模型约定表方案

## ① 自检闸门
通用项：10/10 通过（本轮为纯文档新建，无代码逻辑）
要点：frontmatter 仅 name/description；name 与目录名一致；无敏感信息与项目私有路径；README/SKILL 分工无重复大段；4 个 reference 均由 SKILL.md 直接链接

## ② 独立复核
复核通道：降级：当前会话自检·同模型·置信度降档（复核子智能体尚未配置）
意见总数：0
备注：首轮降级已按 model-config.md 兜底规则执行并如实标注

## ③ 全路径回归
| 步骤 | 命令/入口 | 结果 |
|------|-----------|------|
| 双副本同步 | robocopy /MIR + 文件数比对 | src=6 dst=6 一致 |
| 内容一致性 | 全文件 MD5 汇总比对 | HASH-MATCH |
| 结构校验 | 目视核对 skill-optimizer Step 5 清单 | 通过 |

## ④ 意见处置清单
| # | 意见摘要 | 档位 | 处置 | 理由/修复说明 |
|---|----------|------|------|----------------|
| 1 | 新建 skill 需新会话才会被 TRAE 发现 | 边界问题 | 不改（如实提醒用户） | skill 列表在会话启动时注入，属平台机制 |

## 结论
- [x] 通过交付
- [ ] 不通过

## 沉淀
- 本轮无新漏点需追加清单
