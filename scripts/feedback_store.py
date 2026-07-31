# -*- coding: utf-8 -*-
"""
feedback_store.py — 民航施工资料审核 Skill 反馈存储管理
=======================================================

职责（Phase C-1）：
  1. 管理 feedbacks/ 目录下的反馈 JSON 文件（CRUD 子集）
  2. 自动生成反馈 ID（FB-YYYY-MM-DD-NNN），按日递增序号
  3. 提供 list / get / update_status / count 等查询接口
  4. 反馈文件按 feedback_id 命名，写入 feedbacks/{feedback_id}.json
  5. 内置 Schema 校验（jsonschema 不可用时回退到字段检查）

设计参考：specs/design-rule-management-subsystem/spec.md 第 7.1 节
依赖：Python 3.8+ 标准库；可选 jsonschema（Draft 2020-12）

用法：
    from feedback_store import FeedbackStore
    store = FeedbackStore()
    fb_id = store.create(
        audit_id="AU-2026-07-30-001",
        type="missed",
        user_id="admin",
        context={"doc_id": "DOC-018", "other_hit_rules": ["LG-001"]},
        user_input={"summary": "Z417 桩长突变未触发规则"},
    )

命令行：
    python scripts/feedback_store.py                       # 列出所有反馈
    python scripts/feedback_store.py --stats               # 显示统计
    python scripts/feedback_store.py --new                 # 列出 status=new
    python scripts/feedback_store.py --get FB-2026-07-30-001
    python scripts/feedback_store.py --validate            # 校验所有反馈文件
"""

import argparse
import json
import logging
import re
import sys
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_FEEDBACKS_DIR = SKILL_ROOT / "feedbacks"
FEEDBACK_SCHEMA_PATH = DEFAULT_FEEDBACKS_DIR / "schema" / "feedback-schema.json"

# 中国时区（+08:00）
CST = timezone(timedelta(hours=8))

# 反馈 ID 格式：FB-YYYY-MM-DD-NNN
FEEDBACK_ID_RE = re.compile(r"^FB-\d{4}-\d{2}-\d{2}-\d{3}$")

# 合法枚举
TYPE_ENUM = {"missed", "false_positive"}
STATUS_ENUM = {"new", "analyzed", "clustered", "resolved"}
EXPECTED_RULE_TYPE_ENUM = {"L1-IRON", "L2-LOGIC", "L3-BUSINESS"}
EXPECTED_SEVERITY_ENUM = {"Fatal", "Sanity Check", "Best Practice"}

# 必填顶层字段
REQUIRED_FIELDS = [
    "feedback_id", "audit_id", "type", "user_id", "timestamp",
    "context", "user_input", "status",
]

logger = logging.getLogger(__name__)

# jsonschema 可用性检测（与 rule_schema_validator 一致）
try:
    import jsonschema  # noqa: F401
    from jsonschema import Draft202012Validator
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def now_iso() -> str:
    """返回当前 ISO 8601 时间戳（含 +08:00 时区）。"""
    return datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def today_str() -> str:
    """返回当前日期字符串 YYYY-MM-DD。"""
    return datetime.now(CST).strftime("%Y-%m-%d")


def load_schema() -> Optional[Dict[str, Any]]:
    """加载 feedback-schema.json；不存在返回 None。"""
    if not FEEDBACK_SCHEMA_PATH.is_file():
        return None
    try:
        return json.loads(FEEDBACK_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"读取反馈 schema 失败: {e}")
        return None


