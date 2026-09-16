from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from adaptive_planner.application.planner import PlannerApp
from adaptive_planner.domain.types import AreaCreate, TaskCreate
from adaptive_planner.ui.main_window import MainWindow, TaskRow


def _visible_task_titles(window: MainWindow) -> list[str]:
    titles: list[str] = []
    for index in range(window.inbox_tasks.count()):
        item = window.inbox_tasks.itemAt(index)
        if item is None:
            continue
        widget = item.widget()
        if isinstance(widget, TaskRow):
            titles.append(widget.task.title)
    return titles


def test_tasks_tab_searches_and_filters_all_open_tasks(qtbot, tmp_path) -> None:
    planner = PlannerApp(tmp_path / "planner.db")
    area = planner.create_area(AreaCreate(name="Work"))
    none_area = next(item for item in planner.list_areas() if item.system_key == "UNCATEGORIZED")
    planner.create_task(TaskCreate(area_id=none_area.id, title="Unestimated errand"))
    planner.create_task(
        TaskCreate(area_id=area.id, title="Write status report", estimated_remaining_seconds=45 * 60)
    )

    window = MainWindow(planner)
    qtbot.addWidget(window)
    try:
        assert window.tabs.tabText(1) == "Tasks"
        assert "2 open" in window.task_summary.text()
        assert _visible_task_titles(window) == ["Unestimated errand", "Write status report"]

        window.task_filter_bar.filter.setCurrentIndex(
            window.task_filter_bar.filter.findData("needs_estimate")
        )
        assert window.task_results_count.text() == "Showing 1 of 2"
        assert _visible_task_titles(window) == ["Unestimated errand"]

        window.task_filter_bar.filter.setCurrentIndex(window.task_filter_bar.filter.findData("all"))
        window.task_filter_bar.search.setText("work")
        assert _visible_task_titles(window) == ["Write status report"]
    finally:
        window.close()
        planner.close()
