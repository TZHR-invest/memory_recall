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
# 辅助函数
# ============================================================================


def get_entity_extraction_prompt() -> str:
    """获取实体提取 Prompt"""
    return ENTITY_EXTRACTION_PROMPT
