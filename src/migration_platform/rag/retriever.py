"""
Retriever — hybrid semantic + graph-guided retrieval with token budget.

Every agent call uses retrieve() to get the most relevant code chunks
without exceeding the 6K-token LLM context budget.
"""
from __future__ import annotations

from typing import Any

from migration_platform.core.config import get_settings
from migration_platform.core.logging import get_logger
from migration_platform.graph.graph_store import GraphStore
from migration_platform.rag.embedder import Embedder
from migration_platform.rag.vector_store import VectorStore

logger = get_logger(__name__)


class Retriever:
    """
    Wraps VectorStore + GraphStore to assemble agent context.

    Hard budget: at most max_context_tokens per assembled context block.
    Graph-boost: chunks from graph-identified module files are promoted.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedder: Embedder,
        graph_store: GraphStore | None = None,
    ) -> None:
        self._vs       = vector_store
        self._embedder = embedder
        self._gs       = graph_store
        self._settings = get_settings()

    # ── Public API ─────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        migration_id: str,
        *,
        file_type: str | None = None,
        chunk_type: str | None = None,
        module_hint: str | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Embed query, search ChromaDB, apply graph-boost, enforce token budget.
        Returns a list of chunk dicts sorted by relevance.
        """
        top_k = top_k or self._settings.retrieval_top_k
        embedding = self._embedder.embed(query)

        raw_hits = self._vs.query(
            embedding,
            migration_id=migration_id,
            file_type=file_type,
            chunk_type=chunk_type,
            module_hint=module_hint,
            n_results=top_k * 2,        # over-fetch then filter
        )

        # Graph-boost: promote hits from known module files
        if self._gs and module_hint:
            module_files = set(self._gs.get_module_files(module_hint))
            raw_hits.sort(
                key=lambda c: (
                    0 if c.get("file_path", "") in module_files else 1,
                    -c.get("score", 0.0),
                )
            )

        selected = self._apply_budget(raw_hits)
        return selected[:top_k]

    def build_context(
        self,
        chunks: list[dict[str, Any]],
        system_prefix: str = "",
        extras: list[str] | None = None,
    ) -> str:
        """
        Assemble chunks + extras into a single prompt string.
        Enforces max_context_tokens hard limit.
        """
        parts: list[str] = []
        if system_prefix:
            parts.append(system_prefix)

        for chunk in chunks:
            header = f"// FILE: {chunk.get('file_path', 'unknown')}"
            if chunk.get("class_name"):
                header += f"  CLASS: {chunk['class_name']}"
            if chunk.get("method_name"):
                header += f"  METHOD: {chunk['method_name']}"
            parts.append(f"{header}\n{chunk['raw_text']}")

        if extras:
            parts.extend(extras)

        full = "\n\n---\n\n".join(parts)

        # Hard truncation at token budget
        if self._embedder.count_tokens(full) > self._settings.max_context_tokens:
            full = self._embedder.truncate_to_tokens(full, self._settings.max_context_tokens)

        return full

    # ── Private ────────────────────────────────────────────────────

    def _apply_budget(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return chunks that fit within max_context_tokens, greedy selection."""
        selected: list[dict[str, Any]] = []
        total = 0
        budget = self._settings.max_context_tokens

        for chunk in chunks:
            raw = chunk.get("raw_text", "")
            count = self._embedder.count_tokens(raw)
            if total + count <= budget:
                selected.append(chunk)
                total += count
            elif not selected:
                # Always include at least one chunk
                selected.append(chunk)
                break

        return selected
