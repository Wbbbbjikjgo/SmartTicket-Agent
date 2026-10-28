"""
BM25 全文检索器
基于 Elasticsearch IK 分词的关键词精确匹配检索
"""
import os
import logging
from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")


class BM25Retriever:
    """ES BM25 全文检索器"""

    def __init__(self, index: str = "knowledge_base"):
        self.es = Elasticsearch(ES_HOST)
        self.index = index

    def search(self, query: str, size: int = 20, indices: list = None) -> list:
        """
        BM25 检索
        返回: [{"id": str, "score": float, "content": str, "source": dict}, ...]
        """
        search_indices = indices or [self.index]
        results = []

        for idx in search_indices:
            try:
                match_query = {
                    "multi_match": {
                        "query": query,
                        "fields": [
                            "description", "content", "keywords", "title",
                            "question", "resolution", "solution",
                        ],
                        "type": "best_fields",
                        "analyzer": "ik_smart",
                    }
                }
                if idx == "tickets":
                    # 工单只有已解决（有答案）才允许进入知识检索
                    query_body = {
                        "bool": {
                            "must": [match_query],
                            "filter": [{"terms": {"status": ["已解决", "resolved", "closed"]}}],
                        }
                    }
                else:
                    query_body = match_query

                body = {"query": query_body, "size": size}
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
                logger.error(f"BM25 检索索引 {idx} 失败: {e}")

        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:size]

    def _extract_content(self, source: dict) -> str:
        """从文档中提取主要文本内容"""
        for field in ["content", "description", "question", "title", "resolution", "solution"]:
            if field in source and source[field]:
                return source[field]
        return ""
