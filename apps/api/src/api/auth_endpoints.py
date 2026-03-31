"""
API Key Management Endpoints

POST /v1/auth/api-keys          - Create a new API key
GET  /v1/auth/api-keys          - List user's API keys
DELETE /v1/auth/api-keys/{id}   - Revoke an API key
POST /v1/auth/initialize        - Register new user (dev mode allows multiple)
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import os

from src.api.auth import (
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


class InitializePluginRequest(BaseModel):
    plugin_name: str = Field(
        "memory-recall-plugin",
        description="Name for the API key",
        examples=["opencode-plugin", "openclaw-plugin"],
    )
    user_name: str = Field(
        ...,
        description="Human-readable name for the user (e.g., 'John Doe', 'alice')",
        examples=["John Doe", "alice", "my-project"],
    )
    permissions: List[str] = Field(
        ["read", "write", "delete", "admin"],
        description="Permissions for the API key",
    )


class InitializePluginResponse(BaseModel):
    api_key: str = Field(..., description="The generated API key (shown only once)")
    key_id: str = Field(..., description="The API key ID (used as container_tag)")
    user_id: str = Field(..., description="The user_id associated with this key")
    user_name: str = Field(..., description="The user_name you specified")
    container_tag: str = Field(
        ...,
        description="Your container_tag (same as key_id). One API key = one container.",
    )
    config_example: Dict[str, Any] = Field(
        ..., description="Example config for the plugin"
    )


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


@router.post(
    "/initialize",
    response_model=InitializePluginResponse,
    summary="Initialize Plugin",
    description="""Create an API key for setup.

**Development Mode** (APP_ENV=development):
- Allows multiple users to register without admin key
- Each user gets their own API key and container

**Production Mode** (APP_ENV=production):
- Only allows first-time registration
- Subsequent registrations require admin API key

**One API Key = One Container**:
- Each API key has a unique container_tag (the key's ID)
- All memories created with this key are stored in that container
""",
)
async def initialize_plugin(request: InitializePluginRequest):
    auth_service = AuthService()
    from src.database import db

    app_env = os.getenv("APP_ENV", "development")
    is_dev_mode = app_env in ("development", "dev", "test")

    existing_keys = await db.fetch(
        "SELECT id FROM api_keys WHERE is_active = TRUE LIMIT 1"
    )

    if len(existing_keys) > 0 and not is_dev_mode:
        raise HTTPException(
            status_code=403,
            detail="API keys already exist. Use /auth/api-keys with admin authentication instead.",
        )

    user_id = request.user_name.lower().replace(" ", "-")

    # In dev mode, append suffix if user_id already exists
    if is_dev_mode and len(existing_keys) > 0:
        existing_user = await db.fetchrow(
            "SELECT id FROM api_keys WHERE user_id = $1 AND is_active = TRUE", user_id
        )
        if existing_user:
            import uuid

            user_id = f"{user_id}-{uuid.uuid4().hex[:8]}"

    try:
        result = await auth_service.create_key(
            user_id=user_id,
            user_name=request.user_name,
            name=request.plugin_name,
            permissions=request.permissions,
            is_test=False,
        )

        return InitializePluginResponse(
            api_key=result.key,
            key_id=result.id,
            user_id=user_id,
            user_name=request.user_name,
            container_tag=result.id,
            config_example={
                "apiKey": result.key,
                "baseUrl": "http://localhost:8000",
                "userName": request.user_name,
                "similarityThreshold": 0.6,
                "maxMemories": 5,
                "maxProjectMemories": 10,
                "injectProfile": True,
                "compactionThreshold": 0.8,
                "enableSummaryCapture": True,
                "enableDocumentTracking": True,
                "trackedDocPatterns": ["README*.md", "docs/*.md", "AGENTS.md"],
                "language": "auto",
                "logLevel": "info",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
