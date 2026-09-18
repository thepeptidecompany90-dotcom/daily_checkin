from uuid import UUID

import asyncpg

from glp1_agent.domain.models import (
    ClinicianInstructionCheckin,
    ClinicianInstructionCheckinRecord,
    ClinicianInstructionOutcome,
)


class ClinicianInstructionCheckinRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def all_for_patient(self, patient_id: UUID) -> list[ClinicianInstructionCheckinRecord]:
        rows = await self._pool.fetch(
            """
            SELECT cic.id, ci.metric, ci.instruction, c.completed_at AS checkin_completed_at,
                   cic.outcome::text AS outcome, cic.patient_response, cic.created_at
            FROM clinician_instruction_checkins cic
            JOIN clinician_instructions ci ON ci.id = cic.clinician_instruction_id
            JOIN checkins c ON c.id = cic.checkin_id
            WHERE ci.patient_id = $1
            ORDER BY cic.created_at DESC
            """,
            patient_id,
        )
        return [ClinicianInstructionCheckinRecord(**dict(r)) for r in rows]

    async def record(
        self,
        clinician_instruction_id: UUID,
        checkin_id: UUID,
        outcome: ClinicianInstructionOutcome,
        patient_response: str | None,
    ) -> ClinicianInstructionCheckin:
        """Upserted — an LLM could plausibly double-call acknowledge/skip for the same
        instruction within one call; the latest outcome wins rather than erroring."""
        row = await self._pool.fetchrow(
            """
            INSERT INTO clinician_instruction_checkins
                (clinician_instruction_id, checkin_id, outcome, patient_response)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (clinician_instruction_id, checkin_id)
            DO UPDATE SET outcome = EXCLUDED.outcome, patient_response = EXCLUDED.patient_response,
                           created_at = now()
            RETURNING id, clinician_instruction_id, checkin_id, outcome::text, patient_response, created_at
            """,
            clinician_instruction_id,
            checkin_id,
            outcome.value,
            patient_response,
        )
        return ClinicianInstructionCheckin(**dict(row))
