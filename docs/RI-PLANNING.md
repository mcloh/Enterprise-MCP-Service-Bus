# Planejamento da Reference Implementation (RI) — Enterprise MCP Service Bus

> Gerado a partir do `README.md` (Working Draft v0.2, 2026-09-03) na raiz do repositório, seguindo o processo de planejamento em 4 fases (extração → decisões técnicas → decomposição em backlog → autovalidação). Este documento **planeja**, não implementa: nenhum código de produção foi escrito.

---

## 8.1 Resumo da arquitetura compreendida

O README descreve uma **reference architecture** (não uma RI pronta) para um Enterprise MCP Service Bus: uma camada de integração corporativa acessível via MCP, em que o **MCP Client** (identidade autenticada de workload) define o teto máximo de privilégio (`MaximumEntitlement`), o **MCP Gateway** atua como PEP determinístico, e um **PDP/Policy Engine** avalia entitlement policy e transaction policy. O agente (LLM) nunca é raiz de confiança: informação por ele controlada pode restringir mas nunca ampliar autorização (`EffectiveCapabilities ⊆ ClientEntitlement`). Um **Enterprise MCP Fabric** publica/roteia/media capabilities entre domínios e backends corporativos existentes (API Gateway, ESB, service mesh, SaaS). Em torno desse núcleo de segurança, a v0.2 adiciona uma cadeia de personalização e orquestração governadas: **Service owners + publishing pipeline** alimentam o **Global Capability Registry**; **Profile Intelligence** produz uma visão de perfil genérica e substituível; o **Entitlement Manager** resolve cardápios MCP personalizados; o **Offering Filter** intersecta catálogo, entitlement, perfil e consentimento; o **Service Orchestrator** calcula a Next Best Action (NBA) sobre esse universo já governado; e o **Agent Runtime** despacha a NBA para agentes/canais. Toda decisão de relevância (perfil, ranking, NBA) é estritamente um subconjunto do que o entitlement já permite — nunca o contrário. O documento define 17 RFs, RNFs de segurança/disponibilidade/performance/escalabilidade/portabilidade, um modelo de risco (R0–R4), política de fail-closed, 10 testes de aceite de segurança e 18+ cenários de teste adversarial.

**Componentes identificados:** Agent · Agent Host/Orchestrator · MCP Client · MCP Gateway/PEP · PDP/Policy Engine · Global Capability Registry · Enterprise MCP Fabric · Service owners/Publishing pipeline · Entitlement Manager · Profile Intelligence · Offering Filter · Service Orchestrator · Agent Runtime/Channel adapters · Identity Provider · Audit/Telemetry.

---

## 8.2 Matriz de rastreabilidade

| Seção do README | Componente/Requisito | Tipo | Épico(s) |
|---|---|---|---|
| §6.1 | Agent | RF | EP-13 |
| §6.2 | Agent Host/Orchestrator | RF | EP-11, EP-12 (ver [LACUNA] G12) |
| §6.3, §18, §19 | MCP Client, identidade, shared-client rule | RF/RNF | EP-01 |
| §6.4, §9, §10, §21, §22 | MCP Gateway/PEP, tools/list, tools/call, anti-bypass, header routing | RF | EP-05 |
| §6.5, §25 | PDP/Policy Engine, entitlement+transaction policy | RF | EP-03 |
| §6.6, §23, §24 | Global Capability Registry, governance lifecycle, control/data plane | RF | EP-02 |
| §6.7, §32, §34 | Enterprise MCP Fabric, integração com plataformas existentes, topologia | RF | EP-06, EP-07 |
| §6.8 | Service owners, publishing pipeline, manifesto | RF | EP-02 |
| §6.9, §41 | Entitlement Manager, client profile | RF | EP-04 |
| §6.10 | Profile Intelligence, clusterização genérica | RF | EP-09 |
| §6.11, §7.3 | Offering Filter, conjuntos Global/Max/Filtered/Ranked | RF | EP-10 |
| §6.12 | Service Orchestrator, NBA | RF | EP-11 |
| §6.13 | Agent Runtime, channel adapters | RF | EP-12 |
| §7, §17 | Modelo de entitlement, risk tiers R0–R4 | RF | EP-02, EP-04 |
| §8, §11, §12 | Client-bound capability view, discovery vs execution, dynamic catalog rule | RF | EP-05 |
| §13 | Caching privado de tools/list | RNF | EP-05 |
| §14, §15, §29, §30 | Prompt injection, escalation vs abuse, cenários de ataque | RNF/Segurança | EP-15 |
| §16 | Modelo em camadas de segurança | RNF | EP-01, EP-03, EP-05, EP-14, EP-15 |
| §20 | Inbound vs outbound identity | RF | EP-07 |
| §26 | Human-in-the-loop | RF | EP-14 |
| §27 | Observabilidade e auditoria | RF | EP-08 |
| §28 | Threat model | RNF | EP-15 |
| §31 | Blast-radius containment | RNF | EP-04, EP-01 |
| §33, §43 | Comparação arquitetural, validação externa | Contexto | (sem tarefa — referência) |
| §35 | Anti-patterns | Restrição | EP-01, EP-05, EP-07, EP-15 |
| §36 (RF-01..17) | Requisitos funcionais | RF | todos |
| §37, §38 | RNFs, política de falha | RNF | EP-05, EP-14, EP-15 |
| §39, §40 | Naming/namespaces, versionamento | Restrição | EP-02 |
| §42 | Zero Trust (NIST) | RNF | EP-01, EP-03, EP-05 |
| §45, §46 | Critérios de aceite de segurança, testes adversariais | RF | EP-15 |
| §47 | Roadmap de adoção (Fases 0–5) | Contexto | Mapeado em Marcos (8.7) |
| §48 | Decisões abertas | — | Ver ADRs (8.4) e Lacunas (8.3) |
| §49 | ADRs sugeridos | — | Ver 8.4 |
| §50 | Axiomas | Restrição | Transversal a todos os épicos |

---

## 8.3 Lacunas e premissas

| ID | Tipo | Descrição | Impacto | Pergunta ao autor do README |
|---|---|---|---|---|
| ~~G1~~ | ~~[LACUNA]~~ **[RESOLVIDO]** | O README cita `RI/` com "gateway MCP, PEP/PDP, OPA, Keycloak" na linha 10, mas o diretório não existia no repositório no início deste planejamento. **Confirmado pelo autor em 2026-09-11**: `RI/` é a pasta-alvo onde a implementação será construída do zero — a frase no README é aspiracional/prospectiva, não uma referência a algo já existente. | — (resolvido) | — |
| P1 | [PREMISSA CONFIRMADA] | OPA (PDP) e Keycloak (IdP/OAuth2-OIDC) são as tecnologias-alvo desta RI — citadas no próprio README e OSS/padrões abertos (seção 5 do superprompt). `RI/` deve ser criado integralmente por EP-00 em diante (ver EP-00-T01, atualizado para deixar explícito que cria a pasta do zero). | — | — |
| ~~G2~~ | ~~[LACUNA]~~ **[RESOLVIDO]** | O README não define stack de implementação. **Confirmado pelo autor em 2026-09-11**: adotar como referência concreta de camada Python/LangGraph/Langfuse o repositório de Christiano Hoshikawa, "Agent Platform OCI" (`github.com/hoshikawa2/agent_platform_oci`), analisado em detalhe (README + SPEC-002/003/004/007/012/018). | — (resolvido) | — |
| P2 | [DECISÃO CONFIRMADA] | Python 3.12+/YAML/LangGraph/Langfuse conforme padrão do superprompt, **com o padrão operacional concreto** do Agent Platform OCI (Hoshikawa) como referência de implementação: StateGraph com router/supervisor por backend + Agent Gateway/Global Supervisor roteando entre backends; checkpointing plugável (memory/sqlite/mongodb/produção); taxonomia de eventos Langfuse **IC/NOC/GRL** (negócio/operacional/guardrail); instrumentação híbrida (spans automáticos por nó + `_emit_ic/_emit_noc/_emit_grl` manuais, fail-open); FastMCP como padrão de servidor MCP. **Ressalva crítica adotada como ADR-022/023**: o modelo de autorização do MCP Gateway daquele projeto (allowlist por `agent_id` declarado no payload de entrada) é o anti-padrão exato que nosso ADR-001 proíbe e **não deve ser copiado** — apenas a engenharia de proxy/cache/contratos é reaproveitável, nunca a decisão de autorização. Ver ADR-018, ADR-022, ADR-023. | — | — |
| ~~G3~~ | ~~[LACUNA]~~ **[RESOLVIDO]** | §48, pergunta 3: engine do PDP em aberto. **Confirmado pelo autor em 2026-09-11**: decisão técnica definitiva, não apenas premissa a validar. | — (resolvido) | — |
| P3 | [DECISÃO CONFIRMADA] | OPA/Rego é o PDP da RI — por ser OSS (Apache-2.0) e aderente a "padrões abertos" (seção 5 do superprompt); não é uma suposição a revisitar. Ver ADR-025 (numeração corrigida em 2026-09-11 para não colidir com o ADR-010 do README, "Global Capability Registry Governance"). | — | — |
| ~~G4~~ | ~~[LACUNA]~~ **[RESOLVIDO]** | §48, pergunta 1: tecnologia de identidade do MCP Client em aberto. **Confirmado pelo autor em 2026-09-11**: Keycloak é decisão técnica definitiva, por ser OSS. | — (resolvido) | — |
| P4 | [DECISÃO CONFIRMADA] | OAuth 2.1 `client_credentials` via Keycloak é a identidade do MCP Client na RI (não apenas para dev/CI). mTLS/workload identity seguem como ponto de extensão documentado para produção, não implementado na RI. Ver ADR-019 (atualizado). | — | — |
| G5 | [LACUNA] | §48, pergunta 5: modelo de downstream/outbound identity em aberto. | Médio | — |
| P5 | [PREMISSA] | Token exchange (RFC 8693) via Keycloak quando o backend suportar OIDC; senão, service account por adapter, documentado por backend em `config/backends/*.yaml`. Ver ADR-020. | — | — |
| G6 | [LACUNA] | §48, pergunta 2: granularidade de client profiles em aberto. | Médio | — |
| P6 | [PREMISSA] | Granularidade = domínio + risk tier (ex.: `Sales.Read`=R1, `Sales.Write`=R2, `Finance.Payments`=R3), como já exemplificado em §7.1 e §17. | — | — |
| G7 | [LACUNA] | Profile Intelligence "genérica e substituível" (§6.10) não define algoritmo, fonte de dados real nem taxonomia. | Médio | Existe um dataset de referência (sintético) que a organização gostaria de usar na RI, ou a RI deve ficar 100% sintética? |
| P7 | [PREMISSA] | RI implementa um stub baseado em regras determinísticas sobre atributos sintéticos, atrás de uma interface substituível (`ProfileIntelligenceProvider`), sem clusterização real nem taxonomia proprietária — cumpre o contrato, não a "inteligência". | — | — |
| ~~G8~~ | ~~[LACUNA]~~ **[RESOLVIDO]** | README não menciona LangGraph/Langfuse explicitamente. **Resolvido em 2026-09-11** ao adotar o padrão operacional do Agent Platform OCI (Hoshikawa) — ver P2/ADR-022. | — (resolvido) | — |
| P8 | [DECISÃO CONFIRMADA] | LangGraph aplicado em duas camadas espelhando o padrão de referência: (a) EP-11 — StateGraph de jornada do Service Orchestrator, com nós fixos (resolve profile → resolve entitlement → filter offerings → decide NBA) e recálculo/degradação (§10.1) como aresta condicional; (b) EP-12-T03 — handoff entre agentes, inspirado no padrão de dois níveis do Hoshikawa (Global Supervisor entre backends + router/supervisor interno por backend), mas com a autorização de cada etapa **sempre** resolvida pelo nosso PEP/PDP, nunca por um campo autodeclarado no payload (essa é a lição central do ADR-023). Langfuse aplicado apenas onde há chamada real a LLM (EP-13), com instrumentação híbrida: spans automáticos por nó do grafo + eventos de negócio manuais (fail-open) na taxonomia IC/NOC/GRL (ver EP-08-T02 atualizado). Nenhum roteamento simples do Gateway/Fabric usa LangGraph. | — | — |
| G9 | [LACUNA] | §47 Fase 3 pede "multi-domain fabric" com federação; escopo de RI vs. produto não é definido. | Baixo | — |
| P9 | [PREMISSA] | RI demonstra 2 domínios (Sales, Finance) — suficiente para provar segmentação/blast-radius (§7, §31) sem federação completa. Federação fica fora de escopo (marcada `could`/stretch). | — | — |
| G10 | [LACUNA] | §48 pergunta 9 (multi-cloud/híbrido) e pergunta 10 (dev/test/prod) não são endereçáveis em uma RI local. | Baixo | — |
| P10 | [PREMISSA] | RI roda 100% local via `docker compose`; separação de ambientes é demonstrada via overlay de configuração (`config/env/{dev,ci}.yaml`), sem infraestrutura cloud real. | — | — |
| ~~G11~~ | ~~[LACUNA]~~ **[RESOLVIDO]** | §6.2 ("Agent Host/Orchestrator") e §6.12 ("Service Orchestrator") descrevem responsabilidades sobrepostas. **Resolvido em 2026-09-11** pelo posicionamento confirmado com o autor: §6.2 corresponde a uma plataforma multiagente *externa e consumidora* do bus (ex.: Agent Platform OCI/Hoshikawa — StateGraph + Global Supervisor), não a um componente que a RI precisa construir. | — (resolvido) | — |
| P11 | [DECISÃO CONFIRMADA] | §6.2 é o papel que uma plataforma de agentes externa (como o Agent Platform OCI) ocupa ao se conectar ao E-MCP-BUS como consumidora governada — ver ADR-024. Dentro da RI, apenas EP-11 (Service Orchestrator/NBA) e EP-12 (Agent Runtime/dispatch) são construídos, como a fronteira que essa plataforma externa atravessa até o MCP Client. Nenhum componente duplicado. | — | — |

---

## 8.4 ADRs

Formato: contexto → decisão → alternativas → consequências. ADR-001 a ADR-017 seguem os títulos sugeridos em §49 do README (decisões arquiteturais já implícitas nos princípios/axiomas); ADR-018+ são decisões de implementação da RI necessárias para fechar as lacunas da seção 8.3.

