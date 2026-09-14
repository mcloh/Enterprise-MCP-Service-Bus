# ADR-004: Contexto agentico nunca eleva privilegio

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão. Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Contexto agêntico pode elevar privilégio?

## Decisão

Nunca — contexto só pode subtrair (`Context may subtract, must never add`).

## Alternativas consideradas

Permitir elevação mediante "confiança" do modelo.

## Consequências

Testes de EP-15 (Teste 3/4) validam a invariante.
