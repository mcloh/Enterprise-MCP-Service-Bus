"""Exports JSON Schema for every declarative config/contract model in the RI
into schemas/*.schema.json (EP-00-T02/T03: "todo YAML de config tem JSON
Schema"). Run via `make export-schemas`; CI (`make validate-schemas`) checks
the committed files are up to date rather than regenerating them silently.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from emcp_bus.approval.models import ApprovalRequest
from emcp_bus.downstream.models import BackendConfig
from emcp_bus.entitlement.models import ClientProfile
from emcp_bus.identity.models import ClientRegistration
from emcp_bus.pdp.models import PDPDecision
from emcp_bus.registry.models import CapabilityManifest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = REPO_ROOT / "schemas"

MODELS: dict[str, type[BaseModel]] = {
    "client-registration": ClientRegistration,
    "client-profile": ClientProfile,
    "capability-manifest": CapabilityManifest,
    "backend-credentials": BackendConfig,
    "approval-request": ApprovalRequest,
    "pdp-decision": PDPDecision,
}


def main() -> None:
    SCHEMAS_DIR.mkdir(exist_ok=True)
    for file_stem, model in MODELS.items():
        schema = model.model_json_schema()
        path = SCHEMAS_DIR / f"{file_stem}.schema.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
