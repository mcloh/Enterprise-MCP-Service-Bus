# Assumptions — assumptions and decisions of this RI

This document explains **what was assumed** when building the Reference Implementation (RI) and
**why**, distinguishing that from what is an architectural guarantee of the [reference
architecture](../README.md). It is a synthesis — not a copy — of the decision history recorded
in [`docs/adr/`](../../docs/adr/); each ADR remains the canonical record of an individual
decision, this document groups the "why" by theme for whoever is evaluating the RI.

Target audience: whoever is going to **evaluate or adapt** this RI for a real scenario and needs
to know what was assumed versus what is a guarantee of the architecture.

## General scope

**We assume that an RI proves security properties, it is not a production-ready product.**
Every decision below prioritizes verifiably demonstrating the architecture's invariants
(`MaximumEntitlement` as a ceiling, fail-closed, never elevate privilege by context) over
operational completeness (HA, scale, UI). Where the two collided, we chose the simplest RI
that still proves the real property against a real dependency — never a mock of the very
point being tested.

## Identity and PDP: closed technologies, not hypotheses to revisit

**We assume Keycloak as Identity Provider and OPA/Rego as PDP because they are OSS (Apache-2.0)
and adherent to open standards** (OAuth 2.1/OIDC, Rego), not out of arbitrary preference. This
resolves two gaps that the reference architecture left open (`README.md` §48, questions
1 and 3) with a definitive technical decision, not an assumption — they were never revisited
throughout the implementation. See `docs/adr/ADR-019-identity-extension.md`,
`docs/adr/ADR-025-engine-do-pdp.md`.

