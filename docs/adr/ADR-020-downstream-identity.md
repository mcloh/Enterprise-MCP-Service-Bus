# ADR-020: Downstream identity: token exchange ou service account isolado

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-020 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Downstream identity na RI (fecha G5/P5).

## Decisão

Token exchange (RFC 8693) quando backend suporta OIDC; senão service account isolado por adapter.

## Alternativas consideradas

Reutilizar sempre o token do client (proibido por ADR-006).

## Consequências

EP-07; documentado por backend em manifesto.
