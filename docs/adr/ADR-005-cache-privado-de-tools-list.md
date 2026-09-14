# ADR-005: Cache privado de tools/list

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-005 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Cache de `tools/list` entre clients.

## Decisão

`cacheScope=private`, chave = identidade+contexto+policy_version.

## Alternativas consideradas

Cache compartilhado por performance.

## Consequências

EP-05-T03; teste dedicado de isolamento (EP-15).
