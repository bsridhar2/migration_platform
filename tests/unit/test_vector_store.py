"""Unit tests for ChromaDB VectorStore."""
from __future__ import annotations

import pytest

from migration_platform.rag.vector_store import VectorStore


@pytest.fixture
def store() -> VectorStore:
    """Pure in-memory store — no disk writes during tests."""
    return VectorStore()  # EphemeralClient


def _fake_embedding(seed: int = 1, dim: int = 10) -> list[float]:
    """Return a deterministic unit-ish vector for testing (dim must match collection)."""
    base = [float(seed % (i + 2)) for i in range(dim)]
    norm = sum(x ** 2 for x in base) ** 0.5 or 1.0
    return [x / norm for x in base]


def _make_chunk(idx: int, migration_id: str = "mig-1", file_type: str = "JAVA") -> dict:
    return {
        "chunk_id":    f"chunk-{idx}",
        "migration_id": migration_id,
        "file_path":   f"src/Class{idx}.java",
        "file_type":   file_type,
        "chunk_type":  "METHOD",
        "class_name":  f"Class{idx}",
        "method_name": "doGet",
        "module_hint": "orders",
        "soap_endpoint": "",
        "token_count": "120",
        "raw_text":    f"public void doGet_{idx}() {{ // business logic }}",
    }


def test_upsert_and_count(store: VectorStore) -> None:
    chunks = [_make_chunk(i) for i in range(3)]
    embeddings = [_fake_embedding(i) for i in range(3)]
    store.upsert(chunks, embeddings)
    assert store.count() == 3


def test_query_returns_results(store: VectorStore) -> None:
    chunks = [_make_chunk(i) for i in range(5)]
    embeddings = [_fake_embedding(i) for i in range(5)]
    store.upsert(chunks, embeddings)

    query_vec = _fake_embedding(2)
    results = store.query(query_vec, migration_id="mig-1", n_results=3)

    assert len(results) > 0
    assert "chunk_id" in results[0]
    assert "raw_text" in results[0]
    assert "score" in results[0]


def test_query_with_file_type_filter(store: VectorStore) -> None:
    java_chunks = [_make_chunk(i, file_type="JAVA") for i in range(3)]
    jsp_chunks  = [_make_chunk(i + 10, file_type="JSP") for i in range(2)]
    all_chunks  = java_chunks + jsp_chunks
    embeddings  = [_fake_embedding(i) for i in range(len(all_chunks))]

    store.upsert(all_chunks, embeddings)

    results = store.query(_fake_embedding(1), migration_id="mig-1",
                          file_type="JSP", n_results=5)
    for r in results:
        assert r.get("file_type") == "JSP"


def test_query_different_migration_ids_isolated(store: VectorStore) -> None:
    c1 = [_make_chunk(i, migration_id="mig-A") for i in range(3)]
    c2 = [_make_chunk(i + 10, migration_id="mig-B") for i in range(3)]
    embeddings = [_fake_embedding(i) for i in range(6)]
    store.upsert(c1 + c2, embeddings)

    results_a = store.query(_fake_embedding(1), migration_id="mig-A", n_results=10)
    for r in results_a:
        assert r.get("migration_id") == "mig-A"


def test_exists_returns_true_after_upsert(store: VectorStore) -> None:
    chunk = _make_chunk(99)
    store.upsert([chunk], [_fake_embedding(99)])
    assert store.exists("chunk-99") is True
    assert store.exists("chunk-does-not-exist") is False


def test_get_by_id(store: VectorStore) -> None:
    chunk = _make_chunk(42)
    store.upsert([chunk], [_fake_embedding(42)])
    result = store.get_by_id("chunk-42")
    assert result is not None
    assert result["chunk_id"] == "chunk-42"
    assert "raw_text" in result


def test_get_by_id_nonexistent(store: VectorStore) -> None:
    result = store.get_by_id("nonexistent-id")
    assert result is None


def test_empty_store_query_returns_empty(store: VectorStore) -> None:
    results = store.query(_fake_embedding(1), migration_id="mig-empty", n_results=5)
    assert results == []


def test_upsert_deduplicates_by_id(store: VectorStore) -> None:
    chunk = _make_chunk(1)
    store.upsert([chunk], [_fake_embedding(1)])
    store.upsert([chunk], [_fake_embedding(1)])  # upsert again — no duplicate
    assert store.count() == 1
