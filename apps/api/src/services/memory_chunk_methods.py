"""
超长文本分块处理方法
添加到 MemoryService 类中
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import json
import asyncio
import re


async def _create_with_chunks(
    self,
    content: str,
    user_id: str,
    enable_graph: bool
) -> Dict[str, Any]:
    """
    分块处理超长文本（使用 Function Calling）
    
    Args:
        content: 超长文本
        user_id: 用户 ID
        enable_graph: 是否启用图谱
    
    Returns:
        创建结果
    """
    # 1. 分块（每块最大 5000 字符）
    chunks = self._split_into_chunks(content, max_chars=5000)
    print(f"✂️ 文本已分为 {len(chunks)} 块")
    
    # 2. 使用 Function Calling 处理每个块
    all_memories = []
    all_entities = []
    all_relations = []
    
    for i, chunk in enumerate(chunks):
        try:
            # ⚡ 使用新的 Function Calling 方法
            result = await self._extract_memories_v2(chunk)
            
            if result and result.get("success"):
                memories = result.get("memories", [])
                all_memories.extend(memories)
                
                # 收集实体和关系
                for memory in memories:
                    entities = memory.get("entities", [])
                    relations = memory.get("relations", [])
                    all_entities.extend(entities)
                    all_relations.extend(relations)
                    
            print(f"✅ 块 {i+1}/{len(chunks)} 处理完成")
        except Exception as e:
            print(f"❌ 处理块 {i+1} 失败: {e}")
    
    # 3. 去重（记忆、实体、关系）
    print(f"📊 去重前：{len(all_memories)} 个记忆点")
    unique_memories = self._deduplicate_memories_by_content(all_memories)
    print(f"📊 去重后：{len(unique_memories)} 个记忆点（去重 {len(all_memories) - len(unique_memories)} 个）")
    
    unique_entities = self._deduplicate_entities_v2(all_entities)
    unique_relations = self._deduplicate_relations_v2(all_relations)
    
    # 4. 存储记忆（统一时间标准化）
    memory_ids = []
    
    # 生成整体内容的 embedding（用于所有记忆）
    embedding = await self._generate_embedding(content)
    
    for memory in unique_memories:
        memory_content = memory.get("content", "")
        if not memory_content.strip():
            continue
        
        # 提取结构化信息
        time_info = memory.get("time", {})
        time_value = time_info.get("value") if isinstance(time_info, dict) else None
        time_original = time_info.get("original_text") if isinstance(time_info, dict) else None
        
        # 使用新的时间标准化（带时区）
        time_value = self._parse_time_value_v2(time_value)
        
        # 提取地点
        location_info = memory.get("location", {})
        location_name = location_info.get("name") if isinstance(location_info, dict) else None
        
        # 提取人物
        people = memory.get("people", [])
        
        # 提取标签
        tags = memory.get("tags", [])
        
        # 提取情绪
        emotion = memory.get("emotion", {})
        
        # 记忆点类型和重要性
        point_type = memory.get("type", "event")
        importance = memory.get("importance", 0.5)
        
        # 存储记忆
        memory_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        from ..database import db
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
        
        # 存储图谱（为每个记忆存储关联的实体和关系）
        if enable_graph:
            entities = memory.get("entities", [])
            relations = memory.get("relations", [])
            
            if entities or relations:
                await self._store_graph_v2(
                    entities=entities,
                    relations=relations,
                    user_id=user_id,
                    memory_id=memory_id
                )
    
    return {
        "memory_id": memory_ids[0] if memory_ids else None,
        "graph": {
            "entities": len(unique_entities) if enable_graph else 0,
            "relations": len(unique_relations) if enable_graph else 0
        },
        "extracted": {
            "memories": len(unique_memories),
            "memory_ids": memory_ids
        }
    }


def _split_into_chunks(self, content: str, max_chars: int = 5000) -> List[str]:
    """
    将超长文本分块（按段落+大小+重叠窗口）
    
    策略：
    1. 优先按段落分割（保持语义完整）
    2. 单个段落过长时按句子分割
    3. ⚠️ 添加重叠窗口（10%），防止边界信息丢失
    4. 在句子边界处分割，避免截断句子
    
    Args:
        content: 文本内容
        max_chars: 每块最大字符数（默认 5000）
    
    Returns:
        分块列表
    """
    paragraphs = re.split(r'\n\s*\n', content)
    chunks = []
    current_chunk = []
    current_size = 0
    overlap_sentences = []  # 重叠句子缓存
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        para_size = len(para)
        
        # 单个段落超过限制，按句子分割
        if para_size > max_chars:
            # 先保存当前块
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
            
            # 按句子分割
            sentences = re.split(r'([。！？\n])', para)
            sentences = [''.join(i) for i in zip(sentences[0::2], sentences[1::2] + [''])]
            sentences = [s.strip() for s in sentences if s.strip()]
            
            for i, sentence in enumerate(sentences):
                sent_size = len(sentence)
                
                if current_size + sent_size > max_chars and current_chunk:
                    # 保存当前块
                    chunks.append('\n'.join(current_chunk))
                    
                    # ⚠️ 保留最后 1-2 句作为重叠
                    overlap_sentences = current_chunk[-2:] if len(current_chunk) >= 2 else current_chunk[-1:] if current_chunk else []
                    current_chunk = overlap_sentences.copy()
                    current_size = sum(len(s) for s in current_chunk)
                
                current_chunk.append(sentence)
                current_size += sent_size
        
        # 正常段落
        elif current_size + para_size > max_chars and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            
            # ⚠️ 保留最后一段作为重叠
            overlap_sentences = [current_chunk[-1]] if current_chunk else []
            current_chunk = overlap_sentences.copy()
            current_size = sum(len(p) for p in current_chunk)
            
            current_chunk.append(para)
            current_size += para_size
        else:
            current_chunk.append(para)
            current_size += para_size
    
    # 最后一块
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    
    return chunks


async def _deduplicate_memories(
    self,
    segments: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    记忆去重
    
    策略：
    1. 提取关键词
    2. 计算关键词集合的重叠度
    3. 如果重叠度 > 80%，则认为重复
    4. 保留重要性评分更高的记忆
    
    Args:
        segments: 记忆点列表
    
    Returns:
        去重后的记忆点列表
    """
    if not segments or len(segments) <= 1:
        return segments
    
    # 为每个记忆点提取关键词
    for seg in segments:
        seg["_keywords"] = self._extract_keywords(seg.get("content", ""))
    
    # 去重
    deduplicated = []
    seen = set()
    
    for i, seg in enumerate(segments):
        if i in seen:
            continue
        
        # 检查是否与已保留的记忆重复
        is_duplicate = False
        for j, kept in enumerate(deduplicated):
            similarity = self._calculate_keyword_similarity(
                seg.get("_keywords", set()),
                kept.get("_keywords", set())
            )
            
            if similarity > 0.8:
                # 重复记忆，保留重要性更高的
                seg_importance = seg.get("importance", 0.5)
                kept_importance = kept.get("importance", 0.5)
                
                if seg_importance > kept_importance:
                    # 替换为重要性更高的记忆
                    deduplicated[j] = seg
                    print(f"  🔄 替换重复记忆（相似度 {similarity:.2f}）：{kept.get('content', '')[:30]}... → {seg.get('content', '')[:30]}...")
                else:
                    print(f"  🗑️ 跳过重复记忆（相似度 {similarity:.2f}）：{seg.get('content', '')[:30]}...")
                
                is_duplicate = True
                break
        
        if not is_duplicate:
            deduplicated.append(seg)
    
    # 清理临时字段
    for seg in deduplicated:
        seg.pop("_keywords", None)
    
    return deduplicated


