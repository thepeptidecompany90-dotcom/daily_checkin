from uuid import UUID

import asyncpg

from glp1_agent.domain.models import MetricType, PatientMetricSchedule


class PatientMetricScheduleRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def for_patient(self, patient_id: UUID) -> list[PatientMetricSchedule]:
        rows = await self._pool.fetch(
            """
            SELECT patient_id, metric, frequency_days, updated_at
            FROM patient_metric_schedules
            WHERE patient_id = $1
            ORDER BY metric
            """,
            patient_id,
        )
        return [PatientMetricSchedule(**dict(r)) for r in rows]

    async def upsert(
        self, patient_id: UUID, metric: MetricType, frequency_days: int
    ) -> PatientMetricSchedule:
        row = await self._pool.fetchrow(
            """
            INSERT INTO patient_metric_schedules (patient_id, metric, frequency_days)
            VALUES ($1, $2, $3)
            ON CONFLICT (patient_id, metric)
            DO UPDATE SET frequency_days = EXCLUDED.frequency_days, updated_at = now()
            RETURNING patient_id, metric, frequency_days, updated_at
            """,
            patient_id,
            metric.value,
            frequency_days,
        )
        return PatientMetricSchedule(**dict(row))
