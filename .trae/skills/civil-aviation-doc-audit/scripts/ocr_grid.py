"""几何网格重建（v11.0 治本方案）

======================================================================================================
用途：把 OCR 的 items（带 bbox 坐标）重建为**列对齐**的表格网格，从根上消除"列错位"。

为什么这是治本：
- 旧链路是"OCR → 拍平文本 → 按 token 下标对列"。空单元格（OCR 没给 item）或合并单元格
  （相邻两格并成一个 item）都会让 token 数量与表头列数不一致，导致后面所有列整体错位。
- 本模块改用 bbox 的 X 坐标：每个数据格按"中心点落在哪个表头列的区间"归位。
  空单元格 → 该列留空，不产生位移；合并单元格 → 归到首列，相邻列留空。
  列数永远等于表头列数，绝不错位。

输出：
- 每页一个网格：`grid` = list of rows，每个 row = list of 单元格文本（列对齐，空为 ""）。
- 表头列：`columns` = [{col, header_text}]，供上层做"表头文字 → 字段"映射。
- 不依赖任何提炼模板，表头实时从页面检测。

只读纯函数，无副作用，可独立单测。
======================================================================================================
"""

import re
from typing import List, Dict, Any, Optional, Tuple

# 桩号施工记录表头关键词（命中越多越可能是表头行）
HEADER_KEYWORDS = [
    "桩号", "序号", "桩", "设计", "长", "桩径", "径", "沉管", "拔管", "时间",
    "起", "止", "桩底", "桩顶", "高程", "实长", "密实电流", "电流", "反插",
    "灌入量", "充盈", "竖直度", "数", "(%", "（m", "(m", "m²", "（m²",
]


def _bbox(it: Dict[str, Any]) -> Optional[List[float]]:
    b = it.get("bbox")
    if not b or len(b) != 4:
        return None
    return b


def _cx(it: Dict[str, Any]) -> float:
    b = _bbox(it)
    return (b[0] + b[2]) / 2.0 if b else 0.0


def _cy(it: Dict[str, Any]) -> float:
    b = _bbox(it)
    return (b[1] + b[3]) / 2.0 if b else 0.0


