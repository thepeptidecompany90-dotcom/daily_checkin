from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import asyncpg


async def seed_patient(conn: asyncpg.Connection, **overrides) -> UUID:
    patient_id = overrides.get("id", uuid4())
    await conn.execute(
        """
        INSERT INTO patients (id, first_name, last_name, date_of_birth, phone, timezone, preferred_language)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        patient_id,
        overrides.get("first_name", "Jo"),
        overrides.get("last_name", "Doe"),
        overrides.get("date_of_birth", date(1960, 1, 1)),
        overrides.get("phone", "+15555550100"),
        overrides.get("timezone", "UTC"),
        overrides.get("preferred_language", "en"),
    )
    return patient_id


async def seed_journey(conn: asyncpg.Connection, patient_id: UUID, state: str) -> UUID:
    journey_id = await conn.fetchval(
        "INSERT INTO patient_journeys (patient_id) VALUES ($1) RETURNING id", patient_id
    )
    await conn.execute(
        "INSERT INTO journey_state_history (journey_id, state) VALUES ($1, $2::journey_state)",
        journey_id,
        state,
    )
    return journey_id


async def seed_medication(
    conn: asyncpg.Connection,
    patient_id: UUID,
    next_dose_at: datetime | None = None,
    dose: float = 1.0,
    dose_unit: str = "mg",
    frequency: str = "weekly",
) -> UUID:
    medication_id = await conn.fetchval(
        "INSERT INTO medications (name, route) VALUES ('semaglutide', 'subcutaneous') RETURNING id"
    )
    patient_medication_id = await conn.fetchval(
        """
        INSERT INTO patient_medications
            (patient_id, medication_id, dose, dose_unit, frequency, next_dose_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        patient_id,
        medication_id,
        dose,
        dose_unit,
        frequency,
        next_dose_at,
    )
    return patient_medication_id


async def seed_checkin(
    conn: asyncpg.Connection,
    patient_id: UUID,
    scheduled_at: datetime,
    status: str = "scheduled",
    completed_at: datetime | None = None,
) -> UUID:
    return await conn.fetchval(
        """
        INSERT INTO checkins (patient_id, scheduled_at, status, completed_at)
        VALUES ($1, $2, $3::checkin_status, $4)
        RETURNING id
        """,
        patient_id,
        scheduled_at,
        status,
        completed_at,
    )


UTC_NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
