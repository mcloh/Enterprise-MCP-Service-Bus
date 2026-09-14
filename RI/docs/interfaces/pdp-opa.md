# Interface: PDP (OPA)

Contrato de dados/consulta do Policy Decision Point. Implementação:
[`src/emcp_bus/pdp/client.py`](../../src/emcp_bus/pdp/client.py),
[`pdp/models.py`](../../src/emcp_bus/pdp/models.py),
[`config/policies/entitlement.rego`](../../config/policies/entitlement.rego),
[`config/policies/transaction.rego`](../../config/policies/transaction.rego). Ver
[`AS-BUILT.md`](../AS-BUILT.md#pdp--policy-engine-ep-03).

## Modelo em dois passos

`PDPClient.evaluate(client_profile, tool, arguments, customer_classification)` consulta, em
ordem, e nunca em paralelo:

1. **`emcp.entitlement`** (`entitlement.rego`) — `allow` se `tool` está em
   `data.emcp.client_profiles[client_profile].allowed_tools`. `DENY` aqui é definitivo
   (`reason_code=NOT_IN_ENTITLEMENT`) — nenhum argumento chega a ser avaliado.
2. **`emcp.transaction`** (`transaction.rego`) — só avaliada se o passo 1 permitiu. Restringe por
   argumento/recurso; nunca pode adicionar uma tool ausente do entitlement. Retorna `allow` e
   `require_approval` independentemente.

## Dados versionados no OPA

`EntitlementManager.sync_profiles_to_pdp()` empurra cada `ClientProfile` validado para
`PUT /v1/data/emcp/client_profiles/<profile_name>` no boot — o Rego nunca lê YAML diretamente.

## Requisição de avaliação

```
POST /v1/data/emcp/entitlement/allow
{"input": {"client_profile": "Sales.Write", "tool": "finance.payment.execute"}}
```

```
POST /v1/data/emcp/transaction
{"input": {
  "client_profile": "Finance.Payments",
  "tool": "finance.payment.execute",
  "arguments": {"amount": 15000, "region": "BR-SP"},
  "customer_classification": "standard"
}}
```

## Resposta combinada (`PDPDecision`)

```json
{"outcome": "ALLOW" | "DENY" | "REQUIRE_APPROVAL", "policy_version": "a1b2c3d4e5f6", "reason_code": "..."}
```

Nunca um booleano isolado — `policy_version` e `reason_code` são obrigatórios em toda resposta.

| `reason_code` | `outcome` | Quando |
|---|---|---|
| `NOT_IN_ENTITLEMENT` | `DENY` | Passo 1 negou. |
| `TRANSACTION_POLICY_DENIED` | `DENY` | Passo 1 permitiu, passo 2 negou (limite, região, classificação). |
| `APPROVAL_THRESHOLD_EXCEEDED` | `REQUIRE_APPROVAL` | `allow=true` e `amount > restrictions.approval_threshold`. |
| `ALLOWED` | `ALLOW` | Ambos os passos permitiram, sem exceder o threshold. |

## `policy_version`

Um hash SHA-256 (12 caracteres) do conteúdo dos arquivos `*.rego` (exceto `*_test.rego`) em
`config/policies/`, computado uma vez no boot do Gateway (`compute_policy_version`). Propagado em
toda decisão e evento de auditoria — ver [`audit-events.md`](audit-events.md). Um deployment de
produção substituiria isso por uma revisão de bundle OPA real (ver
`../Production-Recommendations.md`); o contrato (`PDPDecision.policy_version` como string
opaca) não mudaria.

## Erros

| Situação | Exceção | Tratamento pelo caller (Gateway) |
|---|---|---|
| OPA inalcançável, timeout, resposta malformada | `PDPUnavailableError` | Tratado como `DENY` (`PDP_UNAVAILABLE`) — nunca ALLOW implícito (fail-closed, README.md §38). |
| Falha ao empurrar um `ClientProfile` no boot | `PDPUnavailableError` | O Gateway não sobe "saudável" — não há modo degradado sem sincronia de entitlement. |

## Como uma política nova entra em vigor

Editar `config/policies/*.rego` muda o `policy_version` computado (hash do conteúdo). Não há
hot-reload nesta RI — reiniciar o Gateway (que reinicia o processo OPA associado, ou aponta para
um OPA já rodando com o Rego atualizado via `opa run --server config/policies/`).
