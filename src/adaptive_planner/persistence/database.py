"""Single-owner SQLite runtime and dedicated database worker."""

from __future__ import annotations

import queue
import shutil
import sqlite3
import threading
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar, cast

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

T = TypeVar("T")


@event.listens_for(Engine, "connect")
def _set_sqlite_contract(dbapi_connection: sqlite3.Connection, _connection_record: object) -> None:
    """Apply the runtime SQLite contract to every connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.close()


class DatabaseWorker:
    """Owns the only SQLAlchemy engine, sessions, and ORM objects in the app."""

    def __init__(self, db_path: Path, project_root: Path | None = None, backup_count: int = 5) -> None:
        self.db_path = db_path.expanduser().resolve()
        self.project_root = (project_root or Path(__file__).resolve().parents[3]).resolve()
        self.backup_count = backup_count
        self._jobs: queue.Queue[tuple[Callable[[Session], Any] | None, Future[Any]]] = queue.Queue()
        self._ready: Future[None] = Future()
        self._thread = threading.Thread(target=self._run, name="adaptive-planner-db", daemon=True)
        self._thread.start()
        self._ready.result()

    def _run(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._backup_before_migration()
            engine = create_engine(
                f"sqlite:///{self.db_path}",
                future=True,
                connect_args={"check_same_thread": True},
            )
            with engine.begin() as connection:
                config = Config(str(self.project_root / "alembic.ini"))
                config.set_main_option("script_location", str(self.project_root / "migrations"))
                config.set_main_option("prepend_sys_path", str(self.project_root))
                config.attributes["connection"] = connection
                command.upgrade(config, "head")

            session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
            self._ready.set_result(None)
            while True:
                callback, future = self._jobs.get()
                if callback is None:
                    future.set_result(None)
                    break
                session = session_factory()
                try:
                    result = callback(session)
                    session.commit()
                    future.set_result(result)
                except BaseException as exc:
                    session.rollback()
                    future.set_exception(exc)
                finally:
                    session.close()
            engine.dispose()
        except BaseException as exc:
            if not self._ready.done():
                self._ready.set_exception(exc)

    def _backup_before_migration(self) -> None:
        if not self.db_path.exists() or self.db_path.stat().st_size == 0:
            return
        source = sqlite3.connect(self.db_path)
        try:
            self._backup_connection(source)
        finally:
            source.close()

    def _backup_connection(self, source: sqlite3.Connection) -> Path:
        backup_dir = self.db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ%f")
        destination = backup_dir / f"{self.db_path.name}.{stamp}.bak"
        temporary = destination.with_suffix(".tmp")
        target = sqlite3.connect(temporary)
        try:
            source.backup(target)
        finally:
            target.close()
        temporary.replace(destination)
        backups = sorted(
            backup_dir.glob(f"{self.db_path.name}.*.bak"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[self.backup_count :]:
            old_backup.unlink(missing_ok=True)
        return destination

    def backup_now(self) -> Path:
        """Create a consistent SQLite backup through the database worker."""

        def backup(session: Session) -> Path:
            session.flush()
            raw_connection = session.connection().connection
            # SQLAlchemy 2 exposes a ConnectionFairy here; its driver
            # connection is the sqlite3.Connection that owns the WAL state.
            source = getattr(raw_connection, "driver_connection", raw_connection)
            if not isinstance(source, sqlite3.Connection):
                raise RuntimeError("the active database connection is not SQLite")
            return self._backup_connection(source)

        return self.call(backup)

    def call(self, callback: Callable[[Session], T]) -> T:
        if not self._thread.is_alive():
            raise RuntimeError("database worker is not running")
        future: Future[Any] = Future()
        self._jobs.put((callback, future))
        return cast(T, future.result())

    def close(self) -> None:
        if self._thread.is_alive():
            future: Future[Any] = Future()
            self._jobs.put((None, future))
            future.result(timeout=5)
            self._thread.join(timeout=5)


Database = DatabaseWorker
