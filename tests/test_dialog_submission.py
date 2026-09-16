from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QDialogButtonBox

from adaptive_planner.domain.types import AreaDTO, AreaKind, PostDuePolicy
from adaptive_planner.ui.dialogs import AreaDialog, EstimateDialog, QuickCaptureDialog


def _area() -> AreaDTO:
    now = datetime.now(timezone.utc)
    return AreaDTO(
        id=uuid4(),
        system_key="UNCATEGORIZED",
        name="None",
        kind=AreaKind.OTHER,
        default_post_due_policy=PostDuePolicy.ASK,
        archived_at=None,
        created_at=now,
        updated_at=now,
    )


def test_quick_capture_only_saves_from_the_save_button(qtbot) -> None:
    dialog = QuickCaptureDialog((_area(),), "UTC")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.title.setText("A task")

    QTest.keyClick(dialog.title, Qt.Key.Key_Return)
    assert dialog.isVisible()
    assert dialog.result() != QDialog.DialogCode.Accepted

    QTest.keyClick(dialog.title, Qt.Key.Key_Enter)
    assert dialog.isVisible()
    assert dialog.result() != QDialog.DialogCode.Accepted

    dialog.description.setFocus()
    QTest.keyClicks(dialog.description, "First line")
    QTest.keyClick(dialog.description, Qt.Key.Key_Return)
    QTest.keyClicks(dialog.description, "Second line")
    assert dialog.isVisible()
    assert "First line\nSecond line" in dialog.description.toPlainText()

    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    save = buttons.button(QDialogButtonBox.StandardButton.Save)
    assert save is not None
    QTest.mouseClick(save, Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_area_dialog_does_not_save_on_return(qtbot) -> None:
    dialog = AreaDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.name.setText("Work")

    QTest.keyClick(dialog.name, Qt.Key.Key_Return)
    assert dialog.isVisible()
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_estimate_dialog_accepts_compound_duration_without_return_closing_it(qtbot) -> None:
    dialog = EstimateDialog(None)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.estimate.hours_input.setValue(1)
    dialog.estimate.minutes_input.setValue(32)
    dialog.estimate.seconds_input.setValue(56)

    QTest.keyClick(dialog.estimate.seconds_input, Qt.Key.Key_Return)
    assert dialog.isVisible()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.value == (60 * 60) + (32 * 60) + 56

    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    save = buttons.button(QDialogButtonBox.StandardButton.Save)
    assert save is not None
    QTest.mouseClick(save, Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted
