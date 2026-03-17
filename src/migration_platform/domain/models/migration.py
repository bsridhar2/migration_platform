"""Core domain models (dataclasses — no ORM dependency)."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import uuid


class MigrationStatus(str, Enum):
    PENDING = "pending"
    INGESTING = "ingesting"
    PARSING = "parsing"
    GRAPHING = "graphing"
    DETECTING = "detecting"
    DESIGNING = "designing"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    VALIDATING = "validating"
    GENERATING = "generating"
    BUILDING = "building"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class FileType(str, Enum):
    JAVA = "JAVA"
    JSP = "JSP"
    JS = "JS"
    HTML = "HTML"
    CSS = "CSS"
    XML = "XML"
    WSDL = "WSDL"
    SQL = "SQL"
    PROPERTIES = "PROPERTIES"
    OTHER = "OTHER"


class ChunkType(str, Enum):
    METHOD = "METHOD"
    CLASS_HEADER = "CLASS_HEADER"
    JSP_BLOCK = "JSP_BLOCK"
    SERVLET_MAPPING = "SERVLET_MAPPING"
    SOAP_OPERATION = "SOAP_OPERATION"
    JDBC_CALL = "JDBC_CALL"
    JS_FUNCTION = "JS_FUNCTION"
    CONFIG = "CONFIG"


@dataclass
class CodeChunk:
    """A semantically meaningful unit of source code."""
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    migration_id: str = ""
    file_path: str = ""
    file_type: FileType = FileType.JAVA
    chunk_type: ChunkType = ChunkType.METHOD
    raw_text: str = ""
    token_count: int = 0
    start_line: int = 0
    end_line: int = 0
    class_name: str | None = None
    method_name: str | None = None
    module_hint: str = "unknown"
    dependencies: list[str] = field(default_factory=list)
    soap_endpoint: str | None = None
    soap_operation: str | None = None
    wsdl_reference: str | None = None
    jdbc_tables: list[str] = field(default_factory=list)
    jdbc_query_type: str | None = None


@dataclass
class SoapIntegration:
    """Detected SOAP integration point."""
    service_name: str
    endpoint_url: str
    wsdl_url: str
    stub_class: str
    operations: list[str]
    callsite_class: str
    callsite_method: str
    callsite_line: int
    migration_option: str = "A"
    complexity: str = "MEDIUM"


@dataclass
class Migration:
    """Root aggregate for a migration run."""
    migration_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    repo_url: str = ""
    repo_local_path: str = ""
    status: MigrationStatus = MigrationStatus.PENDING
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approval_comment: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error_message: str | None = None
    file_counts: dict[str, int] = field(default_factory=dict)
    chunk_count: int = 0
    soap_integration_count: int = 0
    module_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
