from collections.abc import Callable

from pipecat.flows import NodeConfig

from glp1_agent.domain.models import (
    CheckinStatus,
    HealthEventType,
    MetricType,
    PatientContext,
    TrackingItem,
    TrackingItemKind,
)
from glp1_agent.flows import selection
from glp1_agent.tools.functions import (
    acknowledge_clinician_instruction,
    complete_checkin,
    get_clinical_escalation_protocol,
    record_health_event,
    record_medication_event,
    record_observation,
    record_symptom_event,
    skip_tracking_item,
)

_ROLE_MESSAGE = (
    "You are a calm, warm care-team voice assistant doing a short daily check-in with a "
    "patient aged 55+ on a GLP-1 medication journey. Speak naturally and briefly — at most "
    "2-3 sentences per turn, then stop and wait for the patient's response. Never stack "
    "multiple questions or topics into a single turn; ask one thing, then let the patient "
    "answer before asking the next. Never diagnose, never invent medical advice, and never "
    "tell the patient to change or stop their medication unless "
    "get_clinical_escalation_protocol explicitly says to. If the patient mentions something "
    "concerning, call get_clinical_escalation_protocol before responding, and relay its "
    "instructions verbatim rather than improvising."
)

_EXTRACTION_INSTRUCTIONS = (
    "Whenever the patient describes a new or ongoing symptom, call record_health_event "
    "(event_type='symptom') and then record_symptom_event with what they actually said — "
    "do this as soon as it comes up, do not wait until the end of the call. Whenever they "
    "describe taking, missing, delaying, or refusing a dose, call record_health_event "
    "(event_type='medication') and then record_medication_event. Extract only what the "
    "patient actually said — never infer or invent details they didn't mention."
)

_COMMON_FUNCTIONS = [
    record_health_event,
    record_symptom_event,
    get_clinical_escalation_protocol,
    record_observation,
    acknowledge_clinician_instruction,
    skip_tracking_item,
]

_METRICS_NEEDING_FOLLOWUP = {MetricType.MOOD, MetricType.SLEEP, MetricType.HYDRATION}


def _format_recent_events(context: PatientContext) -> str:
    if not context.recent_health_events:
        return "  (none in the last 7 days)"
    lines = []
    for item in context.recent_health_events[:5]:
        date = item.occurred_at.date()
        if item.event_type == HealthEventType.SYMPTOM:
            trend = f", trend: {item.trend}" if item.trend else ""
            severity = item.severity or "unspecified severity"
            lines.append(f"  - {date}: {item.symptom_type} ({severity}{trend})")
        elif item.event_type == HealthEventType.MEDICATION:
            reason = f" ({item.reason})" if item.reason else ""
            lines.append(f"  - {date}: medication {item.medication_event_type}{reason}")
        else:
            lines.append(f"  - {date}: {item.event_type.value}")
    return "\n".join(lines)


def _format_tracking_items(context: PatientContext) -> str:
    if not context.tracking_items:
        return "  None."
    lines = []
    for item in context.tracking_items:
        if item.kind == TrackingItemKind.CLINICIAN_INSTRUCTION:
            lines.append(
                f"  - Clinician-requested — {item.label}: {item.instruction} "
                "Ask about it directly, in your own words. Once the patient responds, call "
                f"acknowledge_clinician_instruction (tracking_id={item.tracking_id}) with what "
                "they said, or skip_tracking_item if they decline."
            )
        elif item.metric in _METRICS_NEEDING_FOLLOWUP:
            lines.append(
                f"  - Metric check due — {item.metric.value}: ask about it naturally at some "
                "point in the conversation, without turning this into a rigid questionnaire. "
                "If the patient's answer sounds concerning (e.g. LOW), ask ONE brief "
                "follow-up question before moving on — not several stacked questions — "
                "picking whichever is most natural: how long this has been going on, "
                "whether it's new, or whether it seems related to their medication or last "
                "dose (check the recent medication events already listed elsewhere in this "
                "context for real dates — never invent a date or dose). Call "
                "record_observation once the patient answers the original question. If the "
                "follow-up reveals this is new or ongoing (not a one-off), also call "
                "record_health_event (event_type='symptom') and record_symptom_event with "
                "what they said, per the extraction rules below, so it's tracked as a "
                "symptom. If they decline the metric question entirely, call "
                "skip_tracking_item."
            )
        else:
            lines.append(
                f"  - Metric check due — {item.metric.value}: ask about it naturally at some "
                "point in the conversation, without turning this into a rigid questionnaire. "
                "Call record_observation once the patient answers, or skip_tracking_item if "
                "they decline."
            )
    return "\n".join(lines)


def _context_message(context: PatientContext) -> dict:
    medication = context.active_medication
    medication_line = (
        f"{medication.name}, {medication.dose}{medication.dose_unit}, {medication.frequency}"
        + (f", next dose at {medication.next_dose_at}" if medication.next_dose_at else "")
        if medication
        else "No active medication on file."
    )

    missed = sum(1 for c in context.recent_checkins if c.status == CheckinStatus.MISSED)

    content = (
        "Patient context, retrieved from the database — treat this as ground truth, and do "
        "not ask the patient to re-confirm facts already known here:\n"
        f"- Name: {context.patient.first_name}\n"
        f"- Journey state: {context.journey.state.value} "
        f"(since {context.journey.state_started_at.date()})\n"
        f"- Active medication: {medication_line}\n"
        f"- Missed check-ins in the last {len(context.recent_checkins)}: {missed}\n"
        f"- Things to track today:\n{_format_tracking_items(context)}\n"
        f"- Recent symptoms/medication events (last 7 days):\n{_format_recent_events(context)}"
    )
    return {"role": "developer", "content": content}