**We rejected** a custom PDP engine in Python (more control, but reinvents policy evaluation
with no real gain) and Cedar (also would be adequate, but OPA has greater adherence to "open
standards" and a more mature Rego community for the scope of this RI).

## Operational reference Python/LangGraph/Langfuse (Agent Platform OCI)

**We assume as the concrete operational reference the Agent Platform OCI project by Christiano
Hoshikawa** (`docs/research/hoshikawa-agent-platform-oci.md`) for the
LangGraph/Langfuse/FastMCP layer, instead of inventing a generic pattern from scratch — faster,
fewer ad hoc decisions, and a real point of comparison for what "multiagent orchestration"
means in practice. **We reuse** from that reference: `StateGraph` with a router/supervisor per
backend, pluggable checkpointing, the IC/NOC/GRL observability taxonomy with hybrid
instrumentation (automatic spans + fail-open manual events), `identity.yaml`/`BusinessContext`
to normalize identity across channels, FastMCP as the MCP server standard.

**We explicitly rejected** a single element of that reference: its tool authorization model via
a static allowlist evaluated over an `agent_id` that arrives as **data from the conversation's
input payload**, not as a claim from an independently verified authenticated identity — the
reference project itself admits that this does not replace real authentication/authorization.
That is exactly the anti-pattern form that the architecture forbids
(`ADR-001`/`ADR-002`/`ADR-003`). The RI reuses the proxy *shape* of that Gateway
(invocation/result contracts, per-tool cache, catalog) only at the Fabric/conversational UX
layer — the ALLOW/DENY decision remains 100% in our PEP/PDP, never in a self-declared
`agent_id`. See `docs/adr/ADR-022-referencia-hoshikawa-agent-platform-oci.md`,
`docs/adr/ADR-023-autorizacao-nunca-vem-do-payload.md`. This finding also motivated a dedicated
adversarial scenario (`tests/adversarial/test_payload_identity_spoofing.py`).

## Downstream identity

**We assume** token exchange (RFC 8693) when the backend supports OIDC, with a fallback to a
service account isolated per adapter when it does not — because always reusing the client's
token (the simpler alternative) is exactly the "blind token passthrough" that the architecture
forbids (inbound ≠ outbound identity). See `docs/adr/ADR-020-downstream-identity.md`.

## Client profile granularity

**We assume** domain + risk tier (e.g.: `Sales.Read`=R1, `Sales.Write`=R2,
`Finance.Payments`=R3) as the client profile granularity, instead of a single "enterprise
admin" client or domain-only without tier — because only this granularity allows proving
blast-radius segmentation between risk tiers within the same domain (README.md §7, §17,
§31). See `docs/adr/ADR-008-segmentacao-por-dominio-e-risco.md`.

## Profile Intelligence: deterministic stub, not "real AI"

**We assume** that "generic and replaceable" Profile Intelligence (README.md §6.10) does not
prescribe an algorithm, taxonomy, or real data source — because the reference architecture does
not define any of these, deliberately. The RI implements a stub based on deterministic rules
over synthetic attributes, behind a replaceable interface (`ProfileIntelligenceProvider`),
which fulfills the **contract**, not the "intelligence" itself. A production fork replaces only
the implementation, never the contract (`ProfileView`) nor the point where it connects (never
to the PDP).

## Domain scope: two, not full federation

**We assume** two example domains (Sales, Finance) as sufficient to prove
segmentation/blast-radius between distinct domains, without needing full multi-domain
federation. Federation is deliberately out of scope for this RI — it is addressed in the
reference architecture's roadmap as a later phase (§47, Phase 5), not an implementation gap.

## Environment: 100% local via Docker Compose

**We assume** that an RI runs entirely locally via `docker compose`, with environment
separation demonstrated by a configuration overlay (`config/env/{dev,ci}.yaml`) instead of
real cloud/hybrid infrastructure — proving the architecture does not require multi-cloud, and
simulating multi-cloud without real multi-cloud would prove nothing beyond the simulation
itself.

## Substitutions to enable testing without heavy infrastructure

- **Local JWKS server as a stand-in for Keycloak** in most of the e2e suite — valid because
  what is being tested there is the *token validation logic* (signature, `exp`, `iss`,
  `aud`, extraction of `azp`), which is identical against any valid RS256 JWKS. Real protocol
  integration with Keycloak (`client_credentials` grant, real claims issued by a real IdP,
  RFC 8693) is covered separately, against a real Keycloak 26.7.3 via Docker
  (`tests/e2e/test_real_keycloak.py`) — it is not the same test, it is a complementary test
  that covers exactly what the stand-in cannot.
- **SQLite instead of Postgres** for the Registry and for the LangGraph checkpointer — valid to
  prove the contract/behavior (schema, lifecycle, graph pause/resume); it is not a claim
  about performance or concurrency under production load (see
  `Production-Recommendations.md`).
- **`policy_version` as a file hash, not a real OPA bundle revision** — a SHA-256 of the
  content of the `.rego` files on disk is enough to prove that `policy_version` flows end to
  end through every decision and audit event; it is not a claim about policy distribution in a
  production cluster.

## Items deliberately out of scope

- **REST adapter without a live path through the Gateway** (EP-06-T04): implemented and tested
  standalone; none of this RI's example backends is REST, so there is no live path through the
  Gateway exercising it. It would only become relevant if a future domain needed a
  non-MCP-native backend.
- **LangGraph deliberately absent from the Gateway/Fabric** — used only where there is real
  state, cycles, or checkpointing (Service Orchestrator, EP-11; Agent Runtime handoff, EP-12-T03).
  No simple routing (Gateway EP-05, Fabric EP-06, Offering Filter EP-10) uses LangGraph —
  using a stateful graph for stateless routing would be over-engineering, not a neutral choice.
  See `docs/adr/ADR-021-escopo-langgraph-langfuse.md`.
- **Rate limiting and anti-replay**: real, conscious gaps, not oversights — documented and
  covered by a dedicated adversarial test (`tests/adversarial/test_protocol_identity.py`), never
  silently ignored. See `Production-Recommendations.md` for what a real deployment needs to
  add.
