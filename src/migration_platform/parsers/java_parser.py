"""Java AST parser — method-level chunking via javalang."""
from __future__ import annotations
import re
import uuid
from pathlib import Path
import javalang
from migration_platform.domain.models.migration import (
    ChunkType, CodeChunk, FileType
)
from migration_platform.parsers.base import BaseParser

_SOAP_PATTERNS = [
    re.compile(r"import\s+org\.apache\.axis"),
    re.compile(r"new\s+Service\(\)"),
    re.compile(r"\.createCall\("),
    re.compile(r"setTargetEndpointAddress"),
    re.compile(r"new\s+\w+ServiceLocator"),
    re.compile(r"javax\.xml\.rpc\.ServiceFactory"),
]

_JDBC_PATTERNS = [
    re.compile(r"PreparedStatement"),
    re.compile(r"executeQuery\("),
    re.compile(r"executeUpdate\("),
    re.compile(r"DriverManager\.getConnection"),
]

_TABLE_PATTERN = re.compile(
    r"(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)

_SOAP_ENDPOINT_PATTERN = re.compile(
    r'setTargetEndpointAddress\(["\']([^"\']+)["\']'
)


class JavaParser(BaseParser):
    """Parses Java files into per-method CodeChunks."""

    EXTENSIONS = {".java"}

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix in self.EXTENSIONS

    def parse(self, file_path: Path, migration_id: str) -> list[CodeChunk]:
        source = self._read_file(file_path)
        if not source:
            return []

        chunks: list[CodeChunk] = []

        # Class header chunk
        class_chunk = self._make_class_chunk(file_path, source, migration_id)
        if class_chunk:
            chunks.append(class_chunk)

        # Per-method chunks via javalang AST
        try:
            tree = javalang.parse.parse(source)
            for _, class_decl in tree.filter(javalang.tree.ClassDeclaration):
                class_name = class_decl.name
                pkg = tree.package.name if tree.package else ""
                fqn = f"{pkg}.{class_name}" if pkg else class_name

                for method in class_decl.methods or []:
                    chunk = self._method_to_chunk(
                        file_path, source, fqn, method, migration_id
                    )
                    chunks.append(chunk)
        except javalang.parser.JavaSyntaxError:
            # Fall back to line-based chunking
            chunks.extend(self._fallback_chunks(file_path, source, migration_id))

        return chunks

    def _make_class_chunk(
        self, file_path: Path, source: str, migration_id: str
    ) -> CodeChunk | None:
        lines = source.splitlines()
        header_lines = []
        for line in lines[:30]:
            header_lines.append(line)
            if "{" in line and "class" in " ".join(header_lines):
                break

        header = "\n".join(header_lines)
        module = self._infer_module(file_path)

        return CodeChunk(
            chunk_id=str(uuid.uuid4()),
            migration_id=migration_id,
            file_path=str(file_path),
            file_type=FileType.JAVA,
            chunk_type=ChunkType.CLASS_HEADER,
            raw_text=header,
            start_line=1,
            end_line=len(header_lines),
            class_name=file_path.stem,
            module_hint=module,
        )

    def _method_to_chunk(
        self,
        file_path: Path,
        source: str,
        class_fqn: str,
        method: javalang.tree.MethodDeclaration,
        migration_id: str,
    ) -> CodeChunk:
        lines = source.splitlines()
        start = (method.position.line - 1) if method.position else 0
        # Estimate end (find closing brace depth)
        end = min(start + 80, len(lines))
        method_src = "\n".join(lines[start:end])

        # Detect SOAP / JDBC
        soap_ep = None
        soap_op = None
        jdbc_tables: list[str] = []
        chunk_type = ChunkType.METHOD

        for pat in _SOAP_PATTERNS:
            if pat.search(method_src):
                chunk_type = ChunkType.SOAP_OPERATION
                m = _SOAP_ENDPOINT_PATTERN.search(method_src)
                soap_ep = m.group(1) if m else None
                soap_op = method.name
                break

        for pat in _JDBC_PATTERNS:
            if pat.search(method_src):
                chunk_type = ChunkType.JDBC_CALL
                jdbc_tables = _TABLE_PATTERN.findall(method_src)
                break

        return CodeChunk(
            chunk_id=str(uuid.uuid4()),
            migration_id=migration_id,
            file_path=str(file_path),
            file_type=FileType.JAVA,
            chunk_type=chunk_type,
            raw_text=method_src,
            start_line=start + 1,
            end_line=end,
            class_name=class_fqn,
            method_name=method.name,
            module_hint=self._infer_module(file_path),
            soap_endpoint=soap_ep,
            soap_operation=soap_op,
            jdbc_tables=jdbc_tables,
        )

    def _fallback_chunks(
        self, file_path: Path, source: str, migration_id: str
    ) -> list[CodeChunk]:
        """Fallback: chunk by 80-line windows."""
        lines = source.splitlines()
        module = self._infer_module(file_path)
        chunks = []
        for i in range(0, len(lines), 80):
            text = "\n".join(lines[i : i + 80])
            chunks.append(CodeChunk(
                chunk_id=str(uuid.uuid4()),
                migration_id=migration_id,
                file_path=str(file_path),
                file_type=FileType.JAVA,
                chunk_type=ChunkType.METHOD,
                raw_text=text,
                start_line=i + 1,
                end_line=min(i + 80, len(lines)),
                module_hint=module,
            ))
        return chunks

    @staticmethod
    def _infer_module(file_path: Path) -> str:
        """Infer business module from package path."""
        parts = file_path.parts
        for keyword in ("order", "payment", "user", "auth", "report", "product", "invoice"):
            for part in parts:
                if keyword in part.lower():
                    return keyword
        return "core"