def _extract_keywords(self, text: str) -> set:
    """
    提取关键词（简化版）
    
    Args:
        text: 文本内容
    
    Returns:
        关键词集合
    """
    import re
    
    # 停用词列表（常见无意义词）
    stop_words = {
        '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
        '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
        '自己', '这', '那', '但', '而', '与', '等', '对', '为', '以', '被', '把', '让',
        '这周', '上周', '下周', '这个', '那个', '什么', '怎么', '如何', '为什么'
    }
    
    # 提取中文词汇（2-4字的词）
    words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
    
    # 过滤停用词和标点
    keywords = set()
    for word in words:
        if word not in stop_words and len(word) >= 2:
            keywords.add(word)
    
    return keywords


def _calculate_keyword_similarity(self, keywords1: set, keywords2: set) -> float:
    """
    计算关键词集合的相似度（Jaccard 相似度）
    
    Args:
        keywords1: 关键词集合1
        keywords2: 关键词集合2
    
    Returns:
        相似度（0-1）
    """
    if not keywords1 or not keywords2:
        return 0.0
    
    intersection = keywords1 & keywords2
    union = keywords1 | keywords2
    
    if not union:
        return 0.0
    
    return len(intersection) / len(union)


def _deduplicate_memories_by_content(
    self,
    memories: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    基于内容的记忆去重
    
    策略：
    1. 提取关键词
    2. 计算关键词集合的重叠度
    3. 如果重叠度 > 80%，则认为重复
    4. 保留重要性评分更高的记忆
    
    Args:
        memories: 记忆列表
    
    Returns:
        去重后的记忆列表
    """
    if not memories or len(memories) <= 1:
        return memories
    
    # 为每个记忆提取关键词
    for memory in memories:
        memory["_keywords"] = self._extract_keywords(memory.get("content", ""))
    
    # 去重
    deduplicated = []
    seen = set()
    
    for i, memory in enumerate(memories):
        if i in seen:
            continue
        
        # 检查是否与已保留的记忆重复
        is_duplicate = False
        for j, kept in enumerate(deduplicated):
            similarity = self._calculate_keyword_similarity(
                memory.get("_keywords", set()),
                kept.get("_keywords", set())
            )
            
            if similarity > 0.8:
                # 重复记忆，保留重要性更高的
                memory_importance = memory.get("importance", 0.5)
                kept_importance = kept.get("importance", 0.5)
                
                if memory_importance > kept_importance:
                    # 替换为重要性更高的记忆
                    deduplicated[j] = memory
                    print(f"  🔄 替换重复记忆（相似度 {similarity:.2f}）：{kept.get('content', '')[:30]}... → {memory.get('content', '')[:30]}...")
                else:
                    print(f"  🗑️ 跳过重复记忆（相似度 {similarity:.2f}）：{memory.get('content', '')[:30]}...")
                
                is_duplicate = True
                break
        
        if not is_duplicate:
            deduplicated.append(memory)
    
    # 清理临时字段
    for memory in deduplicated:
        memory.pop("_keywords", None)
    
    return deduplicated
