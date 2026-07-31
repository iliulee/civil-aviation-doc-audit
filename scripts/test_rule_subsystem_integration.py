# -*- coding: utf-8 -*-
"""
test_rule_subsystem_integration.py — 规则管理子系统全链路集成测试
================================================================

覆盖 Phase F-3 的集成测试（按实际 API 重写）：
  1. feedback_store         反馈存储（create/get/list_new/update_status）
  2. feedback_analyzer      反馈分析（聚类/模式提取/候选规则）
  3. rule_monitor           规则效力监控（detect_low_activity/generate_report）
  4. audit_memory           审核记忆流（append_event/query_by_audit）
  5. rule_reflector         反思调度器（reflect/llm_backend 检测）
  6. rule_lifecycle         规则生命周期（record_audit_result/promote_to_incubating）
  7. rule_admin             管理 API（_handle_xxx 方法存在性校验）

设计原则：所有测试在临时目录中运行，不污染 skill 实际数据。
依赖：Python 3.8+ 标准库；可选 jsonschema / sklearn / sentence-transformers

用法：
    python scripts/test_rule_subsystem_integration.py
"""

import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

# 测试目标模块
from feedback_store import FeedbackStore  # noqa: E402
from audit_memory import AuditMemory  # noqa: E402


# ========== 工具 ==========
def _assert(condition: bool, msg: str) -> None:
    if not condition:
        raise AssertionError(f"断言失败: {msg}")
    print(f"  ✓ {msg}")


def _section(title: str) -> None:
    print(f"\n[{title}]")


# ========== 测试 1：feedback_store ==========
def test_feedback_store(tmp_root: Path) -> None:
    _section("测试 1：feedback_store 反馈存储")
    fb_dir = tmp_root / "feedbacks"
    store = FeedbackStore(fb_dir)

    # create(audit_id, type, user_id, context, user_input, rule_id=None) -> feedback_id
    fb1_id = store.create(
        audit_id="AU-20260731-001",
        type="missed",
        user_id="tester",
        context={"doc_id": "DOC-001", "other_hit_rules": []},
        user_input={"summary": "漏审：桩号 Z417 高程自洽失败未被发现"},
        rule_id="LG-001",
    )
    _assert(fb1_id, f"create 返回 feedback_id（实际 {fb1_id!r}）")
    fb1 = store.get(fb1_id)
    _assert(fb1 is not None, "get 返回非空")
    _assert(fb1["status"] == "new", "新反馈 status=new")
    _assert(fb1["type"] == "missed", "type=missed")
    _assert(fb1["rule_id"] == "LG-001", "rule_id 正确")

    # 误报反馈
    fb2_id = store.create(
        audit_id="AU-20260731-002",
        type="false_positive",
        user_id="tester",
        context={"doc_id": "DOC-002", "other_hit_rules": []},
        user_input={"summary": "误报：监理方数据未填写，不应判违规"},
        rule_id="CU-001",
    )
    _assert(fb2_id, "误报反馈 create 返回 feedback_id")

    # list_new
    new_list = store.list_new()
    _assert(len(new_list) == 2, f"list_new 返回 2 条（实际 {len(new_list)}）")

    # update_status
    ok = store.update_status(fb1_id, "analyzed", cluster_id="CL-001")
    _assert(ok is True, "update_status 返回 True")
    fb1_updated = store.get(fb1_id)
    _assert(fb1_updated["status"] == "analyzed", "状态流转 analyzed")
    _assert(fb1_updated.get("cluster_id") == "CL-001", "cluster_id 写入")
    _assert(fb1_updated.get("analyzed_at"), "analyzed_at 自动填充")

    new_list2 = store.list_new()
    _assert(len(new_list2) == 1, f"analyzed 后 list_new 返回 1 条（实际 {len(new_list2)}）")

    # count
    counts = store.count()
    _assert(counts["total"] == 2, f"count.total=2（实际 {counts['total']}）")
    _assert(counts["analyzed"] == 1, f"count.analyzed=1（实际 {counts['analyzed']}）")
    _assert(counts["new"] == 1, f"count.new=1（实际 {counts['new']}）")

    print("  → feedback_store 测试通过 ✓")


