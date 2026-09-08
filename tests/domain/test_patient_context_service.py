from glp1_agent.db.repositories.checkin_repo import CheckinRepo
from glp1_agent.db.repositories.clinician_instruction_repo import ClinicianInstructionRepo
from glp1_agent.db.repositories.health_event_repo import HealthEventRepo
from glp1_agent.db.repositories.journey_repo import JourneyRepo
from glp1_agent.db.repositories.medication_repo import MedicationRepo
from glp1_agent.db.repositories.patient_repo import PatientRepo
from glp1_agent.domain.health_event_service import HealthEventService
from glp1_agent.domain.models import (
    HealthEventSource,
    HealthEventType,
    JourneyState,
    SymptomTrend,
)
from glp1_agent.domain.patient_context_service import PatientContextService
from tests.helpers import UTC_NOW, seed_journey, seed_medication, seed_patient


def _build_service(conn) -> PatientContextService:
    return PatientContextService(
        PatientRepo(conn),
        JourneyRepo(conn),
        MedicationRepo(conn),
        CheckinRepo(conn),
        HealthEventRepo(conn),
        ClinicianInstructionRepo(conn),
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
    assert context.active_clinician_instructions == []


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
