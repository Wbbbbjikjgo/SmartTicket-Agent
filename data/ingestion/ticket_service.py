"""
工单全生命周期服务

流程：
1. 创建工单 → 立即写入 ES 关键词/全文字段（不生成向量）
2. 智能派单 → 更新状态「已委派」并通过 Kafka 推送到对应部门
3. 部门处理 → 人工/AI 生成解决方案
4. 解决工单 → 更新状态「已解决」，由 Kafka 消费者沉淀向量与知识库
"""
import os
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

# ========== 状态定义 ==========
STATUS_CREATED = "已创建"
STATUS_ASSIGNED = "已委派"
STATUS_RESOLVED = "已解决"

# ========== 技能组与部门 Topic 映射 ==========
SKILL_GROUPS = ["IT支持组", "维修工程师", "财务组", "客服组"]

SKILL_GROUP_TOPICS = {
    "IT支持组": "ticket-dept-it",
    "维修工程师": "ticket-dept-maintenance",
    "财务组": "ticket-dept-finance",
    "客服组": "ticket-dept-service",
}

DEFAULT_GROUP = "客服组"


def topic_for_group(skill_group: str) -> str:
    """技能组 → 部门 Kafka Topic"""
    return SKILL_GROUP_TOPICS.get(skill_group, SKILL_GROUP_TOPICS[DEFAULT_GROUP])


def _now() -> str:
    return datetime.now().isoformat()


def new_ticket_id() -> str:
    return f"GD{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}"


def _es(es_client=None):
    if es_client is not None:
        return es_client
    from elasticsearch import Elasticsearch
    return Elasticsearch(os.getenv("ES_HOST", "http://localhost:9200"))


# ========== 创建 ==========

def create_ticket(ticket_data: dict, es_client=None) -> dict:
    """
    创建工单：立即写入 ES（关键词 + 全文），不生成向量。
    未解决的工单不会污染向量知识库。
    """
    from data.ingestion.ingest_docs import ingest_ticket, normalize_status

    ticket = dict(ticket_data)
    ticket.setdefault("ticket_id", new_ticket_id())
    ticket["status"] = normalize_status(ticket.get("status") or STATUS_CREATED)
    ticket.setdefault("created_at", _now())
    ticket.setdefault("assigned_to", None)

    ingest_ticket(ticket, with_vector=False, es_client=es_client)
    logger.info(f"工单已创建并写入 ES 关键词: {ticket['ticket_id']} (状态: {ticket['status']})")
    return ticket


# ========== 查询 ==========

def get_ticket(ticket_id: str, es_client=None) -> dict:
    """按工单号查询（ES 关键词精确匹配）"""
    from data.ingestion.ingest_docs import get_ticket as _get_ticket
    return _get_ticket(ticket_id, es_client=es_client)


def find_latest_ticket(es_client=None) -> dict:
    """获取最近创建的工单（用于 FunctionCall 未传工单号时兜底）"""
    client = _es(es_client)
    try:
        resp = client.search(
            index="tickets",
            body={
                "size": 1,
                "query": {"match_all": {}},
                "sort": [{"created_at": {"order": "desc", "missing": "_last"}}],
            },
        )
        hits = resp.get("hits", {}).get("hits", [])
        return hits[0]["_source"] if hits else {}
    except Exception as e:
        logger.warning(f"查询最近工单失败: {e}")
        return {}


def list_tickets(skill_group: str = None, statuses: list = None,
                 limit: int = 50, es_client=None) -> list:
    """按技能组/状态查询工单列表（部门后台工作台）"""
    client = _es(es_client)
    must = []
    if skill_group:
        must.append({"term": {"assigned_to": skill_group}})
    if statuses:
        must.append({"terms": {"status": list(statuses)}})

    body = {
        "size": limit,
        "query": {"bool": {"must": must}} if must else {"match_all": {}},
        "sort": [
            {"created_at": {"order": "desc", "missing": "_last"}},
        ],
    }
    try:
        resp = client.search(index="tickets", body=body)
        return [hit["_source"] for hit in resp["hits"]["hits"]]
    except Exception as e:
        logger.error(f"查询工单列表失败: {e}")
        return []


# ========== 派单 ==========

