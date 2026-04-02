from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List

from src.embedding.client import get_embedding_client
from src.api.auth import require_permission

router = APIRouter(tags=["Embeddings"])


class EmbedRequest(BaseModel):
    texts: List[str] = Field(
        ...,
        description="List of texts to embed (max 50)",
        examples=[["我叫张三", "我的名字是张三"]],
    )


class EmbedResponse(BaseModel):
    embeddings: List[List[float]] = Field(..., description="List of embedding vectors")
    dimension: int = Field(..., description="Embedding dimension")
    count: int = Field(..., description="Number of embeddings")


@router.post("/embed", response_model=EmbedResponse)
async def create_embeddings(
    request: EmbedRequest,
    _: None = Depends(require_permission("read")),
):
    if len(request.texts) == 0:
        raise HTTPException(status_code=400, detail="texts cannot be empty")

    if len(request.texts) > 50:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum 50 texts per batch, got {len(request.texts)}",
        )

    client = get_embedding_client()
    embeddings = await client.embed_batch(request.texts)

    if embeddings is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to compute embeddings",
        )

    return EmbedResponse(
        embeddings=embeddings,
        dimension=len(embeddings[0]) if embeddings else 0,
        count=len(embeddings),
    )
