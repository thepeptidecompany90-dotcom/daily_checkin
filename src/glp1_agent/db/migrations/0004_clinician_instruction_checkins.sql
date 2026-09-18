-- Durable per-checkin outcome for a clinician_instructions row: acknowledged (with what the
-- patient said) or declined. Closes the gap where CLINICIAN_INSTRUCTION tracking items had no
-- structured outcome. Also adds NOT_REPORTED to observation_value_label so due-metric tracking
-- items get an equivalent durable "asked, no answer" outcome (see ObservationService.record_skipped).

ALTER TYPE observation_value_label ADD VALUE 'NOT_REPORTED';

CREATE TYPE clinician_instruction_outcome AS ENUM ('acknowledged', 'declined');

CREATE TABLE clinician_instruction_checkins (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clinician_instruction_id    UUID NOT NULL REFERENCES clinician_instructions(id),
    checkin_id                  UUID NOT NULL REFERENCES checkins(id),
    outcome                     clinician_instruction_outcome NOT NULL,
    patient_response            TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX clinician_instruction_checkins_instruction_checkin_idx
    ON clinician_instruction_checkins (clinician_instruction_id, checkin_id);
