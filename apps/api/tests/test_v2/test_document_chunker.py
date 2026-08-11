"""
Tests for DocumentChunker HTML tag stripping (v5.2.3 recall quality optimization).

Verifies:
- Plain HTML tags are stripped (content preserved)
- HTML inside markdown code blocks is preserved (JSX / generics not mangled)
- Empty input returns empty chunks
"""

import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.document_chunker import DocumentChunker


class TestHTMLStripping:
    def setup_method(self):
        self.chunker = DocumentChunker()

    def test_strips_plain_html_tags(self):
        text = '<div align="center"><h1>Memory Recall</h1><p>AI 记忆系统</p></div>'
        cleaned = self.chunker._strip_html_preserving_code(text)
        assert "<div" not in cleaned
        assert "<h1>" not in cleaned
        assert "Memory Recall" in cleaned
        assert "AI 记忆系统" in cleaned

    def test_preserves_code_block_html(self):
        text = "示例：\n```jsx\nconst x = <div>hello</div>;\n```\n结束"
        cleaned = self.chunker._strip_html_preserving_code(text)
        assert "<div>hello</div>" in cleaned

    def test_preserves_generics_in_code_block(self):
        text = "看 ```ts\nfunction f<T>(a: T) {}\n``` 这个函数"
        cleaned = self.chunker._strip_html_preserving_code(text)
        assert "<T>" in cleaned

    def test_chunk_output_has_no_html_tags(self):
        text = "<div>段落一</div>\n\n<p>段落二</p>"
        chunks = self.chunker.chunk(text)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert "<" not in chunk.content

    def test_empty_input_returns_empty(self):
        assert self.chunker.chunk("") == []
        assert self.chunker.chunk("   ") == []
