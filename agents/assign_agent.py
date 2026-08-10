"""
智能派单 Agent
根据工单类型、优先级和技能组匹配，自动派发工单
"""
import os
import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

ASSIGN_PROMPT = """你是智能派单专家。请根据工单信息，决定将工单派发给哪个技能组。

技能组说明：
- IT支持组：处理登录问题、系统故障、网络异常等IT相关问题
- 维修工程师：处理设备硬件故障、死机、蓝屏等物理设备问题
- 财务组：处理退款、账单、支付等财务相关问题
- 客服组：处理产品咨询、投诉、建议等客户服务问题

工单信息：
{ticket_info}

请以 JSON 格式输出：
{{
    "skill_group": "目标技能组",
    "priority": "处理优先级（高/中/低）",
    "reason": "派单理由",
    "estimated_time": "预计处理时间"
}}
"""


class AssignAgent:
    """智能派单 Agent"""

    SKILL_GROUPS = ["IT支持组", "维修工程师", "财务组", "客服组"]

    # 规则映射（优先使用规则，LLM 作为兜底）
    CATEGORY_TO_GROUP = {
        "登录问题": "IT支持组",
        "系统故障": "IT支持组",
        "网络异常": "IT支持组",
        "设备故障": "维修工程师",
        "财务问题": "财务组",
    }

    def __init__(self, ticket_tools=None):
        self.ticket_tools = ticket_tools
        self.llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.1,
            max_tokens=512,
        )

    def assign(self, ticket: dict) -> dict:
        """
        派单决策
        返回: {"skill_group": str, "priority": str, "reason": str, "assigned": bool}
        """
        # Step 1: 规则匹配
        category = ticket.get("problem_type", "") or ticket.get("category", "")
        rule_group = self.CATEGORY_TO_GROUP.get(category)

        if rule_group:
            result = {
                "skill_group": rule_group,
                "priority": ticket.get("urgency", "中"),
                "reason": f"根据问题类型「{category}」规则路由到 {rule_group}",
                "assigned": True,
            }
        else:
            # Step 2: LLM 决策
            result = self._llm_assign(ticket)

        # Step 3: 执行派单
        ticket_id = ticket.get("ticket_id")
        if ticket_id and self.ticket_tools and result.get("assigned"):
            assign_result = self.ticket_tools.assign_engineer(
                ticket_id=ticket_id,
                skill_group=result["skill_group"],
                reason=result["reason"],
            )
            result["assign_result"] = assign_result

        logger.info(f"派单决策: {ticket_id} → {result['skill_group']}")
        return result

    def _llm_assign(self, ticket: dict) -> dict:
        """LLM 派单决策"""
        try:
            prompt = ASSIGN_PROMPT.format(
                ticket_info=json.dumps(ticket, ensure_ascii=False, indent=2)
            )
            response = self.llm.invoke([HumanMessage(content=prompt)])
            result = self._parse_json(response.content)
            result["assigned"] = True
            return result
        except Exception as e:
            logger.error(f"LLM 派单失败: {e}")
            return {
                "skill_group": "客服组",  # 默认兜底
                "priority": "中",
                "reason": f"LLM 决策失败，默认分配到客服组: {e}",
                "assigned": True,
            }

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
            return {"skill_group": "客服组", "priority": "中", "reason": "解析失败"}
