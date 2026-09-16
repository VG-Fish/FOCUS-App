"""Optional native macOS global shortcut for Quick Capture.

The Qt shortcut remains useful when running without the macOS bridge (for
example, in headless tests). On macOS this listens for Command+Shift+Space
while the app is running in the menu bar.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:  # pragma: no cover - AppKit is only available on macOS
    import AppKit
except ImportError:  # pragma: no cover - exercised on non-macOS CI
    AppKit = None


class GlobalQuickCaptureShortcut:
    def __init__(self, callback: Callable[[], None]) -> None:
        self.callback = callback
        self._monitor: object | None = None
        self._handler: Callable[[Any], None] | None = None

    @property
    def available(self) -> bool:
        return AppKit is not None

    def register(self) -> bool:
        if AppKit is None or self._monitor is not None:
            return False
        event_class = getattr(AppKit, "NSEvent", None)
        if event_class is None:
            return False
        key_down = getattr(AppKit, "NSEventMaskKeyDown", 1 << 10)
        command = getattr(AppKit, "NSEventModifierFlagCommand", 1 << 20)
        shift = getattr(AppKit, "NSEventModifierFlagShift", 1 << 17)

        def handler(event: Any) -> None:
            if event.keyCode() == 49 and (event.modifierFlags() & command) and (event.modifierFlags() & shift):
                self.callback()

        self._handler = handler
        self._monitor = event_class.addGlobalMonitorForEventsMatchingMask_handler_(key_down, handler)
        return self._monitor is not None

    def unregister(self) -> None:
        if AppKit is not None and self._monitor is not None:
            event_class = getattr(AppKit, "NSEvent", None)
            if event_class is not None:
                event_class.removeMonitor_(self._monitor)
        self._monitor = None
        self._handler = None
