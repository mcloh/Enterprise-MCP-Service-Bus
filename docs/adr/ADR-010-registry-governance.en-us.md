# ADR-010: Governance of the Global Capability Registry

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, where applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Governance of the Global Capability Registry (title and number inherited from §49 of the README — "Global Capability Registry Governance").

## Decision

The Registry is a control-plane asset (§6.6) with its own authority and lifecycle, separate from the catalog view delivered to each client. In the RI: dedicated storage and read API (EP-02-T03), consumed by Gateway/Fabric/Offering Filter but never edited by them; formal lifecycle nominate→review→register→publish→observe→(change|deprecate→retire) (§23) implemented as a state machine (EP-02-T04); every change goes through the publishing pipeline (EP-02-T02) — no direct manual registration in production (RF-11). The Registry's organizational owner (who approves schema/policy changes to the control plane itself) remains a corporate governance decision outside the technical scope of the RI (§48, question 4, still open).

## Alternatives Considered

Leaving the Registry as a table editable ad hoc by any service; merging the control view (Registry) with the execution view (catalog filtered per client), which would violate the control plane/data plane separation of §24.

## Consequences

The entire EP-02; reinforces that EP-05 (Gateway) and EP-10 (Offering Filter) only read the Registry, never write to it.
