"""
文本处理器
从文本输入中提取结构化信息
"""
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from ..llm.client import get_llm_client
from ..embedding.client import get_embedding_client
from ..models.memory import (
    MemoryCreate, TimeInfo, LocationInfo, PersonInfo,
    EmotionInfo, DurationInfo, TopicInfo
)


class TextProcessor:
    """文本处理器"""
    
    def __init__(self):
        """初始化处理器"""
        self.llm_client = get_llm_client()
        self.embedding_client = get_embedding_client()
    
    async def process(self, text: str, auto_confirm: bool = False) -> Dict[str, Any]:
        """
        处理文本输入
        
        Args:
            text: 输入文本
            auto_confirm: 是否自动确认（无需询问用户）
        
        Returns:
            处理结果，包含：
            - memory_data: 提取的记忆数据
            - need_confirm: 是否需要用户确认
            - confirm_fields: 需要确认的字段
            - questions: 需要询问的问题
        """
        # 1. 提取结构化信息
        extracted = await self._extract_structured_info(text)
        
        if not extracted:
            return {
                "success": False,
                "error": "无法从文本中提取有效信息"
            }
        
        # 2. 生成向量表示
        embedding = self.embedding_client.embed(text)
        
        # 3. 构建记忆数据
        memory_data = self._build_memory_data(text, extracted, embedding)
        
        # 4. 判断是否需要确认或询问
        need_confirm, confirm_fields, questions = self._analyze_extraction(
            extracted, auto_confirm
        )
        
        return {
            "success": True,
            "memory_data": memory_data,
            "need_confirm": need_confirm,
            "confirm_fields": confirm_fields,
            "questions": questions
        }
    
    async def _extract_structured_info(self, text: str) -> Optional[Dict[str, Any]]:
        """
        提取结构化信息
        
        Args:
            text: 输入文本
        
        Returns:
            提取的结构化信息
        """
        prompt = f"""
从以下文本中提取记忆的关键信息，并以 JSON 格式返回：

文本：{text}

提取字段：
- time: 时间信息对象，包含：
  - value: 时间值（ISO 8601 格式，如果无法确定具体时间，使用相对时间如"今天"、"昨天"）
  - source: 时间来源（"explicit" 表示明确提到，"inferred" 表示推断）
  - confidence: 置信度（0-1）
  - original_text: 原文中的时间文本
- location: 地点信息对象，包含：
  - name: 地点名称
  - address: 详细地址（如果有）
  - latitude: 纬度（如果有）
  - longitude: 经度（如果有）
  - need_confirm: 是否需要确认（布尔值）
  - original_text: 原文中的地点文本
- people: 人物列表，每个人物包含：
  - name: 姓名
  - role: 角色（可选，如"朋友"、"同事"等）
  - relationship: 关系（可选）
- emotion: 情绪信息对象，包含：
  - type: 情绪类型（如"开心"、"难过"、"平静"、"焦虑"等）
  - intensity: 强度（1-10）
  - original_text: 原文中的情绪文本
- duration: 持续时间对象，包含：
  - value: 时长数值
  - unit: 单位（"分钟"、"小时"、"天"等）
  - original_text: 原文中的时长文本
- topic: 主题信息对象，包含：
  - main: 主要话题
  - keywords: 关键词列表（3-5个）
- tags: 标签列表（用于分类，如"工作"、"生活"、"学习"等）

注意事项：
1. 如果某个字段无法从文本中提取，请设置为 null
2. 对于不确定的信息，适当降低置信度
3. 尽量保持提取的信息准确和完整
4. 返回纯 JSON 格式，不要包含其他说明文字

返回格式示例：
{{
    "time": {{
        "value": "昨天下午3点",
        "source": "explicit",
        "confidence": 0.9,
        "original_text": "昨天下午三点"
    }},
    "location": {{
        "name": "公司的会议室",
        "address": null,
        "latitude": null,
        "longitude": null,
        "need_confirm": false,
        "original_text": "公司的会议室"
    }},
    "people": [
        {{
            "name": "张三",
            "role": "同事"
        }}
    ],
    "emotion": {{
        "type": "中性",
        "intensity": 5,
        "original_text": null
    }},
    "duration": {{
        "value": 120,
        "unit": "分钟",
        "original_text": "两个小时"
    }},
    "topic": {{
        "main": "项目会议",
        "keywords": ["会议", "项目", "讨论"]
    }},
    "tags": ["工作"]
}}
        """
        
        result = self.llm_client.extract_json(prompt)
        return result
    
    def _build_memory_data(
        self,
        text: str,
        extracted: Dict[str, Any],
        embedding: Optional[list]
    ) -> MemoryCreate:
        """
        构建记忆数据对象
        
        Args:
            text: 原始文本
            extracted: 提取的结构化信息
            embedding: 向量表示
        
        Returns:
            MemoryCreate 对象
        """
        # 构建时间信息
        time_info = None
        if extracted.get("time"):
            time_data = extracted["time"]
            # 映射 time_source 值（数据库只接受 extracted/inferred/metadata）
            time_source = time_data.get("source", "inferred")
            if time_source == "explicit":
                time_source = "extracted"
            
            time_info = TimeInfo(
                value=self._parse_time_value(time_data.get("value")),
                source=time_source,
                confidence=time_data.get("confidence", 0.5),
                original_text=time_data.get("original_text")
            )
        
        # 构建位置信息
        location_info = None
        if extracted.get("location"):
            loc_data = extracted["location"]
            loc_name = loc_data.get("name")
            if loc_name:  # 只添加有名称的地点
                location_info = LocationInfo(
                    name=loc_name,
                    address=loc_data.get("address"),
                    latitude=loc_data.get("latitude"),
                    longitude=loc_data.get("longitude"),
                    need_confirm=loc_data.get("need_confirm", False),
                    original_text=loc_data.get("original_text")
                )
        
        # 构建人物信息
        people_info = None
        if extracted.get("people"):
            people_list = []
            for p in extracted["people"]:
                name = p.get("name")
                if name:  # 只添加有名字的人物
                    people_list.append(PersonInfo(
                        name=name,
                        role=p.get("role"),
                        relationship=p.get("relationship")
                    ))
            if people_list:
                people_info = people_list
        
        # 构建情绪信息
        emotion_info = None
        if extracted.get("emotion"):
            emo_data = extracted["emotion"]
            emotion_info = EmotionInfo(
                type=emo_data.get("type", "中性"),
                intensity=emo_data.get("intensity", 5),
                original_text=emo_data.get("original_text")
            )
        
        # 构建时长信息
        duration_info = None
        if extracted.get("duration"):
            dur_data = extracted["duration"]
            duration_info = DurationInfo(
                value=dur_data.get("value"),
                unit=dur_data.get("unit"),
                original_text=dur_data.get("original_text")
            )
        
        # 构建主题信息
        topic_info = None
        if extracted.get("topic"):
            topic_data = extracted["topic"]
            topic_info = TopicInfo(
                main=topic_data.get("main"),
                keywords=topic_data.get("keywords", [])
            )
        
        # 构建记忆对象
        memory_data = MemoryCreate(
            content=text,
            input_type="text",
            time=time_info,
            location=location_info,
            people=people_info,
            emotion=emotion_info,
            tags=extracted.get("tags"),
            duration=duration_info,
            topic=topic_info,
            embedding=embedding
        )
        
        return memory_data
    
    def _analyze_extraction(
        self,
        extracted: Dict[str, Any],
        auto_confirm: bool
    ) -> tuple:
        """
        分析提取结果，判断是否需要确认或询问
        
        Args:
            extracted: 提取的结构化信息
            auto_confirm: 是否自动确认
        
        Returns:
            (need_confirm, confirm_fields, questions)
        """
        if auto_confirm:
            return False, [], []
        
        confirm_fields = []
        questions = []
        
        # 检查时间信息
        if extracted.get("time"):
            time_data = extracted["time"]
            if time_data.get("confidence", 0) < 0.7:
                confirm_fields.append("time")
                questions.append({
                    "field": "time",
                    "question": f"确认一下时间是否正确：{time_data.get('value')}？",
                    "original_text": time_data.get("original_text")
                })
        else:
            questions.append({
                "field": "time",
                "question": "这件事情是什么时候发生的？"
            })
        
        # 检查位置信息
        if extracted.get("location"):
            loc_data = extracted["location"]
            if loc_data.get("need_confirm"):
                confirm_fields.append("location")
                questions.append({
                    "field": "location",
                    "question": f"确认一下地点：{loc_data.get('name')}？"
                })
        
        # 检查人物信息
        if not extracted.get("people"):
            # 如果文本中提到人，但未提取到，可能需要询问
            pass
        
        # 检查情绪信息
        if not extracted.get("emotion"):
            questions.append({
                "field": "emotion",
                "question": "你当时的心情怎么样？"
            })
        
        need_confirm = len(confirm_fields) > 0
        
        return need_confirm, confirm_fields, questions
    
    def _parse_time_value(self, value: Optional[str]) -> Optional[datetime]:
        """
        解析时间值
        
        Args:
            value: 时间字符串
        
        Returns:
            datetime 对象，解析失败返回 None
        """
        if not value:
            return None
        
        # TODO: 实现更完善的时间解析
        # 这里先简单处理相对时间
        relative_times = {
            "今天": datetime.now().date(),
            "昨天": (datetime.now() - timedelta(days=1)).date(),
            "前天": (datetime.now() - timedelta(days=2)).date(),
            "明天": (datetime.now() + timedelta(days=1)).date(),
            "后天": (datetime.now() + timedelta(days=2)).date(),
        }
        
        for key, date_val in relative_times.items():
            if key in value:
                # 尝试提取时间部分
                # TODO: 实现时间提取逻辑
                return datetime.combine(date_val, datetime.min.time())
        
        # 尝试解析 ISO 格式
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except:
            return None
    
    async def parse_query(self, query: str) -> Dict[str, Any]:
        """
        使用大模型解析自然语言查询
        
        Args:
            query: 自然语言查询文本
        
        Returns:
            解析结果，包含：
            - time_range: 时间范围 {start, end}
            - location: 地点
            - people: 人物列表
            - emotion: 情绪
            - tags: 标签列表
            - keywords: 关键词列表
        """
        from datetime import datetime, timedelta
        
        now = datetime.now()
        
        prompt = f"""
从以下自然语言查询中提取结构化信息，用于搜索记忆：

查询：{query}

当前时间：{now.strftime("%Y-%m-%d %H:%M:%S")}

请提取以下信息：
1. time_range: 时间范围
   - start: 开始时间（ISO 8601格式）
   - end: 结束时间（ISO 8601格式）
   - original_text: 原文中的时间表述

2. location: 地点名称

3. people: 人物列表

4. emotion: 情绪类型

5. tags: 标签列表（如：社交、工作、学习等）

6. keywords: 关键词列表

注意事项：
- 如果某个字段无法提取，设为 null
- 时间范围要准确计算（如"上周"要计算具体日期范围）
- 人物名称要准确提取（如"老同学"保留原词）
- 返回纯 JSON 格式

返回格式示例：
{{
    "time_range": {{
        "start": "2026-03-12T00:00:00",
        "end": "2026-03-19T23:59:59",
        "original_text": "最近"
    }},
    "location": "咖啡店",
    "people": ["老同学"],
    "emotion": null,
    "tags": ["社交"],
    "keywords": ["见面", "咖啡店", "老同学"]
}}
        """
        
        result = self.llm_client.extract_json(prompt)
        
        if not result:
            return {
                "time_range": None,
                "location": None,
                "people": [],
                "emotion": None,
                "tags": [],
                "keywords": []
            }
        
        # 处理时间范围
        time_range = None
        if result.get("time_range"):
            tr = result["time_range"]
            if tr.get("start") and tr.get("end"):
                try:
                    time_range = {
                        "start": datetime.fromisoformat(tr["start"].replace("Z", "+00:00")),
                        "end": datetime.fromisoformat(tr["end"].replace("Z", "+00:00")),
                        "original_text": tr.get("original_text")
                    }
                except:
                    pass
        
        return {
            "time_range": time_range,
            "location": result.get("location"),
            "people": result.get("people", []),
            "emotion": result.get("emotion"),
            "tags": result.get("tags", []),
            "keywords": result.get("keywords", [])
        }


# 全局文本处理器实例
text_processor: Optional[TextProcessor] = None


def get_text_processor() -> TextProcessor:
    """获取文本处理器实例"""
    global text_processor
    if text_processor is None:
        text_processor = TextProcessor()
    return text_processor
