# ADR-024: Posicionamento do E-MCP-BUS frente a plataformas multiagente externas

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão — não é mais gerado a partir de `docs/RI-PLANNING.md` (removido do repositório após a conclusão do marco M4; histórico preservado no git). Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Posicionamento do E-MCP-BUS em relação a plataformas de orquestração multiagente externas, como o Agent Platform OCI (**decisão confirmada e ampliada pelo autor em 2026-09-11** — resolve G11).

## Decisão

O E-MCP-BUS **não compete** com plataformas de orquestração como o Agent Platform OCI — mas também **não se limita a coexistir sob elas**. Princípio de design explícito: **modularidade + compatibilidade = escolha**. Nosso Service Orchestrator (EP-11) não é um passa-through fino: ele calcula NBA **e NBO** (Next Best Action/Next Best Offer) com um modelo de decisão próprio (regras + guardrails +, opcionalmente, um modelo de IA de ranking/recomendação — ver EP-11-T03) sobre o universo de `FilteredOfferings` que o MCP Fabric expõe (serviços, ofertas, ações, campanhas — não só "tools" técnicas). Isso habilita **dois modos de integração igualmente válidos, escolhidos pelo adotante conforme a topologia desejada**: **(A) Governança-somente** — uma plataforma de orquestração externa (ex.: Agent Platform OCI, com seu próprio Global Supervisor e StateGraph decidindo NBA) conecta-se ao E-MCP-BUS apenas para acesso governado ao Fabric; nosso Service Orchestrator não participa, ou participa apenas como fonte de `FilteredOfferings` (como já descrito no restante deste ADR e em EP-13-T05). **(B) Substituição completa** — nosso próprio Service Orchestrator (EP-11) assume integralmente o papel de "cérebro" de decisão (NBA/NBO), dispensando o Global Supervisor/StateGraph de decisão da plataforma externa; o Agent Runtime (EP-12) e os channel adapters da plataforma externa (ex.: os backends de agente do Hoshikawa) tornam-se meros executores do dispatch que nosso Orchestrator produz. Em qualquer um dos dois modos, o núcleo de segurança (PEP/PDP, EP-05/EP-03) nunca muda de lugar — apenas quem calcula a NBA/NBO muda. Em ambos os modos, cada backend/agente de domínio continua registrado como um **MCP Client distinto** (EP-01), vinculado a um client profile/entitlement próprio por domínio+risk tier (EP-04, P6), e o "MCP Gateway" interno de qualquer plataforma consumidora (ADR-023) é sempre substituído pelo nosso Gateway/PEP como único ponto de autorização. Isso é a "elevação a Enterprise": catálogo/entitlement/auditoria governados centralmente, com a decisão de NBA/NBO podendo vir de dentro (modo B) ou de fora (modo A) do bus, por escolha modular do adotante.

## Alternativas consideradas

Forçar um único modo de integração (ex.: só "governança-somente"), o que subutilizaria o Service Orchestrator e obrigaria sempre uma plataforma externa de decisão; tratar o Agent Platform OCI como um substituto do E-MCP-BUS (incorreto — ele não resolve entitlement); reimplementar do zero a engenharia de orquestração já validada em ADR-022 mesmo quando o modo B é escolhido (a forma StateGraph/checkpointing/handoff continua reaproveitável dentro do nosso EP-11/EP-12).

## Consequências

Reformula o objetivo de EP-11 (Service Orchestrator explicitamente descrito como calculador de NBA **e NBO** sobre serviços/ofertas/ações do Fabric, com modelo de decisão pluggable) e de EP-13 (demonstra os dois modos — ver EP-13-T05 para o modo A e EP-13-T06, novo, para o modo B). Reforça que EP-06/EP-05 tratam qualquer "MCP Gateway" de uma plataforma consumidora como não-confiável para autorização, nos dois modos.
