"""
图片处理器
支持图片上传、EXIF 提取、多模态 Embedding、图片内容理解
"""
import os
import uuid
import shutil
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
from pathlib import Path

from .exif import EXIFExtractor
from ..config import settings
from ..llm.client import get_llm_client
from ..embedding.client import get_embedding_client

logger = logging.getLogger(__name__)


class ImageProcessor:
    """图片处理器"""
    
    def __init__(self):
        """初始化图片处理器"""
        self.storage_path = Path(settings.STORAGE_PATH)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 支持的图片格式
        self.supported_formats = {".jpg", ".jpeg", ".png", ".webp"}
        
        # 最大文件大小（10MB）
        self.max_file_size = 10 * 1024 * 1024
    
    def validate_image(self, file_path: str) -> Dict[str, Any]:
        """
        验证图片文件
        
        Args:
            file_path: 文件路径
        
        Returns:
            验证结果 {"valid": bool, "error": str}
        """
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return {"valid": False, "error": "文件不存在"}
        
        # 检查文件大小
        file_size = os.path.getsize(file_path)
        if file_size > self.max_file_size:
            return {"valid": False, "error": f"文件大小超过限制（最大 {self.max_file_size / 1024 / 1024}MB）"}
        
        # 检查文件格式
        file_ext = Path(file_path).suffix.lower()
        if file_ext not in self.supported_formats:
            return {"valid": False, "error": f"不支持的文件格式（支持: {', '.join(self.supported_formats)}）"}
        
        return {"valid": True, "error": None}
    
    def save_image(self, file_path: str, user_id: Optional[str] = None) -> str:
        """
        保存图片到存储路径
        
        Args:
            file_path: 临时文件路径
            user_id: 用户 ID（可选）
        
        Returns:
            存储路径
        """
        # 生成唯一文件名
        file_ext = Path(file_path).suffix.lower()
        filename = f"{uuid.uuid4().hex}{file_ext}"
        
        # 创建存储目录
        if user_id:
            save_dir = self.storage_path / user_id / "images"
        else:
            save_dir = self.storage_path / "images"
        
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 复制文件
        save_path = save_dir / filename
        shutil.copy2(file_path, str(save_path))
        
        logger.info(f"图片已保存: {save_path}")
        return str(save_path)
    
    def extract_exif(self, image_path: str) -> Dict[str, Any]:
        """
        提取 EXIF 信息
        
        Args:
            image_path: 图片路径
        
        Returns:
            EXIF 信息
        """
        return EXIFExtractor.extract(image_path)
    
    def generate_image_url(self, image_path: str) -> str:
        """
        生成图片访问 URL
        
        注意：这里返回的是 base64 编码的图片
        火山引擎 API 只支持 base64、http 或 https URL
        
        Args:
            image_path: 图片路径
        
        Returns:
            图片 base64 URL (data:image/jpeg;base64,...)
        """
        import base64
        
        # 读取图片并转换为 base64
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        # 获取图片格式
        file_ext = Path(image_path).suffix.lower()
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp"
        }.get(file_ext, "image/jpeg")
        
        # 转换为 base64
        base64_data = base64.b64encode(image_data).decode("utf-8")
        
        # 返回 data URL
        return f"data:{mime_type};base64,{base64_data}"
    
    def get_image_embedding(self, image_path: str, text: Optional[str] = None) -> Optional[List[float]]:
        """
        生成图片的向量表示
        
        Args:
            image_path: 图片路径
            text: 可选的文本描述
        
        Returns:
            向量列表，失败返回 None
        """
        try:
            # 生成图片 URL
            image_url = self.generate_image_url(image_path)
            
            # 获取 Embedding 客户端
            embedding_client = get_embedding_client()
            
            # 调用多模态 Embedding API
            embedding = embedding_client.embed_image(image_url, text)
            
            if embedding:
                logger.info(f"成功生成图片 Embedding，维度: {len(embedding)}")
            else:
                logger.warning(f"图片 Embedding 生成失败")
            
            return embedding
        except Exception as e:
            logger.error(f"生成图片 Embedding 失败: {e}")
            return None
    
    def understand_image(self, image_path: str) -> Dict[str, Any]:
        """
        使用 LLM 理解图片内容
        
        Args:
            image_path: 图片路径
        
        Returns:
            图片内容信息：
            - scene: 场景描述
            - objects: 物体列表
            - people: 人物信息
            - emotion: 情绪
            - activities: 活动
            - text: OCR 文字（如果有）
        """
        try:
            # 获取 LLM 客户端
            llm_client = get_llm_client()
            
            # 构造提示词
            system_prompt = """你是一个专业的图像理解助手。请分析图片内容并提取以下信息：

1. **场景描述**：图片的整体场景和氛围
2. **主要物体**：图片中的主要物体和元素
3. **人物信息**：如果有人物，描述他们的数量、性别、年龄段、动作等
4. **情绪氛围**：图片传达的情绪和氛围
5. **活动内容**：图片中正在进行的活动
6. **文字信息**：图片中的文字内容（如果有）

请以 JSON 格式返回结果：
```json
{
  "scene": "场景描述",
  "objects": ["物体1", "物体2"],
  "people": {
    "count": 人数,
    "description": "人物描述"
  },
  "emotion": "情绪",
  "activities": ["活动1", "活动2"],
  "text": "文字内容"
}
```"""
            
            # 生成图片 URL（base64 格式）
            image_url = self.generate_image_url(image_path)
            
            # 构造消息（图片 + 文本）
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请分析这张图片的内容"
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url}
                        }
                    ]
                }
            ]
            
            # 调用 LLM API
            response = llm_client.chat(messages, temperature=0.3)
            
            # 解析响应
            result = self._parse_image_understanding(response)
            
            logger.info(f"图片内容理解完成: {result}")
            return result
            
        except Exception as e:
            logger.error(f"图片内容理解失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "scene": None,
                "objects": [],
                "people": {},
                "emotion": None,
                "activities": [],
                "text": None,
                "error": str(e)
            }
    
    def _parse_image_understanding(self, response: str) -> Dict[str, Any]:
        """
        解析图片理解响应
        
        Args:
            response: LLM 响应文本
        
        Returns:
            结构化的图片信息
        """
        import json
        
        result = {
            "scene": None,
            "objects": [],
            "people": {},
            "emotion": None,
            "activities": [],
            "text": None
        }
        
        try:
            # 尝试直接解析 JSON
            parsed = json.loads(response)
            result.update(parsed)
        except json.JSONDecodeError:
            # 尝试提取 JSON 代码块
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
                try:
                    parsed = json.loads(json_str)
                    result.update(parsed)
                except:
                    pass
        
        return result
    
    def process_image(
        self,
        file_path: str,
        user_id: Optional[str] = None,
        extract_exif: bool = True,
        generate_embedding: bool = True,
        understand_content: bool = True
    ) -> Dict[str, Any]:
        """
        完整处理图片
        
        Args:
            file_path: 临时文件路径
            user_id: 用户 ID（可选）
            extract_exif: 是否提取 EXIF 信息
            generate_embedding: 是否生成 Embedding
            understand_content: 是否理解图片内容
        
        Returns:
            处理结果：
            - success: 是否成功
            - image_path: 存储路径
            - exif: EXIF 信息
            - embedding: 向量
            - understanding: 内容理解
            - error: 错误信息
        """
        result = {
            "success": False,
            "image_path": None,
            "exif": None,
            "embedding": None,
            "understanding": None,
            "error": None
        }
        
        try:
            # 1. 验证图片
            validation = self.validate_image(file_path)
            if not validation["valid"]:
                result["error"] = validation["error"]
                return result
            
            # 2. 保存图片
            image_path = self.save_image(file_path, user_id)
            result["image_path"] = image_path
            
            # 3. 提取 EXIF 信息
            if extract_exif:
                result["exif"] = self.extract_exif(image_path)
            
            # 4. 生成 Embedding
            if generate_embedding:
                # 如果有内容理解，使用理解结果作为文本
                text = None
                if understand_content:
                    understanding = self.understand_image(image_path)
                    result["understanding"] = understanding
                    
                    # 构造文本描述
                    if understanding.get("scene"):
                        text = understanding["scene"]
                        if understanding.get("objects"):
                            text += f"，包含：{', '.join(understanding['objects'][:5])}"
                
                result["embedding"] = self.get_image_embedding(image_path, text)
            
            # 5. 如果只理解内容
            elif understand_content:
                result["understanding"] = self.understand_image(image_path)
            
            result["success"] = True
            logger.info(f"图片处理完成: {image_path}")
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"图片处理失败: {e}")
        
        return result


# 全局图片处理器实例
_image_processor: Optional[ImageProcessor] = None


def get_image_processor() -> ImageProcessor:
    """获取图片处理器实例"""
    global _image_processor
    if _image_processor is None:
        _image_processor = ImageProcessor()
    return _image_processor
