"""
Chinese-optimized LLM prompt templates for entity extraction.

Based on LLM-IE best practices and ASMR 6-dimension architecture.
"""

from typing import Optional


CHINESE_ENTITY_EXTRACTION_PROMPT = """你是实体提取专家。从文本中提取实体，返回 JSON。

文本: {text}
{context_section}

【提取示例】

"我在谷歌工作" → {{"organization": ["谷歌"]}}
"我入职了字节跳动" → {{"organization": ["字节跳动"]}}
"我就职于阿里巴巴" → {{"organization": ["阿里巴巴"]}}
"我是腾讯员工" → {{"organization": ["腾讯"]}}
"我住在北京" → {{"location": ["北京"]}}
"我住在望京" → {{"location": ["望京"]}}
"和张三见面" → {{"person": ["张三"]}}
"我喜欢吃火锅" → {{"preference": ["喜欢吃火锅"]}}
"我不爱吃辣的食物" → {{"preference": ["不爱吃辣的食物"]}}
"我是素食主义者" → {{"preference": ["素食主义者"]}}
"我喜欢吃火锅，不喜欢吃辣" → {{"preference": ["喜欢吃火锅", "不喜欢吃辣"]}}
"偏好暗黑模式，不喜欢亮色" → {{"preference": ["偏好暗黑模式", "不喜欢亮色"]}}

【边界规则】

1. organization (公司/学校):
   - 只提取名称: "谷歌" 不是 "入职谷歌"
   - 判断: X工作/入职X/就职于X/是X员工 → X是公司名

2. location (地名):
   - 判断: 住在X/来自X → X是地名

3. preference (偏好) - 重要:
   - 完整提取动宾结构: "喜欢吃火锅" 不是 "喜欢"
   - 多个偏好分别提取: "喜欢吃火锅，不喜欢吃辣" → ["喜欢吃火锅", "不喜欢吃辣"]
   - 不是单独动词: 不是 "喜欢" 或 "不喜欢"

【实体类型】
- organization: 公司、学校 (谷歌、字节跳动、北大)
- location: 城市、区域 (北京、上海、望京)
- person: 人名 (张三、李四、老王)
- preference: 偏好 (喜欢吃火锅、素食主义者、不喜欢吃辣)
- skill: 技能 (Python、React)
- contact: 联系方式 (手机号、邮箱)
- occupation: 职业 (工程师、产品经理)

【不提取】
代词(我你他)、模糊时间(最近目前)

【返回格式】
{{
  "entities": {{"organization": ["谷歌"], "person": ["张三"]}},
  "is_static": true,
  "confidence": 0.9
}}"""


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


CHINESE_BATCH_RELATION_PROMPT = """分析新记忆与以下候选记忆的关系。

新记忆：{new_content}

候选记忆：
{candidates_section}

关系类型：
1. updates（更新）：新信息取代旧知识，存在矛盾
   - 指示词：现在、改、换成、不再、已经
   - 例："我现在在字节跳动" 更新 "我在阿里巴巴"

2. extends（扩展）：补充丰富现有信息，同一主题
   - 指示词：而且、另外、还有、同时
   - 例："我喜欢打篮球" 扩展 "我喜欢运动"

3. derives（推断）：从现有记忆推断出新知识
   - 指示词：所以、因此、可以推断、由此可见
   - 例："所以我经常喝咖啡" 推断自 "我工作很忙，经常加班"

4. null：无明显关系，跳过

返回JSON格式：
{{
  "relations": [
    {{"id": "记忆ID1", "type": "updates", "confidence": 0.9}},
    {{"id": "记忆ID2", "type": "extends", "confidence": 0.8}},
    {{"id": "记忆ID3", "type": "derives", "confidence": 0.7}},
    {{"id": "记忆ID4", "type": null}}
  ]
}}

注意：
- 只返回有明显关系的记忆
- 无关系的记忆返回 type: null
- confidence 范围 0.0-1.0
- derives 用于因果关系或推断，不是补充信息"""


def get_chinese_batch_relation_prompt(
    new_content: str,
    candidates: list,
) -> str:
    candidates_section = "\n".join(
        f"{i + 1}. [ID: {c['id']}] {c['content']}" for i, c in enumerate(candidates)
    )
    return CHINESE_BATCH_RELATION_PROMPT.format(
        new_content=new_content,
        candidates_section=candidates_section,
    )


ENTITY_CONTEXT_PROMPT_SECTION = """
<extraction_guidance>
{entity_context}
</extraction_guidance>
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
