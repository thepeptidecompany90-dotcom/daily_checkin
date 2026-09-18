"""Display-only helpers for dashboard templates — formatting and badge coloring, not domain logic.

Coloring is restricted to fixed workflow enums (journey state, checkin status, medication event
type/status, instruction status, instruction checkin outcome, symptom trend). Free-text clinical
fields (escalation severity/urgency, symptom severity) are deliberately left uncolored — inferring
clinical urgency from text here would violate the "backend decides severity, not presentation
code" rule in CLAUDE.md.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

_JOURNEY_STATE_CLASSES = {
    "DISCONTINUED": "badge-danger",
    "DOSE_CHANGE": "badge-warning",
}

_CHECKIN_STATUS_CLASSES = {
    "completed": "badge-success",
    "missed": "badge-danger",
    "failed": "badge-danger",
    "cancelled": "badge-neutral",
    "scheduled": "badge-info",
}

_MEDICATION_EVENT_CLASSES = {
    "TAKEN": "badge-success",
    "MISSED": "badge-danger",
    "REFUSED": "badge-danger",
    "DELAYED": "badge-warning",
    "SIDE_EFFECT": "badge-warning",
    "REFILL_ISSUE": "badge-warning",
}

_MEDICATION_STATUS_CLASSES = {
    "active": "badge-success",
    "ended": "badge-neutral",
}

_INSTRUCTION_STATUS_CLASSES = {
    "active": "badge-success",
    "expired": "badge-warning",
    "completed": "badge-neutral",
}

_SYMPTOM_TREND_CLASSES = {
    "improving": "badge-success",
    "worsening": "badge-danger",
    "same": "badge-neutral",
    "unknown": "badge-neutral",
}

_TRACKING_ITEM_KIND_CLASSES = {
    "clinician_instruction": "badge-info",
    "due_metric": "badge-neutral",
}

_CLINICIAN_INSTRUCTION_OUTCOME_CLASSES = {
    "acknowledged": "badge-success",
    "declined": "badge-warning",
}

_CATEGORY_CLASSES = {
    "journey_state": _JOURNEY_STATE_CLASSES,
    "checkin_status": _CHECKIN_STATUS_CLASSES,
    "medication_event_type": _MEDICATION_EVENT_CLASSES,
    "medication_status": _MEDICATION_STATUS_CLASSES,
    "instruction_status": _INSTRUCTION_STATUS_CLASSES,
    "symptom_trend": _SYMPTOM_TREND_CLASSES,
    "tracking_item_kind": _TRACKING_ITEM_KIND_CLASSES,
    "clinician_instruction_outcome": _CLINICIAN_INSTRUCTION_OUTCOME_CLASSES,
}


def humanize(value: str | None) -> str:
    """'DOSE_CHANGE' / 'improving' -> 'Dose change' / 'Improving'."""
    if not value:
        return "—"
    text = str(value).replace("_", " ").replace("-", " ").strip()
    return text[:1].upper() + text[1:].lower()


def badge_class(value: str | None, category: str) -> str:
    """Semantic badge color for a known status category; unmapped values stay neutral."""
    return _CATEGORY_CLASSES.get(category, {}).get(str(value), "badge-neutral")


def missed_checkin_badge_class(count: int) -> str:
    if count == 0:
        return "badge-neutral"
    if count <= 2:
        return "badge-warning"
    return "badge-danger"


def local_dt(value: datetime | None, timezone: str | None = None) -> str:
    """Human-readable timestamp, converted to `timezone` when given (else left as-is)."""
    if value is None:
        return "—"
    localized = value.astimezone(ZoneInfo(timezone)) if timezone else value
    return localized.strftime("%b %d, %Y, %I:%M %p")
