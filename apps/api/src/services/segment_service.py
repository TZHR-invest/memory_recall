"""
智能分段服务
支持多种分段策略：时间、话题、大小
"""
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio


class SegmentService:
    """智能分段服务"""
    
    # 时间戳正则表达式
    TIME_PATTERNS = [
        # 2026-03-19 17:30:00
        r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}',
        # 2026-03-19T17:30:00
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',
        # 2026/03/19 17:30
        r'\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}',
        # 03-19 17:30
        r'\d{2}-\d{2}\s+\d{2}:\d{2}',
        # 17:30:00
        r'\d{2}:\d{2}:\d{2}',
        # [09:00]
        r'\[\d{2}:\d{2}\]',
        # [2026-03-19 09:00:00]
        r'\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]',
    ]
    
    def __init__(self):
        """初始化"""
        self.time_regex = re.compile('|'.join(self.TIME_PATTERNS))
    
    async def segment(
        self,
        content: str,
        strategy: str = "auto",
        max_size: int = 5000
    ) -> List[Dict[str, Any]]:
        """
        智能分段
        
        Args:
            content: 文本内容
            strategy: 分段策略（auto/time/topic/size）
            max_size: 最大分段大小
        
        Returns:
            分段列表
        """
        # 自动检测策略
        if strategy == "auto":
            strategy = self._detect_strategy(content)
        
        # 根据策略分段
        if strategy == "time":
            return await self._segment_by_time(content, max_size)
        elif strategy == "topic":
            return await self._segment_by_topic(content, max_size)
        else:
            return self._segment_by_size(content, max_size)
    
    def _detect_strategy(self, content: str) -> str:
        """
        检测分段策略
        
        Args:
            content: 文本内容
        
        Returns:
            推荐的策略
        """
        # 检查是否有时间戳
        time_matches = self.time_regex.findall(content)
        
        if len(time_matches) > 10:  # 有较多时间戳
            return "time"
        
        return "size"
    
    async def _segment_by_time(
        self,
        content: str,
        max_size: int = 5000
    ) -> List[Dict[str, Any]]:
        """
        按时间分段
        
        Args:
            content: 文本内容
            max_size: 最大分段大小
        
        Returns:
            分段列表
        """
        lines = content.split('\n')
        segments = []
        current_segment = []
        current_time = None
        segment_start_time = None
        
        for line in lines:
            # 提取时间戳
            time_match = self.time_regex.search(line)
            
            if time_match:
                line_time_str = time_match.group()
                line_time = self._parse_time(line_time_str)
                
                # 判断是否需要分段
                if current_time and line_time:
                    time_diff = (line_time - current_time).total_seconds()
                    
                    # 时间间隔 > 1小时，或者当前分段过大，则分段
                    if time_diff > 3600 or sum(len(l) for l in current_segment) > max_size:
                        if current_segment:
                            segments.append(self._create_segment(
                                current_segment,
                                len(segments),
                                segment_start_time,
                                current_time
                            ))
                            current_segment = []
                            segment_start_time = line_time
                
                if not segment_start_time:
                    segment_start_time = line_time
                current_time = line_time
            
            current_segment.append(line)
        
        # 最后一个分段
        if current_segment:
            segments.append(self._create_segment(
                current_segment,
                len(segments),
                segment_start_time,
                current_time
            ))
        
        return segments
    
    async def _segment_by_topic(
        self,
        content: str,
        max_size: int = 5000
    ) -> List[Dict[str, Any]]:
        """
        按话题分段（混合策略：段落 + 句子）
        
        Args:
            content: 文本内容
            max_size: 最大分段大小
        
        Returns:
            分段列表
        """
        # 1. 按空行分隔段落
        paragraphs = re.split(r'\n\s*\n', content)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        segments = []
        current_content = []
        current_size = 0
        
        for para in paragraphs:
            para_size = len(para)
            
            # 如果段落本身太大，按句子细分
            if para_size > max_size:
                # 先保存当前分段
                if current_content:
                    segments.append(self._create_segment(
                        current_content,
                        len(segments)
                    ))
                    current_content = []
                    current_size = 0
                
                # 按句子分段
                sentences = re.split(r'([。！？\n])', para)
                sentences = [''.join(i) for i in zip(sentences[0::2], sentences[1::2] + [''])]
                sentences = [s.strip() for s in sentences if s.strip()]
                
                for sentence in sentences:
                    sent_size = len(sentence)
                    
                    if current_size + sent_size > max_size and current_content:
                        segments.append(self._create_segment(
                            current_content,
                            len(segments)
                        ))
                        current_content = []
                        current_size = 0
                    
                    current_content.append(sentence)
                    current_size += sent_size
            
            # 正常段落
            else:
                if current_size + para_size > max_size and current_content:
                    segments.append(self._create_segment(
                        current_content,
                        len(segments)
                    ))
                    current_content = []
                    current_size = 0
                
                current_content.append(para)
                current_size += para_size
        
        # 最后一个分段
        if current_content:
            segments.append(self._create_segment(
                current_content,
                len(segments)
            ))
        
        return segments
    
    def _segment_by_size(
        self,
        content: str,
        max_size: int = 5000
    ) -> List[Dict[str, Any]]:
        """
        按大小分段
        
        Args:
            content: 文本内容
            max_size: 最大分段大小
        
        Returns:
            分段列表
        """
        segments = []
        lines = content.split('\n')
        current_content = []
        current_size = 0
        
        for line in lines:
            line_size = len(line) + 1  # +1 for newline
            
            if current_size + line_size > max_size and current_content:
                segments.append(self._create_segment(
                    current_content,
                    len(segments)
                ))
                current_content = []
                current_size = 0
            
            current_content.append(line)
            current_size += line_size
        
        if current_content:
            segments.append(self._create_segment(
                current_content,
                len(segments)
            ))
        
        return segments
    
    def _create_segment(
        self,
        lines: List[str],
        index: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        创建分段对象
        
        Args:
            lines: 行列表
            index: 分段索引
            start_time: 开始时间
            end_time: 结束时间
        
        Returns:
            分段对象
        """
        segment = {
            "content": '\n'.join(lines),
            "index": index,
            "line_count": len(lines)
        }
        
        if start_time and end_time:
            segment["time_range"] = {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            }
        
        return segment
    
    def _parse_time(self, time_str: str) -> Optional[datetime]:
        """
        解析时间字符串
        
        Args:
            time_str: 时间字符串
        
        Returns:
            datetime 对象
        """
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%m-%d %H:%M",
            "%H:%M:%S",
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(time_str, fmt)
                # 如果没有年份，使用当前年份
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return dt
            except ValueError:
                continue
        
        return None


# 全局实例
segment_service: Optional[SegmentService] = None


def get_segment_service() -> SegmentService:
    """获取分段服务实例"""
    global segment_service
    if segment_service is None:
        segment_service = SegmentService()
    return segment_service