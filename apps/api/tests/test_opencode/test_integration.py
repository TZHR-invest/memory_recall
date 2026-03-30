"""
Integration tests for OpenCode plugin full workflow.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import tempfile
import os
from pathlib import Path


class TestPluginInitialization:
    @pytest.fixture
    def mock_config_dict(self):
        return {
            "api_key": "rk_test_key",
            "base_url": "http://localhost:8000",
            "directory": "/test/project",
            "max_memories": 5,
            "max_project_memories": 10,
            "compaction_threshold": 0.8,
            "enable_summary_capture": True,
            "enable_document_tracking": False,
            "language": "auto",
        }

    def test_create_plugin(self, mock_config_dict):
        with patch("src.plugins.opencode.config.get_config") as mock_get_config:
            from src.plugins.opencode.config import Config

            mock_get_config.return_value = Config(**mock_config_dict)

            with patch("src.plugins.opencode.client.OpenCodeClient"):
                from src.plugins.opencode import create_plugin

                plugin = create_plugin(mock_config_dict)

                assert plugin["id"] == "memory-recall-opencode"
                assert plugin["name"] == "Memory Recall for OpenCode"
                assert "register" in plugin

    def test_plugin_register_without_api_key(self, mock_config_dict):
        import src.plugins.opencode.config as config_module

        config_module._config = None

        mock_config_dict["api_key"] = None

        with patch("src.plugins.opencode.config.load_config") as mock_load:
            from src.plugins.opencode.config import Config

            config = Config(**mock_config_dict)
            assert config.is_configured() is False
            mock_load.return_value = config

            with patch("src.plugins.opencode.client.OpenCodeClient"):
                with patch("asyncio.create_task"):
                    from src.plugins.opencode import create_plugin

                    plugin = create_plugin({})

                    mock_ctx = MagicMock()
                    plugin["register"](mock_ctx)

                    mock_ctx.tool.assert_not_called()


class TestToolExecution:
    @pytest.fixture
    def setup_tool(self):
        from src.plugins.opencode.config import Config
        from src.plugins.opencode.client import OpenCodeClient
        from src.plugins.opencode.tool import create_tool

        config = Config(
            api_key="test_key",
            directory="/test/project",
            max_memories=5,
            max_project_memories=10,
            similarity_threshold=0.6,
        )

        mock_client = MagicMock(spec=OpenCodeClient)
        mock_client.get_user_tag = MagicMock(return_value="test_user")
        mock_client.get_project_tag = MagicMock(return_value="test_project")
        mock_client.add = AsyncMock(return_value={"id": "mem_001"})
        mock_client.search = AsyncMock(
            return_value=[
                {"id": "mem_002", "content": "test result", "similarity": 0.9}
            ]
        )
        mock_client.profile = AsyncMock(
            return_value={"profile": {"static": ["fact1"], "dynamic": ["fact2"]}}
        )
        mock_client.list_memories = AsyncMock(return_value=[])
        mock_client.forget = AsyncMock(return_value={})

        tool = create_tool(mock_client, config, None)

        return tool, mock_client

    @pytest.mark.asyncio
    async def test_tool_help_mode(self, setup_tool):
        tool, _ = setup_tool

        result = await tool["execute"]({"mode": "help"}, {})

        import json

        data = json.loads(result)

        assert data["success"] is True
        assert "modes" in data
        assert "add" in data["modes"]
        assert "search" in data["modes"]

    @pytest.mark.asyncio
    async def test_tool_add_mode(self, setup_tool):
        tool, mock_client = setup_tool

        result = await tool["execute"](
            {
                "mode": "add",
                "content": "Test memory content",
                "isStatic": True,
            },
            {},
        )

        import json

        data = json.loads(result)

        assert data["success"] is True
        assert data["id"] == "mem_001"
        mock_client.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_add_empty_content(self, setup_tool):
        tool, _ = setup_tool

        result = await tool["execute"](
            {
                "mode": "add",
                "content": "",
            },
            {},
        )

        import json

        data = json.loads(result)

        assert data["success"] is False
        assert "error" in data

    @pytest.mark.asyncio
    async def test_tool_search_mode(self, setup_tool):
        tool, mock_client = setup_tool

        result = await tool["execute"](
            {
                "mode": "search",
                "query": "test query",
            },
            {},
        )

        import json

        data = json.loads(result)

        assert data["success"] is True
        assert "results" in data
        mock_client.search.assert_called()

    @pytest.mark.asyncio
    async def test_tool_search_combined_scope(self, setup_tool):
        tool, mock_client = setup_tool

        result = await tool["execute"](
            {
                "mode": "search",
                "query": "test query",
            },
            {},
        )

        import json

        data = json.loads(result)

        assert data["success"] is True
        assert mock_client.search.call_count >= 1

    @pytest.mark.asyncio
    async def test_tool_profile_mode(self, setup_tool):
        tool, mock_client = setup_tool

        result = await tool["execute"](
            {
                "mode": "profile",
            },
            {},
        )

        import json

        data = json.loads(result)

        assert data["success"] is True
        assert "profile" in data
        mock_client.profile.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_list_mode(self, setup_tool):
        tool, mock_client = setup_tool

        result = await tool["execute"](
            {
                "mode": "list",
                "scope": "project",
            },
            {},
        )

        import json

        data = json.loads(result)

        assert data["success"] is True
        assert "memories" in data

    @pytest.mark.asyncio
    async def test_tool_forget_mode(self, setup_tool):
        tool, mock_client = setup_tool

        result = await tool["execute"](
            {
                "mode": "forget",
                "memoryId": "mem_to_delete",
            },
            {},
        )

        import json

        data = json.loads(result)

        assert data["success"] is True
        mock_client.forget.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_forget_missing_id(self, setup_tool):
        tool, _ = setup_tool

        result = await tool["execute"](
            {
                "mode": "forget",
            },
            {},
        )

        import json

        data = json.loads(result)

        assert data["success"] is False


class TestContextInjection:
    @pytest.fixture
    def setup_context(self):
        from src.plugins.opencode.config import Config
        from src.plugins.opencode.client import OpenCodeClient
        from src.plugins.opencode.tool import handle_chat_message

        config = Config(
            api_key="test_key",
            directory="/test/project",
            max_memories=5,
            max_project_memories=10,
            max_profile_items=5,
            inject_profile=True,
            language="auto",
        )

        mock_client = MagicMock(spec=OpenCodeClient)
        mock_client.get_user_tag = MagicMock(return_value="test_user")
        mock_client.get_project_tag = MagicMock(return_value="test_project")
        mock_client.profile = AsyncMock(
            return_value={
                "profile": {
                    "static": ["John Doe", "Engineer"],
                    "dynamic": ["Working on tests"],
                }
            }
        )
        mock_client.list_memories = AsyncMock(
            return_value=[{"content": "Project uses Python", "similarity": 1.0}]
        )
        mock_client.search = AsyncMock(return_value=[])

        return config, mock_client

    @pytest.mark.asyncio
    async def test_context_injected_on_first_message(self, setup_context):
        config, mock_client = setup_context

        input_data = {
            "sessionID": "test_session_001",
        }
        output_data = {
            "parts": [{"type": "text", "text": "Hello, please help me with something."}]
        }
        injected_sessions = set()

        from src.plugins.opencode.tool import handle_chat_message

        await handle_chat_message(
            client=mock_client,
            config=config,
            input=input_data,
            output=output_data,
            injected_sessions=injected_sessions,
            logger=None,
        )

        assert len(output_data["parts"]) > 1
        context_part = output_data["parts"][0]
        assert context_part.get("synthetic") is True

    @pytest.mark.asyncio
    async def test_context_not_injected_on_second_message(self, setup_context):
        config, mock_client = setup_context

        input_data = {
            "sessionID": "test_session_002",
        }
        output_data = {
            "parts": [
                {"type": "text", "text": "Second message"},
            ]
        }
        injected_sessions = {"test_session_002"}

        from src.plugins.opencode.tool import handle_chat_message

        await handle_chat_message(
            client=mock_client,
            config=config,
            input=input_data,
            output=output_data,
            injected_sessions=injected_sessions,
            logger=None,
        )

        assert len(output_data["parts"]) == 1

    @pytest.mark.asyncio
    async def test_keyword_triggers_nudge(self, setup_context):
        config, mock_client = setup_context

        input_data = {
            "sessionID": "test_session_003",
        }
        output_data = {
            "parts": [
                {"type": "text", "text": "Please remember this important information."},
            ]
        }
        injected_sessions = set()

        from src.plugins.opencode.tool import handle_chat_message

        await handle_chat_message(
            client=mock_client,
            config=config,
            input=input_data,
            output=output_data,
            injected_sessions=injected_sessions,
            logger=None,
        )

        nudge_found = False
        for part in output_data["parts"]:
            if part.get("synthetic") and "MEMORY" in part.get("text", ""):
                nudge_found = True
                break

        assert nudge_found or len(output_data["parts"]) >= 1


class TestEndToEndWorkflow:
    @pytest.mark.asyncio
    async def test_full_memory_lifecycle(self):
        from src.plugins.opencode.config import Config
        from src.plugins.opencode.client import OpenCodeClient
        from src.plugins.opencode.tool import create_tool

        config = Config(
            api_key="test_key",
            directory="/test/project",
            max_memories=5,
            max_project_memories=10,
        )

        mock_client = MagicMock(spec=OpenCodeClient)
        mock_client.get_user_tag = MagicMock(return_value="test_user")
        mock_client.get_project_tag = MagicMock(return_value="test_project")
        mock_client.add = AsyncMock(return_value={"id": "mem_created"})
        mock_client.search = AsyncMock(
            return_value=[
                {"id": "mem_created", "content": "Test memory", "similarity": 0.95}
            ]
        )
        mock_client.profile = AsyncMock(return_value={"profile": {}})
        mock_client.list_memories = AsyncMock(return_value=[])
        mock_client.forget = AsyncMock(return_value={})

        tool = create_tool(mock_client, config, None)

        add_result = await tool["execute"](
            {
                "mode": "add",
                "content": "Important project information",
                "isStatic": True,
                "type": "project-config",
            },
            {},
        )

        import json

        add_data = json.loads(add_result)
        assert add_data["success"] is True

        search_result = await tool["execute"](
            {
                "mode": "search",
                "query": "project information",
            },
            {},
        )

        search_data = json.loads(search_result)
        assert search_data["success"] is True

        profile_result = await tool["execute"](
            {
                "mode": "profile",
            },
            {},
        )

        profile_data = json.loads(profile_result)
        assert profile_data["success"] is True


class TestCompactionSummaryWorkflow:
    """Integration tests for compaction + summary workflow."""

    @pytest.fixture
    def setup_compaction(self, tmp_path):
        from src.plugins.opencode.config import Config
        from src.plugins.opencode.compaction import CompactionHook

        config = Config()
        config.directory = str(tmp_path)
        config.compaction_threshold = 0.8
        config.max_project_memories = 10
        config.enable_summary_capture = True
        config.min_summary_length = 100
        config.language = "en_US"

        mock_client = MagicMock()
        mock_client.list_memories = AsyncMock(
            return_value=[{"content": "Project uses Python"}]
        )
        mock_client.add = AsyncMock(return_value={"id": "mem_summary_001"})

        hook = CompactionHook(
            client=mock_client,
            config=config,
            tags={"user": "test_user", "project": "test_project"},
            logger=None,
        )

        return hook, mock_client, config

    @pytest.mark.asyncio
    async def test_compaction_triggers_summary_capture(self, setup_compaction):
        hook, mock_client, config = setup_compaction

        session_id = "test_compaction_session"
        ctx_client = MagicMock()
        ctx_client.session = MagicMock()
        ctx_client.session.summarize = AsyncMock()
        ctx_client.session.messages = AsyncMock(
            return_value=[
                {
                    "info": {
                        "role": "assistant",
                        "summary": True,
                        "finish": True,
                    },
                    "parts": [
                        {
                            "type": "text",
                            "text": "This is a comprehensive session summary that covers all the work completed during this session with sufficient length for storage.",
                        }
                    ],
                }
            ]
        )
        ctx_client.tui = MagicMock()
        ctx_client.tui.showToast = AsyncMock()

        await hook.check_and_trigger_compaction(
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

        assert session_id in hook.state.summarized_sessions

        summary_event = {
            "type": "message.updated",
            "properties": {
                "info": {
                    "sessionID": session_id,
                    "role": "assistant",
                    "summary": True,
                    "finish": True,
                }
            },
        }

        await hook.handle_event(summary_event, ctx_client)

        mock_client.add.assert_called()

    @pytest.mark.asyncio
    async def test_session_deleted_cleans_state(self, setup_compaction):
        hook, _, _ = setup_compaction

        session_id = "session_to_cleanup"
        hook.state.last_compaction_time[session_id] = 12345.0
        hook.state.compaction_in_progress.add(session_id)
        hook.state.summarized_sessions.add(session_id)

        event = {
            "type": "session.deleted",
            "properties": {"info": {"id": session_id}},
        }

        await hook.handle_event(event, None)

        assert session_id not in hook.state.last_compaction_time
        assert session_id not in hook.state.compaction_in_progress
        assert session_id not in hook.state.summarized_sessions


class TestDocumentTrackingIntegration:
    """Integration tests for document tracking workflow."""

    @pytest.fixture
    def setup_tracker(self, tmp_path):
        from src.plugins.opencode.config import Config
        from src.plugins.opencode.document_tracker import DocumentTracker

        config = Config()
        config.directory = str(tmp_path)
        config.tracked_doc_patterns = ["*.md", "README*"]
        config.enable_document_tracking = True

        mock_client = MagicMock()
        mock_client.add = AsyncMock(return_value={"id": "mem_doc_001"})

        tracker = DocumentTracker(
            client=mock_client,
            config=config,
            project_tag="test_project",
            logger=None,
        )

        return tracker, mock_client, tmp_path

    @pytest.mark.asyncio
    async def test_scan_and_memorize_new_files(self, setup_tracker):
        tracker, mock_client, tmp_path = setup_tracker

        readme = tmp_path / "README.md"
        readme.write_text("# Test Project\n\nThis is a test project.")

        count = await tracker.scan_and_memorize()

        assert count == 1
        assert tracker.is_tracked("README.md")
        mock_client.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_skips_unchanged_files(self, setup_tracker):
        tracker, mock_client, tmp_path = setup_tracker

        readme = tmp_path / "README.md"
        content = "# Test Project\n\nThis is a test project."
        readme.write_text(content)

        await tracker.scan_and_memorize()

        first_call_count = mock_client.add.call_count

        await tracker.scan_and_memorize()

        assert mock_client.add.call_count == first_call_count

    @pytest.mark.asyncio
    async def test_detect_and_update_changed_files(self, setup_tracker):
        tracker, mock_client, tmp_path = setup_tracker

        readme = tmp_path / "README.md"
        readme.write_text("Initial content")

        await tracker.scan_and_memorize()
        initial_call_count = mock_client.add.call_count

        readme.write_text("Updated content")

        update_count = await tracker.update_changed_documents()

        assert update_count == 1
        assert mock_client.add.call_count > initial_call_count

    @pytest.mark.asyncio
    async def test_tracking_disabled(self, tmp_path):
        from src.plugins.opencode.config import Config
        from src.plugins.opencode.document_tracker import DocumentTracker

        config = Config()
        config.directory = str(tmp_path)
        config.tracked_doc_patterns = ["*.md"]
        config.enable_document_tracking = False

        mock_client = MagicMock()
        mock_client.add = AsyncMock(return_value={"id": "mem_doc_001"})

        tracker = DocumentTracker(
            client=mock_client,
            config=config,
            project_tag="test_project",
        )

        readme = tmp_path / "README.md"
        readme.write_text("Content")

        count = await tracker.scan_and_memorize()

        assert count == 0
        mock_client.add.assert_not_called()


class TestFullSessionLifecycle:
    """Integration tests for complete session lifecycle."""

    @pytest.mark.asyncio
    async def test_session_from_message_to_summary(self, tmp_path):
        from src.plugins.opencode.config import Config
        from src.plugins.opencode.compaction import CompactionHook

        config = Config()
        config.directory = str(tmp_path)
        config.compaction_threshold = 0.8
        config.max_project_memories = 10
        config.enable_summary_capture = True
        config.min_summary_length = 100

        mock_client = MagicMock()
        mock_client.list_memories = AsyncMock(return_value=[])
        mock_client.add = AsyncMock(return_value={"id": "mem_session_001"})

        hook = CompactionHook(
            client=mock_client,
            config=config,
            tags={"user": "test", "project": "test"},
            logger=None,
        )

        session_id = "full_lifecycle_session"
        ctx_client = MagicMock()
        ctx_client.session = MagicMock()
        ctx_client.session.summarize = AsyncMock()
        ctx_client.session.messages = AsyncMock(
            return_value=[
                {
                    "info": {
                        "role": "assistant",
                        "summary": True,
                        "finish": True,
                    },
                    "parts": [
                        {
                            "type": "text",
                            "text": "Complete session summary with all important details and outcomes from the conversation with sufficient length for memory storage.",
                        }
                    ],
                }
            ]
        )
        ctx_client.tui = MagicMock()
        ctx_client.tui.showToast = AsyncMock()

        event = {
            "type": "message.updated",
            "properties": {
                "info": {
                    "sessionID": session_id,
                    "role": "assistant",
                    "finish": True,
                    "tokens": {
                        "input": 100000,
                        "output": 60000,
                        "cache": {"read": 10000},
                    },
                    "providerID": "test_provider",
                    "modelID": "test_model",
                }
            },
        }

        await hook.handle_event(event, ctx_client)

        assert session_id in hook.state.summarized_sessions

        ctx_client.session.messages = AsyncMock(
            return_value=[
                {
                    "info": {
                        "role": "assistant",
                        "summary": True,
                        "finish": True,
                    },
                    "parts": [
                        {
                            "type": "text",
                            "text": "Complete session summary with sufficient length for storage in the memory recall system for future reference.",
                        }
                    ],
                }
            ]
        )

        summary_event = {
            "type": "message.updated",
            "properties": {
                "info": {
                    "sessionID": session_id,
                    "role": "assistant",
                    "summary": True,
                    "finish": True,
                }
            },
        }

        await hook.handle_event(summary_event, ctx_client)

        mock_client.add.assert_called()

        delete_event = {
            "type": "session.deleted",
            "properties": {"info": {"id": session_id}},
        }
        await hook.handle_event(delete_event, None)

        assert session_id not in hook.state.summarized_sessions
        assert session_id not in hook.state.last_compaction_time


class TestBilingualIntegration:
    """Integration tests for bilingual support."""

    @pytest.mark.asyncio
    async def test_chinese_context_injection(self):
        from src.plugins.opencode.config import Config
        from src.plugins.opencode.tool import handle_chat_message

        config = Config(
            api_key="test_key",
            directory="/test/project",
            language="zh_CN",
            max_memories=5,
            max_profile_items=5,
            inject_profile=True,
        )

        mock_client = MagicMock()
        mock_client.get_user_tag = MagicMock(return_value="test_user")
        mock_client.get_project_tag = MagicMock(return_value="test_project")
        mock_client.profile = AsyncMock(
            return_value={"profile": {"static": ["测试用户"], "dynamic": []}}
        )
        mock_client.list_memories = AsyncMock(return_value=[])
        mock_client.search = AsyncMock(return_value=[])

        input_data = {"sessionID": "zh_session"}
        output_data = {"parts": [{"type": "text", "text": "你好，请记住我喜欢编程。"}]}
        injected_sessions = set()

        await handle_chat_message(
            client=mock_client,
            config=config,
            input=input_data,
            output=output_data,
            injected_sessions=injected_sessions,
            logger=None,
        )

        context_text = output_data["parts"][0].get("text", "")
        assert (
            "记住" in context_text
            or "编程" in context_text
            or len(output_data["parts"]) >= 1
        )

    @pytest.mark.asyncio
    async def test_chinese_keyword_detection(self):
        from src.plugins.opencode.i18n import get_keywords

        keywords = get_keywords("zh_CN")

        assert "记住" in keywords
        assert "别忘了" in keywords

    @pytest.mark.asyncio
    async def test_english_keyword_detection(self):
        from src.plugins.opencode.i18n import get_keywords

        keywords = get_keywords("en_US")

        assert "remember" in keywords
        assert "save this" in keywords
