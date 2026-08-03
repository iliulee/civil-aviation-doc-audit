"""
OCR 字符混淆校正检测脚本（ocr_confusion_check.py）
====================================================

用途：在 OCR 提取表格数据后、数据质量检测前，自动检测常见的
     OCR 字符混淆问题，生成"OCR 待核实清单"。

解决的问题：
  1. 桩号 Z→2 混淆（Z370 识别成 2370）
  2. 充盈系数 4→0 混淆（1.46 识别成 1.06）
  3. 数值范围异常（充盈系数 <1.0 或 >1.6）
  4. 桩长与高程差不一致（可能是 OCR 误读某个数字）
  5. 桩号前缀不一致（大部分 Z 开头，个别 2 开头）

核心原则：只标注"存疑"，不自动替换。最终由 AI 视觉或人工核实。

使用方式：
    python ocr_confusion_check.py <数据JSON文件>
    python ocr_confusion_check.py --help

也可以被 import 使用：
    from ocr_confusion_check import OCRConfusionChecker, check

输入 JSON 格式与 data_quality_check.py 相同：
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
      "filling_coeff": 1.37,
      "volume": 5.30,
      "verticality": 0.2,
      "remark": ""
    }
  ]
}
"""

import sys
import json
import re
import argparse
import math
from pathlib import Path
from typing import Any, Optional


# ========== 高频混淆对配置 ==========

# 桩号前缀映射：常见桩号前缀及其 OCR 易混淆字符
PILE_PREFIX_CONFUSION = {
    "Z": ["2", "2"],   # Z → 2 最常见
    "PH": ["P", "PH"], # PH 桩一般不混淆
    "CFG": ["C", "CFG"],
}

# 充盈系数正常范围（碎石桩）
FILLING_COEFF_RANGE = (1.0, 1.6)

# 竖直度正常范围（%）
VERTICALITY_RANGE = (0.0, 1.5)

# 桩长与高程差允许偏差（m）
LENGTH_ELEV_TOLERANCE = 0.1

# 桩长与高程差"疑似 OCR 误读"偏差范围（m）
# 偏差在这个范围内，可能是单个数字 OCR 错误
LENGTH_ELEV_SUSPECT_RANGE = (0.5, 2.0)


