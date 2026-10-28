"""
FunctionCall 工具定义
定义工单系统的所有可调用工具，供 DeepSeek Function Calling 使用

底层统一走 data.ingestion.ticket_service：
- 创建工单：立即写入 ES 关键词（不生成向量）
- 查询状态：ES 关键词精确查询
- 派单：更新「已委派」并推送部门 Kafka Topic
"""
import logging

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
        # 仅用于本轮对话的“最近创建工单”兜底，ES 仍是唯一事实来源
        self._recent_tickets = {}

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
        """创建工单：立即写入 ES 关键词/全文字段，状态「已创建」"""
        from data.ingestion.ticket_service import create_ticket as svc_create

        ticket = svc_create({
            "problem_type": problem_type,
            "category": problem_type,
            "description": description,
            "product": product,
            "urgency": urgency,
        }, es_client=self.es)

        ticket_id = ticket["ticket_id"]
        self._recent_tickets[ticket_id] = ticket

        logger.info(f"工单创建成功: {ticket_id} (状态: {ticket.get('status')})")
        return {
            "success": True,
            "ticket_id": ticket_id,
            "status": ticket.get("status"),
            "message": (
                f"工单 {ticket_id} 已创建并写入工单库，"
                f"问题类型: {problem_type}，紧急程度: {urgency}"
            ),
        }

    def query_ticket_status(self, ticket_id: str) -> dict:
        """查询工单状态：ES 关键词精确查询优先"""
        from data.ingestion.ticket_service import get_ticket

        ticket = get_ticket(ticket_id, es_client=self.es) or self._recent_tickets.get(ticket_id)

        if not ticket:
            return {"success": False, "message": f"未找到工单 {ticket_id}"}

        return {
            "success": True,
            "ticket": {
                "ticket_id": ticket.get("ticket_id"),
                "status": ticket.get("status"),
                "problem_type": ticket.get("problem_type") or ticket.get("category"),
                "description": ticket.get("description"),
                "urgency": ticket.get("urgency"),
                "assigned_to": ticket.get("assigned_to"),
                "resolution": ticket.get("resolution"),
                "created_at": ticket.get("created_at"),
                "assigned_at": ticket.get("assigned_at"),
                "resolved_at": ticket.get("resolved_at"),
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

    def assign_engineer(self, ticket_id: str = None, skill_group: str = None,
                        reason: str = None) -> dict:
        """派单：更新 ES「已委派」并通过 Kafka 推送到部门后台"""
        from data.ingestion.ticket_service import assign_ticket, find_latest_ticket

        # 未提供工单号时，优先取本轮最近创建的工单，再取 ES 最新工单
        if not ticket_id and self._recent_tickets:
            ticket_id = list(self._recent_tickets.keys())[-1]
        if not ticket_id:
            latest = find_latest_ticket(es_client=self.es)
            ticket_id = latest.get("ticket_id")
        if not ticket_id:
            return {"success": False, "message": "未提供工单号，且当前无可用工单"}
        if not skill_group:
            return {"success": False, "message": "未提供目标技能组"}

        result = assign_ticket(
            ticket_id=ticket_id,
            skill_group=skill_group,
            reason=reason,
            es_client=self.es,
        )
        self._recent_tickets[ticket_id] = result.get("ticket", {})

        return {
            "success": result.get("success", False),
            "ticket_id": ticket_id,
            "skill_group": skill_group,
            "status": result.get("status"),
            "kafka_pushed": result.get("kafka_pushed", False),
            "message": result.get("message", f"工单 {ticket_id} 已派发给 {skill_group}"),
        }
