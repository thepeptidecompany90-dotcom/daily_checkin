from uuid import UUID

import asyncpg

from glp1_agent.domain.models import Patient


class PatientRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get(self, patient_id: UUID) -> Patient:
        row = await self._pool.fetchrow(
            """
            SELECT id, first_name, last_name, date_of_birth, phone, timezone, preferred_language
            FROM patients
            WHERE id = $1
            """,
            patient_id,
        )
        if row is None:
            raise LookupError(f"patient {patient_id} not found")
        print("patient row from repo: ", row)
        return Patient(**dict(row))

    async def list_all(self) -> list[Patient]:
        rows = await self._pool.fetch(
            """
            SELECT id, first_name, last_name, date_of_birth, phone, timezone, preferred_language
            FROM patients
            ORDER BY first_name, last_name
            """
        )
        return [Patient(**dict(r)) for r in rows]
