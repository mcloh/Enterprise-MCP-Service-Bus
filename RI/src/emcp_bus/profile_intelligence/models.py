"""ProfileView contract (EP-09-T01, README.md §6.10, Axiom 11).

Field names and shape follow the README §6.10 example exactly (`subjectRef`,
`profileVersion`, `segments`, `attributes`, `reasonCodes`, `expiresAt`) --
"Os nomes acima são ilustrativos. A arquitetura não prescreve taxonomia,
algoritmo, número de clusters ou atributos específicos", so this model is
deliberately generic: any `ProfileIntelligenceProvider` implementation
(rule-based here, EP-09-T02; a real clustering/ML model in a production
fork) produces the same contract. A `ProfileView` only ever *orders or
reduces* candidates for the Offering Filter (EP-10) -- it is never consulted
by the PDP (EP-03) and can never grant a capability outside
MaximumEntitlement (Axiom 11): nothing in this module, or anything that
consumes it, is wired into the authorization path.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Segment(BaseModel):
    id: str
    score: float = Field(ge=0.0, le=1.0)


class ProfileView(BaseModel):
    subject_ref: str = Field(
        description="Pseudonymized subject identifier, e.g. 'subject:7f31c2' -- "
        "never a raw PII identifier (README.md §6.10 governance requirements, "
        "EP-09-T03's guardrail)."
    )
    profile_version: str
    segments: list[Segment] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    expires_at: datetime
