from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget, QLayout, QSizePolicy
from PyQt6.QtCore import Qt


class DashboardPanel(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardPanel")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(10)

        self.header = QLabel(title)
        self.header.setObjectName("panelHeader")
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout.addWidget(self.header)

    def add_widget(self, widget: QWidget, stretch: int = 0):
        self._layout.addWidget(widget, stretch)

    def add_layout(self, layout: QLayout, stretch: int = 0):
        self._layout.addLayout(layout, stretch)

    def set_compact_header(self, enabled: bool = True):
        self.header.setObjectName("panelHeaderCompact" if enabled else "panelHeader")
        self.header.style().unpolish(self.header)
        self.header.style().polish(self.header)

    def set_title(self, text: str):
        self.header.setText(text)

    def show_header(self, visible: bool = True):
        self.header.setVisible(visible)

    def body_layout(self) -> QVBoxLayout:
        return self._layout
