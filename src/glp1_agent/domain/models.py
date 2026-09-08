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


class ClinicianInstruction(BaseModel):
    tracking_id: UUID
    metric: str
    frequency: str
    instruction: str
    start_date: date
    end_date: date | None
    status: str = "active"


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
    active_clinician_instructions: list[ClinicianInstruction]


class PatientFullRecord(BaseModel):
    """Every DB row for a patient, for the dashboard's read-only 'all data' view."""

    patient: Patient
    journey_history: list[JourneyStateHistoryItem]
    medication_history: list[MedicationHistoryItem]
    checkins: list[Checkin]
    health_events: list[ExtractionItem]
    clinician_instructions: list[ClinicianInstruction]
    escalation_protocols: list[EscalationProtocolRow]
