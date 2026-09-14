# Interface: capability manifest and Registry lifecycle

Capability manifest schema and the publishing pipeline, for whoever is going to publish a new
capability to the Global Capability Registry. Implementation:
[`src/emcp_bus/registry/models.py`](../../src/emcp_bus/registry/models.py),
[`registry/pipeline.py`](../../src/emcp_bus/registry/pipeline.py),
[`registry/lifecycle.py`](../../src/emcp_bus/registry/lifecycle.py),
[`registry/store.py`](../../src/emcp_bus/registry/store.py). See
[`AS-BUILT.md`](../AS-BUILT.md#global-capability-registry-ep-02).

## Manifest schema (`CapabilityManifest`)

```yaml
# config/capabilities/finance/payment-execute.yaml
name: finance.payment.execute      # <domain>.<capability>, validated (domain must prefix name)
version: 1.0.0                     # SemVer
domain: finance
owner: finance-platform
risk_tier: R3                      # R0-R4
side_effects: true
idempotent: false
data_classification: [confidential, restricted]   # public | internal | confidential | restricted
entitlements: [Finance.Payments]   # ClientProfile names that may see/call this capability
backend:
  type: mcp                        # mcp | rest | grpc (only "mcp" has live dispatch in this RI)
  service: finance-domain          # id resolved by config/backends/<service>.yaml
approval:
  required: true                   # required if risk_tier is in {R3, R4} — pipeline gate
```

(real example: `config/capabilities/finance/payment-execute.yaml`)

Fields with defaults: `observability.audit_level` (`"full"`), `lifecycle.status`
(`"nominate"` — a new manifest never declares itself `active` directly).

## Lifecycle (`LifecycleStatus`)

```
NOMINATE → REVIEW → REGISTER → ACTIVE ⇄ ACTIVE → DEPRECATED → RETIRED
              ↑________________|
           (rejected review goes back to NOMINATE)
```

Only an `ACTIVE` capability is resolvable by the Fabric (`CapabilityRouter`) — any other status
is a matter exclusively for the control plane. Nothing reaches `ACTIVE` without passing through
`REVIEW` (`registry/lifecycle.py:validate_transition`, mechanically verified).

## Publishing pipeline

```python
pipeline = PublishingPipeline(store)
registered = pipeline.submit(manifest)  # runs the gates -> NOMINATE -> REVIEW -> REGISTER
pipeline.publish(registered.name)  # REGISTER -> ACTIVE
```

`submit()` runs business gates before any state transition (schema/naming is already the
responsibility of `CapabilityManifest` itself at construction time):

| Gate | Rule |
|---|---|
| Owner | `owner` cannot be empty. |
| Backend | `backend.service` cannot be empty. |
| Risk-based approval | `risk_tier` in `{R3, R4}` requires `approval.required: true`. |

Any failed gate raises `PublishingRejectedError(reasons)` — nothing enters the Registry
partially (fail-closed, no ad hoc manual registration).

## How the Fabric resolves a capability

`CapabilityRouter.route(tool)` looks up `tool`'s `ACTIVE` manifest, resolves
`backend.service` to a URL+credential via `BackendCredentialProvider` (see
[`downstream-identity.md`](downstream-identity.md)), and returns a `BackendRoute`. Without a
matching `ACTIVE` manifest, or an unresolvable backend: `UnroutableCapabilityError` — the Gateway
treats this as `UNROUTABLE_CAPABILITY` (DENY).

## Errors

| Situation | Exception |
|---|---|
| `name` without a `.` (not `<domain>.<capability>`) | `pydantic.ValidationError` at manifest construction. |
| `domain` is not the prefix of `name` | `pydantic.ValidationError` at manifest construction. |
| Business gate failed in `submit()` | `PublishingRejectedError` |
| Invalid lifecycle transition (e.g. `NOMINATE` → `ACTIVE` directly) | `InvalidLifecycleTransitionError` |
| `tool` without an `ACTIVE` manifest, or nonexistent backend | `UnroutableCapabilityError` |

## Not implemented in this RI

An administrative HTTP endpoint to publish/revoke via API (today `PublishingPipeline` and the
lifecycle transitions are direct Python calls, exercised in tests, not exposed over the
network) — see `../Production-Recommendations.md`. A `backend.service` health check as a
publishing gate also does not exist (it would be a disguised `TODO` without a real registry of
backend health endpoints in this RI).
