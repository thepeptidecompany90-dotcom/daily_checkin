from glp1_agent.db.repositories.metric_schedule_repo import MetricScheduleRepo
from glp1_agent.db.repositories.observation_repo import ObservationRepo
from glp1_agent.domain.models import MetricType, ObservationValueLabel
from tests.helpers import seed_patient


async def test_create_weight_observation_round_trips(conn):
    patient_id = await seed_patient(conn)
    repo = ObservationRepo(conn)

    created = await repo.create(
        patient_id,
        checkin_id=None,
        observation_type=MetricType.WEIGHT,
        value_label=None,
        value_numeric=182.4,
        unit="lbs",
        confidence=None,
    )

    assert created.value_numeric == 182.4
    assert created.unit == "lbs"
    assert created.value_label is None

    observations = await repo.all_for_patient(patient_id)
    assert [o.id for o in observations] == [created.id]


async def test_create_mood_observation_round_trips(conn):
    patient_id = await seed_patient(conn)
    repo = ObservationRepo(conn)

    created = await repo.create(
        patient_id,
        checkin_id=None,
        observation_type=MetricType.MOOD,
        value_label=ObservationValueLabel.LOW,
        value_numeric=None,
        unit=None,
        confidence=None,
    )

    assert created.value_label == ObservationValueLabel.LOW
    assert created.value_numeric is None


async def test_last_observed_at_by_metric_returns_most_recent_only(conn):
    patient_id = await seed_patient(conn)
    repo = ObservationRepo(conn)

    first = await repo.create(
        patient_id, None, MetricType.MOOD, ObservationValueLabel.LOW, None, None, None
    )
    second = await repo.create(
        patient_id, None, MetricType.MOOD, ObservationValueLabel.HIGH, None, None, None
    )

    last_observed = await repo.last_observed_at_by_metric(patient_id)
    assert last_observed[MetricType.MOOD] >= first.created_at
    assert last_observed[MetricType.MOOD] == second.created_at


async def test_today_joins_patient_name_and_filters_by_day(conn):
    patient_id = await seed_patient(conn, first_name="Ravi", last_name="Kumar")
    repo = ObservationRepo(conn)
    await repo.create(
        patient_id, None, MetricType.WEIGHT, None, 180.0, "lbs", None
    )
    await conn.execute(
        """
        INSERT INTO checkin_observations (patient_id, observation_type, value_label, created_at)
        VALUES ($1, 'MOOD', 'LOW', now() - interval '3 days')
        """,
        patient_id,
    )

    today = await repo.today()

    assert len(today) == 1
    assert today[0].patient_name == "Ravi Kumar"
    assert today[0].observation_type == MetricType.WEIGHT
    assert today[0].value_numeric == 180.0


async def test_metric_schedule_repo_returns_seeded_defaults(conn):
    repo = MetricScheduleRepo(conn)

    schedules = await repo.all()

    assert schedules == {
        MetricType.MOOD: 1,
        MetricType.WEIGHT: 7,
        MetricType.SLEEP: 3,
        MetricType.HYDRATION: 3,
        MetricType.PROTEIN: 3,
    }
