from datetime import timedelta

from glp1_agent.db.repositories.checkin_repo import CheckinRepo
from glp1_agent.db.repositories.clinician_instruction_repo import ClinicianInstructionRepo
from glp1_agent.db.repositories.health_event_repo import HealthEventRepo
from glp1_agent.db.repositories.journey_repo import JourneyRepo
from glp1_agent.db.repositories.medication_repo import MedicationRepo
from glp1_agent.db.repositories.metric_schedule_repo import MetricScheduleRepo
from glp1_agent.db.repositories.observation_repo import ObservationRepo
from glp1_agent.db.repositories.patient_metric_schedule_repo import PatientMetricScheduleRepo
from glp1_agent.db.repositories.patient_repo import PatientRepo
from glp1_agent.domain.health_event_service import HealthEventService
from glp1_agent.domain.models import (
    HealthEventSource,
    HealthEventType,
    JourneyState,
    MetricType,
    ObservationValueLabel,
    PatientContext,
    SymptomTrend,
    TrackingItemKind,
)
from glp1_agent.domain.observation_service import ObservationService
from glp1_agent.domain.patient_context_service import PatientContextService
from tests.helpers import UTC_NOW, seed_journey, seed_medication, seed_patient


def _due_metric(context: PatientContext) -> MetricType | None:
    matches = [i.metric for i in context.tracking_items if i.kind == TrackingItemKind.DUE_METRIC]
    return matches[0] if matches else None


def _build_service(conn) -> PatientContextService:
    return PatientContextService(
        PatientRepo(conn),
        JourneyRepo(conn),
        MedicationRepo(conn),
        CheckinRepo(conn),
        HealthEventRepo(conn),
        ClinicianInstructionRepo(conn),
        ObservationRepo(conn),
        MetricScheduleRepo(conn),
        PatientMetricScheduleRepo(conn),
    )


async def test_assembles_full_context(conn):
    patient_id = await seed_patient(conn)
    await seed_journey(conn, patient_id, JourneyState.ESTABLISHED.value)
    await seed_medication(conn, patient_id, next_dose_at=UTC_NOW)

    service = _build_service(conn)

    context = await service.get_patient_context(patient_id)

    assert context.patient.id == patient_id
    assert context.journey.state == JourneyState.ESTABLISHED
    assert context.active_medication is not None
    assert context.active_medication.name == "semaglutide"
    assert context.recent_checkins == []
    assert context.recent_health_events == []
    assert [
        i for i in context.tracking_items if i.kind == TrackingItemKind.CLINICIAN_INSTRUCTION
    ] == []


async def test_context_with_no_active_medication(conn):
    patient_id = await seed_patient(conn)
    await seed_journey(conn, patient_id, JourneyState.CONSULTED.value)

    service = _build_service(conn)

    context = await service.get_patient_context(patient_id)

    assert context.active_medication is None


async def test_recent_health_events_include_symptom_detail(conn):
    """Regression test: recent_health_events must carry actual symptom/medication detail
    (not just bare event_type), since node builders interpolate this into the LLM prompt."""
    patient_id = await seed_patient(conn)
    await seed_journey(conn, patient_id, JourneyState.ESTABLISHED.value)
    events = HealthEventService(HealthEventRepo(conn))

    health_event = await events.record_health_event(
        patient_id=patient_id,
        checkin_id=None,
        event_type=HealthEventType.SYMPTOM,
        occurred_at=UTC_NOW,
        observed_at=UTC_NOW,
        source=HealthEventSource.PATIENT_REPORT,
    )
    await events.record_symptom_event(
        health_event_id=health_event.id,
        symptom_type="nausea",
        severity="mild",
        onset_at=UTC_NOW,
        onset_is_estimated=False,
        trend=SymptomTrend.IMPROVING,
        notes=None,
    )

    service = _build_service(conn)
    context = await service.get_patient_context(patient_id)

    assert len(context.recent_health_events) == 1
    item = context.recent_health_events[0]
    assert item.symptom_type == "nausea"
    assert item.trend == "improving"


async def test_due_metric_is_mood_when_nothing_ever_observed(conn):
    patient_id = await seed_patient(conn)
    await seed_journey(conn, patient_id, JourneyState.ESTABLISHED.value)

    service = _build_service(conn)
    context = await service.get_patient_context(patient_id, now=UTC_NOW)

    assert _due_metric(context) == MetricType.MOOD


async def test_due_metric_moves_to_next_overdue_metric_after_mood_recorded(conn):
    patient_id = await seed_patient(conn)
    await seed_journey(conn, patient_id, JourneyState.ESTABLISHED.value)
    observations = ObservationService(ObservationRepo(conn))
    await observations.record_observation(
        patient_id=patient_id,
        checkin_id=None,
        observation_type=MetricType.MOOD,
        value_label=ObservationValueLabel.NORMAL,
    )

    service = _build_service(conn)
    context = await service.get_patient_context(patient_id, now=UTC_NOW)

    assert _due_metric(context) == MetricType.WEIGHT


async def test_per_patient_override_changes_due_metric(conn):
    patient_id = await seed_patient(conn)
    await seed_journey(conn, patient_id, JourneyState.ESTABLISHED.value)
    ten_days_ago = UTC_NOW - timedelta(days=10)
    for metric in MetricType:
        await conn.execute(
            """
            INSERT INTO checkin_observations (patient_id, observation_type, value_label, created_at)
            VALUES ($1, $2, 'NORMAL', $3)
            """,
            patient_id,
            metric.value,
            ten_days_ago,
        )

    service = _build_service(conn)
    baseline = await service.get_patient_context(patient_id, now=UTC_NOW)
    # Global defaults: MOOD overdue by 9 days (10 - 1), the largest of all 5.
    assert _due_metric(baseline) == MetricType.MOOD

    await PatientMetricScheduleRepo(conn).upsert(patient_id, MetricType.MOOD, 100)

    overridden = await service.get_patient_context(patient_id, now=UTC_NOW)
    # MOOD no longer due (10 - 100 < 0); SLEEP is next-most-overdue (10 - 3 = 7),
    # winning the declaration-order tiebreak over HYDRATION/PROTEIN (also 7).
    assert _due_metric(overridden) == MetricType.SLEEP
