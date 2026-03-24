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

【⚠️ 分割稳定性规则 - 必须遵守】

核心原则：**保守分割，避免过度细分**

规则0 - 分割数量约束（最高优先级）：
- **每个自然段落提取 1-2 条核心记忆**（不是每句话）
- **每个时间段（早/中/晚）最多 2 条记忆**
- 连续的日常活动（起床、吃饭、看书）→ 合并为 1 条
- 只有独立的重大事件才单独提取

规则1 - 时间分割（优先级低）：
- 时间跨度大（上午/下午/晚上）且事件完全独立 → 可以分割
- 同一时间段内的多个事件 → 合并为 1 条
- **同一时间段的活动描述 → 不分割**

规则2 - 事件分割（严格限制）：
- ❌ 日常行为（吃饭、睡觉、看书、散步）→ 不作为独立分割依据
- ✅ 重要事件（面试、会议、旅行、聚会）→ 可独立分割
- ✅ 有具体人名 + 具体地点的社交活动 → 可独立分割

规则3 - 不分割（默认行为）：
- 连续事件（去A→遇到B→做C）→ 不分割
- 平行事件（做A同时做B）→ 不分割
- 同一时间段的生活片段（起床、做饭、吃饭、看书）→ 不分割
- 情感感悟 + 相关事件 → 合并为 1 条

【稳定性示例】

❌ 过度分割（不稳定）：
输入："早上自然醒，煮了绿茶，看书。下午去公园散步，看到风筝。晚上做了家常菜，在阳台看晚风。"
错误输出：6条记忆（早3条、下2条、晚1条）

✅ 保守分割（稳定）：
输入："早上自然醒，煮了绿茶，看书。下午去公园散步，看到风筝。晚上做了家常菜，在阳台看晚风。"
正确输出：3条记忆
- "早上自然醒，煮了绿茶看书"
- "下午去公园散步，看到风筝"
- "晚上做了家常菜，在阳台看晚风"

❌ 过度分割（不稳定）：
输入："早餐煮了一碗汤圆，搭配牛奶。出门时看到迎春花开了。中午和同事李四吃了面。"
错误输出：3条记忆

✅ 保守分割（稳定）：
输入："早餐煮了一碗汤圆，搭配牛奶。出门时看到迎春花开了。中午和同事李四吃了面。"
正确输出：2条记忆
- "早餐煮汤圆配牛奶，出门看到迎春花开了"
- "中午和同事李四吃了面"

【核心要求】

1. **保守分割**：宁可少分，不要多分
2. **稳定性优先**：相同内容应产生相同数量的记忆
3. 提取时间信息并标准化为 ISO 8601 格式
4. 识别实体并分类
5. 为每个实体创建关系

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

字数范围：30-60 字（严格执行）

精炼示例：

原文："晚上回家，发现家人特意做了我最爱吃的菜，等着我一起吃饭。饭桌上，家人聊着日常的琐事，关心我的生活和工作。"
精炼："晚上回家，家人做了爱吃的菜等我吃饭，饭桌上聊日常琐事。"（27字）

原文："下午尝试学习了一项新技能，刚开始手忙脚乱频频出错，但咬牙坚持下来，一遍遍练习后终于掌握了要领。"
精炼："下午学习新技能，出错后坚持练习，最终掌握了要领。"（24字）

【时间标准化规则】

日期标准化：
- "今天" → 当前日期
- "昨天" → 当前日期 - 1天
- "上周一" → 上周的周一
- 如果无法确定具体日期，time.value 设为 null

时间段标准化（time.period）：

时间段定义（优先级从高到低）：
| 时间范围 | period 值 | 说明 |
|---------|----------|------|
| 00:00-06:00 | night | 凌晨、深夜 |
| 06:00-12:00 | morning | 早上、上午 |
| 12:00-14:00 | afternoon | 中午、正午 |
| 14:00-18:00 | afternoon | 下午 |
| 18:00-22:00 | evening | 傍晚、晚上 |
| 22:00-24:00 | night | 深夜、夜里 |

