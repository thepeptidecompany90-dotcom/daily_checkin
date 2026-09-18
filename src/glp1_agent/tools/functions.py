from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pipecat.flows import FlowArgs, FlowManager, FlowsFunctionSchema

from glp1_agent.domain.models import (
    ClinicianInstructionOutcome,
    HealthEventSource,
    HealthEventType,
    MedicationEventType,
    MetricType,
    ObservationValueLabel,
    SymptomTrend,
    TrackingItem,
    TrackingItemKind,
)
from glp1_agent.domain.observation_service import tracking_item_key
from glp1_agent.services import Services

# flow_manager.state keys populated once at bootstrap (see bot.py) and read by every tool here.
STATE_SERVICES = "services"
STATE_PATIENT_ID = "patient_id"
STATE_CHECKIN_ID = "checkin_id"
STATE_ACTIVE_MEDICATION_ID = "active_medication_id"

# Tracking-item completion state (see bot.py's on_client_connected for seeding, and
# complete_checkin below for the gating logic that reads these).
STATE_TRACKING_ITEMS = "tracking_items"
STATE_RESOLVED_TRACKING_KEYS = "resolved_tracking_keys"
STATE_TRACKING_LOOP_COUNT = "tracking_loop_count"


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


def _mark_tracking_resolved(flow_manager: FlowManager, key: str) -> None:
    flow_manager.state.setdefault(STATE_RESOLVED_TRACKING_KEYS, set()).add(key)


async def _record_observation(args: FlowArgs, flow_manager: FlowManager) -> Any:
    services = _services(flow_manager)
    value_label = ObservationValueLabel(args["value_label"]) if args.get("value_label") else None
    observation = await services.observations.record_observation(
        patient_id=_patient_id(flow_manager),
        checkin_id=_checkin_id(flow_manager),
        observation_type=MetricType(args["observation_type"]),
        value_label=value_label,
        value_numeric=args.get("value_numeric"),
        raw_food_description=args.get("raw_food_description"),
    )
    # Marks the matching due-metric tracking item resolved regardless of which node this was
    # called from — so a metric answered naturally mid-conversation never needs the
    # tracking_checklist remediation node at all (see complete_checkin below).
    _mark_tracking_resolved(flow_manager, f"metric:{args['observation_type']}")
    return {
        "observation_id": str(observation.id),
        "value_label": observation.value_label.value if observation.value_label else None,
        "value_numeric": observation.value_numeric,
    }


record_observation = FlowsFunctionSchema(
    name="record_observation",
    description=(
        "Record a daily wellness metric the patient reported. For MOOD, SLEEP, or "
        "HYDRATION, set value_label to LOW, NORMAL, or HIGH based on how the patient "
        "described it in their own words — never ask them to pick a number. For WEIGHT, "
        "set value_numeric to the number of pounds the patient actually stated — never "
        "estimate, round, or convert units yourself. For PROTEIN, do not ask the patient "
        "to rate or estimate their intake — ask what they ate and pass it verbatim as "
        "raw_food_description; the backend classifies it as adequate or low, never "
        "classify it yourself. Only call this when the patient actually reported the "
        "metric, not proactively."
    ),
    properties={
        "observation_type": {
            "type": "string",
            "enum": [t.value for t in MetricType],
            "description": "Which metric this observation is for.",
        },
        "value_label": {
            "type": "string",
            "enum": ["LOW", "NORMAL", "HIGH"],
            "description": "Patient's self-reported level, for MOOD/SLEEP/HYDRATION only.",
        },
        "value_numeric": {
            "type": "number",
            "description": "Weight in pounds, as stated by the patient, for WEIGHT only.",
        },
        "raw_food_description": {
            "type": "string",
            "description": (
                "Patient's own words describing what they ate, for PROTEIN only. Do not "
                "summarize or judge it — pass what they said."
            ),
        },
    },
    required=["observation_type"],
    handler=_record_observation,
)


async def _acknowledge_clinician_instruction(args: FlowArgs, flow_manager: FlowManager) -> Any:
    services = _services(flow_manager)
    record = await services.clinician_instruction_checkins.record(
        clinician_instruction_id=UUID(args["tracking_id"]),
        checkin_id=_checkin_id(flow_manager),
        outcome=ClinicianInstructionOutcome.ACKNOWLEDGED,
        patient_response=args["patient_response"],
    )
    _mark_tracking_resolved(flow_manager, f"instruction:{args['tracking_id']}")
    return {"clinician_instruction_checkin_id": str(record.id)}


