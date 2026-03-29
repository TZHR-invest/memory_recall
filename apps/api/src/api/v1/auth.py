"""
API Key Management Endpoints

POST /v1/auth/api-keys          - Create a new API key
GET  /v1/auth/api-keys          - List user's API keys
DELETE /v1/auth/api-keys/{id}   - Revoke an API key
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from ..auth import (
    AuthService,
    APIKeyCreate,
    APIKeyResponse,
    APIKeyCreated,
    get_current_user,
    require_permission,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class CreateAPIKeyRequest(BaseModel):
    name: Optional[str] = Field(None, description="Friendly name for the key")
    permissions: List[str] = Field(
        ["read"], description="Permission level: read, write, delete, admin"
    )
    is_test: bool = Field(False, description="Whether this is a test key")
    expires_in_days: Optional[int] = Field(None, description="Key expiration in days")


class APIKeyListResponse(BaseModel):
    keys: List[APIKeyResponse]
    total: int


class RevokeKeyResponse(BaseModel):
    success: bool
    message: str


@router.post(
    "/api-keys",
    response_model=APIKeyCreated,
    summary="Create API Key",
    description="Create a new API key for authentication",
)
async def create_api_key(
    request: CreateAPIKeyRequest,
    current_user: dict = Depends(require_permission("admin")),
):
    auth_service = AuthService()

    try:
        result = await auth_service.create_key(
            user_id=current_user["user_id"],
            name=request.name,
            permissions=request.permissions,
            is_test=request.is_test,
            expires_in_days=request.expires_in_days,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/api-keys",
    response_model=APIKeyListResponse,
    summary="List API Keys",
    description="List all API keys for the current user",
)
async def list_api_keys(
    current_user: dict = Depends(get_current_user),
):
    auth_service = AuthService()
    keys = await auth_service.list_keys(current_user["user_id"])

    return APIKeyListResponse(
        keys=keys,
        total=len(keys),
    )


@router.delete(
    "/api-keys/{key_id}",
    response_model=RevokeKeyResponse,
    summary="Revoke API Key",
    description="Revoke an API key",
)
async def revoke_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user),
):
    auth_service = AuthService()
    success = await auth_service.revoke_key(key_id, current_user["user_id"])

    if not success:
        raise HTTPException(status_code=404, detail="API Key not found")

    return RevokeKeyResponse(
        success=True,
        message=f"API Key {key_id} has been revoked",
    )
