# -*- coding: utf-8 -*-
"""
feedback_analyzer.py — LLM 反馈分析管道
=========================================

职责（Phase C-3）：
  1. 加载 status=new 的反馈
  2. 向量化（embedding 或 TF-IDF / Jaccard 降级）
  3. 聚类（DBSCAN 或贪心聚类降级）
  4. 对每类调用 LLM 或规则化模板提取共性模式
  5. 生成候选规则 JSON（status=incubating）写入 rules/custom/incubator/
  6. 更新反馈 status=analyzed, cluster_id
  7. 输出分析报告到 rules/reflections/feedback-analysis-{日期}.md

设计参考：specs/design-rule-management-subsystem/spec.md 第 7.2 节
依赖：Python 3.8+ 标准库；可选 sentence-transformers / sklearn / jsonschema

降级策略：
  - LLM：优先调用 OpenAI 风格 API（LLM_API_URL / LLM_API_KEY）；
    不可用时回退到规则化模板分析（基于反馈类型/字段/严重度统计）。
  - Embedding：优先 sentence-transformers（all-MiniLM-L6-v2）；
    不可用 → sklearn TfidfVectorizer；再不可用 → Jaccard 关键词集合。
  - Clustering：优先 sklearn.cluster.DBSCAN；
    不可用 → 基于相似度阈值的贪心聚类。

用法：
    python scripts/feedback_analyzer.py                   # 立即分析（min_feedback=3）
    python scripts/feedback_analyzer.py --min-feedback 20 # 仅当 new 反馈≥20 时触发
    python scripts/feedback_analyzer.py --dry-run         # 仅输出报告，不写候选规则/不更新状态
    python scripts/feedback_analyzer.py --auto-threshold  # C-4.1：达到 20 条自动触发，否则跳过
"""

import argparse
import json
import logging
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 路径与模块导入
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from feedback_store import FeedbackStore, now_iso, today_str  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
DEFAULT_FEEDBACKS_DIR = SKILL_ROOT / "feedbacks"
DEFAULT_RULES_DIR = SKILL_ROOT / "rules"
INCUBATOR_DIR = DEFAULT_RULES_DIR / "custom" / "incubator"
REFLECTIONS_DIR = DEFAULT_RULES_DIR / "reflections"

# 中国时区（+08:00）
CST = timezone(timedelta(hours=8))

# 自动触发阈值（C-4.1）
AUTO_TRIGGER_THRESHOLD = 20

# 默认聚类参数
DEFAULT_EPS = 0.3
DEFAULT_MIN_SAMPLES = 3
DEFAULT_JACCARD_THRESHOLD = 0.7  # 贪心聚类：Jaccard ≥ 0.7 视为同类

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 可选依赖检测
# ---------------------------------------------------------------------------
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

try:
    from sklearn.cluster import DBSCAN  # type: ignore
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _today_compact() -> str:
    """返回 YYYYMMDD 格式日期（用于 rule_id / 文件名）。"""
    return datetime.now(CST).strftime("%Y%m%d")


def _today_dash() -> str:
    """返回 YYYY-MM-DD 格式日期（用于报告文件名）。"""
    return datetime.now(CST).strftime("%Y-%m-%d")


def _tokenize(text: str) -> set:
    """简易中英文分词：英文按非字母数字切分，中文按字符切分。

    返回小写 token 集合（用于 Jaccard 相似度）。
    """
    if not text:
        return set()
    text = text.lower()
    # 中文按单字 + 英文/数字按词
    tokens: set = set()
    # 提取英文/数字词
    for m in re.findall(r"[a-z0-9]+", text):
        if len(m) >= 2:
            tokens.add(m)
    # 提取中文字符（按 2-gram 提升语义）
    cn_chars = re.findall(r"[\u4e00-\u9fff]", text)
    for i in range(len(cn_chars) - 1):
        tokens.add(cn_chars[i] + cn_chars[i + 1])
    # 单字也加入（避免短文本漏掉）
    for ch in cn_chars:
        tokens.add(ch)
    return tokens


