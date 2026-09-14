# ADR-016: Contrato de dispatch/handoff do Agent Runtime

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão. Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Contrato de dispatch/handoff do Agent Runtime.

## Decisão

Objeto de dispatch versionado (`decisionId`, `expiresAt`, `reasonCodes`) que não substitui o token do MCP Client.

## Alternativas consideradas

Runtime injetar credenciais próprias no agente.

## Consequências

EP-12-T01 consome exclusivamente o dispatch object + MCP Client já existente.
