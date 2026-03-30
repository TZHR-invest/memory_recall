"""
Unit tests for OpenCode plugin document tracker.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock


class TestDocumentHashComputation:
    def test_compute_hash_consistent(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_config.tracked_doc_patterns = ["README*.md"]

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        content = "Test content for hashing"
        hash1 = tracker._compute_hash(content)
        hash2 = tracker._compute_hash(content)

        assert hash1 == hash2
        assert len(hash1) == 64

    def test_compute_hash_different_content(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        hash1 = tracker._compute_hash("Content A")
        hash2 = tracker._compute_hash("Content B")

        assert hash1 != hash2

    def test_compute_hash_empty_content(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        hash_val = tracker._compute_hash("")

        assert len(hash_val) == 64

    def test_compute_hash_unicode(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        hash1 = tracker._compute_hash("中文内容")
        hash2 = tracker._compute_hash("中文内容")
        hash3 = tracker._compute_hash("English content")

        assert hash1 == hash2
        assert hash1 != hash3


class TestLanguageDetection:
    def test_detect_chinese(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        assert tracker._detect_language("这是中文内容") == "zh_CN"
        assert tracker._detect_language("# 项目说明\n这是文档") == "zh_CN"

    def test_detect_english(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        assert tracker._detect_language("This is English content") == "en_US"
        assert (
            tracker._detect_language("# Project README\nThis is documentation")
            == "en_US"
        )

    def test_detect_mixed(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        mostly_chinese = "这是中文这是中文这是中文这是中文 a little English"
        mostly_english = "This is English This is English This is English 一点中文"

        assert tracker._detect_language(mostly_chinese) == "zh_CN"
        assert tracker._detect_language(mostly_english) == "en_US"


class TestDocumentChunking:
    def test_chunk_by_headers(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        content = """# Main Title

Introduction paragraph.

## Section 1

Content for section 1.

## Section 2

Content for section 2.
"""

        chunks = tracker._chunk_by_headers(content)

        assert len(chunks) >= 2
        assert any("Main Title" in chunk for chunk in chunks)
        assert any("Section 1" in chunk for chunk in chunks)

    def test_chunk_no_headers(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        content = "Just plain text\nwithout any headers\nmultiple lines"

        chunks = tracker._chunk_by_headers(content)

        assert len(chunks) == 1

    def test_chunk_empty_content(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        chunks = tracker._chunk_by_headers("")

        assert len(chunks) == 0


class TestDocumentFormatting:
    def test_format_document_memory_english(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        formatted = tracker._format_document_memory(
            "README.md",
            "# My Project\n\nThis is a test project.",
            "en_US",
        )

        assert "[Document: README.md]" in formatted
        assert "# My Project" in formatted
        assert "[Metadata]" in formatted
        assert "Path: README.md" in formatted
        assert "Type: project-doc" in formatted

    def test_format_document_memory_chinese(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        formatted = tracker._format_document_memory(
            "README.md",
            "# 我的项目\n\n这是一个测试项目。",
            "zh_CN",
        )

        assert "[文档: README.md]" in formatted
        assert "# 我的项目" in formatted
        assert "[元数据]" in formatted
        assert "路径: README.md" in formatted
        assert "类型: project-doc" in formatted


class TestChangeDetection:
    @pytest.fixture
    def tracker(self, tmp_path):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_config.directory = str(tmp_path)
        mock_config.tracked_doc_patterns = ["*.md"]
        mock_config.enable_document_tracking = True

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        return tracker

    def test_detect_new_file(self, tracker, tmp_path):
        test_file = tmp_path / "test.md"
        test_file.write_text("Initial content")

        assert (
            tracker._compute_hash("Initial content") not in tracker.file_hashes.values()
        )

    def test_detect_unchanged_file(self, tracker, tmp_path):
        content = "Same content"
        test_file = tmp_path / "test.md"
        test_file.write_text(content)

        tracker.file_hashes["test.md"] = tracker._compute_hash(content)

        current_hash = tracker._compute_hash(content)

        assert tracker.file_hashes["test.md"] == current_hash

    def test_detect_changed_file(self, tracker, tmp_path):
        old_content = "Old content"
        new_content = "New content"

        tracker.file_hashes["test.md"] = tracker._compute_hash(old_content)

        current_hash = tracker._compute_hash(new_content)

        assert tracker.file_hashes["test.md"] != current_hash


class TestDocumentTracking:
    @pytest.fixture
    def tracker(self, tmp_path):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_client.add = AsyncMock(return_value={"id": "mem_doc_001"})

        mock_config = MagicMock()
        mock_config.directory = str(tmp_path)
        mock_config.tracked_doc_patterns = ["*.md", "README*"]
        mock_config.enable_document_tracking = True

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        return tracker

    def test_is_tracked(self, tracker):
        tracker.file_hashes["test.md"] = "some_hash"

        assert tracker.is_tracked("test.md") is True
        assert tracker.is_tracked("other.md") is False

    def test_remove_tracked_file(self, tracker):
        tracker.file_hashes["test.md"] = "some_hash"
        tracker.memory_ids["test.md"] = "mem_001"

        tracker.remove_tracked_file("test.md")

        assert "test.md" not in tracker.file_hashes
        assert "test.md" not in tracker.memory_ids

    def test_get_tracked_files(self, tracker):
        tracker.file_hashes = {
            "file1.md": "hash1",
            "file2.md": "hash2",
        }

        tracked = tracker.get_tracked_files()

        assert len(tracked) == 2
        assert "file1.md" in tracked
        assert "file2.md" in tracked


class TestLargeDocumentHandling:
    @pytest.fixture
    def tracker(self):
        from src.plugins.opencode.document_tracker import DocumentTracker

        mock_client = MagicMock()
        mock_client.add = AsyncMock(return_value={"id": "mem_chunk_001"})

        mock_config = MagicMock()
        mock_config.directory = "/test"
        mock_config.tracked_doc_patterns = ["*.md"]
        mock_config.enable_document_tracking = True

        tracker = DocumentTracker(
            client=mock_client,
            config=mock_config,
            project_tag="test_project",
        )

        return tracker

    def test_small_document_not_chunked(self, tracker):
        small_content = "Small content"

        assert len(small_content) < 10000
        chunks = tracker._chunk_by_headers(small_content)

        assert len(chunks) <= 1

    def test_large_document_would_chunk(self, tracker):
        large_content = (
            """# Section 1
