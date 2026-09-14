# Interface: MCP Gateway

A superfície MCP do Gateway — o que qualquer MCP Client integrador chama. Implementação:
[`src/emcp_bus/gateway/server.py`](../../src/emcp_bus/gateway/server.py),
[`gateway/canonical_request.py`](../../src/emcp_bus/gateway/canonical_request.py),
[`gateway/cache.py`](../../src/emcp_bus/gateway/cache.py). Ver [`AS-BUILT.md`](../AS-BUILT.md#pep--mcp-gateway-ep-05)
para o papel do componente na arquitetura.

## Autenticação

Bearer token OAuth2/OIDC no header `Authorization`. Validado contra o JWKS do IdP configurado
(`OIDC_JWKS_URL`/`OIDC_ISSUER`/`OIDC_AUDIENCE`) — assinatura RS256, `exp`, `iss`, `aud`. A
identidade confiável é a claim `azp` (ou, na ausência dela, `client_id`) do token — nunca um
campo de `clientInfo` ou de qualquer parte do corpo da requisição.

## Dois modos de deployment

| Modo | Condição | Comportamento |
|---|---|---|
| Com OIDC configurado | `OIDC_JWKS_URL` + `OIDC_ISSUER` definidos | O middleware de auth do SDK `mcp` rejeita qualquer conexão sem bearer token válido antes do handshake `initialize`. |
| Sem OIDC configurado | Env vars ausentes (padrão) | Nenhum middleware de auth instalado; todo handler roda com `get_access_token() is None` e nega por padrão. |

Os dois modos são deny-by-default; nenhum é um "modo incompleto" esperando o outro — ver
`tests/e2e/test_governed_gateway.py`.

## `tools/list`

Sem token válido: retorna `tools: []`. Com token válido: retorna a interseção do catálogo dos
backends entitled (`CapabilityRouter.distinct_backends_for`) com o `MaximumEntitlement` do
client (`EntitlementManager.resolve(...).allowed_tools`) — nunca o catálogo completo de nenhum
backend. Cada chamada reavalia o entitlement do zero; não há cache de catálogo no lado do
servidor entre clients.

**Cache hint (SEP-2549):** a resposta carrega `ttl_ms`/`cache_scope`, sempre
`cache_scope="private"` — nunca `"public"`, já que o resultado depende da autorização do
caller (`gateway/cache.py:tools_list_cache_hint`). **Limitação verificada**: no transporte de
sessão clássica que esta RI usa em toda parte, o SDK descarta `ttl_ms` na serialização (o campo
só é entregue no wire pelo modo *stateless per-request* do protocolo 2026-07-28) — o cliente
sempre vê o default (`ttl_ms=0`), que é o fallback mais conservador possível, nunca inseguro. A
propriedade de segurança real (nunca vazar catálogo entre clientes) não depende disso — vem do
Gateway recalcular o entitlement em toda chamada.

## `tools/call`

Reautorizado de forma completamente independente de `tools/list` — a lista anterior nunca é
consultada para decidir se uma chamada é permitida. Fluxo:

1. Sem token válido → nega (ver tabela de erros abaixo).
2. Client desconhecido (`ClientRegistration` não encontrado) → nega.
3. PDP consultado (`PDPClient.evaluate`, ver [`pdp-opa.md`](pdp-opa.md)) com `client_profile`,
   `tool`, `arguments`.
4. `DENY` → nega com o `reason_code` do PDP.
5. `REQUIRE_APPROVAL` → consulta `ApprovalService.check_and_consume`; sem aprovação concedida,
   cria um `ApprovalRequest` (ver [`approval-workflow.md`](approval-workflow.md)) e nega.
6. `ALLOW` → resolve o backend via `CapabilityRouter.route` (ver
   [`registry-capability-manifest.md`](registry-capability-manifest.md)) e executa a chamada
   contra o domain server, usando a credencial de saída (nunca o token inbound do client — ver
   [`downstream-identity.md`](downstream-identity.md)).

### Formato de negação

Toda negação é um `CallToolResult` estruturado (`is_error: true`), nunca um erro de protocolo:

```json
{"is_error": true, "content": [{"type": "text", "text": "Access denied: <REASON_CODE>"}]}
```

| `REASON_CODE` | Quando |
|---|---|
| `UNAUTHENTICATED` | Sem token válido. |
| `UNKNOWN_CLIENT` | Token válido, mas `client_id` sem `ClientRegistration`. |
| `PDP_UNAVAILABLE` | OPA inalcançável — fail-closed, nunca ALLOW implícito. |
| `NOT_IN_ENTITLEMENT` | A tool não está em `ClientProfile.allowed_tools` (decisão do PDP). |
| `TRANSACTION_POLICY_DENIED` | Entitlement OK, mas os argumentos violam `transaction.rego` (limite, região, classificação). |
| `REQUIRE_APPROVAL:<motivo>:<approval_id>` | Acima do `approval_threshold` — usa `approval_id` para acompanhar/conceder fora de banda. |
| `UNROUTABLE_CAPABILITY` | Nenhum manifesto `ACTIVE` para a tool, ou backend não resolvível. |
| `UNSUPPORTED_BACKEND_TYPE:<tipo>` | O manifesto aponta para um `backend.type` sem dispatch ao vivo nesta RI (ex.: `rest`, ver `AS-BUILT.md`). |

## Consistência header/body (EP-05-T08)

Se a requisição carregar os headers `Mcp-Method`/`Mcp-Name` (SEP-2243), eles devem concordar com
o `method`/nome do recurso no corpo JSON-RPC, ou a requisição é rejeitada com HTTP 400
(`{"error": "header_body_mismatch", "detail": "..."}`) antes de alcançar autenticação. Headers
ausentes não são um erro — é uma checagem de consistência, não um mandato de adoção do SEP.

## Correlação

Toda decisão carrega, e propaga como atributos de span OTel e em todo evento de auditoria:
`decision_id`, `policy_decision_id`, `entitlement_version`, `policy_version`, `mcp_request_id`.
Ver [`audit-events.md`](audit-events.md).
