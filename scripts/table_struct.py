# -*- coding: utf-8 -*-
"""
table_struct.py — 结构化解析层（v14 重写：值格式锚点 + 表头消歧 + 六类数据验证闸门）

======================================================================================================
为何又一次重写（根治"看似干净实则全错"）：
- v13 用"值格式锚点"推断列角色，但仅靠格式指纹（整数/小数/时间）在**手写体 OCR 污染数据**上
  依然会懦弱地产生"非空率 80%~100% 但每行字段全错位"的假健康行。
  例：bottom_elev 拿到 2103.74（实为桩顶高程）、design_length 拿到 24（实为反插次数）。
  v13.1 的另一个硬伤：build_rows_from_table 把可读表头直接丢弃（header_row_idx=-1），
  列角色纯靠值格式打分 → 实测出现 pile_no='28'、actual_length='2401' 的列错位。
- 本版（v14）在值格式锚点之上：
    1. 接入真实表头文字（数据起点上一行），仅作**同分消歧 + 值格式空缺补位**，
       值格式锚点仍为主，防表头 OCR 污染覆盖锚点映射。
    2. 叠加**领域物理约束**作为强校验，把"不可靠行"显式揪出来：
       桩顶高程 ≈ 2103.xx（恒定）、实长 ≈ 顶-底（数学链）、桩号递增、充盈/竖直/反插/桩长合理范围。
    3. 新增 validate_rows() 六类数据验证闸门（落地于数据底座生成前）：
       ①类型 ②格式 ③范围 ④完整性 ⑤一致性 ⑥跨字段，逐行产 issues，命中即标 needs_review。
- 门禁：每行打可信度；某页坏行占比 ≥30% → 整页 needs_review（绝不静默产出假行）。

设计原则：
- 纯函数、无副作用、可独立单测。
- 输入：几何网格（columns + grid）。
- 输出：rows（每行含 page/line_no/pile_no/各字段 + issues）+ 门禁摘要。
======================================================================================================
"""

import re
import statistics
from typing import Any, Dict, List, Optional, Tuple

# ========== 值格式指纹（锚点列定位，互斥） ==========
#   - 桩号/反插次 = 纯整数
#   - 高程/实长/充盈/灌入量/竖直度 = 必须带小数点的小数
#   - 时间 = HH:MM
_NUM_RE = re.compile(r"^[+\-]?\d+(\.\d+)?$")
_INT_RE = re.compile(r"^[+\-]?\d+$")
_TIME_RE = re.compile(r"^\d{1,2}[:：]\d{2}$")
_TIME_LOOSE_RE = re.compile(r"^\d{2,4}$")
_CURRENT_RE = re.compile(r"^\d+\s*/?\s*A$", re.IGNORECASE)
# 桩号：真实扫描件为"字母前缀+数字"（如 Z498、#608），OCR 可能误读为纯数字
_PILE_RE = re.compile(r"^#?[A-Za-z]{0,2}\d{2,6}$")
# 字母前缀桩号（Z499/#608）为强信号，与纯数字的"设计桩长"区分
_PILE_LETTER_RE = re.compile(r"^#?[A-Za-z]{1,2}\d{2,6}$")
# 高程：2xxx.xx（海拔）；充盈系数：1.xx；竖直度：0.x~1.x
_ELEV_RE = re.compile(r"^[2]\d{2}[.,．]\d{1,3}$")
_FILLING_RE = re.compile(r"^[1][.,．]\d{1,2}$")
_VERTICALITY_RE = re.compile(r"^[01][.,．]\d{1,2}$")

# ========== 领域物理约束（质量门禁） ==========
# 桩顶高程恒定值（场地地面高程，机场改扩建常见）；若全表中位值落在该区间则启用"恒定校验"
TOP_ELEV_EXPECTED = (2102.0, 2105.0)
TOP_ELEV_TOL = 0.5          # 恒定校验：顶高程标准差阈值（米）
ELEV_RANGE = (2000.0, 2300.0)    # 高层合理范围
LENGTH_RANGE = (5.0, 40.0)       # 设计桩长/实长合理范围
FILLING_RANGE = (1.0, 1.6)       # 充盈系数
VERTICALITY_RANGE = (0.0, 1.5)   # 竖直度(%)
REPEN_RANGE = (1, 60)            # 反插次数
VOLUME_RANGE = (1.0, 15.0)       # 灌入量(m³)
CURRENT_RANGE = (100.0, 500.0)   # 电流(A)
MATHCHAIN_TOL = 0.5              # 实长 = 顶-底 容差（米）


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _norm_cell(v: Any) -> str:
    s = _clean(v)
    s = s.replace("，", ".").replace("：", ":").replace("．", ".")
    return s


