"""
工单文本清洗模块
负责：去除特殊字符、表情符号、URL、重复标点等无关信息
"""
import re
import unicodedata


class TicketCleaner:
    """工单文本预清洗器"""

    # 表情符号正则
    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )

    # URL 匹配
    URL_PATTERN = re.compile(
        r'https?://\S+|www\.\S+|\S+\.\S+/\S+'
    )

    # 连续重复字符（如 "！！！！" → "！"）
    REPEAT_PATTERN = re.compile(r'(.)\1{2,}')

    @classmethod
    def clean(cls, text: str) -> str:
        """
        清洗工单文本
        1. 去除表情符号
        2. 去除 URL
        3. 去除特殊控制字符
        4. 合并连续重复标点
        5. 规范化空白字符
        """
        if not text:
            return ""

        # 1. 去除表情
        text = cls.EMOJI_PATTERN.sub("", text)

        # 2. 去除 URL
        text = cls.URL_PATTERN.sub("", text)

        # 3. 去除控制字符（保留中文、英文、数字、常见标点）
        text = "".join(
            ch for ch in text
            if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\t")
        )

        # 4. 合并连续重复标点（保留最多2个）
        text = cls.REPEAT_PATTERN.sub(r"\1\1", text)

        # 5. 规范化空白
        text = re.sub(r"\s+", " ", text).strip()

        return text

    @classmethod
    def extract_error_codes(cls, text: str) -> list:
        """从文本中提取错误码（如 502, 404, ERROR-001 等）"""
        patterns = [
            r'\b\d{3,4}\s*(?:error|错误|报错)\b',           # 502错误
            r'\b(?:error|错误|报错)\s*[:\-]?\s*\d{3,4}\b',  # 错误:502
            r'\b[A-Z]+-\d{2,}\b',                            # ERROR-001
        ]
        codes = []
        for p in patterns:
            codes.extend(re.findall(p, text, re.IGNORECASE))
        return list(set(codes))

    @classmethod
    def extract_product_model(cls, text: str) -> str:
        """提取产品型号（如 手环X1, iPhone15, Server-R740）"""
        pattern = r'[\u4e00-\u9fa5A-Za-z]+[A-Za-z0-9]+[-]?[A-Za-z0-9]+'
        matches = re.findall(pattern, text)
        # 过滤太短的匹配
        return [m for m in matches if len(m) >= 3][0] if matches else ""