"""
            + ("Content " * 2000)
            + """
# Section 2
"""
            + ("More content " * 2000)
        )

        assert len(large_content) > 10000

        chunks = tracker._chunk_by_headers(large_content)

        assert len(chunks) >= 1


class TestLargeDocumentChunkingIntegration:
    """Integration tests for large document chunking workflow."""

    @pytest.fixture
    def tracker_with_client(self, tmp_path):
        from src.plugins.opencode.config import Config
        from src.plugins.opencode.document_tracker import (
            DocumentTracker,
            LARGE_DOC_THRESHOLD,
        )

        config = Config()
        config.directory = str(tmp_path)
        config.tracked_doc_patterns = ["*.md"]
        config.enable_document_tracking = True

        mock_client = MagicMock()
        mock_client.add = AsyncMock(return_value={"id": "mem_chunked_001"})

        tracker = DocumentTracker(
            client=mock_client,
            config=config,
            project_tag="test_project",
            logger=None,
        )

        return tracker, mock_client, tmp_path, LARGE_DOC_THRESHOLD

    @pytest.mark.asyncio
    async def test_large_document_is_chunked(self, tracker_with_client):
        tracker, mock_client, tmp_path, threshold = tracker_with_client

        sections = []
        for i in range(10):
            sections.append(f"# Section {i + 1}\n\n")
            sections.append(("Content for section " * 150) + "\n\n")

        large_content = "".join(sections)
        assert len(large_content) > threshold

        large_file = tmp_path / "LARGE_DOC.md"
        large_file.write_text(large_content)

        count = await tracker.scan_and_memorize()

        assert count == 1
        assert mock_client.add.call_count >= 2

    @pytest.mark.asyncio
    async def test_chunked_documents_have_correct_metadata(self, tracker_with_client):
        tracker, mock_client, tmp_path, threshold = tracker_with_client

        content = "# Main Title\n\n" + ("Paragraph " * 500) + "\n\n"
        content += "# Second Section\n\n" + ("More text " * 500)

        assert len(content) > threshold

        doc_file = tmp_path / "document.md"
        doc_file.write_text(content)

        await tracker.scan_and_memorize()

        calls = mock_client.add.call_args_list
        assert len(calls) >= 2

        first_call = calls[0][1]
        assert "container_tag" in first_call
        assert first_call["memory_type"] == "project-doc"
        assert first_call["is_static"] is True

    @pytest.mark.asyncio
    async def test_small_document_not_chunked_path(self, tracker_with_client):
        tracker, mock_client, tmp_path, threshold = tracker_with_client

        small_content = "# Small Doc\n\n" + ("Short " * 100)
        assert len(small_content) < threshold

        small_file = tmp_path / "small.md"
        small_file.write_text(small_content)

        count = await tracker.scan_and_memorize()

        assert count == 1
        assert mock_client.add.call_count == 1

    @pytest.mark.asyncio
    async def test_document_with_many_headers(self, tracker_with_client):
        tracker, mock_client, tmp_path, threshold = tracker_with_client

        sections = []
        for i in range(30):
            sections.append(f"## Subsection {i + 1}\n\n")
            sections.append(("Item content text " * 200) + "\n")

        content = "# Main Header\n\n" + "".join(sections)

        assert len(content) > threshold, (
            f"Content length {len(content)} should exceed threshold {threshold}"
        )

        large_file = tmp_path / "many_headers.md"
        large_file.write_text(content)

        await tracker.scan_and_memorize()

        assert mock_client.add.call_count >= 3

    @pytest.mark.asyncio
    async def test_empty_document_handling(self, tracker_with_client):
        tracker, mock_client, tmp_path, _ = tracker_with_client

        empty_file = tmp_path / "empty.md"
        empty_file.write_text("")

        count = await tracker.scan_and_memorize()

        assert count == 0
        mock_client.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_whitespace_only_document(self, tracker_with_client):
        tracker, mock_client, tmp_path, _ = tracker_with_client

        whitespace_file = tmp_path / "whitespace.md"
        whitespace_file.write_text("   \n\n   \n\t\t\n   ")

        count = await tracker.scan_and_memorize()

        assert count == 1
        mock_client.add.assert_called_once()
