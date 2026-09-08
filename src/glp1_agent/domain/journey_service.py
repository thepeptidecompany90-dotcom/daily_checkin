from uuid import UUID

from glp1_agent.db.repositories.journey_repo import JourneyRepo
from glp1_agent.domain.journey_state_machine import require_transition
from glp1_agent.domain.models import Journey, JourneyState, JourneyStateHistoryItem


class JourneyService:
    def __init__(self, journey_repo: JourneyRepo):
        self._journeys = journey_repo

    async def transition(
        self, patient_id: UUID, target_state: JourneyState, reason: str | None
    ) -> Journey:
        """Move the patient's journey to `target_state`, enforcing journey_state_machine's
        transition table rather than allowing an arbitrary state to be written."""
        current = await self._journeys.get_current(patient_id)
        require_transition(current.state, target_state)
        return await self._journeys.append_transition(current.id, target_state, reason)

    async def history(self, patient_id: UUID) -> list[JourneyStateHistoryItem]:
        return await self._journeys.history(patient_id)
