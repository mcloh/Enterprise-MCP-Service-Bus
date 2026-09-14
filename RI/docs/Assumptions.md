# Assumptions — premissas e decisões desta RI

Este documento explica **o que foi assumido** ao construir a Reference Implementation (RI) e
**por quê**, distinguindo isso do que é garantia arquitetural da [arquitetura de
referência](../README.md). É uma síntese — não uma cópia — do histórico de decisões registrado
em [`docs/adr/`](../../docs/adr/); cada ADR continua sendo o registro canônico de uma decisão
individual, este documento agrupa o "porquê" por tema para quem está avaliando a RI.

Público-alvo: quem vai **avaliar ou adaptar** esta RI para um cenário real e precisa saber o que
foi assumido versus o que é garantia da arquitetura.

## Escopo geral

**Assumimos que uma RI prova propriedades de segurança, não é um produto pronto para produção.**
Toda decisão abaixo prioriza demonstrar de forma verificável os invariantes da arquitetura
(`MaximumEntitlement` como teto, fail-closed, nunca elevar privilégio por contexto) sobre
completude operacional (HA, escala, UI). Onde as duas coisas colidiram, escolhemos a RI mais
simples que ainda prova a propriedade real contra uma dependência real — nunca um mock do
próprio ponto que estava sendo testado.

## Identidade e PDP: tecnologias fechadas, não hipóteses a revisitar

**Assumimos Keycloak como Identity Provider e OPA/Rego como PDP porque são OSS (Apache-2.0) e
aderentes a padrões abertos** (OAuth 2.1/OIDC, Rego), não por preferência arbitrária. Isso
resolve duas lacunas que a arquitetura de referência deixava abertas (`README.md` §48, perguntas
1 e 3) com uma decisão técnica definitiva, não uma suposição — nunca foram revisitadas ao longo
da implementação. Ver `docs/adr/ADR-019-extensao-de-identidade.md`,
`docs/adr/ADR-025-engine-do-pdp.md`.

