from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Set
from datetime import datetime

from src.services.core.memory_store import memory_store
from src.api.auth import (
    require_permission,
    check_rate_limit,
    verify_container_ownership,
)

router = APIRouter(tags=["Knowledge Graph"])


class GraphNode(BaseModel):
    id: str = Field(..., description="Memory ID")
    type: str = Field(default="memory", description="Node type (always 'memory')")
    content: str = Field(..., description="Memory content")
    is_static: bool = Field(..., description="Whether it's a static fact")
    is_latest: bool = Field(..., description="Whether it's the latest version")
    is_inference: bool = Field(
        default=False, description="Whether it's an inferred memory"
    )
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    entities: Optional[Dict[str, List[str]]] = Field(
        None, description="Extracted entities"
    )


class GraphEdge(BaseModel):
    source: str = Field(..., description="Source memory ID")
    target: str = Field(..., description="Target memory ID")
    type: str = Field(..., description="Relation type (updates/extends/derives)")
    confidence: float = Field(..., description="Relation confidence score")


class GraphResponse(BaseModel):
    nodes: List[GraphNode] = Field(..., description="Graph nodes")
    edges: List[GraphEdge] = Field(..., description="Graph edges")
    total_count: int = Field(..., description="Total node count")
    has_more: bool = Field(..., description="More data available")


@router.get(
    "/graph",
    response_model=GraphResponse,
    summary="Get knowledge graph",
    description="Returns nodes and edges for graph visualization. Uses embedded relations for O(1) edge computation.",
    responses={
        200: {
            "description": "Knowledge graph data",
            "content": {
                "application/json": {
                    "example": {
                        "nodes": [
                            {
                                "id": "mem_abc",
                                "type": "memory",
                                "content": "我喜欢喝咖啡",
                                "is_static": True,
                                "is_latest": True,
                                "is_inference": False,
                                "created_at": "2024-01-15T10:30:00",
                                "entities": {"preference": ["喝咖啡"]},
                            }
                        ],
                        "edges": [
                            {
                                "source": "mem_def",
                                "target": "mem_abc",
                                "type": "updates",
                                "confidence": 0.9,
                            }
                        ],
                        "total_count": 1,
                        "has_more": False,
                    }
                }
            },
        }
    },
)
async def get_graph(
    container_tag: str = Query(..., description="Container tag (required)"),
    limit: int = Query(100, ge=1, le=500, description="Max nodes to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    entity_types: Optional[str] = Query(
        None, description="Filter by entity types (comma-separated)"
    ),
    is_static: Optional[bool] = Query(None, description="Filter by static/dynamic"),
    date_from: Optional[str] = Query(None, description="Filter from date (ISO format)"),
    date_to: Optional[str] = Query(None, description="Filter to date (ISO format)"),
    current_user: Dict = Depends(require_permission("read")),
    _: Dict = Depends(check_rate_limit),
):
    verify_container_ownership(container_tag, current_user["key_id"])

    entity_type_filter = None
    if entity_types:
        entity_type_filter = [t.strip() for t in entity_types.split(",")]

    date_filter = None
    if date_from:
        try:
            date_filter = {
                "from": datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            }
            if date_to:
                date_filter["to"] = datetime.fromisoformat(
                    date_to.replace("Z", "+00:00")
                )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")

    memories = await memory_store.get_by_container(
        container_tag=container_tag,
        limit=limit + 1,
        include_forgotten=False,
    )

    if offset > 0:
        memories = memories[offset:]

    filtered_memories = []
    for m in memories:
        if is_static is not None and m.is_static != is_static:
            continue

        if entity_type_filter:
            entities = m.metadata.get("entities", {})
            if not any(et in entities for et in entity_type_filter):
                continue

        if date_filter:
            if m.created_at:
                if "from" in date_filter and m.created_at < date_filter["from"]:
                    continue
                if "to" in date_filter and m.created_at > date_filter["to"]:
                    continue

        filtered_memories.append(m)

    has_more = len(filtered_memories) > limit
    if has_more:
        filtered_memories = filtered_memories[:limit]

    nodes = []
    edges = []
    seen_edges: Set[tuple] = set()

    for m in filtered_memories:
        entities = m.metadata.get("entities")

        nodes.append(
            GraphNode(
                id=m.id,
                type="memory",
                content=m.content,
                is_static=m.is_static,
                is_latest=m.is_latest,
                is_inference=m.is_inference,
                created_at=m.created_at.isoformat() if m.created_at else None,
                entities=entities if entities else None,
            )
        )

        relations = m.metadata.get("relations", {})
        for rel_type, target_ids in relations.items():
            for target_id in target_ids:
                edge_key = (m.id, target_id, rel_type)
                if edge_key not in seen_edges:
                    edges.append(
                        GraphEdge(
                            source=m.id,
                            target=target_id,
                            type=rel_type,
                            confidence=m.confidence,
                        )
                    )
                    seen_edges.add(edge_key)

    return GraphResponse(
        nodes=nodes,
        edges=edges,
        total_count=len(filtered_memories),
        has_more=has_more,
    )
