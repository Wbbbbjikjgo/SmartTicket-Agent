"""
规则引擎：工单快速分流
通过关键词/正则/条件匹配，快速路由约60%的简单工单，降低 LLM 调用成本
"""
import re
import logging

logger = logging.getLogger(__name__)


class RuleEngine:
    """工单规则过滤引擎"""

    # 规则定义：类别 → (关键词列表, 正则模式列表)
    RULES = {
        "登录问题": {
            "keywords": ["密码", "登录", "登不上", "账户", "认证", "忘记密码", "重置密码"],
            "patterns": [r"密码.{0,5}(错误|忘记|不对)", r"(登录|登陆).{0,5}(失败|不了)"],
            "skill_group": "IT支持组",
            "default_priority": "中",
        },
        "网络问题": {
            "keywords": ["网络", "连不上", "断网", "wifi", "WiFi", "DNS", "IP", "ping不通", "网络异常"],
            "patterns": [r"网络.{0,5}(异常|断开|慢)", r"(连接|访问).{0,5}(失败|超时)"],
            "skill_group": "IT支持组",
            "default_priority": "中",
        },
        "设备故障": {
            "keywords": ["死机", "蓝屏", "重启", "卡顿", "黑屏", "花屏", "无法开机", "硬件"],
            "patterns": [r"(设备|电脑|服务器).{0,5}(死机|蓝屏|重启|卡顿)"],
            "skill_group": "维修工程师",
            "default_priority": "高",
        },
        "系统故障": {
            "keywords": ["报错", "错误", "崩溃", "异常", "500", "502", "503", "404", "超时"],
            "patterns": [r"(服务器|系统|接口).{0,5}(报错|错误|崩溃)", r"\d{3}\s*(error|错误|报错)"],
            "skill_group": "IT支持组",
            "default_priority": "高",
        },
        "财务问题": {
            "keywords": ["退款", "金额", "支付", "账单", "发票", "扣费", "充值"],
            "patterns": [r"(退款|支付|账单).{0,5}(问题|异常|疑问)"],
            "skill_group": "财务组",
            "default_priority": "中",
        },
    }

    # 紧急程度关键词
    URGENCY_KEYWORDS = {
        "高": ["急", "紧急", "立即", "马上", "尽快", "严重", "全部", "所有", "无法工作", "生产环境"],
        "低": ["不急", "有空", "方便时", "建议", "优化"],
    }

    def match(self, text: str) -> dict:
        """
        规则匹配
        返回: {
            "matched": bool,          # 是否命中
            "category": str,          # 问题类别
            "confidence": float,      # 置信度
            "skill_group": str,       # 技能组
            "priority": str,          # 优先级
            "match_details": dict,    # 匹配详情
        }
        """
        if not text:
            return self._no_match()

        best_match = None
        best_score = 0.0

        for category, rule in self.RULES.items():
            score = self._calculate_score(text, rule)
            if score > best_score:
                best_score = score
                best_match = {
                    "matched": score >= 0.6,  # 阈值 0.6
                    "category": category,
                    "confidence": min(score, 1.0),
                    "skill_group": rule["skill_group"],
                    "priority": self._detect_priority(text, rule["default_priority"]),
                    "match_details": {"score": score},
                }

        return best_match if best_match else self._no_match()

    def _calculate_score(self, text: str, rule: dict) -> float:
        """计算文本与规则的匹配分数"""
        score = 0.0

        # 关键词匹配（每个关键词 0.3 分，最多 0.7）
        keyword_hits = sum(1 for kw in rule["keywords"] if kw in text)
        score += min(keyword_hits * 0.3, 0.7)

        # 正则匹配（每个模式 0.4 分，最多 0.5）
        pattern_hits = sum(1 for p in rule["patterns"] if re.search(p, text))
        score += min(pattern_hits * 0.4, 0.5)

        return score

    def _detect_priority(self, text: str, default: str) -> str:
        """检测紧急程度"""
        for urgency, keywords in self.URGENCY_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return urgency
        return default

    def _no_match(self) -> dict:
        """未命中规则"""
        return {
            "matched": False,
            "category": "unknown",
            "confidence": 0.0,
            "skill_group": None,
            "priority": None,
            "match_details": {},
        }