def _to_float(s: str) -> Optional[float]:
    s = _norm_cell(s)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ========== 列角色打分（值格式锚点） ==========
def _pile_like(raw: str) -> bool:
    """宽松判定是否为桩号单元格（含数字，容忍字母前缀/尾部污染）。
    手写体 OCR 会把桩号 Z499 读坏成 Z59D、12509、Z51D，
    只要含数字且形似桩号即接受，交给列级递增先验甄别。"""
    s = _clean(raw).lstrip("#")
    if not s:
        return False
    if _PILE_RE.match(s) or _NUM_RE.match(s):
        return True
    if re.match(r"^[A-Za-z]{1,2}\d{1,6}[A-Za-z]?$", s):
        return True
    return False


def _score_pile_no(text: str) -> int:
    if _PILE_LETTER_RE.match(text):
        return 6  # 字母前缀桩号（Z499）最强信号
    if _PILE_RE.match(text):
        return 3  # 纯数字桩号（可能与设计桩长"200"撞车，分低）
    if _pile_like(text):
        return 4  # 污染桩号（Z59D、12509）次强信号
    if _NUM_RE.match(text) and len(text) >= 2 and int(float(text)) > 0:
        return 2
    return 0


def _score_design_length(text: str) -> int:
    f = _to_float(text)
    if f is not None and LENGTH_RANGE[0] <= f <= LENGTH_RANGE[1]:
        return 3
    return 0


def _score_diameter(text: str) -> int:
    f = _to_float(text)
    if f is not None and 0.3 <= f <= 1.5:
        return 2
    return 0


def _score_time(text: str) -> int:
    if _TIME_RE.match(_norm_cell(text)):
        return 4
    if _TIME_LOOSE_RE.match(_norm_cell(text)) and len(_norm_cell(text)) in (4, 5):
        return 2
    return 0


def _score_elev(text: str) -> int:
    if _ELEV_RE.match(text):
        return 4
    f = _to_float(text)
    if f is not None and ELEV_RANGE[0] <= f <= ELEV_RANGE[1]:
        return 3
    return 0


def _score_current(text: str) -> int:
    if _CURRENT_RE.match(text):
        return 4
    f = _to_float(text)
    if f is not None and CURRENT_RANGE[0] <= f <= CURRENT_RANGE[1]:
        return 2
    return 0


def _score_re_penetration(text: str) -> int:
    f = _to_float(text)
    if f is not None and REPEN_RANGE[0] <= f <= REPEN_RANGE[1]:
        return 2
    return 0


def _score_volume(text: str) -> int:
    f = _to_float(text)
    if f is not None and VOLUME_RANGE[0] <= f <= VOLUME_RANGE[1]:
        return 2
    return 0


def _score_filling_coeff(text: str) -> int:
    if _FILLING_RE.match(text):
        return 4
    return 0


def _score_verticality(text: str) -> int:
    if _VERTICALITY_RE.match(text):
        return 4
    return 0


_SCORERS: Dict[str, Any] = {
    "pile_no": _score_pile_no,
    "design_length": _score_design_length,
    "diameter": _score_diameter,
    "sink_start": _score_time,
    "sink_end": _score_time,
    "pull_start": _score_time,
    "pull_end": _score_time,
    "bottom_elev": _score_elev,
    "top_elev": _score_elev,
    "actual_length": _score_design_length,
    "current": _score_current,
    "re_penetration": _score_re_penetration,
    "volume": _score_volume,
    "filling_coeff": _score_filling_coeff,
    "verticality": _score_verticality,
}


