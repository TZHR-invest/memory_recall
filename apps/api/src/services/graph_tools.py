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

RELATION_TYPES = {
    # 人际关系
    "friend": "朋友",
    "colleague": "同事",
    "knows": "认识",
    "family": "家人",
    # 位置关系
    "lives_at": "居住于",
    "works_at": "工作于",
    "studies_at": "就读于",
    # 偏好关系
    "prefers": "偏好/喜欢",
    "uses": "使用",
    # 项目关系
    "works_on": "从事/项目",
    # 所属关系
    "owns": "拥有",
    # 通用关系
    "related_to": "相关",
    "mentioned_in": "提及来源",
}

RELATION_TYPE_LIST = list(RELATION_TYPES.keys())

ENTITY_TYPES = {
    "person": "人物",
    "organization": "组织",
    "location": "地点",
    "event": "事件",
    "preference": "偏好",
    "thing": "物品/概念",
}

ENTITY_TYPE_LIST = list(ENTITY_TYPES.keys())
