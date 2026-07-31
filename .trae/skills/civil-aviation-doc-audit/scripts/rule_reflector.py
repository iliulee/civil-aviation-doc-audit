# -*- coding: utf-8 -*-
"""
rule_reflector.py — 定时反思调度器（Phase D-3）
=================================================

职责（参考 specs/design-rule-management-subsystem/spec.md 第 4 节）：
  1. 汇总本周审核事件日志、反馈数据、规则命中统计
  2. 调用 LLM 生成《规则优化建议报告》，包含：
     - 新增规则建议（基于漏审模式）
     - 修改规则建议（基于误报分析）
     - 停用规则建议（基于低命中率）
     - 层级调整建议（L2→L3 或反向）
  3. 候选规则写入 rules/custom/incubator/
  4. 报告输出到 rules/reflections/YYYY-MM-DD.md
  5. 管理员可查看历史反思报告 / 列出孵化区候选规则
  6. 默认每周日凌晨 2:00 触发（DEFAULT_CRON = "0 2 * * 0"）
  7. 管理员可通过 CLI 手动触发

设计参考：specs/design-rule-management-subsystem/spec.md 第 4 节 LLM 反思调度器
依赖：Python 3.8+ 标准库；同目录下 audit_memory.py / rule_monitor.py / feedback_store.py

降级策略：
  - LLM：优先调用 OpenAI 风格 API（LLM_API_URL / LLM_API_KEY）；
    不可用时回退到规则化模板分析（基于统计数据生成建议）。
  - 各依赖模块缺失时降级为空数据，仍能输出空报告。

用法：
    python scripts/rule_reflector.py --reflect              # 立即执行一次反思
    python scripts/rule_reflector.py --reflect --dry-run    # 仅生成报告，不写候选规则
    python scripts/rule_reflector.py --reflect --days 14    # 指定反思周期
    python scripts/rule_reflector.py --list-reports         # 列出历史报告
    python scripts/rule_reflector.py --get-report 2026-07-30 # 查看指定报告
    python scripts/rule_reflector.py --list-incubator       # 列出孵化区候选规则
    python scripts/rule_reflector.py --promote REF-20260730-001 --reason "..."
    python scripts/rule_reflector.py --reject REF-20260730-001 --reason "..."
    python scripts/rule_reflector.py --schedule-info        # 打印调度配置建议
"""

import argparse
import json
import logging
import os
import re
import sys
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 路径与模块导入
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

DEFAULT_RULES_DIR = SKILL_ROOT / "rules"
DEFAULT_FEEDBACKS_DIR = SKILL_ROOT / "feedbacks"
DEFAULT_AUDIT_MEMORY_DIR = SKILL_ROOT / "audit_memory"
INCUBATOR_DIR = DEFAULT_RULES_DIR / "custom" / "incubator"
REFLECTIONS_DIR = DEFAULT_RULES_DIR / "reflections"

# 中国时区（+08:00）
CST = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# 调度配置
# ---------------------------------------------------------------------------
# 默认每周日凌晨 2:00 触发（分 时 日 月 周）
DEFAULT_CRON = "0 2 * * 0"

SCHEDULE_CONFIG: Dict[str, Any] = {
    "cron": DEFAULT_CRON,
    "timezone": "Asia/Shanghai",
    "description": "每周日凌晨 2:00 执行规则反思（汇总本周数据并生成优化建议报告）",
    "command": "python scripts/rule_reflector.py --reflect",
    "dry_run_command": "python scripts/rule_reflector.py --reflect --dry-run",
    "manual_trigger": "管理员可通过 --reflect 立即触发；--reflect --dry-run 仅生成报告",
    "platform_hint": {
        "linux_cron": f'0 2 * * 0 cd "{SKILL_ROOT}" && /usr/bin/python3 scripts/rule_reflector.py --reflect >> logs/reflector.log 2>&1',
        "windows_task_scheduler": (
            'schtasks /Create /SC WEEKLY /D SUN /TN "CivilAviationRuleReflector" '
            f'/TR \'pythonw "{SCRIPT_DIR / "rule_reflector.py"}" --reflect\' /ST 02:00'
        ),
    },
}

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    """返回当前 ISO 8601 时间戳（含 +08:00 时区）。"""
    return datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _today_str() -> str:
    """返回 YYYY-MM-DD 格式日期（用于报告文件名）。"""
    return datetime.now(CST).strftime("%Y-%m-%d")


def _today_compact() -> str:
    """返回 YYYYMMDD 格式日期（用于 rule_id）。"""
    return datetime.now(CST).strftime("%Y%m%d")


def _safe_load_json(path: Path, default: Any) -> Any:
    """安全读取 JSON 文件；失败返回 default。"""
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        logger.warning(f"读取 JSON 失败 {path}: {e}")
    return default


