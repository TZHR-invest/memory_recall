"""
结构化信息提取模块
"""
from typing import Dict, Any, Optional
from .client import get_llm_client
from .prompts import (
    EXTRACT_MEMORY_PROMPT,
    JUDGE_INQUIRY_PROMPT,
    PARSE_QUERY_PROMPT,
    UNDERSTAND_IMAGE_PROMPT
)


class StructuredExtractor:
    """结构化信息提取器"""
    
    def __init__(self):
        self.llm = get_llm_client()
    
    def extract_memory(self, content: str) -> Optional[Dict[str, Any]]:
        """
        从记忆文本中提取结构化信息
        
        Args:
            content: 记忆文本
        
        Returns:
            提取的结构化信息，失败返回 None
        """
        prompt = EXTRACT_MEMORY_PROMPT.format(content=content)
        return self.llm.extract_json(prompt, temperature=0.3)
    
    def judge_inquiry(
        self,
        field_name: str,
        field_value: Any,
        context: str
    ) -> Optional[Dict[str, Any]]:
        """
        判断是否需要询问
        
        Args:
            field_name: 字段名称
            field_value: 字段值
            context: 上下文
        
        Returns:
            判断结果，失败返回 None
        """
        prompt = JUDGE_INQUIRY_PROMPT.format(
            field_name=field_name,
            field_value=str(field_value),
            context=context
        )
        return self.llm.extract_json(prompt, temperature=0.2)
    
    def parse_query(self, query: str) -> Optional[Dict[str, Any]]:
        """
        解析用户查询
        
        Args:
            query: 查询文本
        
        Returns:
            解析后的查询结构，失败返回 None
        """
        prompt = PARSE_QUERY_PROMPT.format(query=query)
        return self.llm.extract_json(prompt, temperature=0.3)
    
    def understand_image(
        self,
        scene: str = "",
        datetime: str = "",
        location: str = "",
        ocr_text: str = "",
        faces: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        理解图片并提取记忆信息
        
        Args:
            scene: 场景描述
            datetime: 图片时间
            location: 图片地点
            ocr_text: OCR 文字
            faces: 检测到的人物
        
        Returns:
            提取的记忆信息，失败返回 None
        """
        prompt = UNDERSTAND_IMAGE_PROMPT.format(
            scene=scene,
            datetime=datetime,
            location=location,
            ocr_text=ocr_text,
            faces=faces
        )
        return self.llm.extract_json(prompt, temperature=0.3)


# 全局提取器实例
_extractor: Optional[StructuredExtractor] = None


def get_extractor() -> StructuredExtractor:
    """获取结构化提取器实例"""
    global _extractor
    if _extractor is None:
        _extractor = StructuredExtractor()
    return _extractor
