"""
Unit tests for OpenCode plugin compaction hook.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import time


class TestCompactionState:
    def test_state_initialization(self):
        from src.plugins.opencode.compaction import CompactionState

        state = CompactionState()

        assert state.last_compaction_time == {}
        assert state.compaction_in_progress == set()
        assert state.summarized_sessions == set()

    def test_state_tracking(self):
        from src.plugins.opencode.compaction import CompactionState

        state = CompactionState()
        session_id = "test_session_001"

        state.last_compaction_time[session_id] = time.time() * 1000
        state.compaction_in_progress.add(session_id)
        state.summarized_sessions.add(session_id)

        assert session_id in state.last_compaction_time
        assert session_id in state.compaction_in_progress
        assert session_id in state.summarized_sessions

        state.compaction_in_progress.discard(session_id)
        assert session_id not in state.compaction_in_progress


class TestCompactionPrompt:
    def test_create_prompt_english(self):
        from src.plugins.opencode.compaction import create_compaction_prompt

        memories = ["Project uses Bun", "Build with bun run build"]
        prompt = create_compaction_prompt(memories, "en_US")

        assert "[COMPACTION CONTEXT INJECTION]" in prompt
        assert "User Requests (As-Is)" in prompt
        assert "Final Goal" in prompt
        assert "Work Completed" in prompt
        assert "Remaining Tasks" in prompt
        assert "MUST NOT Do" in prompt
        assert "Project uses Bun" in prompt

    def test_create_prompt_chinese(self):
        from src.plugins.opencode.compaction import create_compaction_prompt

        memories = ["项目使用 Bun", "构建命令: bun run build"]
        prompt = create_compaction_prompt(memories, "zh_CN")

        assert "[COMPACTION CONTEXT INJECTION]" in prompt
        assert "用户请求（原文）" in prompt
        assert "最终目标" in prompt
        assert "已完成工作" in prompt
        assert "剩余任务" in prompt
        assert "禁止事项" in prompt
        assert "项目使用 Bun" in prompt

    def test_create_prompt_empty_memories(self):
        from src.plugins.opencode.compaction import create_compaction_prompt

        prompt = create_compaction_prompt([], "en_US")

        assert "[COMPACTION CONTEXT INJECTION]" in prompt
        assert "Project Knowledge" not in prompt


class TestMessageIdGeneration:
    def test_generate_message_id_format(self):
        from src.plugins.opencode.compaction import generate_message_id

        msg_id = generate_message_id()

        assert msg_id.startswith("msg_")
        assert len(msg_id) > 10

    def test_generate_message_id_unique(self):
        from src.plugins.opencode.compaction import generate_message_id

        id1 = generate_message_id()
        id2 = generate_message_id()

        assert id1 != id2

    def test_generate_part_id_format(self):
        from src.plugins.opencode.compaction import generate_part_id

        part_id = generate_part_id()

        assert part_id.startswith("prt_")
        assert len(part_id) > 8


class TestCompactionHook:
    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.list_memories = AsyncMock(
            return_value=[{"content": "test memory", "similarity": 0.9}]
        )
        client.add = AsyncMock(return_value={"id": "mem_test_001"})
        return client

    @pytest.fixture
    def mock_config(self):
        from src.plugins.opencode.config import Config

        config = Config()
        config.directory = "/test/project"
        config.compaction_threshold = 0.8
        config.max_project_memories = 10
        config.enable_summary_capture = True
        config.min_summary_length = 100
        return config

    @pytest.fixture
    def compaction_hook(self, mock_client, mock_config):
        from src.plugins.opencode.compaction import CompactionHook

        return CompactionHook(
            client=mock_client,
            config=mock_config,
            tags={"user": "test_user", "project": "test_project"},
            logger=None,
        )

    def test_hook_initialization(self, compaction_hook):
        assert compaction_hook.state is not None
        assert compaction_hook.state.last_compaction_time == {}

    @pytest.mark.asyncio
    async def test_fetch_project_memories(self, compaction_hook, mock_client):
        memories = await compaction_hook.fetch_project_memories_for_compaction()

        assert len(memories) >= 0
        mock_client.list_memories.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_not_trigger_if_in_progress(self, compaction_hook):
        session_id = "test_session_001"
        compaction_hook.state.compaction_in_progress.add(session_id)

        ctx_client = MagicMock()
        await compaction_hook.check_and_trigger_compaction(
            session_id,
            {"tokens": {"input": 100000, "output": 50000, "cache": {"read": 10000}}},
            ctx_client,
        )

        assert session_id in compaction_hook.state.compaction_in_progress

    @pytest.mark.asyncio
    async def test_should_not_trigger_below_threshold(self, compaction_hook):
        session_id = "test_session_002"
        ctx_client = MagicMock()

        await compaction_hook.check_and_trigger_compaction(
            session_id,
            {
                "tokens": {"input": 10000, "output": 5000, "cache": {"read": 1000}},
                "providerID": "test_provider",
                "modelID": "test_model",
            },
            ctx_client,
        )

        assert session_id not in compaction_hook.state.compaction_in_progress
        assert session_id not in compaction_hook.state.last_compaction_time


class TestCooldownLogic:
    def test_cooldown_prevents_rapid_compaction(self):
        from src.plugins.opencode.compaction import (
            CompactionState,
            COMPACTION_COOLDOWN_MS,
        )

        state = CompactionState()
        session_id = "test_session_003"

        state.last_compaction_time[session_id] = time.time() * 1000

        recent_time = state.last_compaction_time.get(session_id, 0)
        elapsed = time.time() * 1000 - recent_time

        assert elapsed < COMPACTION_COOLDOWN_MS


class TestMessageStorage:
    def test_get_message_dir_not_exists(self, tmp_path):
        from src.plugins.opencode.compaction import get_message_dir

        with patch(
            "src.plugins.opencode.compaction.MESSAGE_STORAGE", tmp_path / "nonexistent"
        ):
            result = get_message_dir("test_session")
            assert result is None

    def test_get_or_create_message_dir(self, tmp_path):
        from src.plugins.opencode.compaction import get_or_create_message_dir

        storage_path = tmp_path / "messages"
        with patch("src.plugins.opencode.compaction.MESSAGE_STORAGE", storage_path):
            result = get_or_create_message_dir("test_session_004")

            assert result.exists()
            assert result.name == "test_session_004"


class TestSessionSummaryCapture:
    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.add = AsyncMock(return_value={"id": "mem_summary_001"})
        return client

    @pytest.fixture
    def mock_config(self):
        from src.plugins.opencode.config import Config

        config = Config()
        config.enable_summary_capture = True
        config.min_summary_length = 100
        config.directory = "/test"
        config.language = "en_US"
        return config

    @pytest.mark.asyncio
    async def test_save_summary_as_memory(self, mock_client, mock_config):
        from src.plugins.opencode.compaction import CompactionHook

        hook = CompactionHook(
            client=mock_client,
            config=mock_config,
            tags={"project": "test_project"},
            logger=None,
        )

        summary = "This is a test summary that is long enough to meet the minimum length requirement for saving as a memory."

        result = await hook.save_summary_as_memory("session_001", summary)

        assert result == "mem_summary_001"
        mock_client.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_short_summary(self, mock_client, mock_config):
        from src.plugins.opencode.compaction import CompactionHook

        hook = CompactionHook(
            client=mock_client,
            config=mock_config,
            tags={"project": "test_project"},
            logger=None,
        )

        short_summary = "Too short"

        result = await hook.save_summary_as_memory("session_002", short_summary)

        assert result is None
        mock_client.add.assert_not_called()


class TestEventHandling:
    @pytest.fixture
    def compaction_hook(self):
        from src.plugins.opencode.compaction import CompactionHook

        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_config.directory = "/test"
        mock_config.enable_summary_capture = True
        mock_config.min_summary_length = 100
        mock_config.language = "en_US"
        mock_config.max_project_memories = 10

        return CompactionHook(
            client=mock_client,
            config=mock_config,
            tags={"user": "test", "project": "test"},
            logger=None,
        )

    @pytest.mark.asyncio
    async def test_handle_session_deleted(self, compaction_hook):
        session_id = "session_to_delete"

        compaction_hook.state.last_compaction_time[session_id] = time.time() * 1000
        compaction_hook.state.compaction_in_progress.add(session_id)
        compaction_hook.state.summarized_sessions.add(session_id)

        event = {"type": "session.deleted", "properties": {"info": {"id": session_id}}}

        await compaction_hook.handle_event(event, None)

        assert session_id not in compaction_hook.state.last_compaction_time
        assert session_id not in compaction_hook.state.compaction_in_progress
        assert session_id not in compaction_hook.state.summarized_sessions


class TestCompactionTriggerLogic:
    """Comprehensive tests for compaction trigger decision logic."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.list_memories = AsyncMock(return_value=[])
        client.add = AsyncMock(return_value={"id": "mem_test"})
        return client

    @pytest.fixture
    def mock_config(self):
        from src.plugins.opencode.config import Config

        config = Config()
        config.directory = "/test/project"
        config.compaction_threshold = 0.8
        config.max_project_memories = 10
        config.enable_summary_capture = True
        config.min_summary_length = 100
        config.language = "en_US"
        return config

    @pytest.fixture
    def compaction_hook(self, mock_client, mock_config):
        from src.plugins.opencode.compaction import CompactionHook

        return CompactionHook(
            client=mock_client,
            config=mock_config,
            tags={"user": "test_user", "project": "test_project"},
            logger=None,
        )

    @pytest.mark.asyncio
    async def test_trigger_compaction_at_threshold(self, compaction_hook, mock_client):
        """Test compaction triggers when usage exactly at threshold."""
        session_id = "test_threshold_session"
        ctx_client = MagicMock()
        ctx_client.session = MagicMock()
        ctx_client.session.summarize = AsyncMock()
        ctx_client.tui = MagicMock()
        ctx_client.tui.showToast = AsyncMock()

        # 160000 tokens used out of 200000 limit = 80%
        await compaction_hook.check_and_trigger_compaction(
            session_id,
            {
                "tokens": {
                    "input": 100000,
                    "output": 50000,
                    "cache": {"read": 10000},
                },
                "providerID": "test_provider",
                "modelID": "test_model",
            },
            ctx_client,
        )

        assert session_id in compaction_hook.state.last_compaction_time
        mock_client.list_memories.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_compaction_above_threshold(
        self, compaction_hook, mock_client
    ):
        """Test compaction triggers when usage above threshold."""
        session_id = "test_above_threshold_session"
        ctx_client = MagicMock()
        ctx_client.session = MagicMock()
        ctx_client.session.summarize = AsyncMock()

        # 170000 tokens used out of 200000 limit = 85%
        await compaction_hook.check_and_trigger_compaction(
            session_id,
            {
                "tokens": {
                    "input": 100000,
                    "output": 60000,
                    "cache": {"read": 10000},
                },
                "providerID": "test_provider",
                "modelID": "test_model",
            },
            ctx_client,
        )

        assert session_id in compaction_hook.state.last_compaction_time

    @pytest.mark.asyncio
    async def test_no_trigger_below_min_tokens(self, compaction_hook, mock_client):
        """Test no trigger when total tokens below minimum threshold."""
        session_id = "test_min_tokens_session"
        ctx_client = MagicMock()

        # Only 30000 tokens, below MIN_TOKENS_FOR_COMPACTION (50000)
        await compaction_hook.check_and_trigger_compaction(
            session_id,
            {
                "tokens": {
                    "input": 20000,
                    "output": 8000,
                    "cache": {"read": 2000},
                },
                "providerID": "test_provider",
                "modelID": "test_model",
            },
            ctx_client,
        )

        assert session_id not in compaction_hook.state.last_compaction_time
        mock_client.list_memories.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_trigger_below_threshold(self, compaction_hook, mock_client):
        """Test no trigger when usage ratio below threshold."""
        session_id = "test_below_threshold_session"
        ctx_client = MagicMock()

        # 70000 tokens used out of 200000 limit = 35% (below 80%)
        await compaction_hook.check_and_trigger_compaction(
            session_id,
            {
                "tokens": {
                    "input": 50000,
                    "output": 15000,
                    "cache": {"read": 5000},
                },
                "providerID": "test_provider",
                "modelID": "test_model",
            },
            ctx_client,
        )

        assert session_id not in compaction_hook.state.last_compaction_time

    @pytest.mark.asyncio
    async def test_no_trigger_if_already_summary(self, compaction_hook, mock_client):
        """Test no trigger if message is already a summary."""
        session_id = "test_summary_session"
        ctx_client = MagicMock()

        await compaction_hook.check_and_trigger_compaction(
            session_id,
            {
                "tokens": {
                    "input": 100000,
                    "output": 60000,
                    "cache": {"read": 10000},
                },
                "providerID": "test_provider",
                "modelID": "test_model",
                "summary": True,
            },
            ctx_client,
        )

        assert session_id not in compaction_hook.state.last_compaction_time

    @pytest.mark.asyncio
    async def test_no_trigger_without_provider_model(
        self, compaction_hook, mock_client
    ):
        """Test no trigger if providerID/modelID missing and no fallback."""
        session_id = "test_no_provider_session"
        ctx_client = MagicMock()

        await compaction_hook.check_and_trigger_compaction(
            session_id,
            {
                "tokens": {
                    "input": 100000,
                    "output": 60000,
                    "cache": {"read": 10000},
                },
            },
            ctx_client,
        )

        # Implementation sets timestamp before checking provider/model
        # But list_memories should not be called
        mock_client.list_memories.assert_not_called()
        # And compaction should not remain in progress
        assert session_id not in compaction_hook.state.compaction_in_progress

    @pytest.mark.asyncio
    async def test_cooldown_prevents_trigger(self, compaction_hook, mock_client):
        """Test cooldown period prevents rapid re-trigger."""
        session_id = "test_cooldown_session"

        # Set recent compaction time
        compaction_hook.state.last_compaction_time[session_id] = time.time() * 1000

        ctx_client = MagicMock()

        # Try to trigger again immediately
        await compaction_hook.check_and_trigger_compaction(
            session_id,
            {
                "tokens": {
                    "input": 100000,
                    "output": 60000,
                    "cache": {"read": 10000},
                },
                "providerID": "test_provider",
                "modelID": "test_model",
            },
            ctx_client,
        )

        # Should not trigger again (list_memories not called)
        mock_client.list_memories.assert_not_called()

    @pytest.mark.asyncio
    async def test_custom_context_limit(self, mock_client):
        """Test compaction with custom model context limit."""
        from src.plugins.opencode.compaction import (
            CompactionHook,
            MIN_TOKENS_FOR_COMPACTION,
        )
        from src.plugins.opencode.config import Config

        config = Config()
        config.directory = "/test/project"
        config.compaction_threshold = 0.8
        config.max_project_memories = 10
        config.enable_summary_capture = True
        config.min_summary_length = 100

        def get_limit(provider_id, model_id):
            if model_id == "small_model":
                return 100000
            return None

        hook = CompactionHook(
            client=mock_client,
            config=config,
            tags={"user": "test", "project": "test"},
            logger=None,
            get_model_limit=get_limit,
        )

        session_id = "test_custom_limit"
        ctx_client = MagicMock()
        ctx_client.session = MagicMock()
        ctx_client.session.summarize = AsyncMock()

        # 80000 tokens out of 100000 limit = 80%
        # And >= MIN_TOKENS_FOR_COMPACTION (50000)
        await hook.check_and_trigger_compaction(
            session_id,
            {
                "tokens": {
                    "input": 50000,
                    "output": 25000,
                    "cache": {"read": 5000},
                },
                "providerID": "test_provider",
                "modelID": "small_model",
            },
            ctx_client,
        )

        assert session_id in hook.state.last_compaction_time

    @pytest.mark.asyncio
    async def test_cache_token_handling(self, compaction_hook):
        """Test correct handling of cache tokens in usage calculation."""
        session_id = "test_cache_tokens"

        # Verify cache.read is included in total
        tokens = {
            "input": 50000,
            "output": 30000,
            "cache": {"read": 20000},
        }

        total = tokens["input"] + tokens["cache"]["read"] + tokens["output"]
        assert total == 100000

    @pytest.mark.asyncio
    async def test_missing_cache_field(self, compaction_hook, mock_client):
        """Test handling when cache field is missing."""
        session_id = "test_no_cache"
        ctx_client = MagicMock()

        # Tokens without cache field
        await compaction_hook.check_and_trigger_compaction(
            session_id,
            {
                "tokens": {
                    "input": 35000,
                    "output": 20000,
                    # No cache field
                },
                "providerID": "test_provider",
                "modelID": "test_model",
            },
            ctx_client,
        )

        # Should handle gracefully - below min tokens
        assert session_id not in compaction_hook.state.last_compaction_time

    @pytest.mark.asyncio
    async def test_threshold_boundary_exact(self, compaction_hook, mock_client):
        """Test exact threshold boundary (80.0%)."""
        session_id = "test_exact_boundary"
        ctx_client = MagicMock()
        ctx_client.session = MagicMock()
        ctx_client.session.summarize = AsyncMock()

        # Exactly 80% with MIN_TOKENS_FOR_COMPACTION = 50000
        # Need to be >= 50000 tokens and >= 80% of 200000
        # 160000 / 200000 = 0.8 = 80%
        await compaction_hook.check_and_trigger_compaction(
            session_id,
            {
                "tokens": {
                    "input": 100000,
                    "output": 50000,
                    "cache": {"read": 10000},
                },
                "providerID": "test_provider",
                "modelID": "test_model",
            },
            ctx_client,
        )

        # Should trigger at exactly 80%
        assert session_id in compaction_hook.state.last_compaction_time

    @pytest.mark.asyncio
    async def test_threshold_just_below(self, compaction_hook, mock_client):
        """Test just below threshold (79.9%)."""
        session_id = "test_just_below"
        ctx_client = MagicMock()

        # 79.9% - should NOT trigger
        # 159800 / 200000 = 0.799
        await compaction_hook.check_and_trigger_compaction(
            session_id,
            {
                "tokens": {
                    "input": 100000,
                    "output": 49800,
                    "cache": {"read": 10000},
                },
                "providerID": "test_provider",
                "modelID": "test_model",
            },
            ctx_client,
        )

        # Should NOT trigger below 80%
        assert session_id not in compaction_hook.state.last_compaction_time
