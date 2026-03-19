"""
Prompt 模板（借鉴 Mem0）

核心设计：
1. 区分用户记忆和 Agent 记忆
2. 明确提取范围（只从特定角色）
3. 多语言支持
4. 丰富的示例（Few-shot Learning）
"""

from datetime import datetime
from typing import List, Dict, Optional


# ============================================================================
# 用户记忆提取 Prompt
# ============================================================================
USER_MEMORY_EXTRACTION_PROMPT = f"""你是一个个人信息整理专家，专门负责从对话中提取用户的记忆和偏好。

# [重要]：只从用户的消息中提取信息，不要包含助手或系统消息的内容。

需要记录的信息类型：

1. **个人偏好**：喜欢什么、不喜欢什么、特定偏好（食物、产品、活动、娱乐等）
2. **重要个人信息**：姓名、关系、重要日期
3. **计划和意图**：即将发生的事件、旅行、目标
4. **活动和服务偏好**：餐饮、旅行、爱好、其他服务
5. **健康和健康偏好**：饮食限制、健身习惯、其他健康相关信息
6. **职业信息**：职位、工作习惯、职业目标
7. **其他信息**：喜欢的书籍、电影、品牌等

以下是几个示例：

用户：嗨。
助手：你好！很高兴为你服务。
输出：{{"facts": []}}

用户：嗨，我正在找旧金山的餐厅。
助手：好的，我可以帮你。你对哪种菜系感兴趣？
输出：{{"facts": ["正在找旧金山的餐厅"]}}

用户：昨天下午3点和约翰开会，我们讨论了新项目。
助手：听起来是一个高效的会议。
输出：{{"facts": ["昨天下午3点和约翰开会并讨论了新项目"]}}

用户：嗨，我叫约翰。我是一名软件工程师。
助手：很高兴认识你，约翰！
输出：{{"facts": ["名字是约翰", "是一名软件工程师"]}}

用户：我最喜欢的电影是《盗梦空间》和《星际穿越》。你呢？
助手：很好的选择！两部电影都很棒。我最喜欢《黑暗骑士》和《肖申克的救赎》。
输出：{{"facts": ["最喜欢的电影是《盗梦空间》和《星际穿越》"]}}

请以 JSON 格式返回事实和偏好。

记住：
- [重要] 只从用户消息中提取信息，不要包含助手或系统消息的内容
- 今天的日期是 {datetime.now().strftime("%Y-%m-%d")}
- 检测用户输入的语言，并用相同的语言记录事实
- 如果找不到相关信息，可以返回空列表
- 返回格式必须是 JSON，包含 "facts" 键，值为字符串列表
"""


# ============================================================================
# Agent 记忆提取 Prompt
# ============================================================================
AGENT_MEMORY_EXTRACTION_PROMPT = f"""你是一个助手信息整理专家，专门负责从对话中提取关于 AI 助手的记忆、偏好和特征。

# [重要]：只从助手的消息中提取信息，不要包含用户或系统消息的内容。

需要记录的信息类型：

1. **助手的偏好**：喜欢什么、不喜欢什么、特定偏好
2. **助手的能力**：特定技能、知识领域、可以执行的任务
3. **助手的假设性计划或活动**：假设性活动或计划
4. **助手的个性特征**：个性特征或特征
5. **助手的工作方式**：如何处理不同类型的任务或问题
6. **助手的知识领域**：展示知识的主题或领域
7. **其他信息**：其他有趣或独特的细节

示例：

用户：我最喜欢的电影是《盗梦空间》和《星际穿越》。你呢？
助手：很好的选择！两部电影都很棒。我最喜欢《黑暗骑士》和《肖申克的救赎》。
输出：{{"facts": ["最喜欢的电影是《黑暗骑士》和《肖申克的救赎》"]}}

请以 JSON 格式返回事实和偏好。

记住：
- [重要] 只从助手消息中提取信息，不要包含用户或系统消息的内容
- 检测助手输入的语言，并用相同的语言记录事实
"""


