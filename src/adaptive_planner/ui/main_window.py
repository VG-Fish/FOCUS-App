"""Readable, keyboard-friendly PySide6 shell for the v0.1 planner."""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
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
from adaptive_planner.domain.types import CalendarEventUpdate, PlannerPreferencesDocument
from adaptive_planner.ui.calendar_view import CalendarView
from adaptive_planner.ui.components import TaskFilterBar, TimezoneComboBox
from adaptive_planner.ui.dialogs import (
    ArchiveAreaDialog,
    AreaDialog,
    BlockTimeDialog,
    DeferTaskDialog,
    EstimateDialog,
    EventDialog,
    HelpDialog,
    QuickCaptureDialog,
    TaskDialog,
)
from adaptive_planner.ui.pickers import TimePickerButton


DEBUG_JSON_EDITING_ENABLED = False


def _button(label: str, *, variant: str | None = None) -> QPushButton:
    button = QPushButton(label)
    if variant:
        button.setProperty("variant", variant)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "Needs an estimate"
    if seconds == 0:
        return "0s"
    parts: list[str] = []
    for suffix, size in (("wk", 5 * 8 * 3600), ("d", 8 * 3600), ("h", 3600), ("m", 60), ("s", 1)):
        amount, seconds = divmod(seconds, size)
        if amount:
            parts.append(f"{amount}{suffix}")
    return " ".join(parts)


class TaskRow(QFrame):
    selected = Signal(object)
    changed = Signal()

    def __init__(
        self,
        task,
        app: PlannerApp,
        parent=None,
        *,
        area_name: str | None = None,
        timezone_name: str = "UTC",
        max_estimate_unit: str = "Hours",
        edit_callback=None,
    ) -> None:
        super().__init__(parent)
        self.task = task
        self.app = app
        self.area_name = area_name
        self.zone = ZoneInfo(timezone_name)
        self.max_estimate_unit = max_estimate_unit
        self.edit_callback = edit_callback
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
        if task.archived_at is not None:
            state = QLabel("Archived")
            state.setObjectName("mutedText")
            actions.addWidget(state)
            actions.addStretch()
            restore = _button("Restore")
            restore.clicked.connect(self._restore)
            actions.addWidget(restore)
        elif task.completed_at is not None:
            state = QLabel("Completed")
            state.setObjectName("mutedText")
            actions.addWidget(state)
            edit = _button("Edit…")
            edit.clicked.connect(lambda: self.edit_callback(self.task) if self.edit_callback else None)
            actions.addWidget(edit)
            actions.addStretch()
            reopen = _button("Reopen")
            reopen.clicked.connect(self._reopen)
            actions.addWidget(reopen)
            archive = _button("Archive")
            archive.clicked.connect(self._archive)
            actions.addWidget(archive)
        else:
            action_hint = QLabel("Set estimate:" if task.estimated_remaining_seconds is None else "Add remaining:")
            action_hint.setObjectName("mutedText")
            actions.addWidget(action_hint)
            presets = [("15m", 15), ("30m", 30), ("1h", 60)]
            if task.estimated_remaining_seconds is None:
                presets.extend((("2h", 120), ("4h", 240)))
            for label, delta in presets:
                estimate = _button(label)
                verb = "Set the estimate to" if task.estimated_remaining_seconds is None else "Add"
                estimate.setToolTip(f"{verb} {label}")
                estimate.clicked.connect(lambda _checked=False, d=delta: self._adjust(d))
                actions.addWidget(estimate)
            set_estimate = _button("Custom…" if task.estimated_remaining_seconds is None else "Set…")
            set_estimate.setToolTip("Set the exact remaining estimate")
            set_estimate.clicked.connect(self._set_estimate)
            actions.addWidget(set_estimate)
            edit = _button("Edit…")
            edit.setToolTip("Edit all task and planning attributes")
            edit.clicked.connect(lambda: self.edit_callback(self.task) if self.edit_callback else None)
            actions.addWidget(edit)
            actions.addStretch()
            defer = _button("Defer…")
            defer.setToolTip("Choose when this task becomes available again")
            defer.clicked.connect(self._defer)
            actions.addWidget(defer)
            archive = _button("Archive")
            archive.clicked.connect(self._archive)
            actions.addWidget(archive)
            done = _button("Done", variant="success")
            done.clicked.connect(self._complete)
            actions.addWidget(done)
        layout.addLayout(actions)

    def mousePressEvent(self, event) -> None:
        self.selected.emit(self.task)
        super().mousePressEvent(event)

    def _metadata(self) -> str:
        if self.task.estimated_remaining_seconds is None:
            parts = ["Needs an estimate"]
        elif self.task.estimated_remaining_seconds == 0:
            parts = ["0s remaining — mark complete or update remaining"]
        else:
            parts = [f"{_format_duration(self.task.estimated_remaining_seconds)} remaining"]
        if self.area_name:
            parts.insert(0, self.area_name)
        if self.task.archived_at is not None:
            parts.insert(0, "Archived")
        elif self.task.completed_at is not None:
            parts.insert(0, "Completed")
        if self.task.due_date:
            parts.append(f"due {self.task.due_date.strftime('%b %-d')}")
        elif self.task.due_at:
            parts.append(f"due {self.task.due_at.astimezone(self.zone).strftime('%b %-d at %-I:%M %p')}")
        if self.task.earliest_start_at and self.task.earliest_start_at > datetime.now(timezone.utc):
            parts.append(
                f"deferred until {self.task.earliest_start_at.astimezone(self.zone).strftime('%b %-d at %-I:%M %p')}"
            )
        return "  •  ".join(parts)

    def _perform(self, operation) -> None:
        try:
            operation()
            self.changed.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Could not update task", str(exc))

    def _adjust(self, delta: int) -> None:
        value = (self.task.estimated_remaining_seconds or 0) + delta * 60
        self._perform(lambda: self.app.adjust_remaining_seconds(self.task.id, value))

    def _set_estimate(self) -> None:
        dialog = EstimateDialog(self.task.estimated_remaining_seconds, self, max_unit=self.max_estimate_unit)
        if dialog.exec():
            self._perform(lambda: self.app.adjust_remaining_seconds(self.task.id, dialog.value))

    def _complete(self) -> None:
        self._perform(lambda: self.app.complete_task(self.task.id))

    def _defer(self) -> None:
        dialog = DeferTaskDialog(
            self.zone.key,
            self.task.earliest_start_at,
            self,
        )
        if dialog.exec():
            self._perform(lambda: self.app.defer_task(self.task.id, dialog.value))

    def _archive(self) -> None:
        if QMessageBox.question(
            self,
            "Archive task",
            f"Archive “{self.task.title}”? You can restore it from the Archived filter.",
        ) == QMessageBox.StandardButton.Yes:
            self._perform(lambda: self.app.archive_task(self.task.id))

    def _restore(self) -> None:
        self._perform(lambda: self.app.restore_task(self.task.id))

    def _reopen(self) -> None:
        self._perform(lambda: self.app.reopen_task(self.task.id))


