"""
工单创建/查询 Agent
通过 DeepSeek FunctionCall 自主决策创建或查询工单
"""
import os
import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是智能工单系统的工单处理助手。你可以帮助用户：
1. 创建工单 - 当用户报告问题时
2. 查询工单 - 当用户询问工单状态时
3. 搜索知识 - 当用户寻找解决方案时

工单状态说明：
- 已创建：工单已写入系统
- 已委派：工单已派发到对应部门处理
- 已解决：部门已给出解决方案

工作规则：
- 创建工单前，确保收集到问题类型和问题描述（必填）
- 如果信息不完整，友好地追问用户补充
- 调用工具时，严格按照工具参数要求传入参数
- 查询工单时必须通过 query_ticket_status 工具查询 ES，不要臆造状态
- 回复用户时使用中文，语气友好专业
"""


class TicketAgent:
    """工单创建/查询 Agent"""

    def __init__(self, ticket_tools):
        """
        ticket_tools: TicketTools 实例
        """
        self.ticket_tools = ticket_tools
        self.llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.3,
            max_tokens=2048,
        )
        # 绑定 FunctionCall 工具
        # 说明：进程内 Agent 使用 DeepSeek 原生 FunctionCall（bind_tools）做工具决策，
        #      工具 Schema 与 tools/mcp_ticket_server.py 的 MCP 服务共享同一份 TOOLS_DEFINITION，
        #      执行统一走 ticket_tools.execute_tool（与 MCP handle_tool_call 同后端）。
        #      MCP 用于跨进程/外部系统通过标准协议调用，两者职责不同、底层一致。
        from tools.function_tools import TOOLS_DEFINITION
        self.tools_def = TOOLS_DEFINITION

    def create_ticket(self, problem_type: str, description: str,
                      product: str = None, urgency: str = "中") -> dict:
        """直接创建工单（走统一工具后端：立即写入 ES 关键词，状态「已创建」）"""
        return self.ticket_tools.execute_tool("create_ticket", {
            "problem_type": problem_type,
            "description": description,
            "product": product,
            "urgency": urgency,
        })

    def query_status(self, ticket_id: str) -> dict:
        """直接查询工单状态（ES 关键词精确查询）"""
        return self.ticket_tools.execute_tool("query_ticket_status", {"ticket_id": ticket_id})

    def process(self, user_input: str, context: dict = None) -> dict:
        """
        处理用户输入，自主决策是否调用工具
        返回: {"response": str, "tool_calls": list, "ticket_id": str or None}
        """
        messages = [SystemMessage(content=SYSTEM_PROMPT)]

        # 添加上下文
        if context:
            context_msg = f"当前对话上下文：{json.dumps(context, ensure_ascii=False)}"
            messages.append(SystemMessage(content=context_msg))

        messages.append(HumanMessage(content=user_input))

        try:
            tool_results = []
            # 循环调用：LLM 可能连续多轮调用工具（最多 3 轮）
            for _ in range(3):
                response = self.llm.bind_tools(self.tools_def).invoke(messages)
                messages.append(response)

                # 无工具调用，视为最终回复
                if not response.tool_calls:
                    break

                # 逐条执行工具，并用 ToolMessage 回填（必须携带 tool_call_id）
                for tc in response.tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc.get("args", {})
                    logger.info(f"FunctionCall: {tool_name}({tool_args})")

                    result = self.ticket_tools.execute_tool(tool_name, tool_args)
                    tool_results.append({
                        "tool": tool_name,
                        "args": tool_args,
                        "result": result,
                    })
                    messages.append(ToolMessage(
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=tc["id"],
                    ))

            final_text = response.content or "已为您处理完成。"
            if not response.tool_calls and not response.content:
                final_text = "已为您处理完成。"

            # 提取工单ID
            ticket_id = None
            for tr in tool_results:
                if isinstance(tr.get("result"), dict) and tr["result"].get("ticket_id"):
                    ticket_id = tr["result"]["ticket_id"]

            return {
                "response": final_text,
                "tool_calls": tool_results,
                "ticket_id": ticket_id,
            }

        except Exception as e:
            logger.error(f"TicketAgent 处理失败: {e}")
            return {
                "response": f"抱歉，处理您的请求时出现错误，请稍后重试。",
                "tool_calls": [],
                "ticket_id": None,
            }
