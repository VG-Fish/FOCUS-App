"""Application entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from adaptive_planner.application.planner import PlannerApp
from adaptive_planner.platform.macos.instance import SingleInstance
from adaptive_planner.platform.macos.global_shortcut import GlobalQuickCaptureShortcut
from adaptive_planner.ui.main_window import MainWindow
from adaptive_planner.ui.styles import STYLESHEET, light_palette


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Adaptive Planner v0.1")
    parser.add_argument("--db", type=Path, help="Path to planner.db (useful for development and backups)")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setApplicationName("Adaptive Planner")
    app.setOrganizationName("Adaptive Planner")
    # Do not inherit dark-mode text colors onto the app's light surfaces.
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setStyleSheet(STYLESHEET)

    database_path = args.db or Path.home() / "Library" / "Application Support" / "Adaptive Planner" / "planner.db"
    instance = SingleInstance(database_path.with_name("adaptive-planner.lock"))
    if not instance.acquire():
        return 2
    planner = PlannerApp(database_path)
    window = MainWindow(planner)
    global_capture = GlobalQuickCaptureShortcut(window.open_quick_capture)
    global_capture.register()

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(window)
        tray.setToolTip("Adaptive Planner")
        menu = QMenu()
        show = menu.addAction("Open Today")
        show.triggered.connect(lambda: (window.show(), window.raise_(), window.activateWindow()))
        capture = menu.addAction("Quick Capture")
        capture.triggered.connect(window.open_quick_capture)
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(app.quit)
        tray.setContextMenu(menu)
        tray.show()
        window.tray = tray

    def cleanup() -> None:
        global_capture.unregister()
        planner.close()
        instance.release()

    app.aboutToQuit.connect(cleanup)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
