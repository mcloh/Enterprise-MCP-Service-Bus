# ADR-005: Cache privado de tools/list

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão — não é mais gerado a partir de `docs/RI-PLANNING.md` (removido do repositório após a conclusão do marco M4; histórico preservado no git). Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Cache de `tools/list` entre clients.

## Decisão

`cacheScope=private`, chave = identidade+contexto+policy_version.

## Alternativas consideradas

Cache compartilhado por performance.

## Consequências

EP-05-T03; teste dedicado de isolamento (EP-15).