acknowledge_clinician_instruction = FlowsFunctionSchema(
    name="acknowledge_clinician_instruction",
    description=(
        "Record that a clinician-requested tracking item was discussed and the patient "
        "answered. Call once the patient has actually responded to that specific ask, using "
        "the tracking_id given in the patient context."
    ),
    properties={
        "tracking_id": {
            "type": "string",
            "description": "The tracking_id for this clinician instruction, from the patient context.",
        },
        "patient_response": {
            "type": "string",
            "description": "What the patient actually said, in their own words.",
        },
    },
    required=["tracking_id", "patient_response"],
    handler=_acknowledge_clinician_instruction,
)


async def _skip_tracking_item(args: FlowArgs, flow_manager: FlowManager) -> Any:
    services = _services(flow_manager)
    kind = TrackingItemKind(args["kind"])
    if kind is TrackingItemKind.DUE_METRIC:
        if not args.get("metric"):
            raise ValueError("metric is required when kind=due_metric")
        metric = MetricType(args["metric"])
        await services.observations.record_skipped(
            _patient_id(flow_manager), _checkin_id(flow_manager), metric
        )
        key = f"metric:{metric.value}"
    else:
        if not args.get("tracking_id"):
            raise ValueError("tracking_id is required when kind=clinician_instruction")
        await services.clinician_instruction_checkins.record(
            clinician_instruction_id=UUID(args["tracking_id"]),
            checkin_id=_checkin_id(flow_manager),
            outcome=ClinicianInstructionOutcome.DECLINED,
            patient_response=args.get("reason"),
        )
        key = f"instruction:{args['tracking_id']}"
    _mark_tracking_resolved(flow_manager, key)
    return {"skipped": key}


skip_tracking_item = FlowsFunctionSchema(
    name="skip_tracking_item",
    description=(
        "Record that a tracking item was asked about but the patient declined to answer, or "
        "genuinely doesn't apply right now. Only call this after actually asking — never to "
        "avoid asking."
    ),
    properties={
        "kind": {
            "type": "string",
            "enum": [k.value for k in TrackingItemKind],
            "description": "Which kind of tracking item this is.",
        },
        "metric": {
            "type": "string",
            "enum": [m.value for m in MetricType],
            "description": "Required when kind=due_metric.",
        },
        "tracking_id": {
            "type": "string",
            "description": "Required when kind=clinician_instruction.",
        },
        "reason": {"type": "string", "description": "Patient's stated reason, if any. Never invent one."},
    },
    required=["kind"],
    handler=_skip_tracking_item,
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


_MAX_CHECKLIST_ATTEMPTS = 2  # bounces into tracking_checklist before force-resolving and ending


async def complete_checkin(flow_manager: FlowManager, duration_seconds: int) -> Any:
    """End today's check-in once the conversation is naturally finished — but only once every
    tracking item (due metric / clinician instruction) has a recorded outcome. If any remain,
    routes into the tracking_checklist node instead, up to _MAX_CHECKLIST_ATTEMPTS bounces
    before force-resolving the rest as skipped and ending anyway, so the call can never be
    held open indefinitely.

    Args:
        duration_seconds (int): Approximate total length of the call so far, in seconds.
    """
    from glp1_agent.flows.nodes import create_end_node, create_tracking_checklist_node

    items: list[TrackingItem] = flow_manager.state.get(STATE_TRACKING_ITEMS, [])
    resolved: set[str] = flow_manager.state.get(STATE_RESOLVED_TRACKING_KEYS, set())
    pending = [item for item in items if tracking_item_key(item) not in resolved]

    if pending:
        attempts = flow_manager.state.get(STATE_TRACKING_LOOP_COUNT, 0)
        if attempts < _MAX_CHECKLIST_ATTEMPTS:
            flow_manager.state[STATE_TRACKING_LOOP_COUNT] = attempts + 1
            return (
                {"status": "pending_tracking_items", "remaining": [item.label for item in pending]},
                create_tracking_checklist_node(pending),
            )
        services = _services(flow_manager)
        for item in pending:
            if item.kind is TrackingItemKind.DUE_METRIC:
                await services.observations.record_skipped(
                    _patient_id(flow_manager), _checkin_id(flow_manager), item.metric
                )
            else:
                await services.clinician_instruction_checkins.record(
                    clinician_instruction_id=item.tracking_id,
                    checkin_id=_checkin_id(flow_manager),
                    outcome=ClinicianInstructionOutcome.DECLINED,
                    patient_response="auto-recorded: not resolved after repeated attempts",
                )
        # Fall through — force-resolved, complete anyway.

    services = _services(flow_manager)
    checkin = await services.checkins.complete(
        checkin_id=_checkin_id(flow_manager),
        completed_at=datetime.now(UTC),
        duration_seconds=duration_seconds,
    )
    return {"checkin_id": str(checkin.id), "status": checkin.status.value}, create_end_node()