# ============================================================================
# 智能记忆更新 Prompt
# ============================================================================
MEMORY_UPDATE_PROMPT = """你是一个智能记忆管理器，负责管理系统的记忆。

你可以执行四种操作：(1) 添加到记忆，(2) 更新记忆，(3) 从记忆中删除，(4) 不改变。

根据以上四种操作，记忆会发生变化。

将新检索的事实与现有记忆进行比较。对于每个新事实，决定是否：
- ADD：将其作为新元素添加到记忆中
- UPDATE：更新现有的记忆元素
- DELETE：从记忆中删除现有记忆元素
- NONE：不做任何更改（如果事实已经存在或无关）

选择执行哪种操作的具体准则：

1. **添加**：如果检索的事实包含记忆中不存在的新信息，则需要添加它，方法是在 id 字段中生成新的 ID。
   
   示例：
   旧记忆：
   [
       {{"id": "0", "text": "用户是一名软件工程师"}}
   ]
   新检索的事实：["名字是约翰"]
   新记忆：
   {{
       "memory": [
           {{"id": "0", "text": "用户是一名软件工程师", "event": "NONE"}},
           {{"id": "1", "text": "名字是约翰", "event": "ADD"}}
       ]
   }}

2. **更新**：如果检索的事实包含记忆中已经存在但完全不同的信息，则需要更新它。如果检索的事实包含与记忆中存在的元素传达相同信息的信息，则需要保留具有最多信息的事实。
   
   示例：
   旧记忆：
   [
       {{"id": "0", "text": "我喜欢奶酪披萨"}},
       {{"id": "1", "text": "用户是一名软件工程师"}},
       {{"id": "2", "text": "用户喜欢打板球"}}
   ]
   新检索的事实：["喜欢鸡肉披萨", "喜欢和朋友一起打板球"]
   新记忆：
   {{
       "memory": [
           {{"id": "0", "text": "喜欢奶酪和鸡肉披萨", "event": "UPDATE", "old_memory": "我喜欢奶酪披萨"}},
           {{"id": "1", "text": "用户是一名软件工程师", "event": "NONE"}},
           {{"id": "2", "text": "喜欢和朋友一起打板球", "event": "UPDATE", "old_memory": "用户喜欢打板球"}}
       ]
   }}

3. **删除**：如果检索的事实包含与记忆中信息矛盾的信息，则需要删除它。
   
   示例：
   旧记忆：
   [
       {{"id": "0", "text": "名字是约翰"}},
       {{"id": "1", "text": "喜欢奶酪披萨"}}
   ]
   新检索的事实：["不喜欢奶酪披萨"]
   新记忆：
   {{
       "memory": [
           {{"id": "0", "text": "名字是约翰", "event": "NONE"}},
           {{"id": "1", "text": "喜欢奶酪披萨", "event": "DELETE"}}
       ]
   }}

4. **不改变**：如果检索的事实包含记忆中已经存在的信息，则不需要进行任何更改。

你必须仅以以下 JSON 结构返回响应：

{{
    "memory": [
        {{
            "id": "<记忆ID>",
            "text": "<记忆内容>",
            "event": "<操作>",
            "old_memory": "<旧记忆内容>"  // 仅在 event 为 "UPDATE" 时需要
        }}
    ]
}}

遵循以下指令：
- 不要返回上面提供的自定义示例中的任何内容
- 如果当前记忆为空，则需要将新检索的事实添加到记忆中
- 你应该仅以 JSON 格式返回更新的记忆
- 如果有添加，生成新的键并添加对应的新记忆
- 如果有删除，应该从记忆中删除记忆键值对
- 如果有更新，ID 键应该保持不变，只有值需要更新

不要返回 JSON 格式以外的任何内容。
"""


# ============================================================================
# 实体提取 Prompt
# ============================================================================
ENTITY_EXTRACTION_PROMPT = """你是一个实体识别专家，专门从文本中提取人物、地点、事件、主题和情感等实体。

请从给定的文本中提取以下类型的实体：

1. **person（人物）**：人名、昵称、称呼等
2. **location（地点）**：地点名称、建筑、场所等
3. **event（事件）**：事件名称、活动、会议等
4. **topic（主题）**：话题、主题、关键词等
5. **emotion（情感）**：情绪、感受、态度等

提取规则：
- 只提取明确提及的实体，不要推测
- 每个实体需要一个置信度分数（0-1）
- 使用原始文本中的名称，不要标准化

示例：

文本：今天和张三在咖啡店讨论了机器学习项目
输出：
{{
    "entities": [
        {{"entity": "张三", "entity_type": "person", "confidence": 0.95}},
        {{"entity": "咖啡店", "entity_type": "location", "confidence": 0.9}},
        {{"entity": "讨论", "entity_type": "event", "confidence": 0.85}},
        {{"entity": "机器学习项目", "entity_type": "topic", "confidence": 0.88}}
    ]
}}

文本：周末和老王去爬山，心情很愉快
输出：
{{
    "entities": [
        {{"entity": "周末", "entity_type": "event", "confidence": 0.9}},
        {{"entity": "老王", "entity_type": "person", "confidence": 0.95}},
        {{"entity": "爬山", "entity_type": "event", "confidence": 0.9}},
        {{"entity": "愉快", "entity_type": "emotion", "confidence": 0.92}}
    ]
}}

请严格按照 JSON 格式返回结果。
"""


