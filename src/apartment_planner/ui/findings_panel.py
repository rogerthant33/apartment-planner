"""The fit-check findings for the current layout. Clicking one selects what it's about."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from apartment_planner.canvas import style
from apartment_planner.fit.findings import Finding

IDS = Qt.ItemDataRole.UserRole  # a row's finding's IDs
PREFIX = {"collision": "Collision", "warning": "Warning"}


class FindingsPanel(QWidget):
    finding_activated = Signal(tuple)  # the IDs a finding involves

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.summary = QLabel()
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemClicked.connect(self._clicked)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.list, 1)
        self._shown: list[Finding] | None = None

    def show_findings(self, findings: list[Finding]) -> None:
        if findings == self._shown:
            return  # this can run inside the list's own click handler
        self._shown = findings
        collisions = sum(f.severity == "collision" for f in findings)
        warnings = len(findings) - collisions
        self.summary.setText(
            f"{collisions} collision{'s' * (collisions != 1)}, "
            f"{warnings} warning{'s' * (warnings != 1)}"
            if findings
            else "Everything fits."
        )
        self.list.clear()
        for finding in findings:
            row = QListWidgetItem(f"{PREFIX[finding.severity]}: {finding.message}")
            color = style.INVALID if finding.severity == "collision" else style.WARNING
            row.setForeground(QBrush(color if style.is_dark() else color.darker(130)))
            row.setData(IDS, finding.ids)
            self.list.addItem(row)

    def restyle(self) -> None:
        """Redraw the rows in the current theme's colours."""
        shown, self._shown = self._shown, None
        if shown is not None:
            self.show_findings(shown)

    def _clicked(self, row: QListWidgetItem) -> None:
        self.finding_activated.emit(tuple(row.data(IDS)))
