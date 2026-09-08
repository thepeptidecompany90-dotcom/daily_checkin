-- V1 schema: only tables needed by the 12 in-scope backend functions.
-- checkin_observations, flags, event_evidence, call_sessions are deferred
-- (no tool in this pass writes to them) — see docs/domain-model.md §15.

CREATE TABLE patients (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name          TEXT NOT NULL,
    last_name           TEXT NOT NULL,
    date_of_birth       DATE NOT NULL,
    phone               TEXT NOT NULL,
    timezone            TEXT NOT NULL,
    preferred_language  TEXT NOT NULL DEFAULT 'en',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE journey_status AS ENUM ('active', 'ended');

CREATE TABLE patient_journeys (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id          UUID NOT NULL REFERENCES patients(id),
    status              journey_status NOT NULL DEFAULT 'active',
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at            TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE journey_state AS ENUM (
    'CONSULTED', 'PRESCRIBED', 'STARTING', 'EARLY_TREATMENT',
    'ESTABLISHED', 'DOSE_CHANGE', 'DISCONTINUED'
);

CREATE TABLE journey_state_history (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journey_id          UUID NOT NULL REFERENCES patient_journeys(id),
    state               journey_state NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at            TIMESTAMPTZ,
    transition_reason   TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Only one open (ended_at IS NULL) state row per journey.
CREATE UNIQUE INDEX journey_state_history_open_idx
    ON journey_state_history (journey_id)
    WHERE ended_at IS NULL;

CREATE TABLE medications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    generic_name        TEXT,
    route               TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE patient_medication_status AS ENUM ('active', 'ended');

CREATE TABLE patient_medications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id          UUID NOT NULL REFERENCES patients(id),
    medication_id       UUID NOT NULL REFERENCES medications(id),
    dose                NUMERIC NOT NULL,
    dose_unit           TEXT NOT NULL,
    frequency           TEXT NOT NULL,
    next_dose_at        TIMESTAMPTZ,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at            TIMESTAMPTZ,
    status              patient_medication_status NOT NULL DEFAULT 'active',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Only one active medication per patient at a time.
CREATE UNIQUE INDEX patient_medications_active_idx
    ON patient_medications (patient_id)
    WHERE status = 'active';

CREATE TYPE checkin_status AS ENUM ('scheduled', 'completed', 'missed', 'cancelled', 'failed');

CREATE TABLE checkins (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id          UUID NOT NULL REFERENCES patients(id),
    scheduled_at        TIMESTAMPTZ NOT NULL,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    status              checkin_status NOT NULL DEFAULT 'scheduled',
    duration_seconds    INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE health_event_type AS ENUM ('symptom', 'medication', 'other');
CREATE TYPE health_event_status AS ENUM ('active', 'resolved');
CREATE TYPE health_event_source AS ENUM ('patient_report', 'system');

CREATE TABLE health_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id          UUID NOT NULL REFERENCES patients(id),
    checkin_id          UUID REFERENCES checkins(id),
    event_type          health_event_type NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL,
    observed_at         TIMESTAMPTZ NOT NULL,
    status              health_event_status NOT NULL DEFAULT 'active',
    source              health_event_source NOT NULL DEFAULT 'patient_report',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE symptom_trend AS ENUM ('improving', 'worsening', 'same', 'unknown');

CREATE TABLE symptom_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    health_event_id     UUID NOT NULL REFERENCES health_events(id),
    symptom_type        TEXT NOT NULL,
    severity            TEXT,
    onset_at            TIMESTAMPTZ,
    onset_is_estimated  BOOLEAN NOT NULL DEFAULT false,
    resolved_at         TIMESTAMPTZ,
    trend               symptom_trend NOT NULL DEFAULT 'unknown',
    notes               TEXT
);

CREATE TYPE medication_event_type AS ENUM (
    'TAKEN', 'MISSED', 'DELAYED', 'REFUSED', 'SIDE_EFFECT', 'REFILL_ISSUE'
);

CREATE TABLE medication_events (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    health_event_id         UUID NOT NULL REFERENCES health_events(id),
    patient_medication_id   UUID NOT NULL REFERENCES patient_medications(id),
    event_type              medication_event_type NOT NULL,
    scheduled_at            TIMESTAMPTZ,
    occurred_at             TIMESTAMPTZ,
    dose_taken              NUMERIC,
    reason                  TEXT,
    notes                   TEXT
);

CREATE TYPE clinician_instruction_status AS ENUM ('active', 'expired', 'completed');

CREATE TABLE clinician_instructions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id          UUID NOT NULL REFERENCES patients(id),
    metric              TEXT NOT NULL,
    frequency           TEXT NOT NULL,
    instruction         TEXT NOT NULL,
    start_date          DATE NOT NULL,
    end_date            DATE,
    status              clinician_instruction_status NOT NULL DEFAULT 'active',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE escalation_protocols (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type          TEXT NOT NULL,
    severity            TEXT,
    action              TEXT NOT NULL,
    instructions        TEXT NOT NULL,
    urgency             TEXT NOT NULL,
    contact             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX checkins_patient_scheduled_idx ON checkins (patient_id, scheduled_at DESC);
CREATE INDEX health_events_patient_occurred_idx ON health_events (patient_id, occurred_at DESC);
CREATE INDEX clinician_instructions_patient_status_idx ON clinician_instructions (patient_id, status);
CREATE INDEX escalation_protocols_event_type_idx ON escalation_protocols (event_type, severity);

-- Generic, non-clinical fail-safe fallback only. Real protocol content must be authored
-- and approved by clinical staff before production use — never invented by application code.
INSERT INTO escalation_protocols (event_type, severity, action, instructions, urgency, contact)
VALUES (
    'default',
    NULL,
    'contact_care_team',
    'Thank the patient, do not offer clinical guidance, and let them know the care team will '
        'follow up. This is a placeholder protocol pending clinical sign-off.',
    'unspecified',
    NULL
);
