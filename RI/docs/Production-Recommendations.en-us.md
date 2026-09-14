# Production Recommendations — what changes for a real production environment

Synthesis of what a real production deployment would need to change relative to this Reference
Implementation (RI), derived from the real limitations found and documented during the
implementation (see [`AS-BUILT.md`](AS-BUILT.md#limitações-e-achados-arquiteturais-reais)
for the detail of each finding). Nothing here is hypothetical: each item corresponds to a real
gap verified in testing, not to an assumption about what "might" be missing.

Target audience: whoever is going to **evaluate or adapt** this RI for a real scenario.

## Identity Provider

A real, highly available IdP (Keycloak cluster, or a managed equivalent), not the single
instance from `docker-compose.yml`. The extension to mTLS/workload identity — covering cases
where `client_credentials` is not strong enough (e.g.: workloads in a service mesh) — is
already documented as an extension point in `docs/adr/ADR-019-extensao-de-identidade.md`; production
would implement that extension, not reinvent the authentication middleware from scratch.

## PDP

Policy distribution via a real OPA bundle (a bundle server, not point-to-point
`push_client_profile` at Gateway boot) — enables versioning, rollback, and consistent
distribution to multiple Gateway replicas. `policy_version` would stop being a hash of local
files (`pdp/client.py:compute_policy_version`, sufficient to prove that the field flows end to
end) and would become the real revision of the published bundle.

## Registry

A durable store (Postgres) instead of the current SQLite (`registry/store.py`) — SQLite
correctly proves the contract/lifecycle, but is not the right choice for write concurrency
across multiple Gateway replicas in production. A real administrative endpoint for
capability revocation/lifecycle also does not exist today: the state transitions
(`registry/lifecycle.py`) are exercised via direct calls to internal methods in tests, not
via a protected HTTP API that an external governance system could call.

## Audit

A durable sink (Postgres, or a queue like Kafka/SQS) instead of the current append-only JSONL
(`audit/sink.py`). More importantly: a real alert connected to sink failure. The Gateway's
current behavior — swallowing any exception from `audit_sink.emit()` (`gateway/server.py:
_emit_audit`) so that an audit failure on a low-risk operation never turns into a 500 error —
is **correct by design**, not a bug to remove; but in production, a silent sink failure that is
never observed is, in practice, an audit blackout with no alarm. Production needs dedicated
observability over the sink itself (a failure metric for `emit`, an alert), not a change to the
Gateway's fail-open behavior.

## Approval workflow

A persistent store (not the in-memory `dict` of `approval/service.py`, which loses all pending
approval state on a process restart) and a real notification/UI integration for the
approver — today `grant()`/`deny()` are called via CLI/test, with no real interface for a
human.

## Rate limiting and anti-replay

Neither of the two exists in this RI today — real gaps, documented and covered by a dedicated
adversarial test (`tests/adversarial/test_protocol_identity.py`), never hidden. A production
Gateway needs both: anti-replay (a nonce, or a deduplication window per
`mcp_request_id`) to close the byte-identical request replay vector with a still-valid token;
rate limiting to contain mass exfiltration via repeated legitimate read calls — today mitigated
only by after-the-fact detectability via audit, never by real-time prevention.

## Observability

The `otel-collector` + Jaeger of the `observability` profile has validated configuration
(`docker compose config`), but has not received real traffic from an automated test —
production needs a real OTLP collector/backend actually receiving and retaining traffic, with
dashboards and alerts on the correlation `span attributes` already emitted (`decision_id`,
`policy_decision_id`, `entitlement_version`). The self-hosted Langfuse (EP-13-T02) is this RI's
only OTLP consumer validated with real traffic, and only manually — replicating that validation
as part of CI is a real investment, not just turning on the profile.

## Secrets

A real secrets manager (Vault, a managed KMS, or equivalent) instead of environment variables
with development values (`SALES_DOMAIN_SERVICE_TOKEN`,
`GATEWAY_TOKEN_EXCHANGE_CLIENT_SECRET`, etc., see `.env.example`) — the indirection *mechanism*
(`BackendConfig.service_account_token_env_var` holds the *name* of the variable, never a
literal value, validated by `field_validator`) is already correct and stays as-is: production
changes only where the env var is populated from, not how the Gateway consumes it.

## Scale and high availability

The Gateway does not maintain shared state between requests — each `tools/call` opens its own
upstream session (`gateway/server.py:_with_downstream_session`), with no persistent connection
pool or in-memory session state between calls. This is favorable for scaling horizontally
(multiple replicas behind a load balancer, without sticky sessions). PDP, Registry, and
Approval, on the other hand, each need their own HA strategy in production (see sections
above) — none of the three was designed for multiple replicas in the RI.

## Multiagent (ADR-024)

- **Mode A**: the `GlobalSupervisor` router (`agent_runtime/global_supervisor.py`) is a
  deliberately simple keyword-based stand-in — it is not, and never intended to be, a claim of
  routing quality. Production would replace `RouterFn` with real intent classification
  (LLM or rules engine), with no change to the security boundary (each backend continues to
  resolve its own entitlement independently, an invariant that does not depend on router
  quality).
- **Mode B**: the `ModeBOrchestrator` invokes the journey graph once per client and combines the
  results in a layer above the graph — it does not scale natively to many domains without an
  extension of `JourneyState`/`build_journey_graph` for multiple clients in a single run (a
  design decision documented in the module itself, deliberately not attempted in this RI so as
  not to risk an already-tested component in a `could` demo). The current combination rule
  ("Finance always beats Sales") is also a reference rule, not a real ranking model — production
  would replace `ModeBOrchestrator._combine` with a real cross-domain `NBADecisionModel`.
