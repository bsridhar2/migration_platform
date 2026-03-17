"""
Persistent LangGraph checkpointer that survives server restarts.

Uses MemorySaver internally but pickle-serialises the checkpoint state to disk
after every `put` / `put_writes` call.  On the next startup it restores the
saved state, so interrupted workflows (e.g. awaiting human approval) can be
resumed even after the process restarts.

Design notes
------------
* No new packages required — uses only the stdlib `pickle` module and the
  already-installed `langgraph.checkpoint.memory.MemorySaver`.
* The defaultdict default-factories (lambdas) are NOT pickle-safe, so we
  reconstruct them manually on load using `functools.partial` (which IS
  pickle-safe) as the restored factory.
* Thread-safe: a threading.Lock serialises all writes.
* Atomic writes: data is written to a `.tmp` file then renamed, preventing
  partial/corrupted files on crash.
"""
from __future__ import annotations

import pickle
import threading
from collections import defaultdict
from collections.abc import AsyncIterator, Iterator, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.memory import MemorySaver

from migration_platform.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helper: a picklable factory for nested defaultdict(dict)
# ---------------------------------------------------------------------------
def _defaultdict_dict_factory() -> defaultdict:
    """Return a defaultdict(dict) — used as the nested-level factory."""
    return defaultdict(dict)


class PersistentMemorySaver(MemorySaver):
    """
    MemorySaver that persists checkpoints to a pickle file on every write.

    Usage::

        saver = PersistentMemorySaver(persist_path="./data/checkpoints.pkl")
        graph = builder.compile(checkpointer=saver)

    The file is created automatically.  Delete it to start with a clean slate.
    """

    def __init__(self, persist_path: str | Path) -> None:
        super().__init__()
        self._persist_path = Path(persist_path)
        self._lock = threading.Lock()
        self._load_from_disk()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_from_disk(self) -> None:
        """Restore checkpoints from the pickle file (if it exists)."""
        if not self._persist_path.exists():
            logger.info("checkpoint_store.no_existing_file", path=str(self._persist_path))
            return
        try:
            with open(self._persist_path, "rb") as fh:
                data: dict = pickle.load(fh)

            # Reconstruct defaultdicts with picklable factories
            # storage: thread_id → ns → ckpt_id → tuple
            self.storage = defaultdict(_defaultdict_dict_factory)
            for thread_id, ns_map in data.get("storage", {}).items():
                self.storage[thread_id] = defaultdict(dict, ns_map)

            # writes: (thread_id, ns, ckpt_id) → {(task_id, idx): …}
            self.writes = defaultdict(dict, data.get("writes", {}))

            # blobs: plain dict (no default factory needed)
            self.blobs = defaultdict(object.__class__)
            self.blobs.update(data.get("blobs", {}))

            ckpt_count = sum(
                len(ns_map) for thread_map in data.get("storage", {}).values()
                for ns_map in thread_map.values()
            )
            logger.info(
                "checkpoint_store.loaded",
                path=str(self._persist_path),
                threads=len(data.get("storage", {})),
                checkpoints=ckpt_count,
            )
        except Exception as exc:
            logger.warning(
                "checkpoint_store.load_failed",
                path=str(self._persist_path),
                error=str(exc),
            )
            # Leave the saver in its default empty state

    def _save_to_disk(self) -> None:
        """Atomically write current checkpoint state to disk."""
        try:
            # Convert inner defaultdicts to plain dicts for safe pickling
            data = {
                "storage": {
                    thread_id: {ns: dict(ckpts) for ns, ckpts in ns_map.items()}
                    for thread_id, ns_map in self.storage.items()
                },
                "writes": dict(self.writes),
                "blobs":  dict(self.blobs),
            }
            tmp = self._persist_path.with_suffix(".tmp")
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "wb") as fh:
                pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(self._persist_path)  # atomic rename
        except Exception as exc:
            logger.error("checkpoint_store.save_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Override sync write methods → call super then persist
    # ------------------------------------------------------------------

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        result = super().put(config, checkpoint, metadata, new_versions)
        with self._lock:
            self._save_to_disk()
        return result

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        super().put_writes(config, writes, task_id, task_path)
        with self._lock:
            self._save_to_disk()

    # ------------------------------------------------------------------
    # Override async write methods → delegate to sync (same as MemorySaver)
    # ------------------------------------------------------------------

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        result = self.put(config, checkpoint, metadata, new_versions)
        return result

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.put_writes(config, writes, task_id, task_path)
