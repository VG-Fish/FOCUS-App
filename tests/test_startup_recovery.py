from __future__ import annotations

import sqlite3

from adaptive_planner.application.planner import PlannerApp
from adaptive_planner.platform.recovery import StartupRecovery


def _sqlite_database(path, value: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES (?)", (value,))
        connection.commit()
    finally:
        connection.close()


def test_startup_recovery_detects_unclean_shutdown_and_cleans_marker(tmp_path) -> None:
    database = tmp_path / "planner.db"
    _sqlite_database(database, "current")
    recovery = StartupRecovery(database)

    first = recovery.begin()
    assert first.unclean_shutdown_detected is False
    assert first.integrity_error is None
    resumed_recovery = StartupRecovery(database)
    second = resumed_recovery.begin()
    assert second.unclean_shutdown_detected is True
    resumed_recovery.finish()
    assert not recovery.marker_path.exists()


def test_startup_recovery_restores_only_a_valid_rolling_backup(tmp_path) -> None:
    database = tmp_path / "planner.db"
    _sqlite_database(database, "current")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup = backup_dir / "planner.db.20260916T120000Z.bak"
    _sqlite_database(backup, "backup")
    recovery = StartupRecovery(database)

    quarantined = recovery.restore_backup(backup)

    assert quarantined is not None and quarantined.exists()
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("backup",)
    finally:
        connection.close()


def test_database_worker_can_create_a_consistent_backup(tmp_path) -> None:
    database = tmp_path / "planner.db"
    app = PlannerApp(database)
    try:
        backup = app.backup_now()
    finally:
        app.close()

    assert backup.parent == tmp_path / "backups"
    connection = sqlite3.connect(backup)
    try:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"areas", "tasks", "calendar_events", "history_events"} <= tables
    finally:
        connection.close()
