# ADR-003: Independent reauthorization on tools/call

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, where applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Is filtered `tools/list` sufficient?

## Decision

No — `tools/call` must be reauthorized independently of discovery.

## Alternatives Considered

Relying only on filtered discovery.

## Consequences

EP-05 implements two enforcement points, not one.
