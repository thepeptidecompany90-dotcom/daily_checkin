from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from glp1_agent.domain.models import (
    ClinicianInstruction,
    Journey,
    JourneyState,
    Medication,
    Patient,
    PatientContext,
)
from glp1_agent.flows.selection import (
    CLINICIAN_TRACKING,
    INITIAL_WEEK,
    MEDICATION_DAY,
    STABLE_CHECKIN,
    select_conversation_mode,
)

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _patient() -> Patient:
    return Patient(
        id=uuid4(),
        first_name="Jo",
        last_name="Doe",
        date_of_birth=date(1960, 1, 1),
        phone="+15555550100",
        timezone="UTC",
        preferred_language="en",
    )


def _journey(state: JourneyState) -> Journey:
    return Journey(id=uuid4(), patient_id=uuid4(), state=state, state_started_at=NOW)


def _medication(next_dose_at: datetime | None) -> Medication:
    return Medication(
        patient_medication_id=uuid4(),
        name="semaglutide",
        dose=1.0,
        dose_unit="mg",
        frequency="weekly",
        next_dose_at=next_dose_at,
    )


def _context(
    state: JourneyState = JourneyState.ESTABLISHED,
    medication: Medication | None = None,
    clinician_instructions: list[ClinicianInstruction] | None = None,
) -> PatientContext:
    return PatientContext(
        patient=_patient(),
        journey=_journey(state),
        active_medication=medication,
        recent_checkins=[],
        recent_health_events=[],
        active_clinician_instructions=clinician_instructions or [],
    )


@pytest.mark.parametrize("state", [JourneyState.STARTING, JourneyState.EARLY_TREATMENT])
def test_initial_week_takes_priority(state):
    context = _context(state=state, medication=_medication(NOW))
    assert select_conversation_mode(context, now=NOW) == INITIAL_WEEK


def test_medication_day_when_dose_due_today():
    context = _context(medication=_medication(NOW))
    assert select_conversation_mode(context, now=NOW) == MEDICATION_DAY


def test_not_medication_day_when_dose_due_another_day():
    context = _context(medication=_medication(NOW + timedelta(days=3)))
    assert select_conversation_mode(context, now=NOW) == STABLE_CHECKIN


def test_no_active_medication_is_not_medication_day():
    context = _context(medication=None)
    assert select_conversation_mode(context, now=NOW) == STABLE_CHECKIN


def _instruction() -> ClinicianInstruction:
    return ClinicianInstruction(
        tracking_id=uuid4(),
        metric="hydration",
        frequency="daily",
        instruction="Track daily fluid intake",
        start_date=NOW.date(),
        end_date=None,
    )


def test_clinician_tracking_when_instructions_present():
    context = _context(medication=None, clinician_instructions=[_instruction()])
    assert select_conversation_mode(context, now=NOW) == CLINICIAN_TRACKING


def test_medication_day_takes_priority_over_clinician_tracking():
    context = _context(medication=_medication(NOW), clinician_instructions=[_instruction()])
    assert select_conversation_mode(context, now=NOW) == MEDICATION_DAY


def test_stable_checkin_is_the_default():
    context = _context(medication=None, clinician_instructions=[])
    assert select_conversation_mode(context, now=NOW) == STABLE_CHECKIN
