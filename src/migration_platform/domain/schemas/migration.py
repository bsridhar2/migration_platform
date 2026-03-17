"""Pydantic v2 request/response schemas."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, HttpUrl


class StartMigrationRequest(BaseModel):
    repo_url: str = Field(..., description="Git repository URL to migrate")
    branch: str = Field("main", description="Branch to checkout")
    description: str = Field("", description="Optional project description")


class MigrationStatusResponse(BaseModel):
    migration_id: str
    status: str
    approval_status: str
    repo_url: str
    created_at: datetime
    updated_at: datetime
    file_counts: dict[str, int] = {}        # embedded files per type
    total_file_counts: dict[str, int] = {}  # all cloned files per type
    chunk_count: int = 0
    soap_integration_count: int = 0
    module_count: int = 0
    error_message: str | None = None
    progress_pct: float = 0.0


class ProgressEvent(BaseModel):
    migration_id: str
    event_type: str
    phase: str
    message: str
    progress_pct: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = {}


class DiagramResponse(BaseModel):
    diagram_type: str
    title: str
    mermaid_source: str
    module: str | None = None


class ArtifactsResponse(BaseModel):
    migration_id: str
    approval_status: str
    diagrams: list[DiagramResponse] = []
    soap_report: dict[str, Any] = {}
    migration_plan: dict[str, Any] = {}
    sequence_diagrams: list[DiagramResponse] = []
    arch_plan: dict[str, Any] = {}          # bounded contexts for UI display
    brd_content: str = ""
    download_urls: dict[str, str] = {}
