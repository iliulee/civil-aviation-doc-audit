"""
文本后处理脚本
====================================================

用途：清理从 PDF / OCR 提取出的中文文本中的常见乱码字符。
解决三个典型问题：
1. 全角英文字母 / 数字 / 标点 → 半角（规范条款引用必须是半角）
2. PDF 私用区字符（PUA）→ 通用对应字符（PDF 嵌入字体常见问题）
3. 异常空白、零宽字符、断行 → 规范化

使用方式：
    from scripts.postprocess import clean_text
    cleaned = clean_text(raw_text)

也可直接命令行使用：
    python scripts/postprocess.py <输入文件> --out <输出文件>
"""

import re
import sys
import argparse
from pathlib import Path

# ========== 全角 → 半角 映射 ==========
# 全角 ASCII 范围：U+FF01 ~ U+FF5E
# 使用 ord/chr 动态生成映射，避免漏字符
def _build_fullwidth_table():
    """构造 str.maketrans 用的映射表。

    str.maketrans(from, to) 中 from/to 都是字符串，但内部把字符 codepoint
    配对。str.translate 直接接受这个表，对文本做字符级替换。
    """
    src_chars = []
    dst_chars = []
    # 0xFF01 ~ 0xFF5E 对应 ASCII 0x21 ~ 0x7E（注意左闭右闭）
    for code in range(0xFF01, 0xFF5F):
        src_chars.append(chr(code))
        dst_chars.append(chr(code - 0xFEE0))
    return str.maketrans("".join(src_chars), "".join(dst_chars))


_FULLWIDTH_TRANS = _build_fullwidth_table()
_FULLWIDTH_RE = re.compile(r"[\uFF01-\uFF5E]")


def fullwidth_to_halfwidth(text: str) -> str:
    """全角 ASCII 转半角。"""
    return text.translate(_FULLWIDTH_TRANS)


# ========== 私用区字符 映射 ==========
# PDF 嵌入字体时常用 PUA 区段存字符，需替换
_PUA_MAP = {
    "\uE000": "—",  # 常用破折号替代
    "\uE001": "·",  # 间隔号
    "\uE002": "×",  # 乘号
    "\uE003": "÷",  # 除号
    "\uE004": "℃",  # 摄氏度
    "\uE005": "±",  # 正负号
    "\uE006": "≤",  # 小于等于
    "\uE007": "≥",  # 大于等于
    "\uE008": "≠",  # 不等号
    "\uE009": "≈",  # 约等于
    "\uE00A": "∑",  # 求和
    "\uE00B": "∏",  # 求积
    "\uE00C": "∫",  # 积分
    "\uE00D": "√",  # 根号
    "\uE00E": "∞",  # 无穷
    "\uE00F": "∠",  # 角
    "\uE010": "∥",  # 平行
    "\uE011": "⊥",  # 垂直
}


def replace_private_use_area(text: str) -> str:
    """替换 PDF 私用区字符为通用 Unicode。"""
    for pua_char, replacement in _PUA_MAP.items():
        text = text.replace(pua_char, replacement)
    return text


# ========== 零宽字符 / 异常空白 ==========
_INVISIBLE_CHARS_RE = re.compile(
    r"[\u200B-\u200F\u2028-\u202F\u205F-\u206F\uFEFF]"
)


def remove_invisible_chars(text: str) -> str:
    """移除零宽空格、零宽连字、字节顺序标记等。"""
    return _INVISIBLE_CHARS_RE.sub("", text)


# ========== 异常标点规范化 ==========
_REPLACEMENTS = {
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "–": "-",  # 短破折号
    "—": "-",  # 长破折号
    " ": " ",  # 不间断空格
    "　": " ",  # 全角空格
    "（": "(",  # 全角左括号（按规范需要时再单独打开）
    "）": ")",
    "【": "[",
    "】": "]",
}


def normalize_punctuation(text: str, keep_chinese_brackets: bool = True) -> str:
    """规范化标点。默认保留中文括号（因为规范条款中常用）。"""
    if not keep_chinese_brackets:
        for k, v in _REPLACEMENTS.items():
            text = text.replace(k, v)
    else:
        for k, v in _REPLACEMENTS.items():
            if k in ("（", "）", "【", "】"):
                continue
            text = text.replace(k, v)
    return text


# ========== 断行规范化 ==========
# PDF 提取常出现英文单词 / 数字被硬换行的情况，例如 "MH/T\n5078.1"
_HARDBREAK_BETWEEN_ASCII_RE = re.compile(
    r"([A-Za-z0-9])\n([A-Za-z0-9])"
)


def fix_hardbreaks(text: str) -> str:
    """修复英文/数字之间的硬换行。"""
    return _HARDBREAK_BETWEEN_ASCII_RE.sub(r"\1\2", text)


# ========== 多空行合并 ==========
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def collapse_blank_lines(text: str) -> str:
    """3 个以上连续换行合并为 2 个。"""
    return _MULTI_NEWLINE_RE.sub("\n\n", text)


# ========== 主入口 ==========
def clean_text(
    raw_text: str,
    fullwidth_to_half: bool = True,
    fix_pua: bool = True,
    remove_invisible: bool = True,
    normalize_punct: bool = True,
    fix_linebreak: bool = True,
    collapse_blank: bool = True,
) -> str:
    """一站式文本清洗入口。

    默认开启所有处理步骤。如需关闭特定步骤，传入对应参数=False。
    """
    text = raw_text
    if remove_invisible:
        text = remove_invisible_chars(text)
    if fix_pua:
        text = replace_private_use_area(text)
    if fullwidth_to_half:
        text = fullwidth_to_halfwidth(text)
    if normalize_punct:
        text = normalize_punctuation(text)
    if fix_linebreak:
        text = fix_hardbreaks(text)
    if collapse_blank:
        text = collapse_blank_lines(text)
    return text.strip()


def main():
    parser = argparse.ArgumentParser(description="PDF/OCR 文本后处理")
    parser.add_argument("input", help="输入文本文件")
    parser.add_argument("--out", help="输出文件（默认覆盖输入）")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"❌ 文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    raw = in_path.read_text(encoding="utf-8")
    cleaned = clean_text(raw)

    out_path = Path(args.out) if args.out else in_path
    out_path.write_text(cleaned, encoding="utf-8")
    print(
        f"✅ 已清洗 {in_path} → {out_path}\n"
        f"   原始 {len(raw)} 字符 → 清洗后 {len(cleaned)} 字符",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
