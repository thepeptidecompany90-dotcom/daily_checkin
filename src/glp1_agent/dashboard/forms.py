"""Parsing/formatting for the "next dose at" <input type=datetime-local> field.

Kept separate from formatting.py because these two functions are a matched pair: dt_input_value
renders the current value into the field, resolve_next_dose_at parses whatever comes back.
"""

from datetime import datetime
from zoneinfo import ZoneInfo


def dt_input_value(value: datetime | None, timezone: str) -> str:
    if value is None:
        return ""
    return value.astimezone(ZoneInfo(timezone)).strftime("%Y-%m-%dT%H:%M")


def resolve_next_dose_at(raw: str, existing: datetime | None, timezone: str) -> datetime | None:
    """An empty submitted value means "left untouched", not "clear it" — a blank
    datetime-local input is exactly what a browser sends when the field was never edited."""
    if not raw:
        return existing
    return datetime.fromisoformat(raw).replace(tzinfo=ZoneInfo(timezone))
