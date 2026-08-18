"""crystal 单元测试：scope 校验 / 幂等键 / 游标编解码（无 DB / 无 key，test-strategy §1）"""

import pytest

from src.api.crystal.evidence import (
    _decode_cursor,
    _encode_cursor,
    compute_idempotency_key,
)
from src.api.crystal.security import (
    build_full_scope,
    owner_from_user,
    verify_scope_ownership,
)
from src.api.crystal.errors import CrystalAPIError

KEY_ID = "11111111-2222-3333-4444-555555555555"


class TestVerifyScopeOwnership:
    def test_none_scope_allowed_global(self):
        assert verify_scope_ownership(None, KEY_ID) is None

    def test_project_scope_allowed(self):
        assert verify_scope_ownership("project-memory_recall", KEY_ID) == "project-memory_recall"

    def test_simple_dir_scope_allowed(self):
        assert verify_scope_ownership("some-dir", KEY_ID) == "some-dir"

    def test_own_key_id_prefix_rejected(self):
        """客户端把 {keyId}_project-x 整体传 scope → 403（v5 container_tag 语义塞回）"""
        with pytest.raises(CrystalAPIError) as exc:
            verify_scope_ownership(f"{KEY_ID}_project-x", KEY_ID)
        assert exc.value.status_code == 403

    def test_other_key_id_prefix_rejected(self):
        """他人 keyId 伪装 scope → 403（防跨 key 串数据）"""
        other = "99999999-aaaa-bbbb-cccc-dddddddddddd"
        with pytest.raises(CrystalAPIError) as exc:
            verify_scope_ownership(f"{other}_project-x", KEY_ID)
        assert exc.value.status_code == 403

    def test_plain_underscore_scope_allowed(self):
        """普通带下划线 scope（不含 uuid 形态）→ 允许"""
        assert verify_scope_ownership("my_project_x", KEY_ID) == "my_project_x"

    def test_non_uuid_hex_prefix_allowed(self):
        """下划线前缀但非合法 uuid（如 'abc12345-xxxx_' 的 xxxx 非 hex）→ 不误杀，允许"""
        assert (
            verify_scope_ownership("abc12345-xxxx_project-x", KEY_ID)
            == "abc12345-xxxx_project-x"
        )


class TestOwnerFromUser:
    def test_owner_personal(self):
        user = {"key_id": KEY_ID, "container_tag": KEY_ID}
        assert owner_from_user(user) == {"owner_type": "personal", "owner_id": KEY_ID}


class TestBuildFullScope:
    def test_none_maps_to_key_id(self):
        assert build_full_scope(None, KEY_ID) == KEY_ID

    def test_project_maps_to_full_tag(self):
        assert build_full_scope("project-x", KEY_ID) == f"{KEY_ID}_project-x"


class TestComputeIdempotencyKey:
    def test_deterministic(self):
        k1 = compute_idempotency_key("s-1", "m-1", "内容")
        k2 = compute_idempotency_key("s-1", "m-1", "内容")
        assert k1 == k2
        assert len(k1) == 32  # sha256 前 32 位

    def test_content_change_changes_key(self):
        k1 = compute_idempotency_key("s-1", "m-1", "内容A")
        k2 = compute_idempotency_key("s-1", "m-1", "内容B")
        assert k1 != k2

    def test_missing_session_or_message_returns_none(self):
        assert compute_idempotency_key(None, "m-1", "内容") is None
        assert compute_idempotency_key("s-1", None, "内容") is None
        assert compute_idempotency_key(None, None, "内容") is None


class TestCursorCodec:
    def test_roundtrip(self):
        from datetime import datetime, timezone

        dt = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        cursor = _encode_cursor(dt, "ev_abc")
        decoded = _decode_cursor(cursor)
        assert decoded == (dt, "ev_abc")

    def test_invalid_cursor_rejected(self):
        with pytest.raises(CrystalAPIError) as exc:
            _decode_cursor("not-base64!!!")
        assert exc.value.status_code == 400

    def test_empty_cursor_returns_none(self):
        assert _decode_cursor(None) is None
        assert _decode_cursor("") is None
