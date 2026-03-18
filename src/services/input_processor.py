"""
输入处理服务
协调文本输入 → 结构化提取 → 存储
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import re

from core.extractor import MemoryExtractor
from core.indexer import MemoryIndexer


class InputProcessor:
    """输入处理器"""
    
    # 文本长度阈值
    SHORT_TEXT_THRESHOLD = 200  # 字符
    MEDIUM_TEXT_THRESHOLD = 1000  # 字符
    
    def __init__(
        self,
        extractor: MemoryExtractor,
        indexer: MemoryIndexer,
        memory_store: Any = None
    ):
        """
        初始化输入处理器
        
        Args:
            extractor: 记忆提取器
            indexer: 记忆索引器
            memory_store: 记忆存储（数据库）
        """
        self.extractor = extractor
        self.indexer = indexer
        self.memory_store = memory_store
    
    def process_text(
        self,
        text: str,
        current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        处理文本输入
        
        Args:
            text: 用户输入文本
            current_time: 当前时间
        
        Returns:
            处理结果（包含提取的记忆和询问问题）
        """
        if current_time is None:
            current_time = datetime.now()
        
        # 1. 判断文本类型
        text_type = self._classify_text(text)
        
        # 2. 根据类型选择处理方式
        if text_type == "short":
            result = self._process_short_text(text, current_time)
        elif text_type == "medium":
            result = self._process_medium_text(text, current_time)
        else:
            result = self._process_long_text(text, current_time)
        
        return result
    
    def _classify_text(self, text: str) -> str:
        """
        分类文本长度
        
        Args:
            text: 输入文本
        
        Returns:
            文本类型（short/medium/long）
        """
        length = len(text)
        
        if length <= self.SHORT_TEXT_THRESHOLD:
            return "short"
        elif length <= self.MEDIUM_TEXT_THRESHOLD:
            return "medium"
        else:
            return "long"
    
    def _process_short_text(
        self,
        text: str,
        current_time: datetime
    ) -> Dict[str, Any]:
        """
        处理短文本（<= 200 字符）
        
        通常是一句话、一个想法、一个简单事件
        
        Args:
            text: 输入文本
            current_time: 当前时间
        
        Returns:
            处理结果
        """
        # 提取结构化信息
        extracted = self.extractor.extract_from_text(text, current_time)
        
        # 判断是否需要询问
        need_questions = extracted.get("need_questions", [])
        
        if need_questions:
            # 返回询问结果
            return {
                "status": "need_info",
                "extracted": extracted,
                "questions": need_questions,
                "memory_id": None
            }
        else:
            # 直接存储
            memory_id = self._store_memory(extracted, text)
            return {
                "status": "success",
                "extracted": extracted,
                "questions": [],
                "memory_id": memory_id
            }
    
    def _process_medium_text(
        self,
        text: str,
        current_time: datetime
    ) -> Dict[str, Any]:
        """
        处理中等长度文本（200-1000 字符）
        
        可能包含多个事件，需要分段处理
        
        Args:
            text: 输入文本
            current_time: 当前时间
        
        Returns:
            处理结果
        """
        # 尝试按句子分段
        segments = self._split_by_sentences(text)
        
        # 如果只有一段，当作短文本处理
        if len(segments) == 1:
            return self._process_short_text(text, current_time)
        
        # 多段处理
        memories = []
        all_questions = []
        
        for segment in segments:
            extracted = self.extractor.extract_from_text(segment, current_time)
            
            questions = extracted.get("need_questions", [])
            if questions:
                all_questions.extend(questions)
            else:
                memory_id = self._store_memory(extracted, segment)
                memories.append({
                    "id": memory_id,
                    "content": segment,
                    "extracted": extracted
                })
        
        if all_questions:
            return {
                "status": "need_info",
                "memories": memories,
                "questions": all_questions[:2],  # 最多 2 个问题
                "total_segments": len(segments)
            }
        else:
            return {
                "status": "success",
                "memories": memories,
                "questions": [],
                "total_segments": len(segments)
            }
    
    def _process_long_text(
        self,
        text: str,
        current_time: datetime
    ) -> Dict[str, Any]:
        """
        处理长文本（> 1000 字符）
        
        日记、文章等，需要智能分段
        
        Args:
            text: 输入文本
            current_time: 当前时间
        
        Returns:
            处理结果
        """
        # 按段落分段
        segments = self._split_by_paragraphs(text)
        
        memories = []
        all_questions = []
        
        for segment in segments:
            # 只处理有效段落（> 50 字符）
            if len(segment.strip()) < 50:
                continue
            
            extracted = self.extractor.extract_from_text(segment, current_time)
            
            questions = extracted.get("need_questions", [])
            if questions:
                all_questions.extend(questions)
            
            memory_id = self._store_memory(extracted, segment)
            memories.append({
                "id": memory_id,
                "content": segment[:100] + "...",  # 截断显示
                "extracted": extracted
            })
        
        return {
            "status": "success",
            "memories": memories,
            "questions": all_questions[:2],  # 最多 2 个问题
            "total_segments": len(segments),
            "stored_memories": len(memories)
        }
    
    def _split_by_sentences(self, text: str) -> List[str]:
        """
        按句子分段
        
        Args:
            text: 输入文本
        
        Returns:
            句子列表
        """
        # 中文句号、感叹号、问号
        sentences = re.split(r'[。！？\n]+', text)
        
        # 过滤空句子
        return [s.strip() for s in sentences if s.strip()]
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """
        按段落分段
        
        Args:
            text: 输入文本
        
        Returns:
            段落列表
        """
        # 按换行分段
        paragraphs = text.split('\n\n')
        
        # 如果段落太长，按句子再分
        result = []
        for para in paragraphs:
            if len(para) > self.MEDIUM_TEXT_THRESHOLD:
                # 按句子分段
                sentences = self._split_by_sentences(para)
                result.extend(sentences)
            else:
                result.append(para)
        
        return [p.strip() for p in result if p.strip()]
    
    def _store_memory(
        self,
        extracted: Dict[str, Any],
        original_text: str
    ) -> Optional[str]:
        """
        存储记忆
        
        Args:
            extracted: 提取的结构化信息
            original_text: 原始文本
        
        Returns:
            记忆 ID（如果存储成功）
        """
        import uuid
        
        # 生成记忆 ID
        memory_id = str(uuid.uuid4())
        
        # 构建记忆数据
        memory_data = {
            "id": memory_id,
            "content": original_text,
            "created_at": datetime.now().isoformat(),
            **extracted
        }
        
        # 添加到索引
        self.indexer.add_memory(memory_id, memory_data)
        
        # 如果有存储服务，存储到数据库
        if self.memory_store:
            # TODO: 存储到数据库
            pass
        
        return memory_id
    
    def process_with_answer(
        self,
        original_text: str,
        questions: List[str],
        answers: List[str],
        current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        处理带回答的输入
        
        用户回答了询问问题后，重新处理
        
        Args:
            original_text: 原始文本
            questions: 问题列表
            answers: 回答列表
            current_time: 当前时间
        
        Returns:
            处理结果
        """
        if current_time is None:
            current_time = datetime.now()
        
        # 合并原始文本和回答
        enhanced_text = original_text
        for question, answer in zip(questions, answers):
            enhanced_text += f" {answer}"
        
        # 重新提取
        return self.process_text(enhanced_text, current_time)
    
    def batch_process(
        self,
        texts: List[str],
        current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        批量处理文本
        
        Args:
            texts: 文本列表
            current_time: 当前时间
        
        Returns:
            批量处理结果
        """
        if current_time is None:
            current_time = datetime.now()
        
        results = []
        for text in texts:
            result = self.process_text(text, current_time)
            results.append(result)
        
        # 统计
        success_count = sum(1 for r in results if r["status"] == "success")
        need_info_count = sum(1 for r in results if r["status"] == "need_info")
        
        return {
            "total": len(texts),
            "success": success_count,
            "need_info": need_info_count,
            "results": results
        }
