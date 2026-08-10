"""
RRF (Reciprocal Rank Fusion) 融合排序
将 BM25 和向量检索的结果融合为统一排序
"""
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def rrf_fusion(result_lists: list[list], k: int = 60) -> list:
    """
    RRF 融合排序算法
    score(d) = Σ 1 / (k + rank_i(d))

    参数:
        result_lists: 多路检索结果列表，每路为 [{"id": ..., "score": ..., ...}, ...]
        k: RRF 常数（默认 60）
    返回:
        融合排序后的结果列表
    """
    # 计算每个文档的 RRF 分数
    rrf_scores = defaultdict(float)
    doc_map = {}  # id → 文档详情

    for results in result_lists:
        for rank, doc in enumerate(results, start=1):
            doc_id = doc["id"]
            rrf_scores[doc_id] += 1.0 / (k + rank)
            # 保留最高原始分数的文档详情
            if doc_id not in doc_map or doc["score"] > doc_map[doc_id]["score"]:
                doc_map[doc_id] = doc

    # 按 RRF 分数排序
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

    fused = []
    for doc_id in sorted_ids:
        doc = doc_map[doc_id].copy()
        doc["rrf_score"] = rrf_scores[doc_id]
        fused.append(doc)

    logger.info(f"RRF 融合: {len(result_lists)} 路 → {len(fused)} 条结果")
    return fused
