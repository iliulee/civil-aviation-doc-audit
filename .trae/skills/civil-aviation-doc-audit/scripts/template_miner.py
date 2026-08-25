# -*- coding: utf-8 -*-
"""
模板提炼工具（template_miner.py）
==================================
从多页同类扫描件的 OCR items（含 bbox）中，提炼出该类型表格的列模板。

核心思路：`锚点列定位 + 做减法`
- 锚点列：类型天然独特、识别极稳的列 —— 桩号(纯数字/Z开头)、密实电流(160A)、
  桩底/桩顶高程(20xx.xx)。它们错不了，先钉死。
- 做减法：锚点列之间的其余列（桩长/桩径/次数/系数）类型相似，无法靠类型区分，
  靠「表头合并 + 相对位置」推断，猜出来的进候选，供人工复核。

输入：
    一份或多份同类扫描件 PDF（示例：碎石桩施工记录）
    或直接传入已 OCR 好的 items（含 text + bbox）
输出：
    模板 JSON：列模板（列名 + 顺序 + 类型 + 锚点标记 + 字段槽位映射）

用法：
    python scripts/template_miner.py <pdf路径...> --doc-type 碎石桩施工记录 \
        --out <模板输出路径.json> [--pages 中间页范围]
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import fitz  # noqa: E401
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import ocr_image as OI  # noqa: E401
    HAS_OCR = True
except Exception:
    HAS_OCR = False


# ═══════════════════════════════════════════════════
# 值类型分类 —— 用于锚点列识别
# ═══════════════════════════════════════════════════
def classify_token(tok: str) -> str:
    """把单个 token 分类成值类型。"""
    t = tok.strip()
    if not t:
        return "empty"
    # 桩号：纯数字 2-6 位，或 Z/D 开头+数字
    if re.match(r"^#?\d{2,6}$", t) or re.match(r"^[ZDzd]\d{1,5}$", t):
        return "pile_no"
    # 高程：20xx.xx 或 2xxx.xx（四位数带小数点）
    if re.match(r"^2\d{3}\.\d{1,2}$", t):
        return "elev"
    # 时间：HH:MM 或 HH.MM
    if re.match(r"^\d{1,2}[:;\.\-]\d{2}$", t):
        return "time"
    # 电流：数字+A
    if re.match(r"^\d+[Aa]$", t):
        return "current"
    # 桩径/长度/系数：小数值（0.x 或 xx.x）
    if re.match(r"^\d+\.\d+$", t):
        return "decimal"
    # 纯整数
    if re.match(r"^\d+$", t):
        return "int"
    # 含数字杂项（可能是错字，如 125i20、90:40）
    if re.search(r"\d", t):
        return "digit_mixed"
    return "text"


TYPE_RANK = {
    "pile_no": 0, "current": 1, "elev": 2, "time": 3,
    "decimal": 4, "int": 5, "digit_mixed": 6, "text": 7, "empty": 8,
}


# ═══════════════════════════════════════════════════
# 表头关键词 —— 用于表头行识别 & 列名合并
# ═══════════════════════════════════════════════════
# 每项: (字段槽位, [列名关键词列表], 值类型锚点)
# 锚点类型: "锚"= 类型独立可钉死; "减"= 靠相对位置猜
FIELD_SPECS: List[Dict[str, Any]] = [
    {"slot": "pile_no",      "kw": ["序号", "桩号", "序号/桩"],                "anchor": "锚"},
    {"slot": "design_length","kw": ["设计桩长", "设计桩", "设计长"],            "anchor": "减"},
    {"slot": "diameter",     "kw": ["桩径", "直径"],                            "anchor": "减"},
    {"slot": "sink_time",    "kw": ["沉管时间", "沉管"],                        "anchor": "锚", "type": "time"},
    {"slot": "pull_time",    "kw": ["拔管时间", "拔管"],                        "anchor": "锚", "type": "time"},
    {"slot": "bottom_elev",  "kw": ["桩底高程", "底高程"],                      "anchor": "锚", "type": "elev"},
    {"slot": "top_elev",     "kw": ["桩顶高程", "顶高程"],                      "anchor": "锚", "type": "elev"},
    {"slot": "actual_length","kw": ["实际桩长", "实际长", "实长"],              "anchor": "减"},
    {"slot": "current",      "kw": ["密实电流", "电流"],                        "anchor": "锚", "type": "current"},
    {"slot": "re_penetration","kw": ["反插次数", "反插"],                       "anchor": "减"},
    {"slot": "volume",       "kw": ["灌入量", "灌入"],                          "anchor": "减"},
    {"slot": "filling_coeff","kw": ["充盈系数", "充盈"],                        "anchor": "减"},
    {"slot": "verticality",  "kw": ["竖直度", "垂直度"],                        "anchor": "减"},
]


def match_field_spec(token: str) -> Optional[str]:
    """表头 token 命中哪个字段槽位。返回 slot 名或 None。"""
    for spec in FIELD_SPECS:
        for kw in spec["kw"]:
            # 归一化：去掉空格/括号
            norm = token.replace(" ", "").replace("(", "").replace(")", "")
            if kw in norm:
                return spec["slot"]
    return None


# ═══════════════════════════════════════════════════
# 锚点列识别 —— 只靠值类型，不依赖表头
# ═══════════════════════════════════════════════════
def compute_column_type_dist(data_rows: List[List[str]]) -> List[Dict[str, Any]]:
    """统计每列的值类型分布，返回每列主类型 + 分布。"""
    max_cols = max(len(r) for r in data_rows) if data_rows else 0
    cols: List[Dict[str, Any]] = []
    for col in range(max_cols):
        dist: Dict[str, int] = {}
        for r in data_rows:
            if col < len(r):
                t = classify_token(r[col])
                dist[t] = dist.get(t, 0) + 1
        if not dist:
            cols.append({"col": col + 1, "main_type": "empty", "dist": {}})
        else:
            main = min(dist.keys(), key=lambda k: (-dist[k], TYPE_RANK.get(k, 9)))
            cols.append({"col": col + 1, "main_type": main, "dist": dict(dist)})
    return cols


def identify_anchor_columns(cols: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    用值类型识别锚点列。返回 {字段槽位: 列索引(0-based)}。
    只钉死类型独立、识别稳的列：
      - 桩号量最大(列1通常就是)
      - current 类型列(160A)
      - elev 类型列(20xx.xx，可能 1-2 个: 桩底/桩顶)
      - time 类型列(HH:MM，可能 1-2 个: 沉管时间/拔管时间)
    """
    anchors: Dict[str, int] = {}
    for i, c in enumerate(cols):
        mt = c["main_type"]
        if mt == "pile_no" and "pile_no" not in anchors:
            anchors["pile_no"] = i
        elif mt == "current" and "current" not in anchors:
            anchors["current"] = i
    # 高程列可能 1-2 个：按顺序标记 桩底(靠左)/桩顶(靠右)
    elev_idxs = [i for i, c in enumerate(cols) if c["main_type"] == "elev"]
    if elev_idxs:
        anchors["bottom_elev"] = elev_idxs[0]
        if len(elev_idxs) >= 2:
            anchors["top_elev"] = elev_idxs[1]
    # 时间列可能 1-2 个：按顺序标记 沉管时间(靠左)/拔管时间(靠右)
    time_idxs = [i for i, c in enumerate(cols) if c["main_type"] == "time"]
    if time_idxs:
        anchors["sink_time"] = time_idxs[0]
        if len(time_idxs) >= 2:
            anchors["pull_time"] = time_idxs[1]
    return anchors


