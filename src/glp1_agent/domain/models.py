from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class JourneyState(StrEnum):
    CONSULTED = "CONSULTED"
    PRESCRIBED = "PRESCRIBED"
    STARTING = "STARTING"
    EARLY_TREATMENT = "EARLY_TREATMENT"
    ESTABLISHED = "ESTABLISHED"
    DOSE_CHANGE = "DOSE_CHANGE"
    DISCONTINUED = "DISCONTINUED"


class CheckinStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    MISSED = "missed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class HealthEventType(StrEnum):
    SYMPTOM = "symptom"
    MEDICATION = "medication"
    OTHER = "other"


class HealthEventSource(StrEnum):
    PATIENT_REPORT = "patient_report"
    SYSTEM = "system"


class SymptomTrend(StrEnum):
    IMPROVING = "improving"
    WORSENING = "worsening"
    SAME = "same"
    UNKNOWN = "unknown"


class MedicationEventType(StrEnum):
    TAKEN = "TAKEN"
    MISSED = "MISSED"
    DELAYED = "DELAYED"
    REFUSED = "REFUSED"
    SIDE_EFFECT = "SIDE_EFFECT"
    REFILL_ISSUE = "REFILL_ISSUE"


class MetricType(StrEnum):
    MOOD = "MOOD"
    WEIGHT = "WEIGHT"
    SLEEP = "SLEEP"
    HYDRATION = "HYDRATION"
    PROTEIN = "PROTEIN"


