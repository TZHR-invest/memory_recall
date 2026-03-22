"""
记忆提取服务（Function Calling 方式）

核心功能：
1. 使用 Function Calling 调用 LLM 提取记忆
2. 解析 Function Calling 返回结果
3. 返回结构化的记忆数据
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime

# 修改导入方式
try:
    from ..llm.client import get_llm_client
    from ..tools.extract_memories_tool import (
        EXTRACT_MEMORIES_TOOL,
        get_extract_memories_system_prompt
    )
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    from llm.client import get_llm_client
    from tools.extract_memories_tool import (
        EXTRACT_MEMORIES_TOOL,
        get_extract_memories_system_prompt
    )


class MemoryExtractionService:
    """记忆提取服务"""
    
    def __init__(self):
        """初始化服务"""
        self.llm_client = get_llm_client()
    
    async def extract_memories(
        self,
        content: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        提取记忆（Function Calling 方式）
        
        Args:
            content: 输入文本
            user_id: 用户 ID（可选，用于上下文）
        
        Returns:
            {
                "success": True,
                "memories": [
                    {
                        "content": "...",
                        "time": {"value": "ISO格式", "original_text": "今天下午"},
                        "location": {"name": "星巴克"},
                        "people": [{"name": "张三"}],
                        "entities": [...],
                        "relations": [...],
                        "tags": [...],
                        "emotion": {...},
                        "importance": 0.8
                    }
                ]
            }
        """
        try:
            # 1. 调用 LLM Function Calling
            response = await self._call_llm_with_function_calling(content)
            
            # 2. 解析工具调用结果
            memories = self._parse_tool_calls(response)
            
            if not memories:
                return {
                    "success": False,
                    "error": "未能提取到记忆",
                    "memories": []
                }
            
            # 3. 后处理：过滤"我"实体
            memories = self._post_process_memories(memories)
            
            return {
                "success": True,
                "memories": memories
            }
            
        except Exception as e:
            print(f"❌ 记忆提取失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "memories": []
            }
    
    async def _call_llm_with_function_calling(
        self,
        content: str
    ) -> Dict[str, Any]:
        """
        使用 Function Calling 调用 LLM
        
        Args:
            content: 输入文本
        
        Returns:
            LLM 响应
        """
        # 获取系统 Prompt（包含当前日期）
        system_prompt = get_extract_memories_system_prompt()
        
        # 构建消息列表
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请从以下文本中提取记忆：\n\n{content}"}
        ]
        
        # 调用 LLM（使用 extract_memories_tool 的 schema）
        response = self.llm_client.call_with_tools(
            messages=messages,
            tools=[EXTRACT_MEMORIES_TOOL],
            temperature=0.3,  # 降低温度以提高一致性
            max_tokens=4000   # 增加最大 token 数以支持长文本
        )
        
        return response
    
    def _parse_tool_calls(
        self,
        response: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        解析工具调用结果
        
        Args:
            response: LLM 响应
        
        Returns:
            记忆列表
        """
        memories = []
        
        # 检查是否有工具调用
        if not response.get("tool_calls"):
            print("⚠️ 没有工具调用，尝试从 JSON 响应中解析")
            return self._parse_json_response(response)
        
        # 遍历工具调用
        for tool_call in response["tool_calls"]:
            function_name = tool_call.get("name")  # 修正：直接访问 "name"
            
            if function_name == "extract_memories_with_graph":
                # 提取记忆
                arguments = tool_call.get("arguments", {})  # 修正：直接访问 "arguments"
                memories = arguments.get("memories", [])
                
                # 确保每个记忆都有必要字段
                for memory in memories:
                    self._ensure_memory_fields(memory)
                
                return memories
        
        return memories
    
    def _parse_json_response(
        self,
        response: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        从 JSON 响应中解析记忆（降级处理）
        
        Args:
            response: LLM 响应
        
        Returns:
            记忆列表
        """
        content = response.get("content", "")
        
        if not content:
            return []
        
        try:
            # 尝试解析 JSON
            data = json.loads(content)
            
            # 检查格式
            if isinstance(data, dict):
                if "memories" in data:
                    memories = data["memories"]
                elif "segments" in data:
                    # 兼容旧格式
                    memories = data["segments"]
                else:
                    # 单条记忆
                    memories = [data]
            elif isinstance(data, list):
                memories = data
            else:
                return []
            
            # 确保每个记忆都有必要字段
            for memory in memories:
                self._ensure_memory_fields(memory)
            
            return memories
            
        except json.JSONDecodeError:
            print(f"⚠️ JSON 解析失败: {content[:100]}")
            return []
    
    def _ensure_memory_fields(self, memory: Dict[str, Any]) -> None:
        """
        确保记忆包含必要字段
        
        Args:
            memory: 记忆数据
        """
        # 确保 content 字段
        if "content" not in memory:
            memory["content"] = ""
        
        # 确保 time 字段
        if "time" not in memory:
            memory["time"] = {
                "value": None,
                "original_text": ""
            }
        elif isinstance(memory["time"], dict):
            if "value" not in memory["time"]:
                memory["time"]["value"] = None
            if "original_text" not in memory["time"]:
                memory["time"]["original_text"] = ""
        
        # 确保 location 字段
        if "location" not in memory:
            memory["location"] = None
        
        # 确保 people 字段
        if "people" not in memory:
            memory["people"] = []
        
        # 确保 entities 字段
        if "entities" not in memory:
            memory["entities"] = []
        
        # 确保 relations 字段
        if "relations" not in memory:
            memory["relations"] = []
        
        # 确保 tags 字段
        if "tags" not in memory:
            memory["tags"] = []
        
        # 确保 importance 字段
        if "importance" not in memory:
            memory["importance"] = 0.5
        
        # 确保实体有 confidence 字段
        for entity in memory.get("entities", []):
            if "confidence" not in entity:
                entity["confidence"] = 0.8
        
        # 确保关系有 confidence 字段
        for relation in memory.get("relations", []):
            if "confidence" not in relation:
                relation["confidence"] = 0.8
    
    def _post_process_memories(
        self,
        memories: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        后处理记忆
        
        主要任务：
        1. 过滤"我"实体
        2. 验证关系
        
        Args:
            memories: 记忆列表
        
        Returns:
            处理后的记忆列表
        """
        # 第一人称代词黑名单
        first_person_pronouns = {
            '我', '本人', '自己', '我们', '咱们', '俺', '鄙人',
            '笔者', '在下', '小弟', '小妹', '说话人', '叙述者'
        }
        
        for memory in memories:
            # 过滤实体（不包含"我"）
            entities = memory.get("entities", [])
            filtered_entities = [
                e for e in entities
                if e.get("name") not in first_person_pronouns
            ]
            memory["entities"] = filtered_entities
            
            # 处理关系
            # "我"可以出现在 source 中，但不能出现在 target 中
            relations = memory.get("relations", [])
            valid_entity_names = {e.get("name") for e in filtered_entities}
            valid_entity_names.add("我")  # 允许"我"在 source 中
            
            filtered_relations = []
            for relation in relations:
                source = relation.get("source")
                target = relation.get("target")
                
                # source 可以是"我"或有效实体
                # target 必须是有效实体（不能是"我"）
                if source in valid_entity_names and target in valid_entity_names and target != "我":
                    filtered_relations.append(relation)
            
            memory["relations"] = filtered_relations
        
        return memories


# 全局记忆提取服务实例
_extraction_service: Optional[MemoryExtractionService] = None


def get_memory_extraction_service() -> MemoryExtractionService:
    """获取记忆提取服务实例"""
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = MemoryExtractionService()
    return _extraction_service
