from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pipecat.flows import FlowArgs, FlowManager, FlowsFunctionSchema

from glp1_agent.domain.models import (
    HealthEventSource,
    HealthEventType,
    MedicationEventType,
    SymptomTrend,
)
from glp1_agent.services import Services

# flow_manager.state keys populated once at bootstrap (see bot.py) and read by every tool here.
STATE_SERVICES = "services"
STATE_PATIENT_ID = "patient_id"
STATE_CHECKIN_ID = "checkin_id"
STATE_ACTIVE_MEDICATION_ID = "active_medication_id"


def _services(flow_manager: FlowManager) -> Services:
    return flow_manager.state[STATE_SERVICES]


def _patient_id(flow_manager: FlowManager) -> UUID:
    return UUID(flow_manager.state[STATE_PATIENT_ID])


def _checkin_id(flow_manager: FlowManager) -> UUID:
    return UUID(flow_manager.state[STATE_CHECKIN_ID])


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


async def _record_health_event(args: FlowArgs, flow_manager: FlowManager) -> Any:
    services = _services(flow_manager)
    event = await services.health_events.record_health_event(
        patient_id=_patient_id(flow_manager),
        checkin_id=_checkin_id(flow_manager),
        event_type=HealthEventType(args["event_type"]),
        occurred_at=_parse_datetime(args["occurred_at"]),
        observed_at=datetime.now(UTC),
        source=HealthEventSource.PATIENT_REPORT,
    )
    return {"health_event_id": str(event.id)}


record_health_event = FlowsFunctionSchema(
    name="record_health_event",
    description=(
        "Record that a patient-reported health event happened. Call this once you have "
        "identified a distinct symptom or medication-related event worth tracking, before "
        "recording its details with record_symptom_event or record_medication_event."
    ),
    properties={
        "event_type": {
            "type": "string",
            "enum": [t.value for t in HealthEventType],
            "description": "Category of the event.",
        },
        "occurred_at": {
            "type": "string",
            "description": (
                "ISO-8601 date/time the event actually happened, resolved from the patient's "
                "own words (e.g. 'two days ago') against today's date. Never the time the "
                "patient is reporting it now unless that is also when it happened."
            ),
        },
    },
    required=["event_type", "occurred_at"],
    handler=_record_health_event,
)


async def _record_symptom_event(args: FlowArgs, flow_manager: FlowManager) -> Any:
    services = _services(flow_manager)
    event = await services.health_events.record_symptom_event(
        health_event_id=UUID(args["health_event_id"]),
        symptom_type=args["symptom_type"],
        severity=args.get("severity"),
        onset_at=_parse_datetime(args.get("onset_at")),
        onset_is_estimated=args.get("onset_is_estimated", False),
        trend=SymptomTrend(args.get("trend", SymptomTrend.UNKNOWN.value)),
        notes=args.get("notes"),
    )
    return {"symptom_event_id": str(event.id)}


record_symptom_event = FlowsFunctionSchema(
    name="record_symptom_event",
    description="Record symptom-specific detail for a health event already created with record_health_event.",
    properties={
        "health_event_id": {
            "type": "string",
            "description": "The health_event_id returned by record_health_event.",
        },
        "symptom_type": {
            "type": "string",
            "description": "Short symptom name, e.g. 'nausea', 'feverish'.",
        },
        "severity": {"type": "string", "description": "Patient-described severity, if stated."},
        "onset_at": {
            "type": "string",
            "description": "ISO-8601 date the symptom started, if the patient gave one.",
        },
        "onset_is_estimated": {
            "type": "boolean",
            "description": (
                "True if the patient was uncertain about onset_at (e.g. 'I think it started "
                "yesterday'). Never silently convert an uncertain date into a certain one."
            ),
        },
        "trend": {
            "type": "string",
            "enum": [t.value for t in SymptomTrend],
            "description": "Whether the symptom is improving, worsening, or the same. Use "
            "'unknown' if not discussed — never guess.",
        },
        "notes": {"type": "string", "description": "Any other relevant detail, in the patient's words."},
    },
    required=["health_event_id", "symptom_type"],
    handler=_record_symptom_event,
)


async def _record_medication_event(args: FlowArgs, flow_manager: FlowManager) -> Any:
    services = _services(flow_manager)
    active_medication_id = UUID(flow_manager.state[STATE_ACTIVE_MEDICATION_ID])
    event = await services.health_events.record_medication_event(
        health_event_id=UUID(args["health_event_id"]),
        patient_medication_id=active_medication_id,
        event_type=MedicationEventType(args["event_type"]),
        scheduled_at=_parse_datetime(args.get("scheduled_at")),
        occurred_at=_parse_datetime(args.get("occurred_at")),
        reason=args.get("reason"),
    )
    return {"medication_event_id": str(event.id)}


record_medication_event = FlowsFunctionSchema(
    name="record_medication_event",
    description=(
        "Record what happened with the patient's medication for a health event already "
        "created with record_health_event (event_type='medication')."
    ),
    properties={
        "health_event_id": {
            "type": "string",
            "description": "The health_event_id returned by record_health_event.",
        },
        "event_type": {
            "type": "string",
            "enum": [t.value for t in MedicationEventType],
            "description": "What happened with the dose.",
        },
        "scheduled_at": {
            "type": "string",
            "description": "ISO-8601 date/time the dose was scheduled, if known.",
        },
        "occurred_at": {
            "type": "string",
            "description": "ISO-8601 date/time the dose was actually taken/missed/etc.",
        },
        "reason": {
            "type": "string",
            "description": "Patient's stated reason, e.g. 'travel', if given. Never invent one.",
        },
    },
    required=["health_event_id", "event_type"],
    handler=_record_medication_event,
)


async def _get_clinical_escalation_protocol(args: FlowArgs, flow_manager: FlowManager) -> Any:
    services = _services(flow_manager)
    protocol = await services.escalation.resolve(
        event_type=args["event_type"], severity=args.get("severity")
    )
    return protocol.model_dump()


get_clinical_escalation_protocol = FlowsFunctionSchema(
    name="get_clinical_escalation_protocol",
    description=(
        "Retrieve the approved clinical escalation protocol for a concerning situation. "
        "Always call this before telling a patient what to do about a symptom or missed "
        "medication that sounds concerning. Relay the returned instructions verbatim — "
        "never invent or improvise clinical guidance."
    ),
    properties={
        "event_type": {
            "type": "string",
            "enum": [t.value for t in HealthEventType],
            "description": "Category of the concerning event.",
        },
        "severity": {
            "type": "string",
            "description": "Patient-described severity, if any, to help match the right protocol.",
        },
    },
    required=["event_type"],
    handler=_get_clinical_escalation_protocol,
)


async def complete_checkin(flow_manager: FlowManager, duration_seconds: int) -> Any:
    """End today's check-in once the conversation is naturally finished.

    Args:
        duration_seconds (int): Approximate total length of the call so far, in seconds.
    """
    from glp1_agent.flows.nodes import create_end_node

    services = _services(flow_manager)
    checkin = await services.checkins.complete(
        checkin_id=_checkin_id(flow_manager),
        completed_at=datetime.now(UTC),
        duration_seconds=duration_seconds,
    )
    return {"checkin_id": str(checkin.id), "status": checkin.status.value}, create_end_node()
