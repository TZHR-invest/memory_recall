"""
摘要生成服务
为长文本分段生成摘要
"""
from typing import List, Dict, Any, Optional
from ..llm.client import get_llm_client


class SummaryService:
    """摘要生成服务"""
    
    def __init__(self):
        """初始化"""
        self.llm_client = get_llm_client()
    
    async def generate_segment_summary(self, content: str) -> str:
        """
        生成分段摘要
        
        Args:
            content: 分段内容
        
        Returns:
            摘要文本（不超过50字）
        """
        # 限制输入长度
        if len(content) > 2000:
            content = content[:2000] + "..."
        
        prompt = f"""请为以下内容生成简洁的摘要（不超过50字）。

内容：
{content}

要求：
1. 提取核心主题和关键信息
2. 格式：主题 - 关键信息
3. 不超过50字

摘要："""
        
        try:
            summary = self.llm_client.chat_with_system(
                "你是一个专业的文本摘要助手，擅长提取核心信息。",
                prompt,
                temperature=0.3,
                max_tokens=100
            )
            return summary.strip()
        except Exception as e:
            # 如果 LLM 调用失败，返回简单的截断
            return content[:50] + "..." if len(content) > 50 else content
    
    async def generate_overall_summary(self, segments: List[Dict[str, Any]]) -> str:
        """
        生成整体摘要
        
        Args:
            segments: 分段列表（每个分段已有摘要）
        
        Returns:
            整体摘要（不超过100字）
        """
        # 汇总所有分段摘要
        summaries = []
        for s in segments:
            if s.get("summary"):
                summaries.append(s["summary"])
        
        if not summaries:
            return ""
        
        # 如果分段太多，只取前10个
        if len(summaries) > 10:
            summaries = summaries[:10]
        
        prompt = f"""请根据以下分段摘要，生成整体摘要（不超过100字）。

分段摘要：
{chr(10).join(f'- {s}' for s in summaries)}

要求：
1. 概括整体主题
2. 突出关键事件
3. 不超过100字

整体摘要："""
        
        try:
            summary = self.llm_client.chat_with_system(
                "你是一个专业的文本摘要助手，擅长汇总信息。",
                prompt,
                temperature=0.3,
                max_tokens=150
            )
            return summary.strip()
        except Exception as e:
            # 如果失败，返回分段摘要的拼接
            return "；".join(summaries[:5])[:100]
    
    async def extract_key_events(self, segments: List[Dict[str, Any]]) -> List[str]:
        """
        提取关键事件
        
        Args:
            segments: 分段列表
        
        Returns:
            关键事件列表
        """
        key_events = []
        
        for segment in segments[:10]:  # 只处理前10个分段
            content = segment.get("content", "")[:1000]
            summary = segment.get("summary", "")
            time_range = segment.get("time_range", {})
            
            # 如果有时间范围，添加时间前缀
            time_prefix = ""
            if time_range:
                start = time_range.get("start", "")
                if start:
                    # 提取时间部分
                    time_prefix = start[11:16] + " "  # HH:MM
            
            # 如果有摘要，添加到关键事件
            if summary:
                key_events.append(time_prefix + summary[:50])
        
        return key_events[:10]  # 最多返回10个关键事件


# 全局实例
summary_service: Optional[SummaryService] = None


def get_summary_service() -> SummaryService:
    """获取摘要服务实例"""
    global summary_service
    if summary_service is None:
        summary_service = SummaryService()
    return summary_service