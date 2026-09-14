"""Contract tests for the Sales domain server (EP-15-T01, README.md §7.1).

The MCP SDK auto-generates `input_schema` from each tool's Python signature
(real, per-field types/required -- verified empirically: a missing required
field or a wrong-typed one is rejected server-side via Pydantic, `is_error`
True, before this RI's own code ever runs) and *validates every call
against it* -- so `input_schema` conformance is exercised directly below,
not re-implemented. `output_schema`, however, is auto-generated from the
Python return type (`dict[str, object]` throughout this RI's example
servers) and comes out too generic (`additionalProperties: true`) to be a
meaningful contract on its own -- `CapabilityManifest` (EP-02-T01) does not
duplicate a schema either (the manifest's job is entitlement/risk metadata,
not shape). This file's own hand-written `jsonschema` per tool *is* the
practical output contract EP-15-T01 asks for, validated against the real,
running server -- not a schema nobody actually checks.
"""

from __future__ import annotations

import jsonschema
import pytest

from tests.contract.conftest import call_tool_directly

_CUSTOMER_SCHEMA = {
    "type": "object",
    "required": ["customer_id", "name", "region"],
    "properties": {
        "customer_id": {"type": "string"},
        "name": {"type": "string"},
        "region": {"type": "string"},
    },
    "additionalProperties": False,
}

_CUSTOMER_SEARCH_SCHEMA = {
    "type": "object",
    "required": ["results"],
    "properties": {"results": {"type": "array", "items": _CUSTOMER_SCHEMA}},
    "additionalProperties": False,
}

_ORDER_SCHEMA = {
    "type": "object",
    "required": ["order_id", "customer_id", "status"],
    "properties": {
        "order_id": {"type": "string"},
        "customer_id": {"type": "string"},
        "status": {"type": "string"},
    },
    "additionalProperties": False,
}

_INVENTORY_SCHEMA = {
    "type": "object",
    "required": ["sku", "available"],
    "properties": {"sku": {"type": "string"}, "available": {"type": "integer"}},
    "additionalProperties": False,
}

_QUOTE_SCHEMA = {
    "type": "object",
    "required": ["quote_id", "customer_id", "amount", "region", "status"],
    "properties": {
        "quote_id": {"type": "string"},
        "customer_id": {"type": "string"},
        "amount": {"type": "number"},
        "region": {"type": "string"},
        "status": {"type": "string"},
    },
    "additionalProperties": False,
}


async def test_customer_search_output_matches_its_contract(sales_domain_url: str) -> None:
    result = await call_tool_directly(
        sales_domain_url, "sales.customer.search", {"query": "Aurora"}
    )

    assert result.is_error is not True
    jsonschema.validate(result.structured_content, _CUSTOMER_SEARCH_SCHEMA)


async def test_customer_get_output_matches_its_contract(sales_domain_url: str) -> None:
    result = await call_tool_directly(
        sales_domain_url, "sales.customer.get", {"customer_id": "cust-001"}
    )

    assert result.is_error is not True
    jsonschema.validate(result.structured_content, _CUSTOMER_SCHEMA)


async def test_order_get_output_matches_its_contract(sales_domain_url: str) -> None:
    result = await call_tool_directly(sales_domain_url, "sales.order.get", {"order_id": "ord-001"})

    assert result.is_error is not True
    jsonschema.validate(result.structured_content, _ORDER_SCHEMA)


async def test_inventory_check_output_matches_its_contract(sales_domain_url: str) -> None:
    result = await call_tool_directly(sales_domain_url, "sales.inventory.check", {"sku": "sku-100"})

    assert result.is_error is not True
    jsonschema.validate(result.structured_content, _INVENTORY_SCHEMA)


async def test_quote_create_output_matches_its_contract(sales_domain_url: str) -> None:
    result = await call_tool_directly(
        sales_domain_url, "sales.quote.create", {"customer_id": "cust-001", "amount": 100.0}
    )

    assert result.is_error is not True
    jsonschema.validate(result.structured_content, _QUOTE_SCHEMA)


async def test_quote_update_output_matches_its_contract(sales_domain_url: str) -> None:
    created = await call_tool_directly(
        sales_domain_url, "sales.quote.create", {"customer_id": "cust-001", "amount": 100.0}
    )
    quote_id = created.structured_content["quote_id"]

    result = await call_tool_directly(
        sales_domain_url, "sales.quote.update", {"quote_id": quote_id, "amount": 200.0}
    )

    assert result.is_error is not True
    jsonschema.validate(result.structured_content, _QUOTE_SCHEMA)


@pytest.mark.parametrize(
    "tool_name",
    [
        "sales.customer.search",
        "sales.customer.get",
        "sales.order.get",
        "sales.inventory.check",
        "sales.quote.create",
        "sales.quote.update",
    ],
)
async def test_a_call_missing_its_required_field_fails_the_contract(
    sales_domain_url: str, tool_name: str
) -> None:
    """EP-15-T01's acceptance criterion, the input side: every tool's
    real, auto-generated `input_schema` is actually enforced server-side --
    an empty argument set (violating every tool's own required fields)
    must always be rejected, never silently coerced or ignored."""
    result = await call_tool_directly(sales_domain_url, tool_name, {})

    assert result.is_error is True


async def test_a_wrong_typed_field_fails_the_contract(sales_domain_url: str) -> None:
    result = await call_tool_directly(sales_domain_url, "sales.inventory.check", {"sku": 12345})

    assert result.is_error is True
