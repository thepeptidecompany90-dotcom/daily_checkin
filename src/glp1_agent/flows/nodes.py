from collections.abc import Callable

from pipecat.flows import NodeConfig

from glp1_agent.domain.models import CheckinStatus, HealthEventType, PatientContext
from glp1_agent.flows import selection
from glp1_agent.tools.functions import (
    complete_checkin,
    get_clinical_escalation_protocol,
    record_health_event,
    record_medication_event,
    record_symptom_event,
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

_COMMON_FUNCTIONS = [record_health_event, record_symptom_event, get_clinical_escalation_protocol]


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


def _context_message(context: PatientContext) -> dict:
    medication = context.active_medication
    medication_line = (
        f"{medication.name}, {medication.dose}{medication.dose_unit}, {medication.frequency}"
        + (f", next dose at {medication.next_dose_at}" if medication.next_dose_at else "")
        if medication
        else "No active medication on file."
    )

    instructions_line = (
        "; ".join(
            f"{i.metric}: {i.instruction}" for i in context.active_clinician_instructions
        )
        if context.active_clinician_instructions
        else "None."
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
        f"- Active clinician tracking: {instructions_line}\n"
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
