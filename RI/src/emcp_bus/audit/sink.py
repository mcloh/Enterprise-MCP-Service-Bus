"""Audit event sinks (EP-08-T02).

Append-only by contract: nothing in this module ever updates or deletes a
previously emitted event. `JSONLFileAuditSink` is the dev/deploy default
(one JSON object per line); `InMemoryAuditSink` exists purely for tests that
need to assert on emitted events without touching a filesystem. A Postgres
sink is a documented future extension (same `AuditSink` protocol), not
implemented in this RI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from emcp_bus.audit.models import EventEnvelope


class AuditSink(Protocol):
    def emit(self, event: EventEnvelope) -> None: ...


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    def emit(self, event: EventEnvelope) -> None:
        self.events.append(event)


class JSONLFileAuditSink:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: EventEnvelope) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")
