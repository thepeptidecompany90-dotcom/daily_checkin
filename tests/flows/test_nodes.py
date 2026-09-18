from datetime import UTC, date, datetime
from uuid import uuid4

from glp1_agent.domain.models import (
    ClinicianInstruction,
    Journey,
    JourneyState,
    Medication,
    MetricType,
    Patient,
    PatientContext,
)
from glp1_agent.domain.observation_service import build_tracking_items
from glp1_agent.flows.nodes import (
    _ROLE_MESSAGE,
    NODE_BUILDERS,
    _format_tracking_items,
    create_stable_checkin_node,
    create_tracking_checklist_node,
)

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _context(
    medication: Medication | None,
    due_metric: MetricType | None = None,
    clinician_instructions: list[ClinicianInstruction] | None = None,
) -> PatientContext:
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
        tracking_items=build_tracking_items(clinician_instructions or [], due_metric),
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


def test_due_metric_surfaces_in_context_message():
    node = create_stable_checkin_node(_context(medication=None, due_metric=MetricType.WEIGHT))
    assert "WEIGHT" in _task_content(node)


def test_no_due_metric_states_none_explicitly():
    node = create_stable_checkin_node(_context(medication=None, due_metric=None))
    assert "None." in _task_content(node)


def test_clinician_instruction_surfaces_acknowledge_tool_and_tracking_id():
    instruction = ClinicianInstruction(
        tracking_id=uuid4(),
        metric="hydration",
        frequency="daily",
        instruction="Track daily fluid intake",
        start_date=NOW.date(),
        end_date=None,
    )
    node = create_stable_checkin_node(
        _context(medication=None, clinician_instructions=[instruction])
    )
    content = _task_content(node)
    assert "Track daily fluid intake" in content
    assert "acknowledge_clinician_instruction" in content
    assert str(instruction.tracking_id) in content


def test_record_observation_available_in_every_node():
    for build_node in NODE_BUILDERS.values():
        node = build_node(_context(medication=None))
        function_names = [getattr(f, "name", getattr(f, "__name__", None)) for f in node["functions"]]
        assert "record_observation" in function_names


def test_new_tracking_tools_available_in_every_mode_node():
    for build_node in NODE_BUILDERS.values():
        node = build_node(_context(medication=None))
        function_names = [getattr(f, "name", getattr(f, "__name__", None)) for f in node["functions"]]
        assert "acknowledge_clinician_instruction" in function_names
        assert "skip_tracking_item" in function_names


def test_tracking_checklist_node_lists_only_pending_items():
    due_metric_item = build_tracking_items([], MetricType.WEIGHT)[0]
    node = create_tracking_checklist_node([due_metric_item])
    content = _task_content(node)
    assert "WEIGHT" in content


def test_tracking_checklist_node_functions_include_new_tools():
    due_metric_item = build_tracking_items([], MetricType.WEIGHT)[0]
    node = create_tracking_checklist_node([due_metric_item])
    function_names = [getattr(f, "name", getattr(f, "__name__", None)) for f in node["functions"]]
    assert "acknowledge_clinician_instruction" in function_names
    assert "skip_tracking_item" in function_names
    assert "complete_checkin" in function_names


def test_format_tracking_items_empty_states_none_explicitly():
    context = _context(medication=None)
    assert _format_tracking_items(context) == "  None."


def test_format_tracking_items_due_metric_includes_tool_names():
    context = _context(medication=None, due_metric=MetricType.HYDRATION)
    line = _format_tracking_items(context)
    assert "HYDRATION" in line
    assert "record_observation" in line
    assert "skip_tracking_item" in line


def test_format_tracking_items_sleep_due_metric_includes_followup_guidance():
    context = _context(medication=None, due_metric=MetricType.SLEEP)
    line = _format_tracking_items(context)
    assert "SLEEP" in line
    assert "record_observation" in line
    assert "skip_tracking_item" in line
    assert "one brief" in line.lower()
    assert "medication or last dose" in line
    assert "record_health_event" in line
    assert "record_symptom_event" in line
    assert "not several stacked questions" in line


def test_format_tracking_items_mood_due_metric_includes_followup_guidance():
    context = _context(medication=None, due_metric=MetricType.MOOD)
    line = _format_tracking_items(context)
    assert "MOOD" in line
    assert "record_health_event" in line
    assert "record_symptom_event" in line


def test_format_tracking_items_hydration_due_metric_includes_followup_guidance():
    context = _context(medication=None, due_metric=MetricType.HYDRATION)
    line = _format_tracking_items(context)
    assert "record_health_event" in line
    assert "record_symptom_event" in line


def test_format_tracking_items_weight_due_metric_has_no_followup_guidance():
    context = _context(medication=None, due_metric=MetricType.WEIGHT)
    line = _format_tracking_items(context)
    assert "WEIGHT" in line
    assert "record_observation" in line
    assert "skip_tracking_item" in line
    assert "record_health_event" not in line
    assert "record_symptom_event" not in line
    assert "follow-up" not in line.lower()


def test_format_tracking_items_protein_due_metric_has_no_followup_guidance():
    context = _context(medication=None, due_metric=MetricType.PROTEIN)
    line = _format_tracking_items(context)
    assert "PROTEIN" in line
    assert "record_observation" in line
    assert "skip_tracking_item" in line
    assert "record_health_event" not in line
    assert "record_symptom_event" not in line
    assert "follow-up" not in line.lower()


def test_tracking_checklist_node_due_metric_bullet_unchanged():
    due_metric_item = build_tracking_items([], MetricType.SLEEP)[0]
    node = create_tracking_checklist_node([due_metric_item])
    content = _task_content(node)
    assert "ask now if you haven't already" in content
    assert "record_health_event" not in content


def test_format_tracking_items_clinician_instruction_includes_details():
    tracking_id = uuid4()
    instruction = ClinicianInstruction(
        tracking_id=tracking_id,
        metric="hydration",
        frequency="daily",
        instruction="Track daily fluid intake",
        start_date=NOW.date(),
        end_date=None,
    )
    context = _context(medication=None, clinician_instructions=[instruction])
    line = _format_tracking_items(context)
    assert "hydration" in line
    assert "Track daily fluid intake" in line
    assert str(tracking_id) in line
    assert "acknowledge_clinician_instruction" in line
    assert "skip_tracking_item" in line


def test_format_tracking_items_lists_clinician_instructions_before_due_metric():
    instruction = ClinicianInstruction(
        tracking_id=uuid4(),
        metric="hydration",
        frequency="daily",
        instruction="Track daily fluid intake",
        start_date=NOW.date(),
        end_date=None,
    )
    context = _context(
        medication=None,
        due_metric=MetricType.WEIGHT,
        clinician_instructions=[instruction],
    )
    lines = _format_tracking_items(context).split("\n")
    assert len(lines) == 2
    assert "Track daily fluid intake" in lines[0]
    assert "WEIGHT" in lines[1]
