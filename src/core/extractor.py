"""
结构化提取模块
从文本/图片输入中提取结构化记忆
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import re


class MemoryExtractor:
    """记忆提取器"""
    
    def __init__(self, llm_client: Any = None):
        """
        初始化提取器
        
        Args:
            llm_client: LLM 客户端（OpenAI、Bailian 等）
        """
        self.llm_client = llm_client
        self.prompt_template = self._load_prompt_template()
    
    def _load_prompt_template(self) -> str:
        """加载提取 prompt 模板"""
        return """你是一个记忆提取助手。请从用户输入中提取结构化记忆。

## 输入
{user_input}

## 当前时间
{current_time}

## 提取规则

### time 字段
1. **明确时间**：直接提取，转换为 ISO 8601 格式
2. **相对时间**：基于当前时间计算
3. **推断时间**：从上下文推断
4. **缺失时间**：设为 null

### location 字段
1. **明确地点**：直接提取
2. **泛指地点**：提取 + 标记 need_confirm
3. **推断地点**：从上下文推断
4. **缺失地点**：设为 null

### people 字段
1. **明确人名**：直接提取
2. **身份指代**：提取 + 标记 need_confirm
3. **关系指代**：提取 + 标记 need_confirm
4. **缺失人物**：设为 null

### emotion 字段（可选）
从文本推断情绪，置信度 0-1

### tags 字段（可选）
生成 3-5 个标签

## 智能询问判断

### 需要询问的场景
1. **事件记录** + 时间缺失 → 询问时间
2. 人物未知 + need_confirm → 询问人物身份

### 不需要询问的场景
1. **心情记录** + 时空缺失 → 不询问
2. 单字段已足够 → 不询问其他

