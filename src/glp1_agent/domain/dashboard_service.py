from uuid import UUID

from glp1_agent.db.repositories.checkin_repo import CheckinRepo
from glp1_agent.db.repositories.clinician_instruction_repo import ClinicianInstructionRepo
from glp1_agent.db.repositories.escalation_repo import EscalationRepo
from glp1_agent.db.repositories.health_event_repo import HealthEventRepo
from glp1_agent.db.repositories.journey_repo import JourneyRepo
from glp1_agent.db.repositories.medication_repo import MedicationRepo
from glp1_agent.db.repositories.patient_repo import PatientRepo
from glp1_agent.domain.models import Checkin, ExtractionItem, Patient, PatientFullRecord


class DashboardService:
    def __init__(
        self,
        patient_repo: PatientRepo,
        checkin_repo: CheckinRepo,
        health_event_repo: HealthEventRepo,
        journey_repo: JourneyRepo,
        medication_repo: MedicationRepo,
        clinician_instruction_repo: ClinicianInstructionRepo,
        escalation_repo: EscalationRepo,
    ):
        self._patients = patient_repo
        self._checkins = checkin_repo
        self._health_events = health_event_repo
        self._journeys = journey_repo
        self._medications = medication_repo
        self._instructions = clinician_instruction_repo
        self._escalations = escalation_repo

    async def list_patients(self) -> list[Patient]:
        return await self._patients.list_all()

    async def get_last_completed_extraction(
        self, patient_id: UUID
    ) -> tuple[Checkin | None, list[ExtractionItem]]:
        checkin = await self._checkins.most_recent_completed(patient_id)
        if checkin is None:
            return None, []
        items = await self._health_events.extraction_for_checkin(checkin.id)
        return checkin, items

    async def get_full_record(self, patient_id: UUID) -> PatientFullRecord:
        return PatientFullRecord(
            patient=await self._patients.get(patient_id),
            journey_history=await self._journeys.history(patient_id),
            medication_history=await self._medications.history(patient_id),
            checkins=await self._checkins.all(patient_id),
            health_events=await self._health_events.all_extraction(patient_id),
            clinician_instructions=await self._instructions.all(patient_id),
            escalation_protocols=await self._escalations.list_all(),
        )
