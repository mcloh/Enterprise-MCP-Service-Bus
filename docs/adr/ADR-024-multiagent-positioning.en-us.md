# ADR-024: E-MCP-BUS positioning relative to external multi-agent platforms

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, when applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

E-MCP-BUS positioning relative to external multi-agent orchestration platforms, such as Agent Platform OCI (**decision confirmed and expanded by the author on 2026-09-11** — resolves G11).

## Decision

E-MCP-BUS **does not compete** with orchestration platforms such as Agent Platform OCI — but it also **is not limited to coexisting under them**. Explicit design principle: **modularity + compatibility = choice**. Our Service Orchestrator (EP-11) is not a thin pass-through: it computes NBA **and NBO** (Next Best Action/Next Best Offer) with its own decision model (rules + guardrails +, optionally, a ranking/recommendation AI model — see EP-11-T03) over the universe of `FilteredOfferings` that the MCP Fabric exposes (services, offers, actions, campaigns — not just technical "tools"). This enables **two equally valid integration modes, chosen by the adopter according to the desired topology**: **(A) Governance-only** — an external orchestration platform (e.g., Agent Platform OCI, with its own Global Supervisor and StateGraph deciding NBA) connects to E-MCP-BUS solely for governed access to the Fabric; our Service Orchestrator does not participate, or participates only as a source of `FilteredOfferings` (as already described in the rest of this ADR and in EP-13-T05). **(B) Full replacement** — our own Service Orchestrator (EP-11) fully takes on the role of the decision "brain" (NBA/NBO), dispensing with the external platform's decision-making Global Supervisor/StateGraph; the Agent Runtime (EP-12) and the external platform's channel adapters (e.g., Hoshikawa's agent backends) become mere executors of the dispatch our Orchestrator produces. In either mode, the security core (PEP/PDP, EP-05/EP-03) never changes place — only who computes the NBA/NBO changes. In both modes, each domain backend/agent remains registered as a **distinct MCP Client** (EP-01), bound to its own client profile/entitlement per domain+risk tier (EP-04, P6), and any consuming platform's internal "MCP Gateway" (ADR-023) is always superseded by our Gateway/PEP as the single point of authorization. This is the "Enterprise elevation": centrally governed catalog/entitlement/audit, with the NBA/NBO decision able to come from inside (mode B) or outside (mode A) the bus, by the adopter's modular choice.

## Alternatives Considered

Forcing a single integration mode (e.g., only "governance-only"), which would underuse the Service Orchestrator and always require an external decision platform; treating Agent Platform OCI as a substitute for E-MCP-BUS (incorrect — it does not solve entitlement); reimplementing from scratch the orchestration engineering already validated in ADR-022 even when mode B is chosen (the StateGraph/checkpointing/handoff form remains reusable within our EP-11/EP-12).

## Consequences

Reshapes the goal of EP-11 (Service Orchestrator explicitly described as computing NBA **and NBO** over Fabric services/offers/actions, with a pluggable decision model) and of EP-13 (demonstrates the two modes — see EP-13-T05 for mode A and EP-13-T06, new, for mode B). Reinforces that EP-06/EP-05 treat any consuming platform's "MCP Gateway" as untrusted for authorization, in both modes.
