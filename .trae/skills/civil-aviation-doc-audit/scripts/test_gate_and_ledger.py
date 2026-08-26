# -*- coding: utf-8 -*-
"""
test_gate_and_ledger.py — 出口闸门 + 纯电子表场景回归测试（防复发保险丝）

覆盖三个已查实根因：
  T1. G-0 闸门：无数据底座 → report 必须拒绝（exit 1）
  T2. 对账闸门：审核日志文件清单与底座不一致 → report 必须拒绝（exit 1）
  T3. --force 默认禁用：无环境变量时 review --force 必须拒绝（exit 1）
  T4. 纯电子表建底座：人造 xlsx build 后记录数准确（494 行表→494 条）
  T5. 验钞机：verify_report.py 对"报告数字与底座不符"的样例必须报不通过

测试数据全部为人造数据，不含任何真实项目信息。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
PY = sys.executable


def run(cmd: list, cwd=None, env=None):
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", cwd=cwd, env=env,
    )


@pytest.fixture()
def fake_project(tmp_path):
    """构造无底座的假项目（只有一个 xlsx + 一个空审核日志）。"""
    proj = tmp_path / "proj"
    (proj / "审核日志").mkdir(parents=True)
    (proj / "审核日志" / "AU-20260825-001_test.json").write_text(
        json.dumps({"audit_id": "AU-TEST", "files": {"audited": ["fake.xlsx"]},
                    "findings": []}, ensure_ascii=False), encoding="utf-8")
    yield proj


def test_g0_gate_rejects_report_without_foundation(fake_project):
    """T1：没有 index.json → report 必须拒绝，且提示走 build。"""
    r = run([PY, str(SCRIPTS / "run_audit.py"), "report", str(fake_project)])
    assert r.returncode != 0, "无底座出报告未被拒绝——G-0 闸门失效"
    assert "G-0" in r.stderr or "数据底座" in r.stderr, f"报错信息不明确: {r.stderr}"


def test_reconciliation_gate_rejects_mismatched_file_list(fake_project):
    """T2：底座 documents 与日志 audited 清单不一致 → 拒绝。"""
    out = fake_project / "数据底座"
    out.mkdir()
    (out / "index.json").write_text(json.dumps({
        "documents": [{"original_file": "a.xlsx"}, {"original_file": "b.xlsx"}]
    }, ensure_ascii=False), encoding="utf-8")
    r = run([PY, str(SCRIPTS / "run_audit.py"), "report", str(fake_project)])
    assert r.returncode != 0, "清单不一致未拦截——对账闸门失效"
    assert "对账闸门" in r.stderr, f"应提示对账闸门: {r.stderr}"


def test_force_disabled_by_default(fake_project):
    """T3：未设置 AUDIT_ALLOW_FORCE 时 --force 必须被拒绝。"""
    out = fake_project / "数据底座"
    out.mkdir(exist_ok=True)
    (out / "index.json").write_text(json.dumps({
        "documents": [{"original_file": "a.xlsx", "human_verified": False}]
    }, ensure_ascii=False), encoding="utf-8")
    r = run([PY, str(SCRIPTS / "review_audit.py"), str(fake_project), "--force"])
    assert r.returncode != 0, "--force 默认未被禁用"
    assert "AUDIT_ALLOW_FORCE" in (r.stderr + r.stdout), \
        f"应提示设置环境变量: {r.stderr}{r.stdout}"


def test_electronic_ledger_build_record_count(tmp_path):
    """T4：人造 xlsx（含一张 494 行的表）建底座后记录数必须准确。"""
    openpyxl = pytest.importorskip("openpyxl")
    proj = tmp_path / "proj2"
    proj.mkdir()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "NB(X1-X3)"
    ws.append(["桩号", "施工日期", "实长(m)", "电流(A)"])
    for i in range(1, 495):  # 494 行数据
        ws.append([f"X1-{i}", "2026-04-20", 8.5, 65])
    wb.save(proj / "test_ledger.xlsx")

    r = run([PY, str(SCRIPTS / "build_foundation.py"), str(proj)])
    idx = proj / "数据底座" / "index.json"
    assert idx.exists(), f"build 未产出 index.json: {r.stdout}{r.stderr}"
    index = json.loads(idx.read_text(encoding="utf-8"))
    docs = index.get("documents", [])
    assert docs, "底座 documents 为空"
    # 记录数核对：data_file rows 长度应为 494
    doc = docs[0]
    data_file = doc.get("data_file")
    assert data_file, "doc 缺 data_file"
    data = json.loads((idx.parent / data_file).read_text(encoding="utf-8"))
    rows = data.get("rows") or data.get("structured_rows") or []
    assert len(rows) == 494, f"494 行表被解析成 {len(rows)} 条——电子表漏行复发"


def test_verify_report_catches_bad_numbers(tmp_path):
    """T5：验钞机必须抓住'报告数字与底座不符'。"""
    proj = tmp_path / "proj3"
    out = proj / "数据底座"
    out.mkdir(parents=True)
    (out / "index.json").write_text(json.dumps({
        "documents": [{"original_file": "a.xlsx", "data_file": "a.json"}]
    }, ensure_ascii=False), encoding="utf-8")
    (out / "a.json").write_text(json.dumps(
        {"rows": [{"桩号": f"X-{i}"} for i in range(100)]}, ensure_ascii=False),
        encoding="utf-8")
    # 报告声称 31 条（底座 100 条）→ 必须报不通过
    (proj / "审核报告.html").write_text(
        "<html><body>共 1 份资料。a 表共 31 条记录。"
        "问题 FATAL-001：依据 MH/T 5078.1-2024 第 6.2.7 条。</body></html>",
        encoding="utf-8")
    r = run([PY, str(SCRIPTS / "verify_report.py"), str(proj)])
    assert r.returncode != 0, "验钞机未抓住记录数不符（31 vs 100）"
    assert "31" in (r.stdout + r.stderr)
