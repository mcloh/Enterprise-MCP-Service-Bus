# ADR-020: Downstream identity: token exchange ou service account isolado

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão — não é mais gerado a partir de `docs/RI-PLANNING.md` (removido do repositório após a conclusão do marco M4; histórico preservado no git). Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Downstream identity na RI (fecha G5/P5).

## Decisão

Token exchange (RFC 8693) quando backend suporta OIDC; senão service account isolado por adapter.

## Alternativas consideradas

Reutilizar sempre o token do client (proibido por ADR-006).

## Consequências

EP-07; documentado por backend em manifesto.
