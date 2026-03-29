"""Context enrichment for code chunks."""

import re
from typing import List, Optional, Set

from .types import ChunkContext


class ContextEnricher:
    """Enriches code chunks with semantic context."""

    def __init__(self, max_chars: int = 200):
        self.max_chars = max_chars

    def enrich(
        self,
        content: str,
        scope_chain: Optional[List[str]] = None,
        signatures: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        language: Optional[str] = None,
    ) -> str:
        context = ChunkContext(
            scope_chain=scope_chain or [],
            signatures=signatures or [],
            dependencies=dependencies or [],
            language=language,
        )

        header = context.to_comment_header(self.max_chars)

        if header:
            return f"{header}\n\n{content}"
        return content

    def extract_scope_chain(
        self,
        entity_name: str,
        parent: Optional[str] = None,
        grandparent: Optional[str] = None,
    ) -> List[str]:
        chain = []
        if grandparent:
            chain.append(grandparent)
        if parent:
            chain.append(parent)
        if entity_name:
            chain.append(entity_name)
        return chain

    def extract_signatures(
        self,
        content: str,
        language: str = "python",
    ) -> List[str]:
        signatures = []

        if language == "python":
            func_pattern = re.compile(
                r"^(?:async\s+)?def\s+(\w+)\s*\([^)]*\)(?:\s*->\s*[^:]+)?", re.MULTILINE
            )
            class_pattern = re.compile(r"^class\s+(\w+)", re.MULTILINE)

            for match in func_pattern.finditer(content):
                signatures.append(match.group(0).strip())
            for match in class_pattern.finditer(content):
                signatures.append(match.group(0).strip())

        elif language in ("javascript", "typescript"):
            patterns = [
                re.compile(r"(?:async\s+)?function\s+\w+\s*\([^)]*\)", re.MULTILINE),
                re.compile(
                    r"(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=>])\s*=>",
                    re.MULTILINE,
                ),
                re.compile(r"class\s+\w+", re.MULTILINE),
            ]

            for pattern in patterns:
                for match in pattern.finditer(content):
                    signatures.append(match.group(0).strip())

        return signatures[:5]

    def extract_dependencies(
        self,
        content: str,
        language: str = "python",
    ) -> List[str]:
        dependencies = set()

        if language == "python":
            import_pattern = re.compile(
                r"^(?:from\s+(\S+)\s+)?import\s+([^\n]+)", re.MULTILINE
            )

            for match in import_pattern.finditer(content):
                if match.group(1):
                    dependencies.add(match.group(1).split(".")[0])
                else:
                    for name in match.group(2).split(","):
                        name = name.strip().split(" as ")[0].strip()
                        if name:
                            dependencies.add(name.split(".")[0])

        elif language in ("javascript", "typescript"):
            import_patterns = [
                re.compile(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]", re.MULTILINE),
                re.compile(r"import\s+['\"]([^'\"]+)['\"]", re.MULTILINE),
                re.compile(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", re.MULTILINE),
            ]

            for pattern in import_patterns:
                for match in pattern.finditer(content):
                    dep = match.group(1)
                    if not dep.startswith("."):
                        dependencies.add(dep.split("/")[0])

        return sorted(list(dependencies))[:10]

    def format_context(
        self,
        scope_chain: Optional[List[str]] = None,
        signatures: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        file_path: Optional[str] = None,
    ) -> str:
        lines = []

        if file_path:
            parts = file_path.split("/")[-3:]
            lines.append(f"# {'/'.join(parts)}")

        if scope_chain:
            lines.append(f"# Scope: {' > '.join(scope_chain)}")

        if signatures:
            sigs = ", ".join(signatures[:3])
            if len(signatures) > 3:
                sigs += ", ..."
            lines.append(f"# Defines: {sigs}")

        if dependencies:
            deps = ", ".join(dependencies[:5])
            if len(dependencies) > 5:
                deps += ", ..."
            lines.append(f"# Uses: {deps}")

        return "\n".join(lines)


context_enricher = ContextEnricher()
