import pytest

from glp1_agent.db.repositories.journey_repo import JourneyRepo
from glp1_agent.domain.journey_service import JourneyService
from glp1_agent.domain.journey_state_machine import IllegalTransitionError
from glp1_agent.domain.models import JourneyState
from tests.helpers import seed_journey, seed_patient


async def test_legal_transition_appends_and_closes_history_rows(conn):
    patient_id = await seed_patient(conn)
    await seed_journey(conn, patient_id, JourneyState.STARTING.value)
    service = JourneyService(JourneyRepo(conn))

    updated = await service.transition(patient_id, JourneyState.EARLY_TREATMENT, reason="test")

    assert updated.state == JourneyState.EARLY_TREATMENT

    history = await service.history(patient_id)
    assert len(history) == 2
    by_state = {h.state: h for h in history}
    assert by_state[JourneyState.STARTING].ended_at is not None
    assert by_state[JourneyState.EARLY_TREATMENT].ended_at is None
    assert by_state[JourneyState.EARLY_TREATMENT].transition_reason == "test"


async def test_illegal_transition_raises_and_leaves_history_untouched(conn):
    patient_id = await seed_patient(conn)
    await seed_journey(conn, patient_id, JourneyState.STARTING.value)
    service = JourneyService(JourneyRepo(conn))

    with pytest.raises(IllegalTransitionError):
        await service.transition(patient_id, JourneyState.ESTABLISHED, reason=None)

    history = await service.history(patient_id)
    assert len(history) == 1
    assert history[0].state == JourneyState.STARTING
    assert history[0].ended_at is None
