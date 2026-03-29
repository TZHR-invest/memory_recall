"""AST-aware code chunking for Python, JavaScript, and TypeScript."""

import ast
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

from .types import ChunkingStrategy, TextChunk, ChunkContext, ContentType, ChunkConfig
from .context_enricher import ContextEnricher


@dataclass
class CodeEntity:
    """Represents a semantic unit in code (function, class, method)."""

    name: str
    entity_type: str  # function, class, method, etc.
    start_line: int
    end_line: int
    start_col: int = 0
    end_col: int = 0
    signature: Optional[str] = None
    docstring: Optional[str] = None
    parent: Optional[str] = None
    scope_chain: List[str] = None

    def __post_init__(self):
        if self.scope_chain is None:
            self.scope_chain = []


class CodeChunker(ChunkingStrategy):
    """AST-aware code chunker for Python, JavaScript, and TypeScript."""

    def __init__(self, config: Optional[ChunkConfig] = None):
        super().__init__(config)
        self.enricher = ContextEnricher(max_chars=self.config.context_max_chars)

        self._js_func_pattern = re.compile(
            r"(?:async\s+)?function\s+(\w+)\s*\([^)]*\)", re.MULTILINE
        )
        self._js_arrow_pattern = re.compile(
            r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=>])\s*=>",
            re.MULTILINE,
        )
        self._ts_interface_pattern = re.compile(
            r"interface\s+(\w+)\s*(?:<[^>]+>)?\s*\{", re.MULTILINE
        )
        self._ts_type_pattern = re.compile(
            r"type\s+(\w+)\s*(?:<[^>]+>)?\s*=", re.MULTILINE
        )
        self._js_class_pattern = re.compile(
            r"class\s+(\w+)(?:\s+extends\s+\w+)?\s*\{", re.MULTILINE
        )

    def chunk(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        document_title: Optional[str] = None,
        document_summary: Optional[str] = None,
    ) -> List[TextChunk]:
        if not text or not text.strip():
            return []

        language = self._detect_language(text, metadata)

        if language == "python":
            return self._chunk_python(text, metadata)
        elif language in ("javascript", "typescript"):
            return self._chunk_js_ts(text, metadata, language)
        else:
            return self._chunk_generic(text, metadata)

    def _detect_language(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        metadata = metadata or {}

        if metadata.get("language"):
            return metadata["language"].lower()

        file_ext = metadata.get("file_extension", "")
        ext_map = {
            ".py": "python",
            ".pyw": "python",
            ".pyi": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
        }
        if file_ext.lower() in ext_map:
            return ext_map[file_ext.lower()]

        if "def " in text or "import " in text and "from " in text:
            return "python"
        if "function " in text or "const " in text or "interface " in text:
            return "javascript"

        return "unknown"

    def _chunk_python(
        self, code: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[TextChunk]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return self._chunk_generic(code, metadata)

        entities = self._extract_python_entities(tree, code)
        return self._entities_to_chunks(entities, code, metadata, "python")

    def _extract_python_entities(self, tree: ast.AST, code: str) -> List[CodeEntity]:
        entities = []
        lines = code.split("\n")

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if hasattr(node, "names"):
                    for alias in node.names:
                        imports.append(alias.name)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(
                node, ast.AsyncFunctionDef
            ):
                entity = self._create_function_entity(node, lines)
                entity.dependencies = imports
                entities.append(entity)

            elif isinstance(node, ast.ClassDef):
                methods = [
                    child
                    for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]

                if methods:
                    for child in methods:
                        method_entity = self._create_function_entity(
                            child, lines, parent=node.name
                        )
                        entities.append(method_entity)
                else:
                    class_entity = CodeEntity(
                        name=node.name,
                        entity_type="class",
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        start_col=node.col_offset,
                        end_col=node.end_col_offset or 0,
                        signature=f"class {node.name}",
                        docstring=ast.get_docstring(node),
                    )
                    entities.append(class_entity)

        return entities

    def _create_function_entity(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        lines: List[str],
        parent: Optional[str] = None,
    ) -> CodeEntity:
        args = []
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {ast.unparse(arg.annotation)}"
            args.append(arg_str)

        return_type = ""
        if node.returns:
            return_type = f" -> {ast.unparse(node.returns)}"

        async_prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        signature = f"{async_prefix}def {node.name}({', '.join(args)}){return_type}"

        return CodeEntity(
            name=node.name,
            entity_type="method" if parent else "function",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            start_col=node.col_offset,
            end_col=node.end_col_offset or 0,
            signature=signature,
            docstring=ast.get_docstring(node),
            parent=parent,
        )

    def _chunk_js_ts(
        self,
        code: str,
        metadata: Optional[Dict[str, Any]] = None,
        language: str = "javascript",
    ) -> List[TextChunk]:
        entities = self._extract_js_ts_entities(code)
        return self._entities_to_chunks(entities, code, metadata, language)

    def _extract_js_ts_entities(self, code: str) -> List[CodeEntity]:
        entities = []
        lines = code.split("\n")

        for match in self._js_func_pattern.finditer(code):
            line_num = code[: match.start()].count("\n") + 1
            end_line = self._find_block_end(code, match.end())
            entities.append(
                CodeEntity(
                    name=match.group(1),
                    entity_type="function",
                    start_line=line_num,
                    end_line=end_line,
                    signature=match.group(0).strip(),
                )
            )

        for match in self._js_arrow_pattern.finditer(code):
            line_num = code[: match.start()].count("\n") + 1
            end_line = self._find_block_end(code, match.end())
            entities.append(
                CodeEntity(
                    name=match.group(1),
                    entity_type="function",
                    start_line=line_num,
                    end_line=end_line,
                    signature=match.group(0).strip(),
                )
            )

        for match in self._js_class_pattern.finditer(code):
            line_num = code[: match.start()].count("\n") + 1
            end_line = self._find_block_end(code, match.end())
            entities.append(
                CodeEntity(
                    name=match.group(1),
                    entity_type="class",
                    start_line=line_num,
                    end_line=end_line,
                    signature=f"class {match.group(1)}",
                )
            )

        for match in self._ts_interface_pattern.finditer(code):
            line_num = code[: match.start()].count("\n") + 1
            end_line = self._find_block_end(code, match.end())
            entities.append(
                CodeEntity(
                    name=match.group(1),
                    entity_type="interface",
                    start_line=line_num,
                    end_line=end_line,
                    signature=f"interface {match.group(1)}",
                )
            )

        for match in self._ts_type_pattern.finditer(code):
            line_num = code[: match.start()].count("\n") + 1
            end_line = line_num
            for i in range(line_num, len(lines)):
                if lines[i - 1].rstrip().endswith(";"):
                    end_line = i
                    break
            entities.append(
                CodeEntity(
                    name=match.group(1),
                    entity_type="type",
                    start_line=line_num,
                    end_line=end_line,
                    signature=f"type {match.group(1)}",
                )
            )

        entities.sort(key=lambda e: e.start_line)
        return entities

    def _find_block_end(self, code: str, start_pos: int) -> int:
        brace_count = 0
        in_string = False
        string_char = None
        i = start_pos

        while i < len(code):
            char = code[i]

            if in_string:
                if char == "\\" and i + 1 < len(code):
                    i += 2
                    continue
                if char == string_char:
                    in_string = False
            else:
                if char in ('"', "'", "`"):
                    in_string = True
                    string_char = char
                elif char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        return code[:i].count("\n") + 1

            i += 1

        return code.count("\n") + 1

    def _entities_to_chunks(
        self,
        entities: List[CodeEntity],
        code: str,
        metadata: Optional[Dict[str, Any]] = None,
        language: str = "unknown",
    ) -> List[TextChunk]:
        if not entities:
            return self._chunk_generic(code, metadata)

        lines = code.split("\n")
        chunks = []

        for entity in entities:
            start_idx = max(0, entity.start_line - 1)
            end_idx = min(len(lines), entity.end_line)
            content = "\n".join(lines[start_idx:end_idx])

            size = self.estimate_tokens_nws(content)

            if size > self.config.max_chunk_size:
                sub_chunks = self._split_large_entity(
                    content, entity, lines, start_idx, end_idx
                )
                chunks.extend(sub_chunks)
                continue

            context = ChunkContext(
                scope_chain=entity.scope_chain
                or ([entity.parent] if entity.parent else []),
                signatures=[entity.signature] if entity.signature else [],
                dependencies=entity.dependencies
                if hasattr(entity, "dependencies")
                else [],
                language=language,
            )

            enriched_content = content
            if self.config.enable_context:
                context_header = context.to_comment_header(
                    self.config.context_max_chars
                )
                if context_header:
                    enriched_content = f"{context_header}\n\n{content}"

            chunks.append(
                TextChunk(
                    content=content,
                    embedded_content=enriched_content,
                    position=len(chunks),
                    token_count=size,
                    start_offset=sum(len(l) + 1 for l in lines[:start_idx]),
                    end_offset=sum(len(l) + 1 for l in lines[:end_idx]),
                    metadata=metadata or {},
                    context=context,
                    content_type=ContentType.CODE,
                )
            )

        return chunks

    def _split_large_entity(
        self,
        content: str,
        entity: CodeEntity,
        lines: List[str],
        start_idx: int,
        end_idx: int,
    ) -> List[TextChunk]:
        chunks = []
        current_lines = []
        current_size = 0
        current_start = start_idx

        for i in range(start_idx, end_idx):
            line = lines[i]
            line_size = self.estimate_tokens_nws(line)

            if current_size + line_size > self.config.max_chunk_size and current_lines:
                chunk_content = "\n".join(current_lines)
                chunks.append(
                    TextChunk(
                        content=chunk_content,
                        position=len(chunks),
                        token_count=current_size,
                        start_offset=sum(len(l) + 1 for l in lines[:current_start]),
                        end_offset=sum(len(l) + 1 for l in lines[:i]),
                        metadata={
                            "entity_name": entity.name,
                            "entity_type": entity.entity_type,
                        },
                        content_type=ContentType.CODE,
                    )
                )
                current_lines = []
                current_size = 0
                current_start = i

            current_lines.append(line)
            current_size += line_size

        if current_lines:
            chunk_content = "\n".join(current_lines)
            chunks.append(
                TextChunk(
                    content=chunk_content,
                    position=len(chunks),
                    token_count=current_size,
                    start_offset=sum(len(l) + 1 for l in lines[:current_start]),
                    end_offset=sum(len(l) + 1 for l in lines[:end_idx]),
                    metadata={
                        "entity_name": entity.name,
                        "entity_type": entity.entity_type,
                    },
                    content_type=ContentType.CODE,
                )
            )

        return chunks

    def _chunk_generic(
        self, code: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[TextChunk]:
        lines = code.split("\n")
        chunks = []
        current_lines = []
        current_size = 0
        current_start = 0

        for i, line in enumerate(lines):
            line_size = self.estimate_tokens_nws(line)

            if current_size + line_size > self.config.max_chunk_size and current_lines:
                chunk_content = "\n".join(current_lines)
                chunks.append(
                    TextChunk(
                        content=chunk_content,
                        position=len(chunks),
                        token_count=current_size,
                        start_offset=sum(len(l) + 1 for l in lines[:current_start]),
                        end_offset=sum(len(l) + 1 for l in lines[:i]),
                        metadata=metadata or {},
                        content_type=ContentType.CODE,
                    )
                )
                current_lines = []
                current_size = 0
                current_start = i

            current_lines.append(line)
            current_size += line_size

        if current_lines:
            chunk_content = "\n".join(current_lines)
            chunks.append(
                TextChunk(
                    content=chunk_content,
                    position=len(chunks),
                    token_count=current_size,
                    start_offset=sum(len(l) + 1 for l in lines[:current_start]),
                    end_offset=len(code),
                    metadata=metadata or {},
                    content_type=ContentType.CODE,
                )
            )

        return chunks


code_chunker = CodeChunker()
