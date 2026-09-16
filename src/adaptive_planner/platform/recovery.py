"""Conservative startup/crash recovery for the local SQLite database."""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class StartupCheck:
    unclean_shutdown_detected: bool
    integrity_error: str | None
    latest_backup: Path | None


class StartupRecovery:
    """Detect interrupted runs and validate before the application opens SQLite."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.expanduser().resolve()
        self.marker_path = self.database_path.with_name("adaptive-planner.running")
        self._begun = False

    def begin(self) -> StartupCheck:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        unclean = self.marker_path.exists()
        integrity_error = self._integrity_error(self.database_path)
        latest_backup = self.latest_backup()
        marker = (
            f"pid={os.getpid()}\n"
            f"started_at={datetime.now(timezone.utc).isoformat()}\n"
        )
        temporary = self.marker_path.with_suffix(".running.tmp")
        temporary.write_text(marker, encoding="utf-8")
        os.replace(temporary, self.marker_path)
        self._begun = True
        return StartupCheck(unclean, integrity_error, latest_backup)

    def finish(self) -> None:
        if self._begun:
            self.marker_path.unlink(missing_ok=True)
            self._begun = False

    def latest_backup(self) -> Path | None:
        backup_dir = self.database_path.parent / "backups"
        backups = sorted(
            backup_dir.glob(f"{self.database_path.name}.*.bak"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return backups[0] if backups else None

    def restore_backup(self, backup: Path) -> Path | None:
        """Restore a validated backup, quarantining the current DB first."""

        backup = backup.expanduser().resolve()
        expected_parent = (self.database_path.parent / "backups").resolve()
        if backup.parent != expected_parent or not backup.is_file():
            raise ValueError("backup is not one of Adaptive Planner's rolling backups")
        error = self._integrity_error(backup)
        if error is not None:
            raise ValueError(f"backup failed SQLite integrity check: {error}")

        quarantined: Path | None = None
        if self.database_path.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            quarantined = self.database_path.with_name(
                f"{self.database_path.name}.corrupt.{stamp}"
            )
            shutil.copy2(self.database_path, quarantined)

        temporary = self.database_path.with_suffix(".restore.tmp")
        shutil.copy2(backup, temporary)
        os.replace(temporary, self.database_path)
        # WAL/SHM files belong to the replaced database and must not be replayed
        # into the restored copy.
        Path(f"{self.database_path}-wal").unlink(missing_ok=True)
        Path(f"{self.database_path}-shm").unlink(missing_ok=True)
        restored_error = self._integrity_error(self.database_path)
        if restored_error is not None:
            raise RuntimeError(f"restored database failed integrity check: {restored_error}")
        return quarantined

    @staticmethod
    def _integrity_error(path: Path) -> str | None:
        if not path.exists() or path.stat().st_size == 0:
            return None
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                result = connection.execute("PRAGMA quick_check").fetchone()
            finally:
                connection.close()
        except sqlite3.DatabaseError as exc:
            return str(exc)
        if result is None or result[0] != "ok":
            return str(result[0] if result else "SQLite returned no integrity result")
        return None
