"""
槽位填充 Agent
从用户输入中提取工单关键参数，缺失时自动追问
"""
import os
import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

SLOT_EXTRACTION_PROMPT = """你是工单槽位填充专家。请从用户输入中提取以下槽位信息。

槽位定义：
- problem_type: 问题类型（登录问题/系统故障/网络异常/设备故障/财务问题）
- description: 问题描述（规范化表达）
- product: 产品/系统名称
- urgency: 紧急程度（高/中/低）
- device: 设备名称/型号
- error_code: 错误码

用户输入：{user_input}

已有上下文信息：{context}

请以 JSON 格式输出：
{{
    "slots": {{
        "problem_type": {{"value": "...", "confidence": 0.0-1.0}},
        "description": {{"value": "...", "confidence": 0.0-1.0}},
        "product": {{"value": "...", "confidence": 0.0-1.0}},
        "urgency": {{"value": "...", "confidence": 0.0-1.0}},
        "device": {{"value": "...", "confidence": 0.0-1.0}},
        "error_code": {{"value": "...", "confidence": 0.0-1.0}}
    }},
    "missing_required": ["缺失的必填槽位列表"],
    "follow_up": "追问消息（如有缺失必填槽位）"
}}
"""


class SlotFillingAgent:
    """槽位填充 Agent"""

    REQUIRED_SLOTS = ["problem_type", "description"]
    CONFIDENCE_THRESHOLD = 0.7

    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.1,
            max_tokens=1024,
        )
        self.slots = {}  # 已填充的槽位

    def fill(self, user_input: str, context: dict = None) -> dict:
        """
        从用户输入中填充槽位
        返回: {"slots": dict, "complete": bool, "follow_up": str or None}
        """
        context_str = json.dumps(context or {}, ensure_ascii=False)

        try:
            prompt = SLOT_EXTRACTION_PROMPT.format(
                user_input=user_input,
                context=context_str,
            )
            response = self.llm.invoke([HumanMessage(content=prompt)])
            result = self._parse_json(response.content)

            # 更新槽位
            extracted_slots = result.get("slots", {})
            for slot_name, slot_info in extracted_slots.items():
                if slot_info.get("value") and slot_info.get("confidence", 0) >= self.CONFIDENCE_THRESHOLD:
                    self.slots[slot_name] = slot_info["value"]

            # 检查完整性
            complete = all(
                slot in self.slots
                for slot in self.REQUIRED_SLOTS
            )

            follow_up = result.get("follow_up") if not complete else None

            return {
                "slots": self.slots.copy(),
                "complete": complete,
                "follow_up": follow_up,
            }

        except Exception as e:
            logger.error(f"槽位填充失败: {e}")
            return {
                "slots": self.slots.copy(),
                "complete": False,
                "follow_up": "请描述您遇到的问题，包括问题类型和具体情况。",
            }

    def reset(self):
        """重置槽位"""
        self.slots = {}

    def get_filled_slots(self) -> dict:
        """获取已填充的槽位"""
        return self.slots.copy()

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
            return {"slots": {}, "missing_required": self.REQUIRED_SLOTS, "follow_up": "请提供更多信息。"}
