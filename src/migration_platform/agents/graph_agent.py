"""
GraphAgent — Phase A / Step 3.

LangChain 1.x advances:
  - LCEL text chain for module naming inference
  - RunnableLambda for inline transformation
  - ChatPromptTemplate for structured module labelling
"""
from __future__ import annotations

import re
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from migration_platform.agents.base import BaseAgent
from migration_platform.config.settings import get_settings
from migration_platform.graph.graph_store import GraphStore
from migration_platform.rag.vector_store import VectorStore
from migration_platform.workflows.state import MigrationState

_IMPORT_RE       = re.compile(r"^import\s+([\w.]+);", re.MULTILINE)
_SOAP_IMPORT_RE  = re.compile(r"import\s+org\.apache\.axis")
_SOAP_ENDPOINT_RE = re.compile(r'setTargetEndpointAddress\(["\']([^"\']+)["\']')
_TABLE_RE        = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z_]\w*)", re.IGNORECASE)

_MODULE_KEYWORDS: dict[str, list[str]] = {
    "orders":        ["order", "checkout", "cart"],
    "payments":      ["payment", "billing", "invoice"],
    "auth":          ["auth", "login", "session", "security", "user"],
    "products":      ["product", "catalog", "item", "sku"],
    "customers":     ["customer", "client", "account"],
    "notifications": ["notification", "email", "sms", "alert"],
    "reports":       ["report", "analytics", "dashboard"],
    "shipping":      ["shipping", "delivery", "carrier"],
}

_MODULE_LABEL_SYSTEM = """
You are a software architect. Given a list of Java class names from one community cluster,
reply with a single business domain name (one word, lowercase, e.g. 'orders', 'payments', 'auth').
If uncertain, reply 'core'.
""".strip()


class GraphAgent(BaseAgent):
    """
    Builds the NetworkX dependency graph from ChromaDB chunks.
    Uses a lightweight LCEL chain to label Louvain module clusters.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        graph_store: GraphStore,
    ) -> None:
        super().__init__()
        self._vs = vector_store
        self._gs = graph_store

        # Lightweight LCEL chain for cluster labelling
        self._label_chain = (
            ChatPromptTemplate.from_messages([
                ("system", _MODULE_LABEL_SYSTEM),
                ("human", "{input}"),
            ])
            | self._claude
            | StrOutputParser()
            | RunnableLambda(lambda s: s.strip().lower().split()[0] if s.strip() else "core")
        ).with_retry(stop_after_attempt=2)

    def run(self, state: MigrationState) -> MigrationState:
        migration_id = state["migration_id"]
        self._logger.info("GraphAgent starting", migration_id=migration_id)

        # Zero-vector broad query — dimension must match the embedding model.
        dim = get_settings().embedding_dimensions
        zero_vec = [0.0] * dim

        # ── 1. Retrieve all JAVA chunks ───────────────────────────────────
        java_chunks = self._vs.query(
            embedding=zero_vec,
            migration_id=migration_id,
            file_type="JAVA",
            n_results=500,
        )

        for chunk in java_chunks:
            class_name  = chunk.get("class_name", "")
            method_name = chunk.get("method_name", "")
            file_path   = chunk.get("file_path", "")
            raw         = chunk.get("raw_text", "")
            module      = self._infer_module_heuristic(file_path)

            if class_name and not self._gs.G.has_node(class_name):
                self._gs.add_class(class_name, file_path, self._classify(raw, file_path), module)

            if class_name and method_name:
                fqn = f"{class_name}.{method_name}"
                self._gs.add_method(fqn, class_name, chunk.get("chunk_id", ""),
                                    is_entry=method_name in ("doGet", "doPost", "service"))

            # Import → DEPENDS_ON edges
            for imp in _IMPORT_RE.findall(raw):
                dep = imp.split(".")[-1]
                if class_name and dep and dep != class_name:
                    self._gs.add_edge(class_name, dep, "DEPENDS_ON")

            # SOAP → CALLS_SOAP edges
            if _SOAP_IMPORT_RE.search(raw) and class_name:
                m = re.search(r"new\s+(\w+ServiceLocator)", raw)
                svc = m.group(1).replace("Locator", "") if m else ""
                if svc:
                    ep_m = _SOAP_ENDPOINT_RE.search(raw)
                    self._gs.add_soap_client(svc, ep_m.group(1) if ep_m else "", "", svc + "Locator", [])
                    if method_name:
                        self._gs.add_edge(f"{class_name}.{method_name}", svc, "CALLS_SOAP")

            # JDBC → QUERIES edges
            for table in _TABLE_RE.findall(raw):
                self._gs.add_table(table.upper())
                if class_name and method_name:
                    self._gs.add_edge(f"{class_name}.{method_name}", table.upper(), "QUERIES")

        # ── 2. JSP → FORWARDS_TO edges ────────────────────────────────────
        jsp_chunks = self._vs.query(
            embedding=zero_vec,
            migration_id=migration_id,
            file_type="JSP",
            n_results=200,
        )
        for chunk in jsp_chunks:
            path = chunk.get("file_path", "")
            if not self._gs.G.has_node(path):
                self._gs.add_jsp(path, "", [chunk.get("chunk_id", "")])
            ref = chunk.get("class_name", "")
            if ref:
                self._gs.add_edge(path, ref, "FORWARDS_TO")

        # ── 3. Louvain community detection ────────────────────────────────
        raw_clusters = self._gs.detect_modules()
        labelled: list[dict] = []
        for cluster in raw_clusters:
            nodes_sample = ", ".join(cluster["classes"][:20])
            try:
                label = self._label_chain.invoke({"input": nodes_sample})
            except Exception:
                label = self._infer_module_heuristic(" ".join(cluster["classes"]))
            labelled.append({
                "module_id":   cluster["module_id"],
                "module_name": label,
                "classes":     cluster["classes"],
                "size":        cluster["size"],
            })

        self._gs.save()
        stats = self._gs.stats()
        self._logger.info("GraphAgent complete", **stats, clusters=len(labelled))

        state["module_clusters"]          = labelled
        state["circular_dependencies"]    = self._gs.find_circular_dependencies()[:10]
        state["high_centrality_files"]    = self._gs.get_high_centrality_files(top_n=20)
        state["current_phase"]            = "graphed"
        return state

    @staticmethod
    def _classify(raw: str, path: str) -> str:
        p = path.lower()
        if "servlet" in raw.lower() or "doget" in raw.lower():  return "SERVLET"
        if "service" in p or "@service" in raw.lower():          return "SERVICE"
        if "dao" in p or "repository" in p:                      return "DAO"
        if "controller" in p:                                     return "CONTROLLER"
        return "UTIL"

    @staticmethod
    def _infer_module_heuristic(text: str) -> str:
        lower = text.lower()
        for module, keywords in _MODULE_KEYWORDS.items():
            if any(k in lower for k in keywords):
                return module
        return "core"
