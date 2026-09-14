"""Journey StateGraph (EP-11-T02/T04/T05), against real OPA + the real seed
config/ + a real SQLite checkpointer -- not hand-built fixtures, matching
the rest of this RI's "real dependencies over mocks" testing style.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from emcp_bus.common.config import load_yaml_model, load_yaml_models
from emcp_bus.entitlement.manager import EntitlementManager
from emcp_bus.entitlement.models import ClientProfile
from emcp_bus.identity.models import ClientRegistration
from emcp_bus.offering_filter.service import ConsentContext, OfferingFilterService
from emcp_bus.orchestrator.decision_context import DecisionContext
from emcp_bus.orchestrator.decisioning import DEFAULT_AGENT, RuleBasedNBADecisionModel
from emcp_bus.orchestrator.graph import build_journey_graph
from emcp_bus.orchestrator.nba_model import NBADecision
from emcp_bus.pdp.client import PDPClient, compute_policy_version
from emcp_bus.profile_intelligence.rule_based_provider import RuleBasedProfileProvider
from emcp_bus.registry.seed import load_all_capability_manifests, publish_all
from emcp_bus.registry.store import RegistryStore

REPO_ROOT = Path(__file__).parents[2]
POLICIES_DIR = REPO_ROOT / "config" / "policies"
PROFILES_DIR = REPO_ROOT / "config" / "clients" / "profiles"
CLIENTS_DIR = REPO_ROOT / "config" / "clients"
CAPABILITIES_DIR = REPO_ROOT / "config" / "capabilities"

SALES_READ_CLIENT_ID = "sales-read-agent"
FINANCE_PAYMENTS_CLIENT_ID = "finance-payments-agent"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
async def entitlement_manager() -> AsyncIterator[EntitlementManager]:
    opa_binary = shutil.which(os.environ.get("OPA_BINARY", "opa"))
    if opa_binary is None:
        pytest.skip("opa binary not found on PATH (set OPA_BINARY or install it)")

    port = _free_port()
    process = subprocess.Popen(
        [opa_binary, "run", "--server", "--addr", f"127.0.0.1:{port}", str(POLICIES_DIR)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pdp = PDPClient(
        base_url=f"http://127.0.0.1:{port}", policy_version=compute_policy_version(POLICIES_DIR)
    )
    try:
        for _ in range(100):
            try:
                await pdp._http.get("/health")
                break
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.05)
        else:
            raise RuntimeError("opa server did not become healthy in time")

        manager = EntitlementManager(pdp)
        manager.load_registrations(
            [
                load_yaml_model(path, ClientRegistration)
                for path in sorted(CLIENTS_DIR.glob("*.yaml"))
            ]
        )
        manager.load_profiles(load_yaml_models(PROFILES_DIR, ClientProfile))
        await manager.sync_profiles_to_pdp()
        yield manager
    finally:
        await pdp.aclose()
        process.terminate()
        process.wait(timeout=5)


@pytest.fixture
def offering_filter(tmp_path: Path) -> OfferingFilterService:
    store = RegistryStore(tmp_path / "registry.db")
    publish_all(store, load_all_capability_manifests(CAPABILITIES_DIR))
    return OfferingFilterService(store)


@pytest.fixture
def sqlite_saver() -> Iterator[SqliteSaver]:
    with (
        tempfile.TemporaryDirectory() as tmp_dir,
        SqliteSaver.from_conn_string(str(Path(tmp_dir) / "checkpoints.db")) as saver,
    ):
        yield saver


class _PreferPaymentExecuteModel:
    """A second `NBADecisionModel` (demonstrating EP-11-T03's pluggability):
    unlike `RuleBasedNBADecisionModel` (least-friction-first), this one
    prefers `finance.payment.execute` when it survives EP-10's filter --
    used here purely to reach the approval-required branch deterministically
    (`RuleBasedNBADecisionModel` would pick the R1 `invoice.get` instead,
    which never requires approval)."""

    def decide(self, context: DecisionContext) -> NBADecision | None:
        offerings_by_name = {o.name: o for o in context.filtered_offerings}
        offering = offerings_by_name.get("finance.payment.execute") or next(
            iter(context.filtered_offerings), None
        )
        if offering is None:
            return None
        return NBADecision(
            decision_id="dec-test-fixed",
            action=offering.name,
            capability_version=offering.version,
            subject_ref=context.profile.subject_ref,
            channel=context.runtime_context.channel,
            agent=DEFAULT_AGENT,
            reason_codes=["ELIGIBLE"],
            policy_context={"entitlementVersion": context.entitlement_version},
            expires_at=context.resolved_at,
        )


async def test_journey_runs_end_to_end_when_no_approval_is_needed(
    entitlement_manager: EntitlementManager,
    offering_filter: OfferingFilterService,
    sqlite_saver: SqliteSaver,
) -> None:
    graph = build_journey_graph(
        profile_provider=RuleBasedProfileProvider(),
        entitlement_manager=entitlement_manager,
        offering_filter=offering_filter,
        decision_model=RuleBasedNBADecisionModel(),
        checkpointer=sqlite_saver,
    )
    config: RunnableConfig = {"configurable": {"thread_id": "journey-1"}}

    result = graph.invoke(
        {"client_id": SALES_READ_CLIENT_ID, "raw_subject_id": "subject:test-1", "channel": "app"},
        config,
    )

    assert result["nba"] is not None
    assert result["nba"].action.startswith("sales.")
    assert result["approval_status"] == "not_required"
    assert "__interrupt__" not in result


async def test_journey_pauses_at_approval_gate_for_a_high_risk_nba(
    entitlement_manager: EntitlementManager,
    offering_filter: OfferingFilterService,
    sqlite_saver: SqliteSaver,
) -> None:
    """finance.payment.execute (R3) requires approval -- README.md §26. With
    consent for restricted data (so it survives EP-10's filter) and a
    Finance.Payments client, the journey graph must pause at approval_gate,
    never silently proceeding as if approved."""
    graph = build_journey_graph(
        profile_provider=RuleBasedProfileProvider(),
        entitlement_manager=entitlement_manager,
        offering_filter=offering_filter,
        decision_model=_PreferPaymentExecuteModel(),
        checkpointer=sqlite_saver,
        consent_context=ConsentContext(allow_restricted_data=True),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "journey-2"}}

    result = graph.invoke(
        {
            "client_id": FINANCE_PAYMENTS_CLIENT_ID,
            "raw_subject_id": "subject:test-2",
            "channel": "app",
        },
        config,
    )

    assert "__interrupt__" in result
    assert "approval_status" not in result  # not yet decided -- no implicit ALLOW

    state = graph.get_state(config)
    assert state.next == ("approval_gate",)


async def test_resuming_an_approval_gate_does_not_reprocess_earlier_nodes(
    entitlement_manager: EntitlementManager,
    offering_filter: OfferingFilterService,
    sqlite_saver: SqliteSaver,
) -> None:
    """EP-11-T02's checkpoint-resume acceptance criterion: resolve_profile/
    resolve_entitlement/filter_offerings/decide_nba must not re-run when the
    graph resumes from a paused approval_gate."""
    profile_calls = 0
    real_provider = RuleBasedProfileProvider()

    class CountingProfileProvider:
        def resolve(self, subject_ref: str, *, as_of: object = None) -> object:
            nonlocal profile_calls
            profile_calls += 1
            return real_provider.resolve(subject_ref)

    graph = build_journey_graph(
        profile_provider=CountingProfileProvider(),  # type: ignore[arg-type]
        entitlement_manager=entitlement_manager,
        offering_filter=offering_filter,
        decision_model=_PreferPaymentExecuteModel(),
        checkpointer=sqlite_saver,
        consent_context=ConsentContext(allow_restricted_data=True),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "journey-3"}}

    graph.invoke(
        {
            "client_id": FINANCE_PAYMENTS_CLIENT_ID,
            "raw_subject_id": "subject:test-3",
            "channel": "app",
        },
        config,
    )
    assert profile_calls == 1

    # Simulate "the process restarted": a fresh CompiledStateGraph, same
    # checkpointer/thread_id -- the paused state must already be there.
    resumed_graph = build_journey_graph(
        profile_provider=CountingProfileProvider(),  # type: ignore[arg-type]
        entitlement_manager=entitlement_manager,
        offering_filter=offering_filter,
        decision_model=_PreferPaymentExecuteModel(),
        checkpointer=sqlite_saver,
        consent_context=ConsentContext(allow_restricted_data=True),
    )
    result = resumed_graph.invoke(Command(resume="approved"), config)

    assert profile_calls == 1  # unchanged -- resolve_profile did not re-run
    assert result["approval_status"] == "approved"


async def test_resuming_with_a_non_approved_decision_denies(
    entitlement_manager: EntitlementManager,
    offering_filter: OfferingFilterService,
    sqlite_saver: SqliteSaver,
) -> None:
    graph = build_journey_graph(
        profile_provider=RuleBasedProfileProvider(),
        entitlement_manager=entitlement_manager,
        offering_filter=offering_filter,
        decision_model=_PreferPaymentExecuteModel(),
        checkpointer=sqlite_saver,
        consent_context=ConsentContext(allow_restricted_data=True),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "journey-4"}}

    graph.invoke(
        {
            "client_id": FINANCE_PAYMENTS_CLIENT_ID,
            "raw_subject_id": "subject:test-4",
            "channel": "app",
        },
        config,
    )
    result = graph.invoke(Command(resume="denied"), config)

    assert result["approval_status"] == "denied"


async def test_denial_reentry_recalculates_nba_excluding_the_denied_action(
    entitlement_manager: EntitlementManager,
    offering_filter: OfferingFilterService,
    sqlite_saver: SqliteSaver,
) -> None:
    """EP-11-T04: after a real Gateway DENY for the first NBA, re-invoking
    the graph with `denied_action` set recomputes NBA over the remaining
    offerings -- never by calling any backend directly (fallback.py has no
    such code path at all)."""
    graph = build_journey_graph(
        profile_provider=RuleBasedProfileProvider(),
        entitlement_manager=entitlement_manager,
        offering_filter=offering_filter,
        decision_model=RuleBasedNBADecisionModel(),
        checkpointer=sqlite_saver,
    )
    config: RunnableConfig = {"configurable": {"thread_id": "journey-5"}}

    first = graph.invoke(
        {"client_id": SALES_READ_CLIENT_ID, "raw_subject_id": "subject:test-5", "channel": "app"},
        config,
    )
    first_action = first["nba"].action

    second = graph.invoke({"denied_action": first_action}, config)

    assert second["denial_outcome"] in {"recalculated", "ended"}
    if second["denial_outcome"] == "recalculated":
        assert second["nba"] is not None
        assert second["nba"].action != first_action
    else:
        assert second["nba"] is None
