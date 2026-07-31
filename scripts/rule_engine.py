# -*- coding: utf-8 -*-
"""
rule_engine.py — 规则引擎核心模块
=================================

职责（Phase A-2）：
  1. RuleLoader            从 rules/ 目录加载规则文件
  2. RuleMatcher           按资料类型 / 专业 / 作用域匹配规则
  3. ExpressionEvaluator   安全求值 jinja-expr 风格表达式
  4. SingleDocChecker      单资料规则校验（逐行求值）
  5. CrossDocChecker       跨资料规则校验
  6. CrossUnitChecker      跨单位对照规则校验（按 join_key 对齐）
  7. ViolationReporter     违规汇总为标准化报告 / 兼容 findings 格式

设计参考：specs/design-rule-management-subsystem/spec.md 第 5、6 节
数据结构：rules/schema/rule-schema.json

用法：
    python scripts/rule_engine.py             # 自检
    from rule_engine import RuleLoader, ...   # 作为模块导入

约束：
    - Python 3.8+，类型注解，中文注释
    - 安全的 eval（白名单函数：abs/max/min/sum/len/round）
    - 表达式语法错误时返回 True（不违规，避免误报）
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ========== 常量 ==========
# 规则层级
LEVEL_L1 = "L1-IRON"
LEVEL_L2 = "L2-LOGIC"
LEVEL_L3 = "L3-BUSINESS"

# 规则作用域
SCOPE_SINGLE_DOC = "SINGLE_DOC"
SCOPE_CROSS_DOC = "CROSS_DOC"
SCOPE_CROSS_UNIT = "CROSS_UNIT"

# 严重度
SEVERITY_FATAL = "Fatal"
SEVERITY_SANITY = "Sanity Check"
SEVERITY_BEST = "Best Practice"


# ========== 字段别名映射 ==========
# 规则文件用中文字段名（如 "实长"），数据底座用英文字段名（如 "actual_length"）。
# 此映射在 SingleDocChecker 构造 context 时自动注入中文别名，确保规则能命中数据。
FIELD_ALIAS_MAP: Dict[str, str] = {
    "实长": "actual_length",
    "实际桩长": "actual_length",
    "实际长度": "actual_length",
    "桩顶高程": "top_elev",
    "顶高程": "top_elev",
    "桩底高程": "bottom_elev",
    "底高程": "bottom_elev",
    "桩号": "pile_no",
    "设计桩长": "design_length",
    "设计长度": "design_length",
    "桩径": "diameter",
    "直径": "diameter",
    "密实电流": "current",
    "电流": "current",
    "反插次数": "re_penetration",
    "反插": "re_penetration",
    "灌入量": "volume",
    "灌入": "volume",
    "充盈系数": "filling_coeff",
    "竖直度": "verticality",
    "垂直度": "verticality",
    "开始时间": "start_time",
    "开钻时间": "start_time",
    "起始时间": "start_time",
    "结束时间": "end_time",
    "终钻时间": "end_time",
    "终止时间": "end_time",
    "沉管时间": "sink_time",
    "拔管时间": "pull_time",
    "备注": "remark",
    "说明": "remark",
}


# ========== 数据结构 ==========
@dataclass
class Rule:
    """规则对象，字段对应 rule-schema.json。

    必填字段直接声明，可选字段默认 None。
    """
    rule_id: str
    name: str
    level: str
    scope: str
    trigger_when: Dict[str, Any]
    check_expr: Dict[str, Any]
    error_template: str
    status: str
    source: str
    version: str
    created_at: str
    updated_at: str
    changelog: List[Dict[str, Any]]
    # 可选字段
    category: Optional[str] = None
    description: Optional[str] = None
    severity_on_violation: Optional[str] = None
    remediation: Optional[str] = None
    owner: Optional[str] = None
    applies_to: Optional[Dict[str, Any]] = None
    stats: Optional[Dict[str, Any]] = None
    alignment: Optional[Dict[str, Any]] = None
    confirmation_required: Optional[bool] = None
    confirmation_scope: Optional[str] = None
    # B-4.4 生效范围：global=全局生效；project=仅 project_scope 列出的项目生效
    effective_scope: Optional[str] = None
    project_scope: Optional[List[str]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rule":
        """从字典构造 Rule 对象（缺失的可选字段使用默认值）。"""
        # project_scope 兼容字符串/列表两种写法
        ps = data.get("project_scope")
        if isinstance(ps, str):
            ps = [ps]
        elif ps is not None and not isinstance(ps, list):
            ps = None
        return cls(
            rule_id=data["rule_id"],
            name=data["name"],
            level=data["level"],
            scope=data["scope"],
            trigger_when=data.get("trigger_when", {}) or {},
            check_expr=data.get("check_expr", {}) or {},
            error_template=data.get("error_template", ""),
            status=data.get("status", ""),
            source=data.get("source", ""),
            version=data.get("version", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            changelog=data.get("changelog", []) or [],
            category=data.get("category"),
            description=data.get("description"),
            severity_on_violation=data.get("severity_on_violation"),
            remediation=data.get("remediation"),
            owner=data.get("owner"),
            applies_to=data.get("applies_to"),
            stats=data.get("stats"),
            alignment=data.get("alignment"),
            confirmation_required=data.get("confirmation_required"),
            confirmation_scope=data.get("confirmation_scope"),
            effective_scope=data.get("effective_scope"),
            project_scope=ps,
        )


@dataclass
class Violation:
    """违规对象。"""
    rule_id: str
    rule_name: str
    level: str              # L1-IRON / L2-LOGIC / L3-BUSINESS
    scope: str              # SINGLE_DOC / CROSS_DOC / CROSS_UNIT
    severity: str           # Fatal / Sanity Check / Best Practice
    row_index: Optional[int]
    error_message: str
    context: Dict[str, Any]  # 命中时的数据快照
    remediation: Optional[str] = None


# ========== 1. RuleLoader ==========
class RuleLoader:
    """从 rules/ 目录加载规则文件。

    扫描 rules/ 下所有 .json 文件，排除 schema/ 与 lifecycle/ 子目录、registry.json。
    """

    # 排除的子目录名
    EXCLUDED_DIRS = {"schema", "lifecycle"}
    # 排除的文件名
    EXCLUDED_FILES = {"registry.json"}

    def load_all(self, rules_dir: Path) -> List[Rule]:
        """扫描 rules/ 目录下所有 .json 规则文件，返回 Rule 列表。"""
        rules: List[Rule] = []
        rules_dir = Path(rules_dir)
        if not rules_dir.is_dir():
            logger.warning(f"规则目录不存在: {rules_dir}")
            return rules

        for json_path in sorted(rules_dir.rglob("*.json")):
            if self._is_excluded(json_path, rules_dir):
                continue
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"读取规则文件失败 {json_path}: {e}")
                continue
            if not isinstance(data, dict):
                continue
            if "rule_id" not in data:
                # 非规则文件（如 registry-schema.json）
                continue
            try:
                rules.append(Rule.from_dict(data))
            except Exception as e:
                logger.warning(f"构造 Rule 失败 {json_path}: {e}")
        return rules

    def load_active(self, rules_dir: Path, project_name: Optional[str] = None) -> List[Rule]:
        """只加载 status='active' 的规则。

        B-4.4 新增 project_name 过滤：
          - project_name=None → 不过滤，加载全部 active 规则（向后兼容）
          - project_name="某项目" → 按 effective_scope 过滤：
            * effective_scope='global' 或未设置 → 始终加载
            * effective_scope='project' 且 project_name 在 project_scope 中 → 加载
            * 否则不加载
        """
        active_rules = [r for r in self.load_all(rules_dir) if r.status == "active"]
        if project_name is None:
            return active_rules
        return [r for r in active_rules if _rule_applies_to_project(r, project_name)]

    def load_by_id(self, rules_dir: Path, rule_id: str) -> Optional[Rule]:
        """按 rule_id 加载单条规则；未找到返回 None。"""
        for rule in self.load_all(rules_dir):
            if rule.rule_id == rule_id:
                return rule
        return None

    def _is_excluded(self, path: Path, rules_dir: Path) -> bool:
        """判断文件是否应被排除（位于 schema/lifecycle/ 子目录或为 registry.json）。"""
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


def _rule_applies_to_project(rule: "Rule", project_name: str) -> bool:
    """判断规则是否在指定项目中生效（B-4.4 生效范围过滤）。

    - effective_scope 未设置或 'global' → 始终生效
    - effective_scope='project' → 仅当 project_name 在 project_scope 列表中生效
    - effective_scope 为其他值 → 视为 'global'，生效（容错）
    """
    scope = (rule.effective_scope or "global").strip().lower()
    if scope == "project":
        projects = rule.project_scope or []
        return project_name in projects
    # global 或未知值：放行
    return True


# ========== 2. RuleMatcher ==========
class RuleMatcher:
    """按资料类型 / 专业 / 作用域匹配规则。"""

    def match_by_doc_type(self, rules: List[Rule], doc_type: str) -> List[Rule]:
        """按资料类型匹配（检查 trigger_when.doc_type 数组）。"""
        matched: List[Rule] = []
        for rule in rules:
            doc_types = rule.trigger_when.get("doc_type", [])
            if isinstance(doc_types, list) and doc_type in doc_types:
                matched.append(rule)
        return matched

    def match_by_professional(self, rules: List[Rule], professional: str) -> List[Rule]:
        """按专业匹配（检查 applies_to.professional）。"""
        matched: List[Rule] = []
        for rule in rules:
            applies_to = rule.applies_to or {}
            profs = applies_to.get("professional", [])
            if isinstance(profs, list) and professional in profs:
                matched.append(rule)
        return matched

    def match_cross_unit(self, rules: List[Rule], doc_types: List[str]) -> List[Rule]:
        """匹配跨单位规则（trigger_when.doc_type_a 与 doc_type_b 同时在 doc_types 中）。"""
        doc_types_set = set(doc_types)
        matched: List[Rule] = []
        for rule in rules:
            if rule.scope != SCOPE_CROSS_UNIT:
                continue
            tw = rule.trigger_when
            a = tw.get("doc_type_a")
            b = tw.get("doc_type_b")
            if a and b and a in doc_types_set and b in doc_types_set:
                matched.append(rule)
        return matched

    def match_by_scope(self, rules: List[Rule], scope: str) -> List[Rule]:
        """按作用域匹配。"""
        return [r for r in rules if r.scope == scope]


# ========== 3. ExpressionEvaluator ==========
class _SafeDict(dict):
    """format_map 用的字典：缺失 key 时保留 {field} 占位符。"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class ExpressionEvaluator:
    """安全求值表达式（jinja-expr / python_eval 风格）。

    约定：
      - 表达式返回 True  → 校验通过
      - 表达式返回 False → 命中违规
      - 表达式语法错误 / 引用未定义变量 → 返回 True（避免误报）并记录警告
    """

    # 白名单函数（数学运算 + 聚合）
    SAFE_FUNCS: Dict[str, Any] = {
        "abs": abs,
        "max": max,
        "min": min,
        "sum": sum,
        "len": len,
        "round": round,
    }
    # 白名单常量
    SAFE_CONSTS: Dict[str, Any] = {
        "True": True,
        "False": False,
        "None": None,
    }
    # 危险关键字（出现即拒绝求值，按不违规处理）
    FORBIDDEN_TOKENS: Tuple[str, ...] = (
        "import", "open", "exec", "eval", "compile",
        "__", "globals", "locals",
        "getattr", "setattr", "delattr",
        "os.", "sys.", "subprocess",
        "builtins",
    )

    def evaluate(self, expr: str, context: dict) -> bool:
        """求值表达式，返回 True（通过）或 False（违规）。"""
        if not expr or not isinstance(expr, str):
            return True
        # 危险关键字检查
        lower = expr.lower()
        for tok in self.FORBIDDEN_TOKENS:
            if tok in lower:
                logger.warning(f"表达式包含禁止关键字 '{tok}'，按不违规处理: {expr}")
                return True
        # 构建安全的求值环境
        globals_dict: Dict[str, Any] = {"__builtins__": {}}
        locals_dict: Dict[str, Any] = {}
        locals_dict.update(self.SAFE_FUNCS)
        locals_dict.update(self.SAFE_CONSTS)
        if context:
            locals_dict.update(context)
        try:
            result = eval(expr, globals_dict, locals_dict)  # noqa: S307 (受限环境)
            return bool(result)
        except Exception as e:
            logger.warning(f"表达式求值失败，按不违规处理: expr='{expr}', error={e}")
            return True

    def render_template(self, template: str, context: dict) -> str:
        """渲染错误消息模板，缺失字段保留 {field} 占位符。"""
        if not template:
            return ""
        safe_ctx = _SafeDict(context or {})
        try:
            return template.format_map(safe_ctx)
        except (IndexError, ValueError) as e:
            # format_map 一般不会抛 KeyError（_SafeDict 已处理）
            logger.warning(f"模板渲染失败: template='{template}', error={e}")
            return template