class ObservationValueLabel(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    ADEQUATE = "ADEQUATE"
    NOT_REPORTED = "NOT_REPORTED"


class Patient(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    date_of_birth: date
    phone: str
    timezone: str
    preferred_language: str


class Journey(BaseModel):
    id: UUID
    patient_id: UUID
    state: JourneyState
    state_started_at: datetime


class Medication(BaseModel):
    patient_medication_id: UUID
    name: str
    dose: float
    dose_unit: str
    frequency: str
    next_dose_at: datetime | None


class Checkin(BaseModel):
    id: UUID
    patient_id: UUID
    scheduled_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    status: CheckinStatus
    duration_seconds: int | None


class HealthEvent(BaseModel):
    id: UUID
    patient_id: UUID
    checkin_id: UUID | None
    event_type: HealthEventType
    occurred_at: datetime
    observed_at: datetime
    source: HealthEventSource


class SymptomEvent(BaseModel):
    id: UUID
    health_event_id: UUID
    symptom_type: str
    severity: str | None
    onset_at: datetime | None
    onset_is_estimated: bool
    trend: SymptomTrend
    notes: str | None


class MedicationEvent(BaseModel):
    id: UUID
    health_event_id: UUID
    patient_medication_id: UUID
    event_type: MedicationEventType
    scheduled_at: datetime | None
    occurred_at: datetime | None
    reason: str | None


class ExtractionItem(BaseModel):
    """Flat, template-friendly view of a health_event joined with its symptom/medication detail."""

    health_event_id: UUID
    event_type: HealthEventType
    occurred_at: datetime
    observed_at: datetime
    symptom_type: str | None
    severity: str | None
    trend: str | None
    medication_event_type: str | None
    reason: str | None
    notes: str | None


class CheckinObservation(BaseModel):
    id: UUID
    patient_id: UUID
    checkin_id: UUID | None
    observation_type: MetricType
    value_label: ObservationValueLabel | None
    value_numeric: float | None
    unit: str | None
    confidence: float | None
    created_at: datetime


class MetricTrendPoint(BaseModel):
    """One plottable observation — value already resolved to a comparable number
    (backend-derived, never the LLM), plus a human-readable label for display."""

    created_at: datetime
    value: float
    display_value: str


class MetricTrend(BaseModel):
    """Chronological (oldest -> newest) series for one metric, for dashboard trend charts."""

    metric: MetricType
    points: list[MetricTrendPoint]


class ClinicianInstruction(BaseModel):
    tracking_id: UUID
    metric: str
    frequency: str
    instruction: str
    start_date: date
    end_date: date | None
    status: str = "active"


class TrackingItemKind(StrEnum):
    CLINICIAN_INSTRUCTION = "clinician_instruction"
    DUE_METRIC = "due_metric"


class TrackingItem(BaseModel):
    """A single ranked entry in the unified 'things to track today' list handed to the
    voice agent — clinician-directed tracking outranks routine metric rotation
    (voice-agent-kb.md §13)."""

    kind: TrackingItemKind
    label: str
    instruction: str | None = None
    metric: MetricType | None = None
    tracking_id: UUID | None = None
    """clinician_instructions.id — set only for CLINICIAN_INSTRUCTION items, so tools can
    reference which instruction to acknowledge/skip."""


class ClinicianInstructionOutcome(StrEnum):
    ACKNOWLEDGED = "acknowledged"
    DECLINED = "declined"


class ClinicianInstructionCheckin(BaseModel):
    id: UUID
    clinician_instruction_id: UUID
    checkin_id: UUID
    outcome: ClinicianInstructionOutcome
    patient_response: str | None
    created_at: datetime


class ClinicianInstructionCheckinRecord(BaseModel):
    """A ClinicianInstructionCheckin joined with its instruction and checkin, for dashboard display."""

    id: UUID
    metric: str
    instruction: str
    checkin_completed_at: datetime | None
    outcome: ClinicianInstructionOutcome
    patient_response: str | None
    created_at: datetime


class EscalationProtocol(BaseModel):
    action: str
    instructions: str
    urgency: str
    contact: str | None


class EscalationProtocolRow(BaseModel):
    """Full row from escalation_protocols, for the read-only reference listing."""

    event_type: str
    severity: str | None
    action: str
    instructions: str
    urgency: str
    contact: str | None


class JourneyStateHistoryItem(BaseModel):
    id: UUID
    state: JourneyState
    started_at: datetime
    ended_at: datetime | None
    transition_reason: str | None


class MedicationHistoryItem(BaseModel):
    patient_medication_id: UUID
    name: str
    dose: float
    dose_unit: str
    frequency: str
    next_dose_at: datetime | None
    status: str
    started_at: datetime
    ended_at: datetime | None


class PatientContext(BaseModel):
    patient: Patient
    journey: Journey
    active_medication: Medication | None
    recent_checkins: list[Checkin]
    recent_health_events: list[ExtractionItem]
    tracking_items: list[TrackingItem]


class TodayObservation(BaseModel):
    """Dashboard-only view: a checkin_observations row joined with the patient's name,
    for the 'what's been captured today' board."""

    patient_id: UUID
    patient_name: str
    observation_type: MetricType
    value_label: ObservationValueLabel | None
    value_numeric: float | None
    unit: str | None
    created_at: datetime


class PatientSummary(BaseModel):
    """Dashboard-only view: a patient row plus at-a-glance risk signals for the list page."""

    patient: Patient
    journey_state: JourneyState | None
    last_completed_checkin_at: datetime | None
    missed_checkin_count: int


class PatientMetricSchedule(BaseModel):
    """Per-patient override of a metric_schedules default frequency."""

    patient_id: UUID
    metric: MetricType
    frequency_days: int
    updated_at: datetime


class PatientFullRecord(BaseModel):
    """Every DB row for a patient, for the dashboard's read-only 'all data' view."""

    patient: Patient
    journey_history: list[JourneyStateHistoryItem]
    medication_history: list[MedicationHistoryItem]
    checkins: list[Checkin]
    health_events: list[ExtractionItem]
    clinician_instructions: list[ClinicianInstruction]
    clinician_instruction_checkins: list[ClinicianInstructionCheckinRecord]
    escalation_protocols: list[EscalationProtocolRow]
    metric_schedule_overrides: list[PatientMetricSchedule]
    observations: list[CheckinObservation]
