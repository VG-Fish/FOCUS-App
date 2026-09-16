from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from adaptive_planner.ui.components import DurationInput


def test_duration_accepts_hours_minutes_and_seconds_together(qtbot) -> None:
    duration = DurationInput(None)
    qtbot.addWidget(duration)

    duration.hours_input.setValue(1)
    duration.minutes_input.setValue(32)
    duration.seconds_input.setValue(56)

    assert duration.seconds == (60 * 60) + (32 * 60) + 56


def test_duration_decomposes_stored_seconds_into_all_fields(qtbot) -> None:
    duration = DurationInput((60 * 60) + (32 * 60) + 56)
    qtbot.addWidget(duration)

    assert duration.hours_input.value() == 1
    assert duration.minutes_input.value() == 32
    assert duration.seconds_input.value() == 56
    assert duration.seconds == (60 * 60) + (32 * 60) + 56


def test_duration_exposes_enabled_week_and_day_fields_together(qtbot) -> None:
    expected = (1 * 5 * 8 * 60 * 60) + (2 * 8 * 60 * 60) + (3 * 60 * 60) + (4 * 60) + 5
    duration = DurationInput(expected, max_unit="Weeks")
    qtbot.addWidget(duration)

    assert duration.weeks_input.value() == 1
    assert duration.days_input.value() == 2
    assert duration.hours_input.value() == 3
    assert duration.minutes_input.value() == 4
    assert duration.seconds_input.value() == 5
    assert duration.seconds == expected
