from datetime import timedelta

from glp1_agent.db.repositories.checkin_repo import CheckinRepo
from glp1_agent.domain.checkin_service import CheckinService
from glp1_agent.domain.models import CheckinStatus
from tests.helpers import UTC_NOW, seed_checkin, seed_patient


async def test_create_and_complete_checkin(conn):
    patient_id = await seed_patient(conn)
    service = CheckinService(CheckinRepo(conn))

    checkin = await service.create(patient_id, UTC_NOW)
    assert checkin.status == CheckinStatus.SCHEDULED

    completed = await service.complete(checkin.id, UTC_NOW, duration_seconds=180)
    assert completed.status == CheckinStatus.COMPLETED
    assert completed.duration_seconds == 180


async def test_seed_missed_creates_missed_checkins_on_preceding_days(conn):
    patient_id = await seed_patient(conn)
    service = CheckinService(CheckinRepo(conn))

    seeded = await service.seed_missed(patient_id, count=3, now=UTC_NOW)

    assert len(seeded) == 3
    assert all(c.status == CheckinStatus.MISSED for c in seeded)
    assert len({c.id for c in seeded}) == 3

    summary = await service.recent_summary(patient_id, limit=7)
    assert summary.missed_checkin_count == 3


async def test_recent_summary_derives_last_completed_and_missed_count(conn):
    patient_id = await seed_patient(conn)
    await seed_checkin(conn, patient_id, UTC_NOW - timedelta(days=3), status="missed")
    await seed_checkin(conn, patient_id, UTC_NOW - timedelta(days=2), status="missed")
    await seed_checkin(
        conn,
        patient_id,
        UTC_NOW - timedelta(days=1),
        status="completed",
        completed_at=UTC_NOW - timedelta(days=1),
    )

    service = CheckinService(CheckinRepo(conn))
    summary = await service.recent_summary(patient_id, limit=7)

    assert summary.missed_checkin_count == 2
    assert summary.last_completed_checkin_at == UTC_NOW - timedelta(days=1)
    assert len(summary.checkins) == 3