# ========== 表头文字 → 字段 映射（仅作消歧/补空缺，值格式锚点仍为主） ==========
# 每个字段一组别名（按长度择最长命中最优先），避免短别名（如"桩"）误命中"桩号/桩长"。
_HEADER_FIELD_ALIASES: List[Tuple[str, List[str]]] = [
    ("pile_no",        ["桩号/序号", "序号/桩号", "桩号", "顺序号", "序号", "编号"]),
    ("design_length",  ["设计桩长", "桩长(设计)", "设计桩长(m)", "设计长度", "桩长设计", "设计长"]),
    ("actual_length",  ["实际桩长", "实际长度", "实长", "成桩桩长"]),
    ("diameter",       ["桩径", "桩径(mm)", "直径", "成孔直径"]),
    ("sink_start",     ["沉管开始", "沉管开始时间", "沉管起", "贯入开始"]),
    ("sink_end",       ["沉管结束", "沉管结束时间", "沉管止", "贯入结束"]),
    ("pull_start",     ["拔管开始", "拔管开始时间", "拔管起", "提管开始"]),
    ("pull_end",       ["拔管结束", "拔管结束时间", "拔管止", "提管结束"]),
    ("bottom_elev",    ["桩底高程", "桩底标高", "底高程", "桩尖高程", "孔底高程"]),
    ("top_elev",       ["桩顶高程", "桩顶标高", "顶高程", "桩头高程"]),
    ("current",        ["密实电流", "电流", "密实电流(A)", "施工电流"]),
    ("re_penetration", ["反插次数", "反插", "复打次数", "反插数"]),
    ("volume",         ["灌入量", "灌入量(m³)", "灌石量", "石料用量"]),
    ("filling_coeff",  ["充盈系数", "充盈率", "充盈"]),
    ("verticality",    ["竖直度", "垂直度", "倾斜度", "桩身垂直度"]),
]


def _norm_header(t: str) -> str:
    """表头文字规范化：去括号注释、去空白、小写化。"""
    return re.sub(r"[（(].*?[)）]", "", str(t or "")).replace(" ", "").replace("\n", "").lower()


def _header_text_to_field(header_text: str) -> Optional[str]:
    """把表头文字映射到字段名；无法识别返回 None。

    匹配规则：遍历所有别名，命中最长别名者胜，避免短别名（如"桩"）误命中"桩号/桩长"。
    规范化后小写匹配。
    """
    norm = _norm_header(header_text)
    if not norm:
        return None
    best_field, best_len = None, -1
    for field, aliases in _HEADER_FIELD_ALIASES:
        for a in aliases:
            na = a.lower()
            if na and na in norm and len(na) > best_len:
                best_field, best_len = field, len(na)
    return best_field


# ========== 列级物理先验（v14.2 增强：列语义推断） ==========
# 值格式锚点无法区分"结构相似"的列（顶/底高程、设计/实长），
# 用列级物理先验 + 数学链把它们拆开，根治列错位。
def _col_prior(cf: str, vals: List[str]) -> Optional[int]:
    """列级物理先验打分；不适用时返回 None（交回值格式锚点）。"""
    # 桩号列优先判定：字母前缀桩号占比高 OR 数字随行递增（样本≥3）
    if cf == "pile_no":
        pileish = [v for v in vals[:30] if _pile_like(v)]
        if len(pileish) >= 3:
            letter = sum(1 for v in pileish if _PILE_LETTER_RE.match(v))
            ds = []
            for v in pileish:
                m = re.search(r"\d+", v)
                if m:
                    ds.append(int(m.group()))
            incr = sum(1 for a, b in zip(ds, ds[1:]) if b > a)
            r = incr / max(len(ds) - 1, 1)
            if letter / len(pileish) >= 0.5 or r >= 0.6:
                return 95
        return 0
    nums = [_to_float(v) for v in vals[:30] if _to_float(v) is not None]
    if not nums:
        return None
    if cf == "top_elev":
        in_r = sum(1 for n in nums if TOP_ELEV_EXPECTED[0] - 0.5 <= n <= TOP_ELEV_EXPECTED[1] + 0.5)
        r = in_r / len(nums)
        return 96 if r >= 0.7 else (40 if r >= 0.3 else 0)
    if cf == "bottom_elev":
        in_r = sum(1 for n in nums if 2070.0 <= n < TOP_ELEV_EXPECTED[0])
        return 90 if in_r / len(nums) >= 0.7 else 20
    if cf == "design_length":
        if len(nums) >= 2 and (max(nums) - min(nums)) <= 0.5:
            return 82
        return 0
    if cf == "actual_length":
        if len(nums) >= 2 and (max(nums) - min(nums)) > 0.5:
            return 78
        return 0
    return None


