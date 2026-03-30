"""
Chinese-optimized LLM prompt templates for entity extraction.

Based on LLM-IE best practices and ASMR 6-dimension architecture.
"""

from typing import Optional


CHINESE_ENTITY_EXTRACTION_PROMPT = """从以下中文文本中提取有价值的实体。

文本：{text}
{context_section}

提取规则：
1. 只提取对记忆召回有价值的实体
2. 不要提取：代词（我、你、他）、数量词（一个、几个）、模糊时间（目前、平时、最近）
3. 实体必须是具体的、可识别的

提取类型：
- person: 人名（张三、李明）
- location: 具体地点（北京、上海、望京）
- organization: 组织机构（字节跳动、北京大学）
- contact: 联系方式（手机号、邮箱、微信号）
- skill: 技术技能（Python、TypeScript、React）
- preference: 明确的偏好（喜欢暗黑模式、不吃辣）
- occupation: 职业身份（软件工程师、产品经理）
- education: 学历信息（硕士、博士）

返回JSON格式：
{{
  "entities": {{
    "person": ["张三"],
    "location": ["北京"],
    "organization": ["字节跳动"],
    "contact": ["13812345678"],
    "skill": ["Python", "React"],
    "preference": ["喜欢暗黑模式"],
    "occupation": ["软件工程师"],
    "education": ["硕士"]
  }},
  "is_static": true,
  "confidence": 0.9
}}

注意：
- 空数组不要返回
- 不确定的不提取
- 宁缺毋滥"""


CHINESE_CONTRADICTION_PROMPT = """分析以下两条中文陈述是否存在矛盾。

陈述1（新）：{new_content}
陈述2（旧）：{existing_content}

常见矛盾类型：
- 职业矛盾："在A公司工作" vs "在B公司工作"
- 位置矛盾："住在北京" vs "住在上海"
- 状态矛盾："是单身" vs "结婚了"
- 偏好矛盾："喜欢X" vs "不喜欢X"

更新指示词：现在、改、换成、不再、已经

返回JSON格式：
{{
  "is_contradiction": true,
  "confidence": 0.9,
  "reason": "简要说明矛盾原因"
}}"""


CHINESE_TOPIC_SIMILARITY_PROMPT = """分析以下两条中文陈述是否属于同一主题。

陈述1：{content1}
陈述2：{content2}

主题相似性判断：
- 共享实体（相同的人物、地点、组织）
- 语义关联（同义词、相关概念）
- 上下文关联（同一主题的不同方面）

扩展指示词：而且、另外、还有、同时、具体来说

返回JSON格式：
{{
  "is_same_topic": true,
  "similarity": 0.8,
  "topic": "共同主题描述"
}}"""


CHINESE_RELATION_DETECTION_PROMPT = """分析新记忆与已有记忆之间的关系。

新记忆：{new_content}
已有记忆：{existing_content}

关系类型：
1. updates（更新）：新信息取代旧知识
   - 指示词：现在、改、换成、不再、已经
   - 示例："我现在在字节跳动" vs "我在阿里巴巴"

2. extends（扩展）：补充丰富现有信息
   - 指示词：而且、另外、还有、同时
   - 示例："我喜欢打篮球" vs "我喜欢运动"

3. derives（推断）：从模式推断新知识
   - 指示词：所以、因此、可以推断
   - 示例：从多次提及咖啡推断用户喜欢咖啡

返回JSON格式：
{{
  "relation_type": "updates",
  "confidence": 0.9,
  "reason": "简要说明关系原因"
}}"""


ENTITY_CONTEXT_PROMPT_SECTION = """
实体上下文：{entity_context}

请根据上述上下文调整提取重点。
"""


def get_chinese_extraction_prompt(
    text: str,
    entity_context: Optional[str] = None,
) -> str:
    """Generate Chinese-optimized entity extraction prompt."""
    context_section = ""
    if entity_context:
        context_section = ENTITY_CONTEXT_PROMPT_SECTION.format(
            entity_context=entity_context
        )

    return CHINESE_ENTITY_EXTRACTION_PROMPT.format(
        text=text,
        context_section=context_section,
    )


def get_chinese_contradiction_prompt(
    new_content: str,
    existing_content: str,
) -> str:
    """Generate Chinese contradiction detection prompt."""
    return CHINESE_CONTRADICTION_PROMPT.format(
        new_content=new_content,
        existing_content=existing_content,
    )


def get_chinese_topic_similarity_prompt(
    content1: str,
    content2: str,
) -> str:
    """Generate Chinese topic similarity detection prompt."""
    return CHINESE_TOPIC_SIMILARITY_PROMPT.format(
        content1=content1,
        content2=content2,
    )


def get_chinese_relation_detection_prompt(
    new_content: str,
    existing_content: str,
) -> str:
    """Generate Chinese relation detection prompt."""
    return CHINESE_RELATION_DETECTION_PROMPT.format(
        new_content=new_content,
        existing_content=existing_content,
    )


def detect_language(text: str) -> str:
    """Detect if text is primarily Chinese or English."""
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    total_chars = len([c for c in text if c.isalpha()])

    if total_chars == 0:
        return "unknown"

    chinese_ratio = chinese_chars / total_chars

    if chinese_ratio > 0.3:
        return "chinese"
    return "english"
