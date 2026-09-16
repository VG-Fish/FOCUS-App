"""Small single-instance guard shared by the macOS shell and tests."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QLockFile


class SingleInstance:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = QLockFile(str(path))
        self.lock.setStaleLockTime(10_000)

    def acquire(self) -> bool:
        return self.lock.tryLock(100)

    def release(self) -> None:
        self.lock.unlock()