# ═══════════════════════════════════════════════════
# 表头合并 —— 把碎片黏回完整列名
# ═══════════════════════════════════════════════════
def merge_header_into_columns(header_line: str, col_count: int) -> Dict[int, str]:
    """
    把表头行按位置切到列，能匹配字段的归位，碎片就近合并。
    返回 {列索引(0-based): 字段槽位}。
    """
    tokens = [t for t in header_line.split("\t") if t.strip()]
    mapping: Dict[int, str] = {}
    # 先精确匹配
    for i, tok in enumerate(tokens):
        if i >= col_count:
            break
        slot = match_field_spec(tok)
        if slot:
            mapping[i] = slot
    return mapping


# ═══════════════════════════════════════════════════
# 综合提炼 —— 锚点列 + 表头合并，做减法
# ═══════════════════════════════════════════════════
def build_template(all_header_lines: List[str], data_rows: List[List[str]],
                   doc_type: str) -> Dict[str, Any]:
    """综合锚点列和表头，提炼列模板。"""
    cols = compute_column_type_dist(data_rows)
    anchors = identify_anchor_columns(cols)

    # 表头合并（取出现最多的表头行）
    header_hits: Dict[str, int] = {}
    for hl in all_header_lines:
        header_hits[hl] = header_hits.get(hl, 0) + 1
    most_common_header = max(header_hits, key=header_hits.get) if header_hits else ""
    header_map = merge_header_into_columns(most_common_header, len(cols))

    # 组装列模板
    column_templates: List[Dict[str, Any]] = []
    for i, c in enumerate(cols):
        slot = header_map.get(i)
        anchor_for_col = None
        for field, col_idx in anchors.items():
            if col_idx == i:
                anchor_for_col = field
        column_templates.append({
            "col": i + 1,
            "slot": slot or anchor_for_col or None,
            "main_type": c["main_type"],
            "dist": {k: v for k, v in c["dist"].items()},
            "anchor_field": anchor_for_col,
            "table_header": slot is not None,
            "confidence": "high" if anchor_for_col else ("medium" if slot else "low"),
        })

    return {
        "schema_version": "1.0",
        "doc_type": doc_type,
        "derived_from_real_ocr": True,
        "method": "anchor_columns + header_merge + subtraction",
        "anchors": {k: v + 1 for k, v in anchors.items()},  # 1-based 列号
        "most_common_header": most_common_header,
        "sample_rows": len(data_rows),
        "columns": column_templates,
        "needs_human_review": True,
    }


