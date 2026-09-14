# AS-BUILT — Enterprise MCP Service Bus (RI)

Technical reference for what exists today in the Reference Implementation (RI): the
responsibility of each component, where the code lives, high-level input/output contracts (the
fine-grained detail of each contract is in [`interfaces/`](interfaces/)), what was validated and
against which real dependency, and the real architectural limitations found during
implementation.

Target audience: those who will **integrate with or extend** the RI. For those who will **run**
the RI, see [`How-To.md`](How-To.md). For those who will **evaluate/adapt** the RI for a real
scenario, see [`Assumptions.md`](Assumptions.md) and
[`Production-Recommendations.md`](Production-Recommendations.md).

Individual architectural decisions are recorded in [`../../docs/adr/`](../../docs/adr/)
(ADR-001 through ADR-025); the assumptions and reasoning behind them are synthesized in
[`Assumptions.md`](Assumptions.md).

## Status

The entire planned backlog (milestones M0 through M4) is implemented, tested, and validated.
**261 automated tests** (count verified via `pytest --collect-only` in this revision): 254 pass
with `pytest --forked` (unit + e2e + contract + adversarial), plus 7 security acceptance tests
(`tests/e2e/test_security_acceptance.py`) that require real Docker and are run separately due to
the build+Keycloak cost per run. Production logic with no mocks in the security and
orchestration core: real OPA (subprocess), real Keycloak (Docker), real LangGraph with SQLite
checkpointer, a real LLM (OpenAI-compatible endpoint), real HTTP JWKS (a lightweight stand-in for
the rest of the e2e suite) with real RS256 JWTs, real YAML from `config/`, real SQLite for the
Registry.

## Epic index

Every `EP-XX-TXX` that appears in comments/docstrings in the source code references one of these
epics. This table is the authoritative reference for these labels — consult it whenever a
comment/docstring cites an `EP-XX-TXX` without further context.

