"""Operating-system timezone helpers."""

from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _valid_zone_name(candidate: str) -> str | None:
    candidate = candidate.strip()
    if candidate.startswith(":"):
        candidate = candidate[1:]
    if not candidate or candidate in {"UTC", "localtime"}:
        return "UTC" if candidate == "UTC" else None
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return None
    return candidate


def local_timezone_name() -> str:
    """Return the machine's local IANA timezone, with a safe UTC fallback."""

    configured = os.environ.get("TZ")
    if configured:
        found = _valid_zone_name(configured)
        if found:
            return found

    for path in (Path("/etc/localtime"), Path("/etc/timezone")):
        try:
            resolved = str(path.resolve()) if path.name == "localtime" else path.read_text().strip()
        except OSError:
            continue
        marker = "/zoneinfo/"
        if marker in resolved:
            resolved = resolved.split(marker, 1)[1]
        found = _valid_zone_name(resolved)
        if found:
            return found
    return "UTC"
