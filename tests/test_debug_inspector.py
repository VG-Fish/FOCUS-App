from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QPushButton

from adaptive_planner.application.planner import PlannerApp
from adaptive_planner.domain.types import TaskCreate
from adaptive_planner.ui.main_window import MainWindow


def test_debug_json_inspector_is_read_only_and_has_no_apply_control(qtbot, tmp_path) -> None:
    planner = PlannerApp(tmp_path / "planner.db")
    area = planner.list_areas()[0]
    task = planner.create_task(TaskCreate(area_id=area.id, title="Keep this title"))
    window = MainWindow(planner)
    qtbot.addWidget(window)
    try:
        window.toggle_debug()
        window.inspect_task(task)

        assert window.debug_panel.isReadOnly()
        assert all(
            button.text() != "Apply debug changes"
            for button in window._debug_dock_widget.findChildren(QPushButton)
        )

        # The inactive mutation path is guarded as well as absent from the UI.
        window.debug_panel.setPlainText('{"title": "Changed through debug"}')
        window.apply_debug_changes()
        assert planner.inspect_task(task.id).title == "Keep this title"
        assert window.status.text() == "Debug JSON editing is temporarily disabled"
    finally:
        window.close()
        planner.close()
