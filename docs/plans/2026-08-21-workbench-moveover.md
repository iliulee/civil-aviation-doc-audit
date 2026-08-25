# 移交文档：资料员工作台 v10 实施方案

> 本文档用于把"资料员工作台"的完整背景、决策、方案与验收要求，从当前会话交接给**新的会话**。
> 新会话需严格按章节 C 的待办清单执行，任何偏离须先与主任确认。

---

## A. 交接总体说明

### A.1 为什么交接
当前会话已完成**方案设计**（含实地勘察现有代码、网上调研、与主任逐项确认决策），但**尚未动手写代码**。为遵循主任"大改动新开分支 + 新对话框"的习惯，现把全部结论沉淀为移交清单，新会话据此实施。

### A.2 主任当前核心诉求（优先级最高）
1. **构建"隐患销号体系"**：每个查实的根因写成一条会失败的测试（隐患登记），修到变绿（整改销号），测试永久保留（复查防复发）。
2. **golden 防倒退**：已核对的干净文档（DOC-001）做基准，任何改动重跑输出须与基准一致，diff 即报警。
3. **一条命令验收**：`python scripts/run_all_tests.py` 全绿 = 可交付；哪条红 = 问题一眼看到。
4. **不造车轮**：能用 GitHub 现成轮子（SortableJS/SheetJS/Vite/ECharts）就用现成的，不手写。
5. **工作台**：把散落的 9 类审核 HTML 整合成"资料员工作台"，一次加载数据、模块共享。
6. **编辑器并入**：v1 本期独立 + 跳转，**v2 才真正并入**（postMessage）。

### A.3 当前状态
- **数据**：测试21 数据底座已建好（含 index.json）；49 条存疑项原样残留待后续重过（不属本轮）。
- **代码**：skill v9.7.1 已同步至 C 盘安装版（470 文件，哈希一致）；git 仓库存在，`main` 分支有未提交改动。
- **方案文档**：`docs/plans/2026-08-21-workbench-v10.md` 已完整写好（含每个 Task 的完整代码）。**本移交文档是它的执行索引。**

---

## B. 已定决策（勿改，除非主任改口）

| # | 决策 | 说明 |
|---|---|---|
| D1 | **编辑器 v1 独立跳转，v2 并入** | v1 不重写 177KB 编辑器，外壳跳转打开；v2 用 iframe+postMessage 并入，布局不变 |
| D2 | **IndexedDB 存目录句柄实现"一键恢复"** | 解决"每个页面都要重新选目录"痛点 |
| D3 | **看板数据绑 index.json 真字段** | human_verified→已核对；confusion_suspects/quality_alerts→存疑角标 等 |
| D4 | **不迁 SQLite，JSON 底座保留** | 仅加原子写 + 自动备份；SQLite 挂后置观察项 |
| D5 | **用 Vite 构建，不再是单 HTML** | 主任已确认；交付 dist/ 产物（浏览器可直接打开） |
| D6 | **不手写拖拽/导出** | 用 SortableJS + SheetJS + ECharts |
| D7 | **网络调研的行业知识落地** | 8节点进度轴"开检隐分竣交档"、台账三本、红黄绿、整改销号 |
| D8 | **每轮改完走 review-gate 四段式复核** | 自检→独立复核→全路径回归→留痕闭环 |

---

## C. 待办清单（新会话执行索引）

> 每个 Task 的**完整代码/命令/验收**在 `docs/plans/2026-08-21-workbench-v10.md` 对应章节。
> 下方是执行顺序 + 关键校验点，**不可跳序**。

### C.0 基线准备（最重要，先做）
- [ ] 1. `git add -A && git commit -m "chore: baseline before workbench-v10 branch"`（清脏工作区）
- [ ] 2. `git checkout -b feature/workbench-v10`（新分支，所有开发在这）
- [ ] 3. 备份测试21数据底座：`Copy-Item 测试21\数据底座 测试21\数据底座_backup_v10 -Recurse`
- [ ] 4. 写 `scripts/test_workbench.py`（平铺在 scripts/，非 tests/），断言 package.json 依赖 + vite.config 存在 + manifest 含 workbench
- [ ] **验收**：跑 `python scripts/run_all_tests.py --only unit` → test_workbench FAIL（无 manifest 条目，符合预期）

### C.1 项目骨架
- [ ] 5. `npm init -y && npm install -D vite && npm install sortablejs xlsx echarts`
- [ ] 6. 写 `vite.config.mjs`（`base:'./'` + `outDir:'dist'`）
- [ ] **验收**：npm install 无报错；`python -m pytest scripts/test_workbench.py -v`

### C.2 数据层 `src/data.js`
- [ ] 7. 实现 WB 对象（双模加载 fetch / showDirectoryPicker + IndexedDB 句柄 + 原子写 + 备份）
- [ ] 8. 追加 data.js 文本断言进 test_workbench
- [ ] **验收**：断言过绿

### C.3 外壳 `src/main.js` + 视图路由
- [ ] 9. 七模块注册表（总览/核对/看板/台账/概览/销号/外部）+ 动态 import 路由
- [ ] 10. `npm run dev` 手验导航/空状态
- [ ] **验收**：dev server 打开正常

### C.4 各视图模块（每模块：先实现→Playwright 测试→commit）
- [ ] 11. Overview.js（总览统计/断档/重扫，移植 project-dashboard）
- [ ] 12. Board.js（看板，SortableJS 拖拽 + 8节点轴 + ECharts 环）
- [ ] 13. Ledger.js（台账三本，SheetJS 导出 xlsx）
- [ ] 14. Quality.js（数据概览导出）
- [ ] 15. Closing.js（整改销号）
- [ ] 16. Verify.js（v1 跳转 + v2 postMessage 埋点）
- [ ] 17. External.js（8765 规则面板外链）

