from datetime import timedelta

from glp1_agent.db.repositories.checkin_repo import CheckinRepo
from glp1_agent.db.repositories.clinician_instruction_checkin_repo import (
    ClinicianInstructionCheckinRepo,
)
from glp1_agent.db.repositories.clinician_instruction_repo import ClinicianInstructionRepo
from glp1_agent.db.repositories.escalation_repo import EscalationRepo
from glp1_agent.db.repositories.health_event_repo import HealthEventRepo
from glp1_agent.db.repositories.journey_repo import JourneyRepo
from glp1_agent.db.repositories.medication_repo import MedicationRepo
from glp1_agent.db.repositories.observation_repo import ObservationRepo
from glp1_agent.db.repositories.patient_metric_schedule_repo import PatientMetricScheduleRepo
from glp1_agent.db.repositories.patient_repo import PatientRepo
from glp1_agent.domain.dashboard_service import DashboardService
from glp1_agent.domain.health_event_service import HealthEventService
from glp1_agent.domain.models import (
    ClinicianInstructionOutcome,
    HealthEventSource,
    HealthEventType,
    JourneyState,
    MedicationEventType,
    MetricType,
    ObservationValueLabel,
    SymptomTrend,
)
from glp1_agent.domain.observation_service import ObservationService
from tests.helpers import UTC_NOW, seed_checkin, seed_journey, seed_medication, seed_patient


async def _service(conn) -> DashboardService:
    return DashboardService(
        PatientRepo(conn),
        CheckinRepo(conn),
        HealthEventRepo(conn),
        JourneyRepo(conn),
        MedicationRepo(conn),
        ClinicianInstructionRepo(conn),
        EscalationRepo(conn),
        ObservationRepo(conn),
        PatientMetricScheduleRepo(conn),
        ClinicianInstructionCheckinRepo(conn),
    )


async def test_list_patients_includes_seeded_patient(conn):
    patient_id = await seed_patient(conn, first_name="Jamie", last_name="Lee")
    service = await _service(conn)

    summaries = await service.list_patients()

    assert any(s.patient.id == patient_id for s in summaries)


async def test_list_patients_reports_no_journey_state_without_active_journey(conn):
    patient_id = await seed_patient(conn)
    service = await _service(conn)

    summaries = await service.list_patients()

    summary = next(s for s in summaries if s.patient.id == patient_id)
    assert summary.journey_state is None
    assert summary.last_completed_checkin_at is None
    assert summary.missed_checkin_count == 0


async def test_list_patients_reports_journey_state_last_checkin_and_missed_count(conn):
    patient_id = await seed_patient(conn)
    await seed_journey(conn, patient_id, JourneyState.ESTABLISHED.value)
    await seed_checkin(conn, patient_id, UTC_NOW - timedelta(days=2), status="missed")
    await seed_checkin(conn, patient_id, UTC_NOW - timedelta(days=1), status="missed")
    await seed_checkin(conn, patient_id, UTC_NOW, status="completed", completed_at=UTC_NOW)
    service = await _service(conn)

    summaries = await service.list_patients()

    summary = next(s for s in summaries if s.patient.id == patient_id)
    assert summary.journey_state == JourneyState.ESTABLISHED
    assert summary.last_completed_checkin_at == UTC_NOW
    assert summary.missed_checkin_count == 2


async def test_no_completed_checkin_returns_empty(conn):
    patient_id = await seed_patient(conn)
    service = await _service(conn)

    checkin, items = await service.get_last_completed_extraction(patient_id)

    assert checkin is None
    assert items == []


