from uuid import UUID

import asyncpg

from glp1_agent.domain.models import Journey, JourneyState, JourneyStateHistoryItem


class JourneyRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_current(self, patient_id: UUID) -> Journey:
        row = await self._pool.fetchrow(
            """
            SELECT pj.id AS journey_id, pj.patient_id, h.state, h.started_at AS state_started_at
            FROM patient_journeys pj
            JOIN journey_state_history h ON h.journey_id = pj.id AND h.ended_at IS NULL
            WHERE pj.patient_id = $1 AND pj.status = 'active'
            """,
            patient_id,
        )
        if row is None:
            raise LookupError(f"no active journey for patient {patient_id}")
        return Journey(
            id=row["journey_id"],
            patient_id=row["patient_id"],
            state=JourneyState(row["state"]),
            state_started_at=row["state_started_at"],
        )

    async def append_transition(
        self, journey_id: UUID, state: JourneyState, reason: str | None
    ) -> Journey:
        """Close the open journey_state_history row and append a new one (docs/domain-model.md §4.2)."""
        await self._pool.execute(
            "UPDATE journey_state_history SET ended_at = now() WHERE journey_id = $1 AND ended_at IS NULL",
            journey_id,
        )
        row = await self._pool.fetchrow(
            """
            INSERT INTO journey_state_history (journey_id, state, transition_reason)
            VALUES ($1, $2::journey_state, $3)
            RETURNING journey_id, state, started_at
            """,
            journey_id,
            state.value,
            reason,
        )
        patient_id = await self._pool.fetchval(
            "SELECT patient_id FROM patient_journeys WHERE id = $1", journey_id
        )
        return Journey(
            id=row["journey_id"],
            patient_id=patient_id,
            state=JourneyState(row["state"]),
            state_started_at=row["started_at"],
        )

    async def history(self, patient_id: UUID) -> list[JourneyStateHistoryItem]:
        rows = await self._pool.fetch(
            """
            SELECT h.id, h.state, h.started_at, h.ended_at, h.transition_reason
            FROM journey_state_history h
            JOIN patient_journeys pj ON pj.id = h.journey_id
            WHERE pj.patient_id = $1
            ORDER BY h.started_at DESC
            """,
            patient_id,
        )
        return [
            JourneyStateHistoryItem(
                id=r["id"],
                state=JourneyState(r["state"]),
                started_at=r["started_at"],
                ended_at=r["ended_at"],
                transition_reason=r["transition_reason"],
            )
            for r in rows
        ]
