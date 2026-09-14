# ADR-003: Reautorizacao independente em tools/call

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-003 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

`tools/list` filtrado é suficiente?

## Decisão

Não — `tools/call` deve ser reautorizado independentemente do discovery.

## Alternativas consideradas

Confiar apenas em filtered discovery.

## Consequências

EP-05 implementa dois pontos de enforcement, não um.
