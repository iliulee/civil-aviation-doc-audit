# -*- coding: utf-8 -*-
"""
PLAN v2.0 实施验收脚本
====================

检查 Phase 1 所有任务是否按要求完成。

用法：
    python scripts/verify_plan_v2.py
"""

import json
import os
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SKILL_DIR.parent.parent.parent  # 项目根目录


def read_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


class Checker:
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors = []

    def check(self, condition: bool, msg: str):
        if condition:
            self.passed += 1
            print(f"  ✅ {msg}")
        else:
            self.failed += 1
            self.errors.append(msg)
            print(f"  ❌ {msg}")

    def summary(self) -> bool:
        total = self.passed + self.failed
        print(f"\n  [{self.name}] {self.passed}/{total} 通过")
        if self.errors:
            print(f"  ❌ 失败项 ({self.failed}):")
            for e in self.errors:
                print(f"     - {e}")
        return self.failed == 0


# ========== 任务 3：同步脚本清理 ==========

def check_task3():
    c = Checker("任务 3：同步脚本清理")

    # 3.1 旧 .ps1 是否已删除
    deleted_ps1 = [
        "同步内部路由到安装版.ps1",
        "同步缺失文件到安装版.ps1",
        "同步run_audit到安装版.ps1",
        "同步SKILL引擎选择到安装版.ps1",
        "同步bug修复到安装版.ps1",
        "同步引擎选择到安装版.ps1",
        "同步修复build_foundation到安装版.ps1",
        "同步优化3项到安装版.ps1",
        "同步精简SKILL到安装版.ps1",
        "同步到安装版.ps1",
        "_同步3个差异文件.ps1",
        "install.ps1",
    ]
    for f in deleted_ps1:
        fp = ROOT_DIR / f
        c.check(not fp.exists(), f"旧 .ps1 已删除: {f}")

    # 3.2 同步 .bat 是否存在且有关注
    bat_path = ROOT_DIR / "同步内部路由到安装版.bat"
    c.check(bat_path.exists(), "同步 .bat 文件存在")
    if bat_path.exists():
        content = read_file(bat_path)
        c.check("唯一同步入口" in content, "同步 .bat 有文件头注释")

    # 3.3 rule-manager.bat 保留
    c.check((ROOT_DIR / "rule-manager.bat").exists(), "rule-manager.bat 保留")

    return c.summary()


# ========== 任务 6：版本号统一 ==========

def check_task6():
    c = Checker("任务 6：版本号统一")

    # 6.1 SKILL.md 标题
    skill = read_file(SKILL_DIR / "SKILL.md")
    c.check("v9.5" in skill.split("\n")[5] if skill else "", "SKILL.md 标题为 v9.5")

    # 6.2 README.md
    readme = read_file(SKILL_DIR / "README.md")
    c.check("v9.5" in readme[:200] if readme else "", "README.md 标记 v9.5")

    # 6.3 PROJECT_SPEC.md
    spec = read_file(SKILL_DIR / "PROJECT_SPEC.md")
    c.check("v9.5" in spec[:200] if spec else "", "PROJECT_SPEC.md 标记 v9.5")

    # 6.4 CHANGELOG.md 有 v9.5 条目
    changelog = read_file(SKILL_DIR / "references" / "CHANGELOG.md")
    c.check("## v9.5" in changelog if changelog else "", "CHANGELOG.md 有 v9.5 条目")

    return c.summary()


# ========== 任务 1：推荐值规则独立化 ==========

def check_task1():
    c = Checker("任务 1：推荐值规则独立化")

    # 1.1 inference_rules.json 存在
    rules_json = SKILL_DIR / "rules" / "inference_rules.json"
    c.check(rules_json.exists(), "inference_rules.json 存在")
    if rules_json.exists():
        rules = read_json(rules_json)
        rule_list = rules.get("rules", [])
        rule_ids = [r.get("id", "") for r in rule_list]
        c.check(len(rule_ids) >= 7, f"规则数量 ≥ 7 条（当前 {len(rule_ids)} 条）")
        c.check("INF-001" in rule_ids, "INF-001 存在（实长=顶-底）")
        c.check("INF-002" in rule_ids, "INF-002 存在（桩顶=底+实长）")
        c.check("INF-003" in rule_ids, "INF-003 存在（桩底=顶-实长）")
        c.check("INF-004" in rule_ids, "INF-004 存在（充盈系数）")
        c.check("INF-005" in rule_ids, "INF-005 存在（灌入量）")
        c.check("INF-006" in rule_ids, "INF-006 存在（碎石桩时长）")
        c.check("INF-007" in rule_ids, "INF-007 存在（垫层厚度）")
        c.check("confidence_color_map" in rules, "置信度颜色映射表存在")

        # 检查每条规则的必要字段
        for r in rule_list:
            rid = r.get("id", "?")
            c.check("type" in r, f"{rid} 有 type 字段")
            c.check("condition" in r, f"{rid} 有 condition 字段")
            c.check("formula" in r, f"{rid} 有 formula 字段")
            c.check("base_confidence" in r, f"{rid} 有 base_confidence 字段")
            c.check("cascade_penalty" in r, f"{rid} 有 cascade_penalty 字段")

    # 1.2 data_quality_check.py 改造
    dq = read_file(SKILL_DIR / "scripts" / "data_quality_check.py")
    c.check("_load_inference_rules" in dq if dq else "", "data_quality_check.py 有 _load_inference_rules()")
    c.check("_apply_rule" in dq if dq else "", "data_quality_check.py 有 _apply_rule()")
    c.check("inference_rules.json" in dq if dq else "", "data_quality_check.py 引用 inference_rules.json")
    c.check("cascade_penalty" in dq if dq else "", "置信度计算含 cascade_penalty")

    # 1.3 build_foundation.py 改造
    bf = read_file(SKILL_DIR / "scripts" / "build_foundation.py")
    c.check("low_confidence" in bf if bf else "", "build_foundation.py 输出 low_confidence 标记")

    # 1.4 SKILL.md 更新
    skill = read_file(SKILL_DIR / "SKILL.md")
    c.check("inference_rules.json" in skill if skill else "", "SKILL.md 引用 inference_rules.json")

    # 1.5 PROJECT_SPEC 更新
    spec = read_file(SKILL_DIR / "PROJECT_SPEC.md")
    c.check("inference_rules.json" in spec if spec else "", "PROJECT_SPEC.md 引用 inference_rules.json")

    # 1.6 CHANGELOG 更新
    changelog = read_file(SKILL_DIR / "references" / "CHANGELOG.md")
    c.check("inference_rules.json" in changelog if changelog else "", "CHANGELOG.md 记录 inference_rules.json")

    return c.summary()


