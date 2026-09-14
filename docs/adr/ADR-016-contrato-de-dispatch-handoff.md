# ADR-016: Contrato de dispatch/handoff do Agent Runtime

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-016 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Contrato de dispatch/handoff do Agent Runtime.

## Decisão

Objeto de dispatch versionado (`decisionId`, `expiresAt`, `reasonCodes`) que não substitui o token do MCP Client.

## Alternativas consideradas

Runtime injetar credenciais próprias no agente.

## Consequências

EP-12-T01 consome exclusivamente o dispatch object + MCP Client já existente.
