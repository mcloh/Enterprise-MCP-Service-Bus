# ADR-006: Proibicao de token passthrough

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-006 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Token do agente pode ser repassado ao backend?

## Decisão

Não — proibido blind token passthrough; inbound ≠ outbound identity.

## Alternativas consideradas

Passthrough direto do token do client.

## Consequências

EP-07 implementa exchange/service account por backend.
