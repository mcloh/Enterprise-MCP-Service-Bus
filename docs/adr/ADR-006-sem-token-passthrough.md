# ADR-006: Proibicao de token passthrough

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão — não é mais gerado a partir de `docs/RI-PLANNING.md` (removido do repositório após a conclusão do marco M4; histórico preservado no git). Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Token do agente pode ser repassado ao backend?

## Decisão

Não — proibido blind token passthrough; inbound ≠ outbound identity.

## Alternativas consideradas

Passthrough direto do token do client.

## Consequências

EP-07 implementa exchange/service account por backend.
