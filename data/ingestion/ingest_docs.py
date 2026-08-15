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
            "status": {"type": "keyword"},
            "content_vector": {
                "type": "dense_vector",
                "dims": VECTOR_DIMS,
                "index": True,
                "similarity": "cosine",
            },
            "created_date": {"type": "date"},
            "created_at": {"type": "date"},
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
    """创建所有 ES 索引"""
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
            logger.info(f"索引 {name} 已存在，跳过")


def ingest_ticket(ticket_data: dict, content_vector: list = None) -> str:
    """导入单条工单到 ES（content_vector 可复用已计算的向量，避免重复调用 Embedding）"""
    if content_vector is None:
        text_for_vector = f"{ticket_data.get('description') or ''} {ticket_data.get('resolution') or ''}"
        content_vector = embedder.embed_text(text_for_vector)
    ticket_data["content_vector"] = content_vector
    ticket_data.setdefault("created_date", datetime.now().isoformat())
    ticket_data.setdefault("status", "open")

    doc_id = ticket_data.get("ticket_id")
    es.index(
        index="tickets",
        id=doc_id,
        document=ticket_data,
    )
    logger.info(f"工单 {doc_id} 导入成功")
    return doc_id


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


def add_ticket(ticket_data: dict) -> str:
    """新增工单：持久化到本地知识源 + 入库 ES"""
    ticket_data.setdefault(
        "ticket_id",
        f"GD{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}",
    )
    _append_source_file("tickets.json", ticket_data)
    return ingest_ticket(ticket_data)


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
        ingest_ticket(t)

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
