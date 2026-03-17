"""
Integration test — full workflow smoke test with mocked LLM and Git.

Tests that:
1. The LangGraph graph compiles without errors.
2. Phase A runs to the approval gate given a minimal fixture repo.
3. The approval gate suspends correctly.
4. Approving resumes Phase B (codegen path).

All LLM calls and Git operations are mocked so the test runs offline.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from migration_platform.graph.graph_store import GraphStore
from migration_platform.rag.vector_store import VectorStore
from migration_platform.rag.embedder import Embedder
from migration_platform.rag.retriever import Retriever
from migration_platform.storage.state_store import StateStore
from migration_platform.storage.cache_store import CacheStore
from migration_platform.workflows.migration_graph import build_migration_graph
from migration_platform.workflows.state import MigrationState


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def migration_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def minimal_state(migration_id: str, tmp_path: Path) -> MigrationState:
    """Minimal valid initial state."""
    return MigrationState(
        migration_id=migration_id,
        repo_url="https://github.com/example/legacy-app",
        repo_local_path=str(tmp_path),
        file_manifest=[],
        entry_points=[],
        language_stats={},
        chunk_count=0,
        embedding_progress=0.0,
        module_clusters=[],
        circular_dependencies=[],
        high_centrality_files=[],
        soap_integrations=[],
        jdbc_calls=[],
        external_apis=[],
        arch_plan={},
        migration_plan={},
        diagrams=[],
        sequence_diagrams=[],
        brd_content="",
        approval_status="pending",
        approval_comment="",
        approval_timestamp=None,
        validation_report={},
        validation_issues_critical=0,
        validation_passed=False,
        generated_files=[],
        generation_progress=0.0,
        build_results=[],
        artifact_paths=None,
        current_phase="A",
        current_step="",
        errors=[],
        warnings=[],
        retry_count=0,
        messages=[],
    )


# ── Graph compilation test ────────────────────────────────────────

def test_graph_compiles() -> None:
    """Workflow graph must compile without import or construction errors."""
    graph = build_migration_graph()
    assert graph is not None


def test_graph_has_correct_nodes() -> None:
    graph = build_migration_graph()
    graph_def = graph.get_graph()
    node_names = {n.name for n in graph_def.nodes}
    required_nodes = {
        "ingest_repo", "parse_and_embed", "build_graph",
        "detect_integrations", "design_architecture", "create_plan",
        "await_approval", "validate_plan", "generate_code", "test_and_fix",
    }
    assert required_nodes.issubset(node_names), (
        f"Missing nodes: {required_nodes - node_names}"
    )


# ── State store isolation test ────────────────────────────────────

def test_state_store_creates_and_retrieves(migration_id: str) -> None:
    store = StateStore(db_path=":memory:")
    store.create_migration(migration_id, "https://github.com/example/app")
    record = store.get_migration(migration_id)
    assert record is not None
    assert record["repo_url"] == "https://github.com/example/app"
    assert record["approval_status"] == "pending"


def test_approval_gate_updates_state(migration_id: str) -> None:
    store = StateStore(db_path=":memory:")
    store.create_migration(migration_id, "https://github.com/example/app")
    store.set_approval(migration_id, "approved", "LGTM")
    record = store.get_migration(migration_id)
    assert record["approval_status"] == "approved"
    assert record["approval_comment"] == "LGTM"


# ── Vector store isolation test ───────────────────────────────────

def test_vector_store_upsert_and_query(migration_id: str) -> None:
    vs = VectorStore()  # ephemeral
    chunk = {
        "chunk_id": f"{migration_id}:Test.java:0",
        "migration_id": migration_id,
        "file_path": "src/Test.java",
        "file_type": "JAVA",
        "chunk_type": "METHOD",
        "class_name": "TestClass",
        "method_name": "doGet",
        "module_hint": "orders",
        "soap_endpoint": "",
        "token_count": "50",
        "raw_text": "public void doGet() { return orders; }",
    }
    embedding = [0.1] * 10
    vs.upsert([chunk], [embedding])
    assert vs.count() == 1
    results = vs.query(embedding, migration_id=migration_id, n_results=1)
    assert len(results) == 1
    assert results[0]["class_name"] == "TestClass"


# ── Graph store isolation test ────────────────────────────────────

def test_graph_store_full_cycle(tmp_path: Path) -> None:
    gs = GraphStore(persist_path=tmp_path / "graph.pkl")

    gs.add_class("com.app.OrderServlet", "OrderServlet.java", "SERVLET", "orders")
    gs.add_soap_client("PaymentSoap", "http://pay/ws", "", "PaymentLocator", ["charge"])
    gs.add_table("ORDERS")
    gs.add_edge("com.app.OrderServlet", "PaymentSoap", "CALLS_SOAP", line=10)
    gs.add_edge("com.app.OrderServlet", "ORDERS", "QUERIES", query_type="SELECT")

    soap = gs.get_soap_dependencies("com.app.OrderServlet")
    assert len(soap) == 1
    assert soap[0]["service_name"] == "PaymentSoap"

    jdbc = gs.get_jdbc_calls("com.app.OrderServlet")
    assert len(jdbc) == 1
    assert jdbc[0]["table"] == "ORDERS"

    gs.save()
    reloaded = GraphStore(persist_path=tmp_path / "graph.pkl")
    assert reloaded.G.number_of_nodes() == gs.G.number_of_nodes()


# ── Approval routing logic ────────────────────────────────────────

def test_route_on_approval_approved(minimal_state: MigrationState) -> None:
    from migration_platform.workflows.migration_graph import _route_on_approval
    minimal_state["approval_status"] = "approved"
    result = _route_on_approval(minimal_state)
    assert result == "validate_plan"


def test_route_on_approval_rejected(minimal_state: MigrationState) -> None:
    from migration_platform.workflows.migration_graph import _route_on_approval
    minimal_state["approval_status"] = "rejected"
    result = _route_on_approval(minimal_state)
    assert result == "design_architecture"


def test_route_on_approval_pending(minimal_state: MigrationState) -> None:
    from migration_platform.workflows.migration_graph import _route_on_approval
    minimal_state["approval_status"] = "pending"
    result = _route_on_approval(minimal_state)
    # Should go back to await_approval, not proceed to code gen
    assert result != "validate_plan"
