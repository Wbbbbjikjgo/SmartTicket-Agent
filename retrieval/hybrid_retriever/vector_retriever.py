"""
向量语义检索器
基于 DashScope Embedding + Elasticsearch knn 的语义相似度检索
"""
import os
import sys
import logging
from elasticsearch import Elasticsearch

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from data.ingestion.embedding_service import DashScopeEmbedding

logger = logging.getLogger(__name__)

ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")


class VectorRetriever:
    """ES 向量语义检索器"""

    def __init__(self, index: str = "knowledge_base"):
        self.es = Elasticsearch(ES_HOST)
        self.index = index
        self.embedder = DashScopeEmbedding()

    def search(self, query: str, size: int = 20, indices: list = None) -> list:
        """
        向量检索
        返回: [{"id": str, "score": float, "content": str, "source": dict}, ...]
        """
        search_indices = indices or [self.index]

        # 生成查询向量
        query_vec = self.embedder.embed_text(query)
        results = []

        for idx in search_indices:
            try:
                knn = {
                    "field": "content_vector",
                    "query_vector": query_vec,
                    "k": size,
                    "num_candidates": size * 4,
                }
                if idx == "tickets":
                    # 只检索已解决工单（未解决工单没有向量/答案）
                    knn["filter"] = {"terms": {"status": ["已解决", "resolved", "closed"]}}

                body = {"knn": knn, "_source": True}
                resp = self.es.search(index=idx, body=body)

                for hit in resp["hits"]["hits"]:
                    results.append({
                        "id": hit["_id"],
                        "score": hit["_score"],
                        "content": self._extract_content(hit["_source"]),
                        "source": hit["_source"],
                        "index": idx,
                    })
            except Exception as e:
                logger.error(f"向量检索索引 {idx} 失败: {e}")

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:size]

    def _extract_content(self, source: dict) -> str:
        """从文档中提取主要文本内容"""
        for field in ["content", "description", "question", "title", "resolution", "solution"]:
            if field in source and source[field]:
                return source[field]
        return ""
