"""
知识沉淀 Agent
工单关闭后，自动将解决方案沉淀到知识库
"""
import os
import json
import logging
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

SUMMARIZE_PROMPT = """你是知识管理专家。请根据工单的处理过程，提炼出一条标准化的知识条目。

工单信息：
{ticket_info}

请提炼知识条目，以 JSON 格式输出：
{{
    "title": "知识标题（简明扼要）",
    "content": "问题描述与排查过程",
    "solution": "标准解决方案",
    "category": "问题类别",
    "tags": ["标签1", "标签2"]
}}
"""


class KnowledgeAgent:
    """知识沉淀 Agent"""

    def __init__(self, es_client=None, embedder=None):
        """
        es_client: Elasticsearch 客户端
        embedder: DashScopeEmbedding 实例
        """
        self.es = es_client
        self.embedder = embedder
        self.llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.3,
            max_tokens=2048,
        )
        self.dedup_threshold = 0.92

    def settle(self, ticket: dict) -> dict:
        """
        将已关闭工单沉淀为知识
        流程：LLM摘要 → 向量化 → 去重检测 → 入库
        """
        if ticket.get("status") != "closed":
            return {"success": False, "message": "工单未关闭，暂不沉淀"}

        # Step 1: LLM 提炼知识
        knowledge = self._summarize(ticket)
        if not knowledge:
            return {"success": False, "message": "知识提炼失败"}

        # Step 2: 向量化（只计算一次，后续去重与入库复用）
        content_vector = None
        if self.embedder:
            text_for_vec = f"{knowledge.get('title', '')} {knowledge.get('content', '')} {knowledge.get('solution', '')}"
            content_vector = self.embedder.embed_text(text_for_vec)
            knowledge["content_vector"] = content_vector

        # Step 3: 去重检测
        if self.es and content_vector:
            duplicate = self._check_duplicate(content_vector)
            if duplicate:
                return {
                    "success": False,
                    "message": f"检测到重复知识（相似度>{self.dedup_threshold}），已有条目: {duplicate}",
                    "duplicate": True,
                }

        # Step 4: 入库（复用 ingest_knowledge，统一向量化与写入逻辑）
        knowledge["source_ticket"] = ticket.get("ticket_id")
        knowledge["quality_score"] = self._evaluate_quality(ticket)
        knowledge["create_date"] = datetime.now().isoformat()
        knowledge["kb_id"] = f"KB{datetime.now().strftime('%Y%m%d%H%M%S')}"

        if self.es:
            try:
                from data.ingestion.ingest_docs import ingest_knowledge
                ingest_knowledge(knowledge, content_vector=content_vector)
                logger.info(f"知识沉淀成功: {knowledge['title']} (kb_id: {knowledge['kb_id']})")
                return {"success": True, "kb_id": knowledge["kb_id"], "knowledge": knowledge}
            except Exception as e:
                logger.error(f"知识入库失败: {e}")
                return {"success": False, "message": f"入库失败: {e}"}

        return {"success": True, "knowledge": knowledge}

    def _summarize(self, ticket: dict) -> dict:
        """LLM 提炼知识摘要"""
        try:
            prompt = SUMMARIZE_PROMPT.format(
                ticket_info=json.dumps(ticket, ensure_ascii=False, indent=2)
            )
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return self._parse_json(response.content)
        except Exception as e:
            logger.error(f"知识摘要失败: {e}")
            return None

    def _check_duplicate(self, vector: list) -> str:
        """向量去重检测"""
        if not self.es or not vector:
            return None
        try:
            resp = self.es.search(
                index="knowledge_base",
                body={
                    "knn": {
                        "field": "content_vector",
                        "query_vector": vector,
                        "k": 1,
                        "num_candidates": 10,
                    },
                    "_source": ["title"],
                },
            )
            hits = resp.get("hits", {}).get("hits", [])
            if hits and hits[0]["_score"] >= self.dedup_threshold:
                return hits[0]["_source"].get("title", hits[0]["_id"])
        except Exception as e:
            logger.warning(f"去重检测失败: {e}")
        return None

    def _evaluate_quality(self, ticket: dict) -> float:
        """评估知识质量（基于工单满意度和解决时长）"""
        score = 0.8  # 基础分

        # 有解决方案加分
        if ticket.get("resolution"):
            score += 0.1

        # 有满意度评分
        satisfaction = ticket.get("satisfaction")
        if satisfaction:
            score = satisfaction * 0.5 + 0.5  # 映射到 0.5-1.0

        return min(score, 1.0)

    def _parse_json(self, text: str) -> dict:
        """解析 JSON"""
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}
