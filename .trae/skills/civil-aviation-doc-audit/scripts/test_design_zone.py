# -*- coding: utf-8 -*-
"""v10.1 回归测试：三重一致性 + 依据缺失渲染 + registry 对齐

背景（2026-08-25 用户实测暴露）：
  B  表头设计桩长(5m) vs sheet分区名"(8米)" vs 实际施工桩长(~8m) 三重矛盾，
     引擎零报警 —— wjj2 对比审核中的 1 号致命项
  C  报告"规范"列 spec 为空时渲染空白，evidence_source=missing 不可见
  E2 registry 声明 L1=17/L2=71，实际文件 L1=16/L2=72（CU-012 标错层）

用法：
    pytest scripts/test_design_zone.py -v
"""

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import data_quality_check as dqc  # noqa: E402


def _cfg_row(table: str, length) -> dict:
    """一行 CFG 桩记录（管道真实字段名）。"""
    return {"table": table, "桩位编号": "1", "有效桩长（m）": str(length)}


# ========== B：三重一致性（表头设计值 vs 分区名 vs 实际数据） ==========

class TestBDesignZoneConsistency:
    """DQ-DESIGN-ZONE-01/02/03：设计值·分区名·实际值三方对账。"""

    def test_fatal_header_vs_zone_vs_data(self):
        """表头5m + 分区名(8米) + 实际8m → 结构性矛盾（error）。

        分区名与实际数据互证、双双打脸表头设计值——正是 wjj2 审核
        立为 1 号致命项的场景，不得静默。
        """
        data = {
            "full_text": "设计桩长                5m",
            "structured_rows": [_cfg_row("MD-X1(8米)", v)
                                for v in (8.1, 8.2, 8.0, 7.9, 8.3)],
        }
        checker = dqc.DataQualityChecker(data)
        w = checker.check_design_zone_consistency()
        assert any(x["severity"] == "error" for x in w), f"三重矛盾未升 error: {w}"

    def test_clean_sheet_zero_fp(self):
        """干净表：设计5m 实际5.0~5.2 无分区名 → 零告警（H-7 同款铁律）。"""
        data = {
            "full_text": "设计桩长 5m",
            "structured_rows": [_cfg_row("NB", v)
                                for v in (5.0, 5.1, 5.2, 5.0, 5.1)],
        }
        checker = dqc.DataQualityChecker(data)
        assert checker.check_design_zone_consistency() == []

    def test_zone_name_only_mismatch_is_warning(self):
        """仅分区名(8米)与表头5m不符、数据≈5m自洽 → 命名问题（warning 非 error）。"""
        data = {
            "full_text": "设计桩长 5m",
            "structured_rows": [_cfg_row("MD-X1(8米)", v)
                                for v in (5.0, 5.1, 5.2, 4.9, 5.0)],
        }
        checker = dqc.DataQualityChecker(data)
        w = checker.check_design_zone_consistency()
        assert w and all(x["severity"] != "error" for x in w), \
            f"数据自洽的命名差异不得升 error: {w}"

    def test_fullwidth_paren_zone_tag(self):
        """全角括号分区名"MD-X7（8米）"同样要识别（真实文件两种括号混用）。"""
        data = {
            "full_text": "设计桩长 5m",
            "structured_rows": [_cfg_row("MD-X7（8米）", v)
                                for v in (7.9, 8.0, 8.1, 8.2, 8.0)],
        }
        checker = dqc.DataQualityChecker(data)
        w = checker.check_design_zone_consistency()
        assert any(x["severity"] == "error" for x in w), w

    def test_no_design_value_skip(self):
        """full_text 无设计桩长（如 OCR 丢失表头）→ 跳过不误报。"""
        data = {"structured_rows": [_cfg_row("MD-X1(8米)", 8.0)] * 5}
        checker = dqc.DataQualityChecker(data)
        assert checker.check_design_zone_consistency() == []

    def test_wired_into_run_all(self):
        """检查必须接入 run_all 主链路，否则永远不进报告。"""
        data = {
            "full_text": "设计桩长 5m",
            "structured_rows": [_cfg_row("MD-X1(8米)", v)
                                for v in (8.1, 8.2, 8.0, 7.9, 8.3)],
        }
        result = dqc.check(data)
        codes = [w["code"] for w in result.get("warnings", [])]
        assert any(c.startswith("DQ-DESIGN-ZONE") for c in codes), codes


# ========== C：报告"规范"列依据缺失不空白 ==========

class TestCRenderSpecCell:
    """run_audit.render_spec_cell：spec 空/missing 必须给出可见标记。"""

    def test_missing_evidence_marked(self):
        import run_audit
        html = run_audit.render_spec_cell({"spec": "", "evidence_source": "missing"})
        assert "依据缺失" in html and html.strip() != ""

    def test_unverified_spec_marked(self):
        """spec 有值但回填查不到原文 → 条款保留 + 未经核验警示（防幻觉条款混过）。"""
        import run_audit
        html = run_audit.render_spec_cell(
            {"spec": "MH/T 5078.1 6.2.7", "evidence_source": "missing"})
        assert "MH/T 5078.1 6.2.7" in html and "未经" in html

    def test_verified_spec_plain(self):
        import run_audit
        html = run_audit.render_spec_cell(
            {"spec": "MH/T 5078.1 6.2.7", "evidence_source": "references"})
        assert "MH/T 5078.1 6.2.7" in html and "⚠" not in html

    def test_empty_spec_no_source_marked(self):
        """legacy 日志无 evidence_source 字段：spec 空也要标记，不留白。"""
        import run_audit
        html = run_audit.render_spec_cell({"spec": ""})
        assert "依据" in html and html.strip() != ""


# ========== E2：registry 声明与规则文件对齐 ==========

class TestERegistryAligned:
    """registry by_level == 目录实际文件数；CU-012 归位 L2。"""

    @staticmethod
    def _load_registry() -> dict:
        return json.loads(
            (SKILL_DIR / "rules" / "registry.json").read_text(encoding="utf-8"))

    def test_registry_counts_match_files(self):
        reg = self._load_registry()
        actual = {}
        for layer in ("L1-iron", "L2-logic", "L3-business"):
            actual[layer.upper()] = len(
                list((SKILL_DIR / "rules" / layer).glob("*.json")))
        assert reg["by_level"] == actual, \
            f"registry 声明 {reg['by_level']} != 实际文件 {actual}"

    def test_cu012_level_l2(self):
        """CU-012 文件在 L2-logic/ 且自声明 L2-LOGIC，registry 不得标 L1。"""
        reg = self._load_registry()
        cu = [r for r in reg["rules"] if r["rule_id"] == "CU-012"]
        assert cu and cu[0]["level"] == "L2-LOGIC", cu

    def test_every_registry_file_exists(self):
        reg = self._load_registry()
        missing = [r["rule_id"] for r in reg["rules"]
                   if not (SKILL_DIR / "rules" / r["file"]).exists()]
        assert missing == [], f"registry 引用不存在的文件: {missing}"

    def test_no_orphan_rule_files(self):
        reg = self._load_registry()
        known = {r["rule_id"] for r in reg["rules"]}
        orphans = []
        for layer in ("L1-iron", "L2-logic", "L3-business"):
            for f in (SKILL_DIR / "rules" / layer).glob("*.json"):
                if f.stem not in known:
                    orphans.append(f"{layer}/{f.stem}")
        assert orphans == [], f"文件存在但 registry 缺条目: {orphans}"
