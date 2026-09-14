"""Contract tests for the Finance domain server (EP-15-T01, README.md §7.2).

See test_sales_domain.py's module docstring for why the output schemas
below are hand-written rather than reused from the SDK's auto-generated
(too-generic) ones.
"""

from __future__ import annotations

import jsonschema
import pytest

from tests.contract.conftest import call_tool_directly

_INVOICE_SCHEMA = {
    "type": "object",
    "required": ["invoice_id", "customer_id", "amount", "status"],
    "properties": {
        "invoice_id": {"type": "string"},
        "customer_id": {"type": "string"},
        "amount": {"type": "number"},
        "status": {"type": "string"},
    },
    "additionalProperties": False,
}

_PAYMENT_CREATE_SCHEMA = {
    "type": "object",
    "required": ["payment_id", "invoice_id", "amount", "status"],
    "properties": {
        "payment_id": {"type": "string"},
        "invoice_id": {"type": "string"},
        "amount": {"type": "number"},
        "status": {"type": "string"},
    },
    "additionalProperties": False,
}

_PAYMENT_EXECUTE_SCHEMA = {
    "type": "object",
    "required": ["payment_id", "invoice_id", "amount", "status", "executed_amount"],
    "properties": {
        "payment_id": {"type": "string"},
        "invoice_id": {"type": "string"},
        "amount": {"type": "number"},
        "status": {"type": "string"},
        "executed_amount": {"type": "number"},
    },
    "additionalProperties": False,
}


async def test_invoice_get_output_matches_its_contract(finance_domain_url: str) -> None:
    result = await call_tool_directly(
        finance_domain_url, "finance.invoice.get", {"invoice_id": "inv-001"}
    )

    assert result.is_error is not True
    jsonschema.validate(result.structured_content, _INVOICE_SCHEMA)


async def test_payment_create_output_matches_its_contract(finance_domain_url: str) -> None:
    result = await call_tool_directly(
        finance_domain_url, "finance.payment.create", {"invoice_id": "inv-001", "amount": 500.0}
    )

    assert result.is_error is not True
    jsonschema.validate(result.structured_content, _PAYMENT_CREATE_SCHEMA)


async def test_payment_execute_output_matches_its_contract(finance_domain_url: str) -> None:
    created = await call_tool_directly(
        finance_domain_url, "finance.payment.create", {"invoice_id": "inv-001", "amount": 500.0}
    )
    payment_id = created.structured_content["payment_id"]

    result = await call_tool_directly(
        finance_domain_url,
        "finance.payment.execute",
        {"payment_id": payment_id, "amount": 500.0},
    )

    assert result.is_error is not True
    jsonschema.validate(result.structured_content, _PAYMENT_EXECUTE_SCHEMA)


@pytest.mark.parametrize(
    "tool_name",
    ["finance.invoice.get", "finance.payment.create", "finance.payment.execute"],
)
async def test_a_call_missing_its_required_field_fails_the_contract(
    finance_domain_url: str, tool_name: str
) -> None:
    result = await call_tool_directly(finance_domain_url, tool_name, {})

    assert result.is_error is True


async def test_a_wrong_typed_field_fails_the_contract(finance_domain_url: str) -> None:
    result = await call_tool_directly(
        finance_domain_url,
        "finance.payment.create",
        {"invoice_id": "inv-001", "amount": "not-a-number"},
    )

    assert result.is_error is True
