"""
ChromaDB vector store — replaces Qdrant, zero server required.

VectorStore wraps a ChromaDB collection.
Supports EphemeralClient (pure in-memory) and PersistentClient (local folder).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.client import Client

from migration_platform.core.logging import get_logger

logger = get_logger(__name__)


class VectorStore:
    """
    ChromaDB-backed vector store.

    Usage:
        VectorStore()                            # ephemeral / in-memory
        VectorStore(persist_dir="./data/chroma") # persisted local folder
    """

    COLLECTION_NAME = "code_chunks"

    def __init__(self, persist_dir: str | Path | None = None) -> None:
        if persist_dir:
            self._client: Client = chromadb.PersistentClient(path=str(persist_dir))
        else:
            self._client = chromadb.EphemeralClient()

        self._col = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("VectorStore initialised", count=self._col.count())

    # ── Write ──────────────────────────────────────────────────────

    def upsert(self, chunks: list[dict[str, Any]], embeddings: list[list[float]]) -> None:
        """Upsert chunks with their embedding vectors."""
        if not chunks:
            return

        ids       = [c["chunk_id"] for c in chunks]
        documents = [c["raw_text"] for c in chunks]
        metadatas = [
            {
                k: (str(v) if not isinstance(v, str) else v)
                for k, v in {
                    "file_path":     c.get("file_path", ""),
                    "file_type":     c.get("file_type", ""),
                    "chunk_type":    c.get("chunk_type", ""),
                    "class_name":    c.get("class_name", ""),
                    "method_name":   c.get("method_name", ""),
                    "module_hint":   c.get("module_hint", ""),
                    "soap_endpoint": c.get("soap_endpoint", ""),
                    "migration_id":  c.get("migration_id", ""),
                    "token_count":   c.get("token_count", "0"),
                }.items()
            }
            for c in chunks
        ]

        self._col.upsert(ids=ids, embeddings=embeddings,
                         documents=documents, metadatas=metadatas)

    # ── Query ──────────────────────────────────────────────────────

    def query(
        self,
        embedding: list[float],
        *,
        migration_id: str,
        file_type: str | None = None,
        chunk_type: str | None = None,
        module_hint: str | None = None,
        n_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Semantic search with optional metadata filters."""
        # ChromaDB requires $and when filtering on more than one field.
        # Build a list of single-key conditions, then wrap in $and if needed.
        conditions: list[dict[str, Any]] = [{"migration_id": {"$eq": migration_id}}]
        if file_type:
            conditions.append({"file_type": {"$eq": file_type}})
        if chunk_type:
            conditions.append({"chunk_type": {"$eq": chunk_type}})
        if module_hint:
            conditions.append({"module_hint": {"$eq": module_hint}})

        where: dict[str, Any] = (
            conditions[0] if len(conditions) == 1
            else {"$and": conditions}
        )

        total = self._col.count()
        if total == 0:
            return []

        results = self._col.query(
            query_embeddings=[embedding],
            n_results=min(n_results, total),
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        hits: list[dict[str, Any]] = []
        ids       = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, chunk_id in enumerate(ids):
            meta = metadatas[i] if metadatas else {}
            hits.append({
                "chunk_id": chunk_id,
                "raw_text": documents[i],
                "score":    1.0 - distances[i],
                **meta,
            })
        return hits

    def get_by_id(self, chunk_id: str) -> dict[str, Any] | None:
        """Fetch a single chunk by its ID."""
        try:
            result = self._col.get(
                ids=[chunk_id],
                include=["documents", "metadatas"],
            )
            if result["ids"]:
                return {
                    "chunk_id": result["ids"][0],
                    "raw_text": result["documents"][0],
                    **(result["metadatas"][0] if result["metadatas"] else {}),
                }
        except Exception:
            pass
        return None

    def get_existing_ids(self, chunk_ids: list[str]) -> set[str]:
        """Return the subset of chunk_ids that already exist in the collection.

        Single batch .get() instead of N per-chunk exists() calls — avoids
        the N-round-trips problem when checking hundreds of chunks at once.
        """
        if not chunk_ids:
            return set()
        try:
            result = self._col.get(ids=chunk_ids, include=[])
            return set(result["ids"])
        except Exception:
            return set()

    def exists(self, chunk_id: str) -> bool:
        """Return True if a chunk_id already exists (for resumable ingestion)."""
        try:
            return len(self._col.get(ids=[chunk_id])["ids"]) > 0
        except Exception:
            return False

    def count(self) -> int:
        return self._col.count()
