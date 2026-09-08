from glp1_agent.db.repositories.checkin_repo import CheckinRepo
from glp1_agent.db.repositories.clinician_instruction_repo import ClinicianInstructionRepo
from glp1_agent.db.repositories.escalation_repo import EscalationRepo
from glp1_agent.db.repositories.health_event_repo import HealthEventRepo
from glp1_agent.db.repositories.journey_repo import JourneyRepo
from glp1_agent.db.repositories.medication_repo import MedicationRepo
from glp1_agent.db.repositories.patient_repo import PatientRepo
from glp1_agent.domain.dashboard_service import DashboardService
from glp1_agent.domain.health_event_service import HealthEventService
from glp1_agent.domain.models import (
    HealthEventSource,
    HealthEventType,
    JourneyState,
    MedicationEventType,
    SymptomTrend,
)
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
    )


async def test_list_patients_includes_seeded_patient(conn):
    patient_id = await seed_patient(conn, first_name="Jamie", last_name="Lee")
    service = await _service(conn)

    patients = await service.list_patients()

    assert any(p.id == patient_id for p in patients)


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
    await ClinicianInstructionRepo(conn).create(
        patient_id,
        metric="hydration",
        frequency="daily",
        instruction="Track fluid intake",
        start_date=UTC_NOW.date(),
        end_date=None,
    )

    service = await _service(conn)
    record = await service.get_full_record(patient_id)

    assert record.patient.first_name == "Ana"
    assert len(record.journey_history) == 1
    assert len(record.medication_history) == 1
    assert len(record.checkins) == 1
    assert len(record.health_events) == 1
    assert len(record.clinician_instructions) == 1
    assert len(record.escalation_protocols) >= 1
