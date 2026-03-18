"""
Prompt 模板
"""


# ========== 记忆提取相关 ==========

EXTRACT_MEMORY_PROMPT = """你是一个专业的信息提取助手，擅长从用户的记忆文本中提取结构化信息。

请从以下文本中提取记忆信息：

文本：{content}

请提取以下信息（如果存在）：

1. 时间：事件发生的时间
2. 地点：事件发生的地点
3. 人物：相关的人物
4. 情绪：用户的情绪状态
5. 标签：相关的标签（如社交、工作、学习等）
6. 主题：主要内容或话题

请以以下 JSON 格式返回结果：
{{
    "time": {{
        "value": "ISO 8601 格式的时间（如能推断）",
        "source": "extracted/inferred",
        "confidence": 0.0-1.0,
        "original_text": "原文中的时间表述"
    }},
    "location": {{
        "name": "地点名称",
        "address": "详细地址（如有）",
        "need_confirm": true/false,
        "original_text": "原文中的地点表述"
    }},
    "people": [
        {{
            "name": "人物名称或称呼",
            "role": "角色（如朋友、同事等）",
            "need_confirm": true/false,
            "original_text": "原文中的人物表述"
        }}
    ],
    "emotion": {{
        "value": "情绪状态",
        "confidence": 0.0-1.0
    }},
    "tags": ["标签1", "标签2"],
    "topic": {{
        "main": "主要内容",
        "keywords": ["关键词1", "关键词2"]
    }}
}}

注意：
- 如果某项信息不存在，请将对应字段设为 null
- confidence 表示提取信息的置信度（0-1）
- need_confirm 表示该信息是否需要用户确认
- 对于时间信息，尽量推断为具体的日期时间
"""

JUDGE_INQUIRY_PROMPT = """你是一个智能判断助手，负责判断是否需要向用户询问更多信息。

背景：用户输入了一条记忆，系统已经提取了部分信息。

字段：{field_name}
当前值：{field_value}
上下文：{context}

请判断是否需要向用户询问这个字段的更多信息。

判断标准：
1. 信息是否明确？模糊的信息需要确认
2. 信息是否完整？不完整的信息需要补充
3. 信息是否合理？不合理的信息需要澄清

请以以下 JSON 格式返回结果：
{{
    "need_inquiry": true/false,
    "reason": "判断理由",
    "suggested_question": "建议询问的问题（如需要询问）"
}}
"""

# ========== 查询解析相关 ==========

PARSE_QUERY_PROMPT = """你是一个查询解析助手，负责从用户的查询中提取结构化查询条件。

查询：{query}

请提取以下查询条件：

1. 时间范围：查询的时间范围（如"上周"、"最近三天"等）
2. 人物：查询的相关人物
3. 地点：查询的地点
4. 标签：查询的标签
5. 关键词：查询的关键词
6. 意图：用户的查询意图（如查询内容、查询数量、查询时间等）

请以以下 JSON 格式返回结果：
{{
    "time_range": {{
        "start": "ISO 8601 格式的开始时间",
        "end": "ISO 8601 格式的结束时间",
        "original_text": "原文中的时间表述"
    }},
    "people": ["人物1", "人物2"],
    "location": "地点",
    "tags": ["标签1", "标签2"],
    "keywords": ["关键词1", "关键词2"],
    "intent": "query_content/query_count/query_time"
}}

注意：
- 如果某项信息不存在，请将对应字段设为 null
- 时间范围尽量转换为具体的日期时间
- 意图类型包括：query_content（查询内容）、query_count（查询数量）、query_time（查询时间）
"""

# ========== 图片理解相关 ==========

UNDERSTAND_IMAGE_PROMPT = """你是一个图片理解助手，负责从图片描述中提取记忆信息。

图片信息：
- 场景：{scene}
- 时间：{datetime}
- 地点：{location}
- OCR文字：{ocr_text}
- 检测到的人物：{faces}

请理解这张图片并提取记忆信息，包括：
1. 图片的主要内容
2. 发生的时间（如有）
3. 发生的地点（如有）
4. 相关的人物（如有）
5. 相关的标签

请以以下 JSON 格式返回结果：
{{
    "content": "图片的主要内容描述",
    "time": {{
        "value": "ISO 8601 格式的时间",
        "source": "metadata/inferred",
        "confidence": 0.0-1.0
    }},
    "location": {{
        "name": "地点名称",
        "need_confirm": true/false
    }},
    "people": [
        {{
            "name": "人物名称",
            "need_confirm": true/false
        }}
    ],
    "tags": ["标签1", "标签2"]
}}
"""

# ========== 总结相关 ==========

SUMMARIZE_MEMORIES_PROMPT = """你是一个总结助手，负责对多条记忆进行总结。

查询：{query}

记忆列表：
{memories}

请对这些记忆进行总结，包括：
1. 主要内容总结
2. 共同点
3. 时间趋势（如有）
4. 相关建议

请以以下 JSON 格式返回结果：
{{
    "summary": "总结内容",
    "common_themes": ["共同点1", "共同点2"],
    "time_trend": "时间趋势描述",
    "suggestions": ["建议1", "建议2"]
}}
"""
