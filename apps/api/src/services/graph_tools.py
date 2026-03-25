"""
图谱工具定义

借鉴 Mem0 的 Function Calling 机制
用于结构化提取实体和关系
"""

# 提取实体工具
EXTRACT_ENTITIES_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_entities",
        "description": "从文本中提取实体及其类型。支持的实体类型：person（人物）、location（地点）、event（事件）、topic（主题）、emotion（情感）、time（时间）、task（任务）、decision（决策）、concept（概念）、solution（解决方案）、problem（问题）。",
        "parameters": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity": {
                                "type": "string",
                                "description": "实体名称（如'张三'、'咖啡店'、'今天下午'）",
                            },
                            "entity_type": {
                                "type": "string",
                                "description": "实体类型（必须从以下类型中选择）",
                                "enum": [
                                    "person",
                                    "location",
                                    "event",
                                    "topic",
                                    "emotion",
                                    "time",
                                    "task",
                                    "decision",
                                    "concept",
                                    "solution",
                                    "problem",
                                ],
                            },
                            "confidence": {
                                "type": "number",
                                "description": "置信度（0-1）",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                        "required": ["entity", "entity_type"],
                    },
                    "description": "实体列表",
                }
            },
            "required": ["entities"],
        },
    },
}

# 添加图谱记忆工具
ADD_GRAPH_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "add_graph_memory",
        "description": "添加新的图谱记忆（实体和关系）。如果实体不存在则自动创建。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源实体名称"},
                "destination": {"type": "string", "description": "目标实体名称"},
                "relationship": {"type": "string", "description": "关系类型"},
                "source_type": {"type": "string", "description": "源实体类型"},
                "destination_type": {"type": "string", "description": "目标实体类型"},
                "confidence": {"type": "number", "description": "置信度"},
            },
            "required": [
                "source",
                "destination",
                "relationship",
                "source_type",
                "destination_type",
            ],
        },
    },
}

# 更新图谱记忆工具
UPDATE_GRAPH_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "update_graph_memory",
        "description": "更新已有图谱记忆的关系。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源实体名称"},
                "destination": {"type": "string", "description": "目标实体名称"},
                "old_relationship": {"type": "string", "description": "旧关系类型"},
                "new_relationship": {"type": "string", "description": "新关系类型"},
            },
            "required": [
                "source",
                "destination",
                "old_relationship",
                "new_relationship",
            ],
        },
    },
}

# 无操作工具
NOOP_TOOL = {
    "type": "function",
    "function": {
        "name": "noop",
        "description": "无操作。不需要对图谱进行任何修改时调用。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

# 所有工具列表
GRAPH_TOOLS = [
    EXTRACT_ENTITIES_TOOL,
    ADD_GRAPH_MEMORY_TOOL,
    UPDATE_GRAPH_MEMORY_TOOL,
    NOOP_TOOL,
]

# 关系类型映射
RELATION_TYPES = {
    # 人物关系
    "friend": "朋友",
    "colleague": "同事",
    "classmate": "同学",
    "family": "家人",
    "acquaintance": "熟人",
    "met_at": "在...遇到",
    # 地点关系
    "at": "在...",
    "visited": "访问过",
    "lives_at": "居住在",
    "works_at": "工作在",
    "studied_at": "学习在",
    # 事件关系
    "participated": "参与",
    "discussed": "讨论",
    "mentioned": "提及",
    "attended": "参加",
    # 主题关系
    "interested_in": "对...感兴趣",
    "knows_about": "了解...",
    "expert_in": "专长于",
    # 情感关系
    "likes": "喜欢",
    "dislikes": "不喜欢",
    "loves": "爱",
    "respects": "尊敬",
    # 通用关系（兜底，不推荐使用）
    "related_to": "相关",
}

# 实体类型
ENTITY_TYPES = {
    "person": "人物",
    "location": "地点",
    "event": "事件",
    "topic": "主题",
    "emotion": "情感",
    "time": "时间",
    "task": "任务",
    "decision": "决策",
    "concept": "概念",
    "solution": "解决方案",
    "problem": "问题",
}
