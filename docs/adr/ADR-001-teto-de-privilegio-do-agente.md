# ADR-001: Fronteira de MaximumEntitlement no MCP Client

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-001 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Quem define o teto de privilégio do agente.

## Decisão

MCP Client (identidade autenticada) é a fronteira de `MaximumEntitlement`, nunca o agente/prompt.

## Alternativas consideradas

Autorização por role autodeclarado do agente.

## Consequências

Todo design de EP-01/EP-04 gira em torno da identidade do client, não do agente.
