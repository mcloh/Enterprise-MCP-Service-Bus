# ADR-004: Agentic context never elevates privilege

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, where applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Can agentic context elevate privilege?

## Decision

Never — context can only subtract (`Context may subtract, must never add`).

## Alternatives Considered

Allowing elevation based on the model's "confidence."

## Consequences

EP-15 tests (Test 3/4) validate the invariant.
