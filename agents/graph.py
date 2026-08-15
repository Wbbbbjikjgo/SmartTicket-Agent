"""
多智能体协同编排（LangGraph）
编排流程：意图识别 → 槽位填充 → 工具调用 → 派单 → 知识沉淀
"""
import os
import json
import logging
from typing import TypedDict, Annotated, Literal
from datetime import datetime

from langgraph.graph import StateGraph, END

from agents.intent_agent import IntentAgent
from agents.slot_filling_agent import SlotFillingAgent
from agents.ticket_agent import TicketAgent
from agents.assign_agent import AssignAgent
from agents.knowledge_agent import KnowledgeAgent
from tools.function_tools import TicketTools

logger = logging.getLogger(__name__)


# ========== 状态定义 ==========

class AgentState(TypedDict):
    """多 Agent 协同状态"""
    user_input: str                    # 用户输入
    intent: str                        # 识别的意图
    intent_confidence: float           # 意图置信度
    slots: dict                        # 已填充的槽位
    slots_complete: bool               # 槽位是否完整
    follow_up: str                     # 追问消息
    response: str                      # 最终回复
    ticket_id: str                     # 工单ID
    tool_calls: list                   # 工具调用记录
    assign_result: dict                # 派单结果
    knowledge_result: dict             # 知识沉淀结果
    step: str                          # 当前步骤


# ========== 节点函数 ==========

