"""Unit tests for DuckDB StateStore."""
import pytest
from migration_platform.storage.state_store import StateStore


@pytest.fixture
def store() -> StateStore:
    """In-memory store — no disk writes during tests."""
    return StateStore(db_path=":memory:")


def test_create_and_get_migration(store: StateStore) -> None:
    store.create_migration("m1", "https://github.com/example/app")
    record = store.get_migration("m1")
    assert record is not None
    assert record["repo_url"] == "https://github.com/example/app"
    assert record["status"] == "pending"


def test_update_status(store: StateStore) -> None:
    store.create_migration("m2", "https://github.com/example/app2")
    store.update_status("m2", "ingested", "ingesting")
    record = store.get_migration("m2")
    assert record["status"] == "ingested"


def test_set_approval(store: StateStore) -> None:
    store.create_migration("m3", "https://github.com/example/app3")
    store.set_approval("m3", "approved", "Looks good")
    record = store.get_migration("m3")
    assert record["approval_status"] == "approved"
    assert record["approval_comment"] == "Looks good"


def test_file_index_progress(store: StateStore) -> None:
    store.create_migration("m4", "https://github.com/example/app4")
    files = [
        {"file_path": "src/Main.java", "file_type": "JAVA"},
        {"file_path": "src/index.jsp", "file_type": "JSP"},
    ]
    store.bulk_insert_files("m4", files)
    progress = store.get_progress("m4")
    assert progress["total_files"] == 2
    assert progress["embedded_files"] == 0

    store.mark_embedded("m4", "src/Main.java", 5)
    progress = store.get_progress("m4")
    assert progress["embedded_files"] == 1


def test_soap_integration_save_and_retrieve(store: StateStore) -> None:
    store.create_migration("m5", "https://github.com/example/app5")
    store.save_soap_integration("m5", {
        "service_name": "OrderService",
        "callsite_class": "com.example.OrderServlet",
        "callsite_method": "processOrder",
        "endpoint_url": "http://legacy/ws/order",
        "wsdl_url": "http://legacy/ws/order?wsdl",
        "stub_class": "com.example.OrderServiceLocator",
        "operations": ["getOrder", "createOrder"],
        "migration_option": "A",
        "complexity": "MEDIUM",
    })
    integrations = store.get_soap_integrations("m5")
    assert len(integrations) == 1
    assert integrations[0]["service_name"] == "OrderService"
    assert "getOrder" in integrations[0]["operations"]


def test_get_nonexistent_migration(store: StateStore) -> None:
    assert store.get_migration("does-not-exist") is None
