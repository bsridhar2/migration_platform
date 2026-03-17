"""Unit tests for NetworkX GraphStore."""
import pytest
from migration_platform.graph.graph_store import GraphStore


@pytest.fixture
def store(tmp_path) -> GraphStore:
    return GraphStore(persist_path=tmp_path / "test_graph.pkl")


def test_add_class_and_retrieve(store: GraphStore) -> None:
    store.add_class("com.example.OrderServlet", "src/OrderServlet.java", "SERVLET", "orders")
    assert "com.example.OrderServlet" in store.G.nodes
    node = store.G.nodes["com.example.OrderServlet"]
    assert node["module"] == "orders"


def test_soap_edge_and_query(store: GraphStore) -> None:
    store.add_class("com.example.OrderServlet", "src/OrderServlet.java", "SERVLET", "orders")
    store.add_method("com.example.OrderServlet.processOrder", "com.example.OrderServlet", "chunk-1")
    store.add_soap_client("OrderSOAP", "http://legacy/ws", "", "OrderLocator", ["getOrder"])
    store.add_edge("com.example.OrderServlet.processOrder", "OrderSOAP", "CALLS_SOAP", line=42)

    deps = store.get_soap_dependencies("com.example.OrderServlet")
    assert len(deps) == 1
    assert deps[0]["service_name"] == "OrderSOAP"
    assert deps[0]["line"] == 42


def test_jdbc_edge_and_query(store: GraphStore) -> None:
    store.add_class("com.example.OrderDao", "src/OrderDao.java", "DAO", "orders")
    store.add_method("com.example.OrderDao.findById", "com.example.OrderDao", "chunk-2")
    store.add_table("orders")
    store.add_edge("com.example.OrderDao.findById", "orders", "QUERIES", query_type="SELECT")

    calls = store.get_jdbc_calls("com.example.OrderDao")
    assert len(calls) == 1
    assert calls[0]["table"] == "orders"
    assert calls[0]["query_type"] == "SELECT"


def test_stats(store: GraphStore) -> None:
    store.add_class("com.example.A", "A.java", "CLASS", "mod")
    store.add_table("my_table")
    store.add_soap_client("MySoap", "http://x", "", "X", [])
    stats = store.stats()
    assert stats["classes"] == 1
    assert stats["tables"] == 1
    assert stats["soap_clients"] == 1


def test_persist_and_reload(store: GraphStore, tmp_path) -> None:
    store.add_class("com.example.Foo", "Foo.java", "CLASS", "core")
    store.save()
    reloaded = GraphStore(persist_path=tmp_path / "test_graph.pkl")
    assert "com.example.Foo" in reloaded.G.nodes
