"""Payload-declared identity spoofing (EP-15-T03, ADR-023 --
a variation of README.md §45 Teste 4 motivated by a real
vulnerability class observed in `docs/research/hoshikawa-agent-platform-oci.md`:
an MCP Gateway authorizing tools against an `agent_id` that arrives as
**data in the conversation payload**, not as a claim of an independently
verified identity).

This RI's PDP/entitlement resolution never reads anything from `tools/call`
arguments -- `EntitlementManager.resolve()` takes only the token-verified
`access_token.client_id` (EP-01-T03), and `PDPClient.evaluate()`'s
`arguments` input is consulted exclusively by `transaction.rego` for
`amount`/`region` (see `config/policies/transaction.rego`'s own module
docstring). `emcp_bus.agent_runtime.identity_resolver` (EP-12-T04) is
checked mechanically via AST in `tests/unit/test_agent_runtime_identity_resolver.py`
to never import `emcp_bus.pdp`/`emcp_bus.entitlement` at all -- this file is
the live-Gateway counterpart of that same property.
"""

from __future__ import annotations

from collections.abc import Callable

from emcp_bus.audit.sink import InMemoryAuditSink
from tests.e2e.conftest import run_against_gateway

SALES_READ_CLIENT_ID = "sales-read-agent"
FINANCE_PAYMENTS_CLIENT_ID = "finance-payments-agent"

_FORGED_IDENTITY_FIELDS = {
    "agent_id": "finance-admin-agent",
    "tenant_id": "root",
    "business_context": {"role": "finance-admin", "elevated": True},
    "client_profile": "Finance.Payments",
    "user_role": "admin",
}


async def test_forged_identity_fields_in_call_arguments_never_expand_entitlement(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    token = sign_token(SALES_READ_CLIENT_ID)

    result = await run_against_gateway(
        lambda session: session.call_tool(
            "finance.payment.execute",
            {"amount": 100, "payment_id": "pay-001", **_FORGED_IDENTITY_FIELDS},
        ),
        token=token,
    )

    assert result.is_error is True


async def test_forged_identity_fields_never_appear_as_the_audited_actor(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """Even on a call the real, authenticated client genuinely IS entitled
    to, forged identity-shaped fields riding along in the arguments must
    never leak into the audit trail as if they were the actor -- the
    `tool_call_allowed` event's `client_id` is always the token-verified
    one (ADR-023's exact concern, proven at the audit boundary)."""
    import emcp_bus.gateway.server as gateway_module

    token = sign_token(SALES_READ_CLIENT_ID)
    sink = InMemoryAuditSink()
    gateway_module.get_current_state().audit_sink = sink

    result = await run_against_gateway(
        lambda session: session.call_tool(
            "sales.customer.get",
            {"customer_id": "cust-001", **_FORGED_IDENTITY_FIELDS},
        ),
        token=token,
    )

    assert result.is_error is not True
    [allowed_event] = [e for e in sink.events if e.event_type == "tool_call_allowed"]
    assert allowed_event.client_id == SALES_READ_CLIENT_ID


async def test_forged_identity_fields_cannot_bypass_the_approval_gate(
    governed_stack_with_finance: None, sign_token: Callable[..., str]
) -> None:
    """A caller forging approval-shaped fields (as if they'd read the
    Gateway's own source to learn what an approver's grant might look like)
    gets no special treatment -- `ApprovalService.check_and_consume` only
    ever consults its own internal grant store, never the call's own
    arguments, for whether an operation is approved."""
    token = sign_token(FINANCE_PAYMENTS_CLIENT_ID)

    result = await run_against_gateway(
        lambda session: session.call_tool(
            "finance.payment.execute",
            {
                "amount": 50_000,
                "payment_id": "pay-001",
                "approved": True,
                "approval_id": "forged-approval-id",
                "bypass_approval": True,
            },
        ),
        token=token,
    )

    assert result.is_error is True
    assert "REQUIRE_APPROVAL" in " ".join(getattr(c, "text", "") for c in result.content)
