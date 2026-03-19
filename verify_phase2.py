"""
Phase 2 验证脚本

验证所有功能是否正常工作
"""
import json
from openai import OpenAI


# 配置
VOLC_API_KEY = "7e4a4d80-c618-41da-bdb4-cb43bd07ec68"
VOLC_API_BASE = "https://ark.cn-beijing.volces.com/api/v3"
VOLC_LLM_MODEL = "doubao-seed-2-0-pro-260215"


def verify_function_calling():
    """验证 Function Calling 功能"""
    print("=" * 60)
    print("验证 Function Calling 功能")
    print("=" * 60)
    
    client = OpenAI(
        api_key=VOLC_API_KEY,
        base_url=VOLC_API_BASE
    )
    
    # 工具定义
    tool = {
        "type": "function",
        "function": {
            "name": "test_function",
            "description": "测试功能",
            "parameters": {
                "type": "object",
                "properties": {
                    "result": {"type": "string"}
                },
                "required": ["result"]
            }
        }
    }
    
    try:
        response = client.chat.completions.create(
            model=VOLC_LLM_MODEL,
            messages=[
                {"role": "system", "content": "你是一个测试助手。"},
                {"role": "user", "content": "请调用测试功能返回结果'success'"}
            ],
            tools=[tool],
            tool_choice="auto"
        )
        
        if response.choices[0].message.tool_calls:
            print("✓ Function Calling 功能正常")
            return True
        else:
            print("✗ Function Calling 功能异常")
            return False
    
    except Exception as e:
        print(f"✗ Function Calling 功能异常: {e}")
        return False


def verify_entity_extraction():
    """验证实体提取功能"""
    print("\n" + "=" * 60)
    print("验证实体提取功能")
    print("=" * 60)
    
    client = OpenAI(
        api_key=VOLC_API_KEY,
        base_url=VOLC_API_BASE
    )
    
    tool = {
        "type": "function",
        "function": {
            "name": "extract_entities",
            "description": "提取实体",
            "parameters": {
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity": {"type": "string"},
                                "entity_type": {"type": "string"},
                                "confidence": {"type": "number"}
                            }
                        }
                    }
                }
            }
        }
    }
    
    try:
        response = client.chat.completions.create(
            model=VOLC_LLM_MODEL,
            messages=[
                {"role": "system", "content": "你是一个实体提取专家。"},
                {"role": "user", "content": "请从文本中提取实体：今天和张三在咖啡店聊天"}
            ],
            tools=[tool],
            tool_choice="auto"
        )
        
        if response.choices[0].message.tool_calls:
            arguments = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
            entities = arguments.get("entities", [])
            
            if len(entities) >= 2:
                print(f"✓ 实体提取功能正常（提取了 {len(entities)} 个实体）")
                return True
            else:
                print("✗ 实体提取功能异常（实体数量不足）")
                return False
        else:
            print("✗ 实体提取功能异常（没有工具调用）")
            return False
    
    except Exception as e:
        print(f"✗ 实体提取功能异常: {e}")
        return False


def verify_relation_extraction():
    """验证关系推理功能"""
    print("\n" + "=" * 60)
    print("验证关系推理功能")
    print("=" * 60)
    
    client = OpenAI(
        api_key=VOLC_API_KEY,
        base_url=VOLC_API_BASE
    )
    
    tool = {
        "type": "function",
        "function": {
            "name": "establish_relations",
            "description": "建立关系",
            "parameters": {
                "type": "object",
                "properties": {
                    "relations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "destination": {"type": "string"},
                                "relationship": {"type": "string"},
                                "confidence": {"type": "number"}
                            }
                        }
                    }
                }
            }
        }
    }
    
    try:
        response = client.chat.completions.create(
            model=VOLC_LLM_MODEL,
            messages=[
                {"role": "system", "content": "你是一个关系推理专家。必须使用预定义的英文关系类型如 friend、at、participated 等。"},
                {"role": "user", "content": "实体列表：张三、咖啡店\n\n文本：今天和张三在咖啡店聊天\n\n请推理实体之间的关系，使用英文关系类型。"}
            ],
            tools=[tool],
            tool_choice="auto"
        )
        
        if response.choices[0].message.tool_calls:
            arguments = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
            relations = arguments.get("relations", [])
            
            if len(relations) >= 1:
                rel_types = [r.get("relationship", "") for r in relations]
                print(f"✓ 关系推理功能正常（提取了 {len(relations)} 个关系: {rel_types}）")
                return True
            else:
                print("✗ 关系推理功能异常（关系数量不足）")
                return False
        else:
            print("✗ 关系推理功能异常（没有工具调用）")
            return False
    
    except Exception as e:
        print(f"✗ 关系推理功能异常: {e}")
        return False


def main():
    """主函数"""
    print("\nPhase 2 功能验证\n")
    
    # 验证各项功能
    fc_ok = verify_function_calling()
    entity_ok = verify_entity_extraction()
    relation_ok = verify_relation_extraction()
    
    # 输出总结
    print("\n" + "=" * 60)
    print("验证总结")
    print("=" * 60)
    print(f"Function Calling: {'✓ 正常' if fc_ok else '✗ 异常'}")
    print(f"实体提取功能: {'✓ 正常' if entity_ok else '✗ 异常'}")
    print(f"关系推理功能: {'✓ 正常' if relation_ok else '✗ 异常'}")
    
    if fc_ok and entity_ok and relation_ok:
        print("\n✓ Phase 2 所有功能验证通过")
        return True
    else:
        print("\n✗ Phase 2 部分功能验证失败")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
