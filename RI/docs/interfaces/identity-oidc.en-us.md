# Interface: MCP Client identity and registration (OIDC)

Contract for registering an MCP Client and the OIDC token it presents to the Gateway.
Implementation: [`src/emcp_bus/identity/models.py`](../../src/emcp_bus/identity/models.py),
[`identity/authn.py`](../../src/emcp_bus/identity/authn.py),
[`identity/shared_client_lint.py`](../../src/emcp_bus/identity/shared_client_lint.py). See
[`AS-BUILT.md`](../AS-BUILT.md#identidade-do-mcp-client-ep-01).

## Registering an MCP Client

One YAML file per client in `config/clients/*.yaml`, validated against `ClientRegistration`:

```yaml
client_id: finance-payments-agent   # exactly the token's azp/client_id claim
profile: Finance.Payments           # name of a ClientProfile under config/clients/profiles/
environment: production             # "dev" | "ci" | "production"
description: "Finance agent authorized to create/execute payments (R3, approval above threshold)"
```

(real example: `config/clients/finance-payments-agent.yaml`)

`client_id` is the sole link between an authenticated identity and a `ClientProfile` — two
distinct `client_id`s never share a `profile` unless that is an explicit and auditable decision
(the shared-client rule, `identity/shared_client_lint.py`, wired into
`make validate-schemas`).

## Registering the client with the IdP

The client must exist in the IdP realm with the `client_credentials` grant enabled and an
audience mapper pointing at the Gateway's `OIDC_AUDIENCE` (`emcp-gateway` by default). See
`deploy/keycloak/realm-export.json` for the 3 example clients already configured this way
(`sales-read-agent`, `sales-write-agent`, `finance-payments-agent`).

## Access token contract

Any OIDC-compliant IdP works (`TokenValidator` is provider-agnostic). Claims required and
validated by `TokenValidator.validate`:

| Claim | Use |
|---|---|
| `exp` | Expiration — required, validated with `leeway_seconds=5`. |
| `iss` | Must match `OIDC_ISSUER` exactly. |
| `aud` | Must contain `OIDC_AUDIENCE`. |
| `azp` (preferred) or `client_id` | Sole source of client identity — never `clientInfo` from the MCP request nor any body field. |

Signature verified via JWKS (`OIDC_JWKS_URL`), `RS256` algorithm. Failure of any check raises
`AuthenticationError`, treated by the Gateway as `UNAUTHENTICATED` (fail-closed).

## How a new client registers, end to end

1. Create/update the client in the IdP (`client_credentials` grant, audience mapper).
2. Create `config/clients/<client-id>.yaml` (`ClientRegistration`).
3. Point `profile` at an existing `ClientProfile`, or create a new one under
   `config/clients/profiles/` (see [`registry-capability-manifest.md`](registry-capability-manifest.md)
   for how a capability references a profile via `entitlements`).
4. `make validate-schemas`.
5. Restart the Gateway (client registrations are loaded at boot, no hot-reload).

## Errors

| Situation | Behavior |
|---|---|
| Missing/malformed/expired token or invalid signature | `AuthenticationError` → Gateway treats it as `UNAUTHENTICATED`. |
| Incorrect `aud`/`iss` | `AuthenticationError` → `UNAUTHENTICATED` (README.md §45 Test 8). |
| Valid token, but `client_id` without a matching `ClientRegistration` | `UnknownClientError` → Gateway responds `UNKNOWN_CLIENT` on `tools/call`, empty list on `tools/list`. |
