"""verify_skill_structure.py — SKILL.md v9.5 工作流清晰度验证脚本

检查 SKILL.md v9.5 优化后所有关键内容是否完整、结构是否正确。
用法: python scripts/verify_skill_structure.py
"""

import re
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
README_FILE = SKILL_DIR / "README.md"
PROJECT_SPEC = SKILL_DIR / "PROJECT_SPEC.md"
REFERENCES_DIR = SKILL_DIR / "references"


def read_file(path: Path) -> str:
    """读取文件，不存在则返回空字符串。"""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


class Checker:
    """验证检查器，逐条检查并记录结果。"""

    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

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


def check_skill_md_structure():
    """检查 SKILL.md 结构完整性。"""
    content = read_file(SKILL_MD)
    if not content:
        print("❌ SKILL.md 不存在或为空")
        return False

    c = Checker("SKILL.md 结构完整性")
    lines = content.splitlines()
    c.check(len(lines) <= 500, f"行数 ≤ 500（当前 {len(lines)} 行）")

    # 1. 路由表
    c.check("路由表" in content or "触发语句" in content, "存在路由表/触发语句章节")
    c.check("场景·审核流水线" in content, "存在「场景·审核流水线」章节")
    c.check("场景·规则管理" in content, "存在「场景·规则管理」章节")

    # 2. 强制闸门（含用户动作列）
    for gate in ["G-0", "G-1", "G-1.5", "G-1.9", "G-2"]:
        c.check(gate in content, f"闸门 {gate} 存在")
    c.check("用户动作" in content, "闸门表包含「用户动作」列")
    c.check("AI 恢复条件" in content, "闸门表包含「AI 恢复条件」列")

    # 3. Anti-Omission Protocol
    c.check("<thought_process>" in content, "存在 <thought_process> 前置检查协议")
    c.check("index.json 的存在性" in content, "thought_process 包含 index.json 检查")
    c.check("6 项前置信息" in content, "thought_process 包含 6 项前置信息检查")
    c.check("ocr_status" in content, "thought_process 包含 ocr_status 检查")
    c.check("human_verified" in content, "thought_process 包含 human_verified 检查")
    c.check("步骤 4/6/7" in content, "强制执行协议引用步骤 4/6/7")

    # 4. OCR 引擎策略
    for engine in ["auto", "rapidocr", "vision", "agent"]:
        c.check(engine in content, f"OCR 引擎选项「{engine}」存在")

    # 5. 三级输出格式
    c.check("Fatal" in content, "三级输出包含 Fatal")
    c.check("Sanity Check" in content or "Sanity" in content, "三级输出包含 Sanity Check")
    c.check("Best Practice" in content or "Best" in content, "三级输出包含 Best Practice")

    # 6. 核心铁律
    c.check("20 条" in content or "L1-IRON" in content or "L1-iron" in content, "核心铁律体系存在")

    # 7. 前置信息确认（在共享基础设施中）
    c.check("前置信息确认" in content, "前置信息确认章节存在")
    for item in ["stage", "nature", "scope", "ocr_engine", "special_notes", "check_signatures"]:
        c.check(item in content, f"前置信息项「{item}」存在")
    # 检查 engine 选择流程
    c.check("ocr_engine_source" in content, "引擎选择流程包含 ocr_engine_source 留痕字段")
    # 检查新 nature 取值（扫描转化电子文档）
    c.check("扫描转化电子文档" in content, "nature 新增取值「扫描转化电子文档」存在")

    # 8. 推断值生成规则
    c.check("推断值生成规则" in content, "推断值生成规则章节存在")
    c.check("数值型" in content, "推断值规则包含数值型场景")
    c.check("文本型" in content, "推断值规则包含文本型场景")
    c.check("签名类" in content, "推断值规则包含签名类场景")

    # 9. CLI 命令
    for cmd in ["build", "review", "report"]:
        c.check(cmd in content, f"CLI 命令「{cmd}」存在")

    # 10. 步骤编号（审核流水线：1~7 线性编号）
    for step in ["步骤 1", "步骤 2", "步骤 3", "步骤 4~7", "步骤 5", "步骤 6", "步骤 7"]:
        c.check(step in content, f"审核流水线步骤编号「{step}」存在")

    # 11. 原生模式（使用步骤编号）
    c.check("原生步骤 4" in content, "原生模式使用步骤 4 编号")
    c.check("原生步骤 5" in content, "原生模式使用步骤 5 编号")
    c.check("原生步骤 6~7" in content, "原生模式使用步骤 6~7 编号")

    # 12. 多 Agent
    c.check("多 Agent" in content or "并行" in content, "多 Agent 并行审核存在")

    # 13. 知识库与红线
    c.check("红线" in content, "知识库红线存在")

    # 14. 附录
    c.check("附录" in content or "CHANGELOG" in content or "版本" in content, "附录章节存在")

    # 15. 规则管理步骤化工作流
    c.check("步骤化工作流" in content, "规则管理存在步骤化工作流")
    c.check("规则浏览" in content, "规则管理第一步: 规则浏览")
    c.check("规则操作" in content, "规则管理第二步: 规则操作")
    c.check("规划中" in content, "规则管理第三/四步标记为规划中")

    # 16. 运行时进度展示（7 步）
    c.check("步骤 1 · 判定运行模式" in content, "进度条包含步骤 1")
    c.check("步骤 7 · 生成报告" in content, "进度条包含步骤 7")

    # 17. 禁忌检查：没有过时命名
    c.check("Route A" not in content, "不包含「Route A」命名（应为场景·）")
    c.check("Route B" not in content, "不包含「Route B」命名（应为场景·）")
    c.check("步骤 0" not in content, "不包含旧编号「步骤 0」")
    c.check("步骤 0.5" not in content, "不包含旧编号「步骤 0.5」")

    return c.summary()


