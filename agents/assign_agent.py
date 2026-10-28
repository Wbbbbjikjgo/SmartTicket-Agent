"""
智能派单 Agent
根据工单类型、优先级和技能组匹配，自动派发工单
规则引擎（RuleEngine）优先，LLM 作为兜底
"""
import os
import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from preprocess.nlp_classifier import RuleEngine
from data.ingestion.ticket_service import SKILL_GROUPS

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
    """智能派单 Agent：规则/LLM 决策 → ES 更新「已委派」→ Kafka 推送部门"""

    SKILL_GROUPS = SKILL_GROUPS

    def __init__(self, ticket_tools=None):
        self.ticket_tools = ticket_tools
        # 复用规则引擎做派单匹配（与工单分流规则保持一致）
        self.rule_engine = RuleEngine()
        self.llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.1,
            max_tokens=512,
        )

    def assign(self, ticket: dict) -> dict:
        """
        派单决策并执行：
        1. 规则引擎优先，LLM 兜底
        2. 更新 ES 状态为「已委派」
        3. Kafka 生产者推送到对应部门后台

        返回: {"skill_group", "priority", "reason", "assigned", "status", "kafka_pushed"}
        """
        # Step 1: 规则引擎匹配（复用 nlp_classifier.RuleEngine）
        raw_text = " ".join(filter(None, [
            ticket.get("description"),
            ticket.get("problem_type"),
            ticket.get("category"),
        ]))
        rule_result = self.rule_engine.match(raw_text)

        if rule_result["matched"] and rule_result["skill_group"]:
            result = {
                "skill_group": rule_result["skill_group"],
                "priority": rule_result["priority"] or ticket.get("urgency", "中"),
                "reason": f"规则引擎匹配「{rule_result['category']}」自动派单",
                "assigned": True,
            }
        else:
            # Step 2: LLM 决策（兜底）
            result = self._llm_assign(ticket)

        # Step 3: 执行派单（ES 更新 + Kafka 推送部门）
        ticket_id = ticket.get("ticket_id")
        if ticket_id and result.get("assigned"):
            try:
                if self.ticket_tools:
                    assign_result = self.ticket_tools.assign_engineer(
                        ticket_id=ticket_id,
                        skill_group=result["skill_group"],
                        reason=result["reason"],
                    )
                else:
                    from data.ingestion.ticket_service import assign_ticket
                    assign_result = assign_ticket(
                        ticket_id=ticket_id,
                        skill_group=result["skill_group"],
                        reason=result["reason"],
                    )
                result["assign_result"] = assign_result
                result["status"] = assign_result.get("status")
                result["kafka_pushed"] = assign_result.get("kafka_pushed", False)
            except Exception as e:
                logger.error(f"派单执行失败: {e}")
                result["assign_result"] = {"success": False, "message": str(e)}

        logger.info(
            f"派单决策: {ticket_id} → {result['skill_group']} "
            f"(Kafka: {'成功' if result.get('kafka_pushed') else '未推送'})"
        )
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
