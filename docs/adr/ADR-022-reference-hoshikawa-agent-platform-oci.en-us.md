# ADR-022: Operational reference: Agent Platform OCI (Hoshikawa)

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, when applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Concrete Python/LangGraph/Langfuse implementation reference (closes G2 — **decision confirmed by the author on 2026-09-11**).

## Decision

Adopt as an operational reference the "Agent Platform OCI" by Christiano Hoshikawa (`github.com/hoshikawa2/agent_platform_oci`): a StateGraph with a router/supervisor per backend + an upper routing layer across backends (our EP-11/EP-12); pluggable checkpointing (memory/sqlite/mongodb/production — we adopt SQLite in dev, see ADR-021); **IC/NOC/GRL** observability taxonomy via Langfuse (business/operational/guardrail event), with hybrid instrumentation (automatic span per node + manual fail-open emission); `identity.yaml`/`BusinessContext` to normalize business identity across channels; FastMCP as the standard MCP server. Full analysis recorded in `docs/research/hoshikawa-agent-platform-oci.md`.

## Alternatives Considered

Continuing with the generic pattern from section 6 of the superprompt without a concrete third-party reference (slower, more ad hoc decisions); adopting a market agent framework (CrewAI, AutoGen) instead of plain LangGraph.

## Consequences

Changes the form (not the security) of EP-08, EP-11, EP-12, EP-13 — see ADR-023 for the explicit boundary of what is NOT adopted.