def check_readme_consistency():
    """检查 README.md 与 SKILL.md 结构一致性。"""
    skill_content = read_file(SKILL_MD)
    readme_content = read_file(README_FILE)
    if not readme_content:
        print("  ⚠️  README.md 不存在，跳过检查")
        return True

    c = Checker("README.md 一致性")

    c.check("v9.5" in readme_content, "README 版本号 v9.5 存在")
    c.check("步骤 1~7" in readme_content, "README 包含步骤 1~7 描述")
    c.check("推断值生成规则" in readme_content, "README 包含推断值生成规则描述")
    c.check("步骤化工作流" in readme_content, "README 包含规则管理步骤化工作流描述")
    c.check("场景" in readme_content or "触发语句" in readme_content or "流水线" in readme_content,
            "README 包含场景/触发/流水线描述")

    engine_refs = readme_content.count("引擎模式")
    c.check(engine_refs <= 5, f"引擎模式引用次数 ≤ 5（当前 {engine_refs}）")

    return c.summary()


def check_project_spec_consistency():
    """检查 PROJECT_SPEC.md 与 SKILL.md 结构一致性。"""
    skill_content = read_file(SKILL_MD)
    spec_content = read_file(PROJECT_SPEC)
    if not spec_content:
        print("  ⚠️  PROJECT_SPEC.md 不存在，跳过检查")
        return True

    c = Checker("PROJECT_SPEC.md 一致性")

    c.check("v9.5" in spec_content, "版本号 v9.5 存在")
    c.check("步骤 1~7" in spec_content, "PROJECT_SPEC 包含步骤 1~7 描述")
    c.check("推断值生成规则" in spec_content, "PROJECT_SPEC 包含推断值生成规则描述")
    c.check("步骤化工作流" in spec_content, "PROJECT_SPEC 包含规则管理步骤化工作流描述")
    c.check("场景" in spec_content or "四阶段" in spec_content or "流水线" in spec_content,
            "包含场景/流水线/架构描述")

    return c.summary()


def check_references_completeness():
    """检查 references/ 目录完整性。"""
    if not REFERENCES_DIR.exists():
        print("  ⚠️  references/ 目录不存在，跳过检查")
        return True

    c = Checker("references/ 完整性")

    required_refs = [
        "skill-config-reference.md",
        "cli-reference.md",
        "CHANGELOG.md",
        "ocr-hybrid-architecture.md",
        "native-mode-checklist.md",
        "native-mode-stage1-checklist.md",
        "data-quality-patterns.md",
        "logic-conflict-patterns.md",
        "README.md",
    ]
    for ref in required_refs:
        ref_path = REFERENCES_DIR / ref
        c.check(ref_path.exists(), f"参考文件「{ref}」存在")

    skill_content = read_file(SKILL_MD)
    return c.summary()


def main():
    """主入口：运行所有检查。"""
    print("=" * 60)
    print("SKILL.md v9.5 工作流清晰度 — 全量验证")
    print("=" * 60)

    results = []

    print("\n📋 1. SKILL.md 结构完整性")
    print("-" * 40)
    results.append(check_skill_md_structure())

    print("\n📋 2. README.md 一致性")
    print("-" * 40)
    results.append(check_readme_consistency())

    print("\n📋 3. PROJECT_SPEC.md 一致性")
    print("-" * 40)
    results.append(check_project_spec_consistency())

    print("\n📋 4. references/ 完整性")
    print("-" * 40)
    results.append(check_references_completeness())

    total = len(results)
    passed = sum(results)
    print("\n" + "=" * 60)
    print(f"验证结果：{passed}/{total} 项全部通过"
          if all(results) else
          f"验证结果：{passed}/{total} 通过，{total - passed} 项有失败")
    print("=" * 60)

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())