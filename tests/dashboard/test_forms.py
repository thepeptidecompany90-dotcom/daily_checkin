from datetime import UTC, datetime

from glp1_agent.dashboard.forms import dt_input_value, resolve_next_dose_at


def test_dt_input_value_formats_for_datetime_local_field_in_patient_timezone():
    value = datetime(2026, 9, 17, 14, 30, tzinfo=UTC)

    assert dt_input_value(value, "America/Los_Angeles") == "2026-09-17T07:30"


def test_dt_input_value_handles_none():
    assert dt_input_value(None, "UTC") == ""


def test_resolve_next_dose_at_keeps_existing_value_when_field_left_blank():
    existing = datetime(2026, 9, 17, 14, 30, tzinfo=UTC)

    assert resolve_next_dose_at("", existing, "UTC") == existing


def test_resolve_next_dose_at_parses_submitted_value_in_patient_timezone():
    result = resolve_next_dose_at("2026-09-17T07:30", None, "America/Los_Angeles")

    assert result == datetime(2026, 9, 17, 14, 30, tzinfo=UTC)
