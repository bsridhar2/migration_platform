"""
BaseAgent — enriched base with injected data stores.

All 9 production agents inherit from this class when they need
access to vector_store, graph_store, state_store and cache_store.
The core LLM logic lives in agents/base.py.
"""
from __future__ import annotations

from migration_platform.agents.base import BaseAgent as _CoreBase
from migration_platform.graph.graph_store import GraphStore
from migration_platform.rag.embedder import Embedder
from migration_platform.rag.retriever import Retriever
from migration_platform.rag.vector_store import VectorStore
from migration_platform.storage.cache_store import CacheStore
from migration_platform.storage.state_store import StateStore
from migration_platform.workflows.state import MigrationState


class BaseAgent(_CoreBase):
    """
    Enriched base agent with injected data stores.

    Agents that need stores should extend this class.
    Agents that only need LLM access (PlannerAgent, ValidationAgent)
    extend agents/base.py directly.
    """

    def __init__(
        self,
        *,
        graph_store: GraphStore,
        vector_store: VectorStore,
        state_store: StateStore,
        cache_store: CacheStore,
        retriever: Retriever,
    ) -> None:
        super().__init__()
        self.graph_store  = graph_store
        self.vector_store = vector_store
        self.state_store  = state_store
        self.cache_store  = cache_store
        self.retriever    = retriever
