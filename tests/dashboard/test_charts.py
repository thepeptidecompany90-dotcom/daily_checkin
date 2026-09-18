from datetime import UTC, datetime, timedelta

from glp1_agent.dashboard.charts import build_trend_chart
from glp1_agent.domain.models import MetricTrend, MetricTrendPoint, MetricType

NOW = datetime(2026, 9, 9, 14, 30, tzinfo=UTC)


def _trend(points: list[MetricTrendPoint], metric: MetricType = MetricType.MOOD) -> MetricTrend:
    return MetricTrend(metric=metric, points=points)


def test_build_trend_chart_none_with_no_points():
    assert build_trend_chart(_trend([]), "UTC") is None


def test_build_trend_chart_none_with_a_single_point():
    points = [MetricTrendPoint(created_at=NOW, value=2, display_value="Normal")]
    assert build_trend_chart(_trend(points), "UTC") is None


def test_build_trend_chart_plots_every_point():
    points = [
        MetricTrendPoint(created_at=NOW - timedelta(days=2), value=1, display_value="Low"),
        MetricTrendPoint(created_at=NOW - timedelta(days=1), value=3, display_value="High"),
        MetricTrendPoint(created_at=NOW, value=2, display_value="Normal"),
    ]
    chart = build_trend_chart(_trend(points), "UTC")

    assert chart is not None
    assert len(chart.points) == 3
    assert chart.end_label == "Normal"


def test_build_trend_chart_range_label_spans_min_to_max():
    points = [
        MetricTrendPoint(created_at=NOW - timedelta(days=1), value=1, display_value="Low"),
        MetricTrendPoint(created_at=NOW, value=3, display_value="High"),
    ]
    chart = build_trend_chart(_trend(points), "UTC")

    assert chart.range_label == "Low – High"


def test_build_trend_chart_end_label_clears_the_endpoint_dot():
    """Regression: the label must not sit on the same row as the dot it names —
    verified against a live render, where a fixed label slot either overlapped the
    dot (endpoint near the top) or floated disconnected from it (endpoint near the
    bottom)."""
    points_near_top = [
        MetricTrendPoint(created_at=NOW - timedelta(days=1), value=1, display_value="Low"),
        MetricTrendPoint(created_at=NOW, value=2, display_value="Normal"),
    ]
    chart = build_trend_chart(_trend(points_near_top, metric=MetricType.SLEEP), "UTC")
    last_point_cy = chart.points[-1].cy
    assert abs(chart.end_label_y - last_point_cy) >= 10

    points_near_bottom = [
        MetricTrendPoint(created_at=NOW - timedelta(days=1), value=196.4, display_value="196.4lbs"),
        MetricTrendPoint(created_at=NOW, value=190.2, display_value="190.2lbs"),
    ]
    chart = build_trend_chart(_trend(points_near_bottom, metric=MetricType.WEIGHT), "UTC")
    last_point_cy = chart.points[-1].cy
    assert abs(chart.end_label_y - last_point_cy) >= 10


def test_build_trend_chart_range_label_collapses_when_flat():
    points = [
        MetricTrendPoint(created_at=NOW - timedelta(days=1), value=2, display_value="Normal"),
        MetricTrendPoint(created_at=NOW, value=2, display_value="Normal"),
    ]
    chart = build_trend_chart(_trend(points), "UTC")

    assert chart.range_label == "Normal"
    assert chart.points[0].cy == chart.points[1].cy


def test_build_trend_chart_dates_use_patient_timezone():
    early_morning_utc = datetime(2026, 9, 9, 4, 0, tzinfo=UTC)
    points = [
        MetricTrendPoint(created_at=early_morning_utc - timedelta(days=1), value=1, display_value="Low"),
        MetricTrendPoint(created_at=early_morning_utc, value=3, display_value="High"),
    ]
    chart = build_trend_chart(_trend(points), "America/Los_Angeles")

    # 04:00 UTC on the 9th is still the 8th in America/Los_Angeles (UTC-7 in September).
    assert chart.end_date == "Sep 08"
    assert "Sep 09, 2026: High" not in chart.points[-1].tooltip
    assert "Sep 08, 2026: High" in chart.points[-1].tooltip