class MultiAgentOrchestrator:
    """多智能体协同编排器"""

    def __init__(self, es_client=None, embedder=None, search_pipeline=None):
        # 初始化工具
        self.ticket_tools = TicketTools(es_client=es_client, search_pipeline=search_pipeline)

        # 初始化各 Agent
        self.intent_agent = IntentAgent()
        self.slot_agent = SlotFillingAgent()
        self.ticket_agent = TicketAgent(self.ticket_tools)
        self.assign_agent = AssignAgent(self.ticket_tools)
        self.knowledge_agent = KnowledgeAgent(es_client=es_client, embedder=embedder)

        # 构建 LangGraph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """构建多 Agent 协同图"""
        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node("intent_recognition", self._intent_node)
        workflow.add_node("slot_filling", self._slot_node)
        workflow.add_node("create_ticket", self._create_ticket_node)
        workflow.add_node("query_ticket", self._query_ticket_node)
        workflow.add_node("search_knowledge", self._search_knowledge_node)
        workflow.add_node("assign_ticket", self._assign_node)
        workflow.add_node("settle_knowledge", self._settle_knowledge_node)
        workflow.add_node("generate_response", self._response_node)

        # 入口
        workflow.set_entry_point("intent_recognition")

        # 条件路由
        workflow.add_conditional_edges(
            "intent_recognition",
            self._route_after_intent,
            {
                "slot_filling": "slot_filling",
                "query_ticket": "query_ticket",
                "search_knowledge": "search_knowledge",
                "generate_response": "generate_response",
            },
        )

        workflow.add_conditional_edges(
            "slot_filling",
            self._route_after_slot,
            {
                # 槽位完整 → 创建工单；槽位缺失 → 先追问补充信息（generate_response 输出追问）
                "create_ticket": "create_ticket",
                "follow_up": "generate_response",
            },
        )

        workflow.add_edge("create_ticket", "assign_ticket")
        workflow.add_edge("assign_ticket", "generate_response")
        workflow.add_edge("query_ticket", "generate_response")
        workflow.add_edge("search_knowledge", "generate_response")
        workflow.add_edge("settle_knowledge", END)
        workflow.add_edge("generate_response", END)

        return workflow.compile()

    # ========== 节点实现 ==========

    def _intent_node(self, state: AgentState) -> dict:
        """意图识别节点"""
        result = self.intent_agent.recognize(state["user_input"])
        return {
            "intent": result["intent"],
            "intent_confidence": result["confidence"],
            "step": "intent",
        }

    def _slot_node(self, state: AgentState) -> dict:
        """槽位填充节点"""
        result = self.slot_agent.fill(state["user_input"])
        return {
            "slots": result["slots"],
            "slots_complete": result["complete"],
            "follow_up": result["follow_up"],
            "step": "slot_filling",
        }

    def _create_ticket_node(self, state: AgentState) -> dict:
        """创建工单节点"""
        slots = state.get("slots", {})
        result = self.ticket_tools.create_ticket(
            problem_type=slots.get("problem_type", "其他"),
            description=slots.get("description", ""),
            product=slots.get("product"),
            urgency=slots.get("urgency", "中"),
        )
        return {
            "ticket_id": result.get("ticket_id"),
            "tool_calls": [{"tool": "create_ticket", "result": result}],
            "step": "create_ticket",
        }

    def _query_ticket_node(self, state: AgentState) -> dict:
        """查询工单节点"""
        result = self.ticket_agent.process(state["user_input"])
        return {
            "response": result["response"],
            "tool_calls": result["tool_calls"],
            "step": "query_ticket",
        }

    def _search_knowledge_node(self, state: AgentState) -> dict:
        """知识检索节点"""
        result = self.ticket_tools.search_knowledge(state["user_input"])
        results = result.get("results", []) if isinstance(result, dict) else []
        if result.get("success") and results:
            results_text = "\n".join(
                f"- [{r['title']}] {r['content'][:100]}"
                for r in results[:5]
            )
            response = f"为您找到以下相关知识：\n{results_text}"
        else:
            response = "抱歉，未找到相关知识。您可以换个关键词，或直接描述问题，我为您创建工单由工程师解答。"
        return {
            "response": response,
            "step": "search_knowledge",
        }

    def _assign_node(self, state: AgentState) -> dict:
        """派单节点"""
        ticket_id = state.get("ticket_id")
        if not ticket_id:
            return {"step": "assign", "assign_result": {"success": False}}

        # 传递完整槽位信息（含 description），供规则引擎基于文本做派单匹配
        ticket_info = {"ticket_id": ticket_id, **state.get("slots", {})}
        result = self.assign_agent.assign(ticket_info)
        return {
            "assign_result": result,
            "step": "assign",
        }

    def _settle_knowledge_node(self, state: AgentState) -> dict:
        """知识沉淀节点"""
        ticket_id = state.get("ticket_id")
        if not ticket_id:
            return {"step": "settle_knowledge"}

        ticket = {
            "ticket_id": ticket_id,
            "status": "closed",
            **state.get("slots", {}),
        }
        result = self.knowledge_agent.settle(ticket)
        return {
            "knowledge_result": result,
            "step": "settle_knowledge",
        }

    def _response_node(self, state: AgentState) -> dict:
        """生成最终回复节点"""
        if state.get("response"):
            return {"step": "response"}

        # 根据状态生成回复
        intent = state.get("intent", "")
        ticket_id = state.get("ticket_id", "")
        assign_result = state.get("assign_result", {})

        if intent == "assign":
            response = (
                "已为您转接专业工程师，请稍候，工程师将尽快与您联系。\n\n"
                "如问题紧急，也可以直接拨打 IT 值班热线。"
            )
        elif intent == "create_ticket" and ticket_id:
            group = assign_result.get("skill_group", "未分配")
            response = (
                f"工单已创建成功！\n\n"
                f"工单号：{ticket_id}\n"
                f"已派发给：{group}\n"
                f"我们会尽快处理您的问题。"
            )
        elif state.get("follow_up"):
            response = state["follow_up"]
        else:
            response = "已收到您的请求，正在处理中..."

        return {"response": response, "step": "response"}

    # ========== 路由函数 ==========

    def _route_after_intent(self, state: AgentState) -> str:
        """意图识别后的路由"""
        intent = state.get("intent", "chitchat")
        if intent == "create_ticket":
            return "slot_filling"
        elif intent == "query_ticket":
            return "query_ticket"
        elif intent == "search_knowledge":
            return "search_knowledge"
        else:
            return "generate_response"

    def _route_after_slot(self, state: AgentState) -> str:
        """槽位填充后的路由"""
        if state.get("slots_complete"):
            return "create_ticket"
        else:
            # 槽位不完整：返回追问消息给用户，待补充后再进入创建流程
            return "follow_up"

    # ========== 公共接口 ==========

    def run(self, user_input: str) -> dict:
        """
        运行多 Agent 协同流程
        返回最终状态
        """
        initial_state = {
            "user_input": user_input,
            "intent": "",
            "intent_confidence": 0.0,
            "slots": {},
            "slots_complete": False,
            "follow_up": None,
            "response": "",
            "ticket_id": None,
            "tool_calls": [],
            "assign_result": {},
            "knowledge_result": {},
            "step": "",
        }

        final_state = self.graph.invoke(initial_state)
        return {
            "response": final_state.get("response", ""),
            "intent": final_state.get("intent", ""),
            "ticket_id": final_state.get("ticket_id"),
            "slots": final_state.get("slots", {}),
            "assign_result": final_state.get("assign_result", {}),
            "step": final_state.get("step", ""),
        }

    def settle_ticket(self, ticket: dict) -> dict:
        """单独调用知识沉淀流程"""
        initial_state = {
            "user_input": "",
            "intent": "settle",
            "intent_confidence": 1.0,
            "slots": {},
            "slots_complete": True,
            "follow_up": None,
            "response": "",
            "ticket_id": ticket.get("ticket_id"),
            "tool_calls": [],
            "assign_result": {},
            "knowledge_result": {},
            "step": "",
        }
        # 直接走知识沉淀节点
        result = self.knowledge_agent.settle(ticket)
        return result
