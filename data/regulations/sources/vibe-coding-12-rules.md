---
source: 微信公众号
author: AI炊事员Ryan
title: Vibe Coding 错误率从 85% 降到 8%，我只做了一件事：加了这12条"天条"
url: https://mp.weixin.qq.com/s/bMIEHYgogd7b-0qcJmQn9Q
date: 2026-07-10
tags: [vibe-coding, AI编码, agent规则, 最佳实践]
---

# Vibe Coding 错误率从 85% 降到 8%：12条规则详解

## 核心观点

AI 编码最大的问题往往不是写不出来，而是太爱自作主张。100 行的需求它能写成 500 行架构；让它修一个 bug，它能顺手改坏旁边没问题的文件。

问题不在模型能力本身，而在**没人提前告诉它什么不能做**。

这 12 条规则真正解决的，就是给 AI Agent 补上行为边界。

## 12条规则速览

| # | 规则 | 核心含义 | 防止的问题 |
|---|------|---------|-----------|
| 1 | Think Before Coding | 编码前先说明假设和不确定性 | 静默假设、误解需求 |
| 2 | Simplicity First | 用最少代码解决问题 | 过度工程、臃肿抽象 |
| 3 | Surgical Changes | 只改必须改的地方 | 无关修改、误伤代码 |
| 4 | Goal-Driven Execution | 定义成功标准并循环验证 | "看起来完成了" |
| 5 | Use the Model Only for Judgment Calls | 确定性逻辑交给代码 | 用AI替代if-else |
| 6 | Token Budgets Are Not Advisory | 设置token预算上限 | 长session漂移 |
| 7 | Surface Conflicts, Do Not Average Them | 遇到冲突模式显式选择 | 代码风格混乱 |
| 8 | Read Before You Write | 写代码前先读上下文 | 重复实现、误判架构 |
| 9 | Tests Verify Intent, Not Just Behavior | 测试验证业务意图 | 浅层测试 |
| 10 | Checkpoint After Every Significant Step | 每一步后做状态总结 | 多步骤漂移 |
| 11 | Match Codebase Conventions | 遵守现有约定 | 风格分叉 |
| 12 | Fail Loud | 不确定就大声说出来 | 假成功、静默失败 |

## 为什么从4条扩展到12条

Karpathy 最初的 4 条规则（Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution）解决的是编码阶段的问题。但现在的 AI 编码是跨文件、多步骤的 Agent 工作流，会引入新的失败模式：

1. **上下文漂移** → 长 session 中模型重复试错 → 需要规则6 (Token Budgets)
2. **模型越界判断** → AI 用自己替代确定性逻辑 → 需要规则5 (Model for Judgment Calls)
3. **冲突模式被"平均"** → 代码风格混乱 → 需要规则7 (Surface Conflicts)
4. **测试假通过** → 浅层验证不覆盖业务意图 → 需要规则9、12
5. **多步骤状态丢失** → 错误一路扩散 → 需要规则10 (Checkpoint)

## 分组

- **编码阶段（Rules 1-4）**：Karpathy原始规则，编码基础
- **Agent执行阶段（Rules 5-12）**：新增规则，针对多步骤Agent工作流

## 放置方式

将规则写入项目的 `CLAUDE.md` 或 `AGENTS.md` 文件，AI 在每次操作前自动读取。

**GitHub 项目：** https://github.com/twj515895394/andrej-karpathy-skills-12
**中文版规则直达：** `CLAUDE.zh.md`

## 适用场景

- 使用 Cursor / Codex / Claude Code 等 AI 编码工具时
- 涉及多文件、多步骤的 Agent 工作流
- 需要防止 AI 过度工程、误改代码
- 团队需要统一的 AI 编码规范

## 局限性

- 简单任务（单文件修改）用4条规则就够了
- 规则本身需要维护，不能一次写好就不管
- 需要团队成员都理解并遵守
