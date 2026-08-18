"""
数据质量检测脚本（data_quality_check.py）
============================================

在规范对账之前，对 OCR 提取的表格数据做 4 类检测：
  1. DQ-REPEAT — 重复值模式（造假检测）
  2. DQ-JUMP   — 突变检测（断崖下跌）
  3. DQ-ALTER  — 涂改痕迹检测（逻辑层面）
  4. DQ-SELF   — 数据自洽校验（行数/桩号/桩长/充盈系数）

使用方式：
    python data_quality_check.py <数据JSON文件>
    python data_quality_check.py --help

也可以被 import 使用：
    from data_quality_check import DataQualityChecker, check

输入 JSON 格式见 --help 或本文件末尾的示例。
"""

import sys
import json
import argparse
import math
import re
from pathlib import Path
from typing import Any, Optional

# ========== 字段名归一化（英文→中文）==========
# 从 rule_engine 导入 FIELD_ALIAS_MAP，构建反向映射
# 统一用中文字段名做阈值查表和豁免判断，消除双写
_REVERSE_ALIAS_MAP: dict[str, str] = {}
try:
    try:
        from rule_engine import FIELD_ALIAS_MAP
    except ImportError:
        from .rule_engine import FIELD_ALIAS_MAP
    for cn_name, en_slot in FIELD_ALIAS_MAP.items():
        # 多个中文名映射到同一英文槽位时，保留第一个（最常用）
        if en_slot not in _REVERSE_ALIAS_MAP:
            _REVERSE_ALIAS_MAP[en_slot] = cn_name
except ImportError:
    pass


def _normalize_col_name(name: str) -> str:
    """将英文字段名映射回中文，未命中则原样返回"""
    return _REVERSE_ALIAS_MAP.get(name, name)


# ========== 豁免列配置（仅中文，英文通过归一化自动覆盖）==========
EXEMPT_COLUMNS_DEFAULT = {
    "桩径", "设计桩长", "密实电流", "表格代号", "工程名称",
}
EXEMPT_COLUMNS_BY_DOC = {
    "碎石桩施工记录": {"桩径", "设计桩长", "密实电流"},
    "DDC桩施工记录": {"桩径", "设计桩长", "夯击能"},
    "混凝土浇筑记录": {"设计强度等级", "配合比编号"},
    "检验批质量验收记录": {"检验批编号"},
}

# ========== 突变阈值（仅中文，英文通过归一化自动覆盖）==========
JUMP_THRESHOLDS = {
    "实长": 0.30,
    "灌入量": 0.30,
    "反插次数": 0.30,
    "充盈系数": 0.20,
    "竖直度": 0.20,
}


