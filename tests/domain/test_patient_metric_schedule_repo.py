from glp1_agent.db.repositories.patient_metric_schedule_repo import PatientMetricScheduleRepo
from glp1_agent.domain.models import MetricType
from tests.helpers import seed_patient


async def test_upsert_creates_then_updates_in_place(conn):
    patient_id = await seed_patient(conn)
    repo = PatientMetricScheduleRepo(conn)

    await repo.upsert(patient_id, MetricType.WEIGHT, 5)
    await repo.upsert(patient_id, MetricType.WEIGHT, 10)

    schedules = await repo.for_patient(patient_id)
    assert len(schedules) == 1
    assert schedules[0].frequency_days == 10


async def test_for_patient_scoped_to_patient(conn):
    patient_a = await seed_patient(conn)
    patient_b = await seed_patient(conn)
    repo = PatientMetricScheduleRepo(conn)

    await repo.upsert(patient_a, MetricType.MOOD, 2)
    await repo.upsert(patient_b, MetricType.SLEEP, 4)

    schedules_a = await repo.for_patient(patient_a)
    assert [s.metric for s in schedules_a] == [MetricType.MOOD]

    schedules_b = await repo.for_patient(patient_b)
    assert [s.metric for s in schedules_b] == [MetricType.SLEEP]
