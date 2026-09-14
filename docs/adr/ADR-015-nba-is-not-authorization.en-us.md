# ADR-015: NBA as an orchestration decision, not an authorization decision

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, when applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Is NBA an authorization decision?

## Decision

No — it is orchestration intent; Gateway/PDP reauthorize every execution.

## Alternatives Considered

Orchestrator dispatching directly to the backend without going through the Gateway.

## Consequences

EP-11-T04 implements the DENY/recalculation branch of §10.1.