def _refine_column_roles(
    assigned: Dict[int, str],
    grid: List[List[Any]],
    header_row_idx: int,
) -> Dict[int, str]:
    """数学链再分配：实长 ≈ 桩顶 − 桩底，错位时互换 top/bottom 列。"""
    tc = next((c for c, f in assigned.items() if f == "top_elev"), None)
    bc = next((c for c, f in assigned.items() if f == "bottom_elev"), None)
    ac = next((c for c, f in assigned.items() if f == "actual_length"), None)
    if tc is None or bc is None or ac is None:
        return assigned
    data_rows = grid[header_row_idx + 1:] if header_row_idx >= 0 else grid[:]
    def chain_pass(t_, b_, a_):
        good = total = 0
        for row in data_rows:
            if t_ < len(row) and b_ < len(row) and a_ < len(row):
                t = _to_float(_norm_cell(row[t_]))
                b = _to_float(_norm_cell(row[b_]))
                a = _to_float(_norm_cell(row[a_]))
                if t and b and a:
                    total += 1
                    if abs(a - (t - b)) <= MATHCHAIN_TOL:
                        good += 1
        return good, total
    good, total = chain_pass(tc, bc, ac)
    if total >= 2 and good / total < 0.5:
        good2, total2 = chain_pass(bc, tc, ac)
        if total2 >= 2 and good2 / total2 > good / total:
                    assigned[tc], assigned[bc] = assigned[bc], assigned[tc]
    return assigned


def _lock_letter_pile(
    assigned: Dict[int, str],
    col_values: Dict[int, List[str]],
    n_cols: int,
) -> Dict[int, str]:
    """字母前缀桩号列锁定：若存在_桩号形值中字母前缀占比≥0.5_的列，
    强制它作为桩号列；被纯数字列(如反插/电流)误抢时让位。
    机场桩号多为 Z498/#608 字母前缀，是比纯数字更可靠的信号。"""
    letter_cols = []
    for i in range(n_cols):
        pl = [v for v in col_values.get(i, [])[:30] if _pile_like(v)]
        if len(pl) >= 3 and sum(1 for v in pl if _PILE_LETTER_RE.match(v)) / len(pl) >= 0.5:
            letter_cols.append(i)
    if not letter_cols:
        return assigned
    cur_pile = next((c for c, f in assigned.items() if f == "pile_no"), None)
    target = letter_cols[0]
    if cur_pile == target:
        return assigned
    if cur_pile is not None:
        old = assigned.get(target)
        del assigned[cur_pile]
        assigned[target] = "pile_no"
        if old and old != "pile_no":
            assigned[cur_pile] = old
    else:
        assigned[target] = "pile_no"
    return assigned


