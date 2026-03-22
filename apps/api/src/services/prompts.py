"""
Prompt 模板（借鉴 Mem0）

核心设计：
1. 实体提取 Prompt
2. 关系推理 Prompt
"""

from datetime import datetime
from typing import List, Dict, Optional


# ============================================================================
# 实体提取 Prompt
# ============================================================================
ENTITY_EXTRACTION_PROMPT = """你是一个实体识别专家，专门从文本中提取人物、地点、事件、主题和情感等实体。

请从给定的文本中提取以下类型的实体：

1. **person（人物）**：人名、昵称、称呼等
2. **location（地点）**：地点名称、建筑、场所等
3. **event（事件）**：事件名称、活动、会议等
4. **topic（主题）**：话题、主题、关键词等
5. **emotion（情感）**：情绪、感受、态度等

提取规则：
- 只提取明确提及的实体，不要推测
- 每个实体需要一个置信度分数（0-1）
- 使用原始文本中的名称，不要标准化

示例：

文本：今天和张三在咖啡店讨论了机器学习项目
输出：
{{
    "entities": [
        {{"entity": "张三", "entity_type": "person", "confidence": 0.95}},
        {{"entity": "咖啡店", "entity_type": "location", "confidence": 0.9}},
        {{"entity": "讨论", "entity_type": "event", "confidence": 0.85}},
        {{"entity": "机器学习项目", "entity_type": "topic", "confidence": 0.88}}
    ]
}}

文本：周末和老王去爬山，心情很愉快
输出：
{{
    "entities": [
        {{"entity": "周末", "entity_type": "event", "confidence": 0.9}},
        {{"entity": "老王", "entity_type": "person", "confidence": 0.95}},
        {{"entity": "爬山", "entity_type": "event", "confidence": 0.9}},
        {{"entity": "愉快", "entity_type": "emotion", "confidence": 0.92}}
    ]
}}

请严格按照 JSON 格式返回结果。
"""


# ============================================================================
# 关系推理 Prompt
# ============================================================================
RELATION_EXTRACTION_PROMPT = """你是一个关系推理专家，专门分析实体之间的关系。

根据给定的实体列表和文本，推理出实体之间的关系。

# [重要] 必须使用以下预定义的关系类型（英文）：

**人物关系**：
- friend: 朋友关系
- colleague: 同事关系
- family: 家人关系
- met_at: 在...遇到

**地点关系**：
- at: 在...地点
- visited: 访问过
- lives_at: 居住在
- works_at: 工作在

**事件关系**：
- participated: 参与事件
- discussed: 讨论主题
- mentioned: 提及

**主题关系**：
- interested_in: 对...感兴趣
- knows_about: 了解...

**情感关系**：
- likes: 喜欢
- dislikes: 不喜欢
- loves: 爱

推理规则：
- 只推理文本中明确暗示的关系
- 每个关系需要一个置信度分数（0-1）
- 关系方向：从 source 到 destination
- **必须使用上面列出的英文关系类型，不要使用中文描述**

示例：

文本：今天和张三在咖啡店讨论了机器学习项目
实体：["张三", "咖啡店", "讨论", "机器学习项目"]
输出：
{{
    "relations": [
        {{"source": "张三", "destination": "咖啡店", "relationship": "at", "confidence": 0.9}},
        {{"source": "张三", "destination": "讨论", "relationship": "participated", "confidence": 0.88}},
        {{"source": "讨论", "destination": "机器学习项目", "relationship": "discussed", "confidence": 0.92}},
        {{"source": "张三", "destination": "机器学习项目", "relationship": "discussed", "confidence": 0.85}}
    ]
}}

文本：周末和老王去爬山，心情很愉快
实体：["周末", "老王", "爬山", "愉快"]
输出：
{{
    "relations": [
        {{"source": "老王", "destination": "爬山", "relationship": "participated", "confidence": 0.9}}
    ]
}}

文本：我和老王是多年的朋友
实体：["我", "老王"]
输出：
{{
    "relations": [
        {{"source": "我", "destination": "老王", "relationship": "friend", "confidence": 0.95}}
    ]
}}

请严格按照 JSON 格式返回结果，并使用预定义的英文关系类型。
"""


# ============================================================================
# 辅助函数
# ============================================================================

def get_entity_extraction_prompt() -> str:
    """获取实体提取 Prompt"""
    return ENTITY_EXTRACTION_PROMPT


def get_relation_extraction_prompt() -> str:
    """获取关系推理 Prompt"""
    return RELATION_EXTRACTION_PROMPT
