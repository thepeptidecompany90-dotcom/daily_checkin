from datetime import datetime, timedelta
from uuid import UUID

from glp1_agent.db.repositories.observation_repo import ObservationRepo
from glp1_agent.domain.models import (
    CheckinObservation,
    ClinicianInstruction,
    MetricTrend,
    MetricTrendPoint,
    MetricType,
    ObservationValueLabel,
    TrackingItem,
    TrackingItemKind,
)

_PROTEIN_KEYWORDS = frozenset(
    {
        "chicken",
        "turkey",
        "fish",
        "salmon",
        "tuna",
        "egg",
        "eggs",
        "yogurt",
        "greek yogurt",
        "cottage cheese",
        "cheese",
        "milk",
        "protein shake",
        "protein powder",
        "beans",
        "lentils",
        "chickpeas",
        "tofu",
        "nuts",
        "peanut butter",
        "steak",
        "beef",
        "pork",
        "bacon",
        "sausage",
    }
)

_ORDINAL_SCORES = {
    ObservationValueLabel.LOW: 1,
    ObservationValueLabel.NORMAL: 2,
    ObservationValueLabel.HIGH: 3,
    ObservationValueLabel.ADEQUATE: 2,
}


def ordinal_score(value_label: ObservationValueLabel) -> int:
    """Backend-only numeric mapping for trend purposes, derived at read time rather than
    stored (docs/domain-model.md §4.1: store facts, derive metrics)."""
    return _ORDINAL_SCORES[value_label]


def classify_protein_description(raw_food_description: str | None) -> ObservationValueLabel | None:
    """Deterministic keyword heuristic — never delegated to the LLM.

    Returns None if no food was mentioned at all; callers must treat that as "do not
    record" rather than as a value to store.
    """
    if not raw_food_description or not raw_food_description.strip():
        return None
    lowered = raw_food_description.lower()
    has_protein_source = any(keyword in lowered for keyword in _PROTEIN_KEYWORDS)
    return ObservationValueLabel.ADEQUATE if has_protein_source else ObservationValueLabel.LOW


def build_metric_trends(observations: list[CheckinObservation]) -> list[MetricTrend]:
    """One chronological series per MetricType, for dashboard trend charts.

    NOT_REPORTED observations carry no plottable value and are dropped. WEIGHT plots
    its raw value_numeric; the other metrics plot their ordinal_score, since LOW/
    NORMAL/HIGH/ADEQUATE aren't otherwise comparable.
    """
    by_metric: dict[MetricType, list[CheckinObservation]] = {metric: [] for metric in MetricType}
    for obs in observations:
        if obs.value_label is ObservationValueLabel.NOT_REPORTED:
            continue
        by_metric[obs.observation_type].append(obs)

    trends = []
    for metric in MetricType:
        rows = sorted(by_metric[metric], key=lambda o: o.created_at)
        points = [
            MetricTrendPoint(
                created_at=o.created_at,
                value=o.value_numeric if metric is MetricType.WEIGHT else ordinal_score(o.value_label),
                display_value=(
                    f"{o.value_numeric:g}{o.unit}"
                    if metric is MetricType.WEIGHT
                    else o.value_label.value.title()
                ),
            )
            for o in rows
        ]
        trends.append(MetricTrend(metric=metric, points=points))
    return trends


def resolve_metric_frequencies(
    defaults: dict[MetricType, int], overrides: dict[MetricType, int]
) -> dict[MetricType, int]:
    """Per-patient overrides win; metrics without an override keep the global default."""
    return {**defaults, **overrides}


def select_due_metric(
    now: datetime,
    last_observed: dict[MetricType, datetime],
    frequencies: dict[MetricType, int],
) -> MetricType | None:
    """The single most-overdue metric, or None if nothing is due.

    A metric never observed before is treated as maximally overdue. Ties are broken by
    MetricType declaration order (MOOD, WEIGHT, SLEEP, HYDRATION, PROTEIN).
    """
    best_metric: MetricType | None = None
    best_overdue_by: timedelta | None = None
    for metric in MetricType:
        frequency_days = frequencies.get(metric)
        if frequency_days is None:
            continue
        last = last_observed.get(metric)
        overdue_by = timedelta.max if last is None else (now - last) - timedelta(days=frequency_days)
        is_due = overdue_by >= timedelta(0)
        if is_due and (best_overdue_by is None or overdue_by > best_overdue_by):
            best_metric, best_overdue_by = metric, overdue_by
    return best_metric


def build_tracking_items(
    clinician_instructions: list[ClinicianInstruction],
    due_metric: MetricType | None,
) -> list[TrackingItem]:
    """Clinician-directed tracking outranks routine metric rotation (voice-agent-kb.md
    §13). Preserves clinician-instruction order; the due metric, if any, is appended last.
    """
    items = [
        TrackingItem(
            kind=TrackingItemKind.CLINICIAN_INSTRUCTION,
            label=ci.metric,
            instruction=ci.instruction,
            tracking_id=ci.tracking_id,
        )
        for ci in clinician_instructions
    ]
    if due_metric is not None:
        items.append(
            TrackingItem(kind=TrackingItemKind.DUE_METRIC, label=due_metric.value, metric=due_metric)
        )
    return items


def tracking_item_key(item: TrackingItem) -> str:
    """Stable identity for a tracking item within a single call, used to track which
    items have a recorded outcome so far — shared by flows/nodes.py and tools/functions.py
    so the key format can't drift between the two."""
    if item.kind is TrackingItemKind.DUE_METRIC:
        return f"metric:{item.metric.value}"
    return f"instruction:{item.tracking_id}"


class ObservationService:
    def __init__(self, observation_repo: ObservationRepo):
        self._observations = observation_repo

    async def record_observation(
        self,
        patient_id: UUID,
        checkin_id: UUID | None,
        observation_type: MetricType,
        value_label: ObservationValueLabel | None = None,
        value_numeric: float | None = None,
        raw_food_description: str | None = None,
    ) -> CheckinObservation:
        unit = None
        if observation_type is MetricType.PROTEIN:
            if not raw_food_description:
                raise ValueError("raw_food_description is required for PROTEIN observations")
            value_label = classify_protein_description(raw_food_description)
            if value_label is None:
                raise ValueError("raw_food_description did not mention any food — do not record")
            value_numeric = None
        elif observation_type is MetricType.WEIGHT:
            if value_numeric is None:
                raise ValueError("value_numeric is required for WEIGHT observations")
            value_label = None
            unit = "lbs"
        else:  # MOOD, SLEEP, HYDRATION
            if value_label is None:
                raise ValueError(f"value_label is required for {observation_type} observations")
            value_numeric = None

        return await self._observations.create(
            patient_id=patient_id,
            checkin_id=checkin_id,
            observation_type=observation_type,
            value_label=value_label,
            value_numeric=value_numeric,
            unit=unit,
            confidence=None,
        )

    async def record_skipped(
        self,
        patient_id: UUID,
        checkin_id: UUID | None,
        observation_type: MetricType,
    ) -> CheckinObservation:
        """Durable "asked, patient declined/no answer" outcome — bypasses the per-type
        required-field validation in record_observation entirely, since NOT_REPORTED is
        valid for every metric type and needs none of those fields."""
        return await self._observations.create(
            patient_id=patient_id,
            checkin_id=checkin_id,
            observation_type=observation_type,
            value_label=ObservationValueLabel.NOT_REPORTED,
            value_numeric=None,
            unit=None,
            confidence=None,
        )
