"""
记忆管理服务
"""
import uuid
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from ..database import db
from ..models.memory import Memory, MemoryCreate, MemoryUpdate
from ..processors.text_processor import get_text_processor


class MemoryService:
    """记忆管理服务"""
    
    async def process_text_input(
        self,
        text: str,
        auto_confirm: bool = False
    ) -> Dict[str, Any]:
        """
        处理文本输入
        
        Args:
            text: 输入文本
            auto_confirm: 是否自动确认（无需询问用户）
        
        Returns:
            处理结果，包含：
            - success: 是否成功
            - memory_id: 记忆 ID（如果已创建）
            - memory_data: 记忆数据
            - need_confirm: 是否需要用户确认
            - confirm_fields: 需要确认的字段
            - questions: 需要询问的问题
        """
        # 获取文本处理器
        processor = get_text_processor()
        
        # 处理文本
        result = await processor.process(text, auto_confirm)
        
        if not result["success"]:
            return result
        
        # 如果不需要确认或自动确认，直接创建记忆
        if not result["need_confirm"] or auto_confirm:
            memory_id = await self.create(result["memory_data"])
            result["memory_id"] = memory_id
        
        return result
    
    async def create(self, memory_data: MemoryCreate) -> str:
        """
        创建记忆
        
        Args:
            memory_data: 记忆创建数据
        
        Returns:
            记忆 ID
        """
        # 生成记忆 ID (使用 UUID)
        memory_id = str(uuid.uuid4())
        
        # 准备数据
        now = datetime.utcnow()
        
        # 插入数据库
        await db.execute("""
            INSERT INTO memories (
                id, content, input_type, created_at,
                time_value, time_source, time_confidence, time_original_text,
                location_name, location_address, location_latitude, location_longitude,
                location_need_confirm, location_original_text,
                people, emotion, tags, duration, topic, attachments, embedding,
                access_count, importance_score, status
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6, $7, $8,
                $9, $10, $11, $12, $13, $14,
                $15, $16, $17, $18, $19, $20, $21,
                $22, $23, $24
            )
        """,
            memory_id,
            memory_data.content,
            memory_data.input_type,
            now,
            memory_data.time.value if memory_data.time else None,
            memory_data.time.source if memory_data.time else None,
            memory_data.time.confidence if memory_data.time else None,
            memory_data.time.original_text if memory_data.time else None,
            memory_data.location.name if memory_data.location else None,
            memory_data.location.address if memory_data.location else None,
            memory_data.location.latitude if memory_data.location else None,
            memory_data.location.longitude if memory_data.location else None,
            memory_data.location.need_confirm if memory_data.location else False,
            memory_data.location.original_text if memory_data.location else None,
            json.dumps([p.model_dump() for p in memory_data.people]) if memory_data.people else None,
            json.dumps(memory_data.emotion.model_dump()) if memory_data.emotion else None,
            json.dumps(memory_data.tags) if memory_data.tags else None,
            json.dumps(memory_data.duration.model_dump()) if memory_data.duration else None,
            json.dumps(memory_data.topic.model_dump()) if memory_data.topic else None,
            json.dumps([a.model_dump() for a in memory_data.attachments]) if memory_data.attachments else None,
            # 向量数据：转换为字符串格式
            "[" + ",".join(map(str, memory_data.embedding)) + "]" if memory_data.embedding else None,
            0,
            0.5,
            "active"
        )
        
        return memory_id
    
    async def get(self, memory_id: str) -> Optional[Memory]:
        """
        获取记忆
        
        Args:
            memory_id: 记忆 ID
        
        Returns:
            记忆数据，不存在返回 None
        """
        row = await db.fetchrow("""
            SELECT * FROM memories WHERE id = $1 AND status != 'deleted'
        """, memory_id)
        
        if not row:
            return None
        
        return self._row_to_memory(row)
    
    async def update(self, memory_id: str, updates: MemoryUpdate) -> bool:
        """
        更新记忆
        
        Args:
            memory_id: 记忆 ID
            updates: 更新数据
        
        Returns:
            是否成功
        """
        # 构建更新 SQL
        update_fields = []
        update_values = []
        param_count = 1
        
        if updates.content is not None:
            update_fields.append(f"content = ${param_count}")
            update_values.append(updates.content)
            param_count += 1
        
        if updates.time is not None:
            if updates.time.value is not None:
                update_fields.append(f"time_value = ${param_count}")
                update_values.append(updates.time.value)
                param_count += 1
            if updates.time.source is not None:
                update_fields.append(f"time_source = ${param_count}")
                update_values.append(updates.time.source)
                param_count += 1
            if updates.time.confidence is not None:
                update_fields.append(f"time_confidence = ${param_count}")
                update_values.append(updates.time.confidence)
                param_count += 1
            if updates.time.original_text is not None:
                update_fields.append(f"time_original_text = ${param_count}")
                update_values.append(updates.time.original_text)
                param_count += 1
        
        if updates.location is not None:
            if updates.location.name is not None:
                update_fields.append(f"location_name = ${param_count}")
                update_values.append(updates.location.name)
                param_count += 1
            if updates.location.address is not None:
                update_fields.append(f"location_address = ${param_count}")
                update_values.append(updates.location.address)
                param_count += 1
            if updates.location.latitude is not None:
                update_fields.append(f"location_latitude = ${param_count}")
                update_values.append(updates.location.latitude)
                param_count += 1
            if updates.location.longitude is not None:
                update_fields.append(f"location_longitude = ${param_count}")
                update_values.append(updates.location.longitude)
                param_count += 1
            if updates.location.need_confirm is not None:
                update_fields.append(f"location_need_confirm = ${param_count}")
                update_values.append(updates.location.need_confirm)
                param_count += 1
            if updates.location.original_text is not None:
                update_fields.append(f"location_original_text = ${param_count}")
                update_values.append(updates.location.original_text)
                param_count += 1
        
        if updates.people is not None:
            update_fields.append(f"people = ${param_count}")
            update_values.append(json.dumps([p.model_dump() for p in updates.people]))
            param_count += 1
        
        if updates.emotion is not None:
            update_fields.append(f"emotion = ${param_count}")
            update_values.append(json.dumps(updates.emotion.model_dump()))
            param_count += 1
        
        if updates.tags is not None:
            update_fields.append(f"tags = ${param_count}")
            update_values.append(json.dumps(updates.tags))
            param_count += 1
        
        if updates.importance_score is not None:
            update_fields.append(f"importance_score = ${param_count}")
            update_values.append(updates.importance_score)
            param_count += 1
        
        if updates.status is not None:
            update_fields.append(f"status = ${param_count}")
            update_values.append(updates.status)
            param_count += 1
        
        if not update_fields:
            return False
        
        # 添加 memory_id 参数
        update_values.append(memory_id)
        
        # 执行更新
        sql = f"""
            UPDATE memories 
            SET {', '.join(update_fields)}, updated_at = NOW()
            WHERE id = ${param_count} AND status != 'deleted'
        """
        
        result = await db.execute(sql, *update_values)
        
        return "UPDATE 1" in result
    
    async def delete(self, memory_id: str) -> bool:
        """
        删除记忆（软删除）
        
        Args:
            memory_id: 记忆 ID
        
        Returns:
            是否成功
        """
        result = await db.execute("""
            UPDATE memories 
            SET status = 'deleted', updated_at = NOW()
            WHERE id = $1
        """, memory_id)
        
        return "UPDATE 1" in result
    
    async def list(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str = "active"
    ) -> List[Memory]:
        """
        列出记忆
        
        Args:
            limit: 数量限制
            offset: 偏移量
            status: 状态过滤
        
        Returns:
            记忆列表
        """
        rows = await db.fetch("""
            SELECT * FROM memories
            WHERE status = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
        """, status, limit, offset)
        
        return [self._row_to_memory(row) for row in rows]
    
    async def search_by_time(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 50
    ) -> List[Memory]:
        """
        按时间范围搜索记忆
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            limit: 数量限制
        
        Returns:
            记忆列表
        """
        rows = await db.fetch("""
            SELECT * FROM memories
            WHERE time_value >= $1 AND time_value <= $2
            AND status = 'active'
            ORDER BY time_value DESC
            LIMIT $3
        """, start_time, end_time, limit)
        
        return [self._row_to_memory(row) for row in rows]
    
    async def search_by_location(
        self,
        location_name: str,
        limit: int = 50
    ) -> List[Memory]:
        """
        按位置搜索记忆
        
        Args:
            location_name: 位置名称
            limit: 数量限制
        
        Returns:
            记忆列表
        """
        rows = await db.fetch("""
            SELECT * FROM memories
            WHERE to_tsvector('simple', location_name) @@ to_tsquery('simple', $1)
            AND status = 'active'
            ORDER BY created_at DESC
            LIMIT $2
        """, location_name, limit)
        
        return [self._row_to_memory(row) for row in rows]
    
    async def search_by_person(
        self,
        person_name: str,
        limit: int = 50
    ) -> List[Memory]:
        """
        按人物搜索记忆
        
        Args:
            person_name: 人物名称
            limit: 数量限制
        
        Returns:
            记忆列表
        """
        rows = await db.fetch("""
            SELECT * FROM memories
            WHERE people @> $1::jsonb
            AND status = 'active'
            ORDER BY created_at DESC
            LIMIT $2
        """, json.dumps([{"name": person_name}]), limit)
        
        return [self._row_to_memory(row) for row in rows]
    
    def _row_to_memory(self, row: Dict[str, Any]) -> Memory:
        """将数据库行转换为 Memory 对象"""
        from ..models.memory import (
            TimeInfo, LocationInfo, PersonInfo, EmotionInfo,
            DurationInfo, TopicInfo, Attachment
        )
        
        # 解析 JSON 字段
        
        # 处理 embedding 字段（从字符串转换为列表）
        embedding_data = row.get('embedding')
        if embedding_data and isinstance(embedding_data, str):
            # 解析向量字符串 "[0.1,0.2,...]" 为列表
            embedding_data = json.loads(embedding_data)
        
        people_data = row.get('people')
        people = None
        if people_data:
            if isinstance(people_data, str):
                people_data = json.loads(people_data)
            people = [PersonInfo(**p) for p in people_data]
        
        emotion_data = row.get('emotion')
        emotion = None
        if emotion_data:
            if isinstance(emotion_data, str):
                emotion_data = json.loads(emotion_data)
            emotion = EmotionInfo(**emotion_data)
        
        tags_data = row.get('tags')
        tags = None
        if tags_data:
            if isinstance(tags_data, str):
                tags_data = json.loads(tags_data)
            tags = tags_data
        
        duration_data = row.get('duration')
        duration = None
        if duration_data:
            if isinstance(duration_data, str):
                duration_data = json.loads(duration_data)
            duration = DurationInfo(**duration_data)
        
        topic_data = row.get('topic')
        topic = None
        if topic_data:
            if isinstance(topic_data, str):
                topic_data = json.loads(topic_data)
            topic = TopicInfo(**topic_data)
        
        attachments_data = row.get('attachments')
        attachments = None
        if attachments_data:
            if isinstance(attachments_data, str):
                attachments_data = json.loads(attachments_data)
            attachments = [Attachment(**a) for a in attachments_data]
        
        # 构建时间信息
        time_info = None
        if row.get('time_value'):
            time_info = TimeInfo(
                value=row['time_value'],
                source=row.get('time_source'),
                confidence=row.get('time_confidence'),
                original_text=row.get('time_original_text')
            )
        
        # 构建位置信息
        location_info = None
        if row.get('location_name'):
            location_info = LocationInfo(
                name=row['location_name'],
                address=row.get('location_address'),
                latitude=row.get('location_latitude'),
                longitude=row.get('location_longitude'),
                need_confirm=row.get('location_need_confirm', False),
                original_text=row.get('location_original_text')
            )
        
        return Memory(
            id=str(row['id']),
            content=row['content'],
            input_type=row['input_type'],
            created_at=row['created_at'],
            updated_at=row.get('updated_at'),
            time=time_info,
            location=location_info,
            people=people,
            emotion=emotion,
            tags=tags,
            duration=duration,
            topic=topic,
            attachments=attachments,
            embedding=embedding_data,
            access_count=row.get('access_count', 0),
            last_accessed_at=row.get('last_accessed_at'),
            importance_score=row.get('importance_score', 0.5),
            status=row.get('status', 'active')
        )


# 全局记忆服务实例
memory_service = MemoryService()