> **关键校验点**：每个模块 commit 前，Playwright 断言该模块行为正常（见方案第五节测试策略）。

### C.5 部署接入
- [ ] 18. template-manifest.json 追加 workbench 产物条目
- [ ] 19. run_all_tests.py 注册 test_workbench
- [ ] 20. verify_plan_v2.py 追加 check_workbench()
- [ ] **验收**：`npm run build` 无报错 + `python scripts/run_all_tests.py` 全绿

### C.6 回归验收（交付闸门，缺一不可）
- [ ] 21. 全量回归：`python scripts/run_all_tests.py` → 全绿（含 test_workbench）
- [ ] 22. golden 防倒退：DOC-001 基准重跑 diff=0
- [ ] 23. 前端 e2e（Playwright）：file:// 直开 + HTTP 加载 + 七模块切换 + 拖拽 + 台账导出 xlsx + 概览导出 + 跳转编辑器
- [ ] 24. review-gate 四段式：自检→独立复核子任务（意见落盘 review_records/）→全路径回归→留痕闭环
- [ ] **验收**：24 项全绿 + 独立复核意见每条有处置

### C.7 合并交付
- [ ] 25. `git checkout main && git merge feature/workbench-v10`
- [ ] 26. 同步 C 盘安装版（Python 子进程复制，双端哈希一致，pycache 除外）
- [ ] 27. CHANGELOG.md 记 v10.0；PROJECT_SPEC.md 更新工作台章节
- [ ] 28. 主任终审（人工最后确认）

---

## D. 关键路径与真实数据（勿臆造）

### D.1 真实文件路径
- 项目根：`d:\2026年7月22日 民航资料skill`
- skill 源码：`d:\2026年7月22日 民航资料skill\.trae\skills\civil-aviation-doc-audit`
- 安装版：`c:\Users\Administrator\.trae-cn\skills\civil-aviation-doc-audit`
- 方案文档：`d:\2026年7月22日 民航资料skill\docs\plans\2026-08-21-workbench-v10.md`
- 测试21 数据底座：`d:\2026年7月22日 民航资料skill\测试21\数据底座\`
- ECharts 离线件：`d:\2026年7月22日 民航资料skill\测试\gravel-pile-comprehensive-audit\_shared\js\echarts.min.js`

### D.2 index.json 真实字段（来自测试21实测，写代码时引这些）
```
documents[] 字段：human_verified / pending_verification / quality_alerts /
  confusion_suspects / audit_status / extraction_mode / professional /
  doc_type / subcategory / last_updated / ocr_confidence
顶层数组：corrections（修正留痕）、gaps（断档）
```

### D.3 测试体系约定（必须遵循）
- 测试文件**平铺在 `scripts/`**，命名 `test_*.py`，**没有 tests 子目录**
- `run_all_tests.py` 用显式列表注册，新测试需在此追加
- 前端行为测试用 **Playwright**（webapp-testing 技能），不混进 pytest

---

## E. 风险与回退（新会话执行时盯紧）

| 风险 | 缓解 |
|---|---|
| Vite 使工作台非单 HTML | 主任已确认；交付 dist/ 静态产物 |
| file:// 下 IndexedDB 存句柄个别浏览器策略差异 | restoreLastHandle 全 try-catch 兜底，失败回退手动选目录 |
| v2 并入 iframe 在 file:// 下 origin=null 限制 | v2 预留降级开关回 v1 跳转 |
| 编辑器 177KB 后续并入引入回归 | v1 绝不改它 |
| localStorage 台账数据丢失 | 交付时明示限制 + SheetJS 导出 xlsx 防丢 |

---

## F. 铁律与硬约束（继承自项目内，新会话必须遵守）

1. **方案不清楚不硬猜**，主动问主任要需求。
2. **真正动代码前 MUST 先给方案 + 待办清单**，等主任说"开始"才动手。
3. **改完必须全流程验证**（如 run_all_tests 全绿、DOC-001 golden、Playwright e2e）。
4. **拿不准的地方停下来和主任商量，不擅自决定**。
5. **双端同步**（项目版 + 安装版），只改一处 = 等于没改。
6. **测试留痕**：每次交付复核实录 review_records/。
7. **硬度约束**：不重写编辑器、不手写拖拽/导出、不迁 SQLite（v1）。
8. **质量红线**：检不出 ≠ 合规；存疑不下确定性结论，标注"建议现场验证"；规范引用须带条款号。

---

## G. 给新会话的开工语（可直接复制粘贴给新对话）

> 请按 `d:\2026年7月22日 民航资料skill\docs\plans\2026-08-21-workbench-v10.md` 实施"资料员工作台 v10"。执行前先读 `docs\plans\2026-08-21-workbench-v10.md` 和当前目录的 `移交文档`，掌握 C 节待办清单。先做 C.0 基线（清 git 脏区 → 建分支 feature/workbench-v10 → 备份测试21 → 写失败测试 test_workbench.py），验收确认后再逐 Task 推进。每个 Task 完成必须跑对应测试变绿，最终交付前需 `run_all_tests.py` 全绿 + DOC-001 golden 不变 + Playwright e2e 通过 + review-gate 四段式复核留痕。方案有偏离主任要求的，先停下来问，不要擅自决定。改动涉及 C 盘安装版时，双端必须同步。