# ============================================================================
# 关系推理 Prompt
# ============================================================================
RELATION_EXTRACTION_PROMPT = """你是一个关系推理专家，专门分析实体之间的关系。

根据给定的实体列表和文本，推理出实体之间的关系。

# [重要] 必须使用以下预定义的关系类型（英文）：

**人物关系**：
- friend: 朋友关系
- colleague: 同事关系
- family: 家人关系
- met_at: 在...遇到

**地点关系**：
- at: 在...地点
- visited: 访问过
- lives_at: 居住在
- works_at: 工作在

**事件关系**：
- participated: 参与事件
- discussed: 讨论主题
- mentioned: 提及

**主题关系**：
- interested_in: 对...感兴趣
- knows_about: 了解...

**情感关系**：
- likes: 喜欢
- dislikes: 不喜欢
- loves: 爱

推理规则：
- 只推理文本中明确暗示的关系
- 每个关系需要一个置信度分数（0-1）
- 关系方向：从 source 到 destination
- **必须使用上面列出的英文关系类型，不要使用中文描述**

示例：

文本：今天和张三在咖啡店讨论了机器学习项目
实体：["张三", "咖啡店", "讨论", "机器学习项目"]
输出：
{{
    "relations": [
        {{"source": "张三", "destination": "咖啡店", "relationship": "at", "confidence": 0.9}},
        {{"source": "张三", "destination": "讨论", "relationship": "participated", "confidence": 0.88}},
        {{"source": "讨论", "destination": "机器学习项目", "relationship": "discussed", "confidence": 0.92}},
        {{"source": "张三", "destination": "机器学习项目", "relationship": "discussed", "confidence": 0.85}}
    ]
}}

文本：周末和老王去爬山，心情很愉快
实体：["周末", "老王", "爬山", "愉快"]
输出：
{{
    "relations": [
        {{"source": "老王", "destination": "爬山", "relationship": "participated", "confidence": 0.9}}
    ]
}}

文本：我和老王是多年的朋友
实体：["我", "老王"]
输出：
{{
    "relations": [
        {{"source": "我", "destination": "老王", "relationship": "friend", "confidence": 0.95}}
    ]
}}

请严格按照 JSON 格式返回结果，并使用预定义的英文关系类型。
"""


# ============================================================================
# 辅助函数
# ============================================================================

def get_memory_update_messages(old_memories: List[Dict], new_facts: List[str]) -> str:
    """生成记忆更新的 Prompt"""
    
    if old_memories:
        current_memory = f"""
下面是我到目前为止收集的当前记忆内容。你必须仅以以下格式更新它：

```
{old_memories}
```

"""
    else:
        current_memory = """
当前记忆为空。

"""
    
    return f"""{MEMORY_UPDATE_PROMPT}

{current_memory}

新检索的事实如下所述。你需要分析新检索的事实，并确定这些事实是应该被添加、更新还是从记忆中删除。

```
{new_facts}
```

你必须仅以以下 JSON 结构返回响应：

{{
    "memory": [
        {{
            "id": "<记忆ID>",
            "text": "<记忆内容>",
            "event": "<操作>",
            "old_memory": "<旧记忆内容>"
        }}
    ]
}}
"""


def get_entity_extraction_prompt() -> str:
    """获取实体提取 Prompt"""
    return ENTITY_EXTRACTION_PROMPT


def get_relation_extraction_prompt() -> str:
    """获取关系推理 Prompt"""
    return RELATION_EXTRACTION_PROMPT


