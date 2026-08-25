# -*- coding: utf-8 -*-
"""
rule_monitor.py — 规则效力自监控（Phase D-1）
================================================

职责：
  1. 从审核日志中提取每条规则的命中统计
  2. 更新规则 JSON 的 stats 字段（total_hits/total_reviews/hit_rate/
     false_positive_count/false_positive_rate/last_hit_at/last_review_at）
  3. 检测低活跃规则（50 次审核命中率 < 5%）→ 标记"低活跃"
  4. 检测高误报规则（误报率 > 30%）→ 自动降级（L2→L3 或 L3→deprecated）
  5. L1 铁律豁免自动降级
  6. 自动降级操作写入 changelog

设计参考：specs/design-rule-management-subsystem/spec.md 第 7.3 节
依赖：Python 3.8+ 标准库；可选 feedback_store.FeedbackStore（用于误报统计）

用法：
    python scripts/rule_monitor.py                    # 扫描所有审核日志，更新统计
    python scripts/rule_monitor.py --audit-log <path> # 只处理指定审核日志
    python scripts/rule_monitor.py --auto-downgrade   # 启用自动降级
    python scripts/rule_monitor.py --report           # 生成监控报告
"""

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 允许 import 同目录下的模块
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# 中国时区（+08:00）
CST = timezone(timedelta(hours=8))

logger = logging.getLogger(__name__)

# 规则层级常量（与 rule_engine.py 保持一致）
LEVEL_L1 = "L1-IRON"
LEVEL_L2 = "L2-LOGIC"
LEVEL_L3 = "L3-BUSINESS"

# 自动降级阈值
LOW_ACTIVITY_MIN_REVIEWS = 50
LOW_ACTIVITY_MAX_HIT_RATE = 0.05
HIGH_FP_MIN_HITS = 5
HIGH_FP_THRESHOLD = 0.30
DORMANT_DAYS = 90

# 降级映射：L2→L3，L3→deprecated
DOWNGRADE_MAP = {
    LEVEL_L2: LEVEL_L3,
    LEVEL_L3: "deprecated",  # deprecated 不是 level，而是 status
}


def _now_iso() -> str:
    """返回当前 ISO 8601 时间戳（含 +08:00 时区）。"""
    return datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _today_str() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


def _safe_load_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        logger.warning(f"读取 JSON 失败 {path}: {e}")
    return default


def _safe_write_json(path: Path, data: Any) -> bool:
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


