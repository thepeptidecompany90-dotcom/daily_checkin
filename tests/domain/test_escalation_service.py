from glp1_agent.db.repositories.escalation_repo import EscalationRepo
from glp1_agent.domain.escalation_service import EscalationService


async def test_falls_back_to_default_seed_when_no_specific_protocol(conn):
    service = EscalationService(EscalationRepo(conn))
    protocol = await service.resolve(event_type="symptom", severity="severe")

    assert protocol.action == "contact_care_team"
    assert "clinical sign-off" in protocol.instructions


async def test_resolves_specific_protocol_when_present(conn):
    await conn.execute(
        """
        INSERT INTO escalation_protocols (event_type, severity, action, instructions, urgency, contact)
        VALUES ('symptom', 'severe', 'call_clinician', 'Call the on-call clinician now.', 'high', '+15555550199')
        """
    )
    service = EscalationService(EscalationRepo(conn))
    protocol = await service.resolve(event_type="symptom", severity="severe")

    assert protocol.action == "call_clinician"
    assert protocol.urgency == "high"
