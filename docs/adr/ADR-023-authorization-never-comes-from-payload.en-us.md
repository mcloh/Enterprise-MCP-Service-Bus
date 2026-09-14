# ADR-023: Tool authorization never comes from a field declared in the payload

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, when applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Tool authorization NEVER comes from a field declared in the payload/conversation (a critical finding from the Hoshikawa analysis, reinforcing ADR-001/002/003).

## Decision

The Agent Platform OCI's MCP Gateway authorizes tools via a static allowlist (`tools.yaml`/`authorization.agents.<agent_id>.allowed_tools`) evaluated over `agent_id`, a field that arrives as **data from the conversation's input payload**, not as a claim from an independently verified authenticated identity — their own SPEC-004 admits that this does not replace real authentication/authorization. Our RI reuses the proxy *form* of this MCP Gateway (`ToolInvocation`/`ToolResult` contracts, idempotent per-tool cache, `/v1/tools` catalog) **exclusively at the Fabric layer (EP-06)/conversational UX**, but the ALLOW/DENY decision remains 100% in our PEP (EP-05) consulting the PDP (EP-03) with the authenticated identity of the MCP Client (EP-01) — never with a self-declared `agent_id`/`tenant_id` in the payload.

## Alternatives Considered

Also reusing their `authorization` block as an implementation shortcut.

## Consequences

EP-15-T03 gains an explicit adversarial "payload-declared agent_id spoofing" scenario (a variation of Test 4, §45) to prove that this specific vector is closed in our RI.