class OCRConfusionChecker:
    """OCR 字符混淆检测器"""

    def __init__(self, data: dict):
        self.data = data
        # 优先读 structured_rows，回退到 rows（向后兼容）
        self.rows = data.get("structured_rows") or data.get("rows", [])
        self.doc_type = data.get("doc_type", "")
        self.n_rows = len(self.rows)
        self.suspects: list[dict] = []

        # 构建列数据（字段名归一化为中文）
        self.columns: dict[str, list] = {}
        self._build_columns()

    def _build_columns(self):
        """从 rows 构建列数据，字段名统一归一化为中文"""
        if not self.rows:
            return
        from data_quality_check import _normalize_col_name
        for row in self.rows:
            for key, val in row.items():
                cn_key = _normalize_col_name(key)
                if cn_key not in self.columns:
                    self.columns[cn_key] = []
                self.columns[cn_key].append(val)

    # ========== 1. 桩号 Z→2 混淆检测 ==========
    def check_pile_prefix_consistency(self, col_name: str = "桩号") -> list[dict]:
        """
        检测桩号前缀一致性：
        - 如果大部分桩号以 Z 开头，个别以 2 开头 → 疑似 Z→2 混淆
        - 如果大部分以 2 开头，个别以 Z 开头 → 同理
        """
        w = []
        pile_nos = self.columns.get(col_name, [])
        if not pile_nos or len(pile_nos) < 3:
            return w

        # 统计前缀
        z_count = 0
        num_start_count = 0
        other_count = 0
        suspicious_indices = []

        for i, pn in enumerate(pile_nos):
            pn_str = str(pn).strip().upper()
            if pn_str.startswith("Z"):
                z_count += 1
            elif pn_str.startswith("2") and len(pn_str) >= 3:
                # 2 开头 + 至少3位数字 → 可能是 Z→2
                num_start_count += 1
                suspicious_indices.append(i)
            else:
                other_count += 1

        total = z_count + num_start_count + other_count
        if total == 0:
            return w

        # 如果 Z 开头占多数（>50%），2 开头的是疑似混淆
        if z_count > 0 and z_count / total > 0.5 and num_start_count > 0:
            for idx in suspicious_indices:
                ocr_val = str(pile_nos[idx])
                # 构造疑似真实值
                if ocr_val.startswith("2"):
                    suspected = "Z" + ocr_val[1:]
                else:
                    suspected = ocr_val

                w.append({
                    "code": "OCR-Z-01",
                    "field": col_name,
                    "row": idx + 1,
                    "ocr_value": ocr_val,
                    "suspected_value": suspected,
                    "reason": f"桩号前缀 Z→2 混淆（{z_count}/{total} 桩号以 Z 开头，本行以 2 开头）",
                    "confidence": "high" if z_count / total > 0.7 else "medium",
                    "action": "建议人工核实原图桩号列",
                })

        # 反向：如果 2 开头占多数，Z 开头的是疑似（较少见但也要查）
        elif num_start_count > 0 and num_start_count / total > 0.5 and z_count > 0:
            for i, pn in enumerate(pile_nos):
                pn_str = str(pn).strip().upper()
                if pn_str.startswith("Z"):
                    w.append({
                        "code": "OCR-Z-02",
                        "field": col_name,
                        "row": i + 1,
                        "ocr_value": pn_str,
                        "suspected_value": "2" + pn_str[1:],
                        "reason": f"桩号前缀 2→Z 混淆（{num_start_count}/{total} 桩号以 2 开头，本行以 Z 开头）",
                        "confidence": "medium",
                        "action": "建议人工核实原图桩号列",
                    })

        return w

    # ========== 2. 充盈系数范围异常检测 ==========
    def check_filling_coeff_range(self, col_name: str = "充盈系数") -> list[dict]:
        """
        检测充盈系数是否超出正常范围：
        - < 1.0 → 几乎不可能，疑似 OCR 误读（如 1.46→1.06 的 4→0）
        - > 1.6 → 罕见，需核实
        """
        w = []
        coeffs = self.columns.get(col_name, [])
        if not coeffs:
            return w

        low, high = FILLING_COEFF_RANGE

        for i, val in enumerate(coeffs):
            if val is None or not isinstance(val, (int, float)):
                continue

            if val < low:
                # 疑似 4→0 混淆：如 1.06 可能是 1.46 或 1.66
                suspected_vals = []
                val_str = f"{val:.2f}"
                # 尝试把 0 替换为 4 或 6
                for replace_char in ["4", "6"]:
                    for j, c in enumerate(val_str):
                        if c == "0":
                            suspected_str = val_str[:j] + replace_char + val_str[j+1:]
                            try:
                                suspected_val = float(suspected_str)
                                if low <= suspected_val <= high:
                                    suspected_vals.append(suspected_val)
                            except ValueError:
                                pass

                reason = f"充盈系数 {val} < {low}，不合理"
                if suspected_vals:
                    reason += f"，疑似 4→0 混淆（可能原值: {suspected_vals}）"

                w.append({
                    "code": "OCR-FC-01",
                    "field": col_name,
                    "row": i + 1,
                    "ocr_value": val,
                    "suspected_value": suspected_vals if suspected_vals else None,
                    "reason": reason,
                    "confidence": "high",
                    "action": "建议人工核实原图充盈系数列",
                })

            elif val > high:
                # 疑似 3→9 混淆：如 1.98 可能是 1.38
                suspected_vals = []
                val_str = f"{val:.2f}"
                for j, c in enumerate(val_str):
                    if c == "9":
                        suspected_str = val_str[:j] + "3" + val_str[j+1:]
                        try:
                            suspected_val = float(suspected_str)
                            if low <= suspected_val <= high:
                                suspected_vals.append(suspected_val)
                        except ValueError:
                            pass

                reason = f"充盈系数 {val} > {high}，需核实"
                if suspected_vals:
                    reason += f"，疑似 9→3 混淆（可能原值: {suspected_vals}）"

                w.append({
                    "code": "OCR-FC-02",
                    "field": col_name,
                    "row": i + 1,
                    "ocr_value": val,
                    "suspected_value": suspected_vals if suspected_vals else None,
                    "reason": reason,
                    "confidence": "medium",
                    "action": "建议人工核实原图充盈系数列",
                })

        return w

    # ========== 3. 竖直度范围异常检测 ==========
    def check_verticality_range(self, col_name: str = "verticality") -> list[dict]:
        """
        检测竖直度是否超出正常范围：
        - 碎石桩竖直度通常 ≤ 1.5%
        - 超出范围可能是 OCR 误读
        """
        w = []
        vals = self.columns.get(col_name, [])
        if not vals:
            return w

        low, high = VERTICALITY_RANGE

        for i, val in enumerate(vals):
            if val is None or not isinstance(val, (int, float)):
                continue

            if val > high:
                w.append({
                    "code": "OCR-VT-01",
                    "field": col_name,
                    "row": i + 1,
                    "ocr_value": val,
                    "suspected_value": None,
                    "reason": f"竖直度 {val}% 超出正常范围（≤{high}%），疑似 OCR 误读",
                    "confidence": "medium",
                    "action": "建议人工核实原图竖直度列",
                })

        return w

    # ========== 4. 桩长与高程差交叉验证 ==========
    def check_length_elevation_consistency(
        self,
        actual_len_col: str = "实长",
        top_elev_col: str = "桩顶高程",
        bottom_elev_col: str = "桩底高程",
        remark_col: str = "备注",
    ) -> list[dict]:
        """
        检测桩长与高程差是否一致：
        - 如果偏差 > 2m → 可能是数据被篡改（已在 data_quality_check 中检测）
        - 如果偏差在 0.5~2.0m → 可能是 OCR 误读某个数字
        - 如果备注列有"致岩""入岩"等 → 桩长可以小于设计值，不报为异常
        """
        w = []
        actuals = self.columns.get(actual_len_col, [])
        tops = self.columns.get(top_elev_col, [])
        bottoms = self.columns.get(bottom_elev_col, [])
        remarks = self.columns.get(remark_col, [])

        if not (actuals and tops and bottoms):
            return w

        n = min(len(actuals), len(tops), len(bottoms))
        for i in range(n):
            if any(v is None for v in [actuals[i], tops[i], bottoms[i]]):
                continue
            if not isinstance(actuals[i], (int, float)):
                continue
            if not isinstance(tops[i], (int, float)) or not isinstance(bottoms[i], (int, float)):
                continue

            calculated = tops[i] - bottoms[i]
            diff = abs(actuals[i] - calculated)

            # 偏差在"疑似 OCR 误读"范围内
            if LENGTH_ELEV_SUSPECT_RANGE[0] <= diff <= LENGTH_ELEV_SUSPECT_RANGE[1]:
                # 检查备注列是否有致岩/入岩
                remark = str(remarks[i]) if i < len(remarks) and remarks[i] else ""
                if any(kw in remark for kw in ["致岩", "入岩", "已入岩", "岩层"]):
                    # 致岩桩，桩长可以小于设计值，不报为 OCR 误读
                    continue

                # 尝试反推可能的真实桩长
                # 高程差通常更可信（两个独立读数）
                suspected_length = round(calculated, 1)

                # 检查是否单个数字差异（如 13.7 vs 13.1 → 7→1 混淆）
                ocr_str = f"{actuals[i]:.1f}"
                calc_str = f"{calculated:.1f}"
                diff_chars = []
                for j, (c1, c2) in enumerate(zip(ocr_str, calc_str)):
                    if c1 != c2:
                        diff_chars.append(f"位置{j}: '{c1}'→'{c2}'")

                reason = (
                    f"桩长 {actuals[i]}m 与高程差 {calculated:.2f}m 不一致"
                    f"（偏差 {diff:.2f}m），疑似 OCR 误读"
                )
                if diff_chars:
                    reason += f"，差异字符: {diff_chars}"

                w.append({
                    "code": "OCR-LEN-01",
                    "field": actual_len_col,
                    "row": i + 1,
                    "ocr_value": actuals[i],
                    "suspected_value": suspected_length,
                    "reason": reason,
                    "confidence": "high",
                    "action": f"建议人工核实原图桩长列（高程差反推桩长约 {suspected_length}m）",
                })

        return w

    # ========== 5. 桩长突变疑似 OCR 误读 ==========
    def check_length_jump_ocr_suspect(
        self,
        actual_len_col: str = "实长",
        remark_col: str = "备注",
    ) -> list[dict]:
        """
        检测桩长突变是否可能是 OCR 误读：
        - 如果相邻桩长差异 > 30%，且备注无"致岩"说明
        - 且差异可以通过单个数字替换解释（如 13.7→8.7 的 3→8）
        → 标注为"疑似 OCR 误读"
        """
        w = []
        lengths = self.columns.get(actual_len_col, [])
        remarks = self.columns.get(remark_col, [])

        if not lengths or len(lengths) < 3:
            return w

        for i in range(1, len(lengths)):
            if not isinstance(lengths[i], (int, float)) or not isinstance(lengths[i-1], (int, float)):
                continue

            prev = lengths[i - 1]
            curr = lengths[i]
            if prev == 0:
                continue

            change_rate = abs(curr - prev) / abs(prev)
            if change_rate < 0.30:
                continue

            # 检查备注列是否有致岩/入岩
            remark = str(remarks[i]) if i < len(remarks) and remarks[i] else ""
            if any(kw in remark for kw in ["致岩", "入岩", "已入岩", "岩层", "变更"]):
                continue

            # 检查是否可以通过单个数字替换解释
            prev_str = f"{prev:.1f}"
            curr_str = f"{curr:.1f}"
            if len(prev_str) == len(curr_str):
                diff_positions = [j for j, (c1, c2) in enumerate(zip(prev_str, curr_str)) if c1 != c2]
                if len(diff_positions) == 1:
                    pos = diff_positions[0]
                    c1 = prev_str[pos]
                    c2 = curr_str[pos]
                    w.append({
                        "code": "OCR-LEN-02",
                        "field": actual_len_col,
                        "row": i + 1,
                        "ocr_value": curr,
                        "suspected_value": prev,  # 可能和上一行一样
                        "reason": (
                            f"桩长突变 {prev}→{curr}（{change_rate:.0%}），"
                            f"仅单个字符差异（'{c1}'→'{c2}'），疑似 OCR 误读"
                        ),
                        "confidence": "medium",
                        "action": "建议人工核实原图桩长列",
                    })

        return w

    # ========== 6. 数字字段中的字母混淆 ==========
    def check_alpha_in_numeric(self) -> list[dict]:
        """
        检测纯数字字段中是否混入了字母（OCR 常见问题）：
        - O→0, l→1, I→1, S→5, B→8
        """
        w = []
        numeric_fields = [
            "实长", "充盈系数", "灌入量", "竖直度",
            "桩径", "设计桩长", "密实电流", "反插次数",
            "桩顶高程", "桩底高程",
        ]

        alpha_to_digit = {"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "s": "5", "B": "8"}

        for field in numeric_fields:
            vals = self.columns.get(field, [])
            for i, val in enumerate(vals):
                if val is None:
                    continue
                # 如果是字符串，检查是否含字母
                if isinstance(val, str):
                    for alpha, digit in alpha_to_digit.items():
                        if alpha in val:
                            w.append({
                                "code": "OCR-ALPHA-01",
                                "field": field,
                                "row": i + 1,
                                "ocr_value": val,
                                "suspected_value": val.replace(alpha, digit),
                                "reason": f"数字字段含字母 '{alpha}'，疑似 OCR 误读为 '{digit}'",
                                "confidence": "high",
                                "action": "建议人工核实原图",
                            })

        return w

    # ========== 主入口 ==========
    def run_all(self) -> dict:
        """运行全部检测，返回结果"""
        self.suspects = []

        # 1. 桩号前缀一致性
        self.suspects.extend(self.check_pile_prefix_consistency())

        # 2. 充盈系数范围
        self.suspects.extend(self.check_filling_coeff_range())

        # 3. 竖直度范围
        self.suspects.extend(self.check_verticality_range())

        # 4. 桩长与高程差交叉验证
        self.suspects.extend(self.check_length_elevation_consistency())

        # 5. 桩长突变疑似 OCR 误读
        self.suspects.extend(self.check_length_jump_ocr_suspect())

        # 6. 数字字段中的字母混淆
        self.suspects.extend(self.check_alpha_in_numeric())

        return self._build_result()

    def _build_result(self) -> dict:
        """构建输出结果"""
        n_high = sum(1 for s in self.suspects if s.get("confidence") == "high")
        n_medium = sum(1 for s in self.suspects if s.get("confidence") == "medium")

        # 透传 _page 信息：从原始数据行中获取页码，供 verify_fields.py 裁剪对应页
        for suspect in self.suspects:
            row_idx = suspect.get("row", 0) - 1  # row 从 1 开始
            if 0 <= row_idx < len(self.rows):
                page = self.rows[row_idx].get("_page", 1)
                suspect["page"] = page
            else:
                suspect["page"] = 1

        return {
            "status": "ok" if not self.suspects else "has_suspects",
            "summary": {
                "total_rows": self.n_rows,
                "total_suspects": len(self.suspects),
                "high_confidence": n_high,
                "medium_confidence": n_medium,
            },
            "suspects": self.suspects,
        }


def check(data: dict) -> dict:
    """便捷函数：一步完成检测"""
    checker = OCRConfusionChecker(data)
    return checker.run_all()


# ========== CLI ==========
def main():
    parser = argparse.ArgumentParser(
        description="OCR 字符混淆校正检测 — 在数据质量检测前自动识别 OCR 误读",
        epilog="""
输入 JSON 格式示例：
{
  "doc_type": "碎石桩施工记录",
  "rows": [
    {
      "pile_no": "Z420",
      "filling_coeff": 1.37,
      "actual_length": 13.7,
      "top_elev": 2103.68,
      "bottom_elev": 2089.98,
      "verticality": 0.2,
      "remark": ""
    }
  ]
}

输出格式：
{
  "status": "has_suspects",
  "summary": { "total_suspects": 2, "high_confidence": 1, ... },
  "suspects": [
    {
      "code": "OCR-Z-01",
      "field": "pile_no",
      "row": 5,
      "ocr_value": "2370",
      "suspected_value": "Z370",
      "reason": "桩号前缀 Z→2 混淆",
      "confidence": "high",
      "action": "建议人工核实原图桩号列"
    }
  ]
}
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", nargs="?", help="输入 JSON 文件路径（不提供则从 stdin 读取）")
    parser.add_argument(
        "--pretty", "-p", action="store_true",
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
    result = check(data)

    # 输出
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
