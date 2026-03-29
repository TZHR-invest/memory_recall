import pytest
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.plugins.opencode.context import (
    detect_memory_keyword,
    remove_code_blocks,
    strip_private_tags,
    is_fully_private,
    format_context,
)


class TestDetectMemoryKeyword:
    def test_detect_remember(self):
        text = "Please remember this important fact"
        assert detect_memory_keyword(text) is True

    def test_detect_save_this(self):
        text = "Save this for later"
        assert detect_memory_keyword(text) is True

    def test_detect_dont_forget(self):
        text = "Don't forget to call me"
        assert detect_memory_keyword(text) is True

    def test_no_keyword(self):
        text = "Hello, how are you?"
        assert detect_memory_keyword(text) is False

    def test_keyword_in_code_block(self):
        text = "```remember this``` but not here"
        assert detect_memory_keyword(text) is False


class TestRemoveCodeBlocks:
    def test_remove_fenced_code(self):
        text = "Before ```code here``` after"
        result = remove_code_blocks(text)
        assert "```" not in result
        assert "Before" in result
        assert "after" in result

    def test_remove_inline_code(self):
        text = "Use `remember` function"
        result = remove_code_blocks(text)
        assert "`" not in result


class TestStripPrivateTags:
    def test_strip_single_tag(self):
        content = "Public <private>secret</private> end"
        result = strip_private_tags(content)
        assert result == "Public  end"

    def test_strip_multiple_tags(self):
        content = "<private>secret1</private> public <private>secret2</private>"
        result = strip_private_tags(content)
        assert "secret1" not in result
        assert "secret2" not in result


class TestIsFullyPrivate:
    def test_fully_private(self):
        content = "<private>all content</private>"
        assert is_fully_private(content) is True

    def test_partially_private(self):
        content = "public <private>secret</private>"
        assert is_fully_private(content) is False

    def test_no_private_tags(self):
        content = "all public content"
        assert is_fully_private(content) is False


class TestFormatContext:
    def test_format_with_profile(self):
        profile = {
            "profile": {
                "static": ["fact1"],
                "dynamic": ["recent1"],
            }
        }

        result = format_context(profile, None, None)

        assert "[SUPERMEMORY]" in result
        assert "User Profile:" in result
        assert "fact1" in result

    def test_format_empty(self):
        result = format_context(None, None, None)
        assert result == ""

    def test_format_with_project_memories(self):
        project_memories = [
            {"content": "proj fact", "similarity": 1.0},
        ]

        result = format_context(None, project_memories, None)

        assert "Project Knowledge:" in result
        assert "proj fact" in result