# ========== 4. SingleDocChecker ==========
class SingleDocChecker:
    """对单份资料数据执行规则（逐行求值）。"""

    def __init__(self, evaluator: Optional[ExpressionEvaluator] = None) -> None:
        self.evaluator = evaluator or ExpressionEvaluator()

    def check(self, rule: Rule, doc_data: dict) -> List[Violation]:
        """对单份资料数据执行规则。

        doc_data 结构：
            {"doc_type": "碎石桩施工记录",
             "professional": "01_场道工程",
             "rows": [{"pile_no": "Z415", "实长": 13.7, ...}, ...]}

        对每一行数据，构建 context（行字段），调用 evaluator.evaluate。
        返回 Violation 列表（每行一个）。
        """
        violations: List[Violation] = []
        if rule.scope != SCOPE_SINGLE_DOC:
            return violations
        rows = doc_data.get("rows", []) if isinstance(doc_data, dict) else []
        if not isinstance(rows, list):
            return violations
        expr = rule.check_expr.get("expr", "")
        if not expr:
            return violations

        field_required = rule.trigger_when.get("field_required", []) or []
        severity = rule.severity_on_violation or SEVERITY_SANITY

        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            # 构造 context（行字段 + 中文别名注入）
            context: Dict[str, Any] = dict(row)
            # 注入中文字段别名：规则用中文字段名，数据用英文字段名
            for cn_name, en_name in FIELD_ALIAS_MAP.items():
                if en_name in row and cn_name not in context:
                    context[cn_name] = row[en_name]
            # 检查必需字段是否齐全（支持中英文双向匹配）
            if field_required:
                matched = all(f in context for f in field_required)
                if not matched:
                    continue
            # 注入派生字段
            self._inject_derived_fields(context, rule)
            # 求值
            passed = self.evaluator.evaluate(expr, context)
            if not passed:
                error_msg = self.evaluator.render_template(rule.error_template, context)
                violations.append(Violation(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    level=rule.level,
                    scope=rule.scope,
                    severity=severity,
                    row_index=idx,
                    error_message=error_msg,
                    context=self._snapshot(context),
                    remediation=rule.remediation,
                ))
        return violations

    def _inject_derived_fields(self, context: Dict[str, Any], rule: Rule) -> None:
        """根据规则 ID 或字段语义，注入常用派生字段（computed / diff）。

        保留通用性：若所需源字段缺失或非数值，则跳过。
        支持中英文字段名双向查找。
        """
        try:
            # 高程自洽：实长 vs (桩顶高程 - 桩底高程)
            实长 = context.get("实长", context.get("actual_length"))
            桩顶 = context.get("桩顶高程", context.get("top_elev"))
            桩底 = context.get("桩底高程", context.get("bottom_elev"))
            if (isinstance(实长, (int, float))
                    and isinstance(桩顶, (int, float))
                    and isinstance(桩底, (int, float))):
                computed = 桩顶 - 桩底
                diff = abs(实长 - computed)
                context.setdefault("computed", round(computed, 4))
                context.setdefault("diff", round(diff, 4))

            # 充盈系数自洽：充盈系数 vs 灌入量 / (π × (桩径/2)² × 实长)
            充盈 = context.get("充盈系数", context.get("filling_coeff"))
            灌入量 = context.get("灌入量", context.get("volume"))
            桩径 = context.get("桩径", context.get("diameter"))
            if (isinstance(充盈, (int, float))
                    and isinstance(灌入量, (int, float))
                    and isinstance(桩径, (int, float))
                    and isinstance(实长, (int, float)) and 实长 > 0):
                import math
                expected = 灌入量 / (math.pi * (桩径 / 2) ** 2 * 实长)
                coeff_diff = abs(充盈 - expected)
                context.setdefault("expected_coeff", round(expected, 4))
                context.setdefault("coeff_diff", round(coeff_diff, 4))

            # 沉管/拔管时间差
            沉管 = context.get("沉管时间", context.get("sink_time"))
            拔管 = context.get("拔管时间", context.get("pull_time"))
            if 沉管 and 拔管:
                context.setdefault("has_time_pair", True)
        except Exception:
            pass

    @staticmethod
    def _snapshot(context: Dict[str, Any]) -> Dict[str, Any]:
        """构造可 JSON 序列化的数据快照。"""
        snap: Dict[str, Any] = {}
        for k, v in context.items():
            try:
                json.dumps(v, ensure_ascii=False)
                snap[k] = v
            except (TypeError, ValueError):
                snap[k] = str(v)
        return snap