def assign_ticket(ticket_id: str, skill_group: str, reason: str = None,
                  es_client=None) -> dict:
    """
    派单：更新 ES 状态为「已委派」，并通过 Kafka 推送到目标部门后台。
    """
    from data.ingestion.ingest_docs import (
        update_ticket, _ticket_content, _ticket_keywords,
    )

    if skill_group not in SKILL_GROUPS:
        logger.warning(f"未知技能组「{skill_group}」，回退到{DEFAULT_GROUP}")
        skill_group = DEFAULT_GROUP

    ticket = get_ticket(ticket_id, es_client=es_client) or {"ticket_id": ticket_id}
    now = _now()
    updates = {
        "status": STATUS_ASSIGNED,
        "assigned_to": skill_group,
        "assign_reason": reason,
        "assigned_at": now,
        "updated_date": now,
    }
    ticket.update(updates)
    # 派单后同步更新全文/关键词字段，便于关键词检索命中部门与派单理由
    updates["content"] = _ticket_content(ticket)
    updates["keywords"] = _ticket_keywords(ticket)
    ticket.update({"content": updates["content"], "keywords": updates["keywords"]})
    ok = update_ticket(ticket_id, updates, es_client=es_client)

    kafka_pushed = _push_to_department(ticket, skill_group)
    logger.info(f"工单派单: {ticket_id} → {skill_group} (Kafka: {'成功' if kafka_pushed else '未推送'})")

    return {
        "success": ok,
        "ticket_id": ticket_id,
        "skill_group": skill_group,
        "status": STATUS_ASSIGNED,
        "kafka_pushed": kafka_pushed,
        "ticket": ticket,
        "message": f"工单 {ticket_id} 已派发给 {skill_group}",
    }


def _push_to_department(ticket: dict, skill_group: str) -> bool:
    """Kafka 推送到部门 Topic（不可用时降级为仅 ES）"""
    producer = None
    try:
        from data.ingestion.kafka_queue import TicketProducer
        producer = TicketProducer()
        if not producer.available:
            return False
        return producer.send_to_department(ticket, skill_group)
    except Exception as e:
        logger.warning(f"Kafka 部门推送失败（已降级为 ES 记录）: {e}")
        return False
    finally:
        if producer is not None:
            producer.close()


def mark_assigned_from_event(ticket: dict) -> bool:
    """部门 Topic 消费者：根据 Kafka 事件确认工单已进入部门后台（幂等）"""
    ticket_id = ticket.get("ticket_id")
    if not ticket_id:
        return False
    from data.ingestion.ingest_docs import update_ticket

    updates = {
        "status": STATUS_ASSIGNED,
        "assigned_to": ticket.get("assigned_to") or ticket.get("skill_group"),
        "assign_reason": ticket.get("assign_reason"),
        "assigned_at": ticket.get("assigned_at") or _now(),
    }
    return update_ticket(ticket_id, updates)


# ========== 解决 ==========

def resolve_ticket(ticket_id: str, resolution: str, satisfaction: float = None,
                   es_client=None, via_kafka: bool = True) -> dict:
    """
    标记工单已解决：
    1. 立即更新 ES 关键词字段与状态「已解决」
    2. 通过 Kafka 发送解决事件，由消费者沉淀向量与知识库
    3. Kafka 不可用时同步沉淀，保证数据不丢
    """
    from data.ingestion.ingest_docs import update_ticket, _ticket_content, _ticket_keywords

    resolution = (resolution or "").strip()
    if not resolution:
        return {"success": False, "message": "解决方案不能为空"}

    ticket = get_ticket(ticket_id, es_client=es_client)
    if not ticket:
        return {"success": False, "message": f"未找到工单 {ticket_id}"}

    now = _now()
    updates = {
        "resolution": resolution,
        "status": STATUS_RESOLVED,
        "resolved_at": now,
        "updated_date": now,
        "vector_stored": False,
        "knowledge_settled": False,
    }
    if satisfaction is not None:
        updates["satisfaction"] = satisfaction

    ticket.update(updates)
    ticket["content"] = _ticket_content(ticket)
    ticket["keywords"] = _ticket_keywords(ticket)
    updates["content"] = ticket["content"]
    updates["keywords"] = ticket["keywords"]

    ok = update_ticket(ticket_id, updates, es_client=es_client)

    kafka_pushed = False
    if via_kafka:
        kafka_pushed = _push_resolution(ticket)

    if not kafka_pushed:
        # 没有消费者可用时立即沉淀，避免向量/知识丢失
        persist_resolution(ticket_id, es_client=es_client)

    return {
        "success": ok,
        "ticket_id": ticket_id,
        "status": STATUS_RESOLVED,
        "kafka_pushed": kafka_pushed,
        "message": "已标记解决，正在异步沉淀知识库" if kafka_pushed else "已标记解决并完成知识沉淀",
    }


