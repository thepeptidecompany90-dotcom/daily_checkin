from uuid import UUID

from glp1_agent.db.repositories.checkin_repo import CheckinRepo
from glp1_agent.db.repositories.clinician_instruction_repo import ClinicianInstructionRepo
from glp1_agent.db.repositories.health_event_repo import HealthEventRepo
from glp1_agent.db.repositories.journey_repo import JourneyRepo
from glp1_agent.db.repositories.medication_repo import MedicationRepo
from glp1_agent.db.repositories.patient_repo import PatientRepo
from glp1_agent.domain.models import PatientContext

_RECENT_CHECKIN_LIMIT = 7
_RECENT_HEALTH_EVENT_DAYS = 7


class PatientContextService:
    """Assembles the minimal per-patient context handed to the LLM (voice-agent-kb.md §19)."""

    def __init__(
        self,
        patient_repo: PatientRepo,
        journey_repo: JourneyRepo,
        medication_repo: MedicationRepo,
        checkin_repo: CheckinRepo,
        health_event_repo: HealthEventRepo,
        clinician_instruction_repo: ClinicianInstructionRepo,
    ):
        self._patients = patient_repo
        self._journeys = journey_repo
        self._medications = medication_repo
        self._checkins = checkin_repo
        self._health_events = health_event_repo
        self._instructions = clinician_instruction_repo

    async def get_patient_context(self, patient_id: UUID) -> PatientContext:
        patient = await self._patients.get(patient_id)
        journey = await self._journeys.get_current(patient_id)
        active_medication = await self._medications.get_active(patient_id)
        recent_checkins = await self._checkins.recent(patient_id, _RECENT_CHECKIN_LIMIT)
        recent_health_events = await self._health_events.recent_extraction(
            patient_id, _RECENT_HEALTH_EVENT_DAYS
        )
        active_clinician_instructions = await self._instructions.active(patient_id)
        return PatientContext(
            patient=patient,
            journey=journey,
            active_medication=active_medication,
            recent_checkins=recent_checkins,
            recent_health_events=recent_health_events,
            active_clinician_instructions=active_clinician_instructions,
        )
