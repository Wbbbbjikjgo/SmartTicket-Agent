"""
意图识别 Agent
基于 DeepSeek 大模型判断用户意图：创建工单/查询工单/知识检索/派单/闲聊
"""
import os
import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个智能工单系统的意图识别模块。你的任务是准确判断用户输入的意图类别。

意图类别及判断标准：
1. create_ticket - 用户想要创建/提交/报告一个工单或问题
2. query_ticket - 用户想要查询已有工单的状态、进度或结果
3. search_knowledge - 用户想要搜索知识库、查找解决方案或历史经验
4. assign - 用户想要转接人工客服、派单给工程师
5. chitchat - 闲聊、问候、或其他不属于以上类别的输入

输出要求：
- 严格以 JSON 格式输出
- confidence 范围 0-1，低于 0.6 表示不确定
"""

USER_PROMPT = """请判断以下用户输入的意图：

用户输入：{user_input}

请以 JSON 格式输出：
{{
    "intent": "意图类别（create_ticket/query_ticket/search_knowledge/assign/chitchat）",
    "confidence": 0.0-1.0,
    "reason": "判断理由（简短）"
}}
"""


class IntentAgent:
    """意图识别 Agent"""

    # 意图枚举
    INTENTS = ["create_ticket", "query_ticket", "search_knowledge", "assign", "chitchat"]

    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.1,
            max_tokens=512,
        )

    def recognize(self, user_input: str) -> dict:
        """
        识别用户意图
        返回: {"intent": str, "confidence": float, "reason": str}
        """
        try:
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=USER_PROMPT.format(user_input=user_input)),
            ]
            response = self.llm.invoke(messages)
            result = self._parse_json(response.content)

            # 验证意图类别
            if result.get("intent") not in self.INTENTS:
                result["intent"] = "chitchat"
                result["confidence"] = 0.5

            return result

        except Exception as e:
            logger.error(f"意图识别失败: {e}")
            return {"intent": "chitchat", "confidence": 0.3, "reason": f"识别异常: {e}"}

    def _parse_json(self, text: str) -> dict:
        """解析 LLM 输出的 JSON"""
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
            return {"intent": "chitchat", "confidence": 0.3, "reason": "解析失败"}
