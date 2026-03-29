import re
from typing import Dict, Any, List, Optional


MEMORY_KEYWORDS = [
    "remember",
    "save this",
    "don't forget",
    "note that",
    "keep in mind",
    "important",
    "for future reference",
    "write down",
    "log this",
]


def detect_memory_keyword(text: str) -> bool:
    text_without_code = remove_code_blocks(text)
    pattern = r"\b(" + "|".join(re.escape(kw) for kw in MEMORY_KEYWORDS) + r")\b"
    return bool(re.search(pattern, text_without_code, re.IGNORECASE))


def remove_code_blocks(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    return text


def strip_private_tags(content: str) -> str:
    return re.sub(r"<private>[\s\S]*?</private>", "", content)


def is_fully_private(content: str) -> bool:
    stripped = strip_private_tags(content).strip()
    return len(stripped) == 0


def format_context(
    profile: Optional[Dict[str, Any]],
    project_memories: Optional[List[Dict[str, Any]]],
    user_memories: Optional[List[Dict[str, Any]]],
) -> str:
    parts = ["[SUPERMEMORY]"]

    if profile and profile.get("profile"):
        static_facts = profile["profile"].get("static", [])
        dynamic_facts = profile["profile"].get("dynamic", [])

        if static_facts:
            parts.append("\nUser Profile:")
            for fact in static_facts[:5]:
                parts.append(f"- {fact}")

        if dynamic_facts:
            parts.append("\nRecent Context:")
            for fact in dynamic_facts[:5]:
                parts.append(f"- {fact}")

    if project_memories:
        parts.append("\nProject Knowledge:")
        for mem in project_memories[:10]:
            similarity = mem.get("similarity", 1.0)
            content = mem.get("content", mem.get("memory", ""))
            pct = int(similarity * 100)
            parts.append(f"- [{pct}%] {content}")

    if user_memories:
        parts.append("\nRelevant Memories:")
        for mem in user_memories[:5]:
            similarity = mem.get("similarity", 0)
            content = mem.get("content", mem.get("memory", ""))
            pct = int(similarity * 100)
            parts.append(f"- [{pct}%] {content}")

    if len(parts) == 1:
        return ""

    return "\n".join(parts)


MEMORY_NUDGE = """[MEMORY TRIGGER DETECTED]
The user wants you to remember something. Use the `supermemory` tool with `mode: "add"` to save this information.

- Use `scope: "project"` for project-specific preferences
- Use `scope: "user"` for cross-project preferences

DO NOT skip this step."""
