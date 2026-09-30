"""POST /memories 的 scope/容器一致性闸门（MR-027 D3，2026-09-30）

背景：`scope` 不是 API 字段，容器只由 `container_tag` 决定。写入方把 scope 塞进 metadata
又不传 container_tag 时，记忆会**静默落到用户容器**并随 dynamic 进首轮画像
（实测 3 条 cron prompt 全量备份 ≈ 19,029 字）。现改为 fail-closed：声明 scope 即校验一致性。
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.api.memories import (
    CreateMemoryRequest,
    _assert_scope_container_consistency,
    create_memory,
)

USER_CONTAINER = "085288ba-8eab-439b-b0d4-b92382e0f95d"
PROJECT_CONTAINER = f"{USER_CONTAINER}_project-demo"


class TestScopeContainerGate:
    def test_project_scope_without_container_tag_rejected(self):
        with pytest.raises(HTTPException) as ei:
            _assert_scope_container_consistency(
                {"scope": "project"}, USER_CONTAINER, USER_CONTAINER
            )
        assert ei.value.status_code == 422
        assert "container_tag" in ei.value.detail

    def test_project_scope_with_project_container_ok(self):
        _assert_scope_container_consistency(
            {"scope": "project"}, PROJECT_CONTAINER, USER_CONTAINER
        )

    def test_user_scope_with_user_container_ok(self):
        _assert_scope_container_consistency(
            {"scope": "user"}, USER_CONTAINER, USER_CONTAINER
        )

    def test_user_scope_with_project_container_rejected(self):
        with pytest.raises(HTTPException) as ei:
            _assert_scope_container_consistency(
                {"scope": "user"}, PROJECT_CONTAINER, USER_CONTAINER
            )
        assert ei.value.status_code == 422

    def test_no_scope_untouched(self):
        """未声明 scope：保持 container_tag or 用户容器 的既有语义（零行为变化）。"""
        for tag in (USER_CONTAINER, PROJECT_CONTAINER):
            _assert_scope_container_consistency({}, tag, USER_CONTAINER)

    def test_unknown_scope_value_untouched(self):
        _assert_scope_container_consistency(
            {"scope": "whatever"}, USER_CONTAINER, USER_CONTAINER
        )


class TestCreateMemoryWiring:
    """端点内确实挂上了闸门（走真实 create_memory 函数体，不依赖依赖注入覆写）。"""

    def _current_user(self):
        return {"container_tag": USER_CONTAINER, "key_id": USER_CONTAINER}

    def test_endpoint_rejects_polluted_write_before_store(self):
        request = CreateMemoryRequest(
            content="round=847 | 旧cron prompt备份(全量)",
            metadata={"scope": "project", "type": "project-config", "kind": "cron_prompt_backup"},
        )
        with patch("src.api.memories.memory_store") as store_mock:
            store_mock.create = AsyncMock()
            with pytest.raises(HTTPException) as ei:
                import asyncio

                asyncio.run(
                    create_memory(
                        request,
                        BackgroundTasks(),
                        current_user=self._current_user(),
                        _={},
                    )
                )
            assert ei.value.status_code == 422
            store_mock.create.assert_not_called(), "被拒的写入不得落库"

    def test_endpoint_allows_explicit_project_container(self):
        request = CreateMemoryRequest(
            content="项目留档",
            container_tag=PROJECT_CONTAINER,
            metadata={"scope": "project", "type": "project-config"},
        )
        created = MagicMock()
        created.id = "mem_new"
        created.content = "项目留档"
        created.container_tag = PROJECT_CONTAINER
        created.is_static = False
        created.created_at = None

        with patch("src.api.memories.memory_store") as store_mock, patch(
            "src.api.memories.profile_service"
        ) as profile_mock:
            store_mock.create = AsyncMock(return_value=created)
            profile_mock.invalidate_cache = AsyncMock()
            profile_mock.get_entity_context = AsyncMock(return_value=None)

            import asyncio

            result = asyncio.run(
                create_memory(
                    request,
                    BackgroundTasks(),
                    current_user=self._current_user(),
                    _={},
                )
            )

        assert result["id"] == "mem_new"
        assert store_mock.create.await_count == 1
        assert store_mock.create.await_args.kwargs["container_tag"] == PROJECT_CONTAINER
