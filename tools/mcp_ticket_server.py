"""
MCP Server 封装
将工单系统 API 封装为 MCP (Model Context Protocol) 服务
供 Agent 通过 MCP 协议统一调用
"""
import os
import sys
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MCPTicketServer:
    """
    MCP 工单服务
    将工单操作封装为标准 MCP 工具描述
    支持 stdio / SSE 两种传输方式
    """

    def __init__(self, ticket_tools):
        """
        ticket_tools: TicketTools 实例
        """
        self.ticket_tools = ticket_tools

    def get_tool_descriptions(self) -> list:
        """获取 MCP 工具描述列表"""
        from tools.function_tools import TOOLS_DEFINITION
        return TOOLS_DEFINITION

    async def handle_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """处理 MCP 工具调用"""
        logger.info(f"MCP 工具调用: {tool_name}({json.dumps(arguments, ensure_ascii=False)})")
        result = self.ticket_tools.execute_tool(tool_name, arguments)
        logger.info(f"MCP 工具结果: {json.dumps(result, ensure_ascii=False)[:200]}")
        return result

    def get_mcp_config(self) -> dict:
        """获取 MCP Server 配置（用于 langchain-mcp-adapters）"""
        return {
            "ticket_system": {
                "command": "python",
                "args": ["tools/mcp_ticket_server.py"],
                "transport": "stdio",
            }
        }


# ========== 独立运行 MCP Server（stdio 模式） ==========

if __name__ == "__main__":
    # 确保项目根目录在 path 中
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    from elasticsearch import Elasticsearch
    from tools.function_tools import TicketTools, TOOLS_DEFINITION

    # 初始化 ES 客户端与检索管道，使工具可真正查询/检索
    es_client = Elasticsearch(os.getenv("ES_HOST", "http://localhost:9200"))

    search_pipeline = None
    try:
        from retrieval.hybrid_search import HybridSearchPipeline
        search_pipeline = HybridSearchPipeline()
    except Exception as e:
        logger.warning(f"检索管道初始化失败，search_knowledge 将不可用: {e}")

    tools = TicketTools(es_client=es_client, search_pipeline=search_pipeline)
    server = MCPTicketServer(tools)

    # stdio 模式：从 stdin 读取 JSON-RPC 请求
    logger.info("MCP Ticket Server 启动（stdio 模式）")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            method = request.get("method", "")

            if method == "tools/list":
                response = {"result": server.get_tool_descriptions()}
            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                result = server.handle_tool_call(tool_name, arguments)
                response = {"result": result}
            else:
                response = {"error": f"未知方法: {method}"}

            print(json.dumps(response, ensure_ascii=False), flush=True)

        except Exception as e:
            error_resp = {"error": str(e)}
            print(json.dumps(error_resp, ensure_ascii=False), flush=True)
