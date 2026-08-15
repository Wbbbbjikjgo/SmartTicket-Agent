"""
FunctionCall 工具定义
定义工单系统的所有可调用工具，供 DeepSeek Function Calling 使用
"""
import json
import uuid
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ========== FunctionCall 工具定义（JSON Schema） ==========

TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": "创建服务工单。当用户报告问题、故障或需求时调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_type": {
                        "type": "string",
                        "description": "问题类型",
                        "enum": ["登录问题", "系统故障", "网络异常", "设备故障", "财务问题", "其他"],
                    },
                    "description": {
                        "type": "string",
                        "description": "问题的详细描述",
                    },
                    "product": {
                        "type": "string",
                        "description": "相关产品或系统名称",
                    },
                    "urgency": {
                        "type": "string",
                        "description": "紧急程度",
                        "enum": ["高", "中", "低"],
                    },
                },
                "required": ["problem_type", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_ticket_status",
            "description": "查询工单状态和处理进度。当用户询问工单进度时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "string",
                        "description": "工单编号（如 GD202604240001）",
                    },
                },
                "required": ["ticket_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "从知识库中检索历史解决方案和FAQ。当用户询问解决方案或想查找类似问题的处理方法时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或问题描述",
                    },
                    "category": {
                        "type": "string",
                        "description": "知识类别（可选）",
                        "enum": ["登录问题", "系统故障", "网络异常", "设备故障", "财务问题"],
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assign_engineer",
            "description": "将工单派发给合适的工程师或技能组。当需要将工单转交给专业人员处理时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "string",
                        "description": "工单编号（如 GD202604240001）。若刚在本轮对话中创建了工单，可不传，系统将自动选择最近创建的工单。",
                    },
                    "skill_group": {
                        "type": "string",
                        "description": "目标技能组",
                        "enum": ["IT支持组", "维修工程师", "财务组", "客服组"],
                    },
                    "reason": {
                        "type": "string",
                        "description": "派单理由",
                    },
                },
                "required": ["skill_group"],
            },
        },
    },
]


# ========== 工具执行函数 ==========

class TicketTools:
    """工单工具执行器"""

    def __init__(self, es_client=None, search_pipeline=None):
        """
        es_client: Elasticsearch 客户端
        search_pipeline: HybridSearchPipeline 实例
        """
        self.es = es_client
        self.search_pipeline = search_pipeline
        # 内存中的工单存储（生产环境应使用 ES 或数据库）
        self._tickets = {}

    def execute_tool(self, tool_name: str, arguments: dict) -> dict:
        """执行工具调用"""
        tool_map = {
            "create_ticket": self.create_ticket,
            "query_ticket_status": self.query_ticket_status,
            "search_knowledge": self.search_knowledge,
            "assign_engineer": self.assign_engineer,
        }

        func = tool_map.get(tool_name)
        if not func:
            return {"error": f"未知工具: {tool_name}"}

        try:
            return func(**arguments)
        except Exception as e:
            logger.error(f"工具 {tool_name} 执行失败: {e}")
            return {"error": str(e)}

    def create_ticket(self, problem_type: str, description: str,
                      product: str = None, urgency: str = "中") -> dict:
        """创建工单"""
        ticket_id = f"GD{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}"
        ticket = {
            "ticket_id": ticket_id,
            "problem_type": problem_type,
            "description": description,
            "product": product,
            "urgency": urgency,
            "status": "open",
            "created_at": datetime.now().isoformat(),
            "assigned_to": None,
        }
        self._tickets[ticket_id] = ticket

        # 写入 ES（如果可用，向量化入库）
        if self.es:
            try:
                from data.ingestion.ingest_docs import ingest_ticket
                ingest_ticket(ticket)
            except Exception as e:
                logger.warning(f"写入 ES 失败: {e}")

        logger.info(f"工单创建成功: {ticket_id}")
        return {
            "success": True,
            "ticket_id": ticket_id,
            "message": f"工单 {ticket_id} 已创建，问题类型: {problem_type}，紧急程度: {urgency}",
        }

    def query_ticket_status(self, ticket_id: str) -> dict:
        """查询工单状态"""
        # 先从内存查
        ticket = self._tickets.get(ticket_id)

        # 内存没有则查 ES
        if not ticket and self.es:
            try:
                resp = self.es.get(index="tickets", id=ticket_id)
                ticket = resp["_source"]
            except Exception:
                pass

        if not ticket:
            return {"success": False, "message": f"未找到工单 {ticket_id}"}

        return {
            "success": True,
            "ticket": {
                "ticket_id": ticket.get("ticket_id"),
                "status": ticket.get("status"),
                "problem_type": ticket.get("problem_type"),
                "description": ticket.get("description"),
                "urgency": ticket.get("urgency"),
                "assigned_to": ticket.get("assigned_to"),
                "created_at": ticket.get("created_at"),
            },
        }

    def search_knowledge(self, query: str, category: str = None) -> dict:
        """检索知识库"""
        if not self.search_pipeline:
            return {"success": False, "message": "检索服务未初始化"}

        results = self.search_pipeline.search(query, top_k=5)
        return {
            "success": True,
            "query": query,
            "results": [
                {
                    "title": self._extract_title(r.get("source", {}), r.get("content", "")),
                    "content": r.get("content", ""),
                    "solution": r.get("source", {}).get("solution", "") or r.get("source", {}).get("answer", ""),
                    "score": r.get("rerank_score", r.get("score", 0)),
                    "category": r.get("source", {}).get("category", ""),
                    "index": r.get("index", ""),
                }
                for r in results
            ],
        }

    @staticmethod
    def _extract_title(source: dict, content: str) -> str:
        """从不同来源的文档中提取标题（知识用 title、FAQ 用 question、工单用 description）"""
        for field in ("title", "question", "description"):
            if source.get(field):
                return source[field]
        return (content or "")[:40]

    def assign_engineer(self, ticket_id: str = None, skill_group: str = None, reason: str = None) -> dict:
        """派单给工程师（ticket_id 缺省时自动选择最近创建的工单）"""
        # 未提供工单号时，自动取最近创建的工单
        if not ticket_id and self._tickets:
            ticket_id = sorted(self._tickets.keys())[-1]
        if not ticket_id:
            return {"success": False, "message": "未提供工单号，且当前会话中无可用工单"}
        if not skill_group:
            return {"success": False, "message": "未提供目标技能组"}

        ticket = self._tickets.get(ticket_id)
        if not ticket and self.es:
            try:
                resp = self.es.get(index="tickets", id=ticket_id)
                ticket = resp["_source"]
            except Exception:
                pass

        if not ticket:
            return {"success": False, "message": f"未找到工单 {ticket_id}"}

        # 更新工单
        ticket["assigned_to"] = skill_group
        ticket["status"] = "assigned"
        ticket["assign_reason"] = reason
        self._tickets[ticket_id] = ticket

        if self.es:
            try:
                self.es.index(index="tickets", id=ticket_id, document=ticket)
            except Exception as e:
                logger.warning(f"更新 ES 失败: {e}")

        return {
            "success": True,
            "message": f"工单 {ticket_id} 已派发给 {skill_group}" + (f"，原因: {reason}" if reason else ""),
        }
