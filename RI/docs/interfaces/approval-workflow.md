# Interface: approval workflow

Contrato do serviço de aprovação, para quem vai construir uma UI/integração de aprovação humana.
Implementação: [`src/emcp_bus/approval/models.py`](../../src/emcp_bus/approval/models.py),
[`approval/service.py`](../../src/emcp_bus/approval/service.py). Ver
[`AS-BUILT.md`](../AS-BUILT.md#approval-workflow-ep-14).

## Quando uma aprovação entra em jogo

O PDP retorna `outcome=REQUIRE_APPROVAL` (ver [`pdp-opa.md`](pdp-opa.md)) quando uma transação
excede `ClientProfile.restrictions.approval_threshold`. O Gateway chama
`ApprovalService.check_and_consume` a cada tentativa dessa operação; sem uma aprovação
concedida e ainda válida, cria um `ApprovalRequest` e nega a chamada com
`REQUIRE_APPROVAL:<reason_code>:<approval_id>` (ver [`mcp-gateway.md`](mcp-gateway.md)).

## `ApprovalRequest`

```python
ApprovalRequest(
    approval_id="...",  # uuid4
    operation_hash="...",  # sha256(client_profile, tool, arguments canônicos)
    client_profile="Finance.Payments",
    tool="finance.payment.execute",
    arguments_summary={"amount": 15000, "region": "BR-SP"},  # não redigido nesta RI
    reason_code="APPROVAL_THRESHOLD_EXCEEDED",
    requested_at="2026-09-14T12:00:00Z",
    expires_at="2026-09-14T12:05:00Z",  # ttl_seconds=300 por padrão
    status="pending",  # pending | granted | denied | consumed
)
```

`operation_hash` vincula a aprovação ao **triplo exato** `(client_profile, tool, arguments)` —
JSON canônico com chaves ordenadas, então a mesma chamada lógica sempre produz o mesmo hash
independentemente da ordem de inserção do dict. Uma aprovação concedida para uma chamada nunca
satisfaz uma chamada diferente com os mesmos `client_profile`/`tool` mas argumentos distintos.

## Ciclo de vida

```
request()  →  pending
grant()    →  granted   (emite evento audit approval_granted)
deny()     →  denied
check_and_consume()  →  True (uma única vez) e marca "consumed"; False caso contrário
```

`request()` é idempotente por operação: uma tentativa repetida da mesma chamada enquanto uma
aprovação está `pending` retorna a mesma requisição, não cria uma segunda para o approver
avaliar. `check_and_consume()` é a única forma de uma tentativa ser liberada, e é single-use por
construção — nunca "enfileira e libera automaticamente depois": uma aprovação `granted` que
passa em `check_and_consume` é imediatamente marcada `consumed` e nunca satisfaz uma segunda
tentativa, mesmo da operação idêntica (README.md §46, "approval replay"). Essa checagem é
protegida por `threading.Lock` — sem ele, duas tentativas concorrentes reais poderiam ambas
observar `granted` antes de qualquer uma escrever `consumed` (achado real corrigido durante
EP-15-T04, ver `AS-BUILT.md`).

## Construindo uma UI/integração de aprovação

1. Um approver observa eventos `tool_call_require_approval` (ver
   [`audit-events.md`](audit-events.md)) — carrega `approval_id` em `payload`.
2. A UI/integração chama `ApprovalService.grant(approval_id)` (ou `deny`) fora de banda — hoje
   via CLI/chamada Python direta, não há endpoint HTTP nesta RI (ver
   `../Production-Recommendations.md`).
3. O caller original retenta a mesma chamada (`tools/call` com os mesmos argumentos) — o Gateway
   consulta `check_and_consume` de novo e, agora `granted`, libera a execução.

## Erros

| Situação | Exceção |
|---|---|
| `grant`/`deny` num `approval_id` inexistente | `ApprovalNotFoundError` |
| Falha inesperada dentro de `check_and_consume` (qualquer exceção) | Tratada pelo Gateway como negação — nunca como aprovação implícita (EP-14-T03: `except Exception: approved = False`). |

## Não implementado nesta RI

Store persistente (hoje um `dict` em memória — perde todo o estado de aprovações pendentes num
restart do processo) e uma UI/notificação real para o approver. Ver
`../Production-Recommendations.md`.
