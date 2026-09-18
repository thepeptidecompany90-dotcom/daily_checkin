from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

from glp1_agent.domain.models import Checkin


def _to_checkin(row: asyncpg.Record) -> Checkin:
    return Checkin(**dict(row))


class CheckinRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def recent(self, patient_id: UUID, limit: int) -> list[Checkin]:
        rows = await self._pool.fetch(
            """
            SELECT id, patient_id, scheduled_at, started_at, completed_at, status, duration_seconds
            FROM checkins
            WHERE patient_id = $1
            ORDER BY scheduled_at DESC
            LIMIT $2
            """,
            patient_id,
            limit,
        )
        return [_to_checkin(r) for r in rows]

    async def create(self, patient_id: UUID, scheduled_at: datetime) -> Checkin:
        row = await self._pool.fetchrow(
            """
            INSERT INTO checkins (patient_id, scheduled_at, status)
            VALUES ($1, $2, 'scheduled')
            RETURNING id, patient_id, scheduled_at, started_at, completed_at, status, duration_seconds
            """,
            patient_id,
            scheduled_at,
        )
        return _to_checkin(row)

    async def complete(
        self, checkin_id: UUID, completed_at: datetime, duration_seconds: int
    ) -> Checkin:
        row = await self._pool.fetchrow(
            """
            UPDATE checkins
            SET status = 'completed', completed_at = $2, duration_seconds = $3
            WHERE id = $1
            RETURNING id, patient_id, scheduled_at, started_at, completed_at, status, duration_seconds
            """,
            checkin_id,
            completed_at,
            duration_seconds,
        )
        if row is None:
            raise LookupError(f"checkin {checkin_id} not found")
        return _to_checkin(row)

    async def most_recent_completed(self, patient_id: UUID) -> Checkin | None:
        row = await self._pool.fetchrow(
            """
            SELECT id, patient_id, scheduled_at, started_at, completed_at, status, duration_seconds
            FROM checkins
            WHERE patient_id = $1 AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            patient_id,
        )
        return _to_checkin(row) if row is not None else None

    async def all(
        self, patient_id: UUID, days: int | None = None, now: datetime | None = None
    ) -> list[Checkin]:
        if days is None:
            rows = await self._pool.fetch(
                """
                SELECT id, patient_id, scheduled_at, started_at, completed_at, status, duration_seconds
                FROM checkins
                WHERE patient_id = $1
                ORDER BY scheduled_at DESC
                """,
                patient_id,
            )
        else:
            since = (now or datetime.now(UTC)) - timedelta(days=days)
            rows = await self._pool.fetch(
                """
                SELECT id, patient_id, scheduled_at, started_at, completed_at, status, duration_seconds
                FROM checkins
                WHERE patient_id = $1 AND scheduled_at >= $2
                ORDER BY scheduled_at DESC
                """,
                patient_id,
                since,
            )
        return [_to_checkin(r) for r in rows]

    async def seed_missed(self, patient_id: UUID, count: int, now: datetime) -> list[Checkin]:
        """Insert `count` past checkins with status='missed', one per preceding day.

        A dashboard-only convenience to simulate missed calls quickly; each row is a real,
        independent checkin (docs/domain-model.md §7.1), not a derived/synthetic count.
        """
        rows = await self._pool.fetch(
            """
            INSERT INTO checkins (patient_id, scheduled_at, status)
            SELECT $1, $2::timestamptz - (n || ' days')::interval, 'missed'
            FROM generate_series(1, $3) AS n
            RETURNING id, patient_id, scheduled_at, started_at, completed_at, status, duration_seconds
            """,
            patient_id,
            now,
            count,
        )
        return [_to_checkin(r) for r in rows]

    async def missed_count(self, patient_id: UUID, limit: int) -> int:
        return await self._pool.fetchval(
            """
            SELECT count(*) FROM (
                SELECT status FROM checkins
                WHERE patient_id = $1
                ORDER BY scheduled_at DESC
                LIMIT $2
            ) recent
            WHERE status = 'missed'
            """,
            patient_id,
            limit,
        )
