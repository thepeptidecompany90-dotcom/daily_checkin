from datetime import datetime
from uuid import UUID

from glp1_agent.db.repositories.health_event_repo import HealthEventRepo
from glp1_agent.domain.models import (
    HealthEvent,
    HealthEventSource,
    HealthEventType,
    MedicationEvent,
    MedicationEventType,
    SymptomEvent,
    SymptomTrend,
)


class HealthEventService:
    def __init__(self, health_event_repo: HealthEventRepo):
        self._events = health_event_repo

    async def recent(
        self, patient_id: UUID, days: int, now: datetime | None = None
    ) -> list[HealthEvent]:
        return await self._events.recent(patient_id, days, now)

    async def record_health_event(
        self,
        patient_id: UUID,
        checkin_id: UUID | None,
        event_type: HealthEventType,
        occurred_at: datetime,
        observed_at: datetime,
        source: HealthEventSource,
    ) -> HealthEvent:
        return await self._events.create_health_event(
            patient_id, checkin_id, event_type, occurred_at, observed_at, source
        )

    async def record_symptom_event(
        self,
        health_event_id: UUID,
        symptom_type: str,
        severity: str | None,
        onset_at: datetime | None,
        onset_is_estimated: bool,
        trend: SymptomTrend,
        notes: str | None,
    ) -> SymptomEvent:
        return await self._events.create_symptom_event(
            health_event_id, symptom_type, severity, onset_at, onset_is_estimated, trend, notes
        )

    async def record_medication_event(
        self,
        health_event_id: UUID,
        patient_medication_id: UUID,
        event_type: MedicationEventType,
        scheduled_at: datetime | None,
        occurred_at: datetime | None,
        reason: str | None,
    ) -> MedicationEvent:
        return await self._events.create_medication_event(
            health_event_id, patient_medication_id, event_type, scheduled_at, occurred_at, reason
        )
