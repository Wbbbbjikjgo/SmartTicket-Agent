"""
Elasticsearch 知识库数据入库脚本
负责：创建索引、导入历史工单/FAQ/知识条目
"""
import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

from elasticsearch import Elasticsearch

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
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

# ========== 索引 Mapping 定义 ==========

TICKETS_MAPPING = {
    "mappings": {
        "properties": {
            "ticket_id": {"type": "keyword"},
            "product": {"type": "keyword"},
            "category": {"type": "keyword"},
            "priority": {"type": "keyword"},
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


def ingest_ticket(ticket_data: dict):
    """导入单条工单到 ES"""
    # 生成向量
    text_for_vector = f"{ticket_data.get('description', '')} {ticket_data.get('resolution', '')}"
    ticket_data["content_vector"] = embedder.embed_text(text_for_vector)
    ticket_data.setdefault("created_date", datetime.now().isoformat())
    ticket_data.setdefault("status", "open")

    doc_id = ticket_data.get("ticket_id", None)
    es.index(
        index="tickets",
        id=doc_id,
        document=ticket_data,
    )
    logger.info(f"工单 {doc_id} 导入成功")


def ingest_knowledge(kb_data: dict):
    """导入单条知识到 ES"""
    text_for_vector = f"{kb_data.get('title', '')} {kb_data.get('content', '')} {kb_data.get('solution', '')}"
    kb_data["content_vector"] = embedder.embed_text(text_for_vector)
    kb_data.setdefault("create_date", datetime.now().isoformat())
    kb_data.setdefault("quality_score", 0.8)

    doc_id = kb_data.get("kb_id", None)
    es.index(
        index="knowledge_base",
        id=doc_id,
        document=kb_data,
    )
    logger.info(f"知识条目 {doc_id} 导入成功")


def ingest_faq(faq_data: dict):
    """导入单条 FAQ 到 ES"""
    text_for_vector = f"{faq_data.get('question', '')} {faq_data.get('answer', '')}"
    faq_data["content_vector"] = embedder.embed_text(text_for_vector)

    doc_id = faq_data.get("faq_id", None)
    es.index(
        index="faq",
        id=doc_id,
        document=faq_data,
    )
    logger.info(f"FAQ {doc_id} 导入成功")


def ingest_sample_data():
    """导入示例数据（用于测试）"""
    # 示例工单
    sample_tickets = [
        {
            "ticket_id": "GD202604240001",
            "product": "手环X1",
            "category": "续航问题",
            "priority": "高",
            "description": "充满电后待机不到24小时自动关机",
            "resolution": "校准电池并激活省电模式后恢复正常",
            "status": "closed",
        },
        {
            "ticket_id": "GD202604240002",
            "product": "OA系统",
            "category": "登录问题",
            "priority": "中",
            "description": "用户输入正确密码后仍提示认证失败，清除缓存后恢复",
            "resolution": "清除浏览器缓存和Cookie后重新登录",
            "status": "closed",
        },
        {
            "ticket_id": "GD202604240003",
            "product": "生产服务器A",
            "category": "系统故障",
            "priority": "高",
            "description": "服务器返回502错误，持续约30分钟，影响全部API接口",
            "resolution": "重启Nginx服务并扩容后端实例，问题恢复",
            "status": "closed",
        },
    ]

    # 示例知识
    sample_knowledge = [
        {
            "kb_id": "KB001",
            "title": "手环X1续航问题排查指南",
            "content": "手环X1出现续航异常时，按以下步骤排查：1.检查固件版本 2.校准电池 3.激活省电模式",
            "category": "设备故障",
            "tags": ["手环", "续航", "电池"],
            "solution": "校准电池并激活省电模式，如仍异常则返厂检测",
        },
        {
            "kb_id": "KB002",
            "title": "502错误通用排查方案",
            "content": "502 Bad Gateway通常由后端服务不可用引起，排查步骤：1.检查后端服务状态 2.检查Nginx配置 3.检查网络连接",
            "category": "系统故障",
            "tags": ["502", "Nginx", "网关"],
            "solution": "重启后端服务和Nginx，如频繁出现需考虑扩容",
        },
    ]

    # 示例 FAQ
    sample_faq = [
        {
            "faq_id": "FAQ001",
            "question": "忘记密码怎么办？",
            "answer": "请点击登录页「忘记密码」链接，通过注册邮箱重置密码。如邮箱也无法访问，请联系IT支持。",
            "category": "登录问题",
            "tags": ["密码", "重置"],
        },
        {
            "faq_id": "FAQ002",
            "question": "如何申请退款？",
            "answer": "请在订单详情页点击「申请退款」，填写退款原因后提交。财务组将在3个工作日内审核处理。",
            "category": "财务问题",
            "tags": ["退款", "订单"],
        },
    ]

    logger.info("开始导入示例数据...")
    for t in sample_tickets:
        ingest_ticket(t)
    for k in sample_knowledge:
        ingest_knowledge(k)
    for f in sample_faq:
        ingest_faq(f)
    logger.info("示例数据导入完成")


if __name__ == "__main__":
    logger.info("=== ES 知识库初始化 ===")
    create_indices()
    ingest_sample_data()
    logger.info("=== 初始化完成 ===")
