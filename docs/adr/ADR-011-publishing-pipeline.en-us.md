# ADR-011: Mandatory pipeline for capability publication

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, where applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Capability publication cycle.

## Decision

Mandatory pipeline with schema/risk/policy/health gates before entering the Registry — no manual registration in production.

## Alternatives Considered

Direct registration via administrative API without a pipeline.

## Consequences

EP-02-T02 implements the gate; no capability is "born" already published.