def jaccard_similarity(a: set, b: set) -> float:
    """Jaccard 相似度：|A∩B| / |A∪B|。空集返回 0。"""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _cosine_similarity(vec_a, vec_b) -> float:
    """计算两个向量的余弦相似度（接受 list 或 numpy array）。"""
    try:
        import math
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# FeedbackAnalyzer — 主分析管道
# ---------------------------------------------------------------------------
class FeedbackAnalyzer:
    """LLM 反馈分析管道。

    通过构造函数配置反馈目录、规则目录与 LLM 参数；
    analyze() 执行完整管道：加载 → 向量化 → 聚类 → 模式提取 → 候选规则 → 报告。
    """

    def __init__(
        self,
        feedbacks_dir: Path = DEFAULT_FEEDBACKS_DIR,
        rules_dir: Path = DEFAULT_RULES_DIR,
        llm_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.feedbacks_dir = Path(feedbacks_dir)
        self.rules_dir = Path(rules_dir)
        self.incubator_dir = self.rules_dir / "custom" / "incubator"
        self.reflections_dir = self.rules_dir / "reflections"
        self.store = FeedbackStore(self.feedbacks_dir)

        self.llm_config = llm_config or {}

        # 检测可用后端
        self.embedding_backend = self._detect_embedding_backend()
        self.clustering_backend = self._detect_clustering_backend()
        self.llm_backend = self._detect_llm_backend()

    # ===== 后端检测 =====
    def _detect_embedding_backend(self) -> str:
        """检测可用的向量化后端。

        优先级：sentence-transformers > sklearn-tfidf > jaccard
        """
        if HAS_SENTENCE_TRANSFORMERS:
            return "sentence-transformers"
        if HAS_SKLEARN:
            return "sklearn-tfidf"
        return "jaccard"

    def _detect_clustering_backend(self) -> str:
        """检测可用的聚类后端：sklearn > greedy。"""
        if HAS_SKLEARN:
            return "sklearn"
        return "greedy"

    def _detect_llm_backend(self) -> str:
        """检测可用的 LLM 后端：api > template。"""
        api_url = self.llm_config.get("api_url") or os.environ.get("LLM_API_URL")
        api_key = self.llm_config.get("api_key") or os.environ.get("LLM_API_KEY")
        if api_url and api_key:
            return "api"
        return "template"

    # ===== 主流程 =====
    def analyze(
        self,
        min_feedback: int = DEFAULT_MIN_SAMPLES,
        dry_run: bool = False,
        eps: float = DEFAULT_EPS,
        min_samples: int = DEFAULT_MIN_SAMPLES,
    ) -> Dict[str, Any]:
        """执行完整分析管道。

        Args:
            min_feedback: 触发分析所需的最小 new 反馈数
            dry_run: True 时仅生成报告，不写候选规则、不更新反馈状态
            eps: DBSCAN 邻域半径（cosine 度量）
            min_samples: DBSCAN 核心点最小邻居数

        Returns:
            分析结果摘要字典
        """
        # 1. 加载 new 反馈
        new_feedbacks = self.store.list_new()
        if len(new_feedbacks) < min_feedback:
            logger.info(
                "反馈不足 %d 条（当前 %d 条），跳过分析",
                min_feedback, len(new_feedbacks),
            )
            return {
                "status": "skipped",
                "reason": f"new 反馈不足 {min_feedback} 条（当前 {len(new_feedbacks)} 条）",
                "total_feedbacks": len(new_feedbacks),
                "embedding_backend": self.embedding_backend,
                "clustering_backend": self.clustering_backend,
                "llm_backend": self.llm_backend,
            }

        # 2. 向量化
        texts = [self._feedback_to_text(f) for f in new_feedbacks]
        vectors, vec_mode = self._vectorize(texts)

        # 3. 聚类
        clusters = self._cluster(vectors, vec_mode, eps=eps, min_samples=min_samples)
        # clusters: {cluster_id: [feedback_indices]}，cluster_id=-1 表示噪声

        # 4. 对每类提取模式 + 生成候选规则
        candidate_rules: List[Dict[str, Any]] = []
        cluster_summaries: List[Dict[str, Any]] = []
        analyzed_feedback_ids: List[str] = []

        # 排序 cluster_id（-1 排最后）
        sorted_cluster_ids = sorted(
            clusters.keys(),
            key=lambda x: (x == -1, x),
        )

        cluster_seq = 0  # 用于生成 CL-NNN 编号（仅有效聚类）
        for cluster_id in sorted_cluster_ids:
            indices = clusters[cluster_id]
            if cluster_id == -1:
                # 噪声点：不生成候选规则，保持 new 状态
                continue

            cluster_seq += 1
            cluster_label = f"CL-{cluster_seq:03d}"
            cluster_feedbacks = [new_feedbacks[i] for i in indices]

            # 提取共性模式
            try:
                pattern = self._extract_pattern(cluster_feedbacks)
            except Exception as e:
                logger.warning("提取模式失败 (cluster=%s): %s", cluster_label, e)
                pattern = {
                    "type": "unknown",
                    "description": f"模式提取失败：{e}",
                    "common_fields": [],
                }

            # 生成候选规则
            candidate = self._generate_candidate_rule(
                cluster_seq, cluster_feedbacks, pattern
            )
            candidate_rules.append(candidate)

            cluster_summaries.append({
                "cluster_id": cluster_label,
                "size": len(indices),
                "pattern": pattern,
                "feedbacks": [f["feedback_id"] for f in cluster_feedbacks],
                "candidate_rule_id": candidate["rule_id"],
            })

            # 更新反馈状态
            if not dry_run:
                for fb in cluster_feedbacks:
                    try:
                        self.store.update_status(
                            fb["feedback_id"],
                            status="analyzed",
                            cluster_id=cluster_label,
                        )
                        analyzed_feedback_ids.append(fb["feedback_id"])
                    except Exception as e:
                        logger.warning(
                            "更新反馈状态失败 %s: %s", fb["feedback_id"], e
                        )

        # 5. 写入候选规则
        written_candidates: List[Dict[str, Any]] = []
        if not dry_run:
            for candidate in candidate_rules:
                try:
                    fp = self._write_candidate_rule(candidate)
                    written_candidates.append({
                        "rule_id": candidate["rule_id"],
                        "file": str(fp.relative_to(self.rules_dir).as_posix()),
                    })
                except Exception as e:
                    logger.warning("写入候选规则失败 %s: %s", candidate["rule_id"], e)

        # 6. 生成分析报告
        noise_count = len(clusters.get(-1, []))
        report = self._generate_report(
            new_feedbacks, clusters, cluster_summaries,
            candidate_rules, noise_count, dry_run,
        )
        report_path = self._write_report(report)

        result = {
            "status": "completed",
            "dry_run": dry_run,
            "total_feedbacks": len(new_feedbacks),
            "total_clusters": len([c for c in clusters if c != -1]),
            "noise_count": noise_count,
            "total_candidates": len(candidate_rules),
            "written_candidates": len(written_candidates),
            "analyzed_feedbacks": len(analyzed_feedback_ids),
            "report_path": str(report_path),
            "embedding_backend": self.embedding_backend,
            "clustering_backend": self.clustering_backend,
            "llm_backend": self.llm_backend,
            "cluster_summaries": cluster_summaries,
        }
        logger.info("分析完成：%s", json.dumps({k: v for k, v in result.items()
                                                  if k != "cluster_summaries"}, ensure_ascii=False))
        return result

    # ===== 文本构造与向量化 =====
    def _feedback_to_text(self, feedback: Dict[str, Any]) -> str:
        """将反馈转为文本（用于向量化）。"""
        ui = feedback.get("user_input") or {}
        ctx = feedback.get("context") or {}
        parts = [
            str(ui.get("summary") or ""),
            str(ui.get("suggested_rule_description") or ""),
            str(ctx.get("field") or ""),
            str(ctx.get("field_value") or ""),
            str(ctx.get("doc_file") or ""),
            str(feedback.get("type") or ""),
            str(feedback.get("rule_id") or ""),
        ]
        return " ".join(p for p in parts if p)

    def _vectorize(self, texts: List[str]) -> Tuple[Any, str]:
        """向量化（多后端降级）。

        Returns:
            (vectors, mode) — mode 为 'dense' / 'tfidf' / 'jaccard'
        """
        if self.embedding_backend == "sentence-transformers":
            try:
                model = SentenceTransformer("all-MiniLM-L6-v2")
                vecs = model.encode(texts)
                return vecs, "dense"
            except Exception as e:
                logger.warning("sentence-transformers 加载失败，降级到 tfidf: %s", e)
                self.embedding_backend = "sklearn-tfidf" if HAS_SKLEARN else "jaccard"

        if self.embedding_backend == "sklearn-tfidf":
            try:
                vec = TfidfVectorizer()
                matrix = vec.fit_transform(texts)
                return matrix.toarray(), "tfidf"
            except Exception as e:
                logger.warning("TF-IDF 向量化失败，降级到 jaccard: %s", e)
                self.embedding_backend = "jaccard"

        # Jaccard 降级：返回关键词集合列表
        token_sets = [_tokenize(t) for t in texts]
        return token_sets, "jaccard"

    # ===== 聚类 =====
    def _cluster(
        self,
        vectors: Any,
        vec_mode: str,
        eps: float = DEFAULT_EPS,
        min_samples: int = DEFAULT_MIN_SAMPLES,
    ) -> Dict[int, List[int]]:
        """聚类（多后端降级）。

        Returns:
            {cluster_id: [feedback_indices]}，cluster_id=-1 为噪声点
        """
        if self.clustering_backend == "sklearn" and vec_mode in ("dense", "tfidf"):
            try:
                db = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine")
                labels = db.fit_predict(vectors)
                clusters: Dict[int, List[int]] = {}
                for i, label in enumerate(labels):
                    clusters.setdefault(int(label), []).append(i)
                return clusters
            except Exception as e:
                logger.warning("DBSCAN 聚类失败，降级到贪心聚类: %s", e)
                self.clustering_backend = "greedy"

        # 贪心聚类（Jaccard 或基于余弦相似度的阈值聚类）
        return self._greedy_cluster(
            vectors, vec_mode,
            threshold=DEFAULT_JACCARD_THRESHOLD,
            min_samples=min_samples,
        )

    def _greedy_cluster(
        self,
        vectors: Any,
        vec_mode: str,
        threshold: float = DEFAULT_JACCARD_THRESHOLD,
        min_samples: int = DEFAULT_MIN_SAMPLES,
    ) -> Dict[int, List[int]]:
        """贪心聚类：按顺序遍历，与已有聚类的最大相似度 ≥ threshold 则归入。

        - vec_mode='jaccard'：基于 token 集合的 Jaccard 相似度
        - vec_mode='dense'/'tfidf'：基于余弦相似度
        - min_samples：聚类大小下限，小于该值的组归为噪声（放宽到 max(2, min_samples)）
        """
        n = len(vectors)
        # 用 min_samples 控制：聚类大小 < min_samples 的归入噪声
        # 先做贪心分组
        groups: List[List[int]] = []  # 每组是 feedback index 列表

        for i in range(n):
            best_group = -1
            best_sim = 0.0
            for gi, group in enumerate(groups):
                # 与该组所有成员的最大相似度
                max_sim = 0.0
                for j in group:
                    if vec_mode == "jaccard":
                        sim = jaccard_similarity(vectors[i], vectors[j])
                    else:
                        sim = _cosine_similarity(vectors[i], vectors[j])
                    if sim > max_sim:
                        max_sim = sim
                        if max_sim >= threshold:
                            break
                if max_sim > best_sim:
                    best_sim = max_sim
                    best_group = gi
            if best_group >= 0 and best_sim >= threshold:
                groups[best_group].append(i)
            else:
                groups.append([i])

        # 将大小 < 2 的组归为噪声（min_samples 在贪心模式下放宽到 2）
        # 严格按 min_samples 来：小于 min_samples 的视为噪声
        # 但为避免噪声过多，使用 max(2, min_samples) 作为阈值
        cluster_threshold = max(2, min_samples)
        clusters: Dict[int, List[int]] = {}
        cluster_id = 0
        noise: List[int] = []
        for group in groups:
            if len(group) >= cluster_threshold:
                clusters[cluster_id] = group
                cluster_id += 1
            else:
                noise.extend(group)
        if noise:
            clusters[-1] = noise
        return clusters

    # ===== 模式提取 =====
    def _extract_pattern(self, cluster_feedbacks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """提取共性模式（LLM 或模板降级）。"""
        if self.llm_backend == "api":
            try:
                return self._llm_extract_pattern(cluster_feedbacks)
            except Exception as e:
                logger.warning("LLM 调用失败，降级到模板分析: %s", e)
                return self._template_extract_pattern(cluster_feedbacks)
        return self._template_extract_pattern(cluster_feedbacks)

    def _llm_extract_pattern(self, cluster_feedbacks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """调用 LLM 提取共性模式。"""
        prompt = self._build_prompt(cluster_feedbacks)
        response = self._call_llm(prompt)
        if not response:
            return self._template_extract_pattern(cluster_feedbacks)
        return self._parse_llm_response(response, cluster_feedbacks)

    def _build_prompt(self, cluster_feedbacks: List[Dict[str, Any]]) -> str:
        """构造 LLM 提示词。"""
        feedback_descriptions = []
        for fb in cluster_feedbacks:
            ui = fb.get("user_input") or {}
            ctx = fb.get("context") or {}
            feedback_descriptions.append(
                f"- [{fb.get('type', '')}] {ui.get('summary', '')}"
                f"（字段: {ctx.get('field', 'N/A')}, "
                f"资料: {ctx.get('doc_file', 'N/A')}, "
                f"规则ID: {fb.get('rule_id', 'N/A')}）"
            )
        feedbacks_text = "\n".join(feedback_descriptions)
        prompt = (
            "以下是民航施工资料审核系统中相似的多条反馈，请提取共性模式并生成候选规则建议。\n\n"
            f"反馈列表（共 {len(cluster_feedbacks)} 条）：\n{feedbacks_text}\n\n"
            "请输出 JSON 对象，包含以下字段：\n"
            "{\n"
            '  "type": "missing_rule" 或 "false_positive_cluster",\n'
            '  "description": "模式描述（中文，简明扼要）",\n'
            '  "common_fields": ["涉及字段1", "涉及字段2"],\n'
            '  "common_doc_types": ["资料类型1"],\n'
            '  "suggested_level": "L1-IRON" / "L2-LOGIC" / "L3-BUSINESS",\n'
            '  "suggested_severity": "Fatal" / "Sanity Check" / "Best Practice",\n'
            '  "rule_id_hint": "如果误报，对应规则ID；否则 null",\n'
            '  "suggested_action": "建议动作（如新增规则/修改表达式/调整阈值）"\n'
            "}\n"
            "仅输出 JSON，不要额外说明。"
        )
        return prompt

    def _call_llm(self, prompt: str) -> Optional[str]:
        """调用 LLM API（OpenAI 风格 /v1/chat/completions）。"""
        api_url = self.llm_config.get("api_url") or os.environ.get("LLM_API_URL")
        api_key = self.llm_config.get("api_key") or os.environ.get("LLM_API_KEY")
        if not api_url or not api_key:
            return None

        payload = {
            "model": self.llm_config.get("model") or os.environ.get("LLM_MODEL", "gpt-4o-mini"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(self.llm_config.get("temperature", 0.3)),
        }
        req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError) as e:
            logger.warning("LLM API 调用失败: %s", e)
            return None

    def _parse_llm_response(
        self,
        response: str,
        cluster_feedbacks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """解析 LLM 返回的 JSON（容错：解析失败时回退到模板）。"""
        # 提取 JSON 块（LLM 可能包裹在 ```json ... ``` 中）
        text = response.strip()
        if "```" in text:
            m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
            if m:
                text = m.group(1).strip()
        # 尝试定位首个 { 到末尾 }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                # 补充默认字段
                data.setdefault("common_fields", [])
                data.setdefault("common_doc_types", [])
                data.setdefault("suggested_level", "L3-BUSINESS")
                data.setdefault("suggested_severity", "Best Practice")
                return data
        except json.JSONDecodeError:
            pass
        # 解析失败 → 模板降级
        return self._template_extract_pattern(cluster_feedbacks)

    def _template_extract_pattern(self, cluster_feedbacks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """规则化模板提取模式（降级方案）。

        基于反馈类型分布、共现字段、共现资料类型，按预定义模板生成 pattern。
        """
        type_counts: Dict[str, int] = {"missed": 0, "false_positive": 0}
        field_counts: Dict[str, int] = {}
        doc_file_counts: Dict[str, int] = {}
        rule_id_counts: Dict[str, int] = {}
        expected_levels: Dict[str, int] = {}
        expected_severities: Dict[str, int] = {}

        for fb in cluster_feedbacks:
            t = fb.get("type", "")
            type_counts[t] = type_counts.get(t, 0) + 1

            ctx = fb.get("context") or {}
            field = ctx.get("field")
            if field:
                field_counts[field] = field_counts.get(field, 0) + 1
            doc_file = ctx.get("doc_file")
            if doc_file:
                # 提取资料类型（去掉扩展名与数字编号）
                doc_type = re.sub(r"\d+", "", Path(doc_file).stem)
                doc_file_counts[doc_type] = doc_file_counts.get(doc_type, 0) + 1

            rid = fb.get("rule_id")
            if rid:
                rule_id_counts[rid] = rule_id_counts.get(rid, 0) + 1

            ui = fb.get("user_input") or {}
            ert = ui.get("expected_rule_type")
            if ert:
                expected_levels[ert] = expected_levels.get(ert, 0) + 1
            es = ui.get("expected_severity")
            if es:
                expected_severities[es] = expected_severities.get(es, 0) + 1

        # Top 3 字段
        top_fields = sorted(field_counts.items(), key=lambda x: -x[1])[:3]
        common_fields = [f[0] for f in top_fields]

        # Top 资料类型
        top_doc_types = sorted(doc_file_counts.items(), key=lambda x: -x[1])[:2]
        common_doc_types = [d[0] for d in top_doc_types]

        # 推断建议层级与严重度（取众数；缺失则默认）
        suggested_level = (
            max(expected_levels, key=expected_levels.get)
            if expected_levels else "L3-BUSINESS"
        )
        suggested_severity = (
            max(expected_severities, key=expected_severities.get)
            if expected_severities else "Best Practice"
        )

        # 主要反馈类型
        missed_count = type_counts.get("missed", 0)
        fp_count = type_counts.get("false_positive", 0)

        if missed_count >= fp_count:
            # 漏审为主：可能是缺失新规则
            fields_str = "、".join(common_fields) if common_fields else "（未识别）"
            doc_str = "、".join(common_doc_types) if common_doc_types else "（未识别）"
            description = (
                f"{len(cluster_feedbacks)} 条漏审反馈指向同一模式："
                f"涉及字段 {fields_str}，资料类型 {doc_str}"
            )
            return {
                "type": "missing_rule",
                "description": description,
                "common_fields": common_fields,
                "common_doc_types": common_doc_types,
                "suggested_level": suggested_level,
                "suggested_severity": suggested_severity,
                "rule_id_hint": None,
                "suggested_action": "新增规则以覆盖此模式",
            }
        else:
            # 误报为主：现有规则表达式可能有问题
            top_rule = max(rule_id_counts, key=rule_id_counts.get) if rule_id_counts else None
            fields_str = "、".join(common_fields) if common_fields else "（未识别）"
            description = (
                f"{len(cluster_feedbacks)} 条误报反馈指向规则 {top_rule}："
                f"涉及字段 {fields_str}"
            )
            return {
                "type": "false_positive_cluster",
                "description": description,
                "common_fields": common_fields,
                "common_doc_types": common_doc_types,
                "suggested_level": suggested_level,
                "suggested_severity": suggested_severity,
                "rule_id_hint": top_rule,
                "suggested_action": "复核规则表达式，考虑调整阈值或增加排除条件",
            }

    # ===== 候选规则生成 =====
    def _generate_candidate_rule(
        self,
        cluster_seq: int,
        cluster_feedbacks: List[Dict[str, Any]],
        pattern: Dict[str, Any],
    ) -> Dict[str, Any]:
        """生成候选规则 JSON。"""
        date_compact = _today_compact()
        rule_id = f"INC-{date_compact}-{cluster_seq:03d}"
        cluster_label = f"CL-{cluster_seq:03d}"
        now = now_iso()

        description = pattern.get("description", "候选规则（待人工补充）")
        # 截断到 50 字符以构造 name
        name = f"[孵化] {description[:50]}"

        common_fields = pattern.get("common_fields", [])
        common_doc_types = pattern.get("common_doc_types", [])
        suggested_level = pattern.get("suggested_level", "L3-BUSINESS")
        suggested_severity = pattern.get("suggested_severity", "Best Practice")
        pattern_type = pattern.get("type", "unknown")

        candidate = {
            "rule_id": rule_id,
            "name": name,
            "level": suggested_level,
            "scope": "SINGLE_DOC",
            "category": "孵化候选",
            "description": description,
            "trigger_when": {
                "doc_type": common_doc_types,  # 待人工补充
                "field_required": common_fields,
            },
            "check_expr": {
                "type": "expression",
                "expr": "# TODO: 人工补充校验表达式",
                "language": "jinja-expr",
            },
            "error_template": f"待补充：{description[:80]}",
            "severity_on_violation": suggested_severity,
            "status": "incubating",
            "source": "incubated",
            "version": "0.1.0",
            "created_at": now,
            "updated_at": now,
            "owner": "feedback_analyzer",
            "changelog": [{
                "version": "0.1.0",
                "date": today_str(),
                "author": "feedback_analyzer",
                "change": (
                    f"由反馈聚类 {cluster_label} 自动生成"
                    f"（基于 {len(cluster_feedbacks)} 条反馈，模式类型: {pattern_type}）"
                ),
            }],
            "stats": {
                "total_hits": 0,
                "total_reviews": 0,
                "hit_rate": 0.0,
                "false_positive_count": 0,
                "false_positive_rate": 0.0,
                "last_hit_at": None,
                "last_review_at": None,
            },
            "alignment": None,
            "incubation_meta": {
                "cluster_id": cluster_label,
                "source_feedbacks": [f["feedback_id"] for f in cluster_feedbacks],
                "pattern": pattern,
                "auto_generated": True,
                "needs_human_review": True,
            },
        }
        return candidate

    def _write_candidate_rule(self, candidate: Dict[str, Any]) -> Path:
        """将候选规则写入 rules/custom/incubator/{rule_id}.json。"""
        self.incubator_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.incubator_dir / f"{candidate['rule_id']}.json"
        file_path.write_text(
            json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return file_path

    # ===== 报告生成 =====
    def _generate_report(
        self,
        feedbacks: List[Dict[str, Any]],
        clusters: Dict[int, List[int]],
        cluster_summaries: List[Dict[str, Any]],
        candidate_rules: List[Dict[str, Any]],
        noise_count: int,
        dry_run: bool,
    ) -> str:
        """生成 Markdown 分析报告。"""
        date_str = _today_dash()
        timestamp = now_iso()
        total = len(feedbacks)
        valid_clusters = [c for c in clusters if c != -1]
        total_clusters = len(valid_clusters)

        # 反馈类型分布
        type_dist: Dict[str, int] = {"missed": 0, "false_positive": 0}
        for fb in feedbacks:
            t = fb.get("type", "")
            type_dist[t] = type_dist.get(t, 0) + 1

        lines: List[str] = []
        lines.append(f"# 反馈分析报告 {date_str}\n")
        lines.append(f"> 生成时间：{timestamp}\n")

        lines.append("## 概览\n")
        lines.append(f"- 反馈总数：**{total}**")
        lines.append(f"- 反馈类型：漏审 {type_dist.get('missed', 0)} 条 / "
                     f"误报 {type_dist.get('false_positive', 0)} 条")
        lines.append(f"- 聚类数：**{total_clusters}**（不含噪声）")
        lines.append(f"- 噪声点数：{noise_count}（未归入任何聚类，保持 new 状态）")
        lines.append(f"- 候选规则数：**{len(candidate_rules)}**")
        lines.append(f"- 模式：{'**dry-run**（未写文件、未更新状态）' if dry_run else '已写入候选规则并更新反馈状态'}")
        lines.append("")

        lines.append("## 后端信息\n")
        lines.append(f"- embedding_backend: `{self.embedding_backend}`")
        lines.append(f"- clustering_backend: `{self.clustering_backend}`")
        lines.append(f"- llm_backend: `{self.llm_backend}`")
        lines.append("")

        lines.append("## 聚类详情\n")
        if not cluster_summaries:
            lines.append("_未生成任何聚类（反馈数量或相似度不足）。_\n")
        for s in cluster_summaries:
            pattern = s["pattern"] or {}
            lines.append(f"### {s['cluster_id']}（{s['size']} 条反馈）\n")
            lines.append(f"- **类型**：{pattern.get('type', 'unknown')}")
            lines.append(f"- **模式描述**：{pattern.get('description', 'N/A')}")
            common_fields = pattern.get("common_fields", [])
            if common_fields:
                lines.append(f"- **涉及字段**：{', '.join(common_fields)}")
            common_docs = pattern.get("common_doc_types", [])
            if common_docs:
                lines.append(f"- **资料类型**：{', '.join(common_docs)}")
            lines.append(f"- **建议层级**：{pattern.get('suggested_level', 'N/A')}")
            lines.append(f"- **建议严重度**：{pattern.get('suggested_severity', 'N/A')}")
            lines.append(f"- **建议动作**：{pattern.get('suggested_action', 'N/A')}")
            lines.append(f"- **候选规则**：`{s['candidate_rule_id']}`")
            fb_ids = s["feedbacks"]
            if fb_ids:
                preview = ", ".join(fb_ids[:5])
                if len(fb_ids) > 5:
                    preview += f" ...（共 {len(fb_ids)} 条）"
                lines.append(f"- **包含反馈**：{preview}")
            lines.append("")

        lines.append("## 候选规则清单\n")
        if not candidate_rules:
            lines.append("_未生成候选规则。_\n")
        else:
            lines.append("| rule_id | cluster_id | 类型 | 层级 | 严重度 | 文件 |")
            lines.append("|---|---|---|---|---|---|")
            for c in candidate_rules:
                meta = c.get("incubation_meta") or {}
                pattern = meta.get("pattern") or {}
                rel_file = f"custom/incubator/{c['rule_id']}.json"
                lines.append(
                    f"| `{c['rule_id']}` | `{meta.get('cluster_id', '')}` | "
                    f"{pattern.get('type', '')} | {c.get('level', '')} | "
                    f"{c.get('severity_on_violation', '')} | `{rel_file}` |"
                )
            lines.append("")

        lines.append("## 反馈处理状态\n")
        if dry_run:
            lines.append("- dry-run 模式：未更新任何反馈状态。")
        else:
            analyzed_count = sum(s["size"] for s in cluster_summaries)
            lines.append(f"- 已更新为 `analyzed` 的反馈：**{analyzed_count}** 条")
            lines.append(f"- 噪声点反馈（保持 `new`）：**{noise_count}** 条")
        lines.append("")

        lines.append("## 备注\n")
        lines.append("- 候选规则 `check_expr.expr` / `error_template` / "
                     "`trigger_when.doc_type` 为占位值，**需人工补充**后方可进入 testing。")
        lines.append("- 候选规则 `source=incubated`、`status=incubating`，"
                     "须经人工评审并通过 transition 流程转入 testing → active。")
        if self.llm_backend == "template":
            lines.append("- 本次分析使用**规则化模板**（LLM 不可用），"
                         "建议配置 `LLM_API_URL` / `LLM_API_KEY` 环境变量以启用 LLM 模式提取。")
        if self.embedding_backend == "jaccard":
            lines.append("- 本次向量化使用 **Jaccard 关键词集合**（sentence-transformers / sklearn 不可用），"
                         "聚类精度受限。")
        if self.clustering_backend == "greedy":
            lines.append("- 本次聚类使用**贪心算法**（sklearn 不可用），"
                         "结果与 DBSCAN 可能存在差异。")
        lines.append("")

        return "\n".join(lines)

    def _write_report(self, report: str) -> Path:
        """将报告写入 rules/reflections/feedback-analysis-{日期}.md。"""
        self.reflections_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.reflections_dir / f"feedback-analysis-{_today_dash()}.md"
        report_path.write_text(report, encoding="utf-8")
        return report_path


# ---------------------------------------------------------------------------
# C-4.1 自动触发判定
# ---------------------------------------------------------------------------
def should_auto_trigger(
    store: FeedbackStore,
    threshold: int = AUTO_TRIGGER_THRESHOLD,
) -> Tuple[bool, int]:
    """判断是否应自动触发分析（累积达到 threshold 条 new 反馈）。

    Returns:
        (should_trigger, current_new_count)
    """
    counts = store.count()
    new_count = counts.get("new", 0)
    return (new_count >= threshold, new_count)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="民航施工资料审核 Skill — LLM 反馈分析管道",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--feedbacks-dir", default=str(DEFAULT_FEEDBACKS_DIR),
                        help=f"反馈目录（默认 {DEFAULT_FEEDBACKS_DIR}）")
    parser.add_argument("--rules-dir", default=str(DEFAULT_RULES_DIR),
                        help=f"规则目录（默认 {DEFAULT_RULES_DIR}）")
    parser.add_argument("--min-feedback", type=int, default=DEFAULT_MIN_SAMPLES,
                        help=f"触发分析所需最小 new 反馈数（默认 {DEFAULT_MIN_SAMPLES}）")
    parser.add_argument("--eps", type=float, default=DEFAULT_EPS,
                        help=f"DBSCAN eps 参数（默认 {DEFAULT_EPS}）")
    parser.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES,
                        help=f"DBSCAN min_samples 参数（默认 {DEFAULT_MIN_SAMPLES}）")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅输出报告，不写候选规则、不更新反馈状态")
    parser.add_argument("--auto-threshold", action="store_true",
                        help=f"C-4.1：达到 {AUTO_TRIGGER_THRESHOLD} 条 new 反馈才触发，否则跳过")
    parser.add_argument("--llm-api-url", default=None,
                        help="LLM API URL（覆盖环境变量 LLM_API_URL）")
    parser.add_argument("--llm-api-key", default=None,
                        help="LLM API Key（覆盖环境变量 LLM_API_KEY）")
    parser.add_argument("--llm-model", default=None,
                        help="LLM 模型名（默认 gpt-4o-mini）")
    parser.add_argument("--verbose", action="store_true", help="启用详细日志")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    llm_config: Dict[str, Any] = {}
    if args.llm_api_url:
        llm_config["api_url"] = args.llm_api_url
    if args.llm_api_key:
        llm_config["api_key"] = args.llm_api_key
    if args.llm_model:
        llm_config["model"] = args.llm_model

    analyzer = FeedbackAnalyzer(
        feedbacks_dir=Path(args.feedbacks_dir),
        rules_dir=Path(args.rules_dir),
        llm_config=llm_config,
    )

    # C-4.1 自动触发阈值判定
    min_feedback = args.min_feedback
    if args.auto_threshold:
        min_feedback = AUTO_TRIGGER_THRESHOLD
        should, current = should_auto_trigger(analyzer.store, AUTO_TRIGGER_THRESHOLD)
        if not should:
            print(f"new 反馈数 {current} < 阈值 {AUTO_TRIGGER_THRESHOLD}，跳过分析")
            return 0

    print("=" * 60)
    print("反馈分析管道启动")
    print("=" * 60)
    print(f"反馈目录: {analyzer.feedbacks_dir}")
    print(f"规则目录: {analyzer.rules_dir}")
    print(f"embedding_backend: {analyzer.embedding_backend}")
    print(f"clustering_backend: {analyzer.clustering_backend}")
    print(f"llm_backend: {analyzer.llm_backend}")
    print(f"min_feedback: {min_feedback}")
    print(f"dry_run: {args.dry_run}")
    print("-" * 60)

    result = analyzer.analyze(
        min_feedback=min_feedback,
        dry_run=args.dry_run,
        eps=args.eps,
        min_samples=args.min_samples,
    )

    print("\n分析结果：")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("status") == "skipped":
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
