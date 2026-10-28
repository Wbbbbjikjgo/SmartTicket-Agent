"""
Elasticsearch 知识库数据入库脚本
负责：创建索引、导入历史工单/FAQ/知识条目、本地知识源管理
"""
import os
import sys
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

# 添加项目根目录到 path
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

# 加载 .env 环境变量
load_dotenv(ROOT_DIR / ".env")

from data.ingestion.embedding_service import DashScopeEmbedding

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ES 连接
ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
es = Elasticsearch(ES_HOST)

# Embedding 服务
embedder = DashScopeEmbedding()

# 索引配置
VECTOR_DIMS = int(os.getenv("VECTOR_DIMS", "1024"))

# 本地知识源目录（作为知识/FAQ/工单的"总的知识源"，扫描后入库 ES）
KNOWLEDGE_DIR = ROOT_DIR / "data" / "knowledge"

# ========== 索引 Mapping 定义 ==========

TICKETS_MAPPING = {
    "mappings": {
        "properties": {
            "ticket_id": {"type": "keyword"},
            "product": {"type": "keyword"},
            "problem_type": {"type": "keyword"},
            "category": {"type": "keyword"},
            "priority": {"type": "keyword"},
            "urgency": {"type": "keyword"},
            "assigned_to": {"type": "keyword"},
            "assign_reason": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
            "error_code": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "description": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "resolution": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            # 全文检索字段：工单创建时即写入，供 BM25 关键词检索
            "content": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            # 关键词字段：问题类型/产品/错误码/标签等，供关键词命中
            "keywords": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
                "fields": {"raw": {"type": "keyword"}},
            },
            "status": {"type": "keyword"},
            "satisfaction": {"type": "float"},
            "vector_stored": {"type": "boolean"},
            "knowledge_settled": {"type": "boolean"},
            "content_vector": {
                "type": "dense_vector",
                "dims": VECTOR_DIMS,
                "index": True,
                "similarity": "cosine",
            },
            "created_date": {"type": "date"},
            "created_at": {"type": "date"},
            "assigned_at": {"type": "date"},
            "resolved_at": {"type": "date"},
            "updated_date": {"type": "date"},
        }
    }
}

KNOWLEDGE_MAPPING = {
    "mappings": {
        "properties": {
            "kb_id": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "content": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "category": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "solution": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "source_ticket": {"type": "keyword"},
            "quality_score": {"type": "float"},
            "content_vector": {
                "type": "dense_vector",
                "dims": VECTOR_DIMS,
                "index": True,
                "similarity": "cosine",
            },
            "create_date": {"type": "date"},
            "update_date": {"type": "date"},
        }
    }
}

FAQ_MAPPING = {
    "mappings": {
        "properties": {
            "faq_id": {"type": "keyword"},
            "question": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "answer": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "category": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "content_vector": {
                "type": "dense_vector",
                "dims": VECTOR_DIMS,
                "index": True,
                "similarity": "cosine",
            },
        }
    }
}


def create_indices():
    """创建所有 ES 索引（已存在时增量补齐新增字段）"""
    indices = {
        "tickets": TICKETS_MAPPING,
        "knowledge_base": KNOWLEDGE_MAPPING,
        "faq": FAQ_MAPPING,
    }
    for name, mapping in indices.items():
        if not es.indices.exists(index=name):
            es.indices.create(index=name, body=mapping)
            logger.info(f"索引 {name} 创建成功")
        else:
            # 增量补充 mapping 中新增的字段（如 content / keywords / 状态时间）
            try:
                es.indices.put_mapping(index=name, properties=mapping["mappings"]["properties"])
                logger.info(f"索引 {name} 已存在，mapping 已同步")
            except Exception as e:
                logger.warning(f"索引 {name} mapping 更新失败: {e}")


# 状态统一：历史数据兼容 open/assigned/closed → 中文状态
_STATUS_ALIASES = {
    "open": "已创建",
    "created": "已创建",
    "已创建": "已创建",
    "assigned": "已委派",
    "已委派": "已委派",
    "resolved": "已解决",
    "closed": "已解决",
    "已解决": "已解决",
}


