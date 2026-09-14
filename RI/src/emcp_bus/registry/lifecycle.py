"""Registry lifecycle state machine (EP-02-T04, README.md §23).

    Nominate -> Review -> Register -> Publish -> Observe
                                          Observe -> Change -> Publish
                                          Observe -> Deprecate -> Retire

`ACTIVE` collapses README.md's Publish+Observe into one steady state (a
manifest that is live and being observed simultaneously, from this RI's
point of view -- there is no separate "being observed" flag to track). The
one invariant every caller of `transition()` gets for free is the one this
task's acceptance criterion names directly: nothing reaches `ACTIVE` without
having passed through `REVIEW` first.
"""

from __future__ import annotations

from emcp_bus.registry.models import LifecycleStatus

_ALLOWED_TRANSITIONS: dict[LifecycleStatus, frozenset[LifecycleStatus]] = {
    LifecycleStatus.NOMINATE: frozenset({LifecycleStatus.REVIEW}),
    # A rejected review goes back to NOMINATE (revise and resubmit) rather
    # than staying stuck in REVIEW or disappearing from the registry.
    LifecycleStatus.REVIEW: frozenset({LifecycleStatus.REGISTER, LifecycleStatus.NOMINATE}),
    LifecycleStatus.REGISTER: frozenset({LifecycleStatus.ACTIVE}),
    # "Change" (README.md §23) re-publishes an already-active capability;
    # modeled as ACTIVE -> ACTIVE rather than a distinct state.
    LifecycleStatus.ACTIVE: frozenset({LifecycleStatus.ACTIVE, LifecycleStatus.DEPRECATED}),
    LifecycleStatus.DEPRECATED: frozenset({LifecycleStatus.RETIRED}),
    LifecycleStatus.RETIRED: frozenset(),
}


class InvalidLifecycleTransitionError(Exception):
    pass


def validate_transition(current: LifecycleStatus, target: LifecycleStatus) -> None:
    """Raises `InvalidLifecycleTransitionError` unless `current -> target` is
    an allowed edge of the state machine above."""
    if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidLifecycleTransitionError(
            f"{current.value} -> {target.value} is not an allowed registry "
            f"lifecycle transition (README.md §23)"
        )
