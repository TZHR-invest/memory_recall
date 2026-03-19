"""
图谱工具定义（借鉴 Mem0）

使用 OpenAI Function Calling 机制，实现结构化输出
"""

# 提取实体工具
EXTRACT_ENTITIES_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_entities",
        "description": "从文本中提取实体（人物、地点、事件等）及其类型。",
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
                                "description": "实体名称（如'张三'、'咖啡店'）"
                            },
                            "entity_type": {
                                "type": "string",
                                "description": "实体类型",
                                "enum": ["person", "location", "event", "topic", "emotion"]
                            },
                            "confidence": {
                                "type": "number",
                                "description": "置信度（0-1）",
                                "minimum": 0,
                                "maximum": 1
                            }
                        },
                        "required": ["entity", "entity_type"]
                    },
                    "description": "实体列表"
                }
            },
            "required": ["entities"]
        }
    }
}

# 建立关系工具
ESTABLISH_RELATIONS_TOOL = {
    "type": "function",
    "function": {
        "name": "establish_relations",
        "description": "建立实体之间的关系。",
        "parameters": {
            "type": "object",
            "properties": {
                "relations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {
                                "type": "string",
                                "description": "源实体名称"
                            },
                            "destination": {
                                "type": "string",
                                "description": "目标实体名称"
                            },
                            "relationship": {
                                "type": "string",
                                "description": "关系类型（如'met_at', 'friend', 'at'）"
                            },
                            "confidence": {
                                "type": "number",
                                "description": "置信度（0-1）"
                            }
                        },
                        "required": ["source", "destination", "relationship"]
                    },
                    "description": "关系列表"
                }
            },
            "required": ["relations"]
        }
    }
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
                "confidence": {"type": "number", "description": "置信度"}
            },
            "required": ["source", "destination", "relationship", "source_type", "destination_type"]
        }
    }
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
                "new_relationship": {"type": "string", "description": "新关系类型"}
            },
            "required": ["source", "destination", "old_relationship", "new_relationship"]
        }
    }
}

# 删除图谱记忆工具
DELETE_GRAPH_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "delete_graph_memory",
        "description": "删除图谱记忆中的实体或关系。",
        "parameters": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "要删除的实体名称"},
                "source": {"type": "string", "description": "关系源实体"},
                "destination": {"type": "string", "description": "关系目标实体"},
                "relationship": {"type": "string", "description": "关系类型"}
            }
        }
    }
}

# 无操作工具
NOOP_TOOL = {
    "type": "function",
    "function": {
        "name": "noop",
        "description": "无操作。不需要对图谱进行任何修改时调用。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

# 所有工具列表
GRAPH_TOOLS = [
    EXTRACT_ENTITIES_TOOL,
    ESTABLISH_RELATIONS_TOOL,
    ADD_GRAPH_MEMORY_TOOL,
    UPDATE_GRAPH_MEMORY_TOOL,
    DELETE_GRAPH_MEMORY_TOOL,
    NOOP_TOOL
]

# 常用的关系类型
RELATION_TYPES = {
    # 人物关系
    "friend": "朋友",
    "colleague": "同事",
    "family": "家人",
    "met_at": "在...遇到",
    
    # 地点关系
    "at": "在...",
    "visited": "访问过",
    "lives_at": "居住在",
    "works_at": "工作在",
    
    # 事件关系
    "participated": "参与",
    "discussed": "讨论",
    "mentioned": "提及",
    
    # 主题关系
    "interested_in": "对...感兴趣",
    "knows_about": "了解...",
    
    # 情感关系
    "likes": "喜欢",
    "dislikes": "不喜欢",
    "loves": "爱",
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
    "problem": "问题"
}


def validate_tool_definition(tool: dict) -> bool:
    """验证工具定义是否符合 OpenAI Function Calling 格式"""
    try:
        assert tool["type"] == "function"
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]
        # 修复：parameters 在 function 内部
        params = tool["function"]["parameters"]
        assert "type" in params
        assert "properties" in params
        return True
    except (KeyError, AssertionError) as e:
        print(f"  验证错误: {e}")
        return False


def validate_all_tools():
    """验证所有工具定义"""
    results = []
    for tool in GRAPH_TOOLS:
        tool_name = tool["function"]["name"]
        is_valid = validate_tool_definition(tool)
        results.append({
            "name": tool_name,
            "valid": is_valid
        })
        print(f"{'✓' if is_valid else '✗'} {tool_name}: {'有效' if is_valid else '无效'}")
    
    return all(r["valid"] for r in results)


if __name__ == "__main__":
    # 测试工具定义
    print("验证工具定义...")
    print()
    all_valid = validate_all_tools()
    print()
    print(f"结果: {'所有工具定义有效 ✓' if all_valid else '部分工具定义无效 ✗'}")