def create_stable_checkin_node(context: PatientContext) -> NodeConfig:
    return NodeConfig(
        name="stable_checkin",
        role_message=_ROLE_MESSAGE,
        task_messages=[
            _context_message(context),
            {
                "role": "developer",
                "content": (
                    "Greet the patient by name and ask how they've been. If they report "
                    "something is off, follow up naturally before moving on. Do not run a "
                    "fixed questionnaire — only ask about appetite/hydration/energy if the "
                    "patient hasn't already covered it naturally. "
                    + _EXTRACTION_INSTRUCTIONS
                    + " When there is nothing more to discuss, call complete_checkin."
                ),
            },
        ],
        functions=[*_COMMON_FUNCTIONS, complete_checkin],
    )


def create_initial_week_node(context: PatientContext) -> NodeConfig:
    return NodeConfig(
        name="initial_week",
        role_message=_ROLE_MESSAGE,
        task_messages=[
            _context_message(context),
            {
                "role": "developer",
                "content": (
                    "The patient is in their first days on this medication. Ask broadly about "
                    "how they've been doing, then naturally explore routine, meals, hydration, "
                    "sleep, energy, appetite, and their experience with the medication so far "
                    "(including whether/when they took their first dose). Do not ask about "
                    "anything the patient has already covered unprompted. "
                    + _EXTRACTION_INSTRUCTIONS
                    + " When there is nothing more to discuss, call complete_checkin."
                ),
            },
        ],
        functions=[*_COMMON_FUNCTIONS, record_medication_event, complete_checkin],
    )


def create_medication_day_node(context: PatientContext) -> NodeConfig:
    return NodeConfig(
        name="medication_day",
        role_message=_ROLE_MESSAGE,
        task_messages=[
            _context_message(context),
            {
                "role": "developer",
                "content": (
                    "Start with how the patient is feeling today, before mentioning "
                    "medication. If they are well, ask how they're doing with today's dose "
                    "(taken, missed, delayed, or refused) and call record_medication_event "
                    "with the result. If they report a concerning symptom, clarify it, call "
                    "get_clinical_escalation_protocol, and follow the returned protocol "
                    "instead of improvising. "
                    + _EXTRACTION_INSTRUCTIONS
                    + " When there is nothing more to discuss, call complete_checkin."
                ),
            },
        ],
        functions=[*_COMMON_FUNCTIONS, record_medication_event, complete_checkin],
    )


def create_clinician_tracking_node(context: PatientContext) -> NodeConfig:
    return NodeConfig(
        name="clinician_tracking",
        role_message=_ROLE_MESSAGE,
        task_messages=[
            _context_message(context),
            {
                "role": "developer",
                "content": (
                    "The care team asked to track something specific for this patient this "
                    "week (see the instruction in the patient context above). Ask about it "
                    "directly, in your own words, without turning it into a different medical "
                    "question. Note: recording the tracked answer as structured data is not "
                    "yet wired up in this build — still acknowledge and discuss it naturally, "
                    "and record any genuine symptom or medication event that comes up via the "
                    "normal tools. "
                    + _EXTRACTION_INSTRUCTIONS
                    + " When there is nothing more to discuss, call complete_checkin."
                ),
            },
        ],
        functions=[*_COMMON_FUNCTIONS, complete_checkin],
    )


def create_tracking_checklist_node(pending_items: list[TrackingItem]) -> NodeConfig:
    """Remediation node — reached only via complete_checkin's returned tuple when tracking
    items remain unresolved (see tools/functions.py). Lists only the items still pending, not
    the whole context, since the rest of the conversation already happened and is still in
    the LLM's context — this is a real Pipecat transition (not a bare 'stay on node' return)
    because pipecat.flows has no partial task_messages update; a fresh node is required to
    re-inject updated instructions."""
    lines = []
    for item in pending_items:
        if item.kind == TrackingItemKind.CLINICIAN_INSTRUCTION:
            lines.append(
                f"  - {item.label} (tracking_id={item.tracking_id}): {item.instruction} Ask "
                "now if you haven't already, then call acknowledge_clinician_instruction or "
                "skip_tracking_item."
            )
        else:
            lines.append(
                f"  - {item.metric.value}: ask now if you haven't already, then call "
                "record_observation or skip_tracking_item."
            )
    return NodeConfig(
        name="tracking_checklist",
        role_message=_ROLE_MESSAGE,
        task_messages=[
            {
                "role": "developer",
                "content": (
                    "Before ending the call, these specific items still need a recorded "
                    "outcome (they may already have come up loosely — actually record the "
                    "outcome now):\n"
                    + "\n".join(lines)
                    + "\nDo not re-ask about anything not listed above. Once every item above "
                    "has a recorded outcome, call complete_checkin again."
                ),
            }
        ],
        functions=[*_COMMON_FUNCTIONS, record_medication_event, complete_checkin],
    )


def create_end_node() -> NodeConfig:
    return NodeConfig(
        name="end",
        task_messages=[
            {
                "role": "developer",
                "content": "Thank the patient warmly and let them know the care team is here if needed.",
            }
        ],
        functions=[],
        post_actions=[{"type": "end_conversation"}],
    )


NODE_BUILDERS: dict[str, Callable[[PatientContext], NodeConfig]] = {
    selection.STABLE_CHECKIN: create_stable_checkin_node,
    selection.INITIAL_WEEK: create_initial_week_node,
    selection.MEDICATION_DAY: create_medication_day_node,
    selection.CLINICIAN_TRACKING: create_clinician_tracking_node,
}
