"""Prompt versioning (EP-13-T04, `could`, README.md's Langfuse Prompt
Management use case).

A local, in-memory version store is the testable core of the acceptance
criterion ("uma mudança de prompt gera nova versão rastreável, sem
sobrescrever a anterior") -- syncing this same data to Langfuse's own Prompt
Management API (`langfuse.api.prompts.create`, one version per `publish()`
call) is a thin adapter over `PromptVersionStore`, not implemented here
since EP-13-T02 (Langfuse self-hosted) is config-only in this session (see
RI/README.md limitations) -- there is no running Langfuse instance to sync
to. `traces` (EP-13-T01's agent turns) would reference `PromptVersion.version`
the same way README.md §6 describes referencing a prompt version in a trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


class UnknownPromptError(Exception):
    pass


@dataclass(frozen=True)
class PromptVersion:
    name: str
    version: int
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class PromptVersionStore:
    def __init__(self) -> None:
        self._versions: dict[str, list[PromptVersion]] = {}

    def publish(self, name: str, content: str) -> PromptVersion:
        """Always appends -- never overwrites or mutates a prior version,
        even if `content` is identical to the latest one."""
        history = self._versions.setdefault(name, [])
        version = PromptVersion(name=name, version=len(history) + 1, content=content)
        history.append(version)
        return version

    def latest(self, name: str) -> PromptVersion:
        history = self._versions.get(name)
        if not history:
            raise UnknownPromptError(name)
        return history[-1]

    def history(self, name: str) -> list[PromptVersion]:
        return list(self._versions.get(name, []))
