"""
记忆提取工具定义

使用 Function Calling 一次性提取：
1. 记忆内容（可多条）
2. 时间信息
3. 情绪信息
4. 实体（人物、地点、事件、主题等）
5. 实体关系

设计原则：
- entities 不提取"我"（记忆所有者通过 user_id 标识）
- relations 中可以包含"我"，表示记忆所有者与其他实体的关系
- 每个实体必须有至少一条关系
- 时间标准化为 ISO 8601 格式
"""

from typing import Dict, Any

# 提取记忆工具
EXTRACT_MEMORIES_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "extract_memories_with_graph",
        "description": """从文本中提取独立的记忆内容，包括时间、情绪、实体和关系。

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

示例4 - 长日记分割：
输入："早上自然醒，煮了绿茶，看书。下午去公园散步，看到风筝。晚上做了家常菜，在阳台看晚风。"
输出：3条记忆
- "早上自然醒，煮了绿茶，看书"
- "下午去公园散步，看到风筝"
- "晚上做了家常菜，在阳台看晚风"

【核心要求】

1. 按上述规则将长文本分割为独立的记忆点
2. 提取时间信息并标准化为 ISO 8601 格式
3. 识别实体并分类
4. 为每个实体创建关系

【记忆内容精炼规则】

精炼原则：保留完整信息，删除冗余修饰

✅ 必须保留：
- 时间、地点、人物（谁在什么时候在哪里做了什么）
- 核心事件和关键细节
- 重要对话主题或结论

❌ 可以删除：
- 过度的情感修饰（"心里暖暖的"、"满满的成就感"）
- 重复的描述
- 无关的场景细节

字数建议：50-100 字，保留完整信息优先

精炼示例：

原文："晚上回家，发现家人特意做了我最爱吃的菜，等着我一起吃饭。饭桌上，家人聊着日常的琐事，关心我的生活和工作。"
精炼："晚上回家，家人做了爱吃的菜等着我，饭桌上聊日常琐事，关心我的生活和工作。"（保留关键细节）

原文："下午尝试学习了一项新技能，刚开始手忙脚乱频频出错，但咬牙坚持下来，一遍遍练习后终于掌握了要领。"
精炼："下午学习新技能，刚开始出错但坚持练习，最终掌握了要领。"（保留过程和结果）

【时间标准化规则】

日期标准化：
- "今天" → 当前日期
- "昨天" → 当前日期 - 1天
- "上周一" → 上周的周一
- 如果无法确定具体日期，time.value 设为 null

时间段标准化（time.period）：
| 时间描述 | period 值 |
|---------|----------|
| 早上、上午、清晨、早晨 | morning |
| 下午、午后 | afternoon |
| 傍晚、晚上、黄昏 | evening |
| 深夜、夜里、半夜、凌晨 | night |

示例：
- "昨天早上" → value: 昨天, period: "morning"
- "今天晚上" → value: 今天, period: "evening"
- "凌晨三点" → value: 今天, period: "night"

【实体提取规则 - 分级策略】

⭐ 必须提取（核心实体，有明确召回价值）：
- person（人物）：
  - 具体人名：张三、王总、李医生
  - 核心家庭成员：爸爸、妈妈、老婆、老公、儿子、女儿
- location（地点）：具体场所，如星巴克、会议室、家、公司
- event（事件）：
  ✅ 重要事件：面试、会议、生日会、婚礼、旅行
  ✅ 课程学习：数学课、语文课、培训课、讲座
  ✅ 社交活动：聚餐、聚会、约会、相亲
  ✅ 工作项目：项目启动、项目上线、年度总结
- organization（组织）：公司/机构名，如腾讯、字节跳动
- project（项目）：具体项目名，如ABC项目、年度总结

⚠️ 有条件提取：
- topic（主题）：明确的讨论话题，如新项目、旅行计划
- object（物品）：仅限重要物品（钥匙、钱包、合同、证书、身份证）
  ❌ 不提取日常物品：汤圆、奶茶、书本、阳光、鸟鸣、露珠等

❌ 不提取：
- 第一人称代词：我、自己、本人、我们
- 泛指人物：家人、亲戚、朋友、同事、同桌、邻居、阿姨、老师、同学
- 时间词：今天、昨天、上周（放到 time 字段）
- 自然现象：阳光、雨声、春风、鸟鸣
- 日常物品：食物、饮料、普通用品
- 日常行为（event类）：
  ❌ 日常起居：吃饭、睡觉、起床、洗漱、午休
  ❌ 日常活动：看书、散步、喝茶、做饭、煮面、看电影
  ❌ 日常琐事：写作业、整理、打扫、洗澡、洗衣服
  ❌ 通用行为：出行、返程、行走、观看、拍照、野餐

【实体提取判断原则】

核心问题：用户会主动搜索这个实体吗？
├── 会搜索 → 提取
│   ├── "我在星巴克的记忆" → location: 星巴克 ✅
│   ├── "我关于面试的记忆" → event: 面试 ✅
│   └── "我关于张三的记忆" → person: 张三 ✅
│
└── 不会搜索 → 不提取
    ├── "我关于吃饭的记忆" → 无意义 ❌
    ├── "我关于散步的记忆" → 无意义 ❌
    └── "我关于看书的记忆" → 无意义 ❌

【关系提取规则】

每个实体必须有至少一条关系连接到"我"：

| 实体类型 | 关系类型 | 示例 |
|---------|---------|------|
| person | met, with, friend, colleague | 我 met 张三 |
| location | at, from, to | 我 at 星巴克 |
| event | participated, organized | 我 participated 会议 |
| organization | at, from | 我 at 腾讯 |
| project | participated, discussed | 我 participated ABC项目 |
| topic | discussed, mentioned | 我 discussed 新项目 |
| object | used, mentioned | 我 used 钥匙 |

【提取示例】

示例1 - 有人物的记忆：
输入："早上在星巴克见了张三，聊了新项目"
输出：
{
  "content": "早上在星巴克见了张三，聊了新项目",
  "time": {"value": "2026-03-23", "period": "morning"},
  "entities": [
    {"name": "张三", "type": "person"},
    {"name": "星巴克", "type": "location"},
    {"name": "新项目", "type": "topic"}
  ],
  "relations": [
    {"source": "我", "target": "星巴克", "relation_type": "at"},
    {"source": "我", "target": "张三", "relation_type": "met"},
    {"source": "我", "target": "新项目", "relation_type": "discussed"}
  ],
  "tags": ["社交", "工作"]
}

示例2 - 无核心实体的记忆：
输入："吃了汤圆，感觉很幸福"
输出：
{
  "content": "吃了汤圆，感觉很幸福",
  "time": null,
  "emotion": {"type": "幸福", "intensity": 8},
  "entities": [],
  "relations": [],
  "tags": ["日常"]
}
说明：汤圆是日常食物，幸福是泛化概念，都不提取

示例3 - 有重要物品的记忆：
输入："丢了钱包，补办了身份证"
输出：
{
  "content": "丢了钱包，补办了身份证",
  "entities": [
    {"name": "钱包", "type": "object"},
    {"name": "身份证", "type": "object"}
  ],
  "relations": [
    {"source": "我", "target": "钱包", "relation_type": "mentioned"},
    {"source": "我", "target": "身份证", "relation_type": "used"}
  ],
  "tags": ["重要"]
}

示例4 - 日常行为不提取 event：
输入："下午在家看书，晚上做了面条吃"
输出：
{
  "content": "下午在家看书，晚上做了面条吃",
  "entities": [
    {"name": "家", "type": "location"}
  ],
  "relations": [
    {"source": "我", "target": "家", "relation_type": "at"}
  ],
  "tags": ["日常"]
}
说明：看书、做面条是日常行为，不提取为 event；家是常驻地点，提取为 location
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
                            "content": {
                                "type": "string",
                                "description": "记忆的核心内容（简洁、完整的一句话或一段话）",
                            },
                            "time": {
                                "type": "object",
                                "description": "时间信息",
                                "properties": {
                                    "value": {
                                        "type": "string",
                                        "description": "ISO 8601 格式日期（如 2026-03-22），只精确到日期",
                                    },
                                    "period": {
                                        "type": "string",
                                        "description": "时间段",
                                        "enum": [
                                            "morning",
                                            "afternoon",
                                            "evening",
                                            "night",
                                        ],
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "description": "时间提取的置信度（0-1）",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                },
                                "required": ["value"],
                            },
                            "entities": {
                                "type": "array",
                                "description": "提取的实体列表（不包含'我'）",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "description": "实体名称",
                                        },
                                        "type": {
                                            "type": "string",
                                            "description": "实体类型",
                                            "enum": [
                                                "person",
                                                "location",
                                                "event",
                                                "topic",
                                                "organization",
                                                "project",
                                                "concept",
                                                "object",
                                                "time",
                                                "emotion",
                                            ],
                                        },
                                        "confidence": {
                                            "type": "number",
                                            "description": "实体识别置信度（0-1）",
                                            "minimum": 0,
                                            "maximum": 1,
                                        },
                                    },
                                    "required": ["name", "type"],
                                },
                            },
                            "relations": {
                                "type": "array",
                                "description": "实体之间的关系列表",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "source": {
                                            "type": "string",
                                            "description": "源实体名称（可以是'我'或具体实体）",
                                        },
                                        "target": {
                                            "type": "string",
                                            "description": "目标实体名称（必须是具体实体）",
                                        },
                                        "relation_type": {
                                            "type": "string",
                                            "description": "关系类型",
                                            "enum": [
                                                "at",
                                                "from",
                                                "to",
                                                "with",
                                                "met",
                                                "friend",
                                                "colleague",
                                                "participated",
                                                "organized",
                                                "discussed",
                                                "belongs_to",
                                                "part_of",
                                                "mentioned",
                                                "related_to",
                                                "caused",
                                                "used",
                                                "experienced",
                                            ],
                                        },
                                        "confidence": {
                                            "type": "number",
                                            "description": "关系推理置信度（0-1）",
                                            "minimum": 0,
                                            "maximum": 1,
                                        },
                                    },
                                    "required": ["source", "target", "relation_type"],
                                },
                            },
                            "tags": {
                                "type": "array",
                                "description": "记忆标签（用于分类）",
                                "items": {"type": "string"},
                            },
                            "emotion": {
                                "type": "object",
                                "description": "情绪信息",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "description": "情绪类型（如'开心'、'焦虑'、'平静'）",
                                    },
                                    "intensity": {
                                        "type": "integer",
                                        "description": "情绪强度（1-10）",
                                        "minimum": 1,
                                        "maximum": 10,
                                    },
                                },
                            },
                            "importance": {
                                "type": "number",
                                "description": "记忆重要性评分（0-1，默认 0.5）",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                        "required": ["content", "entities", "relations"],
                    },
                }
            },
            "required": ["memories"],
        },
    },
}


# 系统 Prompt
EXTRACT_MEMORIES_SYSTEM_PROMPT = """你是一个专业的记忆提取助手。你的任务是从用户输入的文本中提取结构化的记忆信息。

当前日期：{current_date}（{current_weekday}）

请严格按照 Function Calling 工具的 schema 返回结果。确保：
1. 每条记忆内容独立、完整
2. 时间已标准化为 ISO 8601 格式
3. 实体提取遵循分级策略：
   - 必须提取：person, location, event, organization, project
   - 有条件提取：topic, object（重要物品）, concept（核心主题）
   - 不提取：日常物品、自然现象、泛化概念
4. 为每个提取的实体创建关系
5. 如果没有核心实体，entities 和 relations 可以为空
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
    current_weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
        now.weekday()
    ]

    return EXTRACT_MEMORIES_SYSTEM_PROMPT.format(
        current_date=current_date, current_weekday=current_weekday
    )
