"""SVG geometry for per-metric trend sparklines.

Kept out of templates so coordinate/path arithmetic isn't hand-rolled in Jinja — mirrors
forms.py/formatting.py: this package's convention for display-only helpers.
"""

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from glp1_agent.domain.models import MetricTrend

_WIDTH = 280
_HEIGHT = 64
_PAD_X = 6
_PAD_Y = 8
_HIT_RADIUS = 12
_POINT_RADIUS = 4


@dataclass
class TrendPointView:
    cx: float
    cy: float
    tooltip: str


@dataclass
class TrendChartView:
    width: int
    height: int
    path_d: str
    points: list[TrendPointView]
    end_label: str
    end_label_y: float
    range_label: str
    start_date: str
    end_date: str
    point_radius: int = _POINT_RADIUS
    hit_radius: int = _HIT_RADIUS


def build_trend_chart(trend: MetricTrend, timezone: str) -> TrendChartView | None:
    """None when there are fewer than two points — not enough to draw a line."""
    if len(trend.points) < 2:
        return None

    tz = ZoneInfo(timezone)
    local_dates = [p.created_at.astimezone(tz) for p in trend.points]

    values = [p.value for p in trend.points]
    v_min, v_max = min(values), max(values)
    v_range = v_max - v_min or 1  # a flat series still renders as a straight mid-line

    times = [d.timestamp() for d in local_dates]
    t_min, t_max = min(times), max(times)
    t_range = t_max - t_min or 1

    plot_w = _WIDTH - 2 * _PAD_X
    plot_h = _HEIGHT - 2 * _PAD_Y

    coords = [
        (
            _PAD_X + (d.timestamp() - t_min) / t_range * plot_w,
            _PAD_Y + (1 - (p.value - v_min) / v_range) * plot_h,
        )
        for p, d in zip(trend.points, local_dates)
    ]
    path_d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in coords)

    points = [
        TrendPointView(cx=x, cy=y, tooltip=f"{d:%b %d, %Y}: {p.display_value}")
        for (x, y), p, d in zip(coords, trend.points, local_dates)
    ]

    min_point = min(trend.points, key=lambda p: p.value)
    max_point = max(trend.points, key=lambda p: p.value)
    range_label = (
        min_point.display_value
        if min_point.value == max_point.value
        else f"{min_point.display_value} – {max_point.display_value}"
    )

    # Anchor the direct end-label near the line's actual endpoint (marks-and-anatomy.md:
    # "Lines -> value at the end") rather than a fixed slot, which would either float
    # disconnected from the mark or sit on top of it. Offset to whichever side of the
    # endpoint has clearance from the plot edge.
    _, last_y = coords[-1]
    end_label_y = last_y + 14 if last_y < _HEIGHT / 2 else last_y - 10

    return TrendChartView(
        width=_WIDTH,
        height=_HEIGHT,
        path_d=path_d,
        points=points,
        end_label=trend.points[-1].display_value,
        end_label_y=end_label_y,
        range_label=range_label,
        start_date=f"{local_dates[0]:%b %d}",
        end_date=f"{local_dates[-1]:%b %d}",
    )
