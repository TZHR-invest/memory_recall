"""Conversation chunking strategy based on speaker turns."""

import re
from typing import Dict, Any, List, Optional

from .types import ChunkingStrategy, TextChunk, ContentType, ChunkConfig


class ConversationChunker(ChunkingStrategy):
    """Chunker for conversations based on speaker turns."""

    def __init__(self, config: Optional[ChunkConfig] = None):
        super().__init__(config)
        self._turn_patterns = [
            re.compile(r"(?i)^(user|assistant|system|human|ai)[:：]\s*", re.MULTILINE),
            re.compile(r"(?i)^(q|a|question|answer)[:：]\s*", re.MULTILINE),
            re.compile(r"(?i)^>\s*(用户|助手|问题|回答)[:：]?\s*", re.MULTILINE),
        ]

    def chunk(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> List[TextChunk]:
        if not text or not text.strip():
            return []

        turns = self._extract_turns(text)

        if not turns:
            return self._chunk_by_paragraphs(
                text, metadata, document_title, document_summary
            )

        max_size = self.config.max_chunk_size or self.config.max_chunk_tokens
        chunks = []

        current_turns = []
        current_size = 0
        current_start = 0

        for turn in turns:
            turn_size = self.estimate_tokens_nws(turn["content"])

            if current_size + turn_size > max_size and current_turns:
                chunk_content = "\n\n".join(t["content"] for t in current_turns)
                chunks.append(
                    self._create_chunk(
                        chunk_content,
                        len(chunks),
                        current_start,
                        turn["start"],
                        metadata,
                        turns=current_turns,
                        document_title=document_title,
                        document_summary=document_summary,
                    )
                )
                current_turns = [turn]
                current_size = turn_size
                current_start = turn["start"]
            else:
                current_turns.append(turn)
                current_size += turn_size

        if current_turns:
            chunk_content = "\n\n".join(t["content"] for t in current_turns)
            chunks.append(
                self._create_chunk(
                    chunk_content,
                    len(chunks),
                    current_start,
                    turns[-1]["end"],
                    metadata,
                    turns=current_turns,
                    document_title=document_title,
                    document_summary=document_summary,
                )
            )

        return chunks

    def _extract_turns(self, text: str) -> List[Dict[str, Any]]:
        matches = []

        for pattern in self._turn_patterns:
            for match in pattern.finditer(text):
                matches.append(
                    {
                        "start": match.start(),
                        "end": match.end(),
                        "speaker": match.group(1).lower()
                        if match.group(1)
                        else "unknown",
                        "marker_end": match.end(),
                    }
                )

        if not matches:
            return []

        matches.sort(key=lambda m: m["start"])

        turns = []
        for i, match in enumerate(matches):
            start = match["start"]
            end = matches[i + 1]["start"] if i + 1 < len(matches) else len(text)

            content = text[start:end].strip()
            speaker = match["speaker"]

            turns.append(
                {
                    "start": start,
                    "end": end,
                    "speaker": speaker,
                    "content": content,
                }
            )

        return turns

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
        turns: Optional[List[Dict[str, Any]]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> TextChunk:
        embedded_content = None
        if self.config.enable_contextual_retrieval:
            context_parts = []
            if document_title:
                context_parts.append(f"对话主题: {document_title}")

            if turns:
                speakers = list(set(t["speaker"] for t in turns))
                context_parts.append(f"参与者: {', '.join(speakers)}")
                context_parts.append(f"轮次: {len(turns)}")

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
            content_type=ContentType.CONVERSATION,
        )


conversation_chunker = ConversationChunker()
