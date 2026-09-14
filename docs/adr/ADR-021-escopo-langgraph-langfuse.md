# ADR-021: Escopo de LangGraph e Langfuse na RI

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão — não é mais gerado a partir de `docs/RI-PLANNING.md` (removido do repositório após a conclusão do marco M4; histórico preservado no git). Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Escopo de LangGraph/Langfuse (fecha G8/P8).

## Decisão

LangGraph somente no Service Orchestrator (EP-11) e handoff do Agent Runtime (EP-12); Langfuse somente onde há chamada real a LLM (EP-13). Checkpointer: SQLite em dev.

## Alternativas consideradas

Usar LangGraph também no Gateway/Fabric para "consistência de stack".

## Consequências

Evita over-engineering vetado pela seção 6 do superprompt; Gateway/Fabric continuam Python puro.