async def test_extraction_for_last_completed_checkin(conn):
    patient_id = await seed_patient(conn)
    patient_medication_id = await seed_medication(conn, patient_id)
    checkin_id = await seed_checkin(
        conn, patient_id, UTC_NOW, status="completed", completed_at=UTC_NOW
    )
    events = HealthEventService(HealthEventRepo(conn))

    symptom_health_event = await events.record_health_event(
        patient_id=patient_id,
        checkin_id=checkin_id,
        event_type=HealthEventType.SYMPTOM,
        occurred_at=UTC_NOW,
        observed_at=UTC_NOW,
        source=HealthEventSource.PATIENT_REPORT,
    )
    await events.record_symptom_event(
        health_event_id=symptom_health_event.id,
        symptom_type="nausea",
        severity="mild",
        onset_at=UTC_NOW,
        onset_is_estimated=False,
        trend=SymptomTrend.IMPROVING,
        notes="after breakfast",
    )

    medication_health_event = await events.record_health_event(
        patient_id=patient_id,
        checkin_id=checkin_id,
        event_type=HealthEventType.MEDICATION,
        occurred_at=UTC_NOW,
        observed_at=UTC_NOW,
        source=HealthEventSource.PATIENT_REPORT,
    )
    await events.record_medication_event(
        health_event_id=medication_health_event.id,
        patient_medication_id=patient_medication_id,
        event_type=MedicationEventType.TAKEN,
        scheduled_at=UTC_NOW,
        occurred_at=UTC_NOW,
        reason=None,
    )

    service = await _service(conn)
    checkin, items = await service.get_last_completed_extraction(patient_id)

    assert checkin is not None
    assert checkin.id == checkin_id
    assert len(items) == 2

    symptom_item = next(i for i in items if i.event_type == HealthEventType.SYMPTOM)
    assert symptom_item.symptom_type == "nausea"
    assert symptom_item.severity == "mild"
    assert symptom_item.trend == "improving"
    assert symptom_item.medication_event_type is None

    medication_item = next(i for i in items if i.event_type == HealthEventType.MEDICATION)
    assert medication_item.medication_event_type == "TAKEN"
    assert medication_item.symptom_type is None


async def test_get_full_record_aggregates_across_all_tables(conn):
    patient_id = await seed_patient(conn, first_name="Ana")
    await seed_journey(conn, patient_id, JourneyState.STARTING.value)
    await seed_medication(conn, patient_id)
    await seed_checkin(conn, patient_id, UTC_NOW, status="missed")
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
        trend=SymptomTrend.SAME,
        notes=None,
    )
    instruction = await ClinicianInstructionRepo(conn).create(
        patient_id,
        metric="hydration",
        frequency="daily",
        instruction="Track fluid intake",
        start_date=UTC_NOW.date(),
        end_date=None,
    )
    checkin_id = await seed_checkin(
        conn, patient_id, UTC_NOW, status="completed", completed_at=UTC_NOW
    )
    await ClinicianInstructionCheckinRepo(conn).record(
        clinician_instruction_id=instruction.tracking_id,
        checkin_id=checkin_id,
        outcome=ClinicianInstructionOutcome.ACKNOWLEDGED,
        patient_response="Drinking plenty",
    )
    await ObservationService(ObservationRepo(conn)).record_observation(
        patient_id=patient_id,
        checkin_id=None,
        observation_type=MetricType.MOOD,
        value_label=ObservationValueLabel.HIGH,
    )

    service = await _service(conn)
    record = await service.get_full_record(patient_id)

    assert record.patient.first_name == "Ana"
    assert len(record.journey_history) == 1
    assert len(record.medication_history) == 1
    assert len(record.checkins) == 2
    assert len(record.health_events) == 1
    assert len(record.clinician_instructions) == 1
    assert len(record.escalation_protocols) >= 1
    assert record.metric_schedule_overrides == []
    assert len(record.clinician_instruction_checkins) == 1
    checkin_record = record.clinician_instruction_checkins[0]
    assert checkin_record.metric == "hydration"
    assert checkin_record.outcome == ClinicianInstructionOutcome.ACKNOWLEDGED
    assert len(record.observations) == 1
    assert record.observations[0].observation_type == MetricType.MOOD
    assert checkin_record.patient_response == "Drinking plenty"
    assert checkin_record.checkin_completed_at == UTC_NOW