| Epic | Title | Main module/test |
|---|---|---|
| EP-00 | RI bootstrap and tooling | `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `src/emcp_bus/common/config.py` |
| EP-01 | MCP Client identity and authentication | `src/emcp_bus/identity/*.py`, `deploy/keycloak/realm-export.json` |
| EP-02 | Global Capability Registry and publishing pipeline | `src/emcp_bus/registry/*.py` |
| EP-03 | PDP / Policy Engine (OPA) | `src/emcp_bus/pdp/*.py`, `config/policies/*.rego` |
| EP-04 | Entitlement Manager | `src/emcp_bus/entitlement/*.py` |
| EP-05 | MCP Gateway / PEP | `src/emcp_bus/gateway/*.py` |
| EP-06 | Enterprise MCP Fabric and example domain servers | `src/emcp_bus/fabric/*.py`, `services/example_mcp_servers/*` |
| EP-07 | Downstream identity (inbound vs outbound) | `src/emcp_bus/downstream/*.py` |
| EP-08 | Auditing, correlation and observability | `src/emcp_bus/audit/*.py`, `src/emcp_bus/common/otel.py` |
| EP-09 | Profile Intelligence (generic contract) | `src/emcp_bus/profile_intelligence/*.py` |
| EP-10 | Offering Filter | `src/emcp_bus/offering_filter/service.py` |
| EP-11 | Service Orchestrator (NBA/NBO) | `src/emcp_bus/orchestrator/*.py` |
| EP-12 | Agent Runtime and channel adapters | `src/emcp_bus/agent_runtime/*.py` |
| EP-13 | Example agent and Langfuse instrumentation | `agents/example_agent/*` |
| EP-14 | Human-in-the-loop / Approval workflow | `src/emcp_bus/approval/*.py` |
| EP-15 | Security and adversarial tests | `tests/contract/`, `tests/e2e/test_security_acceptance.py`, `tests/adversarial/`, `tests/e2e/test_fail_closed.py` |
| EP-16 | Final deployment and documentation | `docker-compose.yml`, `docs/adr/` |

Within each epic, `TXX` numbers the tasks (e.g., `EP-05-T03` = third task of epic EP-05/Gateway —
the `tools/list` cache hint). The ADRs referenced by number (`ADR-XXX`) are individual files in
[`../../docs/adr/`](../../docs/adr/).

## Components

### MCP Client identity (EP-01)

**Responsibility:** authenticate the workload identity making the call, never the
self-declared identity in `clientInfo` or in any payload field. `src/emcp_bus/identity/authn.py`
(`TokenValidator`) validates an OAuth2/OIDC bearer token against the IdP's JWKS (RS256
signature, `exp`, `iss`, `aud`); the trusted `client_id` comes exclusively from the `azp`/
`client_id` claim of the verified token. `src/emcp_bus/identity/models.py`
(`ClientRegistration`) maps that `client_id` to exactly one `ClientProfile` (EP-04) via YAML in
`config/clients/*.yaml`. `shared_client_lint.py` (EP-01-T05) validates in CI that two distinct
agents never share the same `client_id` under different profiles.

**Validated against:** real Keycloak 26.7.3 via Docker (`tests/e2e/test_real_keycloak.py`) — the
`emcp` realm imported from `deploy/keycloak/realm-export.json`, 3 clients (`sales-read-agent`,
`sales-write-agent`, `finance-payments-agent`) with `client_credentials` grant; and a lighter
local JWKS HTTP server as a stand-in for the rest of the e2e suite (valid for validation logic,
not for real protocol integration with the IdP).

**Production extension documented, not implemented:** mTLS/workload identity —
`docs/adr/ADR-019-extensao-de-identidade.md`.

### PDP / Policy Engine (EP-03)

**Responsibility:** decide ALLOW/DENY/REQUIRE_APPROVAL deterministically and auditably.
Two-step model (`src/emcp_bus/pdp/client.py`, `PDPClient.evaluate`): (1) `entitlement.rego`
decides whether the tool is in `ClientProfile.allowed_tools` — DENY here is definitive, no
argument is evaluated; (2) `transaction.rego` restricts by argument/resource (value limit,
region, client classification) and can downgrade an ALLOW to REQUIRE_APPROVAL above
`approval_threshold`. Every response is a `PDPDecision` (`outcome`, `policy_version`,
`reason_code`) — never a boolean. `policy_version` is a SHA-256 hash (12 chars) of the content of
the `.rego` files on disk, computed once at Gateway boot.

**Validated against:** real OPA via subprocess (`opa run --server` binary), 9 Rego tests
(`opa test`) + 6 Python integration tests.

### Global Capability Registry (EP-02)

**Responsibility:** a control-plane asset with its own authority and lifecycle over the
capability catalog, separate from the execution view that the Gateway exposes to each client.
`registry/models.py` defines `CapabilityManifest` (canonical name `<domain>.<capability>`,
`risk_tier` R0–R4, `data_classification`, `side_effects`, `idempotent`, `entitlements`,
`backend`, `approval`, `observability`, `lifecycle`). `registry/pipeline.py`
(`PublishingPipeline`) is the sole entry path: it validates business gates (owner required,
backend declared, tiers R3/R4 require `approval.required=true`) and advances
`NOMINATE → REVIEW → REGISTER`; a separate `publish()` advances `REGISTER → ACTIVE`, when the
capability becomes resolvable by the Fabric. `registry/lifecycle.py` mechanically ensures that
nothing reaches `ACTIVE` without passing through `REVIEW`. `registry/store.py` persists to
SQLite; `registry/seed.py` populates the Registry from `config/capabilities/*.yaml` at Gateway
boot (one temporary file per process, not shared across runs).

**Validated against:** real SQLite, 9 example manifests (6 Sales + 3 Finance) going through the
full pipeline without manual intervention.

### PEP / MCP Gateway (EP-05)

**Responsibility:** the single Policy Enforcement Point. `src/emcp_bus/gateway/server.py`
implements two invariants: `tools/list` returns the intersection of the entitled backends'
catalog with the authenticated client's `MaximumEntitlement` (filtered discovery); `tools/call`
is reauthorized completely independently of what `tools/list` returned — the PDP is consulted on
every call. Without a valid token: `tools/list` empty, `tools/call` always `Access denied:
UNAUTHENTICATED`. An unreachable PDP is DENY (`PDP_UNAVAILABLE`), never implicit ALLOW. An
`AuditSink` failure never becomes a 500 error on an already-decided operation (`_emit_audit`,
swallows exceptions at all 8 emission points). Routing by capability is resolved on every call
via `CapabilityRouter` (EP-06) against the Registry — a client can see tools from more than one
backend (e.g., Sales + Finance). See [`interfaces/mcp-gateway.md`](interfaces/mcp-gateway.md) for
the full contract (headers, denial codes, cache hint).

**Validated against:** real OPA, real Keycloak (Docker), real RS256 JWTs, and a real host MCP
client against the containerized Gateway (`docker compose --profile core [--profile identity]
up`).

### Enterprise MCP Fabric and example domain servers (EP-06)

**Responsibility:** `src/emcp_bus/fabric/router.py` (`CapabilityRouter`) resolves a
`<domain>.<capability>` tool name to the backend that serves it, using only `ACTIVE` manifests
from the Registry — never a static mapping in the Gateway. `services/example_mcp_servers/sales_domain/`
(6 tools, R1+R2) and `finance_domain/` (3 tools: `invoice.get` R1, `payment.create` R2,
`payment.execute` R3 with a full approval cycle) are the two example domains, protected by
`BackendCredentialGate` (EP-05-T07) — a request without the Gateway's outbound credential never
reaches a tool handler. `fabric/adapters/rest_adapter.py` (EP-06-T04) implements a generic REST
adapter, tested standalone (`httpx.MockTransport`); no seed manifest uses
`backend.type: "rest"`, so there is no live path through the Gateway exercising it.

**Validated against:** real routing Sales→sales-domain / Finance→finance-domain never crossed,
including cross-container via real Docker Compose (network segmentation confirmed: none of the
domain servers or OPA publishes a host port).

### Downstream / outbound identity (EP-07)

**Responsibility:** the credential the Fabric presents to the backend is never the inbound token
of the MCP Client (`src/emcp_bus/downstream/identity.py`, `BackendCredentialProvider`). Two modes
declared per backend in `config/backends/*.yaml` (`BackendConfig.credential_mode`):
`service_account` (static credential read from an env var at call time — the default mode of the
seed backends) and `token_exchange` (RFC 8693 via Keycloak Standard Token Exchange,
`TokenExchangeClient` — two HTTP round-trips per new exchange, with a per-backend cache until
shortly before `expires_in`). See [`interfaces/downstream-identity.md`](interfaces/downstream-identity.md).

**Validated against:** real Keycloak 26.7.3 — the exchange's `audience` must be an actually
registered client id (a free-form string fails with "Audience not found"); requesting `audience`
without a `scope` that effectively adds that audience fails with "Requested audience not
available". The realm gained the `gateway-token-exchange` client and per-backend client scopes
with `oidc-audience-mapper`. 7 tests (4 unit with `httpx.MockTransport`, 3 e2e against real
Keycloak, including a full `tools/call` through the Gateway using a credential obtained via token
exchange).

### Auditing, correlation and observability (EP-08)

**Responsibility:** `audit/models.py` defines `EventEnvelope` with a 3-category taxonomy adopted
from the Agent Platform OCI reference (ADR-022): **IC** (Control Indicator/business journey,
e.g. `client_authenticated`, `tool_call_allowed`), **NOC** (operational/availability error, e.g.
`pdp_unavailable`), **GRL** (guardrail/governance, e.g. `tool_call_denied`,
`tools_list_filtered`, `bypass_attempt_detected`). Every event recursively sanitizes any key
whose name contains `token`/`secret`/`password`/`authorization`/`credential`, replacing the value
with `sha256:<hex>` — a secret value never reaches a sink. `audit/correlation.py` propagates
`decision_id`/`policy_decision_id`/`entitlement_version`/`policy_version`/`mcp_request_id` as
first-class fields on every event and as OTel span attributes (ADR-017). `audit/sink.py`
(`JSONLFileAuditSink`) writes to an append-only JSONL file. `common/otel.py` installs automatic
tracing (`OpenTelemetryMiddleware`) with no manual span code in the Gateway. See
[`interfaces/audit-events.md`](interfaces/audit-events.md).

**Validated against:** real `trace_id` correlation between distinct Docker containers (Gateway ↔
domain server) for a successful call. Local `otel-collector` + Jaeger stack (EP-08-T04,
`observability` profile): configuration validated (`docker compose config`), not exercised with
real OTLP traffic by an automated test — Langfuse (EP-13-T02) is the one that actually received
real OTLP traffic, validated manually (see the "Example agent" component below).

### Entitlement Manager (EP-04)

**Responsibility:** `entitlement/manager.py` (`EntitlementManager`) resolves the
`MaximumEntitlement` by combining the `ClientProfile` (validated YAML, `entitlement/models.py`)
with the PDP's entitlement decision, producing a versioned `ResolvedEntitlement`
(`entitlement_version`) with `allowed_tools`/`risk_ceiling`/`profile_name`.
`sync_profiles_to_pdp` pushes the validated profiles to OPA's data document at boot — a failure
here prevents the Gateway from coming up "healthy" (fail-closed, README.md §38). Revocation
invalidates the entitlement cache and re-evaluates starting from the next call.

**Validated against:** real OPA + real YAML; live policy revocation against a running Gateway
(`tests/adversarial/test_protocol_identity.py`).

### Approval workflow (EP-14)

**Responsibility:** `approval/service.py` (`ApprovalService`) gates `REQUIRE_APPROVAL`
decisions: `check_and_consume` (called by the Gateway on every attempt) only returns true for an
approval that has been granted, is not expired, and has not yet been consumed — single-use,
never "queue and release". An `ApprovalRequest` is bound to a SHA-256 hash of the exact triple
`(client_profile, tool, arguments)` (`compute_operation_hash`), not just the tool name: an
approval for one call never satisfies a different call with the same tool/profile.
`check_and_consume` is protected by a `threading.Lock` (a real concurrency finding, see
"Limitations" below). See [`interfaces/approval-workflow.md`](interfaces/approval-workflow.md).

**Validated against:** full e2e cycle for Sales and Finance (deny → approve externally → execute
→ replay denied); replay under real concurrency (`ThreadPoolExecutor`, 20 threads).

### Profile Intelligence (EP-09)

**Responsibility:** `profile_intelligence/models.py` defines `ProfileView` (pseudonymized
`subject_ref`, `profile_version`, `segments`, `attributes`, `reason_codes`, `expires_at`) as a
generic, replaceable contract — any `ProfileIntelligenceProvider` (the deterministic rule-based
stub in `rule_based_provider.py`, or a real clustering model in a production deployment) produces
the same contract. A `ProfileView` is never consulted by the PDP and can never grant a capability
outside the `MaximumEntitlement` — nothing here is connected to the authorization path.
`governance.py` implements governance guardrails: pseudonymization, lineage logging, a drift
monitor stub.

**Validated against:** determinism (same `subject_ref` + ISO window → same `profileVersion`).

### Offering Filter (EP-10)

**Responsibility:** `offering_filter/service.py` implements
`FilteredOfferings = ActiveCatalog ∩ MaximumEntitlement ∩ ConsentContext`. The order of the
intersection is deliberate: `allowed_tools` (MaximumEntitlement, already resolved by EP-04) is
the only term treated as security-relevant and is applied first; a `ConsentContext` (here, just
`allow_restricted_data` over `CapabilityManifest.data_classification`) can only reduce what has
already survived that intersection, never reintroduce a capability outside the entitlement.

**Validated against:** subset invariant proven with Hypothesis, 2000 generated cases
(`tests/unit/test_offering_filter_invariants.py`).

### Service Orchestrator (EP-11)

**Responsibility:** `orchestrator/graph.py` (`build_journey_graph`) is a real LangGraph
`StateGraph` with fixed nodes `resolve_profile → resolve_entitlement → filter_offerings →
decide_nba → approval_gate`, plus a dedicated re-entry for the recalculation loop after DENY
(`handle_denial_node`, which never calls the Fabric directly — it only recalculates the NBA over
the remaining offerings). `orchestrator/nba_model.py` defines `NBADecision`
(`decision_id`, `action`, `capability_version`, `subject_ref`, `channel`, `agent`,
`reason_codes`, `policy_context`, `expires_at`) and the `NBADecisionModel` protocol — swapping
the reference implementation (`decisioning.RuleBasedNBADecisionModel`) for a ranking/AI model
changes nothing in the input/output contract nor in what EP-03/04/05 authorize, because the model
only orders/selects among `DecisionContext.filtered_offerings`, already intersected by EP-10
before reaching here. `orchestrator/hitl_node.py` uses `langgraph.types.interrupt`/
`Command(resume=...)` to genuinely pause the graph on approval — with no timeout that becomes an
implicit ALLOW.

**Validated against:** real OPA + real LangGraph + real SQLite checkpointer, including proof that
resuming from a paused checkpoint does not reprocess already-executed nodes.

### Agent Runtime (EP-12)

**Responsibility:** `agent_runtime/dispatcher.py` (`AgentDispatcher`) consumes an `NBADecision`
and dispatches it against the real Gateway, authenticated as the MCP Client already registered
for the target agent — never generating or storing its own credential (`AgentTokenProvider`,
typically a real `client_credentials` against the same IdP as any other MCP Client).
`handoff_graph.py` (EP-12-T03, `execute_handoff`/`build_handoff_payload`) implements handoff
between agents with context minimization and entitlement resolution always independent per agent
— see "Limitations" below for the finding that neither Mode A nor Mode B (EP-13-T05/T06) ended up
using this primitive. `identity_resolver.py` (EP-12-T04, `IdentityResolver`) normalizes field
names between channels (`config/orchestrator/identity.yaml`) and is never consulted by the PDP —
checked mechanically via AST analysis in the corresponding unit test, the same discipline
`global_supervisor.py` uses to prove it never imports `emcp_bus.orchestrator`.

**Validated against:** real Gateway + Keycloak — `AgentDispatcher` reaching the real Sales
backend and being denied on cross-domain; two real agents obtaining independent
`client_credentials` tokens.

### Example agent (EP-13)

**Responsibility:** `agents/example_agent/agent.py` is a conversational agent with real
tool-calling against an OpenAI-compatible endpoint, whose catalog is restricted to the client's
own `tools/list`. `common/pii_redaction.py` redacts PII/secrets before any export.
`prompts/store.py` implements local prompt versioning (never overwrites a previous version) as
a testable core — synchronization with Langfuse's Prompt Management API is a thin adapter that
is documented, not implemented.

**Validated against:** a real LLM (`meta.llama-3.3-70b-instruct` via OCI Generative AI's
OpenAI-compatible endpoint), with tool-calling empirically confirmed; the prompt injection
scenario from README.md §29 (requesting a tool outside the entitlement) genuinely reproduced —
the call never executes, either because the model never saw the tool in its own catalog, or
because the Gateway/PDP denies it. Real self-hosted Langfuse (6 containers:
web/worker/postgres/clickhouse/redis/minio, `deploy/langfuse/docker-compose.override.yml`)
receiving real OTLP traffic from the agent — MCP spans and "generation" spans (with real
`gen_ai.request.model`/tokens) physically confirmed in ClickHouse's `events_core` table. This
validation is manual, not an automated e2e test (cost of bringing up 6 containers on every suite
run).

### Mode A — external Global Supervisor (EP-13-T05, ADR-024)

**Responsibility:** `agent_runtime/global_supervisor.py` (`GlobalSupervisor`) is the deliberately
simple stand-in (keyword-based routing) for an external orchestration platform that decides
which backend agent handles a conversation — it never is, nor claims to be, the security
boundary; it never imports `emcp_bus.orchestrator` (checked via AST). The real security property
does not live in this module: it lies in the fact that each `BackendAgent`
(`agents/example_agent/backends/{sales_agent,finance_agent}/`) resolves its own MCP
Client/entitlement completely independently — its own token, `tools/list`, and reauthorization —
and the `GlobalSupervisor` never reads, stores, or passes a credential from one backend to
another.

**Validated against:** real LLM + real Gateway (`tests/e2e/test_multi_agent_mode_a.py`, 2 tests):
handoff from `sales_agent` to `finance_agent` with a completely distinct token; a prompt
injection via handoff attempting `finance.payment.execute` is still denied by the real
Gateway/PDP.

### Mode B — Orchestrator as the sole NBA/NBO brain (EP-13-T06, `could`, ADR-024)

**Responsibility:** `agents/example_agent/mode_b_orchestrator_driven/orchestrator.py`
(`ModeBOrchestrator`) invokes the real EP-11-T02 journey `StateGraph` (unmodified) once per
relevant `client_id` for the same subject, combines the resulting `NBADecision`s (reference rule:
a pending Finance item always beats a discretionary Sales offer), and dispatches the winner via
the real `AgentDispatcher` — never creating its own authorization path. It deliberately does not
extend `JourneyState`/`build_journey_graph` to handle multiple `client_id`s natively; the
combination lives a layer above the graph (a design decision recorded in the module itself).

**Validated against:** real Keycloak + real OPA + real Sales/Finance
(`tests/e2e/test_real_keycloak.py::test_mode_b_orchestrator_combines_offerings_and_dispatches_through_the_real_chain`):
candidates from both domains genuinely combined, final decision from our Orchestrator, `ALLOW`
dispatch end-to-end.

## What was validated, by real dependency

| Real dependency | What it exercises | Where |
|---|---|---|
| OPA (subprocess) | `entitlement.rego`/`transaction.rego`, `PDPClient` | `tests/unit/policies/`, the whole e2e suite |
| Keycloak (Docker, 26.7.3) | client_credentials, real JWKS, RFC 8693 token exchange, Mode B | `tests/e2e/test_real_keycloak.py` |
| LangGraph 0.6 + SQLite checkpointer | journey graph, approval pause/resume | `tests/unit/test_orchestrator_graph.py`, M3 e2e |
| Real LLM (OpenAI-compatible) | example agent tool-calling, prompt injection | `tests/e2e/test_example_agent.py`, `test_multi_agent_mode_a.py` |
| Full Docker Compose | build+up+fail-closed+cross-container trace+network segmentation | `tests/e2e/test_security_acceptance.py`, documented manual validation |
| Self-hosted Langfuse (6 containers) | real OTLP export, generation spans | Manual validation (not automated) |

## Limitations and real architectural findings

- **`ttl_ms` of the `tools/list` cache hint (SEP-2549, EP-05-T03)**: correctly implemented in
  `gateway/cache.py`, but the field belongs to the 2026-07-28 protocol, which only exists in the
  `mcp` SDK's *stateless per-request* mode (no `initialize` handshake). This RI uses the classic
  session handshake everywhere (Gateway↔Client and Gateway↔backends), so `ttl_ms` never reaches
  the wire in this architecture — the SDK drops the field during serialization for protocol
  versions before 2026-07-28 (verified empirically). `cache_scope="private"` is always set, but
  since it does not depend on the wire-mode it is also not something an e2e test can verify in a
  discriminating way. The real security property (never leaking the catalog between clients) is
  guaranteed independently: the Gateway never caches the filtered catalog server-side.
- **Header/body consistency (EP-05-T08)**: implemented as its own gate
  (`gateway/canonical_request.py`) reusing the SDK's field constants, not as the SDK's native
  validation ladder (which only applies to the same 2026-07-28 *stateless per-request* mode
  above) — for the same reason, this RI does not reach it via the native path. Missing headers
  (a client that does not implement this SEP) are not an error.
- **REST adapter (EP-06-T04)**: implemented and tested standalone
  (`fabric/adapters/rest_adapter.py`); no example backend in this RI is REST (both are
  MCP-native), so live routing through the Gateway to a `type: "rest"` backend was never
  exercised end-to-end.
- **Handoff between agents (EP-12-T03, `execute_handoff`/`build_handoff_payload`)**: remains
  implemented and tested (`tests/unit/test_agent_runtime_handoff.py`), but neither Mode A
  (EP-13-T05) nor Mode B (EP-13-T06) ended up using this primitive. Mode A needs conversational
  routing (which backend responds to the next message), not dispatch of a specific `NBADecision`
  — `GlobalSupervisor` calls `run_turn()` directly on the backends. Mode B already combines
  `NBADecision`s from multiple clients in a single step and dispatches the winner via plain
  `AgentDispatcher.dispatch` — there is no "origin" agent handing control to another for
  `execute_handoff` to intercept. The primitive remains correct and reusable for a future
  handoff scenario *within* an Orchestrator-driven journey, but that specific usage form does not
  exist in this RI.
- **Request replay**: no nonce/anti-replay in this RI — a captured request with a still-valid
  token can be resent successfully. Mitigated by short-lived tokens
  (`credential_policy.short_lived` on every seed `ClientProfile`) and by complete auditing (every
  attempt, even an identical one, generates its own `decision_id`). See
  `tests/adversarial/test_protocol_identity.py`.
- **Rate limiting / bulk exfiltration**: no request rate limiting in the Gateway — N consecutive
  legitimate reads are all allowed. Mitigated only by after-the-fact detectability via auditing
  (every call generates a correlated event), never by real-time prevention.
- **Real race condition fixed in `ApprovalService`**: `check_and_consume` did a check-then-set in
  two non-atomic operations — under real thread concurrency, two attempts could both observe
  "granted" before either wrote "consumed" (double-spend of a single-use grant). Fixed with a
  dedicated `threading.Lock`, proven with `ThreadPoolExecutor` (20 threads) in
  `tests/adversarial/test_protocol_identity.py`.
- **Audit sink failure could become a real 500 error, fixed**: none of the 8
  `audit_sink.emit(...)` calls in the Gateway were protected — a sink failure (full disk,
  unavailable queue) could turn an already-`ALLOW`ed operation into a 500 error for the caller,
  violating the policy of never blocking low-risk operations. Fixed with the `_emit_audit` helper
  (`gateway/server.py`), which swallows any exception from the sink at all 8 emission points, for
  both ALLOW and DENY. A sink failure in production needs its own observability (see
  `Production-Recommendations.md`) — this behavior is correct by design, but silent.
- **`GlobalSupervisor` routing (Mode A)**: simple keyword-based, deliberately not the security
  boundary nor a claim of routing quality — just an honest stand-in for what a real external
  platform would do.
- **`ModeBOrchestrator` combination rule (Mode B)**: "Finance always beats Sales" is a simple
  reference rule, not a claim of optimality — the same posture as `RuleBasedNBADecisionModel`
  (EP-11-T03).
- **Observability stack (EP-08-T04)**: configuration validated (`docker compose config`), not
  exercised with real traffic by an automated test (the full startup with the `observability`
  profile was validated manually).
