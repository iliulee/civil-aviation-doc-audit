# -*- coding: utf-8 -*-
"""
audit_memory.py — 审核记忆流（Phase D-2）
==========================================

职责：
  1. 记录审核事件到 audit_memory/YYYY-MM-DD.jsonl（按日期分文件）
  2. 提供查询接口（按日期、按 audit_id、按 rule_id）
  3. 增量追加，不修改历史

事件类型枚举：
  - audit_completed   审核完成
  - feedback_received 收到反馈
  - feedback_analyzed  反馈分析完成
  - rule_transitioned  规则状态流转
  - rule_downgraded    规则自动降级
  - rule_promoted      候选规则提升

设计参考：specs/design-rule-management-subsystem/spec.md 第 7 节

事件日志格式（每行一个 JSON）：
  {
    "event_id": "EVT-2026-07-30-001",
    "event_type": "audit_completed",
    "audit_id": "AU-2026-07-30-001",
    "timestamp": "2026-07-30T15:30:00+08:00",
    "project_name": "项目名称",
    "project_path": "/data/projects/...",
    "summary": {...},
    "rule_details": [...],
    "feedbacks": []
  }

用法：
    from audit_memory import AuditMemory
    memory = AuditMemory(skill_dir / "audit_memory")
    memory.append_audit_completed(
        audit_id="AU-2026-07-30-001",
        project_name="...",
        project_path="...",
        summary={...},
        rule_details=[...],
    )

命令行：
    python scripts/audit_memory.py --list              # 列出所有事件日期
    python scripts/audit_memory.py --date 2026-07-30   # 查看某日事件
    python scripts/audit_memory.py --audit AU-...      # 查看某次审核事件
    python scripts/audit_memory.py --rule LG-001       # 查看某规则相关事件
"""

import argparse
import json
import logging
import re
import sys
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 中国时区（+08:00）
CST = timezone(timedelta(hours=8))

# 事件类型枚举
EVENT_TYPES = {
    "audit_completed",
    "feedback_received",
    "feedback_analyzed",
    "rule_transitioned",
    "rule_downgraded",
    "rule_promoted",
}

# 事件 ID 格式：EVT-YYYY-MM-DD-NNN
EVENT_ID_RE = re.compile(r"^EVT-\d{4}-\d{2}-\d{2}-\d{3}$")


def _now_iso() -> str:
    """返回当前 ISO 8601 时间戳（含 +08:00 时区）。"""
    return datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _today_str() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


