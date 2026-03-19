"""
实体提取准确率测试脚本

测试目标：
- 实体提取准确率 > 90%
- 支持中文实体识别
- 返回置信度
"""
import asyncio
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


# 测试用例
TEST_CASES = [
    # 基础测试
    {
        "text": "今天和张三在咖啡店聊天",
        "expected_entities": ["张三", "咖啡店", "聊天"],
        "expected_types": ["person", "location", "event"],
        "category": "基础"
    },
    {
        "text": "明天要和李四去北京出差",
        "expected_entities": ["李四", "北京", "出差"],
        "expected_types": ["person", "location", "event"],
        "category": "基础"
    },
    
    # 人物关系
    {
        "text": "我和老王是多年的朋友",
        "expected_entities": ["老王", "朋友"],
        "expected_types": ["person", "topic"],
        "category": "人物关系"
    },
    {
        "text": "小明的哥哥是工程师",
        "expected_entities": ["小明", "哥哥", "工程师"],
        "expected_types": ["person", "person", "topic"],
        "category": "人物关系"
    },
    
    # 地点场景
    {
        "text": "周末去电影院看电影",
        "expected_entities": ["周末", "电影院", "看电影"],
        "expected_types": ["event", "location", "event"],
        "category": "地点场景"
    },
    {
        "text": "在公司开会讨论新项目",
        "expected_entities": ["公司", "开会", "新项目"],
        "expected_types": ["location", "event", "topic"],
        "category": "地点场景"
    },
    
    # 情感表达
    {
        "text": "爬山很累但是很开心",
        "expected_entities": ["爬山", "累", "开心"],
        "expected_types": ["event", "emotion", "emotion"],
        "category": "情感表达"
    },
    {
        "text": "对这部电影很失望",
        "expected_entities": ["电影", "失望"],
        "expected_types": ["topic", "emotion"],
        "category": "情感表达"
    },
    
    # 主题话题
    {
        "text": "最近在学习机器学习",
        "expected_entities": ["学习", "机器学习"],
        "expected_types": ["event", "topic"],
        "category": "主题话题"
    },
    {
        "text": "喜欢听周杰伦的歌",
        "expected_entities": ["周杰伦", "歌", "喜欢"],
        "expected_types": ["person", "topic", "emotion"],
        "category": "主题话题"
    },
    
    # 复杂场景
    {
        "text": "上周六和小红、小李在餐厅吃饭，聊了很多有趣的话题",
        "expected_entities": ["上周六", "小红", "小李", "餐厅", "吃饭", "话题"],
        "expected_types": ["event", "person", "person", "location", "event", "topic"],
        "category": "复杂场景"
    },
    {
        "text": "昨天在公园遇到老同学，我们一起散步聊天",
        "expected_entities": ["昨天", "公园", "老同学", "散步", "聊天"],
        "expected_types": ["event", "location", "person", "event", "event"],
        "category": "复杂场景"
    }
]


async def test_entity_extraction():
    """测试实体提取准确率"""
    print("=" * 80)
    print("实体提取准确率测试")
    print("=" * 80)
    
    # 初始化客户端
    client = OpenAI(
        api_key=VOLC_API_KEY,
        base_url=VOLC_API_BASE
    )
    
    # 统计结果
    total_cases = len(TEST_CASES)
    correct_cases = 0
    total_entities = 0
    correct_entities = 0
    category_stats = {}
    
    print(f"\n总测试用例: {total_cases}")
    print("-" * 80)
    
    for i, test_case in enumerate(TEST_CASES, 1):
        category = test_case["category"]
        if category not in category_stats:
            category_stats[category] = {
                "total": 0,
                "correct": 0,
                "entities_total": 0,
                "entities_correct": 0
            }
        
        category_stats[category]["total"] += 1
        
        print(f"\n[{i}/{total_cases}] {category}: {test_case['text']}")
        
        try:
            # 调用 API
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
                    
                    # 提取的实体名称
                    entity_names = [e.get("entity", "") for e in entities]
                    entity_types = {e.get("entity", ""): e.get("entity_type", "") for e in entities}
                    
                    print(f"  期望实体: {test_case['expected_entities']}")
                    print(f"  提取实体: {entity_names}")
                    
                    # 计算匹配度
                    matched = 0
                    for expected in test_case["expected_entities"]:
                        total_entities += 1
                        category_stats[category]["entities_total"] += 1
                        
                        # 检查实体名称
                        if any(expected in name or name in expected for name in entity_names):
                            matched += 1
                            correct_entities += 1
                            category_stats[category]["entities_correct"] += 1
                    
                    # 检查是否通过（允许 1 个遗漏）
                    expected_count = len(test_case["expected_entities"])
                    if matched >= expected_count - 1:
                        correct_cases += 1
                        category_stats[category]["correct"] += 1
                        print(f"  ✓ 测试通过 ({matched}/{expected_count})")
                    else:
                        print(f"  ✗ 测试失败 ({matched}/{expected_count})")
                    
                    # 检查置信度
                    has_confidence = all("confidence" in e for e in entities)
                    if has_confidence:
                        print(f"  ✓ 所有实体都有置信度")
                    else:
                        print(f"  ⚠ 部分实体缺少置信度")
            
            else:
                print("  ✗ 没有工具调用")
        
        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
    
    # 输出统计结果
    print("\n" + "=" * 80)
    print("测试结果统计")
    print("=" * 80)
    
    case_accuracy = correct_cases / total_cases if total_cases > 0 else 0
    entity_accuracy = correct_entities / total_entities if total_entities > 0 else 0
    
    print(f"\n整体准确率:")
    print(f"  用例准确率: {case_accuracy * 100:.1f}% ({correct_cases}/{total_cases})")
    print(f"  实体准确率: {entity_accuracy * 100:.1f}% ({correct_entities}/{total_entities})")
    
    print(f"\n分类统计:")
    for category, stats in category_stats.items():
        cat_case_acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        cat_entity_acc = stats["entities_correct"] / stats["entities_total"] if stats["entities_total"] > 0 else 0
        print(f"  {category}:")
        print(f"    用例准确率: {cat_case_acc * 100:.1f}% ({stats['correct']}/{stats['total']})")
        print(f"    实体准确率: {cat_entity_acc * 100:.1f}% ({stats['entities_correct']}/{stats['entities_total']})")
    
    # 判断是否达标
    print("\n" + "=" * 80)
    if entity_accuracy >= 0.9:
        print("✓ 实体提取准确率达标 (>90%)")
        return True
    else:
        print(f"✗ 实体提取准确率未达标 ({entity_accuracy * 100:.1f}% < 90%)")
        return False


if __name__ == "__main__":
    asyncio.run(test_entity_extraction())
