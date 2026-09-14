"""Global Capability Registry storage (EP-02-T03, README.md §6.6, ADR-010).

A control-plane asset, deliberately separate from the per-client catalog
view the Gateway serves (README.md §6.6: "O Global Registry é um
control-plane asset. Ele não deve ser confundido com a visão de catálogo
entregue a cada client."). Consumers (Gateway, Fabric, Offering Filter) only
ever read through `list_active`/`get` -- nothing outside the publishing
pipeline (EP-02-T02) writes here, and the pipeline never writes directly:
it only transitions status through `lifecycle.py`.

SQLite, used synchronously: this store is not on the Gateway's request
hot path in this milestone (routing is still static, EP-06 wires it in
later), and SQLite operations here are single-digit milliseconds -- an
`asyncio.to_thread` wrapper is a straightforward addition if/when a caller
needs this off the event loop.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from emcp_bus.registry.models import CapabilityManifest, LifecycleStatus


class CapabilityNotFoundError(Exception):
    pass


class RegistryStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS capabilities (
                    name TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    lifecycle_status TEXT NOT NULL
                )
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert(self, manifest: CapabilityManifest) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO capabilities (name, domain, manifest_json, lifecycle_status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    domain = excluded.domain,
                    manifest_json = excluded.manifest_json,
                    lifecycle_status = excluded.lifecycle_status
                """,
                (
                    manifest.name,
                    manifest.domain,
                    manifest.model_dump_json(),
                    manifest.lifecycle.status.value,
                ),
            )

    def get(self, name: str) -> CapabilityManifest:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT manifest_json FROM capabilities WHERE name = ?", (name,)
            ).fetchone()
        if row is None:
            raise CapabilityNotFoundError(name)
        return CapabilityManifest.model_validate_json(row[0])

    def list_by_domain(self, domain: str) -> list[CapabilityManifest]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT manifest_json FROM capabilities WHERE domain = ? ORDER BY name", (domain,)
            ).fetchall()
        return [CapabilityManifest.model_validate_json(row[0]) for row in rows]

    def list_active(self) -> list[CapabilityManifest]:
        """What Gateway/Fabric/Offering Filter are allowed to read (README.md §6.6) --
        anything still in nominate/review/register, or already deprecated/retired,
        is a control-plane-only concern."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT manifest_json FROM capabilities WHERE lifecycle_status = ? ORDER BY name",
                (LifecycleStatus.ACTIVE.value,),
            ).fetchall()
        return [CapabilityManifest.model_validate_json(row[0]) for row in rows]

    def set_lifecycle_status(self, name: str, status: LifecycleStatus) -> None:
        manifest = self.get(name)
        updated = manifest.model_copy(
            update={"lifecycle": manifest.lifecycle.model_copy(update={"status": status})}
        )
        self.upsert(updated)
