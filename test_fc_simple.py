"""
简单的 Function Calling 测试

直接测试火山引擎 API
"""
import json
from openai import OpenAI


# 配置
VOLC_API_KEY = "7e4a4d80-c618-41da-bdb4-cb43bd07ec68"
VOLC_API_BASE = "https://ark.cn-beijing.volces.com/api/v3"
VOLC_LLM_MODEL = "doubao-seed-2-0-pro-260215"

# 工具定义
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


def test_function_calling():
    """测试 Function Calling"""
    print("=" * 60)
    print("测试 Function Calling 功能")
    print("=" * 60)
    
    # 初始化客户端
    client = OpenAI(
        api_key=VOLC_API_KEY,
        base_url=VOLC_API_BASE
    )
    
    # 测试 1：实体提取
    print("\n### 测试 1：实体提取")
    print("-" * 60)
    
    test_cases = [
        "今天和张三在咖啡店聊天",
        "明天要和李四去北京出差",
        "周末和老王爬山，心情很愉快"
    ]
    
    for i, test_text in enumerate(test_cases, 1):
        print(f"\n测试用例 {i}: {test_text}")
        
        try:
            response = client.chat.completions.create(
                model=VOLC_LLM_MODEL,
                messages=[
                    {"role": "system", "content": "你是一个实体提取专家。"},
                    {"role": "user", "content": f"请从以下文本中提取实体：\n\n{test_text}"}
                ],
                tools=[EXTRACT_ENTITIES_TOOL],
                tool_choice="auto",
                temperature=0.3
            )
            
            message = response.choices[0].message
            
            if message.tool_calls:
                print("✓ 成功获取工具调用")
                for tool_call in message.tool_calls:
                    print(f"  工具名称: {tool_call.function.name}")
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                        print(f"  参数: {json.dumps(arguments, ensure_ascii=False, indent=4)}")
                    except json.JSONDecodeError as e:
                        print(f"  解析参数失败: {e}")
            else:
                print("✗ 没有工具调用")
                if message.content:
                    print(f"  文本响应: {message.content[:100]}...")
        
        except Exception as e:
            print(f"✗ 测试失败: {e}")
    
    # 测试 2：关系推理
    print("\n### 测试 2：关系推理")
    print("-" * 60)
    
    relation_test_cases = [
        {
            "text": "今天和张三在咖啡店聊天",
            "entities": ["张三", "咖啡店", "聊天"]
        },
        {
            "text": "我和老王是多年的朋友",
            "entities": ["我", "老王"]
        }
    ]
    
    for i, test_case in enumerate(relation_test_cases, 1):
        print(f"\n测试用例 {i}: {test_case['text']}")
        print(f"实体列表: {test_case['entities']}")
        
        try:
            response = client.chat.completions.create(
                model=VOLC_LLM_MODEL,
                messages=[
                    {"role": "system", "content": "你是一个关系推理专家。"},
                    {"role": "user", "content": f"实体列表：{', '.join(test_case['entities'])}\n\n文本：{test_case['text']}"}
                ],
                tools=[ESTABLISH_RELATIONS_TOOL],
                tool_choice="auto",
                temperature=0.3
            )
            
            message = response.choices[0].message
            
            if message.tool_calls:
                print("✓ 成功获取工具调用")
                for tool_call in message.tool_calls:
                    print(f"  工具名称: {tool_call.function.name}")
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                        print(f"  参数: {json.dumps(arguments, ensure_ascii=False, indent=4)}")
                    except json.JSONDecodeError as e:
                        print(f"  解析参数失败: {e}")
            else:
                print("✗ 没有工具调用")
                if message.content:
                    print(f"  文本响应: {message.content[:100]}...")
        
        except Exception as e:
            print(f"✗ 测试失败: {e}")
    
    # 测试 3：验证实体提取准确率
    print("\n### 测试 3：验证实体提取准确率")
    print("-" * 60)
    
    accuracy_test_cases = [
        {
            "text": "今天和张三在咖啡店聊天",
            "expected_entities": ["张三", "咖啡店", "聊天"],
            "expected_types": ["person", "location", "event"]
        },
        {
            "text": "明天要和李四去北京出差",
            "expected_entities": ["李四", "北京", "出差"],
            "expected_types": ["person", "location", "event"]
        }
    ]
    
    correct_count = 0
    total_count = len(accuracy_test_cases)
    
    for i, test_case in enumerate(accuracy_test_cases, 1):
        print(f"\n准确率测试 {i}: {test_case['text']}")
        
        try:
            response = client.chat.completions.create(
                model=VOLC_LLM_MODEL,
                messages=[
                    {"role": "system", "content": "你是一个实体提取专家。"},
                    {"role": "user", "content": f"请从以下文本中提取实体：\n\n{test_case['text']}"}
                ],
                tools=[EXTRACT_ENTITIES_TOOL],
                tool_choice="auto",
                temperature=0.3
            )
            
            message = response.choices[0].message
            
            if message.tool_calls:
                tool_call = message.tool_calls[0]
                if tool_call.function.name == "extract_entities":
                    arguments = json.loads(tool_call.function.arguments)
                    entities = arguments.get("entities", [])
                    
                    # 检查实体
                    entity_names = [e.get("entity", "") for e in entities]
                    print(f"  提取的实体: {entity_names}")
                    
                    # 检查期望的实体
                    matched = 0
                    for expected in test_case["expected_entities"]:
                        if any(expected in name for name in entity_names):
                            matched += 1
                    
                    if matched >= len(test_case["expected_entities"]) - 1:  # 允许 1 个遗漏
                        correct_count += 1
                        print(f"  ✓ 准确率测试通过")
                    else:
                        print(f"  ✗ 准确率测试失败: 匹配 {matched}/{len(test_case['expected_entities'])}")
            else:
                print("  ✗ 没有工具调用")
        
        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
    
    accuracy = correct_count / total_count if total_count > 0 else 0
    print(f"\n准确率: {accuracy * 100:.1f}% ({correct_count}/{total_count})")
    
    if accuracy >= 0.9:
        print("✓ 准确率达标 (>90%)")
    else:
        print("✗ 准确率未达标 (<90%)")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_function_calling()
