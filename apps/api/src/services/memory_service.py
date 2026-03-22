"""
记忆管理服务
"""
import uuid
import json
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from ..database import db
from ..models.memory import Memory, MemoryCreate, MemoryUpdate
from ..embedding.client import get_embedding_client
from .graph_builder_service import get_graph_builder_service
from .embedding_cache import get_embedding_cache

from .memory_extraction_service import get_memory_extraction_service

# 导入分块处理方法
from .memory_chunk_methods import (
    _create_with_chunks, 
    _split_into_chunks, 
    _deduplicate_memories,
    _deduplicate_memories_by_content, 
    _extract_keywords,
    _calculate_keyword_similarity
)


class MemoryService:
    """记忆管理服务"""
    
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
    
    async def create_from_file(
        self,
        content: str,
        file_info: Dict[str, Any],
        segments: List[Dict[str, Any]],
        overall_summary: Optional[str] = None,
        key_events: Optional[List[str]] = None
    ) -> str:
        """
        从文件创建记忆
        
        Args:
            content: 文件内容
            file_info: 文件信息
            segments: 分段列表
            overall_summary: 整体摘要
            key_events: 关键事件
        
        Returns:
            主记忆 ID
        """
        import json
        from ..embedding.client import get_embedding_client
        
        # 1. 生成主记忆的向量
        embedding_client = get_embedding_client()
        # 只对前 5000 字符生成向量，避免 token 限制
        embedding = embedding_client.embed(content[:5000])
        
        # 2. 创建主记忆
        memory_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        await db.execute("""
            INSERT INTO memories (
                id, content, input_type, created_at,
                embedding, status
            ) VALUES ($1, $2, $3, $4, $5, $6)
        """,
            memory_id,
            content,
            "file",
            now,
            "[" + ",".join(map(str, embedding)) + "]" if embedding else None,
            "active"
        )
        
        # 3. 为每个分段生成向量并创建子记忆
        for segment in segments:
            seg_content = segment.get("content", "")
            seg_embedding = embedding_client.embed(seg_content[:2000]) if seg_content else None
            
            # 提取时间范围
            time_value = None
            if segment.get("time_range"):
                time_range = segment["time_range"]
                if time_range.get("start"):
                    try:
                        time_value = datetime.fromisoformat(time_range["start"])
                    except:
                        pass
            
            # 存储分段摘要
            seg_id = str(uuid.uuid4())  # 为每个分段生成独立的 UUID
            await db.execute("""
                INSERT INTO memories (
                    id, content, input_type, created_at,
                    time_value, embedding, status
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
                seg_id,
                seg_content,
                "segment",
                now,
                time_value,
                "[" + ",".join(map(str, seg_embedding)) + "]" if seg_embedding else None,
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
    
    async def create_memory_with_graph_v2(
        self,
        content: str,
        user_id: str,
        enable_graph: bool = True,
        enable_confirmation: bool = False
    ) -> Dict[str, Any]:
        """
        创建记忆（Function Calling 方式 - 新版本）
        
        流程：
        1. 使用 Function Calling 提取记忆
        2. 存储记忆到 memories 表
        3. 存储实体到 entities 表
        4. 存储关系到 relations 表
        
        Args:
            content: 记忆内容
            user_id: 用户 ID
            enable_graph: 是否启用图谱构建（默认 True）
            enable_confirmation: 是否启用智能确认（默认 False）
        
        Returns:
            创建结果，包含：
            - memory_id: 记忆 ID
            - graph: 图谱信息（如果启用）
            - extracted: 提取的结构化信息
        """
        # 确保用户存在
        await db.init_user(user_id)
        
        # 设置当前用户 schema
        db.set_current_user(user_id)
        
        # 检查文本长度，决定是否需要分块
        content_chars = len(content)
        MAX_CHARS_PER_CHUNK = 5000
        
        if content_chars > MAX_CHARS_PER_CHUNK:
            print(f"⚠️ 文本过长（{content_chars} 字符），启动分块策略")
            return await self._create_with_chunks(content, user_id, enable_graph)
        
        print(f"⚡ 启动处理：Function Calling 提取 + 向量生成")
        
        # ⚡ 并行执行：记忆提取 + 向量生成
        extraction_task = self._extract_memories_v2(content)
        embedding_task = self._generate_embedding(content)
        
        # 等待并行任务完成
        extraction_result, embedding = await asyncio.gather(
            extraction_task, 
            embedding_task,
            return_exceptions=True
        )
        
        # ⚠️ 检查是否为异常
        if isinstance(extraction_result, Exception):
            print(f"⚠️ 记忆提取失败: {extraction_result}")
            extraction_result = None
        if isinstance(embedding, Exception):
            print(f"⚠️ 向量生成失败: {embedding}")
            embedding = None
        
        # ⚠️ 检查提取结果
        if not extraction_result or not extraction_result.get("success"):
            # 提取失败，降级为简单存储
            print(f"⚠️ 记忆提取失败，降级为简单存储")
            if embedding is None:
                embedding = await self._generate_embedding(content)
            memory_id = await self._store_memory(content, embedding, user_id)
            return {
                "memory_id": memory_id,
                "graph": None,
                "extracted": None
            }
        
        memories = extraction_result.get("memories", [])
        
        if not memories:
            # 没有提取到记忆，降级为简单存储
            print(f"⚠️ 未提取到记忆，降级为简单存储")
            if embedding is None:
                embedding = await self._generate_embedding(content)
            memory_id = await self._store_memory(content, embedding, user_id)
            return {
                "memory_id": memory_id,
                "graph": None,
                "extracted": None
            }
        
        print(f"✅ 记忆提取成功：{len(memories)} 条记忆")
        
        # 2. 存储每条记忆
        memory_ids = []
        graph_results = []
        
        for memory in memories:
            memory_content = memory.get("content", "")
            if not memory_content.strip():
                continue
            
            # 提取结构化信息
            time_info = memory.get("time", {})
            location_info = memory.get("location", {})
            people = memory.get("people", [])
            entities = memory.get("entities", [])
            relations = memory.get("relations", [])
            tags = memory.get("tags", [])
            emotion = memory.get("emotion", {})
            importance = memory.get("importance", 0.5)
            
            # 提取时间
            time_value = time_info.get("value") if isinstance(time_info, dict) else None
            time_original = time_info.get("original_text") if isinstance(time_info, dict) else None
            
            # 转换字符串时间为 datetime 对象
            time_value = self._parse_time_value_v2(time_value)
            
            # 提取地点
            location_name = location_info.get("name") if isinstance(location_info, dict) else None
            
            # 存储记忆
            memory_id = str(uuid.uuid4())
            now = datetime.utcnow()
            
            await db.execute("""
                INSERT INTO memories (
                    id, content, input_type, created_at,
                    time_value, time_original_text, location_name, people,
                    tags, emotion, importance_score,
                    embedding, status
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
                memory_id,
                memory_content,
                "text",
                now,
                time_value,
                time_original,
                location_name,
                json.dumps(people) if people else None,
                json.dumps(tags) if tags else None,
                json.dumps(emotion) if emotion else None,
                importance,
                "[" + ",".join(map(str, embedding)) + "]" if embedding else None,
                "active"
            )
            
            memory_ids.append(memory_id)
            
            # 为每条记忆分别存储图谱
            if enable_graph and (entities or relations):
                # 去重当前记忆的实体和关系
                unique_entities = self._deduplicate_entities_v2(entities)
                unique_relations = self._deduplicate_relations_v2(relations)
                
                # 存储实体和关系，关联到当前记忆
                graph_result = await self._store_graph_v2(
                    entities=unique_entities,
                    relations=unique_relations,
                    user_id=user_id,
                    memory_id=memory_id
                )
                graph_results.append(graph_result)
        
        # 返回结果
        return {
            "memory_id": memory_ids[0] if memory_ids else None,
            "graph": graph_results[0] if graph_results else None,
            "extracted": {
                "memories": len(memories),
                "memory_ids": memory_ids
            }
        }
    
    async def _extract_memories_v2(self, content: str) -> Dict[str, Any]:
        """
        提取记忆（调用记忆提取服务）
        
        Args:
            content: 输入文本
        
        Returns:
            提取结果
        """
        extraction_service = get_memory_extraction_service()
        return await extraction_service.extract_memories(content)
    
    async def _store_graph_v2(
        self,
        entities: List[Dict[str, Any]],
        relations: List[Dict[str, Any]],
        user_id: str,
        memory_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        存储图谱（新版本）
        
        Args:
            entities: 实体列表
            relations: 关系列表
            user_id: 用户 ID
            memory_id: 记忆 ID
        
        Returns:
            图谱结果
        """
        if not entities:
            return {
                "entities": [],
                "relations": [],
                "entity_count": 0,
                "relation_count": 0,
                "status": "no_entities"
            }
        
        # 存储实体
        entity_ids = {}
        for entity in entities:
            entity_name = entity.get("name")
            entity_type = entity.get("type", "unknown")
            confidence = entity.get("confidence", 0.8)
            
            # ⚠️ 不存储"我"实体
            if entity_name == "我":
                continue
            
            entity_id = await self._upsert_entity_v2(
                name=entity_name,
                entity_type=entity_type,
                user_id=user_id,
                confidence=confidence
            )
            
            if entity_id:
                entity_ids[entity_name] = entity_id
                
                # 创建记忆-实体关联
                if memory_id:
                    try:
                        # 检查是否已存在
                        existing = await db.fetchrow(
                            """
                            SELECT id FROM memory_entities 
                            WHERE memory_id = $1 AND entity_id = $2
                            """,
                            memory_id, entity_id
                        )
                        
                        if not existing:
                            await db.execute(
                                """
                                INSERT INTO memory_entities (memory_id, entity_id, mention_context)
                                VALUES ($1, $2, $3)
                                """,
                                memory_id, entity_id, None
                            )
                    except Exception as e:
                        print(f"创建记忆-实体关联失败: {e}")
        
        # 存储关系
        stored_relations = []
        for relation in relations:
            source = relation.get("source")
            target = relation.get("target")
            relation_type = relation.get("relation_type")
            confidence = relation.get("confidence", 0.8)
            
            # ⚠️ 检查 target 不能是"我"
            if target == "我":
                continue
            
            success = await self._upsert_relation_v2(
                source=source,
                target=target,
                relation_type=relation_type,
                confidence=confidence,
                user_id=user_id,
                entity_ids=entity_ids
            )
            
            if success:
                stored_relations.append(relation)
        
        return {
            "entities": entities,
            "relations": stored_relations,
            "entity_count": len(entities),
            "relation_count": len(stored_relations),
            "status": "success"
        }
    
    async def _upsert_entity_v2(
        self,
        name: str,
        entity_type: str,
        user_id: str,
        confidence: float = 0.8
    ) -> Optional[str]:
        """
        存储或更新实体
        
        Args:
            name: 实体名称
            entity_type: 实体类型
            user_id: 用户 ID
            confidence: 置信度
        
        Returns:
            实体 ID
        """
        try:
            # 检查实体是否存在
            existing = await db.fetchrow(
                """
                SELECT id FROM entities 
                WHERE name = $1 AND type = $2 AND user_id = $3
                """,
                name, entity_type, user_id
            )
            
            if existing:
                # 更新提及次数和置信度
                await db.execute(
                    """
                    UPDATE entities 
                    SET confidence = GREATEST(confidence, $1),
                        mention_count = mention_count + 1,
                        last_mentioned_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $2
                    """,
                    confidence, str(existing["id"])
                )
                return str(existing["id"])
            else:
                # 创建新实体
                result = await db.fetchrow(
                    """
                    INSERT INTO entities (name, type, confidence, user_id)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    name, entity_type, confidence, user_id
                )
                return str(result["id"]) if result else None
                
        except Exception as e:
            print(f"存储实体失败: {e}")
            return None
    
    async def _upsert_relation_v2(
        self,
        source: str,
        target: str,
        relation_type: str,
        confidence: float,
        user_id: str,
        entity_ids: Dict[str, str]
    ) -> bool:
        """
        存储或更新关系（新版本）
        
        Args:
            source: 源实体名称（可以是"我"）
            target: 目标实体名称（不能是"我"）
            relation_type: 关系类型
            confidence: 置信度
            user_id: 用户 ID
            entity_ids: 实体 ID 映射
        
        Returns:
            是否成功
        """
        try:
            # 获取实体 ID
            # ⚠️ 如果 source == "我"，使用特殊标识（NULL 或 user_id）
            if source == "我":
                source_id = None  # 使用 NULL 表示"我"（记忆所有者）
            else:
                source_id = entity_ids.get(source)
                if not source_id:
                    # 实体不存在，先创建
                    source_id = await self._upsert_entity_v2(
                        name=source,
                        entity_type="unknown",  # 从关系推断类型
                        user_id=user_id,
                        confidence=confidence
                    )
            
            # target 必须是有效实体
            target_id = entity_ids.get(target)
            if not target_id:
                # 实体不存在，先创建
                target_id = await self._upsert_entity_v2(
                    name=target,
                    entity_type="unknown",
                    user_id=user_id,
                    confidence=confidence
                )
            
            if not target_id:
                return False
            
            # 检查关系是否存在
            if source_id:
                existing = await db.fetchrow(
                    """
                    SELECT id FROM relations 
                    WHERE from_entity_id = $1 AND to_entity_id = $2 AND relation_type = $3
                    """,
                    str(source_id), str(target_id), relation_type
                )
            else:
                # source 是"我"（NULL）
                existing = await db.fetchrow(
                    """
                    SELECT id FROM relations 
                    WHERE from_entity_id IS NULL AND to_entity_id = $1 AND relation_type = $2
                    """,
                    str(target_id), relation_type
                )
            
            if existing:
                # 更新权重
                await db.execute(
                    """
                    UPDATE relations 
                    SET weight = LEAST(weight + 0.1, 1.0),
                        confidence = GREATEST(confidence, $1),
                        updated_at = NOW()
                    WHERE id = $2
                    """,
                    confidence, str(existing["id"])
                )
            else:
                # 创建新关系
                await db.execute(
                    """
                    INSERT INTO relations (from_entity_id, to_entity_id, relation_type, weight, confidence, user_id)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    str(source_id) if source_id else None,
                    str(target_id),
                    relation_type,
                    confidence,
                    confidence,
                    user_id
                )
            
            return True
            
        except Exception as e:
            print(f"存储关系失败: {e}")
            return False
    
    def _parse_time_value_v2(self, time_value: Any) -> Optional[datetime]:
        """
        解析时间值
        
        Args:
            time_value: 时间值（字符串或 None）
        
        Returns:
            datetime 对象或 None（带 UTC 时区）
        """
        if not time_value:
            return None
        
        if isinstance(time_value, str):
            time_value = time_value.strip()
            if not time_value:
                return None
            
            try:
                # 解析时间字符串
                dt = datetime.fromisoformat(time_value.replace('Z', '+00:00'))
                
                # 如果没有时区，添加 UTC 时区
                # 这样 PostgreSQL 就不会把它当作本地时间转换
                if dt.tzinfo is None:
                    from datetime import timezone
                    dt = dt.replace(tzinfo=timezone.utc)
                
                return dt
            except (ValueError, AttributeError):
                return None
        
        return None
    
    def _deduplicate_entities_v2(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """实体去重"""
        seen = {}
        result = []
        for entity in entities:
            key = f"{entity.get('name')}_{entity.get('type')}"
            if key not in seen:
                seen[key] = entity
                result.append(entity)
        return result
    
    def _deduplicate_relations_v2(self, relations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """关系去重"""
        seen = {}
        result = []
        for relation in relations:
            key = f"{relation.get('source')}_{relation.get('relation_type')}_{relation.get('target')}"
            if key not in seen:
                seen[key] = relation
                result.append(relation)
        return result
    
    async def _generate_embedding(self, content: str) -> Optional[List[float]]:
        """
        生成内容的向量表示
        
        Args:
            content: 文本内容
        
        Returns:
            向量列表，失败返回 None
        """
        try:
            embedding_client = get_embedding_client()
            # 只对前 5000 字符生成向量，避免 token 限制
            embedding = embedding_client.embed(content[:5000])
            return embedding
        except Exception as e:
            print(f"生成 embedding 失败: {e}")
            return None
    
    async def _store_memory(
        self,
        content: str,
        embedding: Optional[List[float]],
        user_id: str
    ) -> str:
        """
        存储记忆到数据库
        
        Args:
            content: 记忆内容
            embedding: 向量表示
            user_id: 用户 ID
        
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
                embedding, status
            ) VALUES ($1, $2, $3, $4, $5, $6)
        """,
            memory_id,
            content,
            "text",
            now,
            "[" + ",".join(map(str, embedding)) + "]" if embedding else None,
            "active"
        )
        
        return memory_id
    
    async def batch_create_memories(
        self,
        contents: List[str],
        user_id: str,
        enable_graph: bool = True
    ) -> Dict[str, Any]:
        """
        批量创建记忆（减少数据库连接次数）
        
        Args:
            contents: 记忆内容列表
            user_id: 用户 ID
            enable_graph: 是否启用图谱构建（默认 True）
        
        Returns:
            创建结果，包含：
            - memory_ids: 记忆 ID 列表
            - graph_results: 图谱结果列表
            - stats: 统计信息
        """
        import time
        
        start_time = time.time()
        
        # 1. 批量生成 embedding（带缓存）
        embeddings = []
        for content in contents:
            embedding = await self._generate_embedding(content)
            embeddings.append(embedding)
        
        # 2. 批量存储记忆
        memory_ids = []
        now = datetime.utcnow()
        
        # 准备批量插入数据
        values = []
        for i, (content, embedding) in enumerate(zip(contents, embeddings)):
            memory_id = str(uuid.uuid4())
            memory_ids.append(memory_id)
            values.append((
                memory_id,
                content,
                "text",
                now,
                "[" + ",".join(map(str, embedding)) + "]" if embedding else None,
                "active"
            ))
        
        # 批量插入（一次数据库连接）
        try:
            await db.executemany("""
                INSERT INTO memories (
                    id, content, input_type, created_at,
                    embedding, status
                ) VALUES ($1, $2, $3, $4, $5, $6)
            """, values)
        except Exception as e:
            print(f"批量插入失败: {e}")
            # 降级：逐个插入
            for content, embedding, memory_id in zip(contents, embeddings, memory_ids):
                await self._store_memory(content, embedding, user_id)
        
        # 3. 并发构建图谱
        graph_results = []
        if enable_graph:
            graph_builder = get_graph_builder_service()
            
            tasks = [
                graph_builder.build_graph(
                    content=content,
                    user_id=user_id,
                    enable_confirmation=False
                )
                for content in contents
            ]
            
            graph_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        elapsed = time.time() - start_time
        
        # 获取缓存统计
        cache = get_embedding_cache()
        cache_stats = cache.get_stats()
        
        return {
            "memory_ids": memory_ids,
            "graph_results": graph_results,
            "stats": {
                "total": len(contents),
                "elapsed": elapsed,
                "avg_time": elapsed / len(contents) if contents else 0,
                "cache_hit_rate": cache_stats["hit_rate"]
            }
        }


# 全局记忆服务实例
memory_service = MemoryService()

# ⚠️ Monkey patch：添加分块处理方法到 MemoryService 类
MemoryService._create_with_chunks = _create_with_chunks
MemoryService._split_into_chunks = _split_into_chunks
MemoryService._deduplicate_memories = _deduplicate_memories
MemoryService._deduplicate_memories_by_content = _deduplicate_memories_by_content
MemoryService._extract_keywords = _extract_keywords
MemoryService._calculate_keyword_similarity = _calculate_keyword_similarity
