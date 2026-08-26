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
from datetime import date as _date
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


# ========== v9.6 隐患销号：统一谓词 / 归一化 / 白名单（H-1/H-2/H-3）==========
# 原则：一条字段经历 解析→合法性判定→推断→展示 多环节，谓词必须一处定义全链共用，
# 禁止各环节各写各的（曾因此产生"值在库却判非法显示空"的悬空态）。

# 日期标点变体归一表：WPS OCR 手写日期常产出顿号/全角逗号/句点
_DATE_PUNCT_MAP = str.maketrans({"、": ".", "，": ".", "。": ".", "：": ":", "；": ";"})


def normalize_date_punct(s) -> str:
    """日期标点归一化（H-1）：`2026、4.22` → `2026.4.22`。

    所有日期合法性判定（推断触发、pending 生成、展示）必须先过此函数，
    否则顿号变体会被判非法形成悬空态。
    """
    if s is None:
        return ""
    return str(s).translate(_DATE_PUNCT_MAP).strip()


def is_missing(v) -> bool:
    """类缺失谓词（H-3）：None / 空串 / 纯空白 / 纯符号 / 单个乱字 → True。

    管道约定缺失统一为空串 ''（见 Hard Constraints），禁止用 `is not None`
    判定缺失 —— 空串会被误判为"有值"导致数学链推断全灭。
    """
    if v is None:
        return True
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return False
    s = str(v).strip()
    if not s:
        return True
    # 纯符号/标点（无任何字母数字中文），如 `,` `.` `)`
    if not re.search(r"[\u4e00-\u9fff0-9A-Za-z]", s):
        return True
    # 单个汉字：无法构成合法数值/日期/部位，视为乱字（如『了』）
    if len(s) == 1 and re.match(r"[\u4e00-\u9fff]", s):
        return True
    return False


# 部位正规形态：桩型(可选) + 边(可选) + 区号 + 区，如 碎石桩边三区 / DDC桩十二区
_LOC_CANONICAL_RE = re.compile(
    r"^(?:碎石桩|振冲桩|CFG桩|DDC桩|碎石)?(?:边)?[一二三四五六七八九十\d]{1,3}区$"
)
_LOC_KEYWORD_RE = re.compile(r"(碎石|桩)")


def is_legal_loc(value, whitelist=None) -> bool:
    """部位合法性判定（H-2b）：

    - 有区名白名单（用户从图纸提供）→ 必须完全等于白名单项；
    - 无白名单 → 双条件退化：含桩类关键词 **且** 匹配正规区名形态。
      杜绝『碎石机区』『碎石说区』类乱码因子串命中 `.*(碎石|桩)` 蒙混过关。
    """
    if value is None:
        return False
    s = str(value).strip()
    if not s:
        return False
    if whitelist:
        return s in whitelist
    if not _LOC_KEYWORD_RE.search(s):
        return False
    return bool(_LOC_CANONICAL_RE.match(s))


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

# ========== 三重一致性常量（v10.1：表头设计值 vs 分区名 vs 实际数据）==========
# full_text 表头里的设计桩长，如"设计桩长                5m"
_DESIGN_LEN_RE = re.compile(r"设计桩长\s*[:：]?\s*(\d+(?:\.\d+)?)\s*m\b")
# sheet 分区名里的分区桩长，如"MD-X1(8米)" / "MD-X7（8米）"（全半角括号混用）
# 注意必须带"米"字，避免误吞"NB(X1-X3)"这类分区编号
_ZONE_TAG_RE = re.compile(r"[（(]\s*(\d+(?:\.\d+)?)\s*米\s*[)）]")
_DESIGN_DEV_ABS = 0.5   # 设计值 vs 实际 绝对容差（m）
_DESIGN_DEV_REL = 0.2   # 设计值 vs 实际 相对容差（20%）


