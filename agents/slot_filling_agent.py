"""
槽位填充 Agent
复用 EntityExtractor 完成实体抽取与完整性检查，缺失时自动追问
"""
import logging

from preprocess.entity_extraction.extractor import EntityExtractor

logger = logging.getLogger(__name__)


class SlotFillingAgent:
    """槽位填充 Agent（复用 EntityExtractor 的 extract + check_completeness）"""

    # 必填槽位：问题类型、问题描述、紧急程度
    REQUIRED_SLOTS = ["problem_type", "description", "urgency"]
    CONFIDENCE_THRESHOLD = 0.7

    # 需要从抽取结果中沉淀到槽位的字段
    SLOT_FIELDS = [
        "problem_type",
        "description",
        "urgency",
        "product",
        "device",
        "error_code",
        "user_id",
    ]

    def __init__(self):
        self.extractor = EntityExtractor()
        self.slots = {}  # 已填充的槽位

    def fill(self, user_input: str, context: dict = None) -> dict:
        """
        从用户输入中填充槽位（复用 EntityExtractor）
        返回: {"slots": dict, "complete": bool, "follow_up": str or None,
               "missing_slots": list}
        """
        # 合并上下文（多轮追问补充的信息拼接到本轮输入）
        merged_input = user_input
        if context:
            extra = " ".join(str(v) for v in context.values() if v)
            if extra:
                merged_input = f"{user_input} {extra}"

        try:
            extracted = self.extractor.extract(merged_input)

            # 更新槽位
            for field in self.SLOT_FIELDS:
                value = extracted.get(field)
                if value:
                    self.slots[field] = value

            # 完整性检查（复用 check_completeness，缺失时自动生成追问）
            completeness = self.extractor.check_completeness(extracted)

            return {
                "slots": self.slots.copy(),
                "complete": completeness["complete"],
                "follow_up": completeness["follow_up_question"],
                "missing_slots": completeness["missing_slots"],
            }
        except Exception as e:
            logger.error(f"槽位填充失败: {e}")
            return {
                "slots": self.slots.copy(),
                "complete": False,
                "follow_up": "请描述您遇到的问题，包括问题类型、具体情况和紧急程度。",
                "missing_slots": self.REQUIRED_SLOTS,
            }

    def reset(self):
        """重置槽位"""
        self.slots = {}

    def get_filled_slots(self) -> dict:
        """获取已填充的槽位"""
        return self.slots.copy()
