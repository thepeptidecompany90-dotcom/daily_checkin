from datetime import date, timedelta

from glp1_agent.db.repositories.clinician_instruction_repo import ClinicianInstructionRepo
from tests.helpers import seed_patient


async def test_create_then_visible_in_active_and_all(conn):
    patient_id = await seed_patient(conn)
    repo = ClinicianInstructionRepo(conn)

    created = await repo.create(
        patient_id,
        metric="hydration",
        frequency="daily",
        instruction="Track daily fluid intake",
        start_date=date(2026, 9, 5),
        end_date=date(2026, 9, 12),
    )
    assert created.status == "active"

    active = await repo.active(patient_id)
    assert [i.tracking_id for i in active] == [created.tracking_id]

    all_instructions = await repo.all(patient_id)
    assert [i.tracking_id for i in all_instructions] == [created.tracking_id]


async def test_expired_instruction_excluded_from_active_but_present_in_all(conn):
    patient_id = await seed_patient(conn)
    repo = ClinicianInstructionRepo(conn)
    await repo.create(
        patient_id,
        metric="sleep",
        frequency="daily",
        instruction="Track sleep hours",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
    )
    await conn.execute(
        "UPDATE clinician_instructions SET status = 'expired' WHERE patient_id = $1", patient_id
    )

    assert await repo.active(patient_id) == []
    all_instructions = await repo.all(patient_id)
    assert len(all_instructions) == 1
    assert all_instructions[0].status == "expired"


async def test_create_without_end_date(conn):
    patient_id = await seed_patient(conn)
    repo = ClinicianInstructionRepo(conn)

    created = await repo.create(
        patient_id,
        metric="appetite",
        frequency="daily",
        instruction="Ask about appetite",
        start_date=date.today() - timedelta(days=1),
        end_date=None,
    )
    assert created.end_date is None
