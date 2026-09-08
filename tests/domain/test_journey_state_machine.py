import pytest

from glp1_agent.domain.journey_state_machine import (
    IllegalTransitionError,
    can_transition,
    require_transition,
)
from glp1_agent.domain.models import JourneyState

LEGAL_TRANSITIONS = [
    (JourneyState.CONSULTED, JourneyState.PRESCRIBED),
    (JourneyState.PRESCRIBED, JourneyState.STARTING),
    (JourneyState.STARTING, JourneyState.EARLY_TREATMENT),
    (JourneyState.EARLY_TREATMENT, JourneyState.ESTABLISHED),
    (JourneyState.ESTABLISHED, JourneyState.DOSE_CHANGE),
    (JourneyState.DOSE_CHANGE, JourneyState.EARLY_TREATMENT),
    (JourneyState.CONSULTED, JourneyState.DISCONTINUED),
    (JourneyState.PRESCRIBED, JourneyState.DISCONTINUED),
    (JourneyState.STARTING, JourneyState.DISCONTINUED),
    (JourneyState.EARLY_TREATMENT, JourneyState.DISCONTINUED),
    (JourneyState.ESTABLISHED, JourneyState.DISCONTINUED),
    (JourneyState.DOSE_CHANGE, JourneyState.DISCONTINUED),
]


@pytest.mark.parametrize("current,target", LEGAL_TRANSITIONS)
def test_legal_transitions_allowed(current, target):
    assert can_transition(current, target) is True
    require_transition(current, target)  # must not raise


ALL_PAIRS = [(c, t) for c in JourneyState for t in JourneyState]
ILLEGAL_TRANSITIONS = [pair for pair in ALL_PAIRS if pair not in LEGAL_TRANSITIONS]


@pytest.mark.parametrize("current,target", ILLEGAL_TRANSITIONS)
def test_illegal_transitions_rejected(current, target):
    assert can_transition(current, target) is False
    with pytest.raises(IllegalTransitionError):
        require_transition(current, target)


def test_discontinued_is_terminal():
    for target in JourneyState:
        assert can_transition(JourneyState.DISCONTINUED, target) is False


def test_no_skipping_early_treatment_stage():
    # STARTING must not jump straight to ESTABLISHED
    assert can_transition(JourneyState.STARTING, JourneyState.ESTABLISHED) is False


def test_dose_change_reenters_early_treatment_not_established_directly():
    assert can_transition(JourneyState.DOSE_CHANGE, JourneyState.ESTABLISHED) is False
    assert can_transition(JourneyState.DOSE_CHANGE, JourneyState.EARLY_TREATMENT) is True
