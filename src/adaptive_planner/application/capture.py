"""Deterministic, no-LLM Quick Capture parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from adaptive_planner.domain.types import DeadlineKind


@dataclass(frozen=True)
class CaptureFields:
    title: str
    area_name: str | None = None
    due_date: date | None = None
    estimate_minutes: int | None = None


_FIELD_RE = re.compile(r"^\s*(Due|Estimate|Area)\s*:\s*(.*?)\s*$", re.IGNORECASE)


def _parse_estimate(value: str) -> int | None:
    value = value.lower().replace(" ", "")
    hours = re.search(r"(\d+(?:\.\d+)?)h", value)
    minutes = re.search(r"(\d+)m", value)
    total = 0
    if hours:
        total += round(float(hours.group(1)) * 60)
    if minutes:
        total += int(minutes.group(1))
    if total <= 0:
        raise ValueError("Estimate must be a positive duration such as 30m or 2h")
    return total


def _next_weekday(value: str, today: date) -> date | None:
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    weekday = weekdays.get(value.lower().rstrip("."))
    if weekday is None:
        return None
    delta = (weekday - today.weekday()) % 7
    return today + timedelta(days=delta or 7)


def _parse_due(value: str, today: date) -> date:
    normalized = value.strip().lower()
    if normalized == "today":
        return today
    if normalized == "tomorrow":
        return today + timedelta(days=1)
    weekday = _next_weekday(normalized, today)
    if weekday:
        return weekday
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("Due must be today, tomorrow, a weekday, or YYYY-MM-DD") from exc


def parse_quick_capture(text: str, *, today: date) -> CaptureFields:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Capture cannot be empty")
    title_parts: list[str] = []
    area_name = None
    due_date = None
    estimate_minutes = None
    for line in lines:
        match = _FIELD_RE.match(line)
        if not match:
            title_parts.append(line)
            continue
        field, value = match.groups()
        if field.lower() == "area":
            area_name = value.strip() or None
        elif field.lower() == "due":
            due_date = _parse_due(value, today)
        else:
            estimate_minutes = _parse_estimate(value)
    title = " ".join(title_parts).strip()
    if not title:
        raise ValueError("Capture needs a title")
    return CaptureFields(title, area_name, due_date, estimate_minutes)
