# Interface: eventos de auditoria

Taxonomia e schema dos eventos de auditoria, para quem vai construir um consumidor (SIEM,
dashboard). Implementação: [`src/emcp_bus/audit/models.py`](../../src/emcp_bus/audit/models.py),
[`audit/events.py`](../../src/emcp_bus/audit/events.py),
[`audit/sink.py`](../../src/emcp_bus/audit/sink.py),
[`audit/correlation.py`](../../src/emcp_bus/audit/correlation.py). Ver
[`AS-BUILT.md`](../AS-BUILT.md#auditoria-correlação-e-observabilidade-ep-08).

## Sink

`JSONLFileAuditSink` grava um objeto JSON por linha, append-only, em `EMCP_AUDIT_LOG_PATH`
(padrão `/tmp/emcp-audit.jsonl`). Um consumidor de produção substituiria isso por um sink
durável (Postgres, fila) — ver `../Production-Recommendations.md`; o schema do `EventEnvelope`
abaixo não mudaria.

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

Campos de correlação (`decision_id`, `policy_decision_id`, `entitlement_version`,
`policy_version`, `mcp_request_id`, `trace_id`) são de primeira classe, nunca escondidos dentro
de `payload` — um consumidor pode fazer join entre eventos e entre eventos e spans OTel sem
parsear `payload`.

## Taxonomia (`category`)

Adotada da referência Agent Platform OCI (`docs/adr/ADR-022-referencia-hoshikawa-agent-platform-oci.md`)
em vez de uma taxonomia própria:

| Categoria | Significado | Exemplos de `event_type` |
|---|---|---|
| `ic` | Indicador de Controle / negócio-jornada — a chamada progrediu normalmente | `client_authenticated`, `tool_call_allowed`, `agent_turn_completed`, `nba_recalculated` |
| `noc` | Operacional/erro — falha de disponibilidade, não uma decisão de política | `pdp_unavailable`, `backend_credential_unavailable` |
| `grl` | Guardrail/governança — uma fronteira de entitlement/política foi aplicada ou testada | `tool_call_denied`, `tools_list_filtered`, `tool_call_require_approval`, `approval_granted`, `bypass_attempt_detected`, `journey_ended_after_denial` |

Cada `event_type` fixa sua própria categoria na fábrica que o cria (`audit/events.py`) — nunca é
uma decisão do call site.

## Sanitização (nunca opcional)

Qualquer chave de `payload`, em qualquer nível de aninhamento, cujo nome (lowercased) contenha
`token`, `secret`, `password`, `authorization` ou `credential` tem seu valor substituído por
`sha256:<hex>` — nunca um valor real de segredo chega a um sink. Isso roda em
`EventEnvelope.model_post_init`, então vale para toda via de construção, inclusive
desserialização a partir de um sink existente.

## `event_type` disponíveis

| `event_type` | Categoria | Emitido quando |
|---|---|---|
| `client_authenticated` | ic | Um `tools/list` com token válido resolveu um client conhecido. |
| `tools_list_filtered` | grl | Um `tools/list` retornou (inclui contagem `allowed`/`total`). |
| `tool_call_allowed` | ic | Um `tools/call` foi executado com sucesso. |
| `tool_call_denied` | grl | Qualquer negação de `tools/call` (com `reason_code`). |
| `tool_call_require_approval` | grl | Uma tentativa gerou/encontrou um `ApprovalRequest` pendente. |
| `approval_granted` | grl | Um approver concedeu uma aprovação (`ApprovalService.grant`). |
| `pdp_unavailable` | noc | O OPA não respondeu a uma consulta de `tools/call`. |
| `backend_credential_unavailable` | noc | A credencial de saída para um backend não pôde ser obtida. |
| `bypass_attempt_detected` | grl | Uma requisição alcançou um domain server sem a credencial de saída do Gateway (EP-05-T07). |
| `nba_recalculated` | ic | O Orchestrator recalculou a NBA após um DENY do Gateway (nunca reexecuta a ação negada). |
| `agent_turn_completed` | ic | Um turno do agente de exemplo terminou — inclui `tools_attempted`/`tools_denied` (uma tool negada aqui é o guardrail funcionando, não um bug). |
| `journey_ended_after_denial` | grl | Nenhuma offering sobreviveu a um DENY — a jornada termina, sem tentativa direta ao Fabric. |

## Construindo um consumidor

Um SIEM/dashboard deveria: ler o JSONL (ou o sink de produção equivalente), indexar por
`decision_id`/`mcp_request_id`/`trace_id` para reconstrução ponta a ponta, e tratar qualquer
evento `category: "grl"` como um sinal de guardrail (não necessariamente um incidente — negação
correta é o sistema funcionando), e `category: "noc"` como sinal de disponibilidade.
