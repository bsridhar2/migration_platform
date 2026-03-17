"""
LangGraph MigrationState TypedDict — single source of truth for all workflow data.

total=False means all fields are optional (LangGraph partial state updates work correctly).

Reducers (Annotated fields):
  generated_files uses operator.add so that parallel Send fan-out workers each
  append their files and LangGraph merges all lists instead of last-write-wins.
"""
from __future__ import annotations
import operator
from typing import Annotated, Any, Literal
from typing_extensions import TypedDict


class MigrationState(TypedDict, total=False):
    # ── Identity ──────────────────────────────────────────────
    migration_id:          str
    repo_url:              str
    repo_local_path:       str

    # ── Phase A: Repository ingestion ─────────────────────────
    file_manifest:         list[dict[str, Any]]   # list of FileRecord dicts
    entry_points:          list[str]
    language_stats:        dict[str, int]         # {JAVA: 2200, JSP: 1000, ...}

    # ── Phase A: Embeddings ───────────────────────────────────
    chunk_count:           int
    embedding_progress:    float                  # 0.0 – 1.0

    # ── Phase A: Dependency graph ─────────────────────────────
    module_clusters:       list[dict[str, Any]]
    module_count:          int
    circular_dependencies: list[list[str]]
    high_centrality_files: list[tuple[str, float]]

    # ── Phase A: Integration detection ───────────────────────
    soap_integrations:     list[dict[str, Any]]
    soap_report:           dict[str, Any]         # legacy compat key
    soap_integration_count: int
    jdbc_calls:            list[dict[str, Any]]
    jdbc_map:              dict[str, Any]         # legacy compat key
    external_apis:         list[dict[str, Any]]

    # ── Phase A: Architecture + plan ──────────────────────────
    arch_plan:             dict[str, Any]
    migration_plan:        dict[str, Any]
    diagrams:              list[dict[str, Any]]
    sequence_diagrams:     list[dict[str, Any]]
    brd_content:           str

    # ── Phase 6: Human approval gate ─────────────────────────
    approval_status:       Literal["pending", "approved", "rejected"]
    approval_comment:      str
    approval_timestamp:    str | None

    # ── Phase B: Validation ───────────────────────────────────
    validation_report:         dict[str, Any]
    validation_issues_critical: int
    validation_passed:         bool

    # ── Phase B: Code generation ──────────────────────────────
    # Annotated with operator.add so parallel Send fan-out workers all append
    # their file lists; LangGraph merges them instead of last-write-wins.
    generated_files:       Annotated[list[dict[str, Any]], operator.add]
    generation_progress:   float                  # 0.0 – 1.0

    # ── Phase B: Build verification ───────────────────────────
    build_result:          dict[str, Any]         # legacy compat key
    build_results:         list[dict[str, Any]]
    artifact_paths:        dict[str, str] | None

    # ── Runtime ───────────────────────────────────────────────
    current_phase:         str
    current_step:          str
    errors:                list[str]
    warnings:              list[str]
    retry_count:           int
    messages:              list[Any]              # LangGraph message accumulator