## 输出格式
```json
{
  "time": {
    "value": "ISO 8601 或 null",
    "source": "extracted/inferred/null",
    "confidence": 0.0-1.0
  },
  "location": {
    "name": "地点名称 或 null",
    "need_confirm": true/false,
    "source": "extracted/inferred/null"
  },
  "people": [
    {
      "name": "人物名称",
      "need_confirm": true/false,
      "relation": "关系（如知道）"
    }
  ],
  "emotion": {
    "value": "情绪",
    "confidence": 0.0-1.0
  },
  "tags": ["标签1", "标签2", "标签3"],
  "need_questions": ["需要询问的问题（最多2个）"]
}
```"""
    
    def extract_from_text(
        self,
        text: str,
        current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        从文本提取结构化记忆
        
        Args:
            text: 用户输入文本
            current_time: 当前时间（默认为系统时间）
        
        Returns:
            结构化记忆字典
        """
        if current_time is None:
            current_time = datetime.now()
        
        # 使用 LLM 提取
        if self.llm_client:
            return self._extract_with_llm(text, current_time)
        else:
            # 降级：规则提取
            return self._extract_with_rules(text, current_time)
    
    def _extract_with_llm(
        self,
        text: str,
        current_time: datetime
    ) -> Dict[str, Any]:
        """使用 LLM 提取"""
        prompt = self.prompt_template.format(
            user_input=text,
            current_time=current_time.isoformat()
        )
        
        # TODO: 调用 LLM API
        # response = self.llm_client.chat.completions.create(...)
        # return json.loads(response.choices[0].message.content)
        
        # 临时：返回规则提取结果
        return self._extract_with_rules(text, current_time)
    
    def _extract_with_rules(
        self,
        text: str,
        current_time: datetime
    ) -> Dict[str, Any]:
        """使用规则提取（降级方案）"""
        result = {
            "time": self._extract_time(text, current_time),
            "location": self._extract_location(text),
            "people": self._extract_people(text),
            "emotion": self._extract_emotion(text),
            "tags": self._extract_tags(text),
            "need_questions": []
        }
        
        # 智能询问判断
        result["need_questions"] = self._generate_questions(result, text)
        
        return result
    
    def _extract_time(
        self,
        text: str,
        current_time: datetime
    ) -> Dict[str, Any]:
        """提取时间"""
        # 明确时间词
        time_patterns = {
            r"今天": current_time.date().isoformat(),
            r"昨天": (current_time.date() - timedelta(days=1)).isoformat(),
            r"前天": (current_time.date() - timedelta(days=2)).isoformat(),
            r"(\d{4})-(\d{2})-(\d{2})": None,  # 具体日期
            r"(\d{1,2})月(\d{1,2})[日号]": None,  # 月日
        }
        
        for pattern, value in time_patterns.items():
            match = re.search(pattern, text)
            if match:
                if value:
                    return {
                        "value": value,
                        "source": "extracted",
                        "confidence": 0.9
                    }
                # TODO: 解析具体日期
        
        # 推断时间
        infer_patterns = {
            r"下班[后以]": "18:00",
            r"午饭[时]": "12:00",
            r"晚上": "20:00",
            r"下午": "15:00",
            r"上午": "10:00",
        }
        
        for pattern, time_val in infer_patterns.items():
            if re.search(pattern, text):
                return {
                    "value": f"{current_time.date().isoformat()}T{time_val}:00",
                    "source": "inferred",
                    "confidence": 0.6
                }
        
        # 缺失
        return {
            "value": None,
            "source": "null",
            "confidence": 0.0
        }
    
    def _extract_location(self, text: str) -> Dict[str, Any]:
        """提取地点"""
        # 明确地点
        location_patterns = {
            r"在([^\s，。！？]+店)": 0.9,
            r"在([^\s，。！？]+公司)": 0.9,
            r"去([^\s，。！？]+)": 0.7,
            r"在([^\s，。！？]+)": 0.6,
        }
        
        for pattern, confidence in location_patterns.items():
            match = re.search(pattern, text)
            if match:
                location = match.group(1)
                return {
                    "name": location,
                    "need_confirm": confidence < 0.8,
                    "source": "extracted"
                }
        
        # 缺失
        return {
            "name": None,
            "need_confirm": False,
            "source": "null"
        }
    
    def _extract_people(self, text: str) -> List[Dict[str, Any]]:
        """提取人物"""
        people = []
        
        # 明确人名（中文姓名）
        name_pattern = r"([张王李赵刘陈杨黄周吴徐孙朱马胡郭林何高梁郑罗宋谢唐韩曹许邓萧冯曾程蔡彭潘袁于董余苏叶吕魏蒋田杜丁沈姜姚]"
        name_match = re.search(name_pattern + r"[^\s，。！？]{1,2})", text)
        if name_match:
            people.append({
                "name": name_match.group(1),
                "need_confirm": False,
                "relation": "未知"
            })
        
        # 身份指代
        identity_patterns = {
            r"老板": "上级",
            r"同事": "同事",
            r"同学": "同学",
            r"朋友": "朋友",
            r"家人": "家人",
        }
        
        for pattern, relation in identity_patterns.items():
            if re.search(pattern, text):
                people.append({
                    "name": pattern,
                    "need_confirm": True,
                    "relation": relation
                })
        
        return people
    
    def _extract_emotion(self, text: str) -> Dict[str, Any]:
        """提取情绪"""
        emotion_patterns = {
            r"开心|高兴|快乐|愉快": ("开心", 0.9),
            r"难过|伤心|悲伤": ("难过", 0.9),
            r"焦虑|担心|紧张": ("焦虑", 0.8),
            r"生气|愤怒|烦躁": ("生气", 0.8),
            r"平静|放松|轻松": ("平静", 0.7),
        }
        
        for pattern, (emotion, confidence) in emotion_patterns.items():
            if re.search(pattern, text):
                return {
                    "value": emotion,
                    "confidence": confidence
                }
        
        return {
            "value": "平静",
            "confidence": 0.5
        }
    
    def _extract_tags(self, text: str) -> List[str]:
        """提取标签"""
        tags = []
        
        # 事件类型
        event_patterns = {
            r"工作|开会|加班": "工作",
            r"社交|聚会|聊天": "社交",
            r"休闲|娱乐|游戏": "休闲",
            r"学习|看书|上课": "学习",
            r"运动|健身|跑步": "运动",
        }
        
        for pattern, tag in event_patterns.items():
            if re.search(pattern, text):
                tags.append(tag)
        
        # 地点类型
        location_patterns = {
            r"咖啡|咖啡店": "咖啡店",
            r"餐厅|饭店": "餐厅",
            r"公司|办公室": "办公室",
            r"家": "家",
        }
        
        for pattern, tag in location_patterns.items():
            if re.search(pattern, text):
                tags.append(tag)
        
        return tags[:5]  # 最多 5 个标签
    
    def _generate_questions(
        self,
        result: Dict[str, Any],
        text: str
    ) -> List[str]:
        """生成询问问题"""
        questions = []
        
        # 判断是否为事件记录
        is_event = any(tag in result["tags"] for tag in ["社交", "工作", "学习"])
        
        # 事件记录 + 时间缺失 → 询问
        if is_event and result["time"]["value"] is None:
            questions.append("这件事发生在什么时候？")
        
        # 人物未知 → 询问
        for person in result["people"]:
            if person.get("need_confirm") and person.get("relation") == "未知":
                questions.append(f"这位{person['name']}是谁？")
        
        return questions[:2]  # 最多 2 个问题


# 添加缺失的导入
from datetime import timedelta
