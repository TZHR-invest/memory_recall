"""
Document processing service with LLM-based extraction.

Based on Supermemory's approach:
- LLM-based document summarization
- LLM-based title/topic extraction
- Semantic chunking support
"""

import asyncio
import json
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from src.llm.client import get_llm_client


@dataclass
class DocumentMetadata:
    title: Optional[str] = None
    summary: Optional[str] = None
    key_topics: List[str] = None
    language: str = "zh"
    content_type: str = "text"
    confidence: float = 0.8

    def __post_init__(self):
        if self.key_topics is None:
            self.key_topics = []


DOCUMENT_PROCESSING_PROMPT_ZH = """分析以下文档内容，提取关键信息。

文档内容:
{content}

请提取以下信息并以 JSON 格式返回:
1. title: 文档标题或主题（简洁，不超过20字）
2. summary: 文档摘要（概括主要内容，100-200字）
3. key_topics: 关键主题列表（3-5个关键词）
4. language: 语言（zh/en）
5. content_type: 内容类型（article/conversation/code/technical/other）

返回格式:
{{
    "title": "文档标题",
    "summary": "本文主要讨论了...",
    "key_topics": ["主题1", "主题2", "主题3"],
    "language": "zh",
    "content_type": "article"
}}

注意:
- 标题要简洁准确
- 摘要要涵盖主要观点
- 关键主题要有代表性
- 只返回 JSON，不要其他解释"""


DOCUMENT_PROCESSING_PROMPT_EN = """Analyze the following document content and extract key information.

Document content:
{content}

Please extract the following information and return in JSON format:
1. title: Document title or topic (concise, max 20 words)
2. summary: Document summary (main points, 100-200 words)
3. key_topics: List of key topics (3-5 keywords)
4. language: Language (zh/en)
5. content_type: Content type (article/conversation/code/technical/other)

Return format:
{{
    "title": "Document Title",
    "summary": "This document discusses...",
    "key_topics": ["topic1", "topic2", "topic3"],
    "language": "en",
    "content_type": "article"
}}

Note:
- Title should be concise and accurate
- Summary should cover main points
- Key topics should be representative
- Return JSON only, no other explanations"""


SECTION_SUMMARY_PROMPT_ZH = """为以下文档片段生成一个简洁的摘要。

文档片段 {section_num}/{total_sections}:
{content}

要求:
- 摘要长度: 100-150字
- 概括这个片段的主要内容和观点
- 保持客观准确

直接返回摘要文本，不要其他内容。"""


SECTION_SUMMARY_PROMPT_EN = """Generate a concise summary for the following document section.

Section {section_num}/{total_sections}:
{content}

Requirements:
- Summary length: 100-150 words
- Cover main content and points of this section
- Keep it objective and accurate

Return the summary text directly, nothing else."""


MERGE_SUMMARIES_PROMPT_ZH = """以下是一个文档的多个片段摘要，请将它们合并成一个完整的文档摘要。

片段摘要:
{summaries}

要求:
- 合并所有片段摘要
- 去除重复内容
- 保持逻辑连贯
- 最终长度: 150-250字
- 概括整个文档的核心内容

直接返回合并后的摘要文本，不要其他内容。"""


MERGE_SUMMARIES_PROMPT_EN = """Below are summaries of multiple sections from a document. Please merge them into a complete document summary.

Section summaries:
{summaries}

Requirements:
- Merge all section summaries
- Remove duplicate content
- Keep logical coherence
- Final length: 150-250 words
- Cover the core content of the entire document

Return the merged summary text directly, nothing else."""


SUMMARY_ONLY_PROMPT_ZH = """为以下文档生成一个简洁的摘要。

文档内容:
{content}

要求:
- 摘要长度: 100-200字
- 概括主要内容和观点
- 保持客观准确

直接返回摘要文本，不要其他内容。"""


SUMMARY_ONLY_PROMPT_EN = """Generate a concise summary for the following document.

Document content:
{content}

Requirements:
- Summary length: 100-200 words
- Cover main content and points
- Keep it objective and accurate

Return the summary text directly, nothing else."""


