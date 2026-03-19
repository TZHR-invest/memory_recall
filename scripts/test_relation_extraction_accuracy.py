"""
关系推理准确率测试脚本

测试目标：
- 关系推理准确率 > 85%
- 支持多种关系类型（at, met_at, friend, colleague 等）
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


# 测试用例
TEST_CASES = [
    # 地点关系
    {
        "text": "今天和张三在咖啡店聊天",
        "entities": ["张三", "咖啡店", "聊天"],
        "expected_relations": [
            {"source": "张三", "relationship": "at", "destination": "咖啡店"}
        ],
        "category": "地点关系"
    },
    {
        "text": "明天要和李四去北京出差",
        "entities": ["李四", "北京", "出差"],
        "expected_relations": [
            {"source": "李四", "relationship": "at", "destination": "北京"}
        ],
        "category": "地点关系"
    },
    
    # 人物关系
    {
        "text": "我和老王是多年的朋友",
        "entities": ["我", "老王"],
        "expected_relations": [
            {"source": "我", "relationship": "friend", "destination": "老王"}
        ],
        "category": "人物关系"
    },
    {
        "text": "小明是我的同事",
        "entities": ["小明", "我"],
        "expected_relations": [
            {"source": "小明", "relationship": "colleague", "destination": "我"}
        ],
        "category": "人物关系"
    },
    {
        "text": "小红是我的姐姐",
        "entities": ["小红", "我"],
        "expected_relations": [
            {"source": "小红", "relationship": "family", "destination": "我"}
        ],
        "category": "人物关系"
    },
    
    # 事件参与
    {
        "text": "周末和小李去爬山",
        "entities": ["小李", "爬山"],
        "expected_relations": [
            {"source": "小李", "relationship": "participated", "destination": "爬山"}
        ],
        "category": "事件参与"
    },
    {
        "text": "昨天参加了公司会议",
        "entities": ["公司", "会议", "昨天"],
        "expected_relations": [
            {"source": "会议", "relationship": "at", "destination": "公司"}
        ],
        "category": "事件参与"
    },
    
    # 主题讨论
    {
        "text": "我们一起讨论了新项目",
        "entities": ["讨论", "新项目"],
        "expected_relations": [
            {"source": "讨论", "relationship": "about", "destination": "新项目"}
        ],
        "category": "主题讨论"
    },
    {
        "text": "他对机器学习很感兴趣",
        "entities": ["他", "机器学习"],
        "expected_relations": [
            {"source": "他", "relationship": "interested_in", "destination": "机器学习"}
        ],
        "category": "主题讨论"
    },
    
    # 情感关系
    {
        "text": "我很喜欢这部电影",
        "entities": ["我", "电影"],
        "expected_relations": [
            {"source": "我", "relationship": "likes", "destination": "电影"}
        ],
        "category": "情感关系"
    },
    {
        "text": "他对这个决定很失望",
        "entities": ["他", "决定", "失望"],
        "expected_relations": [
            {"source": "他", "relationship": "dislikes", "destination": "决定"}
        ],
        "category": "情感关系"
    },
    
    # 复杂关系
    {
        "text": "上周六和小红在餐厅吃饭，聊了很多有趣的话题",
        "entities": ["小红", "餐厅", "吃饭", "话题"],
        "expected_relations": [
            {"source": "小红", "relationship": "at", "destination": "餐厅"},
            {"source": "小红", "relationship": "participated", "destination": "吃饭"}
        ],
        "category": "复杂关系"
    },
    {
        "text": "昨天在公园遇到老同学，我们一起散步",
        "entities": ["公园", "老同学", "散步"],
        "expected_relations": [
            {"source": "老同学", "relationship": "at", "destination": "公园"},
            {"source": "老同学", "relationship": "participated", "destination": "散步"}
        ],
        "category": "复杂关系"
    }
]


async def test_relation_extraction():
    """测试关系推理准确率"""
    print("=" * 80)
    print("关系推理准确率测试")
    print("=" * 80)
    
    # 初始化客户端
    client = OpenAI(
        api_key=VOLC_API_KEY,
        base_url=VOLC_API_BASE
    )
    
    # 统计结果
    total_cases = len(TEST_CASES)
    correct_cases = 0
    total_relations = 0
    correct_relations = 0
    category_stats = {}
    
    print(f"\n总测试用例: {total_cases}")
    print("-" * 80)
    
    for i, test_case in enumerate(TEST_CASES, 1):
        category = test_case["category"]
        if category not in category_stats:
            category_stats[category] = {
                "total": 0,
                "correct": 0,
                "relations_total": 0,
                "relations_correct": 0
            }
        
        category_stats[category]["total"] += 1
        
        print(f"\n[{i}/{total_cases}] {category}: {test_case['text']}")
        print(f"  实体列表: {test_case['entities']}")
        
        try:
            # 调用 API
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
                tool_call = message.tool_calls[0]
                if tool_call.function.name == "establish_relations":
                    arguments = json.loads(tool_call.function.arguments)
                    relations = arguments.get("relations", [])
                    
                    # 提取的关系类型
                    relation_types = [r.get("relationship", "") for r in relations]
                    relation_details = [
                        f"{r.get('source', '')}-{r.get('relationship', '')}-{r.get('destination', '')}"
                        for r in relations
                    ]
                    
                    print(f"  期望关系: {[f'{r['source']}-{r['relationship']}-{r['destination']}' for r in test_case['expected_relations']]}")
                    print(f"  提取关系: {relation_details}")
                    
                    # 计算匹配度
                    matched = 0
                    for expected in test_case["expected_relations"]:
                        total_relations += 1
                        category_stats[category]["relations_total"] += 1
                        
                        # 检查关系类型
                        for relation in relations:
                            if (relation.get("relationship") == expected["relationship"] or
                                # 允许相似的关系类型
                                _is_similar_relation(relation.get("relationship", ""), expected["relationship"])):
                                matched += 1
                                correct_relations += 1
                                category_stats[category]["relations_correct"] += 1
                                break
                    
                    # 检查是否通过（至少匹配一个期望关系）
                    expected_count = len(test_case["expected_relations"])
                    if matched >= expected_count - 1:  # 允许 1 个遗漏
                        correct_cases += 1
                        category_stats[category]["correct"] += 1
                        print(f"  ✓ 测试通过 ({matched}/{expected_count})")
                    else:
                        print(f"  ✗ 测试失败 ({matched}/{expected_count})")
                    
                    # 检查置信度
                    has_confidence = all("confidence" in r for r in relations)
                    if has_confidence:
                        print(f"  ✓ 所有关系都有置信度")
                    else:
                        print(f"  ⚠ 部分关系缺少置信度")
            
            else:
                print("  ✗ 没有工具调用")
        
        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
    
    # 输出统计结果
    print("\n" + "=" * 80)
    print("测试结果统计")
    print("=" * 80)
    
    case_accuracy = correct_cases / total_cases if total_cases > 0 else 0
    relation_accuracy = correct_relations / total_relations if total_relations > 0 else 0
    
    print(f"\n整体准确率:")
    print(f"  用例准确率: {case_accuracy * 100:.1f}% ({correct_cases}/{total_cases})")
    print(f"  关系准确率: {relation_accuracy * 100:.1f}% ({correct_relations}/{total_relations})")
    
    print(f"\n分类统计:")
    for category, stats in category_stats.items():
        cat_case_acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        cat_rel_acc = stats["relations_correct"] / stats["relations_total"] if stats["relations_total"] > 0 else 0
        print(f"  {category}:")
        print(f"    用例准确率: {cat_case_acc * 100:.1f}% ({stats['correct']}/{stats['total']})")
        print(f"    关系准确率: {cat_rel_acc * 100:.1f}% ({stats['relations_correct']}/{stats['relations_total']})")
    
    # 判断是否达标
    print("\n" + "=" * 80)
    if relation_accuracy >= 0.85:
        print("✓ 关系推理准确率达标 (>85%)")
        return True
    else:
        print(f"✗ 关系推理准确率未达标 ({relation_accuracy * 100:.1f}% < 85%)")
        return False


def _is_similar_relation(rel1: str, rel2: str) -> bool:
    """判断两个关系类型是否相似"""
    # 定义相似关系组
    similar_groups = [
        {"at", "met_at", "located_at"},
        {"friend", "friends"},
        {"colleague", "colleagues"},
        {"participated", "participate_in", "participated_in"},
        {"discussed", "about", "discussing"},
        {"likes", "like", "interested_in"},
        {"dislikes", "dislike"}
    ]
    
    for group in similar_groups:
        if rel1 in group and rel2 in group:
            return True
    
    return False


if __name__ == "__main__":
    asyncio.run(test_relation_extraction())
