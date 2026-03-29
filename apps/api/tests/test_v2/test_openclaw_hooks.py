import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.plugins.openclaw.hooks import (
    format_context,
    deduplicate_memories,
    format_conversation,
)


class TestFormatContext:
    def test_format_with_all_sections(self):
        result = format_context(
            static_facts=["fact1", "fact2"],
            dynamic_facts=["recent1"],
            search_results=[{"content": "result1", "similarity": 0.9}],
            max_results=10,
        )

        assert "User Profile (Persistent)" in result
        assert "fact1" in result
        assert "Recent Context" in result
        assert "recent1" in result
        assert "Relevant Memories" in result
        assert "result1" in result

    def test_format_empty(self):
        result = format_context(
            static_facts=[],
            dynamic_facts=[],
            search_results=[],
            max_results=10,
        )

        assert result == ""

    def test_format_static_only(self):
        result = format_context(
            static_facts=["fact1"],
            dynamic_facts=[],
            search_results=[],
            max_results=10,
        )

        assert "User Profile (Persistent)" in result
        assert "Recent Context" not in result


class TestDeduplicateMemories:
    def test_deduplicate_no_duplicates(self):
        result = deduplicate_memories(
            static_facts=["fact1"],
            dynamic_facts=["recent1"],
            search_results=[{"content": "result1"}],
        )

        assert result["static"] == ["fact1"]
        assert result["dynamic"] == ["recent1"]
        assert len(result["searchResults"]) == 1

    def test_deduplicate_with_duplicates(self):
        result = deduplicate_memories(
            static_facts=["same"],
            dynamic_facts=["same"],
            search_results=[{"content": "same"}],
        )

        assert result["static"] == ["same"]
        assert result["dynamic"] == []
        assert result["searchResults"] == []


class TestFormatConversation:
    def test_format_single_message(self):
        messages = [
            {"role": "user", "content": "Hello"},
        ]

        result = format_conversation(messages)

        assert "[role: user]" in result
        assert "Hello" in result
        assert "[user:end]" in result

    def test_format_multiple_messages(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        result = format_conversation(messages)

        assert "[role: user]" in result
        assert "[role: assistant]" in result
        assert "Hello" in result
        assert "Hi there" in result

    def test_format_list_content(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
        ]

        result = format_conversation(messages)

        assert "Hello" in result
