"""XML parser — web.xml servlet mappings and WSDL operations."""
from __future__ import annotations
import uuid
from pathlib import Path
from bs4 import BeautifulSoup
from migration_platform.domain.models.migration import (
    ChunkType, CodeChunk, FileType
)
from migration_platform.parsers.base import BaseParser


class XmlParser(BaseParser):
    """Parses web.xml and WSDL files into structured CodeChunks."""

    def can_parse(self, file_path: Path) -> bool:
        if file_path.name == "web.xml":
            return True
        if file_path.suffix in (".wsdl", ".xml") and "wsdl" in file_path.name.lower():
            return True
        return False

    def parse(self, file_path: Path, migration_id: str) -> list[CodeChunk]:
        source = self._read_file(file_path)
        if not source:
            return []

        if file_path.name == "web.xml":
            return self._parse_web_xml(file_path, source, migration_id)
        return self._parse_wsdl(file_path, source, migration_id)

    def _parse_web_xml(
        self, file_path: Path, source: str, migration_id: str
    ) -> list[CodeChunk]:
        soup = BeautifulSoup(source, "xml")
        chunks: list[CodeChunk] = []

        for mapping in soup.find_all("servlet-mapping"):
            name_tag = mapping.find("servlet-name")
            pattern_tag = mapping.find("url-pattern")
            if not (name_tag and pattern_tag):
                continue

            text = (
                f"servlet-name: {name_tag.text.strip()}\n"
                f"url-pattern: {pattern_tag.text.strip()}\n"
                f"raw: {str(mapping)}"
            )
            chunks.append(CodeChunk(
                chunk_id=str(uuid.uuid4()),
                migration_id=migration_id,
                file_path=str(file_path),
                file_type=FileType.XML,
                chunk_type=ChunkType.SERVLET_MAPPING,
                raw_text=text,
                module_hint="config",
            ))
        return chunks

    def _parse_wsdl(
        self, file_path: Path, source: str, migration_id: str
    ) -> list[CodeChunk]:
        soup = BeautifulSoup(source, "xml")
        chunks: list[CodeChunk] = []

        # WSDL 1.1 operations
        for op in soup.find_all(["operation", "wsdl:operation"]):
            op_name = op.get("name", "unknown")
            service = soup.find(["service", "wsdl:service"])
            service_name = service.get("name", "UnknownService") if service else "UnknownService"

            port = soup.find(["port", "wsdl:port"])
            address = None
            if port:
                addr_tag = port.find(["address", "soap:address", "soap12:address"])
                if addr_tag:
                    address = addr_tag.get("location")

            text = (
                f"service: {service_name}\n"
                f"operation: {op_name}\n"
                f"endpoint: {address or 'unknown'}\n"
                f"raw: {str(op)[:500]}"
            )
            chunks.append(CodeChunk(
                chunk_id=str(uuid.uuid4()),
                migration_id=migration_id,
                file_path=str(file_path),
                file_type=FileType.WSDL,
                chunk_type=ChunkType.SOAP_OPERATION,
                raw_text=text,
                soap_endpoint=address,
                soap_operation=op_name,
                wsdl_reference=str(file_path),
                module_hint="integration",
            ))
        return chunks
