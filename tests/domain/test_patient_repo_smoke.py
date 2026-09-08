from datetime import date
from uuid import uuid4

from glp1_agent.db.repositories.patient_repo import PatientRepo


async def test_insert_and_fetch_patient(conn):
    patient_id = uuid4()
    await conn.execute(
        """
        INSERT INTO patients (id, first_name, last_name, date_of_birth, phone, timezone, preferred_language)
        VALUES ($1, 'Jo', 'Doe', $2, '+15555550100', 'UTC', 'en')
        """,
        patient_id,
        date(1960, 1, 1),
    )

    repo = PatientRepo(conn)
    patient = await repo.get(patient_id)

    assert patient.id == patient_id
    assert patient.first_name == "Jo"