def _safe_write_json(path: Path, data: Any) -> bool:
    """安全写入 JSON 文件；成功返回 True。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True
    except (OSError, TypeError, ValueError) as e:
        logger.error(f"写入 JSON 失败 {path}: {e}")
        return False


def _bump_patch(version: str) -> str:
    """语义化版本 patch 号 +1：1.0.0 → 1.0.1。解析失败时追加 -1。"""
    try:
        parts = version.split(".")
        if len(parts) == 3:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
    except (ValueError, IndexError):
        pass
    return version + "-1"


# ---------------------------------------------------------------------------
# RuleReflector — 反思调度器主类
# ---------------------------------------------------------------------------
class RuleReflector:
    """定时反思调度器：汇总本周审核数据，调用 LLM 生成规则优化建议报告。

    通过 AuditMemory 获取审核事件，RuleMonitor 获取规则效力统计，FeedbackStore
    获取反馈数据；调用 LLM（不可用降级到模板）生成四类优化建议；候选规则写入
    rules/custom/incubator/；报告输出到 rules/reflections/YYYY-MM-DD.md。
    """

    # 候选规则 ID 前缀（与 feedback_analyzer.py 的 INC- 区分）
    CANDIDATE_PREFIX = "REF"

    def __init__(
        self,
        skill_dir: Path = SKILL_ROOT,
        rules_dir: Path = DEFAULT_RULES_DIR,
        feedbacks_dir: Path = DEFAULT_FEEDBACKS_DIR,
        audit_memory_dir: Path = DEFAULT_AUDIT_MEMORY_DIR,
        llm_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """初始化反思调度器。

        Args:
            skill_dir: Skill 根目录（用于解析相对路径）
            rules_dir: 规则目录（默认 rules/）
            feedbacks_dir: 反馈目录（默认 feedbacks/）
            audit_memory_dir: 审核记忆流目录（默认 audit_memory/）
            llm_config: LLM 配置字典（api_url / api_key / model / temperature）
        """
        self.skill_dir = Path(skill_dir).resolve()
        self.rules_dir = Path(rules_dir).resolve()
        self.feedbacks_dir = Path(feedbacks_dir).resolve()
        self.audit_memory_dir = Path(audit_memory_dir).resolve()

        self.incubator_dir = self.rules_dir / "custom" / "incubator"
        self.reflections_dir = self.rules_dir / "reflections"

        self.llm_config = llm_config or {}
        self.llm_backend = self._detect_llm_backend()

        # 懒加载依赖模块（避免在 import 阶段失败）
        self._memory = None  # type: Optional[Any]
        self._monitor = None  # type: Optional[Any]
        self._store = None  # type: Optional[Any]

    # ===== 后端检测 =====
    def _detect_llm_backend(self) -> str:
        """检测可用的 LLM 后端：api > template。"""
        api_url = self.llm_config.get("api_url") or os.environ.get("LLM_API_URL")
        api_key = self.llm_config.get("api_key") or os.environ.get("LLM_API_KEY")
        if api_url and api_key:
            return "api"
        return "template"

    def _get_memory(self):
        """懒加载 AuditMemory。"""
        if self._memory is None:
            try:
                from audit_memory import AuditMemory
                self._memory = AuditMemory(self.audit_memory_dir)
            except Exception as e:
                logger.warning(f"加载 AuditMemory 失败: {e}")
                self._memory = None
        return self._memory

    def _get_monitor(self):
        """懒加载 RuleMonitor。"""
        if self._monitor is None:
            try:
                from rule_monitor import RuleMonitor
                # RuleMonitor 需 audit_logs_dir / feedbacks_dir；这里只用于检测
                # 现有规则 stats，不需要 audit_logs_dir
                self._monitor = RuleMonitor(
                    self.rules_dir,
                    audit_logs_dir=None,
                    feedbacks_dir=self.feedbacks_dir,
                )
            except Exception as e:
                logger.warning(f"加载 RuleMonitor 失败: {e}")
                self._monitor = None
        return self._monitor

    def _get_store(self):
        """懒加载 FeedbackStore。"""
        if self._store is None:
            try:
                from feedback_store import FeedbackStore
                self._store = FeedbackStore(self.feedbacks_dir)
            except Exception as e:
                logger.warning(f"加载 FeedbackStore 失败: {e}")
                self._store = None
        return self._store

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def reflect(self, days: int = 7, dry_run: bool = False) -> Dict[str, Any]:
        """执行一次反思。

        Args:
            days: 反思周期（默认 7 天）
            dry_run: True 时仅生成报告，不写候选规则

        Returns:
            反思结果摘要字典
        """
        logger.info(
            "开始反思：days=%d dry_run=%s llm_backend=%s",
            days, dry_run, self.llm_backend,
        )

        # 1. 汇总本周数据
        summary = self._collect_weekly_summary(days)

        # 2. 生成四类优化建议
        suggestions = self._generate_optimization_suggestions(summary)

        # 3. 写入候选规则（dry_run 时跳过）
        if dry_run:
            candidates: List[Dict[str, Any]] = []
            logger.info("dry-run 模式：跳过候选规则写入")
        else:
            candidates = self._write_candidate_rules(suggestions)

        # 4. 生成报告
        report = self._generate_report(summary, suggestions, candidates, days, dry_run)
        report_path = self._write_report(report)

        result = {
            "status": "completed",
            "dry_run": dry_run,
            "days": days,
            "summary_stats": {
                "audit_count": summary.get("audit_count", 0),
                "feedback_count": summary.get("feedback_count", 0),
                "rules_triggered_count": summary.get("rules_triggered_count", 0),
                "low_activity_count": len(summary.get("low_activity_rules", [])),
                "high_fp_count": len(summary.get("high_fp_rules", [])),
                "dormant_count": len(summary.get("dormant_rules", [])),
            },
            "suggestions": {
                "new_rules": len(suggestions.get("new_rules", [])),
                "modify_rules": len(suggestions.get("modify_rules", [])),
                "deprecate_rules": len(suggestions.get("deprecate_rules", [])),
                "level_adjust": len(suggestions.get("level_adjust", [])),
            },
            "candidates_written": len(candidates),
            "report_path": str(report_path),
            "llm_backend": self.llm_backend,
        }
        logger.info("反思完成：%s", json.dumps(result, ensure_ascii=False))
        return result

    # ------------------------------------------------------------------
    # 数据汇总
    # ------------------------------------------------------------------
    def _collect_weekly_summary(self, days: int) -> Dict[str, Any]:
        """汇总本周审核事件/反馈/规则命中统计。

        Returns:
            {
                "days": int,
                "period_start": str,
                "period_end": str,
                "audit_count": int,
                "audit_events": [...],
                "feedback_count": int,
                "feedback_counts": {...},
                "feedback_items": [...],
                "missed_feedbacks": [...],
                "false_positive_feedbacks": [...],
                "rules_triggered_count": int,
                "rules_hit_count": int,
                "rule_hit_counter": {rule_id: count},
                "low_activity_rules": [...],
                "high_fp_rules": [...],
                "dormant_rules": [...],
                "downgrade_suggestions": [...],
            }
        """
        now = datetime.now(CST)
        period_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00+08:00")
        period_end = now.strftime("%Y-%m-%dT%H:%M:%S+08:00")

        summary: Dict[str, Any] = {
            "days": days,
            "period_start": period_start,
            "period_end": period_end,
        }

        # 1. 审核事件汇总（来自 AuditMemory）
        audit_events: List[Dict[str, Any]] = []
        memory = self._get_memory()
        if memory is not None:
            try:
                audit_events = memory.get_recent_events(days=days)
            except Exception as e:
                logger.warning(f"获取审核事件失败: {e}")
                audit_events = []

        # 仅保留 audit_completed 类型
        audit_completed_events = [
            e for e in audit_events if e.get("event_type") == "audit_completed"
        ]
        summary["audit_count"] = len(audit_completed_events)
        summary["audit_events"] = audit_completed_events
        summary["all_event_count"] = len(audit_events)
        summary["event_type_counts"] = dict(Counter(
            e.get("event_type", "") for e in audit_events
        ))

        # 聚合规则命中数
        rule_hit_counter: Counter = Counter()
        rules_triggered_count = 0
        rules_hit_count = 0
        for ev in audit_completed_events:
            ev_summary = ev.get("summary") or {}
            rules_triggered_count += int(ev_summary.get("rules_triggered", 0) or 0)
            rules_hit_count += int(ev_summary.get("rules_hit_count", 0) or 0)
            rule_details = ev.get("rule_details") or []
            for rd in rule_details:
                if isinstance(rd, dict):
                    rid = rd.get("rule_id", "")
                    hits = int(rd.get("hits", 0) or 0)
                    if rid:
                        rule_hit_counter[rid] += hits
        summary["rules_triggered_count"] = rules_triggered_count
        summary["rules_hit_count"] = rules_hit_count
        summary["rule_hit_counter"] = dict(rule_hit_counter)

        # 2. 反馈汇总（来自 FeedbackStore）
        feedback_items: List[Dict[str, Any]] = []
        feedback_counts: Dict[str, int] = {}
        store = self._get_store()
        if store is not None:
            try:
                feedback_items = store.list_all()
                feedback_counts = store.count()
            except Exception as e:
                logger.warning(f"获取反馈数据失败: {e}")
        summary["feedback_count"] = len(feedback_items)
        summary["feedback_counts"] = feedback_counts
        summary["feedback_items"] = feedback_items
        summary["missed_feedbacks"] = [
            f for f in feedback_items if f.get("type") == "missed"
        ]
        summary["false_positive_feedbacks"] = [
            f for f in feedback_items if f.get("type") == "false_positive"
        ]

        # 3. 规则效力统计（来自 RuleMonitor）
        low_activity: List[Dict[str, Any]] = []
        high_fp: List[Dict[str, Any]] = []
        dormant: List[Dict[str, Any]] = []
        downgrade_suggestions: List[Dict[str, Any]] = []
        monitor = self._get_monitor()
        if monitor is not None:
            try:
                low_activity = monitor.detect_low_activity()
            except Exception as e:
                logger.warning(f"检测低活跃规则失败: {e}")
            try:
                high_fp = monitor.detect_high_false_positive()
            except Exception as e:
                logger.warning(f"检测高误报规则失败: {e}")
            try:
                dormant = monitor.detect_dormant()
            except Exception as e:
                logger.warning(f"检测休眠规则失败: {e}")
            try:
                downgrade_result = monitor.auto_downgrade(dry_run=True)
                downgrade_suggestions = downgrade_result.get("downgraded", [])
                summary["exempted_l1"] = downgrade_result.get("exempted_l1", [])
            except Exception as e:
                logger.warning(f"生成降级建议失败: {e}")
                summary["exempted_l1"] = []
        else:
            summary["exempted_l1"] = []

        summary["low_activity_rules"] = low_activity
        summary["high_fp_rules"] = high_fp
        summary["dormant_rules"] = dormant
        summary["downgrade_suggestions"] = downgrade_suggestions

        return summary

    # ------------------------------------------------------------------
    # 优化建议生成
    # ------------------------------------------------------------------
    def _generate_optimization_suggestions(self, summary: Dict) -> Dict[str, Any]:
        """生成四类优化建议：新增/修改/停用/层级调整。

        优先调用 LLM；不可用时降级到模板分析。
        """
        if self.llm_backend == "api":
            llm_result = self._call_llm_for_suggestions(summary)
            if llm_result is not None:
                return llm_result
            # LLM 调用失败 → 降级到模板
            logger.warning("LLM 调用失败，降级到模板分析")
            self.llm_backend = "template"
        return self._template_suggestions(summary)

    def _call_llm_for_suggestions(self, summary: Dict) -> Optional[Dict[str, Any]]:
        """调用 LLM 生成优化建议；失败返回 None（由调用方降级到模板）。"""
        prompt = self._build_llm_prompt(summary)
        response = self._call_llm(prompt)
        if not response:
            return None
        parsed = self._parse_llm_response(response)
        if parsed is None:
            return None
        # 补充默认字段
        parsed.setdefault("new_rules", [])
        parsed.setdefault("modify_rules", [])
        parsed.setdefault("deprecate_rules", [])
        parsed.setdefault("level_adjust", [])
        return parsed

    def _build_llm_prompt(self, summary: Dict) -> str:
        """构造 LLM 提示词（基于本周汇总数据）。"""
        # 准备数据摘要（控制 token 数量）
        audit_count = summary.get("audit_count", 0)
        feedback_count = summary.get("feedback_count", 0)
        missed_count = len(summary.get("missed_feedbacks", []))
        fp_count = len(summary.get("false_positive_feedbacks", []))
        rules_hit_count = summary.get("rules_hit_count", 0)
        rules_triggered_count = summary.get("rules_triggered_count", 0)

        # 漏审反馈摘要（前 10 条）
        missed_preview = []
        for fb in summary.get("missed_feedbacks", [])[:10]:
            ui = fb.get("user_input") or {}
            ctx = fb.get("context") or {}
            missed_preview.append(
                f"- [{fb.get('feedback_id', '')}] {ui.get('summary', '')}"
                f"（字段: {ctx.get('field', 'N/A')}, 资料: {ctx.get('doc_file', 'N/A')}）"
            )
        missed_text = "\n".join(missed_preview) if missed_preview else "（无）"

        # 误报反馈摘要（前 10 条）
        fp_preview = []
        for fb in summary.get("false_positive_feedbacks", [])[:10]:
            ui = fb.get("user_input") or {}
            fp_preview.append(
                f"- [{fb.get('feedback_id', '')}] rule={fb.get('rule_id', 'N/A')} "
                f"{ui.get('summary', '')}"
            )
        fp_text = "\n".join(fp_preview) if fp_preview else "（无）"

        # 高误报规则清单
        high_fp_list = "\n".join(
            f"- {r.get('rule_id', '')} | {r.get('name', '')} | "
            f"hits={r.get('total_hits', 0)} fp_rate={r.get('false_positive_rate', 0)*100:.2f}%"
            for r in summary.get("high_fp_rules", [])[:10]
        ) or "（无）"

        # 低活跃规则清单
        low_activity_list = "\n".join(
            f"- {r.get('rule_id', '')} | {r.get('name', '')} | "
            f"reviews={r.get('total_reviews', 0)} hit_rate={r.get('hit_rate', 0)*100:.2f}%"
            for r in summary.get("low_activity_rules", [])[:10]
        ) or "（无）"

        # 休眠规则清单
        dormant_list = "\n".join(
            f"- {r.get('rule_id', '')} | last_hit={r.get('last_hit_at', 'N/A')} | "
            f"dormant_days={r.get('days_since_last_hit', 0)}"
            for r in summary.get("dormant_rules", [])[:10]
        ) or "（无）"

        # 规则命中 TOP 10
        rule_hit_counter = summary.get("rule_hit_counter", {}) or {}
        top_hit_rules = sorted(
            rule_hit_counter.items(), key=lambda x: -x[1]
        )[:10]
        top_hit_text = "\n".join(
            f"- {rid}: {cnt} 次" for rid, cnt in top_hit_rules
        ) or "（无）"

        prompt = (
            "你是民航施工资料审核系统的规则优化顾问。请基于以下本周汇总数据，"
            "生成《规则优化建议报告》的四类建议：新增规则、修改规则、停用规则、层级调整。\n\n"
            f"## 本周数据概览\n"
            f"- 审核次数：{audit_count}\n"
            f"- 反馈总数：{feedback_count}（漏审 {missed_count} / 误报 {fp_count}）\n"
            f"- 规则触发次数：{rules_triggered_count}\n"
            f"- 规则命中次数：{rules_hit_count}\n\n"
            f"## 漏审反馈摘要（用于新增规则建议）\n{missed_text}\n\n"
            f"## 误报反馈摘要（用于修改规则建议）\n{fp_text}\n\n"
            f"## 高误报规则（误报率 > 30%）\n{high_fp_list}\n\n"
            f"## 低活跃规则（≥50 次审核命中率 < 5%）\n{low_activity_list}\n\n"
            f"## 休眠规则（> 90 天未命中）\n{dormant_list}\n\n"
            f"## 规则命中 TOP 10\n{top_hit_text}\n\n"
            "## 输出要求\n"
            "请输出 JSON 对象，包含以下字段：\n"
            "{\n"
            '  "new_rules": [\n'
            '    {"description": "规则描述", "common_fields": ["字段1"], '
            '"common_doc_types": ["资料类型"], "suggested_level": "L2-LOGIC", '
            '"suggested_severity": "Sanity Check", "reason": "基于 N 条漏审反馈", '
            '"source_feedbacks": ["FB-..."]}\n'
            "  ],\n"
            '  "modify_rules": [\n'
            '    {"rule_id": "LG-001", "issue": "误报率高", "current_expr": "...", '
            '"suggested_fix": "增加排除条件", "reason": "..."}\n'
            "  ],\n"
            '  "deprecate_rules": [\n'
            '    {"rule_id": "BZ-001", "reason": "命中率 0%，超过 90 天未命中"}\n'
            "  ],\n"
            '  "level_adjust": [\n'
            '    {"rule_id": "LG-002", "from_level": "L2-LOGIC", "to_level": "L3-BUSINESS", '
            '"reason": "..."}\n'
            "  ]\n"
            "}\n"
            "仅输出 JSON，不要额外说明。每类建议最多 5 条。"
        )
        return prompt

    def _call_llm(self, prompt: str) -> Optional[str]:
        """调用 LLM API（OpenAI 风格 /v1/chat/completions）。"""
        api_url = self.llm_config.get("api_url") or os.environ.get("LLM_API_URL")
        api_key = self.llm_config.get("api_key") or os.environ.get("LLM_API_KEY")
        if not api_url or not api_key:
            return None

        payload = {
            "model": self.llm_config.get("model") or os.environ.get("LLM_MODEL", "gpt-4o-mini"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(self.llm_config.get("temperature", 0.3)),
        }
        req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError) as e:
            logger.warning(f"LLM API 调用失败: {e}")
            return None

    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        """解析 LLM 返回的 JSON（容错：解析失败返回 None）。"""
        text = response.strip()
        # 提取 ```json ... ``` 代码块
        if "```" in text:
            m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
            if m:
                text = m.group(1).strip()
        # 定位首个 { 到末尾 }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as e:
            logger.warning(f"LLM 响应 JSON 解析失败: {e}")
        return None

    def _template_suggestions(self, summary: Dict) -> Dict[str, Any]:
        """模板降级方案：基于统计数据生成四类建议。

        规则化策略：
          - new_rules：基于漏审反馈聚类（按 field / doc_type 简单分组）
          - modify_rules：基于高误报规则清单
          - deprecate_rules：基于休眠规则清单（>90 天未命中）
          - level_adjust：基于高误报规则的降级建议
        """
        new_rules: List[Dict[str, Any]] = []
        modify_rules: List[Dict[str, Any]] = []
        deprecate_rules: List[Dict[str, Any]] = []
        level_adjust: List[Dict[str, Any]] = []

        # ===== 新增规则建议：基于漏审反馈 =====
        # 按 field + doc_type 聚类（同一字段/资料类型的漏审合并）
        missed_groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for fb in summary.get("missed_feedbacks", []):
            ctx = fb.get("context") or {}
            field = str(ctx.get("field") or "")
            doc_file = str(ctx.get("doc_file") or "")
            doc_type = re.sub(r"\d+", "", Path(doc_file).stem) if doc_file else ""
            key = (field, doc_type)
            missed_groups.setdefault(key, []).append(fb)

        for (field, doc_type), group in sorted(
            missed_groups.items(), key=lambda x: -len(x[1])
        ):
            if len(group) < 1:
                continue
            ui_first = (group[0].get("user_input") or {})
            suggested_level = ui_first.get("expected_rule_type", "L3-BUSINESS")
            suggested_severity = ui_first.get("expected_severity", "Best Practice")
            description = ui_first.get("suggested_rule_description") or (
                f"针对字段 {field or 'N/A'}、资料类型 {doc_type or 'N/A'} 的校验规则"
            )
            new_rules.append({
                "description": description,
                "common_fields": [field] if field else [],
                "common_doc_types": [doc_type] if doc_type else [],
                "suggested_level": suggested_level,
                "suggested_severity": suggested_severity,
                "reason": (
                    f"基于 {len(group)} 条漏审反馈"
                    f"（字段: {field or 'N/A'}, 资料: {doc_type or 'N/A'}）"
                ),
                "source_feedbacks": [g.get("feedback_id", "") for g in group],
            })
            if len(new_rules) >= 5:
                break

        # ===== 修改规则建议：基于高误报规则 =====
        for r in summary.get("high_fp_rules", [])[:5]:
            modify_rules.append({
                "rule_id": r.get("rule_id", ""),
                "issue": (
                    f"误报率 {r.get('false_positive_rate', 0)*100:.2f}% > 30%，"
                    f"命中数 {r.get('total_hits', 0)}"
                ),
                "current_expr": "（需人工查阅规则文件）",
                "suggested_fix": (
                    "复核 check_expr，考虑增加排除条件、收紧匹配范围或调整阈值"
                ),
                "reason": (
                    f"误报率 {r.get('false_positive_rate', 0)*100:.2f}% 超过 30% 阈值"
                ),
            })

        # ===== 停用规则建议：基于休眠规则 =====
        for r in summary.get("dormant_rules", [])[:5]:
            deprecate_rules.append({
                "rule_id": r.get("rule_id", ""),
                "reason": (
                    f"已休眠 {r.get('days_since_last_hit', 0)} 天"
                    f"（最近命中: {r.get('last_hit_at', 'N/A')}），建议停用"
                ),
            })

        # ===== 层级调整建议：基于高误报规则的降级 =====
        for r in summary.get("high_fp_rules", [])[:5]:
            level = r.get("level", "")
            if level == "L1-IRON":
                # L1 铁律不降级
                continue
            elif level == "L2-LOGIC":
                level_adjust.append({
                    "rule_id": r.get("rule_id", ""),
                    "from_level": "L2-LOGIC",
                    "to_level": "L3-BUSINESS",
                    "reason": (
                        f"误报率 {r.get('false_positive_rate', 0)*100:.2f}% > 30%，"
                        "建议降级 L2→L3"
                    ),
                })
            elif level == "L3-BUSINESS":
                level_adjust.append({
                    "rule_id": r.get("rule_id", ""),
                    "from_level": "L3-BUSINESS",
                    "to_level": "deprecated",
                    "reason": (
                        f"误报率 {r.get('false_positive_rate', 0)*100:.2f}% > 30%，"
                        "建议停用 L3 规则"
                    ),
                })

        # 同时考虑 RuleMonitor 的降级建议（与上面去重）
        existing_ids = {la.get("rule_id") for la in level_adjust}
        for d in summary.get("downgrade_suggestions", []):
            rid = d.get("rule_id", "")
            if rid in existing_ids:
                continue
            level_adjust.append({
                "rule_id": rid,
                "from_level": d.get("from_level", ""),
                "to_level": d.get("to", ""),
                "reason": d.get("reason", ""),
            })
            existing_ids.add(rid)

        return {
            "new_rules": new_rules,
            "modify_rules": modify_rules,
            "deprecate_rules": deprecate_rules,
            "level_adjust": level_adjust,
        }

    # ------------------------------------------------------------------
    # 候选规则生成与写入
    # ------------------------------------------------------------------
    def _write_candidate_rules(self, suggestions: Dict) -> List[Dict[str, Any]]:
        """将"新增规则建议"转化为候选规则 JSON，写入 incubator 目录。

        Returns:
            已写入的候选规则摘要列表 [{rule_id, file}]
        """
        new_rules = suggestions.get("new_rules", [])
        if not new_rules:
            return []

        self.incubator_dir.mkdir(parents=True, exist_ok=True)
        date_compact = _today_compact()
        # 计算当日已有 REF-{date}-NNN 的最大序号
        base_seq = self._max_incubator_seq(date_compact)

        written: List[Dict[str, Any]] = []
        for idx, suggestion in enumerate(new_rules, start=base_seq + 1):
            rule_id = f"{self.CANDIDATE_PREFIX}-{date_compact}-{idx:03d}"
            candidate = self._build_candidate_rule(rule_id, suggestion)
            try:
                fp = self.incubator_dir / f"{rule_id}.json"
                fp.write_text(
                    json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                written.append({
                    "rule_id": rule_id,
                    "file": str(fp.relative_to(self.rules_dir).as_posix()),
                    "description": suggestion.get("description", ""),
                    "suggested_level": suggestion.get("suggested_level", "L3-BUSINESS"),
                })
                logger.info(f"写入候选规则: {rule_id} → {fp}")
            except OSError as e:
                logger.error(f"写入候选规则失败 {rule_id}: {e}")
        return written

    def _build_candidate_rule(
        self, rule_id: str, suggestion: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构造候选规则 JSON 对象。"""
        description = suggestion.get("description", "候选规则（待人工补充）")
        name = f"[反思] {description[:50]}"
        now = _now_iso()
        today = _today_str()

        common_fields = suggestion.get("common_fields", [])
        common_doc_types = suggestion.get("common_doc_types", [])
        suggested_level = suggestion.get("suggested_level", "L3-BUSINESS")
        suggested_severity = suggestion.get("suggested_severity", "Best Practice")
        source_feedbacks = suggestion.get("source_feedbacks", [])
        reason = suggestion.get("reason", "")

        return {
            "rule_id": rule_id,
            "name": name,
            "level": suggested_level,
            "scope": "SINGLE_DOC",
            "category": "反思候选",
            "description": description,
            "trigger_when": {
                "doc_type": common_doc_types,
                "field_required": common_fields,
            },
            "check_expr": {
                "type": "expression",
                "expr": "# TODO: 人工补充校验表达式",
                "language": "jinja-expr",
            },
            "error_template": f"待补充：{description[:80]}",
            "severity_on_violation": suggested_severity,
            "status": "incubating",
            "source": "incubated",
            "version": "0.1.0",
            "created_at": now,
            "updated_at": now,
            "owner": "rule_reflector",
            "changelog": [{
                "version": "0.1.0",
                "date": today,
                "author": "rule_reflector",
                "change": (
                    f"由反思调度器自动生成（{today}）；"
                    f"建议类型：新增规则；原因：{reason}"
                ),
            }],
            "stats": {
                "total_hits": 0,
                "total_reviews": 0,
                "hit_rate": 0.0,
                "false_positive_count": 0,
                "false_positive_rate": 0.0,
                "last_hit_at": None,
                "last_review_at": None,
            },
            "alignment": None,
            "incubation_meta": {
                "reflection_date": today,
                "suggestion_type": "new_rule",
                "source_feedbacks": source_feedbacks,
                "reason": reason,
                "auto_generated": True,
                "needs_human_review": True,
            },
        }

    def _max_incubator_seq(self, date_compact: str) -> int:
        """扫描 incubator 目录，返回 REF-{date_compact}-NNN 的最大序号。"""
        if not self.incubator_dir.is_dir():
            return 0
        pattern = re.compile(
            rf"^{self.CANDIDATE_PREFIX}-{date_compact}-(\d{{3}})\.json$"
        )
        max_seq = 0
        for p in self.incubator_dir.iterdir():
            m = pattern.match(p.name)
            if m:
                try:
                    seq = int(m.group(1))
                    if seq > max_seq:
                        max_seq = seq
                except ValueError:
                    continue
        return max_seq

    # ------------------------------------------------------------------
    # 报告生成
    # ------------------------------------------------------------------
    def _generate_report(
        self,
        summary: Dict,
        suggestions: Dict,
        candidates: List[Dict],
        days: int,
        dry_run: bool,
    ) -> str:
        """生成 Markdown 报告。"""
        date_str = _today_str()
        timestamp = _now_iso()

        new_rules = suggestions.get("new_rules", [])
        modify_rules = suggestions.get("modify_rules", [])
        deprecate_rules = suggestions.get("deprecate_rules", [])
        level_adjust = suggestions.get("level_adjust", [])

        lines: List[str] = []
        lines.append(f"# 规则优化建议报告 {date_str}")
        lines.append("")
        lines.append(f"> 生成时间：{timestamp}")
        lines.append(f"> 反思周期：最近 {days} 天（{summary.get('period_start', '')} ~ {summary.get('period_end', '')}）")
        lines.append(f"> 后端：llm_backend=`{self.llm_backend}`，dry_run=`{dry_run}`")
        lines.append("")

        # 1. 本周审核概览
        lines.append("## 1. 本周审核概览")
        lines.append("")
        lines.append(f"- 审核次数：**{summary.get('audit_count', 0)}**")
        lines.append(f"- 事件总数：{summary.get('all_event_count', 0)}")
        event_type_counts = summary.get("event_type_counts", {}) or {}
        if event_type_counts:
            type_lines = ", ".join(
                f"`{k}`: {v}" for k, v in sorted(event_type_counts.items())
            )
            lines.append(f"- 事件类型分布：{type_lines}")
        lines.append(f"- 反馈总数：**{summary.get('feedback_count', 0)}**"
                     f"（漏审 {len(summary.get('missed_feedbacks', []))} / "
                     f"误报 {len(summary.get('false_positive_feedbacks', []))}）")
        fb_counts = summary.get("feedback_counts", {}) or {}
        if fb_counts:
            fb_lines = ", ".join(
                f"`{k}`: {v}" for k, v in sorted(fb_counts.items())
            )
            lines.append(f"- 反馈状态分布：{fb_lines}")
        lines.append(f"- 规则触发次数：{summary.get('rules_triggered_count', 0)}")
        lines.append(f"- 规则命中次数：**{summary.get('rules_hit_count', 0)}**")

        # 规则命中 TOP 10
        rule_hit_counter = summary.get("rule_hit_counter", {}) or {}
        top_hit_rules = sorted(
            rule_hit_counter.items(), key=lambda x: -x[1]
        )[:10]
        if top_hit_rules:
            lines.append("")
            lines.append("### 规则命中 TOP 10")
            lines.append("")
            lines.append("| 规则ID | 命中次数 |")
            lines.append("|:---|:---|")
            for rid, cnt in top_hit_rules:
                lines.append(f"| `{rid}` | {cnt} |")
        lines.append("")

        # 2. 规则效力分析
        lines.append("## 2. 规则效力分析")
        lines.append("")

        # 2.1 低活跃规则
        low_activity = summary.get("low_activity_rules", [])
        lines.append(f"### 2.1 低活跃规则（≥50 次审核命中率 < 5%，共 {len(low_activity)} 条）")
        lines.append("")
        if low_activity:
            lines.append("| 规则ID | 名称 | 层级 | 审核次数 | 命中率 | 最近命中 |")
            lines.append("|:---|:---|:---|:---|:---|:---|")
            for r in low_activity[:10]:
                lines.append(
                    f"| `{r.get('rule_id', '')}` | {r.get('name', '')} | "
                    f"{r.get('level', '')} | {r.get('total_reviews', 0)} | "
                    f"{r.get('hit_rate', 0)*100:.2f}% | "
                    f"{r.get('last_hit_at') or '—'} |"
                )
        else:
            lines.append("_暂无低活跃规则_")
        lines.append("")

        # 2.2 高误报规则
        high_fp = summary.get("high_fp_rules", [])
        lines.append(f"### 2.2 高误报规则（误报率 > 30%，共 {len(high_fp)} 条）")
        lines.append("")
        if high_fp:
            lines.append("| 规则ID | 名称 | 层级 | 命中数 | 误报率 |")
            lines.append("|:---|:---|:---|:---|:---|")
            for r in high_fp[:10]:
                lines.append(
                    f"| `{r.get('rule_id', '')}` | {r.get('name', '')} | "
                    f"{r.get('level', '')} | {r.get('total_hits', 0)} | "
                    f"{r.get('false_positive_rate', 0)*100:.2f}% |"
                )
        else:
            lines.append("_暂无高误报规则_")
        lines.append("")

        # 2.3 休眠规则
        dormant = summary.get("dormant_rules", [])
        lines.append(f"### 2.3 休眠规则（>90 天未命中，共 {len(dormant)} 条）")
        lines.append("")
        if dormant:
            lines.append("| 规则ID | 名称 | 层级 | 最近命中 | 休眠天数 |")
            lines.append("|:---|:---|:---|:---|:---|")
            for r in dormant[:10]:
                lines.append(
                    f"| `{r.get('rule_id', '')}` | {r.get('name', '')} | "
                    f"{r.get('level', '')} | {r.get('last_hit_at', '')} | "
                    f"{r.get('days_since_last_hit', 0)} 天 |"
                )
        else:
            lines.append("_暂无休眠规则_")
        lines.append("")

        # L1 豁免清单
        exempted_l1 = summary.get("exempted_l1", []) or []
        if exempted_l1:
            lines.append(f"### 2.4 L1 铁律豁免清单（共 {len(exempted_l1)} 条）")
            lines.append("")
            lines.append("| 规则ID | 名称 | 误报率 | 豁免原因 |")
            lines.append("|:---|:---|:---|:---|")
            for r in exempted_l1[:10]:
                lines.append(
                    f"| `{r.get('rule_id', '')}` | {r.get('name', '')} | "
                    f"{r.get('false_positive_rate', 0)*100:.2f}% | "
                    f"{r.get('reason', '')} |"
                )
            lines.append("")

        # 3. 优化建议
        lines.append("## 3. 优化建议")
        lines.append("")

        # 3.1 新增规则建议
        lines.append(f"### 3.1 新增规则建议（基于漏审模式，共 {len(new_rules)} 条）")
        lines.append("")
        if new_rules:
            lines.append("| # | 描述 | 字段 | 资料类型 | 建议层级 | 建议严重度 | 原因 |")
            lines.append("|:---|:---|:---|:---|:---|:---|:---|")
            for i, s in enumerate(new_rules, 1):
                fields = ", ".join(s.get("common_fields", [])) or "—"
                docs = ", ".join(s.get("common_doc_types", [])) or "—"
                lines.append(
                    f"| {i} | {s.get('description', '')} | {fields} | {docs} | "
                    f"{s.get('suggested_level', '')} | "
                    f"{s.get('suggested_severity', '')} | "
                    f"{s.get('reason', '')} |"
                )
        else:
            lines.append("_暂无新增规则建议_")
        lines.append("")

        # 3.2 修改规则建议
        lines.append(f"### 3.2 修改规则建议（基于误报分析，共 {len(modify_rules)} 条）")
        lines.append("")
        if modify_rules:
            lines.append("| 规则ID | 问题 | 当前表达式 | 建议修复 | 原因 |")
            lines.append("|:---|:---|:---|:---|:---|")
            for s in modify_rules:
                lines.append(
                    f"| `{s.get('rule_id', '')}` | {s.get('issue', '')} | "
                    f"{s.get('current_expr', '')} | {s.get('suggested_fix', '')} | "
                    f"{s.get('reason', '')} |"
                )
        else:
            lines.append("_暂无修改规则建议_")
        lines.append("")

        # 3.3 停用规则建议
        lines.append(f"### 3.3 停用规则建议（基于低命中率，共 {len(deprecate_rules)} 条）")
        lines.append("")
        if deprecate_rules:
            lines.append("| 规则ID | 原因 |")
            lines.append("|:---|:---|")
            for s in deprecate_rules:
                lines.append(
                    f"| `{s.get('rule_id', '')}` | {s.get('reason', '')} |"
                )
        else:
            lines.append("_暂无停用规则建议_")
        lines.append("")

        # 3.4 层级调整建议
        lines.append(f"### 3.4 层级调整建议（共 {len(level_adjust)} 条）")
        lines.append("")
        if level_adjust:
            lines.append("| 规则ID | 原层级 | 新层级 | 原因 |")
            lines.append("|:---|:---|:---|:---|")
            for s in level_adjust:
                lines.append(
                    f"| `{s.get('rule_id', '')}` | {s.get('from_level', '')} | "
                    f"{s.get('to_level', '')} | {s.get('reason', '')} |"
                )
        else:
            lines.append("_暂无层级调整建议_")
        lines.append("")

        # 4. 候选规则清单
        lines.append("## 4. 候选规则清单")
        lines.append("")
        if dry_run:
            lines.append("_dry-run 模式：未写入候选规则文件。以下为本次建议的新增规则（已写入 / 未写入）。_")
            lines.append("")
        if candidates:
            lines.append("| rule_id | 类型 | 层级 | 文件 |")
            lines.append("|:---|:---|:---|:---|")
            for c in candidates:
                lines.append(
                    f"| `{c.get('rule_id', '')}` | 新增规则 | "
                    f"{c.get('suggested_level', '')} | "
                    f"`{c.get('file', '')}` |"
                )
        elif not dry_run:
            lines.append("_本次未生成候选规则_")
        lines.append("")

        # 5. 后端信息
        lines.append("## 5. 后端信息")
        lines.append("")
        lines.append(f"- llm_backend: `{self.llm_backend}`")
        lines.append(f"- dry_run: `{dry_run}`")
        lines.append(f"- 反思周期: {days} 天")
        lines.append(f"- 报告路径: `{self.reflections_dir / f'{date_str}.md'}`")
        lines.append(f"- 候选规则目录: `{self.incubator_dir.as_posix()}`")
        if self.llm_backend == "template":
            lines.append("")
            lines.append("> 本次使用**规则化模板**（LLM 不可用）。"
                         "建议配置 `LLM_API_URL` / `LLM_API_KEY` 环境变量以启用 LLM 模式。")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(f"_报告由 `rule_reflector.py` 自动生成（DEFAULT_CRON=`{DEFAULT_CRON}`）_")
        lines.append("")

        return "\n".join(lines)

    def _write_report(self, report: str) -> Path:
        """将报告写入 rules/reflections/YYYY-MM-DD.md。"""
        self.reflections_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.reflections_dir / f"{_today_str()}.md"
        report_path.write_text(report, encoding="utf-8")
        logger.info(f"反思报告已写入: {report_path}")
        return report_path

    # ------------------------------------------------------------------
    # 报告查询接口
    # ------------------------------------------------------------------
    def list_reports(self) -> List[Dict[str, Any]]:
        """列出历史反思报告。

        Returns:
            [{date, file, size, mtime, title}]，按日期降序
        """
        if not self.reflections_dir.is_dir():
            return []
        reports: List[Dict[str, Any]] = []
        for p in sorted(self.reflections_dir.glob("*.md"), reverse=True):
            # 仅识别 YYYY-MM-DD.md 格式
            if not re.match(r"^\d{4}-\d{2}-\d{2}\.md$", p.name):
                continue
            try:
                stat = p.stat()
                size = stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=CST).strftime(
                    "%Y-%m-%dT%H:%M:%S+08:00"
                )
            except OSError:
                size = 0
                mtime = ""
            # 读取首行作为标题
            title = p.stem
            try:
                with open(p, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                if first_line.startswith("#"):
                    title = first_line.lstrip("# ").strip()
            except (OSError, UnicodeDecodeError):
                pass
            reports.append({
                "date": p.stem,
                "file": str(p),
                "size": size,
                "mtime": mtime,
                "title": title,
            })
        return reports

    def get_report(self, date_str: str) -> Optional[str]:
        """获取指定日期报告内容；不存在返回 None。"""
        # 容错：允许传入带或不带 .md 后缀
        if not date_str.endswith(".md"):
            date_str = date_str + ".md"
        path = self.reflections_dir / date_str
        if not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"读取报告失败 {path}: {e}")
            return None

    # ------------------------------------------------------------------
    # 孵化区候选规则管理
    # ------------------------------------------------------------------
    def list_incubator_rules(self) -> List[Dict[str, Any]]:
        """列出孵化区候选规则。

        Returns:
            [{rule_id, name, level, status, source, created_at, file, description}]
            按 created_at 降序
        """
        if not self.incubator_dir.is_dir():
            return []
        items: List[Dict[str, Any]] = []
        for p in sorted(self.incubator_dir.glob("*.json")):
            data = _safe_load_json(p, None)
            if not isinstance(data, dict):
                continue
            items.append({
                "rule_id": data.get("rule_id", p.stem),
                "name": data.get("name", ""),
                "level": data.get("level", ""),
                "status": data.get("status", ""),
                "source": data.get("source", ""),
                "created_at": data.get("created_at", ""),
                "description": data.get("description", ""),
                "file": str(p),
            })
        # 按 created_at 降序
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items

    def promote_candidate(self, rule_id: str, reason: str) -> bool:
        """提升候选规则为 active。

        - 校验当前 status 必须为 incubating
        - 将 status 改为 active，追加 changelog，写回文件
        - 通过 AuditMemory 记录 rule_promoted 事件

        Args:
            rule_id: 候选规则 ID（如 REF-20260730-001）
            reason: 提升原因

        Returns:
            是否成功
        """
        rule_file = self.incubator_dir / f"{rule_id}.json"
        data = _safe_load_json(rule_file, None)
        if not isinstance(data, dict):
            logger.warning(f"promote_candidate: 候选规则文件未找到或格式异常 {rule_id}")
            return False

        current_status = data.get("status")
        if current_status != "incubating":
            logger.warning(
                f"promote_candidate: 规则 {rule_id} 当前状态为 {current_status}，"
                f"非 incubating，无法提升"
            )
            return False

        old_version = data.get("version", "0.1.0")
        new_version = _bump_patch(old_version)
        old_status = current_status

        data["status"] = "active"
        data["version"] = new_version
        data["updated_at"] = _now_iso()

        # 追加 changelog
        changelog = data.get("changelog") or []
        if not isinstance(changelog, list):
            changelog = []
        changelog.append({
            "version": new_version,
            "date": _today_str(),
            "author": "rule_reflector.admin",
            "change": (
                f"管理员提升候选规则: {old_status} → active"
                f"（原因: {reason}）"
            ),
        })
        data["changelog"] = changelog

        # 更新 incubation_meta
        meta = data.get("incubation_meta") or {}
        if isinstance(meta, dict):
            meta["promoted_at"] = _now_iso()
            meta["promote_reason"] = reason
            meta["promoted_by"] = "rule_reflector.admin"
            data["incubation_meta"] = meta

        if not _safe_write_json(rule_file, data):
            return False
        logger.info(f"候选规则 {rule_id} 已提升为 active（原因: {reason}）")

        # 记录 AuditMemory 事件
        memory = self._get_memory()
        if memory is not None:
            try:
                memory.append_rule_promoted(
                    rule_id=rule_id,
                    from_status=old_status,
                    to_status="active",
                    reason=reason,
                )
            except Exception as e:
                logger.warning(f"记录 rule_promoted 事件失败: {e}")
        return True

    def reject_candidate(self, rule_id: str, reason: str) -> bool:
        """驳回候选规则（标记 deprecated）。

        - 校验当前 status 必须为 incubating
        - 将 status 改为 deprecated，追加 changelog，写回文件

        Args:
            rule_id: 候选规则 ID
            reason: 驳回原因

        Returns:
            是否成功
        """
        rule_file = self.incubator_dir / f"{rule_id}.json"
        data = _safe_load_json(rule_file, None)
        if not isinstance(data, dict):
            logger.warning(f"reject_candidate: 候选规则文件未找到或格式异常 {rule_id}")
            return False

        current_status = data.get("status")
        if current_status != "incubating":
            logger.warning(
                f"reject_candidate: 规则 {rule_id} 当前状态为 {current_status}，"
                f"非 incubating，无法驳回"
            )
            return False

        old_version = data.get("version", "0.1.0")
        new_version = _bump_patch(old_version)
        old_status = current_status

        data["status"] = "deprecated"
        data["version"] = new_version
        data["updated_at"] = _now_iso()

        # 追加 changelog
        changelog = data.get("changelog") or []
        if not isinstance(changelog, list):
            changelog = []
        changelog.append({
            "version": new_version,
            "date": _today_str(),
            "author": "rule_reflector.admin",
            "change": (
                f"管理员驳回候选规则: {old_status} → deprecated"
                f"（原因: {reason}）"
            ),
        })
        data["changelog"] = changelog

        # 更新 incubation_meta
        meta = data.get("incubation_meta") or {}
        if isinstance(meta, dict):
            meta["rejected_at"] = _now_iso()
            meta["reject_reason"] = reason
            meta["rejected_by"] = "rule_reflector.admin"
            data["incubation_meta"] = meta

        if not _safe_write_json(rule_file, data):
            return False
        logger.info(f"候选规则 {rule_id} 已驳回（deprecated）（原因: {reason}）")

        # 记录 AuditMemory 事件（rule_transitioned）
        memory = self._get_memory()
        if memory is not None:
            try:
                memory.append_rule_transitioned(
                    rule_id=rule_id,
                    from_status=old_status,
                    to_status="deprecated",
                    reason=reason,
                    operator="admin",
                )
            except Exception as e:
                logger.warning(f"记录 rule_transitioned 事件失败: {e}")
        return True


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="民航施工资料审核 Skill — 定时反思调度器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--skill-dir", default=str(SKILL_ROOT),
        help=f"Skill 根目录（默认 {SKILL_ROOT}）",
    )
    parser.add_argument(
        "--rules-dir", default=str(DEFAULT_RULES_DIR),
        help=f"规则目录（默认 {DEFAULT_RULES_DIR}）",
    )
    parser.add_argument(
        "--feedbacks-dir", default=str(DEFAULT_FEEDBACKS_DIR),
        help=f"反馈目录（默认 {DEFAULT_FEEDBACKS_DIR}）",
    )
    parser.add_argument(
        "--audit-memory-dir", default=str(DEFAULT_AUDIT_MEMORY_DIR),
        help=f"审核记忆流目录（默认 {DEFAULT_AUDIT_MEMORY_DIR}）",
    )
    parser.add_argument(
        "--llm-api-url", default=None,
        help="LLM API URL（覆盖环境变量 LLM_API_URL）",
    )
    parser.add_argument(
        "--llm-api-key", default=None,
        help="LLM API Key（覆盖环境变量 LLM_API_KEY）",
    )
    parser.add_argument(
        "--llm-model", default=None,
        help="LLM 模型名（默认 gpt-4o-mini）",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="启用详细日志"
    )

    # 互斥动作组
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--reflect", action="store_true",
        help="立即执行一次反思",
    )
    group.add_argument(
        "--list-reports", action="store_true",
        help="列出历史反思报告",
    )
    group.add_argument(
        "--get-report", metavar="YYYY-MM-DD",
        help="查看指定日期的报告",
    )
    group.add_argument(
        "--list-incubator", action="store_true",
        help="列出孵化区候选规则",
    )
    group.add_argument(
        "--promote", metavar="RULE_ID",
        help="提升候选规则为 active（需配合 --reason）",
    )
    group.add_argument(
        "--reject", metavar="RULE_ID",
        help="驳回候选规则（标记 deprecated，需配合 --reason）",
    )
    group.add_argument(
        "--schedule-info", action="store_true",
        help="打印调度配置建议",
    )

    # --reflect 的附加参数
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅生成报告，不写候选规则（与 --reflect 配合）",
    )
    parser.add_argument(
        "--days", type=int, default=7,
        help="反思周期（天数，默认 7，与 --reflect 配合）",
    )
    parser.add_argument(
        "--reason", default="",
        help="提升/驳回原因（与 --promote / --reject 配合）",
    )
    return parser.parse_args(argv)


