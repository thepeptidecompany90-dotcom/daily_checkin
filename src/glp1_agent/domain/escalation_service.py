from glp1_agent.db.repositories.escalation_repo import EscalationRepo
from glp1_agent.domain.models import EscalationProtocol


class EscalationService:
    def __init__(self, escalation_repo: EscalationRepo):
        self._protocols = escalation_repo

    async def resolve(self, event_type: str, severity: str | None = None) -> EscalationProtocol:
        return await self._protocols.resolve(event_type, severity)
