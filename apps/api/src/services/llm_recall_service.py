"""
LLM 召回服务
基于大语言模型的记忆召回与回答生成
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from ..llm.client import get_llm_client
from ..config import settings


class LLMRecallService:
    """LLM 召回服务"""

    def __init__(self):
        """初始化服务"""
        self.llm_client = get_llm_client()

    async def call_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: List[Dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """
        使用 Function Calling 调用 LLM

        Args:
            system_prompt: 系统提示
            user_prompt: 用户提示
            tools: 工具列表（OpenAI Function Calling 格式）
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            包含 tool_calls 或 content 的响应：
            {
                "content": str,  # 普通文本响应
                "tool_calls": [  # 工具调用列表
                    {
                        "id": str,
                        "type": "function",
                        "function": {
                            "name": str,
                            "arguments": dict
                        }
                    }
                ]
            }
        """
        try:
            # 准备消息
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            # 调用 OpenAI 兼容的 API（支持 Function Calling）
            response = self.llm_client.client.chat.completions.create(
                model=self.llm_client.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # 解析响应
            message = response.choices[0].message

            result = {"content": message.content, "tool_calls": []}

            # 如果有工具调用
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    # 解析参数
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as e:
                        print(f"解析工具参数失败: {e}")
                        arguments = {}

                    result["tool_calls"].append(
                        {
                            "id": tool_call.id,
                            "type": tool_call.type,
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": arguments,
                            },
                        }
                    )

            return result

        except Exception as e:
            print(f"Function Calling 调用失败: {e}")
            # 降级处理：返回空响应
            return {"content": None, "tool_calls": [], "error": str(e)}

    async def generate_recall_response(
        self,
        query: str,
        memory_results: List[Dict[str, Any]],
        detail_level: str = "medium",
        user_id: Optional[str] = None,  # 新增参数
    ) -> Dict[str, Any]:
        """
        基于记忆检索结果生成自然语言回答

        Args:
            query: 用户查询
            memory_results: 检索到的记忆列表
            detail_level: 详情级别 (brief/medium/detailed)
            user_id: 用户 ID（用于获取图谱关系）

        Returns:
            包含回答和引用记忆的结果
        """
        if not memory_results or len(memory_results) == 0:
            return {"answer": "未找到相关记忆", "used_memories": [], "memory_count": 0}

        # 构建记忆上下文（默认最多 5 条）
        max_memories = min(5, len(memory_results))
        memory_context = self._build_simple_memory_context(
            memory_results[:max_memories]
        )

        # 简化系统提示
        system_prompt = "直接回答用户问题，不要说'根据记忆'。只陈述事实，不要推断。"

        # 简化用户提示
        user_prompt = f"问题：{query}\n\n记忆：\n{memory_context}\n\n直接回答："

        # 调用 LLM
        try:
            answer = self.llm_client.chat_with_system(
                system_prompt=system_prompt,
                user_message=user_prompt,
                temperature=0.1,  # 更低的温度
                max_tokens=200,  # 更短的输出
            )

            # 标记使用的记忆
            used_memories = self._identify_used_memories(answer, memory_results)

            return {
                "answer": answer,
                "used_memories": used_memories,
                "memory_count": len(used_memories),
            }
        except Exception as e:
            # 降级处理：返回简单总结
            return {
                "answer": f"找到 {len(memory_results)} 条相关记忆，但生成回答时出错：{str(e)}",
                "used_memories": memory_results[:3],
                "memory_count": min(3, len(memory_results)),
            }

    def _build_simple_memory_context(self, memories: List[Dict[str, Any]]) -> str:
        """
        构建简化的记忆上下文（快速版）

        Args:
            memories: 记忆列表

        Returns:
            格式化的记忆文本
        """
        context_parts = []
        for i, mem in enumerate(memories, 1):
            content = mem.get("content", "")
            # 只保留内容和时间
            time_str = ""
            time_value = mem.get("time_value")
            if time_value:
                if isinstance(time_value, str):
                    time_str = f"（{time_value[:10]}）"
                elif hasattr(time_value, "strftime"):
                    time_str = f"（{time_value.strftime('%Y-%m-%d')}）"
            context_parts.append(f"{i}. {content}{time_str}")

        return "\n".join(context_parts)

    def _identify_used_memories(
        self, answer: str, memories: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        识别回答中使用的记忆，并按重要性排序

        Args:
            answer: LLM 生成的回答
            memories: 候选记忆列表

        Returns:
            排序后的被使用记忆列表（最多 5 条，已去重）
        """
        used_with_scores = []
        seen_contents = set()

        for mem in memories:
            content = mem.get("content", "")
            if not content or len(content) < 5:
                continue

            if content in seen_contents:
                continue
            seen_contents.add(content)

            # 提取关键实体/短语（人名、地名、事件等）
            # 使用滑动窗口提取 2-4 字符的片段
            key_phrases = []
            for window in [4, 3, 2]:
                for i in range(len(content) - window + 1):
                    phrase = content[i : i + window]
                    # 过滤掉全是标点或纯虚词的片段
                    if any(c.isalnum() for c in phrase):
                        key_phrases.append(phrase)

            if not key_phrases:
                continue

            # 统计在回答中出现的片段数
            matched = sum(1 for phrase in key_phrases if phrase in answer)
            match_ratio = matched / len(key_phrases) if key_phrases else 0

            # 匹配度超过 15% 认为被使用
            if match_ratio > 0.15:
                similarity = mem.get("similarity", 0.5)
                score = match_ratio * 0.6 + similarity * 0.4
                used_with_scores.append((mem, score))

        # 按分数降序排序，最多返回 5 条
        used_with_scores.sort(key=lambda x: x[1], reverse=True)

        # 更新 similarity 为综合分数
        used = []
        for mem, score in used_with_scores[:5]:
            mem_copy = mem.copy()
            mem_copy["similarity"] = score
            used.append(mem_copy)

        # 如果没有识别到，按 similarity 排序返回前 3 条
        if not used and memories:
            seen = set()
            unique_memories = []
            for m in memories:
                c = m.get("content", "")
                if c not in seen:
                    seen.add(c)
                    unique_memories.append(m)

            sorted_memories = sorted(
                unique_memories,
                key=lambda m: -m.get("similarity", 0),
            )
            return sorted_memories[:3]

        return used

    async def _get_entity_relations(
        self, memories: List[Dict[str, Any]], user_id: str
    ) -> List[Dict[str, Any]]:
        """
        获取记忆中实体的关系

        Args:
            memories: 记忆列表
            user_id: 用户 ID

        Returns:
            实体关系列表
        """
        try:
            from ..database import db

            # 提取记忆中的实体
            entity_names = set()
            for mem in memories:
                # 从 memory_entities 表获取实体
                memory_id = mem.get("memory_id") or mem.get("id")
                if memory_id:
                    entities = await db.fetch(
                        """
                        SELECT e.name
                        FROM entities e
                        JOIN memory_entities me ON e.id = me.entity_id
                        WHERE me.memory_id = $1
                        """,
                        memory_id,
                    )
                    entity_names.update([e["name"] for e in entities])

            if not entity_names:
                return []

            # 查询关系
            relations = await db.fetch(
                """
                SELECT 
                    e1.name as source,
                    r.relation_type,
                    e2.name as destination,
                    r.weight
                FROM relations r
                JOIN entities e1 ON e1.id = r.from_entity_id
                JOIN entities e2 ON e2.id = r.to_entity_id
                WHERE (e1.name = ANY($1) OR e2.name = ANY($1))
                AND (r.user_id = $2 OR r.user_id = 'system')
                ORDER BY r.weight DESC
                LIMIT 20
                """,
                list(entity_names),
                user_id,
            )

            return [dict(r) for r in relations]

        except Exception as e:
            # 如果查询失败，返回空列表
            import logging

            logging.warning(f"获取实体关系失败: {e}")
            return []


# 全局 LLM 召回服务实例
llm_recall_service: Optional[LLMRecallService] = None


def get_llm_recall_service() -> LLMRecallService:
    """获取 LLM 召回服务实例"""
    global llm_recall_service
    if llm_recall_service is None:
        llm_recall_service = LLMRecallService()
    return llm_recall_service
