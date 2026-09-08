import pytest

from glp1_agent.domain.models import HealthEventType, MedicationEventType, SymptomTrend
from glp1_agent.services import Services
from glp1_agent.tools.functions import (
    STATE_ACTIVE_MEDICATION_ID,
    STATE_CHECKIN_ID,
    STATE_PATIENT_ID,
    STATE_SERVICES,
    complete_checkin,
    get_clinical_escalation_protocol,
    record_health_event,
    record_medication_event,
    record_symptom_event,
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