async def test_get_full_record_includes_metric_schedule_overrides(conn):
    patient_id = await seed_patient(conn)
    await PatientMetricScheduleRepo(conn).upsert(patient_id, MetricType.WEIGHT, 3)

    service = await _service(conn)
    record = await service.get_full_record(patient_id)

    assert len(record.metric_schedule_overrides) == 1
    assert record.metric_schedule_overrides[0].metric == MetricType.WEIGHT
    assert record.metric_schedule_overrides[0].frequency_days == 3


async def test_get_full_record_days_window_excludes_older_checkins_and_health_events(conn):
    patient_id = await seed_patient(conn)
    await seed_checkin(conn, patient_id, UTC_NOW - timedelta(days=40), status="missed")
    await seed_checkin(conn, patient_id, UTC_NOW - timedelta(days=1), status="missed")
    events = HealthEventService(HealthEventRepo(conn))

    old_event = await events.record_health_event(
        patient_id=patient_id,
        checkin_id=None,
        event_type=HealthEventType.SYMPTOM,
        occurred_at=UTC_NOW - timedelta(days=40),
        observed_at=UTC_NOW - timedelta(days=40),
        source=HealthEventSource.PATIENT_REPORT,
    )
    await events.record_symptom_event(
        health_event_id=old_event.id,
        symptom_type="nausea",
        severity=None,
        onset_at=UTC_NOW - timedelta(days=40),
        onset_is_estimated=False,
        trend=SymptomTrend.SAME,
        notes=None,
    )
    recent_event = await events.record_health_event(
        patient_id=patient_id,
        checkin_id=None,
        event_type=HealthEventType.SYMPTOM,
        occurred_at=UTC_NOW - timedelta(days=1),
        observed_at=UTC_NOW - timedelta(days=1),
        source=HealthEventSource.PATIENT_REPORT,
    )
    await events.record_symptom_event(
        health_event_id=recent_event.id,
        symptom_type="fatigue",
        severity=None,
        onset_at=UTC_NOW - timedelta(days=1),
        onset_is_estimated=False,
        trend=SymptomTrend.SAME,
        notes=None,
    )

    service = await _service(conn)
    record = await service.get_full_record(patient_id, days=30, now=UTC_NOW)

    assert len(record.checkins) == 1
    assert len(record.health_events) == 1
    assert record.health_events[0].symptom_type == "fatigue"


async def test_get_full_record_without_days_includes_everything(conn):
    patient_id = await seed_patient(conn)
    await seed_checkin(conn, patient_id, UTC_NOW - timedelta(days=400), status="missed")

    service = await _service(conn)
    record = await service.get_full_record(patient_id)

    assert len(record.checkins) == 1


async def test_get_today_observations_includes_observation_recorded_today(conn):
    patient_id = await seed_patient(conn, first_name="Ravi")
    observations = ObservationService(ObservationRepo(conn))
    await observations.record_observation(
        patient_id=patient_id,
        checkin_id=None,
        observation_type=MetricType.MOOD,
        value_label=ObservationValueLabel.NORMAL,
    )

    service = await _service(conn)
    today = await service.get_today_observations()

    assert len(today) == 1
    assert today[0].patient_name == "Ravi Doe"
    assert today[0].observation_type == MetricType.MOOD
    assert today[0].value_label == ObservationValueLabel.NORMAL


async def test_get_today_observations_excludes_observations_from_other_days(conn):
    patient_id = await seed_patient(conn)
    await conn.execute(
        """
        INSERT INTO checkin_observations (patient_id, observation_type, value_label, created_at)
        VALUES ($1, 'MOOD', 'LOW', $2)
        """,
        patient_id,
        UTC_NOW - timedelta(days=5),
    )

    service = await _service(conn)
    today = await service.get_today_observations()

    assert today == []
