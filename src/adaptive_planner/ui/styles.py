"""A complete light palette and compact visual system for the desktop UI."""

from PySide6.QtGui import QColor, QPalette


def light_palette() -> QPalette:
    """Return an explicit palette so macOS dark mode cannot hide light-theme text."""

    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#f5f7fa",
        QPalette.ColorRole.WindowText: "#172033",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#f7f9fc",
        QPalette.ColorRole.ToolTipBase: "#172033",
        QPalette.ColorRole.ToolTipText: "#ffffff",
        QPalette.ColorRole.Text: "#172033",
        QPalette.ColorRole.Button: "#ffffff",
        QPalette.ColorRole.ButtonText: "#172033",
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Link: "#2563eb",
        QPalette.ColorRole.Highlight: "#2563eb",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#8490a3",
    }
    for role, color in colors.items():
        palette.setColor(QPalette.ColorGroup.All, role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#98a2b3"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#98a2b3"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#98a2b3"))
    return palette


STYLESHEET = """
QMainWindow, QDialog, QWidget#page, QWidget#scrollContents {
    background: #f5f7fa;
    color: #172033;
}
QWidget {
    color: #172033;
    font-size: 13px;
}
QLabel {
    background: transparent;
    color: #172033;
}
QLabel#pageTitle {
    color: #111827;
    font-size: 28px;
    font-weight: 700;
}
QLabel#pageSubtitle {
    color: #667085;
    font-size: 13px;
}
QLabel#sectionTitle {
    color: #344054;
    font-size: 13px;
    font-weight: 650;
}
QLabel#sectionMeta, QLabel#mutedText, QLabel#taskMeta {
    color: #667085;
}
QLabel#calendarPeriod {
    color: #172033;
    font-size: 15px;
    font-weight: 650;
    padding-left: 7px;
}
QLabel#calendarTimezone, QLabel#calendarHint {
    color: #667085;
    font-size: 11px;
}
QLabel#healthStrip {
    background: #eaf4ef;
    border: 1px solid #d4e8dc;
    border-radius: 9px;
    color: #28543b;
    font-weight: 600;
    padding: 11px 13px;
}
QFrame#nextActionCard {
    background: #fffaf0;
    border: 1px solid #f2d99b;
    border-radius: 10px;
}
QLabel#cardEyebrow {
    color: #8a6420;
    font-size: 11px;
    font-weight: 700;
}
QLabel#nextActionTitle {
    color: #513b12;
    font-size: 17px;
    font-weight: 650;
}
QFrame#taskCard, QFrame#infoCard, QWidget#settingsCard {
    background: #ffffff;
    border: 1px solid #dfe4ec;
    border-radius: 10px;
}
QFrame#taskCard:hover {
    border-color: #b9c7dc;
}
QLabel#taskTitle {
    color: #172033;
    font-size: 15px;
    font-weight: 650;
}
QLabel#priorityPill {
    background: #eef2f7;
    border-radius: 9px;
    color: #475467;
    font-size: 11px;
    font-weight: 650;
    padding: 3px 8px;
}
QFrame#emptyState {
    background: #ffffff;
    border: 1px dashed #ccd4df;
    border-radius: 10px;
}
QLabel#emptyTitle {
    color: #344054;
    font-size: 15px;
    font-weight: 650;
}
QLabel#emptyBody {
    color: #667085;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #cfd6e1;
    border-radius: 7px;
    color: #344054;
    font-weight: 600;
    min-height: 20px;
    padding: 6px 11px;
}
QPushButton:hover {
    background: #f8fafc;
    border-color: #aeb8c7;
}
QPushButton:pressed {
    background: #eef2f7;
}
QPushButton:disabled {
    background: #f2f4f7;
    border-color: #e4e7ec;
    color: #98a2b3;
}
QPushButton[variant="primary"] {
    background: #2563eb;
    border-color: #2563eb;
    color: #ffffff;
}
QPushButton[variant="primary"]:hover {
    background: #1d4ed8;
    border-color: #1d4ed8;
}
QPushButton[variant="success"] {
    background: #eaf6ef;
    border-color: #b8dfc7;
    color: #23623c;
}
QPushButton[variant="danger"] {
    background: #ffffff;
    border-color: #efc4c4;
    color: #b42318;
}
QPushButton[variant="primary"]:disabled,
QPushButton[variant="success"]:disabled,
QPushButton[variant="danger"]:disabled {
    background: #f2f4f7;
    border-color: #e4e7ec;
    color: #98a2b3;
}
QPushButton#calendarNavButton {
    min-width: 24px;
    padding-left: 9px;
    padding-right: 9px;
}
QPushButton#calendarModeButton {
    border-radius: 6px;
    min-width: 44px;
    padding-left: 9px;
    padding-right: 9px;
}
QPushButton#calendarModeButton:checked {
    background: #e5edff;
    border-color: #9cb6ed;
    color: #1849a9;
}
QPushButton#pickerButton {
    background: #ffffff;
    border-color: #cfd6e1;
    color: #172033;
    font-weight: 500;
    text-align: left;
    padding: 7px 10px;
}
QPushButton#pickerButton:hover {
    background: #f8fafc;
    border-color: #7da2ef;
}
QLineEdit, QTextEdit, QSpinBox, QDateEdit, QDateTimeEdit, QComboBox, QListWidget, QTableWidget {
    background: #ffffff;
    border: 1px solid #cfd6e1;
    border-radius: 7px;
    color: #172033;
    padding: 6px 8px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDateEdit:focus,
QDateTimeEdit:focus, QComboBox:focus, QListWidget:focus, QTableWidget:focus {
    border: 1px solid #4f7ff0;
}
QSpinBox, QDateEdit, QDateTimeEdit {
    padding-right: 22px;
}
QListWidget {
    outline: none;
}
QListWidget::item {
    border-bottom: 1px solid #edf0f4;
    color: #344054;
    min-height: 28px;
    padding: 8px 10px;
}
QListWidget::item:selected {
    background: #e9f0ff;
    color: #1849a9;
}
QTableWidget {
    gridline-color: #edf0f4;
    outline: none;
}
QTableWidget::item {
    padding: 6px 8px;
}
QTableWidget::item:selected {
    background: #e9f0ff;
    color: #1849a9;
}
QHeaderView::section {
    background: #f7f9fc;
    border: none;
    border-bottom: 1px solid #dfe4ec;
    color: #667085;
    font-size: 11px;
    font-weight: 650;
    padding: 7px 8px;
}
QCalendarWidget QWidget {
    background: #ffffff;
    color: #172033;
}
QCalendarWidget QToolButton {
    background: transparent;
    border: none;
    color: #172033;
    font-weight: 650;
}
QCalendarWidget QAbstractItemView {
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QScrollArea {
    background: transparent;
    border: none;
}
QGraphicsView {
    background: #ffffff;
    border: 1px solid #dfe4ec;
}
QTabWidget::pane {
    background: #f5f7fa;
    border: none;
}
QTabBar::tab {
    background: transparent;
    border: none;
    border-radius: 7px;
    color: #667085;
    font-weight: 600;
    margin: 7px 2px;
    min-width: 74px;
    padding: 7px 13px;
}
QTabBar::tab:hover {
    background: #edf1f6;
    color: #344054;
}
QTabBar::tab:selected {
    background: #e5edff;
    color: #1849a9;
}
QMenuBar {
    background: #f5f7fa;
    color: #172033;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #e5edff;
    color: #1849a9;
}
QMenu {
    background: #ffffff;
    border: 1px solid #dfe4ec;
    color: #172033;
}
QStatusBar {
    background: #f5f7fa;
    border-top: 1px solid #e4e7ec;
    color: #667085;
}
QStatusBar QLabel {
    color: #667085;
}
QGroupBox {
    border: 1px solid #dfe4ec;
    border-radius: 9px;
    color: #344054;
    font-weight: 650;
    margin-top: 12px;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QToolTip {
    background: #172033;
    border: none;
    color: #ffffff;
    padding: 5px;
}
"""
