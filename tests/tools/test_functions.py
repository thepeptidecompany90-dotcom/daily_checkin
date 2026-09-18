import pytest

from glp1_agent.db.repositories.clinician_instruction_repo import ClinicianInstructionRepo
from glp1_agent.domain.models import HealthEventType, MedicationEventType, MetricType, SymptomTrend
from glp1_agent.domain.observation_service import build_tracking_items
from glp1_agent.services import Services
from glp1_agent.tools.functions import (
    STATE_ACTIVE_MEDICATION_ID,
    STATE_CHECKIN_ID,
    STATE_PATIENT_ID,
    STATE_RESOLVED_TRACKING_KEYS,
    STATE_SERVICES,
    STATE_TRACKING_ITEMS,
    STATE_TRACKING_LOOP_COUNT,
    acknowledge_clinician_instruction,
    complete_checkin,
    get_clinical_escalation_protocol,
    record_health_event,
    record_medication_event,
    record_observation,
    record_symptom_event,
    skip_tracking_item,
)
from tests.helpers import UTC_NOW, seed_checkin, seed_medication, seed_patient


class FakeFlowManager:
    def __init__(self, state: dict):
        self.state = state


@pytest.fixture
async def flow_manager(conn) -> FakeFlowManager:
    patient_id = await seed_patient(conn)
    checkin_id = await seed_checkin(conn, patient_id, UTC_NOW)
    medication_id = await seed_medication(conn, patient_id)
    services = Services.build(conn)
    return FakeFlowManager(
        {
            STATE_SERVICES: services,
            STATE_PATIENT_ID: str(patient_id),
            STATE_CHECKIN_ID: str(checkin_id),
            STATE_ACTIVE_MEDICATION_ID: str(medication_id),
        }
    )


@pytest.fixture
async def flow_manager_with_tracking(conn):
    """A flow_manager with one pending due metric (WEIGHT) and one pending clinician
    instruction ("hydration") — the common shape for exercising the completion loop."""
    patient_id = await seed_patient(conn)
    checkin_id = await seed_checkin(conn, patient_id, UTC_NOW)
    medication_id = await seed_medication(conn, patient_id)
    instruction = await ClinicianInstructionRepo(conn).create(
        patient_id,
        metric="hydration",
        frequency="daily",
        instruction="Track daily fluid intake",
        start_date=UTC_NOW.date(),
        end_date=None,
    )
    tracking_items = build_tracking_items([instruction], MetricType.WEIGHT)
    services = Services.build(conn)
    fm = FakeFlowManager(
        {
            STATE_SERVICES: services,
            STATE_PATIENT_ID: str(patient_id),
            STATE_CHECKIN_ID: str(checkin_id),
            STATE_ACTIVE_MEDICATION_ID: str(medication_id),
            STATE_TRACKING_ITEMS: tracking_items,
            STATE_RESOLVED_TRACKING_KEYS: set(),
            STATE_TRACKING_LOOP_COUNT: 0,
        }
    )
    return fm, instruction, checkin_id


async def test_record_health_event_persists_and_stays_on_node(flow_manager):
    result = await record_health_event.handler(
        {"event_type": HealthEventType.SYMPTOM.value, "occurred_at": UTC_NOW.isoformat()},
        flow_manager,
    )
    assert "health_event_id" in result


async def test_record_health_event_rejects_bad_enum(flow_manager):
    with pytest.raises(ValueError):
        await record_health_event.handler(
            {"event_type": "not_a_real_type", "occurred_at": UTC_NOW.isoformat()},
            flow_manager,
        )


async def test_record_symptom_event_chains_from_health_event(flow_manager):
    health_event = await record_health_event.handler(
        {"event_type": HealthEventType.SYMPTOM.value, "occurred_at": UTC_NOW.isoformat()},
        flow_manager,
    )
    result = await record_symptom_event.handler(
        {
            "health_event_id": health_event["health_event_id"],
            "symptom_type": "nausea",
            "trend": SymptomTrend.IMPROVING.value,
        },
        flow_manager,
    )
    assert "symptom_event_id" in result


async def test_record_medication_event_uses_active_medication_from_state(flow_manager):
    health_event = await record_health_event.handler(
        {"event_type": HealthEventType.MEDICATION.value, "occurred_at": UTC_NOW.isoformat()},
        flow_manager,
    )
    result = await record_medication_event.handler(
        {
            "health_event_id": health_event["health_event_id"],
            "event_type": MedicationEventType.MISSED.value,
        },
        flow_manager,
    )
    assert "medication_event_id" in result


async def test_get_clinical_escalation_protocol_returns_fallback(flow_manager):
    protocol = await get_clinical_escalation_protocol.handler(
        {"event_type": HealthEventType.SYMPTOM.value}, flow_manager
    )
    assert protocol["action"] == "contact_care_team"


async def test_complete_checkin_transitions_to_end_node(flow_manager):
    result, next_node = await complete_checkin(flow_manager, duration_seconds=120)
    assert result["status"] == "completed"
    assert next_node["name"] == "end"


async def test_record_observation_weight_persists(flow_manager):
    result = await record_observation.handler(
        {"observation_type": "WEIGHT", "value_numeric": 182.4}, flow_manager
    )
    assert result["value_numeric"] == 182.4
    assert result["value_label"] is None


async def test_record_observation_mood_persists(flow_manager):
    result = await record_observation.handler(
        {"observation_type": "MOOD", "value_label": "LOW"}, flow_manager
    )
    assert result["value_label"] == "LOW"
    assert result["value_numeric"] is None


