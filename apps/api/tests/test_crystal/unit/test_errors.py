"""crystal 单元测试：统一响应信封与错误规范（api-contract §3）"""

import pytest

from src.api.crystal.errors import (
    CrystalAPIError,
    error_response,
    ok_response,
)


class TestOkResponse:
    def test_default(self):
        assert ok_response() == {"code": 0, "message": "ok", "data": None}

    def test_with_data(self):
        assert ok_response({"a": 1}) == {"code": 0, "message": "ok", "data": {"a": 1}}


class TestErrorResponse:
    def test_minimal(self):
        assert error_response(403, "denied") == {"code": 403, "message": "denied"}

    def test_with_detail(self):
        body = error_response(409, "conflict", {"id": "ev_1"})
        assert body["code"] == 409
        assert body["detail"] == {"id": "ev_1"}


class TestCrystalAPIError:
    def test_is_http_exception(self):
        err = CrystalAPIError(404, "not found")
        assert err.status_code == 404
        assert err.message == "not found"

    def test_status_code_roundtrip(self):
        err = CrystalAPIError(403, "denied", {"scope": "x"})
        assert err.detail == {"scope": "x"}
