-- Per-patient overrides of metric_schedules' global default cadence. A row here for
-- (patient, metric) takes precedence over the global default; no row means the global
-- default from metric_schedules still applies (see observation_service.resolve_metric_frequencies).

CREATE TABLE patient_metric_schedules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      UUID NOT NULL REFERENCES patients(id),
    metric          metric_type NOT NULL,
    frequency_days  INT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX patient_metric_schedules_patient_metric_idx
    ON patient_metric_schedules (patient_id, metric);