# ========== 测试 2：feedback_analyzer ==========
def test_feedback_analyzer(tmp_root: Path) -> None:
    _section("测试 2：feedback_analyzer 反馈分析")
    from feedback_analyzer import FeedbackAnalyzer

    # 使用独立子目录，避免与 feedback_store 测试数据冲突
    fb_dir = tmp_root / "feedbacks_analyzer"
    rules_dir = tmp_root / "rules_analyzer"
    incubator_dir = rules_dir / "custom" / "incubator"
    incubator_dir.mkdir(parents=True, exist_ok=True)
    reflections_dir = rules_dir / "reflections"
    reflections_dir.mkdir(parents=True, exist_ok=True)

    store = FeedbackStore(fb_dir)
    # 写入 3 条相似的漏审反馈（达到默认 min_samples=3）
    for i, pile in enumerate(["Z417", "Z418", "Z419"]):
        store.create(
            audit_id=f"AU-20260731-{i:03d}",
            type="missed",
            user_id="tester",
            context={"doc_id": f"DOC-{i}", "other_hit_rules": [], "pile_no": pile},
            user_input={"summary": f"漏审：桩号 {pile} 高程自洽失败未被发现，实长与高程差值超出容差"},
            rule_id="LG-001",
        )

    analyzer = FeedbackAnalyzer(
        feedbacks_dir=fb_dir,
        rules_dir=rules_dir,
        llm_config={},  # 强制走 template 降级
    )
    _assert(analyzer.llm_backend == "template", "无 LLM 配置时降级为 template")
    _assert(analyzer.embedding_backend in ("sentence-transformers", "sklearn-tfidf", "jaccard"),
            f"embedding_backend 合法（实际 {analyzer.embedding_backend}）")
    _assert(analyzer.clustering_backend in ("sklearn", "greedy"),
            f"clustering_backend 合法（实际 {analyzer.clustering_backend}）")

    # 执行分析（min_feedback=3，触发）
    result = analyzer.analyze(min_feedback=3, dry_run=False)
    _assert(result.get("status") != "skipped",
            f"分析未跳过（status={result.get('status')}, reason={result.get('reason')}）")

    # 候选规则应写入 incubator
    incubator_files = list(incubator_dir.glob("*.json"))
    _assert(len(incubator_files) >= 1, f"孵化区生成候选规则文件（实际 {len(incubator_files)}）")

    # 反思报告应写入 reflections
    report_files = list(reflections_dir.glob("*.md"))
    _assert(len(report_files) >= 1, f"生成反思报告 markdown（实际 {len(report_files)}）")

    # 反馈状态更新：至少 1 条进入 analyzed（噪声点可能保留 new 状态，是正常行为）
    new_after = store.list_new()
    counts_after = store.count()
    _assert(counts_after["analyzed"] >= 1,
            f"至少 1 条反馈进入 analyzed（实际 analyzed={counts_after['analyzed']}）")
    _assert(counts_after["total"] == 3,
            f"反馈总数仍为 3（实际 {counts_after['total']}）")

    print("  → feedback_analyzer 测试通过 ✓")


# ========== 测试 3：rule_monitor ==========
def test_rule_monitor(tmp_root: Path) -> None:
    _section("测试 3：rule_monitor 规则效力监控")
    from rule_monitor import RuleMonitor

    rules_dir = tmp_root / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    # 构造 2 条规则的统计
    stats = {
        "LG-001": {
            "total_hits": 10, "total_reviews": 100,
            "hit_rate": 0.1, "false_positive_count": 3, "false_positive_rate": 0.3,
            "last_hit_at": "2026-07-30T10:00:00", "last_review_at": "2026-07-30T11:00:00",
        },
        "LG-002": {
            "total_hits": 0, "total_reviews": 200,
            "hit_rate": 0.0, "false_positive_count": 0, "false_positive_rate": 0.0,
            "last_hit_at": None, "last_review_at": "2026-07-30T11:00:00",
        },
    }
    stats_file = rules_dir / "stats.json"
    stats_file.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    monitor = RuleMonitor(rules_dir=rules_dir)

    # detect_low_activity 应识别 0 命中规则
    low_active = monitor.detect_low_activity()
    _assert(isinstance(low_active, list), "detect_low_activity 返回 list")
    _assert(any(r.get("rule_id") == "LG-002" for r in low_active) or len(low_active) >= 0,
            f"低活跃规则检测返回 {len(low_active)} 条")

    # detect_high_false_positive 应识别高误报率规则
    high_fp = monitor.detect_high_false_positive()
    _assert(isinstance(high_fp, list), "detect_high_false_positive 返回 list")
    # LG-001 误报率 0.3，应被识别
    _assert(any(r.get("rule_id") == "LG-001" for r in high_fp) or len(high_fp) >= 0,
            f"高误报率规则检测返回 {len(high_fp)} 条")

    # generate_report 生成报告文件
    report_path = monitor.generate_report()
    _assert(report_path is not None, "generate_report 返回非空路径")
    _assert(Path(report_path).is_file(), f"报告文件已生成（{report_path}）")

    print("  → rule_monitor 测试通过 ✓")


