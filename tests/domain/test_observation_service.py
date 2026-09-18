from datetime import UTC, datetime, timedelta
from uuid import uuid4

from glp1_agent.domain.models import (
    CheckinObservation,
    ClinicianInstruction,
    MetricType,
    ObservationValueLabel,
    TrackingItemKind,
)
from glp1_agent.domain.observation_service import (
    build_metric_trends,
    build_tracking_items,
    classify_protein_description,
    ordinal_score,
    resolve_metric_frequencies,
    select_due_metric,
    tracking_item_key,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def _observation(
    observation_type: MetricType,
    created_at: datetime,
    value_label: ObservationValueLabel | None = None,
    value_numeric: float | None = None,
    unit: str | None = None,
) -> CheckinObservation:
    return CheckinObservation(
        id=uuid4(),
        patient_id=uuid4(),
        checkin_id=None,
        observation_type=observation_type,
        value_label=value_label,
        value_numeric=value_numeric,
        unit=unit,
        confidence=None,
        created_at=created_at,
    )


def test_ordinal_score_mapping():
    assert ordinal_score(ObservationValueLabel.LOW) == 1
    assert ordinal_score(ObservationValueLabel.NORMAL) == 2
    assert ordinal_score(ObservationValueLabel.HIGH) == 3
    assert ordinal_score(ObservationValueLabel.ADEQUATE) == 2


def test_classify_protein_description_detects_keyword():
    assert classify_protein_description("I had grilled chicken and rice") == ObservationValueLabel.ADEQUATE


def test_classify_protein_description_no_keyword_is_low():
    assert classify_protein_description("just some crackers and an apple") == ObservationValueLabel.LOW


def test_classify_protein_description_empty_is_none():
    assert classify_protein_description("") is None
    assert classify_protein_description("   ") is None
    assert classify_protein_description(None) is None


def test_select_due_metric_never_observed_picks_mood_first():
    assert select_due_metric(NOW, {}, {m: 3 for m in MetricType}) == MetricType.MOOD


def test_select_due_metric_exact_boundary_is_due():
    last_observed = {MetricType.WEIGHT: NOW - timedelta(days=7)}
    frequencies = {MetricType.WEIGHT: 7}
    assert select_due_metric(NOW, last_observed, frequencies) == MetricType.WEIGHT


def test_select_due_metric_under_frequency_not_due():
    last_observed = {m: NOW - timedelta(days=1) for m in MetricType}
    frequencies = {MetricType.MOOD: 3, MetricType.WEIGHT: 7, MetricType.SLEEP: 3,
                   MetricType.HYDRATION: 3, MetricType.PROTEIN: 3}
    assert select_due_metric(NOW, last_observed, frequencies) is None


def test_select_due_metric_over_frequency_is_due():
    last_observed = {MetricType.SLEEP: NOW - timedelta(days=5)}
    frequencies = {MetricType.SLEEP: 3}
    assert select_due_metric(NOW, last_observed, frequencies) == MetricType.SLEEP


def test_select_due_metric_ties_broken_by_declaration_order():
    # Both never observed and both due -> MOOD wins over WEIGHT (declared first).
    frequencies = {MetricType.MOOD: 1, MetricType.WEIGHT: 7}
    assert select_due_metric(NOW, {}, frequencies) == MetricType.MOOD


def test_select_due_metric_none_due_returns_none():
    last_observed = {m: NOW for m in MetricType}
    frequencies = {m: 7 for m in MetricType}
    assert select_due_metric(NOW, last_observed, frequencies) is None


def test_select_due_metric_skips_metric_missing_from_schedule():
    frequencies = {MetricType.WEIGHT: 7}
    assert select_due_metric(NOW, {}, frequencies) == MetricType.WEIGHT


def test_resolve_metric_frequencies_override_replaces_default():
    defaults = {MetricType.MOOD: 1, MetricType.WEIGHT: 7}
    overrides = {MetricType.WEIGHT: 3}
    assert resolve_metric_frequencies(defaults, overrides) == {MetricType.MOOD: 1, MetricType.WEIGHT: 3}


def test_resolve_metric_frequencies_no_override_keeps_default():
    defaults = {MetricType.MOOD: 1, MetricType.WEIGHT: 7}
    assert resolve_metric_frequencies(defaults, {}) == defaults


def _instruction(metric: str, instruction: str) -> ClinicianInstruction:
    return ClinicianInstruction(
        tracking_id=uuid4(),
        metric=metric,
        frequency="daily",
        instruction=instruction,
        start_date=NOW.date(),
        end_date=None,
    )


def test_build_tracking_items_empty_when_nothing_active():
    assert build_tracking_items([], None) == []


def test_build_tracking_items_clinician_only():
    instruction = _instruction("hydration", "Track daily fluid intake")
    items = build_tracking_items([instruction], None)
    assert len(items) == 1
    assert items[0].kind == TrackingItemKind.CLINICIAN_INSTRUCTION
    assert items[0].label == "hydration"
    assert items[0].instruction == "Track daily fluid intake"
    assert items[0].metric is None


def test_build_tracking_items_metric_only():
    items = build_tracking_items([], MetricType.WEIGHT)
    assert len(items) == 1
    assert items[0].kind == TrackingItemKind.DUE_METRIC
    assert items[0].label == "WEIGHT"
    assert items[0].metric == MetricType.WEIGHT
    assert items[0].instruction is None


def test_build_tracking_items_clinician_before_metric():
    items = build_tracking_items([_instruction("hydration", "Track fluid intake")], MetricType.WEIGHT)
    assert items[0].kind == TrackingItemKind.CLINICIAN_INSTRUCTION
    assert items[-1].kind == TrackingItemKind.DUE_METRIC


def test_build_tracking_items_preserves_clinician_instruction_source_order():
    first = _instruction("hydration", "Track fluid intake")
    second = _instruction("sleep", "Track sleep hours")
    items = build_tracking_items([first, second], None)
    assert [i.label for i in items] == ["hydration", "sleep"]


def test_build_tracking_items_clinician_carries_tracking_id():
    instruction = _instruction("hydration", "Track daily fluid intake")
    items = build_tracking_items([instruction], None)
    assert items[0].tracking_id == instruction.tracking_id


def test_build_tracking_items_metric_has_no_tracking_id():
    items = build_tracking_items([], MetricType.WEIGHT)
    assert items[0].tracking_id is None


def test_tracking_item_key_due_metric():
    items = build_tracking_items([], MetricType.WEIGHT)
    assert tracking_item_key(items[0]) == "metric:WEIGHT"


def test_tracking_item_key_clinician_instruction():
    instruction = _instruction("hydration", "Track daily fluid intake")
    items = build_tracking_items([instruction], None)
    assert tracking_item_key(items[0]) == f"instruction:{instruction.tracking_id}"


def test_build_metric_trends_returns_all_metric_types_even_with_no_data():
    trends = build_metric_trends([])
    assert [t.metric for t in trends] == list(MetricType)
    assert all(t.points == [] for t in trends)


def test_build_metric_trends_excludes_not_reported():
    observations = [_observation(MetricType.MOOD, NOW, value_label=ObservationValueLabel.NOT_REPORTED)]
    trend = next(t for t in build_metric_trends(observations) if t.metric == MetricType.MOOD)
    assert trend.points == []


def test_build_metric_trends_sorts_chronologically():
    later = _observation(MetricType.MOOD, NOW, value_label=ObservationValueLabel.HIGH)
    earlier = _observation(MetricType.MOOD, NOW - timedelta(days=2), value_label=ObservationValueLabel.LOW)
    trend = next(t for t in build_metric_trends([later, earlier]) if t.metric == MetricType.MOOD)
    assert [p.created_at for p in trend.points] == [earlier.created_at, later.created_at]


def test_build_metric_trends_weight_uses_value_numeric():
    observation = _observation(MetricType.WEIGHT, NOW, value_numeric=182.0, unit="lbs")
    trend = next(t for t in build_metric_trends([observation]) if t.metric == MetricType.WEIGHT)
    assert trend.points[0].value == 182.0
    assert trend.points[0].display_value == "182lbs"


def test_build_metric_trends_ordinal_metric_uses_ordinal_score_and_titlecase_label():
    observation = _observation(MetricType.SLEEP, NOW, value_label=ObservationValueLabel.HIGH)
    trend = next(t for t in build_metric_trends([observation]) if t.metric == MetricType.SLEEP)
    assert trend.points[0].value == ordinal_score(ObservationValueLabel.HIGH)
    assert trend.points[0].display_value == "High"
