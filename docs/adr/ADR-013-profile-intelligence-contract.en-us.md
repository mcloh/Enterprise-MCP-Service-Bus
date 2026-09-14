# ADR-013: Pluggable Profile Intelligence contract

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, when applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Profile Intelligence contract.

## Decision

Generic, replaceable interface (versioned `ProfileView`, with `reasonCodes`), pluggable implementation.

## Alternatives Considered

Coupling to a specific vendor/taxonomy for segmentation.

## Consequences

EP-09 defines only the contract + reference stub (see P7).
