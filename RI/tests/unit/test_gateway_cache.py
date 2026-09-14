"""Private tools/list cache hint (EP-05-T03, README.md §13/§28)."""

from __future__ import annotations

import pytest

from emcp_bus.gateway.cache import tools_list_cache_hint


def test_default_hint_is_private_scope_with_a_positive_ttl() -> None:
    hint = tools_list_cache_hint()

    assert hint.scope == "private"
    assert hint.ttl_ms > 0


def test_ttl_is_configurable_via_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMCP_TOOLS_LIST_CACHE_TTL_MS", "12345")

    hint = tools_list_cache_hint()

    assert hint.ttl_ms == 12345
    assert hint.scope == "private"  # never configurable to "public" (Teste 5, §45)
