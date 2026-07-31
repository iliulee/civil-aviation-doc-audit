# -*- coding: utf-8 -*-
"""
数据底座建立脚本（build_foundation.py）
======================================

Phase 1 核心脚本：扫描项目文件夹 → 文件分类 → OCR/PDF 提取 → 结构化 JSON →
数据质量检测 → 混淆检测 → index.json 总索引 → 复制 Web 模板。

用法：
    python scripts/build_foundation.py <项目文件夹路径> \
        --engine <auto|vision|paddle> \
        --incremental \
        --out <数据底座目录名，默认"数据底座"> \
        --preconditions <前置信息JSON文件路径> \
        --expected-rows <预期行数JSON文件路径，可选>

约束：
    - 不进入正式审核（Phase 1 结束后停止）。
    - 不引入数据库、后端服务、云端依赖（OCR 引擎选择 vision 时依赖用户本地 API Key）。
    - index.json 是唯一真相源，任何数据变更都会更新它。
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 允许 import 同目录下的 run_audit.py
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from run_audit import sniff_document  # noqa: E402
from audit_config import assign_subdivision_to_document, get_subdivision_info  # noqa: E402


# ========== 路径常量 ==========
OCR_IMAGE_PY = SCRIPT_DIR / "ocr_image.py"
EXTRACT_PDF_PY = SCRIPT_DIR / "extract_pdf.py"
DQ_CHECK_PY = SCRIPT_DIR / "data_quality_check.py"
CONFUSION_CHECK_PY = SCRIPT_DIR / "ocr_confusion_check.py"
TEMPLATES_DIR = SKILL_DIR / "templates"

# 页面平均行数（用于未提供 expected-rows 时的推断）
DEFAULT_ROWS_PER_PDF_PAGE = 20
DEFAULT_ROWS_PER_IMAGE_PAGE = 15

# 行数校验阈值：实际行数低于预期的 80% 时触发重试
ROW_COUNT_THRESHOLD = 0.8

# 默认纳入扫描的被审核资料扩展名（--include-all 可关闭此过滤）
DEFAULT_ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp",
    ".txt", ".md", ".doc", ".docx", ".xls", ".xlsx",
}


# ========== 专业/资料分类规则 ==========
PROFESSIONAL_RULES: List[Tuple[List[str], str]] = [
    (["场道", "土方", "碎石桩", "换填", "混凝土", "跑道", "滑行道"], "01_场道工程"),
    (["空管", "雷达", "VOR", "DME", "ILS", "航向"], "02_空管工程"),
    (["助航", "灯光", "灯箱", "标记牌", "调光器", "PAPI"], "03_助航设施"),
    (["弱电", "监控", "安防", "网络", "信息集成"], "04_弱电系统"),
    (["供油", "储油", "管线", "油罐", "加油"], "05_供油工程"),
]

REFERENCE_KEYWORDS = ["变更", "设计变更", "变更通知", "变更图纸"]
GENERIC_KEYWORDS = {
    "施工日志": ("通用资料", "施工日志", "施工日志"),
    "监理": ("通用资料", "监理文件", "监理文件"),
    "会议纪要": ("通用资料", "会议纪要", "会议纪要"),
    "联系单": ("通用资料", "工程联系单", "工程联系单"),
}

# 碎石桩表头关键词 → 字段名
PILE_HEADER_KEYWORDS: Dict[str, List[str]] = {
    "pile_no": ["桩号", "序号/桩", "序号", "桩"],
    "design_length": ["设计桩长", "设计长度"],
    "diameter": ["桩径", "直径"],
    "bottom_elev": ["桩底高程", "底高程"],
    "top_elev": ["桩顶高程", "顶高程"],
    "actual_length": ["实长", "实际桩长", "实际长度"],
    "current": ["密实电流", "电流"],
    "re_penetration": ["反插次数", "反插"],
    "volume": ["灌入量", "灌入"],
    "filling_coeff": ["充盈系数"],
    "verticality": ["竖直度", "垂直度"],
    "start_time": ["开始时间", "开钻时间", "起始时间"],
    "end_time": ["结束时间", "终钻时间", "终止时间"],
    "remark": ["备注", "说明"],
}

PILE_FIELDS = [
    "pile_no", "design_length", "diameter", "bottom_elev", "top_elev",
    "actual_length", "current", "re_penetration", "volume", "filling_coeff",
    "verticality", "start_time", "end_time", "remark",
]


# ========== 工具函数 ==========
def now_iso() -> str:
    """返回当前时间的 ISO 8601 字符串。"""
    return datetime.now().isoformat(timespec="seconds")


def generate_default_preconditions(project_path: Path) -> Dict[str, Any]:
    """未提供前置信息文件时，生成显式默认值并保存到输出目录供追溯。"""
    return {
        "stage": "分部分项验收",
        "nature": "扫描件",
        "scope": "全量审核",
        "ocr_engine": "auto",
        "special_notes": "由 build_foundation.py 自动生成默认前置信息，未经过人工确认",
        "excluded_files": [],
        "expected_rows": {},
    }


def load_json(path: Path) -> Any:
    """读取 JSON 文件，不存在时返回 None。"""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    """以 UTF-8 写入 JSON，保持中文可读。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_filename(name: str) -> str:
    """去除 Windows 非法字符，用于生成文件/目录名。"""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def run_subprocess(cmd: List[str]) -> Tuple[int, str, str]:
    """运行子进程命令，返回 (returncode, stdout, stderr)。"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)


def _compute_file_hash(file_path: Path) -> str:
    """计算文件的 SHA256 哈希值（用于增量更新检测）。

    对大文件采用分块读取，避免内存溢出。
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# ========== 文件扫描与分类 ==========
def is_temp_or_hidden(rel_path: Path) -> bool:
    """判断相对路径是否包含隐藏文件/目录或临时文件。"""
    parts = rel_path.parts
    for part in parts:
        if part.startswith("."):
            return True
    name = rel_path.name
    if name.startswith("~") or name.startswith("."):
        return True
    if name.lower().endswith((".tmp", ".bak", ".log", ".db", ".cache")):
        return True
    return False


