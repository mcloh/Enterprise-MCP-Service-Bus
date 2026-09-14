"""Header/body consistency check (EP-05-T08, README.md §22, SEP-2243)."""

from __future__ import annotations

import json

from emcp_bus.gateway.canonical_request import find_header_body_mismatch


def _body(method: str, params: dict[str, object] | None = None) -> bytes:
    return json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    ).encode()


def test_no_headers_present_is_never_a_mismatch() -> None:
    assert (
        find_header_body_mismatch(_body("tools/call"), method_header=None, name_header=None) is None
    )


def test_matching_method_header_is_not_a_mismatch() -> None:
    body = _body("tools/list")

    assert find_header_body_mismatch(body, method_header="tools/list", name_header=None) is None


def test_mismatched_method_header_is_rejected() -> None:
    body = _body("tools/list")

    reason = find_header_body_mismatch(body, method_header="tools/call", name_header=None)

    assert reason is not None
    assert "mcp-method" in reason


def test_matching_name_header_for_tools_call_is_not_a_mismatch() -> None:
    body = _body("tools/call", {"name": "sales.customer.get", "arguments": {}})

    reason = find_header_body_mismatch(
        body, method_header="tools/call", name_header="sales.customer.get"
    )

    assert reason is None


def test_mismatched_name_header_for_tools_call_is_rejected() -> None:
    """The concrete attack this closes: a header claiming one tool while the
    body actually invokes another -- whichever a naive reader trusted, the
    request must instead be rejected outright (README.md §22)."""
    body = _body("tools/call", {"name": "finance.payment.execute", "arguments": {}})

    reason = find_header_body_mismatch(
        body, method_header="tools/call", name_header="sales.customer.get"
    )

    assert reason is not None
    assert "mcp-name" in reason


def test_name_header_is_irrelevant_for_a_non_name_bearing_method() -> None:
    body = _body("tools/list")

    reason = find_header_body_mismatch(body, method_header="tools/list", name_header="anything")

    assert reason is None


def test_unparseable_body_is_left_to_the_app_itself() -> None:
    reason = find_header_body_mismatch(b"not json", method_header="tools/list", name_header=None)

    assert reason is None
