# ADR-014: Perfil nunca amplia entitlement

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-014 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Perfil pode ampliar entitlement?

## Decisão

Nunca — `FilteredOfferings ⊆ MaximumEntitlement`, perfil só ordena/reduz.

## Alternativas consideradas

Perfil de alto engajamento desbloqueando novas tools.

## Consequências

EP-10-T02 traz teste de propriedade validando a invariante para entradas aleatórias.