class AuditMemory:
    """审核记忆流：增量追加事件日志到按日期分文件。

    文件路径：{memory_dir}/{YYYY-MM-DD}.jsonl
    每行一个 JSON 事件（JSON Lines 格式）。
    """

    # 类级可重入锁：保护 event_id 生成与 jsonl 追加的 check-then-act 临界区，
    # 避免并发追加时分配到相同 event_id。RLock 允许 append_event 与
    # _next_event_id / _append_to_jsonl 嵌套加锁而不死锁。
    _lock = threading.RLock()

    def __init__(self, memory_dir: Path) -> None:
        """初始化。

        Args:
            memory_dir: 记忆流目录（如 skill_dir / "audit_memory"）
        """
        self.memory_dir = Path(memory_dir).resolve()
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 事件追加 API
    # ------------------------------------------------------------------
    def append_event(self, event_type: str, **kwargs) -> str:
        """追加事件到当日 jsonl 文件。

        Args:
            event_type: 事件类型（必须为 EVENT_TYPES 之一）
            **kwargs: 事件字段（audit_id / project_name / summary / rule_details / ...）

        Returns:
            event_id（EVT-YYYY-MM-DD-NNN）

        Raises:
            ValueError: 当 event_type 不在枚举中时
        """
        if event_type not in EVENT_TYPES:
            raise ValueError(
                f"event_type 必须为 {EVENT_TYPES} 之一，实际: {event_type!r}"
            )

        # 临界区：分配 event_id 与追加写入必须原子化，
        # 否则两个并发请求可能分配到相同 event_id。
        with self._lock:
            date_str = _today_str()
            event_id = self._next_event_id(date_str)

            event: Dict[str, Any] = {
                "event_id": event_id,
                "event_type": event_type,
                "timestamp": _now_iso(),
            }
            # 合并额外字段（audit_id / project_name / summary / rule_details / feedbacks ...）
            for k, v in kwargs.items():
                if v is not None:
                    event[k] = v

            self._append_to_jsonl(date_str, event)
            return event_id

    def append_audit_completed(
        self,
        audit_id: str,
        project_name: str,
        project_path: str,
        summary: Dict[str, Any],
        rule_details: List[Dict[str, Any]],
        feedbacks: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """记录审核完成事件。

        Args:
            audit_id: 审核编号（如 AU-2026-07-30-001）
            project_name: 项目名称
            project_path: 项目文件夹路径
            summary: 审核摘要（含 documents_audited / total_findings /
                     rule_engine_findings / rules_triggered / rules_hit_count /
                     feedbacks_count）
            rule_details: 每条命中规则的详情（含 rule_id / rule_name / level /
                          scope / hits / false_positives / docs_affected）
            feedbacks: 本次审核收到的反馈（默认空列表）

        Returns:
            event_id
        """
        return self.append_event(
            "audit_completed",
            audit_id=audit_id,
            project_name=project_name,
            project_path=project_path,
            summary=summary,
            rule_details=rule_details,
            feedbacks=feedbacks or [],
        )

    def append_feedback_received(
        self,
        feedback_id: str,
        audit_id: str,
        feedback_type: str,
        rule_id: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> str:
        """记录反馈接收事件。

        Args:
            feedback_id: 反馈编号（如 FB-2026-07-30-001）
            audit_id: 关联审核编号
            feedback_type: 反馈类型（missed / false_positive）
            rule_id: 关联规则 ID（误报反馈时必填）
            summary: 反馈摘要

        Returns:
            event_id
        """
        return self.append_event(
            "feedback_received",
            feedback_id=feedback_id,
            audit_id=audit_id,
            feedback_type=feedback_type,
            rule_id=rule_id,
            summary=summary,
        )

    def append_feedback_analyzed(
        self,
        cluster_count: int,
        candidate_rules_count: int,
        report_path: Optional[str] = None,
    ) -> str:
        """记录反馈分析完成事件。

        Args:
            cluster_count: 聚类簇数
            candidate_rules_count: 生成的候选规则数
            report_path: 分析报告路径

        Returns:
            event_id
        """
        return self.append_event(
            "feedback_analyzed",
            cluster_count=cluster_count,
            candidate_rules_count=candidate_rules_count,
            report_path=report_path,
        )

    def append_rule_transitioned(
        self,
        rule_id: str,
        from_status: str,
        to_status: str,
        reason: str,
        operator: str = "system",
    ) -> str:
        """记录规则状态流转事件。

        Args:
            rule_id: 规则 ID
            from_status: 原状态
            to_status: 新状态
            reason: 流转原因
            operator: 操作者（system / admin / auto）

        Returns:
            event_id
        """
        return self.append_event(
            "rule_transitioned",
            rule_id=rule_id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            operator=operator,
        )

    def append_rule_downgraded(
        self,
        rule_id: str,
        from_level: str,
        to_level: str,
        reason: str,
        fp_rate: float,
    ) -> str:
        """记录规则自动降级事件。

        Args:
            rule_id: 规则 ID
            from_level: 原层级（L1-IRON / L2-LOGIC / L3-BUSINESS）
            to_level: 新层级（L3-BUSINESS / deprecated）
            reason: 降级原因
            fp_rate: 触发降级的误报率

        Returns:
            event_id
        """
        return self.append_event(
            "rule_downgraded",
            rule_id=rule_id,
            from_level=from_level,
            to_level=to_level,
            reason=reason,
            false_positive_rate=fp_rate,
        )

    def append_rule_promoted(
        self,
        rule_id: str,
        from_status: str,
        to_status: str,
        reason: str,
    ) -> str:
        """记录候选规则提升事件。

        Args:
            rule_id: 规则 ID
            from_status: 原状态（如 testing / incubating）
            to_status: 新状态（如 incubating / active）
            reason: 提升原因

        Returns:
            event_id
        """
        return self.append_event(
            "rule_promoted",
            rule_id=rule_id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # 查询 API
    # ------------------------------------------------------------------
    def query_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """查询某日所有事件。

        Args:
            date_str: 日期字符串（YYYY-MM-DD）

        Returns:
            事件列表（按 timestamp 升序）
        """
        path = self._date_file(date_str)
        events = self._read_jsonl(path)
        events.sort(key=lambda e: e.get("timestamp", ""))
        return events

    def query_by_audit(self, audit_id: str) -> List[Dict[str, Any]]:
        """查询某次审核的所有事件（跨日期聚合）。

        Args:
            audit_id: 审核编号

        Returns:
            事件列表（按 timestamp 升序）
        """
        result: List[Dict[str, Any]] = []
        for path in self._iter_all_date_files():
            for event in self._read_jsonl(path):
                if event.get("audit_id") == audit_id:
                    result.append(event)
        result.sort(key=lambda e: e.get("timestamp", ""))
        return result

    def query_by_rule(self, rule_id: str) -> List[Dict[str, Any]]:
        """查询某条规则的所有事件（跨日期聚合）。

        匹配规则：
          - event 顶层有 rule_id 字段
          - event.rule_details 数组中包含 rule_id（audit_completed 事件）

        Args:
            rule_id: 规则 ID

        Returns:
            事件列表（按 timestamp 升序）
        """
        result: List[Dict[str, Any]] = []
        for path in self._iter_all_date_files():
            for event in self._read_jsonl(path):
                # 1. 顶层 rule_id 匹配（feedback_received / rule_transitioned / rule_downgraded / rule_promoted）
                if event.get("rule_id") == rule_id:
                    result.append(event)
                    continue
                # 2. rule_details 数组中包含 rule_id（audit_completed 事件）
                rule_details = event.get("rule_details") or []
                if isinstance(rule_details, list):
                    for rd in rule_details:
                        if isinstance(rd, dict) and rd.get("rule_id") == rule_id:
                            result.append(event)
                            break
        result.sort(key=lambda e: e.get("timestamp", ""))
        return result

    def get_recent_events(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取最近 N 天的事件。

        Args:
            days: 天数（默认 7）

        Returns:
            事件列表（按 timestamp 升序）
        """
        now = datetime.now(CST)
        cutoff = now - timedelta(days=days)
        result: List[Dict[str, Any]] = []
        for path in self._iter_all_date_files():
            # 先按文件名日期过滤
            date_str = path.stem
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CST)
            except ValueError:
                continue
            if file_date < cutoff:
                continue
            # 再按事件 timestamp 精确过滤
            for event in self._read_jsonl(path):
                ts = event.get("timestamp", "")
                try:
                    event_dt = datetime.fromisoformat(
                        str(ts).replace("Z", "+00:00")
                    )
                    if event_dt.tzinfo is None:
                        event_dt = event_dt.replace(tzinfo=CST)
                    if event_dt >= cutoff:
                        result.append(event)
                except (ValueError, TypeError):
                    # 时间戳解析失败，仍按文件日期判断为近期，保留
                    result.append(event)
        result.sort(key=lambda e: e.get("timestamp", ""))
        return result

    def list_dates(self) -> List[str]:
        """列出所有有事件记录的日期（升序）。"""
        dates: List[str] = []
        for path in self._iter_all_date_files():
            dates.append(path.stem)
        dates.sort()
        return dates

    def count_events(self) -> Dict[str, int]:
        """返回事件统计：{total, by_type}。"""
        counts: Dict[str, int] = {"total": 0}
        for event_type in EVENT_TYPES:
            counts[event_type] = 0
        for path in self._iter_all_date_files():
            for event in self._read_jsonl(path):
                counts["total"] += 1
                et = event.get("event_type", "")
                if et in counts:
                    counts[et] += 1
                else:
                    # 未知类型归入一个特殊键
                    counts[f"unknown:{et}"] = counts.get(f"unknown:{et}", 0) + 1
        return counts

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _date_file(self, date_str: str) -> Path:
        """根据日期返回对应的 jsonl 文件路径。"""
        return self.memory_dir / f"{date_str}.jsonl"

    def _iter_all_date_files(self) -> List[Path]:
        """遍历所有日期 jsonl 文件（按文件名升序）。"""
        if not self.memory_dir.is_dir():
            return []
        return sorted(self.memory_dir.glob("*.jsonl"))

    def _read_jsonl(self, path: Path) -> List[Dict[str, Any]]:
        """读取 jsonl 文件，返回事件列表。"""
        if not path.is_file():
            return []
        events: List[Dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        if isinstance(event, dict):
                            events.append(event)
                    except json.JSONDecodeError as e:
                        logger.warning(
                            f"解析 JSONL 失败 {path}:{line_no}: {e}"
                        )
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"读取 JSONL 文件失败 {path}: {e}")
        return events

    def _append_to_jsonl(self, date_str: str, event: Dict[str, Any]) -> None:
        """追加一个事件到当日 jsonl 文件。"""
        with self._lock:
            path = self._date_file(date_str)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
            except (OSError, TypeError, ValueError) as e:
                logger.error(f"追加事件到 JSONL 失败 {path}: {e}")

    def _next_event_id(self, date_str: str) -> str:
        """生成下一个 event_id（EVT-YYYY-MM-DD-NNN）。

        扫描当日 jsonl 文件，序号 +1；当日无事件则从 001 开始。

        通过类级 _lock 保护整个 check-then-act 逻辑（扫描 → 计算 → 返回），
        防止并发分配到相同序号。调用方（append_event）应在外层同样持锁以
        覆盖追加写入，使“分配 ID + 追加文件”成为原子操作。
        """
        with self._lock:
            path = self._date_file(date_str)
            existing: List[int] = []
            for event in self._read_jsonl(path):
                eid = event.get("event_id", "")
                if isinstance(eid, str) and eid.startswith(f"EVT-{date_str}-"):
                    try:
                        existing.append(int(eid[-3:]))
                    except ValueError:
                        continue
            seq = (max(existing) + 1) if existing else 1
            return f"EVT-{date_str}-{seq:03d}"


# ========== CLI 入口 ==========
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="民航施工资料审核 Skill — 审核记忆流",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    skill_dir = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--memory-dir", default=str(skill_dir / "audit_memory"),
        help=f"记忆流目录（默认 {skill_dir / 'audit_memory'}）",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="列出所有事件日期与统计")
    group.add_argument("--date", metavar="YYYY-MM-DD", help="查看某日所有事件")
    group.add_argument("--audit", metavar="AU-...", help="查看某次审核的所有事件")
    group.add_argument("--rule", metavar="RULE_ID", help="查看某条规则的所有事件")
    group.add_argument("--recent", type=int, metavar="N", help="查看最近 N 天的事件")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)

    memory = AuditMemory(Path(args.memory_dir))

    if args.list:
        dates = memory.list_dates()
        counts = memory.count_events()
        print(f"记忆流目录: {memory.memory_dir}")
        print(f"事件总数: {counts.get('total', 0)}")
        print(f"日期文件数: {len(dates)}")
        print("\n按事件类型统计：")
        for et in sorted(EVENT_TYPES):
            print(f"  {et}: {counts.get(et, 0)}")
        # 未知类型
        for k, v in counts.items():
            if k.startswith("unknown:"):
                print(f"  {k}: {v}")
        if dates:
            print("\n有事件的日期：")
            for d in dates:
                events = memory.query_by_date(d)
                print(f"  {d}: {len(events)} 条事件")
        return 0

    if args.date:
        events = memory.query_by_date(args.date)
        print(f"日期 {args.date} 的事件：{len(events)} 条")
        for e in events:
            print(json.dumps(e, ensure_ascii=False, indent=2))
        return 0

    if args.audit:
        events = memory.query_by_audit(args.audit)
        print(f"审核 {args.audit} 的事件：{len(events)} 条")
        for e in events:
            print(json.dumps(e, ensure_ascii=False, indent=2))
        return 0

    if args.rule:
        events = memory.query_by_rule(args.rule)
        print(f"规则 {args.rule} 的事件：{len(events)} 条")
        for e in events:
            print(json.dumps(e, ensure_ascii=False, indent=2))
        return 0

    if args.recent is not None:
        events = memory.get_recent_events(args.recent)
        print(f"最近 {args.recent} 天的事件：{len(events)} 条")
        for e in events:
            et = e.get("event_type", "")
            ts = e.get("timestamp", "")
            extra = ""
            if "audit_id" in e:
                extra = f" audit={e['audit_id']}"
            elif "rule_id" in e:
                extra = f" rule={e['rule_id']}"
            print(f"  {ts} | {et}{extra}")
        return 0

    # 默认行为：显示简报
    print("民航施工资料审核 Skill — 审核记忆流")
    print(f"记忆流目录: {memory.memory_dir}")
    counts = memory.count_events()
    print(f"事件总数: {counts.get('total', 0)}")
    print("\n可用参数：")
    print("  --list               列出所有事件日期与统计")
    print("  --date YYYY-MM-DD    查看某日所有事件")
    print("  --audit AU-...       查看某次审核的所有事件")
    print("  --rule RULE_ID       查看某条规则的所有事件")
    print("  --recent N          查看最近 N 天的事件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
