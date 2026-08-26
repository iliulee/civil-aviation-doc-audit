# -*- coding: utf-8 -*-
"""
skill 前端资源一致性断言（scripts/test_skill_assets.py）
=========================================================
文件级断言：pytest 直接收集。

背景
----
v10 资料员工作台把原 9 个散页 HTML 入口合并为单一工作台。
本套件钉住三条契约，防止文档/资源重新跑到 v8.7 旧模型：

  A1  templates/ 源模板文件齐全（data-editor / project-dashboard / tokens.css /
      pdf.min.js / pdf.worker.min.js 等）——复制源可用
  A2  v10 工作台构建产物存在（项目版 dist/ 或安装版 workbench/，含 index.html +
      assets 模块 JS，Overview/Verify 等模块齐全）
  A3  全 skill 内不得存在名为「数据核对编辑器.html」「项目总览.html」的散页
      （已被工作台合并，只允许英文源名 data-editor.html / project-dashboard.html 存在于 templates/）
  A4  SKILL.md 门禁一致性：不得再声称「数据底座/ 下必须存在：数据核对编辑器.html、
      项目总览.html、tokens.css、pdf.min.js、pdf.worker.min.js」这条 v8.7 旧闸门
"""

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]

# templates/ 下必须齐全的源模板（英文原名）
REQUIRED_TEMPLATE_SOURCES = [
    "data-editor.html",
    "project-dashboard.html",
    "launcher.html",
    "alignment-view.html",
    "tokens.css",
    "pdf.min.js",
    "pdf.worker.min.js",
    "audit-scope-template.html",
]

# 工作台合并后必须存在的核心模块（对应 assets/ 下的分块 JS 前缀）
REQUIRED_WORKBENCH_MODULES = ["Overview", "Verify", "Board", "Ledger", "Quality", "Closing"]

# v8.7 旧散页的中文名（合并进工作台后禁止再以散页形式出现在 skill 内）
OBSOLETE_CHINESE_PAGES = ["数据核对编辑器.html", "项目总览.html"]


def _workbench_dirs():
    """按优先级返回可能存在工作台产物的目录。项目版为 dist/，安装版为 workbench/。"""
    return {
        "dist": SKILL / "dist",
        "workbench": SKILL / "workbench",
    }


def _workbench_index_candidates():
    return [d for d in _workbench_dirs().values() if (d / "index.html").exists()]


def test_templates_source_files_exist():
    tpl = SKILL / "templates"
    missing = [f for f in REQUIRED_TEMPLATE_SOURCES if not (tpl / f).exists()]
    assert not missing, f"templates/ 缺失源模板: {missing}"


def test_workbench_bundle_exists():
    candidates = _workbench_index_candidates()
    assert candidates, f"v10 工作台产物缺失：project 应存在 dist/index.html，安装版应存在 workbench/index.html（现有目录: {[str(d) for d in _workbench_dirs().values()]}）"


def test_workbench_has_core_modules():
    candidates = _workbench_index_candidates()
    assert candidates, "v10 工作台产物缺失（见 test_workbench_bundle_exists）"
    wb = candidates[0]
    assets = wb / "assets"
    assert assets.is_dir(), f"工作台 assets/ 目录缺失: {assets}"
    asset_names = [p.name for p in assets.iterdir() if p.suffix == ".js"]
    # 模块文件形如 Overview-xxx.js，按前缀匹配；无 hash 时也可能直接叫 Overview.js
    missing = [
        m for m in REQUIRED_WORKBENCH_MODULES
        if not any(n == f"{m}.js" or n.startswith(f"{m}-") for n in asset_names)
    ]
    assert not missing, f"工作台 assets/ 缺少核心模块分块: {missing}（已有: {asset_names}）"


def test_no_obsolete_chinese_pages_shipped():
    """v8.7 中文名散页已被工作台合并，禁止再以文件形式出现在 skill 任何位置。"""
    found = []
    for base in SKILL.rglob("*"):
        if base.is_file() and base.name in OBSOLETE_CHINESE_PAGES:
            found.append(str(base))
    assert not found, f"skill 内仍存在已废弃的中文名散页（应仅保留 templates/ 下英文源名）: {found}"


def test_skill_md_gate_no_v87_claim():
    """SKILL.md 不得再声称"数据底座/ 下必须存在：数据核对编辑器.html、项目总览.html…"的 v8.7 旧闸门。"""
    p = SKILL / "SKILL.md"
    assert p.exists(), "SKILL.md 缺失"
    text = p.read_text(encoding="utf-8")
    hits = [k for k in OBSOLETE_CHINESE_PAGES if k in text]
    assert not hits, (
        f"SKILL.md 仍引用已废弃的中文名散页 {hits}（v8.7 旧模型，v10 已并入工作台，请改为引用 "
        f"「资料员工作台已部署」或「templates/data-editor.html」）"
    )