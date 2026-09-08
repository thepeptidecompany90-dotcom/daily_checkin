from datetime import date
from uuid import UUID

import asyncpg

from glp1_agent.domain.models import ClinicianInstruction


class ClinicianInstructionRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def active(self, patient_id: UUID) -> list[ClinicianInstruction]:
        rows = await self._pool.fetch(
            """
            SELECT id AS tracking_id, metric, frequency, instruction, start_date, end_date
            FROM clinician_instructions
            WHERE patient_id = $1 AND status = 'active'
            ORDER BY start_date DESC
            """,
            patient_id,
        )
        return [ClinicianInstruction(**dict(r)) for r in rows]

    async def all(self, patient_id: UUID) -> list[ClinicianInstruction]:
        rows = await self._pool.fetch(
            """
            SELECT id AS tracking_id, metric, frequency, instruction, start_date, end_date,
                   status::text AS status
            FROM clinician_instructions
            WHERE patient_id = $1
            ORDER BY start_date DESC
            """,
            patient_id,
        )
        return [ClinicianInstruction(**dict(r)) for r in rows]

    async def create(
        self,
        patient_id: UUID,
        metric: str,
        frequency: str,
        instruction: str,
        start_date: date,
        end_date: date | None,
    ) -> ClinicianInstruction:
        row = await self._pool.fetchrow(
            """
            INSERT INTO clinician_instructions (patient_id, metric, frequency, instruction, start_date, end_date)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id AS tracking_id, metric, frequency, instruction, start_date, end_date,
                      status::text AS status
            """,
            patient_id,
            metric,
            frequency,
            instruction,
            start_date,
            end_date,
        )
        return ClinicianInstruction(**dict(row))