def normalize_status(status: str) -> str:
    """统一工单状态为中文状态值"""
    return _STATUS_ALIASES.get(status or "", status or "已创建")


def _ticket_content(ticket: dict) -> str:
    """构造工单全文检索内容（创建时即可写入）"""
    fields = [
        "description", "resolution", "problem_type", "category",
        "product", "error_code", "assigned_to", "assign_reason",
    ]
    return " ".join(str(ticket[f]) for f in fields if ticket.get(f))


def _ticket_keywords(ticket: dict) -> str:
    """构造工单关键词字段（问题类型/产品/错误码/标签等）"""
    values = []
    for field in ("problem_type", "category", "product", "urgency", "error_code", "assigned_to"):
        if ticket.get(field):
            values.append(str(ticket[field]))
    tags = ticket.get("tags")
    if isinstance(tags, list):
        values.extend(str(t) for t in tags if t)
    elif tags:
        values.append(str(tags))
    # 去重并保持顺序
    return " ".join(dict.fromkeys(values))


def ingest_ticket(ticket_data: dict, content_vector: list = None,
                  with_vector: bool = True, es_client=None) -> str:
    """
    导入单条工单到 ES

    with_vector=False：仅写入关键词/全文字段（创建工单时使用，避免未解决工单占用向量）
    with_vector=True ：同时写入向量（解决后沉淀 / 历史工单导入时使用）
    """
    client = es_client or es
    doc = dict(ticket_data)

    doc["status"] = normalize_status(doc.get("status"))
    doc.setdefault("created_at", datetime.now().isoformat())
    doc.setdefault("created_date", doc["created_at"])
    doc["updated_date"] = datetime.now().isoformat()
    doc["content"] = doc.get("content") or _ticket_content(doc)
    doc["keywords"] = doc.get("keywords") or _ticket_keywords(doc)

    if content_vector is None and with_vector:
        text_for_vector = f"{doc.get('description') or ''} {doc.get('resolution') or ''}".strip()
        if text_for_vector:
            content_vector = embedder.embed_text(text_for_vector)

    if content_vector is not None:
        doc["content_vector"] = content_vector
        doc["vector_stored"] = True

    doc_id = doc.get("ticket_id")
    client.index(
        index="tickets",
        id=doc_id,
        document=doc,
    )
    logger.info(f"工单 {doc_id} 导入成功（向量: {'是' if content_vector is not None else '否'}）")
    return doc_id


def update_ticket(ticket_id: str, updates: dict, es_client=None) -> bool:
    """增量更新工单（不存在时自动创建）"""
    client = es_client or es
    doc = dict(updates)
    doc.setdefault("updated_date", datetime.now().isoformat())
    try:
        client.update(
            index="tickets",
            id=ticket_id,
            doc=doc,
            upsert={"ticket_id": ticket_id, **doc},
        )
        logger.info(f"工单 {ticket_id} 更新成功: {list(doc.keys())}")
        return True
    except Exception as e:
        logger.error(f"工单 {ticket_id} 更新失败: {e}")
        return False


def get_ticket(ticket_id: str, es_client=None) -> dict:
    """按工单号读取 ES 文档（关键词精确查询）"""
    client = es_client or es
    try:
        return client.get(index="tickets", id=ticket_id)["_source"]
    except Exception:
        return None


def ingest_knowledge(kb_data: dict, content_vector: list = None) -> str:
    """导入单条知识到 ES（content_vector 可复用已计算的向量）"""
    if content_vector is None:
        text_for_vector = f"{kb_data.get('title') or ''} {kb_data.get('content') or ''} {kb_data.get('solution') or ''}"
        content_vector = embedder.embed_text(text_for_vector)
    kb_data["content_vector"] = content_vector
    kb_data.setdefault("create_date", datetime.now().isoformat())
    kb_data.setdefault("quality_score", 0.8)

    doc_id = kb_data.get("kb_id")
    es.index(
        index="knowledge_base",
        id=doc_id,
        document=kb_data,
    )
    logger.info(f"知识条目 {doc_id} 导入成功")
    return doc_id


