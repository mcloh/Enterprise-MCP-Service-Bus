# Interface: Agent Runtime dispatch (`AgentDispatcher`, `GlobalSupervisor`, `ModeBOrchestrator`)

Agent Runtime dispatch contracts, for whoever is going to build a new agent backend or a
new multi-agent integration following `docs/adr/ADR-024-posicionamento-multiagente.md`.
Implementation: [`src/emcp_bus/agent_runtime/dispatcher.py`](../../src/emcp_bus/agent_runtime/dispatcher.py),
[`agent_runtime/global_supervisor.py`](../../src/emcp_bus/agent_runtime/global_supervisor.py),
[`agent_runtime/handoff_graph.py`](../../src/emcp_bus/agent_runtime/handoff_graph.py),
[`agent_runtime/identity_resolver.py`](../../src/emcp_bus/agent_runtime/identity_resolver.py),
[`agents/example_agent/mode_b_orchestrator_driven/orchestrator.py`](../../agents/example_agent/mode_b_orchestrator_driven/orchestrator.py).
See [`AS-BUILT.md`](../AS-BUILT.md) (Agent Runtime, Mode A, Mode B sections).

## `AgentDispatcher` — the primitive common to both modes

```python
result = await dispatcher.dispatch(nba: NBADecision, arguments: dict[str, Any]) -> DispatchResult
```

`nba` (see `orchestrator/nba_model.py`) carries `agent` — the name of the agent whose credential
must be used. `AgentDispatcher` never generates or holds its own credential: it obtains the
token via `AgentTokenProvider.token_for(nba.agent)`, typically a real `client_credentials`
against the same IdP as any other MCP Client (`OIDCAgentTokenProvider`), and calls
`nba.action` through the real Gateway — the same reauthorization as any other `tools/call`
(EP-05/EP-03).

```python
DispatchResult(decision_id="...", action="finance.payment.execute", status="allowed" | "denied",
                structured_content={...} | None, error_text: str | None)
```

A denial from the Gateway/PDP becomes `status="denied"` with `error_text` — `dispatch()` never
reinterprets or re-executes around a denial; NBA recalculation after a DENY is the
responsibility of a layer above (`orchestrator/fallback.handle_denial`).

## Mode A — `GlobalSupervisor` (governance-only, ADR-024)

For when an **external orchestration platform** decides which agent handles the conversation;
the Service Orchestrator (EP-11) does not participate.

```python
supervisor = GlobalSupervisor(backends={"sales_agent": ..., "finance_agent": ...})
result = await supervisor.route_and_run(
    message, current_backend="sales_agent", router=keyword_router
)
# RoutingResult(backend_name, handed_off: bool, turn_result)
```

- `router: RouterFn` — `Callable[[str], str | None]`, chooses a backend name from the
  message content, or `None` to stay on the current backend. `keyword_router` is the
  reference implementation (keyword-based, deliberately simple) — **it is not the security
  boundary**; a wrong routing decision, or an attempt to manipulate routing via prompt, is
  always recaptured by the real Gateway/PDP at the backend that actually responds.
- `BackendAgent` — the only contract a backend needs to satisfy:
  `async def run_turn(message: str) -> object`. Each `BackendAgent` resolves its **own** MCP
  Client/entitlement completely independently (token, `tools/list`, reauthorization) —
  `GlobalSupervisor` never reads, holds, or forwards one backend's credential to another.
- `GlobalSupervisor` never imports `emcp_bus.orchestrator` (verified via AST analysis in the
  corresponding unit test) — mechanical proof that Mode A does not use its own NBA.

**To integrate a new agent backend in Mode A:** implement `BackendAgent.run_turn`,
register its own `ClientRegistration`/`ClientProfile` (see
[`identity-oidc.md`](identity-oidc.md)) like any other MCP Client, and add it to the
`GlobalSupervisor`'s `backends` dict.

## Mode B — `ModeBOrchestrator` (full replacement, ADR-024)

For when **our own Service Orchestrator** is the sole NBA/NBO brain — no external Global
Supervisor is consulted.

```python
orchestrator = ModeBOrchestrator(
    graph=journey_graph,
    dispatcher=dispatcher,
    client_ids=["sales-read-agent", "finance-payments-agent"],
)
decision = orchestrator.decide(subject_id="subject:7f31c2", channel="chat")
# ModeBDecision(chosen: NBADecision, considered: list[NBADecision]) | None
result = await orchestrator.decide_and_dispatch(subject_id=..., channel=..., arguments={...})
```

`graph` is the real journey `StateGraph` from EP-11-T02 (`orchestrator/graph.py`,
`build_journey_graph`), invoked **without modification**, once per `client_id` in `client_ids`,
for the same `subject_id` — each invocation resolves that client's profile/entitlement/offerings
independently. `_combine` is the reference rule that decides among the resulting
`NBADecision`s (a Finance pending item always beats a Sales offer) — it is not a claim of
optimality, just the same stance as `RuleBasedNBADecisionModel` (EP-11-T03). A `client_id`
whose journey ends with no surviving offer (`nba is None`) simply does not contribute to
`considered` — never an error.

**To extend the combination rule:** replace `ModeBOrchestrator._combine` with a real
cross-domain ranking model — the input/output contract (`list[NBADecision]` →
`NBADecision | None`) does not change.

## `execute_handoff`/`build_handoff_payload` (EP-12-T03) — implemented, not used by Modes A/B

Cross-process handoff primitive with two structurally separated concerns: context minimization
(`build_handoff_payload`, only `carry_keys` survives) and always-independent entitlement
resolution (`execute_handoff` dispatches via the same `AgentDispatcher`, which resolves the
destination agent's credential from scratch). **Real finding**: neither Mode A (pure
conversational routing, with no originating `NBADecision`) nor Mode B (already combines
decisions and dispatches the winner directly) uses this primitive — see `AS-BUILT.md` for
details. It remains correct and reusable for a handoff *within* an Orchestrator-driven journey
that needs to hand control to another agent mid-execution.

## `IdentityResolver` (EP-12-T04) — never an authorization input

```python
resolver = IdentityResolver(IdentityResolverConfig(aliases={"msisdn": "customer_key"}))
resolver.resolve(
    {"msisdn": "5511...", "amount": 100}
)  # -> {"customer_key": "5511...", "amount": 100}
```

Normalizes field names across channels for the Fabric/MCP parameter mapping — **never**
consulted by the PDP (verified via AST in the corresponding unit test, the same discipline as
`GlobalSupervisor`). A field resolved from caller-supplied data should never influence an
authorization decision (the lesson of `docs/adr/ADR-023-autorizacao-nunca-vem-do-payload.md`).

## Errors

| Situation | Exception |
|---|---|
| `nba.agent` without a configured `AgentTokenProvider` | `UnknownAgentError` |
| IdP rejects obtaining the agent's token | `AgentCredentialError` |
| `current_backend` not registered in `GlobalSupervisor` | `UnknownBackendError` |
| Handoff's `nba.agent` diverges from `payload.target_agent` | `ValueError` (`execute_handoff`) |
| Channel without a registered `ChannelAdapter` | `UnsupportedChannelError` |
