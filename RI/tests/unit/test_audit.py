"""Audit events, sinks and correlation (EP-08-T02/T03, README.md §27/§28)."""

from __future__ import annotations

import json
from pathlib import Path

from emcp_bus.audit import events
from emcp_bus.audit.correlation import (
    DecisionCorrelation,
    compute_policy_decision_id,
    new_decision_id,
)
from emcp_bus.audit.models import EventCategory
from emcp_bus.audit.sink import InMemoryAuditSink, JSONLFileAuditSink


def test_tool_call_denied_is_classified_as_grl() -> None:
    event = events.tool_call_denied(
        client_id="sales-read-agent",
        profile_name="Sales.Read",
        tool="finance.payment.execute",
        reason_code="NOT_IN_ENTITLEMENT",
    )

    assert event.category is EventCategory.GRL
    assert event.reason_code == "NOT_IN_ENTITLEMENT"


def test_tool_call_allowed_is_classified_as_ic() -> None:
    correlation = DecisionCorrelation(
        decision_id="d1",
        policy_decision_id="p1",
        entitlement_version="e1",
        policy_version="v1",
        mcp_request_id="1",
    )
    event = events.tool_call_allowed(
        client_id="sales-read-agent",
        profile_name="Sales.Read",
        tool="sales.customer.get",
        correlation=correlation,
    )

    assert event.category is EventCategory.IC
    assert event.decision_id == "d1"
    assert event.policy_decision_id == "p1"
    assert event.entitlement_version == "e1"


def test_pdp_unavailable_is_classified_as_noc() -> None:
    event = events.pdp_unavailable(client_id="sales-read-agent", tool="sales.customer.get")

    assert event.category is EventCategory.NOC


def test_bypass_attempt_detected_is_classified_as_grl() -> None:
    event = events.bypass_attempt_detected(backend="sales-domain", reason="missing_credential")

    assert event.category is EventCategory.GRL
    assert event.payload == {"backend": "sales-domain", "reason": "missing_credential"}


def test_event_payload_never_contains_a_raw_token_value() -> None:
    """README.md §27, 'Não registrar': a payload key that looks like a secret
    is replaced by a hash reference, never left as the raw value."""
    event = events.tool_call_allowed(
        client_id="c1",
        profile_name="Sales.Read",
        tool="sales.customer.get",
        correlation=DecisionCorrelation(
            decision_id="d1",
            policy_decision_id="p1",
            entitlement_version=None,
            policy_version=None,
            mcp_request_id=None,
        ),
    )
    event.payload = {"backend_token": "super-secret-value", "customer_id": "cust-001"}
    # Re-trigger sanitization the way construction does (model_post_init runs
    # once at construction; this simulates a caller building payload then
    # assigning it, which the real call sites never do -- included as an
    # explicit regression guard on the sanitizer itself).
    from emcp_bus.audit.models import _sanitize

    sanitized = _sanitize(event.payload)
    assert sanitized["backend_token"].startswith("sha256:")
    assert sanitized["backend_token"] != "super-secret-value"
    assert sanitized["customer_id"] == "cust-001"


def test_in_memory_sink_collects_emitted_events() -> None:
    sink = InMemoryAuditSink()
    event = events.client_authenticated(client_id="c1", mcp_request_id="1")

    sink.emit(event)

    assert sink.events == [event]


def test_jsonl_file_sink_appends_one_line_per_event(tmp_path: Path) -> None:
    path = tmp_path / "audit" / "events.jsonl"
    sink = JSONLFileAuditSink(path)

    sink.emit(events.client_authenticated(client_id="c1", mcp_request_id="1"))
    sink.emit(events.client_authenticated(client_id="c2", mcp_request_id="2"))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["client_id"] == "c1"
    assert json.loads(lines[1])["client_id"] == "c2"


def test_new_decision_id_is_unique_per_call() -> None:
    assert new_decision_id() != new_decision_id()


def test_policy_decision_id_is_deterministic_for_identical_inputs() -> None:
    def _compute() -> str:
        return compute_policy_decision_id(
            policy_version="v1",
            client_profile="Sales.Write",
            tool="sales.quote.create",
            arguments={"amount": 100, "region": "BR-SP"},
        )

    assert _compute() == _compute()


def test_policy_decision_id_differs_for_different_arguments() -> None:
    def _compute(amount: int) -> str:
        return compute_policy_decision_id(
            policy_version="v1",
            client_profile="Sales.Write",
            tool="sales.quote.create",
            arguments={"amount": amount},
        )

    assert _compute(100) != _compute(200)
