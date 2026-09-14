# ADR-004: Contexto agentico nunca eleva privilegio

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-004 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Contexto agêntico pode elevar privilégio?

## Decisão

Nunca — contexto só pode subtrair (`Context may subtract, must never add`).

## Alternativas consideradas

Permitir elevação mediante "confiança" do modelo.

## Consequências

Testes de EP-15 (Teste 3/4) validam a invariante.
