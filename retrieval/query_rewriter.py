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
            "登录不了": ["登录失败", "无法登录", "认证失败"],
            "登录不上": ["登录失败", "无法登录", "认证失败"],
            "连不上网": ["网络异常", "无法连接", "网络断开"],
            "断网": ["网络断开", "网络中断", "网络异常"],
            "连不上": ["无法连接", "连接失败", "连接超时"],
            "没网": ["网络异常", "无法联网"],
            "死机": ["无响应", "卡死", "冻结"],
            "蓝屏": ["BSOD", "系统崩溃"],
            "黑屏": ["显示异常", "无画面", "屏幕无显示"],
            "花屏": ["显示异常", "画面错乱"],
            "卡顿": ["响应慢", "延迟高", "运行缓慢"],
            "卡": ["卡顿", "响应慢", "延迟"],
            "重启": ["重新启动", "重启设备", "重新开机"],
            "无法开机": ["不能开机", "开机失败", "无法启动"],
            "报错": ["错误提示", "异常报错", "返回错误"],
            "崩溃": ["宕机", "程序异常退出", "系统崩溃"],
            "打不开": ["无法打开", "无法访问", "打开失败"],
            "打不开网页": ["无法访问", "网页加载失败"],
            "超时": ["响应超时", "连接超时", "请求超时"],
            "退款": ["退费", "返还金额", "退回款项"],
            "扣费": ["扣款", "重复收费", "异常扣款"],
            "支付": ["付款", "交易", "下单"],
            "发票": ["报销凭证", "开票"],
            "忘记密码": ["密码找回", "重置密码", "修改密码"],
            "密码": ["口令", "认证凭证"],
            "邮件": ["邮箱", "Email"],
            "网络慢": ["网速慢", "延迟高", "网络延迟"],
            "下载不了": ["无法下载", "下载失败"],
            "上传不了": ["无法上传", "上传失败"],
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