描述词映射：
| 时间描述 | period 值 |
|---------|----------|
| 早上、上午、清晨、早晨 | morning |
| 中午、正午 | afternoon |
| 下午、午后 | afternoon |
| 傍晚、黄昏、晚饭时间 | evening |
| 晚上、晚间 | evening |
| 深夜、夜里、半夜、凌晨 | night |

重要规则：
1. **中午、正午归类为 afternoon**（12:00-14:00）
2. **晚上默认归类为 evening**（18:00-22:00）
3. **深夜、夜里、半夜、凌晨归类为 night**（22:00-06:00）
4. **如果提到具体时间，按时间范围判断**：
   - "晚上8点" → evening
   - "晚上11点" → night
   - "夜里3点" → night
5. **如果没有明确时间，按描述词判断**：
   - "晚上看了电影" → evening（默认晚上是18:00-22:00）
   - "深夜还在工作" → night

⚠️ 特殊情况处理（稳定性关键）：
- **"晚上"单独出现 → 必须归类为 evening**（即使后面有"夜风"、"夜色"等修饰）
- **"晚上回家"、"晚上做了X" → evening**
- **"夜里"、"深夜"、"半夜"、"凌晨"单独出现 → night**
- **判断依据：以第一个明确的时间描述词为准**
- 示例：
  - "晚上回家开窗吹夜风" → evening（"晚上"在前，主导分类）
  - "深夜还在加班" → night
  - "晚上11点" → night（有具体时间）

示例：
- "昨天早上" → value: 昨天, period: "morning"
- "今天中午" → value: 今天, period: "afternoon"
- "今天晚上" → value: 今天, period: "evening"
- "晚上8点" → value: 今天, period: "evening"
- "晚上11点" → value: 今天, period: "night"
- "凌晨三点" → value: 今天, period: "night"
- "深夜还在加班" → value: 今天, period: "night"
- "晚上回家开窗看夜色" → value: 今天, period: "evening"（晚上在前，主导分类）
- "晚上做了家常菜" → value: 今天, period: "evening"

【实体提取规则 - 分级策略】

⭐ 必须提取（核心实体，有明确召回价值）：

1. person（人物）：
   - 具体人名：张三、王总、李医生
   - 核心家庭成员：爸爸、妈妈、老婆、老公、儿子、女儿
   - ❌ 不提取泛指：家人、朋友、同事、邻居

2. location（地点）：
   - 具体场所：星巴克、公司、学校、公园
   - ❌ 不提取泛指：附近、路边、户外

3. event（事件）：
   - ✅ 重要事件：面试、会议、生日会、婚礼、旅行
   - ✅ 课程活动：数学课、培训课、讲座
   - ✅ 社交活动：聚餐、聚会、约会
   - ❌ 不提取日常行为：吃饭、睡觉、看书、散步

4. organization（组织）：
   - 定义：正式注册的公司、机构、学校
   - ✅ 提取：腾讯、字节跳动、清华大学、人民医院
   - ❌ 不提取：非正式群体（我们团队、项目组、部门）

5. project（项目）：
   - 具体项目名：ABC项目、年度总结、新产品开发

⚠️ 有条件提取：

1. topic（主题）：
   - 定义：明确讨论的话题或计划
   - ✅ 提取：新项目、旅行计划、季度计划
   - ❌ 不提取泛化词：工作、学习、生活

2. concept（概念）：
   - 定义：具体的理论、方法论、节日主题
   - ✅ 提取：番茄工作法、精益创业、龙抬头（节日）
   - ❌ 不提取：抽象概念（独处、成长、幸福、焦虑）

3. object（物品）：
   - 仅限重要物品：钥匙、钱包、合同、证书
   - ❌ 不提取日常物品：汤圆、奶茶、书本、茶

【实体名称粒度规则】

⚠️ 核心原则：地点名称必须简洁，用户会用这个词搜索

【地点名称粒度规则】

✅ 正确提取：
| 原文 | 提取结果 | 原因 |
|-----|---------|------|
| 城郊湿地公园 | 城郊湿地公园 | 专有名词，保留完整 |
| 公园 | 公园 | 已经是核心名称 |
| 星巴克 | 星巴克 | 品牌名 |
| 公司 | 公司 | 通用场所 |
| 家 | 家 | 通用场所 |
| 学校 | 学校 | 通用场所 |

