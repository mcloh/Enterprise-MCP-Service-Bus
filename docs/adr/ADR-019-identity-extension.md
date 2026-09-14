# ADR-019: MCP Client identity -- production extension point (mTLS / workload identity)

**Status:** Documented (spike), not implemented in the RI (EP-01-T04, `could`).
**Related:** `docs/RI-PLANNING.md` ADR-019 entry (confirmed decision, 2026-09-11), README.md §19, RF-02, Axiom 2.

## Context

The RI's identity boundary (`src/emcp_bus/identity/authn.py`, EP-01-T03) is
OAuth 2.1 `client_credentials` against Keycloak (EP-01-T01): every MCP Client
authenticates with a client_id + secret, gets a short-lived JWT, and the
Gateway validates that JWT's signature/issuer/audience/expiry against the
IdP's JWKS before trusting the `azp` claim as the caller's identity.

This is a deliberate, confirmed decision for the RI (not a placeholder): OAuth
2.1 satisfies every property README.md §19 actually requires of an identity
mechanism -- short-lived, revocable, audience-bound, verifiable without a
shared long-term secret in the request path. Real enterprise deployments
commonly go further, using mTLS (mutual TLS client certificates) or a cloud
provider's workload identity federation (e.g. SPIFFE/SPIRE, AWS IAM roles for
service accounts, GCP Workload Identity, Azure Managed Identity) instead of --
or in addition to -- a bearer JWT. This ADR documents how that extension
plugs into the RI's existing seam, without requiring one, so a production
fork isn't blocked on a redesign.

## Decision

Do **not** implement mTLS/workload identity in the RI. Document the
extension point instead, so `EP-01-T03`'s contract is provably stable under
it.

## The extension point

`TokenValidator.validate(token: str) -> AuthenticatedClient` is the *only*
function in the RI that produces client identity for authorization purposes
(`emcp_bus.gateway.server.on_list_tools`/`on_call_tool` both call
`get_access_token()`, which is populated by the SDK's `TokenVerifier`
protocol wrapping this same validator -- see
`emcp_bus.identity.token_verifier.MCPTokenVerifier`). Everything downstream
of it -- `EntitlementManager.resolve`, the PDP, the audit/correlation layer
(EP-08) -- consumes only the resulting `AuthenticatedClient.client_id`. None
of that code cares *how* the identity was established.

A production deployment adding mTLS or workload identity would:

1. Implement a second identity source honoring the same output contract:

   ```python
   class MTLSClientValidator:
       def validate(self, request: ...) -> AuthenticatedClient: ...
   ```

   fed from the terminating proxy/load balancer's verified client
   certificate (a `X-Client-Cert-CN` style header from a trusted mTLS
   terminator, or the ASGI `scope["extensions"]["tls"]` a compliant server
   exposes) instead of a JWT. `AuthenticatedClient.client_id` would be the
   certificate's Subject/SAN, mapped 1:1 to a `ClientRegistration.client_id`
   exactly the way a JWT's `azp` is today -- **no other model in the RI
   changes**: `ClientRegistration`, `ClientProfile`, `EntitlementManager`,
   the PDP contract, and the audit schema are all already identity-mechanism
   agnostic.

2. Provide an alternate `build_auth()`-equivalent in
   `emcp_bus/gateway/server.py` that wires the new validator in instead of
   `MCPTokenVerifier`, gated by deployment config -- the same shape as
   today's `build_auth()` returning `(None, None)` for the "no OIDC
   configured" mode. A hybrid deployment (mTLS for one class of backend
   service, OAuth for interactive agents) is possible by making the
   `TokenVerifier`/equivalent selection per-listener rather than
   per-process, which the SDK's `streamable_http_app(auth=..., token_verifier=...)`
   parameters already support per app instance.

3. Cloud workload identity (SPIFFE/SPIRE, IRSA, Workload Identity, Managed
   Identity) is a variant of the same shape: the "verify a credential the
   caller cannot forge, and extract a stable identifier from it" contract is
   identical, only the credential format and verification library differ.
   None of it requires touching `EntitlementManager`, the PDP, the Fabric
   router (EP-06-T01), or the audit/correlation layer (EP-08-T02/T03).

## What must not change

- **`AuthenticatedClient` shape** (`client_id`, `issuer`, `expires_at`):
  every downstream consumer types against this, not against a JWT-specific
  claim set.
- **Fail-closed contract**: any identity mechanism's failure path must raise
  (an `AuthenticationError`-shaped exception) rather than fall back to an
  unauthenticated or agent-declared identity (README.md §5, Axiom 2) -- this
  is the actual security property EP-01-T03's acceptance criteria test, and
  it is mechanism-independent.
- **No new privileged path for `clientInfo`**: whatever the identity
  mechanism, only a value verified independently of the MCP request body
  may ever populate `client_id`.

## Consequences

- Confirmed for the RI: reduces EP-01's implementation effort without
  weakening any of README.md §19's desirable identity properties (all are
  satisfied by OAuth 2.1 `client_credentials` against Keycloak).
- A production fork adding mTLS/workload identity changes exactly one
  module (`identity/`) and one wiring function (`build_auth`-equivalent);
  every other component in the RI (Entitlement Manager, PDP, Fabric,
  Registry, audit/correlation, approval) requires zero changes.
