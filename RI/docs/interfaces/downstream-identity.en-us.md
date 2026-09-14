# Interface: downstream / outbound identity

Outbound identity contract, for whoever is going to integrate a new backend/domain server.
Implementation: [`src/emcp_bus/downstream/models.py`](../../src/emcp_bus/downstream/models.py),
[`downstream/identity.py`](../../src/emcp_bus/downstream/identity.py). See
[`AS-BUILT.md`](../AS-BUILT.md#downstream--outbound-identity-ep-07).

Principle: `inbound token (MCP Client → Gateway) ≠ outbound token (Fabric → Backend)`. The Gateway
authenticates the *caller*; this contract resolves a separate question — which credential the
Fabric presents *to the backend* — and never resolves it by forwarding the inbound token
unmodified.

## Registering a backend (`BackendConfig`)

One YAML file per backend in `config/backends/*.yaml`:

```yaml
# service_account (default mode of the seed backends)
backend: sales-domain
url: http://sales-domain:8100/mcp
audience: sales-domain-service        # never the same as the Gateway's inbound OIDC_AUDIENCE
credential_mode: service_account
service_account_token_env_var: SALES_DOMAIN_SERVICE_TOKEN   # env var name, never a literal value
```

```yaml
# token_exchange (available alternative, verified against real Keycloak)
backend: finance-domain
url: http://finance-domain:8101/mcp
audience: finance-domain-service
credential_mode: token_exchange
token_exchange_endpoint: http://keycloak:8080/realms/emcp/protocol/openid-connect/token
token_exchange_scope: aud-finance-domain-service
```

## `service_account` mode

Static credential, read from an environment variable (name, never value, declared in
`service_account_token_env_var`) at the time of each call. Absence of the variable at runtime →
`BackendCredentialUnavailableError`.

## `token_exchange` mode (RFC 8693, Keycloak Standard Token Exchange)

Two HTTP round trips per new exchange (`TokenExchangeClient.exchange`): (1) `client_credentials`
as the Gateway's own exchange client, producing a `subject_token`; (2) exchanging that
`subject_token` for a token with the target backend's `audience`. Cached per backend until
shortly before the exchange's own `expires_in` — a cache hit costs zero round trips.

**Required IdP configuration (empirically verified against real Keycloak 26.7.3):**

- The Gateway's exchange client (`GATEWAY_TOKEN_EXCHANGE_CLIENT_ID`/`_SECRET`) needs
  `attributes.standard.token.exchange.enabled = "true"` and `serviceAccountsEnabled`.
- `audience` must be the id of a client **actually registered** in the realm — a free-form string
  fails with `"Audience not found"`.
- Requesting `audience` without also requesting, via `scope`, a client scope that actually adds
  that audience fails with `"Requested audience not available"` — the `audience` parameter only
  **restricts**, never **adds**. That is why `token_exchange_scope` is mandatory in this mode.
- That client scope must carry an `oidc-audience-mapper` pointing at the backend's `audience`,
  and be a default scope (or requested optional scope) of the Gateway's exchange client.

See `deploy/keycloak/realm-export.json` for a real, already-configured example (`gateway-token-exchange`
+ client scopes `aud-sales-domain-service`/`aud-finance-domain-service`).

## Outbound contract (`BackendCredential`)

```python
BackendCredential(
    backend="finance-domain",
    url="http://finance-domain:8101/mcp",
    token="...",
    audience="finance-domain-service",
)
```

## How to integrate a new backend

1. Register the backend with the IdP if using `token_exchange` (client scope +
   `oidc-audience-mapper` for the chosen `audience`) — or simply define the static token's env
   var if using `service_account`.
2. Create `config/backends/<backend>.yaml` (`BackendConfig`).
3. Reference `backend.service` == that same id in every `CapabilityManifest` that routes to
   it (see [`registry-capability-manifest.md`](registry-capability-manifest.md)).
4. If the backend is MCP-native (`backend.type: mcp`, the only one with live dispatch in this
   RI), implement the `BackendCredentialGate` on the backend side (see
   `services/example_mcp_servers/sales_domain/server.py` as a reference) — a request without the
   Gateway's outbound credential should never reach a tool handler.

## Errors

| Situation | Exception | Handling by the caller (Gateway) |
|---|---|---|
| `backend` without a registered `BackendConfig` | `UnknownBackendError` | `UnroutableCapabilityError` in the Fabric → `UNROUTABLE_CAPABILITY`. |
| `service_account` env var missing at runtime | `BackendCredentialUnavailableError` | `backend_credential_unavailable` (NOC event) → call denied. |
| RFC 8693 exchange rejected by the IdP | `TokenExchangeError` → re-raised as `BackendCredentialUnavailableError` | Same as above. |
