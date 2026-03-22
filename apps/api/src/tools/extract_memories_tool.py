"""
记忆提取工具定义

使用 Function Calling 一次性提取：
1. 记忆内容（可多条）
2. 结构化信息（时间、地点、人物）
3. 实体（人物、地点、事件、主题等）
4. 实体关系

设计原则：
- entities 不提取"我"（记忆所有者通过 user_id 标识）
- relations 中可以包含"我"，表示记忆所有者与其他实体的关系
- 时间标准化为 ISO 8601 格式
"""

from typing import Dict, Any

# 提取记忆工具
EXTRACT_MEMORIES_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "extract_memories_with_graph",
        "description": """从文本中提取独立的记忆内容，包括结构化信息、实体和关系。

【记忆分割规则】

规则1 - 时间分割：
- 时间跨度大（上午/下午/晚上）→ 分割成多条记忆
- 同一时间段内的多个事件 → 检查规则2

规则2 - 事件分割：
- 事件有独立的时间 → 分割
- 事件有独立的地点 → 分割
- 事件有独立的人物 → 分割

规则3 - 不分割：
- 连续事件（去A→遇到B→做C）→ 不分割
- 平行事件（做A同时做B）→ 不分割
- 边界情况（同一会议的多个环节、同一时间段内的细节）→ 不分割

【分割示例】

示例1 - 时间分割：
输入："早上在公司开会讨论项目，下午和张三吃饭，晚上看了部电影"
输出：3条记忆
- "早上在公司开会讨论项目"
- "下午和张三吃饭"  
- "晚上看了部电影"

示例2 - 地点分割：
输入："上午在星巴克见了张三，然后去公司开了个会"
输出：2条记忆
- "上午在星巴克见了张三"
- "去公司开了个会"

示例3 - 连续事件不分割：
输入："去市场买菜，遇到张三，聊了很久"
输出：1条记忆
- "去市场买菜，遇到张三，聊了很久"

【核心要求】

1. 按上述规则将长文本分割为独立的记忆点
2. 提取时间信息并标准化为 ISO 8601 格式（基于当前日期推算）
3. 识别实体（人物、地点、事件、主题等）并分类
4. 推理实体之间的关系

【时间标准化规则】
- "今天" → 当前日期
- "昨天" → 当前日期 - 1天
- "上周一" → 上周的周一
- 如果无法确定具体时间，time.value 设为 null，但必须提供 time.original_text

【实体提取规则】
- ❌ 不提取"我"、"自己"等第一人称代词作为实体
- ✅ 提取具体的人名（张三、李四、王总等）
- ✅ 提取地点名称（星巴克、公司会议室等）
- ✅ 提取事件（会议、面试等）
- ✅ 提取主题/项目（新项目、计划等）

【关系提取规则】
- 关系必须连接两个已提取的实体
- ✅ "我"可以出现在关系的 source 中，表示记忆所有者与其他实体的关系
- 使用标准关系类型：at, met, discussed, with, participated
""",
        "parameters": {
            "type": "object",
            "properties": {
                "memories": {
                    "type": "array",
                    "description": "提取的记忆列表（每条记忆独立）",
                    "items": {
                        "type": "object",
                        "properties": {
                            # 记忆内容
                            "content": {
                                "type": "string",
                                "description": "记忆的核心内容（简洁、完整的一句话或一段话）"
                            },
                            
                            # 时间信息
                            "time": {
                                "type": "object",
                                "description": "时间信息",
                                "properties": {
                                    "value": {
                                        "type": "string",
                                        "description": "ISO 8601 格式日期（如 2026-03-22），只精确到日期，不推断具体时间"
                                    },
                                    "original_text": {
                                        "type": "string",
                                        "description": "原文中的时间描述（必须提供）"
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "description": "时间提取的置信度（0-1）",
                                        "minimum": 0,
                                        "maximum": 1
                                    }
                                },
                                "required": ["value", "original_text"]
                            },
                            
                            # 位置信息
                            "location": {
                                "type": "object",
                                "description": "位置信息",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": "地点名称（如'星巴克'、'公司会议室'）"
                                    },
                                    "address": {
                                        "type": "string",
                                        "description": "详细地址（如果有）"
                                    },
                                    "original_text": {
                                        "type": "string",
                                        "description": "原文中的地点描述"
                                    }
                                }
                            },
                            
                            # 人物信息
                            "people": {
                                "type": "array",
                                "description": "涉及的人物列表",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "description": "人物姓名"
                                        },
                                        "role": {
                                            "type": "string",
                                            "description": "人物角色或关系（如'同事'、'朋友'）"
                                        }
                                    },
                                    "required": ["name"]
                                }
                            },
                            
                            # 实体信息
                            "entities": {
                                "type": "array",
                                "description": "提取的实体列表（不包含'我'）",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "description": "实体名称"
                                        },
                                        "type": {
                                            "type": "string",
                                            "description": "实体类型",
                                            "enum": [
                                                "person",       # 人物
                                                "location",     # 地点
                                                "event",        # 事件
                                                "topic",        # 主题/话题
                                                "organization", # 组织/公司
                                                "project",      # 项目
                                                "concept",      # 概念
                                                "object",       # 物品
                                                "time",         # 时间实体
                                                "emotion"       # 情感
                                            ]
                                        },
                                        "confidence": {
                                            "type": "number",
                                            "description": "实体识别置信度（0-1）",
                                            "minimum": 0,
                                            "maximum": 1
                                        }
                                    },
                                    "required": ["name", "type"]
                                }
                            },
                            
                            # 关系信息
                            "relations": {
                                "type": "array",
                                "description": "实体之间的关系列表（'我'可以出现在 source 中）",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "source": {
                                            "type": "string",
                                            "description": "源实体名称（可以是'我'或具体实体）"
                                        },
                                        "target": {
                                            "type": "string",
                                            "description": "目标实体名称（必须是具体实体）"
                                        },
                                        "relation_type": {
                                            "type": "string",
                                            "description": "关系类型",
                                            "enum": [
                                                # 空间关系
                                                "at",           # 在某地
                                                "from",         # 来自某地
                                                "to",           # 去往某地
                                                
                                                # 社交关系
                                                "with",         # 和某人一起
                                                "met",          # 遇见某人
                                                "friend",       # 朋友关系
                                                "colleague",    # 同事关系
                                                
                                                # 事件关系
                                                "participated", # 参与某事
                                                "organized",    # 组织某事
                                                "discussed",    # 讨论某话题
                                                
                                                # 归属关系
                                                "belongs_to",   # 属于
                                                "part_of",      # 是...的一部分
                                                
                                                # 其他
                                                "mentioned",    # 提到
                                                "related_to",   # 相关
                                                "caused"        # 导致
                                            ]
                                        },
                                        "confidence": {
                                            "type": "number",
                                            "description": "关系推理置信度（0-1）",
                                            "minimum": 0,
                                            "maximum": 1
                                        }
                                    },
                                    "required": ["source", "target", "relation_type"]
                                }
                            },
                            
                            # 标签
                            "tags": {
                                "type": "array",
                                "description": "记忆标签（用于分类）",
                                "items": {
                                    "type": "string"
                                }
                            },
                            
                            # 情绪
                            "emotion": {
                                "type": "object",
                                "description": "情绪信息",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "description": "情绪类型（如'开心'、'焦虑'、'平静'）"
                                    },
                                    "intensity": {
                                        "type": "integer",
                                        "description": "情绪强度（1-10）",
                                        "minimum": 1,
                                        "maximum": 10
                                    }
                                }
                            },
                            
                            # 重要性
                            "importance": {
                                "type": "number",
                                "description": "记忆重要性评分（0-1，默认 0.5）",
                                "minimum": 0,
                                "maximum": 1
                            }
                        },
                        "required": ["content", "entities"]
                    }
                }
            },
            "required": ["memories"]
        }
    }
}


# 系统 Prompt
EXTRACT_MEMORIES_SYSTEM_PROMPT = """你是一个专业的记忆提取助手。你的任务是从用户输入的文本中提取结构化的记忆信息。

当前日期：{current_date}（{current_weekday}）

请严格按照 Function Calling 工具的 schema 返回结果。确保：
1. 每条记忆内容独立、完整
2. 时间已标准化为 ISO 8601 格式
3. 实体类型准确（不提取"我"作为实体）
4. 关系类型合理（"我"可以出现在关系中）
"""


def get_extract_memories_system_prompt() -> str:
    """
    获取系统 Prompt
    
    Returns:
        系统 Prompt 字符串
    """
    from datetime import datetime
    
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
    
    return EXTRACT_MEMORIES_SYSTEM_PROMPT.format(
        current_date=current_date,
        current_weekday=current_weekday
    )