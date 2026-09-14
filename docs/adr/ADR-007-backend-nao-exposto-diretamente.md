# ADR-007: Backend nunca exposto diretamente ao client

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-007 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Backend acessível diretamente pelo client?

## Decisão

Não — rede/identidade restringem acesso só ao Gateway/Fabric.

## Alternativas consideradas

Expor Fabric publicamente com authz "best effort".

## Consequências

EP-05-T07, EP-15 (teste de bypass).