def _validate_fallback(data: Dict[str, Any]) -> List[str]:
    """内置回退校验器（jsonschema 不可用时使用）。

    校验逻辑与 feedback-schema.json 等价，返回错误信息列表（空表示通过）。
    """
    errors: List[str] = []

    # 必填字段
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"缺少必填字段: {field}")

    if errors:
        return errors

    # feedback_id 格式
    fb_id = data.get("feedback_id", "")
    if not isinstance(fb_id, str) or not FEEDBACK_ID_RE.match(fb_id):
        errors.append(f"feedback_id 格式不合法: {fb_id!r}（应为 FB-YYYY-MM-DD-NNN）")

    # audit_id
    audit_id = data.get("audit_id", "")
    if not isinstance(audit_id, str) or not audit_id.strip():
        errors.append("audit_id 必须为非空字符串")

    # type 枚举
    if data.get("type") not in TYPE_ENUM:
        errors.append(f"type 必须为 {TYPE_ENUM} 之一，实际: {data.get('type')!r}")

    # user_id
    if not isinstance(data.get("user_id"), str) or not data.get("user_id", "").strip():
        errors.append("user_id 必须为非空字符串")

    # timestamp 格式（简易校验）
    ts = data.get("timestamp", "")
    if not isinstance(ts, str) or not re.match(
        r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?(Z|[+-]\d{2}:\d{2})?$", ts
    ):
        errors.append(f"timestamp 格式不合法: {ts!r}")

    # context
    ctx = data.get("context")
    if not isinstance(ctx, dict):
        errors.append("context 必须为对象")
    else:
        other = ctx.get("other_hit_rules")
        if not isinstance(other, list):
            errors.append("context.other_hit_rules 必须为数组")
        elif not all(isinstance(x, str) and x for x in other):
            errors.append("context.other_hit_rules 必须为非空字符串数组")

    # user_input
    ui = data.get("user_input")
    if not isinstance(ui, dict):
        errors.append("user_input 必须为对象")
    else:
        summary = ui.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            errors.append("user_input.summary 必须为非空字符串")
        ert = ui.get("expected_rule_type")
        if ert is not None and ert not in EXPECTED_RULE_TYPE_ENUM:
            errors.append(f"user_input.expected_rule_type 必须为 {EXPECTED_RULE_TYPE_ENUM} 或 null")
        es = ui.get("expected_severity")
        if es is not None and es not in EXPECTED_SEVERITY_ENUM:
            errors.append(f"user_input.expected_severity 必须为 {EXPECTED_SEVERITY_ENUM} 或 null")

    # status 枚举
    if data.get("status") not in STATUS_ENUM:
        errors.append(f"status 必须为 {STATUS_ENUM} 之一，实际: {data.get('status')!r}")

    # type=false_positive 时 rule_id 必填
    if data.get("type") == "false_positive":
        rid = data.get("rule_id")
        if not isinstance(rid, str) or not rid.strip():
            errors.append("type=false_positive 时 rule_id 必填且非空")

    return errors


