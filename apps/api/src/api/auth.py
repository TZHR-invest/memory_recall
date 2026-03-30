"""
API Key Authentication Service

Features:
- API Key generation (rk_live_xxx, rk_test_xxx)
- Key validation and hashing
- Permission checking
- Rate limiting
"""

import secrets
import hashlib
import hmac
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from pydantic import BaseModel
from fastapi import HTTPException, Depends, Request
from fastapi.security import APIKeyHeader

# Constants
KEY_PREFIX_LIVE = "rk_live_"
KEY_PREFIX_TEST = "rk_test_"
KEY_LENGTH = 32  # Random part length

# Permission levels
PERMISSIONS = {
    "read": ["read"],
    "write": ["read", "write"],
    "delete": ["read", "write", "delete"],
    "admin": ["read", "write", "delete", "admin"],
}


@dataclass
class APIKey:
    id: str
    user_id: str
    user_name: Optional[str]
    key_hash: str
    key_prefix: str
    name: Optional[str]
    permissions: List[str]
    is_active: bool
    is_test: bool
    last_used_at: Optional[datetime]
    usage_count: int
    expires_at: Optional[datetime]
    created_at: datetime
    revoked_at: Optional[datetime]


class APIKeyCreate(BaseModel):
    name: Optional[str] = None
    permissions: List[str] = ["read"]
    is_test: bool = False
    expires_in_days: Optional[int] = None


class APIKeyResponse(BaseModel):
    id: str
    name: Optional[str]
    key_prefix: str
    permissions: List[str]
    is_test: bool
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    usage_count: int


class APIKeyCreated(BaseModel):
    id: str
    key: str  # Full key (only shown once)
    name: Optional[str]
    key_prefix: str
    permissions: List[str]
    is_test: bool
    created_at: datetime
    expires_at: Optional[datetime]


