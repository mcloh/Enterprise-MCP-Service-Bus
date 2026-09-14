# ADR-019: Identidade do MCP Client -- ponto de extensão de produção (mTLS / workload identity)

**Status:** Documentado (spike), não implementado na RI (EP-01-T04, `could`).
**Fonte:** este ADR é o registro canônico desta decisão. Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/identity-oidc.md`. Também relevante: README.md §19, RF-02, Axiom 2.

## Contexto

A fronteira de identidade da RI (`src/emcp_bus/identity/authn.py`, EP-01-T03) é
OAuth 2.1 `client_credentials` contra o Keycloak (EP-01-T01): todo MCP Client
se autentica com um client_id + secret, obtém um JWT de vida curta, e o
Gateway valida a assinatura/emissor/audience/expiração desse JWT contra o
JWKS do IdP antes de confiar na claim `azp` como a identidade do caller.

Esta é uma decisão deliberada e confirmada para a RI (não um placeholder): OAuth
2.1 satisfaz toda propriedade que o README.md §19 de fato exige de um mecanismo
de identidade -- vida curta, revogável, vinculado a uma audience, verificável
sem um segredo de longo prazo compartilhado no caminho da requisição.
Implantações corporativas reais comumente vão além, usando mTLS (certificados
de cliente TLS mútuo) ou a federação de workload identity de um provedor de
nuvem (ex.: SPIFFE/SPIRE, AWS IAM roles for service accounts, GCP Workload
Identity, Azure Managed Identity) em vez de -- ou além de -- um JWT bearer.
Este ADR documenta como essa extensão se encaixa na costura já existente da
RI, sem exigi-la, para que um fork de produção não fique bloqueado por um
redesenho.

## Decisão

**Não** implementar mTLS/workload identity na RI. Documentar o ponto de
extensão em vez disso, para que o contrato do `EP-01-T03` seja
comprovadamente estável sob ele.

## O ponto de extensão

`TokenValidator.validate(token: str) -> AuthenticatedClient` é a *única*
função na RI que produz identidade de client para fins de autorização
(`emcp_bus.gateway.server.on_list_tools`/`on_call_tool` chamam ambos
`get_access_token()`, que é populado pelo protocolo `TokenVerifier` do SDK
envolvendo esse mesmo validator -- ver
`emcp_bus.identity.token_verifier.MCPTokenVerifier`). Tudo a jusante dela --
`EntitlementManager.resolve`, o PDP, a camada de audit/correlação (EP-08) --
consome apenas o `AuthenticatedClient.client_id` resultante. Nenhum desse
código se importa com *como* a identidade foi estabelecida.

Uma implantação de produção adicionando mTLS ou workload identity faria:

1. Implementar uma segunda fonte de identidade honrando o mesmo contrato de saída:

   ```python
   class MTLSClientValidator:
       def validate(self, request: ...) -> AuthenticatedClient: ...
   ```

   alimentada pelo certificado de cliente já verificado pelo proxy/load
   balancer que termina a conexão (um header estilo `X-Client-Cert-CN` de um
   terminador mTLS confiável, ou o `scope["extensions"]["tls"]` ASGI que um
   servidor compliant expõe) em vez de um JWT. `AuthenticatedClient.client_id`
   seria o Subject/SAN do certificado, mapeado 1:1 a um
   `ClientRegistration.client_id` exatamente da mesma forma que o `azp` de um
   JWT é hoje -- **nenhum outro modelo da RI muda**: `ClientRegistration`,
   `ClientProfile`, `EntitlementManager`, o contrato do PDP e o schema de
   auditoria já são todos agnósticos de mecanismo de identidade.

2. Fornecer um equivalente alternativo de `build_auth()` em
   `emcp_bus/gateway/server.py` que conecta o novo validator no lugar de
   `MCPTokenVerifier`, controlado por configuração de deployment -- o mesmo
   formato do `build_auth()` de hoje retornando `(None, None)` para o modo
   "sem OIDC configurado". Uma implantação híbrida (mTLS para uma classe de
   backend service, OAuth para agentes interativos) é possível fazendo a
   seleção de `TokenVerifier`/equivalente por listener em vez de por
   processo, o que os parâmetros
   `streamable_http_app(auth=..., token_verifier=...)` do SDK já suportam
   por instância de app.

3. Workload identity de nuvem (SPIFFE/SPIRE, IRSA, Workload Identity, Managed
   Identity) é uma variante da mesma forma: o contrato "verificar uma
   credencial que o caller não pode forjar, e extrair dela um identificador
   estável" é idêntico, só o formato da credencial e a biblioteca de
   verificação diferem. Nada disso exige tocar no `EntitlementManager`, no
   PDP, no roteador do Fabric (EP-06-T01), ou na camada de audit/correlação
   (EP-08-T02/T03).

## O que não pode mudar

- **Formato de `AuthenticatedClient`** (`client_id`, `issuer`, `expires_at`):
  todo consumidor a jusante tipa contra isso, não contra um conjunto de
  claims específico de JWT.
- **Contrato fail-closed**: o caminho de falha de qualquer mecanismo de
  identidade deve levantar uma exceção (no formato `AuthenticationError`) em
  vez de recair para uma identidade não autenticada ou autodeclarada pelo
  agente (README.md §5, Axiom 2) -- essa é a propriedade de segurança real
  que o critério de aceite do EP-01-T03 testa, e ela é independente de
  mecanismo.
- **Nenhum caminho privilegiado novo para `clientInfo`**: qualquer que seja o
  mecanismo de identidade, apenas um valor verificado de forma independente
  do corpo da requisição MCP pode popular `client_id`.

## Consequências

- Confirmado para a RI: reduz o esforço de implementação do EP-01 sem
  enfraquecer nenhuma das propriedades de identidade desejáveis do README.md
  §19 (todas satisfeitas por OAuth 2.1 `client_credentials` contra o
  Keycloak).
- Um fork de produção adicionando mTLS/workload identity muda exatamente um
  módulo (`identity/`) e uma função de wiring (equivalente a `build_auth`);
  todo outro componente da RI (Entitlement Manager, PDP, Fabric, Registry,
  audit/correlação, approval) não exige nenhuma mudança.
