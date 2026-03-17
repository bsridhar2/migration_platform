"""Unit tests for JspParser — scriptlet-block chunking."""
from __future__ import annotations

from pathlib import Path

import pytest

from migration_platform.parsers.jsp_parser import JspParser

MIGRATION_ID = "test-migration"


@pytest.fixture
def parser() -> JspParser:
    return JspParser()


def _path(name: str = "order.jsp") -> Path:
    return Path(f"web/{name}")


ORDER_JSP = """<%@ page import="com.example.OrderService" %>
<%@ include file="header.jsp" %>
<html>
<body>
<h1>Order Details</h1>
<%
    String orderId = request.getParameter("id");
    OrderService svc = new OrderService();
    Order order = svc.getOrder(orderId);
%>
<form action="/order/submit" method="POST">
    <input type="hidden" name="orderId" value="<%= orderId %>"/>
    <input type="text" name="quantity"/>
    <input type="submit" value="Submit"/>
</form>
<%
    if (order != null) {
        out.println("<p>Status: " + order.getStatus() + "</p>");
    }
%>
</body>
</html>
"""


def test_chunks_returned(parser: JspParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    assert len(chunks) >= 1


def test_scriptlet_chunks_extracted(parser: JspParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    scriptlets = [c for c in chunks if c.chunk_type.value in ("JSP_BLOCK", "JSP_SCRIPTLET")]
    assert len(scriptlets) >= 1


def test_form_chunk_captured(parser: JspParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    form_chunks = [
        c for c in chunks
        if "form" in c.raw_text.lower() or c.chunk_type.value == "JSP_FORM"
    ]
    assert len(form_chunks) >= 1


def test_migration_id_on_all_chunks(parser: JspParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    for c in chunks:
        assert c.migration_id == MIGRATION_ID


def test_raw_text_nonempty(parser: JspParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    for c in chunks:
        assert c.raw_text.strip() != ""


def test_file_path_set(parser: JspParser) -> None:
    chunks = parser.parse(_path(), MIGRATION_ID)
    for c in chunks:
        assert "order.jsp" in str(c.file_path)


def test_can_parse_ext(parser: JspParser) -> None:
    assert parser.can_parse(Path("index.jsp")) is True
    assert parser.can_parse(Path("index.jspx")) is True
    assert parser.can_parse(Path("Main.java")) is False


def test_empty_jsp_returns_no_crash(parser: JspParser) -> None:
    chunks = parser.parse(_path(), "")
    assert isinstance(chunks, list)
