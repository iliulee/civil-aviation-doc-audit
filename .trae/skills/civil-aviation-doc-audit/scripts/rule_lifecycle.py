# -*- coding: utf-8 -*-
"""
rule_lifecycle.py — 规则生命周期管理（Phase B-4.2 / B-4.3）
============================================================

职责：
  1. 跟踪 testing 状态规则的审核表现（命中次数、误报反馈数）
  2. 自动检测流转条件：误报率 < 10% 且 ≥ 3 个项目测试通过 → 自动转入 incubating
  3. 项目级 vs 全局生效范围管理（B-4.4 配合 RuleLoader 使用）

数据存储：
  - rules/lifecycle/tracking.json：跟踪每条 testing 规则的审核记录
    结构：
    {
      "rule_id": "LG-CUSTOM-001",
      "status": "testing",
      "project_tests": [
        {"project": "项目A", "audit_id": "AU-...", "hits": 5,
         "false_positives": 0, "tested_at": "..."},
        ...
      ],
      "total_hits": 12,
      "total_false_positives": 1,
      "false_positive_rate": 0.083,
      "auto_promote_eligible": false,
      "last_updated": "..."
    }
  - rules/lifecycle/history.jsonl：生命周期事件日志（追加写，每行一个 JSON）

设计原则：
  - 单文件实现，零第三方依赖（仅标准库）
  - 与 rule_admin.py 解耦：rule_admin 调用本模块的 API，不直接操作文件
  - 与 review_audit.py 解耦：review_audit 在 run_rule_engine 末尾调用 record_audit_result
  - 自动流转通过 promote_to_incubating 实现，不依赖 rule_admin API
  - 失败安全：任何 IO/解析异常不向上抛出，仅记录日志，避免阻塞审核流程

用法：
    from rule_lifecycle import RuleLifecycleManager
    mgr = RuleLifecycleManager(rules_dir)
    mgr.record_audit_result(rule_id="LG-CUSTOM-001",
                            project="项目A",
                            audit_id="AU-20260730-001",
                            hits=5,
                            false_positives=0)
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 中国时区（+08:00）
CST = timezone(timedelta(hours=8))

# 自动提升阈值
AUTO_PROMOTE_MIN_PROJECTS = 3
AUTO_PROMOTE_MAX_FALSE_POSITIVE_RATE = 0.10  # 10%


def _now_iso() -> str:
    """返回当前 ISO 8601 时间戳（含 +08:00 时区）。"""
    return datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _safe_load_json(path: Path, default: Any) -> Any:
    """安全读取 JSON 文件；失败返回 default。"""
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        logger.warning(f"读取 JSON 失败 {path}: {e}")
    return default


def _safe_write_json(path: Path, data: Any) -> bool:
    """安全写入 JSON 文件；返回是否成功。"""
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


def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    """追加一行 JSON 到 jsonl 文件。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError) as e:
        logger.error(f"追加 JSONL 失败 {path}: {e}")