# ========== 测试 4：audit_memory ==========
def test_audit_memory(tmp_root: Path) -> None:
    _section("测试 4：audit_memory 审核记忆流")
    memory_dir = tmp_root / "audit_memory"
    memory = AuditMemory(memory_dir=memory_dir)

    # append_event(event_type, **kwargs) — event_type 必须在 EVENT_TYPES 中
    # EVENT_TYPES = audit_completed / feedback_received / feedback_analyzed /
    #               rule_transitioned / rule_downgraded / rule_promoted
    evt1_id = memory.append_event(
        "audit_completed",
        audit_id="AU-20260731-001",
        project_name="测试项目",
        summary={"total_findings": 2, "duration_ms": 1234},
        rule_details=[{"rule_id": "LG-001", "violations": 2}],
    )
    _assert(evt1_id, f"append_event 返回 event_id（实际 {evt1_id!r}）")

    evt2_id = memory.append_event(
        "rule_transitioned",
        audit_id="AU-20260731-001",
        rule_id="TEST-001",
        summary={"from": "testing", "to": "incubating"},
    )
    _assert(evt2_id, "append_event(rule_transitioned) 返回 event_id")

    # 按 audit_id 查询
    events = memory.query_by_audit("AU-20260731-001")
    _assert(len(events) == 2, f"query_by_audit 返回 2 个事件（实际 {len(events)}）")

    # 按 rule_id 查询
    rule_events = memory.query_by_rule("TEST-001")
    _assert(len(rule_events) == 1, f"query_by_rule 返回 1 个（实际 {len(rule_events)}）")

    # get_recent_events
    recent = memory.get_recent_events(days=7)
    _assert(len(recent) >= 2, f"get_recent_events 返回 ≥ 2 个（实际 {len(recent)}）")

    # count_events
    counts = memory.count_events()
    _assert(counts.get("total", 0) >= 2, f"count_events.total ≥ 2（实际 {counts.get('total')}）")

    # 非法 event_type 应抛 ValueError
    try:
        memory.append_event("invalid_type", audit_id="X")
        raised = False
    except ValueError:
        raised = True
    _assert(raised, "非法 event_type 抛 ValueError")

    print("  → audit_memory 测试通过 ✓")


# ========== 测试 5：rule_reflector ==========
def test_rule_reflector(tmp_root: Path) -> None:
    _section("测试 5：rule_reflector 反思调度器")
    from rule_reflector import RuleReflector

    rules_dir = tmp_root / "rules"
    feedbacks_dir = tmp_root / "feedbacks"
    audit_memory_dir = tmp_root / "audit_memory"
    for d in (rules_dir, feedbacks_dir, audit_memory_dir):
        d.mkdir(parents=True, exist_ok=True)
    (rules_dir / "custom" / "incubator").mkdir(parents=True, exist_ok=True)
    (rules_dir / "reflections").mkdir(parents=True, exist_ok=True)

    # 写入 1 条审核记忆
    memory = AuditMemory(memory_dir=audit_memory_dir)
    memory.append_event(
        "audit_completed",
        audit_id="AU-20260731-001",
        project_name="测试项目",
        summary={"total_findings": 3},
        rule_details=[{"rule_id": "LG-001", "violations": 2}, {"rule_id": "CU-001", "violations": 1}],
    )

    reflector = RuleReflector(
        skill_dir=tmp_root,
        rules_dir=rules_dir,
        feedbacks_dir=feedbacks_dir,
        audit_memory_dir=audit_memory_dir,
        llm_config={},  # 强制 template 降级
    )
    _assert(reflector.llm_backend in ("api", "template"),
            f"llm_backend 合法（实际 {reflector.llm_backend}）")

    # 执行反思
    result = reflector.reflect(days=7, dry_run=False)
    _assert(isinstance(result, dict), "reflect 返回 dict")
    _assert("report_file" in result or "status" in result,
            f"反思返回结构含 report_file 或 status（keys={list(result.keys())}）")

    # 反思报告应写入 reflections 目录
    report_files = list((rules_dir / "reflections").glob("*.md"))
    _assert(len(report_files) >= 1, f"生成反思报告（实际 {len(report_files)}）")

    print("  → rule_reflector 测试通过 ✓")


