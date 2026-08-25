# Review Gate 记录 — 2026-08-18 20:00

## 本轮范围
- 改动内容：civil-aviation-doc-audit skill 新增「AI 对话框人工核对（Chat-Verify）」通道 + 修 6 项数据待办（None 污染 / pages:1 / DOC-002 路径归位 / 分类确认 / is_handwritten 去 null / build_foundation docx 表格解析下沉）
- 涉及文件：
  - `scripts/chat_verify_apply.py`（Chat-Verify 应用器，本轮独立复核意见修复主战场）
  - `SKILL.md`（阶段 2 定义：修正记录路径、failed 留痕、聊天通道不产 corrected_data.json）
  - `scripts/build_foundation.py`（v9.6 注释→v9.5、image_ref 回退分支去 None、状态注按 method 区分）
  - `PROJECT_SPEC.md` / `CHANGELOG.md`（版本与变更记录随轮更新）
  - 测试21 数据底座 index.json + DOC-002 数据文件（None→''、路径归位、pages 修正、分类确认）
- 待办清单版本/来源：移交清单 + 会话 v2 方案（7 项任务）

## ① 自检闸门
通用项：10/10 通过（依据：本会话实测证据 + 上一会话独立复核结论）

| # | 检查项 | 判定 | 证据 |
|---|--------|------|------|
| 1 | 方案承诺项→实际产物 | YES | chat_verify_apply.py 存在且可执行；SKILL.md 阶段2 已改；6 项数据修复在 index.json/数据文件可查 |
| 2 | 状态字段归位 | YES | status 实测：classification_confirmed=true、classification_pending_count=0 |
| 3 | 元数据与物理位置一致 | YES | DOC-002 data_file=通用资料/碎石桩施工记录/扫描件合计的27页.json，与 subcategory 一致 |
| 4 | 数据污染（null/None 落盘） | YES | DOC-002 structured_rows 全为字符串，None→'' 已修（rows 抽查无 None） |
| 5 | 派生值失真 | YES | DOC-002 pages 1→27（实测 index.json pages=27） |
| 6 | 缓存清理 | YES | robocopy /MIR 清 18 个 .pyc；剩余 __pycache__ 为空目录，无旧字节码顶替 |
| 7 | 双副本同步 | YES | 454=454 文件，DIFF_COUNT=0；5 个关键文件 SHA256 一致 |
| 8 | 无重复造轮子 | YES | 上一会话独立复核已核（新增通道无等价实现），本会话未发现等价物 |
| 9 | 无越界改动 | YES | 本轮 diff 均在待办范围内（Chat-Verify + 6 项修复） |
| 10 | 版本一致 | YES | 代码注释统一 v9.5，CHANGELOG 含 2026-08-18 条目 |

## ② 独立复核
复核通道：上一会话派独立上下文子任务（跨模型优先，本会话承接其结论）
意见总数：9（阻断 5：A-1、B-3、B-4、B-5、B-8；边界 4：内容随上一会话上下文丢失，本会话无法恢复明细，见处置清单）
阻断性问题：5（均已修复，且本轮回归逐一实证）

## ③ 全路径回归（本会话真实执行）
| 步骤 | 命令/入口 | 结果 |
|------|-----------|------|
| 双端同步 | robocopy /MIR 项目版→安装版 | 454=454，DIFF_COUNT=0；18 个 .pyc 被清 |
| 关键文件哈希 | 5 文件 SHA256 比对 | 全 OK（chat_verify_apply / SKILL / PROJECT_SPEC / build_foundation / CHANGELOG） |
| status（真实测试21） | chat_verify_apply.py status 测试21 | DOC-001 verified；DOC-002 pending 49、human_verified=false；分类已确认 |
| list（真实测试21） | chat_verify_apply.py list --doc DOC-002 --table 0 | 表0 施工部位 OCR 乱码 + 施工日期残缺，按表分组输出正常 |
| apply（沙箱，表级+accept） | 3 条修正（施工部位/日期/accept） | 9 条留痕落库；resolved 2；remaining 49→47；corrections_total=9 |
| B-5 修正路径 | apply 后查文件 | 修正记录/corrections.json 已生成 |
| A-1 失败落库 | apply 表2/桩507 充盈系数="xyz" | failed 返回"不可解析为数字"；index.json corrections.failed 落库含 doc_id |
| B-3 全角逗号 | apply 表2/桩507 充盈系数="1，2" | 归一化为 1.2 落库（原值"了"→1.2） |
| B-4 row_index | apply table=3 row_index=16 桩底高程=2099.99 | 仅第 15 行（0-based）变更，其余 145 行零误改 |
| G-1.9 闸门 | confirm --doc DOC-002（沙箱） | 剩余 45 条 → blocked，禁止确认，未绕过 |
| B-8 空文档 | status 空 documents | all_human_verified=false，无误报 |

## ④ 意见处置清单
| # | 意见摘要 | 档位 | 处置 | 理由/修复说明 |
|---|----------|------|------|----------------|
| A-1 | 失败修正未持久化到 index.json | 阻断 | 改 | `_update_index_corrections` + `cmd_apply` 写 `corrections.failed`；回归实测 failed 项含 doc_id 落库 |
| B-3 | 数值字段全角/半角逗号未归一化 | 阻断 | 改 | 新增 `_fmt_number` + `try_float` 归一化（"1，2"→"1.2"）；回归实测落库 1.2 |
| B-4 | row_index 0/1 基不一致 | 阻断 | 改 | `_locate_rows` 按 1-based 用户视角输入、内部转 0-based；回归实测精确定位且零误改 |
| B-5 | corrections.json 路径与文档不一致 | 阻断 | 改 | 统一为 修正记录/corrections.json（代码 + SKILL.md + apply 输出）；回归实测文件在该路径生成 |
| B-8 | 空文档列表 status 误报 all_human_verified | 阻断 | 改 | `all_verified = bool(summary) and all(...)`；回归实测空列表=false |
| 边界×4 | 上一会话独立复核的 4 项边界意见 | 边界 | 不改（明细缺失） | ⚠️ 具体内容随上一会话上下文丢失，本会话未恢复、不臆造。上一会话已处置为"边界问题，不改"。如需补全，可重跑独立复核子任务对当前 diff 重新出意见 |

## 结论
- [x] 通过交付（本会话实证范围内）
- [ ] 不通过

## 沉淀
- 本轮暴露的新漏点：**独立复核意见未落盘即被下一会话依赖** → 建议追加 self-check-checklist 项目扩展位条目：`独立复核意见清单在当轮留痕落盘（review_records/），不依赖会话记忆`。
- 遗留提示：测试21 DOC-002 仍停在阶段 2（49→人工核对中），human_verified=false，禁止出报告（G-1.9）。
