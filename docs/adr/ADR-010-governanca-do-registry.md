# ADR-010: Governanca do Global Capability Registry

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-010 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Governança do Global Capability Registry (título e número herdados de §49 do README — "Global Capability Registry Governance").

## Decisão

O Registry é um control-plane asset (§6.6) com autoridade e ciclo de vida próprios, separados da visão de catálogo entregue a cada client. Na RI: armazenamento e API de leitura dedicados (EP-02-T03), consumidos por Gateway/Fabric/Offering Filter mas nunca editados por eles; lifecycle formal nominate→review→register→publish→observe→(change|deprecate→retire) (§23) implementado como máquina de estados (EP-02-T04); toda alteração passa pelo publishing pipeline (EP-02-T02) — nenhum cadastro manual direto em produção (RF-11). Owner organizacional do Registry (quem aprova mudanças de schema/política do próprio control plane) permanece uma decisão de governança corporativa fora do escopo técnico da RI (§48, pergunta 4, segue aberta).

## Alternativas consideradas

Deixar o Registry como uma tabela editável ad hoc por qualquer serviço; fundir a visão de controle (Registry) com a visão de execução (catálogo filtrado por client), o que violaria a separação control plane/data plane do §24.

## Consequências

EP-02 inteiro; reforça que EP-05 (Gateway) e EP-10 (Offering Filter) só leem o Registry, nunca escrevem nele.
