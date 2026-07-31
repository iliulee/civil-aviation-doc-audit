# -*- coding: utf-8 -*-
"""
rule_admin.py — 民航施工资料审核 Skill 规则管理 API
=====================================================

职责（Phase B-1）：
  1. 提供规则 CRUD（创建/读取/更新/删除）REST 端点
  2. 规则生命周期状态流转（draft → testing → incubating → active / deprecated）
  3. 跨单位规则协同确认机制（pending_confirmation → active / incubating）
  4. 规则命中率/误报率统计、变更历史、沙箱测试
  5. 静态文件服务（rule-manager.html 前端面板）+ registry + 总体统计

设计参考：specs/design-rule-management-subsystem/spec.md 第 10.1 节
依赖：Python 3.8+ 标准库（http.server），无第三方 Web 框架

用法：
    python scripts/rule_admin.py                       # 默认 127.0.0.1:8765（仅本机）
    python scripts/rule_admin.py --port 9000           # 指定端口
    python scripts/rule_admin.py --host 0.0.0.0        # 显式开放外部访问（谨慎）
    python scripts/rule_admin.py --rules-dir /path     # 指定规则目录

约束：
    - 单文件实现，包含 RuleAdminServer 类与各端点处理函数
    - 通过 JSON 文件存储规则，无数据库依赖
    - 监听端口默认 8765，可通过 --port 配置
    - 规则目录默认为脚本同级 ../rules
"""

import argparse
import json
import logging
import os
import re
import sys
import traceback
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs, unquote

# ---------------------------------------------------------------------------
# 路径与模块导入
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent

# 将 scripts/ 加入 sys.path，便于导入同目录模块
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 导入规则引擎与校验工具（同目录模块）
from rule_engine import (  # noqa: E402
    Rule,
    RuleLoader,
    SingleDocChecker,
    CrossDocChecker,
    CrossUnitChecker,
    SCOPE_SINGLE_DOC,
    SCOPE_CROSS_DOC,
    SCOPE_CROSS_UNIT,
    LEVEL_L1,
)
from rule_schema_validator import (  # noqa: E402
    validate_rule_fallback,
    validate_with_jsonschema,
    HAS_JSONSCHEMA,
)
from feedback_store import (  # noqa: E402
    FeedbackStore,
    validate_feedback,
    DEFAULT_FEEDBACKS_DIR,
    FEEDBACK_ID_RE,
    TYPE_ENUM as FEEDBACK_TYPE_ENUM,
    STATUS_ENUM as FEEDBACK_STATUS_ENUM,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_RULES_DIR = SKILL_ROOT / "rules"
RULE_SCHEMA_PATH = DEFAULT_RULES_DIR / "schema" / "rule-schema.json"
# 反馈存储目录（Phase C-1）：feedbacks/
DEFAULT_FEEDBACKS_DIR_LOCAL = SKILL_ROOT / "feedbacks"

# 请求体大小上限（10MB），防止 DoS 攻击
MAX_BODY = 10 * 1024 * 1024

# 层级 → rule_id 前缀映射（用于自动生成 rule_id）
LEVEL_PREFIX = {
    "L1-IRON": "IR",
    "L2-LOGIC": "LG",
    "L3-BUSINESS": "BZ",
}

# rule_id 合法模式（与 schema 一致）
RULE_ID_RE = re.compile(r"^[A-Z]+-[A-Z0-9-]+$")

# 状态机：合法的状态流转
# draft → testing
# testing → incubating
# incubating → active / deprecated
# active → deprecated
# deprecated → active
# pending_confirmation → active / incubating
# （draft 之外的状态在跨单位规则修改后可进入 pending_confirmation，由 PUT 处理）
STATE_TRANSITIONS: Dict[str, set] = {
    "draft": {"testing"},
    "testing": {"incubating"},
    "incubating": {"active", "deprecated"},
    "active": {"deprecated"},
    "deprecated": {"active"},
    "pending_confirmation": {"active", "incubating"},
}

# 中国时区（+08:00），用于生成 ISO 8601 时间戳
CST = timezone(timedelta(hours=8))

# 排除的子目录与文件（与 RuleLoader 一致）
EXCLUDED_DIRS = {"schema", "lifecycle"}
EXCLUDED_FILES = {"registry.json"}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def now_iso() -> str:
    """返回当前 ISO 8601 时间戳（含 +08:00 时区）。"""
    return datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def today_str() -> str:
    """返回当前日期字符串 YYYY-MM-DD（用于 changelog.date）。"""
    return datetime.now(CST).strftime("%Y-%m-%d")


def _is_excluded(path: Path, rules_dir: Path) -> bool:
    """判断文件是否应被排除（schema/ 子目录或 registry.json）。"""
    if path.name in EXCLUDED_FILES:
        return True
    try:
        rel = path.relative_to(rules_dir)
    except ValueError:
        return True
    for part in rel.parts[:-1]:
        if part in EXCLUDED_DIRS:
            return True
    return False


def collect_rule_files(rules_dir: Path) -> List[Path]:
    """扫描 rules/ 目录下所有规则 JSON 文件（排除 registry.json 与 schema/）。"""
    rules_dir = Path(rules_dir)
    if not rules_dir.is_dir():
        return []
    files: List[Path] = []
    for p in sorted(rules_dir.rglob("*.json")):
        if _is_excluded(p, rules_dir):
            continue
        files.append(p)
    return files


def load_all_rules_raw(rules_dir: Path) -> List[Tuple[Path, Dict[str, Any]]]:
    """加载所有规则文件，返回 (路径, 数据字典) 列表。

    跳过非规则文件（无 rule_id 字段）与解析失败的文件。
    """
    rules_dir = Path(rules_dir)
    result: List[Tuple[Path, Dict[str, Any]]] = []
    for fp in collect_rule_files(rules_dir):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"读取规则文件失败 {fp}: {e}")
            continue
        if not isinstance(data, dict) or "rule_id" not in data:
            continue
        result.append((fp, data))
    return result


def find_rule_file(rules_dir: Path, rule_id: str) -> Optional[Path]:
    """按 rule_id 查找规则文件路径；未找到返回 None。"""
    for fp, data in load_all_rules_raw(rules_dir):
        if data.get("rule_id") == rule_id:
            return fp
    return None


def load_rule(rules_dir: Path, rule_id: str) -> Optional[Dict[str, Any]]:
    """按 rule_id 加载规则数据字典；未找到返回 None。"""
    fp = find_rule_file(rules_dir, rule_id)
    if fp is None:
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"加载规则 {rule_id} 失败: {e}")
        return None


