# ADR-001: Fronteira de MaximumEntitlement no MCP Client

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão. Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Quem define o teto de privilégio do agente.

## Decisão

MCP Client (identidade autenticada) é a fronteira de `MaximumEntitlement`, nunca o agente/prompt.

## Alternativas consideradas

Autorização por role autodeclarado do agente.

## Consequências

Todo design de EP-01/EP-04 gira em torno da identidade do client, não do agente.
