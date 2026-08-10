"""
重排序模块
使用阿里云 DashScope gte-rerank-v2 进行精排（替代 BGE-Reranker / BGE-M3）
"""
import os
import logging

import dashscope
from dashscope import TextReRank

logger = logging.getLogger(__name__)


class DashScopeReranker:
    """阿里云 DashScope Rerank 服务"""

    def __init__(self, model: str = None):
        self.model = model or os.getenv("RERANK_MODEL", "gte-rerank-v2")
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.top_n = 10
        dashscope.api_key = self.api_key

    def rerank(self, query: str, documents: list[dict], top_n: int = None) -> list:
        """
        重排序
        参数:
            query: 查询文本
            documents: 候选文档列表 [{"id": str, "content": str, ...}, ...]
            top_n: 返回前 N 条
        返回:
            重排序后的文档列表
        """
        if not documents:
            return []

        top_n = top_n or self.top_n
        contents = [doc.get("content", "") for doc in documents]

        try:
            resp = TextReRank.call(
                model=self.model,
                query=query,
                documents=contents,
                top_n=top_n,
                return_documents=False,
            )

            if resp.status_code == 200:
                reranked = []
                for item in resp.output.results:
                    doc = documents[item.index].copy()
                    doc["rerank_score"] = item.relevance_score
                    reranked.append(doc)
                logger.info(f"Rerank 完成: {len(documents)} → {len(reranked)} 条")
                return reranked
            else:
                logger.error(f"Rerank 调用失败: {resp.code} - {resp.message}")
                return documents[:top_n]

        except Exception as e:
            logger.error(f"Rerank 异常: {e}")
            return documents[:top_n]
