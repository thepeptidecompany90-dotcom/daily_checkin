from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

from glp1_agent.domain.models import (
    CheckinObservation,
    MetricType,
    ObservationValueLabel,
    TodayObservation,
)

_COLUMNS = (
    "id, patient_id, checkin_id, observation_type, value_label, value_numeric, "
    "unit, confidence, created_at"
)


def _to_observation(row: asyncpg.Record) -> CheckinObservation:
    return CheckinObservation(**dict(row))


class ObservationRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def last_observed_at_by_metric(self, patient_id: UUID) -> dict[MetricType, datetime]:
        rows = await self._pool.fetch(
            """
            SELECT DISTINCT ON (observation_type) observation_type, created_at
            FROM checkin_observations
            WHERE patient_id = $1
            ORDER BY observation_type, created_at DESC
            """,
            patient_id,
        )
        return {MetricType(r["observation_type"]): r["created_at"] for r in rows}

    async def create(
        self,
        patient_id: UUID,
        checkin_id: UUID | None,
        observation_type: MetricType,
        value_label: ObservationValueLabel | None,
        value_numeric: float | None,
        unit: str | None,
        confidence: float | None,
    ) -> CheckinObservation:
        row = await self._pool.fetchrow(
            f"""
            INSERT INTO checkin_observations
                (patient_id, checkin_id, observation_type, value_label, value_numeric, unit, confidence)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING {_COLUMNS}
            """,
            patient_id,
            checkin_id,
            observation_type.value,
            value_label.value if value_label else None,
            value_numeric,
            unit,
            confidence,
        )
        return _to_observation(row)

    async def today(self, now: datetime | None = None) -> list[TodayObservation]:
        now = now or datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        rows = await self._pool.fetch(
            """
            SELECT
                o.patient_id,
                p.first_name || ' ' || p.last_name AS patient_name,
                o.observation_type,
                o.value_label,
                o.value_numeric,
                o.unit,
                o.created_at
            FROM checkin_observations o
            JOIN patients p ON p.id = o.patient_id
            WHERE o.created_at >= $1 AND o.created_at < $2
            ORDER BY o.created_at DESC
            """,
            day_start,
            day_end,
        )
        return [TodayObservation(**dict(r)) for r in rows]

    async def all_for_patient(self, patient_id: UUID) -> list[CheckinObservation]:
        rows = await self._pool.fetch(
            f"""
            SELECT {_COLUMNS}
            FROM checkin_observations
            WHERE patient_id = $1
            ORDER BY created_at DESC
            """,
            patient_id,
        )
        return [_to_observation(r) for r in rows]