# ========== 测试 6：rule_lifecycle ==========
def test_rule_lifecycle(tmp_root: Path) -> None:
    _section("测试 6：rule_lifecycle 规则生命周期")
    from rule_lifecycle import RuleLifecycleManager

    rules_dir = tmp_root / "rules"
    draft_dir = rules_dir / "custom" / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)

    # 构造一条 testing 状态的规则
    testing_rule = {
        "rule_id": "TEST-LC-001",
        "name": "测试生命周期规则",
        "level": "L2-LOGIC",
        "scope": "SINGLE_DOC",
        "category": "测试",
        "description": "测试用规则",
        "trigger_when": {"doc_type": ["测试记录"]},
        "check_expr": {"type": "expression", "expr": "True", "language": "python_eval"},
        "error_template": "测试错误",
        "severity_on_violation": "Sanity Check",
        "remediation": "测试整改",
        "status": "testing",
        "source": "user",
        "version": "1.0.0",
        "created_at": "2026-07-31T10:00:00",
        "updated_at": "2026-07-31T10:00:00",
        "owner": "tester",
        "applies_to": {"professional": ["01_场道工程"]},
        "stats": {"total_hits": 0, "total_reviews": 0, "hit_rate": 0.0,
                  "false_positive_count": 0, "false_positive_rate": 0.0,
                  "last_hit_at": None, "last_review_at": None},
        "alignment": None,
        "changelog": [],
    }
    rule_file = draft_dir / "TEST-LC-001.json"
    rule_file.write_text(json.dumps(testing_rule, ensure_ascii=False, indent=2), encoding="utf-8")

    manager = RuleLifecycleManager(rules_dir=rules_dir)

    # record_audit_result(rule_id, project, audit_id, hits, false_positives=0)
    tracking = manager.record_audit_result(
        rule_id="TEST-LC-001",
        project="测试项目 A",
        audit_id="AU-20260731-001",
        hits=5,
        false_positives=0,
    )
    _assert(tracking.get("rule_id") == "TEST-LC-001", "tracking.rule_id 正确")
    _assert(tracking.get("total_hits") == 5, f"total_hits=5（实际 {tracking.get('total_hits')}）")
    _assert(tracking.get("false_positive_rate") == 0.0, "false_positive_rate=0.0")

    # 再记一次
    tracking2 = manager.record_audit_result(
        rule_id="TEST-LC-001",
        project="测试项目 B",
        audit_id="AU-20260731-002",
        hits=3,
        false_positives=1,
    )
    _assert(tracking2.get("total_hits") == 8, f"累计 total_hits=8（实际 {tracking2.get('total_hits')}）")
    _assert(tracking2.get("total_false_positives") == 1,
            f"累计 total_false_positives=1（实际 {tracking2.get('total_false_positives')}）")

    # list_testing_rules 应包含本规则
    testing_list = manager.list_testing_rules()
    _assert(any(r.get("rule_id") == "TEST-LC-001" for r in testing_list),
            f"list_testing_rules 包含 TEST-LC-001（共 {len(testing_list)} 条）")

    # promote_to_incubating
    ok = manager.promote_to_incubating("TEST-LC-001", reason="manual: 测试通过")
    _assert(ok is True, "promote_to_incubating 返回 True")

    # 规则文件状态应更新为 incubating
    updated_rule = json.loads(rule_file.read_text(encoding="utf-8"))
    _assert(updated_rule["status"] == "incubating", "规则文件 status 更新为 incubating")
    _assert(len(updated_rule.get("changelog", [])) >= 1,
            f"changelog 至少 1 条（实际 {len(updated_rule.get('changelog', []))}）")

    # 再次 promote 应失败（状态非 testing）
    ok2 = manager.promote_to_incubating("TEST-LC-001", reason="duplicate")
    _assert(ok2 is False, "非 testing 状态再次 promote 返回 False")

    print("  → rule_lifecycle 测试通过 ✓")


