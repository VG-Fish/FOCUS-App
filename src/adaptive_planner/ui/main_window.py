"""Readable, keyboard-friendly PySide6 shell for the v0.1 planner."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFormLayout,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from adaptive_planner.application.planner import PlannerApp
from adaptive_planner.domain.types import PlannerPreferencesDocument
from adaptive_planner.platform.timezone import local_timezone_name
from adaptive_planner.ui.calendar_view import CalendarView
from adaptive_planner.ui.dialogs import (
    AreaDialog,
    BlockTimeDialog,
    EstimateDialog,
    EventDialog,
    HelpDialog,
    QuickCaptureDialog,
)


def _button(label: str, *, variant: str | None = None) -> QPushButton:
    button = QPushButton(label)
    if variant:
        button.setProperty("variant", variant)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class TaskRow(QFrame):
    selected = Signal(object)
    changed = Signal()

    def __init__(self, task, app: PlannerApp, parent=None) -> None:
        super().__init__(parent)
        self.task = task
        self.app = app
        self.setObjectName("taskCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 13, 15, 13)
        layout.setSpacing(10)

        summary = QHBoxLayout()
        summary.setSpacing(12)
        text_column = QVBoxLayout()
        text_column.setSpacing(3)
        title = QLabel(task.title)
        title.setObjectName("taskTitle")
        title.setWordWrap(True)
        text_column.addWidget(title)
        metadata = QLabel(self._metadata())
        metadata.setObjectName("taskMeta")
        metadata.setWordWrap(True)
        text_column.addWidget(metadata)
        summary.addLayout(text_column, 1)
        priority = QLabel(f"Priority {task.priority}")
        priority.setObjectName("priorityPill")
        priority.setAlignment(Qt.AlignmentFlag.AlignCenter)
        priority.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        summary.addWidget(priority, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(summary)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        action_hint = QLabel("Set estimate:" if task.estimated_remaining_minutes is None else "Add remaining:")
        action_hint.setObjectName("mutedText")
        actions.addWidget(action_hint)
        for label, delta in (("15m", 15), ("30m", 30), ("1h", 60)):
            estimate = _button(label)
            estimate.setToolTip(f"Add {label} to the remaining estimate")
            estimate.clicked.connect(lambda _checked=False, d=delta: self._adjust(d))
            actions.addWidget(estimate)
        set_estimate = _button("Set…")
        set_estimate.setToolTip("Set the exact remaining estimate")
        set_estimate.clicked.connect(self._set_estimate)
        actions.addWidget(set_estimate)
        actions.addStretch()
        defer = _button("Tomorrow")
        defer.setToolTip("Hide this task until this time tomorrow")
        defer.clicked.connect(self._defer)
        actions.addWidget(defer)
        done = _button("Done", variant="success")
        done.clicked.connect(self._complete)
        actions.addWidget(done)
        layout.addLayout(actions)

    def mousePressEvent(self, event) -> None:
        self.selected.emit(self.task)
        super().mousePressEvent(event)

    def _metadata(self) -> str:
        if self.task.estimated_remaining_minutes is None:
            parts = ["Needs an estimate"]
        elif self.task.estimated_remaining_minutes == 0:
            parts = ["0m remaining — mark complete or update remaining"]
        else:
            parts = [f"{self.task.estimated_remaining_minutes}m remaining"]
        if self.task.due_date:
            parts.append(f"due {self.task.due_date.strftime('%b %-d')}")
        elif self.task.due_at:
            parts.append(f"due {self.task.due_at.astimezone().strftime('%b %-d at %-I:%M %p')}")
        if self.task.earliest_start_at and self.task.earliest_start_at > datetime.now(timezone.utc):
            parts.append(f"deferred until {self.task.earliest_start_at.astimezone().strftime('%b %-d at %-I:%M %p')}")
        return "  •  ".join(parts)

    def _perform(self, operation) -> None:
        try:
            operation()
            self.changed.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Could not update task", str(exc))

    def _adjust(self, delta: int) -> None:
        value = (self.task.estimated_remaining_minutes or 0) + delta
        self._perform(lambda: self.app.adjust_remaining(self.task.id, value))

    def _set_estimate(self) -> None:
        dialog = EstimateDialog(self.task.estimated_remaining_minutes, self)
        if dialog.exec():
            self._perform(lambda: self.app.adjust_remaining(self.task.id, dialog.value))

    def _complete(self) -> None:
        self._perform(lambda: self.app.complete_task(self.task.id))

    def _defer(self) -> None:
        until = datetime.now(timezone.utc) + timedelta(days=1)
        self._perform(lambda: self.app.defer_task(self.task.id, until))


class MainWindow(QMainWindow):
    def __init__(self, planner: PlannerApp, tray=None) -> None:
        super().__init__()
        self.planner = planner
        self.tray = tray
        self.debug_enabled = False
        self._areas_by_id = {}
        self.setWindowTitle("Adaptive Planner")
        self.setMinimumSize(760, 560)
        self.resize(1080, 720)
        self._build_actions()
        self._build_ui()
        self.refresh()

    def _build_actions(self) -> None:
        menu = self.menuBar().addMenu("Planner")
        quick = QAction("Quick Capture", self)
        quick.setShortcut(QKeySequence("Meta+Shift+Space"))
        quick.triggered.connect(self.open_quick_capture)
        menu.addAction(quick)
        settings = QAction("Settings", self)
        settings.setShortcuts([QKeySequence("Meta+Shift+S"), QKeySequence("Ctrl+Shift+S")])
        settings.triggered.connect(self.show_settings)
        menu.addAction(settings)
        menu.addAction("Refresh", self.refresh)
        menu.addSeparator()
        quit_action = QAction("Quit", self)
        application = QApplication.instance()
        assert application is not None
        quit_action.triggered.connect(application.quit)
        menu.addAction(quit_action)
        # Command is owned by the menu action; Control is a development/Linux fallback.
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+Space"), self)
        shortcut.activated.connect(self.open_quick_capture)
        for sequence in ("Meta+Shift+D", "Ctrl+Shift+D"):
            debug_shortcut = QShortcut(QKeySequence(sequence), self)
            debug_shortcut.activated.connect(self.toggle_debug)
        help_menu = self.menuBar().addMenu("Help")
        help_action = QAction("Capabilities and Shortcuts", self)
        help_action.setShortcuts([QKeySequence("Meta+Shift+H"), QKeySequence("Ctrl+Shift+H")])
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)

    def _build_ui(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setExpanding(False)
        self.setCentralWidget(self.tabs)
        self.today_tab = self._build_today_tab()
        self.inbox_tab = self._build_inbox_tab()
        self.calendar_tab = self._build_calendar_tab()
        self.areas_tab = self._build_areas_tab()
        self.history_tab = self._build_history_tab()
        self.preferences_tab = self._build_preferences_tab()
        self.tabs.addTab(self.today_tab, "Today")
        self.tabs.addTab(self.inbox_tab, "Inbox")
        self.tabs.addTab(self.calendar_tab, "Calendar")
        self.tabs.addTab(self.areas_tab, "Areas")
        self.tabs.addTab(self.history_tab, "History")
        self.tabs.addTab(self.preferences_tab, "Settings")

        self.status = QLabel("Ready")
        self.statusBar().addPermanentWidget(self.status)
        self.debug_label = QLabel("DEBUG")
        self.debug_label.setStyleSheet("color: #b42318; font-weight: 700;")
        self.debug_label.hide()
        self.statusBar().addPermanentWidget(self.debug_label)
        self.debug_panel = QTextEdit()
        self.debug_panel.setReadOnly(True)
        self.debug_panel.setWindowTitle("Debug Inspector")
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._debug_dock())

    def _debug_dock(self):
        from PySide6.QtWidgets import QDockWidget

        dock = QDockWidget("Debug Inspector", self)
        dock.setWidget(self.debug_panel)
        dock.hide()
        self._debug_dock_widget = dock
        return dock

    @staticmethod
    def _page() -> tuple[QWidget, QVBoxLayout]:
        root = QWidget()
        root.setObjectName("page")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(14)
        return root, layout

    @staticmethod
    def _header(title: str, subtitle: str) -> tuple[QWidget, QHBoxLayout]:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(12)
        labels = QVBoxLayout()
        labels.setSpacing(2)
        page_title = QLabel(title)
        page_title.setObjectName("pageTitle")
        labels.addWidget(page_title)
        page_subtitle = QLabel(subtitle)
        page_subtitle.setObjectName("pageSubtitle")
        page_subtitle.setWordWrap(True)
        labels.addWidget(page_subtitle)
        layout.addLayout(labels, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        layout.addLayout(actions)
        return header, actions

    @staticmethod
    def _section_header(title: str) -> tuple[QWidget, QLabel]:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 2, 0, 0)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        layout.addWidget(label)
        layout.addStretch()
        metadata = QLabel()
        metadata.setObjectName("sectionMeta")
        layout.addWidget(metadata)
        return widget, metadata

    @staticmethod
    def _task_scroller() -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("scrollContents")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(9)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(content)
        return scroll, layout

    def _build_today_tab(self) -> QWidget:
        root, layout = self._page()
        header, actions = self._header("Today", "See what matters now and keep your plan honest.")
        block = _button("Block Time…")
        block.clicked.connect(self.block_time)
        actions.addWidget(block)
        capture = _button("Quick Capture", variant="primary")
        capture.clicked.connect(self.open_quick_capture)
        actions.addWidget(capture)
        layout.addWidget(header)

        self.health = QLabel()
        self.health.setObjectName("healthStrip")
        self.health.setWordWrap(True)
        layout.addWidget(self.health)

        next_card = QFrame()
        next_card.setObjectName("nextActionCard")
        next_layout = QVBoxLayout(next_card)
        next_layout.setContentsMargins(14, 11, 14, 12)
        next_layout.setSpacing(3)
        eyebrow = QLabel("NEXT ACTION")
        eyebrow.setObjectName("cardEyebrow")
        next_layout.addWidget(eyebrow)
        self.next_action = QLabel()
        self.next_action.setObjectName("nextActionTitle")
        self.next_action.setWordWrap(True)
        next_layout.addWidget(self.next_action)
        self.next_action_detail = QLabel()
        self.next_action_detail.setObjectName("mutedText")
        self.next_action_detail.setWordWrap(True)
        next_layout.addWidget(self.next_action_detail)
        layout.addWidget(next_card)

        section, self.today_count_label = self._section_header("Open tasks")
        layout.addWidget(section)
        scroll, self.today_tasks = self._task_scroller()
        layout.addWidget(scroll, 1)
        return root

    def _build_inbox_tab(self) -> QWidget:
        root, layout = self._page()
        header, actions = self._header("Inbox", "Estimate captured work so it can enter planning.")
        capture = _button("Quick Capture", variant="primary")
        capture.clicked.connect(self.open_quick_capture)
        actions.addWidget(capture)
        layout.addWidget(header)

        info = QFrame()
        info.setObjectName("infoCard")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(14, 11, 14, 11)
        info_layout.setSpacing(2)
        self.inbox_count_label = QLabel()
        self.inbox_count_label.setObjectName("sectionTitle")
        info_layout.addWidget(self.inbox_count_label)
        hint = QLabel("Use the fast estimate buttons on each task. No extra status change is required.")
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)
        info_layout.addWidget(hint)
        layout.addWidget(info)

        scroll, self.inbox_tasks = self._task_scroller()
        layout.addWidget(scroll, 1)
        return root

    def _build_calendar_tab(self) -> QWidget:
        root, layout = self._page()
        header, actions = self._header(
            "Calendar",
            "Review protected commitments by day, week, or month.",
        )
        self.edit_event_button = _button("Edit selected…")
        self.edit_event_button.setEnabled(False)
        self.edit_event_button.clicked.connect(self.edit_selected_event)
        actions.addWidget(self.edit_event_button)
        self.cancel_event_button = _button("Cancel selected", variant="danger")
        self.cancel_event_button.setEnabled(False)
        self.cancel_event_button.clicked.connect(self.cancel_selected_event)
        actions.addWidget(self.cancel_event_button)
        add = _button("Block Time…", variant="primary")
        add.clicked.connect(self.block_time)
        actions.addWidget(add)
        layout.addWidget(header)
        self.calendar = CalendarView()
        self.calendar.rangeChanged.connect(self._refresh_calendar)
        self.calendar.eventSelected.connect(self._calendar_event_selected)
        self.calendar.eventEditRequested.connect(self.edit_event)
        self.calendar.blockTimeRequested.connect(self.block_time_at)
        layout.addWidget(self.calendar, 1)
        return root

    def _build_areas_tab(self) -> QWidget:
        root, layout = self._page()
        header, actions = self._header("Areas", "Group obligations by course, project, work, or life area.")
        self.archive_area_button = _button("Archive", variant="danger")
        self.archive_area_button.setEnabled(False)
        self.archive_area_button.clicked.connect(self.archive_selected_area)
        actions.addWidget(self.archive_area_button)
        self.rename_area_button = _button("Rename")
        self.rename_area_button.setEnabled(False)
        self.rename_area_button.clicked.connect(self.rename_selected_area)
        actions.addWidget(self.rename_area_button)
        add = _button("New Area", variant="primary")
        add.clicked.connect(self.create_area)
        actions.addWidget(add)
        layout.addWidget(header)
        explanation = QLabel("“None” is the permanent fallback for uncategorized captures.")
        explanation.setObjectName("mutedText")
        layout.addWidget(explanation)
        self.areas_list = QListWidget()
        self.areas_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.areas_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.areas_list.currentItemChanged.connect(self._area_selection_changed)
        layout.addWidget(self.areas_list, 1)
        return root

    def _build_history_tab(self) -> QWidget:
        root, layout = self._page()
        header, actions = self._header(
            "History",
            "Review the durable local record of changes to tasks, events, Areas, and preferences.",
        )
        refresh = _button("Refresh")
        refresh.clicked.connect(self._refresh_history)
        actions.addWidget(refresh)
        layout.addWidget(header)
        self.history_count = QLabel()
        self.history_count.setObjectName("mutedText")
        layout.addWidget(self.history_count)

        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(("When", "Action", "Entity", "ID"))
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.verticalHeader().hide()
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.history_table.itemSelectionChanged.connect(self._history_selection_changed)
        layout.addWidget(self.history_table, 2)

        detail_label = QLabel("Change details")
        detail_label.setObjectName("sectionTitle")
        layout.addWidget(detail_label)
        self.history_detail = QTextEdit()
        self.history_detail.setReadOnly(True)
        self.history_detail.setPlaceholderText("Select a history entry to inspect its before and after values.")
        layout.addWidget(self.history_detail, 1)
        return root

    def _build_preferences_tab(self) -> QWidget:
        root, layout = self._page()
        header, _actions = self._header("Settings", "Set the defaults future scheduling will use.")
        layout.addWidget(header)

        row = QHBoxLayout()
        card = QWidget()
        card.setObjectName("settingsCard")
        card.setMaximumWidth(620)
        form = QFormLayout(card)
        form.setContentsMargins(20, 18, 20, 20)
        form.setHorizontalSpacing(22)
        form.setVerticalSpacing(13)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.timezone = QLabel()
        self.timezone.setObjectName("sectionTitle")
        self.use_local_timezone = QCheckBox("Use local timezone")
        self.use_local_timezone.setToolTip(
            "Use the timezone configured by macOS for Today, Calendar, pickers, and History."
        )
        self.default_block = QSpinBox()
        self.default_block.setRange(1, 24 * 60)
        self.default_block.setSuffix(" min")
        self.minimum_block = QSpinBox()
        self.minimum_block.setRange(1, 24 * 60)
        self.minimum_block.setSuffix(" min")
        self.maximum_block = QSpinBox()
        self.maximum_block.setRange(1, 24 * 60)
        self.maximum_block.setSuffix(" min")
        form.addRow("Timezone", self.timezone)
        form.addRow("Timezone mode", self.use_local_timezone)
        form.addRow("Default block", self.default_block)
        form.addRow("Minimum block", self.minimum_block)
        form.addRow("Maximum block", self.maximum_block)
        save = _button("Save preferences", variant="primary")
        save.clicked.connect(self.save_preferences)
        form.addRow("", save)
        note = QLabel("These values are stored now and will be consumed by the v0.2 scheduler.")
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        form.addRow("", note)
        row.addWidget(card, 1)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch()
        return root

    @staticmethod
    def _empty_state(title: str, body: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("emptyState")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("emptyTitle")
        layout.addWidget(title_label)
        body_label = QLabel(body)
        body_label.setObjectName("emptyBody")
        body_label.setWordWrap(True)
        layout.addWidget(body_label)
        return frame

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def refresh(self) -> None:
        try:
            today = self.planner.get_today()
            preferences = self.planner.get_preferences()
            schedulable = sum(1 for task in today.tasks if (task.estimated_remaining_minutes or 0) > 0)
            self.health.setText(
                f"{today.date.strftime('%A, %B %-d')}   •   {schedulable} ready to plan   •   "
                f"{today.inbox_count} need estimates   •   {len(today.events)} calendar events"
            )
            now = datetime.now(timezone.utc)
            next_task = next(
                (
                    task
                    for task in today.tasks
                    if (task.estimated_remaining_minutes or 0) > 0
                    and (task.earliest_start_at is None or task.earliest_start_at <= now)
                ),
                None,
            )
            if next_task:
                self.next_action.setText(next_task.title)
                details = [f"{next_task.estimated_remaining_minutes}m remaining", f"Priority {next_task.priority}"]
                if next_task.due_date:
                    details.insert(1, f"due {next_task.due_date.strftime('%b %-d')}")
                self.next_action_detail.setText("  •  ".join(details))
            else:
                self.next_action.setText("Capture something worth doing")
                self.next_action_detail.setText("Add an estimate to make a task ready for planning.")

            self.today_count_label.setText(f"{len(today.tasks)} total")
            self._populate_task_layout(
                self.today_tasks,
                today.tasks,
                "Your day is clear",
                "Use Quick Capture to add your first obligation. You can organize it later without losing it.",
            )
            inbox = tuple(task for task in today.tasks if task.estimated_remaining_minutes is None)
            noun = "task" if len(inbox) == 1 else "tasks"
            self.inbox_count_label.setText(f"{len(inbox)} {noun} need an estimate")
            self._populate_task_layout(
                self.inbox_tasks,
                inbox,
                "Inbox cleared",
                "Every open task has a remaining estimate and is ready for planning.",
            )

            self.calendar.set_timezone(preferences.timezone_name)
            self._refresh_calendar()

            self.areas_list.clear()
            areas = self.planner.list_areas()
            self._areas_by_id = {str(area.id): area for area in areas}
            for area in areas:
                suffix = "System fallback" if area.system_key else area.kind.value.title()
                item = QListWidgetItem(f"{area.name}\n{suffix}")
                item.setData(Qt.ItemDataRole.UserRole, str(area.id))
                self.areas_list.addItem(item)
            self._area_selection_changed(None, None)

            self.timezone.setText(preferences.timezone_name)
            self.use_local_timezone.setChecked(preferences.timezone_name == local_timezone_name())
            scheduling = preferences.scheduling
            self.default_block.setValue(int(scheduling.get("default_block_minutes", 60)))
            self.minimum_block.setValue(int(scheduling.get("minimum_block_minutes", 20)))
            self.maximum_block.setValue(int(scheduling.get("maximum_block_minutes", 90)))
            self._refresh_history(timezone_name=preferences.timezone_name)
            self.status.setText("Saved locally")
        except Exception as exc:
            self.status.setText(f"Error: {exc}")
            QMessageBox.warning(self, "Could not refresh planner", str(exc))

    def _populate_task_layout(self, layout, tasks, empty_title: str, empty_body: str) -> None:
        self._clear_layout(layout)
        if not tasks:
            layout.addWidget(self._empty_state(empty_title, empty_body))
            return
        for task in tasks:
            row = TaskRow(task, self.planner)
            row.changed.connect(self.refresh)
            row.selected.connect(self.inspect_task)
            layout.addWidget(row)

    def open_quick_capture(self) -> None:
        # Keep global capture compact when the main window is hidden in the
        # menu bar; a hidden/minimized parent can suppress its child dialog.
        parent = self if self.isVisible() and not self.isMinimized() else None
        preferences = self.planner.get_preferences()
        dialog = QuickCaptureDialog(
            self.planner.list_areas(),
            preferences.timezone_name,
            parent,
            create_area=self.planner.create_area,
        )
        accepted = bool(dialog.exec())
        if accepted:
            try:
                self.planner.create_task(dialog.value)
            except Exception as exc:
                QMessageBox.warning(self, "Could not capture", str(exc))
        if accepted or dialog.area_was_created:
            self.refresh()

    def create_area(self) -> None:
        dialog = AreaDialog(self)
        if dialog.exec():
            try:
                self.planner.create_area(dialog.value)
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Could not create Area", str(exc))

    def _selected_area(self):
        item = self.areas_list.currentItem()
        if item is None:
            return None
        return self._areas_by_id.get(item.data(Qt.ItemDataRole.UserRole))

    def _area_selection_changed(self, current, _previous) -> None:
        area = self._areas_by_id.get(current.data(Qt.ItemDataRole.UserRole)) if current else None
        editable = area is not None and area.system_key is None
        self.rename_area_button.setEnabled(editable)
        self.archive_area_button.setEnabled(editable)

    def rename_selected_area(self) -> None:
        area = self._selected_area()
        if area is None or area.system_key:
            return
        dialog = AreaDialog(self, title="Rename Area", initial_name=area.name)
        if dialog.exec():
            try:
                self.planner.rename_area(area.id, dialog.name.text())
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Could not rename Area", str(exc))

    def archive_selected_area(self) -> None:
        area = self._selected_area()
        if area is None or area.system_key:
            return
        tasks = tuple(task for task in self.planner.list_tasks() if task.area_id == area.id)
        if tasks:
            prompt = QMessageBox(self)
            prompt.setWindowTitle("Archive Area")
            prompt.setIcon(QMessageBox.Icon.Warning)
            prompt.setText(f"{area.name} contains {len(tasks)} incomplete task(s).")
            prompt.setInformativeText("Choose what should happen to those tasks before the Area is archived.")
            move = prompt.addButton("Move tasks to None", QMessageBox.ButtonRole.AcceptRole)
            archive = prompt.addButton("Archive tasks", QMessageBox.ButtonRole.DestructiveRole)
            prompt.addButton(QMessageBox.StandardButton.Cancel)
            prompt.exec()
            clicked = prompt.clickedButton()
            if clicked is move:
                destination = next(item for item in self._areas_by_id.values() if item.system_key == "UNCATEGORIZED")
                action, destination_id = "move_contents", destination.id
            elif clicked is archive:
                action, destination_id = "archive_contents", None
            else:
                return
        else:
            answer = QMessageBox.question(
                self,
                "Archive Area",
                f"Archive {area.name}? You can still inspect it through history.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            action, destination_id = "area_only", None
        try:
            self.planner.archive_area(area.id, action=action, destination_area_id=destination_id)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not archive Area", str(exc))

    def block_time(
        self,
        _checked: bool = False,
        *,
        initial_start: datetime | None = None,
        initial_end: datetime | None = None,
    ) -> None:
        preferences = self.planner.get_preferences()
        dialog = BlockTimeDialog(
            self,
            initial_start=initial_start,
            initial_end=initial_end,
            timezone_name=preferences.timezone_name,
        )
        if dialog.exec():
            try:
                title, start, end = dialog.values
                self.planner.block_time(title, start, end)
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Could not block time", str(exc))

    def block_time_at(self, start: datetime, end: datetime) -> None:
        self.block_time(initial_start=start, initial_end=end)

    def _refresh_calendar(self) -> None:
        try:
            start, end = self.calendar.visible_utc_range()
            # CalendarEvent all-day bounds are local dates, while timed query
            # bounds are UTC instants. A one-day pad safely covers every IANA
            # offset; CalendarView trims the result to the exact visible days.
            events = self.planner.list_events(
                start=start - timedelta(days=1),
                end=end + timedelta(days=1),
            )
            self.calendar.set_events(events)
        except Exception as exc:
            self.status.setText(f"Calendar error: {exc}")
            QMessageBox.warning(self, "Could not load calendar", str(exc))

    def _calendar_event_selected(self, event) -> None:
        self.edit_event_button.setEnabled(event is not None)
        self.cancel_event_button.setEnabled(event is not None)
        if event is not None:
            self.inspect_event(event)

    def edit_selected_event(self) -> None:
        event = self.calendar.selected_event
        if event is not None:
            self.edit_event(event)

    def edit_event(self, event) -> None:
        preferences = self.planner.get_preferences()
        dialog = EventDialog(
            event,
            self.planner.list_areas(),
            preferences.timezone_name,
            self,
        )
        if not dialog.exec():
            return
        try:
            updated = self.planner.update_event(event.id, dialog.value)
            self.inspect_event(updated)
            self.refresh()
            self.status.setText("Calendar event updated")
        except Exception as exc:
            QMessageBox.warning(self, "Could not update event", str(exc))

    def cancel_selected_event(self) -> None:
        event = self.calendar.selected_event
        if event is None:
            return
        if QMessageBox.question(
            self,
            "Cancel calendar event",
            f"Cancel “{event.title}”?\nThis remains in history.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            cancelled = self.planner.cancel_event(event.id)
            self.inspect_event(cancelled)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not cancel event", str(exc))

    def _refresh_history(self, _checked: bool = False, *, timezone_name: str | None = None) -> None:
        try:
            zone_name = timezone_name or self.planner.get_preferences().timezone_name
            events = self.planner.list_history(250)
            selected_id = None
            selected_items = self.history_table.selectedItems()
            if selected_items:
                selected_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
            self._history_by_id = {str(event.id): event for event in events}
            self.history_table.setRowCount(len(events))
            for row, event in enumerate(events):
                occurred = event.occurred_at.astimezone(ZoneInfo(zone_name))
                values = (
                    occurred.strftime("%b %-d, %Y  %-I:%M:%S %p"),
                    event.event_type.replace("_", " ").title(),
                    event.entity_type,
                    str(event.entity_id),
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.ItemDataRole.UserRole, str(event.id))
                    self.history_table.setItem(row, column, item)
                if str(event.id) == selected_id:
                    self.history_table.selectRow(row)
            noun = "entry" if len(events) == 1 else "entries"
            self.history_count.setText(f"Showing {len(events)} most recent {noun}")
            if not events:
                self.history_detail.clear()
        except Exception as exc:
            self.status.setText(f"History error: {exc}")

    def _history_selection_changed(self) -> None:
        items = self.history_table.selectedItems()
        if not items:
            return
        event = self._history_by_id.get(items[0].data(Qt.ItemDataRole.UserRole))
        if event is None:
            return
        payload = event.model_dump(mode="json")
        self.history_detail.setPlainText(json.dumps(payload, indent=2))

    def show_settings(self, _checked: bool = False) -> None:
        self.show()
        self.tabs.setCurrentWidget(self.preferences_tab)
        self.raise_()
        self.activateWindow()

    def show_help(self, _checked: bool = False) -> None:
        HelpDialog(self).exec()

    def save_preferences(self) -> None:
        if self.minimum_block.value() > self.maximum_block.value():
            QMessageBox.warning(self, "Invalid block sizes", "Maximum block size must be at least the minimum.")
            return
        try:
            current = self.planner.get_preferences()
            scheduling = dict(current.scheduling)
            scheduling.update(
                {
                    "default_block_minutes": self.default_block.value(),
                    "minimum_block_minutes": self.minimum_block.value(),
                    "maximum_block_minutes": self.maximum_block.value(),
                }
            )
            updated = current.model_copy(update={"scheduling": scheduling})
            timezone_name = local_timezone_name() if self.use_local_timezone.isChecked() else "UTC"
            updated = updated.model_copy(update={"timezone_name": timezone_name})
            self.planner.update_preferences(PlannerPreferencesDocument.model_validate(updated))
            self.refresh()
            self.status.setText("Preferences saved")
        except Exception as exc:
            QMessageBox.warning(self, "Could not save preferences", str(exc))

    def inspect_task(self, task) -> None:
        if not self.debug_enabled:
            return
        self.debug_panel.setPlainText(json.dumps(task.model_dump(mode="json"), indent=2))

    def inspect_event(self, event) -> None:
        if not self.debug_enabled:
            return
        self.debug_panel.setPlainText(json.dumps(event.model_dump(mode="json"), indent=2))

    def toggle_debug(self) -> None:
        self.debug_enabled = not self.debug_enabled
        self.debug_label.setVisible(self.debug_enabled)
        self._debug_dock_widget.setVisible(self.debug_enabled)
        if not self.debug_enabled:
            self.debug_panel.clear()

    def closeEvent(self, event) -> None:
        if self.tray is not None:
            event.ignore()
            self.hide()
            self.status.setText("Running in the menu bar")
            return
        super().closeEvent(event)
