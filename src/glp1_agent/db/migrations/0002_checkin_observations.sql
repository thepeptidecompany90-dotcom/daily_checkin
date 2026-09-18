-- Builds out checkin_observations (deferred in 0001_initial.sql, see docs/domain-model.md
-- §10) for the daily metric rotation feature, extended with a denormalized patient_id
-- (same pattern as health_events) and a split value_label/value_numeric so both
-- categorical self-reports and numeric measurements fit one table.
--
-- metric_schedules is a small global config table (not per-patient) giving the default
-- cadence used to derive which single metric is "due" for a patient on a given day —
-- the due-ness itself is never stored, only derived at read time from these frequencies
-- plus the most recent checkin_observations row per metric (docs/domain-model.md §4.1).

CREATE TYPE metric_type AS ENUM ('MOOD', 'WEIGHT', 'SLEEP', 'HYDRATION', 'PROTEIN');
CREATE TYPE observation_value_label AS ENUM ('LOW', 'NORMAL', 'HIGH', 'ADEQUATE');

CREATE TABLE metric_schedules (
    metric          metric_type PRIMARY KEY,
    frequency_days  INT NOT NULL
);

INSERT INTO metric_schedules (metric, frequency_days) VALUES
    ('MOOD', 1),
    ('WEIGHT', 7),
    ('SLEEP', 3),
    ('HYDRATION', 3),
    ('PROTEIN', 3);

CREATE TABLE checkin_observations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id          UUID NOT NULL REFERENCES patients(id),
    checkin_id          UUID REFERENCES checkins(id),
    observation_type    metric_type NOT NULL,
    value_label         observation_value_label,
    value_numeric       NUMERIC,
    unit                TEXT,
    confidence          REAL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX checkin_observations_patient_type_idx
    ON checkin_observations (patient_id, observation_type, created_at DESC);