# ========== 5. CrossDocChecker ==========
class CrossDocChecker:
    """对多份资料执行跨资料规则（scope=CROSS_DOC）。

    适用场景：累计工程量闭合、同一工序不同资料日期一致性等。
    """

    def __init__(self, evaluator: Optional[ExpressionEvaluator] = None) -> None:
        self.evaluator = evaluator or ExpressionEvaluator()

    def check(self, rule: Rule, docs_data: List[dict]) -> List[Violation]:
        """对多份资料执行跨资料规则。

        简化策略：合并所有 rows，逐行求值；表达式可引用聚合值（如 sum_value）。
        """
        violations: List[Violation] = []
        if rule.scope != SCOPE_CROSS_DOC:
            return violations
        if not docs_data:
            return violations

        # 合并所有文档的 rows
        all_rows: List[Dict[str, Any]] = []
        for doc in docs_data:
            if not isinstance(doc, dict):
                continue
            for row in doc.get("rows", []) or []:
                if isinstance(row, dict):
                    all_rows.append(row)

        expr = rule.check_expr.get("expr", "")
        if not expr:
            return violations
        severity = rule.severity_on_violation or SEVERITY_SANITY

        for idx, row in enumerate(all_rows):
            context: Dict[str, Any] = dict(row)
            passed = self.evaluator.evaluate(expr, context)
            if not passed:
                error_msg = self.evaluator.render_template(rule.error_template, context)
                violations.append(Violation(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    level=rule.level,
                    scope=rule.scope,
                    severity=severity,
                    row_index=idx,
                    error_message=error_msg,
                    context=dict(context),
                    remediation=rule.remediation,
                ))
        return violations


