from datetime import UTC, date, datetime
from uuid import uuid4

from glp1_agent.domain.models import (
    Journey,
    JourneyState,
    Medication,
    Patient,
    PatientContext,
)
from glp1_agent.flows.nodes import _ROLE_MESSAGE, create_stable_checkin_node

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _context(medication: Medication | None) -> PatientContext:
    return PatientContext(
        patient=Patient(
            id=uuid4(),
            first_name="Alex",
            last_name="Rivera",
            date_of_birth=date(1962, 4, 12),
            phone="+15555550100",
            timezone="UTC",
            preferred_language="en",
        ),
        journey=Journey(id=uuid4(), patient_id=uuid4(), state=JourneyState.ESTABLISHED, state_started_at=NOW),
        active_medication=medication,
        recent_checkins=[],
        recent_health_events=[],
        active_clinician_instructions=[],
    )


def _task_content(node) -> str:
    return " ".join(m["content"] for m in node["task_messages"])


def test_role_message_has_pacing_guardrail():
    assert "2-3 sentences" in _ROLE_MESSAGE


def test_context_includes_patient_name():
    node = create_stable_checkin_node(_context(medication=None))
    assert "Alex" in _task_content(node)


def test_context_includes_active_medication():
    medication = Medication(
        patient_medication_id=uuid4(),
        name="semaglutide",
        dose=0.25,
        dose_unit="mg",
        frequency="weekly",
        next_dose_at=None,
    )
    node = create_stable_checkin_node(_context(medication=medication))
    assert "semaglutide" in _task_content(node)


def test_no_medication_states_none_explicitly():
    node = create_stable_checkin_node(_context(medication=None))
    assert "No active medication on file." in _task_content(node)


def test_extraction_instructions_present():
    node = create_stable_checkin_node(_context(medication=None))
    assert "record_health_event" in _task_content(node)
    assert "record_symptom_event" in _task_content(node)