class RuleMonitor:
    """规则效力自监控器。

    从审核日志中聚合每条规则的命中/误报统计，更新规则 JSON 的 stats 字段；
    检测低活跃/高误报规则；支持 L1 豁免的自动降级。
    """

    # 排除的子目录（与 RuleLoader 一致）
    EXCLUDED_DIRS = {"schema", "lifecycle", "custom"}
    EXCLUDED_FILES = {"registry.json"}

    def __init__(
        self,
        rules_dir: Path,
        audit_logs_dir: Optional[Path] = None,
        feedbacks_dir: Optional[Path] = None,
    ) -> None:
        self.rules_dir = Path(rules_dir).resolve()
        # audit_logs_dir 是所有项目审核日志的统一根目录；
        # 实际使用时也支持传入单项目下的"数据底座/审核日志"
        self.audit_logs_dir = Path(audit_logs_dir).resolve() if audit_logs_dir else None
        # feedbacks_dir 用于查询误报反馈
        self.feedbacks_dir = Path(feedbacks_dir).resolve() if feedbacks_dir else None

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def update_stats_from_audit_log(self, audit_log_path: Path) -> Dict[str, Any]:
        """从单个审核日志中提取命中统计，更新规则 stats。

        Args:
            audit_log_path: 审核日志 JSON 文件路径

        Returns:
            汇总字典：{audit_id, rules_updated, errors}
        """
        audit_log_path = Path(audit_log_path)
        audit_log = _safe_load_json(audit_log_path, None)
        if not isinstance(audit_log, dict):
            return {"audit_id": "", "rules_updated": 0, "errors": ["无法读取审核日志"]}

        audit_id = audit_log.get("audit_id", audit_log_path.stem)
        audit_completed_at = audit_log.get("audit_completed_at") or audit_log.get("audit_started_at") or _now_iso()

        # 1. 提取 rule_engine_findings，按 rule_id 聚合命中数
        rule_engine_findings = audit_log.get("rule_engine_findings", []) or []
        if not isinstance(rule_engine_findings, list):
            rule_engine_findings = []
        hits_by_rule: Dict[str, int] = Counter(
            f.get("rule_id", "") for f in rule_engine_findings if f.get("rule_id")
        )

        # 2. 查询本次审核的误报反馈
        false_positives_by_rule = self._count_false_positives(audit_id)

        # 3. 对每条命中的规则，更新 stats
        rules_updated = 0
        errors: List[str] = []
        all_rule_ids = set(hits_by_rule.keys()) | set(false_positives_by_rule.keys())

        for rule_id in all_rule_ids:
            hits = hits_by_rule.get(rule_id, 0)
            false_positives = false_positives_by_rule.get(rule_id, 0)

            rule_file = self._find_rule_file(rule_id)
            if rule_file is None:
                errors.append(f"规则文件未找到: {rule_id}")
                continue

            ok = self._update_rule_stats(
                rule_file=rule_file,
                rule_id=rule_id,
                hits=hits,
                false_positives=false_positives,
                audit_completed_at=audit_completed_at,
            )
            if ok:
                rules_updated += 1
            else:
                errors.append(f"更新规则 stats 失败: {rule_id}")

        return {
            "audit_id": audit_id,
            "rules_updated": rules_updated,
            "errors": errors,
            "hits_by_rule": dict(hits_by_rule),
            "false_positives_by_rule": dict(false_positives_by_rule),
        }

    def scan_all_audit_logs(self) -> Dict[str, Any]:
        """扫描所有审核日志，批量更新统计。

        遍历 audit_logs_dir 下所有 .json 文件（递归），对每个文件调用
        update_stats_from_audit_log。

        Returns:
            {total_logs, total_rules_updated, errors, logs_processed}
        """
        if not self.audit_logs_dir or not self.audit_logs_dir.is_dir():
            return {
                "total_logs": 0,
                "total_rules_updated": 0,
                "errors": ["审核日志目录不存在或未设置"],
                "logs_processed": [],
            }

        log_files = sorted(self.audit_logs_dir.rglob("AU-*.json"))
        total_logs = 0
        total_rules_updated = 0
        all_errors: List[str] = []
        logs_processed: List[str] = []

        for log_path in log_files:
            total_logs += 1
            result = self.update_stats_from_audit_log(log_path)
            if result.get("errors"):
                all_errors.extend(result["errors"])
            total_rules_updated += result.get("rules_updated", 0)
            logs_processed.append(str(log_path))

        return {
            "total_logs": total_logs,
            "total_rules_updated": total_rules_updated,
            "errors": all_errors,
            "logs_processed": logs_processed,
        }

    def detect_low_activity(
        self,
        threshold_reviews: int = LOW_ACTIVITY_MIN_REVIEWS,
        threshold_hit_rate: float = LOW_ACTIVITY_MAX_HIT_RATE,
    ) -> List[Dict[str, Any]]:
        """检测低活跃规则（50 次审核命中率 < 5%）。

        Returns:
            [{rule_id, name, level, total_reviews, hit_rate, last_hit_at}, ...]
        """
        result: List[Dict[str, Any]] = []
        for rule, rule_file in self._iter_all_rules_with_files():
            stats = rule.get("stats") or {}
            total_reviews = int(stats.get("total_reviews", 0) or 0)
            hit_rate = float(stats.get("hit_rate", 0.0) or 0.0)
            if total_reviews >= threshold_reviews and hit_rate < threshold_hit_rate:
                result.append({
                    "rule_id": rule.get("rule_id", ""),
                    "name": rule.get("name", ""),
                    "level": rule.get("level", ""),
                    "total_reviews": total_reviews,
                    "hit_rate": round(hit_rate, 4),
                    "last_hit_at": stats.get("last_hit_at"),
                })
        # 按 total_reviews 降序（活跃度最低的在前）
        result.sort(key=lambda x: x["total_reviews"], reverse=True)
        return result

    def detect_high_false_positive(
        self,
        threshold_fp_rate: float = HIGH_FP_THRESHOLD,
        min_hits: int = HIGH_FP_MIN_HITS,
    ) -> List[Dict[str, Any]]:
        """检测高误报规则（误报率 > 30%，命中数 ≥ 5）。

        Returns:
            [{rule_id, name, level, total_hits, false_positive_rate}, ...]
        """
        result: List[Dict[str, Any]] = []
        for rule, rule_file in self._iter_all_rules_with_files():
            stats = rule.get("stats") or {}
            total_hits = int(stats.get("total_hits", 0) or 0)
            fp_rate = float(stats.get("false_positive_rate", 0.0) or 0.0)
            if total_hits >= min_hits and fp_rate > threshold_fp_rate:
                result.append({
                    "rule_id": rule.get("rule_id", ""),
                    "name": rule.get("name", ""),
                    "level": rule.get("level", ""),
                    "total_hits": total_hits,
                    "false_positive_rate": round(fp_rate, 4),
                })
        # 按误报率降序
        result.sort(key=lambda x: x["false_positive_rate"], reverse=True)
        return result

    def detect_dormant(self, days: int = DORMANT_DAYS) -> List[Dict[str, Any]]:
        """检测休眠规则（> 90 天未命中）。

        Returns:
            [{rule_id, name, level, last_hit_at, days_since_last_hit}, ...]
        """
        result: List[Dict[str, Any]] = []
        now = datetime.now(CST)
        for rule, rule_file in self._iter_all_rules_with_files():
            stats = rule.get("stats") or {}
            last_hit_at = stats.get("last_hit_at")
            if not last_hit_at:
                continue
            try:
                # 兼容多种时间格式
                ts_str = str(last_hit_at).replace("Z", "+00:00")
                # 截断到秒
                if "+" in ts_str and "T" in ts_str:
                    last_dt = datetime.fromisoformat(ts_str)
                else:
                    # 尝试去掉时区后缀
                    last_dt = datetime.fromisoformat(ts_str[:19])
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=CST)
                days_since = (now - last_dt).days
                if days_since > days:
                    result.append({
                        "rule_id": rule.get("rule_id", ""),
                        "name": rule.get("name", ""),
                        "level": rule.get("level", ""),
                        "last_hit_at": last_hit_at,
                        "days_since_last_hit": days_since,
                    })
            except (ValueError, TypeError) as e:
                logger.debug(f"解析 last_hit_at 失败 rule_id={rule.get('rule_id')}: {e}")
                continue
        result.sort(key=lambda x: x["days_since_last_hit"], reverse=True)
        return result

    def auto_downgrade(self, dry_run: bool = False) -> Dict[str, Any]:
        """自动降级高误报规则。

        降级策略：
          - L1-IRON → 跳过（豁免）
          - L2-LOGIC → 降级为 L3-BUSINESS
          - L3-BUSINESS → 状态变为 deprecated

        Args:
            dry_run: True 仅返回降级清单，不修改规则文件

        Returns:
            {downgraded, exempted_l1, errors, dry_run}
        """
        high_fp_rules = self.detect_high_false_positive()
        downgraded: List[Dict[str, Any]] = []
        exempted_l1: List[Dict[str, Any]] = []
        errors: List[str] = []

        for item in high_fp_rules:
            rule_id = item["rule_id"]
            level = item["level"]
            fp_rate = item["false_positive_rate"]

            # L1 铁律豁免
            if level == LEVEL_L1:
                exempted_l1.append({
                    "rule_id": rule_id,
                    "name": item.get("name", ""),
                    "level": level,
                    "false_positive_rate": fp_rate,
                    "reason": "L1-IRON 铁律豁免自动降级",
                })
                continue

            target = DOWNGRADE_MAP.get(level)
            if target is None:
                # 未知层级，跳过
                continue

            if dry_run:
                downgraded.append({
                    "rule_id": rule_id,
                    "name": item.get("name", ""),
                    "from_level": level,
                    "to": target,
                    "false_positive_rate": fp_rate,
                    "reason": f"误报率 {fp_rate*100:.2f}% > 30%",
                    "dry_run": True,
                })
                continue

            # 实际执行降级
            rule_file = self._find_rule_file(rule_id)
            if rule_file is None:
                errors.append(f"规则文件未找到: {rule_id}")
                continue

            ok, from_value, to_value = self._apply_downgrade(
                rule_file=rule_file,
                rule_id=rule_id,
                from_level=level,
                target=target,
                fp_rate=fp_rate,
            )
            if ok:
                downgraded.append({
                    "rule_id": rule_id,
                    "name": item.get("name", ""),
                    "from_level": from_value if from_value else level,
                    "to": to_value,
                    "false_positive_rate": fp_rate,
                    "reason": f"误报率 {fp_rate*100:.2f}% > 30%",
                })
            else:
                errors.append(f"降级失败: {rule_id}")

        return {
            "downgraded": downgraded,
            "exempted_l1": exempted_l1,
            "errors": errors,
            "dry_run": dry_run,
        }

    def generate_report(self, out_path: Optional[Path] = None) -> Path:
        """生成监控报告 Markdown。

        Args:
            out_path: 输出文件路径；默认 rules/reflections/rule-monitor-{date}.md

        Returns:
            实际写入的报告文件路径
        """
        if out_path is None:
            reflections_dir = self.rules_dir / "reflections"
            reflections_dir.mkdir(parents=True, exist_ok=True)
            out_path = reflections_dir / f"rule-monitor-{_today_str()}.md"

        # 收集统计数据
        all_rules = [r for r, _ in self._iter_all_rules_with_files()]
        total_rules = len(all_rules)
        active_rules = [r for r in all_rules if r.get("status") == "active"]
        active_count = len(active_rules)

        # 平均命中率 / 误报率（基于 active 规则）
        hit_rates = []
        fp_rates = []
        for r in active_rules:
            stats = r.get("stats") or {}
            hit_rates.append(float(stats.get("hit_rate", 0.0) or 0.0))
            fp_rates.append(float(stats.get("false_positive_rate", 0.0) or 0.0))
        avg_hit_rate = sum(hit_rates) / len(hit_rates) if hit_rates else 0.0
        avg_fp_rate = sum(fp_rates) / len(fp_rates) if fp_rates else 0.0

        low_activity = self.detect_low_activity()
        high_fp = self.detect_high_false_positive()
        dormant = self.detect_dormant()

        # 构建报告
        lines: List[str] = []
        lines.append(f"# 规则效力监控报告 — {_today_str()}")
        lines.append("")
        lines.append(f"> 生成时间：{_now_iso()}")
        lines.append(f"> 规则目录：`{self.rules_dir}`")
        lines.append("")
        lines.append("## 1. 总体统计")
        lines.append("")
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|:---|:---|")
        lines.append(f"| 规则总数 | {total_rules} |")
        lines.append(f"| active 规则数 | {active_count} |")
        lines.append(f"| 平均命中率 | {avg_hit_rate*100:.2f}% |")
        lines.append(f"| 平均误报率 | {avg_fp_rate*100:.2f}% |")
        lines.append(f"| 低活跃规则数 | {len(low_activity)} |")
        lines.append(f"| 高误报规则数 | {len(high_fp)} |")
        lines.append(f"| 休眠规则数（>90天未命中） | {len(dormant)} |")
        lines.append("")

        # 低活跃 TOP 10
        lines.append("## 2. 低活跃规则 TOP 10（≥50 次审核，命中率 < 5%）")
        lines.append("")
        if low_activity:
            lines.append("| 规则ID | 名称 | 层级 | 审核次数 | 命中率 | 最近命中 |")
            lines.append("|:---|:---|:---|:---|:---|:---|")
            for item in low_activity[:10]:
                lines.append(
                    f"| {item['rule_id']} | {item['name']} | {item['level']} | "
                    f"{item['total_reviews']} | {item['hit_rate']*100:.2f}% | "
                    f"{item.get('last_hit_at') or '—'} |"
                )
        else:
            lines.append("_暂无低活跃规则_")
        lines.append("")

        # 高误报 TOP 10
        lines.append("## 3. 高误报规则 TOP 10（误报率 > 30%，命中数 ≥ 5）")
        lines.append("")
        if high_fp:
            lines.append("| 规则ID | 名称 | 层级 | 命中数 | 误报率 |")
            lines.append("|:---|:---|:---|:---|:---|")
            for item in high_fp[:10]:
                lines.append(
                    f"| {item['rule_id']} | {item['name']} | {item['level']} | "
                    f"{item['total_hits']} | {item['false_positive_rate']*100:.2f}% |"
                )
        else:
            lines.append("_暂无高误报规则_")
        lines.append("")

        # 休眠规则
        lines.append("## 4. 休眠规则（> 90 天未命中）")
        lines.append("")
        if dormant:
            lines.append("| 规则ID | 名称 | 层级 | 最近命中 | 休眠天数 |")
            lines.append("|:---|:---|:---|:---|:---|")
            for item in dormant[:10]:
                lines.append(
                    f"| {item['rule_id']} | {item['name']} | {item['level']} | "
                    f"{item['last_hit_at']} | {item['days_since_last_hit']} 天 |"
                )
        else:
            lines.append("_暂无休眠规则_")
        lines.append("")

        # 自动降级建议
        lines.append("## 5. 自动降级建议（dry-run）")
        lines.append("")
        downgrade_result = self.auto_downgrade(dry_run=True)
        if downgrade_result["downgraded"]:
            lines.append("| 规则ID | 名称 | 原层级 | 降级为 | 误报率 | 原因 |")
            lines.append("|:---|:---|:---|:---|:---|:---|")
            for item in downgrade_result["downgraded"]:
                lines.append(
                    f"| {item['rule_id']} | {item['name']} | {item['from_level']} | "
                    f"{item['to']} | {item['false_positive_rate']*100:.2f}% | "
                    f"{item['reason']} |"
                )
        else:
            lines.append("_暂无降级建议_")
        lines.append("")

        # L1 豁免清单
        lines.append("## 6. L1 铁律豁免清单")
        lines.append("")
        if downgrade_result["exempted_l1"]:
            lines.append("| 规则ID | 名称 | 误报率 | 豁免原因 |")
            lines.append("|:---|:---|:---|:---|")
            for item in downgrade_result["exempted_l1"]:
                lines.append(
                    f"| {item['rule_id']} | {item['name']} | "
                    f"{item['false_positive_rate']*100:.2f}% | {item['reason']} |"
                )
        else:
            lines.append("_暂无 L1 规则触发降级条件_")
        lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(f"_报告由 `rule_monitor.py` 自动生成_")

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out_path

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _count_false_positives(self, audit_id: str) -> Dict[str, int]:
        """查询某次审核的误报反馈，按 rule_id 聚合数量。

        优先使用 FeedbackStore；若 feedbacks_dir 不可用则返回空字典。
        """
        if not self.feedbacks_dir or not self.feedbacks_dir.is_dir():
            return {}
        try:
            from feedback_store import FeedbackStore
            store = FeedbackStore(self.feedbacks_dir)
            items = store.list_all(type="false_positive", audit_id=audit_id)
        except Exception as e:
            logger.debug(f"查询误报反馈失败 audit_id={audit_id}: {e}")
            return {}

        counter: Dict[str, int] = Counter(
            it.get("rule_id", "") for it in items if it.get("rule_id")
        )
        return dict(counter)

    def _update_rule_stats(
        self,
        rule_file: Path,
        rule_id: str,
        hits: int,
        false_positives: int,
        audit_completed_at: str,
    ) -> bool:
        """更新单条规则的 stats 字段并写回文件。"""
        data = _safe_load_json(rule_file, None)
        if not isinstance(data, dict):
            return False

        stats = data.get("stats") or {}
        # 兼容旧数据：补齐字段
        stats.setdefault("total_hits", 0)
        stats.setdefault("total_reviews", 0)
        stats.setdefault("hit_rate", 0.0)
        stats.setdefault("false_positive_count", 0)
        stats.setdefault("false_positive_rate", 0.0)
        stats.setdefault("last_hit_at", None)
        stats.setdefault("last_review_at", None)

        # 累加
        stats["total_hits"] = int(stats["total_hits"]) + int(hits)
        stats["total_reviews"] = int(stats["total_reviews"]) + 1
        stats["false_positive_count"] = int(stats["false_positive_count"]) + int(false_positives)

        # 重算比率
        stats["hit_rate"] = round(stats["total_hits"] / stats["total_reviews"], 4) if stats["total_reviews"] > 0 else 0.0
        stats["false_positive_rate"] = (
            round(stats["false_positive_count"] / stats["total_hits"], 4)
            if stats["total_hits"] > 0 else 0.0
        )

        # 时间戳
        if hits > 0:
            old_last_hit = stats.get("last_hit_at")
            stats["last_hit_at"] = self._max_timestamp(old_last_hit, audit_completed_at)
        stats["last_review_at"] = audit_completed_at

        data["stats"] = stats
        data["updated_at"] = _now_iso()
        return _safe_write_json(rule_file, data)

    @staticmethod
    def _max_timestamp(a: Optional[str], b: str) -> str:
        """返回两个 ISO 时间戳中较晚的一个；解析失败时返回 b。"""
        if not a:
            return b
        try:
            ta = datetime.fromisoformat(str(a).replace("Z", "+00:00"))
            tb = datetime.fromisoformat(str(b).replace("Z", "+00:00"))
            if ta.tzinfo is None:
                ta = ta.replace(tzinfo=CST)
            if tb.tzinfo is None:
                tb = tb.replace(tzinfo=CST)
            return a if ta >= tb else b
        except (ValueError, TypeError):
            return b

    def _apply_downgrade(
        self,
        rule_file: Path,
        rule_id: str,
        from_level: str,
        target: str,
        fp_rate: float,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """实际执行降级操作，写回规则文件并追加 changelog。

        Returns:
            (success, from_value, to_value)
            - L2 → L3：from_value=L2-LOGIC, to_value=L3-BUSINESS
            - L3 → deprecated：from_value=L3-BUSINESS, to_value=deprecated
        """
        data = _safe_load_json(rule_file, None)
        if not isinstance(data, dict):
            return False, None, None

        old_version = data.get("version", "1.0.0")
        new_version = self._bump_patch(old_version)

        from_value = data.get("level", from_level)

        if target == "deprecated":
            # L3 → deprecated：status 变为 deprecated，level 不变
            data["status"] = "deprecated"
            to_value = "deprecated"
            change_desc = (
                f"自动降级：L3-BUSINESS → deprecated（误报率 {fp_rate*100:.2f}% > 30%）"
            )
        else:
            # L2 → L3：level 变为 L3-BUSINESS
            data["level"] = LEVEL_L3
            to_value = LEVEL_L3
            change_desc = (
                f"自动降级：L2-LOGIC → L3-BUSINESS（误报率 {fp_rate*100:.2f}% > 30%）"
            )

        data["version"] = new_version
        data["updated_at"] = _now_iso()

        # 追加 changelog（沿用 rule_lifecycle 风格）
        changelog = data.get("changelog") or []
        if not isinstance(changelog, list):
            changelog = []
        changelog.append({
            "version": new_version,
            "date": datetime.now(CST).strftime("%Y-%m-%d"),
            "author": "rule_monitor.auto",
            "change": change_desc,
        })
        data["changelog"] = changelog

        ok = _safe_write_json(rule_file, data)
        if ok:
            logger.info(f"规则 {rule_id} 自动降级：{from_value} → {to_value}")
        return ok, from_value, to_value

    @staticmethod
    def _bump_patch(version: str) -> str:
        """语义化版本 patch 号 +1：1.0.0 → 1.0.1。"""
        try:
            parts = version.split(".")
            if len(parts) == 3:
                parts[2] = str(int(parts[2]) + 1)
                return ".".join(parts)
        except (ValueError, IndexError):
            pass
        return version + "-1"

    def _iter_all_rules_with_files(self) -> List[Tuple[Dict[str, Any], Path]]:
        """遍历所有规则文件，返回 [(rule_dict, file_path), ...]。"""
        result: List[Tuple[Dict[str, Any], Path]] = []
        if not self.rules_dir.is_dir():
            return result
        for p in sorted(self.rules_dir.rglob("*.json")):
            if self._is_excluded(p, self.rules_dir):
                continue
            data = _safe_load_json(p, None)
            if isinstance(data, dict) and "rule_id" in data:
                result.append((data, p))
        return result

    def _find_rule_file(self, rule_id: str) -> Optional[Path]:
        """按 rule_id 查找规则 JSON 文件。"""
        if not self.rules_dir.is_dir():
            return None
        for p in sorted(self.rules_dir.rglob("*.json")):
            if self._is_excluded(p, self.rules_dir):
                continue
            data = _safe_load_json(p, None)
            if isinstance(data, dict) and data.get("rule_id") == rule_id:
                return p
        return None

    def _is_excluded(self, path: Path, rules_dir: Path) -> bool:
        """判断文件是否应被排除（schema/lifecycle/custom/registry.json）。"""
        if path.name in self.EXCLUDED_FILES:
            return True
        try:
            rel = path.relative_to(rules_dir)
        except ValueError:
            return True
        for part in rel.parts[:-1]:
            if part in self.EXCLUDED_DIRS:
                return True
        return False


# ========== CLI 入口 ==========
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="民航施工资料审核 Skill — 规则效力自监控",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    skill_dir = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--rules-dir", default=str(skill_dir / "rules"),
        help=f"规则目录（默认 {skill_dir / 'rules'}）",
    )
    parser.add_argument(
        "--audit-logs-dir", default=None,
        help="审核日志目录（用于批量扫描；省略时仅处理 --audit-log 指定的文件）",
    )
    parser.add_argument(
        "--feedbacks-dir", default=str(skill_dir / "feedbacks"),
        help=f"反馈目录（默认 {skill_dir / 'feedbacks'}）",
    )
    parser.add_argument(
        "--audit-log", default=None,
        help="只处理指定的审核日志文件",
    )
    parser.add_argument(
        "--auto-downgrade", action="store_true",
        help="启用自动降级（误报率 > 30%）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅输出降级清单，不实际修改规则文件（与 --auto-downgrade 配合）",
    )
    parser.add_argument(
        "--report", action="store_true",
        help="生成监控报告 Markdown",
    )
    parser.add_argument(
        "--low-activity", action="store_true",
        help="列出低活跃规则",
    )
    parser.add_argument(
        "--high-fp", action="store_true",
        help="列出高误报规则",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)

    rules_dir = Path(args.rules_dir)
    audit_logs_dir = Path(args.audit_logs_dir) if args.audit_logs_dir else None
    feedbacks_dir = Path(args.feedbacks_dir)

    monitor = RuleMonitor(rules_dir, audit_logs_dir, feedbacks_dir)

    # 1. 扫描指定审核日志
    if args.audit_log:
        result = monitor.update_stats_from_audit_log(Path(args.audit_log))
        print(f"处理审核日志: {args.audit_log}")
        print(f"  audit_id: {result.get('audit_id', '')}")
        print(f"  更新规则数: {result.get('rules_updated', 0)}")
        if result.get("hits_by_rule"):
            print(f"  命中规则: {result['hits_by_rule']}")
        if result.get("errors"):
            for err in result["errors"]:
                print(f"  [!] {err}", file=sys.stderr)
        return 0

    # 2. 扫描所有审核日志
    if audit_logs_dir:
        print(f"扫描审核日志目录: {audit_logs_dir}")
        result = monitor.scan_all_audit_logs()
        print(f"  处理日志数: {result['total_logs']}")
        print(f"  更新规则数（累计）: {result['total_rules_updated']}")
        if result.get("errors"):
            for err in result["errors"][:10]:
                print(f"  [!] {err}", file=sys.stderr)

    # 3. 低活跃规则
    if args.low_activity:
        items = monitor.detect_low_activity()
        print(f"\n低活跃规则（≥50 次审核，命中率 < 5%）: {len(items)} 条")
        for it in items:
            print(f"  - {it['rule_id']} | {it['name']} | {it['level']} | "
                  f"reviews={it['total_reviews']} hit_rate={it['hit_rate']*100:.2f}%")

    # 4. 高误报规则
    if args.high_fp:
        items = monitor.detect_high_false_positive()
        print(f"\n高误报规则（误报率 > 30%，命中数 ≥ 5）: {len(items)} 条")
        for it in items:
            print(f"  - {it['rule_id']} | {it['name']} | {it['level']} | "
                  f"hits={it['total_hits']} fp_rate={it['false_positive_rate']*100:.2f}%")

    # 5. 自动降级
    if args.auto_downgrade:
        print("\n执行自动降级...")
        result = monitor.auto_downgrade(dry_run=args.dry_run)
        if args.dry_run:
            print("（dry-run 模式：仅输出清单，不修改规则文件）")
        print(f"  降级规则数: {len(result['downgraded'])}")
        for it in result["downgraded"]:
            print(f"  ↓ {it['rule_id']} | {it['name']} | "
                  f"{it.get('from_level', '')} → {it['to']} | "
                  f"fp_rate={it['false_positive_rate']*100:.2f}%")
        print(f"  L1 豁免数: {len(result['exempted_l1'])}")
        for it in result["exempted_l1"]:
            print(f"  ⊗ {it['rule_id']} | {it['name']} | "
                  f"fp_rate={it['false_positive_rate']*100:.2f}% | {it['reason']}")
        if result.get("errors"):
            for err in result["errors"]:
                print(f"  [!] {err}", file=sys.stderr)

    # 6. 生成报告
    if args.report:
        report_path = monitor.generate_report()
        print(f"\n监控报告已生成: {report_path}")

    # 默认行为：如果没有任何动作参数，输出简报
    if not any([args.audit_log, args.low_activity, args.high_fp,
                args.auto_downgrade, args.report, audit_logs_dir]):
        print("民航施工资料审核 Skill — 规则效力自监控")
        print(f"规则目录: {rules_dir}")
        print(f"反馈目录: {feedbacks_dir}")
        print("\n可用参数：")
        print("  --audit-log <path>   处理指定审核日志")
        print("  --audit-logs-dir <path>  批量扫描审核日志目录")
        print("  --low-activity       列出低活跃规则")
        print("  --high-fp            列出高误报规则")
        print("  --auto-downgrade     启用自动降级")
        print("  --dry-run            仅输出降级清单（与 --auto-downgrade 配合）")
        print("  --report             生成监控报告 Markdown")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
