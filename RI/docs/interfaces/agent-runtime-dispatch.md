# Interface: Agent Runtime dispatch (`AgentDispatcher`, `GlobalSupervisor`, `ModeBOrchestrator`)

Contratos de despacho do Agent Runtime, para quem vai construir um novo backend de agente ou uma
nova integração multiagente seguindo o `docs/adr/ADR-024-posicionamento-multiagente.md`.
Implementação: [`src/emcp_bus/agent_runtime/dispatcher.py`](../../src/emcp_bus/agent_runtime/dispatcher.py),
[`agent_runtime/global_supervisor.py`](../../src/emcp_bus/agent_runtime/global_supervisor.py),
[`agent_runtime/handoff_graph.py`](../../src/emcp_bus/agent_runtime/handoff_graph.py),
[`agent_runtime/identity_resolver.py`](../../src/emcp_bus/agent_runtime/identity_resolver.py),
[`agents/example_agent/mode_b_orchestrator_driven/orchestrator.py`](../../agents/example_agent/mode_b_orchestrator_driven/orchestrator.py).
Ver [`AS-BUILT.md`](../AS-BUILT.md) (seções Agent Runtime, Modo A, Modo B).

## `AgentDispatcher` — o primitivo comum aos dois modos

```python
result = await dispatcher.dispatch(nba: NBADecision, arguments: dict[str, Any]) -> DispatchResult
```

`nba` (ver `orchestrator/nba_model.py`) carrega `agent` — o nome do agente cuja credencial deve
ser usada. `AgentDispatcher` nunca gera ou guarda credencial própria: obtém o token via
`AgentTokenProvider.token_for(nba.agent)`, tipicamente um `client_credentials` real contra o
mesmo IdP de qualquer outro MCP Client (`OIDCAgentTokenProvider`), e chama `nba.action` através
do Gateway real — a mesma reautorização de qualquer outro `tools/call` (EP-05/EP-03).

```python
DispatchResult(decision_id="...", action="finance.payment.execute", status="allowed" | "denied",
                structured_content={...} | None, error_text: str | None)
```

Uma negação do Gateway/PDP vira `status="denied"` com `error_text` — `dispatch()` nunca
reinterpreta ou reexecuta em torno de uma negação; recálculo de NBA após DENY é responsabilidade
de uma camada acima (`orchestrator/fallback.handle_denial`).

## Modo A — `GlobalSupervisor` (governança-somente, ADR-024)

Para quando uma **plataforma de orquestração externa** decide qual agente atende a conversa; o
Service Orchestrator (EP-11) não participa.

```python
supervisor = GlobalSupervisor(backends={"sales_agent": ..., "finance_agent": ...})
result = await supervisor.route_and_run(
    message, current_backend="sales_agent", router=keyword_router
)
# RoutingResult(backend_name, handed_off: bool, turn_result)
```

- `router: RouterFn` — `Callable[[str], str | None]`, escolhe um nome de backend a partir do
  conteúdo da mensagem, ou `None` para permanecer no backend atual. `keyword_router` é a
  implementação de referência (palavra-chave, deliberadamente simples) — **não é a fronteira de
  segurança**; um roteamento errado, ou uma tentativa de manipular o roteamento via prompt, é
  sempre recapturado pelo Gateway/PDP real no backend que efetivamente responde.
- `BackendAgent` — o único contrato que um backend precisa satisfazer:
  `async def run_turn(message: str) -> object`. Cada `BackendAgent` resolve seu **próprio** MCP
  Client/entitlement de forma completamente independente (token, `tools/list`, reautorização) —
  `GlobalSupervisor` nunca lê, guarda ou repassa a credencial de um backend para outro.
- `GlobalSupervisor` nunca importa `emcp_bus.orchestrator` (verificado via análise de AST no
  teste unitário correspondente) — prova mecânica de que o Modo A não usa NBA própria.

**Para integrar um novo backend de agente no Modo A:** implementar `BackendAgent.run_turn`,
registrar seu próprio `ClientRegistration`/`ClientProfile` (ver
[`identity-oidc.md`](identity-oidc.md)) como qualquer outro MCP Client, e adicioná-lo ao dict
`backends` do `GlobalSupervisor`.

## Modo B — `ModeBOrchestrator` (substituição completa, ADR-024)

Para quando o **nosso próprio Service Orchestrator** é o único cérebro de NBA/NBO — nenhum
Global Supervisor externo é consultado.

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

`graph` é o journey `StateGraph` real do EP-11-T02 (`orchestrator/graph.py`,
`build_journey_graph`), invocado **sem modificação**, uma vez por `client_id` em `client_ids`,
para o mesmo `subject_id` — cada invocação resolve profile/entitlement/offerings daquele client
de forma independente. `_combine` é a regra de referência que decide entre os `NBADecision`s
resultantes (pendência de Finance sempre vence oferta de Sales) — não é uma reivindicação de
otimalidade, apenas a mesma postura de `RuleBasedNBADecisionModel` (EP-11-T03). Um `client_id`
cuja jornada termina sem oferta sobrevivente (`nba is None`) simplesmente não contribui a
`considered` — nunca um erro.

**Para estender a regra de combinação:** substituir `ModeBOrchestrator._combine` por um modelo
de ranking cross-domain real — o contrato de entrada/saída (`list[NBADecision]` →
`NBADecision | None`) não muda.

## `execute_handoff`/`build_handoff_payload` (EP-12-T03) — implementado, não usado pelos modos A/B

Primitivo de handoff cross-process com dois cuidados estruturalmente separados: minimização de
contexto (`build_handoff_payload`, só `carry_keys` sobrevive) e resolução de entitlement sempre
independente (`execute_handoff` despacha via o mesmo `AgentDispatcher`, que resolve a credencial
do agente destino do zero). **Achado real**: nem o Modo A (roteamento conversacional puro, sem
uma `NBADecision` de origem) nem o Modo B (já combina decisões e despacha o vencedor direto)
usam este primitivo — ver `AS-BUILT.md` para o detalhe. Continua correto e reutilizável para um
handoff *dentro* de uma jornada Orchestrator-driven que precise ceder controle a outro agente no
meio da execução.

## `IdentityResolver` (EP-12-T04) — nunca uma entrada de autorização

```python
resolver = IdentityResolver(IdentityResolverConfig(aliases={"msisdn": "customer_key"}))
resolver.resolve(
    {"msisdn": "5511...", "amount": 100}
)  # -> {"customer_key": "5511...", "amount": 100}
```

Normaliza nomes de campo entre canais para o mapeamento de parâmetros do Fabric/MCP — **nunca**
consultado pelo PDP (verificado via AST no teste unitário correspondente, mesma disciplina do
`GlobalSupervisor`). Um campo resolvido a partir de dado fornecido pelo caller nunca deve
influenciar uma decisão de autorização (a lição do `docs/adr/ADR-023-autorizacao-nunca-vem-do-payload.md`).

## Erros

| Situação | Exceção |
|---|---|
| `nba.agent` sem `AgentTokenProvider` configurado | `UnknownAgentError` |
| IdP rejeita a obtenção do token do agente | `AgentCredentialError` |
| `current_backend` não registrado no `GlobalSupervisor` | `UnknownBackendError` |
| `nba.agent` do handoff diverge de `payload.target_agent` | `ValueError` (`execute_handoff`) |
| Canal sem `ChannelAdapter` registrado | `UnsupportedChannelError` |