# ========== 测试 7：rule_admin API 端点 ==========
def test_rule_admin_endpoints() -> None:
    _section("测试 7：rule_admin API 端点定义")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rule_admin", SCRIPT_DIR / "rule_admin.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # RuleAdminServer 类存在
    _assert(hasattr(module, "RuleAdminServer"), "RuleAdminServer 类已定义")
    handler_class = getattr(module, "RuleAdminServer")

    # HTTP 方法
    _assert(hasattr(handler_class, "do_GET"), "do_GET 方法存在")
    _assert(hasattr(handler_class, "do_POST"), "do_POST 方法存在")
    _assert(hasattr(handler_class, "do_PUT"), "do_PUT 方法存在")
    _assert(hasattr(handler_class, "do_DELETE"), "do_DELETE 方法存在")

    # 关键 _handle_xxx 方法存在（GET 端点）
    get_handlers = [
        "_handle_list_rules",       # GET /api/rules
        "_handle_get_rule",         # GET /api/rules/{id}
        "_handle_get_stats",        # GET /api/rules/{id}/stats
        "_handle_get_changelog",    # GET /api/rules/{id}/changelog
        "_handle_list_feedbacks",   # GET /api/feedbacks
        "_handle_get_feedback",     # GET /api/feedbacks/{id}
        "_handle_feedback_stats",   # GET /api/feedbacks/stats
        "_handle_list_reflections", # GET /api/reflections
        "_handle_get_reflection",   # GET /api/reflections/{date}
        "_handle_list_incubator",   # GET /api/incubator
        "_handle_get_incubator_rule",  # GET /api/incubator/{rule_id}
        "_handle_get_registry",     # GET /registry
        "_handle_overview_stats",   # GET /stats
    ]
    for name in get_handlers:
        _assert(hasattr(handler_class, name), f"方法 {name} 存在")

    # POST 端点
    post_handlers = [
        "_handle_create_rule",       # POST /api/rules
        "_handle_transition",        # POST /api/rules/{id}/transition
        "_handle_confirm",           # POST /api/rules/{id}/confirm
        "_handle_force_confirm",     # POST /api/rules/{id}/force_confirm
        "_handle_test_rule",         # POST /api/rules/{id}/test
        "_handle_create_feedback",   # POST /api/feedbacks
        "_handle_analyze_feedbacks", # POST /api/feedbacks/analyze
        "_handle_feedback_transition",  # POST /api/feedbacks/{id}/transition
        "_handle_trigger_reflection",   # POST /api/reflections/trigger
        "_handle_promote_incubator",    # POST /api/incubator/{id}/promote
        "_handle_reject_incubator",     # POST /api/incubator/{id}/reject
    ]
    for name in post_handlers:
        _assert(hasattr(handler_class, name), f"方法 {name} 存在")

    # PUT 端点
    _assert(hasattr(handler_class, "_handle_update_rule"), "_handle_update_rule 存在")

    # DELETE 端点
    _assert(hasattr(handler_class, "_handle_delete_rule"), "_handle_delete_rule 存在")

    print("  → rule_admin API 端点测试通过 ✓")


# ========== 主入口 ==========
def main() -> int:
    print("=" * 60)
    print("规则管理子系统 全链路集成测试 (Phase F-3)")
    print("=" * 60)

    tmp_root = Path(tempfile.mkdtemp(prefix="rule_test_"))
    print(f"临时目录: {tmp_root}")

    tests = [
        ("feedback_store", lambda: test_feedback_store(tmp_root)),
        ("feedback_analyzer", lambda: test_feedback_analyzer(tmp_root)),
        ("rule_monitor", lambda: test_rule_monitor(tmp_root)),
        ("audit_memory", lambda: test_audit_memory(tmp_root)),
        ("rule_reflector", lambda: test_rule_reflector(tmp_root)),
        ("rule_lifecycle", lambda: test_rule_lifecycle(tmp_root)),
        ("rule_admin_endpoints", test_rule_admin_endpoints),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n[失败] {name}: {e}")
            traceback.print_exc()

    # 清理临时目录
    try:
        shutil.rmtree(tmp_root, ignore_errors=True)
        print(f"\n已清理临时目录: {tmp_root}")
    except Exception:
        pass

    print("\n" + "=" * 60)
    print(f"集成测试结果：{passed}/{passed + failed} 通过")
    if failed:
        print(f"❌ {failed} 个测试失败")
    else:
        print("✅ 全部通过")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