| ADR | Contexto | Decisão | Alternativas consideradas | Consequências |
|---|---|---|---|---|
| ADR-001 | Quem define o teto de privilégio do agente. | MCP Client (identidade autenticada) é a fronteira de `MaximumEntitlement`, nunca o agente/prompt. | Autorização por role autodeclarado do agente. | Todo design de EP-01/EP-04 gira em torno da identidade do client, não do agente. |
| ADR-002 | Onde aplicar enforcement. | MCP Gateway é o único PEP; nunca delega decisão ALLOW/DENY ao LLM. | Enforcement distribuído em cada MCP Server. | Centraliza EP-05; servidores de domínio (EP-06) não reimplementam authz. |
| ADR-003 | `tools/list` filtrado é suficiente? | Não — `tools/call` deve ser reautorizado independentemente do discovery. | Confiar apenas em filtered discovery. | EP-05 implementa dois pontos de enforcement, não um. |
| ADR-004 | Contexto agêntico pode elevar privilégio? | Nunca — contexto só pode subtrair (`Context may subtract, must never add`). | Permitir elevação mediante "confiança" do modelo. | Testes de EP-15 (Teste 3/4) validam a invariante. |
| ADR-005 | Cache de `tools/list` entre clients. | `cacheScope=private`, chave = identidade+contexto+policy_version. | Cache compartilhado por performance. | EP-05-T03; teste dedicado de isolamento (EP-15). |
| ADR-006 | Token do agente pode ser repassado ao backend? | Não — proibido blind token passthrough; inbound ≠ outbound identity. | Passthrough direto do token do client. | EP-07 implementa exchange/service account por backend. |
| ADR-007 | Backend acessível diretamente pelo client? | Não — rede/identidade restringem acesso só ao Gateway/Fabric. | Expor Fabric publicamente com authz "best effort". | EP-05-T07, EP-15 (teste de bypass). |
| ADR-008 | Como segmentar clients. | Por domínio + risk tier (R0–R4), não um client global. | Um client "enterprise admin" único. | Define P6 (granularidade) e EP-04. |
| ADR-009 | Como classificar capabilities. | Risk tiers R0–R4 no Registry, controlando aprovação/observabilidade exigidas. | Sem classificação formal. | EP-02-T01 inclui `risk_tier` obrigatório no schema do manifesto. |
| ADR-010 | Governança do Global Capability Registry (título e número herdados de §49 do README — "Global Capability Registry Governance"). | O Registry é um control-plane asset (§6.6) com autoridade e ciclo de vida próprios, separados da visão de catálogo entregue a cada client. Na RI: armazenamento e API de leitura dedicados (EP-02-T03), consumidos por Gateway/Fabric/Offering Filter mas nunca editados por eles; lifecycle formal nominate→review→register→publish→observe→(change\|deprecate→retire) (§23) implementado como máquina de estados (EP-02-T04); toda alteração passa pelo publishing pipeline (EP-02-T02) — nenhum cadastro manual direto em produção (RF-11). Owner organizacional do Registry (quem aprova mudanças de schema/política do próprio control plane) permanece uma decisão de governança corporativa fora do escopo técnico da RI (§48, pergunta 4, segue aberta). | Deixar o Registry como uma tabela editável ad hoc por qualquer serviço; fundir a visão de controle (Registry) com a visão de execução (catálogo filtrado por client), o que violaria a separação control plane/data plane do §24. | EP-02 inteiro; reforça que EP-05 (Gateway) e EP-10 (Offering Filter) só leem o Registry, nunca escrevem nele. |
| ADR-011 | Ciclo de publicação de capabilities. | Pipeline obrigatório com gates de schema/risco/policy/health antes de entrar no Registry — sem cadastro manual em produção. | Registro direto via API administrativa sem pipeline. | EP-02-T02 implementa o gate; nenhuma capability "nasce" já publicada. |
| ADR-012 | Autoridade do cardápio máximo. | Entitlement Manager é a única autoridade de `MaximumEntitlement`; não faz ranking nem confia em atributos autodeclarados do LLM. | Fundir Entitlement Manager e Offering Filter num único componente. | Mantém EP-04 e EP-10 como serviços/módulos distintos com contratos próprios. |
| ADR-013 | Contrato de Profile Intelligence. | Interface genérica e substituível (`ProfileView` versionado, com `reasonCodes`), implementação plugável. | Acoplar a um vendor/taxonomia específica de segmentação. | EP-09 define apenas o contrato + stub de referência (ver P7). |
| ADR-014 | Perfil pode ampliar entitlement? | Nunca — `FilteredOfferings ⊆ MaximumEntitlement`, perfil só ordena/reduz. | Perfil de alto engajamento desbloqueando novas tools. | EP-10-T02 traz teste de propriedade validando a invariante para entradas aleatórias. |
| ADR-015 | NBA é decisão de autorização? | Não — é intenção de orquestração; Gateway/PDP reautorizam toda execução. | Orchestrator despachar direto para o backend sem passar pelo Gateway. | EP-11-T04 implementa o branch de DENY/recálculo do §10.1. |
| ADR-016 | Contrato de dispatch/handoff do Agent Runtime. | Objeto de dispatch versionado (`decisionId`, `expiresAt`, `reasonCodes`) que não substitui o token do MCP Client. | Runtime injetar credenciais próprias no agente. | EP-12-T01 consome exclusivamente o dispatch object + MCP Client já existente. |
| ADR-017 | Correlação ponta a ponta. | `profileVersion`+`entitlementVersion`+`decisionId`+`policyDecisionId`+`mcpRequestId` propagados via OTel/trace context em todos os componentes. | Correlação apenas por log textual sem padrão. | EP-08-T03 formaliza os campos; base para EP-15 (auditabilidade). |
| ADR-018 | Stack de implementação da RI (fecha G2). | Python 3.12+, `uv`, Pydantic v2, YAML declarativo com JSON Schema, SDK oficial `mcp`. | Node/TypeScript (SDK MCP também oficial); Go. | Define toda a estrutura de repositório (8.5). |
| ADR-019 | Identidade do MCP Client na RI (fecha G4 — **decisão confirmada pelo autor em 2026-09-11**). | Keycloak (OAuth 2.1 `client_credentials`) é a identidade do MCP Client na RI, por ser OSS. Decisão definitiva; mTLS/workload identity seguem documentados como extensão de produção não implementada na RI. | mTLS completo desde o início. | Reduz esforço de EP-01 sem violar §19 (propriedades desejáveis ainda são satisfeitas: curta duração, revogável, audience-bound). |
| ADR-020 | Downstream identity na RI (fecha G5/P5). | Token exchange (RFC 8693) quando backend suporta OIDC; senão service account isolado por adapter. | Reutilizar sempre o token do client (proibido por ADR-006). | EP-07; documentado por backend em manifesto. |
| ADR-021 | Escopo de LangGraph/Langfuse (fecha G8/P8). | LangGraph somente no Service Orchestrator (EP-11) e handoff do Agent Runtime (EP-12); Langfuse somente onde há chamada real a LLM (EP-13). Checkpointer: SQLite em dev. | Usar LangGraph também no Gateway/Fabric para "consistência de stack". | Evita over-engineering vetado pela seção 6 do superprompt; Gateway/Fabric continuam Python puro. |
| ADR-022 | Referência concreta de implementação Python/LangGraph/Langfuse (fecha G2 — **decisão confirmada pelo autor em 2026-09-11**). | Adotar como referência operacional o "Agent Platform OCI" de Christiano Hoshikawa (`github.com/hoshikawa2/agent_platform_oci`): StateGraph com router/supervisor por backend + camada superior de roteamento entre backends (nosso EP-11/EP-12); checkpointing plugável (memory/sqlite/mongodb/produção — nós adotamos SQLite em dev, ver ADR-021); taxonomia de observabilidade **IC/NOC/GRL** via Langfuse (evento de negócio/operacional/guardrail), com instrumentação híbrida (span automático por nó + emissão manual fail-open); `identity.yaml`/`BusinessContext` para normalizar identidade de negócio entre canais; FastMCP como padrão de servidor MCP. Análise completa registrada em `docs/research/hoshikawa-agent-platform-oci.md`. | Continuar com o padrão genérico da seção 6 do superprompt sem referência concreta de terceiros (mais lento, mais decisões ad hoc); adotar um framework de agentes de mercado (CrewAI, AutoGen) em vez de LangGraph puro. | Muda a forma (não a segurança) de EP-08, EP-11, EP-12, EP-13 — ver ADR-023 para o limite explícito do que NÃO é adotado. |
| ADR-023 | Autorização de tools NUNCA vem de um campo declarado no payload/conversa (achado crítico da análise do Hoshikawa, reforça ADR-001/002/003). | O MCP Gateway do Agent Platform OCI autoriza tools por um allowlist estático (`tools.yaml`/`authorization.agents.<agent_id>.allowed_tools`) avaliado sobre `agent_id`, campo que chega como **dado do payload de entrada da conversa**, não como claim de uma identidade autenticada verificada independentemente — a própria SPEC-004 deles admite que isso não substitui autenticação/autorização real. Nossa RI reaproveita a *forma* de proxy desse MCP Gateway (contratos `ToolInvocation`/`ToolResult`, cache por tool idempotente, catálogo `/v1/tools`) **exclusivamente na camada de Fabric (EP-06)/UX conversacional**, mas a decisão ALLOW/DENY continua 100% no nosso PEP (EP-05) consultando o PDP (EP-03) com a identidade autenticada do MCP Client (EP-01) — nunca com `agent_id`/`tenant_id` autodeclarado no payload. | Reaproveitar também o bloco `authorization` deles como atalho de implementação. | EP-15-T03 ganha um cenário adversarial explícito de "payload-declared agent_id spoofing" (variação do Teste 4, §45) para provar que esse vetor específico está fechado na nossa RI. |
| ADR-024 | Posicionamento do E-MCP-BUS em relação a plataformas de orquestração multiagente externas, como o Agent Platform OCI (**decisão confirmada e ampliada pelo autor em 2026-09-11** — resolve G11). | O E-MCP-BUS **não compete** com plataformas de orquestração como o Agent Platform OCI — mas também **não se limita a coexistir sob elas**. Princípio de design explícito: **modularidade + compatibilidade = escolha**. Nosso Service Orchestrator (EP-11) não é um passa-through fino: ele calcula NBA **e NBO** (Next Best Action/Next Best Offer) com um modelo de decisão próprio (regras + guardrails +, opcionalmente, um modelo de IA de ranking/recomendação — ver EP-11-T03) sobre o universo de `FilteredOfferings` que o MCP Fabric expõe (serviços, ofertas, ações, campanhas — não só "tools" técnicas). Isso habilita **dois modos de integração igualmente válidos, escolhidos pelo adotante conforme a topologia desejada**: **(A) Governança-somente** — uma plataforma de orquestração externa (ex.: Agent Platform OCI, com seu próprio Global Supervisor e StateGraph decidindo NBA) conecta-se ao E-MCP-BUS apenas para acesso governado ao Fabric; nosso Service Orchestrator não participa, ou participa apenas como fonte de `FilteredOfferings` (como já descrito no restante deste ADR e em EP-13-T05). **(B) Substituição completa** — nosso próprio Service Orchestrator (EP-11) assume integralmente o papel de "cérebro" de decisão (NBA/NBO), dispensando o Global Supervisor/StateGraph de decisão da plataforma externa; o Agent Runtime (EP-12) e os channel adapters da plataforma externa (ex.: os backends de agente do Hoshikawa) tornam-se meros executores do dispatch que nosso Orchestrator produz. Em qualquer um dos dois modos, o núcleo de segurança (PEP/PDP, EP-05/EP-03) nunca muda de lugar — apenas quem calcula a NBA/NBO muda. Em ambos os modos, cada backend/agente de domínio continua registrado como um **MCP Client distinto** (EP-01), vinculado a um client profile/entitlement próprio por domínio+risk tier (EP-04, P6), e o "MCP Gateway" interno de qualquer plataforma consumidora (ADR-023) é sempre substituído pelo nosso Gateway/PEP como único ponto de autorização. Isso é a "elevação a Enterprise": catálogo/entitlement/auditoria governados centralmente, com a decisão de NBA/NBO podendo vir de dentro (modo B) ou de fora (modo A) do bus, por escolha modular do adotante. | Forçar um único modo de integração (ex.: só "governança-somente"), o que subutilizaria o Service Orchestrator e obrigaria sempre uma plataforma externa de decisão; tratar o Agent Platform OCI como um substituto do E-MCP-BUS (incorreto — ele não resolve entitlement); reimplementar do zero a engenharia de orquestração já validada em ADR-022 mesmo quando o modo B é escolhido (a forma StateGraph/checkpointing/handoff continua reaproveitável dentro do nosso EP-11/EP-12). | Reformula o objetivo de EP-11 (Service Orchestrator explicitamente descrito como calculador de NBA **e NBO** sobre serviços/ofertas/ações do Fabric, com modelo de decisão pluggable) e de EP-13 (demonstra os dois modos — ver EP-13-T05 para o modo A e EP-13-T06, novo, para o modo B). Reforça que EP-06/EP-05 tratam qualquer "MCP Gateway" de uma plataforma consumidora como não-confiável para autorização, nos dois modos. |
| ADR-025 | Engine do PDP (fecha G3 — **decisão confirmada pelo autor em 2026-09-11**; renumerado de ADR-010 para ADR-025 em 2026-09-11 para não colidir com o ADR-010 do README, "Global Capability Registry Governance"). | OPA/Rego, self-hosted, OSS (Apache-2.0). Decisão definitiva, não sujeita a revisão. **Verificado em 2026-09-11 via busca web**: OPA está em v1.0+, com sintaxe Rego v1 como padrão (breaking change vs. v0) — EP-03 deve escrever policies em sintaxe Rego v1 desde o início. | Cedar (AWS, cita-se em §43.2); engine própria em Python. | EP-03 inteiro fica acoplado à API REST do OPA; policies versionadas como código em Rego v1. |

---

## 8.5 Estrutura proposta do repositório

```text
Enterprise-MCP-Service-Bus/
├── README.md                      # arquitetura de referência (existente)
├── docs/
│   ├── RI-PLANNING.md             # este documento
│   └── adr/                       # ADR-001..021 em arquivos individuais (EP-16-T03)
└── RI/                            # implementação executável (não existe ainda — ver G1)
    ├── pyproject.toml             # PEP 621, uv, ruff, mypy/pyright, pytest
    ├── Makefile                   # up/down/logs/test/lint/validate-schemas
    ├── docker-compose.yml         # stack completa (perfis: core, llm-observability)
    ├── README.md                  # quickstart da RI
    ├── config/                    # TUDO que é configurável, em YAML
    │   ├── env/                   # overlays dev/ci
    │   ├── clients/                # client profiles (§41) — EP-04
    │   ├── capabilities/           # manifests de capability (§6.8) — EP-02
    │   ├── policies/               # Rego (entitlement + transaction) — EP-03
    │   ├── backends/               # config de downstream identity por adapter — EP-07
    │   └── orchestrator/           # definição declarativa de jornadas/regras — EP-11
    ├── schemas/                    # 1 JSON Schema por tipo de YAML/JSON acima
    ├── src/emcp_bus/
    │   ├── common/                  # config loader, Pydantic base models, OTel setup
    │   ├── identity/                 # EP-01
    │   ├── registry/                 # EP-02 (control plane)
    │   ├── pdp/                      # EP-03 (cliente OPA)
    │   ├── entitlement/               # EP-04
    │   ├── gateway/                   # EP-05 (PEP, data plane)
    │   ├── fabric/                    # EP-06 (router, mediation)
    │   ├── downstream/                # EP-07 (outbound identity)
    │   ├── audit/                     # EP-08
    │   ├── profile_intelligence/      # EP-09
    │   ├── offering_filter/           # EP-10
    │   ├── orchestrator/              # EP-11 (grafos LangGraph)
    │   └── agent_runtime/             # EP-12
    ├── services/
    │   └── example_mcp_servers/
    │       ├── sales_domain/          # EP-06
    │       └── finance_domain/        # EP-06
    ├── agents/
    │   └── example_agent/             # EP-13 (Langfuse)
    ├── deploy/
    │   ├── keycloak/                  # realm export — EP-01
    │   ├── opa/                       # bundles Rego — EP-03
    │   ├── otel/                      # collector config — EP-08
    │   └── langfuse/                  # compose overlay OSS — EP-13
    └── tests/
        ├── unit/
        ├── contract/                  # EP-15-T01
        ├── e2e/                       # EP-15-T02
        └── adversarial/               # EP-15-T03/T04
```

---

## 8.6 Backlog estruturado

