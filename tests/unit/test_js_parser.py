"""Unit tests for JsParser — function-level chunking."""
from __future__ import annotations

from pathlib import Path

import pytest

from migration_platform.parsers.js_parser import JsParser

MIGRATION_ID = "test-migration"


@pytest.fixture
def parser() -> JsParser:
    return JsParser()


ES_MODULE = """
import axios from 'axios';

export function loadOrders(userId) {
    return axios.get(`/api/orders?userId=${userId}`);
}

export const createOrder = async (payload) => {
    const resp = await fetch('/api/orders', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
    return resp.json();
};

function _formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
        .format(amount);
}
"""

JQUERY_LEGACY = """
$(document).ready(function() {
    $('#orderForm').submit(function(e) {
        e.preventDefault();
        $.ajax({
            url: '/order/submit',
            type: 'POST',
            data: $(this).serialize(),
            success: function(resp) {
                alert('Order placed: ' + resp.orderId);
            }
        });
    });
});
"""


def test_es_module_chunks_returned(parser: JsParser) -> None:
    chunks = parser.parse(Path("orders.js"), MIGRATION_ID)
    assert len(chunks) >= 1


def test_function_names_extracted(parser: JsParser) -> None:
    chunks = parser.parse(Path("orders.js"), MIGRATION_ID)
    names = [c.method_name for c in chunks]
    assert any(n in names for n in ("loadOrders", "createOrder", "_formatCurrency"))


def test_api_calls_in_metadata(parser: JsParser) -> None:
    chunks = parser.parse(Path("orders.js"), MIGRATION_ID)
    api_chunks = [c for c in chunks if c.metadata.get("api_calls")]
    assert len(api_chunks) >= 1


def test_has_ajax_detected_in_jquery(parser: JsParser) -> None:
    chunks = parser.parse(Path("legacy.js"), MIGRATION_ID)
    ajax_chunks = [c for c in chunks if c.metadata.get("has_ajax")]
    assert len(ajax_chunks) >= 1


def test_can_parse_extensions(parser: JsParser) -> None:
    for ext in (".js", ".ts", ".jsx", ".tsx", ".mjs"):
        assert parser.can_parse(Path(f"file{ext}")) is True
    assert parser.can_parse(Path("file.java")) is False
    assert parser.can_parse(Path("file.jsp")) is False


def test_migration_id_set(parser: JsParser) -> None:
    chunks = parser.parse(Path("orders.js"), MIGRATION_ID)
    for c in chunks:
        assert c.migration_id == MIGRATION_ID


def test_empty_file_no_crash(parser: JsParser) -> None:
    chunks = parser.parse(Path("empty.js"), MIGRATION_ID)
    assert isinstance(chunks, list)


def test_chunk_ids_unique(parser: JsParser) -> None:
    chunks = parser.parse(Path("orders.js"), MIGRATION_ID)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), "chunk IDs must be unique"
