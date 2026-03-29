import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.api.auth import (
    AuthService,
    verify_container_ownership,
    require_permission,
    check_rate_limit,
    get_current_user,
    APIKey,
)


class TestContainerOwnership:
    def test_verify_container_ownership_same_user(self):
        result = verify_container_ownership("user_123", "user_123")
        assert result == "user_123"

    def test_verify_container_ownership_with_project(self):
        result = verify_container_ownership("user_123_project_alpha", "user_123")
        assert result == "user_123_project_alpha"

    def test_verify_container_ownership_mismatch_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            verify_container_ownership("user_456_data", "user_123")

        assert exc_info.value.status_code == 403
        assert "ownership mismatch" in exc_info.value.detail.lower()

    def test_verify_container_ownership_different_user_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            verify_container_ownership("user_999", "user_123")

        assert exc_info.value.status_code == 403


class TestRequirePermission:
    @pytest.mark.asyncio
    async def test_require_permission_has_permission(self):
        checker = require_permission("write")
        current_user = {"user_id": "user_123", "permissions": ["read", "write"]}

        result = await checker(current_user=current_user)
        assert result == current_user

    @pytest.mark.asyncio
    async def test_require_permission_missing_permission(self):
        from fastapi import HTTPException

        checker = require_permission("admin")
        current_user = {"user_id": "user_123", "permissions": ["read", "write"]}

        with pytest.raises(HTTPException) as exc_info:
            await checker(current_user=current_user)

        assert exc_info.value.status_code == 403


class TestAuthService:
    def test_generate_key_format(self):
        service = AuthService()
        full_key, prefix, key_hash = service._generate_key(is_test=False)

        assert full_key.startswith("rk_live_")
        assert prefix == "rk_live_"
        assert len(key_hash) == 64  # SHA256 hex length

    def test_generate_test_key_format(self):
        service = AuthService()
        full_key, prefix, key_hash = service._generate_key(is_test=True)

        assert full_key.startswith("rk_test_")
        assert prefix == "rk_test_"

    def test_hash_key_consistency(self):
        service = AuthService()
        test_key = "rk_live_abc123"

        hash1 = service._hash_key(test_key)
        hash2 = service._hash_key(test_key)

        assert hash1 == hash2

    def test_check_permission(self):
        service = AuthService()

        api_key = MagicMock()
        api_key.permissions = ["read", "write", "delete"]

        assert service.check_permission(api_key, "read") is True
        assert service.check_permission(api_key, "write") is True
        assert service.check_permission(api_key, "admin") is False


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limit_allows_under_limit(self):
        from src.api.auth import _rate_limit_store, RATE_LIMIT_REQUESTS

        _rate_limit_store.clear()

        request = MagicMock()
        current_user = {"key_id": "test_key_123"}

        for i in range(10):
            result = await check_rate_limit(request, current_user)
            assert result == current_user

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_over_limit(self):
        from fastapi import HTTPException
        from src.api.auth import _rate_limit_store, RATE_LIMIT_REQUESTS
        from datetime import datetime

        _rate_limit_store["test_key_456"] = [datetime.utcnow()] * RATE_LIMIT_REQUESTS

        request = MagicMock()
        current_user = {"key_id": "test_key_456"}

        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(request, current_user)

        assert exc_info.value.status_code == 429
