"""
Kafka 工单消息队列
负责：工单缓冲削峰、异步处理、规则路由分发
"""
import os
import json
import logging
import uuid
from datetime import datetime
from typing import Optional, Callable

from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC_RAW = os.getenv("KAFKA_TOPIC_RAW", "ticket-raw")
TOPIC_ROUTED = os.getenv("KAFKA_TOPIC_ROUTED", "ticket-routed")


class TicketProducer:
    """工单生产者：将工单发送到 Kafka"""

    def __init__(self):
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                acks="all",
                retries=3,
            )
            logger.info(f"Kafka Producer 初始化成功，连接: {KAFKA_BOOTSTRAP}")
        except KafkaError as e:
            logger.error(f"Kafka Producer 初始化失败: {e}")
            self.producer = None

    def send_ticket(self, ticket_data: dict) -> bool:
        """发送工单到 ticket-raw topic"""
        if not self.producer:
            logger.error("Producer 未初始化，无法发送")
            return False

        # 添加工单元信息
        ticket_data.setdefault("ticket_id", f"GD{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}")
        ticket_data.setdefault("submit_time", datetime.now().isoformat())

        try:
            future = self.producer.send(TOPIC_RAW, value=ticket_data)
            future.get(timeout=10)  # 等待发送确认
            logger.info(f"工单 {ticket_data['ticket_id']} 已发送到 {TOPIC_RAW}")
            return True
        except KafkaError as e:
            logger.error(f"工单发送失败: {e}")
            return False

    def close(self):
        if self.producer:
            self.producer.flush()
            self.producer.close()


class TicketConsumer:
    """工单消费者：从 Kafka 拉取工单并处理"""

    def __init__(self, group_id: str = "ticket-agent"):
        self.group_id = group_id
        self.consumer = None
        self._init_consumer()

    def _init_consumer(self):
        """初始化消费者"""
        try:
            self.consumer = KafkaConsumer(
                TOPIC_RAW,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                group_id=self.group_id,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                consumer_timeout_ms=1000,  # 无消息时 1s 超时退出
            )
            logger.info(f"Kafka Consumer 初始化成功，group: {self.group_id}")
        except KafkaError as e:
            logger.error(f"Kafka Consumer 初始化失败: {e}")

    def consume(self, handler: Callable[[dict], None], max_messages: int = None):
        """
        消费工单消息
        handler: 处理函数，接收工单 dict
        max_messages: 最大消费数量（None 表示持续消费）
        """
        if not self.consumer:
            logger.error("Consumer 未初始化")
            return

        count = 0
        for message in self.consumer:
            try:
                ticket = message.value
                logger.info(f"消费工单: {ticket.get('ticket_id', 'unknown')}")
                handler(ticket)
                count += 1
                if max_messages and count >= max_messages:
                    break
            except Exception as e:
                logger.error(f"处理工单异常: {e}")
                continue

    def close(self):
        if self.consumer:
            self.consumer.close()


class TicketRouter:
    """
    工单路由器：结合规则引擎和 LLM 进行工单分流
    流程：Kafka消费 → 规则匹配 → 命中则直连路由 → 未命中走 LLM 清洗
    """

    def __init__(self, rule_engine, llm_processor=None):
        """
        rule_engine: RuleEngine 实例
        llm_processor: LLM 处理函数（规则未命中时调用）
        """
        self.rule_engine = rule_engine
        self.llm_processor = llm_processor

    def route(self, ticket: dict) -> dict:
        """
        路由工单
        返回: {**ticket, "route_result": {...}}
        """
        raw_text = ticket.get("raw_text", "") or ticket.get("description", "")

        # Step 1: 规则匹配
        rule_result = self.rule_engine.match(raw_text)

        if rule_result["matched"] and rule_result["confidence"] >= 0.8:
            # 规则高置信度命中，直接路由
            ticket["route_source"] = "rule"
            ticket["route_result"] = rule_result
            logger.info(f"工单规则直连路由: {rule_result['category']} (置信度: {rule_result['confidence']:.2f})")
            return ticket

        # Step 2: 规则未命中或低置信度，走 LLM
        if self.llm_processor:
            ticket["route_source"] = "llm"
            ticket["rule_hint"] = rule_result  # 给 LLM 提供参考
            ticket = self.llm_processor(ticket)
            logger.info(f"工单 LLM 路由: {ticket.get('category', 'unknown')}")
        else:
            ticket["route_source"] = "rule_low"
            ticket["route_result"] = rule_result

        return ticket

    def handle_ticket(self, ticket: dict):
        """Kafka 消费者回调：路由工单"""
        routed = self.route(ticket)
        # 这里可以将路由结果写回 ES 或发送到下一个 topic
        logger.info(f"工单路由完成: {routed.get('ticket_id')} → {routed.get('category', 'unknown')}")
        return routed