```yaml
backlog:
  - epico_id: EP-00
    titulo: "Bootstrap e tooling da RI"
    objetivo: "Estabelecer scaffolding Python/YAML, CI e docker-compose base necessários a todos os demais épicos."
    secoes_readme: ["Seção 5 do superprompt (stack)"]
    tarefas:
      - id: EP-00-T01
        titulo: "Scaffold do projeto Python"
        descricao: "Criar o diretório RI/ do zero (não existe no repositório) com pyproject.toml (PEP 621, uv), ruff, mypy/pyright estrito, pytest+pytest-asyncio, pre-commit."
        componente: "tooling"
        tipo: infra
        prioridade: must
        estimativa: P
        depende_de: []
        entregaveis: ["RI/pyproject.toml", "RI/.pre-commit-config.yaml", "RI/Makefile"]
        criterios_aceite: ["Dado o repo clonado, quando se roda `make lint test`, então lint e um teste smoke passam sem erro."]
        padroes_abertos: ["SemVer", "Conventional Commits"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: ["Escolha prematura de versões — mitigado por EP-16-T04"]
        rastreabilidade: ["ADR-018"]

      - id: EP-00-T02
        titulo: "Framework de configuração declarativa"
        descricao: "Loader YAML->Pydantic v2 com interpolação de variáveis de ambiente, overlay por ambiente (config/env/*.yaml) e exportação automática de JSON Schema por modelo."
        componente: "common/config"
        tipo: infra
        prioridade: must
        estimativa: M
        depende_de: ["EP-00-T01"]
        entregaveis: ["src/emcp_bus/common/config.py", "schemas/README.md (convenção de geração)"]
        criterios_aceite: ["Dado um YAML inválido contra seu schema, quando carregado, então falha com erro legível apontando o campo.", "Segredos nunca são aceitos como valor literal em YAML — apenas via ${ENV_VAR}."]
        padroes_abertos: ["JSON Schema"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["ADR-018"]

      - id: EP-00-T03
        titulo: "Pipeline de CI"
        descricao: "CI (lint, type-check, testes, validação de todo YAML em config/ contra seu JSON Schema) executando a cada PR."
        componente: "ci"
        tipo: infra
        prioridade: must
        estimativa: P
        depende_de: ["EP-00-T01", "EP-00-T02"]
        entregaveis: [".github/workflows/ci.yml (ou equivalente)"]
        criterios_aceite: ["Quando um YAML de config/ viola seu schema, então o CI falha antes de qualquer teste de integração."]
        padroes_abertos: ["JSON Schema"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: []

      - id: EP-00-T04
        titulo: "docker-compose base (walking skeleton)"
        descricao: "docker-compose.yml mínimo capaz de subir apenas o Gateway e um MCP Server de exemplo, com perfis (`core`, `llm-observability`) para adicionar serviços pesados depois."
        componente: "deploy"
        tipo: infra
        prioridade: must
        estimativa: P
        depende_de: ["EP-00-T01"]
        entregaveis: ["RI/docker-compose.yml"]
        criterios_aceite: ["Quando `docker compose --profile core up`, então gateway e example-server sobem e respondem health check."]
        padroes_abertos: ["OCI"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: []

      - id: EP-00-T05
        titulo: "Gestão de segredos"
        descricao: "Convenção e mecanismo (.env + docker secrets, ou SOPS quando fizer sentido) para segredos: client secrets, tokens de backend, credenciais de banco — nunca em YAML versionado."
        componente: "common/config"
        tipo: seguranca
        prioridade: must
        estimativa: P
        depende_de: ["EP-00-T02"]
        entregaveis: ["RI/.env.example", "docs de convenção em RI/README.md#secrets"]
        criterios_aceite: ["Um `git grep` por padrões de segredo nos arquivos versionados não encontra nenhum valor real.", "Todo segredo referenciado em config YAML usa ${ENV_VAR}."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: ["Vazamento acidental de secret em commit — mitigado por pre-commit hook de detecção"]
        rastreabilidade: ["RNF-Segurança (§37)"]

  - epico_id: EP-01
    titulo: "Identidade do MCP Client e autenticação"
    objetivo: "Garantir que a identidade usada para autorização venha de um mecanismo autenticado, nunca de campos autodeclarados (§5, Observação crítica sobre clientInfo)."
    secoes_readme: ["§5", "§6.3", "§18", "§19", "§20", "§35.5", "§35.6"]
    tarefas:
      - id: EP-01-T01
        titulo: "Keycloak como Identity Provider da RI"
        descricao: "Serviço Keycloak no compose com realm de exemplo (script de import) representando ambiente enterprise."
        componente: "identity"
        tipo: infra
        prioridade: must
        estimativa: P
        depende_de: ["EP-00-T04"]
        entregaveis: ["deploy/keycloak/realm-export.json", "compose service `keycloak`"]
        criterios_aceite: ["Dado o compose no ar, quando se acessa o endpoint OIDC discovery do realm, então retorna metadata válida."]
        padroes_abertos: ["OAuth 2.1", "OpenID Connect"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: ["[NÃO-OSS]: nenhum — Keycloak é Apache-2.0"]
        rastreabilidade: ["RF-02", "ADR-019"]

      - id: EP-01-T02
        titulo: "Schema de registro de MCP Client"
        descricao: "YAML `config/clients/*.yaml` + Pydantic + JSON Schema mapeando client_id ↔ client Keycloak ↔ nome do client profile (ex.: Sales.Read)."
        componente: "identity"
        tipo: feature
        prioridade: must
        estimativa: P
        depende_de: ["EP-00-T02"]
        entregaveis: ["schemas/client-registration.schema.json", "src/emcp_bus/identity/models.py"]
        criterios_aceite: ["Dado um client_id não registrado, quando consultado, então retorna 'not found' determinístico."]
        padroes_abertos: ["JSON Schema"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-01"]

      - id: EP-01-T03
        titulo: "Middleware de autenticação do Gateway"
        descricao: "Validação de access token OAuth2/OIDC (assinatura via JWKS do Keycloak, audience, expiração) antes de qualquer processamento MCP; identidade nunca lida de clientInfo autodeclarado."
        componente: "identity"
        tipo: seguranca
        prioridade: must
        estimativa: M
        depende_de: ["EP-01-T01", "EP-01-T02"]
        entregaveis: ["src/emcp_bus/identity/authn.py", "tests/unit/test_authn.py"]
        criterios_aceite: ["Dado um token com audience incorreta, quando usado em qualquer request, então é rejeitado (Teste 8, §45).", "Dado um `clientInfo.name` autodeclarado divergente do token, quando processado, então a identidade usada é a do token, não a declarada."]
        padroes_abertos: ["OAuth 2.1", "OpenID Connect"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-02", "Axiom 2", "ADR-001"]

      - id: EP-01-T04
        titulo: "Spike: workload identity / mTLS (extensão de produção)"
        descricao: "Documentar (sem implementar) como mTLS/cloud workload identity substituiria client_credentials em produção, como ponto de extensão do middleware EP-01-T03."
        componente: "identity"
        tipo: spike
        prioridade: could
        estimativa: P
        depende_de: ["EP-01-T03"]
        entregaveis: ["docs/adr/ADR-019-identity-extension.md"]
        criterios_aceite: ["Documento revisado explicita a interface de extensão sem exigir mudança de contrato no restante do Gateway."]
        padroes_abertos: ["mTLS"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§19", "ADR-019"]

      - id: EP-01-T05
        titulo: "Regra de shared client"
        descricao: "Validação (lint de config) que impede dois agentes distintos referenciarem o mesmo MCP Client quando seus client profiles nominais diferem (anti-pattern §18/§35)."
        componente: "identity"
        tipo: seguranca
        prioridade: should
        estimativa: P
        depende_de: ["EP-01-T02"]
        entregaveis: ["src/emcp_bus/identity/shared_client_lint.py"]
        criterios_aceite: ["Dado dois agentes configurados apontando ao mesmo client_id com client profiles diferentes, quando o lint roda, então falha com mensagem explicando o anti-pattern."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§18", "§35.4"]

  - epico_id: EP-02
    titulo: "Global Capability Registry e publishing pipeline"
    objetivo: "Permitir que service owners publiquem capabilities por pipeline governado, alimentando o Registry como control-plane asset (§6.6, §6.8, §23, §24)."
    secoes_readme: ["§6.6", "§6.8", "§17", "§23", "§24", "§39", "§40"]
    tarefas:
      - id: EP-02-T01
        titulo: "Schema de capability manifest"
        descricao: "YAML de manifesto (baseado no exemplo §6.8) + Pydantic + JSON Schema: nome canônico `<domain>.<capability>`, versão, owner, risk_tier, data_classification, side_effects, idempotent, requiredEntitlements, backend, lifecycle."
        componente: "registry"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-00-T02"]
        entregaveis: ["schemas/capability-manifest.schema.json", "config/capabilities/README.md (convenção de naming §39)"]
        criterios_aceite: ["Um manifesto sem `risk_tier` ou `owner` é rejeitado pelo schema."]
        padroes_abertos: ["JSON Schema", "SemVer"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-06", "RF-11", "ADR-009"]

      - id: EP-02-T02
        titulo: "Publishing pipeline (gate de validação)"
        descricao: "CLI/serviço que valida manifesto (schema, referência de policy existente em EP-03, health check do backend declarado) antes de permitir publicação — nenhum cadastro manual direto em produção."
        componente: "registry"
        tipo: feature
        prioridade: must
        estimativa: G
        depende_de: ["EP-02-T01"]
        entregaveis: ["src/emcp_bus/registry/pipeline.py", "tests/contract/test_publishing_gate.py"]
        criterios_aceite: ["Dado um manifesto com política inexistente referenciada, quando submetido ao pipeline, então é rejeitado com motivo.", "Dado um manifesto válido, quando aprovado, então aparece no Registry com status `active`."]
        padroes_abertos: ["JSON Schema"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-11", "ADR-011"]

      - id: EP-02-T03
        titulo: "Armazenamento e API de leitura do Registry"
        descricao: "Persistência (SQLite dev / Postgres compartilhado) do catálogo administrativo completo + API de leitura consumida por Gateway, Fabric e Offering Filter — distinta da visão por client."
        componente: "registry"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-00-T04", "EP-02-T01"]
        entregaveis: ["src/emcp_bus/registry/store.py", "src/emcp_bus/registry/api.py"]
        criterios_aceite: ["Dado o Registry populado, quando consultado por domínio, então retorna somente capabilities `active` daquele domínio."]
        padroes_abertos: ["OpenAPI 3.1"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-06"]

      - id: EP-02-T04
        titulo: "Máquina de estados de lifecycle"
        descricao: "Implementar nominate→review→register→publish→observe→(change|deprecate→retire) do §23 como status controlado, com transições auditadas (EP-08)."
        componente: "registry"
        tipo: feature
        prioridade: should
        estimativa: M
        depende_de: ["EP-02-T03"]
        entregaveis: ["src/emcp_bus/registry/lifecycle.py"]
        criterios_aceite: ["Uma capability não pode ir de `register` direto para `publish` sem passar por `review` aprovado."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§23"]

      - id: EP-02-T05
        titulo: "Manifests de exemplo (Sales, Finance)"
        descricao: "Seed data cobrindo tiers R1–R3: sales.customer.get/search (R1), sales.quote.create/update (R2), finance.payment.execute (R3, exige aprovação)."
        componente: "registry"
        tipo: feature
        prioridade: must
        estimativa: P
        depende_de: ["EP-02-T02", "EP-02-T03"]
        entregaveis: ["config/capabilities/sales/*.yaml", "config/capabilities/finance/*.yaml"]
        criterios_aceite: ["Todos os manifestos de seed passam pelo pipeline (EP-02-T02) sem intervenção manual."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§7.1", "§17"]

  - epico_id: EP-03
    titulo: "PDP / Policy Engine (OPA)"
    objetivo: "Avaliar entitlement policy e transaction policy de forma determinística e auditável, sem nunca conceder tool ausente do client entitlement (§6.5, §25)."
    secoes_readme: ["§6.5", "§16", "§25", "§42", "§48(3)"]
    tarefas:
      - id: EP-03-T01
        titulo: "Integração com OPA"
        descricao: "Serviço OPA no compose + client Python (REST) para avaliação de policies; contrato de decisão ALLOW/DENY/REQUIRE_APPROVAL."
        componente: "pdp"
        tipo: infra
        prioridade: must
        estimativa: M
        depende_de: ["EP-00-T04"]
        entregaveis: ["deploy/opa/", "src/emcp_bus/pdp/client.py"]
        criterios_aceite: ["Dado o OPA no ar, quando uma policy de teste é avaliada via client Python, então o resultado corresponde ao esperado pela suíte `opa test`."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: ["[NÃO-OSS]: nenhum — OPA é Apache-2.0"]
        rastreabilidade: ["ADR-025"]

      - id: EP-03-T02
        titulo: "Entitlement policy em Rego"
        descricao: "Policy `permit if requested_tool in entitlement(client)` (§25 Passo 1), com dados de entitlement carregados do client profile (EP-04-T01)."
        componente: "pdp"
        tipo: seguranca
        prioridade: must
        estimativa: M
        depende_de: ["EP-03-T01", "EP-04-T01"]
        entregaveis: ["config/policies/entitlement.rego", "tests/unit/policies/entitlement_test.rego"]
        criterios_aceite: ["Dado client=Sales.Read e tool=finance.createPayment, quando avaliado, então DENY (Teste 1/2, §45)."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-05", "Axiom 4", "ADR-025"]

      - id: EP-03-T03
        titulo: "Transaction policy em Rego"
        descricao: "Policy de argumentos/recursos (§25 Passo 2, exemplo quote.create: amount ≤ limit, region, classification)."
        componente: "pdp"
        tipo: seguranca
        prioridade: must
        estimativa: M
        depende_de: ["EP-03-T01"]
        entregaveis: ["config/policies/transaction.rego", "tests/unit/policies/transaction_test.rego"]
        criterios_aceite: ["Dado quote.create com amount acima do limite do client, quando avaliado, então DENY mesmo que a tool esteja no entitlement."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-05", "§6.5.B"]

      - id: EP-03-T04
        titulo: "Contrato de decisão do PDP"
        descricao: "Modelo Pydantic unificado de decisão (ALLOW/DENY/REQUIRE_APPROVAL + policy_version + reason_code) consumido pelo Gateway."
        componente: "pdp"
        tipo: feature
        prioridade: must
        estimativa: P
        depende_de: ["EP-03-T02", "EP-03-T03"]
        entregaveis: ["src/emcp_bus/pdp/models.py"]
        criterios_aceite: ["Toda resposta do PDP inclui policy_version e reason_code, nunca apenas um booleano."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§27 (campos de auditoria)"]

  - epico_id: EP-04
    titulo: "Entitlement Manager"
    objetivo: "Resolver e versionar o MaximumEntitlement por client, com provenance e invalidação em revogação (§6.9, §41)."
    secoes_readme: ["§6.9", "§7.1", "§7.2", "§17", "§31", "§41"]
    tarefas:
      - id: EP-04-T01
        titulo: "Schema de client profile"
        descricao: "YAML `config/clients profile` (§41 exemplo) + Pydantic + JSON Schema: name, owner, risk_ceiling, allowed_tools, restrictions, credential_policy, audit level."
        componente: "entitlement"
        tipo: feature
        prioridade: must
        estimativa: P
        depende_de: ["EP-00-T02"]
        entregaveis: ["schemas/client-profile.schema.json", "config/clients/profiles/*.yaml (Sales.Read/Write/Approve, Finance.*)"]
        criterios_aceite: ["Um client profile sem `risk_ceiling` é rejeitado pelo schema."]
        padroes_abertos: ["JSON Schema"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-01", "ADR-008", "P6"]

      - id: EP-04-T02
        titulo: "Serviço resolveMaximumEntitlement"
        descricao: "Combina client profile + decisão de entitlement do PDP, produz versão cacheável (`entitlementVersion`) com provenance (qual regra incluiu/restringiu cada capability)."
        componente: "entitlement"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-04-T01", "EP-03-T02", "EP-03-T04"]
        entregaveis: ["src/emcp_bus/entitlement/manager.py"]
        criterios_aceite: ["Dado client=Sales.Write, quando resolvido, então o conjunto retornado é exatamente {customer.search, customer.get, order.get, inventory.check, quote.create, quote.update} (§7.1)."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-01", "RF-12", "Axiom 2"]

      - id: EP-04-T03
        titulo: "Revogação e invalidação de cache"
        descricao: "Endpoint/evento de revogação de client ou policy que invalida entitlement cacheado e emite `policy_changed`/`client_revoked` (consumido por EP-08 e EP-05)."
        componente: "entitlement"
        tipo: seguranca
        prioridade: must
        estimativa: M
        depende_de: ["EP-04-T02"]
        entregaveis: ["src/emcp_bus/entitlement/revocation.py"]
        criterios_aceite: ["Dado um client revogado, quando uma nova tools/call chega, então é negada mesmo com cache de tools/list ainda não expirado (Teste 6, §45)."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-08"]

      - id: EP-04-T04
        titulo: "Contrato de versão de entitlement"
        descricao: "Expor `entitlementVersion` de forma consistente para PDP, Gateway e Orchestrator, usado na correlação ponta a ponta (RF-17)."
        componente: "entitlement"
        tipo: feature
        prioridade: should
        estimativa: P
        depende_de: ["EP-04-T02"]
        entregaveis: ["src/emcp_bus/entitlement/models.py (EntitlementVersion)"]
        criterios_aceite: ["Toda resposta de resolveMaximumEntitlement inclui entitlementVersion não-nulo."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-17"]

  - epico_id: EP-05
    titulo: "MCP Gateway / PEP"
    objetivo: "Implementar o PEP: discovery filtrado, execution enforcement, caching privado, anti-bypass e fail-closed (§6.4, §9, §10, §12, §13, §21, §22, §38)."
    secoes_readme: ["§6.4", "§9", "§10", "§11", "§12", "§13", "§21", "§22", "§35.3", "§38", "§42"]
    tarefas:
      - id: EP-05-T01
        titulo: "Gateway skeleton (walking skeleton)"
        descricao: "Servidor MCP (SDK oficial `mcp`, transporte Streamable HTTP) que recebe tools/list e tools/call e os encaminha, sem enforcement ainda, a um roteamento estático de um único MCP Server de exemplo."
        componente: "gateway"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-00-T04", "EP-06-T02"]
        entregaveis: ["src/emcp_bus/gateway/server.py"]
        criterios_aceite: ["Dado o compose no ar (perfil core), quando um cliente MCP chama tools/list e tools/call, então recebe resposta do example server via Gateway, com trace_id visível no log (EP-08-T01)."]
        padroes_abertos: ["MCP", "JSON-RPC 2.0"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: "Roteamento/proxy simples — pertence ao núcleo do bus em Python puro, não a um grafo de agente."
        riscos: []
        rastreabilidade: ["Marco M0"]

      - id: EP-05-T02
        titulo: "Filtered tools/list"
        descricao: "Implementar sequência do §9: autenticar client (EP-01-T03), resolver MaximumEntitlement (EP-04-T02), obter catálogo do Registry (EP-02-T03), retornar interseção."
        componente: "gateway"
        tipo: seguranca
        prioridade: must
        estimativa: M
        depende_de: ["EP-05-T01", "EP-01-T03", "EP-04-T02"]
        entregaveis: ["src/emcp_bus/gateway/discovery.py"]
        criterios_aceite: ["Dado client=Sales.Read, quando tools/list é chamado, então finance.createPayment NUNCA aparece na resposta (Teste 1, §45)."]
        padroes_abertos: ["MCP"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-03", "P4", "P5 (invariantes §9)"]

      - id: EP-05-T03
        titulo: "Cache privado de tools/list"
        descricao: "Cache com chave = client_identity+authorization_context+policy_version+params, cacheScope=private, TTL curto configurável, invalidado em revogação (EP-04-T03). Verificado em 2026-09-11: SEP-2549 (ttlMs/cacheScope, GA na revisão 2026-07-28) já é suportado nativamente pelo SDK Python `mcp` v2 via `cache_hints=` no servidor — usar o primitivo do SDK em vez de reimplementar cache HTTP manual."
        componente: "gateway"
        tipo: seguranca
        prioridade: must
        estimativa: M
        depende_de: ["EP-05-T02"]
        entregaveis: ["src/emcp_bus/gateway/cache.py"]
        criterios_aceite: ["Dado catálogo cacheado de Sales.Read, quando Finance.Payments faz a mesma requisição, então nunca recebe o cache de Sales.Read (Teste 5, §45)."]
        padroes_abertos: ["MCP 2026-07-28 (SEP-2549) — confirmado via busca web em 2026-09-11"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§13", "Threat: Cache leakage (§28)"]

      - id: EP-05-T04
        titulo: "Enforcement de tools/call"
        descricao: "Reautorização independente do discovery (§10): client capability check → transaction policy → REQUIRE_APPROVAL/ALLOW/DENY determinístico."
        componente: "gateway"
        tipo: seguranca
        prioridade: must
        estimativa: G
        depende_de: ["EP-05-T01", "EP-03-T04"]
        entregaveis: ["src/emcp_bus/gateway/enforcement.py"]
        criterios_aceite: ["Dado client=Sales.Read chamando diretamente tools/call(finance.createPayment) sem nunca ter visto a tool em tools/list, quando executado, então DENY determinístico (Teste 2, §45)."]
        padroes_abertos: ["MCP"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-04", "Axiom 5", "ADR-003"]

      - id: EP-05-T05
        titulo: "Rate limiting e quota por client"
        descricao: "Limites configuráveis por client profile, aplicados no Gateway antes do roteamento ao Fabric."
        componente: "gateway"
        tipo: seguranca
        prioridade: should
        estimativa: M
        depende_de: ["EP-05-T01"]
        entregaveis: ["src/emcp_bus/gateway/rate_limit.py"]
        criterios_aceite: ["Dado um client excedendo seu limite configurado, quando chama tools/call, então recebe 429/DENY determinístico sem consultar backend."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RNF-Disponibilidade (§37)", "Threat: bulk exfiltration (§28)"]

      - id: EP-05-T06
        titulo: "Fail-closed em indisponibilidade"
        descricao: "Implementar tabela do §38: PDP indisponível → fail closed; Registry indisponível → cache válido dentro do contexto; approval service indisponível → nega high-risk."
        componente: "gateway"
        tipo: seguranca
        prioridade: must
        estimativa: M
        depende_de: ["EP-05-T04"]
        entregaveis: ["src/emcp_bus/gateway/failure_policy.py"]
        criterios_aceite: ["Dado o OPA fora do ar, quando qualquer tools/call chega, então a resposta é DENY, nunca ALLOW por omissão."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RNF-Disponibilidade (§37)", "§38"]

      - id: EP-05-T07
        titulo: "Prevenção de bypass do PEP"
        descricao: "Isolamento de rede no compose (Fabric/backends só aceitam origem do Gateway) + detecção de chamadas que não atravessaram o PEP em telemetria."
        componente: "gateway"
        tipo: seguranca
        prioridade: must
        estimativa: M
        depende_de: ["EP-06-T01"]
        entregaveis: ["docker-compose network segmentation", "src/emcp_bus/audit/bypass_detection.py"]
        criterios_aceite: ["Dado acesso direto tentado ao Fabric/backend a partir de fora da rede do Gateway, quando tentado, então falha (Teste 7, §45)."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§21", "ADR-007", "Axiom 7"]

      - id: EP-05-T08
        titulo: "Consistência header/body (revisão MCP 2026-07-28)"
        descricao: "Validar consistência entre `Mcp-Method`/`Mcp-Name` e o corpo JSON-RPC antes de decisão de autorização, produzindo representação canônica única (§22). Verificado em 2026-09-11: a revisão 2026-07-28 é real (GA, SEP-2243) e o SDK Python `mcp` v2 já expõe esses headers nativamente no transporte Streamable HTTP — a tarefa é validar/canonicalizar, não implementar o parsing do zero."
        componente: "gateway"
        tipo: seguranca
        prioridade: should
        estimativa: M
        depende_de: ["EP-05-T04"]
        entregaveis: ["src/emcp_bus/gateway/canonical_request.py"]
        criterios_aceite: ["Dado header Mcp-Name divergente do `params.name` do body, quando recebido, então a requisição é rejeitada por ambiguidade, nunca processada com um dos dois valores 'na confiança'."]
        padroes_abertos: ["MCP 2026-07-28 (SEP-2243) — confirmado via busca web em 2026-09-11"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§22"]

  - epico_id: EP-06
    titulo: "Enterprise MCP Fabric e servidores de domínio de exemplo"
    objetivo: "Resolver capability em implementação concreta via roteamento por domínio, com servidores MCP de exemplo demonstrando risk tiers (§6.7, §32, §34)."
    secoes_readme: ["§6.7", "§17", "§32", "§34"]
    tarefas:
      - id: EP-06-T01
        titulo: "Fabric core (capability router)"
        descricao: "Router que resolve `<domain>.<capability>` para o adapter/backend correto usando o Registry (EP-02-T03), com retries/timeouts e telemetria."
        componente: "fabric"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-02-T03", "EP-06-T02", "EP-06-T03"]
        entregaveis: ["src/emcp_bus/fabric/router.py"]
        criterios_aceite: ["Dado uma capability publicada em Sales, quando roteada, então chega ao MCP Server de Sales, não ao de Finance."]
        padroes_abertos: ["MCP"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: "Roteamento determinístico simples — não é fluxo de agente."
        riscos: []
        rastreabilidade: ["RF component (§6.7)"]

      - id: EP-06-T02
        titulo: "MCP Server de exemplo: domínio Sales"
        descricao: "Servidor MCP (SDK oficial, padrão FastMCP — `from mcp.server.fastmcp import FastMCP`, `@mcp.tool()`, transporte `streamable-http` — confirmado como padrão de referência em ADR-022) com customer.search/get (R1), order.get (R1), inventory.check (R1), quote.create/update (R2) contra dados mockados. O servidor permanece 'burro': nunca decide autorização (ADR-023) — toda decisão vem do Gateway/PDP antes da chamada chegar aqui."
        componente: "fabric"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-00-T01"]
        entregaveis: ["services/example_mcp_servers/sales_domain/"]
        criterios_aceite: ["Cada tool expõe input/output schema conforme manifesto correspondente (EP-02-T05)."]
        padroes_abertos: ["MCP"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§7.1", "Marco M0"]

      - id: EP-06-T03
        titulo: "MCP Server de exemplo: domínio Finance"
        descricao: "Servidor MCP com invoice.get (R1), payment.create (R2), payment.execute (R3, sujeito a aprovação — EP-14) contra dados mockados."
        componente: "fabric"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-00-T01"]
        entregaveis: ["services/example_mcp_servers/finance_domain/"]
        criterios_aceite: ["payment.execute >= 10k dispara REQUIRE_APPROVAL na policy correspondente (§26)."]
        padroes_abertos: ["MCP"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§17", "§26"]

      - id: EP-06-T04
        titulo: "Adapter REST genérico"
        descricao: "Padrão de adapter reutilizável que traduz uma capability MCP para uma chamada REST (documentada via OpenAPI) de backend, usado pelos dois domínios."
        componente: "fabric"
        tipo: feature
        prioridade: should
        estimativa: M
        depende_de: ["EP-06-T01"]
        entregaveis: ["src/emcp_bus/fabric/adapters/rest_adapter.py"]
        criterios_aceite: ["Dado um novo backend descrito por OpenAPI, quando configurado via YAML, então nenhum código Python novo é necessário para expô-lo (apenas config)."]
        padroes_abertos: ["OpenAPI 3.1"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§6.7"]

  - epico_id: EP-07
    titulo: "Downstream identity (inbound vs outbound)"
    objetivo: "Evitar blind token passthrough — identidade de entrada no Fabric não é reutilizada automaticamente no backend (§20)."
    secoes_readme: ["§20", "§35.6"]
    tarefas:
      - id: EP-07-T01
        titulo: "Componente de outbound identity"
        descricao: "Antes de chamar o backend, o Fabric obtém credencial apropriada (token exchange RFC 8693 via Keycloak, ou service account por adapter) em vez de repassar o token do client."
        componente: "downstream"
        tipo: seguranca
        prioridade: must
        estimativa: M
        depende_de: ["EP-06-T04", "EP-01-T01"]
        entregaveis: ["src/emcp_bus/downstream/identity.py"]
        criterios_aceite: ["Dado um tools/call autorizado, quando a chamada chega ao backend mock, então o token usado no backend é diferente do token do MCP Client (audience distinta)."]
        padroes_abertos: ["OAuth 2.1 (token exchange RFC 8693)"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-09", "ADR-006", "ADR-020"]

      - id: EP-07-T02
        titulo: "Config de credenciais por backend"
        descricao: "Schema YAML `config/backends/*.yaml` (sem segredos inline — via ${ENV_VAR}, ver EP-00-T05) declarando o modelo de outbound identity por backend."
        componente: "downstream"
        tipo: feature
        prioridade: must
        estimativa: P
        depende_de: ["EP-07-T01", "EP-00-T05"]
        entregaveis: ["schemas/backend-credentials.schema.json", "config/backends/*.yaml"]
        criterios_aceite: ["Um arquivo com segredo literal (não ${ENV_VAR}) é rejeitado pelo schema/CI."]
        padroes_abertos: ["JSON Schema"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-09", "ADR-020"]

  - epico_id: EP-08
    titulo: "Auditoria, correlação e observabilidade"
    objetivo: "Tornar toda decisão relevante rastreável ponta a ponta, sem registrar segredos (§27, RF-17)."
    secoes_readme: ["§27", "§28 (traceability gap)", "RF-17"]
    tarefas:
      - id: EP-08-T01
        titulo: "Tracing OTel de base"
        descricao: "Instrumentação OpenTelemetry (traces/metrics/logs) com propagação W3C Trace Context em Gateway, Fabric e serviços de exemplo."
        componente: "audit"
        tipo: observabilidade
        prioridade: must
        estimativa: M
        depende_de: ["EP-00-T01"]
        entregaveis: ["src/emcp_bus/common/otel.py", "deploy/otel/collector-config.yaml"]
        criterios_aceite: ["Dado um tools/call ponta a ponta, quando inspecionado no coletor, então um único trace_id conecta Gateway→Fabric→backend mock (Marco M0)."]
        padroes_abertos: ["OpenTelemetry", "W3C Trace Context"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RNF-Performance (§37)", "Marco M0"]

      - id: EP-08-T02
        titulo: "Emissor de eventos de auditoria"
        descricao: "Taxonomia de eventos do §27 (client_authenticated, tools_list_filtered, tool_call_denied, etc.) com sink append-only (arquivo em dev, Postgres opcional), excluindo tokens/secrets/dados sensíveis. Adota o vocabulário IC/NOC/GRL (evento de negócio-jornada / operacional-erro / guardrail-governança) do Agent Platform OCI (ADR-022) como categorização do `EventEnvelope`, carregando `decisionId`/`policyDecisionId`/`entitlementVersion` (ADR-017) como campos extras do payload em vez de reinventar taxonomia."
        componente: "audit"
        tipo: observabilidade
        prioridade: must
        estimativa: M
        depende_de: ["EP-08-T01"]
        entregaveis: ["src/emcp_bus/audit/events.py", "src/emcp_bus/audit/sink.py"]
        criterios_aceite: ["Um evento de auditoria nunca contém o valor de um token/secret, apenas seu hash/referência (§27, 'Não registrar').", "Toda decisão DENY do PDP gera um evento `tool_call_denied` com reason_code.", "Todo evento é classificável em IC (negócio/jornada), NOC (operacional/erro) ou GRL (guardrail/governança)."]
        padroes_abertos: ["CloudEvents"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-07", "ADR-022"]

      - id: EP-08-T03
        titulo: "Correlação ponta a ponta"
        descricao: "Encadear profileVersion + entitlementVersion + decisionId + policyDecisionId + mcpRequestId através de todos os componentes, expostos no trace e no evento de auditoria."
        componente: "audit"
        tipo: observabilidade
        prioridade: must
        estimativa: M
        depende_de: ["EP-08-T02", "EP-04-T04"]
        entregaveis: ["src/emcp_bus/audit/correlation.py"]
        criterios_aceite: ["Dada uma jornada completa (perfil→entitlement→NBA→execução), quando consultada por decisionId, então todos os eventos relacionados são recuperáveis (fecha Threat: Traceability gap, §28)."]
        padroes_abertos: ["W3C Trace Context"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-17", "ADR-017"]

      - id: EP-08-T04
        titulo: "Stack local de observabilidade"
        descricao: "OTel Collector + backend de traces OSS (Jaeger ou Tempo) no compose (`llm-observability` profile opcional para não pesar o M0)."
        componente: "audit"
        tipo: infra
        prioridade: should
        estimativa: P
        depende_de: ["EP-08-T01"]
        entregaveis: ["compose services `otel-collector`, `jaeger`"]
        criterios_aceite: ["Traces do EP-08-T01 são visíveis na UI do Jaeger local."]
        padroes_abertos: ["OpenTelemetry"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: []

  - epico_id: EP-09
    titulo: "Profile Intelligence (contrato genérico)"
    objetivo: "Expor uma visão de perfil versionada e substituível que apenas ordena/reduz candidatas, nunca concede entitlement (§6.10)."
    secoes_readme: ["§6.10", "Axiom 11"]
    tarefas:
      - id: EP-09-T01
        titulo: "Contrato ProfileView"
        descricao: "Schema JSON + Pydantic do exemplo §6.10 (subjectRef, profileVersion, segments, attributes, reasonCodes, expiresAt)."
        componente: "profile_intelligence"
        tipo: feature
        prioridade: must
        estimativa: P
        depende_de: ["EP-00-T02"]
        entregaveis: ["schemas/profile-view.schema.json", "src/emcp_bus/profile_intelligence/models.py"]
        criterios_aceite: ["Um ProfileView sem `expiresAt` ou `profileVersion` é rejeitado pelo schema."]
        padroes_abertos: ["JSON Schema"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-13", "ADR-013"]

      - id: EP-09-T02
        titulo: "Stub de referência (regras determinísticas)"
        descricao: "Implementação plugável (`ProfileIntelligenceProvider`) baseada em regras sobre atributos sintéticos (ver P7) — não implementa clusterização real nem taxonomia proprietária."
        componente: "profile_intelligence"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-09-T01"]
        entregaveis: ["src/emcp_bus/profile_intelligence/rule_based_provider.py"]
        criterios_aceite: ["Dado o mesmo subjectRef e mesma janela temporal, quando resolvido duas vezes, então produz o mesmo profileVersion (determinismo para fins de demo)."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: "Regra determinística, sem estado conversacional — não requer LangGraph."
        riscos: ["Risco de escopo: tentar implementar clusterização 'de verdade' sem dataset real — mitigado por P7."]
        rastreabilidade: ["RF-13", "P7"]

      - id: EP-09-T03
        titulo: "Guardrails de governança de dados"
        descricao: "subjectRef pseudonimizado, log de lineage de features/versão/janela temporal, stub de monitor de drift (§6.10, requisitos de governança)."
        componente: "profile_intelligence"
        tipo: seguranca
        prioridade: should
        estimativa: M
        depende_de: ["EP-09-T02"]
        entregaveis: ["src/emcp_bus/profile_intelligence/governance.py"]
        criterios_aceite: ["Nenhum ProfileView expõe PII direta — apenas subjectRef pseudonimizado (Threat: Sensitive attribute leakage, §28)."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§6.10", "Threat §28"]

  - epico_id: EP-10
    titulo: "Offering Filter"
    objetivo: "Intersectar catálogo ativo, entitlement, perfil e contexto/consentimento sem nunca reintroduzir capability fora do entitlement (§6.11, §7.3)."
    secoes_readme: ["§6.11", "§7.3", "Axiom 8/11"]
    tarefas:
      - id: EP-10-T01
        titulo: "Serviço Offering Filter"
        descricao: "FilteredOfferings = ActiveCatalog ∩ MaximumEntitlement ∩ SubjectAndContextConstraints, consumindo Registry (EP-02), Entitlement Manager (EP-04), ProfileView (EP-09) e consentimento/contexto declarados."
        componente: "offering_filter"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-02-T03", "EP-04-T02", "EP-09-T01"]
        entregaveis: ["src/emcp_bus/offering_filter/service.py"]
        criterios_aceite: ["Dado um item fora do MaximumEntitlement do client, quando o filtro roda com qualquer score de perfil, então o item nunca aparece em FilteredOfferings."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: "Interseção de conjuntos determinística — não é fluxo de agente."
        riscos: []
        rastreabilidade: ["RF-14", "ADR-014"]

      - id: EP-10-T02
        titulo: "Testes de propriedade da invariante de subconjunto"
        descricao: "Testes baseados em propriedade (ex.: Hypothesis) provando FilteredOfferings ⊆ MaximumEntitlement ⊆ GlobalCatalog para entradas geradas aleatoriamente (§7.3)."
        componente: "offering_filter"
        tipo: teste
        prioridade: must
        estimativa: M
        depende_de: ["EP-10-T01"]
        entregaveis: ["tests/unit/test_offering_filter_invariants.py"]
        criterios_aceite: ["1000+ casos gerados aleatoriamente não produzem nenhuma violação da invariante de subconjunto."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§7.3", "RF-14"]

  - epico_id: EP-11
    titulo: "Service Orchestrator (NBA/NBO)"
    objetivo: "Calcular a Next Best Action e a Next Best Offer (NBA/NBO) como decisão de orquestração — nunca de autorização — sobre estado de jornada, regras, guardrails, memória e o universo de serviços/ofertas/ações que o MCP Fabric expõe (§6.12, §10.1). Por ADR-024, este componente é deliberadamente robusto o suficiente (modelo de decisão pluggable, incluindo IA de ranking/recomendação) para operar tanto como fonte de FilteredOfferings para uma plataforma de orquestração externa (modo A) quanto como o único cérebro de decisão de uma integração ponta a ponta, substituindo a camada de decisão dessa plataforma externa (modo B) — modularidade + compatibilidade = escolha do adotante, nunca uma imposição da RI."
    secoes_readme: ["§6.12", "§10.1", "P9 (NBA não é autorização)", "Axiom 12", "ADR-024"]
    tarefas:
      - id: EP-11-T01
        titulo: "Contrato DecisionContext"
        descricao: "Modelo Pydantic versionado combinando ProfileView, identidade autenticada, EntitlementLimits, FilteredOfferings e RuntimeContext (§1, contrato formal)."
        componente: "orchestrator"
        tipo: feature
        prioridade: must
        estimativa: P
        depende_de: ["EP-09-T01", "EP-04-T04", "EP-10-T01"]
        entregaveis: ["src/emcp_bus/orchestrator/decision_context.py"]
        criterios_aceite: ["DecisionContext é serializável/versionado e rejeita construção sem entitlementVersion."]
        padroes_abertos: ["JSON Schema"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§1"]

      - id: EP-11-T02
        titulo: "Grafo de jornada em LangGraph"
        descricao: "StateGraph com estado de jornada, objetivo e memória; checkpointer SQLite (dev, com ponto de extensão para mongodb/produção — padrão de providers plugáveis do ADR-022). Nós fixos: resolve profile → resolve entitlement → filter offerings → decide NBA, seguindo o padrão de grafo corporativo fixo (dev só acrescenta nós de domínio, nunca mexe na espinha dorsal) descrito em `docs/research/hoshikawa-agent-platform-oci.md`."
        componente: "orchestrator"
        tipo: feature
        prioridade: must
        estimativa: G
        depende_de: ["EP-11-T01"]
        entregaveis: ["src/emcp_bus/orchestrator/graph.py", "src/emcp_bus/orchestrator/state.py (TypedDict do estado de jornada)"]
        criterios_aceite: ["Dado um checkpoint salvo, quando o processo reinicia, então a jornada retoma do último estado sem reprocessar do zero."]
        padroes_abertos: []
        usa_langgraph: true
        usa_langfuse: false
        justificativa_langgraph_langfuse: "Fluxo com estado, múltiplos passos e necessidade de checkpointing/retomada — critério explícito da seção 6 do superprompt para uso de LangGraph."
        riscos: ["Overhead de checkpointing para um fluxo ainda simples na RI — mitigado mantendo o grafo mínimo até M3"]
        rastreabilidade: ["RF-15", "ADR-015", "ADR-022"]

      - id: EP-11-T03
        titulo: "Nó de decisioning (NBA/NBO)"
        descricao: "Função de decisão versionada combinando rules + guardrails sobre DecisionContext, produzindo NBA/NBO (§6.13, exemplo JSON) e persistindo a trilha de decisão. Modelo de decisão pluggable (interface `NBADecisionModel`): implementação de referência determinística (regras/prioridade) na RI, com ponto de extensão explícito para um modelo de IA de ranking/recomendação sobre `FilteredOfferings` (serviços/ofertas/ações do Fabric) — sempre restrito ao universo já filtrado por entitlement (Axiom 8/11), nunca decidindo autorização."
        componente: "orchestrator"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-11-T02"]
        entregaveis: ["src/emcp_bus/orchestrator/decisioning.py", "src/emcp_bus/orchestrator/nba_model.py (interface pluggable)"]
        criterios_aceite: ["Toda NBA/NBO emitida inclui reasonCodes, policyContext e expiresAt (§6.13).", "Trocar a implementação de `NBADecisionModel` (regras → modelo de IA) não exige mudança de contrato em EP-05/EP-03/EP-04 — a superfície de autorização é idêntica independentemente do modelo de decisão."]
        padroes_abertos: []
        usa_langgraph: true
        usa_langfuse: false
        justificativa_langgraph_langfuse: "Nó do grafo de jornada definido em EP-11-T02."
        riscos: []
        rastreabilidade: ["RF-15", "ADR-024"]

      - id: EP-11-T04
        titulo: "Recálculo e degradação segura"
        descricao: "Branch DENY/indisponível do fluxo §10.1: recalcular NBA, degradar com segurança ou encerrar jornada quando o Gateway nega a execução — a NBA negada NUNCA é substituída por bypass."
        componente: "orchestrator"
        tipo: seguranca
        prioridade: must
        estimativa: M
        depende_de: ["EP-11-T03", "EP-05-T04"]
        entregaveis: ["src/emcp_bus/orchestrator/fallback.py"]
        criterios_aceite: ["Dado um DENY do Gateway, quando recebido pelo Orchestrator, então nenhuma tentativa de execução direta ao Fabric ocorre — apenas recálculo ou encerramento auditado."]
        padroes_abertos: []
        usa_langgraph: true
        usa_langfuse: false
        justificativa_langgraph_langfuse: "Edge condicional do StateGraph de EP-11-T02."
        riscos: []
        rastreabilidade: ["§10.1", "Axiom 12", "P9"]

      - id: EP-11-T05
        titulo: "Interrupção human-in-the-loop"
        descricao: "Nó de interrupção do grafo (`interrupt`) disparado quando a NBA envolve capability REQUIRE_APPROVAL, integrando com EP-14."
        componente: "orchestrator"
        tipo: feature
        prioridade: should
        estimativa: M
        depende_de: ["EP-11-T03"]
        entregaveis: ["src/emcp_bus/orchestrator/hitl_node.py"]
        criterios_aceite: ["Dada uma NBA de alto risco, quando o grafo chega ao nó de aprovação, então a execução pausa até resposta de EP-14, sem timeout silencioso que vire ALLOW."]
        padroes_abertos: []
        usa_langgraph: true
        usa_langfuse: false
        justificativa_langgraph_langfuse: "Human-in-the-loop com pausa/retomada de estado — critério explícito da seção 6 do superprompt."
        riscos: []
        rastreabilidade: ["RF-10", "§26"]

  - epico_id: EP-12
    titulo: "Agent Runtime e channel adapters"
    objetivo: "Traduzir a NBA em execução coordenada — sessão, contexto mínimo, handoff — sem nunca substituir o token do MCP Client (§6.13)."
    secoes_readme: ["§6.13", "ADR-016"]
    tarefas:
      - id: EP-12-T01
        titulo: "Serviço de dispatch"
        descricao: "Consome o objeto de dispatch da NBA (§6.13, exemplo JSON), gerencia sessão/correlação e invoca o MCP Client correspondente ao agente/canal selecionado."
        componente: "agent_runtime"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-11-T03", "EP-01-T02"]
        entregaveis: ["src/emcp_bus/agent_runtime/dispatcher.py"]
        criterios_aceite: ["O Agent Runtime nunca gera ou armazena credenciais próprias — usa exclusivamente o MCP Client já registrado (EP-01)."]
        padroes_abertos: ["MCP"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: "Dispatch é invocação direta de um MCP Client já autenticado — não há estado cíclico próprio aqui (o estado vive no Orchestrator)."
        riscos: []
        rastreabilidade: ["RF-16", "ADR-016"]

      - id: EP-12-T02
        titulo: "Channel adapter conversacional"
        descricao: "Um adapter concreto (app/conversacional) para a demo da RI, encapsulando diferenças de canal citadas em §6.13/§3.3."
        componente: "agent_runtime"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-12-T01"]
        entregaveis: ["src/emcp_bus/agent_runtime/channels/conversational.py"]
        criterios_aceite: ["Uma NBA com channel=app é entregue ao adapter correto; um channel não suportado falha de forma explícita, não silenciosa."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-16"]

      - id: EP-12-T03
        titulo: "Handoff entre agentes"
        descricao: "Lógica de handoff (ex.: engagement-assistant → especialista de domínio) coordenada como subgrafo LangGraph, preservando contexto mínimo necessário e correlação. Inspirado no padrão de dois níveis do Agent Platform OCI (ADR-022): handoff intra-processo via aresta condicional de retorno, e um campo de metadata análogo a `metadata.handover_backend` quando o handoff cruza para outro agente/serviço. Restrição de segurança explícita (ADR-023): o campo de handoff é só um sinal de intenção de roteamento — a tools/list e tools/call do agente-destino continuam sendo autorizadas do zero pelo Gateway/PDP (EP-05), nunca herdadas do agente de origem."
        componente: "agent_runtime"
        tipo: feature
        prioridade: could
        estimativa: M
        depende_de: ["EP-12-T01"]
        entregaveis: ["src/emcp_bus/agent_runtime/handoff_graph.py"]
        criterios_aceite: ["Dado um handoff, quando concluído, então o novo agente recebe apenas o contexto mínimo necessário, não o histórico bruto completo.", "O MCP Client/entitlement do agente-destino após handoff é resolvido independentemente, nunca herdado do agente de origem."]
        padroes_abertos: []
        usa_langgraph: true
        usa_langfuse: false
        justificativa_langgraph_langfuse: "Coordenação multiagente com handoff — critério explícito da seção 6 do superprompt (padrão supervisor/handoff)."
        riscos: ["Feature poderia ser considerada fora do essencial da RI — marcada `could`, não bloqueia marcos principais."]
        rastreabilidade: ["§6.13", "ADR-022", "ADR-023"]

      - id: EP-12-T04
        titulo: "Identity Resolver / BusinessContext"
        descricao: "Adota o padrão `identity.yaml`/BusinessContext do Agent Platform OCI (ADR-022): aliases declarativos de nomes de canal → chaves canônicas de negócio (ex.: customer_key, contract_key, session_key), usados para montar argumentos de tool de forma padronizada. É puramente normalização de identidade de negócio — nunca decide autorização (a diferença explícita do achado do ADR-023: aqui o campo resolvido não deve, em nenhuma hipótese, alimentar a decisão do PDP)."
        componente: "agent_runtime"
        tipo: feature
        prioridade: should
        estimativa: M
        depende_de: ["EP-12-T01"]
        entregaveis: ["schemas/identity-resolver.schema.json", "config/orchestrator/identity.yaml", "src/emcp_bus/agent_runtime/identity_resolver.py"]
        criterios_aceite: ["Dado um payload de canal com um alias declarado (ex.: `msisdn`), quando resolvido, então produz a chave canônica correta (`customer_key`).", "O resultado do Identity Resolver nunca é aceito como entrada do PDP (EP-03) — apenas do Fabric/MCP Parameter Mapping."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["ADR-022", "ADR-023"]

  - epico_id: EP-13
    titulo: "Agente de exemplo e instrumentação Langfuse"
    objetivo: "Demonstrar um agente LLM real consumindo o catálogo filtrado, com observabilidade de LLM via Langfuse self-hosted e mascaramento de PII (§6.1). Por ADR-024, o objetivo final do épico vai além de um único agente: demonstrar a posição de 'elevação a Enterprise' do E-MCP-BUS — múltiplos backends/agentes (padrão Agent Platform OCI/Hoshikawa), cada um com seu próprio MCP Client e entitlement, orquestrados por um Global Supervisor acima do bus, sem que a troca de backend amplie privilégio (EP-13-T05)."
    secoes_readme: ["§6.1", "§14", "§29"]
    tarefas:
      - id: EP-13-T01
        titulo: "Agente conversacional de exemplo"
        descricao: "Agente LLM com tool-calling restrito ao catálogo retornado por tools/list do client atribuído (demonstra P1–P4 do §1: agente não escolhe entitlement). Instrumentação híbrida conforme ADR-022: span técnico automático por etapa do agente + eventos de negócio manuais e fail-open (IC/NOC/GRL, ver EP-08-T02) — um erro no observer nunca derruba a jornada."
        componente: "example_agent"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-05-T02", "EP-05-T04"]
        entregaveis: ["agents/example_agent/"]
        criterios_aceite: ["Cenário do §29 (prompt injection pedindo finance.createPayment) reproduzido: o agente tenta, o Gateway nega (Teste 3, §45)."]
        padroes_abertos: ["MCP"]
        usa_langgraph: false
        usa_langfuse: true
        justificativa_langgraph_langfuse: "Chamadas reais a LLM (tokens, custo, latência) precisam de tracing de generation — critério explícito da seção 6 do superprompt para uso de Langfuse."
        riscos: []
        rastreabilidade: ["§6.1", "§14", "§29", "ADR-022"]

      - id: EP-13-T02
        titulo: "Langfuse self-hosted no compose"
        descricao: "Deploy da edição OSS do Langfuse (perfil `llm-observability`) com exportação de traces via OTel a partir do agente e do Orchestrator. Stack de referência confirmada em `docs/research/hoshikawa-agent-platform-oci.md` (ADR-022): langfuse-web + langfuse-worker + PostgreSQL + ClickHouse + Redis + MinIO. Habilitar instrumentação automática de chamadas LLM compatíveis com OpenAI (equivalente a `ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION`) para captar tokens/custo/latência sem código manual por chamada."
        componente: "example_agent"
        tipo: infra
        prioridade: must
        estimativa: M
        depende_de: ["EP-08-T01"]
        entregaveis: ["deploy/langfuse/docker-compose.override.yml"]
        criterios_aceite: ["Uma execução do agente de exemplo aparece na UI do Langfuse com spans de generation, tokens e latência."]
        padroes_abertos: ["OpenTelemetry"]
        usa_langgraph: false
        usa_langfuse: true
        justificativa_langgraph_langfuse: "Infra de suporte à instrumentação definida em EP-13-T01."
        riscos: ["[NÃO-OSS]: recursos de billing/RBAC avançado do Langfuse Cloud não são usados — apenas a edição self-hosted/OSS."]
        rastreabilidade: ["§6 (seção Langfuse do superprompt)", "ADR-022"]

      - id: EP-13-T03
        titulo: "Redação de PII/segredos antes do trace"
        descricao: "Camada de mascaramento aplicada a prompts/outputs antes de enviar ao Langfuse — obrigatória por regra da seção 6 do superprompt."
        componente: "example_agent"
        tipo: seguranca
        prioridade: must
        estimativa: M
        depende_de: ["EP-13-T02"]
        entregaveis: ["src/emcp_bus/common/pii_redaction.py"]
        criterios_aceite: ["Dado um output de tool contendo um e-mail/CPF sintético, quando exportado ao Langfuse, então aparece mascarado no trace."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: true
        justificativa_langgraph_langfuse: "Pré-processamento obrigatório antes de qualquer envio a Langfuse."
        riscos: []
        rastreabilidade: ["§27 ('Não registrar')"]

      - id: EP-13-T04
        titulo: "Versionamento de prompt no Langfuse"
        descricao: "Gestão do system prompt do agente de exemplo via Langfuse Prompt Management, versionado e referenciado por versão nas traces."
        componente: "example_agent"
        tipo: feature
        prioridade: could
        estimativa: P
        depende_de: ["EP-13-T02"]
        entregaveis: ["agents/example_agent/prompts/"]
        criterios_aceite: ["Uma mudança de prompt gera nova versão rastreável, sem sobrescrever a anterior."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: true
        justificativa_langgraph_langfuse: "Gestão/versionamento de prompts — caso de uso explícito de Langfuse na seção 6 do superprompt."
        riscos: []
        rastreabilidade: []

      - id: EP-13-T05
        titulo: "Modo A — Multiagente governado: Global Supervisor externo sobre o E-MCP-BUS"
        descricao: "Materializa o modo A do ADR-024 (governança-somente) — a demonstração central de 'elevação a Enterprise' pedida pelo autor. Dois backends de agente distintos (`sales_agent`, `finance_agent`, cada um seu próprio processo/StateGraph, padrão Agent Platform OCI), cada um com seu próprio MCP Client (EP-01) vinculado a um client profile/entitlement diferente (Sales.Read/Write via EP-04 vs. Finance.Read/Payments). Um Global Supervisor **externo** (padrão Agent Gateway do ADR-022, decidindo por conta própria qual backend/NBA usar) roteia a conversa entre os dois backends, incluindo handoff, mas TODA autorização de tools continua exclusivamente no PEP/PDP do E-MCP-BUS — o Global Supervisor nunca decide nem amplia entitlement, e nosso Service Orchestrator (EP-11) não participa da decisão de NBA neste modo."
        componente: "example_agent"
        tipo: feature
        prioridade: should
        estimativa: G
        depende_de: ["EP-12-T01", "EP-12-T03", "EP-13-T01", "EP-04-T02"]
        entregaveis: ["agents/example_agent/backends/sales_agent/", "agents/example_agent/backends/finance_agent/", "src/emcp_bus/agent_runtime/global_supervisor.py"]
        criterios_aceite: ["Dado uma conversa iniciada em sales_agent (MCP Client=Sales.Read/Write) que sofre handoff para finance_agent, quando o handoff ocorre, então finance_agent resolve seu próprio MaximumEntitlement (Finance.*) do zero — nunca herda nem amplia o de sales_agent (Axiom 4/9).", "Uma injeção de prompt em sales_agent tentando, via handoff, alcançar finance.payment.execute fora do entitlement de sales_agent é negada pelo Gateway, mesmo que o Global Supervisor tenha roteado a conversa."]
        padroes_abertos: ["MCP"]
        usa_langgraph: true
        usa_langfuse: true
        justificativa_langgraph_langfuse: "Orquestração multiagente com handoff entre backends distintos (padrão Global Supervisor do ADR-022) e necessidade de correlacionar em uma única trace toda a jornada cross-backend (Langfuse) — critérios explícitos da seção 6 do superprompt para ambos."
        riscos: ["Escopo maior que um agente único; não bloqueia M0-M2. É a tarefa que melhor demonstra o valor 'Enterprise' do bus (ADR-024) — priorizar dentro de M3/M4 mesmo não sendo `must`."]
        rastreabilidade: ["ADR-024", "§18 (shared client rule)", "§31 (blast-radius containment)", "Axiom 9"]

      - id: EP-13-T06
        titulo: "Modo B — Service Orchestrator como único cérebro de NBA/NBO"
        descricao: "Materializa o modo B do ADR-024 (substituição completa): a mesma cena de dois backends (Sales/Finance) de EP-13-T05, mas agora o Global Supervisor externo é dispensado — nosso próprio Service Orchestrator (EP-11-T03) calcula a NBA/NBO diretamente sobre `FilteredOfferings` combinando ofertas de Sales e Finance (ex.: apresentar um benefício vs. cobrar uma pendência), e o Agent Runtime (EP-12) apenas despacha o resultado para o backend/canal indicado — os backends de agente tornam-se executores puros, sem lógica própria de decisão de qual agir. Demonstra que a mesma stack de segurança (EP-01/EP-03/EP-05) não muda entre os dois modos, apenas quem decide a NBA/NBO."
        componente: "example_agent"
        tipo: feature
        prioridade: could
        estimativa: M
        depende_de: ["EP-11-T03", "EP-13-T05"]
        entregaveis: ["agents/example_agent/mode_b_orchestrator_driven/"]
        criterios_aceite: ["Dado o mesmo cenário de EP-13-T05 (subject elegível a um benefício de Sales e com pendência em Finance), quando rodado no modo B, então a NBA/NBO escolhida e o backend acionado vêm do nosso Service Orchestrator, não de um Global Supervisor externo.", "O conjunto de testes de segurança de EP-15-T02 passa igualmente nos modos A e B, sem nenhuma alteração no PEP/PDP entre eles."]
        padroes_abertos: []
        usa_langgraph: true
        usa_langfuse: true
        justificativa_langgraph_langfuse: "Mesmo grafo de jornada de EP-11-T02 agora dirigindo diretamente múltiplos backends de execução; Langfuse correlaciona a decisão única do Orchestrator com a execução em qualquer um dos backends."
        riscos: ["Prioridade `could` — demonstra a modularidade do ADR-024, mas não é necessária para nenhum critério de aceite de segurança; pode ser adiada sem risco para o núcleo da RI."]
        rastreabilidade: ["ADR-024", "RF-15"]

  - epico_id: EP-14
    titulo: "Human-in-the-loop / Approval workflow"
    objetivo: "Aprovação adicional para operações de alto risco, fora da influência exclusiva do LLM (§26)."
    secoes_readme: ["§26", "§17 (R3/R4)"]
    tarefas:
      - id: EP-14-T01
        titulo: "Contrato de aprovação"
        descricao: "Objeto de aprovação out-of-band, criptograficamente associado à operação, com prazo de validade e single-use (§26)."
        componente: "approval"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-03-T04"]
        entregaveis: ["schemas/approval-request.schema.json", "src/emcp_bus/approval/models.py"]
        criterios_aceite: ["Uma aprovação usada duas vezes na segunda tentativa é rejeitada (single-use, Threat: approval replay, §46)."]
        padroes_abertos: ["JSON Schema"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-10"]

      - id: EP-14-T02
        titulo: "Serviço de aprovação"
        descricao: "API/CLI mínima que gate a execução de REQUIRE_APPROVAL do PDP/Orchestrator, com resumo dos argumentos relevantes exibido ao aprovador."
        componente: "approval"
        tipo: feature
        prioridade: must
        estimativa: M
        depende_de: ["EP-14-T01", "EP-11-T05"]
        entregaveis: ["src/emcp_bus/approval/service.py"]
        criterios_aceite: ["Dado payment.execute >= 10k, quando solicitado, então a execução só prossegue após aprovação explícita registrada (§26 exemplo)."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-10", "§26"]

      - id: EP-14-T03
        titulo: "Fail-closed do serviço de aprovação"
        descricao: "Se o serviço de aprovação estiver indisponível, toda operação high-risk é negada, nunca liberada por omissão (§38)."
        componente: "approval"
        tipo: seguranca
        prioridade: must
        estimativa: P
        depende_de: ["EP-14-T02"]
        entregaveis: ["src/emcp_bus/approval/failure_policy.py"]
        criterios_aceite: ["Dado o serviço de aprovação fora do ar, quando uma R3/R4 é solicitada, então DENY, não timeout silencioso."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§38"]

  - epico_id: EP-15
    titulo: "Testes de segurança e adversariais"
    objetivo: "Validar formalmente os 10 critérios de aceite de segurança (§45) e os cenários adversariais (§46) contra a stack completa."
    secoes_readme: ["§45", "§46", "§28"]
    tarefas:
      - id: EP-15-T01
        titulo: "Testes de contrato dos MCP Servers"
        descricao: "Testes que validam cada tool exposta contra o input/output schema declarado em seu manifesto (EP-02)."
        componente: "tests"
        tipo: teste
        prioridade: must
        estimativa: M
        depende_de: ["EP-06-T02", "EP-06-T03", "EP-02-T05"]
        entregaveis: ["tests/contract/test_sales_domain.py", "tests/contract/test_finance_domain.py"]
        criterios_aceite: ["Uma resposta de tool que viola seu output schema falha o teste de contrato."]
        padroes_abertos: ["JSON Schema"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["RF-06"]

      - id: EP-15-T02
        titulo: "Suíte de aceite de segurança (Testes 1–10, §45)"
        descricao: "Automação pytest dos 10 testes formais do §45 rodando contra o docker-compose completo."
        componente: "tests"
        tipo: teste
        prioridade: must
        estimativa: G
        depende_de: ["EP-05-T02", "EP-05-T03", "EP-05-T04", "EP-05-T07", "EP-01-T03", "EP-04-T03"]
        entregaveis: ["tests/e2e/test_security_acceptance.py"]
        criterios_aceite: ["Os 10 testes do §45 (unauthorized discovery, direct unauthorized call, prompt injection, role spoofing, cache isolation, policy revocation, gateway bypass, token audience, backend isolation, client compromise) passam de ponta a ponta."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: ["Suíte grande — dividir execução por marco em vez de tentar completar tudo de uma vez"]
        rastreabilidade: ["§45", "todos os RF de segurança"]

      - id: EP-15-T03
        titulo: "Testes adversariais de prompt/tool injection"
        descricao: "Cenários do §46: direct/indirect prompt injection, malicious RAG chunk, tool output injection, tool description poisoning, hidden tool invocation, tool name spoofing. Inclui um cenário adicional derivado do achado do ADR-023 (payload-declared identity spoofing): forjar `agent_id`/`tenant_id`/`business_context` no payload de entrada do canal, tentando `tools/call` de uma capability fora do MaximumEntitlement do MCP Client real — variação prática do Teste 4 (§45, agent role spoofing), motivada por uma vulnerabilidade real observada em pesquisa de referência (docs/research/hoshikawa-agent-platform-oci.md)."
        componente: "tests"
        tipo: teste
        prioridade: must
        estimativa: G
        depende_de: ["EP-13-T01"]
        entregaveis: ["tests/adversarial/test_prompt_injection.py", "tests/adversarial/test_tool_poisoning.py", "tests/adversarial/test_payload_identity_spoofing.py"]
        criterios_aceite: ["Nenhum cenário simulado resulta em EffectiveCapabilities excedendo ClientEntitlement (Axiom 4).", "Um `agent_id`/`tenant_id` forjado no payload de entrada nunca altera a identidade usada pelo PDP para resolver entitlement (ADR-023)."]
        padroes_abertos: ["OWASP GenAI LLM01"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§14", "§28", "§46", "ADR-023"]

      - id: EP-15-T04
        titulo: "Testes adversariais de protocolo/identidade"
        descricao: "Cenários do §46: replay, stolen/expired/wrong-audience token, header/body mismatch, shared-cache poisoning, entitlement race condition, approval replay, bulk exfiltration via tools legítimas."
        componente: "tests"
        tipo: teste
        prioridade: must
        estimativa: G
        depende_de: ["EP-05-T08", "EP-05-T03", "EP-14-T01", "EP-05-T05"]
        entregaveis: ["tests/adversarial/test_protocol_identity.py"]
        criterios_aceite: ["Cada um dos 8 cenários resulta em DENY/rejeição determinística, sem exceção não tratada."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§46", "§28"]

      - id: EP-15-T05
        titulo: "Testes de política de falha (fail-closed)"
        descricao: "Chaos tests derrubando PDP/IdP/Registry/Approval individualmente e validando o comportamento esperado da tabela do §38."
        componente: "tests"
        tipo: teste
        prioridade: must
        estimativa: M
        depende_de: ["EP-05-T06", "EP-14-T03"]
        entregaveis: ["tests/e2e/test_fail_closed.py"]
        criterios_aceite: ["Para cada componente da tabela §38, o comportamento observado corresponde exatamente ao recomendado."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: ["§38", "RNF-Disponibilidade"]

  - epico_id: EP-16
    titulo: "Deploy final e documentação"
    objetivo: "Consolidar a stack completa, ADRs e documentação de uso da RI."
    secoes_readme: ["Todo o documento — integração final"]
    tarefas:
      - id: EP-16-T01
        titulo: "docker-compose completo"
        descricao: "Expandir EP-00-T04 para incluir todos os serviços (Keycloak, OPA, Registry store, Gateway, Fabric, servidores de domínio, Orchestrator, Agent Runtime, agente de exemplo, OTel/Jaeger, Langfuse) com perfis coerentes."
        componente: "deploy"
        tipo: infra
        prioridade: must
        estimativa: M
        depende_de: ["EP-05-T08", "EP-11-T05", "EP-12-T02", "EP-13-T04", "EP-14-T03", "EP-15-T05"]
        entregaveis: ["RI/docker-compose.yml (final)"]
        criterios_aceite: ["`docker compose up` sobe a stack completa e a suíte EP-15-T02 passa contra ela."]
        padroes_abertos: ["OCI"]
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: []

      - id: EP-16-T02
        titulo: "README da RI"
        descricao: "Quickstart, mapa de volta para as seções do README de arquitetura, como rodar cada suíte de testes."
        componente: "docs"
        tipo: docs
        prioridade: must
        estimativa: P
        depende_de: ["EP-16-T01"]
        entregaveis: ["RI/README.md"]
        criterios_aceite: ["Uma pessoa nova consegue subir a stack e rodar a suíte M0 seguindo apenas o README da RI."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: []

      - id: EP-16-T03
        titulo: "ADRs formalizados"
        descricao: "Um arquivo por ADR (ADR-001..021 da seção 8.4 deste documento) em docs/adr/, no formato Contexto/Decisão/Alternativas/Consequências."
        componente: "docs"
        tipo: docs
        prioridade: should
        estimativa: M
        depende_de: ["EP-16-T01"]
        entregaveis: ["docs/adr/ADR-001-*.md ... ADR-021-*.md"]
        criterios_aceite: ["Todos os 21 ADRs listados na seção 8.4 deste documento existem como arquivo individual."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: []
        rastreabilidade: []

      - id: EP-16-T04
        titulo: "Spike: verificação de versões estáveis"
        descricao: "Confirmar, imediatamente antes de fixar em pyproject.toml, os números exatos de versão estável de: SDK `mcp` (Python v2), LangGraph, Langfuse (edição OSS), OPA (v1.x, sintaxe Rego v1), Keycloak. Parcialmente pré-verificado em 2026-09-11 via busca web: a revisão MCP 2026-07-28 é real e GA (não é invenção do README); o SDK Python `mcp` v2 já suporta nativamente `cache_hints`/ttlMs/cacheScope (SEP-2549) e os headers Mcp-Method/Mcp-Name (SEP-2243); OPA está em v1.0+ com Rego v1 como sintaxe padrão. Falta apenas fixar os números de patch/minor exatos no pyproject.toml no momento da implementação."
        componente: "docs"
        tipo: spike
        prioridade: must
        estimativa: P
        depende_de: []
        entregaveis: ["docs/adr/ADR-018-version-pins.md (registro das versões confirmadas e data da verificação)"]
        criterios_aceite: ["Nenhuma versão é citada em código/config sem ter sido confirmada nesta tarefa."]
        padroes_abertos: []
        usa_langgraph: false
        usa_langfuse: false
        justificativa_langgraph_langfuse: ""
        riscos: ["Sem esta tarefa, há risco de alucinação de versão — por isso priorizada `must` e sem dependências, executável a qualquer momento."]
        rastreabilidade: ["Regra 4 do superprompt (sem alucinação de versões)"]
```

---

## 8.7 Sequenciamento e marcos

| Marco | Tarefas | Critério de "pronto" |
|---|---|---|
| **M0 — Walking skeleton ✅ concluído (2026-09-11, revalidado 2026-09-14)** | EP-00-T01, EP-00-T02, EP-00-T04, EP-06-T02, EP-05-T01, EP-08-T01 | Cliente MCP → Gateway → (roteamento estático) → MCP Server de exemplo (Sales) → resposta, com `trace_id` correlacionado visível em log/coletor OTel. Sem enforcement real ainda. Critério satisfeito desde a implementação inicial; hoje o roteamento deixou de ser estático (EP-06-T01, ver M1), mas o próprio trace correlacionado do walking skeleton continua coberto por `tests/e2e/test_walking_skeleton.py`. |
| **M1 — Segurança núcleo (Fase 1 do README) ✅ concluído (2026-09-11, revalidado 2026-09-14)** | EP-01 completo, EP-03 completo, EP-04 completo, EP-05-T02/T03/T04/T06/T07/T08, EP-02-T01/T02/T03/T05 (via M2), EP-06-T01/T03/T04, EP-08-T02/T03/T04 | `tools/list` filtrado por entitlement real (Keycloak+OPA), `tools/call` reautorizado, cache privado, fail-closed, anti-bypass, auditoria completa. Cobre RF-01 a RF-09 e Fases 0–2 do roadmap do README. **Adendo (2026-09-11, fechamento retroativo pós-M2)**: todos os itens acima que ainda restavam abertos após o M2 (EP-01-T04/T05, EP-05-T03/T07/T08, EP-06-T01/T03/T04, EP-08-T02/T03/T04) foram implementados nesta rodada — Fabric router real (multi-backend, EP-06-T01), segundo domínio Finance com backend real (EP-06-T03), adapter REST genérico standalone (EP-06-T04), taxonomia de auditoria IC/NOC/GRL + correlação decisionId/policyDecisionId/entitlementVersion (EP-08-T02/T03), stack local otel-collector+Jaeger (EP-08-T04), cache hint SEP-2549 (EP-05-T03 — ver limitação de wire-mode abaixo), segmentação de rede + gate de credencial nos domain servers (EP-05-T07), validação header/body Mcp-Method/Mcp-Name (EP-05-T08), lint de shared client (EP-01-T05), spike de mTLS documentado em `docs/adr/ADR-019-identity-extension.md` (EP-01-T04). **Limitação real descoberta e documentada**: SEP-2549 (`ttlMs`) é vocabulário exclusivo do protocolo 2026-07-28, que só existe no modo *stateless per-request* do SDK (`server/discover`, sem handshake `initialize`) — esta RI usa o handshake de sessão clássico em toda parte, então o campo nunca chega ao wire nesta arquitetura (o SDK descarta o campo na serialização para versões de protocolo anteriores); `cache_scope="private"` e o não-caching server-side já garantem a propriedade de segurança do Teste 5 independentemente disso. Ver `src/emcp_bus/gateway/cache.py`. **EP-00-T03 (pipeline de CI)**, apesar de não listado nesta linha, também foi implementado (`.github/workflows/ci.yml`). **Adendo (2026-09-14, revalidação de prontidão)**: reinstalação limpa do `.venv` (3 dias depois, mesmo ambiente) + `make lint`/`make typecheck`/`make validate-schemas`/`make export-schemas` (sem diff) + suíte completa `--forked` → **119/119 testes passando** (97 unit + 22 e2e), sem nenhuma falha — confirma que o commit `f3efcc3` ("M0 e M1 revisados e fixes implementados") capturou exatamente o estado validado na sessão anterior, sem drift. |
| **M2 — Governança e downstream ✅ concluído (2026-09-11, revalidado 2026-09-14)** | EP-02 completo (T01-T05, incluindo T02/T03/T05 adiados do M1), EP-04-T04, EP-07 completo, EP-14 completo | Publishing pipeline com lifecycle completo, outbound identity sem passthrough, aprovação humana funcionando fail-closed — todos ligados ao Gateway real (EP-05) e testados com OPA real. Cobre RF-10, RF-11, Fase 3 parcial. Detalhes e limitações em `RI/README.md`. **Adendo (2026-09-11, mesmo dia — Docker e Java passaram a estar disponíveis no ambiente)**: `docker-compose.yml` validado com daemon Docker real (build/up/fail-closed/trace cross-container), e **EP-01-T01 (Keycloak) implementado e validado com Keycloak 26.7.3 real** (`deploy/keycloak/realm-export.json`, perfil `identity` no compose, `tests/e2e/test_real_keycloak.py`) — item que a linha do M1 acima já citava como pré-requisito ("Keycloak+OPA") mas que só foi de fato implementado/testado agora. Ciclo de aprovação (EP-14) hoje testado e2e tanto contra Sales quanto contra Finance (EP-06-T03, ver M1). |
| **M3 — Personalização e orquestração (Fase 4 do README) ✅ concluído (2026-09-14)** | EP-09, EP-10, EP-11, EP-12, EP-13-T01..T04 | Perfil→entitlement→ofertas filtradas→NBA→dispatch→execução MCP funcionando ponta a ponta com LangGraph no Orchestrator e Langfuse no agente de exemplo. Cobre RF-12 a RF-17. **EP-09 (Profile Intelligence) ✅** — `src/emcp_bus/profile_intelligence/{models,rule_based_provider,governance}.py`: contrato `ProfileView` (T01), provider determinístico rule-based (T02), guardrails de governança — pseudonimização, lineage log, stub de drift monitor (T03). **EP-10 (Offering Filter) ✅** — `src/emcp_bus/offering_filter/service.py`: `FilteredOfferings = ActiveCatalog ∩ MaximumEntitlement ∩ ConsentContext` (T01); invariante de subconjunto provada com Hypothesis, 2000 casos gerados (T02). **EP-11 (Service Orchestrator) ✅** — `src/emcp_bus/orchestrator/*.py`: `DecisionContext` versionado (T01); `StateGraph` real do LangGraph 0.6 com checkpointer SQLite, nós fixos resolve_profile→resolve_entitlement→filter_offerings→decide_nba→approval_gate (T02); `NBADecisionModel` pluggable + referência determinística (T03); recálculo/degradação após DENY como edge condicional, nunca chamando o Fabric diretamente (T04); interrupção human-in-the-loop via `langgraph.types.interrupt`/`Command(resume=...)`, integrada a EP-14 (T05) — validado contra OPA real + LangGraph real + checkpointer SQLite real, incluindo prova de que retomar de um checkpoint pausado não reprocessa nós já executados. **EP-12 (Agent Runtime) ✅** — `src/emcp_bus/agent_runtime/*.py`: serviço de dispatch que nunca gera/armazena credencial própria, usa exclusivamente o MCP Client já registrado via `client_credentials` real (T01); channel adapter conversacional + registro com falha explícita para canal não suportado (T02); handoff com minimização de contexto e resolução de entitlement sempre independente por agente (T03, `could`); Identity Resolver/BusinessContext declarativo (`config/orchestrator/identity.yaml`), nunca consultado pelo PDP — checado mecanicamente via AST (T04). Validado com **Keycloak real + Gateway real**: `AgentDispatcher` alcançando o backend Sales real e sendo negado no cross-domain, e dois agentes reais (`sales-read-agent`/`finance-payments-agent`) obtendo tokens `client_credentials` independentes. **EP-13-T01..T04 (Agente de exemplo + Langfuse) ✅** — `agents/example_agent/`: agente conversacional com tool-calling **real** (endpoint OpenAI-compatible da OCI Generative AI, `meta.llama-3.3-70b-instruct`, tool-calling confirmado empiricamente 2026-09-14), catálogo restrito ao `tools/list` do próprio client — cenário de prompt injection do §29 reproduzido de verdade contra o Gateway/PDP reais (T01); Langfuse self-hosted real (`deploy/langfuse/docker-compose.override.yml`, adaptado do compose oficial upstream, perfil `llm-observability` opt-in) — **subida de verdade e validada**: 6 containers (web/worker/postgres/clickhouse/redis/minio) saudáveis, spans de MCP e de generation (com `gen_ai.request.model`/tokens reais) confirmados fisicamente na tabela `events_core` do ClickHouse via o endpoint OTLP real do Langfuse (`/api/public/otel/v1/traces`) — validação manual documentada em `RI/README.md`, não um teste e2e automatizado (custo de subir 6 containers a cada run) (T02); redação de PII/segredos antes de qualquer export (`src/emcp_bus/common/pii_redaction.py`, T03); versionamento de prompt local (`agents/example_agent/prompts/store.py`) como núcleo testável do "nunca sobrescreve versão anterior" — sync real para a API de Prompt Management do Langfuse documentado como adapter fino não implementado nesta sessão (T04, `could`). Dependências novas: `langgraph`, `langgraph-checkpoint-sqlite`, `hypothesis`, `openai`, `python-dotenv`. **201 testes automatizados no total** (171 unit + 30 e2e, todos passando com `--forked`, incluindo os novos testes reais de LLM/Keycloak/OPA/LangGraph do M3 — nenhum mock no núcleo de segurança ou orquestração). |
| **M4 — Hardening e entrega ✅ concluído (2026-09-14)** | EP-13-T05, EP-13-T06 (could), EP-15 completo, EP-16 completo | Suíte de 10 testes de aceite (§45) e cenários adversariais (§46, incluindo o de EP-15-T03/ADR-023) passando contra a stack completa; **os dois modos de integração do ADR-024 demonstrados** — Modo A (EP-13-T05: Global Supervisor externo, dois backends/MCP Clients, handoff sem elevação de privilégio) e Modo B (EP-13-T06: nosso Service Orchestrator como único cérebro de NBA/NBO, mesma stack de segurança); ADRs documentados; README da RI publicado. **Todas as tarefas concluídas, incluindo as duas `could` (EP-13-T05/T06) — nenhum item do backlog de M0-M4 permanece aberto.** Detalhamento tarefa-a-tarefa: **EP-15-T01/T02 ✅** (ver adendo de 2026-09-14 abaixo, sessão anterior a esta). **EP-15-T03 (testes adversariais de prompt/tool injection) ✅** — `tests/adversarial/{test_prompt_injection,test_tool_poisoning,test_payload_identity_spoofing}.py`, 12 testes novos contra o Gateway real (`governed_stack`/`governed_stack_with_finance`): injeção direta/indireta de conteúdo em argumentos nunca altera autorização nem o catálogo (`tools/list` idêntico antes/depois de processar conteúdo adversarial); hidden tool invocation e spoofing de nome de tool (case/whitespace/typo) sempre negados por comparação exata; **tool description poisoning** provado com um MCP server malicioso real montado em runtime (`MCPServer` in-process, descrição hostil pedindo "acesso admin"), confirmando que a Gateway repassa a descrição verbatim (nunca a sanitiza) mas ela não tem nenhum efeito na decisão PDP; variação explícita do achado ADR-023 (payload-declared `agent_id`/`tenant_id`/`business_context` forjados nos argumentos de `tools/call`) provada tanto por negação de entitlement quanto por auditoria (o evento `tool_call_allowed` sempre registra o `client_id` real, nunca o forjado). **Achado de dados**: `CapabilityManifest` não tem campo `description` (mesmo achado do EP-15-T01) — "tool description poisoning" é portanto um vetor de *domain server*, não de Registry, documentado explicitamente no docstring do arquivo. **EP-15-T04 (testes adversariais de protocolo/identidade) ✅** — `tests/adversarial/test_protocol_identity.py`, 6 testes novos + referências cruzadas explícitas para os cenários já cobertos alhures (expired/wrong-audience/stolen token em `test_governed_gateway.py`/`test_authn.py`/`test_security_acceptance.py` Teste 10; approval replay sequencial já existente): header/body mismatch rejeitado antes da autenticação (POST cru com `Mcp-Method` divergente do body); replay de requisição byte-idêntica não é bloqueado (gap real e documentado — sem nonce/anti-replay nesta RI; mitigado por token de vida curta) mas cada tentativa gera `decision_id` distinto no audit trail; **revogação de política ao vivo** contra um Gateway real rodando (fecha a lacuna que o EP-15-T02 havia documentado para o Teste 6 — sem endpoint HTTP de revogação, exercitado diretamente via `EntitlementManager.load_profiles`/`revoke_profile` + `PDPClient.push_client_profile`, os mesmos primitivos que tal endpoint chamaria); condição de corrida de entitlement sob concorrência real (`asyncio.gather`) nunca resulta em crash ou resultado inconsistente; **approval replay sob concorrência real** (`ThreadPoolExecutor`, 20 threads) prova atomicidade de `ApprovalService.check_and_consume` — **achado real corrigido**: o método não era thread-safe (check-then-set em duas operações não atômicas), corrigido com um `threading.Lock` dedicado; bulk exfiltration via tools de leitura legítimas não é bloqueado (gap real e documentado — sem rate limiting nesta RI) mas cada chamada gera evento de auditoria com `decision_id` próprio, provando reconstrutibilidade completa a posteriori. **EP-15-T05 (testes de política de falha) ✅** — `tests/e2e/test_fail_closed.py`, um teste por linha da tabela do §38, incluindo cenários que EP-05-T06/`test_governed_gateway.py` não cobriam (PDP/IdP indisponíveis *em runtime*, não só no boot): IdP inalcançável nega novas autenticações; PDP morrendo em pleno funcionamento (processo OPA descartável morto no meio do teste) faz a próxima chamada falhar fechado (`PDP_UNAVAILABLE`); Registry sem `capabilities/` para semear falha o boot do Gateway (`FileNotFoundError`, mesma postura do PDP inalcançável); **achado real corrigido**: nenhum dos 8 `audit_sink.emit(...)` do Gateway estava protegido — uma falha no sink (disco cheio, fila indisponível) teria virado erro 500 para uma operação de baixo risco já ALLOWed, violando "não bloquear low-risk"; corrigido com o helper `_emit_audit` (`src/emcp_bus/gateway/server.py`), que engole qualquer exceção do sink em todos os 8 pontos de emissão, para ALLOW e para DENY; approval service falho nega (nunca crasha nem libera) uma operação de alto risco, provando ao vivo pela primeira vez o `except Exception: approved = False` do EP-14-T03; backend morto falha só aquela requisição, sem derrubar o processo do Gateway (um client não-relacionado, entitled a um backend saudável diferente, não é afetado). **EP-13-T05 (Modo A, `should`) ✅** — `src/emcp_bus/agent_runtime/global_supervisor.py` + `agents/example_agent/backends/{sales_agent,finance_agent}/`: `GlobalSupervisor` com roteamento por palavra-chave simples (deliberadamente não-inteligente — não é a fronteira de segurança, documentado explicitamente), nunca importa `emcp_bus.orchestrator` (checado via AST, mesma disciplina do EP-12-T04) — prova mecânica de que o Modo A realmente não usa o Orchestrator/NBA próprio. Validado com **LLM real + Gateway real + Keycloak-stand-in real** (`tests/e2e/test_multi_agent_mode_a.py`, 2 testes): (1) handoff de `sales_agent` para `finance_agent` — `finance_agent` resolve seu próprio `tools/list`/entitlement do zero, com token Bearer completamente distinto do de `sales_agent` (Axiom 4/9); (2) uma injeção de prompt tentando, via handoff, forçar `finance.payment.execute` fora de aprovação continua negada pelo Gateway/PDP reais, mesmo com o roteamento tendo migrado a conversa para o backend certo. **EP-13-T06 (Modo B, `could`) ✅** — `agents/example_agent/mode_b_orchestrator_driven/{decision_model,orchestrator}.py`: `ModeBOrchestrator` invoca o **journey `StateGraph` real do EP-11-T02** (não modificado) uma vez por `client_id` relevante para o mesmo subject, combina os `NBADecision`s resultantes (regra de referência: pendência de Finance sempre vence oferta discricionária de Sales) e despacha via `AgentDispatcher` real (EP-12-T01) — nunca cria um caminho de autorização próprio. Validado **contra Keycloak real, OPA real, Sales+Finance reais e o Gateway real** (`tests/e2e/test_real_keycloak.py::test_mode_b_orchestrator_combines_offerings_and_dispatches_through_the_real_chain`): a mesma subject realmente produz candidatos de AMBOS os domínios (prova de combinação real, não apenas um domínio rodando sozinho), a decisão final vem do combinador do nosso Orchestrator (nunca de um Global Supervisor externo), e o dispatch é `ALLOW` de ponta a ponta. **Decisão de design registrada**: `ModeBOrchestrator` não estende `JourneyState`/`build_journey_graph` para abranger múltiplos `client_id`s nativamente (arriscaria um componente já testado por um demo `could`) — a combinação vive uma camada acima do grafo, exatamente onde o próprio docstring do `AgentDispatcher` já dizia que a orquestração pós-decisão pertence. **EP-16-T01 (docker-compose completo) ✅** — validado com `docker compose --profile core --profile identity --profile observability up -d --build` real: todos os 7 serviços sobem limpos (Keycloak, OPA, Sales, Finance, Gateway, OTel Collector, Jaeger), healthchecks passam, Gateway inicia só depois de Sales/Finance saudáveis; a suíte completa do EP-15-T02 (7 testes) já passa contra o mesmo compose (`core`+`identity`). Agente de exemplo/Orchestrator/Agent Runtime permanecem bibliotecas Python consumidas por processo (Gateway ou scripts de teste/demo), não serviços containerizados próprios — decisão de escopo deliberada: esta RI demonstra propriedades de segurança, não uma UI de chat pronta para produção. **EP-16-T02 (README da RI) ✅** — ver `RI/README.md`, seções M4/"O que existe hoje"/"Limitações conhecidas" atualizadas nesta rodada. **EP-16-T03 (ADRs formalizados) ✅** — 25 arquivos em `docs/adr/` (ADR-001 a ADR-025, um a mais que os 21 originalmente previstos: a tabela §8.4 cresceu para 25 entradas durante o M3/M4 com a pesquisa Hoshikawa, ADR-022 a ADR-025), gerados mecanicamente a partir da própria tabela da seção 8.4 (fonte única, evita divergência) no formato Contexto/Decisão/Alternativas/Consequências; ADR-019 já existia como o spike aprofundado do EP-01-T04 e foi preservado como está. **EP-16-T04 (versões confirmadas) ✅** — registro consolidado adicionado como seção final de `docs/adr/ADR-018-stack-de-implementacao.md` (não um arquivo `ADR-018-version-pins.md` separado como o texto original da tarefa sugeria — colidiria com o ADR-018 real da tabela §8.4, "Stack de implementação"; resolvido fundindo o conteúdo no mesmo arquivo em vez de criar uma segunda contagem "ADR-018"). **Correções de código reais feitas durante a validação do M4** (não apenas testes novos): (1) `ApprovalService` ganhou um `threading.Lock` — sem ele, `check_and_consume` tinha uma race condition real de double-spend sob concorrência de threads reais; (2) `_emit_audit` no Gateway — nenhuma das 8 chamadas a `audit_sink.emit` estava protegida contra falha do sink, violando §38 para o caso ALLOW. Ambas descobertas escrevendo os testes adversariais/fail-closed, não hipotéticas. **Suíte final: 260 testes automatizados no total** — 253 passando com `--forked` (confirmado nesta rodada, todo o `tests/` exceto `test_security_acceptance.py`) mais os 7 de EP-15-T02 contra o Docker real (rodados separadamente pelo custo de build+Keycloak por execução) — ver `RI/README.md` para a composição exata por categoria. |

**Caminho crítico:** EP-00 → EP-01/EP-06 (paralelos) → EP-05 (núcleo do PEP) → EP-02/EP-03/EP-04 (entitlement real) → EP-08 (correlação) → EP-09/EP-10 → EP-11 (Orchestrator) → EP-12/EP-13 → EP-15 (validação) → EP-16 (entrega). EP-07 e EP-14 podem ser paralelizados a partir de M1 sem bloquear o caminho principal até M3.

### Nível de prontidão para M4 — histórico da avaliação inicial (2026-09-14, atualizado após conclusão do M3; ver a linha do M4 na tabela de marcos acima para o estado final, M4 100% concluído)

**M0, M1, M2 e M3 estão concluídos** (ver linha do M3 na tabela acima para o detalhamento tarefa-a-tarefa — EP-09 a EP-12 completos, EP-13-T01..T04 completos). Caminho crítico até M4 (`... → EP-11 → EP-12/EP-13 → EP-15 (validação) → EP-16 (entrega)`): EP-11 (Orchestrator, LangGraph real) e EP-12/EP-13 (Agent Runtime + agente de exemplo) — os itens que o caminho crítico original citava como pré-requisito do M4 — estão implementados e testados contra dependências reais (OPA, Keycloak, LangGraph, LLM, Langfuse). **Não há bloqueio técnico para iniciar o M4** (EP-13-T05/T06, EP-15, EP-16).

Ressalvas não-bloqueantes específicas do M3 (ver `RI/README.md`, seção "M3 — Personalização e orquestração" e "Limitações conhecidas", para o detalhamento completo): EP-12-T03 (handoff) tem o primitivo cross-process pronto mas nenhum subgrafo LangGraph intra-processo ainda (não há dois agentes ativos simultâneos até o EP-13-T05); EP-13-T02 (Langfuse) foi validado manualmente de verdade, não por teste e2e automatizado; EP-13-T04 (prompt versioning) tem o núcleo local pronto mas não sincroniza com a API real do Langfuse.

**Progresso do M4 (2026-09-14)** — **EP-15-T01 (testes de contrato) ✅ concluído**: `tests/contract/{conftest,test_sales_domain,test_finance_domain}.py`, conectando direto a cada domain server (nunca pelo Gateway — o contrato input/output de uma tool é propriedade do domain server, independente de quem está ou não entitled a chamá-la, ADR-023). **Achado de dados durante a implementação**: `CapabilityManifest` (EP-02-T01) não carrega `input_schema`/`output_schema` — o desenho original do EP-02 nunca incluiu isso (o papel do manifesto é metadado de entitlement/risco, não formato). Resolvido de forma honesta e verificada empiricamente contra o servidor Sales real: (a) o `input_schema` que o MCP SDK **auto-gera** a partir da assinatura Python de cada tool é real, específico por campo, e **de fato validado no servidor** (campo obrigatório ausente ou tipado errado é rejeitado via Pydantic antes de qualquer código da RI rodar) — reaproveitado diretamente, não reimplementado; (b) o `output_schema` auto-gerado é genérico demais (`additionalProperties: true`, já que toda tool retorna `dict[str, object]`) para servir de contrato — resolvido com JSON Schema escrito à mão por tool (biblioteca `jsonschema`, já dependência transitiva), validado contra a resposta real de cada uma das 9 tools (6 Sales + 3 Finance). 20 testes novos (6 positivos de schema + 1 parametrizado de campo ausente + 1 de tipo errado, por domínio). **EP-15-T02 (suíte de aceite de segurança, §45) ✅ concluído**: `tests/e2e/test_security_acceptance.py`, rodando contra o `docker-compose.yml` real (`--profile core --profile identity`, Keycloak real incluído) — não os fixtures in-process do resto da suíte e2e. 7 dos 10 testes formais automatizados diretamente contra o stack: Teste 1 (unauthorized discovery), Teste 2 (direct unauthorized call), Teste 4 (role spoofing via campos forjados no payload), Teste 5 (cache isolation, incluindo asserção de `cache_scope="private"`), Teste 7 (gateway bypass — confirma que `sales-domain`/`finance-domain`/`opa` não publicam porta de host), Teste 9 (backend/transaction-policy isolation — `TRANSACTION_POLICY_DENIED` real do Rego), Teste 10 (client compromise containment — token válido de `sales-read-agent` não escapa do seu próprio MaximumEntitlement). Os outros 3 têm cobertura real já existente, documentada no docstring do arquivo em vez de duplicada: Teste 3 (prompt injection) já é coberto com LLM real em `tests/e2e/test_example_agent.py`; Teste 6 (policy revocation) não tem endpoint HTTP de revogação nesta RI (`EntitlementManager.revoke_client`/`revoke_profile` são métodos in-process) — coberto em `tests/unit/test_entitlement_manager.py`; Teste 8 (token audience) já é provado contra o mesmo realm Keycloak real em `tests/e2e/test_real_keycloak.py`. Suíte completa revalidada após as duas tarefas: **228 testes automatizados no total** — 221 (171 unit + 30 e2e + 20 contract) passando com `--forked` em ~6.5min, mais os 7 de EP-15-T02 confirmados separadamente contra o Docker real (~72s, não incluídos na rodada `--forked` padrão dado o custo de build+Keycloak por execução).

### Nível de prontidão para M3/M4 — avaliação histórica, antes do início do M3 (2026-09-14)

**M0, M1 e M2 estão 100% concluídos e revalidados** — nenhuma tarefa aberta nos três marcos (auditoria tarefa-a-tarefa contra os entregáveis reais em disco, feita nesta revisão: todo `entregavel` de EP-00 a EP-08 e EP-14 existe e está funcional). Especificamente para o caminho crítico até M3 (`EP-06 → EP-05 → EP-02/03/04 → EP-08 → EP-09/10`, ver acima): EP-06-T01 (Fabric router multi-backend) e EP-06-T03 (segundo domínio real, Finance) — os dois itens que este mesmo documento identificou como bloqueio técnico real do M3 — estão implementados e testados, assim como EP-08-T02/T03 (auditoria/correlação), também pré-requisito citado. **Não há bloqueio técnico remanescente para iniciar o M3.**

Únicas ressalvas, nenhuma bloqueante:
- **EP-06-T04** (adapter REST) implementado e testado apenas de forma standalone — nenhum backend de exemplo desta RI é REST, então não há um caminho ao vivo através do Gateway exercitando-o. Só passa a importar se um EP-09+ precisar de um backend não-MCP-nativo.
- **EP-08-T04** (stack de observabilidade) tem a config validada (`docker compose config`) mas não foi exercitada com tráfego OTLP real end-to-end.
- A flakiness de teste e2e que sessões anteriores documentaram como um risco de credibilidade da suíte está **resolvida** (`pytest-forked`, 119/119 testes reprodutíveis) — deixa de ser um risco a carregar para M3/M4.

**Adendo (2026-09-14, resolvido durante o início do M3, a pedido do autor)**: **Token exchange RFC 8693** (modo `token_exchange` de `BackendConfig`, dentro de EP-07) deixou de ser um `NotImplementedError` — implementado em `src/emcp_bus/downstream/identity.py` (`TokenExchangeClient`) contra o Standard Token Exchange do Keycloak (GA desde 26.2, sem feature flag de preview). Validado empiricamente contra um Keycloak 26.7.3 real (não apenas suposto pela doc): (a) o parâmetro `audience` do exchange exige um **client id realmente registrado** no realm — uma string livre ("custom audience") falha com "Audience not found"; (b) pedir `audience` sem também pedir, via `scope`, um client scope que efetivamente adiciona essa audience falha com "Requested audience not available" (o parâmetro `audience` só restringe, nunca adiciona). `deploy/keycloak/realm-export.json` ganhou o client `gateway-token-exchange` (`standard.token.exchange.enabled: true`), dois clients placeholder somente-audiência (`sales-domain-service`/`finance-domain-service`, nunca usados para login) e dois client scopes (`aud-sales-domain-service`/`aud-finance-domain-service`) com `oidc-audience-mapper`. `BackendConfig` ganhou `token_exchange_scope` (novo campo obrigatório no modo `token_exchange`). `credential_for`/`CapabilityRouter.route` tornaram-se `async def` (a troca de token é uma chamada de rede) — refletido em todo o Gateway. 7 novos testes (4 unit com `httpx.MockTransport` simulando o fluxo de dois passos do Keycloak + cache; 3 e2e contra Keycloak real, incluindo um `tools/call` de ponta a ponta pelo Gateway usando uma credencial obtida por token exchange, não `SALES_DOMAIN_SERVICE_TOKEN`) — todos passando. `service_account` continua o modo padrão dos backends seed (`config/backends/*.yaml`); `token_exchange` é uma alternativa disponível e verificada, não o padrão.

---

## 8.8 Riscos principais

| # | Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|---|
| 1 | Curva de aprendizado de OPA/Rego atrasa EP-03 | Média | Médio | Começar com poucas policies R1 (Fase 1 do roadmap); usar `opa test` desde o primeiro commit. |
| 2 | Complexidade do realm Keycloak para ambiente local | Baixa | Médio | Usar realm export versionado e reproduzível (EP-01-T01), não configuração manual. |
| 3 | LangGraph aplicado além do necessário, contaminando componentes determinísticos | Média | Baixo | Critério da seção 6 aplicado rigorosamente por task (ver campo `justificativa_langgraph_langfuse` de cada tarefa). |
| 4 | Cache privado mal configurado causa leakage entre clients (§35.8) | Baixa | Alto | EP-15-T04 testa isolamento de cache explicitamente antes de M4. |
| 5 | Profile Intelligence vira tentativa de "IA de verdade" sem dataset real | Média | Baixo | P7 fixa o escopo como stub baseado em regras; revisão de escopo em EP-09-T02. |
| 6 | Langfuse self-hosted (Postgres+ClickHouse+Redis+S3-compatible) torna o compose pesado | Alta | Médio | Perfil `llm-observability` opcional e desacoplado do `core` (M0–M2 não dependem dele). |
| 7 | Divergência entre stack do README (OPA/Keycloak citados) e stack Python definida pelo superprompt | Baixa | Médio | G1/P1 explicitados; confirmar com autor do README assim que possível. |
| 8 | Suíte adversarial (EP-15) subestimada — cobre 18+ cenários | Alta | Médio | Dividida em EP-15-T03/T04 por categoria, incrementável por marco em vez de "big bang" em M4. |
| 9 | Token exchange (RFC 8693) não suportado por todo backend mock | Média | Baixo | Fallback documentado para service account por adapter (P5/ADR-020). |
| 10 | Stakeholders cobrarem federação multi-domínio/multi-cloud antes do previsto | Média | Médio | Roadmap explicita (8.7) que federação e ambientes híbridos são pós-RI (Fase 5 do README), não M0–M4. |

---

## 8.9 Resultado do checklist de autovalidação

- ✅ Todo componente do README aparece em pelo menos uma tarefa (ver matriz 8.2); nenhuma tarefa implementa algo ausente do README sem `[PREMISSA]` declarada (ver 8.3).
- ✅ O YAML do backlog é sintaticamente válido; todos os IDs em `depende_de` referenciam tarefas existentes no próprio backlog (verificação manual cruzada durante a escrita — recomenda-se rodar um linter YAML/schema antes do uso operacional).
- ✅ O grafo de dependências é acíclico por construção: dependências apontam sempre para tarefas de épico igual ou numericamente anterior, exceto EP-06→EP-02 (fabric depende do registry, EP-02 < EP-06, sem ciclo) e EP-05-T07→EP-06-T01 (mesmo sentido). M0 (seção 8.7) é executável isoladamente com as 6 tarefas listadas, todas com dependências internas ao próprio conjunto M0.
- ✅ Cada tarefa tem ao menos um entregável e um critério de aceite testável (ver backlog 8.6).
- ✅ Todo uso de LangGraph está restrito a EP-11 (Service Orchestrator — estado, ciclos, checkpointing, HITL) e EP-12-T03 (handoff multiagente); todo uso de Langfuse está restrito a EP-13 (única camada com chamadas reais a LLM). Nenhum roteamento simples (Gateway EP-05, Fabric EP-06, Offering Filter EP-10) usa LangGraph — justificativa explícita em cada tarefa.
- ✅ Nenhuma dependência proprietária entrou sem marca `[NÃO-OSS]`; Keycloak e OPA foram verificados como Apache-2.0, Langfuse usado apenas em sua edição self-hosted/OSS (nota em EP-13-T02).
- ✅ Todo arquivo YAML de configuração previsto (client registration, capability manifest, client profile, backend credentials) tem tarefa correspondente de JSON Schema + modelo Pydantic + validação em CI (EP-00-T02/T03 fornecem o framework genérico; cada schema específico é entregável de sua tarefa de domínio).
- ✅ Há tarefas explícitas para: autenticação/autorização (EP-01), allowlist de tools por client/tenant (EP-04, EP-05-T02), defesa contra prompt injection via conteúdo de tools (EP-15-T03, governança de publicação em EP-02-T02), gestão de segredos (EP-00-T05, EP-07-T02), auditoria (EP-08) e mascaramento de PII (EP-13-T03, EP-09-T03).
- ✅ Há tarefas de testes de contrato para os servidores MCP (EP-15-T01) e testes end-to-end dos fluxos principais do README (EP-15-T02, cobrindo os 10 testes formais do §45).
- ✅ Nenhuma versão de biblioteca ou API foi afirmada sem certeza — todas as menções a versões usam "verificar" (ex.: EP-05-T08, referência à revisão MCP 2026-07-28) e uma tarefa dedicada (EP-16-T04) confirma versões antes de fixá-las em `pyproject.toml`.

---

*Documento gerado seguindo o SUPERPROMPT de planejamento da RI. Confirmado pelo autor em 2026-09-11: G1 (`RI/` é criado do zero por este backlog, a partir de EP-00-T01), G3 (OPA é decisão técnica definitiva de PDP, por ser OSS), G4 (Keycloak é decisão técnica definitiva de identidade do MCP Client, por ser OSS), G2/G8 (Python/LangGraph/Langfuse seguem o padrão operacional do "Agent Platform OCI" de Christiano Hoshikawa — ver `docs/research/hoshikawa-agent-platform-oci.md` e ADR-022/ADR-023) e G11 (§6.2 do README corresponde ao papel de uma plataforma multiagente externa e consumidora do bus, não a um componente da RI — ADR-024, "elevação a Enterprise": o E-MCP-BUS é a camada de governança de catálogo/entitlement sob a qual qualquer plataforma de orquestração como o Agent Platform OCI se conecta, com o "MCP Gateway" interno dela substituído pelo nosso PEP/PDP. Ampliado em seguida pelo autor: nosso Service Orchestrator calcula NBA **e NBO** com modelo de decisão pluggable — modularidade + compatibilidade = escolha — habilitando dois modos de integração: A, governança-somente sob um orquestrador externo, e B, substituição completa da camada de decisão externa pelo nosso próprio Orchestrator; ambos demonstrados em EP-13-T05/T06). Também verificado via busca web em 2026-09-11 (não apenas suposto): a revisão MCP 2026-07-28 é real/GA e o SDK Python `mcp` v2 já suporta nativamente os recursos usados em EP-05-T03/T08; OPA está em v1.0+ com Rego v1. Restam abertas G5–G7, G9–G10 (ver 8.3), nenhuma delas bloqueando o início de M0/M1.*
