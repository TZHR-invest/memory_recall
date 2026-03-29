"""Markdown chunking strategy based on heading hierarchy."""

import re
from typing import Dict, Any, List, Optional

from .types import ChunkingStrategy, TextChunk, ContentType, ChunkConfig


class MarkdownChunker(ChunkingStrategy):
    """Chunker for Markdown documents using heading hierarchy."""

    def __init__(self, config: Optional[ChunkConfig] = None):
        super().__init__(config)
        self._heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        self._code_block_pattern = re.compile(r"```[\s\S]*?```")

    def chunk(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> List[TextChunk]:
        if not text or not text.strip():
            return []

        max_size = self.config.max_chunk_size or self.config.max_chunk_tokens

        headings = list(self._heading_pattern.finditer(text))

        if not headings:
            return self._chunk_by_paragraphs(
                text, metadata, document_title, document_summary
            )

        sections = []

        for i, match in enumerate(headings):
            start = match.start()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)

            heading_level = len(match.group(1))
            heading_text = match.group(2).strip()
            section_content = text[start:end].strip()

            sections.append(
                {
                    "level": heading_level,
                    "title": heading_text,
                    "content": section_content,
                    "start": start,
                    "end": end,
                }
            )

        chunks = []

        for section in sections:
            section_size = self.estimate_tokens_nws(section["content"])

            if section_size <= max_size:
                chunks.append(
                    self._create_chunk(
                        section["content"],
                        len(chunks),
                        section["start"],
                        section["end"],
                        metadata,
                        section_title=section["title"],
                        section_level=section["level"],
                        document_title=document_title,
                        document_summary=document_summary,
                    )
                )
            else:
                sub_chunks = self._split_section(
                    section, metadata, document_title, document_summary
                )
                for sub in sub_chunks:
                    sub.position = len(chunks)
                    chunks.append(sub)

        return chunks

    def _split_section(
        self,
        section: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> List[TextChunk]:
        content = section["content"]
        max_size = self.config.max_chunk_size or self.config.max_chunk_tokens

        code_blocks = list(self._code_block_pattern.finditer(content))

        if code_blocks:
            return self._split_with_code_blocks(
                content, section, metadata, document_title, document_summary
            )

        paragraphs = re.split(r"\n\s*\n", content)
        chunks = []
        current_para = []
        current_size = 0
        current_start = section["start"]

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_size = self.estimate_tokens_nws(para)

            if current_size + para_size > max_size and current_para:
                chunk_content = "\n\n".join(current_para)
                chunks.append(
                    self._create_chunk(
                        chunk_content,
                        0,
                        current_start,
                        current_start + len(chunk_content),
                        metadata,
                        section_title=section["title"],
                        section_level=section["level"],
                        document_title=document_title,
                        document_summary=document_summary,
                    )
                )
                current_para = [para]
                current_size = para_size
                current_start = section["start"] + content.find(para)
            else:
                current_para.append(para)
                current_size += para_size

        if current_para:
            chunk_content = "\n\n".join(current_para)
            chunks.append(
                self._create_chunk(
                    chunk_content,
                    0,
                    current_start,
                    section["end"],
                    metadata,
                    section_title=section["title"],
                    section_level=section["level"],
                    document_title=document_title,
                    document_summary=document_summary,
                )
            )

        return chunks

    def _split_with_code_blocks(
        self,
        content: str,
        section: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> List[TextChunk]:
        chunks = []
        last_end = 0

        for match in self._code_block_pattern.finditer(content):
            if match.start() > last_end:
                text_before = content[last_end : match.start()].strip()
                if text_before:
                    chunks.append(
                        self._create_chunk(
                            text_before,
                            0,
                            section["start"] + last_end,
                            section["start"] + match.start(),
                            metadata,
                            section_title=section["title"],
                            document_title=document_title,
                            document_summary=document_summary,
                        )
                    )

            code_block = match.group(0)
            chunks.append(
                self._create_chunk(
                    code_block,
                    0,
                    section["start"] + match.start(),
                    section["start"] + match.end(),
                    metadata,
                    section_title=section["title"],
                    document_title=document_title,
                    document_summary=document_summary,
                )
            )
            last_end = match.end()

        if last_end < len(content):
            remaining = content[last_end:].strip()
            if remaining:
                chunks.append(
                    self._create_chunk(
                        remaining,
                        0,
                        section["start"] + last_end,
                        section["end"],
                        metadata,
                        section_title=section["title"],
                        document_title=document_title,
                        document_summary=document_summary,
                    )
                )

        return chunks

    def _chunk_by_paragraphs(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> List[TextChunk]:
        paragraphs = re.split(r"\n\s*\n", text)
        chunks = []
        current_para = []
        current_size = 0
        current_start = 0

        max_size = self.config.max_chunk_size or self.config.max_chunk_tokens

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_size = self.estimate_tokens_nws(para)

            if current_size + para_size > max_size and current_para:
                chunk_content = "\n\n".join(current_para)
                chunks.append(
                    self._create_chunk(
                        chunk_content,
                        len(chunks),
                        current_start,
                        current_start + len(chunk_content),
                        metadata,
                        document_title=document_title,
                        document_summary=document_summary,
                    )
                )
                current_para = [para]
                current_size = para_size
            else:
                current_para.append(para)
                current_size += para_size

        if current_para:
            chunk_content = "\n\n".join(current_para)
            chunks.append(
                self._create_chunk(
                    chunk_content,
                    len(chunks),
                    current_start,
                    len(text),
                    metadata,
                    document_title=document_title,
                    document_summary=document_summary,
                )
            )

        return chunks

    def _create_chunk(
        self,
        content: str,
        position: int,
        start_offset: int,
        end_offset: int,
        metadata: Optional[Dict[str, Any]] = None,
        section_title: Optional[str] = None,
        section_level: Optional[int] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> TextChunk:
        embedded_content = None
        if self.config.enable_contextual_retrieval:
            context_parts = []
            if document_title:
                context_parts.append(f"文档主题: {document_title}")
            if section_title:
                prefix = "#" * (section_level or 1)
                context_parts.append(f"章节: {prefix} {section_title}")
            if document_summary:
                context_parts.append(f"摘要: {document_summary[:100]}")

            if context_parts:
                embedded_content = "\n".join(context_parts) + "\n\n" + content
            else:
                embedded_content = content

        return TextChunk(
            content=content,
            embedded_content=embedded_content,
            position=position,
            token_count=self.estimate_tokens_nws(content),
            start_offset=start_offset,
            end_offset=end_offset,
            metadata=metadata or {},
            content_type=ContentType.MARKDOWN,
        )


markdown_chunker = MarkdownChunker()
