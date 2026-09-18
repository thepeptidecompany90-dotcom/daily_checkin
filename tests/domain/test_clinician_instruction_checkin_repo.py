from datetime import date

from glp1_agent.db.repositories.clinician_instruction_checkin_repo import (
    ClinicianInstructionCheckinRepo,
)
from glp1_agent.db.repositories.clinician_instruction_repo import ClinicianInstructionRepo
from glp1_agent.domain.models import ClinicianInstructionOutcome
from tests.helpers import UTC_NOW, seed_checkin, seed_patient


async def test_record_acknowledged(conn):
    patient_id = await seed_patient(conn)
    checkin_id = await seed_checkin(conn, patient_id, UTC_NOW)
    instruction = await ClinicianInstructionRepo(conn).create(
        patient_id,
        metric="hydration",
        frequency="daily",
        instruction="Track daily fluid intake",
        start_date=date(2026, 9, 5),
        end_date=None,
    )
    repo = ClinicianInstructionCheckinRepo(conn)

    record = await repo.record(
        instruction.tracking_id, checkin_id, ClinicianInstructionOutcome.ACKNOWLEDGED, "Drinking plenty"
    )
    assert record.outcome == ClinicianInstructionOutcome.ACKNOWLEDGED
    assert record.patient_response == "Drinking plenty"
    assert record.clinician_instruction_id == instruction.tracking_id
    assert record.checkin_id == checkin_id


async def test_record_upserts_on_conflict(conn):
    patient_id = await seed_patient(conn)
    checkin_id = await seed_checkin(conn, patient_id, UTC_NOW)
    instruction = await ClinicianInstructionRepo(conn).create(
        patient_id,
        metric="sleep",
        frequency="daily",
        instruction="Track sleep hours",
        start_date=date(2026, 9, 5),
        end_date=None,
    )
    repo = ClinicianInstructionCheckinRepo(conn)

    first = await repo.record(
        instruction.tracking_id, checkin_id, ClinicianInstructionOutcome.ACKNOWLEDGED, "Slept fine"
    )
    second = await repo.record(
        instruction.tracking_id, checkin_id, ClinicianInstructionOutcome.DECLINED, "changed mind"
    )

    assert first.id == second.id
    assert second.outcome == ClinicianInstructionOutcome.DECLINED
    assert second.patient_response == "changed mind"

    count = await conn.fetchval(
        "SELECT count(*) FROM clinician_instruction_checkins WHERE clinician_instruction_id = $1",
        instruction.tracking_id,
    )
    assert count == 1


async def test_all_for_patient_joins_metric_and_instruction_and_checkin(conn):
    patient_id = await seed_patient(conn)
    checkin_id = await seed_checkin(
        conn, patient_id, UTC_NOW, status="completed", completed_at=UTC_NOW
    )
    instruction = await ClinicianInstructionRepo(conn).create(
        patient_id,
        metric="hydration",
        frequency="daily",
        instruction="Track daily fluid intake",
        start_date=date(2026, 9, 5),
        end_date=None,
    )
    repo = ClinicianInstructionCheckinRepo(conn)
    await repo.record(
        instruction.tracking_id, checkin_id, ClinicianInstructionOutcome.ACKNOWLEDGED, "Drinking plenty"
    )

    records = await repo.all_for_patient(patient_id)

    assert len(records) == 1
    assert records[0].metric == "hydration"
    assert records[0].instruction == "Track daily fluid intake"
    assert records[0].checkin_completed_at == UTC_NOW
    assert records[0].outcome == ClinicianInstructionOutcome.ACKNOWLEDGED
    assert records[0].patient_response == "Drinking plenty"


async def test_all_for_patient_excludes_other_patients(conn):
    patient_id = await seed_patient(conn)
    other_patient_id = await seed_patient(conn)
    checkin_id = await seed_checkin(conn, other_patient_id, UTC_NOW, status="completed", completed_at=UTC_NOW)
    instruction = await ClinicianInstructionRepo(conn).create(
        other_patient_id,
        metric="sleep",
        frequency="daily",
        instruction="Track sleep hours",
        start_date=date(2026, 9, 5),
        end_date=None,
    )
    repo = ClinicianInstructionCheckinRepo(conn)
    await repo.record(
        instruction.tracking_id, checkin_id, ClinicianInstructionOutcome.ACKNOWLEDGED, "Slept fine"
    )

    records = await repo.all_for_patient(patient_id)

    assert records == []
