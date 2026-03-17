"""
JsParser — function-level chunking of JavaScript / TypeScript files.

Uses regex-based extraction to split JS/TS files into per-function chunks.
Handles ES modules, CommonJS, and jQuery-style IIFE patterns common in
legacy monoliths migrating from JSP + vanilla JS.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from migration_platform.domain.models.migration import ChunkType, CodeChunk, FileType
from migration_platform.parsers.base import BaseParser

_FUNCTION_RE = re.compile(
    r"(?:^|\n)"
    r"(?:export\s+)?(?:default\s+)?"
    r"(?:"
    r"function\s+(\w+)\s*\([^)]*\)"
    r"|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"
    r"|(?:const|let|var)\s+(\w+)\s*=\s*function"
    r")",
    re.MULTILINE,
)

_AJAX_RE = re.compile(
    r"(?:fetch|axios|XMLHttpRequest|\$\.ajax|\$\.get|\$\.post)\s*\(",
    re.IGNORECASE,
)


class JsParser(BaseParser):
    """
    Parses JavaScript and TypeScript files into per-function CodeChunks.
    Falls back to 60-line blocks for files that can't be structured.
    """

    EXTENSIONS = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.EXTENSIONS

    def parse(self, file_path: Path, migration_id: str) -> list[CodeChunk]:
        source = self._read_file(file_path)
        if not source:
            return []

        lines = source.splitlines()
        function_starts: list[tuple[int, str]] = []

        for m in _FUNCTION_RE.finditer(source):
            fn_name = m.group(1) or m.group(2) or m.group(3) or "anonymous"
            line_no = source[: m.start()].count("\n")
            function_starts.append((line_no, fn_name))

        if not function_starts:
            return self._fallback_chunks(source, file_path, migration_id)

        chunks: list[CodeChunk] = []
        for idx, (start_line, fn_name) in enumerate(function_starts):
            end_line = (
                function_starts[idx + 1][0] - 1
                if idx + 1 < len(function_starts)
                else len(lines)
            )
            end_line = min(end_line, start_line + 120)
            block = "\n".join(lines[start_line:end_line]).strip()
            if not block:
                continue

            chunks.append(
                CodeChunk(
                    chunk_id=str(uuid.uuid4()),
                    migration_id=migration_id,
                    file_path=str(file_path),
                    file_type=FileType.JS,
                    chunk_type=ChunkType.JS_FUNCTION,
                    class_name="",
                    method_name=fn_name,
                    raw_text=block,
                    start_line=start_line + 1,
                    end_line=end_line,
                )
            )

        return chunks

    def _fallback_chunks(
        self, source: str, file_path: Path, migration_id: str
    ) -> list[CodeChunk]:
        lines = source.splitlines()
        chunks: list[CodeChunk] = []
        for i in range(0, len(lines), 60):
            block = "\n".join(lines[i : i + 60]).strip()
            if block:
                chunks.append(
                    CodeChunk(
                        chunk_id=str(uuid.uuid4()),
                        migration_id=migration_id,
                        file_path=str(file_path),
                        file_type=FileType.JS,
                        chunk_type=ChunkType.JS_FUNCTION,
                        class_name="",
                        method_name="",
                        raw_text=block,
                        start_line=i + 1,
                        end_line=min(i + 60, len(lines)),
                    )
                )
        return chunks
