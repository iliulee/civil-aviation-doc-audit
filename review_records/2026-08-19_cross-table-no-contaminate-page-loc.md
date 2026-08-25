# 独立只读复核记录 · 跨表防污染 + 页码定位 + VLM 措辞修正（2026-08-19）

## 复核范围
本轮在 **civil-aviation-doc-audit** 上的改动（项目版 == 安装版，双端哈希一致、454=454 文件）：
1. `scripts/data_quality_check.py` — 改 `_text_mode_by_row` / `_neighbor_lookup` / `_text_fill_date`，新增 `_row_table` / `_same_table`（建议值候选与邻行检索严格限定**同一张表**，杜绝跨表/跨页污染）。
2. `scripts/chat_verify_apply.py` — `cmd_list` 新增 `_derive_page` 页码定位（item.page → 命中行 row.page → docx 表数==页数时 page=table+1），JSON/非 JSON 两处一致带 page。
3. `scripts/test_inferred_values.py` — 新增 `test_inf008_cross_table_not_contaminate`、`test_inf008_cross_table_date_not_contaminate`。
4. `SKILL.md` — 新增「建议值说明」（含 VLM 预留扩展点 + 页码/建议值展示说明）。

## 复核方式
独立只读复核子任务（不含原文，重新审源端 4 文件 + inference_rules.json），按四档归类：正确 / 边界 / 与约定不符 / 数据一致性。

## 复核结论
**无「与约定不符」、无「数据一致性」级问题，本轮可交付。** 三条铁律满足：
- 只建议不入库（refresh 排除 `suggested_only`；apply 仅 `accept_recommended` 才落库）；
- 文本规则不参与审核判定（仅走 `infer_values` 的 `_apply_text_rule` 分支）；
- 跨表不污染（table=0 用相等比较 `r.get('table')==table_id`，0 是 falsy 未被真值判断误伤；`_same_table` 越界返回 False）。

## 复核发现与处置

### 正确（抽查无问题）
- `_same_table`/`_row_table` 对 table=0 的相等比较正确；表0 首表 page=table+1=1 正确；`table is None`（无 table 字段，如 DOC-001 xlsx）回退全文档且不崩溃，与旧版兼容。
- `_derive_page` 优先级与 None 兜底正确；JSON 与非 JSON 输出一致；页码缺失时不崩、suggestion 单独成行可读。
- 实测：test21 `list` 页码 1~27 逐表对应；`refresh` 不动 pending(49)/human_verified(false)/corrections(0)，进度零丢失。

### 边界（不阻断，知悉即可）
- B1 `_same_table` 依赖 table 为 int 类型；若个别行 table 存字符串 `"0"` 会被 `"0"==0` 判为跨表（假阴性，宁可少建议也不污染，方向安全）。
- B2 `_same_table` 在 `table_id is None` 时回退整文档检索；若同文档个别行缺 table 混排会重新引入跨表窗口（正常交付数据 uniform，不影响主路径）。

### 处置点（本文档修正 SKILL.md 措辞）
- **D1**：SKILL.md 初稿 VLM 措辞暗示「已实现可用」（"若配置了 VLM 模型…系统可做软增强"），但代码无 VLM hook，属「文档先行、实现未达」，且原措辞「通过环境变量启用」与既定契约「默认不依赖环境变量/模型」相悖。→ **已改**为「VLM 视觉核验属**预留的可插拔扩展点**，仅当用户后续显式配置后启用，未配置/未启用时静默使用规则建议、默认不依赖任何模型」，并与安装版同步（双端哈希一致）。

## 验收门（安装版执行）
- `verify_skill_structure.py`：4/4 通过（84ms）。
- `review_skill.py`：64/64 通过、0 失败。
- 单测 `test_inferred_values.py`：18 通过（含新增 2 条跨表防污染锁定用例 + 原 16 条回归）。