def infer_column_roles(
    columns: List[Dict[str, Any]],
    grid: List[List[Any]],
    header_row_idx: int,
) -> Dict[int, str]:
    """值格式锚点 + 表头文字消歧 + 领域范围打分推断每列角色。

    优先级：值格式锚点为主（打分），表头文字仅作 ①同分消歧 ②值格式空缺补位，
    不得让表头覆盖锚点映射（防表头 OCR 污染）。
    """
    n_cols = len(columns)
    if n_cols == 0:
        return {}

    # 表头最后一行即数据前一行（表头可能多行，+1 即可；空分隔行由空单元格自然跳过）

    data_rows = grid[header_row_idx + 1:] if header_row_idx >= 0 else grid[:]
    col_values: Dict[int, List[str]] = {i: [] for i in range(n_cols)}
    for row in data_rows:
        for i in range(n_cols):
            if i < len(row):
                v = _norm_cell(row[i])
                if v:
                    col_values[i].append(v)

    col_scores: Dict[int, Dict[str, int]] = {i: {} for i in range(n_cols)}
    for i in range(n_cols):
        vals = col_values[i]
        if not vals:
            continue
        for field, scorer in _SCORERS.items():
            # v14.2：列级物理先验优先（顶/底高程、设计/实长靠物理约束拆开）
            prior = _col_prior(field, vals)
            if prior is not None and prior >= 70:
                # 仅高置信物理先验覆盖锚点；低分(20/0)不覆盖，交给值格式锚点
                col_scores[i][field] = prior
                continue
            if field == "pile_no" and sum(1 for v in vals if _pile_like(v)) < 3:
                continue  # 桩号样本不足，禁止判桩号（防设计桩长列抢桩号）
            hits = sum(1 for v in vals[:30] if scorer(v) > 0)
            consistency = hits / max(len(vals[:30]), 1)
            if consistency >= 0.5:
                strength = scorer(vals[0]) if vals else 0
                col_scores[i][field] = int(consistency * 100 + strength)

    assigned: Dict[int, str] = {}
    used: set = set()

    # 表头文字信号（仅作同分消歧 + 值格式空缺时补位，不覆盖锚点映射）
    header_field_of_col: Dict[int, Optional[str]] = {}
    for i in range(n_cols):
        ht = columns[i].get("header_text", "") if i < len(columns) else ""
        header_field_of_col[i] = _header_text_to_field(ht)

    order = sorted(col_scores.keys(), key=lambda i: max(col_scores[i].values(), default=0), reverse=True)
    for i in order:
        best_field, best_score = None, -1
        for field, score in col_scores[i].items():
            if field in used:
                continue
            eff = score
            # 值格式锚点为主；仅当候选得分相当时，表头命中者优先（如两个时间列谁是谁）
            if header_field_of_col.get(i) == field:
                eff += 2
            if eff > best_score:
                best_field, best_score = field, eff
        if best_field is not None:
            assigned[i] = best_field
            used.add(best_field)

    # 值格式无法判定的列，用表头文字补空缺（不敢定列的列才走这里）
    if len(assigned) < n_cols:
        for i in range(n_cols):
            if i in assigned:
                continue
            hf = header_field_of_col.get(i)
            if hf and hf not in used and col_values[i]:
                assigned[i] = hf
                used.add(hf)

    # v14.2：数学链再分配（实长≈顶−底），错位时互换 top/bottom 列
    assigned = _refine_column_roles(assigned, grid, header_row_idx)

    # v14.7：字母前缀桩号列锁定（纯数字列让位）
    assigned = _lock_letter_pile(assigned, col_values, n_cols)

    return assigned


def coerce_value(field: str, raw: Any) -> Any:
    s = _norm_cell(raw)
    if not s:
        return None
    if field in ("pile_no", "remark"):
        return s
    if field in ("sink_start", "sink_end", "pull_start", "pull_end"):
        return s
    try:
        if re.search(r"[.,．]", s):
            return float(s.replace(",", ".").replace("．", "."))
        return int(s)
    except ValueError:
        return s