class AuthService:
    """API Key Authentication Service"""

    def __init__(self):
        from src.database import db

        self.db = db

    def _generate_key(self, is_test: bool = False) -> tuple[str, str, str]:
        """Generate a new API key. Returns (full_key, prefix, hash)"""
        prefix = KEY_PREFIX_TEST if is_test else KEY_PREFIX_LIVE
        random_part = secrets.token_hex(KEY_LENGTH)
        full_key = f"{prefix}{random_part}"
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        return full_key, prefix, key_hash

    def _hash_key(self, key: str) -> str:
        """Hash an API key"""
        return hashlib.sha256(key.encode()).hexdigest()

    async def create_key(
        self,
        user_id: str,
        user_name: Optional[str] = None,
        name: Optional[str] = None,
        permissions: List[str] = ["read"],
        is_test: bool = False,
        expires_in_days: Optional[int] = None,
    ) -> APIKeyCreated:
        """Create a new API key"""
        import uuid

        full_key, prefix, key_hash = self._generate_key(is_test)

        # Validate permissions
        valid_perms = set()
        for perm in permissions:
            if perm in PERMISSIONS:
                valid_perms.update(PERMISSIONS[perm])

        # Calculate expiration
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        key_id = str(uuid.uuid4())
        now = datetime.utcnow()

        await self.db.execute(
            """
            INSERT INTO api_keys (
                id, user_id, user_name, key_hash, key_prefix, name, 
                permissions, is_active, is_test, expires_at, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            key_id,
            user_id,
            user_name,
            key_hash,
            prefix,
            name,
            list(valid_perms),
            True,
            is_test,
            expires_at,
            now,
        )

        return APIKeyCreated(
            id=key_id,
            key=full_key,
            name=name,
            key_prefix=prefix,
            permissions=list(valid_perms),
            is_test=is_test,
            created_at=now,
            expires_at=expires_at,
        )

    async def validate_key(self, key: str) -> Optional[APIKey]:
        """Validate an API key and return key info"""
        if not key.startswith((KEY_PREFIX_LIVE, KEY_PREFIX_TEST)):
            return None

        key_hash = self._hash_key(key)

        row = await self.db.fetchrow(
            """
            SELECT * FROM api_keys 
            WHERE key_hash = $1 AND is_active = TRUE
            """,
            key_hash,
        )

        if not row:
            return None

        # Check expiration
        if row["expires_at"] and row["expires_at"] < datetime.utcnow():
            return None

        # Check if revoked
        if row["revoked_at"]:
            return None

        # Update usage stats
        await self.db.execute(
            """
            UPDATE api_keys 
            SET last_used_at = NOW(), usage_count = usage_count + 1
            WHERE id = $1
            """,
            row["id"],
        )

        return APIKey(
            id=row["id"],
            user_id=row["user_id"],
            user_name=row.get("user_name"),
            key_hash=row["key_hash"],
            key_prefix=row["key_prefix"],
            name=row["name"],
            permissions=row["permissions"],
            is_active=row["is_active"],
            is_test=row["is_test"],
            last_used_at=row["last_used_at"],
            usage_count=row["usage_count"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            revoked_at=row["revoked_at"],
        )

    async def list_keys(self, user_id: str) -> List[APIKeyResponse]:
        """List all API keys for a user"""
        rows = await self.db.fetch(
            """
            SELECT * FROM api_keys 
            WHERE user_id = $1 AND revoked_at IS NULL
            ORDER BY created_at DESC
            """,
            user_id,
        )

        return [
            APIKeyResponse(
                id=row["id"],
                name=row["name"],
                key_prefix=row["key_prefix"],
                permissions=row["permissions"],
                is_test=row["is_test"],
                is_active=row["is_active"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                last_used_at=row["last_used_at"],
                usage_count=row["usage_count"],
            )
            for row in rows
        ]

    async def revoke_key(self, key_id: str, user_id: str) -> bool:
        """Revoke an API key"""
        result = await self.db.execute(
            """
            UPDATE api_keys 
            SET revoked_at = NOW(), is_active = FALSE
            WHERE id = $1 AND user_id = $2
            """,
            key_id,
            user_id,
        )
        return result > 0

    def check_permission(self, api_key: APIKey, required_permission: str) -> bool:
        """Check if key has required permission"""
        return required_permission in api_key.permissions


# FastAPI Dependencies
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    request: Request,
    api_key: str = Depends(api_key_header),
) -> Dict[str, Any]:
    """Dependency to get current user from API key"""
    if not api_key:
        raise HTTPException(
            status_code=401, detail="API Key required. Pass via X-API-Key header."
        )

    auth_service = AuthService()
    key_info = await auth_service.validate_key(api_key)

    if not key_info:
        raise HTTPException(status_code=401, detail="Invalid or expired API Key")

    return {
        "user_id": key_info.user_id,
        "user_name": key_info.user_name,
        "key_id": str(key_info.id),
        "container_tag": str(key_info.id),  # One API key = one container
        "permissions": key_info.permissions,
        "is_test": key_info.is_test,
    }


def require_permission(permission: str):
    """Dependency factory to require specific permission"""

    async def permission_checker(
        current_user: Dict = Depends(get_current_user),
    ) -> Dict[str, Any]:
        if permission not in current_user["permissions"]:
            raise HTTPException(
                status_code=403, detail=f"Permission '{permission}' required"
            )
        return current_user

    return permission_checker


# Rate limiting (simple in-memory, should use Redis in production)
_rate_limit_store: Dict[str, List[datetime]] = {}
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 60  # seconds


async def check_rate_limit(
    request: Request,
    current_user: Dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Check rate limit for API key"""
    key_id = current_user["key_id"]
    now = datetime.utcnow()

    if key_id not in _rate_limit_store:
        _rate_limit_store[key_id] = []

    # Clean old requests
    _rate_limit_store[key_id] = [
        t
        for t in _rate_limit_store[key_id]
        if (now - t).total_seconds() < RATE_LIMIT_WINDOW
    ]

    if len(_rate_limit_store[key_id]) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Please try again later."
        )

    _rate_limit_store[key_id].append(now)
    return current_user


def verify_container_ownership(
    container_tag: str,
    api_key_id: str,
) -> str:
    """Verify that container_tag matches the API key ID.

    One API key = one container. The container_tag must equal the API key's ID.
    """
    if container_tag != api_key_id:
        raise HTTPException(
            status_code=403,
            detail=f"Container access denied. Your API key can only access container '{api_key_id}'.",
        )
    return container_tag


# Singleton
auth_service = AuthService()
