"""Global Supervisor / Modo A (EP-13-T05, ADR-024)."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from emcp_bus.agent_runtime.global_supervisor import (
    GlobalSupervisor,
    UnknownBackendError,
    keyword_router,
)


@dataclass
class _StubBackend:
    name: str
    calls: list[str] = field(default_factory=list)

    async def run_turn(self, message: str) -> str:
        self.calls.append(message)
        return f"{self.name} handled: {message}"


async def test_routes_to_the_current_backend_when_the_router_finds_no_match() -> None:
    sales = _StubBackend("sales_agent")
    finance = _StubBackend("finance_agent")
    supervisor = GlobalSupervisor({"sales_agent": sales, "finance_agent": finance})

    result = await supervisor.route_and_run(
        "What's the price of SKU-100?", current_backend="sales_agent", router=keyword_router
    )

    assert result.backend_name == "sales_agent"
    assert result.handed_off is False
    assert sales.calls == ["What's the price of SKU-100?"]
    assert finance.calls == []


async def test_hands_off_to_the_backend_the_router_selects() -> None:
    sales = _StubBackend("sales_agent")
    finance = _StubBackend("finance_agent")
    supervisor = GlobalSupervisor({"sales_agent": sales, "finance_agent": finance})

    result = await supervisor.route_and_run(
        "I'd like to pay my invoice", current_backend="sales_agent", router=keyword_router
    )

    assert result.backend_name == "finance_agent"
    assert result.handed_off is True
    assert finance.calls == ["I'd like to pay my invoice"]
    assert sales.calls == []


async def test_a_route_to_an_unregistered_backend_stays_on_the_current_one() -> None:
    sales = _StubBackend("sales_agent")
    supervisor = GlobalSupervisor({"sales_agent": sales})

    result = await supervisor.route_and_run(
        "I'd like to pay my invoice",  # keyword_router would pick "finance_agent"
        current_backend="sales_agent",
        router=keyword_router,
    )

    assert result.backend_name == "sales_agent"
    assert result.handed_off is False


async def test_an_unknown_current_backend_raises() -> None:
    supervisor = GlobalSupervisor({"sales_agent": _StubBackend("sales_agent")})

    with pytest.raises(UnknownBackendError):
        await supervisor.route_and_run("hi", current_backend="nope", router=keyword_router)


def test_global_supervisor_module_never_imports_the_orchestrator() -> None:
    """ADR-024's Modo A/Modo B split, made mechanically checkable: Modo A
    (this module) must never gain a dependency on `emcp_bus.orchestrator`
    (the NBA/NBO decision model) or `emcp_bus.agent_runtime.handoff_graph`
    (which consumes an `NBADecision`) -- reaching for either would silently
    turn Modo A into Modo B (EP-13-T06)."""
    import emcp_bus.agent_runtime.global_supervisor as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    imported_modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)

    assert not any(name.startswith("emcp_bus.orchestrator") for name in imported_modules)
    assert not any(
        name.startswith("emcp_bus.agent_runtime.handoff_graph") for name in imported_modules
    )
    assert not any(
        name.startswith("emcp_bus.agent_runtime.dispatcher") for name in imported_modules
    )
