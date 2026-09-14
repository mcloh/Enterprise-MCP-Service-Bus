# ADR-021: Escopo de LangGraph e Langfuse na RI

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-021 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Escopo de LangGraph/Langfuse (fecha G8/P8).

## Decisão

LangGraph somente no Service Orchestrator (EP-11) e handoff do Agent Runtime (EP-12); Langfuse somente onde há chamada real a LLM (EP-13). Checkpointer: SQLite em dev.

## Alternativas consideradas

Usar LangGraph também no Gateway/Fabric para "consistência de stack".

## Consequências

Evita over-engineering vetado pela seção 6 do superprompt; Gateway/Fabric continuam Python puro.
