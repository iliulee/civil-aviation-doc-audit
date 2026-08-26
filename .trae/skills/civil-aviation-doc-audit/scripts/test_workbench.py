# -*- coding: utf-8 -*-
"""
workbench 结构断言（scripts/test_workbench.py）
================================================
文件级断言：pytest 直接收集。浏览器端行为由 Playwright e2e（tests/e2e/）覆盖，不混入本文件。

覆盖点：
  H1  package.json 已声明 workbench 开源依赖（sortablejs / xlsx）
  H2  vite.config.mjs 存在（Vite 构建配置）
  H3  template-manifest.json 无 dist/ 断链条目（产物不走模板复制管线）
  H4  src/data.js 存在且含数据层关键能力（双模加载 / 句柄持久化 / 原子写 / 备份）
  H5  src/main.js 存在且含七模块注册表 + 动态 import 路由
"""

import json
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]


def test_package_json_has_deps():
    pkg = json.loads((SKILL / "package.json").read_text(encoding="utf-8"))
    deps = pkg.get("dependencies", {})
    assert "sortablejs" in deps, "缺少 sortablejs 依赖"
    assert "xlsx" in deps, "缺少 xlsx(SheetJS) 依赖"
    assert "echarts" in deps, "缺少 echarts 依赖"


def test_vite_config_exists():
    assert (SKILL / "vite.config.mjs").exists(), "vite.config.mjs 缺失"


def test_manifest_no_dist_entries():
    m = json.loads((SKILL / "templates" / "template-manifest.json").read_text(encoding="utf-8"))
    srcs = [t["src"] for t in m["templates"]]
    # v10.1：manifest 不登记 dist/ 产物（dist/assets 为目录无法逐文件复制、
    # file:// 下 dist/index.html 受非安全上下文限制），工作台产物由部署管线直达
    # （产物存在性由 test_skill_assets 校验），此处防 dist 断链条目回归
    assert not any(s.startswith("dist/") for s in srcs), "manifest 不应登记 dist/ 条目（模板复制断链）"


# --- Task 1 数据层断言（追加） ---
def test_src_data_js_exists_and_has_core_capabilities():
    p = SKILL / "src" / "data.js"
    assert p.exists(), "src/data.js 缺失"
    text = p.read_text(encoding="utf-8")
    assert "showDirectoryPicker" in text, "缺少 File System Access 目录选择（双模加载之一）"
    assert "indexedDB" in text, "缺少 IndexedDB 句柄持久化"
    assert "WB.index" in text, "缺少 _index 内存共享（一次加载）"
    assert "atomicWriteJSON" in text, "缺少原子写能力"
    assert "backups" in text, "缺少写前自动备份（backups 目录）"


# --- Task 2 外壳断言（追加） ---
def test_src_main_js_has_module_registry_and_router():
    p = SKILL / "src" / "main.js"
    assert p.exists(), "src/main.js 缺失"
    text = p.read_text(encoding="utf-8")
    # 七模块注册表（总览/核对/看板/台账/概览/销号/外部）
    for mod in ["overview", "verify", "board", "ledger", "quality", "closing", "external"]:
        assert mod in text, f"模块注册表缺少 {mod}"
    assert "import(" in text, "缺少动态 import 路由"
    assert "views/" in text, "路由未指向 views/ 子目录"