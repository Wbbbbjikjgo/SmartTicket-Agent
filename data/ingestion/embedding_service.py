"""
DashScope Embedding 服务封装
使用阿里云 text-embedding-v3 模型，国内直连，替代 BGE-M3
"""
import os
import logging
from typing import Union

import dashscope
from dashscope import TextEmbedding

logger = logging.getLogger(__name__)


class DashScopeEmbedding:
    """阿里云 DashScope Embedding 服务"""

    def __init__(self, model: str = None):
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.dims = int(os.getenv("VECTOR_DIMS", "1024"))
        dashscope.api_key = self.api_key

    def embed_text(self, text: str) -> list[float]:
        """单条文本向量化"""
        try:
            resp = TextEmbedding.call(
                model=self.model,
                input=text,
                dimension=self.dims,
            )
            if resp.status_code == 200:
                return resp.output["embeddings"][0]["embedding"]
            else:
                logger.error(f"Embedding 调用失败: {resp.code} - {resp.message}")
                return [0.0] * self.dims
        except Exception as e:
            logger.error(f"Embedding 异常: {e}")
            return [0.0] * self.dims

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化（DashScope 单次最多 25 条）"""
        all_embeddings = []
        batch_size = 25

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                resp = TextEmbedding.call(
                    model=self.model,
                    input=batch,
                    dimension=self.dims,
                )
                if resp.status_code == 200:
                    batch_embeddings = [item["embedding"] for item in resp.output["embeddings"]]
                    all_embeddings.extend(batch_embeddings)
                else:
                    logger.error(f"批量 Embedding 失败: {resp.code}")
                    all_embeddings.extend([[0.0] * self.dims] * len(batch))
            except Exception as e:
                logger.error(f"批量 Embedding 异常: {e}")
                all_embeddings.extend([[0.0] * self.dims] * len(batch))

        return all_embeddings
