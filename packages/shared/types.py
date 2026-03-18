"""
Memory Recall - 共享类型定义
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class InputType(str, Enum):
    """输入类型"""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"


class TimeSource(str, Enum):
    """时间来源"""
    EXTRACTED = "extracted"      # 用户明确说明
    INFERRED = "inferred"        # 大模型推断
    METADATA = "metadata"        # 从图片 EXIF 获取


class MemoryStatus(str, Enum):
    """记忆状态"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


# ========== 时间字段 ==========

class TimeInfo(BaseModel):
    """时间信息"""
    value: Optional[datetime] = None
    source: Optional[TimeSource] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    original_text: Optional[str] = None


# ========== 位置字段 ==========

class LocationInfo(BaseModel):
    """位置信息"""
    name: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    need_confirm: bool = False
    original_text: Optional[str] = None


# ========== 人物字段 ==========

class PersonInfo(BaseModel):
    """人物信息"""
    name: str
    person_id: Optional[str] = None
    need_confirm: bool = False
    role: Optional[str] = None
    original_text: Optional[str] = None


# ========== 情绪字段 ==========

class EmotionInfo(BaseModel):
    """情绪信息"""
    value: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


# ========== 持续时间字段 ==========

class DurationInfo(BaseModel):
    """持续时间信息"""
    value: Optional[str] = None
    source: Optional[str] = None


# ========== 主题字段 ==========

class TopicInfo(BaseModel):
    """主题信息"""
    main: Optional[str] = None
    keywords: Optional[List[str]] = None


# ========== 附件字段 ==========

class Attachment(BaseModel):
    """附件"""
    type: str
    path: str
    metadata: Optional[Dict[str, Any]] = None


# ========== 记忆数据结构 ==========

class Memory(BaseModel):
    """记忆数据结构"""
    id: str
    content: str
    input_type: InputType
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # 核心字段
    time: Optional[TimeInfo] = None
    location: Optional[LocationInfo] = None
    people: Optional[List[PersonInfo]] = None
    
    # 可选字段
    emotion: Optional[EmotionInfo] = None
    tags: Optional[List[str]] = None
    duration: Optional[DurationInfo] = None
    topic: Optional[TopicInfo] = None
    attachments: Optional[List[Attachment]] = None
    
    # 向量
    embedding: Optional[List[float]] = None
    
    # 系统管理
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    status: MemoryStatus = MemoryStatus.ACTIVE


class MemoryCreate(BaseModel):
    """创建记忆请求"""
    content: str
    input_type: InputType = InputType.TEXT
    time: Optional[TimeInfo] = None
    location: Optional[LocationInfo] = None
    people: Optional[List[PersonInfo]] = None
    emotion: Optional[EmotionInfo] = None
    tags: Optional[List[str]] = None
    duration: Optional[DurationInfo] = None
    topic: Optional[TopicInfo] = None
    attachments: Optional[List[Attachment]] = None


class MemoryUpdate(BaseModel):
    """更新记忆请求"""
    content: Optional[str] = None
    time: Optional[TimeInfo] = None
    location: Optional[LocationInfo] = None
    people: Optional[List[PersonInfo]] = None
    emotion: Optional[EmotionInfo] = None
    tags: Optional[List[str]] = None
    duration: Optional[DurationInfo] = None
    topic: Optional[TopicInfo] = None
    importance_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    status: Optional[MemoryStatus] = None


# ========== 人物档案数据结构 ==========

class PersonProfile(BaseModel):
    """人物档案"""
    id: str
    name: str
    aliases: Optional[List[str]] = None
    relationship: Optional[str] = None
    first_mentioned: Optional[datetime] = None
    last_mentioned: Optional[datetime] = None
    mention_count: int = 0
    profile: Optional[Dict[str, Any]] = None
    interactions: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class PersonCreate(BaseModel):
    """创建人物请求"""
    name: str
    aliases: Optional[List[str]] = None
    relationship: Optional[str] = None
    profile: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


# ========== 人脸特征数据结构 ==========

class FaceBox(BaseModel):
    """人脸框"""
    x: int
    y: int
    width: int
    height: int


class Landmark(BaseModel):
    """面部关键点"""
    x: int
    y: int


class FaceFeature(BaseModel):
    """人脸特征"""
    id: str
    person_id: Optional[str] = None
    image_path: str
    face_box: Optional[FaceBox] = None
    landmarks: Optional[List[Landmark]] = None
    embedding: Optional[List[float]] = None  # 128 维向量
    quality_score: Optional[float] = None
    blur_score: Optional[float] = None
    brightness: Optional[float] = None
    created_at: datetime
    source_memory: Optional[str] = None


# ========== 召回相关 ==========

class RecallRequest(BaseModel):
    """召回请求"""
    query: str
    time_range: Optional[tuple] = None
    location: Optional[str] = None
    people: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    top_k: int = 10


class RecallResult(BaseModel):
    """召回结果"""
    memory_id: str
    memory: Memory
    score: float
    matched_fields: List[str] = []


# ========== 响应模型 ==========

class ApiResponse(BaseModel):
    """API 响应"""
    code: int = 200
    message: str = "success"
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """错误响应"""
    code: int
    message: str
    error: Optional[str] = None
