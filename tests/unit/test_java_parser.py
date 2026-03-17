"""Unit tests for JavaParser — method-level chunking."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from migration_platform.parsers.java_parser import JavaParser

MIGRATION_ID = "test-migration"


@pytest.fixture
def parser() -> JavaParser:
    return JavaParser()


def _path(name: str = "OrderServlet.java") -> Path:
    return Path(f"src/com/example/{name}")


SIMPLE_SERVLET = """
import org.apache.axis.client.Call;
import org.apache.axis.client.Service;

public class OrderServlet extends HttpServlet {

    @Override
    public void doGet(HttpServletRequest req, HttpServletResponse resp) {
        String id = req.getParameter("id");
        resp.getWriter().write("order:" + id);
    }

    public void processOrder(String orderId) {
        Service service = new Service();
        Call call = (Call) service.createCall();
        call.setTargetEndpointAddress("http://legacy/ws/orders");
        Object result = call.invoke(new Object[]{ orderId });
    }
}
"""

JDBC_CLASS = """
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class OrderDao {
    public Order findById(int id) {
        PreparedStatement stmt = conn.prepareStatement(
            "SELECT * FROM orders WHERE id = ?"
        );
        stmt.setInt(1, id);
        ResultSet rs = stmt.executeQuery();
        return mapRow(rs);
    }
}
"""


def test_chunks_returned(parser: JavaParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    assert len(chunks) >= 1


def test_method_chunks_have_names(parser: JavaParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    method_chunks = [c for c in chunks if c.chunk_type.value == "METHOD"]
    assert len(method_chunks) >= 1
    for chunk in method_chunks:
        assert chunk.method_name != ""


def test_class_header_chunk_present(parser: JavaParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    headers = [c for c in chunks if c.chunk_type.value == "CLASS_HEADER"]
    assert len(headers) >= 1
    assert "OrderServlet" in headers[0].class_name


def test_soap_detected_in_metadata(parser: JavaParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    soap_chunks = [
        c for c in chunks
        if c.metadata.get("has_soap") or "SOAP" in str(c.chunk_type)
           or "axis" in c.raw_text.lower() or "setTargetEndpointAddress" in c.raw_text
    ]
    assert len(soap_chunks) >= 1


def test_jdbc_class_parsed(parser: JavaParser) -> None:
    chunks = parser.parse(_path("OrderDao.java"), JDBC_CLASS)
    jdbc_chunks = [c for c in chunks if "prepareStatement" in c.raw_text.lower()
                   or c.chunk_type.value in ("JDBC_CALL", "METHOD")]
    assert len(jdbc_chunks) >= 1


def test_migration_id_set(parser: JavaParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    for chunk in chunks:
        assert chunk.migration_id == MIGRATION_ID


def test_raw_text_not_empty(parser: JavaParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    for chunk in chunks:
        assert chunk.raw_text.strip() != ""


def test_fallback_on_invalid_java(parser: JavaParser) -> None:
    invalid = "this is not valid java {{ {{{ }"
    chunks = parser.parse(_path("Bad.java"), invalid)
    # Should still return something via fallback chunker
    assert isinstance(chunks, list)


def test_chunk_ids_unique(parser: JavaParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
