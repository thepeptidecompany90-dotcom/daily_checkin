from datetime import timedelta

from glp1_agent.db.repositories.health_event_repo import HealthEventRepo
from glp1_agent.domain.health_event_service import HealthEventService
from glp1_agent.domain.models import (
    HealthEventSource,
    HealthEventType,
    MedicationEventType,
    SymptomTrend,
)
from tests.helpers import UTC_NOW, seed_medication, seed_patient


async def test_record_symptom_preserves_occurred_vs_observed_at(conn):
    """docs/domain-model.md §4.3 / §13: patient reports on day N a symptom that started
    two days earlier — occurred_at and observed_at must not collapse into one timestamp."""
    patient_id = await seed_patient(conn)
    service = HealthEventService(HealthEventRepo(conn))

    onset = UTC_NOW - timedelta(days=2)
    event = await service.record_health_event(
        patient_id=patient_id,
        checkin_id=None,
        event_type=HealthEventType.SYMPTOM,
        occurred_at=onset,
        observed_at=UTC_NOW,
        source=HealthEventSource.PATIENT_REPORT,
    )
    assert event.occurred_at == onset
    assert event.observed_at == UTC_NOW
    assert event.occurred_at != event.observed_at

    symptom = await service.record_symptom_event(
        health_event_id=event.id,
        symptom_type="feverish",
        severity=None,
        onset_at=onset,
        onset_is_estimated=True,
        trend=SymptomTrend.SAME,
        notes=None,
    )
    assert symptom.onset_at == onset
    assert symptom.onset_is_estimated is True
    assert symptom.trend == SymptomTrend.SAME


async def test_record_medication_event(conn):
    patient_id = await seed_patient(conn)
    patient_medication_id = await seed_medication(conn, patient_id)
    service = HealthEventService(HealthEventRepo(conn))

    health_event = await service.record_health_event(
        patient_id=patient_id,
        checkin_id=None,
        event_type=HealthEventType.MEDICATION,
        occurred_at=UTC_NOW,
        observed_at=UTC_NOW,
        source=HealthEventSource.PATIENT_REPORT,
    )
    medication_event = await service.record_medication_event(
        health_event_id=health_event.id,
        patient_medication_id=patient_medication_id,
        event_type=MedicationEventType.MISSED,
        scheduled_at=UTC_NOW - timedelta(days=1),
        occurred_at=UTC_NOW - timedelta(days=1),
        reason="travel",
    )
    assert medication_event.event_type == MedicationEventType.MISSED
    assert medication_event.reason == "travel"


async def test_recent_filters_by_occurred_at_window(conn):
    patient_id = await seed_patient(conn)
    service = HealthEventService(HealthEventRepo(conn))

    await service.record_health_event(
        patient_id=patient_id,
        checkin_id=None,
        event_type=HealthEventType.SYMPTOM,
        occurred_at=UTC_NOW - timedelta(days=30),
        observed_at=UTC_NOW - timedelta(days=30),
        source=HealthEventSource.PATIENT_REPORT,
    )
    recent = await service.record_health_event(
        patient_id=patient_id,
        checkin_id=None,
        event_type=HealthEventType.SYMPTOM,
        occurred_at=UTC_NOW - timedelta(days=1),
        observed_at=UTC_NOW,
        source=HealthEventSource.PATIENT_REPORT,
    )

    events = await service.recent(patient_id, days=7, now=UTC_NOW)
    assert [e.id for e in events] == [recent.id]
