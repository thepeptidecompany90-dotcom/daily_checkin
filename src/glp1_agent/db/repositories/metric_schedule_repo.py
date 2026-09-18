import asyncpg

from glp1_agent.domain.models import MetricType


class MetricScheduleRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def all(self) -> dict[MetricType, int]:
        rows = await self._pool.fetch("SELECT metric, frequency_days FROM metric_schedules")
        return {MetricType(r["metric"]): r["frequency_days"] for r in rows}
