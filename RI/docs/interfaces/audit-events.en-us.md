# Interface: audit events

Taxonomy and schema of audit events, for whoever is going to build a consumer (SIEM,
dashboard). Implementation: [`src/emcp_bus/audit/models.py`](../../src/emcp_bus/audit/models.py),
[`audit/events.py`](../../src/emcp_bus/audit/events.py),
[`audit/sink.py`](../../src/emcp_bus/audit/sink.py),
[`audit/correlation.py`](../../src/emcp_bus/audit/correlation.py). See
[`AS-BUILT.md`](../AS-BUILT.md#auditoria-correlação-e-observabilidade-ep-08).

## Sink

`JSONLFileAuditSink` writes one JSON object per line, append-only, to `EMCP_AUDIT_LOG_PATH`
(default `/tmp/emcp-audit.jsonl`). A production consumer would replace this with a durable
sink (Postgres, queue) — see `../Production-Recommendations.md`; the `EventEnvelope` schema
below would not change.

## `EventEnvelope`

```json
{
  "event_id": "3f9a...",
  "event_type": "tool_call_denied",
  "category": "grl",
  "timestamp": "2026-09-14T12:00:00Z",
  "client_id": "sales-read-agent",
  "profile_name": "Sales.Read",
  "tool": "finance.payment.execute",
  "reason_code": "NOT_IN_ENTITLEMENT",
  "decision_id": "...",
  "policy_decision_id": "...",
  "entitlement_version": "...",
  "policy_version": "a1b2c3d4e5f6",
  "mcp_request_id": "...",
  "trace_id": "...",
  "payload": {}
}
```

Correlation fields (`decision_id`, `policy_decision_id`, `entitlement_version`,
`policy_version`, `mcp_request_id`, `trace_id`) are first-class, never hidden inside
`payload` — a consumer can join across events and between events and OTel spans without
parsing `payload`.

## Taxonomy (`category`)

Adopted from the Agent Platform OCI reference (`docs/adr/ADR-022-referencia-hoshikawa-agent-platform-oci.md`)
rather than a taxonomy of its own:

| Category | Meaning | `event_type` examples |
|---|---|---|
| `ic` | Control Indicator / business journey — the call progressed normally | `client_authenticated`, `tool_call_allowed`, `agent_turn_completed`, `nba_recalculated` |
| `noc` | Operational/error — an availability failure, not a policy decision | `pdp_unavailable`, `backend_credential_unavailable` |
| `grl` | Guardrail/governance — an entitlement/policy boundary was applied or tested | `tool_call_denied`, `tools_list_filtered`, `tool_call_require_approval`, `approval_granted`, `bypass_attempt_detected`, `journey_ended_after_denial` |

Each `event_type` fixes its own category in the factory that creates it (`audit/events.py`) —
never a call-site decision.

## Sanitization (never optional)

Any `payload` key, at any nesting level, whose (lowercased) name contains `token`, `secret`,
`password`, `authorization`, or `credential` has its value replaced with `sha256:<hex>` — a
real secret value never reaches a sink. This runs in
`EventEnvelope.model_post_init`, so it applies to every construction path, including
deserialization from an existing sink.

## Available `event_type` values

| `event_type` | Category | Emitted when |
|---|---|---|
| `client_authenticated` | ic | A `tools/list` with a valid token resolved a known client. |
| `tools_list_filtered` | grl | A `tools/list` returned (includes `allowed`/`total` counts). |
| `tool_call_allowed` | ic | A `tools/call` was executed successfully. |
| `tool_call_denied` | grl | Any `tools/call` denial (with `reason_code`). |
| `tool_call_require_approval` | grl | An attempt generated/encountered a pending `ApprovalRequest`. |
| `approval_granted` | grl | An approver granted an approval (`ApprovalService.grant`). |
| `pdp_unavailable` | noc | OPA did not respond to a `tools/call` query. |
| `backend_credential_unavailable` | noc | The outbound credential for a backend could not be obtained. |
| `bypass_attempt_detected` | grl | A request reached a domain server without the Gateway's outbound credential (EP-05-T07). |
| `nba_recalculated` | ic | The Orchestrator recalculated the NBA after a DENY from the Gateway (never re-executes the denied action). |
| `agent_turn_completed` | ic | An example agent's turn ended — includes `tools_attempted`/`tools_denied` (a tool denied here is the guardrail working, not a bug). |
| `journey_ended_after_denial` | grl | No offering survived a DENY — the journey ends, with no direct attempt against the Fabric. |

## Building a consumer

A SIEM/dashboard should: read the JSONL (or the equivalent production sink), index by
`decision_id`/`mcp_request_id`/`trace_id` for end-to-end reconstruction, and treat any
`category: "grl"` event as a guardrail signal (not necessarily an incident — a correct denial
is the system working), and `category: "noc"` as an availability signal.