class RuleLifecycleManager:
    """规则生命周期管理器。

    负责 tracking testing 状态规则的审核表现，并在满足条件时自动流转到 incubating。

    所有方法均为失败安全：异常被捕获并记录日志，不向上抛出。
    """

    def __init__(self, rules_dir: Path) -> None:
        """初始化。

        Args:
            rules_dir: 规则根目录（rules/），tracking 文件存放在 rules/lifecycle/
        """
        self.rules_dir = Path(rules_dir).resolve()
        self.lifecycle_dir = self.rules_dir / "lifecycle"
        self.tracking_file = self.lifecycle_dir / "tracking.json"
        self.history_file = self.lifecycle_dir / "history.jsonl"

    # ------------------------------------------------------------------
    # 内部：tracking 文件读写
    # ------------------------------------------------------------------
    def _load_tracking_all(self) -> Dict[str, Dict[str, Any]]:
        """加载 tracking.json，返回 {rule_id: tracking_dict}。

        文件不存在或解析失败时返回空字典（视为尚未有任何 testing 跟踪记录）。
        """
        data = _safe_load_json(self.tracking_file, None)
        if not isinstance(data, dict):
            return {}
        # 兼容两种结构：直接 {rule_id: {...}} 或 {"rules": {rule_id: {...}}}
        if "rules" in data and isinstance(data["rules"], dict):
            return data["rules"]
        return data

    def _save_tracking_all(self, tracking_map: Dict[str, Dict[str, Any]]) -> None:
        """写回 tracking.json（保留 schema_version / updated_at 元信息）。"""
        payload = {
            "schema_version": "1.0",
            "updated_at": _now_iso(),
            "rules": tracking_map,
        }
        _safe_write_json(self.tracking_file, payload)

    def _emit_event(self, event_type: str, rule_id: str,
                    payload: Optional[Dict[str, Any]] = None) -> None:
        """追加生命周期事件到 history.jsonl。"""
        record = {
            "event": event_type,
            "rule_id": rule_id,
            "timestamp": _now_iso(),
        }
        if payload:
            record.update(payload)
        _append_jsonl(self.history_file, record)

    # ------------------------------------------------------------------
    # 核心 API
    # ------------------------------------------------------------------
    def record_audit_result(
        self,
        rule_id: str,
        project: str,
        audit_id: str,
        hits: int,
        false_positives: int = 0,
    ) -> Dict[str, Any]:
        """记录一次审核中 testing 规则的命中情况。

        若累计已满足自动提升条件（≥3 个项目，误报率<10%），自动调用
        promote_to_incubating 将规则状态流转到 incubating。

        Args:
            rule_id: 规则 ID
            project: 项目名称
            audit_id: 审核 ID（如 AU-20260730-001）
            hits: 本次审核中该规则的命中数
            false_positives: 误报数（来自反馈系统，C 阶段接入前先填 0）

        Returns:
            该规则的最新 tracking 字典
        """
        try:
            tracking_map = self._load_tracking_all()
            tracking = tracking_map.get(rule_id) or {
                "rule_id": rule_id,
                "status": "testing",
                "project_tests": [],
                "total_hits": 0,
                "total_false_positives": 0,
                "false_positive_rate": 0.0,
                "auto_promote_eligible": False,
                "last_updated": _now_iso(),
            }

            # 追加本次审核记录
            entry = {
                "project": project or "unknown",
                "audit_id": audit_id or "",
                "hits": int(hits) if hits else 0,
                "false_positives": int(false_positives) if false_positives else 0,
                "tested_at": _now_iso(),
            }
            tests = tracking.get("project_tests", [])
            if not isinstance(tests, list):
                tests = []
            tests.append(entry)
            tracking["project_tests"] = tests

            # 重算汇总
            total_hits = sum(t.get("hits", 0) for t in tests)
            total_fp = sum(t.get("false_positives", 0) for t in tests)
            tracking["total_hits"] = total_hits
            tracking["total_false_positives"] = total_fp
            # 误报率 = 误报数 / 命中数（命中数为 0 时记为 0）
            if total_hits > 0:
                tracking["false_positive_rate"] = round(total_fp / total_hits, 4)
            else:
                tracking["false_positive_rate"] = 0.0

            # 检查自动提升条件
            distinct_projects = {t.get("project") for t in tests if t.get("project")}
            eligible = (
                len(distinct_projects) >= AUTO_PROMOTE_MIN_PROJECTS
                and tracking["false_positive_rate"] < AUTO_PROMOTE_MAX_FALSE_POSITIVE_RATE
            )
            tracking["auto_promote_eligible"] = eligible
            tracking["last_updated"] = _now_iso()

            tracking_map[rule_id] = tracking
            self._save_tracking_all(tracking_map)

            self._emit_event(
                "audit_result_recorded",
                rule_id,
                {
                    "project": project,
                    "audit_id": audit_id,
                    "hits": hits,
                    "false_positives": false_positives,
                    "total_hits": total_hits,
                    "false_positive_rate": tracking["false_positive_rate"],
                    "auto_promote_eligible": eligible,
                },
            )

            # 满足条件 → 自动提升
            if eligible and tracking.get("status") == "testing":
                self.promote_to_incubating(
                    rule_id,
                    reason=(
                        f"auto: 通过 {len(distinct_projects)} 个项目测试，"
                        f"误报率 {tracking['false_positive_rate']*100:.2f}% < 10%"
                    ),
                )
                # 更新内存中的 tracking 状态
                tracking["status"] = "incubating"

            return tracking
        except Exception as e:
            logger.error(f"record_audit_result 异常 rule_id={rule_id}: {e}")
            return {
                "rule_id": rule_id,
                "error": str(e),
            }

    def promote_to_incubating(self, rule_id: str, reason: str = "auto") -> bool:
        """将 testing 规则流转为 incubating。

        Args:
            rule_id: 规则 ID
            reason: 流转原因（"auto" 表示自动提升，其他为人工/管理员操作）

        Returns:
            是否成功流转
        """
        try:
            # 加载规则 JSON 文件
            rule_file = self._find_rule_file(rule_id)
            if rule_file is None:
                logger.warning(f"promote_to_incubating: 规则文件未找到 {rule_id}")
                return False

            data = json.loads(rule_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                logger.warning(f"promote_to_incubating: 规则文件格式异常 {rule_file}")
                return False

            current_status = data.get("status")
            if current_status != "testing":
                logger.info(
                    f"promote_to_incubating: 规则 {rule_id} 当前状态为 {current_status}，"
                    f"非 testing，跳过"
                )
                return False

            # 更新状态
            old_status = current_status
            data["status"] = "incubating"
            data["updated_at"] = _now_iso()

            # 追加 changelog（version patch 号 +1，沿用 rule_admin 风格）
            old_version = data.get("version", "1.0.0")
            new_version = self._bump_patch(old_version)
            data["version"] = new_version
            changelog = data.get("changelog") or []
            if not isinstance(changelog, list):
                changelog = []
            changelog.append({
                "version": new_version,
                "date": datetime.now(CST).strftime("%Y-%m-%d"),
                "author": "rule_lifecycle.auto" if reason == "auto" else "rule_lifecycle.admin",
                "change": f"状态自动流转: {old_status} → incubating（原因: {reason}）",
            })
            data["changelog"] = changelog

            # 写回规则文件
            try:
                rule_file.parent.mkdir(parents=True, exist_ok=True)
                rule_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except OSError as e:
                logger.error(f"promote_to_incubating: 写规则文件失败 {rule_file}: {e}")
                return False

            # 同步更新 tracking.json 中的状态
            tracking_map = self._load_tracking_all()
            if rule_id in tracking_map:
                tracking_map[rule_id]["status"] = "incubating"
                tracking_map[rule_id]["last_updated"] = _now_iso()
                self._save_tracking_all(tracking_map)

            self._emit_event(
                "auto_promoted_to_incubating" if reason == "auto" or reason.startswith("auto:") else "promoted_to_incubating",
                rule_id,
                {"from": old_status, "to": "incubating", "reason": reason,
                 "version": new_version},
            )
            logger.info(
                f"规则 {rule_id} 自动提升 testing → incubating（{reason}）"
            )
            return True
        except Exception as e:
            logger.error(f"promote_to_incubating 异常 rule_id={rule_id}: {e}")
            return False

    def get_tracking(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """获取规则的跟踪记录；未找到返回 None。"""
        tracking_map = self._load_tracking_all()
        return tracking_map.get(rule_id)

    def list_testing_rules(self) -> List[Dict[str, Any]]:
        """列出所有 testing 状态规则的跟踪记录。"""
        tracking_map = self._load_tracking_all()
        return [
            {**t, "rule_id": rid}
            for rid, t in tracking_map.items()
            if t.get("status") == "testing"
        ]

    def list_auto_promote_eligible(self) -> List[Dict[str, Any]]:
        """列出可自动提升的规则（auto_promote_eligible=True 且仍为 testing）。"""
        tracking_map = self._load_tracking_all()
        return [
            {**t, "rule_id": rid}
            for rid, t in tracking_map.items()
            if t.get("auto_promote_eligible") is True
            and t.get("status") == "testing"
        ]

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _find_rule_file(self, rule_id: str) -> Optional[Path]:
        """按 rule_id 查找规则 JSON 文件。

        扫描 rules/ 下所有 .json 文件（排除 lifecycle/、schema/、registry.json），
        返回首个 rule_id 匹配的文件路径。
        """
        if not self.rules_dir.is_dir():
            return None
        excluded_dirs = {"lifecycle", "schema"}
        excluded_files = {"registry.json"}
        for p in sorted(self.rules_dir.rglob("*.json")):
            if p.name in excluded_files:
                continue
            try:
                rel = p.relative_to(self.rules_dir)
            except ValueError:
                continue
            if any(part in excluded_dirs for part in rel.parts[:-1]):
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue
            if isinstance(data, dict) and data.get("rule_id") == rule_id:
                return p
        return None

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


# ========== 自检入口 ==========
def main() -> int:
    """自检：扫描所有 testing 状态规则并打印跟踪状态。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    skill_dir = Path(__file__).resolve().parent.parent
    rules_dir = skill_dir / "rules"

    mgr = RuleLifecycleManager(rules_dir)
    print(f"规则目录: {rules_dir}")
    print(f"跟踪文件: {mgr.tracking_file}")
    print(f"历史文件: {mgr.history_file}")
    print(f"跟踪文件存在: {mgr.tracking_file.is_file()}")
    print(f"历史文件存在: {mgr.history_file.is_file()}")

    testing_rules = mgr.list_testing_rules()
    print(f"\ntesting 状态跟踪记录: {len(testing_rules)} 条")
    for t in testing_rules:
        print(f"  - {t.get('rule_id')}: 命中 {t.get('total_hits', 0)}, "
              f"误报率 {t.get('false_positive_rate', 0)*100:.2f}%, "
              f"项目数 {len(t.get('project_tests', []))}")

    eligible = mgr.list_auto_promote_eligible()
    print(f"\n可自动提升: {len(eligible)} 条")
    for t in eligible:
        print(f"  - {t.get('rule_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
