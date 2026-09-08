from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

from glp1_agent.domain.models import (
    ExtractionItem,
    HealthEvent,
    HealthEventSource,
    HealthEventType,
    MedicationEvent,
    MedicationEventType,
    SymptomEvent,
    SymptomTrend,
)


def _to_extraction_item(row: asyncpg.Record) -> ExtractionItem:
    return ExtractionItem(
        health_event_id=row["health_event_id"],
        event_type=HealthEventType(row["event_type"]),
        occurred_at=row["occurred_at"],
        observed_at=row["observed_at"],
        symptom_type=row["symptom_type"],
        severity=row["severity"],
        trend=row["trend"],
        medication_event_type=row["medication_event_type"],
        reason=row["reason"],
        notes=row["notes"],
    )


_EXTRACTION_SELECT = """
    SELECT
        he.id AS health_event_id,
        he.event_type,
        he.occurred_at,
        he.observed_at,
        se.symptom_type,
        se.severity,
        se.trend::text AS trend,
        me.event_type::text AS medication_event_type,
        me.reason,
        se.notes
    FROM health_events he
    LEFT JOIN symptom_events se ON se.health_event_id = he.id
    LEFT JOIN medication_events me ON me.health_event_id = he.id
"""


class HealthEventRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def extraction_for_checkin(self, checkin_id: UUID) -> list[ExtractionItem]:
        rows = await self._pool.fetch(
            _EXTRACTION_SELECT + " WHERE he.checkin_id = $1 ORDER BY he.occurred_at",
            checkin_id,
        )
        return [_to_extraction_item(r) for r in rows]

    async def recent_extraction(
        self, patient_id: UUID, days: int, now: datetime | None = None
    ) -> list[ExtractionItem]:
        since = (now or datetime.now(UTC)) - timedelta(days=days)
        rows = await self._pool.fetch(
            _EXTRACTION_SELECT
            + " WHERE he.patient_id = $1 AND he.occurred_at >= $2 ORDER BY he.occurred_at DESC",
            patient_id,
            since,
        )
        return [_to_extraction_item(r) for r in rows]

    async def all_extraction(self, patient_id: UUID) -> list[ExtractionItem]:
        rows = await self._pool.fetch(
            _EXTRACTION_SELECT + " WHERE he.patient_id = $1 ORDER BY he.occurred_at DESC",
            patient_id,
        )
        return [_to_extraction_item(r) for r in rows]

    async def recent(
        self, patient_id: UUID, days: int, now: datetime | None = None
    ) -> list[HealthEvent]:
        since = (now or datetime.now(UTC)) - timedelta(days=days)
        rows = await self._pool.fetch(
            """
            SELECT id, patient_id, checkin_id, event_type, occurred_at, observed_at, source
            FROM health_events
            WHERE patient_id = $1 AND occurred_at >= $2
            ORDER BY occurred_at DESC
            """,
            patient_id,
            since,
        )
        return [
            HealthEvent(
                id=r["id"],
                patient_id=r["patient_id"],
                checkin_id=r["checkin_id"],
                event_type=HealthEventType(r["event_type"]),
                occurred_at=r["occurred_at"],
                observed_at=r["observed_at"],
                source=HealthEventSource(r["source"]),
            )
            for r in rows
        ]

    async def create_health_event(
        self,
        patient_id: UUID,
        checkin_id: UUID | None,
        event_type: HealthEventType,
        occurred_at: datetime,
        observed_at: datetime,
        source: HealthEventSource,
    ) -> HealthEvent:
        row = await self._pool.fetchrow(
            """
            INSERT INTO health_events
                (patient_id, checkin_id, event_type, occurred_at, observed_at, source)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, patient_id, checkin_id, event_type, occurred_at, observed_at, source
            """,
            patient_id,
            checkin_id,
            event_type.value,
            occurred_at,
            observed_at,
            source.value,
        )
        return HealthEvent(
            id=row["id"],
            patient_id=row["patient_id"],
            checkin_id=row["checkin_id"],
            event_type=HealthEventType(row["event_type"]),
            occurred_at=row["occurred_at"],
            observed_at=row["observed_at"],
            source=HealthEventSource(row["source"]),
        )

    async def create_symptom_event(
        self,
        health_event_id: UUID,
        symptom_type: str,
        severity: str | None,
        onset_at: datetime | None,
        onset_is_estimated: bool,
        trend: SymptomTrend,
        notes: str | None,
    ) -> SymptomEvent:
        row = await self._pool.fetchrow(
            """
            INSERT INTO symptom_events
                (health_event_id, symptom_type, severity, onset_at, onset_is_estimated, trend, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, health_event_id, symptom_type, severity, onset_at, onset_is_estimated, trend, notes
            """,
            health_event_id,
            symptom_type,
            severity,
            onset_at,
            onset_is_estimated,
            trend.value,
            notes,
        )
        return SymptomEvent(
            id=row["id"],
            health_event_id=row["health_event_id"],
            symptom_type=row["symptom_type"],
            severity=row["severity"],
            onset_at=row["onset_at"],
            onset_is_estimated=row["onset_is_estimated"],
            trend=SymptomTrend(row["trend"]),
            notes=row["notes"],
        )

    async def create_medication_event(
        self,
        health_event_id: UUID,
        patient_medication_id: UUID,
        event_type: MedicationEventType,
        scheduled_at: datetime | None,
        occurred_at: datetime | None,
        reason: str | None,
    ) -> MedicationEvent:
        row = await self._pool.fetchrow(
            """
            INSERT INTO medication_events
                (health_event_id, patient_medication_id, event_type, scheduled_at, occurred_at, reason)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, health_event_id, patient_medication_id, event_type, scheduled_at, occurred_at, reason
            """,
            health_event_id,
            patient_medication_id,
            event_type.value,
            scheduled_at,
            occurred_at,
            reason,
        )
        return MedicationEvent(
            id=row["id"],
            health_event_id=row["health_event_id"],
            patient_medication_id=row["patient_medication_id"],
            event_type=MedicationEventType(row["event_type"]),
            scheduled_at=row["scheduled_at"],
            occurred_at=row["occurred_at"],
            reason=row["reason"],
        )
