# -*- coding: utf-8 -*-
"""
signature_check.py — 签字一致性检测模块
========================================

功能：
  1. 从 PDF/扫描件页面中检测签字区域并裁剪签字图像
  2. 使用 pHash（感知哈希）+ SSIM（结构相似度）比对同一人不同文档的签字
  3. 管理签字特征库（gallery.json）
  4. 生成签字异常报告数据（含 base64 编码的对比图）

调用方式：
  from signature_check import SignatureChecker
  
  checker = SignatureChecker(data_base_dir)
  results = checker.check_all_signatures(index_docs, project_path)
  
前置条件：签字检查为可选项，仅在前置信息确认时选择"签字检查"才执行

依赖：
  - PyMuPDF (fitz): PDF 页面渲染
  - imagehash: pHash 计算
  - scikit-image: SSIM 计算
  - Pillow: 图像处理
  - numpy: 数组运算
"""

import base64
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import imagehash
    HAS_IMAGEHASH = True
except ImportError:
    HAS_IMAGEHASH = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from skimage.metrics import structural_similarity as ssim
    HAS_SSIM = True
except ImportError:
    HAS_SSIM = False


# ========== Constants ==========
SIGNATURE_KEYWORDS = [
    "签字", "签名", "施工员", "质检员", "监理工程师", "监理员",
    "项目经理", "技术负责人", "安全员", "总监", "专业监理",
    "施工负责人", "质量负责人", "项目技术负责人",
]

# Signature region: search right and below of the keyword
SIGNATURE_SEARCH_OFFSET_X = 0    # pixels right of keyword
SIGNATURE_SEARCH_OFFSET_Y = 0    # pixels below keyword  
SIGNATURE_SEARCH_WIDTH = 200     # search width
SIGNATURE_SEARCH_HEIGHT = 80     # search height

# Similarity thresholds
PHASH_THRESHOLD = 10             # Hamming distance threshold (lower = more similar)
SSIM_PASS_THRESHOLD = 0.85       # >= this = pass
SSIM_SUSPECT_THRESHOLD = 0.70    # >= this but < pass = suspect
# Below suspect = likely forgery

# Minimum ink density to consider as a signature (not blank)
MIN_INK_DENSITY = 0.02


