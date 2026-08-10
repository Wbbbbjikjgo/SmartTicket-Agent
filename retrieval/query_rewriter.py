"""
Query 改写与语义增强模块
通过 LLM 将口语化描述改写为更适合知识库检索的表达
"""
import os
import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

REWRITE_PROMPT = """你是检索查询改写专家。请将下面的工单描述改写为更适合知识库检索的表达。

要求：
1. 去除口语化冗余，保留核心信息
2. 补充领域同义词（如"登不上"→"登录失败"）
3. 保留关键报错码、设备型号等信息
4. 生成 2-3 个检索变体，覆盖不同表述方式

原描述：{query}

请以 JSON 格式输出：
{{
    "rewritten": "改写后的主查询",
    "variants": ["变体1", "变体2"],
    "keywords": ["关键词1", "关键词2"]
}}
"""


class QueryRewriter:
    """Query 改写器"""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.3,
            max_tokens=1024,
        )

        # 领域同义词表（IT运维/客服场景）
        self.synonyms = {
            "登不上": ["登录失败", "无法登录", "认证失败"],
            "连不上网": ["网络异常", "无法连接", "网络断开"],
            "死机": ["无响应", "卡死", "冻结"],
            "蓝屏": ["BSOD", "系统崩溃"],
            "退款": ["退费", "返还金额"],
            "卡顿": ["响应慢", "延迟高", "运行缓慢"],
        }

    def rewrite(self, query: str) -> dict:
        """
        改写查询
        返回: {"rewritten": str, "variants": list, "keywords": list, "original": str}
        """
        # Step 1: 同义词扩展
        expanded = self._expand_synonyms(query)

        # Step 2: LLM 改写
        try:
            prompt = REWRITE_PROMPT.format(query=query)
            response = self.llm.invoke([HumanMessage(content=prompt)])
            result = self._parse_json(response.content)
            result["original"] = query
            result["expanded"] = expanded
            return result
        except Exception as e:
            logger.error(f"Query 改写失败: {e}")
            return {
                "original": query,
                "rewritten": query,
                "variants": [expanded],
                "keywords": self._extract_keywords(query),
                "expanded": expanded,
            }

    def _expand_synonyms(self, text: str) -> str:
        """基于同义词表扩展"""
        result = text
        for original, synonyms in self.synonyms.items():
            if original in text:
                # 将同义词追加到文本末尾
                result += " " + " ".join(synonyms[:2])
                break
        return result

    def _extract_keywords(self, text: str) -> list:
        """简单关键词提取（基于分词）"""
        import re
        # 提取中文词组（2-6字）和英文单词
        cn_words = re.findall(r'[\u4e00-\u9fa5]{2,6}', text)
        en_words = re.findall(r'[A-Za-z]+[-]?[A-Za-z0-9]*', text)
        # 去重
        keywords = list(set(cn_words + en_words))
        return keywords[:10]

    def _parse_json(self, text: str) -> dict:
        """从 LLM 输出中解析 JSON"""
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"rewritten": text, "variants": [], "keywords": []}
