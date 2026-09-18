from datetime import UTC, datetime
from uuid import UUID

from glp1_agent.db.repositories.checkin_repo import CheckinRepo
from glp1_agent.db.repositories.clinician_instruction_repo import ClinicianInstructionRepo
from glp1_agent.db.repositories.health_event_repo import HealthEventRepo
from glp1_agent.db.repositories.journey_repo import JourneyRepo
from glp1_agent.db.repositories.medication_repo import MedicationRepo
from glp1_agent.db.repositories.metric_schedule_repo import MetricScheduleRepo
from glp1_agent.db.repositories.observation_repo import ObservationRepo
from glp1_agent.db.repositories.patient_metric_schedule_repo import PatientMetricScheduleRepo
from glp1_agent.db.repositories.patient_repo import PatientRepo
from glp1_agent.domain.models import PatientContext
from glp1_agent.domain.observation_service import (
    build_tracking_items,
    resolve_metric_frequencies,
    select_due_metric,
)

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
        observation_repo: ObservationRepo,
        metric_schedule_repo: MetricScheduleRepo,
        patient_metric_schedule_repo: PatientMetricScheduleRepo,
    ):
        self._patients = patient_repo
        self._journeys = journey_repo
        self._medications = medication_repo
        self._checkins = checkin_repo
        self._health_events = health_event_repo
        self._instructions = clinician_instruction_repo
        self._observations = observation_repo
        self._metric_schedules = metric_schedule_repo
        self._patient_metric_schedules = patient_metric_schedule_repo

    async def get_patient_context(
        self, patient_id: UUID, now: datetime | None = None
    ) -> PatientContext:
        now = now or datetime.now(UTC)
        patient = await self._patients.get(patient_id)
        journey = await self._journeys.get_current(patient_id)
        active_medication = await self._medications.get_active(patient_id)
        recent_checkins = await self._checkins.recent(patient_id, _RECENT_CHECKIN_LIMIT)
        recent_health_events = await self._health_events.recent_extraction(
            patient_id, _RECENT_HEALTH_EVENT_DAYS
        )
        active_clinician_instructions = await self._instructions.active(patient_id)
        last_observed = await self._observations.last_observed_at_by_metric(patient_id)
        default_frequencies = await self._metric_schedules.all()
        overrides = await self._patient_metric_schedules.for_patient(patient_id)
        override_map = {o.metric: o.frequency_days for o in overrides}
        frequencies = resolve_metric_frequencies(default_frequencies, override_map)
        due_metric = select_due_metric(now, last_observed, frequencies)
        return PatientContext(
            patient=patient,
            journey=journey,
            active_medication=active_medication,
            recent_checkins=recent_checkins,
            recent_health_events=recent_health_events,
            tracking_items=build_tracking_items(active_clinician_instructions, due_metric),
        )
