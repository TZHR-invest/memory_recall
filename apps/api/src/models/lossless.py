from dataclasses import dataclass, field
from typing import Optional, List, Literal
from datetime import datetime

MemoryType = Literal["preference", "note", "dialogue"]
SummaryKind = Literal["leaf", "condensed"]
ItemType = Literal["message", "summary"]
CompressionLevel = Literal["normal", "aggressive", "fallback"]
MemoryBehavior = Literal["fact", "preference", "episode"]
MemoryLifespan = Literal["temporary", "short_term", "long_term", "permanent"]


@dataclass
class RawMessage:
    memory_type: MemoryType
    content: str
    user_id: str
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    document_id: Optional[str] = None
    role: str = "user"
    token_count: int = 0
    embedding: Optional[List[float]] = None
    time_value: Optional[datetime] = None
    time_source: Optional[str] = None
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    location_latitude: Optional[float] = None
    location_longitude: Optional[float] = None
    people: List[dict] = field(default_factory=list)
    emotion: Optional[dict] = None
    tags: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    source_type: str = "manual"
    input_type: str = "text"
    importance_score: float = 0.5
    id: Optional[str] = None
    created_at: Optional[datetime] = None
    is_archived: bool = False
    event_date: Optional[datetime] = None
    document_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    memory_lifespan: MemoryLifespan = "long_term"
    is_latest: bool = True
    is_expired: bool = False
    container_id: Optional[str] = None
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    memory_behavior: MemoryBehavior = "episode"
    chunk_count: int = 0


@dataclass
class Summary:
    kind: SummaryKind
    content: str
    user_id: str
    agent_id: Optional[str] = None
    depth: int = 0
    token_count: int = 0
    embedding: Optional[List[float]] = None
    earliest_at: Optional[datetime] = None
    latest_at: Optional[datetime] = None
    descendant_count: int = 0
    descendant_token_count: int = 0
    source_message_token_count: int = 0
    document_id: Optional[str] = None
    model: str = "unknown"
    compression_level: CompressionLevel = "normal"
    summary_id: Optional[str] = None
    created_at: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    is_expired: bool = False


@dataclass
class ContextItem:
    user_id: str
    session_id: str
    ordinal: int
    item_type: ItemType
    message_id: Optional[str] = None
    summary_id: Optional[str] = None
    agent_id: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class CompactionResult:
    action_taken: bool
    tokens_before: int
    tokens_after: int
    summary_id: Optional[str] = None
    level: Optional[CompressionLevel] = None