def _push_resolution(ticket: dict) -> bool:
    """Kafka 发送解决事件"""
    producer = None
    try:
        from data.ingestion.kafka_queue import TicketProducer
        producer = TicketProducer()
        if not producer.available:
            return False
        return producer.send_resolution(ticket)
    except Exception as e:
        logger.warning(f"Kafka 解决事件发送失败: {e}")
        return False
    finally:
        if producer is not None:
            producer.close()


def persist_resolution(ticket_id: str, es_client=None) -> dict:
    """
    Kafka 消费者处理解决事件：
    - 为已解决工单生成向量（此时才有答案，向量才有意义）
    - 写入本地知识源
    - 调用知识沉淀 Agent 写入 knowledge_base
    """
    from data.ingestion.ingest_docs import (
        update_ticket, append_resolved_ticket, _ticket_content, _ticket_keywords,
    )

    ticket = get_ticket(ticket_id, es_client=es_client)
    if not ticket:
        logger.warning(f"解决事件对应工单不存在: {ticket_id}")
        return {"success": False, "message": "工单不存在"}

    if not ticket.get("resolution"):
        logger.info(f"工单 {ticket_id} 尚无解决方案，跳过向量沉淀")
        return {"success": False, "message": "工单尚无解决方案"}

    if ticket.get("vector_stored") and ticket.get("knowledge_settled"):
        return {"success": True, "skipped": True, "message": "已沉淀"}

    from data.ingestion.embedding_service import DashScopeEmbedding
    embedder = DashScopeEmbedding()

    if not ticket.get("vector_stored"):
        text = f"{ticket.get('description') or ''} {ticket.get('resolution') or ''}".strip()
        vector = embedder.embed_text(text) if text else None
        updates = {
            "content_vector": vector,
            "vector_stored": vector is not None,
            "content": _ticket_content(ticket),
            "keywords": _ticket_keywords(ticket),
        }
        update_ticket(ticket_id, updates, es_client=es_client)
        ticket.update(updates)
        logger.info(f"工单 {ticket_id} 向量沉淀完成")

    append_resolved_ticket(ticket)

    knowledge_settled = bool(ticket.get("knowledge_settled"))
    if not knowledge_settled:
        try:
            from agents.knowledge_agent import KnowledgeAgent
            agent = KnowledgeAgent(es_client=_es(es_client), embedder=embedder)
            result = agent.settle(ticket)
            knowledge_settled = bool(result.get("success"))
            logger.info(f"工单 {ticket_id} 知识沉淀: {result.get('message', '成功')}")
        except Exception as e:
            logger.error(f"工单 {ticket_id} 知识沉淀失败: {e}")

    update_ticket(ticket_id, {"knowledge_settled": knowledge_settled}, es_client=es_client)

    return {
        "success": True,
        "ticket_id": ticket_id,
        "vector_stored": bool(ticket.get("vector_stored")),
        "knowledge_settled": knowledge_settled,
    }


# ========== AI 辅助回复 ==========

REPLY_PROMPT = """你是一名专业的企业客服工程师。请根据工单信息，给出一段可以直接回复客户的解决方案。

要求：
1. 使用中文，语气专业、友好、简洁
2. 条理清晰，必要时分步骤说明
3. 只输出回复内容，不要输出 JSON 或额外解释

工单信息：
- 工单号：{ticket_id}
- 产品：{product}
- 问题类型：{problem_type}
- 紧急程度：{urgency}
- 问题描述：{description}
"""


def suggest_reply(ticket: dict) -> str:
    """调用大模型生成客服建议回复（部门后台可编辑后提交）"""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.3,
            max_tokens=1024,
        )
        prompt = REPLY_PROMPT.format(
            ticket_id=ticket.get("ticket_id", ""),
            product=ticket.get("product") or "未提供",
            problem_type=ticket.get("problem_type") or ticket.get("category") or "未分类",
            urgency=ticket.get("urgency") or "中",
            description=ticket.get("description") or "",
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        return (response.content or "").strip()
    except Exception as e:
        logger.error(f"AI 生成建议回复失败: {e}")
        return f"AI 生成失败：{e}\n\n请人工填写解决方案。"
