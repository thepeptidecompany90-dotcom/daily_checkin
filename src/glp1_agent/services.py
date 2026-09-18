from dataclasses import dataclass

import asyncpg

from glp1_agent.db.repositories.checkin_repo import CheckinRepo
from glp1_agent.db.repositories.clinician_instruction_checkin_repo import (
    ClinicianInstructionCheckinRepo,
)
from glp1_agent.db.repositories.clinician_instruction_repo import ClinicianInstructionRepo
from glp1_agent.db.repositories.escalation_repo import EscalationRepo
from glp1_agent.db.repositories.health_event_repo import HealthEventRepo
from glp1_agent.db.repositories.journey_repo import JourneyRepo
from glp1_agent.db.repositories.medication_repo import MedicationRepo
from glp1_agent.db.repositories.metric_schedule_repo import MetricScheduleRepo
from glp1_agent.db.repositories.observation_repo import ObservationRepo
from glp1_agent.db.repositories.patient_metric_schedule_repo import PatientMetricScheduleRepo
from glp1_agent.db.repositories.patient_repo import PatientRepo
from glp1_agent.domain.checkin_service import CheckinService
from glp1_agent.domain.dashboard_service import DashboardService
from glp1_agent.domain.escalation_service import EscalationService
from glp1_agent.domain.health_event_service import HealthEventService
from glp1_agent.domain.journey_service import JourneyService
from glp1_agent.domain.observation_service import ObservationService
from glp1_agent.domain.patient_context_service import PatientContextService


@dataclass
class Services:
    """Bundle of domain services, built once per pool and shared across a conversation."""

    patient_repo: PatientRepo
    journey_repo: JourneyRepo
    medication_repo: MedicationRepo
    checkins: CheckinService
    health_events: HealthEventService
    clinician_instructions: ClinicianInstructionRepo
    clinician_instruction_checkins: ClinicianInstructionCheckinRepo
    patient_metric_schedules: PatientMetricScheduleRepo
    observations: ObservationService
    escalation: EscalationService
    journey: JourneyService
    patient_context: PatientContextService
    dashboard: DashboardService

    @classmethod
    def build(cls, pool: asyncpg.Pool) -> "Services":
        patient_repo = PatientRepo(pool)
        journey_repo = JourneyRepo(pool)
        medication_repo = MedicationRepo(pool)
        checkin_repo = CheckinRepo(pool)
        health_event_repo = HealthEventRepo(pool)
        clinician_instruction_repo = ClinicianInstructionRepo(pool)
        clinician_instruction_checkin_repo = ClinicianInstructionCheckinRepo(pool)
        escalation_repo = EscalationRepo(pool)
        observation_repo = ObservationRepo(pool)
        metric_schedule_repo = MetricScheduleRepo(pool)
        patient_metric_schedule_repo = PatientMetricScheduleRepo(pool)
        return cls(
            patient_repo=patient_repo,
            journey_repo=journey_repo,
            medication_repo=medication_repo,
            checkins=CheckinService(checkin_repo),
            health_events=HealthEventService(health_event_repo),
            clinician_instructions=clinician_instruction_repo,
            clinician_instruction_checkins=clinician_instruction_checkin_repo,
            patient_metric_schedules=patient_metric_schedule_repo,
            observations=ObservationService(observation_repo),
            escalation=EscalationService(escalation_repo),
            journey=JourneyService(journey_repo),
            patient_context=PatientContextService(
                patient_repo,
                journey_repo,
                medication_repo,
                checkin_repo,
                health_event_repo,
                clinician_instruction_repo,
                observation_repo,
                metric_schedule_repo,
                patient_metric_schedule_repo,
            ),
            dashboard=DashboardService(
                patient_repo,
                checkin_repo,
                health_event_repo,
                journey_repo,
                medication_repo,
                clinician_instruction_repo,
                escalation_repo,
                observation_repo,
                patient_metric_schedule_repo,
                clinician_instruction_checkin_repo,
            ),
        )
