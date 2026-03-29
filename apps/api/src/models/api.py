"""
Universal Agent Memory API Models

REST API v1 request/response models
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime


# ==================== Memory Models ====================

MemoryType = Literal["preference", "note", "dialogue"]
MemoryBehavior = Literal["fact", "preference", "episode"]
MemoryLifespan = Literal["temporary", "short_term", "long_term", "permanent"]


class MemoryCreate(BaseModel):
    """Request to create a new memory"""

    content: str = Field(
        ..., description="Memory content", min_length=1, max_length=100000
    )
    memory_type: MemoryType = Field("preference", description="Type of memory")
    memory_behavior: MemoryBehavior = Field("episode", description="Behavior pattern")
    memory_lifespan: MemoryLifespan = Field("long_term", description="Retention policy")

    # Optional metadata
    event_date: Optional[datetime] = Field(None, description="When the event occurred")
    location_name: Optional[str] = Field(None, description="Location name")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags")

    # Relations
    container_id: Optional[str] = Field(None, description="Container/group ID")
    related_memory_id: Optional[str] = Field(None, description="ID of related memory")

    class Config:
        json_schema_extra = {
            "example": {
                "content": "User prefers dark mode in all applications",
                "memory_type": "preference",
                "memory_behavior": "preference",
                "memory_lifespan": "permanent",
                "tags": ["ui", "preference"],
            }
        }


class MemoryUpdate(BaseModel):
    """Request to update memory metadata"""

    tags: Optional[List[str]] = None
    importance_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    memory_lifespan: Optional[MemoryLifespan] = None
    expiration_date: Optional[datetime] = None


class MemoryResponse(BaseModel):
    """Response for a single memory"""

    id: str
    content: str
    memory_type: MemoryType
    memory_behavior: MemoryBehavior
    memory_lifespan: MemoryLifespan

    # Timestamps
    event_date: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]
    expiration_date: Optional[datetime]

    # Status
    is_latest: bool
    is_expired: bool

    # Metadata
    tags: List[str]
    importance_score: float
    access_count: int
    container_id: Optional[str]

    # Stats
    token_count: int
    chunk_count: int


class MemoryListResponse(BaseModel):
    """Response for listing memories"""

    memories: List[MemoryResponse]
    total: int
    has_more: bool


# ==================== Recall Models ====================


class RecallRequest(BaseModel):
    """Request to recall memories"""

    query: str = Field(..., description="Natural language query", min_length=1)
    limit: int = Field(10, ge=1, le=100, description="Max results")
    min_similarity: float = Field(0.3, ge=0.0, le=1.0, description="Minimum similarity")
    scope: Literal["all", "manual_only", "agent_only"] = Field("all")
    include_expired: bool = Field(False, description="Include expired memories")


class RecallResult(BaseModel):
    """Single recall result"""

    memory_id: str
    content: str
    similarity: float
    memory_type: MemoryType
    created_at: datetime
    source: str


class RecallResponse(BaseModel):
    """Response for recall operation"""

    query: str
    results: List[RecallResult]
    total: int
    recall_mode: str


# ==================== Profile Models ====================


class ProfileResponse(BaseModel):
    """User profile response"""

    user_id: str
    static_facts: Dict[str, Any]
    dynamic_facts: Dict[str, Any]
    preferences: Dict[str, Any]
    source_memory_count: int
    last_rebuilt_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ProfileRefreshResponse(BaseModel):
    """Response for profile refresh"""

    success: bool
    message: str
    source_memory_count: int
    profile: ProfileResponse


# ==================== Container Models ====================


class ContainerCreate(BaseModel):
    """Request to create a container"""

    name: str = Field(..., description="Container name")
    description: Optional[str] = Field(None, description="Container description")
    agent_id: Optional[str] = Field(None, description="Associated agent ID")


class ContainerResponse(BaseModel):
    """Container response"""

    id: str
    name: str
    description: Optional[str]
    agent_id: Optional[str]
    memory_count: int
    created_at: datetime


class ContainerListResponse(BaseModel):
    """Response for listing containers"""

    containers: List[ContainerResponse]
    total: int


# ==================== Relation Models ====================

RelationType = Literal["updates", "extends", "derives", "supersedes", "related_to"]


class MemoryRelationCreate(BaseModel):
    """Request to create a memory relation"""

    source_memory_id: str
    target_memory_id: str
    relation_type: RelationType
    confidence: float = Field(0.8, ge=0.0, le=1.0)


class MemoryRelationResponse(BaseModel):
    """Memory relation response"""

    id: str
    source_memory_id: str
    target_memory_id: str
    relation_type: RelationType
    confidence: float
    detected_by: str
    created_at: datetime


# ==================== Notification Models ====================


class NotificationResponse(BaseModel):
    """Notification response"""

    id: str
    notification_type: str
    memory_id: Optional[str]
    message: str
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Response for listing notifications"""

    notifications: List[NotificationResponse]
    total: int
    unread_count: int


# ==================== Common Models ====================


class ErrorResponse(BaseModel):
    """Error response"""

    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class SuccessResponse(BaseModel):
    """Generic success response"""

    success: bool
    message: str