class SignatureChecker:
    """签字一致性检测器"""
    
    def __init__(self, data_base_dir: Path):
        self.data_base = Path(data_base_dir)
        self.sig_dir = self.data_base / "_signatures"
        self.baseline_dir = self.sig_dir / "baseline"
        self.suspects_dir = self.sig_dir / "suspects"
        self.gallery_file = self.sig_dir / "gallery.json"
        
        # Create directories
        self.sig_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        self.suspects_dir.mkdir(parents=True, exist_ok=True)
        
        # Load or init gallery
        self.gallery = self._load_gallery()
        
        self.results: List[Dict[str, Any]] = []
    
    def _load_gallery(self) -> Dict[str, Any]:
        if self.gallery_file.exists():
            return json.loads(self.gallery_file.read_text(encoding="utf-8"))
        return {"signers": {}}
    
    def _save_gallery(self):
        self.gallery_file.write_text(
            json.dumps(self.gallery, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def check_all_signatures(
        self,
        docs: List[Dict[str, Any]],
        project_path: Path,
    ) -> List[Dict[str, Any]]:
        """
        对所有文档执行签字检测。
        
        Args:
            docs: index.json 中的 documents 数组
            project_path: 项目根目录
            
        Returns:
            签字异常列表，每项含:
            - signer: 签字人姓名
            - doc_id: 文档ID
            - doc_file: 源文件路径
            - page: 页码
            - similarity: 相似度
            - status: pass / suspect / likely_forgery
            - baseline_doc: 基准样本文档
            - compare_image_base64: 对比图(base64)
            - rule: 触发规则
        """
        if not HAS_FITZ:
            print("[signature_check] PyMuPDF 未安装，跳过签字检测", file=sys.stderr)
            return []
        
        if not HAS_PIL:
            print("[signature_check] Pillow 未安装，跳过签字检测", file=sys.stderr)
            return []
        
        print(f"\n🖋️  开始签字一致性检测...", file=sys.stderr)
        
        anomalies: List[Dict[str, Any]] = []
        
        for doc in docs:
            # Skip Excel and non-scanned docs without images
            if doc.get("data_format") == "excel_raw":
                continue
            if not doc.get("is_scanned") and doc.get("file_type") not in ("PDF", "IMAGE"):
                continue
            
            doc_id = doc.get("id", "")
            original_file = doc.get("original_file", "")
            file_path = project_path / original_file
            
            if not file_path.exists():
                continue
            
            # Extract signatures from this document
            sigs = self._extract_signatures(file_path, doc_id)
            
            for sig in sigs:
                signer = sig["signer"]
                if not signer:
                    continue
                
                result = self._compare_with_gallery(sig, doc)
                
                if result and result["status"] != "pass":
                    anomalies.append(result)
            
            # Save signatures to gallery
            for sig in sigs:
                signer = sig["signer"]
                if not signer:
                    continue
                self._add_to_gallery(sig, doc)
        
        self._save_gallery()
        
        print(f"   签字检测完成: {len(anomalies)} 个异常", file=sys.stderr)
        self.results = anomalies
        return anomalies
    
    def _extract_signatures(
        self,
        file_path: Path,
        doc_id: str,
    ) -> List[Dict[str, Any]]:
        """
        从 PDF/图片中提取签字区域。
        
        策略：
        1. 渲染每页为图像
        2. OCR 定位签字关键词位置
        3. 在关键词右侧/下方裁剪签字区域
        4. 检测是否有手写笔迹（ink density）
        """
        signatures: List[Dict[str, Any]] = []
        
        try:
            if file_path.suffix.lower() == ".pdf":
                doc = fitz.open(str(file_path))
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    # Search for signature keywords
                    for keyword in SIGNATURE_KEYWORDS:
                        rects = page.search_for(keyword)
                        for rect in rects:
                            # Expand search area to the right of the keyword
                            sig_rect = fitz.Rect(
                                rect.x1 + SIGNATURE_SEARCH_OFFSET_X,
                                rect.y0 + SIGNATURE_SEARCH_OFFSET_Y,
                                rect.x1 + SIGNATURE_SEARCH_OFFSET_X + SIGNATURE_SEARCH_WIDTH,
                                rect.y1 + SIGNATURE_SEARCH_OFFSET_Y + SIGNATURE_SEARCH_HEIGHT,
                            )
                            # Clip to page bounds
                            page_rect = page.rect
                            sig_rect = fitz.Rect(
                                max(sig_rect.x0, 0),
                                max(sig_rect.y0, 0),
                                min(sig_rect.x1, page_rect.width),
                                min(sig_rect.y1, page_rect.height),
                            )
                            
                            # Render the signature region
                            clip = sig_rect
                            matrix = fitz.Matrix(2, 2)  # 2x zoom
                            pix = page.get_pixmap(matrix=matrix, clip=clip)
                            
                            # Convert to PIL Image
                            img_data = pix.tobytes("png")
                            img = Image.open(io.BytesIO(img_data))
                            
                            # Check ink density
                            if not self._has_ink(img):
                                continue
                            
                            # Try to extract signer name from keyword context
                            signer = self._infer_signer_name(page, keyword, rect)
                            
                            # Save signature image
                            sig_filename = f"{doc_id}_p{page_num+1}_{signer or 'unknown'}.png"
                            sig_path = self.sig_dir / sig_filename
                            img.save(str(sig_path))
                            
                            signatures.append({
                                "signer": signer,
                                "doc_id": doc_id,
                                "page": page_num + 1,
                                "image_path": str(sig_path),
                                "image": img,
                                "keyword": keyword,
                            })
                
                doc.close()
            
            elif file_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".tiff"):
                # For image files, can't locate signatures precisely
                # Skip for now - would need OCR + layout analysis
                pass
                
        except Exception as e:
            print(f"  [!] 签字提取失败 {file_path.name}: {e}", file=sys.stderr)
        
        return signatures
    
    def _has_ink(self, img: "Image.Image") -> bool:
        """检测图像中是否有手写笔迹（非空白）。"""
        if not HAS_NUMPY:
            # Fallback: check if image is not mostly white
            gray = img.convert("L")
            pixels = list(gray.getdata())
            dark_count = sum(1 for p in pixels if p < 128)
            return dark_count / len(pixels) > MIN_INK_DENSITY
        
        arr = np.array(img.convert("L"))
        dark_ratio = (arr < 128).sum() / arr.size
        return dark_ratio > MIN_INK_DENSITY
    
    def _infer_signer_name(
        self,
        page: "fitz.Page",
        keyword: str,
        rect: "fitz.Rect",
    ) -> Optional[str]:
        """从关键词附近推断签字人姓名。"""
        # Try to find a name near the keyword
        # Search in a region below the keyword
        search_rect = fitz.Rect(
            rect.x0 - 50,
            rect.y1 + 5,
            rect.x1 + 100,
            rect.y1 + 30,
        )
        text = page.get_text("text", clip=search_rect).strip()
        
        # Clean up: remove common non-name characters
        text = re.sub(r'[：:（）\(\)签字签名日期年月日\s]+', '', text)
        
        # If text is 2-4 Chinese characters, likely a name
        if text and 2 <= len(text) <= 4 and re.match(r'^[\u4e00-\u9fff]+$', text):
            return text
        
        # If keyword itself contains a role, use that as signer identifier
        # This is a fallback - we don't know the actual name
        return None
    
    def _compute_phash(self, img: "Image.Image") -> Optional[str]:
        """计算图像的感知哈希。"""
        if not HAS_IMAGEHASH:
            return None
        h = imagehash.phash(img.convert("L").resize((32, 32)))
        return str(h)
    
    def _compute_ssim(
        self,
        img_a: "Image.Image",
        img_b: "Image.Image",
    ) -> Optional[float]:
        """计算两张图片的结构相似度。"""
        if not HAS_SSIM or not HAS_NUMPY:
            return None
        
        # Resize to same size
        size = (128, 64)
        a = np.array(img_a.convert("L").resize(size))
        b = np.array(img_b.convert("L").resize(size))
        
        return float(ssim(a, b, data_range=255))
    
    def _compare_with_gallery(
        self,
        sig: Dict[str, Any],
        doc: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """与签字特征库比对。"""
        signer = sig["signer"]
        signers = self.gallery.get("signers", {})
        
        if signer not in signers:
            # First appearance - becomes baseline
            return None
        
        baseline = signers[signer]
        baseline_path = self.sig_dir / baseline.get("baseline_file", "")
        if not baseline_path.exists():
            return None
        
        baseline_img = Image.open(str(baseline_path))
        current_img = sig["image"]
        
        # Compute similarity
        ssim_score = self._compute_ssim(baseline_img, current_img)
        if ssim_score is None:
            return None
        
        # Determine status
        if ssim_score >= SSIM_PASS_THRESHOLD:
            status = "pass"
        elif ssim_score >= SSIM_SUSPECT_THRESHOLD:
            status = "suspect"
        else:
            status = "likely_forgery"
        
        if status == "pass":
            return None  # No anomaly
        
        # Create comparison image (side by side)
        compare_img = self._create_comparison_image(baseline_img, current_img, signer, ssim_score)
        compare_b64 = self._image_to_base64(compare_img)
        
        # Save comparison image
        compare_filename = f"compare_{sig['doc_id']}_p{sig['page']}_{signer}.png"
        compare_path = self.suspects_dir / compare_filename
        compare_img.save(str(compare_path))
        
        return {
            "signer": signer,
            "role": baseline.get("role", ""),
            "doc_id": sig["doc_id"],
            "doc_file": doc.get("original_file", ""),
            "page": sig["page"],
            "similarity": round(ssim_score, 3),
            "status": status,
            "baseline_doc": baseline.get("baseline_doc", ""),
            "baseline_date": baseline.get("baseline_date", ""),
            "compare_image_base64": compare_b64,
            "compare_image_path": str(compare_path),
            "rule": "LG-304: 同一签字人在不同资料的笔迹一致",
            "suggestion": "调取原始纸质资料核对，或联系当事人确认签字真实性" if status == "likely_forgery" else "建议核实签字差异原因",
        }
    
    def _create_comparison_image(
        self,
        baseline: "Image.Image",
        current: "Image.Image",
        signer: str,
        similarity: float,
    ) -> "Image.Image":
        """创建左右对比图。"""
        from PIL import Image as PILImage, ImageDraw, ImageFont
        
        # Resize both to same height
        h = 100
        bw = int(baseline.width * h / baseline.height) if baseline.height > 0 else 200
        cw = int(current.width * h / current.height) if current.height > 0 else 200
        
        baseline_resized = baseline.resize((bw, h))
        current_resized = current.resize((cw, h))
        
        # Create canvas with labels
        gap = 20
        label_h = 30
        total_w = bw + gap + cw + 40
        total_h = h + label_h * 2 + 20
        
        canvas = PILImage.new("RGB", (total_w, total_h), "white")
        draw = ImageDraw.Draw(canvas)
        
        # Left: baseline
        canvas.paste(baseline_resized, (20, label_h + 10))
        draw.text((20, 5), f"基准样本: {signer}", fill="black")
        
        # Right: current
        canvas.paste(current_resized, (20 + bw + gap, label_h + 10))
        status_text = f"当前签字 (相似度: {similarity:.1%})"
        color = "red" if similarity < SSIM_SUSPECT_THRESHOLD else "orange"
        draw.text((20 + bw + gap, 5), status_text, fill=color)
        
        return canvas
    
    def _image_to_base64(self, img: "Image.Image") -> str:
        """将 PIL Image 转为 base64 字符串。"""
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    
    def _add_to_gallery(self, sig: Dict[str, Any], doc: Dict[str, Any]):
        """将签字添加到特征库。"""
        signer = sig["signer"]
        signers = self.gallery.setdefault("signers", {})
        
        if signer not in signers:
            # First occurrence - set as baseline
            baseline_filename = f"{signer}_{sig.get('keyword', 'sig')}.png"
            baseline_path = self.baseline_dir / baseline_filename
            sig["image"].save(str(baseline_path))
            
            phash = self._compute_phash(sig["image"])
            
            signers[signer] = {
                "role": sig.get("keyword", ""),
                "baseline_file": f"baseline/{baseline_filename}",
                "baseline_phash": phash,
                "baseline_doc": sig["doc_id"],
                "baseline_date": doc.get("last_updated", ""),
                "appearances": [{
                    "doc": sig["doc_id"],
                    "page": sig["page"],
                    "file": str(sig["image_path"]),
                    "similarity": 1.0,
                    "status": "baseline",
                }],
            }
        else:
            # Add appearance
            appearances = signers[signer].setdefault("appearances", [])
            phash = self._compute_phash(sig["image"])
            
            # Compute similarity with baseline
            baseline_file = signers[signer].get("baseline_file", "")
            baseline_path = self.sig_dir / baseline_file
            similarity = 0.0
            if baseline_path.exists():
                baseline_img = Image.open(str(baseline_path))
                similarity = self._compute_ssim(baseline_img, sig["image"]) or 0.0
            
            status = "pass"
            if similarity < SSIM_SUSPECT_THRESHOLD:
                status = "likely_forgery"
            elif similarity < SSIM_PASS_THRESHOLD:
                status = "suspect"
            
            appearances.append({
                "doc": sig["doc_id"],
                "page": sig["page"],
                "file": str(sig["image_path"]),
                "similarity": round(similarity, 3),
                "status": status,
            })
    
    def get_results(self) -> List[Dict[str, Any]]:
        """获取检测结果。"""
        return self.results


# ========== CLI entry point ==========
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="签字一致性检测")
    parser.add_argument("project_path", help="项目文件夹路径")
    parser.add_argument("--data-base", default="数据底座", help="数据底座目录名")
    args = parser.parse_args()
    
    project_path = Path(args.project_path).resolve()
    data_base = project_path / args.data_base
    index_path = data_base / "index.json"
    
    if not index_path.exists():
        print(f"❌ 未找到 index.json: {index_path}", file=sys.stderr)
        sys.exit(1)
    
    index = json.loads(index_path.read_text(encoding="utf-8"))
    docs = index.get("documents", [])
    
    checker = SignatureChecker(data_base)
    results = checker.check_all_signatures(docs, project_path)
    
    # Save results
    results_file = data_base / "signature_results.json"
    results_file.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    print(f"\n✅ 签字检测完成: {len(results)} 个异常", file=sys.stderr)
    print(f"   结果已保存: {results_file}", file=sys.stderr)
    
    if results:
        print(f"\n异常清单:", file=sys.stderr)
        for r in results:
            print(f"   - {r['signer']} ({r['status']}): {r['doc_file']} 第{r['page']}页, 相似度={r['similarity']:.1%}", file=sys.stderr)
