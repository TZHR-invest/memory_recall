"""Content type detection for chunking strategy selection."""

import re
from typing import Dict, Any, Optional

from .types import ContentType


CODE_EXTENSIONS = {
    ".py",
    ".pyw",
    ".pyi",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".c",
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hpp",
    ".hxx",
    ".rb",
    ".php",
    ".swift",
    ".sh",
    ".bash",
    ".zsh",
    ".sql",
    ".prisma",
}

CODE_KEYWORDS = [
    "def ",
    "class ",
    "import ",
    "from ",
    "export ",
    "function ",
    "const ",
    "let ",
    "var ",
    "async ",
    "await ",
    "return ",
    "interface ",
    "type ",
    "enum ",
    "pub fn ",
    "fn ",
    "impl ",
    "package ",
    "func ",
    "struct ",
]

MARKDOWN_PATTERNS = [
    re.compile(r"^#{1,6}\s+\S", re.MULTILINE),
    re.compile(r"^\*{3,}$|^-{3,}$|^_{3,}$", re.MULTILINE),
    re.compile(r"^\s*[-*+]\s+\S", re.MULTILINE),
    re.compile(r"^\s*\d+\.\s+\S", re.MULTILINE),
]

CONVERSATION_PATTERNS = [
    re.compile(r"(?i)^(user|assistant|system|human|ai)[:：]\s*", re.MULTILINE),
    re.compile(r"(?i)^(q|a|question|answer)[:：]\s*", re.MULTILINE),
    re.compile(r"(?i)^>\s*(用户|助手|问题|回答)", re.MULTILINE),
]


class ContentDetector:
    """Detects content type for chunking strategy selection."""

    def detect(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContentType:
        metadata = metadata or {}

        if metadata.get("content_type"):
            return ContentType(metadata["content_type"])

        file_ext = metadata.get("file_extension", "")
        if file_ext:
            ext = file_ext.lower()
            if not ext.startswith("."):
                ext = "." + ext
            if ext in CODE_EXTENSIONS:
                return ContentType.CODE

        return self._detect_from_content(content)

    def _detect_from_content(self, content: str) -> ContentType:
        if not content or not content.strip():
            return ContentType.UNKNOWN

        code_score = self._score_code(content)
        markdown_score = self._score_markdown(content)
        conversation_score = self._score_conversation(content)

        scores = {
            ContentType.CODE: code_score,
            ContentType.MARKDOWN: markdown_score,
            ContentType.CONVERSATION: conversation_score,
        }

        max_type = max(scores, key=scores.get)
        if scores[max_type] > 0:
            return max_type

        return ContentType.DOCUMENT

    def _score_code(self, content: str) -> int:
        score = 0

        keyword_count = sum(1 for kw in CODE_KEYWORDS if kw in content)
        score += keyword_count * 2

        if re.search(
            r"^\s*(def |class |function |const |async |import |export )",
            content,
            re.MULTILINE,
        ):
            score += 5

        if re.search(r"[:：]\s*->\s*\w", content):
            score += 3

        if re.search(r"^\s*@\w+", content, re.MULTILINE):
            score += 3

        brace_balance = content.count("{") - content.count("}")
        if abs(brace_balance) <= 2 and "{" in content:
            score += 2

        indent_pattern = re.compile(r"^    [a-zA-Z_]", re.MULTILINE)
        if indent_pattern.search(content):
            score += 2

        return score

    def _score_markdown(self, content: str) -> int:
        score = 0

        for pattern in MARKDOWN_PATTERNS:
            matches = pattern.findall(content)
            score += len(matches)

        if re.search(r"`{3}\w*\n", content):
            score += 3

        if re.search(r"\[.+?\]\(.+?\)", content):
            score += 2

        return score

    def _score_conversation(self, content: str) -> int:
        score = 0

        for pattern in CONVERSATION_PATTERNS:
            matches = pattern.findall(content)
            score += len(matches) * 3

        return score


def detect_content_type(
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> ContentType:
    detector = ContentDetector()
    return detector.detect(content, metadata)


content_detector = ContentDetector()
