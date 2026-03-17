"""Abstract base parser — Strategy pattern for file-type parsers."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from migration_platform.domain.models.migration import CodeChunk, FileType


class BaseParser(ABC):
    """All parsers implement this interface."""

    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """Return True if this parser handles the given file."""

    @abstractmethod
    def parse(self, file_path: Path, migration_id: str) -> list[CodeChunk]:
        """Parse a file and return a list of code chunks."""

    @staticmethod
    def _read_file(file_path: Path) -> str | None:
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                return file_path.read_text(encoding=encoding)
            except (UnicodeDecodeError, OSError):
                continue
        return None


class ParserRegistry:
    """Factory — selects the correct parser for a given file."""

    def __init__(self) -> None:
        self._parsers: list[BaseParser] = []

    def register(self, parser: BaseParser) -> None:
        self._parsers.append(parser)

    def get_parser(self, file_path: Path) -> BaseParser | None:
        for parser in self._parsers:
            if parser.can_parse(file_path):
                return parser
        return None

    def parse_file(
        self, file_path: Path, migration_id: str
    ) -> list[CodeChunk]:
        parser = self.get_parser(file_path)
        if parser is None:
            return []
        try:
            return parser.parse(file_path, migration_id)
        except Exception as exc:
            from migration_platform.core.logging import get_logger
            get_logger(__name__).warning(
                "Parser error", file=str(file_path), error=str(exc)
            )
            return []
