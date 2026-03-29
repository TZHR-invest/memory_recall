"""
Container Endpoints

POST   /v1/containers           - Create container
GET    /v1/containers           - List containers
DELETE /v1/containers/{id}      - Delete container
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import uuid

from ...models.api import ContainerCreate, ContainerResponse, ContainerListResponse
from ..auth import get_current_user, require_permission

router = APIRouter(prefix="/containers", tags=["Containers"])


@router.post(
    "",
    response_model=ContainerResponse,
    summary="Create Container",
    description="Create a new memory container",
)
async def create_container(
    request: ContainerCreate,
    current_user: dict = Depends(require_permission("write")),
):
    """
    Create a memory container

    Containers group memories together (e.g., per agent, per session).
    """
    from src.database import db

    user_id = current_user["user_id"]
    container_id = f"cnt_{uuid.uuid4().hex[:16]}"
    now = datetime.utcnow()

    await db.execute(
        """
        INSERT INTO raw_messages (id, user_id, content, memory_type, container_id, created_at)
        SELECT $1, $2, $3, 'note', $4, $5
        WHERE NOT EXISTS (
            SELECT 1 FROM raw_messages WHERE id = $1
        )
        """,
        container_id,
        user_id,
        request.name,
        container_id,
        now,
    )

    return ContainerResponse(
        id=container_id,
        name=request.name,
        description=request.description,
        agent_id=request.agent_id,
        memory_count=0,
        created_at=now,
    )


@router.get(
    "",
    response_model=ContainerListResponse,
    summary="List Containers",
    description="List all containers for user",
)
async def list_containers(
    current_user: dict = Depends(get_current_user),
):
    """List all containers"""
    from src.database import db

    user_id = current_user["user_id"]

    rows = await db.fetch(
        """
        SELECT DISTINCT container_id, COUNT(*) as memory_count
        FROM raw_messages
        WHERE user_id = $1 AND container_id IS NOT NULL
        GROUP BY container_id
        ORDER BY memory_count DESC
        """,
        user_id,
    )

    containers = [
        ContainerResponse(
            id=row["container_id"],
            name=row["container_id"],
            description=None,
            agent_id=None,
            memory_count=row["memory_count"],
            created_at=None,
        )
        for row in rows
    ]

    return ContainerListResponse(
        containers=containers,
        total=len(containers),
    )


@router.delete(
    "/{container_id}",
    summary="Delete Container",
    description="Delete a container (memories are not deleted)",
)
async def delete_container(
    container_id: str,
    current_user: dict = Depends(require_permission("delete")),
):
    """Delete container (memories keep their container_id but container is dissolved)"""
    from src.database import db

    user_id = current_user["user_id"]

    result = await db.execute(
        """
        UPDATE raw_messages
        SET container_id = NULL
        WHERE user_id = $1 AND container_id = $2
        """,
        user_id,
        container_id,
    )

    return {
        "success": True,
        "message": f"Container {container_id} dissolved, {result} memories unassigned",
    }
