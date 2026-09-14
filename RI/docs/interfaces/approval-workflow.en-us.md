# Interface: approval workflow

Contract for the approval service, for whoever is going to build a human-approval UI/integration.
Implementation: [`src/emcp_bus/approval/models.py`](../../src/emcp_bus/approval/models.py),
[`approval/service.py`](../../src/emcp_bus/approval/service.py). See
[`AS-BUILT.md`](../AS-BUILT.md#approval-workflow-ep-14).

## When an approval comes into play

The PDP returns `outcome=REQUIRE_APPROVAL` (see [`pdp-opa.md`](pdp-opa.md)) when a transaction
exceeds `ClientProfile.restrictions.approval_threshold`. The Gateway calls
`ApprovalService.check_and_consume` on every attempt of that operation; without a granted and
still-valid approval, it creates an `ApprovalRequest` and denies the call with
`REQUIRE_APPROVAL:<reason_code>:<approval_id>` (see [`mcp-gateway.md`](mcp-gateway.md)).

## `ApprovalRequest`

```python
ApprovalRequest(
    approval_id="...",  # uuid4
    operation_hash="...",  # sha256(client_profile, tool, canonical arguments)
    client_profile="Finance.Payments",
    tool="finance.payment.execute",
    arguments_summary={"amount": 15000, "region": "BR-SP"},  # not redacted in this RI
    reason_code="APPROVAL_THRESHOLD_EXCEEDED",
    requested_at="2026-09-14T12:00:00Z",
    expires_at="2026-09-14T12:05:00Z",  # ttl_seconds=300 by default
    status="pending",  # pending | granted | denied | consumed
)
```

`operation_hash` binds the approval to the **exact triple** `(client_profile, tool, arguments)` —
canonical JSON with sorted keys, so the same logical call always produces the same hash
regardless of dict insertion order. An approval granted for one call never satisfies a different
call with the same `client_profile`/`tool` but different arguments.

## Lifecycle

```
request()  →  pending
grant()    →  granted   (emits an approval_granted audit event)
deny()     →  denied
check_and_consume()  →  True (exactly once) and marks "consumed"; False otherwise
```

`request()` is idempotent per operation: a repeated attempt of the same call while an approval is
`pending` returns the same request, and does not create a second one for the approver to
evaluate. `check_and_consume()` is the only way an attempt is released, and is single-use by
construction — never "enqueue and auto-release later": a `granted` approval that passes
`check_and_consume` is immediately marked `consumed` and never satisfies a second attempt, even
of the identical operation (README.md §46, "approval replay"). This check is protected by a
`threading.Lock` — without it, two genuinely concurrent attempts could both observe `granted`
before either wrote `consumed` (a real finding fixed during EP-15-T04, see `AS-BUILT.md`).

## Building an approval UI/integration

1. An approver watches for `tool_call_require_approval` events (see
   [`audit-events.md`](audit-events.md)) — `approval_id` is carried in `payload`.
2. The UI/integration calls `ApprovalService.grant(approval_id)` (or `deny`) out of band — today
   via CLI/direct Python call, there is no HTTP endpoint in this RI (see
   `../Production-Recommendations.md`).
3. The original caller retries the same call (`tools/call` with the same arguments) — the Gateway
   consults `check_and_consume` again and, now `granted`, releases the execution.

## Errors

| Situation | Exception |
|---|---|
| `grant`/`deny` on a nonexistent `approval_id` | `ApprovalNotFoundError` |
| Unexpected failure inside `check_and_consume` (any exception) | Handled by the Gateway as a denial — never as an implicit approval (EP-14-T03: `except Exception: approved = False`). |

## Not implemented in this RI

Persistent store (today an in-memory `dict` — loses all pending-approval state on a process
restart) and a real UI/notification for the approver. See
`../Production-Recommendations.md`.