def validate_feedback(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """校验反馈数据字典是否符合 feedback-schema.json。

    Returns:
        (success, errors) — errors 为空列表表示通过
    """
    schema = load_schema()
    if schema is None:
        # schema 缺失，直接走回退校验
        errs = _validate_fallback(data)
        return (len(errs) == 0), errs

    if HAS_JSONSCHEMA:
        try:
            validator = Draft202012Validator(schema)
            errs = sorted(validator.iter_errors(data), key=lambda e: e.path)
            messages = []
            for e in errs:
                loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
                messages.append(f"{loc}: {e.message}")
            return (len(messages) == 0), messages
        except Exception as e:
            logger.warning(f"jsonschema 校验异常，回退到内置校验: {e}")
            errs = _validate_fallback(data)
            return (len(errs) == 0), errs

    errs = _validate_fallback(data)
    return (len(errs) == 0), errs


# ---------------------------------------------------------------------------
# FeedbackStore — 反馈存储管理
# ---------------------------------------------------------------------------
class FeedbackStore:
    """反馈存储管理器。

    通过类属性 feedbacks_dir 配置存储目录，所有反馈 JSON 文件
    按文件名 {feedback_id}.json 直接存放在该目录下。
    """

    # 类属性：反馈目录（默认 feedbacks/）
    feedbacks_dir: Path = DEFAULT_FEEDBACKS_DIR

    # 类级可重入锁：保护 ID 生成与文件写入的 check-then-act 临界区，
    # 避免并发创建时分配到相同 feedback_id。RLock 允许 _next_id 与
    # create() 嵌套加锁而不死锁。
    _lock = threading.RLock()

    def __init__(self, feedbacks_dir: Optional[Path] = None) -> None:
        if feedbacks_dir is not None:
            self.feedbacks_dir = Path(feedbacks_dir)
        # 确保目录存在
        self.feedbacks_dir.mkdir(parents=True, exist_ok=True)

    # ===== 内部工具 =====
    def _feedback_file(self, feedback_id: str) -> Path:
        """根据 feedback_id 返回对应的文件路径。"""
        return self.feedbacks_dir / f"{feedback_id}.json"

    def _scan_all(self) -> List[Tuple[Path, Dict[str, Any]]]:
        """扫描 feedbacks/ 目录下所有反馈 JSON（排除 schema/）。"""
        result: List[Tuple[Path, Dict[str, Any]]] = []
        if not self.feedbacks_dir.is_dir():
            return result
        for fp in sorted(self.feedbacks_dir.glob("FB-*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"读取反馈文件失败 {fp}: {e}")
                continue
            if isinstance(data, dict) and "feedback_id" in data:
                result.append((fp, data))
        return result

    def _next_id(self) -> str:
        """生成下一个 feedback_id（FB-YYYY-MM-DD-NNN）。

        扫描当天已存在的反馈文件，序号 +1；当日无反馈则从 001 开始。

        通过类级 _lock 保护整个 check-then-act 逻辑（扫描 → 计算 → 返回），
        防止并发分配到相同序号。调用方（create）应在外层同样持锁以覆盖
        文件写入，使“分配 ID + 写入文件”成为原子操作。
        """
        with self._lock:
            date_str = today_str()
            prefix = f"FB-{date_str}-"
            existing: List[int] = []
            for fp, data in self._scan_all():
                fb_id = data.get("feedback_id", "")
                if isinstance(fb_id, str) and fb_id.startswith(prefix):
                    try:
                        existing.append(int(fb_id[-3:]))
                    except ValueError:
                        continue
            seq = (max(existing) + 1) if existing else 1
            return f"FB-{date_str}-{seq:03d}"

    # ===== 公共 API =====
    def create(
        self,
        audit_id: str,
        type: str,
        user_id: str,
        context: Dict[str, Any],
        user_input: Dict[str, Any],
        rule_id: Optional[str] = None,
    ) -> str:
        """创建一条反馈，自动生成 feedback_id 并写入文件。

        Args:
            audit_id: 关联审核编号
            type: 反馈类型（missed / false_positive）
            user_id: 提交者标识
            context: 审核上下文快照（应包含 other_hit_rules 字段，缺省自动补 []）
            user_input: 用户输入（必须包含 summary）
            rule_id: 误报时填被误报的规则ID；漏审时填期望规则ID或 None

        Returns:
            feedback_id

        Raises:
            ValueError: 当必填字段缺失或 type/rule_id 约束不满足时
        """
        # 基础校验
        if not audit_id or not isinstance(audit_id, str):
            raise ValueError("audit_id 必须为非空字符串")
        if type not in TYPE_ENUM:
            raise ValueError(f"type 必须为 {TYPE_ENUM} 之一")
        if not user_id or not isinstance(user_id, str):
            raise ValueError("user_id 必须为非空字符串")
        if not isinstance(user_input, dict) or not str(user_input.get("summary", "")).strip():
            raise ValueError("user_input.summary 必填且非空")
        if type == "false_positive" and (not rule_id or not str(rule_id).strip()):
            raise ValueError("type=false_positive 时 rule_id 必填且非空")

        # 规整化 context
        ctx = dict(context) if isinstance(context, dict) else {}
        if "other_hit_rules" not in ctx:
            ctx["other_hit_rules"] = []
        elif not isinstance(ctx["other_hit_rules"], list):
            raise ValueError("context.other_hit_rules 必须为数组")

        # 规整化 user_input（去除 undefined 字段，便于 JSON 序列化）
        ui = {}
        for k in ("summary", "expected_rule_type", "expected_severity", "suggested_rule_description"):
            if k in user_input:
                ui[k] = user_input[k]
        # 缺省 expected_rule_type / expected_severity / suggested_rule_description → null
        ui.setdefault("expected_rule_type", None)
        ui.setdefault("expected_severity", None)
        ui.setdefault("suggested_rule_description", None)

        # 临界区：分配 feedback_id 与写入文件必须原子化，
        # 否则两个并发请求可能分配到相同 ID 并互相覆盖。
        with self._lock:
            feedback_id = self._next_id()
            record: Dict[str, Any] = {
                "feedback_id": feedback_id,
                "audit_id": audit_id,
                "type": type,
                "rule_id": rule_id,
                "user_id": user_id,
                "timestamp": now_iso(),
                "context": ctx,
                "user_input": ui,
                "status": "new",
                "analyzed_at": None,
                "cluster_id": None,
            }

            # 写入前校验
            ok, errs = validate_feedback(record)
            if not ok:
                raise ValueError(f"反馈数据校验失败: {errs}")

            fp = self._feedback_file(feedback_id)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return feedback_id

    def get(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """读取单条反馈；不存在返回 None。"""
        if not FEEDBACK_ID_RE.match(feedback_id or ""):
            return None
        fp = self._feedback_file(feedback_id)
        if not fp.is_file():
            return None
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"读取反馈 {feedback_id} 失败: {e}")
            return None

    def list_all(
        self,
        status: Optional[str] = None,
        type: Optional[str] = None,
        audit_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出反馈，支持按 status / type / audit_id 筛选。"""
        if status is not None and status not in STATUS_ENUM:
            raise ValueError(f"status 必须为 {STATUS_ENUM} 之一")
        if type is not None and type not in TYPE_ENUM:
            raise ValueError(f"type 必须为 {TYPE_ENUM} 之一")

        items: List[Dict[str, Any]] = []
        for _fp, data in self._scan_all():
            if status is not None and data.get("status") != status:
                continue
            if type is not None and data.get("type") != type:
                continue
            if audit_id is not None and data.get("audit_id") != audit_id:
                continue
            items.append(data)
        # 按 timestamp 倒序（最新在前）
        items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return items

    def list_new(self) -> List[Dict[str, Any]]:
        """列出 status=new 的反馈（按 timestamp 倒序）。"""
        return self.list_all(status="new")

    def update_status(
        self,
        feedback_id: str,
        status: str,
        cluster_id: Optional[str] = None,
    ) -> bool:
        """更新反馈状态；成功返回 True，未找到返回 False。

        若状态为 analyzed/clustered/resolved 且 analyzed_at 为空，则自动写入时间戳。
        cluster_id 非 None 时一并写入。
        """
        if status not in STATUS_ENUM:
            raise ValueError(f"status 必须为 {STATUS_ENUM} 之一")

        data = self.get(feedback_id)
        if data is None:
            return False

        data["status"] = status
        if cluster_id is not None:
            data["cluster_id"] = cluster_id
        # 进入 analyzed/clustered/resolved 时记录 analyzed_at（若尚未记录）
        if status in {"analyzed", "clustered", "resolved"} and not data.get("analyzed_at"):
            data["analyzed_at"] = now_iso()

        # 写入前再校验一次
        ok, errs = validate_feedback(data)
        if not ok:
            raise ValueError(f"更新后校验失败: {errs}")

        fp = self._feedback_file(feedback_id)
        fp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True

    def count(self) -> Dict[str, int]:
        """返回统计：{total, new, analyzed, clustered, resolved}。"""
        counts = {"total": 0, "new": 0, "analyzed": 0, "clustered": 0, "resolved": 0}
        for _fp, data in self._scan_all():
            counts["total"] += 1
            s = data.get("status", "new")
            if s in counts:
                counts[s] += 1
            else:
                # 未知状态归入 new 计数（防御性）
                counts["new"] += 1
        return counts

    def count_new(self) -> int:
        """返回 status=new 的反馈数量（用于 C-4.1 自动触发判定）。"""
        return self.count().get("new", 0)


# ---------------------------------------------------------------------------
# CLI 入口（用于测试与运维查询）
# ---------------------------------------------------------------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="民航施工资料审核 Skill — 反馈存储管理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--feedbacks-dir", default=str(DEFAULT_FEEDBACKS_DIR),
                        help=f"反馈目录（默认 {DEFAULT_FEEDBACKS_DIR}）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--stats", action="store_true", help="显示统计")
    group.add_argument("--new", action="store_true", help="列出 status=new 的反馈")
    group.add_argument("--get", metavar="FB_ID", help="查看单条反馈详情")
    group.add_argument("--validate", action="store_true", help="校验所有反馈文件")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    store = FeedbackStore(Path(args.feedbacks_dir))

    if args.stats:
        print(json.dumps(store.count(), ensure_ascii=False, indent=2))
        return 0

    if args.new:
        items = store.list_new()
        print(f"new 反馈数量: {len(items)}")
        for it in items:
            print(f"  {it['feedback_id']} | {it['type']:14s} | {it['timestamp']} | "
                  f"{it.get('user_input', {}).get('summary', '')[:50]}")
        return 0

    if args.get:
        data = store.get(args.get)
        if data is None:
            print(f"反馈不存在: {args.get}", file=sys.stderr)
            return 1
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if args.validate:
        all_items = store.list_all()
        if not all_items:
            print("无反馈文件可校验")
            return 0
        failed = 0
        for it in all_items:
            ok, errs = validate_feedback(it)
            if ok:
                print(f"  ✓ {it['feedback_id']}")
            else:
                failed += 1
                print(f"  ✗ {it['feedback_id']}: {errs}")
        if failed:
            print(f"\n校验完成：{len(all_items)} 条，{failed} 条失败", file=sys.stderr)
            return 1
        print(f"\n校验完成：{len(all_items)} 条全部通过")
        return 0

    # 默认：列出所有反馈
    items = store.list_all()
    print(f"反馈总数: {len(items)}")
    for it in items:
        print(f"  {it['feedback_id']} | {it['type']:14s} | {it['status']:10s} | "
              f"{it['audit_id']} | {it['timestamp']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