async def test_record_observation_protein_classifies_adequate(flow_manager):
    result = await record_observation.handler(
        {"observation_type": "PROTEIN", "raw_food_description": "grilled chicken and a salad"},
        flow_manager,
    )
    assert result["value_label"] == "ADEQUATE"


async def test_record_observation_protein_classifies_low(flow_manager):
    result = await record_observation.handler(
        {"observation_type": "PROTEIN", "raw_food_description": "just some crackers"},
        flow_manager,
    )
    assert result["value_label"] == "LOW"


async def test_record_observation_protein_rejects_empty_description(flow_manager):
    with pytest.raises(ValueError):
        await record_observation.handler(
            {"observation_type": "PROTEIN", "raw_food_description": ""}, flow_manager
        )


async def test_record_observation_weight_rejects_missing_numeric(flow_manager):
    with pytest.raises(ValueError):
        await record_observation.handler({"observation_type": "WEIGHT"}, flow_manager)


async def test_record_observation_mood_rejects_missing_label(flow_manager):
    with pytest.raises(ValueError):
        await record_observation.handler({"observation_type": "MOOD"}, flow_manager)


async def test_complete_checkin_with_pending_items_returns_tracking_checklist_node(
    flow_manager_with_tracking,
):
    fm, _instruction, _checkin_id = flow_manager_with_tracking
    result, next_node = await complete_checkin(fm, duration_seconds=60)
    assert result["status"] == "pending_tracking_items"
    assert next_node["name"] == "tracking_checklist"
    assert fm.state[STATE_TRACKING_LOOP_COUNT] == 1


async def test_complete_checkin_loop_cap_force_resolves_and_ends(conn, flow_manager_with_tracking):
    fm, _instruction, checkin_id = flow_manager_with_tracking
    await complete_checkin(fm, duration_seconds=60)  # attempt 1 -> loop
    await complete_checkin(fm, duration_seconds=60)  # attempt 2 -> loop
    result, next_node = await complete_checkin(fm, duration_seconds=60)  # attempt 3 -> force-resolve

    assert next_node["name"] == "end"
    assert result["status"] == "completed"

    not_reported = await conn.fetchval(
        "SELECT count(*) FROM checkin_observations WHERE checkin_id = $1 AND value_label = 'NOT_REPORTED'",
        checkin_id,
    )
    assert not_reported == 1

    declined = await conn.fetchval(
        "SELECT count(*) FROM clinician_instruction_checkins WHERE checkin_id = $1 AND outcome = 'declined'",
        checkin_id,
    )
    assert declined == 1


async def test_record_observation_marks_matching_due_metric_resolved(flow_manager_with_tracking):
    fm, _instruction, _checkin_id = flow_manager_with_tracking
    await record_observation.handler({"observation_type": "WEIGHT", "value_numeric": 180.0}, fm)
    assert "metric:WEIGHT" in fm.state[STATE_RESOLVED_TRACKING_KEYS]

    # Only the clinician instruction remains pending now.
    result, next_node = await complete_checkin(fm, duration_seconds=60)
    assert next_node["name"] == "tracking_checklist"
    assert result["remaining"] == ["hydration"]


async def test_acknowledge_clinician_instruction_persists_and_resolves(flow_manager_with_tracking):
    fm, instruction, _checkin_id = flow_manager_with_tracking
    result = await acknowledge_clinician_instruction.handler(
        {"tracking_id": str(instruction.tracking_id), "patient_response": "Drinking plenty of water"},
        fm,
    )
    assert "clinician_instruction_checkin_id" in result
    assert f"instruction:{instruction.tracking_id}" in fm.state[STATE_RESOLVED_TRACKING_KEYS]


async def test_skip_tracking_item_due_metric_persists_not_reported(conn, flow_manager_with_tracking):
    fm, _instruction, checkin_id = flow_manager_with_tracking
    result = await skip_tracking_item.handler({"kind": "due_metric", "metric": "WEIGHT"}, fm)
    assert result["skipped"] == "metric:WEIGHT"
    row = await conn.fetchrow(
        "SELECT value_label FROM checkin_observations WHERE checkin_id = $1 AND observation_type = 'WEIGHT'",
        checkin_id,
    )
    assert row["value_label"] == "NOT_REPORTED"


async def test_skip_tracking_item_clinician_instruction_persists_declined(
    conn, flow_manager_with_tracking
):
    fm, instruction, checkin_id = flow_manager_with_tracking
    result = await skip_tracking_item.handler(
        {
            "kind": "clinician_instruction",
            "tracking_id": str(instruction.tracking_id),
            "reason": "declined to answer",
        },
        fm,
    )
    assert result["skipped"] == f"instruction:{instruction.tracking_id}"
    row = await conn.fetchrow(
        "SELECT outcome FROM clinician_instruction_checkins WHERE checkin_id = $1", checkin_id
    )
    assert row["outcome"] == "declined"


async def test_skip_tracking_item_due_metric_requires_metric(flow_manager_with_tracking):
    fm, _instruction, _checkin_id = flow_manager_with_tracking
    with pytest.raises(ValueError):
        await skip_tracking_item.handler({"kind": "due_metric"}, fm)


async def test_skip_tracking_item_clinician_instruction_requires_tracking_id(flow_manager_with_tracking):
    fm, _instruction, _checkin_id = flow_manager_with_tracking
    with pytest.raises(ValueError):
        await skip_tracking_item.handler({"kind": "clinician_instruction"}, fm)
