"""
记忆数据模型
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class TimeInfo(BaseModel):
    """时间信息"""
    value: Optional[datetime] = None
    source: Optional[str] = None  # extracted/inferred/metadata
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    original_text: Optional[str] = None


class LocationInfo(BaseModel):
    """位置信息"""
    name: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    need_confirm: bool = False
    original_text: Optional[str] = None


class PersonInfo(BaseModel):
    """人物信息"""
    name: str
    person_id: Optional[str] = None
    need_confirm: bool = False
    role: Optional[str] = None
    original_text: Optional[str] = None


class EmotionInfo(BaseModel):
    """情绪信息"""
    value: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class DurationInfo(BaseModel):
    """持续时间信息"""
    value: Optional[str] = None
    source: Optional[str] = None


class TopicInfo(BaseModel):
    """主题信息"""
    main: Optional[str] = None
    keywords: Optional[List[str]] = None


class Attachment(BaseModel):
    """附件"""
    type: str
    path: str
    metadata: Optional[dict] = None


class Memory(BaseModel):
    """记忆数据模型"""
    id: str
    content: str
    input_type: str  # text/image/audio
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
    status: str = "active"  # active/archived/deleted
    
    class Config:
        from_attributes = True


class MemoryCreate(BaseModel):
    """创建记忆请求"""
    content: str
    input_type: str = "text"
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
    status: Optional[str] = None