TITLE_ONLY_PROMPT_ZH = """为以下文档生成一个简洁的标题。

文档内容:
{content}

要求:
- 标题长度: 不超过20字
- 准确概括文档主题
- 简洁明了

直接返回标题文本，不要其他内容。"""


TITLE_ONLY_PROMPT_EN = """Generate a concise title for the following document.

Document content:
{content}

Requirements:
- Title length: max 20 words
- Accurately summarize the document topic
- Keep it concise and clear

Return the title text directly, nothing else."""


class DocumentProcessor:
    def __init__(self, timeout: float = 30.0):
        self.llm_client = None
        self.timeout = timeout
        try:
            self.llm_client = get_llm_client()
        except Exception:
            pass

    async def process_document(
        self,
        content: str,
        max_content_length: int = 4000,
    ) -> DocumentMetadata:
        if not self.llm_client:
            return self._fallback_metadata(content)

        truncated_content = self._truncate_content(content, max_content_length)

        language = self._detect_language(truncated_content)
        prompt = self._get_processing_prompt(truncated_content, language)

        try:
            result = await asyncio.wait_for(
                self.llm_client.aextract_json(
                    prompt,
                    0.3,
                ),
                timeout=self.timeout,
            )

            if result:
                return DocumentMetadata(
                    title=result.get("title"),
                    summary=result.get("summary"),
                    key_topics=result.get("key_topics", []),
                    language=result.get("language", language),
                    content_type=result.get("content_type", "text"),
                    confidence=0.9,
                )
        except Exception:
            pass

        return self._fallback_metadata(content)

    async def extract_summary(
        self,
        content: str,
        max_content_length: int = 4000,
        max_section_length: int = 3000,
    ) -> Optional[str]:
        if not self.llm_client:
            return self._fallback_summary(content)

        if len(content) <= max_content_length:
            truncated_content = self._truncate_content(content, max_content_length)
            language = self._detect_language(truncated_content)
            prompt = self._get_summary_prompt(truncated_content, language)

            try:
                result = await asyncio.wait_for(
                    self.llm_client.achat(
                        [{"role": "user", "content": prompt}],
                        0.3,
                        300,
                    ),
                    timeout=self.timeout,
                )
                return result.strip() if result else None
            except Exception:
                return self._fallback_summary(content)

        return await self._hierarchical_summary(content, max_section_length)

    async def extract_title(
        self,
        content: str,
        max_content_length: int = 2000,
    ) -> Optional[str]:
        if not self.llm_client:
            return self._fallback_title(content)

        truncated_content = self._truncate_content(content, max_content_length)
        language = self._detect_language(truncated_content)
        prompt = self._get_title_prompt(truncated_content, language)

        try:
            result = await asyncio.wait_for(
                self.llm_client.achat(
                    [{"role": "user", "content": prompt}],
                    0.3,
                    100,
                ),
                timeout=self.timeout,
            )
            return result.strip() if result else None
        except Exception:
            return self._fallback_title(content)

    async def extract_key_topics(
        self,
        content: str,
        max_content_length: int = 4000,
    ) -> List[str]:
        metadata = await self.process_document(content, max_content_length)
        return metadata.key_topics

    def _truncate_content(self, content: str, max_length: int) -> str:
        if len(content) <= max_length:
            return content

        truncated = content[:max_length]

        last_sentence_end = max(
            truncated.rfind("。"),
            truncated.rfind("！"),
            truncated.rfind("？"),
            truncated.rfind("."),
            truncated.rfind("!"),
            truncated.rfind("?"),
        )

        if last_sentence_end > max_length * 0.8:
            truncated = truncated[: last_sentence_end + 1]

        return truncated

    def _detect_language(self, text: str) -> str:
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        total_chars = len(text.replace(" ", "").replace("\n", ""))

        if total_chars > 0 and chinese_chars / total_chars > 0.3:
            return "zh"
        return "en"

    def _get_processing_prompt(self, content: str, language: str) -> str:
        if language == "zh":
            return DOCUMENT_PROCESSING_PROMPT_ZH.format(content=content)
        return DOCUMENT_PROCESSING_PROMPT_EN.format(content=content)

    def _get_summary_prompt(self, content: str, language: str) -> str:
        if language == "zh":
            return SUMMARY_ONLY_PROMPT_ZH.format(content=content)
        return SUMMARY_ONLY_PROMPT_EN.format(content=content)

    def _get_title_prompt(self, content: str, language: str) -> str:
        if language == "zh":
            return TITLE_ONLY_PROMPT_ZH.format(content=content)
        return TITLE_ONLY_PROMPT_EN.format(content=content)

    async def _hierarchical_summary(
        self,
        content: str,
        max_section_length: int = 3000,
    ) -> Optional[str]:
        language = self._detect_language(content)
        sections = self._split_into_sections(content, max_section_length)

        if not sections:
            return self._fallback_summary(content)

        section_summaries = []
        total_sections = len(sections)

        for i, section in enumerate(sections, 1):
            try:
                if language == "zh":
                    prompt = SECTION_SUMMARY_PROMPT_ZH.format(
                        section_num=i,
                        total_sections=total_sections,
                        content=section,
                    )
                else:
                    prompt = SECTION_SUMMARY_PROMPT_EN.format(
                        section_num=i,
                        total_sections=total_sections,
                        content=section,
                    )

                result = await asyncio.wait_for(
                    self.llm_client.achat(
                        [{"role": "user", "content": prompt}],
                        0.3,
                        200,
                    ),
                    timeout=self.timeout,
                )

                if result:
                    section_summaries.append(result.strip())
            except Exception:
                continue

        if not section_summaries:
            return self._fallback_summary(content)

        if len(section_summaries) == 1:
            return section_summaries[0]

        return await self._merge_summaries(section_summaries, language)

    async def _merge_summaries(
        self,
        summaries: List[str],
        language: str,
    ) -> Optional[str]:
        combined = "\n\n".join(f"片段 {i + 1}: {s}" for i, s in enumerate(summaries))

        if language == "zh":
            prompt = MERGE_SUMMARIES_PROMPT_ZH.format(summaries=combined)
        else:
            prompt = MERGE_SUMMARIES_PROMPT_EN.format(summaries=combined)

        try:
            result = await asyncio.wait_for(
                self.llm_client.achat(
                    [{"role": "user", "content": prompt}],
                    0.3,
                    400,
                ),
                timeout=self.timeout,
            )
            return result.strip() if result else None
        except Exception:
            return " ".join(summaries)

    def _split_into_sections(
        self,
        content: str,
        max_section_length: int,
    ) -> List[str]:
        if len(content) <= max_section_length:
            return [content]

        sections = []
        paragraphs = re.split(r"\n\s*\n", content)

        current_section = []
        current_length = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_length = len(para)

            if current_length + para_length > max_section_length and current_section:
                sections.append("\n\n".join(current_section))
                current_section = [para]
                current_length = para_length
            else:
                current_section.append(para)
                current_length += para_length

        if current_section:
            sections.append("\n\n".join(current_section))

        return sections

    def _fallback_metadata(self, content: str) -> DocumentMetadata:
        return DocumentMetadata(
            title=self._fallback_title(content),
            summary=self._fallback_summary(content),
            key_topics=[],
            language=self._detect_language(content),
            content_type="text",
            confidence=0.5,
        )

    def _fallback_title(self, content: str) -> str:
        lines = content.strip().split("\n")
        if lines:
            first_line = lines[0].strip()
            if len(first_line) <= 50:
                return first_line
            return first_line[:50] + "..."
        return "Untitled"

    def _fallback_summary(self, content: str) -> str:
        cleaned = content.strip().replace("\n", " ")
        if len(cleaned) <= 200:
            return cleaned
        return cleaned[:200] + "..."


document_processor = DocumentProcessor()
