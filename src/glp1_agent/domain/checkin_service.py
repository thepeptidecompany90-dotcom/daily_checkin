from datetime import datetime
from uuid import UUID

from glp1_agent.db.repositories.checkin_repo import CheckinRepo
from glp1_agent.domain.models import Checkin


class RecentCheckinSummary:
    def __init__(self, checkins: list[Checkin], missed_checkin_count: int):
        self.checkins = checkins
        self.missed_checkin_count = missed_checkin_count
        self.last_completed_checkin_at: datetime | None = next(
            (c.completed_at for c in checkins if c.status.value == "completed"), None
        )


class CheckinService:
    def __init__(self, checkin_repo: CheckinRepo):
        self._checkins = checkin_repo

    async def recent_summary(self, patient_id: UUID, limit: int) -> RecentCheckinSummary:
        checkins = await self._checkins.recent(patient_id, limit)
        missed_count = await self._checkins.missed_count(patient_id, limit)
        return RecentCheckinSummary(checkins, missed_count)

    async def create(self, patient_id: UUID, scheduled_at: datetime) -> Checkin:
        return await self._checkins.create(patient_id, scheduled_at)

    async def complete(
        self, checkin_id: UUID, completed_at: datetime, duration_seconds: int
    ) -> Checkin:
        return await self._checkins.complete(checkin_id, completed_at, duration_seconds)

    async def seed_missed(self, patient_id: UUID, count: int, now: datetime) -> list[Checkin]:
        return await self._checkins.seed_missed(patient_id, count, now)
