# Interface: downstream / outbound identity

Contrato de identidade de saída, para quem vai integrar um novo backend/domain server.
Implementação: [`src/emcp_bus/downstream/models.py`](../../src/emcp_bus/downstream/models.py),
[`downstream/identity.py`](../../src/emcp_bus/downstream/identity.py). Ver
[`AS-BUILT.md`](../AS-BUILT.md#downstream--outbound-identity-ep-07).

Princípio: `inbound token (MCP Client → Gateway) ≠ outbound token (Fabric → Backend)`. O Gateway
autentica o *caller*; este contrato resolve uma pergunta separada — qual credencial o Fabric
apresenta *ao backend* — e nunca a resolve repassando o token inbound sem modificação.

## Registro de um backend (`BackendConfig`)

Um arquivo YAML por backend em `config/backends/*.yaml`:

```yaml
# service_account (modo padrão dos backends seed)
backend: sales-domain
url: http://sales-domain:8100/mcp
audience: sales-domain-service        # nunca igual ao OIDC_AUDIENCE inbound do Gateway
credential_mode: service_account
service_account_token_env_var: SALES_DOMAIN_SERVICE_TOKEN   # nome da env var, nunca um valor literal
```

```yaml
# token_exchange (alternativa disponível e verificada contra Keycloak real)
backend: finance-domain
url: http://finance-domain:8101/mcp
audience: finance-domain-service
credential_mode: token_exchange
token_exchange_endpoint: http://keycloak:8080/realms/emcp/protocol/openid-connect/token
token_exchange_scope: aud-finance-domain-service
```

## Modo `service_account`

Credencial estática, lida de uma variável de ambiente (nome, nunca valor, declarado em
`service_account_token_env_var`) no momento de cada chamada. Ausência da variável em runtime →
`BackendCredentialUnavailableError`.

## Modo `token_exchange` (RFC 8693, Keycloak Standard Token Exchange)

Dois round-trips HTTP por troca nova (`TokenExchangeClient.exchange`): (1) `client_credentials`
como o próprio client de exchange do Gateway, produzindo um `subject_token`; (2) troca desse
`subject_token` por um token com a `audience` do backend alvo. Cacheado por backend até pouco
antes do próprio `expires_in` da troca — um cache hit custa zero round-trips.

**Configuração exigida no IdP (verificada empiricamente contra Keycloak 26.7.3 real):**

- O client de exchange do Gateway (`GATEWAY_TOKEN_EXCHANGE_CLIENT_ID`/`_SECRET`) precisa ter
  `attributes.standard.token.exchange.enabled = "true"` e `serviceAccountsEnabled`.
- `audience` precisa ser o id de um client **realmente registrado** no realm — uma string livre
  falha com `"Audience not found"`.
- Pedir `audience` sem também pedir, via `scope`, um client scope que efetivamente adiciona essa
  audience falha com `"Requested audience not available"` — o parâmetro `audience` só
  **restringe**, nunca **adiciona**. Por isso `token_exchange_scope` é obrigatório neste modo.
- Esse client scope precisa carregar um `oidc-audience-mapper` apontando para a `audience` do
  backend, e ser um scope padrão (ou opcional solicitado) do client de exchange do Gateway.

Ver `deploy/keycloak/realm-export.json` para um exemplo real já configurado (`gateway-token-exchange`
+ client scopes `aud-sales-domain-service`/`aud-finance-domain-service`).

## Contrato de saída (`BackendCredential`)

```python
BackendCredential(
    backend="finance-domain",
    url="http://finance-domain:8101/mcp",
    token="...",
    audience="finance-domain-service",
)
```

## Como integrar um novo backend

1. Registrar o backend no IdP se usar `token_exchange` (client scope + `oidc-audience-mapper`
   para a `audience` escolhida) — ou apenas definir a env var do token estático se usar
   `service_account`.
2. Criar `config/backends/<backend>.yaml` (`BackendConfig`).
3. Referenciar `backend.service` == esse mesmo id em cada `CapabilityManifest` que rotear para
   ele (ver [`registry-capability-manifest.md`](registry-capability-manifest.md)).
4. Se o backend for MCP-nativo (`backend.type: mcp`, o único com dispatch ao vivo nesta RI),
   implementar o `BackendCredentialGate` do lado do backend (ver
   `services/example_mcp_servers/sales_domain/server.py` como referência) — uma requisição sem a
   credencial de saída do Gateway nunca deve alcançar um handler de tool.

## Erros

| Situação | Exceção | Tratamento pelo caller (Gateway) |
|---|---|---|
| `backend` sem `BackendConfig` registrado | `UnknownBackendError` | `UnroutableCapabilityError` no Fabric → `UNROUTABLE_CAPABILITY`. |
| Env var de `service_account` ausente em runtime | `BackendCredentialUnavailableError` | `backend_credential_unavailable` (evento NOC) → chamada negada. |
| Troca RFC 8693 rejeitada pelo IdP | `TokenExchangeError` → relançada como `BackendCredentialUnavailableError` | Idem acima. |