def _to_float(v):
    """宽松转 float：None/空串/含文字垃圾（如"筑业软件 485…"）一律返回 None。"""
    if v is None:
        return None
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


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
            # v10.2（P10）：底座行值为字符串（Excel 序列化/OCR 文本），
            # 原 isinstance(int/float) 对全字符串数据百分百误报非数值。
            # 改为宽松 float 判定（None/空串/乱码 → False）。
            if isinstance(v, bool):
                return False
            return _to_float(v) is not None

        def _is_time_str(v) -> bool:
            return (
                isinstance(v, str)
                and re.match(r"^\d{1,2}[:;.\-]\d{2}", v.strip()) is not None
            )

        def _col_val(col: str, i: int):
            vals = self.columns.get(col, [])
            # v10.2：缺失列统一 None（_col_val 直接取值，None 即跳过判定）
            return vals[i] if i < len(vals) else None

        suspect_rows: list[int] = []
        for i in range(len(self.rows)):
            row_issues: list[str] = []
            # 数值列（缺失=空串/None 一律跳过，缺失不算错位）
            for col in numeric_columns:
                v = _col_val(col, i)
                if v is None or str(v).strip() == "":
                    continue
                if not _is_num(v):
                    row_issues.append(f"{col}={v!r} 非数值")
            # 时间列（缺失跳过）
            for col in time_columns:
                v = _col_val(col, i)
                if v is None or str(v).strip() == "":
                    continue
                if not _is_time_str(v):
                    row_issues.append(f"{col}={v!r} 非时间格式")
            # 数学链：实长 = 顶高程 - 底高程（转 float 计算，字符串直接相减会 TypeError）
            actual, top, bottom = (_to_float(_col_val("实长", i)),
                                   _to_float(_col_val("桩顶高程", i)),
                                   _to_float(_col_val("桩底高程", i)))
            if all(x is not None for x in (actual, top, bottom)):
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

    # ========== 7.5 三重一致性：表头设计值 vs 分区名 vs 实际数据（v10.1） ==========
    def check_design_zone_consistency(self) -> list[dict]:
        """表头设计桩长 / sheet分区名 / 实际施工桩长 三方对账。

        背景（2026-08-25 实测）：CFG 桩工作簿表头统一写"设计桩长 5m"，
        但 sheet 名自带"(8米)"分区、实际施工大量 7~8m——同一份资料
        两种互斥设计值，结构性矛盾，旧引擎零报警。

        判定用"偏离占比"而非中位数（实测 MD-X1 双峰：5m 群体与 8m 群体
        混存，中位数 5.5 正好卡在两峰之间把矛盾糊平）：
          - error  DQ-DESIGN-ZONE-01：分区名(如8米)对应施工群体占比≥20%
                    且与表头设计值矛盾 → 同表两种互斥设计值，结构性矛盾
          - warning DQ-DESIGN-ZONE-02：无分区名佐证，但≥20%桩长偏离设计值
                    （成片超长/欠长，待现场核实）
          - warning DQ-DESIGN-ZONE-03：仅分区名与表头不符、数据与设计自洽
                    （疑似 sheet 命名笔误）

        数据源：full_text（表头设计值）/ 行数据 table 列（分区名）/ 有效桩长。
        任一来源缺失即跳过，宁缺勿误报。
        """
        w: list[dict] = []
        ft = str(self.data.get("full_text") or "")
        designs = set(_DESIGN_LEN_RE.findall(ft))
        if len(designs) != 1:
            # 无设计值或表内出现多个不同设计值 → 无法对账，跳过
            return w
        design = float(next(iter(designs)))

        tables: dict[str, list] = {}
        for r in self.rows:
            if not isinstance(r, dict):
                continue
            t = str(r.get("table") or r.get("_sheet") or "").strip()
            if t:
                tables.setdefault(t, []).append(r)

        tol = max(_DESIGN_DEV_ABS, _DESIGN_DEV_REL * design)
        for t, rows in tables.items():
            vals = []
            for r in rows:
                for f in ("有效桩长（m）", "有效桩长(m)", "桩深度 （m）", "桩深度(m)"):
                    v = _to_float(r.get(f))
                    if v is not None and v > 0:
                        vals.append(v)
                        break
            if len(vals) < 5:
                continue  # 样本太少，占比不稳
            n = len(vals)
            zm = _ZONE_TAG_RE.search(t)
            zone = float(zm.group(1)) if zm else None

            share_dev = sum(1 for v in vals if abs(v - design) > tol) / n
            share_zone = 0.0
            if zone is not None:
                ztol = max(_DESIGN_DEV_ABS, _DESIGN_DEV_REL * zone)
                share_zone = sum(1 for v in vals if abs(v - zone) <= ztol) / n

            if zone is not None and share_zone >= 0.2 and abs(zone - design) > tol:
                w.append({
                    "code": "DQ-DESIGN-ZONE-01",
                    "severity": "error",
                    "message": (f"表[{t}]表头设计桩长{design:g}m与分区名({zone:g}米)"
                                f"矛盾：{share_zone:.0%}的桩实际按{zone:g}m级施工"),
                    "detail": ("同一记录表存在两种互斥设计值（表头统一值 vs 分区施工群体），"
                               "结构性矛盾，需对照设计文件核实真实设计桩长"),
                })
            elif share_dev >= 0.2:
                w.append({
                    "code": "DQ-DESIGN-ZONE-02",
                    "severity": "warning",
                    "message": (f"表[{t}]{share_dev:.0%}的桩长偏离表头设计值"
                                f"{design:g}m超容差（±{tol:g}m）"),
                    "detail": "存在成片超长/欠长桩，建议核实是模板设计值过期还是施工偏差",
                })
            elif zone is not None and abs(zone - design) > tol:
                w.append({
                    "code": "DQ-DESIGN-ZONE-03",
                    "severity": "warning",
                    "message": (f"表[{t}]分区名({zone:g}米)与表头设计桩长{design:g}m"
                                f"不一致，但实际数据与设计值自洽"),
                    "detail": "疑似 sheet 命名笔误，人工核实分区名即可",
                })
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
        # H-3：类缺失（None/空串/纯符号/单乱字）视为"无值"，必须触发推断；
        #      旧逻辑 `is not None` 会把空串当"已有值"挡死数学链（INF-003/004 全灭）
        if not is_missing(row.get(target)):
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
        # H-3：真实管道值为字符串（如 "2083.70"），须可解析；空串/纯符号按类缺失
        source_values: dict[str, float] = {}
        for f in source_fields:
            v = row.get(f)
            if is_missing(v) and f in row_inferred:
                # 级联场景：取行内已推断的值
                v = row_inferred[f].get("value") if isinstance(row_inferred[f], dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                source_values[f] = float(v)
            elif not is_missing(v):
                try:
                    cleaned = str(v).strip().replace(",", "").replace("，", "")
                    source_values[f] = float(cleaned)
                except ValueError:
                    return None  # 非数值文本（如『了』），源不可信
            else:
                return None

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

    # ========== 文本 / 枚举规则（type=text）==========
    # 只建议不入库：仅当目标字段为空或疑似乱码时触发；置信度封顶 0.70。
    # 产出仅供参考，绝不自动写入 structured_rows，必须经用户确认才落库。
    # 文本规则绝不参与审核判定，仅作为阶段2 Chat-Verify 对话框的建议值提示。

    _DATE_RE = re.compile(r'^(\d{4})\s*[.\-/年]\s*(\d{1,2})\s*[.\-/月]\s*(\d{1,2})')
    # 可读字符集合：中文、数字、常见日期/部位分隔符
    _READABLE_RE = re.compile(r'[\u4e00-\u9fff0-9A-Za-z.\-/:年月日时分◆\-]')

    def _looks_garble(self, s) -> bool:
        """判断取值是否为疑似乱码（可读字符占比过低或含明确乱码符）。"""
        if s is None:
            return False  # None 由调用方单独处理（视为空）
        text = str(s)
        if not text:
            return False  # 空串也已由调用方处理，这里仅对非空判定
        readable = len(self._READABLE_RE.findall(text))
        total = len(text)
        if total == 0:
            return False
        return (readable / total) < 0.5

    def _col_values(self, field: str) -> list:
        """按英文字段名取全列值（字段名归一化为中文）。"""
        cn_key = _normalize_col_name(field)
        vals = self.columns.get(cn_key)
        if vals is None:
            vals = self.columns.get(field)
        return vals or []

    def _compile_legal(self, pattern: Optional[str]) -> Optional[re.Pattern]:
        """把 legal_pattern 编译为正则；空/非法返回 None。"""
        if not pattern:
            return None
        try:
            return re.compile(pattern)
        except re.error:
            return None

    def _apply_text_rule(self, rule: dict, row: dict, row_idx: int) -> dict | None:
        """文本/枚举建议值推断。返回 { field: {value, confidence, source, reason, suggested_only} } 或 None。

        触发判定对齐 pending_verification 的『合法格式』语义：
          - 规则带 legal_pattern 时：值不匹配规范格式（空/乱码/非法）即触发，合法值绝不推断；
          - 规则不带 legal_pattern 时：回退到可读字符占比乱码判定。
        """
        field = rule.get("field", "")
        if not field:
            return None
        raw = row.get(field)
        # H-1：日期类字段判定前先做标点归一化，杜绝顿号变体悬空态
        if field in ("date_raw", "施工日期"):
            raw = normalize_date_punct(raw)
        is_empty = raw is None or str(raw).strip() == ""
        legal_re = self._compile_legal(rule.get("legal_pattern"))

        # 触发判定
        if legal_re is not None:
            if not is_empty and legal_re.match(str(raw).strip()):
                return None  # 合法格式，不推断
        else:
            if not is_empty and not self._looks_garble(raw):
                return None

        strategy = rule.get("strategy", "")
        max_conf = float(rule.get("max_confidence", 0.70))
        base_conf = float(rule.get("base_confidence", 0.65))

        if strategy == "mode_by_row":
            return self._text_mode_by_row(field, row_idx, base_conf, max_conf, legal_re)
        if strategy == "fill_date":
            return self._text_fill_date(field, row_idx, base_conf, max_conf, legal_re)
        return None

    def _row_table(self, row_idx: int):
        """返回 row_idx(1-based) 所属的表号；行不存在或无 table 字段时返回 None。"""
        if not (1 <= row_idx <= len(self.rows)):
            return None
        r = self.rows[row_idx - 1]
        return r.get("table") if isinstance(r, dict) else None

    def _same_table(self, pos: int, table_id) -> bool:
        """pos(1-based) 是否与 table_id 同一表。table_id 为 None（无表字段）时视为同表，向后兼容。"""
        if not (1 <= pos <= len(self.rows)):
            return False
        r = self.rows[pos - 1]
        if not isinstance(r, dict):
            return False
        if table_id is None:
            return True
        return r.get("table") == table_id

    def _text_mode_by_row(self, field, row_idx, base_conf, max_conf,
                          legal_re: Optional[re.Pattern]) -> dict | None:
        """施工部位：同表众数，同表部位唯一值≥2种则退化为同表邻行检索。

        仅以『合法格式』值为参考（legal_re 命中），杜绝用乱码值做推断基底；
        且候选与邻行检索都严格限定在**同一张表**内，杜绝跨表/跨页污染
        （不同表=不同施工部位，跨表抓值会给出误导建议）。
        """
        vals = self._col_values(field)
        if not vals:
            return None
        n = len(vals)
        if not (1 <= row_idx <= n):
            return None
        table_id = self._row_table(row_idx)
        # 收集同表合法参考值（非空、且匹配合法格式）
        valid = []
        for pos in range(1, n + 1):
            if not self._same_table(pos, table_id):
                continue
            v = vals[pos - 1]
            if v is None or str(v).strip() == "":
                continue
            s = str(v).strip()
            if legal_re is not None and not legal_re.match(s):
                continue
            valid.append(s)
        if not valid:
            # H-4：表级字段整表乱码时走邻表通道（日期相近 + 桩号区段连续双门控）
            return self._neighbor_table_loc(field, row_idx, base_conf, max_conf, legal_re)

        unique = {v for v in valid}
        # 同表众数：仅当部位唯一值恰为 1 种时采用（同表单一部位）
        mode = None
        if len(unique) == 1:
            mode = next(iter(unique))
            confidence = max_conf
            source = "同表众数"
            reason = f"同表其余合法行均为『{mode}』，推断此值应为『{mode}』"
        else:
            # 退化：同表邻行检索（上下各 4 行）
            candidate, dist = self._neighbor_lookup(vals, row_idx, legal_re, table_id)
            if candidate is None:
                return None
            mode = candidate
            confidence = base_conf
            if dist >= 4:
                confidence -= 0.20
            elif dist >= 2:
                confidence -= 0.10
            else:
                confidence -= 0.00
            source = "邻行推断"
            reason = f"同表合法部位不唯一，按相邻行（±{dist}行）推断为『{mode}』"
        confidence = round(max(0.0, min(max_conf, confidence)), 2)
        return {
            field: {
                "value": mode,
                "confidence": confidence,
                "source": source,
                "reason": reason,
                "suggested_only": True,
            }
        }

    def _neighbor_lookup(self, vals: list, row_idx: int,
                         legal_re: Optional[re.Pattern] = None,
                         table_id=None) -> tuple:
        """在**同一表**内查找距 row_idx 最近的有效值，返回 (value, 距离)；无则 (None, 0)。

        距离 d 从 1 递增，同距先看上方再看下方；只接受非空且匹配合法格式的值。
        跨表行不参与（不跨表抓建议值）。
        """
        if not vals:
            return None, 0
        n = len(vals)
        for d in range(1, 5):
            for pos in (row_idx - d, row_idx + d):  # pos 为 1-based 行号
                if 1 <= pos <= n and self._same_table(pos, table_id):
                    v = vals[pos - 1]
                    if v is None or str(v).strip() == "":
                        continue
                    s = str(v).strip()
                    if legal_re is not None and not legal_re.match(s):
                        continue
                    if not is_legal_loc(s):
                        continue  # H-2：邻行参考同样从严
                    return s, d
        return None, 0

    # ========== H-4：表级字段邻表推断（双门控） ==========

    _PILE_NUM_RE = re.compile(r"\d+")

    def _table_stats(self, table_id) -> dict:
        """收集一张表的 合法部位集合 / 日期ordinal / 桩号数值区间。"""
        locs, dates, piles = set(), [], []
        for r in self.rows:
            if not isinstance(r, dict) or r.get("table") != table_id:
                continue
            loc = str(r.get("loc") or "").strip()
            if loc and is_legal_loc(loc):
                locs.add(loc)
            d_raw = normalize_date_punct(r.get("date_raw"))
            m = self._DATE_RE.match(d_raw) if d_raw else None
            if m:
                try:
                    dates.append(_date(int(m.group(1)), int(m.group(2)),
                                       int(m.group(3))).toordinal())
                except ValueError:
                    pass
            pn = r.get("pile_no")
            if pn is not None:
                mm = self._PILE_NUM_RE.search(str(pn))
                if mm:
                    piles.append(int(mm.group()))
        return {"locs": locs,
                "date": min(dates) if dates else None,
                "pile_min": min(piles) if piles else None,
                "pile_max": max(piles) if piles else None}

    def _neighbor_table_loc(self, field, row_idx, base_conf, max_conf,
                            legal_re: Optional[re.Pattern]):
        """同表无合法参考时的邻表检索（H-4，双门控：日期相近 + 桩号区段连续）。

        施工记录按日期顺序成页推进：邻表若日期相近（≤3 天）且桩号区段衔接
        （区间距离 ≤ 20），其唯一合法部位可作为本表建议值 —— 有据跨表，
        非无脑跨表；任一门控不过即放弃（杜绝跨区污染）。
        """
        cur = self._row_table(row_idx)
        if cur is None:
            return None
        cur_stats = self._table_stats(cur)
        if cur_stats["date"] is None or cur_stats["pile_min"] is None:
            return None  # 当前表日期/桩号不可解析 → 无门控依据，不跨表
        all_tables = sorted({r.get("table") for r in self.rows
                             if isinstance(r, dict) and r.get("table") is not None})
        for dist in range(1, len(all_tables) + 1):  # 邻近优先：|Δ表号| 从小到大
            for cand_table in (cur - dist, cur + dist):
                if cand_table not in all_tables:
                    continue
                st = self._table_stats(cand_table)
                if len(st["locs"]) != 1 or st["date"] is None or st["pile_min"] is None:
                    continue  # 候选表部位须唯一合法，且可门控
                # 门控1：日期相近（≤3 天）
                if abs(st["date"] - cur_stats["date"]) > 3:
                    continue
                # 门控2：桩号区段连续（区间距离 ≤ 20）
                gap = max(st["pile_min"] - cur_stats["pile_max"],
                          cur_stats["pile_min"] - st["pile_max"])
                if gap > 20:
                    continue
                mode = next(iter(st["locs"]))
                confidence = round(max(0.0, min(max_conf, base_conf - 0.05 * dist)), 2)
                return {
                    field: {
                        "value": mode,
                        "confidence": confidence,
                        "source": "邻表推断",
                        "reason": (f"本表部位整表乱码，邻表(表{cand_table})日期相近"
                                   f"且桩号区段连续，推断为『{mode}』"),
                        "suggested_only": True,
                    }
                }
        return None

    def _text_fill_date(self, field, row_idx, base_conf, max_conf,
                        legal_re: Optional[re.Pattern]) -> dict | None:
        """施工日期：残形补齐，从**同表**相邻行取完整日期（不跨表/跨页取日期）。"""
        vals = self._col_values(field)
        if not vals:
            return None
        n = len(vals)
        if not (1 <= row_idx <= n):
            return None
        table_id = self._row_table(row_idx)
        # 残缺值：若原值非空（如『2026.4.◆』），尝试取出其年月片段用于跨月判断
        raw = vals[row_idx - 1] if 0 <= row_idx - 1 < n else None
        raw_str = str(raw) if raw is not None else ""
        year_month = self._extract_year_month(raw_str) if raw_str.strip() else None

        for d in range(1, 5):
            for pos in (row_idx - d, row_idx + d):
                if 1 <= pos <= n and self._same_table(pos, table_id):
                    v = vals[pos - 1]
                    if v is None or str(v).strip() == "":
                        continue
                    # H-1：候选日期先归一化（顿号变体可作完整日期候选）
                    cand = normalize_date_punct(str(v).strip())
                    m = self._DATE_RE.match(cand)
                    if not m:
                        continue  # 相邻行为非完整日期，不可采信
                    confidence = base_conf
                    # 跨月：候选完整日期与残缺值的年月不一致 → 降置信度
                    if year_month and self._extract_year_month(cand) != year_month:
                        confidence -= 0.15
                    confidence = round(max(0.0, min(max_conf, confidence)), 2)
                    return {
                        field: {
                            "value": cand,
                            "confidence": confidence,
                            "source": "相邻日期补齐",
                            "reason": f"该行日期缺失/残形，按相邻行占位日期补齐为『{cand}』",
                            "suggested_only": True,
                        }
                    }
        return None

    def _extract_year_month(self, text: str) -> str:
        """从日期文本提取『年月』用于跨月判断；无法解析返回 ''。"""
        m = self._DATE_RE.match(text.strip())
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        # 容错：仅含年/月份的残形
        m2 = re.match(r'^\s*(\d{4})\s*[.\-/年]\s*(\d{1,2})', text.strip())
        if m2:
            return f"{m2.group(1)}-{m2.group(2)}"
        return ""

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
        suggested_only_fields = 0

        for i, row in enumerate(self.rows):
            if not isinstance(row, dict):
                continue
            inferred: dict[str, dict] = {}
            row_idx = i + 1  # 1-based

            # 按顺序应用每条规则
            for rule in rules:
                # 文本/枚举规则（type=text）走独立建议值推断，只建议不入库
                if rule.get("type") == "text":
                    rule_result = self._apply_text_rule(rule, row, row_idx)
                else:
                    rule_result = self._apply_rule(rule, row, row_idx, inferred)
                if rule_result is not None:
                    inferred.update(rule_result)

            if inferred:
                result[str(row_idx)] = inferred
                total_inferred += len(inferred)
                rows_with_inferred += 1
                suggested_only_fields += sum(
                    1 for v in inferred.values()
                    if isinstance(v, dict) and v.get("suggested_only")
                )

        return {
            "row_inferred": result,
            "summary": {
                "total_rows": len(self.rows),
                "rows_with_inferred": rows_with_inferred,
                "total_inferred_fields": total_inferred,
                "suggested_only_fields": suggested_only_fields,
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
        # v10.3 E3：material schema 同样跳过桩基领域规则（桩号/桩长/充盈系数不适用），
        # 但不提示"schema 未确认"——材料 schema 是可确认的领域，只是领域不同。
        if self.schema_status == "material":
            pass
        elif self.schema_status == "unknown_domain" or self._unparsed_count == self.n_rows:
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

        # 3.7 三重一致性（v10.1）：表头设计桩长 vs 分区名 vs 实际数据
        # 仅依赖 full_text/行数据，与 schema 确认无关，unknown_domain 也可对账
        self.warnings.extend(self.check_design_zone_consistency())

        # 3.6 双份 rows 一致性守卫（H-6 接线）：structured_rows 与 rows 分叉
        # 会导致不同消费方各看各的数据，静默失效 —— 升为 error 级告警
        for msg in check_dual_rows(self.data):
            self.warnings.append({
                "code": "DQ-SELF-DUAL-01",
                "severity": "error",
                "message": f"双份数据不一致：{msg}",
                "detail": "structured_rows 与 rows 应保持镜像；请以 structured_rows 为准修复 rows",
            })

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


# ========== v9.6 隐患销号：pending 完整性重算（H-5） + 双份 rows 守卫（H-6）==========

# 参与应疑重算的数值字段（管道真实字段名）
_RECALC_NUM_FIELDS = (
    "bottom_elev", "top_elev", "actual_length", "design_length", "diameter",
    "volume", "filling_coeff", "verticality", "current", "re_penetration",
)

_RECALC_DATE_RE = re.compile(r"^\d{4}\s*[.\-/年]\s*\d{1,2}\s*[.\-/月]\s*\d{1,2}")


def recalc_pending(data: dict, zone_whitelist=None) -> list:
    """全量重扫 structured_rows 生成应疑清单（H-5）。

    与存量 pending_verification 比对可发现漏网项，供 G-1.9 闸门完整性审计：
    闸门只认 pending 清空，pending 本身有漏 → 漏网项当真值进报告。

    判定规则（与推断触发同源，一处谓词全链共用）：
      - 数值字段：类缺失（is_missing）或不可解析 float → 疑
      - 施工日期：归一化（normalize_date_punct）后仍不匹配合法格式 → 疑
      - 施工部位：is_legal_loc 判非法（白名单/正规形态）→ 疑
      - 跨表互斥：互异部位数 > 8 → 全文档加一条互斥告警（部位真实性存疑）
    """
    rows = data.get("structured_rows") or data.get("rows") or []
    rows = [r for r in rows if isinstance(r, dict)]
    pending: list = []
    loc_unique = {str(r.get("loc")).strip() for r in rows
                  if str(r.get("loc") or "").strip()}

    for r in rows:
        table = r.get("table")
        # 1) 数值字段
        for f in _RECALC_NUM_FIELDS:
            v = r.get(f)
            if is_missing(v):
                pending.append({"table": table, "field": f, "raw": str(v or ""),
                                "reason": f"数值缺失（{_REVERSE_ALIAS_MAP.get(f, f)}）"})
                continue
            try:
                float(str(v).strip().replace(",", "").replace("，", ""))
            except ValueError:
                pending.append({"table": table, "field": f, "raw": str(v),
                                "reason": f"数值不可解析:『{v}』"})
        # 2) 施工日期（归一化后判定）
        d_raw = normalize_date_punct(r.get("date_raw"))
        if not d_raw or not _RECALC_DATE_RE.match(d_raw):
            pending.append({"table": table, "field": "施工日期",
                            "raw": str(r.get("date_raw") or ""),
                            "reason": f"日期格式异常/残缺，无法确认（归一后『{d_raw}』）"})
        # 3) 施工部位
        loc = str(r.get("loc") or "").strip()
        if not loc:
            pending.append({"table": table, "field": "施工部位", "raw": "",
                            "reason": "部位为空白"})
        elif not is_legal_loc(loc, whitelist=zone_whitelist):
            pending.append({"table": table, "field": "施工部位", "raw": loc,
                            "reason": "部位疑似OCR乱码，不在合法区名形态/白名单内"})

    # 4) 跨表互斥：互异部位远超合理分区数（H-2a 兜底）
    if len(loc_unique) > 8:
        pending.append({"table": None, "field": "施工部位", "raw": f"{len(loc_unique)}种互异部位",
                        "reason": f"跨表互斥：同文档出现 {len(loc_unique)} 种互异部位，"
                                  f"远超合理分区数，部位整体真实性存疑，建议翻原图核对"})

    # 表级去重：部位/日期是表级字段（一页一写），同表同类疑项只留一条
    seen, deduped = set(), []
    for p in pending:
        if p["field"] in ("施工部位", "施工日期") and p["table"] is not None:
            key = (p["table"], p["field"])
            if key in seen:
                continue
            seen.add(key)
        deduped.append(p)
    return deduped


def check_dual_rows(data: dict) -> list:
    """双份 rows 一致性守卫（H-6）。

    结构化文件同时存 structured_rows 与 rows 两份（历史管道冗余），
    消费方落库若只写一份会静默分叉 —— 本守卫供写入路径调用，返回问题清单。
    """
    a = data.get("structured_rows")
    b = data.get("rows")
    if not isinstance(a, list) or not isinstance(b, list):
        return []  # 单份存在（历史文件）不误报
    if len(a) != len(b):
        return [f"行数不一致: structured_rows={len(a)}, rows={len(b)}"]
    issues = []
    for i, (ra, rb) in enumerate(zip(a, b), 1):
        if (json.dumps(ra, sort_keys=True, ensure_ascii=False)
                != json.dumps(rb, sort_keys=True, ensure_ascii=False)):
            issues.append(f"第{i}行内容不一致")
            if len(issues) >= 5:
                issues.append("...（后续不一致项省略）")
                break
    return issues


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