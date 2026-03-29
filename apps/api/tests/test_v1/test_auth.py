import pytest
from pathlib import Path
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from src.api.auth import AuthService


@pytest.mark.asyncio
async def test_generate_key():
    """Test API key generation"""
    service = AuthService()
    full_key, prefix, key_hash = service._generate_key(is_test=False)

    assert full_key.startswith("rk_live_")
    assert prefix == "rk_live_"
    assert len(key_hash) == 64


@pytest.mark.asyncio
async def test_generate_test_key():
    """Test test key generation"""
    service = AuthService()
    full_key, prefix, key_hash = service._generate_key(is_test=True)

    assert full_key.startswith("rk_test_")
    assert prefix == "rk_test_"


@pytest.mark.asyncio
async def test_hash_key():
    """Test key hashing"""
    service = AuthService()
    key = "rk_test_abc123"
    hash1 = service._hash_key(key)
    hash2 = service._hash_key(key)

    assert hash1 == hash2
    assert len(hash1) == 64


@pytest.mark.asyncio
async def test_check_permission():
    """Test permission checking"""
    from src.api.auth import APIKey

    service = AuthService()
    key = APIKey(
        id="test",
        user_id="user1",
        key_hash="hash",
        key_prefix="rk_live_",
        name="test",
        permissions=["read", "write"],
        is_active=True,
        is_test=False,
        last_used_at=None,
        usage_count=0,
        expires_at=None,
        created_at=None,
        revoked_at=None,
    )

    assert service.check_permission(key, "read") is True
    assert service.check_permission(key, "write") is True
    assert service.check_permission(key, "delete") is False
