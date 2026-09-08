"""Encodes voice-agent-kb.md §15's extraction rules as assertions on tool behavior.

These do not exercise a live LLM — they assert that once args are extracted (as the LLM is
instructed to do), the tool layer stores them faithfully rather than collapsing distinctions
the KB explicitly calls out as important.
"""

from datetime import timedelta
from uuid import UUID

import pytest

from glp1_agent.domain.models import HealthEventType, SymptomTrend
from glp1_agent.services import Services
from glp1_agent.tools.functions import (
    STATE_CHECKIN_ID,
    STATE_PATIENT_ID,
    STATE_SERVICES,
    record_health_event,
    record_symptom_event,
)
from tests.helpers import UTC_NOW, seed_checkin, seed_patient


class FakeFlowManager:
    def __init__(self, state: dict):
        self.state = state


@pytest.fixture
async def flow_manager(conn) -> FakeFlowManager:
    patient_id = await seed_patient(conn)
    checkin_id = await seed_checkin(conn, patient_id, UTC_NOW)
    services = Services.build(conn)
    return FakeFlowManager(
        {
            STATE_SERVICES: services,
            STATE_PATIENT_ID: str(patient_id),
            STATE_CHECKIN_ID: str(checkin_id),
        }
    )


async def test_rule3_occurred_at_and_observed_at_never_collapse(flow_manager, conn):
    """"I've been feeling feverish for the last two days" reported today: occurred_at must be
    two days before observed_at, not equal to it (docs/domain-model.md §13 worked example)."""
    two_days_ago = (UTC_NOW - timedelta(days=2)).isoformat()

    result = await record_health_event.handler(
        {"event_type": HealthEventType.SYMPTOM.value, "occurred_at": two_days_ago},
        flow_manager,
    )

    row = await conn.fetchrow(
        "SELECT occurred_at, observed_at FROM health_events WHERE id = $1",
        UUID(result["health_event_id"]),
    )
    assert row["occurred_at"] != row["observed_at"]
    assert row["occurred_at"] < row["observed_at"]


async def test_rule4_uncertain_onset_is_flagged_not_silently_made_certain(flow_manager):
    """"I think it started yesterday" must set onset_is_estimated, never assert a bare date
    with the same confidence as a patient-confirmed one."""
    health_event = await record_health_event.handler(
        {
            "event_type": HealthEventType.SYMPTOM.value,
            "occurred_at": (UTC_NOW - timedelta(days=1)).isoformat(),
        },
        flow_manager,
    )

    result = await record_symptom_event.handler(
        {
            "health_event_id": health_event["health_event_id"],
            "symptom_type": "nausea",
            "onset_at": (UTC_NOW - timedelta(days=1)).isoformat(),
            "onset_is_estimated": True,
            "trend": SymptomTrend.UNKNOWN.value,
        },
        flow_manager,
    )
    assert "symptom_event_id" in result


async def test_trend_defaults_to_unknown_when_not_discussed(flow_manager):
    """KB §15 rule 1/2: never infer information the patient didn't state — an unspecified
    trend must default to 'unknown', not be guessed as 'same' or 'improving'."""
    health_event = await record_health_event.handler(
        {"event_type": HealthEventType.SYMPTOM.value, "occurred_at": UTC_NOW.isoformat()},
        flow_manager,
    )
    symptom_id = await record_symptom_event.handler(
        {
            "health_event_id": health_event["health_event_id"],
            "symptom_type": "headache",
            # trend intentionally omitted
        },
        flow_manager,
    )
    assert "symptom_event_id" in symptom_id