# ═══════════════════════════════════════════════════
# 主流程 —— 读 PDF，OCR，聚类，提炼
# ═══════════════════════════════════════════════════
def _render_page(doc, idx: int, matrix):
    page = doc[idx]
    pix = page.get_pixmap(matrix=matrix)
    from PIL import Image
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def mine_from_pdf(pdf_path: Path, page_range: Optional[Tuple[int, int]] = None,
                  max_pages: Optional[int] = None) -> Dict[str, Any]:
    """从 PDF 提炼模板（OCR 固定走 RapidOCR）。"""
    if not HAS_PYMUPDF:
        raise RuntimeError("PyMuPDF 不可用")
    if not HAS_OCR:
        raise RuntimeError("ocr_image 不可用")

    doc = fitz.open(str(pdf_path))
    N = len(doc)
    # 默认全部页；支持中间页范围
    if page_range:
        idxs = list(range(page_range[0] - 1, page_range[1]))
    else:
        idxs = list(range(N))
    if max_pages and len(idxs) > max_pages:
        # 均匀抽样 max_pages 页
        step = len(idxs) / max_pages
        idxs = [idxs[int(i * step)] for i in range(max_pages)]

    gobject = None
    try:
        gobject = OI._get_rapidocr_engine()
    except Exception as e:
        print(f"  [!] OCR 引擎初始化失败: {e}", file=sys.stderr)

    # 动态 dpi：按每页尺寸计算缩放，使渲染长边约等于 TARGET_SIDE，
    # 避免 200dpi 暴力渲染大图纸产生数百 MB 中间图导致 OOM。
    TARGET_SIDE = 1800.0

    all_header_lines: List[str] = []
    data_rows: List[List[str]] = []
    HEADER_KW = ["桩", "时间", "高程", "长", "电流", "系数", "序号", "直径"]

    for idx in idxs:
        page_no = idx + 1
        rect = doc[idx].rect
        scale = TARGET_SIDE / max(rect.width, rect.height)
        matrix = fitz.Matrix(scale, scale)
        try:
            img = _render_page(doc, idx, matrix)
        except Exception as e:
            print(f"  [x] 第{page_no}页渲染失败: {e}", file=sys.stderr)
            continue
        if gobject is None:
            print(f"  [!] 第{page_no}页 OCR 引擎不可用，跳过", file=sys.stderr)
            continue
        try:
            items = OI._ocr_single_image_rapidocr(img, gobject, page=page_no)
        except Exception as e:
            print(f"  [x] 第{page_no}页 OCR 失败: {e}", file=sys.stderr)
            continue

        rows = OI._cluster_items_into_rows(items, y_threshold=0.6)
        for r in rows:
            tokens = [it.get("text", "").strip() for it in r]
            tokens = [t for t in tokens if t]
            if not tokens:
                continue
            text_tokens = [t for t in tokens if not re.search(r"\d", t) and len(t) >= 2]
            hits = sum(1 for t in tokens if any(k in t for k in HEADER_KW))
            # 表头行：命中关键词多，或纯文字 token 多
            if hits >= 2 or len(text_tokens) >= 4:
                all_header_lines.append("\t".join(tokens))
                continue
            # 数据行：任一位是桩号形式，或数值型 token ≥3 个，且不是纯文字
            numeric = [t for t in tokens
                       if classify_token(t) in ("pile_no", "current", "elev",
                                                "time", "decimal", "int")]
            has_pile = any(re.match(r"^#?\d{2,6}$", t) or re.match(r"^[ZDzd]\d{2,5}$", t)
                           for t in tokens)
            if len(numeric) >= 3 or has_pile:
                data_rows.append(tokens)
    doc.close()
    return build_template(all_header_lines, data_rows, Path(pdf_path).stem)


def main():
    ap = argparse.ArgumentParser(description="从扫描件提炼表格模板")
    ap.add_argument("pdfs", nargs="+", help="一个或多个扫描件 PDF 路径")
    ap.add_argument("--doc-type", default="碎石桩施工记录", help="文档类型")
    ap.add_argument("--out", required=True, help="模板 JSON 输出路径")
    ap.add_argument("--page-from", type=int, default=None, help="起始页(1-based)")
    ap.add_argument("--page-to", type=int, default=None, help="结束页(1-based)")
    ap.add_argument("--max-pages", type=int, default=None, help="最多抽样页数")
    args = ap.parse_args()

    page_range = None
    if args.page_from and args.page_to:
        page_range = (args.page_from, args.page_to)

    # 处理每份 PDF，输出各自模板
    for p in args.pdfs:
        pdf = Path(p)
        if not pdf.exists():
            print(f"  [x] 找不到 {pdf}", file=sys.stderr)
            continue
        print(f"  [i] 提炼 {pdf.name} ...", file=sys.stderr)
        tpl = mine_from_pdf(pdf, page_range=page_range, max_pages=args.max_pages)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(tpl, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [OK] 模板已写出: {out}")
        print(json.dumps(tpl, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()