# ========== 6. CrossUnitChecker ==========
class CrossUnitChecker:
    """跨单位对照规则校验（scope=CROSS_UNIT）。

    读取 rule.alignment，按 join_key 对双方数据做 join，
    对每对匹配行比较 field_a 与 field_b。

    性能优化（E-2）：
      - 按 join_key 建立哈希索引，将 join 复杂度从 O(n*m) 降为 O(n+m)
      - 支持一对多匹配（同一 join_key 多行）
      - 数据量 > CHUNK_THRESHOLD 时启用分块处理，避免内存峰值
    """

    # 分块处理阈值：当 party_a 行数超过此值时启用分块
    CHUNK_THRESHOLD: int = 5000
    # 分块大小：每块处理的行数
    CHUNK_SIZE: int = 2000

    def __init__(self, evaluator: Optional[ExpressionEvaluator] = None) -> None:
        self.evaluator = evaluator or ExpressionEvaluator()

    def check(self, rule: Rule, party_a_data: dict, party_b_data: dict,
              chunk_progress: Optional[Callable[[int, int], None]] = None) -> List[Violation]:
        """对 party_a_data 与 party_b_data 执行跨单位对照。

        Args:
            rule: 跨单位规则（scope=CROSS_UNIT，alignment 非空）
            party_a_data: 甲方资料，结构同 SingleDocChecker 的 doc_data
            party_b_data: 乙方资料，结构同上
            chunk_progress: 可选分块进度回调 (processed, total)；仅在大数据量分块时触发

        Returns:
            Violation 列表（含偏差超阈值 + 缺失对齐键告警）
        """
        violations: List[Violation] = []
        if rule.scope != SCOPE_CROSS_UNIT:
            return violations
        alignment = rule.alignment
        if not alignment:
            return violations

        join_keys: List[str] = alignment.get("join_key", []) or []
        field_a: Optional[str] = alignment.get("field_a")
        field_b: Optional[str] = alignment.get("field_b")
        if not join_keys or not field_a or not field_b:
            return violations

        a_rows = party_a_data.get("rows", []) if isinstance(party_a_data, dict) else []
        b_rows = party_b_data.get("rows", []) if isinstance(party_b_data, dict) else []

        # E-2.1 按 join_key 建立乙方哈希索引（一对多：{key_str: [row1, row2, ...]}）
        b_index: Dict[str, List[Dict[str, Any]]] = self._build_index(b_rows, join_keys)
        # 记录已被匹配过的乙方行 id（用于检测甲方缺失的乙方行）
        matched_b_ids: set = set()

        expr = rule.check_expr.get("expr", "")
        severity = rule.severity_on_violation or SEVERITY_SANITY

        total = len(a_rows)
        # E-2.2 大数据量分块处理
        if total > self.CHUNK_THRESHOLD:
            chunks = [a_rows[i:i + self.CHUNK_SIZE]
                      for i in range(0, total, self.CHUNK_SIZE)]
            logger.info(
                f"跨单位规则 {rule.rule_id} 启用分块处理：共 {total} 行，"
                f"分 {len(chunks)} 块，每块 ≤ {self.CHUNK_SIZE} 行"
            )
            processed = 0
            for chunk_idx, chunk in enumerate(chunks):
                chunk_violations = self._check_chunk(
                    chunk, b_index, rule, join_keys, field_a, field_b,
                    expr, severity, matched_b_ids,
                )
                violations.extend(chunk_violations)
                processed += len(chunk)
                if chunk_progress is not None:
                    try:
                        chunk_progress(processed, total)
                    except Exception as e:
                        logger.warning(f"chunk_progress 回调异常: {e}")
                logger.debug(
                    f"分块 {chunk_idx + 1}/{len(chunks)} 完成，"
                    f"已处理 {processed}/{total}"
                )
        else:
            # 数据量小：直接处理（行为与原实现一致）
            violations = self._check_chunk(
                a_rows, b_index, rule, join_keys, field_a, field_b,
                expr, severity, matched_b_ids,
            )

        # 检查乙方中未匹配的行（甲方缺失）
        for _key_str, b_rows_with_key in b_index.items():
            for b_row in b_rows_with_key:
                if id(b_row) in matched_b_ids:
                    continue
                key_tuple = tuple(b_row.get(k) for k in join_keys)
                violations.append(self._make_missing_violation(
                    rule, key_tuple, join_keys, b_row, side="party_a"
                ))
        return violations

    def _build_index(self, data: List[Dict[str, Any]],
                     join_keys: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """按 join_key 构建哈希索引（支持一对多）。

        Args:
            data: 行列表
            join_keys: 对齐键字段名列表

        Returns:
            {index_key_str: [row1, row2, ...]}
        """
        index: Dict[str, List[Dict[str, Any]]] = {}
        for row in data:
            if not isinstance(row, dict):
                continue
            key = self._make_index_key(row, join_keys)
            index.setdefault(key, []).append(row)
        return index

    @staticmethod
    def _make_index_key(row: Dict[str, Any], join_keys: List[str]) -> str:
        """根据 join_keys 生成索引键字符串（支持多字段）。

        使用 '||' 作为字段分隔符以避免歧义；缺失字段以空串占位。
        """
        parts: List[str] = []
        for k in join_keys:
            v = row.get(k)
            parts.append("" if v is None else str(v))
        return "||".join(parts)

    def _check_chunk(
        self,
        party_a_chunk: List[Dict[str, Any]],
        party_b_index: Dict[str, List[Dict[str, Any]]],
        rule: Rule,
        join_keys: List[str],
        field_a: str,
        field_b: str,
        expr: str,
        severity: str,
        matched_b_ids: set,
    ) -> List[Violation]:
        """处理一块 party_a 数据，返回该块的 Violation 列表。

        Args:
            party_a_chunk: party_a 的一块行数据
            party_b_index: 乙方索引（_build_index 产物）
            rule: 规则对象
            join_keys: 对齐键
            field_a / field_b: 比较字段名
            expr: 校验表达式
            severity: 违规严重度
            matched_b_ids: 已匹配过的乙方行 id 集合（会被本方法更新）

        Returns:
            该块的 Violation 列表
        """
        violations: List[Violation] = []
        for idx, a_row in enumerate(party_a_chunk):
            if not isinstance(a_row, dict):
                continue
            key_str = self._make_index_key(a_row, join_keys)
            key_tuple = tuple(a_row.get(k) for k in join_keys)
            b_rows_matched = party_b_index.get(key_str)
            if not b_rows_matched:
                # 乙方缺失该对齐键 → 缺失告警
                violations.append(self._make_missing_violation(
                    rule, key_tuple, join_keys, a_row, side="party_b"
                ))
                continue

            # 一对多匹配：对每个乙方匹配行执行校验
            for b_row in b_rows_matched:
                matched_b_ids.add(id(b_row))
                va = a_row.get(field_a)
                vb = b_row.get(field_b)
                # 合并双方字段到 context
                context: Dict[str, Any] = {}
                context.update(a_row)
                context.update(b_row)
                context["field_a"] = va
                context["field_b"] = vb
                context["join_key_value"] = " / ".join(str(k) for k in key_tuple)
                # 若 join_key 是单一 pile_no，则填充 pile_no 便于模板渲染
                if len(join_keys) == 1 and join_keys[0] == "pile_no":
                    context.setdefault("pile_no", key_tuple[0])
                # 注入偏差百分比
                self._inject_deviation(context, va, vb)
                # 求值
                passed = self.evaluator.evaluate(expr, context) if expr else True
                if not passed:
                    error_msg = self.evaluator.render_template(rule.error_template, context)
                    violations.append(Violation(
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        level=rule.level,
                        scope=rule.scope,
                        severity=severity,
                        row_index=idx,
                        error_message=error_msg,
                        context=self._snapshot(context),
                        remediation=rule.remediation,
                    ))
        return violations

    @staticmethod
    def _inject_deviation(context: Dict[str, Any], va: Any, vb: Any) -> None:
        """计算并注入 deviation 字段（百分比偏差）。"""
        try:
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                denom = max(abs(va), abs(vb))
                if denom == 0:
                    context.setdefault("deviation", 0.0)
                else:
                    dev = abs(va - vb) / denom * 100
                    context.setdefault("deviation", round(dev, 2))
        except Exception:
            pass

    @staticmethod
    def _make_missing_violation(
        rule: Rule,
        key: Tuple,
        join_keys: List[str],
        row: Dict[str, Any],
        side: str,
    ) -> Violation:
        """生成缺失对齐键的告警 Violation（severity 较低）。"""
        key_str = " / ".join(str(k) for k in key)
        side_label = {"party_a": "甲方", "party_b": "乙方"}.get(side, side)
        msg = f"对齐键 [{key_str}] 在 {side_label} 数据中缺失（join_key={join_keys}）"
        snap: Dict[str, Any] = {}
        for k, v in row.items():
            try:
                json.dumps(v, ensure_ascii=False)
                snap[k] = v
            except (TypeError, ValueError):
                snap[k] = str(v)
        return Violation(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            level=rule.level,
            scope=rule.scope,
            severity=SEVERITY_BEST,  # 缺失告警，severity 较低
            row_index=None,
            error_message=msg,
            context={"join_key_value": key_str, "available_row": snap},
            remediation=rule.remediation,
        )

    @staticmethod
    def _snapshot(context: Dict[str, Any]) -> Dict[str, Any]:
        """构造可 JSON 序列化的数据快照。"""
        snap: Dict[str, Any] = {}
        for k, v in context.items():
            try:
                json.dumps(v, ensure_ascii=False)
                snap[k] = v
            except (TypeError, ValueError):
                snap[k] = str(v)
        return snap


# ========== 7. ViolationReporter ==========
class ViolationReporter:
    """汇总违规为标准化报告，并兼容现有审核系统的 findings 格式。"""

    def report(self, violations: List[Violation]) -> dict:
        """汇总为标准化报告。

        输出结构：
            {"total": N,
             "by_level":     {"L1-IRON": x, "L2-LOGIC": y, "L3-BUSINESS": z},
             "by_severity":  {"Fatal": a, "Sanity Check": b, "Best Practice": c},
             "violations":   [...]}
        """
        by_level: Dict[str, int] = {LEVEL_L1: 0, LEVEL_L2: 0, LEVEL_L3: 0}
        by_severity: Dict[str, int] = {
            SEVERITY_FATAL: 0, SEVERITY_SANITY: 0, SEVERITY_BEST: 0,
        }
        for v in violations:
            by_level[v.level] = by_level.get(v.level, 0) + 1
            by_severity[v.severity] = by_severity.get(v.severity, 0) + 1
        return {
            "total": len(violations),
            "by_level": by_level,
            "by_severity": by_severity,
            "violations": [self._violation_to_dict(v) for v in violations],
        }

    def to_audit_findings(self, violations: List[Violation]) -> List[dict]:
        """转换为现有审核系统兼容的 findings 格式。

        映射规则：
          - Fatal         → result="fail"
          - Sanity Check  → result="suspicious"
          - Best Practice → result="pass"（提示性警告，不影响合规判定）
        """
        findings: List[dict] = []
        for v in violations:
            if v.severity == SEVERITY_FATAL:
                result = "fail"
            elif v.severity == SEVERITY_SANITY:
                result = "suspicious"
            else:
                result = "pass"
            findings.append({
                "rule_id": v.rule_id,
                "rule_name": v.rule_name,
                "level": v.level,
                "scope": v.scope,
                "severity": v.severity,
                "result": result,
                "row_index": v.row_index,
                "finding": v.error_message,
                "evidence": v.context,
                "remediation": v.remediation or "",
            })
        return findings

    @staticmethod
    def _violation_to_dict(v: Violation) -> dict:
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


# ========== 自检入口 ==========
def main() -> int:
    """自检：加载规则、打印摘要。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    skill_dir = Path(__file__).resolve().parent.parent
    rules_dir = skill_dir / "rules"

    loader = RuleLoader()
    rules = loader.load_all(rules_dir)
    print(f"加载规则数: {len(rules)}")
    for r in rules:
        print(f"  - {r.rule_id} | {r.name} | {r.level} | {r.scope} | {r.status}")

    active = loader.load_active(rules_dir)
    print(f"\nactive 规则数: {len(active)}")

    matcher = RuleMatcher()
    matched = matcher.match_by_doc_type(rules, "碎石桩施工记录")
    print(f"\n匹配 doc_type=碎石桩施工记录: {len(matched)} 条")
    for r in matched:
        print(f"  - {r.rule_id}")

    cross_unit = matcher.match_cross_unit(rules, ["监理旁站记录", "碎石桩施工记录"])
    print(f"匹配 cross_unit: {len(cross_unit)} 条")
    for r in cross_unit:
        print(f"  - {r.rule_id}")

    # 表达式求值示例
    evaluator = ExpressionEvaluator()
    print("\n表达式求值示例:")
    print(f"  abs(13.7 - (2103.7 - 2090.0)) <= 0.1 → "
          f"{evaluator.evaluate('abs(实长 - (桩顶高程 - 桩底高程)) <= 0.1', {'实长': 13.7, '桩顶高程': 2103.7, '桩底高程': 2090.0})}")
    print(f"  abs(9.0 - (2103.7 - 2090.0)) <= 0.1  → "
          f"{evaluator.evaluate('abs(实长 - (桩顶高程 - 桩底高程)) <= 0.1', {'实长': 9.0, '桩顶高程': 2103.7, '桩底高程': 2090.0})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
