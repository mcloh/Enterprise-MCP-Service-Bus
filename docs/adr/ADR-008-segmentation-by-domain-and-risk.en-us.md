# ADR-008: Client segmentation by domain and risk tier

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, where applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

How to segment clients.

## Decision

By domain + risk tier (R0–R4), not a single global client.

## Alternatives Considered

A single "enterprise admin" client.

## Consequences

Defines P6 (granularity) and EP-04.