def scan_files(
    project_path: Path,
    out_name: str,
    include_all: bool = False,
) -> List[Path]:
    """
    扫描项目文件夹下所有文件，排除数据底座目录自身、输出文件、隐藏/临时文件。
    默认仅保留资料类扩展名，--include-all 时扫描所有扩展名。
    返回文件相对 Path 列表。
    """
    files: List[Path] = []
    output_root_files = {"data-editor.html", "项目总览.html", "审核报告.html"}
    # 排除任意层级的输出目录：用户指定的 out_name 以及默认的"数据底座"
    output_dir_names = {out_name, "数据底座"}
    for p in project_path.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(project_path)
        # 排除输出目录（任意层级）
        if any(part in output_dir_names for part in rel.parts[:-1]):
            continue
        # 排除 Web/报告产物（任意层级）
        if rel.name in output_root_files:
            continue
        if is_temp_or_hidden(rel):
            continue
        # 默认扩展名过滤
        if not include_all and p.suffix.lower() not in DEFAULT_ALLOWED_EXTENSIONS:
            continue
        files.append(rel)
    return sorted(files)


def classify_file(
    rel_path: Path,
    excluded_set: set,
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    对单个文件进行分类。

    返回：
        (classification, professional, subcategory, doc_type)
        classification ∈ {"audited_files", "reference_files", "excluded_files"}
    """
    name = rel_path.name

    # 1. 用户明确排除
    if name in excluded_set or str(rel_path) in excluded_set:
        return "excluded_files", None, None, None

    # 2. 依据文件（设计变更类）
    for kw in REFERENCE_KEYWORDS:
        if kw in name:
            return "reference_files", "依据文件", "设计依据", "设计变更文件"

    # 3. 通用资料
    for kw, (prof, sub, doc) in GENERIC_KEYWORDS.items():
        if kw in name:
            return "audited_files", prof, sub, doc

    # 4. 五大专业匹配
    for kws, prof in PROFESSIONAL_RULES:
        if any(kw in name for kw in kws):
            sub, doc = detect_subcategory_and_doctype(name, prof)
            return "audited_files", prof, sub, doc

    # 5. 默认：作为通用资料被审核
    return "audited_files", "通用资料", "其他", "其他资料"


def detect_subcategory_and_doctype(name: str, professional: str) -> Tuple[str, str]:
    """根据文件名关键词推测 subcategory 与 doc_type。"""
    lower = name.lower()

    if professional == "01_场道工程":
        if "碎石桩" in name:
            return "施工记录", "碎石桩施工记录"
        if "cfg" in lower:
            return "施工记录", "CFG桩施工记录"
        if "桩" in name:
            return "施工记录", "桩基施工记录"
        if "土方" in name:
            return "施工记录", "土方工程"
        if "换填" in name:
            return "施工记录", "换填施工记录"
        if "混凝土" in name:
            return "施工记录", "混凝土工程"
        if any(kw in name for kw in ["跑道", "滑行道"]):
            return "施工记录", "场道施工记录"
        return "施工记录", "场道工程"

    if professional == "02_空管工程":
        if "vor" in lower:
            return "施工记录", "VOR台施工记录"
        if "dme" in lower:
            return "施工记录", "DME台施工记录"
        if "ils" in lower:
            return "施工记录", "ILS施工记录"
        if "雷达" in name:
            return "施工记录", "雷达工程"
        if "航向" in name:
            return "施工记录", "航向台施工记录"
        return "施工记录", "空管工程"

    if professional == "03_助航设施":
        if "灯光" in name:
            return "施工记录", "助航灯光工程"
        if "灯箱" in name:
            return "施工记录", "灯箱工程"
        if "标记牌" in name:
            return "施工记录", "标记牌工程"
        if "调光器" in name:
            return "施工记录", "调光器工程"
        if "papi" in lower:
            return "施工记录", "PAPI工程"
        return "施工记录", "助航设施工程"

    if professional == "04_弱电系统":
        if "监控" in name:
            return "施工记录", "监控系统"
        if "安防" in name:
            return "施工记录", "安防系统"
        if "网络" in name:
            return "施工记录", "网络系统"
        if "信息集成" in name:
            return "施工记录", "信息集成系统"
        return "施工记录", "弱电系统工程"

    if professional == "05_供油工程":
        if any(kw in name for kw in ["储油", "油罐"]):
            return "施工记录", "储油工程"
        if "管线" in name:
            return "施工记录", "管线工程"
        if "加油" in name:
            return "施工记录", "加油工程"
        return "施工记录", "供油工程"

    return "其他", "其他资料"


# ========== OCR / PDF 提取 ==========
def call_ocr_image(
    file_path: Path,
    engine: str,
    text_out: Path,
    json_out: Path,
    preprocess: Optional[str] = None,
) -> Dict[str, Any]:
    """
    调用 ocr_image.py 对扫描件 PDF / 图片做 OCR。
    返回 {"text", "engine", "confidence", "items"}，失败时 confidence 为 0。
    """
    cmd = [
        sys.executable, str(OCR_IMAGE_PY),
        str(file_path),
        "--engine", engine,
        "--out", str(text_out),
        "--json-out", str(json_out),
    ]
    if preprocess:
        cmd.extend(["--preprocess", preprocess])

    print(f"  [i] 调用 OCR: engine={engine}, preprocess={preprocess or 'default'}", file=sys.stderr)
    rc, stdout, stderr = run_subprocess(cmd)
    if stderr:
        print(stderr, file=sys.stderr)

    result: Dict[str, Any] = {"text": "", "engine": engine, "confidence": 0.0, "items": []}
    if rc == 0 and json_out.exists():
        try:
            raw = json.loads(json_out.read_text(encoding="utf-8"))
            result["text"] = raw.get("text", "")
            result["engine"] = raw.get("engine", engine)
            result["confidence"] = raw.get("confidence", 0.0)
            result["items"] = raw.get("items", [])
        except Exception as e:
            print(f"  [!] 解析 OCR JSON 失败: {e}", file=sys.stderr)
    else:
        print(f"  [!] OCR 子进程退出码: {rc}", file=sys.stderr)

    return result


def call_extract_pdf(file_path: Path, text_out: Path) -> Dict[str, Any]:
    """
    调用 extract_pdf.py 提取电子档 PDF 文字。
    返回 {"text", "engine", "confidence", "items": []}。
    """
    cmd = [sys.executable, str(EXTRACT_PDF_PY), str(file_path), "--out", str(text_out)]
    print("  [i] 调用 PyMuPDF 提取电子档 PDF", file=sys.stderr)
    rc, stdout, stderr = run_subprocess(cmd)
    if stderr:
        print(stderr, file=sys.stderr)

    text = ""
    if text_out.exists():
        text = text_out.read_text(encoding="utf-8")
    elif rc == 0:
        text = stdout

    return {
        "text": text,
        "engine": "PyMuPDF",
        "confidence": 1.0,
        "items": [],
    }


def call_extract_text(file_path: Path, text_out: Path) -> Dict[str, Any]:
    """
    直接读取文本文件（.txt/.md 等）内容。
    返回 {"text", "engine", "confidence", "items": []}。
    """
    print("  [i] 直接读取文本文件", file=sys.stderr)
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  [!] 读取文本文件失败: {e}", file=sys.stderr)
        text = ""
    text_out.write_text(text, encoding="utf-8")
    return {
        "text": text,
        "engine": "text",
        "confidence": 1.0,
        "items": [],
    }


# ========== 结构化 rows 转换 ==========
def coerce_pile_value(field: str, raw: str) -> Any:
    """将字符串转换为字段对应的数据类型。"""
    raw = raw.strip()
    if field == "pile_no":
        return raw
    if field in ("start_time", "end_time", "remark"):
        return raw
    # 时间字符串保持原样
    if field in ("start_time", "end_time") and re.match(r"^\d{1,2}:\d{2}$", raw):
        return raw
    # 数字字段
    if raw == "":
        return None
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def detect_header(line: str) -> Optional[Dict[int, str]]:
    """检测表头行，返回列索引 → 字段名的映射。"""
    # 用 2 个以上空格或制表符分隔，更符合 OCR 表格文本特点
    tokens = re.split(r"[\t\s]{2,}", line.strip())
    if len(tokens) < 3:
        tokens = line.strip().split()
    mapping: Dict[int, str] = {}
    for idx, tok in enumerate(tokens):
        for field, kws in PILE_HEADER_KEYWORDS.items():
            if any(kw in tok for kw in kws):
                # 若同一列命中多个关键词，以首次为准（理论上不会）
                if idx not in mapping:
                    mapping[idx] = field
                break
    # 至少识别到 4 列才认为是有效表头
    return mapping if len(mapping) >= 4 else None


def parse_pile_data_line(line: str, header_map: Dict[int, str], page: int, line_no: int) -> Optional[Dict[str, Any]]:
    """按表头映射解析一行碎石桩/桩基数据。"""
    tokens = re.split(r"[\t\s]{2,}", line.strip())
    if len(tokens) < len(header_map):
        tokens += [""] * (len(header_map) - len(tokens))

    record: Dict[str, Any] = {"page": page, "line_no": line_no}
    for idx, field in header_map.items():
        if idx < len(tokens):
            record[field] = coerce_pile_value(field, tokens[idx])

    # 至少要有桩号列才认为是数据行
    if not record.get("pile_no"):
        return None
    return record


def heuristic_pile_row(line: str, page: int, line_no: int) -> Optional[Dict[str, Any]]:
    """无表头时的启发式解析：按数值范围粗略匹配碎石桩字段。"""
    tokens = line.strip().split()
    if len(tokens) < 6:
        return None

    # 找桩号：Z 开头或 2 开头
    pile_idx = None
    for i, t in enumerate(tokens):
        if re.match(r"^[Zz2][\.\,\;\:\-]?[4-9]\d{1,2}[A-Da-d]?$", t.strip()):
            pile_idx = i
            break
    if pile_idx is None:
        return None

    nums = []
    for t in tokens[pile_idx + 1:]:
        s = t.strip()
        if re.match(r"^[\d\.]+$", s):
            try:
                nums.append(float(s))
            except ValueError:
                pass
        elif re.match(r"^\d{1,2}:\d{2}$", s):
            nums.append(s)

    record: Dict[str, Any] = {"page": page, "line_no": line_no, "pile_no": tokens[pile_idx].strip()}
    field_order = [
        "design_length", "diameter", "bottom_elev", "top_elev", "actual_length",
        "current", "re_penetration", "volume", "filling_coeff", "verticality",
    ]
    num_idx = 0
    for field in field_order:
        if num_idx >= len(nums):
            break
        v = nums[num_idx]
        if isinstance(v, str):
            # 时间字段只出现在最后两个位置
            if field in ("start_time", "end_time"):
                record[field] = v
            num_idx += 1
            continue
        record[field] = v
        num_idx += 1

    # 最后两个数字可能是开始/结束时间字符串
    times = [v for v in nums if isinstance(v, str)]
    if "start_time" not in record and len(times) >= 1:
        record["start_time"] = times[0]
    if "end_time" not in record and len(times) >= 2:
        record["end_time"] = times[1]

    return record


def parse_pile_rows(text: str, start_line_no: int = 1) -> List[Dict[str, Any]]:
    """从 OCR/PDF 文本中解析碎石桩类表格 rows。"""
    rows: List[Dict[str, Any]] = []
    page = 1
    line_no = start_line_no
    header_map: Optional[Dict[int, str]] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # 页分隔符
        m = re.match(r"===\s*第\s*(\d+)\s*页\s*===", line)
        if m:
            page = int(m.group(1))
            header_map = None
            continue

        # 表头检测
        if header_map is None:
            header_map = detect_header(line)
            if header_map:
                continue

        if header_map:
            record = parse_pile_data_line(line, header_map, page, line_no)
        else:
            record = heuristic_pile_row(line, page, line_no)

        if record:
            rows.append(record)
            line_no += 1

    return rows


def parse_generic_rows(text: str, start_line_no: int = 1) -> List[Dict[str, Any]]:
    """从文本中提取通用 rows：page / line_no / raw_text。"""
    rows: List[Dict[str, Any]] = []
    page = 1
    line_no = start_line_no
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = re.match(r"===\s*第\s*(\d+)\s*页\s*===", line)
        if m:
            page = int(m.group(1))
            continue
        rows.append({"page": page, "line_no": line_no, "raw_text": line})
        line_no += 1
    return rows


def build_rows(text: str, doc_type: str) -> List[Dict[str, Any]]:
    """根据 doc_type 选择解析策略。"""
    lower = doc_type.lower()
    is_pile = any(kw in lower for kw in ["碎石桩", "cfg", "桩"])
    if is_pile:
        return parse_pile_rows(text)
    return parse_generic_rows(text)


# ========== 行数校验 ==========
def get_expected_rows(
    rel_path: Path,
    pages: int,
    file_type: str,
    expected_map: Dict[str, int],
) -> Optional[int]:
    """获取文件的期望行数。"""
    name = rel_path.name
    # 1. 显式 expected-rows 配置
    for pattern, n in expected_map.items():
        if pattern in name:
            return n
    # 2. 按页推断
    if pages and pages > 0:
        if file_type.upper() == "PDF":
            return pages * DEFAULT_ROWS_PER_PDF_PAGE
        return pages * DEFAULT_ROWS_PER_IMAGE_PAGE
    return None


def check_row_count(actual: int, expected: Optional[int]) -> Tuple[bool, Optional[float]]:
    """返回 (是否通过, 实际/预期比例)。"""
    if expected is None or expected <= 0:
        return True, None
    ratio = actual / expected
    return ratio >= ROW_COUNT_THRESHOLD, ratio


# ========== MD 预览 ==========
def write_md_preview(
    data_file: Path,
    md_file: Path,
    meta: Dict[str, Any],
) -> None:
    """根据 {name}.json 生成只读 Markdown 预览。"""
    data = load_json(data_file) or {}
    rows = data.get("rows", [])

    lines: List[str] = []
    lines.append(f"# {meta.get('doc_type', '文档')} - 数据预览")
    lines.append("")
    lines.append(f"- **原始文件**: `{meta.get('original_file', '')}`")
    lines.append(f"- **OCR 引擎**: {meta.get('ocr_engine', '')}")
    conf = meta.get("ocr_confidence", 0.0) or 0.0
    lines.append(f"- **平均置信度**: {conf:.1%}")
    lines.append(f"- **页数**: {meta.get('pages', '')}")
    lines.append(f"- **生成时间**: {meta.get('ocr_completed_at', '')}")
    lines.append(f"- **状态**: {meta.get('ocr_status', '')}")
    lines.append("")

    if not rows:
        lines.append("> 未识别到数据行")
    else:
        headers = list(rows[0].keys())
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            vals = [str(v) if v is not None else "" for v in row.values()]
            lines.append("| " + " | ".join(vals) + " |")

    md_file.parent.mkdir(parents=True, exist_ok=True)
    md_file.write_text("\n".join(lines), encoding="utf-8")


# ========== 质量检测 / 混淆检测 ==========
def call_data_quality_check(data_file: Path) -> Tuple[Dict[str, Any], int]:
    """调用 data_quality_check.py，返回结果字典与告警总数。"""
    cmd = [sys.executable, str(DQ_CHECK_PY), str(data_file), "--pretty"]
    rc, stdout, stderr = run_subprocess(cmd)
    if stderr:
        print(stderr, file=sys.stderr)
    if rc != 0:
        print(f"  [!] 数据质量检测失败，退出码 {rc}", file=sys.stderr)
        return {"status": "error", "summary": {"total_warnings": 0}, "warnings": []}, 0
    try:
        result = json.loads(stdout)
        alerts = result.get("summary", {}).get("total_warnings", 0)
        return result, alerts
    except Exception as e:
        print(f"  [!] 解析数据质量结果失败: {e}", file=sys.stderr)
        return {"status": "error", "summary": {"total_warnings": 0}, "warnings": []}, 0


def call_ocr_confusion_check(data_file: Path) -> Tuple[Dict[str, Any], int]:
    """调用 ocr_confusion_check.py，返回结果字典与存疑总数。"""
    cmd = [sys.executable, str(CONFUSION_CHECK_PY), str(data_file), "--pretty"]
    rc, stdout, stderr = run_subprocess(cmd)
    if stderr:
        print(stderr, file=sys.stderr)
    if rc != 0:
        print(f"  [!] 混淆检测失败，退出码 {rc}", file=sys.stderr)
        return {"status": "error", "summary": {"total_suspects": 0}, "suspects": []}, 0
    try:
        result = json.loads(stdout)
        suspects = result.get("summary", {}).get("total_suspects", 0)
        return result, suspects
    except Exception as e:
        print(f"  [!] 解析混淆检测结果失败: {e}", file=sys.stderr)
        return {"status": "error", "summary": {"total_suspects": 0}, "suspects": []}, 0


# ========== index.json ==========
def ensure_index(
    project_path: Path,
    out_base: Path,
    preconditions: Dict[str, Any],
) -> Dict[str, Any]:
    """读取或初始化 index.json。"""
    index_path = out_base / "index.json"
    existing = load_json(index_path)
    if existing and existing.get("schema_version") == "1.0":
        existing.setdefault("preconditions", preconditions)
        return existing

    return {
        "schema_version": "1.0",
        "project_name": project_path.name,
        "project_path": str(project_path.resolve()),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "stage": "foundation_built",
        "preconditions": preconditions,
        "file_classification": {
            "audited_files": [],
            "reference_files": [],
            "excluded_files": [],
        },
        "documents": [],
        "corrections": {"total": 0, "files": []},
        "gaps": [],
        "audit_logs": [],
    }


def next_doc_id(index: Dict[str, Any]) -> str:
    """生成下一个 DOC-xxx 编号。"""
    existing = [d.get("id", "") for d in index.get("documents", [])]
    nums = []
    for e in existing:
        m = re.match(r"DOC-(\d+)", e)
        if m:
            nums.append(int(m.group(1)))
    nxt = max(nums, default=0) + 1
    return f"DOC-{nxt:03d}"


def find_doc_by_original(index: Dict[str, Any], original: str) -> Optional[Dict[str, Any]]:
    """根据 original_file 查找已有文档记录。"""
    for d in index.get("documents", []):
        if d.get("original_file") == original:
            return d
    return None


def sync_documents_with_classification(index: Dict[str, Any]) -> None:
    """
    根据当前 file_classification 重新同步 documents 数组。
    - 保留 original_file 仍在 audited_files 中的条目；
    - 人工核对过的条目（human_verified=true）即使不再被审核也保留，但标记 stale；
    - 其余 stale 条目清理。
    """
    audited_files = set(index.get("file_classification", {}).get("audited_files", []))
    docs = index.setdefault("documents", [])
    kept: List[Dict[str, Any]] = []
    for doc in docs:
        original = doc.get("original_file")
        if original in audited_files:
            doc.pop("stale", None)
            kept.append(doc)
        elif doc.get("human_verified") is True:
            doc["stale"] = True
            kept.append(doc)
        # 其他情况直接丢弃
    index["documents"] = kept


def update_index_for_doc(
    index: Dict[str, Any],
    doc: Dict[str, Any],
) -> None:
    """用新的文档记录更新 index.json（新增或替换）。"""
    docs = index.setdefault("documents", [])
    for i, d in enumerate(docs):
        if d.get("id") == doc.get("id"):
            docs[i] = doc
            return
    docs.append(doc)


# ========== 模板复制 ==========
def copy_web_templates(project_path: Path) -> None:
    """将 Web 模板复制到项目文件夹根目录（含 PDF.js 离线依赖）。"""
    # 模板文件清单：(源文件名, 目标文件名, 描述)
    template_files = [
        ("data-editor.html", "data-editor.html", "数据编辑器"),
        ("project-dashboard.html", "项目总览.html", "项目总览仪表盘"),
        ("pdf.min.js", "pdf.min.js", "PDF.js 主库（离线）"),
        ("pdf.worker.min.js", "pdf.worker.min.js", "PDF.js Worker（离线）"),
    ]

    for src_name, dst_name, desc in template_files:
        src = TEMPLATES_DIR / src_name
        dst = project_path / dst_name
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  ✓ 复制模板: {dst}（{desc}）", file=sys.stderr)
        else:
            print(f"  [!] 模板缺失: {src}（{desc}）", file=sys.stderr)


# ========== 断档检测（N-09） ==========
def _parse_pile_no(raw: str) -> Optional[int]:
    """解析桩号字符串，提取数值部分。

    支持格式：
      - Z420 → 420
      - Z-420 → 420
      - PHC-001 → 1
      - K0+120 → None（里程桩号，不适合数值连续性检测）
      - 纯数字 → 数字本身
    """
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    # 里程桩号（Kxx+xxx 格式），不参与数值连续性检测
    if re.match(r'^K\d+[\+]\d+', raw, re.IGNORECASE):
        return None
    # 提取最后的连续数字
    m = re.search(r'(\d+)$', raw)
    if m:
        return int(m.group(1))
    return None


def _extract_field_from_rows(rows: List[Dict[str, Any]], field_names: List[str]) -> List[Any]:
    """从 rows 中提取指定字段的值列表（按行顺序，去空）。"""
    values = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for fn in field_names:
            v = row.get(fn)
            if v is not None and v != "":
                values.append(v)
                break
    return values


def _detect_sequence_gaps(
    numbers: List[int],
    doc_label: str,
    professional: str,
    gap_type: str = "pile_no",
) -> List[Dict[str, Any]]:
    """检测数值序列中的断档。

    Args:
        numbers: 已排序的数值列表
        doc_label: 文档标识（用于描述）
        professional: 专业分类
        gap_type: 断档类型（pile_no / serial_no / date_seq）

    Returns:
        断档列表，每项包含 range_start, range_end, missing_count, description
    """
    if len(numbers) < 2:
        return []

    gaps = []
    # 先排序去重
    sorted_unique = sorted(set(numbers))
    min_val = sorted_unique[0]
    max_val = sorted_unique[-1]
    expected_range = max_val - min_val + 1
    actual_count = len(sorted_unique)

    if actual_count >= expected_range:
        return []  # 无断档

    # 找出缺失的具体数值
    missing = sorted(set(range(min_val, max_val + 1)) - set(sorted_unique))

    if not missing:
        return []

    # 将连续缺失合并为区间
    range_start = missing[0]
    range_end = missing[0]
    for m in missing[1:]:
        if m == range_end + 1:
            range_end = m
        else:
            gaps.append({
                "type": gap_type,
                "professional": professional,
                "range_start": str(range_start),
                "range_end": str(range_end) if range_end != range_start else str(range_start),
                "missing_count": range_end - range_start + 1,
                "description": f"{doc_label}：{gap_type} {range_start}-{range_end} 缺失（共 {range_end - range_start + 1} 个）",
                "detected_at": now_iso(),
            })
            range_start = m
            range_end = m

    # 最后一组
    gaps.append({
        "type": gap_type,
        "professional": professional,
        "range_start": str(range_start),
        "range_end": str(range_end) if range_end != range_start else str(range_start),
        "missing_count": range_end - range_start + 1,
        "description": f"{doc_label}：{gap_type} {range_start}-{range_end} 缺失（共 {range_end - range_start + 1} 个）",
        "detected_at": now_iso(),
    })

    return gaps


def detect_gaps(index: Dict[str, Any], out_base: Path) -> List[Dict[str, Any]]:
    """检测数据底座中的断档（桩号/日期/编号连续性）。

    从 index.json 的 documents 数组中读取所有已完成 OCR 的文件，
    加载其结构化数据，检测以下类型的断档：
    1. 桩号连续性：桩基施工记录中桩号是否连续
    2. 日期连续性：施工日志中日期是否连续
    3. 编号连续性：检验批/隐蔽工程编号是否连续

    Returns:
        断档列表，同时写入 index["gaps"]
    """
    all_gaps: List[Dict[str, Any]] = []

    # 桩号相关字段名（按优先级）
    PILE_NO_FIELDS = ["pile_no", "桩号", "序号/桩", "桩号/序号", "编号"]
    DATE_FIELDS = ["date", "日期", "施工日期", "记录日期", "start_time", "开始时间"]
    SERIAL_FIELDS = ["serial_no", "编号", "序号", "检验批编号", "no"]

    # 桩相关文档类型关键词
    PILE_DOC_KEYWORDS = ["桩", "碎石桩", "PHC", "CFG", "管桩", "灌注桩"]

    for doc in index.get("documents", []):
        doc_id = doc.get("id", "")
        doc_type = doc.get("doc_type", "")
        professional = doc.get("professional", "")
        data_file_rel = doc.get("data_file", "")
        ocr_status = doc.get("ocr_status", "")

        if ocr_status != "completed":
            continue

        data_path = out_base / data_file_rel
        if not data_path.exists():
            continue

        data = load_json(data_path)
        if not data:
            continue

        rows = data.get("rows", [])
        if not rows:
            continue

        doc_label = f"{doc_type}（{doc.get('original_file', doc_id)}）"

        # === 1. 桩号连续性检测 ===
        is_pile_doc = any(kw in doc_type for kw in PILE_DOC_KEYWORDS)
        if is_pile_doc:
            pile_raw = _extract_field_from_rows(rows, PILE_NO_FIELDS)
            pile_nums = []
            for p in pile_raw:
                num = _parse_pile_no(str(p))
                if num is not None:
                    pile_nums.append(num)

            if pile_nums:
                pile_nums.sort()
                pile_gaps = _detect_sequence_gaps(
                    pile_nums, doc_label, professional, gap_type="pile_no"
                )
                all_gaps.extend(pile_gaps)
                if pile_gaps:
                    print(f"  🔍 桩号断档: {doc_label} — 发现 {len(pile_gaps)} 处断档", file=sys.stderr)

        # === 2. 日期连续性检测 ===
        dates_raw = _extract_field_from_rows(rows, DATE_FIELDS)
        if dates_raw:
            date_nums = []
            for d in dates_raw:
                num = _parse_date_to_ordinal(str(d))
                if num is not None:
                    date_nums.append(num)
            if len(date_nums) >= 2:
                date_nums.sort()
                date_gaps = _detect_sequence_gaps(
                    date_nums, doc_label, professional, gap_type="date"
                )
                # 日期断档需要转换为可读格式
                for g in date_gaps:
                    try:
                        g["range_start"] = _ordinal_to_date_str(int(g["range_start"]))
                        g["range_end"] = _ordinal_to_date_str(int(g["range_end"]))
                        g["description"] = (
                            f"{doc_label}：日期 {g['range_start']} 至 {g['range_end']} "
                            f"缺失（共 {g['missing_count']} 天）"
                        )
                    except (ValueError, TypeError):
                        pass
                all_gaps.extend(date_gaps)
                if date_gaps:
                    print(f"  🔍 日期断档: {doc_label} — 发现 {len(date_gaps)} 处断档", file=sys.stderr)

        # === 3. 编号连续性检测（非桩类文档） ===
        if not is_pile_doc:
            serial_raw = _extract_field_from_rows(rows, SERIAL_FIELDS)
            serial_nums = []
            for s in serial_raw:
                num = _parse_pile_no(str(s))  # 复用同一解析逻辑
                if num is not None:
                    serial_nums.append(num)

            if len(serial_nums) >= 3:
                serial_nums.sort()
                serial_gaps = _detect_sequence_gaps(
                    serial_nums, doc_label, professional, gap_type="serial_no"
                )
                all_gaps.extend(serial_gaps)
                if serial_gaps:
                    print(f"  🔍 编号断档: {doc_label} — 发现 {len(serial_gaps)} 处断档", file=sys.stderr)

    # 写入 index
    index["gaps"] = all_gaps

    if all_gaps:
        print(f"\n⚠️  断档检测完成：共发现 {len(all_gaps)} 处断档", file=sys.stderr)
    else:
        print(f"\n✅ 断档检测完成：未发现断档", file=sys.stderr)

    return all_gaps


def _parse_date_to_ordinal(date_str: str) -> Optional[int]:
    """将日期字符串转换为序数（用于连续性检测）。

    支持格式：
      - 2026-04-15, 2026/04/15
      - 04-15, 4/15
      - 20260415
      - 2026年4月15日
    """
    if not date_str or not isinstance(date_str, str):
        return None
    date_str = date_str.strip()

    # 尝试多种格式
    formats = [
        (r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$', lambda m: (int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        (r'^(\d{4})年(\d{1,2})月(\d{1,2})日$', lambda m: (int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        (r'^(\d{1,2})[-/](\d{1,2})$', lambda m: (datetime.now().year, int(m.group(1)), int(m.group(2)))),
        (r'^(\d{8})$', lambda m: (int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8]))),
    ]

    for pattern, extractor in formats:
        m = re.match(pattern, date_str)
        if m:
            try:
                y, mo, d = extractor(m)
                return datetime(y, mo, d).toordinal()
            except (ValueError, OverflowError):
                return None

    return None


def _ordinal_to_date_str(ordinal: int) -> str:
    """将序数转换为日期字符串 YYYY-MM-DD。"""
    dt = datetime.fromordinal(ordinal)
    return dt.strftime("%Y-%m-%d")


# ========== 主流程 ==========
def main() -> int:
    parser = argparse.ArgumentParser(
        description="建立民航施工资料数据底座（Phase 1）"
    )
    parser.add_argument("project_path", help="项目文件夹路径")
    parser.add_argument(
        "--engine", choices=["auto", "vision", "paddle"], default="auto",
        help="OCR 引擎（默认 auto）"
    )
    parser.add_argument(
        "--incremental", action="store_true",
        help="增量模式：仅处理新文件或已变更文件"
    )
    parser.add_argument(
        "--out", default="数据底座",
        help="数据底座目录名（默认：数据底座）"
    )
    parser.add_argument(
        "--preconditions",
        help="前置信息 JSON 文件路径（含 stage/nature/scope/ocr_engine/special_notes/excluded_files/expected_rows）。"
             "未提供时将在输出目录生成默认前置信息文件。"
    )
    parser.add_argument(
        "--expected-rows",
        help="预期行数 JSON 文件路径，格式：{\"文件名模式\": 行数}"
    )
    parser.add_argument(
        "--include-all", action="store_true",
        help="扫描所有文件扩展名（默认仅扫描资料类扩展名）"
    )
    args = parser.parse_args()

    project_path = Path(args.project_path).resolve()
    if not project_path.is_dir():
        print(f"❌ 项目文件夹不存在: {project_path}", file=sys.stderr)
        return 1

    out_base = project_path / args.out
    out_base.mkdir(parents=True, exist_ok=True)

    # 读取前置信息；未提供时生成默认值并保存到输出目录
    if args.preconditions:
        preconditions_path = Path(args.preconditions).resolve()
        if not preconditions_path.exists():
            print(f"❌ 前置信息文件不存在: {preconditions_path}", file=sys.stderr)
            return 1
        preconditions = load_json(preconditions_path) or {}
    else:
        preconditions = generate_default_preconditions(project_path)

    # 命令行指定的 OCR 引擎优先级最高，回写到前置信息
    preconditions["ocr_engine"] = args.engine

    if not args.preconditions:
        default_pre_path = out_base / "preconditions_default.json"
        save_json(default_pre_path, preconditions)
        print(f"  [i] 未提供前置信息文件，已生成默认值: {default_pre_path}", file=sys.stderr)

    # 读取预期行数配置
    expected_map: Dict[str, int] = {}
    if args.expected_rows:
        ep = load_json(Path(args.expected_rows).resolve()) or {}
        if isinstance(ep, dict):
            expected_map = {k: int(v) for k, v in ep.items()}
    # 也支持从 preconditions.expected_rows 读取
    if isinstance(preconditions.get("expected_rows"), dict):
        for k, v in preconditions["expected_rows"].items():
            expected_map.setdefault(k, int(v))

    excluded_set = set(preconditions.get("excluded_files", []))

    print(f"\n🏗️  开始建立数据底座: {project_path}", file=sys.stderr)
    print(f"   输出目录: {out_base}\n", file=sys.stderr)

    # 初始化/读取 index.json
    index = ensure_index(project_path, out_base, preconditions)
    # 同步前置信息（CLI 引擎优先，覆盖旧值）
    index["preconditions"] = preconditions

    # 扫描文件
    rel_files = scan_files(project_path, args.out, args.include_all)
    print(f"📁 共扫描到 {len(rel_files)} 个文件", file=sys.stderr)

    # 重置分类清单（将按本次扫描结果重新写入）
    file_classification = index.setdefault("file_classification", {
        "audited_files": [],
        "reference_files": [],
        "excluded_files": [],
    })
    file_classification["audited_files"] = []
    file_classification["reference_files"] = []
    file_classification["excluded_files"] = []

    # 逐个处理
    for rel in rel_files:
      try:
        abs_path = project_path / rel
        classification, professional, subcategory, doc_type = classify_file(rel, excluded_set)

        if classification == "excluded_files":
            file_classification["excluded_files"].append(str(rel))
            print(f"  [排除] {rel.name}", file=sys.stderr)
            continue

        if classification == "reference_files":
            file_classification["reference_files"].append(str(rel))
            print(f"  [依据] {rel.name}", file=sys.stderr)
            continue

        file_classification["audited_files"].append(str(rel))

        # 格式识别
        sniff = sniff_document(str(abs_path))
        pages = sniff.get("page_count") or 1
        is_scanned = bool(sniff.get("is_scanned"))
        method = sniff.get("extraction_method", "unknown")
        file_type = sniff.get("suffix", "").upper().lstrip(".") or "UNKNOWN"
        if file_type in ("PNG", "JPG", "JPEG", "BMP", "TIFF", "TIF"):
            file_type = "IMAGE"

        print(f"\n📄 {rel.name} | type={file_type} | pages={pages} | scanned={is_scanned} | method={method}", file=sys.stderr)

        # 增量模式：已存在且未变更则跳过
        existing_doc = find_doc_by_original(index, str(rel))
        content_hash = _compute_file_hash(abs_path)
        if args.incremental and existing_doc:
            old_hash = existing_doc.get("content_hash", "")
            if existing_doc.get("ocr_status") == "completed" and old_hash and old_hash == content_hash:
                print(f"  [增量跳过] 已处理且内容未变更", file=sys.stderr)
                continue
            elif old_hash and old_hash != content_hash:
                print(f"  [增量更新] 文件内容已变更，重新处理", file=sys.stderr)

        # 确定存储目录与文件名
        folder = out_base / safe_filename(professional) / safe_filename(subcategory)
        folder.mkdir(parents=True, exist_ok=True)
        base_name = safe_filename(abs_path.stem)

        data_file = folder / f"{base_name}.json"
        md_file = folder / f"{base_name}.md"
        ocr_raw_file = folder / f"{base_name}_ocr.json"
        quality_file = folder / f"{base_name}_quality.json"
        confusion_file = folder / f"{base_name}_confusion.json"
        text_file = folder / f"{base_name}_raw.txt"

        ocr_status = "completed"
        ocr_engine = "unknown"
        ocr_confidence = 0.0
        ocr_text = ""
        retry_log: List[Dict[str, Any]] = []

        # ===== 提取 =====
        if method == "ocr":
            # 扫描件 PDF / 图片
            engine = args.engine
            result = call_ocr_image(abs_path, engine, text_file, ocr_raw_file)
            ocr_text = result.get("text", "")
            ocr_engine = result.get("engine", engine)
            ocr_confidence = result.get("confidence", 0.0)

            # 行数校验与自动重试（铁律 R-16）
            rows = build_rows(ocr_text, doc_type)
            expected = get_expected_rows(rel, pages, file_type, expected_map)
            passed, ratio = check_row_count(len(rows), expected)

            if not passed:
                # 第一次重试：图像增强（增量模式也执行，确保数据质量）
                print(f"  [!] 行数不足（实际 {len(rows)} / 预期 {expected}，比例 {ratio:.0%}），尝试增强重识别...", file=sys.stderr)
                retry_log.append({"attempt": 1, "action": "preprocess_enhance", "engine": engine})
                result = call_ocr_image(abs_path, engine, text_file, ocr_raw_file, preprocess="enhance")
                ocr_text = result.get("text", "")
                ocr_engine = result.get("engine", engine)
                ocr_confidence = result.get("confidence", 0.0)
                rows = build_rows(ocr_text, doc_type)
                passed, ratio = check_row_count(len(rows), expected)

                # 第二次重试：切换引擎（paddle → vision）
                if not passed:
                    fallback_engine = "vision" if engine in ("paddle", "auto") else "vision"
                    print(f"  [!] 增强后仍不足，尝试切换引擎 {fallback_engine}...", file=sys.stderr)
                    retry_log.append({"attempt": 2, "action": "switch_engine", "from": engine, "to": fallback_engine})
                    result = call_ocr_image(abs_path, fallback_engine, text_file, ocr_raw_file)
                    if result.get("text"):
                        ocr_text = result.get("text", "")
                        ocr_engine = result.get("engine", fallback_engine)
                        ocr_confidence = result.get("confidence", 0.0)
                        rows = build_rows(ocr_text, doc_type)
                        passed, ratio = check_row_count(len(rows), expected)

                if not passed:
                    ocr_status = "needs_review"
                    retry_log.append({
                        "attempt": "final",
                        "action": "mark_needs_review",
                        "reason": f"实际行数 {len(rows)} 低于预期 {expected} 的 {ROW_COUNT_THRESHOLD:.0%}",
                    })
                    print(f"  [⚠️] 行数校验未通过，标记为 needs_review", file=sys.stderr)

        elif method == "pymupdf":
            # 电子档 PDF
            result = call_extract_pdf(abs_path, text_file)
            ocr_text = result.get("text", "")
            ocr_engine = result.get("engine", "PyMuPDF")
            ocr_confidence = result.get("confidence", 1.0)
            # 写入 ocr_raw_file（仅做追溯用）
            save_json(ocr_raw_file, {
                "text": ocr_text,
                "engine": ocr_engine,
                "confidence": ocr_confidence,
                "items": [],
                "page_count": pages,
                "source": "extract_pdf.py",
            })

        elif method == "text":
            # 纯文本文件
            result = call_extract_text(abs_path, text_file)
            ocr_text = result.get("text", "")
            ocr_engine = result.get("engine", "text")
            ocr_confidence = result.get("confidence", 1.0)
            save_json(ocr_raw_file, {
                "text": ocr_text,
                "engine": ocr_engine,
                "confidence": ocr_confidence,
                "items": [],
                "page_count": pages,
                "source": "direct_read",
            })

        else:
            # 暂不支持的类型
            ocr_status = "unsupported"
            ocr_engine = method
            ocr_confidence = 0.0
            reason = f"暂不支持的提取方式: {method}"
            save_json(ocr_raw_file, {
                "text": "",
                "engine": method,
                "confidence": 0.0,
                "items": [],
                "reason": reason,
            })
            print(f"  [!] {reason}", file=sys.stderr)

        # ===== 生成结构化 rows =====
        rows: List[Dict[str, Any]] = []
        if ocr_status != "unsupported":
            rows = build_rows(ocr_text, doc_type)
            # 空内容也触发 needs_review
            if not rows:
                ocr_status = "needs_review"
                print(f"  [!] 未识别到任何数据行", file=sys.stderr)

        structured = {
            "schema_version": "1.0",
            "doc_id": existing_doc.get("id") if existing_doc else next_doc_id(index),
            "doc_type": doc_type,
            "source_file": str(rel),
            "professional": professional,
            "subcategory": subcategory,
            "ocr_engine": ocr_engine,
            "ocr_confidence": ocr_confidence,
            "ocr_completed_at": now_iso(),
            "rows": rows,
            "quality_result": {},
            "confusion_result": {},
            "corrections_applied": [],
        }

        # ===== 分配分部分项 code（v6.0 新增） =====
        subdivision_code = assign_subdivision_to_document(
            professional=professional,
            doc_type=doc_type,
            subcategory=subcategory,
        )
        if subdivision_code:
            sub_info = get_subdivision_info(professional, subdivision_code)
            structured["subdivision_code"] = subdivision_code
            structured["subdivision_label"] = sub_info["label"] if sub_info else ""
            structured["sub_division"] = sub_info["sub_label"] if sub_info else ""
            print(f"  [分部分项] {subdivision_code} {structured['subdivision_label']}（{structured['sub_division']}）", file=sys.stderr)
        else:
            structured["subdivision_code"] = None
            structured["subdivision_label"] = ""
            structured["sub_division"] = ""
            print(f"  [!] 未能匹配分部分项", file=sys.stderr)
        save_json(data_file, structured)

        # ===== MD 预览 =====
        md_meta = {
            "doc_type": doc_type,
            "original_file": str(rel),
            "ocr_engine": ocr_engine,
            "ocr_confidence": ocr_confidence,
            "pages": pages,
            "ocr_completed_at": structured["ocr_completed_at"],
            "ocr_status": ocr_status,
        }
        write_md_preview(data_file, md_file, md_meta)

        # ===== 数据质量检测 & 混淆检测 =====
        quality_alerts = 0
        confusion_suspects = 0
        if ocr_status not in ("unsupported",):
            quality_result, quality_alerts = call_data_quality_check(data_file)
            save_json(quality_file, quality_result)
            confusion_result, confusion_suspects = call_ocr_confusion_check(data_file)
            save_json(confusion_file, confusion_result)

            # 将质量/混淆结果回填到结构化 JSON
            structured["quality_result"] = quality_result
            structured["confusion_result"] = confusion_result
            save_json(data_file, structured)

        # ===== 更新 index.json =====
        doc = {
            "id": structured["doc_id"],
            "original_file": str(rel),
            "file_type": file_type,
            "is_scanned": is_scanned,
            "doc_type": doc_type,
            "professional": professional,
            "subcategory": subcategory,
            "subdivision_code": structured.get("subdivision_code"),
            "subdivision_label": structured.get("subdivision_label", ""),
            "sub_division": structured.get("sub_division", ""),
            "pages": pages,
            "ocr_status": ocr_status,
            "ocr_engine": ocr_engine,
            "ocr_confidence": ocr_confidence,
            "ocr_completed_at": structured["ocr_completed_at"],
            "data_file": str(data_file.relative_to(out_base)).replace("\\", "/"),
            "data_md": str(md_file.relative_to(out_base)).replace("\\", "/"),
            "ocr_raw_file": str(ocr_raw_file.relative_to(out_base)).replace("\\", "/"),
            "quality_file": str(quality_file.relative_to(out_base)).replace("\\", "/"),
            "confusion_file": str(confusion_file.relative_to(out_base)).replace("\\", "/"),
            "quality_alerts": quality_alerts,
            "confusion_suspects": confusion_suspects,
            "human_verified": False,
            "corrected_file": None,
            "audit_status": "pending",
            "last_updated": now_iso(),
            "size_bytes": sniff.get("size_bytes"),
            "content_hash": content_hash,
            "retry_log": retry_log,
        }
        update_index_for_doc(index, doc)
        print(f"  ✓ 已生成: {data_file.name}, {md_file.name}, 告警 {quality_alerts}, 存疑 {confusion_suspects}", file=sys.stderr)
      except Exception as e:
        print(f"  ❌ 处理失败，跳过此文件: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        continue

    # 同步 documents 与当前 file_classification，清理 stale 条目
    sync_documents_with_classification(index)

    # 断档检测（N-09）：桩号/日期/编号连续性
    print(f"\n🔍 开始断档检测...", file=sys.stderr)
    detect_gaps(index, out_base)

    # 更新 index 元信息
    index["updated_at"] = now_iso()
    index["stage"] = "foundation_built"
    save_json(out_base / "index.json", index)

    # 复制 Web 模板
    copy_web_templates(project_path)

    print(f"\n✅ 数据底座建立完成: {out_base}", file=sys.stderr)
    print(f"   阶段: {index['stage']}", file=sys.stderr)
    print(f"   被审核文件: {len(file_classification['audited_files'])}", file=sys.stderr)
    print(f"   依据文件: {len(file_classification['reference_files'])}", file=sys.stderr)
    print(f"   排除文件: {len(file_classification['excluded_files'])}", file=sys.stderr)
    print(f"\n⛔ Phase 1 结束。请打开项目文件夹中的 data-editor.html 进行人工核对。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
