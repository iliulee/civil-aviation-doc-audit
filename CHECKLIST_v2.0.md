# 待办清单 v2.0

> 按 Phase 1 任务拆解到可执行级别。做完一项打勾一项。

---

## 任务 3：同步脚本清理（最简单，排第一）

- [ ] 3.1 删除 12 个 .ps1 文件
- [ ] 3.2 修改 `同步内部路由到安装版.bat` 加文件头注释
- [ ] 3.3 更新 `README.md` 注明唯一同步入口
- [ ] 3.4 验证：同步脚本能正常执行

## 任务 6：版本号统一（排第二，不涉及代码逻辑）

- [ ] 6.1 SKILL.md 标题 `v9.4` → `v9.5`
- [ ] 6.2 CHANGELOG.md 补充 v9.5 条目
- [ ] 6.3 验证：各处版本号一致

## 任务 1：推荐值规则独立化 + 扩展（核心）

- [ ] 1.1 新建 `rules/inference_rules.json`
  - [ ] 写入 INF-001~INF-007 共 7 条规则
  - [ ] 写入置信度颜色映射表
  - [ ] 写 JSON Schema 注释便于理解
- [ ] 1.2 改造 `data_quality_check.py`
  - [ ] 新增 `_load_inference_rules()` 读取 JSON
  - [ ] 新增 `_apply_rule(rule, row)` 执行单条规则
  - [ ] 改造 `infer_values()` 改为循环读取规则列表
  - [ ] 保留原有 5 条逻辑，迁移到配置文件
  - [ ] 实现置信度计算公式（base_confidence - cascade_penalty - low_confidence_penalty）
- [ ] 1.3 改造 `build_foundation.py` 的 `call_inference()`
  - [ ] 置信度 < 0.5 也输出，打上 `low_confidence: true` 标记
- [ ] 1.4 更新 `SKILL.md` 推荐值规则描述
- [ ] 1.5 更新 `PROJECT_SPEC.md`
- [ ] 1.6 更新 `CHANGELOG.md`
- [ ] 1.7 验证：推荐值规则能正常加载和执行

## 任务 2：手写体混合型文档优化

- [ ] 2.1 新建 `ocr_image.py` 的 `crop_and_verify()`
  - [ ] 根据 page + bbox 裁剪图片
  - [ ] 调用 AI 读图复核
  - [ ] 返回修正值 + 置信度
- [ ] 2.2 改造 `build_foundation.py` 新增低置信字段复核步骤
  - [ ] OCR 完成后遍历 structured_rows 中所有字段
  - [ ] 对 text_score < 0.5 的字段记录 page + bbox
  - [ ] 调用 `crop_and_verify()` 复核
  - [ ] 更新结构化数据，标记 `ai_reviewed: true`
- [ ] 2.3 更新 `references/ocr-hybrid-architecture.md`
- [ ] 2.4 更新 `SKILL.md` OCR 引擎策略描述
- [ ] 2.5 验证：混合型文档的低置信字段能被正确复核

## 任务 4：增量对比清单 + 保护机制

- [ ] 4.1 改造 `build_foundation.py` 增量保护逻辑
  - [ ] 增量模式下保留已有文档的 human_verified / corrected_file / audit_status
  - [ ] 新增 `incremental_added_at` 时间戳
  - [ ] 新增 `incremental_from` 标记（"new" / "existing"）
- [ ] 4.2 更新 `SKILL.md` 增量路径描述（含对比清单展示时机）
- [ ] 4.3 更新 `PROJECT_SPEC.md`
- [ ] 4.4 验证：增量更新时老文件状态不被覆盖

## 任务 5：统一测试体系

- [ ] 5.1 新建 `scripts/run_all_tests.py`
  - [ ] 集成 5 个现有测试
  - [ ] 支持 `--skip-slow` 跳过慢测试
  - [ ] 输出汇总报告（通过/失败/跳过）
- [ ] 5.2 新建 `scripts/test_data_foundation.py`
  - [ ] 测试新建路径
  - [ ] 测试增量路径
  - [ ] 测试 OCR 引擎选择
  - [ ] 测试 index.json 生成
- [ ] 5.3 新建 `scripts/test_inferred_values.py`
  - [ ] 构造桩基测试数据 10 行
  - [ ] 验证 INF-001~INF-005 触发
  - [ ] 验证置信度标定
  - [ ] 验证级联推断扣减
- [ ] 5.4 验证：`run_all_tests.py` 能正常执行且全部通过

---

## 汇总检查

- [ ] 所有新建文件已创建
- [ ] 所有修改文件已到位
- [ ] 所有删除文件已清理
- [ ] `run_all_tests.py` 全部通过
- [ ] 同步到安装版后验证无报错
- [ ] 版本号统一为 v9.5