class DataQualityChecker:
    """数据质量检测器"""

    def __init__(self, data: dict):
        self.data = data
        # 优先读 structured_rows，回退到 rows（向后兼容）
        self.rows = data.get("structured_rows") or data.get("rows", [])
        self.doc_type = data.get("doc_type", "")
        self.n_rows = len(self.rows)
        self.warnings: list[dict] = []

        # 数据契约感知（v9.5）：schema_status + 未解析行统计，供领域检查开关
        self.schema_status = data.get("schema_status", "")
        self._unparsed_count = 0
        for r in self.rows:
            if isinstance(r, dict) and r.get("parsed") is False:
                self._unparsed_count += 1
        self._consumable_rows = [r for r in self.rows if isinstance(r, dict) and r.get("parsed") is not False]

        # 从 rows 中提取各列数据（字段名归一化为中文）
        self.columns: dict[str, list] = {}
        self._build_columns()

    def _build_columns(self):
        """从 rows 构建列数据，字段名统一归一化为中文"""
        if not self.rows:
            return
        for row in self.rows:
            for key, val in row.items():
                cn_key = _normalize_col_name(key)
                if cn_key not in self.columns:
                    self.columns[cn_key] = []
                self.columns[cn_key].append(val)

    def _is_exempt(self, col_name: str) -> bool:
        """判断某列是否豁免"""
        if col_name in EXEMPT_COLUMNS_DEFAULT:
            return True
        doc_exempt = EXEMPT_COLUMNS_BY_DOC.get(self.doc_type, set())
        if col_name in doc_exempt:
            return True
        return False

    # ========== 1. 行数自检 ==========
    def check_row_count(self, expected: Optional[int] = None) -> list[dict]:
        """检查识别行数是否与实际一致"""
        w = []
        actual = self.n_rows
        if expected is not None and actual != expected:
            w.append({
                "code": "DQ-SELF-ROW-01",
                "severity": "error",
                "message": f"行数不匹配：识别到 {actual} 行，实际 {expected} 行",
                "detail": f"可能漏行或 OCR 识别错误，必须重新提取",
                "expected": expected,
                "actual": actual,
            })
        elif actual == 0:
            w.append({
                "code": "DQ-SELF-ROW-02",
                "severity": "error",
                "message": "未识别到任何数据行",
                "detail": "OCR 可能完全失败，需检查扫描件质量或重新提取",
            })
        return w

    # ========== 2. 桩号总数校验（v2.0：不强制连号） ==========
    def check_pile_continuity(
        self,
        col_name: str = "桩号",
        expected_total: Optional[int] = None,
    ) -> list[dict]:
        """
        检查桩号总数和重复号（v2.0 改版）。

        桩号顺序按现场施工顺序拟定，不强制连号。只检查：
        1. 总数是否与设计总桩数一致（如提供 expected_total）
        2. 是否有重复桩号

        旧版检查"连续递减"已废弃——现场施工顺序不等于桩号顺序。
        """
        w = []
        pile_nos = self.columns.get(col_name, [])
        if not pile_nos:
            return w

        # 尝试解析桩号（如 Z420 → 420）
        parsed = []
        for pn in pile_nos:
            try:
                num = int("".join(c for c in str(pn) if c.isdigit()))
                parsed.append((str(pn).strip(), num))
            except ValueError:
                w.append({
                    "code": "DQ-SELF-PILE-01",
                    "severity": "warning",
                    "message": f"桩号格式无法解析：{pn}",
                    "detail": "无法验证桩号总数",
                })
                return w

        # 检查重复桩号
        seen = {}
        for pn_str, num in parsed:
            if pn_str in seen:
                w.append({
                    "code": "DQ-SELF-PILE-02",
                    "severity": "warning",
                    "message": f"桩号重复：{pn_str} 出现多次",
                    "detail": "可能为重复记录或 OCR 误读，需核实",
                })
            else:
                seen[pn_str] = True

        # 检查总数（如提供期望值）
        if expected_total is not None:
            actual_total = len(parsed)
            if actual_total != expected_total:
                w.append({
                    "code": "DQ-SELF-PILE-03",
                    "severity": "error" if abs(actual_total - expected_total) > 5 else "warning",
                    "message": f"桩号总数不匹配：识别到 {actual_total} 根，设计 {expected_total} 根",
                    "detail": f"差值 {actual_total - expected_total} 根，需核实是否有缺桩或漏录",
                    "actual": actual_total,
                    "expected": expected_total,
                })

        return w

    # ========== 3. 桩长自洽 ==========
    def check_length_consistency(
        self,
        actual_len_col: str = "actual_length",
        top_elev_col: str = "top_elev",
        bottom_elev_col: str = "bottom_elev",
        tolerance: float = 0.1,
    ) -> list[dict]:
        """检查桩长 = 桩顶高程 - 桩底高程"""
        w = []
        actuals = self.columns.get(actual_len_col, [])
        tops = self.columns.get(top_elev_col, [])
        bottoms = self.columns.get(bottom_elev_col, [])

        if not (actuals and tops and bottoms):
            return w

        n = min(len(actuals), len(tops), len(bottoms))
        for i in range(n):
            if any(v is None for v in [actuals[i], tops[i], bottoms[i]]):
                continue
            calculated = tops[i] - bottoms[i]
            diff = abs(actuals[i] - calculated)
            if diff > tolerance:
                w.append({
                    "code": "DQ-SELF-LEN-01",
                    "severity": "error",
                    "message": (
                        f"第 {i+1} 行桩长自洽失败："
                        f"记录值 {actuals[i]}m ≠ 计算值 {calculated:.2f}m "
                        f"（{tops[i]} - {bottoms[i]}），偏差 {diff:.2f}m"
                    ),
                    "detail": "数据错误或 OCR 识别错误，需人工复核",
                    "row": i + 1,
                    "recorded": actuals[i],
                    "calculated": round(calculated, 2),
                    "diff": round(diff, 2),
                })
        return w

    # ========== 3.5 列错位兜底校验（v8.9） ==========
    def check_column_shift(
        self,
        numeric_columns: tuple = ("桩径", "桩底高程", "桩顶高程", "实长", "密实电流", "反插次数", "灌入量", "充盈系数", "竖直度"),
        time_columns: tuple = ("沉管时间", "拔管时间", "开始时间", "结束时间"),
        tolerance: float = 0.1,
    ) -> list[dict]:
        """审核阶段列级兜底校验。

        对每行检查:
          - 数值列必须为数值（空值不算，因可能确实缺项）
          - 时间列必须为时间格式（HH:MM / HH.MM / HH;MM / HH-MM）
          - 数学链：实长 ≈ 桩顶高程 - 桩底高程
        返回整表列错位告警（含错位率汇总），与 build_foundation 的
        validate_structured_rows 形成双保险。
        """
        w = []
        if not self.rows:
            return w

        def _is_num(v) -> bool:
            return isinstance(v, (int, float)) and not isinstance(v, bool)

        def _is_time_str(v) -> bool:
            return (
                isinstance(v, str)
                and re.match(r"^\d{1,2}[:;.\-]\d{2}", v.strip()) is not None
            )

        def _col_val(col: str, i: int):
            vals = self.columns.get(col, [])
            return vals[i] if i < len(vals) else None

        suspect_rows: list[int] = []
        for i in range(len(self.rows)):
            row_issues: list[str] = []
            # 数值列
            for col in numeric_columns:
                v = _col_val(col, i)
                if v is None:
                    continue
                if not _is_num(v):
                    row_issues.append(f"{col}={v!r} 非数值")
            # 时间列
            for col in time_columns:
                v = _col_val(col, i)
                if v is not None and not _is_time_str(v):
                    row_issues.append(f"{col}={v!r} 非时间格式")
            # 数学链：实长 = 顶高程 - 底高程
            actual, top, bottom = (_col_val("实长", i), _col_val("桩顶高程", i),
                                   _col_val("桩底高程", i))
            if all(_is_num(x) for x in (actual, top, bottom)):
                if abs(actual - (top - bottom)) > tolerance:
                    row_issues.append(f"实长={actual} 与 顶高程-底高程={top - bottom:.2f} 偏差>0.1")

            if row_issues:
                suspect_rows.append(i + 1)
                w.append({
                    "code": "DQ-SHIFT-01",
                    "severity": "high",
                    "message": f"第 {i+1} 行列错位：{'；'.join(row_issues)}",
                    "detail": "列值类型不符或数学链断裂，疑似 OCR 列错位，需人工复核",
                    "row": i + 1,
                    "issues": row_issues,
                })

        total = len(self.rows)
        ratio = len(suspect_rows) / total if total else 0
        if suspect_rows:
            # v9.2: 错位率高风险阈值收紧至 5%（用户要求），≥5% 即强制人工复核
            risk = "high" if ratio >= 0.05 else ("medium" if ratio >= 0.02 else "low")
            w.append({
                "code": "DQ-SHIFT-SUM",
                "severity": "high" if risk == "high" else "warning",
                "message": (
                    f"整表列错位风险 {risk}：{len(suspect_rows)}/{total} 行错位"
                    f"（{ratio:.0%}）"
                ),
                "detail": "错位率 ≥5% 应强制 needs_review 并人工复核",
                "suspect_rows": suspect_rows,
                "total_rows": total,
                "ratio": round(ratio, 2),
                "risk": risk,
            })
        return w

    # ========== 4. 充盈系数自洽 ==========
    def check_filling_coeff_consistency(
        self,
        filling_coeff_col: str = "filling_coeff",
        volume_col: str = "volume",
        diameter_col: str = "diameter",
        actual_len_col: str = "actual_length",
        tolerance: float = 0.15,
    ) -> list[dict]:
        """检查充盈系数 = 灌入量 / (π × (桩径/2)² × 实长)"""
        w = []
        coeffs = self.columns.get(filling_coeff_col, [])
        volumes = self.columns.get(volume_col, [])
        diameters = self.columns.get(diameter_col, [])
        lengths = self.columns.get(actual_len_col, [])

        if not (coeffs and volumes and diameters and lengths):
            return w

        n = min(len(coeffs), len(volumes), len(diameters), len(lengths))
        for i in range(n):
            # 跳过 null 值（AI 视觉提取时部分列可能缺失）
            if any(v is None for v in [coeffs[i], volumes[i], diameters[i], lengths[i]]):
                continue
            radius = diameters[i] / 2.0
            theory_vol = math.pi * radius * radius * lengths[i]
            if theory_vol == 0:
                continue
            calculated = volumes[i] / theory_vol
            diff = abs(coeffs[i] - calculated)
            if diff > tolerance:
                w.append({
                    "code": "DQ-SELF-FC-01",
                    "severity": "warning",
                    "message": (
                        f"第 {i+1} 行充盈系数自洽失败："
                        f"记录值 {coeffs[i]} ≠ 计算值 {calculated:.2f}"
                        f"（{volumes[i]} / (π×{radius}²×{lengths[i]})），偏差 {diff:.2f}"
                    ),
                    "detail": "可能为涂改或记录错误",
                    "row": i + 1,
                    "recorded": coeffs[i],
                    "calculated": round(calculated, 2),
                    "diff": round(diff, 2),
                })
        return w

    # ========== 5. 重复值模式检测 ==========
    def check_repeat_pattern(self) -> list[dict]:
        """检测数值列中的重复值模式（造假检测）"""
        w = []
        for col_name, values in self.columns.items():
            if self._is_exempt(col_name):
                continue
            # 只检测数值列
            numeric_vals = [v for v in values if isinstance(v, (int, float))]
            if len(numeric_vals) < 4:
                continue

            unique_vals = list(set(numeric_vals))
            n_unique = len(unique_vals)
            n_total = len(numeric_vals)
            unique_ratio = n_unique / n_total

            # 检测交替模式
            is_alternating = self._detect_alternating(numeric_vals)

            if n_unique == 2 and is_alternating:
                w.append({
                    "code": "DQ-REPEAT-01",
                    "severity": "high",
                    "message": (
                        f"列「{col_name}」：仅 2 个值交替出现 "
                        f"（{unique_vals}），数据造假嫌疑"
                    ),
                    "detail": (
                        f"{n_total} 个样本只有 2 个值且交替循环，"
                        f"是典型手工编造特征，建议现场取芯验证"
                    ),
                    "column": col_name,
                    "unique_values": unique_vals,
                    "pattern": "alternating",
                })
            elif n_unique == 2 and not is_alternating:
                w.append({
                    "code": "DQ-REPEAT-02",
                    "severity": "medium",
                    "message": f"列「{col_name}」：仅 2 个值（{unique_vals}），数据异常",
                    "detail": "值分布过于集中，需结合工序判断是否合理",
                    "column": col_name,
                    "unique_values": unique_vals,
                    "pattern": "clustered",
                })
            elif n_unique == 1:
                w.append({
                    "code": "DQ-REPEAT-03",
                    "severity": "medium",
                    "message": f"列「{col_name}」：全部相同（{unique_vals[0]}），可能为一次填入",
                    "detail": "需结合工序判断是否合理，如为实测值则不正常",
                    "column": col_name,
                    "unique_values": unique_vals,
                    "pattern": "all_same",
                })
            elif unique_ratio < 0.30:
                w.append({
                    "code": "DQ-REPEAT-04",
                    "severity": "medium",
                    "message": (
                        f"列「{col_name}」：值分布过于集中"
                        f"（{n_unique}/{n_total}，占比 {unique_ratio:.0%}）"
                    ),
                    "detail": "数据异常——值分布过于集中，需人工判断",
                    "column": col_name,
                    "unique_values": unique_vals,
                    "unique_ratio": round(unique_ratio, 2),
                })
        return w

    @staticmethod
    def _detect_alternating(values: list) -> bool:
        """检测是否交替模式 (A→B→A→B→A→B)"""
        if len(values) < 4:
            return False
        unique = list(set(values))
        if len(unique) != 2:
            return False
        a, b = unique
        # 检查 4 个连续值是否交替
        for i in range(len(values) - 3):
            window = values[i : i + 4]
            if window == [a, b, a, b] or window == [b, a, b, a]:
                return True
        return False

    # ========== 6. 突变检测（v2.0：含致岩豁免） ==========
    def check_jump(self, remark_col: str = "备注") -> list[dict]:
        """检测数值列的突变

        v2.0 新增：
        - 致岩/入岩豁免：备注列含"致岩""入岩"等关键词时，桩长突变不报
        - 设计变更豁免：备注列含"变更"关键词时，不报

        注意：已被 DQ-REPEAT-01（交替模式）标记的列，不再重复报告突变——
        交替模式本身已经解释了数据波动，逐行突变告警是冗余的。
        """
        # 先收集已被交替模式标记的列名
        alternating_cols = {
            w["column"]
            for w in self.warnings
            if w["code"] == "DQ-REPEAT-01" and w.get("pattern") == "alternating"
        }

        # 获取备注列数据
        remarks = self.columns.get(remark_col, [])

        # 致岩/入岩/变更关键词
        exempt_keywords = ["致岩", "入岩", "已入岩", "岩层", "变更", "设计变更", "签证"]

        w = []
        for col_name, values in self.columns.items():
            if self._is_exempt(col_name):
                continue
            if col_name in ("桩号", remark_col):
                continue

            # 跳过已被交替模式标记的列
            if col_name in alternating_cols:
                continue

            numeric_vals = [v for v in values if isinstance(v, (int, float))]
            if len(numeric_vals) < 3:
                continue

            threshold = JUMP_THRESHOLDS.get(col_name, 0.30)

            for i in range(1, len(numeric_vals)):
                prev = numeric_vals[i - 1]
                curr = numeric_vals[i]
                if prev == 0:
                    continue
                change_rate = abs(curr - prev) / abs(prev)
                if change_rate >= threshold:
                    # 检查备注列是否有致岩/入岩/变更等豁免关键词
                    remark = str(remarks[i]) if i < len(remarks) and remarks[i] else ""
                    is_exempt = any(kw in remark for kw in exempt_keywords)

                    if is_exempt:
                        # 致岩桩或设计变更，桩长可以不同于设计值，不报突变
                        continue

                    direction = "下降" if curr < prev else "上升"
                    w.append({
                        "code": "DQ-JUMP-01",
                        "severity": "high" if change_rate >= 0.50 else "medium",
                        "message": (
                            f"列「{col_name}」突变：第 {i}→{i+1} 行，"
                            f"{prev} → {curr}，{direction} {change_rate:.0%}（阈值 {threshold:.0%}）"
                        ),
                        "detail": (
                            "需说明原因：地层变化？设备故障？停工？变更？"
                            f"（备注列无致岩/变更说明）"
                        ),
                        "column": col_name,
                        "from_row": i,
                        "to_row": i + 1,
                        "from_value": prev,
                        "to_value": curr,
                        "change_rate": round(change_rate, 4),
                    })
        return w

    # ========== 7. 时间连续性 ==========
    def check_time_continuity(
        self,
        start_time_col: str = "开始时间",
        end_time_col: str = "结束时间",
    ) -> list[dict]:
        """检查后行开始时间 ≥ 前行结束时间"""
        w = []
        starts = self.columns.get(start_time_col, [])
        ends = self.columns.get(end_time_col, [])

        if not (starts and ends):
            return w

        n = min(len(starts), len(ends))
        for i in range(1, n):
            # 简单比较：如果都是 "HH:MM" 格式
            try:
                if isinstance(starts[i], str) and isinstance(ends[i - 1], str):
                    if starts[i] < ends[i - 1]:
                        w.append({
                            "code": "DQ-SELF-TIME-01",
                            "severity": "warning",
                            "message": (
                                f"时间倒挂：第 {i+1} 行开始时间 {starts[i]} "
                                f"< 第 {i} 行结束时间 {ends[i-1]}"
                            ),
                            "detail": "可能存在时间倒签或记录错误",
                        })
            except (TypeError, ValueError):
                pass
        return w

    # ========== 8. 行级推断规则加载 ==========
    def _load_inference_rules(self) -> list[dict]:
        """从 inference_rules.json 加载推断规则配置"""
        skill_dir = Path(__file__).resolve().parent.parent
        rules_path = skill_dir / "rules" / "inference_rules.json"
        if not rules_path.exists():
            return []
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            return config.get("rules", [])
        except (json.JSONDecodeError, OSError):
            return []

    # ========== 9. 单条推断规则应用（动态计算） ==========
    def _apply_rule(self, rule: dict, row: dict, row_idx: int,
                    current_inferred: dict) -> dict | None:
        """根据规则配置动态计算推断值，支持 cascade_penalty 级联扣减。

        Args:
            rule: 规则配置 dict（含 id, formula, base_confidence, cascade_penalty 等）
            row: 当前行数据 dict
            row_idx: 行号（1-based），仅用于错误日志
            current_inferred: 当前行已推断的字段 dict（用于检测级联）

        Returns:
            { field_name: { value, confidence, source, reason } } 或 None
        """
        formula = rule.get("formula", "")
        if "=" not in formula:
            return None

        target = formula.split("=", 1)[0].strip()
        expr = formula.split("=", 1)[1].strip()

        # 目标字段已有值，跳过
        if row.get(target) is not None:
            return None

        # 已知字段名集合，用于从公式中提取源字段
        KNOWN_FIELDS = {
            "actual_length", "top_elev", "bottom_elev", "filling_coeff",
            "volume", "diameter", "duration", "sink_time", "pull_time",
            "thickness",
        }

        # 提取源字段（出现在表达式中且不等于目标字段）
        source_fields = [f for f in KNOWN_FIELDS if f in expr and f != target]
        if not source_fields:
            return None

        # 合并行内已有推断值 + 当前运行已推断值（用于级联检测和取值）
        row_inferred: dict = {}
        row_inferred_field = row.get("inferred")
        if isinstance(row_inferred_field, dict):
            row_inferred.update(row_inferred_field)
        row_inferred.update(current_inferred)

        # 检查所有源字段均为非空数值（支持从 row_inferred 取级联值）
        source_values: dict[str, float] = {}
        for f in source_fields:
            v = row.get(f)
            if v is None and f in row_inferred:
                # 级联场景：取行内已推断的值
                v = row_inferred[f].get("value") if isinstance(row_inferred[f], dict) else None
            if v is None or not isinstance(v, (int, float)):
                return None
            source_values[f] = v

        # 根据公式模式计算推断值
        try:
            if "π" in expr:
                # 含 π 的公式：充盈系数 / 灌入量计算
                r = source_values.get("diameter", 0) / 2.0
                theory = math.pi * r * r * source_values.get("actual_length", 0)
                if theory == 0:
                    return None
                if target == "filling_coeff":
                    value = round(source_values["volume"] / theory, 2)
                elif target == "volume":
                    value = round(source_values["filling_coeff"] * theory, 2)
                else:
                    return None
            elif "+" in expr:
                # 加法公式
                value = round(sum(source_values.values()), 2)
            elif "-" in expr:
                # 减法公式：按字段在表达式中的出现顺序确定先后
                field_positions = [(expr.index(f), f) for f in source_fields]
                field_positions.sort()
                ordered = [f for _, f in field_positions]
                if len(ordered) == 2:
                    value = round(source_values[ordered[0]] - source_values[ordered[1]], 2)
                else:
                    return None
            else:
                return None
        except (TypeError, ValueError, ZeroDivisionError, KeyError):
            return None

        # 判断是否级联推断（源字段中混有行内已有推断值或当前运行已推断的值）
        has_cascade = any(f in row_inferred for f in source_fields)
        base_conf = rule.get("base_confidence", 0.85)
        cascade_penalty = rule.get("cascade_penalty", 0.30)
        confidence = base_conf - (cascade_penalty if has_cascade else 0)
        confidence = max(0.0, min(1.0, round(confidence, 2)))

        # 构建中文描述
        def _cn(field: str) -> str:
            return _REVERSE_ALIAS_MAP.get(field, field)

        source_desc = "、".join(
            f"{_cn(f)}({source_values[f]})" for f in source_fields
        )

        # 生成 reason
        reason = f"{_cn(target)}缺失，由{source_desc}推算为{value}"
        if has_cascade:
            reason += "（含级联推断）"

        return {
            target: {
                "value": value,
                "confidence": confidence,
                "source": formula,
                "reason": reason,
            }
        }

    # ========== 10. 行级推断建议值生成 ==========
    def infer_values(self) -> dict:
        """对缺失值做数学关系推断，返回行级 inferred 建议值。

        推断规则（按优先级）：
          1. actual_length = top_elev - bottom_elev（桩顶-桩底→实长）
          2. top_elev = bottom_elev + actual_length（桩底+实长→桩顶）
          3. bottom_elev = top_elev - actual_length（桩顶-实长→桩底）
          4. filling_coeff = volume / (π × (diameter/2)² × actual_length)（灌入量→充盈系数）
          5. volume = filling_coeff × π × (diameter/2)² × actual_length（充盈系数→灌入量）

        置信度标定：
          - ≥0.95: 源字段均为确认值（非推断值），数学关系直接
          - 0.80-0.94: 源字段均为确认值，但涉及 π/平方等含入误差
          - 0.50-0.79: 源字段包含推断值（级联推断），仅供参考
          - <0.50: 不输出

        输出格式：
          {
            "row_inferred": {                # 行号(1-based) → 推断字段 dict
              "row_index": {
                "field_name": {
                  "value": <推断值>,
                  "confidence": <0~1>,
                  "source": "桩顶高程 - 桩底高程",
                  "reason": "实长缺失，由桩顶高程(2103.72) - 桩底高程(2089.98) 推算"
                }
              }
            },
            "summary": {
              "total_rows": N,
              "rows_with_inferred": N,
              "total_inferred_fields": N
            }
          }
        """
        # 加载 inference_rules.json 规则配置
        rules = self._load_inference_rules()

        result: dict[str, dict] = {}
        total_inferred = 0
        rows_with_inferred = 0

        for i, row in enumerate(self.rows):
            if not isinstance(row, dict):
                continue
            inferred: dict[str, dict] = {}
            row_idx = i + 1  # 1-based

            # 按顺序应用每条规则
            for rule in rules:
                rule_result = self._apply_rule(rule, row, row_idx, inferred)
                if rule_result is not None:
                    inferred.update(rule_result)

            if inferred:
                result[str(row_idx)] = inferred
                total_inferred += len(inferred)
                rows_with_inferred += 1

        return {
            "row_inferred": result,
            "summary": {
                "total_rows": len(self.rows),
                "rows_with_inferred": rows_with_inferred,
                "total_inferred_fields": total_inferred,
            },
        }

    # ========== 主入口 ==========
    def run_all(
        self,
        expected_rows: Optional[int] = None,
        expected_pile_total: Optional[int] = None,
    ) -> dict:
        """运行全部检测，返回结果

        Args:
            expected_rows: 期望的数据行数（用于行数自检）
            expected_pile_total: 设计总桩数（用于桩号总数校验，v2.0新增）
        """
        self.warnings = []

        # 1. 硬门槛：行数自检
        row_warnings = self.check_row_count(expected_rows)
        self.warnings.extend(row_warnings)

        # 如果有行数错误，跳过后续检测（数据不可靠）
        has_row_error = any(w["severity"] == "error" for w in row_warnings)
        if has_row_error:
            return self._build_result()

        # 数据契约感知：unknown_domain / 未解析行 → 仅执行通用检查，并显式提示
        if self.schema_status == "unknown_domain" or self._unparsed_count == self.n_rows:
            self.warnings.append({
                "code": "DQ-SCHEMA-UNKNOWN",
                "severity": "warning",
                "message": "表格 schema 未确认（unknown_domain）或全部为未解析行，跳过领域自洽检查",
                "detail": "请人工确认列语义后复用 table-schemas.json，再执行完整性审核",
            })
        else:
            # 2. 桩号总数校验（v2.0：不强制连号，只查总数和重复号）
            self.warnings.extend(self.check_pile_continuity(expected_total=expected_pile_total))

            # 3. 数据自洽
            self.warnings.extend(self.check_length_consistency())
            self.warnings.extend(self.check_filling_coeff_consistency())
            self.warnings.extend(self.check_time_continuity())

        # 3.5 列错位兜底校验（v8.9）
        self.warnings.extend(self.check_column_shift())

        # 4. 重复值模式
        self.warnings.extend(self.check_repeat_pattern())

        # 5. 突变检测（v2.0：含致岩豁免）
        self.warnings.extend(self.check_jump())

        return self._build_result()

    def _build_result(self) -> dict:
        """构建输出结果"""
        n_high = sum(1 for w in self.warnings if w["severity"] == "high")
        n_medium = sum(1 for w in self.warnings if w["severity"] == "medium")
        n_error = sum(1 for w in self.warnings if w["severity"] == "error")
        n_warning = sum(1 for w in self.warnings if w["severity"] == "warning")

        return {
            "status": "error" if n_error > 0 else ("warning" if self.warnings else "pass"),
            "summary": {
                "total_rows": self.n_rows,
                "total_warnings": len(self.warnings),
                "high": n_high,
                "medium": n_medium,
                "warning": n_warning,
                "error": n_error,
            },
            "warnings": self.warnings,
        }


