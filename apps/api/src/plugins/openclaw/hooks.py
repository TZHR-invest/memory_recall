from typing import Dict, Any, List, Optional
from src.plugins.openclaw.client import OpenClawClient


def format_context(
    static_facts: List[str],
    dynamic_facts: List[str],
    search_results: List[Dict[str, Any]],
    max_results: int = 10,
) -> str:
    deduped = deduplicate_memories(static_facts, dynamic_facts, search_results)
    statics = deduped["static"][:max_results]
    dynamics = deduped["dynamic"][:max_results]
    searches = deduped["searchResults"][:max_results]

    if not statics and not dynamics and not searches:
        return ""

    sections = []

    if statics:
        sections.append(
            "## User Profile (Persistent)\n" + "\n".join(f"- {f}" for f in statics)
        )

    if dynamics:
        sections.append("## Recent Context\n" + "\n".join(f"- {f}" for f in dynamics))

    if searches:
        lines = []
        for r in searches:
            content = r.get("content", r.get("memory", ""))
            similarity = r.get("similarity")
            pct = f"[{int(similarity * 100)}%]" if similarity else ""
            lines.append(f"- {content} {pct}".strip())
        sections.append("## Relevant Memories\n" + "\n".join(lines))

    intro = "Background context from long-term memory. Use silently to inform understanding."
    disclaimer = "Do not proactively bring up memories unless directly relevant."

    return (
        f"<memory-context>\n{intro}\n\n"
        + "\n\n".join(sections)
        + f"\n\n{disclaimer}\n</memory-context>"
    )


def deduplicate_memories(
    static_facts: List[str],
    dynamic_facts: List[str],
    search_results: List[Dict[str, Any]],
) -> Dict[str, List]:
    seen = set()

    unique_static = []
    for m in static_facts:
        if m not in seen:
            seen.add(m)
            unique_static.append(m)

    unique_dynamic = []
    for m in dynamic_facts:
        if m not in seen:
            seen.add(m)
            unique_dynamic.append(m)

    unique_search = []
    for r in search_results:
        memory = r.get("content", r.get("memory", ""))
        if memory and memory not in seen:
            seen.add(memory)
            unique_search.append(r)

    return {
        "static": unique_static,
        "dynamic": unique_dynamic,
        "searchResults": unique_search,
    }


def format_conversation(messages: List[Dict[str, Any]]) -> str:
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                block.get("text", "")
                for block in content
                if block.get("type") == "text"
            )
        if content:
            parts.append(f"[role: {role}]\n{content}\n[{role}:end]")

    return "\n\n".join(parts)


async def recall_handler(
    client: OpenClawClient,
    config: Dict[str, Any],
    event: Dict[str, Any],
    ctx: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    prompt = event.get("prompt", "")
    if not prompt or len(prompt) < 5:
        return None

    try:
        profile = await client.profile(query=prompt)
        context = format_context(
            static_facts=profile.get("profile", {}).get("static", []),
            dynamic_facts=profile.get("profile", {}).get("dynamic", []),
            search_results=profile.get("searchResults", []),
            max_results=config.get("maxRecallResults", 10),
        )

        if context:
            return {"prependContext": context}
    except Exception:
        pass

    return None


async def capture_handler(
    client: OpenClawClient,
    config: Dict[str, Any],
    event: Dict[str, Any],
    ctx: Dict[str, Any],
):
    if not config.get("autoCapture", True):
        return

    messages = event.get("messages", [])
    if not messages:
        return

    content = format_conversation(messages)
    if len(content) < 10:
        return

    try:
        await client.store(content=content)
    except Exception:
        pass
