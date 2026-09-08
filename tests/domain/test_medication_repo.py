from datetime import timedelta

from glp1_agent.db.repositories.medication_repo import MedicationRepo
from tests.helpers import UTC_NOW, seed_medication, seed_patient


async def test_replace_active_ends_old_row_and_starts_new_one(conn):
    patient_id = await seed_patient(conn)
    original_id = await seed_medication(conn, patient_id, dose=1.0, frequency="weekly")
    repo = MedicationRepo(conn)
    new_next_dose = UTC_NOW + timedelta(days=1)

    updated = await repo.replace_active(
        original_id, dose=2.0, dose_unit="mg", frequency="daily", next_dose_at=new_next_dose
    )

    assert updated.dose == 2.0
    assert updated.frequency == "daily"
    assert updated.next_dose_at == new_next_dose

    active = await repo.get_active(patient_id)
    assert active is not None
    assert active.patient_medication_id == updated.patient_medication_id
    assert active.dose == 2.0

    history = await repo.history(patient_id)
    assert len(history) == 2
    by_id = {h.patient_medication_id: h for h in history}
    assert by_id[original_id].status == "ended"
    assert by_id[original_id].ended_at is not None
    assert by_id[updated.patient_medication_id].status == "active"
