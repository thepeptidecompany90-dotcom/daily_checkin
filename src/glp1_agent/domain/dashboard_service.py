from datetime import datetime
from uuid import UUID

from glp1_agent.db.repositories.checkin_repo import CheckinRepo
from glp1_agent.db.repositories.clinician_instruction_checkin_repo import (
    ClinicianInstructionCheckinRepo,
)
from glp1_agent.db.repositories.clinician_instruction_repo import ClinicianInstructionRepo
from glp1_agent.db.repositories.escalation_repo import EscalationRepo
from glp1_agent.db.repositories.health_event_repo import HealthEventRepo
from glp1_agent.db.repositories.journey_repo import JourneyRepo
from glp1_agent.db.repositories.medication_repo import MedicationRepo
from glp1_agent.db.repositories.observation_repo import ObservationRepo
from glp1_agent.db.repositories.patient_metric_schedule_repo import PatientMetricScheduleRepo
from glp1_agent.db.repositories.patient_repo import PatientRepo
from glp1_agent.domain.models import (
    Checkin,
    ExtractionItem,
    PatientFullRecord,
    PatientSummary,
    TodayObservation,
)

_MISSED_CHECKIN_WINDOW = 14


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
        observation_repo: ObservationRepo,
        patient_metric_schedule_repo: PatientMetricScheduleRepo,
        clinician_instruction_checkin_repo: ClinicianInstructionCheckinRepo,
    ):
        self._patients = patient_repo
        self._checkins = checkin_repo
        self._health_events = health_event_repo
        self._journeys = journey_repo
        self._medications = medication_repo
        self._instructions = clinician_instruction_repo
        self._escalations = escalation_repo
        self._observations = observation_repo
        self._patient_metric_schedules = patient_metric_schedule_repo
        self._instruction_checkins = clinician_instruction_checkin_repo

    async def list_patients(self) -> list[PatientSummary]:
        patients = await self._patients.list_all()
        summaries = []
        for patient in patients:
            try:
                journey_state = (await self._journeys.get_current(patient.id)).state
            except LookupError:
                journey_state = None
            last_checkin = await self._checkins.most_recent_completed(patient.id)
            missed_checkin_count = await self._checkins.missed_count(
                patient.id, _MISSED_CHECKIN_WINDOW
            )
            summaries.append(
                PatientSummary(
                    patient=patient,
                    journey_state=journey_state,
                    last_completed_checkin_at=(
                        last_checkin.completed_at if last_checkin else None
                    ),
                    missed_checkin_count=missed_checkin_count,
                )
            )
        return summaries

    async def get_last_completed_extraction(
        self, patient_id: UUID
    ) -> tuple[Checkin | None, list[ExtractionItem]]:
        checkin = await self._checkins.most_recent_completed(patient_id)
        if checkin is None:
            return None, []
        items = await self._health_events.extraction_for_checkin(checkin.id)
        return checkin, items

    async def get_today_observations(self, now: datetime | None = None) -> list[TodayObservation]:
        return await self._observations.today(now)

    async def get_full_record(
        self, patient_id: UUID, days: int | None = None, now: datetime | None = None
    ) -> PatientFullRecord:
        return PatientFullRecord(
            patient=await self._patients.get(patient_id),
            journey_history=await self._journeys.history(patient_id),
            medication_history=await self._medications.history(patient_id),
            checkins=await self._checkins.all(patient_id, days, now),
            health_events=await self._health_events.all_extraction(patient_id, days, now),
            clinician_instructions=await self._instructions.all(patient_id),
            clinician_instruction_checkins=await self._instruction_checkins.all_for_patient(
                patient_id
            ),
            escalation_protocols=await self._escalations.list_all(),
            metric_schedule_overrides=await self._patient_metric_schedules.for_patient(patient_id),
            observations=await self._observations.all_for_patient(patient_id),
        )