class MainWindow(QMainWindow):
    def __init__(self, planner: PlannerApp, tray=None) -> None:
        super().__init__()
        self.planner = planner
        self.tray = tray
        self.debug_enabled = False
        self._areas_by_id = {}
        self._task_area_names: dict[object, str] = {}
        self._open_tasks = ()
        self._timezone_name = "UTC"
        self._task_filter_now = datetime.now(timezone.utc)
        self._task_filter_today = self._task_filter_now.date()
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
        self.tabs.addTab(self.inbox_tab, "Tasks")
        self.tabs.addTab(self.calendar_tab, "Calendar")
        self.tabs.addTab(self.areas_tab, "Areas")
        self.tabs.addTab(self.history_tab, "History")
        self.tabs.addTab(self.preferences_tab, "Settings")
        self.tabs.currentChanged.connect(self._debug_tab_changed)

        self.status = QLabel("Ready")
        self.statusBar().addPermanentWidget(self.status)
        self.debug_label = QLabel("DEBUG")
        self.debug_label.setStyleSheet("color: #b42318; font-weight: 700;")
        self.debug_label.hide()
        self.statusBar().addPermanentWidget(self.debug_label)
        self.debug_panel = QTextEdit()
        self.debug_panel.setReadOnly(not DEBUG_JSON_EDITING_ENABLED)
        self.debug_panel.setPlaceholderText("Select a task, Area, or event to inspect its read-only JSON.")
        if DEBUG_JSON_EDITING_ENABLED:
            self.debug_panel.textChanged.connect(self._clear_debug_error)
        self.debug_entity: tuple[str, UUID | None] | None = None
        self.debug_panel.setWindowTitle("Debug Inspector")
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._debug_dock())

    def _debug_dock(self):
        from PySide6.QtWidgets import QDockWidget

        dock = QDockWidget("Debug Inspector", self)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 8, 8, 8)
        if not DEBUG_JSON_EDITING_ENABLED:
            notice = QLabel("JSON editing is temporarily disabled. You can still select and copy inspector data.")
            notice.setObjectName("mutedText")
            notice.setWordWrap(True)
            body_layout.addWidget(notice)
        body_layout.addWidget(self.debug_panel, 1)
        self.debug_error = QLabel()
        self.debug_error.setObjectName("debugError")
        self.debug_error.setWordWrap(True)
        self.debug_error.hide()
        body_layout.addWidget(self.debug_error)
        copy_button = _button("Copy debug snapshot")
        copy_button.clicked.connect(self.copy_debug_snapshot)
        body_layout.addWidget(copy_button)
        if DEBUG_JSON_EDITING_ENABLED:
            apply_button = _button("Apply debug changes", variant="primary")
            apply_button.clicked.connect(self.apply_debug_changes)
            body_layout.addWidget(apply_button)
        dock.setWidget(body)
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
        self.triage_estimates = _button("Triage tasks needing estimates…")
        self.triage_estimates.clicked.connect(self._show_needs_estimate)
        layout.addWidget(self.triage_estimates, 0, Qt.AlignmentFlag.AlignLeft)

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
        header, actions = self._header("Tasks", "Find, triage, and update every open task.")
        capture = _button("Quick Capture", variant="primary")
        capture.clicked.connect(self.open_quick_capture)
        actions.addWidget(capture)
        layout.addWidget(header)

        info = QFrame()
        info.setObjectName("infoCard")
        info_layout = QHBoxLayout(info)
        info_layout.setContentsMargins(14, 11, 14, 11)
        info_layout.setSpacing(10)
        self.task_summary = QLabel()
        self.task_summary.setObjectName("taskSummary")
        self.task_summary.setWordWrap(True)
        info_layout.addWidget(self.task_summary, 1)
        layout.addWidget(info)

        self.task_filter_bar = TaskFilterBar()
        self.task_filter_bar.changed.connect(self._refresh_task_browser)
        layout.addWidget(self.task_filter_bar)

        section, self.task_results_count = self._section_header("Open tasks")
        layout.addWidget(section)
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
        self.archive_event_button = _button("Archive selected")
        self.archive_event_button.setEnabled(False)
        self.archive_event_button.clicked.connect(self.archive_selected_event)
        actions.addWidget(self.archive_event_button)
        self.restore_event_button = _button("Restore selected")
        self.restore_event_button.setEnabled(False)
        self.restore_event_button.clicked.connect(self.restore_selected_event)
        actions.addWidget(self.restore_event_button)
        add = _button("Block Time…", variant="primary")
        add.clicked.connect(self.block_time)
        actions.addWidget(add)
        self.show_archived_events = QCheckBox("Show archived")
        self.show_archived_events.setToolTip("Include archived work blocks so they can be restored")
        self.show_archived_events.toggled.connect(lambda _checked: self._refresh_calendar())
        actions.addWidget(self.show_archived_events)
        layout.addWidget(header)
        self.calendar = CalendarView()
        self.calendar.rangeChanged.connect(self._refresh_calendar)
        self.calendar.eventSelected.connect(self._calendar_event_selected)
        self.calendar.eventEditRequested.connect(self.edit_event)
        self.calendar.eventMoveRequested.connect(self.move_event)
        self.calendar.eventResizeRequested.connect(self.resize_event)
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
        self.restore_area_button = _button("Restore")
        self.restore_area_button.setEnabled(False)
        self.restore_area_button.clicked.connect(self.restore_selected_area)
        actions.addWidget(self.restore_area_button)
        self.rename_area_button = _button("Edit selected…")
        self.rename_area_button.setEnabled(False)
        self.rename_area_button.clicked.connect(self.rename_selected_area)
        actions.addWidget(self.rename_area_button)
        add = _button("New Area", variant="primary")
        add.clicked.connect(self.create_area)
        actions.addWidget(add)
        layout.addWidget(header)
        filter_row = QWidget()
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        explanation = QLabel("“None” is the permanent fallback for uncategorized captures.")
        explanation.setObjectName("mutedText")
        filter_layout.addWidget(explanation)
        filter_layout.addStretch()
        self.show_archived_areas = QCheckBox("Show archived")
        self.show_archived_areas.setToolTip("Include archived Areas in the table so they can be reviewed or restored.")
        self.show_archived_areas.toggled.connect(lambda _checked: self.refresh())
        filter_layout.addWidget(self.show_archived_areas)
        layout.addWidget(filter_row)
        self.areas_list = QTableWidget(0, 5)
        self.areas_list.setHorizontalHeaderLabels(("Area", "Type", "After due date", "Status", ""))
        self.areas_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.areas_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.areas_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.areas_list.verticalHeader().hide()
        self.areas_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.areas_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.areas_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.areas_list.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        # QTableWidget::item padding is not included when Qt measures a cell
        # widget. Reserve the action column explicitly so styled buttons do not
        # lose their first/last character at different font scales.
        self.areas_list.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.areas_list.setColumnWidth(4, 90)
        self.areas_list.itemSelectionChanged.connect(self._area_selection_changed)
        self.areas_list.cellDoubleClicked.connect(lambda _row, _column: self.rename_selected_area())
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
        self.timezone = TimezoneComboBox()
        self.default_block = QSpinBox()
        self.default_block.setRange(1, 24 * 60)
        self.default_block.setSuffix(" min")
        self.minimum_block = QSpinBox()
        self.minimum_block.setRange(1, 24 * 60)
        self.minimum_block.setSuffix(" min")
        self.maximum_block = QSpinBox()
        self.maximum_block.setRange(1, 24 * 60)
        self.maximum_block.setSuffix(" min")
        self.before_event_buffer = QSpinBox()
        self.before_event_buffer.setRange(0, 240)
        self.before_event_buffer.setSuffix(" min")
        self.after_event_buffer = QSpinBox()
        self.after_event_buffer.setRange(0, 240)
        self.after_event_buffer.setSuffix(" min")
        self.deadline_cutoff = TimePickerButton(time(hour=23, minute=59))
        self.estimate_max_unit = QComboBox()
        self.estimate_max_unit.addItem("Hours, minutes, and seconds", "Hours")
        self.estimate_max_unit.addItem("Also allow days", "Days")
        self.estimate_max_unit.addItem("Also allow days and weeks", "Weeks")
        form.addRow("Timezone", self.timezone)
        form.addRow("Default block", self.default_block)
        form.addRow("Minimum block", self.minimum_block)
        form.addRow("Maximum block", self.maximum_block)
        form.addRow("Before-event buffer", self.before_event_buffer)
        form.addRow("After-event buffer", self.after_event_buffer)
        form.addRow("Date-only deadline cutoff", self.deadline_cutoff)
        form.addRow("Task estimate units", self.estimate_max_unit)
        actions = QHBoxLayout()
        save = _button("Save preferences", variant="primary")
        save.clicked.connect(self.save_preferences)
        actions.addWidget(save)
        backup = _button("Back Up Now")
        backup.setToolTip("Create a consistent SQLite backup in the app's backups folder")
        backup.clicked.connect(self.backup_now)
        actions.addWidget(backup)
        actions.addStretch()
        form.addRow("", actions)
        self.backup_status = QLabel()
        self.backup_status.setObjectName("mutedText")
        self.backup_status.setWordWrap(True)
        form.addRow("Backups", self.backup_status)
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
            self._timezone_name = preferences.timezone_name
            active_areas = self.planner.list_areas()
            all_areas = self.planner.list_areas(include_archived=True)
            self._task_area_names = {area.id: area.name for area in all_areas}
            all_tasks = self.planner.list_tasks(include_archived=True, include_completed=True)
            schedulable = sum(1 for task in today.tasks if (task.estimated_remaining_seconds or 0) > 0)
            self.health.setText(
                f"{today.date.strftime('%A, %B %-d')}   •   {schedulable} ready to plan   •   "
                f"{today.inbox_count} need estimates   •   {len(today.events)} calendar events"
            )
            self.triage_estimates.setText(
                f"Triage {today.inbox_count} task{'s' if today.inbox_count != 1 else ''} needing estimates…"
            )
            self.triage_estimates.setVisible(today.inbox_count > 0)
            now = datetime.now(timezone.utc)
            next_task = next(
                (
                    task
                    for task in today.tasks
                    if (task.estimated_remaining_seconds or 0) > 0
                    and (task.earliest_start_at is None or task.earliest_start_at <= now)
                ),
                None,
            )
            if next_task:
                self.next_action.setText(next_task.title)
                details = [f"{_format_duration(next_task.estimated_remaining_seconds)} remaining", f"Priority {next_task.priority}"]
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
            self._open_tasks = all_tasks
            self._task_filter_now = now
            self._task_filter_today = now.astimezone(ZoneInfo(preferences.timezone_name)).date()
            filter_counts = self._task_filter_counts(all_tasks)
            self.task_filter_bar.set_counts(filter_counts)
            if filter_counts["all"]:
                self.task_summary.setText(
                    f"{filter_counts['all']} open   •   {filter_counts['needs_estimate']} need an estimate   •   "
                    f"{filter_counts['ready']} ready to plan   •   {filter_counts['completed']} completed   •   "
                    f"{filter_counts['archived']} archived"
                )
            else:
                self.task_summary.setText("No open tasks — use Quick Capture when something new comes up.")
            self._refresh_task_browser()

            self.calendar.set_timezone(preferences.timezone_name)
            self._refresh_calendar()

            selected_area = self._selected_area()
            selected_area_id = str(selected_area.id) if selected_area else None
            self.areas_list.setRowCount(0)
            areas = (
                self.planner.list_areas(include_archived=True)
                if self.show_archived_areas.isChecked()
                else active_areas
            )
            self._areas_by_id = {str(area.id): area for area in areas}
            policy_labels = {
                "ASK": "Ask me",
                "ALLOW": "Allow after due date",
                "FORBID": "Never after due date",
            }
            self.areas_list.setRowCount(len(areas))
            area_action_width = 90
            for row, area in enumerate(areas):
                name = QTableWidgetItem(area.name)
                name.setData(Qt.ItemDataRole.UserRole, str(area.id))
                self.areas_list.setItem(row, 0, name)
                kind = "System fallback" if area.system_key else area.kind.value.title()
                self.areas_list.setItem(row, 1, QTableWidgetItem(kind))
                policy = "—" if area.system_key else policy_labels[area.default_post_due_policy.value]
                self.areas_list.setItem(row, 2, QTableWidgetItem(policy))
                self.areas_list.setItem(row, 3, QTableWidgetItem("Archived" if area.archived_at else "Active"))
                if area.system_key is None:
                    if area.archived_at:
                        action = _button("Restore")
                        action.clicked.connect(lambda _checked=False, selected=area: self.restore_area(selected))
                    else:
                        action = _button("Edit…")
                        action.clicked.connect(lambda _checked=False, selected=area: self.edit_area(selected))
                    self.areas_list.setCellWidget(row, 4, action)
                    # The table style adds 8 px of padding on each side of the
                    # cell widget, plus a border. Qt's ResizeToContents mode
                    # does not account for that inset.
                    area_action_width = max(area_action_width, action.sizeHint().width() + 18)
                if str(area.id) == selected_area_id:
                    self.areas_list.selectRow(row)
            self.areas_list.setColumnWidth(4, area_action_width)
            self.areas_list.resizeRowsToContents()
            self._area_selection_changed()

            self.timezone.set_timezone(preferences.timezone_name)
            scheduling = preferences.scheduling
            self.default_block.setValue(int(scheduling.get("default_block_minutes", 60)))
            self.minimum_block.setValue(int(scheduling.get("minimum_block_minutes", 20)))
            self.maximum_block.setValue(int(scheduling.get("maximum_block_minutes", 90)))
            self.before_event_buffer.setValue(int(scheduling.get("before_event_buffer_minutes", 10)))
            self.after_event_buffer.setValue(int(scheduling.get("after_event_buffer_minutes", 10)))
            cutoff_hour, cutoff_minute = (
                int(part) for part in str(scheduling.get("date_only_deadline_cutoff", "23:59")).split(":", 1)
            )
            self.deadline_cutoff.set_value(time(cutoff_hour, cutoff_minute))
            estimate_unit = str(scheduling.get("estimate_max_unit", "Hours"))
            index = self.estimate_max_unit.findData(estimate_unit)
            fallback = self.estimate_max_unit.findData("Hours")
            self.estimate_max_unit.setCurrentIndex(index if index >= 0 else fallback)
            self._refresh_history(timezone_name=preferences.timezone_name)
            self._refresh_debug_entity(preferences)
            backup_dir = self.planner.database.db_path.parent / "backups"
            backups = sorted(
                backup_dir.glob(f"{self.planner.database.db_path.name}.*.bak"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            self.backup_status.setText(f"Latest: {backups[0].name}" if backups else "No backup created yet.")
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
            row = TaskRow(
                task,
                self.planner,
                area_name=self._task_area_names.get(task.area_id),
                timezone_name=self._timezone_name,
                max_estimate_unit=self._estimate_max_unit(),
                edit_callback=self.edit_task,
            )
            row.changed.connect(self.refresh)
            row.selected.connect(self.inspect_task)
            layout.addWidget(row)

    def _task_is_due_soon(self, task) -> bool:
        horizon = self._task_filter_now + timedelta(days=7)
        if task.due_at is not None:
            return task.due_at <= horizon
        if task.due_date is not None:
            return task.due_date <= self._task_filter_today + timedelta(days=7)
        return False

    def _task_filter_counts(self, tasks) -> dict[str, int]:
        open_tasks = tuple(
            task for task in tasks if task.completed_at is None and task.archived_at is None
        )
        return {
            "all": len(open_tasks),
            "needs_estimate": sum(task.estimated_remaining_seconds is None for task in open_tasks),
            "ready": sum((task.estimated_remaining_seconds or 0) > 0 for task in open_tasks),
            "zero_remaining": sum(task.estimated_remaining_seconds == 0 for task in open_tasks),
            "deferred": sum(
                task.earliest_start_at is not None and task.earliest_start_at > self._task_filter_now
                for task in open_tasks
            ),
            "due_soon": sum(self._task_is_due_soon(task) for task in open_tasks),
            "no_deadline": sum(task.due_date is None and task.due_at is None for task in open_tasks),
            "completed": sum(task.completed_at is not None and task.archived_at is None for task in tasks),
            "archived": sum(task.archived_at is not None for task in tasks),
        }

    def _task_matches_browser(self, task) -> bool:
        query = self.task_filter_bar.query
        if query:
            area_name = self._task_area_names.get(task.area_id, "")
            searchable = (task.title, task.description or "", area_name)
            if not any(query in value.casefold() for value in searchable):
                return False

        key = self.task_filter_bar.filter_key
        if key == "completed":
            return task.completed_at is not None and task.archived_at is None
        if key == "archived":
            return task.archived_at is not None
        if task.completed_at is not None or task.archived_at is not None:
            return False
        if key == "needs_estimate":
            return task.estimated_remaining_seconds is None
        if key == "ready":
            return (task.estimated_remaining_seconds or 0) > 0
        if key == "zero_remaining":
            return task.estimated_remaining_seconds == 0
        if key == "deferred":
            return task.earliest_start_at is not None and task.earliest_start_at > self._task_filter_now
        if key == "due_soon":
            return self._task_is_due_soon(task)
        if key == "no_deadline":
            return task.due_date is None and task.due_at is None
        return True

    def _refresh_task_browser(self) -> None:
        if not hasattr(self, "task_filter_bar"):
            return
        matches = tuple(task for task in self._open_tasks if self._task_matches_browser(task))
        total = len(self._open_tasks)
        self.task_results_count.setText(f"Showing {len(matches)} of {total}")
        if not total:
            empty_title = "No open tasks"
            empty_body = "Use Quick Capture to add an obligation when something new comes up."
        else:
            empty_title = "No matching tasks"
            empty_body = "Try a different search or filter."
        self._populate_task_layout(self.inbox_tasks, matches, empty_title, empty_body)

    def _show_needs_estimate(self) -> None:
        self.tabs.setCurrentWidget(self.inbox_tab)
        index = self.task_filter_bar.filter.findData("needs_estimate")
        if index >= 0:
            self.task_filter_bar.filter.setCurrentIndex(index)
        self.task_filter_bar.search.setFocus()

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
            max_estimate_unit=self._estimate_max_unit(),
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
        row = self.areas_list.currentRow()
        item = self.areas_list.item(row, 0) if row >= 0 else None
        if item is None:
            return None
        return self._areas_by_id.get(item.data(Qt.ItemDataRole.UserRole))

    def _area_selection_changed(self) -> None:
        area = self._selected_area()
        editable = area is not None and area.system_key is None
        self.rename_area_button.setEnabled(editable)
        self.archive_area_button.setEnabled(editable and area.archived_at is None)
        self.restore_area_button.setEnabled(editable and area.archived_at is not None)
        self.inspect_area(area)

    def edit_task(self, task) -> None:
        preferences = self.planner.get_preferences()
        areas = list(self.planner.list_areas())
        if not any(area.id == task.area_id for area in areas):
            archived_area = next(
                (
                    area
                    for area in self.planner.list_areas(include_archived=True)
                    if area.id == task.area_id
                ),
                None,
            )
            if archived_area is not None:
                areas.append(archived_area)
        dialog = TaskDialog(
            task,
            tuple(areas),
            preferences.timezone_name,
            self,
            max_unit=self._estimate_max_unit(),
        )
        if not dialog.exec():
            return
        try:
            updated = self.planner.update_task(task.id, dialog.value)
            self.inspect_task(updated)
            self.refresh()
            self.status.setText("Task updated")
        except Exception as exc:
            QMessageBox.warning(self, "Could not update task", str(exc))

    def rename_selected_area(self) -> None:
        area = self._selected_area()
        if area is None or area.system_key:
            return
        self.edit_area(area)

    def edit_area(self, area) -> None:
        if area is None or area.system_key:
            return
        dialog = AreaDialog(
            self,
            title="Edit Area",
            initial_name=area.name,
            initial_kind=area.kind,
            initial_policy=area.default_post_due_policy,
        )
        if dialog.exec():
            try:
                self.planner.update_area(area.id, dialog.value)
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Could not rename Area", str(exc))

    def archive_selected_area(self) -> None:
        area = self._selected_area()
        if area is None or area.system_key or area.archived_at is not None:
            return
        tasks = tuple(task for task in self.planner.list_tasks() if task.area_id == area.id)
        if tasks:
            destinations = tuple(item for item in self.planner.list_areas() if item.id != area.id)
            dialog = ArchiveAreaDialog(area, len(tasks), destinations, self)
            if not dialog.exec():
                return
            action, destination_id = dialog.value
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

    def restore_selected_area(self) -> None:
        self.restore_area(self._selected_area())

    def restore_area(self, area) -> None:
        if area is None or area.system_key or area.archived_at is None:
            return
        answer = QMessageBox.question(
            self,
            "Restore Area",
            f"Restore {area.name}?\n\n"
            "It will be available for tasks again. Tasks previously moved or archived will not be restored automatically.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            restored = self.planner.restore_area(area.id)
            self.refresh()
            self.inspect_area(restored)
            self.status.setText(f"Restored Area: {restored.name}")
        except Exception as exc:
            QMessageBox.warning(self, "Could not restore Area", str(exc))

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

    def move_event(self, event, start: datetime, end: datetime) -> None:
        self._update_event_range(event, start, end, action="Moved")

    def resize_event(self, event, start: datetime, end: datetime) -> None:
        self._update_event_range(event, start, end, action="Resized")

    def _update_event_range(self, event, start: datetime, end: datetime, *, action: str) -> None:
        try:
            updated = self.planner.update_event(
                event.id,
                CalendarEventUpdate(start_at=start, end_at=end),
            )
            self.refresh()
            self.inspect_event(updated)
            if updated.start_at is not None:
                zone = ZoneInfo(self.planner.get_preferences().timezone_name)
                local_start = updated.start_at.astimezone(zone)
                local_end = updated.end_at.astimezone(zone) if updated.end_at is not None else None
                suffix = local_start.strftime("%b %-d at %-I:%M %p")
                if action == "Resized" and local_end is not None:
                    suffix = f"{local_start.strftime('%b %-d, %-I:%M %p')} – {local_end.strftime('%-I:%M %p')}"
                self.status.setText(f"{action} {updated.title}: {suffix}")
        except Exception as exc:
            self.refresh()
            QMessageBox.warning(self, f"Could not {action.casefold()} event", str(exc))

    def _refresh_calendar(self) -> None:
        try:
            start, end = self.calendar.visible_utc_range()
            # CalendarEvent all-day bounds are local dates, while timed query
            # bounds are UTC instants. A one-day pad safely covers every IANA
            # offset; CalendarView trims the result to the exact visible days.
            events = self.planner.list_events(
                start=start - timedelta(days=1),
                end=end + timedelta(days=1),
                include_archived=self.show_archived_events.isChecked(),
            )
            self.calendar.set_events(events)
        except Exception as exc:
            self.status.setText(f"Calendar error: {exc}")
            QMessageBox.warning(self, "Could not load calendar", str(exc))

    def _calendar_event_selected(self, event) -> None:
        active = event is not None and event.cancelled_at is None and event.archived_at is None
        archived = event is not None and event.cancelled_at is None and event.archived_at is not None
        self.edit_event_button.setEnabled(active)
        self.cancel_event_button.setEnabled(active)
        self.archive_event_button.setEnabled(active)
        self.restore_event_button.setEnabled(archived)
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

    def archive_selected_event(self) -> None:
        event = self.calendar.selected_event
        if event is None or event.cancelled_at is not None or event.archived_at is not None:
            return
        answer = QMessageBox.question(
            self,
            "Archive calendar block",
            f"Archive “{event.title}”?\n\nIt will leave the active calendar and remain available under Show archived.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            archived = self.planner.archive_event(event.id)
            self.inspect_event(archived)
            self.refresh()
            self.status.setText(f"Archived calendar block: {archived.title}")
        except Exception as exc:
            QMessageBox.warning(self, "Could not archive event", str(exc))

    def restore_selected_event(self) -> None:
        event = self.calendar.selected_event
        if event is None or event.archived_at is None:
            return
        try:
            restored = self.planner.restore_event(event.id)
            self.inspect_event(restored)
            self.refresh()
            self.status.setText(f"Restored calendar block: {restored.title}")
        except Exception as exc:
            QMessageBox.warning(self, "Could not restore event", str(exc))

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
            self.history_count.setText(
                f"Showing {len(events)} most recent {noun}  •  Times shown in {zone_name}"
            )
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
        if not self.minimum_block.value() <= self.default_block.value() <= self.maximum_block.value():
            QMessageBox.warning(
                self,
                "Invalid block sizes",
                "Default block size must be between the minimum and maximum.",
            )
            return
        try:
            current = self.planner.get_preferences()
            scheduling = dict(current.scheduling)
            scheduling.update(
                {
                    "default_block_minutes": self.default_block.value(),
                    "minimum_block_minutes": self.minimum_block.value(),
                    "maximum_block_minutes": self.maximum_block.value(),
                    "before_event_buffer_minutes": self.before_event_buffer.value(),
                    "after_event_buffer_minutes": self.after_event_buffer.value(),
                    "date_only_deadline_cutoff": self.deadline_cutoff.value.strftime("%H:%M"),
                    "estimate_max_unit": self.estimate_max_unit.currentData(),
                }
            )
            updated = current.model_copy(update={"scheduling": scheduling})
            timezone_name = self.timezone.timezone_name()
            updated = updated.model_copy(update={"timezone_name": timezone_name})
            self.planner.update_preferences(PlannerPreferencesDocument.model_validate(updated))
            self.refresh()
            self.status.setText("Preferences saved")
        except Exception as exc:
            QMessageBox.warning(self, "Could not save preferences", str(exc))

    def backup_now(self) -> None:
        try:
            destination = self.planner.backup_now()
            self.backup_status.setText(f"Latest: {destination.name}")
            self.status.setText(f"Backup created: {destination.name}")
        except Exception as exc:
            QMessageBox.warning(self, "Could not create backup", str(exc))

    def inspect_task(self, task) -> None:
        if not self.debug_enabled or task is None:
            return
        self.debug_entity = ("task", task.id)
        self.debug_panel.setPlainText(json.dumps(task.model_dump(mode="json"), indent=2))

    def inspect_event(self, event) -> None:
        if not self.debug_enabled or event is None:
            return
        self.debug_entity = ("event", event.id)
        self.debug_panel.setPlainText(json.dumps(event.model_dump(mode="json"), indent=2))

    def inspect_area(self, area) -> None:
        if not self.debug_enabled or area is None:
            return
        self.debug_entity = ("area", area.id)
        self.debug_panel.setPlainText(json.dumps(area.model_dump(mode="json"), indent=2))

    def inspect_preferences(self, preferences=None) -> None:
        if not self.debug_enabled:
            return
        document = preferences or self.planner.get_preferences()
        self.debug_entity = ("preferences", None)
        self.debug_panel.setPlainText(json.dumps(document.model_dump(mode="json"), indent=2))

    def copy_debug_snapshot(self) -> None:
        text = self.debug_panel.toPlainText()
        if not text:
            self.status.setText("Select something to copy from Debug Inspector")
            return
        QApplication.clipboard().setText(text)
        self.status.setText("Debug snapshot copied")

    def _refresh_debug_entity(self, preferences=None) -> None:
        if not self.debug_enabled or self.debug_entity is None:
            return
        entity_type, entity_id = self.debug_entity
        try:
            if entity_type == "task":
                assert entity_id is not None
                self.inspect_task(self.planner.inspect_task(entity_id))
            elif entity_type == "event":
                assert entity_id is not None
                self.inspect_event(self.planner.inspect_event(entity_id))
            elif entity_type == "area":
                area = next(
                    (
                        item
                        for item in self.planner.list_areas(include_archived=True)
                        if item.id == entity_id
                    ),
                    None,
                )
                self.inspect_area(area)
            elif entity_type == "preferences":
                self.inspect_preferences(preferences)
        except ValueError:
            self.debug_panel.clear()
            self.debug_entity = None

    def _debug_tab_changed(self, _index: int) -> None:
        if not self.debug_enabled:
            return
        if self.tabs.currentWidget() is self.areas_tab:
            self.inspect_area(self._selected_area())
        elif self.tabs.currentWidget() is self.calendar_tab:
            self.inspect_event(self.calendar.selected_event)
        elif self.tabs.currentWidget() is self.preferences_tab:
            self.inspect_preferences()

    def apply_debug_changes(self) -> None:
        if not DEBUG_JSON_EDITING_ENABLED:
            self.status.setText("Debug JSON editing is temporarily disabled")
            return
        if self.debug_entity is None:
            self._show_debug_error("Select a task, Area, or event before applying changes.")
            return
        try:
            payload = json.loads(self.debug_panel.toPlainText())
        except json.JSONDecodeError as exc:
            self._show_debug_error(f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")
            cursor = self.debug_panel.textCursor()
            cursor.setPosition(min(exc.pos, len(self.debug_panel.toPlainText())))
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
            self.debug_panel.setTextCursor(cursor)
            self.debug_panel.setFocus()
            self.status.setText("Debug changes rejected: invalid JSON")
            return
        if not isinstance(payload, dict):
            self._show_debug_error("The debug document must be a JSON object enclosed in { }.")
            self.status.setText("Debug changes rejected: expected a JSON object")
            return
        try:
            entity_type, entity_id = self.debug_entity
            if entity_type == "task":
                from adaptive_planner.domain.types import TaskUpdate

                allowed = set(TaskUpdate.model_fields)
                self.planner.update_task(entity_id, TaskUpdate.model_validate({key: value for key, value in payload.items() if key in allowed}))
            elif entity_type == "event":
                from adaptive_planner.domain.types import CalendarEventUpdate

                allowed = set(CalendarEventUpdate.model_fields)
                self.planner.update_event(entity_id, CalendarEventUpdate.model_validate({key: value for key, value in payload.items() if key in allowed}))
            elif entity_type == "area":
                from adaptive_planner.domain.types import AreaCreate

                self.planner.update_area(entity_id, AreaCreate.model_validate({key: payload[key] for key in ("name", "kind", "default_post_due_policy")}))
            self.refresh()
            self._clear_debug_error()
            self.status.setText("Debug changes applied")
        except Exception as exc:
            self._show_debug_error(f"Changes rejected: {exc}")
            self.status.setText("Debug changes rejected")

    def _show_debug_error(self, message: str) -> None:
        self.debug_error.setText(message)
        self.debug_error.show()
        self.debug_panel.setProperty("invalid", True)
        self.debug_panel.style().unpolish(self.debug_panel)
        self.debug_panel.style().polish(self.debug_panel)

    def _clear_debug_error(self) -> None:
        if not hasattr(self, "debug_error"):
            return
        self.debug_error.clear()
        self.debug_error.hide()
        self.debug_panel.setProperty("invalid", False)
        self.debug_panel.style().unpolish(self.debug_panel)
        self.debug_panel.style().polish(self.debug_panel)

    def toggle_debug(self) -> None:
        self.debug_enabled = not self.debug_enabled
        self.debug_label.setVisible(self.debug_enabled)
        self._debug_dock_widget.setVisible(self.debug_enabled)
        if not self.debug_enabled:
            self.debug_panel.clear()
            self.debug_entity = None
        elif self.tabs.currentWidget() is self.areas_tab:
            self.inspect_area(self._selected_area())
        elif self.tabs.currentWidget() is self.calendar_tab:
            self.inspect_event(self.calendar.selected_event)
        elif self.tabs.currentWidget() is self.preferences_tab:
            self.inspect_preferences()

    def _estimate_max_unit(self) -> str:
        preferences = self.planner.get_preferences()
        return str(preferences.scheduling.get("estimate_max_unit", "Hours"))

    def closeEvent(self, event) -> None:
        if self.tray is not None:
            event.ignore()
            self.hide()
            self.status.setText("Running in the menu bar")
            return
        super().closeEvent(event)
