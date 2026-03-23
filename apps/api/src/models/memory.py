from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator


TimePeriod = Literal["morning", "afternoon", "evening", "night"]


class TimeInfo(BaseModel):
    value: Optional[datetime] = None
    period: Optional[TimePeriod] = None
    source: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class LocationInfo(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    need_confirm: bool = False


class PersonInfo(BaseModel):
    name: str
    person_id: Optional[str] = None
    need_confirm: bool = False
    role: Optional[str] = None


class EmotionInfo(BaseModel):
    type: Optional[str] = None
    intensity: Optional[int] = Field(None, ge=1, le=10)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class DurationInfo(BaseModel):
    value: Optional[int] = None
    unit: Optional[str] = None
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

    # 关键事件
    key_events: Optional[List[str]] = None

    # 分段存储（用于长文本）
    segment_ids: Optional[List[str]] = None  # 分段记忆 ID 列表
    file_name: Optional[str] = None  # 文件名
    file_size: Optional[int] = None  # 文件大小（字节）
    segment_count: Optional[int] = None  # 分段数量

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

    # 关键事件
    key_events: Optional[List[str]] = None

    emotion: Optional[EmotionInfo] = None
    tags: Optional[List[str]] = None
    duration: Optional[DurationInfo] = None
    topic: Optional[TopicInfo] = None
    attachments: Optional[List[Attachment]] = None
    embedding: Optional[List[float]] = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        """验证内容不能为空"""
        if not v or not v.strip():
            raise ValueError("内容不能为空")
        return v.strip()  # 返回去除首尾空白的内容


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
