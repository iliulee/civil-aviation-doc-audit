# -*- coding: utf-8 -*-
"""
test_ocr_verify_upgrade.py — OCR 复核升级回归套件（v10.6 改造安全网）
==========================================================================
背景：OCR提升与跨平台改造方案（v2）三线改造的隐患登记。先红后绿：
     红表示隐患存在（当前代码有 bug/悬空），修复后变绿（销号），
     测试永久保留防复发。任何代码改动必须保证本套件全绿。

隐患清单（接 test_regression_hazards.py 的 H-1~H-8）：
  H-9  crop_and_verify 空壳 + 悬空（v10.6 销号）
      H-9a 空壳销号：未读回时不得假抬置信度（空壳返回 max(conf,0.70)），
          必须返回 0.55 + needs_host_review=True，且裁图真实落盘
      H-9b 读回闭环：宿主写 verify_results.json 后，同格再调必须合并真值
      H-9c 双闸门：置信度 < 0.985、"数字:数字"（如 0:8）、"m2/m3" 单位
          即使 1.0 置信也必须判可疑；正常值（0.8）必须放行
      H-9d 接线守卫：_ocr_single_image_rapidocr 源码中必须有对
          crop_and_verify 的真实调用（防"只改函数不接线"的悬空复发）
      H-9e 阈值常量：CROP_VERIFY_THRESH == 0.985
  H-10 文本层体检路由（v10.6 销号）
      H-10a probe_text_layer 存在且返回结构化路由结果（含 kind/action）
      H-10b 密度判定：纯文字版→text/direct_extract；纯扫描→scanned/ocr；
           "整本只有页码字"的空壳 PDF→scanned（防几个页码字误判文字版）
      H-10c 旧接口兼容：detect_scanned(pdf)->bool 薄包装仍可用
      H-10d 单一实现守卫：全 scripts 目录文本层判定只允许一处实现
  H-11 视觉能力探测与降级（v10.6 销号）
      H-11a vision_reviewer 模块存在，confirm_vision_capability 返回结构
      H-11b 四档降级正确：纯函数 resolve_review_level 四种组合各落对应档
      H-11c has_agent 硬编码移除：select_verify_path 默认参数改 None
           （探测），显式传 True/False 仍兼容（外部接口不变）
  H-12 缓存路径绕过复核（v10.6 销号，验收期查实）
      断点缓存命中分支曾直接返回 items——旧缓存无 cv 标记复核从未跑过，
      新缓存待宿主读回但重跑时真值永远合不上（缓存=复核盲区）
      H-12a 补复核生效：无 cv 标记的缓存 items 过 _cropverify_cached_page
           后必须带 cv 痕迹
      H-12b 接线守卫：ocr_pdf_rapidocr 缓存命中分支必须调
           _cropverify_cached_page（防删调用复发盲区）
  H-13 PDF 裁图坐标系塌缩（v10.6 销号，验收期查实）
      _crop_cell_image PDF 分支曾固定 2x(144dpi) 渲染，把 200dpi 的 bbox
      当 PDF 点用 → clamp 到页边区域塌缩 → 静默 False → 裁图全空。
      A/B 实验传 PNG 源（scale=1）没暴露，真实管道传 PDF 源才炸
      H-13a PDF 源 + 200dpi bbox → 裁图必须真实落盘（crop_image 非空）

用法：
    pytest scripts/test_ocr_verify_upgrade.py -v
"""

import sys
import inspect
import re as _re
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import ocr_image as oi


# ========== H-9：crop_and_verify 做真 + 接线 ==========