# ========== 行级可信度校验（六类数据验证） ==========
# 覆盖式重算六类校验：①类型 ②格式 ③范围 ④完整性 ⑤一致性 ⑥跨字段数学链。
# 与 validate_rows 共享（validate_rows 对每行调用并覆盖 issues）。
def check_row(row: Dict[str, Any]) -> List[str]:
    """返回该行的六类校验问题列表；空列表 = 该行可信。

    ① 类型：数值列非空必须能解析为数值
    ② 格式：时间列必须为 HH:MM
    ③ 范围：领域常量（长度/充盈/竖直度/反插/灌入量/桩顶高程）
    ④ 完整性：必填项缺失 error、强建议(时间)缺失 suspicious
    ⑤ 一致性：列角色已在 infer_column_roles 保证（锚点优先、表头消歧）
    ⑥ 跨字段：数学链（实长≈顶−底）；桩顶高程恒定性
    """
    issues: List[str] = []

    # 3.1 类型校验：数值列非空必须为数值
    for field, label in [
        ("design_length", "设计桩长"), ("actual_length", "实长"),
        ("diameter", "桩径"), ("bottom_elev", "桩底高程"), ("top_elev", "桩顶高程"),
        ("current", "密实电流"), ("re_penetration", "反插次数"),
        ("volume", "灌入量"), ("filling_coeff", "充盈系数"), ("verticality", "竖直度"),
    ]:
        v = row.get(field)
        sv = _clean(v)
        if sv and _to_float(sv) is None:
            issues.append(f"{label}类型错误: {v!r} 非数值")

    # 3.2 格式校验：时间列必须为 HH:MM
    for field, label in [("sink_start", "沉管开始"), ("sink_end", "沉管结束"),
                         ("pull_start", "拔管开始"), ("pull_end", "拔管结束")]:
        v = row.get(field)
        sv = _norm_cell(v)
        if sv and not _TIME_RE.match(sv):
            issues.append(f"{label}格式错误: {v!r} 非 HH:MM")

    # 3.4 完整性校验：必填项缺失 error；强建议(时间)缺失 suspicious
    for field, label in [("pile_no", "桩号"), ("design_length", "设计桩长"),
                         ("bottom_elev", "桩底高程"), ("top_elev", "桩顶高程")]:
        if not _clean(row.get(field)):
            issues.append(f"必填项缺失: {label}")
    for field, label in [("sink_start", "沉管开始"), ("sink_end", "沉管结束"),
                         ("pull_start", "拔管开始"), ("pull_end", "拔管结束")]:
        if not _clean(row.get(field)):
            issues.append(f"时间缺失(强建议): {label}")

    top = _to_float(str(row.get("top_elev") or ""))
    bottom = _to_float(str(row.get("bottom_elev") or ""))
    actual = _to_float(str(row.get("actual_length") or ""))

    # 3.6 跨字段：数学链 实长 ≈ 顶高程 - 底高程
    if bottom is not None and top is not None and actual is not None:
        if abs(actual - (top - bottom)) > MATHCHAIN_TOL:
            issues.append(f"数学链断裂: 实长={actual}, 顶-底={top - bottom:.2f}")

    # 3.6 跨字段：桩顶高程恒定（若解析出）
    if top is not None and not (TOP_ELEV_EXPECTED[0] <= top <= TOP_ELEV_EXPECTED[1]):
        issues.append(f"桩顶高程异常: {top}")

    # 3.3 范围校验：各项合理范围
    checks = [
        ("design_length", LENGTH_RANGE, "设计桩长"),
        ("actual_length", LENGTH_RANGE, "实长"),
        ("filling_coeff", FILLING_RANGE, "充盈系数"),
        ("verticality", VERTICALITY_RANGE, "竖直度"),
        ("volume", VOLUME_RANGE, "灌入量"),
    ]
    for field, rng, label in checks:
        f = _to_float(str(row.get(field) or ""))
        if f is not None and not (rng[0] <= f <= rng[1]):
            issues.append(f"{label}越界: {f}")

    rept = _to_float(str(row.get("re_penetration") or ""))
    if rept is not None and not (REPEN_RANGE[0] <= rept <= REPEN_RANGE[1]):
        issues.append(f"反插次数越界: {rept}")

    return issues


def page_reliability(rows_in_page: List[Dict[str, Any]]) -> Dict[str, Any]:
    """计算一页的可信度：坏行占比 → 门禁结论。"""
    if not rows_in_page:
        return {"total": 0, "bad": 0, "bad_ratio": 0.0, "needs_review": True, "reason": "无数据行"}
    bad = sum(1 for r in rows_in_page if r.get("issues"))
    ratio = bad / len(rows_in_page)
    return {
        "total": len(rows_in_page),
        "bad": bad,
        "bad_ratio": ratio,
        "needs_review": ratio >= 0.3,
    }


def _pile_int(pile_raw: str) -> Optional[int]:
    s = _clean(pile_raw).lstrip("#")
    if not s or not s.isdigit():
        return None
    v = int(s)
    return v if 0 < v <= 999999 else None


def build_rows_from_grid(
    pages_grid: List[Dict[str, Any]],
    start_line_no: int = 1,
) -> List[Dict[str, Any]]:
    """把几何网格 pages 组装成结构化 rows（值格式锚点 + 表头消歧 + 六类校验）。

    每页先做列角色推断，再做行级六类校验，坏行打 issues 标记。
    返回 list[dict]，每行含 page/line_no/pile_no/各字段/issues。
    """
    rows: List[Dict[str, Any]] = []
    line_no = start_line_no

    for pg in pages_grid:
        page = pg.get("page", 1)
        columns = pg.get("columns", [])
        grid = pg.get("grid", [])
        header_row_idx = pg.get("header_row_idx", -1)
        if not columns or not grid:
            continue

        col_field = infer_column_roles(columns, grid, header_row_idx)
        if not col_field:
            continue

        pile_col = next((c for c, f in col_field.items() if f == "pile_no"), None)
        if pile_col is None:
            continue

        # 表头最后一行即数据前一行（表头可能多行，+1 即可；空分隔行由空单元格自然跳过）

        data_rows = grid[header_row_idx + 1:] if header_row_idx >= 0 else grid[:]
        for cells in data_rows:
            if pile_col >= len(cells):
                continue
            pile_raw = _clean(cells[pile_col])
            if not pile_raw:
                continue
            if not _pile_like(pile_raw):
                continue

            record: Dict[str, Any] = {"page": page, "line_no": line_no}
            for col, field in col_field.items():
                if col < len(cells):
                    record[field] = coerce_value(field, cells[col])
            record["pile_no"] = _clean(cells[pile_col])
            record["issues"] = check_row(record)
            rows.append(record)
            line_no += 1

    return rows


