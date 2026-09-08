from datetime import datetime
from uuid import UUID

import asyncpg

from glp1_agent.domain.models import Medication, MedicationHistoryItem


class MedicationRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_active(self, patient_id: UUID) -> Medication | None:
        row = await self._pool.fetchrow(
            """
            SELECT pm.id AS patient_medication_id, m.name, pm.dose, pm.dose_unit,
                   pm.frequency, pm.next_dose_at
            FROM patient_medications pm
            JOIN medications m ON m.id = pm.medication_id
            WHERE pm.patient_id = $1 AND pm.status = 'active'
            """,
            patient_id,
        )
        if row is None:
            return None
        return Medication(**dict(row))

    async def replace_active(
        self,
        patient_medication_id: UUID,
        dose: float,
        dose_unit: str,
        frequency: str,
        next_dose_at: datetime | None,
    ) -> Medication:
        """End the given active row and start a new active one for the same patient/medication
        (docs/domain-model.md §6.2: dose changes are versioned, never overwritten in place)."""
        source = await self._pool.fetchrow(
            "SELECT patient_id, medication_id FROM patient_medications WHERE id = $1",
            patient_medication_id,
        )
        if source is None:
            raise LookupError(f"patient_medication {patient_medication_id} not found")

        medication_name = await self._pool.fetchval(
            "SELECT name FROM medications WHERE id = $1", source["medication_id"]
        )
        await self._pool.execute(
            "UPDATE patient_medications SET status = 'ended', ended_at = now() WHERE id = $1",
            patient_medication_id,
        )
        row = await self._pool.fetchrow(
            """
            INSERT INTO patient_medications (patient_id, medication_id, dose, dose_unit, frequency, next_dose_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id AS patient_medication_id, dose, dose_unit, frequency, next_dose_at
            """,
            source["patient_id"],
            source["medication_id"],
            dose,
            dose_unit,
            frequency,
            next_dose_at,
        )
        return Medication(**dict(row), name=medication_name)

    async def history(self, patient_id: UUID) -> list[MedicationHistoryItem]:
        rows = await self._pool.fetch(
            """
            SELECT pm.id AS patient_medication_id, m.name, pm.dose, pm.dose_unit, pm.frequency,
                   pm.next_dose_at, pm.status::text AS status, pm.started_at, pm.ended_at
            FROM patient_medications pm
            JOIN medications m ON m.id = pm.medication_id
            WHERE pm.patient_id = $1
            ORDER BY pm.started_at DESC
            """,
            patient_id,
        )
        return [MedicationHistoryItem(**dict(r)) for r in rows]