def cluster_into_rows(items: List[Dict[str, Any]], y_threshold: float = 0.5) -> List[List[Dict[str, Any]]]:
    """按 bbox 纵坐标把识别项聚类成表格行（与 ocr_image 同逻辑，独立实现避免耦合）。"""
    valid = [it for it in items if _bbox(it)]
    if not valid:
        return [[it] for it in items]

    heights = sorted((b[3] - b[1]) for b in (it["bbox"] for it in valid))
    median_h = heights[len(heights) // 2] if heights else 20.0
    threshold = max(median_h * y_threshold, 8.0)

    ordered = sorted(valid, key=_cy)
    rows: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    cur_y = None
    for it in ordered:
        cy = _cy(it)
        if cur_y is None or abs(cy - cur_y) <= threshold:
            cur.append(it)
            cur_y = cy if cur_y is None else (cur_y * (len(cur) - 1) + cy) / len(cur)
        else:
            cur.sort(key=_cx)
            rows.append(cur)
            cur = [it]
            cur_y = cy
    if cur:
        cur.sort(key=_cx)
        rows.append(cur)
    return rows


def _header_hits(row: List[Dict[str, Any]]) -> int:
    """一行中命中表头关键词的**项数**（用于区分表头续行 vs 数据行）。"""
    hits = 0
    for it in row:
        text = str(it.get("text", ""))
        if any(kw in text for kw in HEADER_KEYWORDS):
            hits += 1
    return hits


def _header_score(row: List[Dict[str, Any]]) -> int:
    """一行命中表头关键词的得分。

    v12.1 修复：**禁止计入 len(row)**。
    旧版 `hits*2 + len(row)` 会让"18 列的数据行"（含 0 关键词）也得到 18 分，
    导致第一行数据被误判为表头续行、并入表头区，表头文字被污染、列区间被拉偏。
    现在得分只反映关键词密度：表头行关键词密集，数据行几乎为 0。
    """
    return _header_hits(row) * 2 + (1 if row else 0)


def _is_header_like(row: List[Dict[str, Any]]) -> bool:
    """是否为表头行/表头续行：至少命中 2 个不同关键词项。"""
    return _header_hits(row) >= 2


def detect_header_region(
    rows: List[List[Dict[str, Any]]],
) -> Tuple[Optional[List[List[Dict[str, Any]]]], int]:
    """检测表头区（通常跨 1~2 行）。

    策略：全页找"关键词命中最多"的行作为表头（表头短文本关键词密集，数据行几乎为 0）。
    合并紧邻的上一行/下一行时，同样要求它命中 ≥2 个关键词（v12.1：避免把数据行并进来）。

    返回 (表头区行列表, 起始行下标)；未找到返回 (None, -1)。
    """
    if not rows:
        return None, -1

    scored = [(i, _header_score(r)) for i, r in enumerate(rows)]
    if not scored:
        return None, -1

    best_i = max(scored, key=lambda x: x[1])[0]
    # 得分需超过最低门槛（至少 2 个关键词命中）
    if not _is_header_like(rows[best_i]):
        return None, -1

    # 合并紧邻的下一行（表头续行，如"序 号/桩\n号 长 起 止"）——仅当它也是表头样式
    region = [rows[best_i]]
    if best_i + 1 < len(rows):
        nxt = rows[best_i + 1]
        if _is_header_like(nxt):
            region.append(nxt)
    # 也合并紧邻的上一行（若表头被拆成两行、数据更靠下）
    if best_i - 1 >= 0:
        prev = rows[best_i - 1]
        if _is_header_like(prev):
            region.insert(0, prev)
    return region, best_i


def _column_anchors(
    header_items: List[Dict[str, Any]], img_width: int
) -> List[Tuple[float, List[Dict[str, Any]]]]:
    """把表头项按 X 中心聚类成列锚点。

    同一列的多个表头标签（如"桩底"+"高程"）纵向堆叠、X 中心接近 → 合成一列。
    返回 [(col_center_x, [该列的表头项]), ...] 按 X 升序。
    """
    if not header_items or img_width <= 0:
        return []
    tol = max(12.0, img_width * 0.015)
    ordered = sorted(header_items, key=_cx)
    groups: List[List[Dict[str, Any]]] = []
    for it in ordered:
        cx = _cx(it)
        placed = False
        for g in groups:
            if abs(cx - _cx(g[0])) <= tol:
                g.append(it)
                placed = True
                break
        if not placed:
            groups.append([it])
    groups = [g for g in groups if g]
    groups.sort(key=lambda g: _cx(g[0]))
    return [(_cx(g[0]), g) for g in groups]


def _boundaries(anchors: List[Tuple[float, List[Dict[str, Any]]]]) -> List[float]:
    """由列锚点中心计算列边界（相邻锚点中点）。"""
    if len(anchors) < 2:
        return []
    centers = [a[0] for a in anchors]
    boundaries = []
    for i in range(len(centers) - 1):
        boundaries.append((centers[i] + centers[i + 1]) / 2.0)
    return boundaries


def _nearest_col(cx: float, centers: List[float]) -> int:
    """返回离 cx 最近的列下标。"""
    best, best_d = 0, float("inf")
    for i, c in enumerate(centers):
        d = abs(cx - c)
        if d < best_d:
            best, best_d = i, d
    return best


def reconstruct_page_grid(
    page_items: List[Dict[str, Any]], img_width: int
) -> Dict[str, Any]:
    """重建一页的列对齐网格。

    Args:
        page_items: 该页所有 OCR items（含 bbox）。
        img_width: 页面图像宽度（像素）。

    Returns:
        {
          "columns": [{col, header_text}],          # 表头列（按 X 升序）
          "grid": [[cell, ...], ...],               # 数据行（含表头行），列对齐，空为 ""
          "header_cols": int,                       # 列数
        }
    """
    rows = cluster_into_rows(page_items)
    header_region, header_row_idx = detect_header_region(rows)
    if not header_region:
        return {"columns": [], "grid": rows, "header_cols": 0}

    header_items = [it for r in header_region for it in r]
    anchors = _column_anchors(header_items, img_width)
    if len(anchors) < 2:
        return {"columns": [], "grid": rows, "header_cols": 0}

    centers = [a[0] for a in anchors]
    n_cols = len(centers)

    # 表头列文字（同列多段按 y 排序拼接）
    columns = []
    for a in anchors:
        col_items = sorted(a[1], key=_cy)
        header_text = "".join(str(it.get("text", "")).strip() for it in col_items)
        columns.append(header_text)

    # 重建网格：所有行（含表头行）都按列归位
    grid: List[List[str]] = []
    for row in rows:
        cells: List[str] = [""] * n_cols
        for it in row:
            col = _nearest_col(_cx(it), centers)
            text = str(it.get("text", "")).strip()
            if text:
                cells[col] = (cells[col] + " " + text).strip()
        grid.append(cells)

    return {
        "columns": [{"col": i, "header_text": columns[i]} for i in range(n_cols)],
        "grid": grid,
        "header_cols": n_cols,
        "header_row_idx": header_row_idx,
    }


def reconstruct_document_grid(
    items: List[Dict[str, Any]], img_width: int
) -> Dict[str, Any]:
    """重建整份文档（多页）的网格，按页分组。

    Returns: {"pages": [ {page, columns, grid, header_cols}, ... ]}
    """
    pages: Dict[int, List[Dict[str, Any]]] = {}
    for it in items:
        p = it.get("page") or 1
        pages.setdefault(p, []).append(it)

    out = []
    for p in sorted(pages.keys()):
        out.append({"page": p, **reconstruct_page_grid(pages[p], img_width)})
    return {"pages": out}