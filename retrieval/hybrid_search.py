"""
混合检索管道
整合：Query改写 → BM25 + 向量检索 → RRF融合 → Rerank精排
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retrieval.query_rewriter import QueryRewriter
from retrieval.hybrid_retriever.bm25_retriever import BM25Retriever
from retrieval.hybrid_retriever.vector_retriever import VectorRetriever
from retrieval.hybrid_retriever.fusion import rrf_fusion
from retrieval.reranker.reranker import DashScopeReranker

logger = logging.getLogger(__name__)


class HybridSearchPipeline:
    """
    混合检索管道
    Query改写 → BM25 + 向量并行召回 → RRF融合 → Rerank精排
    """

    def __init__(self, indices: list = None):
        """
        indices: 要检索的 ES 索引列表，默认 ["knowledge_base", "tickets", "faq"]
        """
        self.indices = indices or ["knowledge_base", "tickets", "faq"]
        self.rewriter = QueryRewriter()
        self.bm25 = BM25Retriever()
        self.vector = VectorRetriever()
        self.reranker = DashScopeReranker()

    def search(self, query: str, top_k: int = 10) -> list:
        """
        完整混合检索流程
        返回: top_k 条精排后的结果
        """
        # Step 1: Query 改写
        rewrite_result = self.rewriter.rewrite(query)
        main_query = rewrite_result.get("rewritten", query)
        variants = rewrite_result.get("variants", [])

        logger.info(f"Query改写: '{query}' → '{main_query}'")

        # Step 2: 多路并行检索
        all_queries = [main_query] + variants[:2]
        bm25_results = []
        vector_results = []

        for q in all_queries:
            bm25_results.extend(self.bm25.search(q, size=10, indices=self.indices))
            vector_results.extend(self.vector.search(q, size=10, indices=self.indices))

        # 去重（按 id）
        bm25_results = self._deduplicate(bm25_results)
        vector_results = self._deduplicate(vector_results)

        logger.info(f"检索召回: BM25={len(bm25_results)}, Vector={len(vector_results)}")

        # Step 3: RRF 融合
        fused = rrf_fusion([bm25_results, vector_results], k=60)
        logger.info(f"RRF融合后: {len(fused)} 条")

        # Step 4: Rerank 精排
        reranked = self.reranker.rerank(main_query, fused, top_n=top_k)
        logger.info(f"Rerank精排后: {len(reranked)} 条")

        return reranked

    def _deduplicate(self, results: list) -> list:
        """按文档 ID 去重"""
        seen = set()
        unique = []
        for doc in results:
            if doc["id"] not in seen:
                seen.add(doc["id"])
                unique.append(doc)
        return unique
