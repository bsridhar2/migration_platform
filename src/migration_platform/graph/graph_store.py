"""
NetworkX dependency graph — replaces Neo4j, zero server required.

Provides GraphStore (used by existing agents) with InMemoryGraphStore alias.
"""
from __future__ import annotations
import pickle
from pathlib import Path
from typing import Any

import networkx as nx
import community as community_louvain

from migration_platform.core.logging import get_logger

logger = get_logger(__name__)


class GraphStore:
    """
    In-memory directed graph for tracking class/method dependencies,
    SOAP integrations, and JDBC table access patterns.

    Persists to a single pickle file — survives restarts without any server.
    """

    def __init__(self, persist_path: str | Path = "./data/graph.pkl") -> None:
        self._path = Path(persist_path)
        self.G: nx.DiGraph = nx.DiGraph()
        self._load_if_exists()
        logger.info("GraphStore initialised", nodes=self.G.number_of_nodes())

    # ── Node builders ──────────────────────────────────────────────

    def add_class(self, fqn: str, file_path: str, node_type: str, module: str) -> None:
        self.G.add_node(fqn, label="Class", file_path=file_path,
                        node_type=node_type, module=module)

    def add_method(self, fqn: str, class_fqn: str, chunk_id: str = "",
                   is_entry: bool = False) -> None:
        self.G.add_node(fqn, label="Method", class_fqn=class_fqn,
                        chunk_id=chunk_id, is_entry=is_entry)

    def add_jsp(self, path: str, servlet_ref: str, chunk_ids: list[str] | None = None) -> None:
        self.G.add_node(path, label="JSP", servlet_ref=servlet_ref,
                        chunk_ids=chunk_ids or [])

    def add_soap_client(self, service_name: str, endpoint_url: str = "",
                        wsdl_url: str = "", stub_class: str = "",
                        operations: list[str] | None = None) -> None:
        self.G.add_node(service_name, label="SOAPClient",
                        endpoint_url=endpoint_url, wsdl_url=wsdl_url,
                        stub_class=stub_class, operations=operations or [])

    def add_table(self, table_name: str, schema: str = "public") -> None:
        if not self.G.has_node(table_name):
            self.G.add_node(table_name, label="Table", schema=schema)

    def add_edge(self, from_node: str, to_node: str, rel_type: str,
                 **props: Any) -> None:
        """
        Add a directed relationship edge.

        rel_type values: CALLS | DEPENDS_ON | CALLS_SOAP | QUERIES |
                         FORWARDS_TO | INCLUDES | SUBMITS_TO
        """
        for node in (from_node, to_node):
            if not self.G.has_node(node):
                self.G.add_node(node, label="Unknown")
        self.G.add_edge(from_node, to_node, rel_type=rel_type, **props)

    # ── Queries ────────────────────────────────────────────────────

    def get_soap_dependencies(self, class_fqn: str) -> list[dict[str, Any]]:
        """Return all SOAP clients called by methods in a class."""
        return [
            {
                "from_method":   u,
                "service_name":  v,
                "endpoint_url":  self.G.nodes[v].get("endpoint_url", ""),
                "wsdl_url":      self.G.nodes[v].get("wsdl_url", ""),
                "operations":    self.G.nodes[v].get("operations", []),
                "line":          d.get("line", 0),
            }
            for u, v, d in self.G.edges(data=True)
            if d.get("rel_type") == "CALLS_SOAP" and u.startswith(class_fqn)
        ]

    def get_jdbc_calls(self, class_fqn: str) -> list[dict[str, Any]]:
        """Return all DB tables accessed by methods in a class."""
        return [
            {"method": u, "table": v, "query_type": d.get("query_type", "UNKNOWN")}
            for u, v, d in self.G.edges(data=True)
            if d.get("rel_type") == "QUERIES" and u.startswith(class_fqn)
        ]

    def get_dependency_chain(self, class_fqn: str, depth: int = 5) -> list[str]:
        """Transitive dependencies up to `depth` hops — replaces Neo4j variable-length path."""
        try:
            return list(
                nx.single_source_shortest_path(self.G, class_fqn, cutoff=depth).keys()
            )
        except (nx.NodeNotFound, nx.NetworkXError):
            return []

    def get_module_files(self, module: str) -> list[str]:
        """All source file paths belonging to a business module."""
        return [
            d["file_path"]
            for _, d in self.G.nodes(data=True)
            if d.get("module") == module and "file_path" in d
        ]

    def get_all_soap_integrations(self) -> list[dict[str, Any]]:
        """Full SOAP inventory from graph edges."""
        return [
            {
                "callsite": u,
                "service":  v,
                **{k: self.G.nodes.get(v, {}).get(k, "")
                   for k in ("endpoint_url", "wsdl_url", "stub_class", "operations")},
            }
            for u, v, d in self.G.edges(data=True)
            if d.get("rel_type") == "CALLS_SOAP"
        ]

    def detect_modules(self) -> list[dict[str, Any]]:
        """
        Louvain community detection — same algorithm as Neo4j GDS plugin.
        Returns inferred business module clusters.
        """
        undirected = self.G.to_undirected()
        if undirected.number_of_nodes() == 0:
            return []
        partition = community_louvain.best_partition(undirected)
        groups: dict[int, list[str]] = {}
        for node, cid in partition.items():
            groups.setdefault(cid, []).append(node)
        return [
            {"module_id": f"module_{k}", "classes": v, "size": len(v)}
            for k, v in groups.items()
        ]

    def find_circular_dependencies(self) -> list[list[str]]:
        try:
            return list(nx.simple_cycles(self.G))
        except Exception:
            return []

    def get_high_centrality_files(self, top_n: int = 20) -> list[tuple[str, float]]:
        """Files most depended on — useful for prioritising migration order."""
        centrality = nx.in_degree_centrality(self.G)
        return sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]

    def stats(self) -> dict[str, int]:
        nodes_data = list(self.G.nodes(data=True))
        return {
            "nodes":       self.G.number_of_nodes(),
            "edges":       self.G.number_of_edges(),
            "classes":     sum(1 for _, d in nodes_data if d.get("label") == "Class"),
            "methods":     sum(1 for _, d in nodes_data if d.get("label") == "Method"),
            "soap_clients": sum(1 for _, d in nodes_data if d.get("label") == "SOAPClient"),
            "tables":      sum(1 for _, d in nodes_data if d.get("label") == "Table"),
            "jsps":        sum(1 for _, d in nodes_data if d.get("label") == "JSP"),
        }

    # ── Persistence ────────────────────────────────────────────────

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            pickle.dump(self.G, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.debug("GraphStore saved", path=str(self._path))

    def _load_if_exists(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "rb") as f:
                    self.G = pickle.load(f)
                logger.info("GraphStore loaded", nodes=self.G.number_of_nodes())
            except Exception as exc:
                logger.warning("GraphStore load failed — starting fresh", error=str(exc))
                self.G = nx.DiGraph()


# Alias so newer code that imports InMemoryGraphStore still works
InMemoryGraphStore = GraphStore
