from datetime import UTC, datetime

from glp1_agent.domain.models import JourneyState, PatientContext, TrackingItemKind

STABLE_CHECKIN = "stable_checkin"
INITIAL_WEEK = "initial_week"
MEDICATION_DAY = "medication_day"
CLINICIAN_TRACKING = "clinician_tracking"

_INITIAL_WEEK_STATES = frozenset({JourneyState.STARTING, JourneyState.EARLY_TREATMENT})


def _is_medication_day(context: PatientContext, now: datetime) -> bool:
    medication = context.active_medication
    if medication is None or medication.next_dose_at is None:
        return False
    return medication.next_dose_at.date() == now.date()


def select_conversation_mode(context: PatientContext, now: datetime | None = None) -> str:
    """Reduced V1 version of voice-agent-kb.md §14's selection logic.

    Emergency/active-escalation branches from the KB are omitted here because
    they depend on `flags`, which is out of scope for this pass — those cases
    are instead handled reactively mid-conversation via get_clinical_escalation_protocol.
    """
    now = now or datetime.now(UTC)

    if context.journey.state in _INITIAL_WEEK_STATES:
        return INITIAL_WEEK

    if _is_medication_day(context, now):
        return MEDICATION_DAY

    if any(item.kind == TrackingItemKind.CLINICIAN_INSTRUCTION for item in context.tracking_items):
        return CLINICIAN_TRACKING

    return STABLE_CHECKIN
