"""
实体抽取 Prompt 模板
用于 DeepSeek 大模型结构化抽取工单关键实体
"""

ENTITY_EXTRACTION_PROMPT = """你是一个工单信息抽取专家。请从用户提交的工单文本中提取以下结构化信息。

要求：
1. 严格按照 schema 输出 JSON 格式
2. 如果某字段无法从文本中提取，设为 null
3. 对每个提取的字段给出置信度（0-1）
4. description 字段需要你对原始描述进行规范化改写，去除口语化表达

提取字段说明：
- problem_type: 问题类型，枚举值之一：{problem_types}
- device: 涉及的设备/系统名称
- description: 规范化后的问题描述
- urgency: 紧急程度，枚举值之一：高/中/低
- error_code: 错误码（如有）
- product: 产品名称/型号
- user_id: 用户ID（如有提及）

用户工单原文：
{ticket_text}

请以 JSON 格式输出，格式如下：
{{
    "problem_type": "...",
    "problem_type_confidence": 0.0-1.0,
    "device": "...",
    "description": "...",
    "description_confidence": 0.0-1.0,
    "urgency": "...",
    "urgency_confidence": 0.0-1.0,
    "error_code": "...",
    "product": "...",
    "user_id": "..."
}}
"""

SLOT_SUPPLEMENT_PROMPT = """根据已提取的工单信息，以下关键字段缺失或置信度不足，请向用户提出追问以补充信息。

已提取信息：
{extracted_info}

缺失/低置信度字段：
{missing_slots}

请生成一条友好的追问消息，引导用户补充缺失信息。要求：
1. 语气友好、简洁
2. 明确说明需要补充什么信息
3. 如果可以提供示例帮助用户理解

追问消息：
"""

INTENT_CLASSIFY_PROMPT = """你是一个工单意图分类器。请判断用户输入的意图类别。

意图类别：
- create_ticket: 用户想创建/提交工单
- query_ticket: 用户想查询工单状态/进度
- search_knowledge: 用户想搜索解决方案/知识库
- assign: 用户想转接人工/派单
- chitchat: 闲聊/其他

用户输入：
{user_input}

请输出 JSON：
{{
    "intent": "意图类别",
    "confidence": 0.0-1.0
}}
"""
