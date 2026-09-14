# Interface: PDP (OPA)

Data/query contract for the Policy Decision Point. Implementation:
[`src/emcp_bus/pdp/client.py`](../../src/emcp_bus/pdp/client.py),
[`pdp/models.py`](../../src/emcp_bus/pdp/models.py),
[`config/policies/entitlement.rego`](../../config/policies/entitlement.rego),
[`config/policies/transaction.rego`](../../config/policies/transaction.rego). See
[`AS-BUILT.md`](../AS-BUILT.md#pdp--policy-engine-ep-03).

## Two-step model

`PDPClient.evaluate(client_profile, tool, arguments, customer_classification)` queries, in
order, and never in parallel:

1. **`emcp.entitlement`** (`entitlement.rego`) — `allow` if `tool` is in
   `data.emcp.client_profiles[client_profile].allowed_tools`. `DENY` here is final
   (`reason_code=NOT_IN_ENTITLEMENT`) — no argument is ever evaluated.
2. **`emcp.transaction`** (`transaction.rego`) — only evaluated if step 1 allowed. Restricts by
   argument/resource; can never add a tool absent from the entitlement. Returns `allow` and
   `require_approval` independently.

## Versioned data in OPA

`EntitlementManager.sync_profiles_to_pdp()` pushes each validated `ClientProfile` to
`PUT /v1/data/emcp/client_profiles/<profile_name>` at boot — the Rego never reads YAML directly.

## Evaluation request

```
POST /v1/data/emcp/entitlement/allow
{"input": {"client_profile": "Sales.Write", "tool": "finance.payment.execute"}}
```

```
POST /v1/data/emcp/transaction
{"input": {
  "client_profile": "Finance.Payments",
  "tool": "finance.payment.execute",
  "arguments": {"amount": 15000, "region": "BR-SP"},
  "customer_classification": "standard"
}}
```

## Combined response (`PDPDecision`)

```json
{"outcome": "ALLOW" | "DENY" | "REQUIRE_APPROVAL", "policy_version": "a1b2c3d4e5f6", "reason_code": "..."}
```

Never a lone boolean — `policy_version` and `reason_code` are mandatory in every response.

| `reason_code` | `outcome` | When |
|---|---|---|
| `NOT_IN_ENTITLEMENT` | `DENY` | Step 1 denied. |
| `TRANSACTION_POLICY_DENIED` | `DENY` | Step 1 allowed, step 2 denied (limit, region, classification). |
| `APPROVAL_THRESHOLD_EXCEEDED` | `REQUIRE_APPROVAL` | `allow=true` and `amount > restrictions.approval_threshold`. |
| `ALLOWED` | `ALLOW` | Both steps allowed, without exceeding the threshold. |

## `policy_version`

A SHA-256 hash (12 characters) of the content of the `*.rego` files (except `*_test.rego`) in
`config/policies/`, computed once at Gateway boot (`compute_policy_version`). Propagated in
every decision and audit event — see [`audit-events.md`](audit-events.md). A production
deployment would replace this with a real OPA bundle revision (see
`../Production-Recommendations.md`); the contract (`PDPDecision.policy_version` as an opaque
string) would not change.

## Errors

| Situation | Exception | Handling by the caller (Gateway) |
|---|---|---|
| OPA unreachable, timeout, malformed response | `PDPUnavailableError` | Treated as `DENY` (`PDP_UNAVAILABLE`) — never an implicit ALLOW (fail-closed, README.md §38). |
| Failure to push a `ClientProfile` at boot | `PDPUnavailableError` | The Gateway does not come up "healthy" — there is no degraded mode without entitlement sync. |

## How a new policy takes effect

Editing `config/policies/*.rego` changes the computed `policy_version` (content hash). There is
no hot-reload in this RI — restart the Gateway (which restarts the associated OPA process, or
point it at an already-running OPA with the updated Rego via `opa run --server config/policies/`).
