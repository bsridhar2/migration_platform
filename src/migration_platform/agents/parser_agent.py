"""Parser Agent — parallel file chunking and embedding."""
from __future__ import annotations
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from migration_platform.agents.base import BaseAgent
from migration_platform.config.settings import get_settings
from migration_platform.domain.models.migration import CodeChunk
from migration_platform.parsers.base import ParserRegistry
from migration_platform.parsers.java_parser import JavaParser
from migration_platform.parsers.jsp_parser import JspParser
from migration_platform.parsers.xml_parser import XmlParser
from migration_platform.rag.embedder import Embedder
from migration_platform.rag.vector_store import VectorStore
from migration_platform.storage.state_store import StateStore
from migration_platform.workflows.state import MigrationState


def _build_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(JavaParser())
    registry.register(JspParser())
    registry.register(XmlParser())
    return registry


class ParserAgent(BaseAgent):
    """
    Parses all source files into CodeChunks in parallel,
    then embeds and upserts each chunk into ChromaDB.
    Resumable: skips already-embedded chunks.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        state_store: StateStore,
        embedder: Embedder,
    ) -> None:
        super().__init__()
        self._vector_store = vector_store
        self._state_store = state_store
        self._embedder = embedder
        self._registry = _build_registry()

    def run(self, state: MigrationState) -> MigrationState:
        settings = get_settings()
        migration_id = state["migration_id"]
        root = Path(state["repo_local_path"])
        files = state["file_manifest"].get("files", [])

        self._logger.info("ParserAgent starting", total_files=len(files))

        # Register all files in state store (idempotent)
        self._state_store.bulk_insert_files(migration_id, files)

        unembedded = self._state_store.get_unembedded_files(migration_id)
        self._logger.info("Files to embed", count=len(unembedded))

        # ── Phase 1: Parse all files in parallel (CPU/disk only, no API) ──────
        # All threads do pure CPU work here — no OpenAI calls yet.
        parsed: dict[str, list] = {}   # rel_path → list[CodeChunk]
        with ThreadPoolExecutor(max_workers=settings.parser_max_workers) as pool:
            futures = {
                pool.submit(self._parse_file, root / fp, migration_id): fp
                for fp in unembedded
            }
            for future in as_completed(futures):
                fp = futures[future]
                try:
                    parsed[fp] = future.result()
                except Exception as exc:
                    self._logger.warning("File parse failed", file=fp, error=str(exc))
                    parsed[fp] = []

        # Mark empty files immediately (nothing to embed)
        for fp, chunks in parsed.items():
            if not chunks:
                self._state_store.mark_embedded(migration_id, Path(fp).name, 0)

        all_chunks = [c for chunks in parsed.values() for c in chunks]

        # ── Phase 2: One batch exists-check (replaces N per-chunk calls) ──────
        existing_ids = self._vector_store.get_existing_ids(
            [c.chunk_id for c in all_chunks]
        )
        new_chunks = [c for c in all_chunks if c.chunk_id not in existing_ids]

        self._logger.info(
            "Chunks ready for embedding",
            total=len(all_chunks),
            new=len(new_chunks),
            skipped=len(existing_ids),
        )

        # ── Phase 3: One batched embed + upsert (single OpenAI round-trip) ────
        if new_chunks:
            texts = [c.raw_text for c in new_chunks]
            embeddings = self._embedder.embed_batch(texts)
            self._vector_store.upsert(
                [self._chunk_to_dict(c) for c in new_chunks],
                embeddings,
            )

            # Mark files that contributed at least one new chunk
            new_ids: set[str] = {c.chunk_id for c in new_chunks}
            for fp, chunks in parsed.items():
                count = sum(1 for c in chunks if c.chunk_id in new_ids)
                if count:
                    self._state_store.mark_embedded(migration_id, fp, count)

        state["chunk_count"] = len(new_chunks)
        state["current_phase"] = "parsed"
        self._logger.info("ParserAgent complete", total_chunks=len(new_chunks))
        return state

    def _parse_file(self, file_path: Path, migration_id: str) -> list:
        """Parse a file into CodeChunks — CPU/disk only, no API calls."""
        return self._registry.parse_file(file_path, migration_id) or []

    @staticmethod
    def _chunk_to_dict(chunk: CodeChunk) -> dict:
        return {
            "chunk_id":      chunk.chunk_id,
            "migration_id":  chunk.migration_id,
            "file_path":     chunk.file_path,
            "file_type":     chunk.file_type.value,
            "chunk_type":    chunk.chunk_type.value,
            "raw_text":      chunk.raw_text,
            "token_count":   chunk.token_count,
            "class_name":    chunk.class_name,
            "method_name":   chunk.method_name,
            "module_hint":   chunk.module_hint,
            "soap_endpoint": chunk.soap_endpoint,
        }