# ========== 任务 2：手写体混合型文档优化 ==========

def check_task2():
    c = Checker("任务 2：手写体混合型文档优化")

    # 2.1 crop_and_verify 存在
    ocr_img = read_file(SKILL_DIR / "scripts" / "ocr_image.py")
    c.check("crop_and_verify" in ocr_img if ocr_img else "", "ocr_image.py 有 crop_and_verify()")

    # 2.2 build_foundation.py 有低置信复核步骤
    bf = read_file(SKILL_DIR / "scripts" / "build_foundation.py")
    c.check("ai_reviewed" in bf if bf else "", "build_foundation.py 有 ai_reviewed 标记")

    # 2.3 ocr-hybrid-architecture.md 更新
    arch = read_file(SKILL_DIR / "references" / "ocr-hybrid-architecture.md")
    c.check("crop_and_verify" in arch if arch else "", "ocr-hybrid-architecture.md 引用 crop_and_verify")

    return c.summary()


# ========== 任务 4：增量对比清单 + 保护机制 ==========

def check_task4():
    c = Checker("任务 4：增量保护")

    bf = read_file(SKILL_DIR / "scripts" / "build_foundation.py")
    c.check("incremental_added_at" in bf if bf else "", "build_foundation.py 有 incremental_added_at")
    c.check("incremental_from" in bf if bf else "", "build_foundation.py 有 incremental_from 标记")

    skill = read_file(SKILL_DIR / "SKILL.md")
    c.check("对比清单" in skill if skill else "", "SKILL.md 包含增量对比清单描述")

    return c.summary()


# ========== 任务 5：统一测试体系 ==========

def check_task5():
    c = Checker("任务 5：统一测试体系")

    # 5.1 run_all_tests.py 存在
    runner = SKILL_DIR / "scripts" / "run_all_tests.py"
    c.check(runner.exists(), "run_all_tests.py 存在")
    if runner.exists():
        content = read_file(runner)
        c.check("test_rule_engine" in content, "集成 test_rule_engine")
        c.check("test_ocr_routing" in content, "集成 test_ocr_routing")
        c.check("test_data_foundation" in content, "集成 test_data_foundation")
        c.check("test_inferred_values" in content, "集成 test_inferred_values")

    # 5.2 test_data_foundation.py 存在
    c.check((SKILL_DIR / "scripts" / "test_data_foundation.py").exists(), "test_data_foundation.py 存在")

    # 5.3 test_inferred_values.py 存在
    c.check((SKILL_DIR / "scripts" / "test_inferred_values.py").exists(), "test_inferred_values.py 存在")

    return c.summary()


# ========== 汇总 ==========

def main():
    print("=" * 60)
    print("PLAN v2.0 实施验收")
    print("=" * 60)
    print(f"Skill 目录: {SKILL_DIR}")
    print(f"项目根目录: {ROOT_DIR}")
    print()

    results = [
        ("任务 3：同步脚本清理", check_task3()),
        ("任务 6：版本号统一", check_task6()),
        ("任务 1：推荐值规则独立化", check_task1()),
        ("任务 2：手写体混合型文档优化", check_task2()),
        ("任务 4：增量保护", check_task4()),
        ("任务 5：统一测试体系", check_task5()),
    ]

    print("\n" + "=" * 60)
    print("验收汇总")
    print("=" * 60)
    total = len(results)
    passed = sum(1 for _, r in results if r)
    for name, r in results:
        status = "✅" if r else "❌"
        print(f"  {status} {name}")

    print(f"\n  总体: {passed}/{total} 项通过")
    if passed < total:
        print("  ❌ 有未通过项，请对照 CHECKLIST_v2.0.md 逐项修复")
        sys.exit(1)
    else:
        print("  ✅ 全部通过，可以同步到安装版")
        print("  📋 同步命令: & \"同步内部路由到安装版.bat\"")
        sys.exit(0)


if __name__ == "__main__":
    main()