def ingest_faq(faq_data: dict, content_vector: list = None) -> str:
    """导入单条 FAQ 到 ES（content_vector 可复用已计算的向量）"""
    if content_vector is None:
        text_for_vector = f"{faq_data.get('question') or ''} {faq_data.get('answer') or ''}"
        content_vector = embedder.embed_text(text_for_vector)
    faq_data["content_vector"] = content_vector

    doc_id = faq_data.get("faq_id")
    es.index(
        index="faq",
        id=doc_id,
        document=faq_data,
    )
    logger.info(f"FAQ {doc_id} 导入成功")
    return doc_id


# ========== 本地知识源读写（总的知识源） ==========

def _read_source_file(filename: str) -> list:
    """读取本地知识源 JSON 文件（不存在或解析失败返回空列表）"""
    path = KNOWLEDGE_DIR / filename
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"读取本地知识源 {filename} 失败: {e}")
        return []


def _append_source_file(filename: str, data: dict):
    """追加一条记录到本地知识源 JSON 文件"""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    items = _read_source_file(filename)
    items.append(data)
    path = KNOWLEDGE_DIR / filename
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def append_resolved_ticket(ticket: dict):
    """将已解决工单沉淀到本地知识源（按工单号去重）"""
    items = _read_source_file("tickets.json")
    if any(t.get("ticket_id") == ticket.get("ticket_id") for t in items):
        return
    fields = (
        "ticket_id", "product", "problem_type", "category", "priority", "urgency",
        "description", "resolution", "status", "assigned_to", "error_code",
        "created_at", "assigned_at", "resolved_at",
    )
    payload = {k: ticket.get(k) for k in fields if ticket.get(k) is not None}
    _append_source_file("tickets.json", payload)


def add_ticket(ticket_data: dict) -> str:
    """新增工单：持久化到本地知识源 + 入库 ES（未解决工单不生成向量）"""
    ticket_data.setdefault(
        "ticket_id",
        f"GD{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}",
    )
    _append_source_file("tickets.json", ticket_data)
    resolved = normalize_status(ticket_data.get("status")) == "已解决"
    return ingest_ticket(ticket_data, with_vector=resolved)


def add_knowledge(kb_data: dict) -> str:
    """新增知识条目：持久化到本地知识源 + 入库 ES"""
    kb_data.setdefault("kb_id", f"KB{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}")
    _append_source_file("knowledge_base.json", kb_data)
    return ingest_knowledge(kb_data)


def add_faq(faq_data: dict) -> str:
    """新增 FAQ：持久化到本地知识源 + 入库 ES"""
    faq_data.setdefault("faq_id", f"FAQ{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}")
    _append_source_file("faq.json", faq_data)
    return ingest_faq(faq_data)


def load_knowledge_source():
    """扫描本地知识源目录，将工单/知识/FAQ 批量导入 ES"""
    logger.info("开始扫描本地知识源目录...")

    tickets = _read_source_file("tickets.json")
    for t in tickets:
        # 只有已给出解决方案的工单才生成向量
        ingest_ticket(t, with_vector=bool(t.get("resolution")))

    knowledge = _read_source_file("knowledge_base.json")
    for k in knowledge:
        ingest_knowledge(k)

    faqs = _read_source_file("faq.json")
    for f in faqs:
        ingest_faq(f)

    logger.info(f"本地知识源导入完成: 工单 {len(tickets)} 条, 知识 {len(knowledge)} 条, FAQ {len(faqs)} 条")


if __name__ == "__main__":
    logger.info("=== ES 知识库初始化 ===")
    create_indices()
    load_knowledge_source()
    logger.info("=== 初始化完成 ===")
