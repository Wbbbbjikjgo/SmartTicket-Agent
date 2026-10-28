"""
Kafka 工单消息队列

职责：
- 生产者：把派单后的工单推送到对应部门 Topic；把已解决工单推送到 solution Topic
- 消费者：部门 Topic 确认工单进入后台；solution Topic 触发向量与知识库沉淀
"""
import os
import json
import logging
import threading
from datetime import datetime
from typing import Callable

from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC_RESOLVED = os.getenv("KAFKA_TOPIC_RESOLVED", "ticket-resolved")
WORKER_GROUP = os.getenv("KAFKA_WORKER_GROUP", "ticket-resolution-worker")


def _department_topics() -> list:
    """获取所有部门 Topic（延迟导入，避免循环依赖）"""
    from data.ingestion.ticket_service import SKILL_GROUP_TOPICS
    return list(SKILL_GROUP_TOPICS.values())


def _all_topics() -> list:
    return [TOPIC_RESOLVED] + _department_topics()


def _ensure_topics():
    """确保所需 Topic 已创建（Kafka 自动建 Topic 关闭时也能工作）"""
    try:
        from kafka.admin import KafkaAdminClient, NewTopic

        admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP, client_id="smart-ticket-admin")
        existing = set(admin.list_topics())
        missing = [
            NewTopic(name=name, num_partitions=1, replication_factor=1)
            for name in _all_topics() if name not in existing
        ]
        if missing:
            admin.create_topics(missing)
            logger.info(f"Kafka Topic 已创建: {[t.name for t in missing]}")
        admin.close()
    except Exception as e:
        logger.warning(f"Kafka Topic 初始化失败（可能已存在或 Broker 未启动）: {e}")


class TicketProducer:
    """工单生产者：派单 → 部门 Topic；解决 → 解决 Topic"""

    def __init__(self):
        self.producer = None
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False, default=str).encode("utf-8"),
                acks="all",
                retries=3,
                linger_ms=10,
            )
            _ensure_topics()
            logger.info(f"Kafka Producer 初始化成功，连接: {KAFKA_BOOTSTRAP}")
        except KafkaError as e:
            logger.error(f"Kafka Producer 初始化失败: {e}")
            self.producer = None
        except Exception as e:
            logger.error(f"Kafka Producer 初始化异常: {e}")
            self.producer = None

    @property
    def available(self) -> bool:
        return self.producer is not None

    def _send(self, topic: str, payload: dict) -> bool:
        if not self.available:
            logger.warning(f"Producer 不可用，消息未发送: {topic}")
            return False
        try:
            payload.setdefault("event_time", datetime.now().isoformat())
            future = self.producer.send(topic, value=payload)
            future.get(timeout=10)
            logger.info(f"消息已发送到 {topic}: {payload.get('ticket_id', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"Kafka 消息发送失败 [{topic}]: {e}")
            return False

    def send_to_department(self, ticket_data: dict, skill_group: str) -> bool:
        """派单后推送到部门后台"""
        from data.ingestion.ticket_service import topic_for_group, STATUS_ASSIGNED

        payload = dict(ticket_data)
        payload["skill_group"] = skill_group
        payload["status"] = STATUS_ASSIGNED
        return self._send(topic_for_group(skill_group), payload)

    def send_resolution(self, ticket_data: dict) -> bool:
        """解决事件，由消费者沉淀向量与知识"""
        return self._send(TOPIC_RESOLVED, dict(ticket_data))

    def close(self):
        if self.producer:
            try:
                self.producer.flush()
                self.producer.close()
            except Exception:
                pass


class TicketConsumer:
    """通用消费者：订阅多个 Topic"""

    def __init__(self, topics: list, group_id: str = WORKER_GROUP):
        self.topics = topics
        self.group_id = group_id
        self.consumer = None
        try:
            self.consumer = KafkaConsumer(
                *topics,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                group_id=group_id,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            )
            logger.info(f"Kafka Consumer 初始化成功，group={group_id}, topics={topics}")
        except Exception as e:
            logger.error(f"Kafka Consumer 初始化失败: {e}")
            self.consumer = None

    @property
    def available(self) -> bool:
        return self.consumer is not None

    def consume(self, handler: Callable[[str, dict], None], max_messages: int = None):
        """持续消费"""
        if not self.available:
            logger.error("Consumer 未初始化，worker 退出")
            return

        count = 0
        try:
            for message in self.consumer:
                try:
                    handler(message.topic, message.value)
                    count += 1
                    if max_messages and count >= max_messages:
                        break
                except Exception as e:
                    logger.error(f"处理 Kafka 消息异常: {e}")
        except KeyboardInterrupt:
            logger.info("收到中断信号，停止消费")
        finally:
            self.close()

    def close(self):
        if self.consumer:
            try:
                self.consumer.close()
            except Exception:
                pass


def _handle_event(topic: str, payload: dict):
    """根据 Topic 分发处理"""
    from data.ingestion.ticket_service import persist_resolution, mark_assigned_from_event

    if topic == TOPIC_RESOLVED:
        ticket_id = payload.get("ticket_id")
        logger.info(f"收到解决事件: {ticket_id}")
        persist_resolution(ticket_id)
    else:
        # 部门 Topic：确认工单进入部门后台（幂等）
        logger.info(f"收到部门工单事件: {payload.get('ticket_id')} [{topic}]")
        mark_assigned_from_event(payload)


def run_worker(group_id: str = WORKER_GROUP):
    """
    启动后台消费者 worker
    订阅：所有部门 Topic + ticket-resolved
    """
    _ensure_topics()
    topics = _department_topics() + [TOPIC_RESOLVED]
    consumer = TicketConsumer(topics, group_id=group_id)
    consumer.consume(_handle_event)


def start_resolution_worker(group_id: str = None) -> threading.Thread:
    """在 Streamlit 进程内启动后台消费者线程，避免必须单独运行 worker"""
    group_id = group_id or os.getenv("KAFKA_UI_WORKER_GROUP", "ticket-resolution-ui")
    thread = threading.Thread(
        target=run_worker,
        kwargs={"group_id": group_id},
        daemon=True,
        name="ticket-kafka-worker",
    )
    thread.start()
    return thread


if __name__ == "__main__":
    import sys
    from pathlib import Path

    ROOT_DIR = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(ROOT_DIR))

    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    run_worker()
