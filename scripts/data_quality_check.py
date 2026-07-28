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
from pathlib import Path
from typing import Any, Optional

# ========== 豁免列配置 ==========
EXEMPT_COLUMNS_DEFAULT = {
    "桩径", "设计桩长", "密实电流", "表格代号", "工程名称",
    "diameter", "design_length", "current",
}
EXEMPT_COLUMNS_BY_DOC = {
    "碎石桩施工记录": {"桩径", "设计桩长", "密实电流"},
    "DDC桩施工记录": {"桩径", "设计桩长", "夯击能"},
    "混凝土浇筑记录": {"设计强度等级", "配合比编号"},
    "检验批质量验收记录": {"检验批编号"},
}

# ========== 突变阈值 ==========
JUMP_THRESHOLDS = {
    "实长": 0.30,
    "灌入量": 0.30,
    "反插次数": 0.30,
    "充盈系数": 0.20,
    "竖直度": 0.20,
    "actual_length": 0.30,
    "volume": 0.30,
    "re_penetration": 0.30,
    "filling_coeff": 0.20,
    "verticality": 0.20,
}


class DataQualityChecker:
    """数据质量检测器"""

    def __init__(self, data: dict):
        self.data = data
        self.rows = data.get("rows", [])
        self.doc_type = data.get("doc_type", "")
        self.n_rows = len(self.rows)
        self.warnings: list[dict] = []

        # 从 rows 中提取各列数据
        self.columns: dict[str, list] = {}
        self._build_columns()

    def _build_columns(self):
        """从 rows 构建列数据"""
        if not self.rows:
            return
        for row in self.rows:
            for key, val in row.items():
                if key not in self.columns:
                    self.columns[key] = []
                self.columns[key].append(val)

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
        col_name: str = "pile_no",
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
    def check_jump(self, remark_col: str = "remark") -> list[dict]:
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
            if col_name in ("pile_no", remark_col):
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
        start_time_col: str = "start_time",
        end_time_col: str = "end_time",
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

        # 2. 桩号总数校验（v2.0：不强制连号，只查总数和重复号）
        self.warnings.extend(self.check_pile_continuity(expected_total=expected_pile_total))

        # 3. 数据自洽
        self.warnings.extend(self.check_length_consistency())
        self.warnings.extend(self.check_filling_coeff_consistency())
        self.warnings.extend(self.check_time_continuity())

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
    args = parser.parse_args()

    # 读取输入
    if args.input:
        raw = Path(args.input).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()

    data = json.loads(raw)

    # 运行检测
    result = check(data, args.expected_rows, args.expected_pile_total)

    # 输出
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()