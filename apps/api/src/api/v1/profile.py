"""
Profile Endpoints

GET  /v1/profile         - Get user profile
POST /v1/profile/refresh - Force refresh profile
"""

from fastapi import APIRouter, Depends
from datetime import datetime

from ...models.api import ProfileResponse, ProfileRefreshResponse
from ..auth import get_current_user

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get(
    "",
    response_model=ProfileResponse,
    summary="Get User Profile",
    description="Get aggregated user profile with facts and preferences",
)
async def get_profile(
    current_user: dict = Depends(get_current_user),
):
    """
    Get user profile

    Returns static facts, dynamic facts, and preferences aggregated from memories.
    Target: ~50ms response time.
    """
    from src.database import db

    user_id = current_user["user_id"]

    row = await db.fetchrow(
        """
        SELECT * FROM user_profiles WHERE user_id = $1
        """,
        user_id,
    )

    if not row:
        return ProfileResponse(
            user_id=user_id,
            static_facts={},
            dynamic_facts={},
            preferences={},
            source_memory_count=0,
            last_rebuilt_at=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    return ProfileResponse(
        user_id=row["user_id"],
        static_facts=row["static_facts"] or {},
        dynamic_facts=row["dynamic_facts"] or {},
        preferences=row["preferences"] or {},
        source_memory_count=row["source_memory_count"] or 0,
        last_rebuilt_at=row["last_rebuilt_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post(
    "/refresh",
    response_model=ProfileRefreshResponse,
    summary="Refresh Profile",
    description="Force rebuild user profile from memories",
)
async def refresh_profile(
    current_user: dict = Depends(get_current_user),
):
    """
    Force refresh user profile

    Rebuilds profile from all user memories.
    May take a few seconds for users with many memories.
    """
    from src.database import db
    from src.services.core.lossless_recall_service import lossless_recall_service

    user_id = current_user["user_id"]
    db.set_current_user(user_id)

    memories = await lossless_recall_service.hybrid_recall(
        query="",  # Get all
        user_id=user_id,
        scope="manual_only",
        limit=1000,
        min_similarity=0.0,
    )

    static_facts = {}
    dynamic_facts = {}
    preferences = {}

    for memory in memories:
        content = memory.get("content", "")
        memory_behavior = memory.get("memory_behavior", "episode")

        if memory_behavior == "fact":
            static_facts[f"fact_{len(static_facts)}"] = content
        elif memory_behavior == "preference":
            preferences[f"pref_{len(preferences)}"] = content
        else:
            dynamic_facts[f"event_{len(dynamic_facts)}"] = content

    now = datetime.utcnow()

    await db.execute(
        """
        INSERT INTO user_profiles (user_id, static_facts, dynamic_facts, preferences, source_memory_count, last_rebuilt_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (user_id) DO UPDATE SET
            static_facts = $2,
            dynamic_facts = $3,
            preferences = $4,
            source_memory_count = $5,
            last_rebuilt_at = $6,
            updated_at = $7,
            is_dirty = FALSE
        """,
        user_id,
        static_facts,
        dynamic_facts,
        preferences,
        len(memories),
        now,
        now,
    )

    return ProfileRefreshResponse(
        success=True,
        message=f"Profile rebuilt from {len(memories)} memories",
        source_memory_count=len(memories),
        profile=ProfileResponse(
            user_id=user_id,
            static_facts=static_facts,
            dynamic_facts=dynamic_facts,
            preferences=preferences,
            source_memory_count=len(memories),
            last_rebuilt_at=now,
            created_at=now,
            updated_at=now,
        ),
    )
