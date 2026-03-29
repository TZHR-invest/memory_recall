"""
Notification Endpoints

GET  /v1/notifications           - List notifications
POST /v1/notifications/{id}/read - Mark as read
"""

from fastapi import APIRouter, Depends
from datetime import datetime

from ...models.api import NotificationResponse, NotificationListResponse
from ..auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List Notifications",
    description="List user notifications",
)
async def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """List notifications for user"""
    from src.database import db

    user_id = current_user["user_id"]

    if unread_only:
        rows = await db.fetch(
            """
            SELECT * FROM notifications
            WHERE user_id = $1 AND is_read = FALSE
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
    else:
        rows = await db.fetch(
            """
            SELECT * FROM notifications
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )

    unread_count = await db.fetchval(
        """
        SELECT COUNT(*) FROM notifications
        WHERE user_id = $1 AND is_read = FALSE
        """,
        user_id,
    )

    return NotificationListResponse(
        notifications=[
            NotificationResponse(
                id=row["id"],
                notification_type=row["notification_type"],
                memory_id=row["memory_id"],
                message=row["message"],
                is_read=row["is_read"],
                created_at=row["created_at"],
            )
            for row in rows
        ],
        total=len(rows),
        unread_count=unread_count or 0,
    )


@router.post(
    "/{notification_id}/read",
    summary="Mark as Read",
    description="Mark a notification as read",
)
async def mark_as_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Mark notification as read"""
    from src.database import db

    user_id = current_user["user_id"]

    await db.execute(
        """
        UPDATE notifications
        SET is_read = TRUE, read_at = NOW()
        WHERE id = $1 AND user_id = $2
        """,
        notification_id,
        user_id,
    )

    return {
        "success": True,
        "message": f"Notification {notification_id} marked as read",
    }


@router.post(
    "/read-all",
    summary="Mark All as Read",
    description="Mark all notifications as read",
)
async def mark_all_as_read(
    current_user: dict = Depends(get_current_user),
):
    """Mark all notifications as read"""
    from src.database import db

    user_id = current_user["user_id"]

    result = await db.execute(
        """
        UPDATE notifications
        SET is_read = TRUE, read_at = NOW()
        WHERE user_id = $1 AND is_read = FALSE
        """,
        user_id,
    )

    return {"success": True, "message": f"{result} notifications marked as read"}