def _make_cell_png(tmp_path: Path, name: str = "cell.png") -> Path:
    """造一张白底小图当"页面原图"（crop_and_verify 只需可裁的位图）。"""
    from PIL import Image, ImageDraw

    p = tmp_path / name
    img = Image.new("RGB", (400, 300), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([120, 110, 280, 160], outline="black", width=2)
    d.text((130, 125), "0:8", fill="black")
    img.save(p, "PNG")
    return p


def _reset_batch_key():
    """批级根键是模块全局缓存，测试间必须清零（绕过 lock 直改）。"""
    oi._BATCH_ROOT_KEY = None
    if hasattr(oi, "_BATCH_ROOT_LOCK"):
        oi._BATCH_ROOT_LOCK = False


class TestH9CropVerifyReal:
    """H-9：crop_and_verify 必须是真实现且已接线。"""

    def test_h9a_no_fake_confidence(self, tmp_path):
        """H-9a：未读回时不得假抬置信度（空壳的 max(conf, 0.70) 即造假）。"""
        _reset_batch_key()
        png = _make_cell_png(tmp_path)
        v = oi.crop_and_verify(str(png), [120, 110, 280, 160], "0:8", 0.90, page=0)
        assert "needs_host_review" in v, "返回结构缺少 needs_host_review 字段（空壳实现）"
        assert v["needs_host_review"] is True, "宿主未读回时必须标记待复核"
        assert abs(float(v["verified_confidence"]) - 0.55) < 1e-9, (
            f"未读回复核置信度必须压到 0.55（当前={v['verified_confidence']}，"
            "空壳会假抬到 max(conf, 0.70) 造假通过）"
        )
        assert v.get("crop_image"), "裁图路径为空：没有真实裁图"
        assert Path(v["crop_image"]).is_file(), "裁图未落盘：crop 是假的"

    def test_h9b_host_readback_merges(self, tmp_path):
        """H-9b：宿主写回 verify_results.json 后，同格再调必须合并真值。"""
        _reset_batch_key()
        png = _make_cell_png(tmp_path)
        bbox = [120, 110, 280, 160]
        # 第一次：生成任务（未读回）
        v1 = oi.crop_and_verify(str(png), bbox, "0:8", 0.90, page=0)
        task_id = v1["task_id"]
        assert task_id, "读图任务 ID 为空：任务清单协议未生成"
        # 宿主 AI 读图回写（模拟）
        out = oi.write_cropverify_results(
            str(png),
            [{"task_id": task_id, "verified_value": "0.8", "confidence": "high"}],
        )
        assert out.is_file()
        # 第二次：同格重调，必须合并到真值
        _reset_batch_key()
        v2 = oi.crop_and_verify(str(png), bbox, "0:8", 0.90, page=0)
        assert v2["verified_text"] == "0.8", f"读回后未合并真值（当前={v2['verified_text']!r}）"
        assert v2["needs_host_review"] is False, "读回后不应再标待复核"
        assert v2["changed"] is True, "0:8 → 0.8 应记 changed=True"
        assert float(v2["verified_confidence"]) >= 0.85, "high 置信读回应 ≥0.85"

    def test_h9c_double_gates(self):
        """H-9c：双闸门——高置信错识也必须拦下，正常值放行。"""
        assert hasattr(oi, "_needs_review"), "模块级 _needs_review 闸门函数不存在（悬空未接线）"
        f = oi._needs_review
        # 冒号数字：RapidOCR 1.0 置信也是错识（0.8 读成 0:8）
        assert f({"text": "0:8", "confidence": 1.0}) is True, "数字:数字形态必须强制复核"
        assert f({"text": "8:03", "confidence": 0.9999}) is True
        # 单位错配：m2/m3 常为 m²/m³ 误读
        assert f({"text": "m2", "confidence": 1.0}) is True, "m2/m3 单位必须复核"
        assert f({"text": "灌入量(m3)", "confidence": 0.99}) is True
        # 低置信闸门
        assert f({"text": "20.0", "confidence": 0.50}) is True
        # 正常值放行（不得误杀）
        assert f({"text": "0.8", "confidence": 0.99}) is False, "正常小数不得误杀"
        assert f({"text": "Z-01", "confidence": 0.999}) is False
        assert f({"text": "20.0", "confidence": 0.996}) is False

    def test_h9d_wired_into_rapidocr_flow(self):
        """H-9d：_ocr_single_image_rapidocr 必须真实调用 crop_and_verify（防悬空复发）。"""
        src = inspect.getsource(oi._ocr_single_image_rapidocr)
        calls = [ln for ln in src.splitlines()
                 if "crop_and_verify(" in ln and "def " not in ln and "#" != ln.strip()[:1]]
        assert calls, "_ocr_single_image_rapidocr 未调用 crop_and_verify：改了函数没接线=白改"

    def test_h9e_threshold_constant(self):
        """H-9e：双闸门置信阈值锁定 0.985（实测校准值，防回调放宽）。"""
        assert getattr(oi, "CROP_VERIFY_THRESH") == 0.985


# ========== H-10：文本层体检路由 ==========

class TestH10TextLayerRouting:
    """H-10：extract_pdf 文本层探测升级（增强不新建）。"""

    @pytest.fixture(scope="class")
    def ex(self):
        import extract_pdf as ex_mod
        return ex_mod

    def _make_pdf(self, tmp_path, name: str, page_specs):
        """造测试 PDF：page_specs 每项 (文字 or None)。None=空白页（无文本层）。"""
        import fitz
        p = tmp_path / name
        doc = fitz.open()
        for text in page_specs:
            pg = doc.new_page()
            if text:
                pg.insert_text((72, 100), text, fontsize=12)
        doc.save(str(p))
        doc.close()
        return p

    def test_h10a_probe_text_layer_exists(self, ex):
        """H-10a：probe_text_layer 模块级存在，返回结构化路由结果。"""
        assert hasattr(ex, "probe_text_layer"), "extract_pdf 缺 probe_text_layer（体检路由未升级）"

    def test_h10b_density_routing(self, ex, tmp_path):
        """H-10b：密度判定——纯文字/纯扫描/页码字空壳三分流。"""
        # 纯文字版：2 页实文 → text / direct_extract
        text_pdf = self._make_pdf(tmp_path, "text.pdf",
                                  ["第一章 总则 为规范运输机场建设工程资料管理", "第二章 术语 本规程适用于运输机场"])
        r1 = ex.probe_text_layer(str(text_pdf))
        assert r1["kind"] == "text", f"纯文字版误判（{r1}）"
        assert r1["action"] == "direct_extract"
        # 纯扫描件：2 页空白（无文本层）→ scanned / ocr
        scan_pdf = self._make_pdf(tmp_path, "scan.pdf", [None, None])
        r2 = ex.probe_text_layer(str(scan_pdf))
        assert r2["kind"] == "scanned", f"纯扫描件误判（{r2}）"
        assert r2["action"] == "ocr"
        # 空壳 PDF：每页只有页码字（4 字×20 页=80 字 < 100）→ scanned
        hollow_pdf = self._make_pdf(tmp_path, "hollow.pdf", ["第%d页" % (i + 1) for i in range(20)])
        r3 = ex.probe_text_layer(str(hollow_pdf))
        assert r3["kind"] == "scanned", f"页码字空壳 PDF 不得判文字版（{r3}）"

    def test_h10c_detect_scanned_compat(self, ex, tmp_path):
        """H-10c：旧接口 detect_scanned(pdf)->bool 薄包装保留，不破坏调用方。"""
        text_pdf = self._make_pdf(tmp_path, "t2.pdf", ["充足文字内容" * 10])
        scan_pdf = self._make_pdf(tmp_path, "s2.pdf", [None, None])
        assert ex.detect_scanned(str(text_pdf)) is False
        assert ex.detect_scanned(str(scan_pdf)) is True

    def test_h10d_single_implementation(self):
        """H-10d：全 scripts 只允许一处文本层判定实现（防双套体检打架）。"""
        owners = []
        for f in SCRIPT_DIR.glob("*.py"):
            if f.name.startswith("test_"):
                continue
            try:
                src = f.read_text(encoding="utf-8")
            except Exception:
                continue
            if _re.search(r"def\s+(probe_text_layer|detect_scanned)\s*\(", src):
                owners.append(f.name)
        assert owners == ["extract_pdf.py"], (
            f"文本层判定实现必须只在 extract_pdf.py（当前出现在：{owners}，"
            "第二套实现=两套阈值打架=麻花）"
        )


# ========== H-11：视觉能力探测与降级 ==========

class TestH11VisionReviewer:
    """H-11：vision_reviewer 薄调度层 + has_agent 硬编码销号。"""

    def test_h11a_module_and_capability_probe(self):
        """H-11a：模块存在，confirm_vision_capability 返回结构化探测结果。"""
        import vision_reviewer as vr
        cap = vr.confirm_vision_capability()
        for key in ("host_agent_vision", "api", "level", "source"):
            assert key in cap, f"探测结果缺 {key} 字段"
        assert cap["level"] in ("host_agent", "api", "rule", "noop")

    def test_h11b_four_level_fallback(self):
        """H-11b：四档降级——资源组合必须各落对应档，不允许空等。"""
        import vision_reviewer as vr
        cases = [
            # (host, api) → 期望档位
            ({"host_agent_vision": True, "api": True}, "host_agent"),
            ({"host_agent_vision": True, "api": False}, "host_agent"),
            ({"host_agent_vision": False, "api": True}, "api"),
            ({"host_agent_vision": False, "api": False}, "rule"),  # 本地规则兜底优先于 noop
        ]
        for cap, want in cases:
            got = vr.resolve_review_level(cap)
            assert got == want, f"降级错误：{cap} 期望 {want}，实际 {got}"

    def test_h11c_has_agent_hardcode_removed(self):
        """H-11c：select_verify_path 默认参数不再硬编码 True（无视觉平台空等根因）。"""
        import verify_fields as vf
        sig = inspect.signature(vf.select_verify_path)
        default = sig.parameters["has_agent"].default
        assert default is None, (
            f"has_agent 默认值仍为 {default!r}：硬编码 True 导致无视觉宿主任务空等"
        )
        # 外部接口兼容：显式传参语义不变
        assert vf.select_verify_path(has_agent=True, has_api=False) == "agent"
        assert vf.select_verify_path(has_agent=False, has_api=True) == "api"
        # 默认（None）→ 走能力探测，不再无脑 agent
        got = vf.select_verify_path(has_agent=None, has_api=False)
        assert got in ("agent", "api", "rule"), f"None 时必须走探测（当前={got!r}）"


# ========== H-12：缓存路径不得绕过复核 ==========

class TestH12CachePathVerify:
    """H-12：断点缓存命中曾是复核盲区（旧缓存无 cv 标记、读回真值合不上）。"""

    def test_h12a_cached_items_get_reviewed(self, tmp_path):
        """H-12a：无 cv 标记的缓存 items 补复核后必须带 cv 痕迹。"""
        _reset_batch_key()
        png = _make_cell_png(tmp_path)
        # 旧版缓存形态：无任何 cv_/ai_reviewed 标记，含双闸门必拦的 0:8
        citems = [{"text": "0:8", "confidence": 1.0, "bbox": [120, 110, 280, 160], "page": 1}]
        out = oi._cropverify_cached_page(citems, str(png), 1)
        assert any(k.startswith("cv_") or k == "ai_reviewed" for k in out[0]), (
            "缓存 items 补复核后无 cv 痕迹：缓存路径仍是复核盲区"
        )
        assert abs(float(out[0]["confidence"]) - 0.55) < 1e-9, (
            "补复核未落待读态（置信应压 0.55）"
        )

    def test_h12b_cache_branch_wired(self):
        """H-12b：ocr_pdf_rapidocr 缓存命中分支必须调用 _cropverify_cached_page。"""
        src = inspect.getsource(oi.ocr_pdf_rapidocr)
        calls = [ln for ln in src.splitlines()
                 if "_cropverify_cached_page(" in ln and "def " not in ln and "#" != ln.strip()[:1]]
        assert calls, (
            "缓存命中分支未接补复核：缓存路径绕过 crop_and_verify（盲区复发）"
        )


# ========== H-13：PDF 裁图坐标系对齐 ==========

class TestH13PDFCropCoordinate:
    """H-13：PDF 源裁图坐标系塌缩（v10.6 销号，验收期查实）。

    _crop_cell_image PDF 分支曾固定 2x（144dpi）渲染，把 200dpi 的 bbox
    当 PDF 点用 → 坐标越界被 clamp 到页边 → 区域塌缩 → 静默 False。
    A/B 实验传 PNG 源（scale=1）没暴露，真实管道传 PDF 源才炸。
    """

    def test_h13a_pdf_bbox_crop_success(self, tmp_path):
        """H-13a PDF 源 + 200dpi bbox → 裁图必须真实落盘（crop_image 非空）。"""
        _reset_batch_key()
        import fitz

        # 造单页 PDF，在 (130,125) 起写入文本（PDF 点坐标）
        pdf = tmp_path / "test.pdf"
        doc = fitz.open()
        pg = doc.new_page()
        pg.insert_text((130, 125), "0:8", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        # 模拟 RapidOCR 输出 bbox（200dpi 坐标系：PDF 点 × 200/72 ≈ 2.78）
        scale = 200 / 72.0
        bbox = [120 * scale, 110 * scale, 280 * scale, 160 * scale]
        v = oi.crop_and_verify(str(pdf), bbox, "0:8", 0.90, page=0, bbox_dpi=200)
        assert v.get("crop_image"), "PDF 裁图路径为空：坐标系仍塌缩"
        assert Path(v["crop_image"]).is_file(), "PDF 裁图未落盘：_crop_cell_image 失败"
        # 裁图必须是有效非空位图（区域塌缩会得到近零像素或直接 False）
        from PIL import Image
        with Image.open(v["crop_image"]) as im:
            assert im.width > 8 and im.height > 8, (
                f"裁图尺寸异常（{im.width}x{im.height}）：区域被 clamp 塌缩"
            )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