def build_rows_from_items(
    items: List[Dict[str, Any]],
    doc_type: str = "",
    text: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """统一入口：items(含bbox) → 几何网格 → 结构化 rows + 门禁摘要。

    返回 (rows, gate)，gate 结构：
        {"applied", "page_summary": {page: {total,bad,bad_ratio,needs_review}},
         "suspect_count", "total_rows", "needs_review", "reason"}
    当 doc_type 非桩基表或 items 无 bbox 时，退回旧文本解析（build_rows_text）。
    """
    from ocr_grid import reconstruct_document_grid

    has_bbox = any(it.get("bbox") for it in (items or []))
    if not has_bbox:
        return _build_text_rows(text or "", doc_type), _empty_gate()

    lower = (doc_type or "").lower()
    is_pile = any(kw in lower for kw in ["碎石桩", "cfg", "桩"])

    try:
        max_x = max((it["bbox"][2] for it in items if it.get("bbox")), default=1000)
        img_width = int(max_x + 20)
        doc = reconstruct_document_grid(items, img_width)
        pages_grid = doc.get("pages", [])
        if not pages_grid:
            return _build_text_rows(text or "", doc_type), _empty_gate()

        rows = build_rows_from_grid(pages_grid)
        # 桩基文档：即使结构化失败也返回（空 rows 由上层判定降级）
        if is_pile:
            return rows, gate_from_rows(rows)
        # 非桩基文档：结构化成功（有桩号列/值格式锚点可识别）才采纳，否则回退纯文本
        if rows:
            return rows, gate_from_rows(rows)
        return _build_text_rows(text or "", doc_type), _empty_gate()
    except Exception as e:
        return _build_text_rows(text or "", doc_type), _empty_gate()


def _locate_data_start(grid: List[List[Any]], n_cols: int) -> int:
    """自动定位数据起始行。

    扫描整个网格,统计每列中匹配桩号格式(_PILE_RE)的单元格数,取命中最多的列为"桩号列"；
    返回该列首个有效桩号所在的行号。无法定位时回退 0。
    这样能自动跳过 RapidTable(SLANetPlus) 网格顶部的标题行/工程信息行/表头行,
    避免这些非数据行污染值格式锚点的列角色推断。
    """
    if not grid:
        return 0
    pile_hits: List[int] = [0] * n_cols
    first_valid: List[Optional[int]] = [None] * n_cols
    for r, row in enumerate(grid):
        for c in range(min(n_cols, len(row))):
            v = _norm_cell(_clean(row[c]))
            if _PILE_RE.match(v):
                pile_hits[c] += 1
                if first_valid[c] is None:
                    first_valid[c] = r
    if not any(pile_hits):
        return 0
    pile_col = max(range(n_cols), key=lambda c: pile_hits[c])
    return first_valid[pile_col] if first_valid[pile_col] is not None else 0


def build_rows_from_table(
    table: Dict[str, Any],
    doc_type: str = "",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """由 RapidTable(SLANetPlus) 的 table 结构(cells 网格)生成结构化 rows。

    table 结构(来自 ocr_image.ocr_pdf use_table 逐页识别):
        {"ok": bool, "pages": [{"ok", "page", "cells": {"r,c": text}, "n_rows", "n_cols"}, ...], "n_pages"}
    每页把 cells 网格转为 build_rows_from_grid 需要的 pages_grid(columns + grid + header_row_idx)。
    顶部标题/工程信息/表头行通过 _locate_data_start 自动裁剪,只保留数据行；
    表头行 = 数据起点上一行，提取文字填入 columns[].header_text，供列角色消歧/补空缺。
    返回 (rows, gate)。与 build_rows_from_items 同构,失败回退 (rows, gate) 空结构。
    """
    if not table or not table.get("ok"):
        return [], _empty_gate()

    pages_grid: List[Dict[str, Any]] = []
    for pg in table.get("pages", []) or []:
        if not pg.get("ok"):
            continue
        cells = pg.get("cells", {}) or {}
        n_rows = int(pg.get("n_rows", 0) or 0)
        n_cols = int(pg.get("n_cols", 0) or 0)
        if n_rows <= 0 or n_cols <= 0:
            continue
        grid: List[List[Any]] = [[""] * n_cols for _ in range(n_rows)]
        for key, val in cells.items():
            try:
                r, c = (int(x) for x in key.split(","))
            except (ValueError, AttributeError):
                continue
            if 0 <= r < n_rows and 0 <= c < n_cols:
                grid[r][c] = val
        data_start = _locate_data_start(grid, n_cols)
        data_grid = grid[data_start:]
        # 提取真实表头行（数据起点上一行，RapidTable 网格通常为可读表头）
        # 填入 columns[].header_text，供 infer_column_roles 消歧/补空缺（值格式锚点仍为主）
        columns: List[Dict[str, Any]] = [{"col": c, "header_text": ""} for c in range(n_cols)]
        if 0 < data_start <= len(grid):
            head_row = grid[data_start - 1]
            for c in range(min(n_cols, len(head_row))):
                ht = _clean(head_row[c])
                if ht:
                    columns[c]["header_text"] = ht
        pages_grid.append({
            "page": int(pg.get("page", 1) or 1),
            "columns": columns,
            "grid": data_grid,
            "header_row_idx": -1,
        })

    if not pages_grid:
        return [], _empty_gate()

    try:
        rows = build_rows_from_grid(pages_grid)
        return rows, gate_from_rows(rows)
    except Exception as e:
        return [], _empty_gate()


def _empty_gate() -> Dict[str, Any]:
    return {
        "applied": False, "page_summary": {}, "suspect_count": 0,
        "total_rows": 0, "needs_review": False, "reason": "",
    }


def gate_from_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """由结构化 rows 聚合出门禁摘要。"""
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for r in rows:
        by_page.setdefault(r.get("page", 1), []).append(r)

    page_summary = {}
    suspect_count = 0
    for page, prs in sorted(by_page.items()):
        rel = page_reliability(prs)
        page_summary[page] = rel
        suspect_count += rel["bad"]

    total = len(rows)
    bad_ratio = suspect_count / total if total else 0.0
    needs_review = bad_ratio >= 0.3 or suspect_count == total
    reason = ""
    if needs_review:
        reason = f"六类校验不达标: {suspect_count}/{total} 行(human 需核对)"
    elif suspect_count > 0:
        reason = f"{suspect_count}/{total} 行存疑(供参考)"

    return {
        "applied": True, "page_summary": page_summary,
        "suspect_count": suspect_count, "total_rows": total,
        "needs_review": needs_review, "reason": reason,
    }


def validate_rows(
    rows: List[Dict[str, Any]],
    doc_type: str = "",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """六类数据验证闸门（落地于数据底座生成前，见《数据验证_方案设计》）。

    对每行覆盖式重算 issues（check_row 已含：①类型 ②格式 ③范围 ④完整性 ⑥跨字段数学链），
    ⑤一致性已在 infer_column_roles 层保证（值格式锚点为主、表头消歧/补空缺）。
    命中即标记该行，聚合门禁供上层判定 needs_review。

    返回 (rows, gate)：
      - rows：过闸后的行（每行含最新的 issues）
      - gate：与 gate_from_rows 同构的门禁摘要（needs_review / suspect_count / total_rows）

    与 build_foundation.validate_structured_rows 分层：本函数是**行级**闸门（数据底座前），
    后者是**整表/跨行**统计（审核阶段），两者不重复。
    """
    # 非桩基表不启用行级六类校验（无桩物理常量），原样返回
    lower = (doc_type or "").lower()
    if not any(kw in lower for kw in ["碎石桩", "cfg", "桩"]):
        return rows, gate_from_rows(rows)

    for row in rows:
        # 覆盖式重算 issues（含类型/格式/完整性），避免与既有 issues 叠加误判
        row["issues"] = check_row(row)
    return rows, gate_from_rows(rows)


# ========== 旧文本解析回退（非桩基表 / 无 bbox） ==========
def _build_text_rows(text: str, doc_type: str) -> List[Dict[str, Any]]:
    """纯文本回退：按行存 raw_text（不做列对齐，列对齐依赖 bbox）。"""
    rows: List[Dict[str, Any]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if s:
            rows.append({"page": 1, "line_no": i, "raw_text": s})
    return rows
