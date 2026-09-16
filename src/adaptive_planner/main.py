"""Application entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QStyle, QSystemTrayIcon

from adaptive_planner.application.planner import PlannerApp
from adaptive_planner.platform.macos.instance import SingleInstance
from adaptive_planner.platform.macos.global_shortcut import GlobalQuickCaptureShortcut
from adaptive_planner.platform.recovery import StartupRecovery
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
    recovery = StartupRecovery(database_path)
    startup = recovery.begin()
    if startup.integrity_error is not None:
        message = QMessageBox()
        message.setIcon(QMessageBox.Icon.Critical)
        message.setWindowTitle("Planner database needs recovery")
        message.setText("Adaptive Planner could not safely open planner.db.")
        message.setInformativeText(
            f"SQLite reported: {startup.integrity_error}\n\n"
            "The current database will never be overwritten without your confirmation."
        )
        restore_button = None
        if startup.latest_backup is not None:
            restore_button = message.addButton(
                "Restore latest backup",
                QMessageBox.ButtonRole.AcceptRole,
            )
        message.addButton("Quit", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        if restore_button is None or message.clickedButton() is not restore_button:
            recovery.finish()
            instance.release()
            return 1
        try:
            assert startup.latest_backup is not None
            recovery.restore_backup(startup.latest_backup)
        except Exception as exc:
            QMessageBox.critical(None, "Recovery failed", str(exc))
            recovery.finish()
            instance.release()
            return 1

    try:
        planner = PlannerApp(database_path)
    except Exception as exc:
        QMessageBox.critical(None, "Adaptive Planner could not start", str(exc))
        recovery.finish()
        instance.release()
        return 1
    window = MainWindow(planner)
    application_icon = app.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
    app.setWindowIcon(application_icon)
    window.setWindowIcon(application_icon)
    global_capture = GlobalQuickCaptureShortcut(window.open_quick_capture)
    global_capture.register()

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(window)
        tray.setIcon(application_icon)
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
        recovery.finish()
        instance.release()

    app.aboutToQuit.connect(cleanup)
    window.show()
    if startup.unclean_shutdown_detected:
        window.status.setText("Recovered after an interrupted shutdown; database integrity passed")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
