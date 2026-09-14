"""Identity Resolver / BusinessContext (EP-12-T04, ADR-022, ADR-023)."""

from __future__ import annotations

from pathlib import Path

from emcp_bus.agent_runtime.identity_resolver import IdentityResolver, IdentityResolverConfig
from emcp_bus.common.config import load_yaml_model

REPO_ROOT = Path(__file__).parents[2]
IDENTITY_YAML = REPO_ROOT / "config" / "orchestrator" / "identity.yaml"


def test_resolve_maps_a_declared_alias_to_its_canonical_key() -> None:
    resolver = IdentityResolver(IdentityResolverConfig(aliases={"msisdn": "customer_key"}))

    result = resolver.resolve({"msisdn": "+5511999999999"})

    assert result == {"customer_key": "+5511999999999"}


def test_resolve_passes_through_unaliased_keys_unchanged() -> None:
    resolver = IdentityResolver(IdentityResolverConfig(aliases={"msisdn": "customer_key"}))

    result = resolver.resolve({"amount": 100})

    assert result == {"amount": 100}


def test_the_real_seed_identity_yaml_validates_and_resolves_msisdn() -> None:
    config = load_yaml_model(IDENTITY_YAML, IdentityResolverConfig)
    resolver = IdentityResolver(config)

    result = resolver.resolve({"msisdn": "+5511999999999"})

    assert result == {"customer_key": "+5511999999999"}


def test_identity_resolver_module_never_imports_pdp_or_entitlement() -> None:
    """ADR-023's guardrail, made mechanically checkable: this module must
    never gain a dependency on the authorization path."""
    import ast

    import emcp_bus.agent_runtime.identity_resolver as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    imported_modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)

    assert not any(name.startswith("emcp_bus.pdp") for name in imported_modules)
    assert not any(name.startswith("emcp_bus.entitlement") for name in imported_modules)
