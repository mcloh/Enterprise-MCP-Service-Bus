# ADR-017: End-to-end correlation via versioned IDs

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, when applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

End-to-end correlation.

## Decision

`profileVersion`+`entitlementVersion`+`decisionId`+`policyDecisionId`+`mcpRequestId` propagated via OTel/trace context across all components.

## Alternatives Considered

Correlation only via free-text logs with no standard.

## Consequences

EP-08-T03 formalizes the fields; basis for EP-15 (auditability).
