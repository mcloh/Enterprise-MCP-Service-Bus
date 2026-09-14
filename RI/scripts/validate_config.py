"""CI/local check (EP-00-T03): every YAML file under config/ must validate
against its Pydantic model -- this is the thing that actually matters
(RI-PLANNING.md's "todo YAML de config tem ... validação em CI"), not just
that a JSON Schema file exists somewhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel

from emcp_bus.common.config import ConfigError, load_yaml_models
from emcp_bus.downstream.models import BackendConfig
from emcp_bus.entitlement.models import ClientProfile
from emcp_bus.identity.models import ClientRegistration
from emcp_bus.identity.shared_client_lint import find_shared_client_violations
from emcp_bus.registry.models import CapabilityManifest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"

CHECKS: list[tuple[str, type[BaseModel]]] = [
    ("clients/profiles", ClientProfile),
    ("clients", ClientRegistration),  # non-recursive glob: skips clients/profiles/
    ("backends", BackendConfig),
    ("capabilities/sales", CapabilityManifest),
    ("capabilities/finance", CapabilityManifest),
]


def main() -> int:
    had_errors = False
    client_registrations: list[ClientRegistration] = []
    for relative_dir, model in CHECKS:
        directory = CONFIG_DIR / relative_dir
        try:
            items = load_yaml_models(directory, model)
        except ConfigError as exc:
            print(f"FAIL  {relative_dir}: {exc}")
            had_errors = True
            continue
        print(f"OK    {relative_dir}: {len(items)} file(s) validated against {model.__name__}")
        if model is ClientRegistration:
            client_registrations = items  # type: ignore[assignment]

    # EP-01-T05: two agents sharing an MCP Client identity must resolve to
    # the same profile (README.md §18/§35) -- a config-shape check schema
    # validation alone cannot express, since it spans multiple files.
    violations = find_shared_client_violations(client_registrations)
    if violations:
        for violation in violations:
            print(f"FAIL  clients (shared-client lint): {violation}")
        had_errors = True
    else:
        print("OK    clients (shared-client lint): no violations")

    if had_errors:
        print("\nConfig validation failed.")
        return 1
    print("\nAll config files validate against their schema.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