❌ 错误提取：
| 原文 | 错误提取 | 正确做法 |
|-----|---------|---------|
| 附近的公园 | 附近公园 ❌ | 公园 ✅ |
| 公园湖边小路 | 公园湖边 ❌ | 公园 ✅ |
| 公司楼下小馆子 | 公司楼下小馆子 ❌ | 不提取 ✅ |
| 家附近的咖啡馆 | 家附近的咖啡馆 ❌ | 咖啡馆 ✅ 或不提取 |
| 公园旁小咖啡馆 | 小咖啡馆 ❌ | 咖啡馆 ✅ 或不提取 |
| 楼下小卖部 | 小卖部 ❌ | 不提取 ✅ |
| 校园小湖边 | 小湖 ❌ | 不提取 ✅ |

判断标准：
1. 如果地点名称包含"附近、旁边、楼下、路边"等方位词 → 去掉方位词或不提取
2. 如果地点名称包含"小、大"等形容词 → 去掉形容词或不提取
3. 如果地点是更大场所的细分位置（如"公园湖边"）→ 不提取，只提取核心场所

【人物名称粒度规则】

✅ 正确提取：
| 原文 | 提取结果 |
|-----|---------|
| 老朋友张三 | 张三 |
| 同事李四 | 李四 |
| 王总 | 王总 |

❌ 不提取泛指：
| 原文 | 不提取 |
|-----|--------|
| 家人 | - |
| 朋友 | - |
| 同事 | - |
| 邻居 | - |

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
    └── "我关于独处的记忆" → 太泛 ❌

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

示例2 - 地点名称粒度：
输入："下午去城郊湿地公园散步，在湖边小路上走了很久"
输出：
{
  "content": "下午去城郊湿地公园散步，在湖边走了很久",
  "entities": [
    {"name": "城郊湿地公园", "type": "location"}
  ],
  "relations": [
    {"source": "我", "target": "城郊湿地公园", "relation_type": "at"}
  ]
}
说明：提取"城郊湿地公园"，不提取"湖边小路"（是公园内的细分位置）

示例3 - 地点名称去掉修饰词：
输入："早上在家附近的咖啡馆喝了杯拿铁，然后去公司楼下小店买了早餐"
输出：
{
  "content": "早上在咖啡馆喝了拿铁，去小店买了早餐",
  "entities": [
    {"name": "咖啡馆", "type": "location"},
    {"name": "公司", "type": "location"}
  ],
  "relations": [
    {"source": "我", "target": "咖啡馆", "relation_type": "at"},
    {"source": "我", "target": "公司", "relation_type": "at"}
  ]
}
说明：
- "家附近的咖啡馆" → 提取"咖啡馆"（去掉"家附近的"）
- "公司楼下小店" → 不提取"小店"，提取"公司"（核心场所）

示例4 - organization 提取：
输入："今天收到腾讯的面试邀请，下周要去深圳面试"
输出：
{
  "content": "收到腾讯面试邀请，下周去深圳面试",
  "entities": [
    {"name": "腾讯", "type": "organization"},
    {"name": "深圳", "type": "location"},
    {"name": "面试", "type": "event"}
  ],
  "relations": [
    {"source": "我", "target": "腾讯", "relation_type": "at"},
    {"source": "我", "target": "深圳", "relation_type": "to"},
    {"source": "我", "target": "面试", "relation_type": "participated"}
  ]
}

示例4 - 不提取 concept 和日常行为：
输入："周末在家独处，看了一下午书，感觉很充实"
输出：
{
  "content": "周末在家看书，感觉很充实",
  "entities": [
    {"name": "家", "type": "location"}
  ],
  "relations": [
    {"source": "我", "target": "家", "relation_type": "at"}
  ]
}
说明：独处是泛化概念不提取，看书是日常行为不提取

示例5 - 无核心实体的记忆：
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

示例6 - 有重要物品的记忆：
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
