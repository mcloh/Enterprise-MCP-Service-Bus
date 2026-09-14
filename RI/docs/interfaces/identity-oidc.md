# Interface: identidade e registro de MCP Client (OIDC)

Contrato de registro de um MCP Client e do token OIDC que ele apresenta ao Gateway.
Implementação: [`src/emcp_bus/identity/models.py`](../../src/emcp_bus/identity/models.py),
[`identity/authn.py`](../../src/emcp_bus/identity/authn.py),
[`identity/shared_client_lint.py`](../../src/emcp_bus/identity/shared_client_lint.py). Ver
[`AS-BUILT.md`](../AS-BUILT.md#identidade-do-mcp-client-ep-01).

## Registro de um MCP Client

Um arquivo YAML por client em `config/clients/*.yaml`, validado contra `ClientRegistration`:

```yaml
client_id: finance-payments-agent   # exatamente a claim azp/client_id do token
profile: Finance.Payments           # nome de um ClientProfile em config/clients/profiles/
environment: production             # "dev" | "ci" | "production"
description: "Finance agent authorized to create/execute payments (R3, approval above threshold)"
```

(exemplo real: `config/clients/finance-payments-agent.yaml`)

`client_id` é o único vínculo entre uma identidade autenticada e um `ClientProfile` — dois
`client_id`s distintos nunca compartilham `profile` a menos que isso seja uma decisão explícita
e auditável (regra de shared client, `identity/shared_client_lint.py`, ligada a
`make validate-schemas`).

## Registro do client no IdP

O client precisa existir no realm do IdP com o grant `client_credentials` habilitado e um
mapper de audience apontando para o `OIDC_AUDIENCE` do Gateway (`emcp-gateway` por padrão). Ver
`deploy/keycloak/realm-export.json` para os 3 clients de exemplo já configurados dessa forma
(`sales-read-agent`, `sales-write-agent`, `finance-payments-agent`).

## Contrato do token de acesso

Qualquer IdP compatível com OIDC funciona (`TokenValidator` é agnóstico de fornecedor). Claims
exigidas e validadas por `TokenValidator.validate`:

| Claim | Uso |
|---|---|
| `exp` | Expiração — obrigatória, validada com `leeway_seconds=5`. |
| `iss` | Deve casar exatamente com `OIDC_ISSUER`. |
| `aud` | Deve conter `OIDC_AUDIENCE`. |
| `azp` (preferencial) ou `client_id` | Fonte única de identidade do client — nunca `clientInfo` do request MCP nem qualquer campo do corpo. |

Assinatura verificada via JWKS (`OIDC_JWKS_URL`), algoritmo `RS256`. Falha em qualquer checagem
levanta `AuthenticationError`, tratada pelo Gateway como `UNAUTHENTICATED` (fail-closed).

## Como um novo client se registra, ponta a ponta

1. Criar/atualizar o client no IdP (grant `client_credentials`, mapper de audience).
2. Criar `config/clients/<client-id>.yaml` (`ClientRegistration`).
3. Apontar `profile` para um `ClientProfile` existente, ou criar um novo em
   `config/clients/profiles/` (ver [`registry-capability-manifest.md`](registry-capability-manifest.md)
   para como uma capability referencia um profile via `entitlements`).
4. `make validate-schemas`.
5. Reiniciar o Gateway (registros de client são carregados no boot, sem hot-reload).

## Erros

| Situação | Comportamento |
|---|---|
| Token ausente/malformado/expirado/assinatura inválida | `AuthenticationError` → Gateway trata como `UNAUTHENTICATED`. |
| `aud`/`iss` incorretos | `AuthenticationError` → `UNAUTHENTICATED` (README.md §45 Teste 8). |
| Token válido, mas `client_id` sem `ClientRegistration` correspondente | `UnknownClientError` → Gateway responde `UNKNOWN_CLIENT` em `tools/call`, lista vazia em `tools/list`. |