def _print_schedule_info() -> int:
    """打印调度配置建议。"""
    print("=" * 60)
    print("民航施工资料审核 Skill — 反思调度器配置")
    print("=" * 60)
    print(f"默认 cron 表达式: {DEFAULT_CRON}")
    print(f"  含义: 每周日凌晨 02:00 触发")
    print(f"时区: {SCHEDULE_CONFIG['timezone']}")
    print(f"说明: {SCHEDULE_CONFIG['description']}")
    print()
    print("执行命令:")
    print(f"  反思（写候选规则）: {SCHEDULE_CONFIG['command']}")
    print(f"  反思（dry-run）:   {SCHEDULE_CONFIG['dry_run_command']}")
    print(f"  手动触发:          {SCHEDULE_CONFIG['manual_trigger']}")
    print()
    print("Linux cron 配置示例:")
    print(f"  {SCHEDULE_CONFIG['platform_hint']['linux_cron']}")
    print()
    print("Windows 任务计划程序配置示例:")
    print(f"  {SCHEDULE_CONFIG['platform_hint']['windows_task_scheduler']}")
    print()
    print("其他常用 CLI:")
    print("  python scripts/rule_reflector.py --list-reports")
    print("  python scripts/rule_reflector.py --list-incubator")
    print("  python scripts/rule_reflector.py --get-report 2026-07-30")
    print("  python scripts/rule_reflector.py --promote REF-20260730-001 --reason \"...\"")
    print("  python scripts/rule_reflector.py --reject REF-20260730-001 --reason \"...\"")
    print()
    print("可配置项（环境变量）:")
    print("  LLM_API_URL  LLM_API_KEY  LLM_MODEL")
    print("=" * 60)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 调度信息（不需要初始化 RuleReflector）
    if args.schedule_info:
        return _print_schedule_info()

    # 构造 LLM 配置
    llm_config: Dict[str, Any] = {}
    if args.llm_api_url:
        llm_config["api_url"] = args.llm_api_url
    if args.llm_api_key:
        llm_config["api_key"] = args.llm_api_key
    if args.llm_model:
        llm_config["model"] = args.llm_model

    reflector = RuleReflector(
        skill_dir=Path(args.skill_dir),
        rules_dir=Path(args.rules_dir),
        feedbacks_dir=Path(args.feedbacks_dir),
        audit_memory_dir=Path(args.audit_memory_dir),
        llm_config=llm_config,
    )

    # --reflect
    if args.reflect:
        print("=" * 60)
        print("反思调度器启动")
        print("=" * 60)
        print(f"规则目录: {reflector.rules_dir}")
        print(f"反馈目录: {reflector.feedbacks_dir}")
        print(f"审核记忆流目录: {reflector.audit_memory_dir}")
        print(f"候选规则目录: {reflector.incubator_dir}")
        print(f"报告目录: {reflector.reflections_dir}")
        print(f"llm_backend: {reflector.llm_backend}")
        print(f"days: {args.days}")
        print(f"dry_run: {args.dry_run}")
        print("-" * 60)
        result = reflector.reflect(days=args.days, dry_run=args.dry_run)
        print("\n反思结果：")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # --list-reports
    if args.list_reports:
        reports = reflector.list_reports()
        print(f"历史反思报告（共 {len(reports)} 份）：")
        if not reports:
            print("（暂无报告）")
        for r in reports:
            print(f"  {r['date']} | {r['title']} | {r['size']} 字节 | {r['mtime']}")
        return 0

    # --get-report
    if args.get_report:
        content = reflector.get_report(args.get_report)
        if content is None:
            print(f"未找到日期为 {args.get_report} 的反思报告", file=sys.stderr)
            return 1
        print(content)
        return 0

    # --list-incubator
    if args.list_incubator:
        items = reflector.list_incubator_rules()
        print(f"孵化区候选规则（共 {len(items)} 条）：")
        if not items:
            print("（暂无候选规则）")
        for it in items:
            print(
                f"  {it['rule_id']} | {it['name']} | {it['level']} | "
                f"status={it['status']} | source={it['source']} | "
                f"created_at={it['created_at']}"
            )
        return 0

    # --promote
    if args.promote:
        if not args.reason:
            print("错误：--promote 必须配合 --reason 使用", file=sys.stderr)
            return 1
        ok = reflector.promote_candidate(args.promote, args.reason)
        if ok:
            print(f"候选规则 {args.promote} 已提升为 active")
            return 0
        else:
            print(f"提升失败：{args.promote}（请检查规则 ID 与当前状态）", file=sys.stderr)
            return 1

    # --reject
    if args.reject:
        if not args.reason:
            print("错误：--reject 必须配合 --reason 使用", file=sys.stderr)
            return 1
        ok = reflector.reject_candidate(args.reject, args.reason)
        if ok:
            print(f"候选规则 {args.reject} 已驳回（deprecated）")
            return 0
        else:
            print(f"驳回失败：{args.reject}（请检查规则 ID 与当前状态）", file=sys.stderr)
            return 1

    # 默认行为：显示简报
    print("民航施工资料审核 Skill — 定时反思调度器")
    print(f"规则目录: {reflector.rules_dir}")
    print(f"候选规则目录: {reflector.incubator_dir}")
    print(f"报告目录: {reflector.reflections_dir}")
    print(f"llm_backend: {reflector.llm_backend}")
    print()
    print("可用参数：")
    print("  --reflect                立即执行一次反思")
    print("  --reflect --dry-run      仅生成报告，不写候选规则")
    print("  --reflect --days 14      指定反思周期")
    print("  --list-reports           列出历史反思报告")
    print("  --get-report YYYY-MM-DD  查看指定报告")
    print("  --list-incubator         列出孵化区候选规则")
    print("  --promote RULE_ID --reason \"...\"  提升候选规则")
    print("  --reject RULE_ID --reason \"...\"   驳回候选规则")
    print("  --schedule-info          打印调度配置建议")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
