"""Assembles LLM context within strict token budget."""
from __future__ import annotations
import json
from migration_platform.config.settings import get_settings
from migration_platform.graph.graph_store import GraphStore
from migration_platform.rag.embedder import Embedder
from migration_platform.rag.retriever import Retriever
from migration_platform.rag.vector_store import VectorStore


class ContextBuilder:
    """RAG -> LLM context assembly. Hard limit: max_context_tokens (default 6000)."""

    def __init__(self, vector_store: VectorStore, graph_store: GraphStore, embedder: Embedder) -> None:
        self._retriever = Retriever(vector_store, embedder)
        self._gs = graph_store
        self._embedder = embedder
        self._settings = get_settings()

    def build_react_context(self, migration_id: str, module_name: str, bc: dict, arch_plan: dict) -> str:
        from migration_platform.prompts.templates import REACT_CODEGEN_SYSTEM
        chunks = self._retriever.retrieve(
            query=f"JSP page UI logic {module_name}",
            migration_id=migration_id, file_type="JSP", module_hint=module_name, top_k=4,
        )
        api_contract = {"endpoints": bc.get("rest_endpoints", []), "components": bc.get("react_components", [])}
        extras = [f"# Module: {module_name}", f"# API Contract:\n{json.dumps(api_contract, indent=2)}"]
        return self._retriever.build_context(chunks, REACT_CODEGEN_SYSTEM, extras)

    def build_spring_context(self, migration_id: str, module_name: str, bc: dict, state: dict) -> str:
        from migration_platform.prompts.templates import SPRING_CODEGEN_SYSTEM
        chunks = self._retriever.retrieve(
            query=f"servlet controller business logic {module_name}",
            migration_id=migration_id, file_type="JAVA", module_hint=module_name, top_k=5,
        )
        soap_deps = state.get("soap_report", {}).get("integrations", [])
        extras = [
            f"# Module: {module_name}",
            f"# SOAP dependencies:\n{json.dumps(soap_deps[:3], indent=2)}",
            f"# JPA entities: {bc.get('jpa_entities', [])}",
            f"# REST endpoints:\n{json.dumps(bc.get('rest_endpoints', []), indent=2)}",
        ]
        return self._retriever.build_context(chunks, SPRING_CODEGEN_SYSTEM, extras)
