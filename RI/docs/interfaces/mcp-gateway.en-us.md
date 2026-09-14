# Interface: MCP Gateway

The Gateway's MCP surface — what any integrating MCP Client calls. Implementation:
[`src/emcp_bus/gateway/server.py`](../../src/emcp_bus/gateway/server.py),
[`gateway/canonical_request.py`](../../src/emcp_bus/gateway/canonical_request.py),
[`gateway/cache.py`](../../src/emcp_bus/gateway/cache.py). See [`AS-BUILT.md`](../AS-BUILT.md#pep--mcp-gateway-ep-05)
for the component's role in the architecture.

## Authentication

OAuth2/OIDC bearer token in the `Authorization` header. Validated against the JWKS of the configured
IdP (`OIDC_JWKS_URL`/`OIDC_ISSUER`/`OIDC_AUDIENCE`) — RS256 signature, `exp`, `iss`, `aud`. The
trusted identity is the token's `azp` claim (or, in its absence, `client_id`) — never a
`clientInfo` field or any part of the request body.

## Two deployment modes

| Mode | Condition | Behavior |
|---|---|---|
| With OIDC configured | `OIDC_JWKS_URL` + `OIDC_ISSUER` set | The `mcp` SDK's auth middleware rejects any connection without a valid bearer token before the `initialize` handshake. |
| Without OIDC configured | Env vars absent (default) | No auth middleware installed; every handler runs with `get_access_token() is None` and denies by default. |

Both modes are deny-by-default; neither is an "incomplete mode" waiting on the other — see
`tests/e2e/test_governed_gateway.py`.

## `tools/list`

Without a valid token: returns `tools: []`. With a valid token: returns the intersection of the
entitled backends' catalog (`CapabilityRouter.distinct_backends_for`) with the client's
`MaximumEntitlement` (`EntitlementManager.resolve(...).allowed_tools`) — never any backend's full
catalog. Each call re-evaluates entitlement from scratch; there is no server-side catalog cache
between clients.

**Cache hint (SEP-2549):** the response carries `ttl_ms`/`cache_scope`, always
`cache_scope="private"` — never `"public"`, since the result depends on the caller's authorization
(`gateway/cache.py:tools_list_cache_hint`). **Verified limitation**: on the classic session
transport this RI uses everywhere, the SDK drops `ttl_ms` during serialization (the field is only
delivered on the wire by the protocol's 2026-07-28 *stateless per-request* mode) — the client
always sees the default (`ttl_ms=0`), which is the most conservative fallback possible, never an
unsafe one. The actual security property (never leaking a catalog between clients) does not
depend on this — it comes from the Gateway recomputing entitlement on every call.

## `tools/call`

Reauthorized completely independently of `tools/list` — the prior list is never consulted to
decide whether a call is allowed. Flow:

1. No valid token → deny (see error table below).
2. Unknown client (`ClientRegistration` not found) → deny.
3. PDP consulted (`PDPClient.evaluate`, see [`pdp-opa.md`](pdp-opa.md)) with `client_profile`,
   `tool`, `arguments`.
4. `DENY` → deny with the PDP's `reason_code`.
5. `REQUIRE_APPROVAL` → consults `ApprovalService.check_and_consume`; without a granted approval,
   creates an `ApprovalRequest` (see [`approval-workflow.md`](approval-workflow.md)) and denies.
6. `ALLOW` → resolves the backend via `CapabilityRouter.route` (see
   [`registry-capability-manifest.md`](registry-capability-manifest.md)) and executes the call
   against the domain server, using the outbound credential (never the client's inbound token — see
   [`downstream-identity.md`](downstream-identity.md)).

### Denial format

Every denial is a structured `CallToolResult` (`is_error: true`), never a protocol error:

```json
{"is_error": true, "content": [{"type": "text", "text": "Access denied: <REASON_CODE>"}]}
```

| `REASON_CODE` | When |
|---|---|
| `UNAUTHENTICATED` | No valid token. |
| `UNKNOWN_CLIENT` | Valid token, but `client_id` without a `ClientRegistration`. |
| `PDP_UNAVAILABLE` | OPA unreachable — fail-closed, never an implicit ALLOW. |
| `NOT_IN_ENTITLEMENT` | The tool is not in `ClientProfile.allowed_tools` (PDP decision). |
| `TRANSACTION_POLICY_DENIED` | Entitlement OK, but the arguments violate `transaction.rego` (limit, region, classification). |
| `REQUIRE_APPROVAL:<reason>:<approval_id>` | Above the `approval_threshold` — use `approval_id` to track/grant out of band. |
| `UNROUTABLE_CAPABILITY` | No `ACTIVE` manifest for the tool, or the backend is not resolvable. |
| `UNSUPPORTED_BACKEND_TYPE:<type>` | The manifest points to a `backend.type` with no live dispatch in this RI (e.g. `rest`, see `AS-BUILT.md`). |

## Header/body consistency (EP-05-T08)

If the request carries the `Mcp-Method`/`Mcp-Name` headers (SEP-2243), they must agree with the
`method`/resource name in the JSON-RPC body, or the request is rejected with HTTP 400
(`{"error": "header_body_mismatch", "detail": "..."}`) before reaching authentication. Missing
headers are not an error — it's a consistency check, not a mandate to adopt the SEP.

## Correlation

Every decision carries, and propagates as OTel span attributes and in every audit event:
`decision_id`, `policy_decision_id`, `entitlement_version`, `policy_version`, `mcp_request_id`.
See [`audit-events.md`](audit-events.md).
