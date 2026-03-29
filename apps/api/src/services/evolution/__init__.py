from src.services.evolution.user_profile_service import (
    user_profile_service,
    UserProfileService,
    UserProfile,
)
from src.services.evolution.temporal_service import (
    temporal_service,
    TemporalService,
    TemporalInfo,
)
from src.services.evolution.forgetting_service import (
    forgetting_service,
    ForgettingService,
)
from src.services.evolution.chunking_service import (
    chunking_service,
    ChunkingService,
    Chunk,
)
from src.services.evolution.importance_service import (
    importance_service,
    ImportanceService,
    ImportanceFactors,
)
from src.services.evolution.fusion_service import (
    fusion_service,
    FusionService,
)
from src.services.evolution.fact_extraction_service import (
    fact_extraction_service,
    FactExtractionService,
    ExtractedFact,
)
from src.services.evolution.memory_behavior_service import (
    memory_behavior_service,
    MemoryBehaviorService,
    BehaviorConfig,
)
from src.services.evolution.memory_relation_service import (
    memory_relation_service,
    MemoryRelationService,
    MemoryRelation,
    ContradictionResult,
)

__all__ = [
    "user_profile_service",
    "UserProfileService",
    "UserProfile",
    "temporal_service",
    "TemporalService",
    "TemporalInfo",
    "forgetting_service",
    "ForgettingService",
    "chunking_service",
    "ChunkingService",
    "Chunk",
    "importance_service",
    "ImportanceService",
    "ImportanceFactors",
    "fusion_service",
    "FusionService",
    "fact_extraction_service",
    "FactExtractionService",
    "ExtractedFact",
    "memory_behavior_service",
    "MemoryBehaviorService",
    "BehaviorConfig",
    "memory_relation_service",
    "MemoryRelationService",
    "MemoryRelation",
    "ContradictionResult",
]