def check(
    data: dict,
    expected_rows: Optional[int] = None,
    expected_pile_total: Optional[int] = None,
) -> dict:
    """便捷函数：一步完成检测"""
    checker = DataQualityChecker(data)
    return checker.run_all(expected_rows, expected_pile_total)


def infer_values(data: dict) -> dict:
    """便捷函数：一步完成行级推断建议值生成"""
    checker = DataQualityChecker(data)
    return checker.infer_values()


# ========== CLI ==========
def main():
    parser = argparse.ArgumentParser(
        description="数据质量检测脚本 — 在规范对账前先做数据真实性审查",
        epilog="""
输入 JSON 格式示例：
{
  "doc_type": "碎石桩施工记录",
  "rows": [
    {
      "pile_no": "Z420",
      "design_length": 20.0,
      "diameter": 0.6,
      "bottom_elev": 2089.98,
      "top_elev": 2103.68,
      "actual_length": 13.7,
      "current": 160,
      "re_penetration": 19,
      "volume": 5.30,
      "filling_coeff": 1.37,
      "verticality": 0.2,
      "start_time": "00:00",
      "end_time": "00:39"
    }
  ]
}
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", nargs="?", help="输入 JSON 文件路径（不提供则从 stdin 读取）")
    parser.add_argument(
        "--expected-rows", "-n", type=int, default=None,
        help="期望行数（用于行数自检）",
    )
    parser.add_argument(
        "--expected-pile-total", "-p", type=int, default=None,
        help="设计总桩数（用于桩号总数校验，v2.0新增）",
    )
    parser.add_argument(
        "--pretty", action="store_true",
        help="美化输出（带缩进）",
    )
    parser.add_argument(
        "--infer", action="store_true",
        help="生成行级推断建议值（inferred field），输出推断结果 JSON",
    )
    args = parser.parse_args()

    # 读取输入
    if args.input:
        raw = Path(args.input).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()

    data = json.loads(raw)

    # 运行检测
    if args.infer:
        checker = DataQualityChecker(data)
        result = checker.infer_values()
    else:
        result = check(data, args.expected_rows, args.expected_pile_total)

    # 输出
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()