**Rejeitamos** um engine de PDP próprio em Python (mais controle, mas reinventa avaliação de
política sem ganho real) e Cedar (também seria adequado, mas OPA tem maior aderência a "padrões
abertos" e uma comunidade Rego mais madura para o escopo desta RI).

## Referência operacional Python/LangGraph/Langfuse (Agent Platform OCI)

**Assumimos como referência operacional concreta o projeto Agent Platform OCI de Christiano
Hoshikawa** (`docs/research/hoshikawa-agent-platform-oci.md`) para a camada de
LangGraph/Langfuse/FastMCP, em vez de inventar um padrão genérico do zero — mais rápido, menos
decisões ad hoc, e um ponto de comparação real do que "orquestração multiagente" significa na
prática. **Reaproveitamos** dessa referência: `StateGraph` com router/supervisor por backend,
checkpointing plugável, taxonomia de observabilidade IC/NOC/GRL com instrumentação híbrida
(spans automáticos + eventos manuais fail-open), `identity.yaml`/`BusinessContext` para
normalizar identidade entre canais, FastMCP como padrão de servidor MCP.

**Rejeitamos explicitamente** um único elemento dessa referência: seu modelo de autorização de
tools por allowlist estático avaliado sobre um `agent_id` que chega como **dado do payload de
entrada da conversa**, não como claim de uma identidade autenticada verificada
independentemente — o próprio projeto de referência admite que isso não substitui
autenticação/autorização real. Essa é exatamente a forma de anti-padrão que a arquitetura
proíbe (`ADR-001`/`ADR-002`/`ADR-003`). A RI reaproveita a *forma* de proxy desse Gateway
(contratos de invocação/resultado, cache por tool, catálogo) apenas na camada de Fabric/UX
conversacional — a decisão ALLOW/DENY continua 100% no nosso PEP/PDP, nunca em `agent_id`
autodeclarado. Ver `docs/adr/ADR-022-referencia-hoshikawa-agent-platform-oci.md`,
`docs/adr/ADR-023-autorizacao-nunca-vem-do-payload.md`. Este achado também motivou um cenário
adversarial dedicado (`tests/adversarial/test_payload_identity_spoofing.py`).

## Downstream identity

**Assumimos** token exchange (RFC 8693) quando o backend suporta OIDC, com fallback para
service account isolado por adapter quando não suporta — porque reutilizar sempre o token do
client (a alternativa mais simples) é exatamente o "blind token passthrough" que a arquitetura
proíbe (inbound ≠ outbound identity). Ver `docs/adr/ADR-020-downstream-identity.md`.

## Granularidade de client profile

**Assumimos** domínio + risk tier (ex.: `Sales.Read`=R1, `Sales.Write`=R2,
`Finance.Payments`=R3) como a granularidade de client profile, em vez de um client "enterprise
admin" único ou apenas domínio sem tier — porque só essa granularidade permite provar
segmentação de blast-radius entre tiers de risco dentro do mesmo domínio (README.md §7, §17,
§31). Ver `docs/adr/ADR-008-segmentacao-por-dominio-e-risco.md`.

## Profile Intelligence: stub determinístico, não "IA de verdade"

**Assumimos** que Profile Intelligence "genérica e substituível" (README.md §6.10) não prescreve
algoritmo, taxonomia nem fonte de dados real — porque a arquitetura de referência não define
nenhum desses, deliberadamente. A RI implementa um stub baseado em regras determinísticas sobre
atributos sintéticos, atrás de uma interface substituível (`ProfileIntelligenceProvider`), que
cumpre o **contrato**, não a "inteligência" em si. Um fork de produção substitui apenas a
implementação, nunca o contrato (`ProfileView`) nem o ponto em que ele se conecta (nunca ao PDP).

## Escopo de domínios: dois, não federação completa

**Assumimos** dois domínios de exemplo (Sales, Finance) como suficientes para provar
segmentação/blast-radius entre domínios distintos, sem precisar de federação multi-domínio
completa. Federação fica deliberadamente fora de escopo desta RI — é tratada no roadmap da
arquitetura de referência como uma fase posterior (§47, Fase 5), não uma lacuna de
implementação.

## Ambiente: 100% local via Docker Compose

**Assumimos** que uma RI roda inteiramente local via `docker compose`, com separação de
ambientes demonstrada por overlay de configuração (`config/env/{dev,ci}.yaml`) em vez de
infraestrutura cloud/híbrida real — provar a arquitetura não exige multi-cloud, e simular
multi-cloud sem multi-cloud real não provaria nada além da própria simulação.

## Substituições para viabilizar teste sem infraestrutura pesada

- **Servidor JWKS local como stand-in de Keycloak** na maior parte da suíte e2e — válido porque
  o que está sendo testado ali é a *lógica de validação de token* (assinatura, `exp`, `iss`,
  `aud`, extração de `azp`), que é idêntica contra qualquer JWKS RS256 válido. A integração de
  protocolo real com Keycloak (grant `client_credentials`, claims reais emitidas por um IdP real,
  RFC 8693) é coberta à parte, contra um Keycloak 26.7.3 real via Docker
  (`tests/e2e/test_real_keycloak.py`) — não é o mesmo teste, é um teste complementar que cobre
  exatamente o que o stand-in não pode.
- **SQLite em vez de Postgres** para o Registry e para o checkpointer do LangGraph — válido para
  provar o contrato/comportamento (schema, lifecycle, pausa/retomada de grafo); não é uma
  alegação sobre desempenho ou concorrência sob carga de produção (ver
  `Production-Recommendations.md`).
- **`policy_version` como hash de arquivo, não revisão de bundle OPA real** — um SHA-256 do
  conteúdo dos `.rego` em disco é suficiente para provar que `policy_version` flui ponta a ponta
  em toda decisão e evento de auditoria; não é uma alegação sobre distribuição de política em um
  cluster de produção.

## Itens deliberadamente fora de escopo

- **Adapter REST sem caminho ao vivo pelo Gateway** (EP-06-T04): implementado e testado
  standalone; nenhum backend de exemplo desta RI é REST, então não há um caminho ao vivo através
  do Gateway exercitando-o. Só passaria a importar se um domínio futuro precisasse de um backend
  não-MCP-nativo.
- **LangGraph deliberadamente ausente do Gateway/Fabric** — usado apenas onde há estado,
  ciclos ou checkpointing reais (Service Orchestrator, EP-11; handoff do Agent Runtime, EP-12-T03).
  Nenhum roteamento simples (Gateway EP-05, Fabric EP-06, Offering Filter EP-10) usa LangGraph —
  usar um grafo com estado para um roteamento sem estado seria over-engineering, não uma escolha
  neutra. Ver `docs/adr/ADR-021-escopo-langgraph-langfuse.md`.
- **Rate limiting e anti-replay**: gaps reais e conscientes, não esquecimentos — documentados e
  cobertos por teste adversarial dedicado (`tests/adversarial/test_protocol_identity.py`), nunca
  silenciosamente ignorados. Ver `Production-Recommendations.md` para o que um deployment real
  precisa adicionar.
