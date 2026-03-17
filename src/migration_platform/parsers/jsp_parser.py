"""JSP parser — scriptlet-block level chunking via BeautifulSoup."""
from __future__ import annotations
import re
import uuid
from pathlib import Path
from bs4 import BeautifulSoup
from migration_platform.domain.models.migration import (
    ChunkType, CodeChunk, FileType
)
from migration_platform.parsers.base import BaseParser

_SCRIPTLET_RE = re.compile(r"<%(?!=)(.*?)%>", re.DOTALL)
_FORM_ACTION_RE = re.compile(r'<form[^>]+action=[\"\']([^\"\' ]+)[\"\']', re.IGNORECASE)
_SERVLET_REF_RE = re.compile(r'<jsp:forward[^>]+page=[\"\']([^\"\' ]+)[\"\']', re.IGNORECASE)


class JspParser(BaseParser):
    """Parses JSP files into per-scriptlet-block CodeChunks."""

    EXTENSIONS = {".jsp", ".jspx"}

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix in self.EXTENSIONS

    def parse(self, file_path: Path, migration_id: str) -> list[CodeChunk]:
        source = self._read_file(file_path)
        if not source:
            return []

        chunks: list[CodeChunk] = []
        lines = source.splitlines()

        # One chunk per scriptlet block
        for match in _SCRIPTLET_RE.finditer(source):
            start_line = source[: match.start()].count("\n") + 1
            end_line = source[: match.end()].count("\n") + 1

            # Include 5 lines of surrounding HTML context
            ctx_start = max(0, start_line - 6)
            ctx_end = min(len(lines), end_line + 5)
            context = "\n".join(lines[ctx_start:ctx_end])

            form_actions = _FORM_ACTION_RE.findall(context)
            servlet_ref = next(iter(_SERVLET_REF_RE.findall(source)), None)

            chunks.append(CodeChunk(
                chunk_id=str(uuid.uuid4()),
                migration_id=migration_id,
                file_path=str(file_path),
                file_type=FileType.JSP,
                chunk_type=ChunkType.JSP_BLOCK,
                raw_text=context,
                start_line=ctx_start + 1,
                end_line=ctx_end,
                module_hint=self._infer_module(file_path),
            ))

        # If no scriptlets, create one chunk for the full page
        if not chunks:
            chunks.append(CodeChunk(
                chunk_id=str(uuid.uuid4()),
                migration_id=migration_id,
                file_path=str(file_path),
                file_type=FileType.JSP,
                chunk_type=ChunkType.JSP_BLOCK,
                raw_text=source[:3000],  # first 3000 chars
                start_line=1,
                end_line=len(lines),
                module_hint=self._infer_module(file_path),
            ))

        return chunks

    @staticmethod
    def _infer_module(file_path: Path) -> str:
        parts = file_path.parts
        for keyword in ("order", "payment", "user", "auth", "report", "product"):
            for part in parts:
                if keyword in part.lower():
                    return keyword
        return "ui"
