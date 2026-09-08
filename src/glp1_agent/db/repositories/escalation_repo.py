import asyncpg

from glp1_agent.domain.models import EscalationProtocol, EscalationProtocolRow


class EscalationRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def list_all(self) -> list[EscalationProtocolRow]:
        rows = await self._pool.fetch(
            "SELECT event_type, severity, action, instructions, urgency, contact FROM escalation_protocols "
            "ORDER BY event_type, severity NULLS LAST"
        )
        return [EscalationProtocolRow(**dict(r)) for r in rows]

    async def resolve(self, event_type: str, severity: str | None) -> EscalationProtocol:
        row = await self._pool.fetchrow(
            """
            SELECT action, instructions, urgency, contact
            FROM escalation_protocols
            WHERE event_type = $1 AND (severity = $2 OR severity IS NULL)
            ORDER BY severity NULLS LAST
            LIMIT 1
            """,
            event_type,
            severity,
        )
        if row is None:
            row = await self._pool.fetchrow(
                """
                SELECT action, instructions, urgency, contact
                FROM escalation_protocols
                WHERE event_type = 'default'
                """
            )
        return EscalationProtocol(**dict(row))
