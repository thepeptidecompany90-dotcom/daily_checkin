from glp1_agent.domain.models import JourneyState

# Confirmed V1 transition table (docs/domain-model.md §3, §17).
# Anything not listed here is illegal and must be rejected rather than silently applied.
_ALLOWED_TRANSITIONS: dict[JourneyState, frozenset[JourneyState]] = {
    JourneyState.CONSULTED: frozenset({JourneyState.PRESCRIBED, JourneyState.DISCONTINUED}),
    JourneyState.PRESCRIBED: frozenset({JourneyState.STARTING, JourneyState.DISCONTINUED}),
    JourneyState.STARTING: frozenset({JourneyState.EARLY_TREATMENT, JourneyState.DISCONTINUED}),
    JourneyState.EARLY_TREATMENT: frozenset({JourneyState.ESTABLISHED, JourneyState.DISCONTINUED}),
    JourneyState.ESTABLISHED: frozenset(
        {JourneyState.DOSE_CHANGE, JourneyState.DISCONTINUED}
    ),
    JourneyState.DOSE_CHANGE: frozenset(
        {JourneyState.EARLY_TREATMENT, JourneyState.DISCONTINUED}
    ),
    JourneyState.DISCONTINUED: frozenset(),
}


class IllegalTransitionError(ValueError):
    def __init__(self, current: JourneyState, target: JourneyState):
        super().__init__(f"Illegal journey transition: {current} -> {target}")
        self.current = current
        self.target = target


def can_transition(current: JourneyState, target: JourneyState) -> bool:
    return target in _ALLOWED_TRANSITIONS[current]


def require_transition(current: JourneyState, target: JourneyState) -> None:
    if not can_transition(current, target):
        raise IllegalTransitionError(current, target)
