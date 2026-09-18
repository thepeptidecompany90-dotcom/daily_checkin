from datetime import UTC, datetime

from glp1_agent.dashboard.formatting import (
    badge_class,
    humanize,
    local_dt,
    missed_checkin_badge_class,
)


def test_humanize_converts_shouty_snake_case():
    assert humanize("DOSE_CHANGE") == "Dose change"


def test_humanize_capitalizes_lowercase_enum_value():
    assert humanize("improving") == "Improving"


def test_humanize_handles_none_and_empty():
    assert humanize(None) == "—"
    assert humanize("") == "—"


def test_badge_class_maps_known_value_in_category():
    assert badge_class("DISCONTINUED", "journey_state") == "badge-danger"
    assert badge_class("missed", "checkin_status") == "badge-danger"
    assert badge_class("TAKEN", "medication_event_type") == "badge-success"


def test_badge_class_falls_back_to_neutral_for_unknown_value_or_category():
    assert badge_class("ESTABLISHED", "journey_state") == "badge-neutral"
    assert badge_class("mild", "symptom_severity") == "badge-neutral"


def test_badge_class_maps_tracking_item_kind():
    assert badge_class("clinician_instruction", "tracking_item_kind") == "badge-info"
    assert badge_class("due_metric", "tracking_item_kind") == "badge-neutral"


def test_badge_class_maps_clinician_instruction_outcome():
    assert badge_class("acknowledged", "clinician_instruction_outcome") == "badge-success"
    assert badge_class("declined", "clinician_instruction_outcome") == "badge-warning"


def test_missed_checkin_badge_class_thresholds():
    assert missed_checkin_badge_class(0) == "badge-neutral"
    assert missed_checkin_badge_class(2) == "badge-warning"
    assert missed_checkin_badge_class(3) == "badge-danger"


def test_local_dt_converts_to_named_timezone():
    value = datetime(2026, 9, 17, 14, 30, tzinfo=UTC)

    assert local_dt(value, "America/Los_Angeles") == "Sep 17, 2026, 07:30 AM"


def test_local_dt_without_timezone_keeps_original_offset():
    value = datetime(2026, 9, 17, 14, 30, tzinfo=UTC)

    assert local_dt(value) == "Sep 17, 2026, 02:30 PM"


def test_local_dt_handles_none():
    assert local_dt(None) == "—"