def write_rule(file_path: Path, data: Dict[str, Any]) -> None:
    """写入规则 JSON 文件（UTF-8，缩进 2 空格，ensure_ascii=False）。"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_rule_data(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """校验规则数据字典是否符合 rule-schema.json。

    Returns:
        (success, errors) — errors 为空列表表示通过
    """
    try:
        schema = json.loads(RULE_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        # schema 读取失败时回退到内置校验器
        errors = validate_rule_fallback(data)
        return (len(errors) == 0), errors

    if HAS_JSONSCHEMA:
        errors = validate_with_jsonschema(data, schema)
    else:
        errors = validate_rule_fallback(data)
    return (len(errors) == 0), errors


def bump_patch_version(version: str) -> str:
    """语义化版本 patch 号自增：1.0.0 → 1.0.1。失败时追加 -1。"""
    try:
        parts = version.split(".")
        if len(parts) == 3:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
    except (ValueError, IndexError):
        pass
    return version + "-1"


def generate_rule_id(level: str) -> str:
    """根据层级前缀 + 时间戳自动生成 rule_id。

    格式：{前缀}-CUSTOM-{YYYYMMDDHHMMSS}，如 LG-CUSTOM-20260730153000
    """
    prefix = LEVEL_PREFIX.get(level, "R")
    ts = datetime.now(CST).strftime("%Y%m%d%H%M%S")
    return f"{prefix}-CUSTOM-{ts}"


def rel_file_path(file_path: Path, rules_dir: Path) -> str:
    """返回相对 rules_dir 的 posix 路径（用于 registry 风格的 file 字段）。"""
    try:
        return file_path.relative_to(rules_dir).as_posix()
    except ValueError:
        return file_path.name


def make_response(code: int, msg: str, data: Any = None) -> Dict[str, Any]:
    """构造统一响应 JSON。"""
    return {"code": code, "msg": msg, "data": data}


def violation_to_dict(v) -> Dict[str, Any]:
    """将 rule_engine.Violation 转为可 JSON 序列化的字典。"""
    return {
        "rule_id": v.rule_id,
        "rule_name": v.rule_name,
        "level": v.level,
        "scope": v.scope,
        "severity": v.severity,
        "row_index": v.row_index,
        "error_message": v.error_message,
        "context": v.context,
        "remediation": v.remediation,
    }


# ---------------------------------------------------------------------------
# RuleAdminServer — HTTP 请求处理器
# ---------------------------------------------------------------------------
class RuleAdminServer(BaseHTTPRequestHandler):
    """规则管理 API 请求处理器。

    继承 BaseHTTPRequestHandler，通过类属性 rules_dir 配置规则目录。
    路由分发：解析 method + path，调用对应 _handle_* 方法。
    """

    # 类属性：规则目录（由 run() 在启动前设置）
    rules_dir: Path = DEFAULT_RULES_DIR
    # 反馈存储目录（Phase C-1，由 run() 在启动前设置）
    feedbacks_dir: Path = DEFAULT_FEEDBACKS_DIR_LOCAL
    # 静态根目录（templates/）
    static_dir: Path = SKILL_ROOT / "templates"

    # 关闭默认日志输出（避免污染控制台，保留错误日志）
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        logger.debug(format % args)

    # ===== 响应工具 =====
    def _send_json(self, payload: Dict[str, Any], http_status: int = 200) -> None:
        """发送 JSON 响应（含 CORS 头）。"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(http_status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        """发送 CORS 响应头。

        安全策略：默认仅允许 localhost 来源，避免任意网页调用本 API。
        可通过环境变量 RULE_ADMIN_CORS_ORIGIN 显式指定允许的来源
        （如需开放外部访问，请同时使用 --host 0.0.0.0）。
        """
        # 显式配置的环境变量优先
        allowed_origin = os.environ.get("RULE_ADMIN_CORS_ORIGIN", "")
        if allowed_origin:
            cors_origin = allowed_origin
        else:
            # 仅允许 localhost 来源：读取请求 Origin 并校验是否为本地
            origin = self.headers.get("Origin", "")
            if origin and (
                origin.startswith("http://localhost")
                or origin.startswith("http://127.0.0.1")
            ):
                cors_origin = origin
            else:
                cors_origin = "http://localhost:8765"
        self.send_header("Access-Control-Allow-Origin", cors_origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods",
                         "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, Authorization, X-Requested-With")

    def _send_text(self, body: bytes, content_type: str, http_status: int = 200) -> None:
        """发送原始字节响应（用于静态文件）。"""
        self.send_response(http_status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _ok(self, data: Any = None, msg: str = "success") -> None:
        """发送成功响应。"""
        self._send_json(make_response(0, msg, data), 200)

    def _err(self, msg: str, code: int = 1, http_status: int = 400) -> None:
        """发送错误响应。"""
        self._send_json(make_response(code, msg, None), http_status)

    def _not_found(self, msg: str = "规则不存在") -> None:
        self._err(msg, code=404, http_status=404)

    def _server_error(self, msg: str = "服务器内部错误") -> None:
        self._err(msg, code=500, http_status=500)

    def _read_body(self) -> Dict[str, Any]:
        """读取请求体 JSON 并解析为字典。空请求体返回 {}。

        对 Content-Length 做大小与合法性校验，防止超大请求体造成 DoS。
        """
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length < 0:
            raise ValueError(f"非法 Content-Length: {length}")
        if length > MAX_BODY:
            raise ValueError(f"请求体过大: {length} > {MAX_BODY}")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"请求体 JSON 解析失败: {e}")
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data

    # ===== 路由分发 =====
    def do_OPTIONS(self) -> None:
        """处理 CORS 预检请求。"""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """GET 路由分发。"""
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            query = parse_qs(parsed.query)
            segments = [s for s in path.split("/") if s]

            # /api/rules, /api/rules/{id}, /api/rules/{id}/stats, /api/rules/{id}/changelog
            if len(segments) >= 2 and segments[0] == "api" and segments[1] == "rules":
                if len(segments) == 2:
                    self._handle_list_rules(query)
                    return
                rule_id = segments[2]
                if len(segments) == 3:
                    self._handle_get_rule(rule_id)
                    return
                if len(segments) == 4:
                    if segments[3] == "stats":
                        self._handle_get_stats(rule_id)
                        return
                    if segments[3] == "changelog":
                        self._handle_get_changelog(rule_id)
                        return
                self._not_found("API 端点不存在")
                return

            # /api/feedbacks, /api/feedbacks/{id}, /api/feedbacks/stats
            if len(segments) >= 2 and segments[0] == "api" and segments[1] == "feedbacks":
                if len(segments) == 2:
                    self._handle_list_feedbacks(query)
                    return
                if len(segments) == 3:
                    if segments[2] == "stats":
                        self._handle_feedback_stats()
                        return
                    self._handle_get_feedback(segments[2])
                    return
                self._not_found("API 端点不存在")
                return

            # /api/reflections, /api/reflections/{date}
            # D-4.2: 反思报告列表与详情
            if len(segments) >= 2 and segments[0] == "api" and segments[1] == "reflections":
                if len(segments) == 2:
                    self._handle_list_reflections()
                    return
                if len(segments) == 3:
                    self._handle_get_reflection(segments[2])
                    return
                self._not_found("API 端点不存在")
                return

            # /api/incubator, /api/incubator/{rule_id}
            # D-4.3: 孵化区候选规则列表与详情
            if len(segments) >= 2 and segments[0] == "api" and segments[1] == "incubator":
                if len(segments) == 2:
                    self._handle_list_incubator()
                    return
                if len(segments) == 3:
                    self._handle_get_incubator_rule(segments[2])
                    return
                self._not_found("API 端点不存在")
                return

            # /registry
            if len(segments) == 1 and segments[0] == "registry":
                self._handle_get_registry()
                return

            # /stats
            if len(segments) == 1 and segments[0] == "stats":
                self._handle_overview_stats()
                return

            # /feedback-collector — 返回反馈收集组件 HTML
            if len(segments) == 1 and segments[0] == "feedback-collector":
                self._serve_feedback_collector()
                return

            # /static/*
            if len(segments) >= 1 and segments[0] == "static":
                self._serve_static(segments[1:])
                return

            # / 或 /index.html → rule-manager.html
            if len(segments) == 0 or (len(segments) == 1 and segments[0] == "index.html"):
                self._serve_index()
                return

            self._not_found("路径不存在")
        except Exception as e:
            logger.error(f"GET 处理异常: {e}\n{traceback.format_exc()}")
            self._server_error(f"服务器内部错误: {e}")

    def do_POST(self) -> None:
        """POST 路由分发。"""
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            segments = [s for s in path.split("/") if s]

            if len(segments) >= 2 and segments[0] == "api" and segments[1] == "rules":
                # POST /api/rules
                if len(segments) == 2:
                    self._handle_create_rule()
                    return
                rule_id = segments[2]
                if len(segments) == 4:
                    if segments[3] == "transition":
                        self._handle_transition(rule_id)
                        return
                    if segments[3] == "confirm":
                        self._handle_confirm(rule_id)
                        return
                    if segments[3] == "force_confirm":
                        self._handle_force_confirm(rule_id)
                        return
                    if segments[3] == "test":
                        self._handle_test_rule(rule_id)
                        return
                self._not_found("API 端点不存在")
                return

            # POST /api/feedbacks — 创建反馈
            if len(segments) == 2 and segments[0] == "api" and segments[1] == "feedbacks":
                self._handle_create_feedback()
                return

            # POST /api/feedbacks/analyze — 手动触发 LLM 反馈分析管道（C-4.3）
            if (len(segments) == 3 and segments[0] == "api"
                    and segments[1] == "feedbacks" and segments[2] == "analyze"):
                self._handle_analyze_feedbacks()
                return

            # POST /api/feedbacks/{feedback_id}/transition — 更新反馈状态
            if (len(segments) == 4 and segments[0] == "api"
                    and segments[1] == "feedbacks" and segments[3] == "transition"):
                self._handle_feedback_transition(segments[2])
                return

            # POST /api/reflections/trigger — 手动触发反思（D-4.2）
            if (len(segments) == 3 and segments[0] == "api"
                    and segments[1] == "reflections" and segments[2] == "trigger"):
                self._handle_trigger_reflection()
                return

            # POST /api/incubator/{rule_id}/promote | /reject — 候选规则提升/驳回（D-4.3）
            if (len(segments) == 4 and segments[0] == "api"
                    and segments[1] == "incubator"
                    and segments[3] in ("promote", "reject")):
                if segments[3] == "promote":
                    self._handle_promote_incubator(segments[2])
                else:
                    self._handle_reject_incubator(segments[2])
                return

            self._not_found("路径不存在")
        except ValueError as e:
            self._err(str(e), code=400, http_status=400)
        except Exception as e:
            logger.error(f"POST 处理异常: {e}\n{traceback.format_exc()}")
            self._server_error(f"服务器内部错误: {e}")

    def do_PUT(self) -> None:
        """PUT 路由分发。"""
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            segments = [s for s in path.split("/") if s]

            if len(segments) == 3 and segments[0] == "api" and segments[1] == "rules":
                self._handle_update_rule(segments[2])
                return
            self._not_found("路径不存在")
        except ValueError as e:
            self._err(str(e), code=400, http_status=400)
        except Exception as e:
            logger.error(f"PUT 处理异常: {e}\n{traceback.format_exc()}")
            self._server_error(f"服务器内部错误: {e}")

    def do_DELETE(self) -> None:
        """DELETE 路由分发。"""
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            segments = [s for s in path.split("/") if s]

            if len(segments) == 3 and segments[0] == "api" and segments[1] == "rules":
                self._handle_delete_rule(segments[2])
                return
            self._not_found("路径不存在")
        except Exception as e:
            logger.error(f"DELETE 处理异常: {e}\n{traceback.format_exc()}")
            self._server_error(f"服务器内部错误: {e}")

    # ===== API: GET /api/rules（列表筛选）=====
    def _handle_list_rules(self, query: Dict[str, List[str]]) -> None:
        """GET /api/rules — 规则列表，支持 level/scope/status/source/q 筛选。"""
        rules_dir = self.rules_dir
        all_rules = load_all_rules_raw(rules_dir)

        # 筛选参数
        level = (query.get("level", [""])[0] or "").strip()
        scope = (query.get("scope", [""])[0] or "").strip()
        status = (query.get("status", [""])[0] or "").strip()
        source = (query.get("source", [""])[0] or "").strip()
        q = (query.get("q", [""])[0] or "").strip().lower()

        items: List[Dict[str, Any]] = []
        for fp, data in all_rules:
            if level and data.get("level") != level:
                continue
            if scope and data.get("scope") != scope:
                continue
            if status and data.get("status") != status:
                continue
            if source and data.get("source") != source:
                continue
            if q:
                name = (data.get("name") or "").lower()
                desc = (data.get("description") or "").lower()
                rid = (data.get("rule_id") or "").lower()
                if q not in name and q not in desc and q not in rid:
                    continue
            stats = data.get("stats") or {}
            items.append({
                "rule_id": data.get("rule_id"),
                "name": data.get("name"),
                "level": data.get("level"),
                "scope": data.get("scope"),
                "status": data.get("status"),
                "version": data.get("version"),
                "source": data.get("source"),
                "category": data.get("category"),
                "file": rel_file_path(fp, rules_dir),
                "hit_rate": stats.get("hit_rate", 0.0),
                "severity_on_violation": data.get("severity_on_violation"),
            })

        self._ok({"total": len(items), "rules": items}, "查询成功")

    # ===== API: GET /api/rules/{rule_id}（详情）=====
    def _handle_get_rule(self, rule_id: str) -> None:
        """GET /api/rules/{rule_id} — 规则详情（含 changelog）。"""
        data = load_rule(self.rules_dir, rule_id)
        if data is None:
            self._not_found(f"规则 {rule_id} 不存在")
            return
        self._ok(data, "查询成功")

    # ===== API: POST /api/rules（创建草稿）=====
    def _handle_create_rule(self) -> None:
        """POST /api/rules — 创建草稿规则。

        自动生成 rule_id（若未提供）、status=draft、source=custom、version=1.0.0。
        校验 Schema 后写入 rules/custom/draft/{rule_id}.json。
        """
        body = self._read_body()

        # 自动生成 rule_id
        level = body.get("level", "")
        if not level:
            self._err("缺少必填字段: level")
            return
        rule_id = body.get("rule_id") or generate_rule_id(level)
        if not RULE_ID_RE.match(rule_id):
            self._err(f"rule_id 格式不合法: {rule_id!r}")
            return

        # 检查重复
        if find_rule_file(self.rules_dir, rule_id) is not None:
            self._err(f"rule_id 已存在: {rule_id}", code=409, http_status=409)
            return

        # 填充默认字段
        now = now_iso()
        body["rule_id"] = rule_id
        body["status"] = "draft"
        body["source"] = body.get("source") or "custom"
        body["version"] = body.get("version") or "1.0.0"
        body["created_at"] = now
        body["updated_at"] = now
        body["changelog"] = body.get("changelog") or [
            {
                "version": body["version"],
                "date": today_str(),
                "author": body.get("owner") or "anonymous",
                "change": "初始版本（草稿创建）",
            }
        ]

        # Schema 校验
        ok, errors = validate_rule_data(body)
        if not ok:
            self._err("Schema 校验失败: " + "; ".join(errors), code=400)
            return

        # 写入文件：rules/custom/draft/{rule_id}.json
        file_path = self.rules_dir / "custom" / "draft" / f"{rule_id}.json"
        write_rule(file_path, body)
        self._ok({"rule_id": rule_id, "file": rel_file_path(file_path, self.rules_dir)},
                 "创建成功")

    # ===== API: PUT /api/rules/{rule_id}（更新 + 自动 changelog）=====
    def _handle_update_rule(self, rule_id: str) -> None:
        """PUT /api/rules/{rule_id} — 更新规则并自动写 changelog。

        不允许修改 rule_id/created_at。version patch 号自增。
        跨单位规则（confirmation_required=true）修改后状态变为 pending_confirmation。
        L1 铁律不可降级为 L2/L3。
        """
        existing = load_rule(self.rules_dir, rule_id)
        if existing is None:
            self._not_found(f"规则 {rule_id} 不存在")
            return

        body = self._read_body()

        # L1 不可降级检查
        old_level = existing.get("level")
        new_level = body.get("level")
        if old_level == LEVEL_L1 and new_level in ("L2-LOGIC", "L3-BUSINESS"):
            self._err("L1 铁律不可降级为 L2/L3", code=403, http_status=403)
            return

        # 合并字段（禁止修改 rule_id / created_at）
        author = body.pop("author", None) or body.pop("_author", None) or "system"
        change_note = body.pop("change", None) or body.pop("_change", None)
        body.pop("rule_id", None)
        body.pop("created_at", None)
        existing.update(body)

        # version patch 号自增
        old_version = existing.get("version", "1.0.0")
        new_version = bump_patch_version(old_version)
        existing["version"] = new_version
        existing["updated_at"] = now_iso()

        # 跨单位规则修改后进入 pending_confirmation（draft 除外）
        is_cross_unit = existing.get("scope") == SCOPE_CROSS_UNIT
        confirmation_required = existing.get("confirmation_required") is True
        if is_cross_unit and confirmation_required and existing.get("status") != "draft":
            existing["status"] = "pending_confirmation"

        # 追加 changelog
        change_desc = change_note or "更新规则字段"
        existing.setdefault("changelog", []).append({
            "version": new_version,
            "date": today_str(),
            "author": author,
            "change": change_desc,
        })

        # Schema 校验
        ok, errors = validate_rule_data(existing)
        if not ok:
            self._err("Schema 校验失败: " + "; ".join(errors), code=400)
            return

        # 写回原文件
        file_path = find_rule_file(self.rules_dir, rule_id)
        if file_path is None:
            self._not_found(f"规则 {rule_id} 文件定位失败")
            return
        write_rule(file_path, existing)
        self._ok({"rule_id": rule_id, "version": new_version}, "更新成功")

    # ===== API: DELETE /api/rules/{rule_id}（仅 draft 可删）=====
    def _handle_delete_rule(self, rule_id: str) -> None:
        """DELETE /api/rules/{rule_id} — 删除规则（仅 draft 状态可删）。"""
        data = load_rule(self.rules_dir, rule_id)
        if data is None:
            self._not_found(f"规则 {rule_id} 不存在")
            return
        if data.get("status") != "draft":
            self._err("仅 draft 状态可删", code=403, http_status=403)
            return
        file_path = find_rule_file(self.rules_dir, rule_id)
        if file_path is None:
            self._not_found(f"规则 {rule_id} 文件定位失败")
            return
        try:
            file_path.unlink()
        except OSError as e:
            self._server_error(f"删除文件失败: {e}")
            return
        self._ok({"rule_id": rule_id}, "删除成功")

    # ===== API: POST /api/rules/{rule_id}/transition（状态流转）=====
    def _handle_transition(self, rule_id: str) -> None:
        """POST /api/rules/{rule_id}/transition — 状态流转。

        body: {"to": "目标状态", "reason": "...", "operator": "...",
               "effective_scope": "global"|"project", "project_scope": ["项目A", ...]}
        检查状态转换合法性，更新 status 并追加 changelog。
        跨单位规则变为 active 需经协同确认。

        B-4.4 新增：当流转目标为 active 时，请求体可携带 effective_scope 与
        project_scope，写入规则 JSON：
          - effective_scope="global" → 全局生效（默认）
          - effective_scope="project" + project_scope=[项目名...] → 仅指定项目生效
        """
        data = load_rule(self.rules_dir, rule_id)
        if data is None:
            self._not_found(f"规则 {rule_id} 不存在")
            return

        body = self._read_body()
        target = body.get("to", "").strip()
        reason = body.get("reason", "").strip()
        if not target:
            self._err("缺少必填字段: to")
            return

        current = data.get("status", "")
        if current == target:
            self._err(f"当前状态已是 {current}")
            return

        # 检查状态转换合法性
        allowed = STATE_TRANSITIONS.get(current, set())
        if target not in allowed:
            self._err(
                f"非法状态转换: {current} → {target}（允许: {sorted(allowed) or '无'}）",
                code=400,
            )
            return

        # 跨单位规则变为 active 需协同确认（从 pending_confirmation 经 confirm 流程除外）
        is_cross_unit = data.get("scope") == SCOPE_CROSS_UNIT
        confirmation_required = data.get("confirmation_required") is True
        if (is_cross_unit and confirmation_required and target == "active"
                and current != "pending_confirmation"):
            self._err("跨单位规则需协同确认后方可激活，请改用 /confirm 流程", code=403,
                      http_status=403)
            return

        # B-4.4：流转到 active 时，可选写入 effective_scope / project_scope
        if target == "active":
            effective_scope = body.get("effective_scope")
            if effective_scope is not None:
                if effective_scope not in ("global", "project"):
                    self._err("effective_scope 必须为 global 或 project")
                    return
                data["effective_scope"] = effective_scope
                if effective_scope == "project":
                    ps = body.get("project_scope")
                    if ps is None:
                        self._err("effective_scope=project 时必须提供 project_scope")
                        return
                    if isinstance(ps, str):
                        ps = [ps]
                    if not isinstance(ps, list) or not ps:
                        self._err("project_scope 必须是非空字符串数组")
                        return
                    if not all(isinstance(x, str) and x.strip() for x in ps):
                        self._err("project_scope 数组元素必须是非空字符串")
                        return
                    data["project_scope"] = ps
                else:
                    # global 时清空 project_scope（避免历史值干扰）
                    data["project_scope"] = []
            change_desc_extra = ""
            if data.get("effective_scope"):
                if data["effective_scope"] == "project":
                    change_desc_extra = f"（生效范围: 项目级 {data.get('project_scope', [])}）"
                else:
                    change_desc_extra = "（生效范围: 全局）"
        else:
            change_desc_extra = ""

        # 更新状态
        data["status"] = target
        data["updated_at"] = now_iso()
        new_version = bump_patch_version(data.get("version", "1.0.0"))
        data["version"] = new_version
        change_desc = f"状态流转: {current} → {target}"
        if reason:
            change_desc += f"（原因: {reason}）"
        change_desc += change_desc_extra
        data.setdefault("changelog", []).append({
            "version": new_version,
            "date": today_str(),
            "author": body.get("operator") or "system",
            "change": change_desc,
        })

        file_path = find_rule_file(self.rules_dir, rule_id)
        if file_path is None:
            self._not_found(f"规则 {rule_id} 文件定位失败")
            return
        write_rule(file_path, data)
        self._ok({"rule_id": rule_id, "status": target, "version": new_version},
                 "状态流转成功")

    # ===== API: POST /api/rules/{rule_id}/confirm（协同确认）=====
    def _handle_confirm(self, rule_id: str) -> None:
        """POST /api/rules/{rule_id}/confirm — 协同确认（跨单位规则）。

        body: {"confirmor": "...", "decision": "approve"/"reject", "reason": "..."}
        approve → 状态变为 active；reject → 状态回退至 incubating。
        """
        data = load_rule(self.rules_dir, rule_id)
        if data is None:
            self._not_found(f"规则 {rule_id} 不存在")
            return

        if not data.get("confirmation_required"):
            self._err("该规则无需协同确认", code=400)
            return
        if data.get("status") != "pending_confirmation":
            self._err(f"规则当前状态为 {data.get('status')}，非 pending_confirmation，无法确认",
                      code=400)
            return

        body = self._read_body()
        confirmor = body.get("confirmor", "").strip()
        decision = body.get("decision", "").strip().lower()
        reason = body.get("reason", "").strip()
        if not confirmor:
            self._err("缺少必填字段: confirmor")
            return
        if decision not in ("approve", "reject"):
            self._err("decision 必须为 approve 或 reject")
            return

        new_status = "active" if decision == "approve" else "incubating"
        old_status = data["status"]
        data["status"] = new_status
        data["updated_at"] = now_iso()
        new_version = bump_patch_version(data.get("version", "1.0.0"))
        data["version"] = new_version
        action = "确认通过" if decision == "approve" else "确认驳回"
        change_desc = f"协同确认({action}): 确认人={confirmor}"
        if reason:
            change_desc += f"（理由: {reason}）"
        data.setdefault("changelog", []).append({
            "version": new_version,
            "date": today_str(),
            "author": confirmor,
            "change": change_desc,
        })

        file_path = find_rule_file(self.rules_dir, rule_id)
        if file_path is None:
            self._not_found(f"规则 {rule_id} 文件定位失败")
            return
        write_rule(file_path, data)

        # E-3.2：协同确认成功后调用 audit_memory.append_rule_transitioned 记录事件
        # 通过审核记忆流通知发起方（容错，模块缺失时跳过）
        owner = data.get("owner") or "unknown"
        memory_event: Dict[str, Any] = {
            "recorded": False,
            "owner": owner,
            "decision": decision,
        }
        try:
            from audit_memory import AuditMemory  # type: ignore
            memory = AuditMemory(SKILL_ROOT / "audit_memory")
            event_reason = (
                f"协同确认({action}): 确认人={confirmor}"
                f"（decision={decision}, owner={owner}）"
            )
            if reason:
                event_reason += f"（理由: {reason}）"
            memory.append_rule_transitioned(
                rule_id=rule_id,
                from_status=old_status,
                to_status=new_status,
                reason=event_reason,
                operator=confirmor,
            )
            memory_event["recorded"] = True
            logger.info(
                "E-3.2 协同确认事件已记录到审核记忆流: rule_id=%s decision=%s owner=%s",
                rule_id, decision, owner,
            )
        except ImportError:
            logger.warning("audit_memory 模块未安装，跳过协同确认事件记录")
            memory_event["reason"] = "audit_memory 模块未安装"
        except Exception as e:
            logger.warning(f"记录协同确认事件失败（不影响主流程）: {e}")
            memory_event["reason"] = str(e)

        self._ok({
            "rule_id": rule_id,
            "status": new_status,
            "version": new_version,
            "decision": decision,
            "owner": owner,
            "memory_event": memory_event,
        }, f"协同确认{action}成功")

    # ===== API: POST /api/rules/{rule_id}/force_confirm（管理员强制确认）=====
    def _handle_force_confirm(self, rule_id: str) -> None:
        """POST /api/rules/{rule_id}/force_confirm — 管理员强制确认（B-5.3）。

        body: {"admin": "admin_zhang", "reason": "监理方未响应超过7天..."}

        逻辑：
          1. 加载规则，检查 status=pending_confirmation
          2. 检查请求体 admin 与 reason 非空（reason 至少 5 个字符）
          3. 更新 status=active，追加 changelog 条目（含 admin、reason、
             force_confirm=true 标记）
          4. 写回规则文件
          5. 返回成功
        """
        data = load_rule(self.rules_dir, rule_id)
        if data is None:
            self._not_found(f"规则 {rule_id} 不存在")
            return

        if data.get("status") != "pending_confirmation":
            self._err(
                f"规则当前状态为 {data.get('status')}，非 pending_confirmation，无法强制确认",
                code=400,
            )
            return

        body = self._read_body()
        admin = (body.get("admin") or "").strip()
        reason = (body.get("reason") or "").strip()
        if not admin:
            self._err("缺少必填字段: admin")
            return
        if not reason or len(reason) < 5:
            self._err("reason 必填且至少 5 个字符（强制确认须填写充分理由）")
            return

        old_status = data["status"]
        new_status = "active"
        data["status"] = new_status
        data["updated_at"] = now_iso()
        new_version = bump_patch_version(data.get("version", "1.0.0"))
        data["version"] = new_version
        change_desc = (
            f"管理员强制确认: {old_status} → {new_status}（admin={admin}, "
            f"reason={reason}, force_confirm=true）"
        )
        data.setdefault("changelog", []).append({
            "version": new_version,
            "date": today_str(),
            "author": admin,
            "change": change_desc,
            "force_confirm": True,
            "admin": admin,
            "reason": reason,
        })

        file_path = find_rule_file(self.rules_dir, rule_id)
        if file_path is None:
            self._not_found(f"规则 {rule_id} 文件定位失败")
            return
        write_rule(file_path, data)

        # E-3.2：强制确认同样通过审核记忆流通知发起方（owner）
        owner = data.get("owner") or "unknown"
        memory_event: Dict[str, Any] = {
            "recorded": False,
            "owner": owner,
            "decision": "force_approve",
        }
        try:
            from audit_memory import AuditMemory  # type: ignore
            memory = AuditMemory(SKILL_ROOT / "audit_memory")
            event_reason = (
                f"管理员强制确认: {old_status} → {new_status}"
                f"（admin={admin}, owner={owner}, reason={reason}）"
            )
            memory.append_rule_transitioned(
                rule_id=rule_id,
                from_status=old_status,
                to_status=new_status,
                reason=event_reason,
                operator=admin,
            )
            memory_event["recorded"] = True
            logger.info(
                "E-3.2 强制确认事件已记录到审核记忆流: rule_id=%s admin=%s owner=%s",
                rule_id, admin, owner,
            )
        except ImportError:
            logger.warning("audit_memory 模块未安装，跳过强制确认事件记录")
            memory_event["reason"] = "audit_memory 模块未安装"
        except Exception as e:
            logger.warning(f"记录强制确认事件失败（不影响主流程）: {e}")
            memory_event["reason"] = str(e)

        self._ok({
            "rule_id": rule_id,
            "status": new_status,
            "version": new_version,
            "force_confirm": True,
            "admin": admin,
            "owner": owner,
            "memory_event": memory_event,
        }, "强制确认成功")

    # ===== API: GET /api/rules/{rule_id}/stats（命中率/误报率）=====
    def _handle_get_stats(self, rule_id: str) -> None:
        """GET /api/rules/{rule_id}/stats — 返回规则命中率/误报率统计。"""
        data = load_rule(self.rules_dir, rule_id)
        if data is None:
            self._not_found(f"规则 {rule_id} 不存在")
            return
        stats = data.get("stats") or {}
        result = {
            "rule_id": rule_id,
            "total_hits": stats.get("total_hits", 0),
            "total_reviews": stats.get("total_reviews", 0),
            "hit_rate": stats.get("hit_rate", 0.0),
            "false_positive_count": stats.get("false_positive_count", 0),
            "false_positive_rate": stats.get("false_positive_rate", 0.0),
            "last_hit_at": stats.get("last_hit_at"),
            "last_review_at": stats.get("last_review_at"),
        }
        self._ok(result, "查询成功")

    # ===== API: GET /api/rules/{rule_id}/changelog（变更历史）=====
    def _handle_get_changelog(self, rule_id: str) -> None:
        """GET /api/rules/{rule_id}/changelog — 返回规则变更历史。"""
        data = load_rule(self.rules_dir, rule_id)
        if data is None:
            self._not_found(f"规则 {rule_id} 不存在")
            return
        self._ok({"rule_id": rule_id, "changelog": data.get("changelog", [])},
                 "查询成功")

    # ===== API: POST /api/rules/{rule_id}/test（沙箱测试）=====
    def _handle_test_rule(self, rule_id: str) -> None:
        """POST /api/rules/{rule_id}/test — 在沙箱中测试规则。

        body: {"sample_data": {"rows": [...]}, "doc_data": {...}}
        SINGLE_DOC/CROSS_DOC → 用 sample_data 作为单份资料数据
        CROSS_UNIT → 用 doc_data.party_a_data / party_b_data
        """
        data = load_rule(self.rules_dir, rule_id)
        if data is None:
            self._not_found(f"规则 {rule_id} 不存在")
            return

        body = self._read_body()
        sample_data = body.get("sample_data") or {}
        doc_data = body.get("doc_data") or {}

        try:
            rule_obj = Rule.from_dict(data)
        except Exception as e:
            self._err(f"规则对象构造失败: {e}", code=500, http_status=500)
            return

        scope = data.get("scope")
        violations: List[Any] = []

        if scope == SCOPE_SINGLE_DOC:
            checker = SingleDocChecker()
            violations = checker.check(rule_obj, sample_data)
        elif scope == SCOPE_CROSS_DOC:
            checker = CrossDocChecker()
            # CROSS_DOC 支持传入 docs 列表或单份资料
            docs = body.get("docs")
            if isinstance(docs, list):
                violations = checker.check(rule_obj, docs)
            else:
                violations = checker.check(rule_obj, [sample_data])
        elif scope == SCOPE_CROSS_UNIT:
            checker = CrossUnitChecker()
            party_a = doc_data.get("party_a_data") or sample_data
            party_b = doc_data.get("party_b_data")
            if party_b is None:
                self._err("CROSS_UNIT 规则测试需要 doc_data.party_b_data", code=400)
                return
            violations = checker.check(rule_obj, party_a, party_b)
        else:
            self._err(f"未知作用域: {scope}", code=400)
            return

        violation_list = [violation_to_dict(v) for v in violations]
        self._ok({
            "rule_id": rule_id,
            "scope": scope,
            "violations": violation_list,
            "passed": len(violation_list) == 0,
        }, "测试完成")

    # ===== GET /registry =====
    def _handle_get_registry(self) -> None:
        """GET /registry — 返回 registry.json 注册表。"""
        reg_path = self.rules_dir / "registry.json"
        if not reg_path.is_file():
            self._err("registry.json 不存在", code=404, http_status=404)
            return
        try:
            data = json.loads(reg_path.read_text(encoding="utf-8"))
        except Exception as e:
            self._server_error(f"读取 registry.json 失败: {e}")
            return
        self._ok(data, "查询成功")

    # ===== GET /stats（总体统计）=====
    def _handle_overview_stats(self) -> None:
        """GET /stats — 返回规则总体统计（按 level/scope/status 分布）。"""
        all_rules = load_all_rules_raw(self.rules_dir)
        by_level: Dict[str, int] = {}
        by_scope: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        for _fp, data in all_rules:
            lvl = data.get("level", "UNKNOWN")
            scp = data.get("scope", "UNKNOWN")
            stt = data.get("status", "UNKNOWN")
            by_level[lvl] = by_level.get(lvl, 0) + 1
            by_scope[scp] = by_scope.get(scp, 0) + 1
            by_status[stt] = by_status.get(stt, 0) + 1
        self._ok({
            "total_rules": len(all_rules),
            "by_level": by_level,
            "by_scope": by_scope,
            "by_status": by_status,
        }, "查询成功")

    # ===== API: GET /api/feedbacks（列表筛选）=====
    def _handle_list_feedbacks(self, query: Dict[str, List[str]]) -> None:
        """GET /api/feedbacks — 反馈列表，支持 type/status/audit_id 筛选。"""
        store = FeedbackStore(self.feedbacks_dir)
        ftype = (query.get("type", [""])[0] or "").strip()
        status = (query.get("status", [""])[0] or "").strip()
        audit_id = (query.get("audit_id", [""])[0] or "").strip()
        try:
            items = store.list_all(
                type=(ftype or None),
                status=(status or None),
                audit_id=(audit_id or None),
            )
        except ValueError as e:
            self._err(str(e))
            return
        self._ok({"total": len(items), "feedbacks": items}, "查询成功")

    # ===== API: GET /api/feedbacks/{feedback_id}（详情）=====
    def _handle_get_feedback(self, feedback_id: str) -> None:
        """GET /api/feedbacks/{feedback_id} — 反馈详情。"""
        if not FEEDBACK_ID_RE.match(feedback_id):
            self._err(f"feedback_id 格式不合法: {feedback_id!r}")
            return
        store = FeedbackStore(self.feedbacks_dir)
        data = store.get(feedback_id)
        if data is None:
            self._not_found(f"反馈 {feedback_id} 不存在")
            return
        self._ok(data, "查询成功")

    # ===== API: GET /api/feedbacks/stats（统计）=====
    def _handle_feedback_stats(self) -> None:
        """GET /api/feedbacks/stats — 按 type/status 分布统计。"""
        store = FeedbackStore(self.feedbacks_dir)
        items = store.list_all()
        by_type: Dict[str, int] = {"missed": 0, "false_positive": 0}
        by_status: Dict[str, int] = {"new": 0, "analyzed": 0, "clustered": 0, "resolved": 0}
        by_audit: Dict[str, int] = {}
        for it in items:
            t = it.get("type", "")
            s = it.get("status", "new")
            a = it.get("audit_id", "")
            if t in by_type:
                by_type[t] += 1
            if s in by_status:
                by_status[s] += 1
            if a:
                by_audit[a] = by_audit.get(a, 0) + 1
        counts = store.count()
        self._ok({
            "total": counts["total"],
            "by_type": by_type,
            "by_status": by_status,
            "by_audit_id": by_audit,
            "counts": counts,
        }, "查询成功")

    # ===== API: POST /api/feedbacks（创建反馈）=====
    def _handle_create_feedback(self) -> None:
        """POST /api/feedbacks — 创建反馈。

        请求体字段：
            audit_id (str, 必填)
            type (str, 必填): missed / false_positive
            user_id (str, 必填)
            context (dict, 必填): 含 other_hit_rules
            user_input (dict, 必填): 含 summary
            rule_id (str, 误报时必填)
        """
        try:
            body = self._read_body()
        except ValueError as e:
            self._err(str(e))
            return

        audit_id = body.get("audit_id")
        ftype = body.get("type")
        user_id = body.get("user_id")
        context = body.get("context")
        user_input = body.get("user_input")
        rule_id = body.get("rule_id")

        # 基础字段校验
        if not audit_id or not isinstance(audit_id, str):
            self._err("缺少必填字段: audit_id")
            return
        if ftype not in FEEDBACK_TYPE_ENUM:
            self._err(f"type 必须为 {FEEDBACK_TYPE_ENUM} 之一")
            return
        if not user_id or not isinstance(user_id, str):
            self._err("缺少必填字段: user_id")
            return
        if not isinstance(context, dict):
            self._err("context 必须为对象")
            return
        if not isinstance(user_input, dict):
            self._err("user_input 必须为对象")
            return
        if not str(user_input.get("summary", "")).strip():
            self._err("user_input.summary 必填且非空")
            return
        if ftype == "false_positive" and (not rule_id or not str(rule_id).strip()):
            self._err("type=false_positive 时 rule_id 必填")
            return

        store = FeedbackStore(self.feedbacks_dir)
        try:
            feedback_id = store.create(
                audit_id=audit_id,
                type=ftype,
                user_id=user_id,
                context=context,
                user_input=user_input,
                rule_id=rule_id,
            )
        except ValueError as e:
            self._err(str(e))
            return
        except Exception as e:
            logger.error(f"创建反馈失败: {e}\n{traceback.format_exc()}")
            self._server_error(f"创建反馈失败: {e}")
            return

        data = store.get(feedback_id)

        # C-4.1 自动触发：累积达到 AUTO_TRIGGER_THRESHOLD(20) 条 new 反馈时，
        # 自动调用反馈分析管道。失败不影响反馈创建结果。
        auto_analyze_result: Optional[Dict[str, Any]] = None
        try:
            from feedback_analyzer import (
                FeedbackAnalyzer as _FA,
                AUTO_TRIGGER_THRESHOLD as _THRESHOLD,
                should_auto_trigger as _should,
            )
            should, new_count = _should(store, _THRESHOLD)
            if should:
                analyzer = _FA(
                    feedbacks_dir=self.feedbacks_dir,
                    rules_dir=self.rules_dir,
                )
                auto_analyze_result = analyzer.analyze(
                    min_feedback=_THRESHOLD,
                    dry_run=False,
                )
                logger.info(
                    "C-4.1 自动触发反馈分析：new_count=%d, status=%s",
                    new_count, auto_analyze_result.get("status"),
                )
        except Exception as e:
            # 自动触发失败不影响反馈创建
            logger.warning(f"C-4.1 自动触发反馈分析失败（不影响反馈创建）: {e}")
            auto_analyze_result = {"status": "error", "reason": str(e)}

        resp_data = {"feedback_id": feedback_id, "feedback": data}
        if auto_analyze_result is not None:
            resp_data["auto_analyze"] = auto_analyze_result
        self._ok(resp_data, "创建成功")

    # ===== API: POST /api/feedbacks/{feedback_id}/transition（状态流转）=====
    def _handle_feedback_transition(self, feedback_id: str) -> None:
        """POST /api/feedbacks/{feedback_id}/transition — 更新反馈状态。

        请求体字段：
            status (str, 必填): new / analyzed / clustered / resolved
            cluster_id (str, 可选)
        """
        if not FEEDBACK_ID_RE.match(feedback_id):
            self._err(f"feedback_id 格式不合法: {feedback_id!r}")
            return
        try:
            body = self._read_body()
        except ValueError as e:
            self._err(str(e))
            return
        new_status = body.get("status")
        cluster_id = body.get("cluster_id")
        if new_status not in FEEDBACK_STATUS_ENUM:
            self._err(f"status 必须为 {FEEDBACK_STATUS_ENUM} 之一")
            return
        store = FeedbackStore(self.feedbacks_dir)
        try:
            ok = store.update_status(feedback_id, new_status, cluster_id=cluster_id)
        except ValueError as e:
            self._err(str(e))
            return
        except Exception as e:
            logger.error(f"更新反馈状态失败: {e}\n{traceback.format_exc()}")
            self._server_error(f"更新反馈状态失败: {e}")
            return
        if not ok:
            self._not_found(f"反馈 {feedback_id} 不存在")
            return
        self._ok({"feedback_id": feedback_id, "status": new_status}, "更新成功")

    # ===== API: POST /api/feedbacks/analyze（手动触发 LLM 分析管道，C-4.3）=====
    def _handle_analyze_feedbacks(self) -> None:
        """POST /api/feedbacks/analyze — 手动触发 LLM 反馈分析管道。

        请求体字段（均可选）：
            min_feedback (int, 默认 3): 触发分析所需最小 new 反馈数
            dry_run (bool, 默认 false): 仅输出报告，不写候选规则/不更新状态
            eps (float, 默认 0.3): DBSCAN eps
            min_samples (int, 默认 3): DBSCAN min_samples
        """
        try:
            from feedback_analyzer import FeedbackAnalyzer, AUTO_TRIGGER_THRESHOLD
        except ImportError as e:
            self._server_error(f"feedback_analyzer 模块加载失败: {e}")
            return

        try:
            body = self._read_body()
        except ValueError as e:
            self._err(str(e))
            return

        min_feedback = int(body.get("min_feedback", 3))
        dry_run = bool(body.get("dry_run", False))
        eps = float(body.get("eps", 0.3))
        min_samples = int(body.get("min_samples", 3))

        try:
            analyzer = FeedbackAnalyzer(
                feedbacks_dir=self.feedbacks_dir,
                rules_dir=self.rules_dir,
            )
            result = analyzer.analyze(
                min_feedback=min_feedback,
                dry_run=dry_run,
                eps=eps,
                min_samples=min_samples,
            )
        except Exception as e:
            logger.error(f"反馈分析失败: {e}\n{traceback.format_exc()}")
            self._server_error(f"反馈分析失败: {e}")
            return

        # 状态码：skipped 视为业务正常（不算错误），返回 200
        msg = ("分析完成" if result.get("status") == "completed"
               else f"分析跳过: {result.get('reason', '')}")
        self._ok(result, msg)

    # ===== API: GET /api/reflections（反思报告列表，D-4.2）=====
    def _handle_list_reflections(self) -> None:
        """GET /api/reflections — 反思报告列表。

        扫描 rules/reflections/*.md 文件，按日期降序返回
        [{date, title, file, size, mtime}, ...]。
        模块缺失时返回 503。
        """
        try:
            from rule_reflector import RuleReflector
        except ImportError as e:
            self._err(f"rule_reflector 模块加载失败: {e}", code=503, http_status=503)
            return
        try:
            reflector = RuleReflector(rules_dir=self.rules_dir)
            reports = reflector.list_reports()
        except Exception as e:
            logger.error(f"列出反思报告失败: {e}\n{traceback.format_exc()}")
            self._server_error(f"列出反思报告失败: {e}")
            return
        self._ok({"total": len(reports), "reports": reports}, "查询成功")

    # ===== API: GET /api/reflections/{date}（反思报告内容，D-4.2）=====
    def _handle_get_reflection(self, date_str: str) -> None:
        """GET /api/reflections/{date} — 指定日期的反思报告内容。

        返回 {date, content, file}。报告不存在返回 404。
        """
        try:
            from rule_reflector import RuleReflector
        except ImportError as e:
            self._err(f"rule_reflector 模块加载失败: {e}", code=503, http_status=503)
            return
        # 容错：剥离 .md 后缀（URL 中通常不带后缀）
        date_clean = date_str[:-3] if date_str.endswith(".md") else date_str
        try:
            reflector = RuleReflector(rules_dir=self.rules_dir)
            content = reflector.get_report(date_clean)
        except Exception as e:
            logger.error(f"读取反思报告失败: {e}\n{traceback.format_exc()}")
            self._server_error(f"读取反思报告失败: {e}")
            return
        if content is None:
            self._not_found(f"反思报告 {date_clean} 不存在")
            return
        self._ok({"date": date_clean, "content": content,
                  "file": str(reflector.reflections_dir / f"{date_clean}.md")},
                 "查询成功")

    # ===== API: POST /api/reflections/trigger（手动触发反思，D-4.2）=====
    def _handle_trigger_reflection(self) -> None:
        """POST /api/reflections/trigger — 手动触发一次反思。

        body: {"days": 7, "dry_run": false}
        调用 rule_reflector.RuleReflector.reflect，返回结果摘要。
        """
        try:
            from rule_reflector import RuleReflector
        except ImportError as e:
            self._err(f"rule_reflector 模块加载失败: {e}", code=503, http_status=503)
            return
        try:
            body = self._read_body()
        except ValueError as e:
            self._err(str(e))
            return
        days = int(body.get("days", 7))
        dry_run = bool(body.get("dry_run", False))
        if days <= 0 or days > 365:
            self._err("days 必须为 1~365 之间的整数")
            return
        try:
            reflector = RuleReflector(rules_dir=self.rules_dir)
            result = reflector.reflect(days=days, dry_run=dry_run)
        except Exception as e:
            logger.error(f"触发反思失败: {e}\n{traceback.format_exc()}")
            self._server_error(f"触发反思失败: {e}")
            return
        self._ok(result, "反思完成")

    # ===== API: GET /api/incubator（孵化区候选规则列表，D-4.3）=====
    def _handle_list_incubator(self) -> None:
        """GET /api/incubator — 孵化区候选规则列表。

        扫描 rules/custom/incubator/*.json，返回
        [{rule_id, name, level, status, source, incubation_meta, file}, ...]。
        """
        try:
            from rule_reflector import RuleReflector
        except ImportError as e:
            self._err(f"rule_reflector 模块加载失败: {e}", code=503, http_status=503)
            return
        try:
            reflector = RuleReflector(rules_dir=self.rules_dir)
            items = reflector.list_incubator_rules()
        except Exception as e:
            logger.error(f"列出孵化区候选规则失败: {e}\n{traceback.format_exc()}")
            self._server_error(f"列出孵化区候选规则失败: {e}")
            return
        # 补充 incubation_meta 字段（list_incubator_rules 默认未返回）
        # 通过文件读取补充
        from pathlib import Path as _P
        enriched: List[Dict[str, Any]] = []
        for it in items:
            entry = dict(it)
            fp = it.get("file")
            meta: Dict[str, Any] = {}
            if fp:
                try:
                    raw = json.loads(_P(fp).read_text(encoding="utf-8"))
                    meta = raw.get("incubation_meta") or {}
                except Exception:
                    meta = {}
            entry["incubation_meta"] = meta
            enriched.append(entry)
        self._ok({"total": len(enriched), "candidates": enriched}, "查询成功")

    # ===== API: GET /api/incubator/{rule_id}（候选规则详情，D-4.3）=====
    def _handle_get_incubator_rule(self, rule_id: str) -> None:
        """GET /api/incubator/{rule_id} — 候选规则详情。"""
        try:
            from rule_reflector import RuleReflector
        except ImportError as e:
            self._err(f"rule_reflector 模块加载失败: {e}", code=503, http_status=503)
            return
        try:
            reflector = RuleReflector(rules_dir=self.rules_dir)
            items = reflector.list_incubator_rules()
        except Exception as e:
            logger.error(f"查询候选规则详情失败: {e}\n{traceback.format_exc()}")
            self._server_error(f"查询候选规则详情失败: {e}")
            return
        target = next((it for it in items if it.get("rule_id") == rule_id), None)
        if target is None:
            self._not_found(f"候选规则 {rule_id} 不存在")
            return
        # 读取完整 JSON
        fp = target.get("file")
        full_data: Dict[str, Any] = {}
        if fp:
            try:
                full_data = json.loads(Path(fp).read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"读取候选规则文件失败 {fp}: {e}")
        self._ok({"summary": target, "rule": full_data}, "查询成功")

    # ===== API: POST /api/incubator/{rule_id}/promote（提升候选规则，D-4.3）=====
    def _handle_promote_incubator(self, rule_id: str) -> None:
        """POST /api/incubator/{rule_id}/promote — 提升候选规则为 active。

        body: {"reason": "..."}
        """
        try:
            from rule_reflector import RuleReflector
        except ImportError as e:
            self._err(f"rule_reflector 模块加载失败: {e}", code=503, http_status=503)
            return
        try:
            body = self._read_body()
        except ValueError as e:
            self._err(str(e))
            return
        reason = (body.get("reason") or "").strip()
        if not reason:
            self._err("缺少必填字段: reason")
            return
        try:
            reflector = RuleReflector(rules_dir=self.rules_dir)
            ok = reflector.promote_candidate(rule_id, reason)
        except Exception as e:
            logger.error(f"提升候选规则失败: {e}\n{traceback.format_exc()}")
            self._server_error(f"提升候选规则失败: {e}")
            return
        if not ok:
            self._err(f"提升失败：{rule_id}（请检查规则 ID 与当前状态，需为 incubating）",
                      code=400)
            return
        self._ok({"rule_id": rule_id, "status": "active"}, "候选规则已提升为 active")

    # ===== API: POST /api/incubator/{rule_id}/reject（驳回候选规则，D-4.3）=====
    def _handle_reject_incubator(self, rule_id: str) -> None:
        """POST /api/incubator/{rule_id}/reject — 驳回候选规则（标记 deprecated）。

        body: {"reason": "..."}
        """
        try:
            from rule_reflector import RuleReflector
        except ImportError as e:
            self._err(f"rule_reflector 模块加载失败: {e}", code=503, http_status=503)
            return
        try:
            body = self._read_body()
        except ValueError as e:
            self._err(str(e))
            return
        reason = (body.get("reason") or "").strip()
        if not reason:
            self._err("缺少必填字段: reason")
            return
        try:
            reflector = RuleReflector(rules_dir=self.rules_dir)
            ok = reflector.reject_candidate(rule_id, reason)
        except Exception as e:
            logger.error(f"驳回候选规则失败: {e}\n{traceback.format_exc()}")
            self._server_error(f"驳回候选规则失败: {e}")
            return
        if not ok:
            self._err(f"驳回失败：{rule_id}（请检查规则 ID 与当前状态，需为 incubating）",
                      code=400)
            return
        self._ok({"rule_id": rule_id, "status": "deprecated"}, "候选规则已驳回（deprecated）")

    # ===== 静态文件服务 =====
    def _serve_index(self) -> None:
        """GET / — 返回 rule-manager.html（若存在）。"""
        html_path = self.static_dir / "rule-manager.html"
        if not html_path.is_file():
            fallback_html = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                "<title>Rule Admin</title></head><body>"
                "<h1>Rule Admin API</h1>"
                "<p>rule-manager.html 未找到，请开发前端面板。</p>"
                "<p>API 文档参见 /api/rules</p>"
                "</body></html>"
            )
            self._send_text(fallback_html.encode("utf-8"), "text/html; charset=utf-8")
            return
        self._serve_file(html_path)

    # ===== 静态文件服务（补充：feedback-collector.html）=====
    def _serve_feedback_collector(self) -> None:
        """GET /feedback-collector — 返回 feedback-collector.html（若存在）。"""
        html_path = self.static_dir / "feedback-collector.html"
        if not html_path.is_file():
            self._not_found("feedback-collector.html 未找到")
            return
        self._serve_file(html_path)

    def _serve_static(self, segments: List[str]) -> None:
        """GET /static/* — 返回静态资源。"""
        if not segments:
            self._not_found("静态资源路径为空")
            return
        # 防止路径穿越：先做基础检查，再用 resolve() 严格校验
        rel = Path(*segments)
        if ".." in rel.parts:
            self._not_found("非法路径")
            return
        static_root = self.static_dir.resolve()
        file_path = (self.static_dir / rel).resolve()
        try:
            # 验证解析后的绝对路径仍位于 static_dir 之下
            file_path.relative_to(static_root)
        except ValueError:
            self._not_found("非法路径")
            return
        if not file_path.is_file():
            self._not_found("静态资源不存在")
            return
        self._serve_file(file_path)

    def _serve_file(self, file_path: Path) -> None:
        """根据扩展名设置 Content-Type 并返回文件内容。"""
        ext = file_path.suffix.lower()
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }
        content_type = content_types.get(ext, "application/octet-stream")
        try:
            body = file_path.read_bytes()
        except OSError as e:
            self._server_error(f"读取文件失败: {e}")
            return
        self._send_text(body, content_type)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="民航施工资料审核 Skill — 规则管理 API 服务",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"监听端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help=(f"监听地址（默认 {DEFAULT_HOST}，仅本机访问）；"
                              "仅当显式指定 --host 0.0.0.0 时才开放外部访问（需配合防火墙与认证）"))
    parser.add_argument("--rules-dir", default=str(DEFAULT_RULES_DIR),
                        help=f"规则目录（默认 {DEFAULT_RULES_DIR}）")
    return parser.parse_args(argv)


def run(argv: Optional[List[str]] = None) -> int:
    """启动 HTTP 服务。"""
    args = parse_args(argv)
    rules_dir = Path(args.rules_dir).resolve()
    if not rules_dir.is_dir():
        print(f"错误: 规则目录不存在: {rules_dir}", file=sys.stderr)
        return 1

    # 配置处理器类属性
    RuleAdminServer.rules_dir = rules_dir
    RuleAdminServer.static_dir = SKILL_ROOT / "templates"
    RuleAdminServer.feedbacks_dir = SKILL_ROOT / "feedbacks"
    # 确保反馈目录存在
    RuleAdminServer.feedbacks_dir.mkdir(parents=True, exist_ok=True)

    # 预加载规则数
    preloaded = load_all_rules_raw(rules_dir)
    # 预加载反馈数
    try:
        from feedback_store import FeedbackStore as _FS
        fb_count = _FS(RuleAdminServer.feedbacks_dir).count()
    except Exception:
        fb_count = {"total": 0}
    print("=" * 60)
    print("民航施工资料审核 Skill — 规则管理 API")
    print("=" * 60)
    print(f"规则目录: {rules_dir}")
    print(f"规则数量: {len(preloaded)}")
    print(f"反馈目录: {RuleAdminServer.feedbacks_dir}")
    print(f"反馈数量: {fb_count.get('total', 0)}")
    print(f"监听地址: http://{args.host}:{args.port}")
    print(f"API 文档: http://localhost:{args.port}/api/rules")
    print(f"          http://localhost:{args.port}/api/feedbacks")
    print(f"管理面板: http://localhost:{args.port}/")
    print(f"反馈组件: http://localhost:{args.port}/feedback-collector")
    print("-" * 60)
    print("按 Ctrl+C 停止服务")
    print("=" * 60)

    httpd = ThreadingHTTPServer((args.host, args.port), RuleAdminServer)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
