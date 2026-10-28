"""
基于 DeepSeek 大模型的工单实体抽取模块
通过 LangChain 结构化输出提取关键实体
"""
import json
import os
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from preprocess.cleaner import TicketCleaner
from preprocess.entity_extraction.prompt_templates import (
    ENTITY_EXTRACTION_PROMPT,
    SLOT_SUPPLEMENT_PROMPT,
)

logger = logging.getLogger(__name__)

# 问题类型枚举
PROBLEM_TYPES = ["登录问题", "系统故障", "网络异常", "设备故障", "财务问题", "其他"]


class EntityExtractor:
    """基于 DeepSeek 的工单实体抽取器"""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.1,
            max_tokens=2048,
        )
        self.confidence_threshold = 0.7

    def extract(self, raw_text: str) -> dict:
        """
        从原始工单文本中提取结构化实体
        流程：清洗 → LLM抽取 → 置信度判断
        """
        # Step 1: 文本清洗
        cleaned_text = TicketCleaner.clean(raw_text)
        error_codes = TicketCleaner.extract_error_codes(raw_text)

        # Step 2: LLM 结构化抽取
        prompt = ENTITY_EXTRACTION_PROMPT.format(
            problem_types="、".join(PROBLEM_TYPES),
            ticket_text=cleaned_text,
        )

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            result = self._parse_json(response.content)
        except Exception as e:
            logger.error(f"LLM 实体抽取失败: {e}")
            result = self._fallback_extract(cleaned_text)

        # Step 3: 补充错误码
        if error_codes and not result.get("error_code"):
            result["error_code"] = error_codes[0]

        result["raw_text"] = raw_text
        result["cleaned_text"] = cleaned_text

        return result

    def check_completeness(self, extracted: dict) -> dict:
        """
        检查抽取结果的完整性
        返回：{"complete": bool, "missing_slots": [...], "follow_up_question": str or None}
        """
        missing = []

        # 检查必填字段
        if not extracted.get("problem_type"):
            missing.append("problem_type（问题类型）")
        elif extracted.get("problem_type_confidence", 1.0) < self.confidence_threshold:
            missing.append(f"problem_type（问题类型，当前置信度{extracted['problem_type_confidence']}）")

        if not extracted.get("description"):
            missing.append("description（问题描述）")
        elif extracted.get("description_confidence", 1.0) < self.confidence_threshold:
            missing.append(f"description（问题描述，当前置信度{extracted['description_confidence']}）")

        if not extracted.get("urgency"):
            missing.append("urgency（紧急程度）")

        if not missing:
            return {"complete": True, "missing_slots": [], "follow_up_question": None}

        # 生成追问
        follow_up = self._generate_follow_up(extracted, missing)

        return {
            "complete": False,
            "missing_slots": missing,
            "follow_up_question": follow_up,
        }

    def _generate_follow_up(self, extracted: dict, missing: list) -> str:
        """生成追问消息"""
        prompt = SLOT_SUPPLEMENT_PROMPT.format(
            extracted_info=json.dumps(extracted, ensure_ascii=False, indent=2),
            missing_slots="\n".join(f"- {s}" for s in missing),
        )
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            logger.error(f"生成追问失败: {e}")
            return f"请补充以下信息：{', '.join(missing)}"

    def _parse_json(self, text: str) -> dict:
        """从 LLM 输出中解析 JSON"""
        # 尝试提取 ```json ... ``` 代码块
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        else:
            # 尝试直接找 JSON 对象
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"JSON 解析失败，原文: {text[:200]}")
            return {}

    def _fallback_extract(self, text: str) -> dict:
        """当 LLM 调用失败时的简单规则抽取"""
        result = {
            "problem_type": None,
            "description": text[:200],
            "urgency": None,
        }

        # 简单关键词匹配
        keyword_map = {
            "登录问题": ["密码", "登录", "登不上", "账户"],
            "网络异常": ["网络", "断网", "连不上", "wifi"],
            "设备故障": ["死机", "蓝屏", "重启", "卡顿"],
            "系统故障": ["报错", "错误", "崩溃", "异常"],
            "财务问题": ["退款", "金额", "支付", "账单"],
        }
        for ptype, keywords in keyword_map.items():
            if any(kw in text for kw in keywords):
                result["problem_type"] = ptype
                result["problem_type_confidence"] = 0.6
                break

        # 紧急程度判断
        if any(w in text for w in ["急", "紧急", "立即", "马上", "马上"]):
            result["urgency"] = "高"
            result["urgency_confidence"] = 0.7
        else:
            result["urgency"] = "中"
            result["urgency_confidence"] = 0.5

        return result