# ============================================================================
# 场景自适应提取 Prompt（Phase 3）
# ============================================================================
SCENARIO_AWARE_EXTRACTION_PROMPT = """你是一个场景识别和实体提取专家，能够同时判断文本场景类型并提取相关实体。

# 场景类型说明

1. **daily_chat（日常对话）**
   - 特征：日常交流、闲聊、分享生活
   - 关注实体类型：person（人物）、location（地点）、emotion（情感）、event（事件）
   - 示例：今天和张三在咖啡店聊了很久

2. **work_meeting（工作会议）**
   - 特征：工作讨论、会议安排、任务分配
   - 关注实体类型：event（事件）、time（时间）、task（任务）、decision（决策）、person（人物）
   - 示例：明天的会议改到下午3点，记得准备PPT

3. **diary（日记）**
   - 特征：个人记录、情感表达、事件回顾
   - 关注实体类型：event（事件）、emotion（情感）、time（时间）、location（地点）
   - 示例：今天心情不错，完成了好多事情

4. **technical（技术讨论）**
   - 特征：技术问题、方案讨论、问题解决
   - 关注实体类型：concept（概念）、problem（问题）、solution（解决方案）、person（人物）
   - 示例：我们讨论了使用Redis做缓存，解决了性能问题

# 实体类型说明

**通用实体类型**：
- person: 人物（人名、昵称）
- location: 地点（场所、位置）
- event: 事件（活动、会议）
- emotion: 情感（情绪、感受）

**工作会议专用**：
- time: 时间（具体时间点或时段）
- task: 任务（待办事项）
- decision: 决策（会议决定）

**技术讨论专用**：
- concept: 概念（技术概念、术语）
- problem: 问题（遇到的难题）
- solution: 解决方案（解决方法）

# 提取规则

1. **场景判断**：根据文本内容和语气判断最合适的场景类型
2. **实体提取**：根据场景类型提取相关实体
3. **置信度**：每个实体需要给出置信度（0-1）
4. **不要推测**：只提取明确提及的实体

# 示例

**示例 1：日常对话**
文本：今天和张三在咖啡店聊了很久
输出：
{{
    "scenario": "daily_chat",
    "entities": [
        {{"entity": "张三", "entity_type": "person", "confidence": 0.95}},
        {{"entity": "咖啡店", "entity_type": "location", "confidence": 0.9}}
    ]
}}

**示例 2：工作会议**
文本：明天的会议改到下午3点，记得准备PPT
输出：
{{
    "scenario": "work_meeting",
    "entities": [
        {{"entity": "会议", "entity_type": "event", "confidence": 0.95}},
        {{"entity": "下午3点", "entity_type": "time", "confidence": 0.95}},
        {{"entity": "准备PPT", "entity_type": "task", "confidence": 0.9}}
    ]
}}

**示例 3：日记**
文本：今天心情不错，完成了好多事情
输出：
{{
    "scenario": "diary",
    "entities": [
        {{"entity": "心情不错", "entity_type": "emotion", "confidence": 0.95}},
        {{"entity": "完成了好多事情", "entity_type": "event", "confidence": 0.85}}
    ]
}}

**示例 4：技术讨论**
文本：我们讨论了使用Redis做缓存，解决了性能问题
输出：
{{
    "scenario": "technical",
    "entities": [
        {{"entity": "Redis", "entity_type": "concept", "confidence": 0.95}},
        {{"entity": "缓存", "entity_type": "concept", "confidence": 0.9}},
        {{"entity": "性能问题", "entity_type": "problem", "confidence": 0.95}},
        {{"entity": "使用Redis做缓存", "entity_type": "solution", "confidence": 0.9}}
    ]
}}

请严格按照 JSON 格式返回结果。
"""


def get_scenario_aware_extraction_prompt() -> str:
    """获取场景自适应提取 Prompt"""
    return SCENARIO_AWARE_EXTRACTION_PROMPT


if __name__ == "__main__":
    # 测试 Prompt 模板
    print("=" * 60)
    print("用户记忆提取 Prompt")
    print("=" * 60)
    print(USER_MEMORY_EXTRACTION_PROMPT[:500] + "...")
    print()
    
    print("=" * 60)
    print("实体提取 Prompt")
    print("=" * 60)
    print(ENTITY_EXTRACTION_PROMPT)
    print()
    
    print("=" * 60)
    print("关系推理 Prompt")
    print("=" * 60)
    print(RELATION_EXTRACTION_PROMPT)
    print()
    
    # 测试记忆更新 Prompt
    print("=" * 60)
    print("记忆更新 Prompt 示例")
    print("=" * 60)
    old_memories = [{"id": "0", "text": "用户是一名软件工程师"}]
    new_facts = ["名字是约翰"]
    prompt = get_memory_update_messages(old_memories, new_facts)
    print(prompt[:500] + "...")
