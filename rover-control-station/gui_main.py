from __future__ import annotations

import csv
import json
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QLayout,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from dashboard_panel import DashboardPanel
from logger_utils import log_accelerometer_to_csv, setup_csv_logging, write_session_metadata
from rover_core import (
    CommandFrame,
    EventRecord,
    RoverState,
    TelemetryFrame,
    UIRuntimeProfile,
    PROTOCOL_VERSION,
)
from rover_protocol import encryption_mode_name, is_encryption_enabled, set_encryption_enabled
from rover_worker import SerialWorker
from theme import build_stylesheet, get_theme


class IndicatorLamp(QWidget):
    def __init__(self, diameter: int = 12, parent: QWidget | None = None):
        super().__init__(parent)
        self.diameter = diameter
        self._color = QColor("#59e05d")
        self.setFixedSize(diameter + 6, diameter + 6)

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(3, 3, -3, -3)
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(rect)


class SensorIndicatorRow(QWidget):
    NAME_WIDTH = 96
    VALUE_WIDTH = 118

    def __init__(self, name: str, parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.label = QLabel(name)
        self.label.setMinimumWidth(self.NAME_WIDTH)
        self.label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.label.setObjectName("sensorCell")
        self.lamp = IndicatorLamp(12)
        self.hint = QLabel("Waiting")
        self.hint.setObjectName("sensorValueCell")
        self.hint.setMinimumWidth(self.VALUE_WIDTH)
        self.hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.label)
        row.addWidget(self.hint)
        row.addWidget(self.lamp)

    @classmethod
    def make_header(cls, parent: QWidget | None = None) -> QWidget:
        widget = QWidget(parent)
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        sensor = QLabel("Sensor")
        sensor.setObjectName("mutedText")
        sensor.setMinimumWidth(cls.NAME_WIDTH)
        sensor.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        state = QLabel("State / Value")
        state.setObjectName("mutedText")
        state.setMinimumWidth(cls.VALUE_WIDTH)
        state.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        state.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        lamp = QLabel("Lamp")
        lamp.setObjectName("mutedText")
        lamp.setMinimumWidth(24)
        lamp.setAlignment(Qt.AlignmentFlag.AlignCenter)

        row.addWidget(sensor)
        row.addWidget(state)
        row.addWidget(lamp)
        return widget

    def update_state(self, state: str, hint: str, colors: dict[str, str]):
        color_map = {
            "ok": colors["success"],
            "special": colors["special"],
            "warning": colors["warning"],
            "danger": colors["danger"],
        }
        self.lamp.set_color(color_map.get(state, colors["special"]))
        self.hint.setText(hint)


class TelemetryBar(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(16)
        self.setMaximumHeight(16)
        self.ratio = 0.0
        self.fill_color = "#59e05d"
        self.empty_color = "#cfd7e2"
        self.border_color = "#2b4570"

    def set_colors(self, fill_color: str, empty_color: str, border_color: str):
        self.fill_color = fill_color
        self.empty_color = empty_color
        self.border_color = border_color
        self.update()

    def set_ratio(self, ratio: float):
        self.ratio = max(0.0, min(1.0, ratio))
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor(self.border_color), 1))
        painter.setBrush(QBrush(QColor(self.empty_color)))
        painter.drawRoundedRect(rect, 6, 6)

        width = int(rect.width() * self.ratio)
        if width > 0:
            fill_rect = rect.adjusted(0, 0, -(rect.width() - width), 0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(self.fill_color)))
            painter.drawRoundedRect(fill_rect, 6, 6)



class ConvergingBar(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(20)
        self.setMaximumHeight(20)
        self.ratio = 0.0
        self.fill_color = "#59e05d"
        self.empty_color = "#cfd7e2"
        self.border_color = "#2b4570"

    def set_colors(self, fill_color: str, empty_color: str, border_color: str):
        self.fill_color = fill_color
        self.empty_color = empty_color
        self.border_color = border_color
        self.update()

    def set_ratio(self, ratio: float):
        self.ratio = max(0.0, min(1.0, ratio))
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor(self.border_color), 1))
        painter.setBrush(QBrush(QColor(self.empty_color)))
        painter.drawRoundedRect(rect, 8, 8)

        # ratio = safety level; higher ratio means a longer coloured centre bar.
        fill_width = int(rect.width() * self.ratio)
        if fill_width <= 0:
            return
        center_x = rect.left() + rect.width() / 2.0
        left_x = int(center_x - fill_width / 2.0)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self.fill_color)))
        fill_rect = rect.adjusted(left_x - rect.left(), 0, -((rect.right() + 1) - (left_x + fill_width)), 0)
        painter.drawRoundedRect(fill_rect, 8, 8)

class MplCanvas(FigureCanvas):
    def __init__(self, plot_bg: str, text_color: str, parent: QWidget | None = None):
        self.figure = Figure(figsize=(5, 3), tight_layout=True)
        self.ax = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)
        self.update_theme(plot_bg, text_color)

    def update_theme(self, plot_bg: str, text_color: str):
        self.figure.patch.set_facecolor(plot_bg)
        self.ax.set_facecolor(plot_bg)
        self.ax.tick_params(colors=text_color)
        for spine in self.ax.spines.values():
            spine.set_color(text_color)
        self.ax.title.set_color(text_color)
        self.ax.xaxis.label.set_color(text_color)
        self.ax.yaxis.label.set_color(text_color)


class RoverGUI(QMainWindow):
    status_message = pyqtSignal(str)
    command_outbound = pyqtSignal(object)
    worker_start = pyqtSignal(str, int)
    worker_stop = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rover Control Station - PyQt6")
        self.resize(1540, 980)
        # Allow smaller windows, then switch to scroll mode before text gets compressed.
        self.setMinimumSize(1120, 700)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.theme_name = "Dark Blue"
        self.view_mode = "Simple"
        self.signal_view = "Overlay"
        self.decimal_mode = "Simple"
        self.ui_profile = UIRuntimeProfile()
        self.connected = False
        self.logging_enabled = True
        self.current_command = "STOP"
        self.session_dir = Path("session_logs")
        self.session_dir.mkdir(exist_ok=True)
        self.log_file_path = str(self.session_dir / "accelerometer_log.csv")
        self.metadata_path = str(self.session_dir / "session_metadata.json")
        setup_csv_logging(self.log_file_path)

        self.max_points = 180
        self.log_points = 240
        self.protocol_version = PROTOCOL_VERSION
        self.rover_state = RoverState.DISCONNECTED
        self.packet_counter = 0
        self.samples_logged = 0
        self.parse_errors = 0
        self.dropped_packets = 0
        self.timeout_counter = 0
        self.last_packet_age_ms = 0
        self.serial_state = "Disconnected"
        self.system_alert = "Idle"

        self.imu_filter = "Low-pass"
        self.ultra_filter = "Median + Avg"
        self.link_filter = "Smooth"
        self.imu_alpha = 0.25
        self.link_alpha = 0.30
        self.avg_window = 6
        self.median_window = 5
        self.obstacle_warning_cm = 35
        self.obstacle_danger_cm = 20
        self.obstacle_display_max_cm = 50
        self.battery_warning_v = 6.9
        self.battery_danger_v = 6.5
        self.plot_history = 90
        self.update_interval_ms = 400

        self.raw_x = deque([0.00] * self.max_points, maxlen=self.max_points)
        self.raw_y = deque([0.00] * self.max_points, maxlen=self.max_points)
        self.raw_z = deque([1.00] * self.max_points, maxlen=self.max_points)
        self.raw_mag = deque([1.00] * self.max_points, maxlen=self.max_points)
        self.raw_rssi = deque([-88.0] * self.max_points, maxlen=self.max_points)
        self.raw_snr = deque([10.0] * self.max_points, maxlen=self.max_points)
        self.raw_batt_v = deque([7.40] * self.max_points, maxlen=self.max_points)
        self.raw_front_cm = deque([60.0] * self.max_points, maxlen=self.max_points)
        self.raw_humidity = deque([48.0] * self.max_points, maxlen=self.max_points)
        self.raw_thermistor = deque([24.0] * self.max_points, maxlen=self.max_points)
        self.raw_log_mag = deque([1.00] * self.log_points, maxlen=self.log_points)
        self.log_lines = deque(maxlen=300)

        self.lp_x = 0.0
        self.lp_y = 0.0
        self.lp_z = 1.0
        self.lp_mag = 1.0
        self.lp_rssi = -88.0
        self.lp_batt = 7.40
        self.lp_front = 60.0
        self.lp_humidity = 48.0
        self.lp_thermistor = 24.0
        self.last_alert_message = "Nominal"
        self.alert_cooldowns = {}
        self.current_alert_level = "info"
        self.current_alert_text = "Nominal"
        self.alert_hold_until = 0.0
        self.event_records = deque(maxlen=500)
        self.pending_commands: dict[int, CommandFrame] = {}
        self.command_counter = 0
        self.last_ack_latency_ms = 0.0
        self.ack_latency_samples = deque(maxlen=30)
        self.avg_ack_latency_ms = 0.0
        self.recent_timeouts = 0
        self.last_rx_monotonic = time.time()
        self.last_heartbeat_sent = 0.0
        self.battery_alert_zone = "normal"
        self.last_battery_alert_v = 7.40
        self.battery_realert_drop_v = 0.25
        self.replay_frames: list[TelemetryFrame] = []
        self.replay_index = 0
        self.replay_playing = False
        self._pending_log_refresh = False
        self._pending_protocol_refresh = False
        self._latest_protocol_kind = ""
        self._latest_protocol_raw = ""
        self._latest_protocol_decoded_raw = ""
        self._latest_protocol_decoded = ""
        self.active_alerts: dict[str, tuple[str, float]] = {}
        self.active_alert_limit = 6

        self._build_ui()
        self.apply_theme()
        self.reset_dashboard_state()
        self._bind_events()
        self.status_message.connect(self.append_log_line)
        self.status_message.connect(lambda text: self.statusBar().showMessage(text, 4000))
        self._setup_worker()
        self._setup_refresh_timers()
        self._refresh_interaction_state()
        self.on_view_changed(self.view_mode)
        self.set_active_tab_refresh_policy("Dashboard")
        self._apply_responsive_layout()

    def _setup_worker(self):
        self.worker_thread = QThread(self)
        self.serial_worker = SerialWorker()
        self.serial_worker.moveToThread(self.worker_thread)
        self.command_outbound.connect(self.serial_worker.enqueue_command)
        self.worker_start.connect(self.serial_worker.start_link)
        self.worker_stop.connect(self.serial_worker.stop_link)
        self.serial_worker.telemetry_received.connect(self.on_telemetry_received)
        self.serial_worker.ack_received.connect(self.on_ack_received)
        self.serial_worker.worker_event.connect(self.on_worker_event)
        self.serial_worker.link_state_changed.connect(self.on_link_state_changed)
        self.serial_worker.protocol_trace.connect(self.on_protocol_trace)
        self.worker_thread.start()

    def _setup_refresh_timers(self):
        self.dashboard_timer = QTimer(self)
        self.dashboard_timer.setInterval(350)
        self.dashboard_timer.timeout.connect(lambda: self.refresh_dashboard_cards(force=False))
        self.dashboard_timer.start()

        self.imu_plot_timer = QTimer(self)
        self.imu_plot_timer.setInterval(400)
        self.imu_plot_timer.timeout.connect(lambda: self.refresh_imu_plots(force=False))
        self.imu_plot_timer.start()

        self.secondary_plot_timer = QTimer(self)
        self.secondary_plot_timer.setInterval(650)
        self.secondary_plot_timer.timeout.connect(lambda: self.refresh_secondary_plots(force=False))
        self.secondary_plot_timer.start()

        self.system_timer = QTimer(self)
        self.system_timer.setInterval(1000)
        self.system_timer.timeout.connect(lambda: self.refresh_system_page(force=False))
        self.system_timer.start()

        self.health_timer = QTimer(self)
        self.health_timer.setInterval(1000)
        self.health_timer.timeout.connect(self._check_command_timeouts)
        self.health_timer.start()

        self.text_refresh_timer = QTimer(self)
        self.text_refresh_timer.setInterval(250)
        self.text_refresh_timer.timeout.connect(self._flush_throttled_text_updates)
        self.text_refresh_timer.start()
        self.replay_timer = QTimer(self)
        self.replay_timer.setSingleShot(True)
        self.replay_timer.timeout.connect(self._on_replay_tick)

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        self.header_bar = QFrame()
        self.header_bar.setObjectName("headerBar")
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(12)

        title = QLabel("Rover Control Station")
        title.setObjectName("mainTitle")
        header_layout.addWidget(title, 1)
        root.addWidget(self.header_bar)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tab_mode_strip = QFrame()
        self.tab_mode_strip.setObjectName("tabModeStrip")
        tab_mode_layout = QHBoxLayout(self.tab_mode_strip)
        tab_mode_layout.setContentsMargins(6, 2, 6, 2)
        tab_mode_layout.setSpacing(6)
        self.tab_mode_label = QLabel("Mode:")
        self.tab_mode_label.setObjectName("mutedText")
        self.page_mode_combo = QComboBox()
        self.page_mode_combo.addItems(["Simple", "Advanced"])
        self.page_mode_combo.setCurrentText(self.view_mode)
        self.page_mode_combo.setMinimumWidth(108)
        tab_mode_layout.addWidget(self.tab_mode_label)
        tab_mode_layout.addWidget(self.page_mode_combo)
        self.tabs.setCornerWidget(self.tab_mode_strip, Qt.Corner.TopRightCorner)

        self.dashboard_page = QWidget()
        self.telemetry_page = QWidget()
        self.system_page = QWidget()
        self.settings_page = QWidget()
        self.tabs.addTab(self.dashboard_page, "Dashboard")
        self.tabs.addTab(self.telemetry_page, "Telemetry")
        self.tabs.addTab(self.system_page, "System")
        self.tabs.addTab(self.settings_page, "Settings")

        self._build_dashboard_page()
        self._build_telemetry_page()
        self._build_system_page()
        self._build_settings_page()
        self._build_status_bar()

    def _build_status_bar(self):
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        self.status_conn = QLabel("Conn: OFF")
        self.status_mode = QLabel(f"Mode: {self.view_mode}")
        self.status_batt = QLabel("Battery: --")
        self.status_alert = QLabel("Alert: Nominal")
        self.status_log = QLabel("Logging: On")
        for item in [self.status_conn, self.status_mode, self.status_batt, self.status_alert, self.status_log]:
            item.setObjectName("statusPill")
            bar.addPermanentWidget(item)
        # Backward-compatible aliases for existing refresh methods.
        self.top_status_conn = self.status_conn
        self.top_status_mode = self.status_mode
        self.top_status_batt = self.status_batt
        self.top_status_alert = self.status_alert
        self.top_status_log = self.status_log

    def _build_dashboard_page(self):
        outer = QVBoxLayout(self.dashboard_page)
        outer.setContentsMargins(0, 0, 0, 0)
        self.dashboard_scroll = QScrollArea()
        self.dashboard_scroll.setWidgetResizable(True)
        outer.addWidget(self.dashboard_scroll)
        self.dashboard_page_body = QWidget()
        self.dashboard_scroll.setWidget(self.dashboard_page_body)
        layout = QVBoxLayout(self.dashboard_page_body)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        top = QHBoxLayout(); top.setSpacing(10)
        layout.addLayout(top)

        self.connection_panel = self._create_connection_panel()
        self.status_panel = self._create_status_panel()
        self.obstacle_panel = self._create_obstacle_panel(compact=True)
        self.control_panel = self._create_control_panel()
        left = QVBoxLayout(); left.setSpacing(10)
        left.addWidget(self.connection_panel)
        left.addWidget(self.status_panel)
        left.addWidget(self.obstacle_panel)
        left.addWidget(self.control_panel)
        left.addStretch(1)
        top.addLayout(left, 0)

        right = QVBoxLayout(); right.setSpacing(10)
        top.addLayout(right, 1)

        info_grid = QGridLayout(); info_grid.setSpacing(10)
        right.addLayout(info_grid)
        self.link_panel = self._create_link_panel()
        self.environment_panel = self._create_environment_panel()
        self.sensor_panel = self._create_sensor_panel()
        info_grid.addWidget(self.link_panel, 0, 0)
        info_grid.addWidget(self.environment_panel, 0, 1)
        info_grid.addWidget(self.sensor_panel, 0, 2)
        info_grid.setColumnStretch(0, 1)
        info_grid.setColumnStretch(1, 1)
        info_grid.setColumnStretch(2, 1)

        mid = QHBoxLayout(); mid.setSpacing(10)
        right.addLayout(mid, 1)
        self.imu_panel = self._create_imu_panel(compact=True)
        mid.addWidget(self.imu_panel, 1)

        bottom = QHBoxLayout(); bottom.setSpacing(10)
        right.addLayout(bottom)
        self.alert_panel = self._create_alert_panel()
        self.quick_diag_panel = self._create_quick_diag_panel()
        bottom.addWidget(self.alert_panel, 3)
        bottom.addWidget(self.quick_diag_panel, 1)

    def _build_telemetry_page(self):
        outer = QVBoxLayout(self.telemetry_page)
        outer.setContentsMargins(0, 0, 0, 0)
        self.telemetry_scroll = QScrollArea()
        self.telemetry_scroll.setWidgetResizable(True)
        outer.addWidget(self.telemetry_scroll)
        self.telemetry_page_body = QWidget()
        self.telemetry_scroll.setWidget(self.telemetry_page_body)
        layout = QVBoxLayout(self.telemetry_page_body)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        self.telemetry_control_panel = DashboardPanel("Telemetry Controls")
        form = QFormLayout(); form.setHorizontalSpacing(14); form.setVerticalSpacing(8)
        self.telemetry_imu_filter_combo = QComboBox(); self.telemetry_imu_filter_combo.addItems(["Raw", "Moving Avg", "Low-pass"])
        self.telemetry_ultra_filter_combo = QComboBox(); self.telemetry_ultra_filter_combo.addItems(["Raw", "Median", "Median + Avg"])
        self.telemetry_link_filter_combo = QComboBox(); self.telemetry_link_filter_combo.addItems(["Raw", "Smooth"])
        form.addRow("IMU Filter:", self.telemetry_imu_filter_combo)
        form.addRow("Obstacle Filter:", self.telemetry_ultra_filter_combo)
        form.addRow("Link Filter:", self.telemetry_link_filter_combo)
        self.telemetry_control_panel.add_layout(form)
        layout.addWidget(self.telemetry_control_panel)

        grid = QGridLayout(); grid.setSpacing(10)
        layout.addLayout(grid, 1)

        self.telemetry_imu_panel = DashboardPanel("IMU / Motion")
        self.telemetry_imu_canvas = self._make_plot_canvas()
        self.telemetry_imu_panel.add_widget(self.telemetry_imu_canvas, 1)
        grid.addWidget(self.telemetry_imu_panel, 0, 0)

        self.telemetry_link_plot_panel = DashboardPanel("Link Quality")
        self.telemetry_link_canvas = self._make_plot_canvas()
        self.telemetry_link_plot_panel.add_widget(self.telemetry_link_canvas, 1)
        grid.addWidget(self.telemetry_link_plot_panel, 0, 1)

        self.telemetry_environment_panel = DashboardPanel("Environment")
        self.telemetry_environment_canvas = self._make_plot_canvas()
        self.telemetry_environment_panel.add_widget(self.telemetry_environment_canvas, 1)
        grid.addWidget(self.telemetry_environment_panel, 1, 0)

        self.telemetry_distance_panel = DashboardPanel("Distance Trend")
        self.telemetry_distance_canvas = self._make_plot_canvas()
        self.telemetry_distance_panel.add_widget(self.telemetry_distance_canvas, 1)
        grid.addWidget(self.telemetry_distance_panel, 1, 1)

    def _build_system_page(self):
        outer = QVBoxLayout(self.system_page)
        outer.setContentsMargins(0, 0, 0, 0)
        self.system_scroll = QScrollArea()
        self.system_scroll.setWidgetResizable(True)
        outer.addWidget(self.system_scroll)
        self.system_page_body = QWidget()
        self.system_scroll.setWidget(self.system_page_body)
        layout = QVBoxLayout(self.system_page_body)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)
        self.system_page_layout = layout
        self.system_top_row = QWidget()
        top = QHBoxLayout(self.system_top_row)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        layout.addWidget(self.system_top_row, 1)

        self.diagnostics_overview_panel = DashboardPanel("Operations")
        self.diagnostics_overview_panel.set_compact_header(True)
        self.diagnostics_overview_panel.setMinimumHeight(156)
        self.diag_serial_label = QLabel()
        self.diag_battery_label = QLabel()
        self.diag_last_packet_label = QLabel()
        self.diag_packet_rate_label = QLabel()
        self.diag_packet_loss_label = QLabel()
        self.diag_dropped_label = QLabel()
        self.diag_parse_label = QLabel()
        self.diag_timeout_label = QLabel()
        self.logging_state_label = QLabel()
        self.logging_samples_label = QLabel()
        self.diag_state_label = QLabel()
        self.diag_protocol_label = QLabel()
        self.diag_ack_label = QLabel()
        self.diag_timeout_recent_label = QLabel()
        overview_cols = QHBoxLayout()
        overview_cols.setSpacing(10)
        self.operations_left_form = QFormLayout(); self.operations_left_form.setHorizontalSpacing(10); self.operations_left_form.setVerticalSpacing(4)
        self.operations_right_form = QFormLayout(); self.operations_right_form.setHorizontalSpacing(10); self.operations_right_form.setVerticalSpacing(4)
        self.operations_left_form.addRow("Link:", self.diag_serial_label)
        self.operations_left_form.addRow("Rover:", self.diag_state_label)
        self.operations_left_form.addRow("Battery:", self.diag_battery_label)
        self.operations_right_form.addRow("Pkt Age:", self.diag_last_packet_label)
        self.operations_right_form.addRow("Pkt Loss:", self.diag_packet_loss_label)
        self.operations_right_form.addRow("ACK:", self.diag_ack_label)
        self.operations_right_form.addRow("Timeouts:", self.diag_timeout_recent_label)
        overview_cols.addLayout(self.operations_left_form, 1)
        overview_cols.addLayout(self.operations_right_form, 1)
        self.diagnostics_overview_panel.add_layout(overview_cols)
        top.addWidget(self.diagnostics_overview_panel, 2)

        self.system_logging_panel = DashboardPanel("Logging")
        self.system_logging_panel.set_compact_header(True)
        self.system_logging_panel.setMinimumHeight(156)
        self.system_logging_form = QFormLayout(); self.system_logging_form.setHorizontalSpacing(12); self.system_logging_form.setVerticalSpacing(6)
        self.logging_file_label = QLabel()
        self.logging_metadata_label = QLabel()
        self.logging_file_label.setWordWrap(False)
        self.logging_metadata_label.setWordWrap(False)
        self.encryption_state_label = QLabel()
        self.encryption_method_label = QLabel()
        self.logging_toggle_button = QPushButton("Stop Logging")
        self.export_metadata_button = QPushButton("Save Metadata")
        self.system_logging_form.addRow("State:", self.logging_state_label)
        self.system_logging_form.addRow("Samples:", self.logging_samples_label)
        self.system_logging_form.addRow("Dropped:", self.diag_dropped_label)
        self.system_logging_form.addRow("Timeouts:", self.diag_timeout_label)
        btns = QHBoxLayout(); btns.addWidget(self.logging_toggle_button); btns.addWidget(self.export_metadata_button)
        self.system_logging_panel.add_layout(self.system_logging_form)
        self.system_logging_panel.add_layout(btns)
        top.addWidget(self.system_logging_panel, 3)

        self.system_detail_panel = DashboardPanel("Diagnostics")
        self.system_detail_panel.set_compact_header(True)
        self.system_detail_panel.setMinimumHeight(140)
        detail_cols = QHBoxLayout(); detail_cols.setSpacing(12)
        detail_left = QFormLayout(); detail_left.setHorizontalSpacing(10); detail_left.setVerticalSpacing(4)
        detail_right = QFormLayout(); detail_right.setHorizontalSpacing(10); detail_right.setVerticalSpacing(4)
        detail_left.addRow("Protocol:", self.diag_protocol_label)
        detail_left.addRow("Pkt Rate:", self.diag_packet_rate_label)
        detail_left.addRow("Parse:", self.diag_parse_label)
        detail_right.addRow("Encryption:", self.encryption_state_label)
        detail_right.addRow("Cipher:", self.encryption_method_label)
        detail_right.addRow("CSV:", self.logging_file_label)
        detail_right.addRow("Meta:", self.logging_metadata_label)
        detail_cols.addLayout(detail_left, 2)
        detail_cols.addLayout(detail_right, 3)
        self.system_detail_panel.add_layout(detail_cols)

        self.system_middle_row = QWidget()
        middle = QHBoxLayout(self.system_middle_row)
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(10)
        layout.addWidget(self.system_middle_row, 1)

        self.sensor_health_panel = DashboardPanel("Sensor Health")
        self.sensor_health_panel.set_compact_header(True)
        self.sensor_health_panel.setMinimumHeight(248)
        self.sensor_health_panel.body_layout().setSpacing(6)
        self.sensor_grid_host = QWidget()
        self.sensor_grid_layout = QGridLayout(self.sensor_grid_host)
        self.sensor_grid_layout.setContentsMargins(0, 0, 0, 0)
        self.sensor_grid_layout.setHorizontalSpacing(8)
        self.sensor_grid_layout.setVerticalSpacing(4)
        self.diag_rows = {
            "IMU": SensorIndicatorRow("IMU"),
            "Ultrasonic": SensorIndicatorRow("Ultrasonic"),
            "Battery": SensorIndicatorRow("Battery"),
            "Humidity": SensorIndicatorRow("Humidity"),
            "Thermistor": SensorIndicatorRow("Thermistor"),
            "LoRa": SensorIndicatorRow("LoRa Link"),
            "SD": SensorIndicatorRow("SD Logger"),
        }
        self.sensor_cell_widgets = list(self.diag_rows.values())
        self._relayout_system_sensor_grid(self._recommended_sensor_columns())
        self.sensor_table_scroll = QScrollArea()
        self.sensor_table_scroll.setWidgetResizable(True)
        self.sensor_table_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sensor_table_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.sensor_table_scroll.setWidget(self.sensor_grid_host)
        self.sensor_table_scroll.setMinimumHeight(212)
        self.sensor_health_panel.add_widget(self.sensor_table_scroll, 1)
        middle.addWidget(self.sensor_health_panel, 2)

        self.logging_note_panel = DashboardPanel("Session Notes")
        self.logging_note_panel.set_compact_header(True)
        self.logging_note_panel.setMinimumHeight(248)
        self.session_notes = QPlainTextEdit()
        self.session_notes.setPlaceholderText("Record test condition, terrain, filter mode, or failures here.")
        self.logging_note_panel.add_widget(self.session_notes, 1)
        middle.addWidget(self.logging_note_panel, 3)

        self.warning_panel = DashboardPanel("Events and Messages")
        self.warning_panel.set_compact_header(True)
        self.warning_panel.show_header(False)
        active_row = QHBoxLayout()
        active_row.setSpacing(8)
        self.active_alerts_label = QLabel("Active Alerts")
        self.active_alerts_label.setObjectName("valueStrong")
        self.active_alerts_text = QPlainTextEdit()
        self.active_alerts_text.setReadOnly(True)
        self.active_alerts_text.setMaximumHeight(64)
        self.active_alerts_text.setPlaceholderText("No active alerts.")
        self.ack_alerts_button = QPushButton("ACK")
        self.ack_alerts_button.setMinimumWidth(88)
        active_row.addWidget(self.active_alerts_label, 0)
        active_row.addWidget(self.active_alerts_text, 1)
        active_row.addWidget(self.ack_alerts_button, 0)
        self.warning_panel.add_layout(active_row)
        filter_row = QHBoxLayout()
        self.events_all_btn = QPushButton("All")
        self.events_warn_btn = QPushButton("Warning")
        self.events_error_btn = QPushButton("Error")
        for btn in [self.events_all_btn, self.events_warn_btn, self.events_error_btn]:
            btn.setCheckable(True)
            btn.setMaximumWidth(90)
            filter_row.addWidget(btn)
        filter_row.addStretch(1)
        self.warning_panel.add_layout(filter_row)
        self.warning_text = QTextEdit(); self.warning_text.setReadOnly(True)
        self.warning_text.setMinimumHeight(180)
        self.warning_panel.add_widget(self.warning_text, 1)

        self.protocol_monitor_panel = DashboardPanel("Protocol Monitor")
        self.protocol_monitor_panel.set_compact_header(True)
        self.protocol_monitor_panel.show_header(False)
        proto_row = QHBoxLayout()
        self.raw_signal_text = QPlainTextEdit(); self.raw_signal_text.setReadOnly(True); self.raw_signal_text.setPlaceholderText("Raw signal (hex)")
        self.decoded_signal_text = QPlainTextEdit(); self.decoded_signal_text.setReadOnly(True); self.decoded_signal_text.setPlaceholderText("Decoded signal (json)")
        self.raw_signal_text.setMinimumHeight(210)
        self.decoded_signal_text.setMinimumHeight(210)
        proto_row.addWidget(self.raw_signal_text, 1)
        proto_row.addWidget(self.decoded_signal_text, 1)
        self.protocol_monitor_panel.add_layout(proto_row)
        self.system_detail_panel.show_header(False)
        self.system_bottom_tabs = QTabWidget()
        self.system_bottom_tabs.setDocumentMode(True)
        self.system_bottom_tabs.setMinimumHeight(280)
        self.system_tab_events_idx = self.system_bottom_tabs.addTab(self.warning_panel, "Events")
        self.system_tab_protocol_idx = self.system_bottom_tabs.addTab(self.protocol_monitor_panel, "Protocol")
        self.system_tab_diag_idx = self.system_bottom_tabs.addTab(self.system_detail_panel, "Diagnostics")
        layout.addWidget(self.system_bottom_tabs, 2)
    def _build_settings_page(self):
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        layout = QVBoxLayout(self.settings_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.settings_scroll)

        self.settings_page_body = QWidget()
        self.settings_scroll.setWidget(self.settings_page_body)
        body_layout = QVBoxLayout(self.settings_page_body)
        body_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        body_layout.setContentsMargins(6, 6, 6, 6)
        body_layout.setSpacing(10)

        main_grid = QGridLayout(); main_grid.setSpacing(10)
        body_layout.addLayout(main_grid)

        appearance = DashboardPanel("Appearance Notes")
        appearance_note = QLabel(
            "Use 'Live Display Controls' on the right to change View/Theme/Signal mode.\n"
            "These controls are moved from the top bar to improve readability."
        )
        appearance_note.setObjectName("mutedText")
        appearance_note.setWordWrap(True)
        appearance.add_widget(appearance_note)
        main_grid.addWidget(appearance, 0, 0)

        filters = DashboardPanel("Filter Parameters")
        filters_form = QFormLayout(); filters_form.setHorizontalSpacing(16); filters_form.setVerticalSpacing(8)
        self.imu_alpha_spin = QDoubleSpinBox(); self.imu_alpha_spin.setRange(0.05, 0.95); self.imu_alpha_spin.setSingleStep(0.05); self.imu_alpha_spin.setValue(self.imu_alpha)
        self.link_alpha_spin = QDoubleSpinBox(); self.link_alpha_spin.setRange(0.05, 0.95); self.link_alpha_spin.setSingleStep(0.05); self.link_alpha_spin.setValue(self.link_alpha)
        self.avg_window_spin = QSpinBox(); self.avg_window_spin.setRange(2, 25); self.avg_window_spin.setValue(self.avg_window)
        self.median_window_spin = QSpinBox(); self.median_window_spin.setRange(3, 11); self.median_window_spin.setSingleStep(2); self.median_window_spin.setValue(self.median_window)
        filters_form.addRow("IMU low-pass alpha:", self.imu_alpha_spin)
        filters_form.addRow("Link smooth alpha:", self.link_alpha_spin)
        filters_form.addRow("Average window:", self.avg_window_spin)
        filters_form.addRow("Median window:", self.median_window_spin)
        filters.add_layout(filters_form)
        main_grid.addWidget(filters, 0, 1)

        thresholds = DashboardPanel("Thresholds")
        thr_form = QFormLayout(); thr_form.setHorizontalSpacing(16); thr_form.setVerticalSpacing(8)
        self.obstacle_warning_spin = QSpinBox(); self.obstacle_warning_spin.setRange(10, 200); self.obstacle_warning_spin.setValue(self.obstacle_warning_cm)
        self.obstacle_danger_spin = QSpinBox(); self.obstacle_danger_spin.setRange(5, 150); self.obstacle_danger_spin.setValue(self.obstacle_danger_cm)
        self.batt_warning_spin = QDoubleSpinBox(); self.batt_warning_spin.setRange(5.0, 8.4); self.batt_warning_spin.setSingleStep(0.1); self.batt_warning_spin.setValue(self.battery_warning_v)
        self.batt_danger_spin = QDoubleSpinBox(); self.batt_danger_spin.setRange(5.0, 8.4); self.batt_danger_spin.setSingleStep(0.1); self.batt_danger_spin.setValue(self.battery_danger_v)
        thr_form.addRow("Obstacle warning (cm):", self.obstacle_warning_spin)
        thr_form.addRow("Obstacle danger (cm):", self.obstacle_danger_spin)
        thr_form.addRow("Battery warning (V):", self.batt_warning_spin)
        thr_form.addRow("Battery danger (V):", self.batt_danger_spin)
        thresholds.add_layout(thr_form)
        main_grid.addWidget(thresholds, 1, 0)

        system = DashboardPanel("System")
        sys_form = QFormLayout(); sys_form.setHorizontalSpacing(16); sys_form.setVerticalSpacing(8)
        self.history_spin = QSpinBox(); self.history_spin.setRange(60, 500); self.history_spin.setValue(self.plot_history)
        self.refresh_spin = QSpinBox(); self.refresh_spin.setRange(100, 1000); self.refresh_spin.setSingleStep(50); self.refresh_spin.setValue(self.update_interval_ms)
        self.com_port_edit = QLineEdit("COM3")
        self.baud_edit = QLineEdit("115200")
        self.operator_edit = QLineEdit("Team 3")
        self.experiment_edit = QLineEdit("MarsRover-Session-01")
        self.config_version_edit = QLineEdit("cfg-v1")
        self.encrypt_checkbox = QCheckBox("Enable protocol encryption")
        self.encrypt_checkbox.setChecked(is_encryption_enabled())
        self.encryption_mode_runtime_label = QLabel(encryption_mode_name())
        sys_form.addRow("Plot history:", self.history_spin)
        sys_form.addRow("Refresh interval (ms):", self.refresh_spin)
        sys_form.addRow("Default COM port:", self.com_port_edit)
        sys_form.addRow("Default baud:", self.baud_edit)
        sys_form.addRow("Operator:", self.operator_edit)
        sys_form.addRow("Experiment ID:", self.experiment_edit)
        sys_form.addRow("Config Version:", self.config_version_edit)
        sys_form.addRow("Encryption:", self.encrypt_checkbox)
        sys_form.addRow("Method:", self.encryption_mode_runtime_label)
        system.add_layout(sys_form)
        main_grid.addWidget(system, 1, 1)

        live_controls = DashboardPanel("Live Display Controls")
        live_form = QFormLayout(); live_form.setHorizontalSpacing(16); live_form.setVerticalSpacing(8)
        self.view_combo = QComboBox(); self.view_combo.addItems(["Simple", "Advanced"]); self.view_combo.setCurrentText(self.view_mode)
        self.theme_combo = QComboBox(); self.theme_combo.addItems(["Dark Blue", "Light Blue", "Matrix Dark", "Amber Terminal"]); self.theme_combo.setCurrentText(self.theme_name)
        self.signal_view_combo = QComboBox(); self.signal_view_combo.addItems(["Raw", "Filtered", "Overlay"]); self.signal_view_combo.setCurrentText(self.signal_view)
        self.precision_combo = QComboBox(); self.precision_combo.addItems(["Simple", "Precise"]); self.precision_combo.setCurrentText(self.decimal_mode)
        self.reset_button = QPushButton("Reset")
        self.reset_button.setObjectName("resetButton")
        self.reset_button.setMinimumHeight(34)
        live_form.addRow("View (Global):", self.view_combo)
        live_form.addRow("Theme:", self.theme_combo)
        live_form.addRow("Signal View:", self.signal_view_combo)
        live_form.addRow("Decimals:", self.precision_combo)
        live_controls.add_layout(live_form)
        live_controls.add_widget(self.reset_button)
        main_grid.addWidget(live_controls, 0, 2, 2, 1)
        main_grid.setColumnStretch(0, 1)
        main_grid.setColumnStretch(1, 1)
        main_grid.setColumnStretch(2, 1)

        save_btn = QPushButton("Apply Settings")
        body_layout.addWidget(save_btn)
        self.apply_settings_button = save_btn
        body_layout.addStretch(1)

    def _apply_responsive_layout(self):
        compact_w, compact_h = self.ui_profile.compact_mode_threshold
        compact = self.width() < compact_w or self.height() < compact_h
        horizontal_policy = (
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if compact else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        page_min_width = self.ui_profile.panel_min_widths

        if hasattr(self, "dashboard_page_body"):
            self.dashboard_page_body.setMinimumWidth(page_min_width.get("dashboard", 1500) if compact else 0)
            self.dashboard_scroll.setHorizontalScrollBarPolicy(horizontal_policy)
            self.dashboard_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        if hasattr(self, "telemetry_page_body"):
            self.telemetry_page_body.setMinimumWidth(page_min_width.get("telemetry", 1280) if compact else 0)
            self.telemetry_scroll.setHorizontalScrollBarPolicy(horizontal_policy)
            self.telemetry_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        if hasattr(self, "system_page_body"):
            self.system_page_body.setMinimumWidth(page_min_width.get("system", 1360) if compact else 0)
            self.system_scroll.setHorizontalScrollBarPolicy(horizontal_policy)
            self.system_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        if hasattr(self, "settings_page_body"):
            self.settings_page_body.setMinimumWidth(page_min_width.get("settings", 1360) if compact else 0)
            self.settings_scroll.setHorizontalScrollBarPolicy(horizontal_policy)
            self.settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        if hasattr(self, "sensor_grid_layout"):
            self._relayout_system_sensor_grid(self._recommended_sensor_columns())

    def _recommended_sensor_columns(self) -> int:
        if not hasattr(self, "sensor_health_panel"):
            return 1
        panel_width = self.sensor_health_panel.width() if self.sensor_health_panel.width() > 0 else self.width()
        if hasattr(self, "sensor_table_scroll"):
            viewport_w = self.sensor_table_scroll.viewport().width()
            if viewport_w > 0:
                panel_width = viewport_w

        if panel_width >= 760:
            cols = 3
        elif panel_width >= 440:
            cols = 2
        else:
            cols = 1

        # Tight-height fallback: increase columns to avoid clipping the last row.
        if hasattr(self, "sensor_cell_widgets") and hasattr(self, "sensor_table_scroll"):
            viewport_h = self.sensor_table_scroll.viewport().height()
            if viewport_h > 0:
                row_count = (len(self.sensor_cell_widgets) + cols - 1) // cols
                est_row_height = 34
                if row_count * est_row_height > max(120, viewport_h - 6) and cols < 3 and panel_width >= 620:
                    cols += 1
        return cols

    def _relayout_system_sensor_grid(self, columns: int):
        if not hasattr(self, "sensor_grid_layout") or not hasattr(self, "sensor_cell_widgets"):
            return
        cols = max(1, min(3, columns))
        while self.sensor_grid_layout.count():
            item = self.sensor_grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
        for index, row_widget in enumerate(self.sensor_cell_widgets):
            row = index // cols
            col = index % cols
            self.sensor_grid_layout.addWidget(row_widget, row, col)
        for col in range(cols):
            self.sensor_grid_layout.setColumnStretch(col, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _create_connection_panel(self) -> DashboardPanel:
        panel = DashboardPanel("Connection")
        panel.setFixedWidth(330)
        panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        form = QFormLayout(); form.setHorizontalSpacing(12); form.setVerticalSpacing(8)
        self.port_combo = QComboBox(); self.port_combo.addItems(["COM3", "COM4", "COM5"])
        self.baud_combo = QComboBox(); self.baud_combo.addItems(["9600", "57600", "115200"])
        self.data_source_combo = QComboBox(); self.data_source_combo.addItems(["Live", "Replay"])
        form.addRow("Port:", self.port_combo)
        form.addRow("Baud:", self.baud_combo)
        form.addRow("Source:", self.data_source_combo)
        panel.add_layout(form)
        row = QHBoxLayout(); row.setSpacing(8)
        self.connect_button = QPushButton("Connect"); self.connect_button.setObjectName("connectButton")
        self.disconnect_button = QPushButton("Disconnect"); self.disconnect_button.setObjectName("disconnectButton")
        self.connect_button.setMinimumHeight(32)
        self.disconnect_button.setMinimumHeight(32)
        row.addWidget(self.connect_button)
        row.addWidget(self.disconnect_button)
        panel.add_layout(row)
        replay_controls = QHBoxLayout(); replay_controls.setSpacing(6)
        self.replay_play_button = QPushButton("Play")
        self.replay_pause_button = QPushButton("Pause")
        self.replay_stop_button = QPushButton("Stop")
        self.replay_speed_combo = QComboBox(); self.replay_speed_combo.addItems(["0.5x", "1.0x", "2.0x"]); self.replay_speed_combo.setCurrentText("1.0x")
        for btn in [self.replay_play_button, self.replay_pause_button, self.replay_stop_button]:
            btn.setMinimumHeight(30)
            btn.setMinimumWidth(64)
        self.replay_speed_combo.setMinimumWidth(70)
        replay_controls.addWidget(self.replay_play_button)
        replay_controls.addWidget(self.replay_pause_button)
        replay_controls.addWidget(self.replay_stop_button)
        replay_controls.addWidget(self.replay_speed_combo)
        panel.add_layout(replay_controls)
        self.replay_status_label = QLabel("Replay: idle")
        self.replay_status_label.setObjectName("mutedText")
        self.replay_status_label.setWordWrap(True)
        panel.add_widget(self.replay_status_label)
        self.connection_hint = QLabel("Use Connect to start telemetry.")
        self.connection_hint.setObjectName("mutedText")
        self.connection_hint.setWordWrap(True)
        panel.add_widget(self.connection_hint)
        return panel

    def _create_control_panel(self) -> DashboardPanel:
        panel = DashboardPanel("Rover Control")
        panel.setFixedWidth(330)
        panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        grid = QGridLayout(); grid.setHorizontalSpacing(4); grid.setVerticalSpacing(4)
        self.btn_forward = QPushButton("↑")
        self.btn_left = QPushButton("←")
        self.btn_stop = QPushButton("STOP")
        self.btn_estop = QPushButton("E-STOP")
        self.btn_right = QPushButton("→")
        self.btn_back = QPushButton("↓")
        for btn in [self.btn_forward, self.btn_left, self.btn_stop, self.btn_estop, self.btn_right, self.btn_back]:
            btn.setMinimumHeight(34)
        self.btn_stop.setMinimumWidth(84)
        self.btn_estop.setObjectName("disconnectButton")
        grid.addWidget(self.btn_forward, 0, 1)
        grid.addWidget(self.btn_left, 1, 0)
        grid.addWidget(self.btn_stop, 1, 1)
        grid.addWidget(self.btn_right, 1, 2)
        grid.addWidget(self.btn_back, 2, 1)
        grid.addWidget(self.btn_estop, 3, 0, 1, 3)
        panel.add_layout(grid)

        speed_title = QLabel("Speed")
        speed_title.setObjectName("valueStrong")
        panel.add_widget(speed_title)
        row = QHBoxLayout(); row.setSpacing(8)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal); self.speed_slider.setRange(0, 100); self.speed_slider.setValue(45)
        self.speed_label = QLabel("45%")
        self.speed_label.setObjectName("valueStrong")
        row.addWidget(self.speed_slider); row.addWidget(self.speed_label)
        panel.add_layout(row)
        self.control_shortcut_hint = QLabel("Keyboard: W/A/S/D move, Space stop")
        self.control_shortcut_hint.setObjectName("mutedText")
        panel.add_widget(self.control_shortcut_hint)
        return panel

    def _create_status_panel(self) -> DashboardPanel:
        panel = DashboardPanel("Rover Status")
        panel.setFixedWidth(280)
        panel.setMinimumHeight(150)
        form = QFormLayout(); form.setHorizontalSpacing(14); form.setVerticalSpacing(8)
        self.state_label = QLabel()
        self.mode_label = QLabel()
        self.command_label = QLabel()
        self.speed_state_label = QLabel()
        form.addRow("State:", self.state_label)
        form.addRow("Mode:", self.mode_label)
        form.addRow("Command:", self.command_label)
        form.addRow("Speed:", self.speed_state_label)
        panel.add_layout(form)
        return panel

    def _create_link_panel(self) -> DashboardPanel:
        panel = DashboardPanel("Link Quality")
        panel.setMinimumHeight(248)
        panel.body_layout().setSpacing(8)
        self.rssi_value = QLabel(); self.rssi_value.setObjectName("valueStrong")
        self.snr_value = QLabel(); self.snr_value.setObjectName("valueStrong")
        self.packet_rate_value = QLabel(); self.packet_rate_value.setObjectName("valueStrong")
        self.packet_loss_badge = QLabel("Loss --")
        self.packet_loss_badge.setObjectName("statusPill")
        self.link_offline_label = QLabel("No connection")
        self.link_offline_label.setObjectName("mutedText")
        panel.add_widget(self.rssi_value)
        self.rssi_bar = TelemetryBar(); panel.add_widget(self.rssi_bar)
        panel.add_widget(self.snr_value)
        self.snr_hint = QLabel(); self.snr_hint.setObjectName("mutedText")
        panel.add_widget(self.snr_hint)
        row = QHBoxLayout()
        row.addWidget(self.packet_rate_value, 1)
        row.addWidget(self.packet_loss_badge, 0)
        panel.add_layout(row)
        panel.add_widget(self.link_offline_label)
        return panel

    def _create_environment_panel(self) -> DashboardPanel:
        panel = DashboardPanel("Environmental Telemetry")
        panel.setMinimumHeight(248)
        panel.body_layout().setSpacing(8)
        self.batt_value = QLabel(); self.batt_value.setObjectName("valueStrong")
        self.batt_bar = TelemetryBar()
        self.current_value = QLabel()
        self.temp_value = QLabel()
        self.humidity_value = QLabel()
        self.thermistor_value = QLabel()
        panel.add_widget(self.batt_value)
        panel.add_widget(self.batt_bar)
        panel.add_widget(self.current_value)
        panel.add_widget(self.temp_value)
        panel.add_widget(self.humidity_value)
        panel.add_widget(self.thermistor_value)
        return panel

    def _create_sensor_panel(self) -> DashboardPanel:
        panel = DashboardPanel("Sensor Indicators")
        panel.setMinimumHeight(248)
        panel.add_widget(SensorIndicatorRow.make_header(panel))
        self.sensor_rows = {
            "IMU": SensorIndicatorRow("IMU"),
            "Ultrasonic": SensorIndicatorRow("Ultrasonic"),
            "Battery": SensorIndicatorRow("Battery"),
            "Humidity": SensorIndicatorRow("Humidity"),
            "Thermistor": SensorIndicatorRow("Thermistor"),
            "LoRa": SensorIndicatorRow("LoRa Link"),
            "SD": SensorIndicatorRow("SD Logger"),
        }
        for row in self.sensor_rows.values():
            panel.add_widget(row)
        return panel

    def _create_imu_panel(self, compact: bool) -> DashboardPanel:
        panel = DashboardPanel("IMU / Motion")
        self.imu_canvas = self._make_plot_canvas()
        panel.add_widget(self.imu_canvas, 1)
        self.imu_style_hint = QLabel("")
        self.imu_style_hint.setObjectName("mutedText")
        self.imu_style_hint.setFixedHeight(4)
        panel.add_widget(self.imu_style_hint)
        if compact:
            panel.setMinimumHeight(360)
        return panel

    def _create_obstacle_panel(self, compact: bool = False) -> DashboardPanel:
        panel = DashboardPanel("Front Obstacle Detection")
        panel.setFixedWidth(280)
        panel.setMinimumHeight(122 if compact else 150)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        self.front_distance_value = QLabel()
        self.front_distance_value.setObjectName("obstacleDistance")
        self.front_status_value = QLabel("GOOD")
        self.front_status_value.setObjectName("obstacleBadge")
        self.front_status_value.setFixedWidth(90)
        self.front_status_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(self.front_distance_value, 1)
        top_row.addWidget(self.front_status_value, 0)

        self.front_bar = ConvergingBar()
        self.front_bar.setMinimumHeight(16)
        self.front_bar.setMaximumHeight(16)
        panel.add_layout(top_row)
        panel.add_widget(self.front_bar)
        return panel

    def _create_alert_panel(self) -> DashboardPanel:
        panel = DashboardPanel("Alerts")
        panel.setMaximumHeight(110)
        row = QHBoxLayout()
        row.setContentsMargins(0,0,0,0)
        row.setSpacing(8)
        self.alert_strip = QFrame()
        self.alert_strip.setFixedWidth(8)
        self.alert_strip.setObjectName("alertStrip")
        self.alert_strip.setStyleSheet("background-color:#59e05d; border-radius:5px;")
        self.alert_label = QLabel("Nominal")
        self.alert_label.setWordWrap(False)
        self.alert_label.setObjectName("valueStrong")
        self.alert_label.setMinimumHeight(28)
        row.addWidget(self.alert_strip)
        row.addWidget(self.alert_label, 1)
        panel.add_layout(row)
        return panel

    def _create_quick_diag_panel(self) -> DashboardPanel:
        panel = DashboardPanel("Quick Diagnostics")
        panel.setMaximumHeight(140)
        panel.body_layout().setSpacing(4)
        self.quick_link_state = QLabel()
        self.quick_sample_state = QLabel()
        self.quick_timeout_state = QLabel()
        panel.add_widget(self.quick_link_state)
        panel.add_widget(self.quick_sample_state)
        panel.add_widget(self.quick_timeout_state)
        return panel

    def _make_plot_canvas(self) -> MplCanvas:
        theme = get_theme(self.theme_name)
        canvas = MplCanvas(theme["plot_bg"], theme["text"])
        return canvas

    # ---------- Bindings ----------
    def _bind_events(self):
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.view_combo.currentTextChanged.connect(self.on_view_changed)
        self.page_mode_combo.currentTextChanged.connect(self.on_view_changed)
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        self.signal_view_combo.currentTextChanged.connect(self.on_signal_view_changed)
        self.precision_combo.currentTextChanged.connect(self.on_precision_mode_changed)
        self.reset_button.clicked.connect(self.reset_dashboard_state)
        self.connect_button.clicked.connect(self.connect_rover)
        self.disconnect_button.clicked.connect(self.disconnect_rover)
        self.data_source_combo.currentTextChanged.connect(self.on_data_source_changed)
        self.replay_play_button.clicked.connect(self.start_replay)
        self.replay_pause_button.clicked.connect(self.pause_replay)
        self.replay_stop_button.clicked.connect(self.stop_replay)
        self.speed_slider.valueChanged.connect(lambda v: self.speed_label.setText(f"{v}%"))
        self.btn_forward.clicked.connect(lambda: self.send_command("FORWARD"))
        self.btn_left.clicked.connect(lambda: self.send_command("LEFT"))
        self.btn_stop.clicked.connect(lambda: self.send_command("STOP"))
        self.btn_estop.clicked.connect(self.trigger_estop)
        self.btn_right.clicked.connect(lambda: self.send_command("RIGHT"))
        self.btn_back.clicked.connect(lambda: self.send_command("BACKWARD"))
        self.logging_toggle_button.clicked.connect(self.toggle_logging)
        self.export_metadata_button.clicked.connect(self.save_metadata)
        self.apply_settings_button.clicked.connect(self.apply_settings_from_page)
        self.telemetry_imu_filter_combo.currentTextChanged.connect(self.set_imu_filter)
        self.telemetry_ultra_filter_combo.currentTextChanged.connect(self.set_ultra_filter)
        self.telemetry_link_filter_combo.currentTextChanged.connect(self.set_link_filter)
        self.encrypt_checkbox.toggled.connect(self.on_encryption_toggled)
        self.events_all_btn.clicked.connect(lambda: self.set_event_filter("all"))
        self.events_warn_btn.clicked.connect(lambda: self.set_event_filter("warning"))
        self.events_error_btn.clicked.connect(lambda: self.set_event_filter("error"))
        self.ack_alerts_button.clicked.connect(self.acknowledge_alerts)
        self.set_event_filter("all")
        self.on_data_source_changed(self.data_source_combo.currentText())
        self._refresh_encryption_labels()
        self.on_view_changed(self.view_mode)
        self._refresh_active_alerts_view()

    # ---------- Actions ----------
    def connect_rover(self):
        if self.data_source_combo.currentText() == "Replay":
            self.start_replay()
            return
        port = self.port_combo.currentText()
        baud = int(self.baud_combo.currentText())
        self.set_rover_state(RoverState.CONNECTED)
        self.worker_start.emit(port, baud)
        self.record_event("info", "ui", "CONNECT_REQ", f"Connect requested {port}@{baud}")

    def disconnect_rover(self):
        if self.data_source_combo.currentText() == "Replay":
            self.stop_replay()
            return
        self.worker_stop.emit()
        self.pending_commands.clear()
        self.current_command = "STOP"
        self.set_rover_state(RoverState.DISCONNECTED)
        self.record_event("warning", "ui", "DISCONNECT_REQ", "Disconnect requested")

    def send_command(self, command: str):
        if self.data_source_combo.currentText() == "Replay":
            self.status_message.emit("Replay mode: movement commands are disabled.")
            return
        if not self.connected or self.rover_state == RoverState.DISCONNECTED:
            self.status_message.emit("Connect rover before sending movement commands.")
            return
        if self.rover_state in {RoverState.ESTOP, RoverState.FAULT} and command not in {"STOP"}:
            self.status_message.emit("Command blocked while rover is in ESTOP/FAULT.")
            return
        self.current_command = command
        cmd_name = {
            "FORWARD": "FWD",
            "BACKWARD": "BACK",
            "LEFT": "LEFT",
            "RIGHT": "RIGHT",
            "STOP": "STOP",
            "ESTOP": "ESTOP",
        }.get(command, command)
        self.command_counter += 1
        frame = CommandFrame(
            cmd_id=self.command_counter,
            name=cmd_name,
            params={"speed_percent": int(self.speed_slider.value())},
            deadline_ms=1200,
        )
        self.pending_commands[frame.cmd_id] = frame
        self.command_outbound.emit(frame)
        self.status_message.emit(f"Command queued: {cmd_name} #{frame.cmd_id}")
        self.record_event("info", "command", "CMD_SENT", f"{cmd_name} queued", {"cmd_id": frame.cmd_id})
        buttons = {
            "FORWARD": self.btn_forward,
            "LEFT": self.btn_left,
            "STOP": self.btn_stop,
            "RIGHT": self.btn_right,
            "BACKWARD": self.btn_back,
        }
        for btn in [self.btn_forward, self.btn_left, self.btn_stop, self.btn_right, self.btn_back]:
            btn.setProperty("activeDirection", False)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if command in buttons:
            buttons[command].setProperty("activeDirection", True)
            buttons[command].style().unpolish(buttons[command])
            buttons[command].style().polish(buttons[command])
        if command in {"FORWARD", "BACKWARD", "LEFT", "RIGHT"}:
            self.set_rover_state(RoverState.RUNNING)
        elif command == "STOP":
            if self.rover_state == RoverState.ESTOP:
                self.set_rover_state(RoverState.CONNECTED)
                self.push_alert("E-STOP cleared", "info")
                self.record_event("info", "safety", "ESTOP_CLEAR", "Emergency stop cleared by operator")
            elif self.rover_state == RoverState.RUNNING:
                self.set_rover_state(RoverState.CONNECTED)

    def trigger_estop(self):
        if self.rover_state == RoverState.ESTOP:
            self.send_command("STOP")
            return
        self.send_command("ESTOP")
        self.set_rover_state(RoverState.ESTOP)
        self.push_alert("Emergency stop activated", "danger")
        self.record_event("danger", "safety", "ESTOP", "Emergency stop activated")

    def on_data_source_changed(self, text: str):
        replay_mode = text == "Replay"
        if replay_mode and self.connected and self.serial_state.startswith("Connected @"):
            self.worker_stop.emit()
            self.pending_commands.clear()
            self.set_rover_state(RoverState.DISCONNECTED)
        self.replay_play_button.setEnabled(replay_mode)
        self.replay_pause_button.setEnabled(replay_mode)
        self.replay_stop_button.setEnabled(replay_mode)
        self.replay_speed_combo.setEnabled(replay_mode)
        self.port_combo.setEnabled(not replay_mode)
        self.baud_combo.setEnabled(not replay_mode)
        self.connect_button.setText("Start Replay" if replay_mode else "Connect")
        self.disconnect_button.setText("Stop Replay" if replay_mode else "Disconnect")
        if not replay_mode and self.replay_playing:
            self.stop_replay()
        if replay_mode:
            self.connection_hint.setText("Replay source: session_logs CSV")
        elif not self.connected:
            self.connection_hint.setText("Disconnected. Press Connect to start telemetry.")

    def _replay_speed_factor(self) -> float:
        text = self.replay_speed_combo.currentText().lower().replace("x", "").strip()
        try:
            value = float(text)
        except ValueError:
            value = 1.0
        return max(0.25, min(4.0, value))

    def _load_replay_frames(self):
        path = Path(self.log_file_path)
        if not path.exists():
            self.status_message.emit(f"Replay file not found: {path}")
            return
        frames: list[TelemetryFrame] = []
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            for idx, row in enumerate(reader):
                ts_text = row.get("timestamp", "").strip()
                try:
                    ts = datetime.strptime(ts_text, "%Y-%m-%d %H:%M:%S.%f").timestamp() if ts_text else float(idx)
                except ValueError:
                    ts = float(idx)
                ax = float(row.get("ax_g", 0.0))
                ay = float(row.get("ay_g", 0.0))
                az = float(row.get("az_g", 1.0))
                mag = float(row.get("magnitude_g", 1.0))
                frame = TelemetryFrame(
                    timestamp=ts,
                    seq=idx,
                    rssi=-86.0,
                    snr=10.0,
                    packet_loss=0.0,
                    batt_v=max(6.2, 7.4 - idx * 0.0008),
                    imu=(ax, ay, az, mag),
                    distance_cm=max(8.0, 50.0 - (mag - 1.0) * 20.0),
                    humidity=48.0,
                    thermistor_c=24.0,
                    status_bits=0,
                    protocol_version=self.protocol_version,
                )
                frames.append(frame)
        self.replay_frames = frames
        self.replay_index = 0
        self.replay_status_label.setText(f"Replay: loaded {len(frames)} frames")
        self.record_event("info", "replay", "REPLAY_LOADED", f"Loaded {len(frames)} frames")

    def start_replay(self):
        if self.data_source_combo.currentText() != "Replay":
            return
        if not self.replay_frames:
            self._load_replay_frames()
        if not self.replay_frames:
            return
        if self.replay_index >= len(self.replay_frames):
            self.replay_index = 0
        self.replay_playing = True
        self.set_rover_state(RoverState.CONNECTED)
        self.serial_state = "Replay mode"
        self.connected = True
        self._refresh_interaction_state()
        self.replay_status_label.setText(f"Replay: playing {self.replay_index + 1}/{len(self.replay_frames)}")
        self.record_event("info", "replay", "REPLAY_PLAY", "Replay started")
        self._on_replay_tick()

    def pause_replay(self):
        if not self.replay_playing:
            return
        self.replay_playing = False
        self.replay_timer.stop()
        self.replay_status_label.setText(f"Replay: paused {self.replay_index}/{len(self.replay_frames)}")
        self.record_event("info", "replay", "REPLAY_PAUSE", "Replay paused")

    def stop_replay(self):
        self.replay_playing = False
        self.replay_timer.stop()
        self.replay_index = 0
        if self.data_source_combo.currentText() == "Replay":
            self.set_rover_state(RoverState.DISCONNECTED)
            self.connected = False
            self.serial_state = "Replay stopped"
        self._refresh_interaction_state()
        total = len(self.replay_frames)
        self.replay_status_label.setText(f"Replay: stopped 0/{total}")
        self.record_event("warning", "replay", "REPLAY_STOP", "Replay stopped")

    def _on_replay_tick(self):
        if not self.replay_playing or self.data_source_combo.currentText() != "Replay":
            return
        if self.replay_index >= len(self.replay_frames):
            self.pause_replay()
            self.replay_status_label.setText(f"Replay: completed {len(self.replay_frames)}/{len(self.replay_frames)}")
            self.record_event("info", "replay", "REPLAY_END", "Replay completed")
            return
        frame = self.replay_frames[self.replay_index]
        self.replay_index += 1
        self.on_telemetry_received(frame)
        self.replay_status_label.setText(f"Replay: playing {self.replay_index}/{len(self.replay_frames)}")
        if self.replay_index >= len(self.replay_frames):
            self.pause_replay()
            self.replay_status_label.setText(f"Replay: completed {len(self.replay_frames)}/{len(self.replay_frames)}")
            self.record_event("info", "replay", "REPLAY_END", "Replay completed")
            return
        curr = frame.timestamp
        nxt = self.replay_frames[self.replay_index].timestamp
        dt_ms = max(60, min(800, int((nxt - curr) * 1000)))
        interval = max(40, int(dt_ms / self._replay_speed_factor()))
        self.replay_timer.start(interval)

    def on_encryption_toggled(self, checked: bool):
        set_encryption_enabled(checked)
        # Keep system/status labels in sync with protocol runtime mode.
        self._refresh_encryption_labels()
        mode = encryption_mode_name()
        self.record_event("info", "protocol", "ENC_MODE", f"Encryption mode set to {mode}")

    def _refresh_encryption_labels(self):
        enabled = is_encryption_enabled()
        mode = encryption_mode_name()
        if hasattr(self, "encryption_state_label"):
            self.encryption_state_label.setText("Enabled" if enabled else "Disabled")
        if hasattr(self, "encryption_method_label"):
            self.encryption_method_label.setText(mode)
        if hasattr(self, "encryption_mode_runtime_label"):
            self.encryption_mode_runtime_label.setText(mode)

    def on_protocol_trace(self, kind: str, raw_hex: str, decoded_json: str):
        self._latest_protocol_kind = kind
        self._latest_protocol_raw = raw_hex
        self._latest_protocol_decoded_raw = decoded_json
        self._latest_protocol_decoded = self._format_decoded_json_for_display(kind, decoded_json)
        self._pending_protocol_refresh = True

    def on_link_state_changed(self, connected: bool, detail: str):
        self.connected = connected
        self.serial_state = detail
        self.last_packet_age_ms = 0
        if connected:
            if self.rover_state == RoverState.DISCONNECTED:
                self.set_rover_state(RoverState.CONNECTED)
            self.status_message.emit("Connected to rover link.")
        else:
            self.set_rover_state(RoverState.DISCONNECTED)
            self.status_message.emit("Disconnected from rover link.")
        self._refresh_interaction_state()

    def on_worker_event(self, level: str, source: str, code: str, payload: object):
        message = str(payload)
        if source == "protocol" and code in {"CMD_PARSE_FAIL", "TELEM_PARSE_FAIL"}:
            self.parse_errors += 1
        self.record_event(level, source, code, message, {"payload": message})
        if level in {"warning", "danger"}:
            self.push_alert(message, "danger" if level == "danger" else "warning")

    def on_ack_received(self, cmd_id: int, latency_ms: float):
        frame = self.pending_commands.pop(cmd_id, None)
        self.last_ack_latency_ms = latency_ms
        self.ack_latency_samples.append(latency_ms)
        self.avg_ack_latency_ms = sum(self.ack_latency_samples) / len(self.ack_latency_samples)
        if frame:
            self.record_event("info", "command", "CMD_ACK", f"ACK {frame.name} #{cmd_id}", {"latency_ms": latency_ms})

    def on_telemetry_received(self, frame: object):
        if not isinstance(frame, TelemetryFrame):
            return
        if frame.protocol_version != self.protocol_version:
            self.parse_errors += 1
            self.record_event(
                "warning",
                "protocol",
                "VERSION_MISMATCH",
                f"Telemetry version {frame.protocol_version} != GUI {self.protocol_version}",
            )
            return
        self.last_rx_monotonic = time.time()
        self.last_packet_age_ms = 0
        self.packet_counter += 1
        self.raw_rssi.append(frame.rssi)
        self.raw_snr.append(frame.snr)
        self.raw_batt_v.append(frame.batt_v)
        self.raw_front_cm.append(frame.distance_cm)
        self.raw_humidity.append(frame.humidity)
        self.raw_thermistor.append(frame.thermistor_c)
        ax, ay, az, mag = frame.imu
        self.raw_x.append(ax); self.raw_y.append(ay); self.raw_z.append(az); self.raw_mag.append(mag)
        self.raw_log_mag.append(mag)
        self.dropped_packets = int((frame.packet_loss / 100.0) * max(1, self.packet_counter))

        self.lp_x = self.low_pass(ax, self.lp_x, self.imu_alpha)
        self.lp_y = self.low_pass(ay, self.lp_y, self.imu_alpha)
        self.lp_z = self.low_pass(az, self.lp_z, self.imu_alpha)
        self.lp_mag = self.low_pass(mag, self.lp_mag, self.imu_alpha)
        self.lp_rssi = self.low_pass(frame.rssi, self.lp_rssi, self.link_alpha)
        self.lp_batt = self.low_pass(frame.batt_v, self.lp_batt, 0.12)
        self.lp_front = self.low_pass(frame.distance_cm, self.lp_front, 0.18)
        self.lp_humidity = self.low_pass(frame.humidity, self.lp_humidity, 0.16)
        self.lp_thermistor = self.low_pass(frame.thermistor_c, self.lp_thermistor, 0.14)

        if self.logging_enabled:
            log_accelerometer_to_csv(self.log_file_path, ax, ay, az, mag)
            self.samples_logged += 1

        if frame.batt_v <= self.battery_danger_v and self.rover_state == RoverState.RUNNING:
            self.set_rover_state(RoverState.FAULT)
            self.push_alert(f"Battery critical: {frame.batt_v:.2f} V", "danger")
            self.send_command("STOP")

        alert = self.evaluate_system_alert(frame.distance_cm, frame.batt_v, frame.rssi)
        if alert:
            self.system_alert = alert
            self.status_message.emit(alert)
        else:
            self.system_alert = "Nominal"

    def toggle_logging(self):
        self.logging_enabled = not self.logging_enabled
        self.logging_toggle_button.setText("Stop Logging" if self.logging_enabled else "Start Logging")
        self.status_message.emit("Logging enabled." if self.logging_enabled else "Logging paused.")
        self.refresh_all_views()

    def save_metadata(self):
        metadata = {
            "protocol_version": self.protocol_version,
            "rover_state": self.rover_state.value,
            "theme": self.theme_name,
            "view_mode": self.view_mode,
            "signal_view": self.signal_view,
            "decimal_mode": self.decimal_mode,
            "imu_filter": self.imu_filter,
            "ultrasonic_filter": self.ultra_filter,
            "link_filter": self.link_filter,
            "update_interval_ms": self.update_interval_ms,
            "operator": self.operator_edit.text().strip(),
            "experiment_id": self.experiment_edit.text().strip(),
            "config_version": self.config_version_edit.text().strip(),
            "notes": self.session_notes.toPlainText().strip(),
            "csv_file": self.log_file_path,
            "pending_commands": len(self.pending_commands),
            "event_records": len(self.event_records),
            "samples_logged": self.samples_logged,
        }
        write_session_metadata(self.metadata_path, metadata)
        self.status_message.emit(f"Session metadata saved to {self.metadata_path}")
        self.refresh_all_views()

    def apply_settings_from_page(self):
        if self.obstacle_danger_spin.value() >= self.obstacle_warning_spin.value():
            self.status_message.emit("Obstacle danger threshold must be lower than warning threshold.")
            return
        if self.batt_danger_spin.value() >= self.batt_warning_spin.value():
            self.status_message.emit("Battery danger threshold must be lower than warning threshold.")
            return
        self.imu_alpha = float(self.imu_alpha_spin.value())
        self.link_alpha = float(self.link_alpha_spin.value())
        self.avg_window = int(self.avg_window_spin.value())
        self.median_window = int(self.median_window_spin.value())
        self.obstacle_warning_cm = int(self.obstacle_warning_spin.value())
        self.obstacle_danger_cm = int(self.obstacle_danger_spin.value())
        self.battery_warning_v = float(self.batt_warning_spin.value())
        self.battery_danger_v = float(self.batt_danger_spin.value())
        self.plot_history = int(self.history_spin.value())
        self.update_interval_ms = int(self.refresh_spin.value())
        self.dashboard_timer.setInterval(max(300, min(400, self.update_interval_ms)))
        self.imu_plot_timer.setInterval(400)
        self.secondary_plot_timer.setInterval(650)
        self.system_timer.setInterval(1000)
        self.health_timer.setInterval(1000)
        self._sync_connection_settings()
        self.status_message.emit("Settings applied.")
        self.refresh_visible_views_only()

    def set_imu_filter(self, text: str):
        self.imu_filter = text
        self.status_message.emit(f"IMU filter set to {text}.")

    def set_ultra_filter(self, text: str):
        self.ultra_filter = text
        self.status_message.emit(f"Obstacle filter set to {text}.")

    def set_link_filter(self, text: str):
        self.link_filter = text
        self.status_message.emit(f"Link filter set to {text}.")

    def set_event_filter(self, mode: str):
        self.event_filter = mode
        self.events_all_btn.setChecked(mode == "all")
        self.events_warn_btn.setChecked(mode == "warning")
        self.events_error_btn.setChecked(mode == "error")
        self.refresh_event_log()

    def _is_advanced_view(self) -> bool:
        return self.view_mode == "Advanced"

    def _set_visible_if_exists(self, attr_name: str, visible: bool):
        widget = getattr(self, attr_name, None)
        if isinstance(widget, QWidget):
            widget.setVisible(visible)

    def _apply_view_profile(self):
        advanced_visible = self._is_advanced_view()

        # Dashboard: keep safety-critical controls always visible in Simple.
        for attr_name in [
            "connection_panel",
            "status_panel",
            "obstacle_panel",
            "control_panel",
            "link_panel",
            "environment_panel",
            "imu_panel",
            "alert_panel",
        ]:
            self._set_visible_if_exists(attr_name, True)
        self._set_visible_if_exists("sensor_panel", advanced_visible)
        self._set_visible_if_exists("quick_diag_panel", advanced_visible)
        if hasattr(self, "alert_panel"):
            self.alert_panel.setMaximumHeight(110 if advanced_visible else 144)

        # Telemetry: Simple keeps only the two primary plots.
        self._set_visible_if_exists("telemetry_imu_panel", True)
        self._set_visible_if_exists("telemetry_link_plot_panel", True)
        self._set_visible_if_exists("telemetry_control_panel", advanced_visible)
        self._set_visible_if_exists("telemetry_environment_panel", advanced_visible)
        self._set_visible_if_exists("telemetry_distance_panel", advanced_visible)

        # System: Simple focuses on operations/logging/events only.
        self._set_visible_if_exists("diagnostics_overview_panel", True)
        self._set_visible_if_exists("system_logging_panel", True)
        self._set_visible_if_exists("warning_panel", True)
        self._set_visible_if_exists("system_middle_row", advanced_visible)
        self._set_visible_if_exists("sensor_health_panel", advanced_visible)
        self._set_visible_if_exists("logging_note_panel", advanced_visible)
        if hasattr(self, "operations_right_form"):
            self.operations_right_form.setRowVisible(2, advanced_visible)  # ACK
            self.operations_right_form.setRowVisible(3, advanced_visible)  # Timeouts
        if hasattr(self, "system_logging_form"):
            self.system_logging_form.setRowVisible(2, advanced_visible)  # Dropped
            self.system_logging_form.setRowVisible(3, advanced_visible)  # Timeouts
        if hasattr(self, "system_page_layout"):
            self.system_page_layout.setStretch(0, 1 if advanced_visible else 2)
            self.system_page_layout.setStretch(1, 1 if advanced_visible else 0)
            self.system_page_layout.setStretch(2, 2 if advanced_visible else 3)
        if hasattr(self, "system_bottom_tabs"):
            self.system_bottom_tabs.setTabVisible(self.system_tab_protocol_idx, advanced_visible)
            self.system_bottom_tabs.setTabVisible(self.system_tab_diag_idx, advanced_visible)
            self.system_bottom_tabs.setMinimumHeight(280 if advanced_visible else 220)
            if not advanced_visible:
                self.system_bottom_tabs.setCurrentIndex(self.system_tab_events_idx)

        # Keep System and Settings reachable in both modes.
        self.tabs.setTabVisible(2, True)
        self.tabs.setTabVisible(3, True)

    def on_view_changed(self, text: str):
        self.view_mode = text
        if hasattr(self, "view_combo") and self.view_combo.currentText() != text:
            blocked = self.view_combo.blockSignals(True)
            self.view_combo.setCurrentText(text)
            self.view_combo.blockSignals(blocked)
        if hasattr(self, "page_mode_combo") and self.page_mode_combo.currentText() != text:
            blocked = self.page_mode_combo.blockSignals(True)
            self.page_mode_combo.setCurrentText(text)
            self.page_mode_combo.blockSignals(blocked)
        self._apply_view_profile()
        if self._is_advanced_view() and self._latest_protocol_raw:
            self._pending_protocol_refresh = True
        self._apply_responsive_layout()
        self.refresh_visible_views_only()
        self.status_message.emit(f"View mode switched to {text}.")

    def on_theme_changed(self, text: str):
        self.theme_name = text
        self.apply_theme()
        self.refresh_all_views()

    def on_signal_view_changed(self, text: str):
        self.signal_view = text
        self.refresh_visible_views_only()

    def on_precision_mode_changed(self, text: str):
        self.decimal_mode = text
        if self._latest_protocol_decoded_raw:
            self._latest_protocol_decoded = self._format_decoded_json_for_display(
                self._latest_protocol_kind,
                self._latest_protocol_decoded_raw,
            )
            self._pending_protocol_refresh = True
        self.refresh_visible_views_only()

    def _tab_name(self, index: int) -> str:
        title = self.tabs.tabText(index).strip().lower()
        mapping = {
            "dashboard": "Dashboard",
            "telemetry": "Telemetry",
            "system": "System",
            "settings": "Settings",
        }
        return mapping.get(title, "Dashboard")

    def _is_tab_visible(self, name: str) -> bool:
        current = self._tab_name(self.tabs.currentIndex())
        return current == name

    def on_tab_changed(self, index: int):
        self.set_active_tab_refresh_policy(self._tab_name(index))
        self.refresh_visible_views_only()

    def set_active_tab_refresh_policy(self, tab_name: str):
        if not self.ui_profile.lazy_refresh_enabled:
            for timer in [self.dashboard_timer, self.imu_plot_timer, self.secondary_plot_timer, self.system_timer]:
                if not timer.isActive():
                    timer.start()
            return

        tab = tab_name or "Dashboard"
        dashboard_on = tab == "Dashboard"
        telemetry_on = tab == "Telemetry"
        system_on = tab == "System"

        self.dashboard_timer.start() if dashboard_on else self.dashboard_timer.stop()
        self.imu_plot_timer.start() if (dashboard_on or telemetry_on) else self.imu_plot_timer.stop()
        self.secondary_plot_timer.start() if telemetry_on else self.secondary_plot_timer.stop()
        self.system_timer.start() if system_on else self.system_timer.stop()

    def refresh_visible_views_only(self):
        self.refresh_dashboard_cards(force=False)
        self.refresh_system_page(force=False)
        self.refresh_all_plots(force=False)

    def apply_theme(self):
        QApplication.instance().setStyleSheet(build_stylesheet(self.theme_name))
        theme = get_theme(self.theme_name)
        for bar in [self.rssi_bar, self.batt_bar, self.front_bar]:
            bar.set_colors(theme["success"], theme["bar_empty"], theme["border"])
        for canvas in [self.imu_canvas, self.telemetry_imu_canvas, self.telemetry_link_canvas, self.telemetry_environment_canvas, self.telemetry_distance_canvas]:
            canvas.update_theme(theme["plot_bg"], theme["text"])
        self.refresh_all_plots()

    def _sync_connection_settings(self):
        port = self.com_port_edit.text().strip().upper()
        if port:
            if self.port_combo.findText(port) < 0:
                self.port_combo.addItem(port)
            self.port_combo.setCurrentText(port)
        baud_text = self.baud_edit.text().strip()
        if baud_text.isdigit():
            if self.baud_combo.findText(baud_text) < 0:
                self.baud_combo.addItem(baud_text)
            self.baud_combo.setCurrentText(baud_text)

    def _refresh_interaction_state(self):
        connected = self.connected
        replay_mode = self.data_source_combo.currentText() == "Replay"
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        allow_motion = connected and (not replay_mode) and self.rover_state not in {RoverState.ESTOP, RoverState.FAULT}
        self.speed_slider.setEnabled(allow_motion)
        for btn in [self.btn_forward, self.btn_left, self.btn_right, self.btn_back]:
            btn.setEnabled(allow_motion)
        self.btn_stop.setEnabled(connected)
        self.btn_estop.setEnabled(connected)
        self.logging_toggle_button.setEnabled(self.rover_state != RoverState.ESTOP)
        if self.rover_state == RoverState.ESTOP:
            self.connection_hint.setText("E-STOP active. Press STOP to clear, then resume control.")
        elif connected:
            self.connection_hint.setText("Telemetry active. Use controls or W/A/S/D + Space.")
        else:
            self.connection_hint.setText("Disconnected. Press Connect to start telemetry.")

    def _filtered_log_lines(self) -> list[str]:
        # `appendleft` keeps newest entries at the front, so slice from the start.
        lines = list(self.log_lines)[:120]
        mode = getattr(self, "event_filter", "all")
        if mode == "all":
            return lines
        if mode == "warning":
            keys = ("warning", "weak", "loss", "degraded")
            return [line for line in lines if any(key in line.lower() for key in keys)]
        keys = ("danger", "critical", "error", "failed")
        return [line for line in lines if any(key in line.lower() for key in keys)]

    def refresh_event_log(self):
        if hasattr(self, "warning_text"):
            html = self.format_log_html(self._filtered_log_lines())
            self._set_rich_text_preserve_scroll(self.warning_text, html)

    def _flush_throttled_text_updates(self):
        if self._pending_log_refresh:
            self._pending_log_refresh = False
            self.refresh_event_log()
        if self._pending_protocol_refresh:
            self._pending_protocol_refresh = False
            if not self._is_advanced_view():
                return
            if hasattr(self, "raw_signal_text"):
                self._set_plain_text_preserve_scroll(
                    self.raw_signal_text,
                    f"[{self._latest_protocol_kind}]\n{self._latest_protocol_raw}",
                )
            if hasattr(self, "decoded_signal_text"):
                self._set_plain_text_preserve_scroll(
                    self.decoded_signal_text,
                    f"[{self._latest_protocol_kind}]\n{self._latest_protocol_decoded}",
                )

    @staticmethod
    def _set_rich_text_preserve_scroll(widget: QTextEdit, html: str):
        bar = widget.verticalScrollBar()
        old_max = bar.maximum()
        old_value = bar.value()
        follow_latest = old_value <= bar.minimum() + 1
        widget.setHtml(html)
        if follow_latest:
            bar.setValue(bar.minimum())
        else:
            delta = max(0, bar.maximum() - old_max)
            bar.setValue(min(old_value + delta, bar.maximum()))

    @staticmethod
    def _set_plain_text_preserve_scroll(widget: QPlainTextEdit, text: str):
        bar = widget.verticalScrollBar()
        old_max = bar.maximum()
        old_value = bar.value()
        follow_latest = old_value <= bar.minimum() + 1
        widget.setPlainText(text)
        if follow_latest:
            bar.setValue(bar.minimum())
        else:
            delta = max(0, bar.maximum() - old_max)
            bar.setValue(min(old_value + delta, bar.maximum()))

    def set_rover_state(self, state: RoverState):
        self.rover_state = state
        self.connected = state != RoverState.DISCONNECTED
        if state == RoverState.DISCONNECTED:
            self.serial_state = "Disconnected"
            self.system_alert = "Telemetry stopped"
        elif state == RoverState.CONNECTED:
            self.system_alert = "Telemetry live"
        elif state == RoverState.RUNNING:
            self.system_alert = "Running"
        elif state == RoverState.FAULT:
            self.system_alert = "Fault detected"
        elif state == RoverState.ESTOP:
            self.system_alert = "Emergency stop"
        self._refresh_interaction_state()

    def record_event(self, level: str, source: str, code: str, message: str, payload: dict | None = None):
        event = EventRecord(
            time=time.time(),
            level=level,
            source=source,
            code=code,
            message=message,
            payload=payload or {},
        )
        self.event_records.append(event)
        stamp = time.strftime("%H:%M:%S", time.localtime(event.time))
        self.status_message.emit(f"[{stamp}] [{level.upper()}] {source}:{code} - {message}")

    def _check_command_timeouts(self):
        if self.data_source_combo.currentText() == "Replay":
            self._refresh_global_status_strip(self.raw_batt_v[-1])
            return
        if self.connected:
            self.last_packet_age_ms = int((time.time() - self.last_rx_monotonic) * 1000.0)
            if time.time() - self.last_heartbeat_sent >= 3.0:
                self.last_heartbeat_sent = time.time()
                hb = CommandFrame(
                    cmd_id=0,
                    name="HEARTBEAT",
                    params={},
                    deadline_ms=800,
                    max_retries=0,
                )
                self.command_outbound.emit(hb)
        timed_out = []
        now = time.time()
        for cmd_id, frame in self.pending_commands.items():
            age_ms = (now - frame.created_at) * 1000.0
            if age_ms <= frame.deadline_ms:
                continue
            if frame.retry_count < frame.max_retries:
                frame.retry_count += 1
                frame.created_at = now
                self.command_outbound.emit(frame)
                self.record_event("warning", "command", "CMD_RETRY", f"Retry {frame.name} #{cmd_id}", {"retry": frame.retry_count})
            else:
                timed_out.append(cmd_id)
        for cmd_id in timed_out:
            frame = self.pending_commands.pop(cmd_id, None)
            if not frame:
                continue
            self.timeout_counter += 1
            self.recent_timeouts += 1
            self.record_event("danger", "command", "CMD_TIMEOUT", f"Timeout {frame.name} #{cmd_id}")
        if self.last_packet_age_ms > 2000 and self.connected:
            if self.rover_state in {RoverState.RUNNING, RoverState.CONNECTED}:
                self.set_rover_state(RoverState.FAULT)
                self.push_alert("Link timeout >2s", "danger")
        self._refresh_global_status_strip(self.raw_batt_v[-1])

    # ---------- Data / Filters ----------
    def reset_dashboard_state(self):
        self.raw_x = deque([0.00] * self.max_points, maxlen=self.max_points)
        self.raw_y = deque([0.00] * self.max_points, maxlen=self.max_points)
        self.raw_z = deque([1.00] * self.max_points, maxlen=self.max_points)
        self.raw_mag = deque([1.00] * self.max_points, maxlen=self.max_points)
        self.raw_rssi = deque([-88.0] * self.max_points, maxlen=self.max_points)
        self.raw_snr = deque([10.0] * self.max_points, maxlen=self.max_points)
        self.raw_batt_v = deque([7.40] * self.max_points, maxlen=self.max_points)
        self.raw_front_cm = deque([60.0] * self.max_points, maxlen=self.max_points)
        self.raw_humidity = deque([48.0] * self.max_points, maxlen=self.max_points)
        self.raw_thermistor = deque([24.0] * self.max_points, maxlen=self.max_points)
        self.raw_log_mag = deque([1.00] * self.log_points, maxlen=self.log_points)
        self.log_lines.clear()
        self.samples_logged = 0
        self.packet_counter = 0
        self.parse_errors = 0
        self.dropped_packets = 0
        self.timeout_counter = 0
        self.last_packet_age_ms = 0
        self.battery_alert_zone = "normal"
        self.last_battery_alert_v = self.raw_batt_v[-1]
        self.active_alerts.clear()
        self._refresh_active_alerts_view()
        self.push_alert("Dashboard reset", "info")
        self.status_message.emit("Dashboard state reset.")
        self.refresh_all_views()

    @staticmethod
    def low_pass(value: float, previous: float, alpha: float) -> float:
        return alpha * value + (1.0 - alpha) * previous

    def moving_average(self, values: deque[float] | list[float], window: int) -> list[float]:
        src = list(values)
        out = []
        for idx in range(len(src)):
            s = src[max(0, idx - window + 1): idx + 1]
            out.append(sum(s) / len(s))
        return out

    def median_filter(self, values: deque[float] | list[float], window: int) -> list[float]:
        src = list(values)
        out = []
        half = max(1, window // 2)
        for idx in range(len(src)):
            s = src[max(0, idx - half): min(len(src), idx + half + 1)]
            ordered = sorted(s)
            out.append(ordered[len(ordered) // 2])
        return out

    def get_imu_filtered_series(self):
        x = list(self.raw_x); y = list(self.raw_y); z = list(self.raw_z); m = list(self.raw_mag)
        if self.imu_filter == "Moving Avg":
            return (
                self.moving_average(x, self.avg_window),
                self.moving_average(y, self.avg_window),
                self.moving_average(z, self.avg_window),
                self.moving_average(m, self.avg_window),
            )
        if self.imu_filter == "Low-pass":
            fx, fy, fz, fm = [], [], [], []
            px, py, pz, pm = x[0], y[0], z[0], m[0]
            for a, b, c, d in zip(x, y, z, m):
                px = self.low_pass(a, px, self.imu_alpha)
                py = self.low_pass(b, py, self.imu_alpha)
                pz = self.low_pass(c, pz, self.imu_alpha)
                pm = self.low_pass(d, pm, self.imu_alpha)
                fx.append(px); fy.append(py); fz.append(pz); fm.append(pm)
            return fx, fy, fz, fm
        return x, y, z, m

    def get_link_filtered_series(self):
        r = list(self.raw_rssi)
        if self.link_filter == "Smooth":
            out = []
            prev = r[0]
            for value in r:
                prev = self.low_pass(value, prev, self.link_alpha)
                out.append(prev)
            return out
        return r

    def get_obstacle_filtered_series(self):
        d = list(self.raw_front_cm)
        if self.ultra_filter == "Median":
            return self.median_filter(d, self.median_window)
        if self.ultra_filter == "Median + Avg":
            med = self.median_filter(d, self.median_window)
            return self.moving_average(med, self.avg_window)
        return d

    def evaluate_system_alert(self, front_cm: float, batt_v: float, rssi: float) -> str | None:
        now = self.packet_counter
        checks = [
            (front_cm <= self.obstacle_danger_cm, f"Obstacle danger: {front_cm:.0f} cm", 4),
            (rssi <= -102, f"LoRa warning: RSSI {rssi:.1f} dBm", 12),
            (front_cm <= self.obstacle_warning_cm, f"Obstacle warning: {front_cm:.0f} cm", 8),
        ]
        for triggered, message, cooldown in checks:
            if triggered:
                last = self.alert_cooldowns.get(message, -9999)
                if now - last >= cooldown:
                    self.alert_cooldowns[message] = now
                    return message
        battery_alert = self._battery_alert_event(batt_v)
        if battery_alert:
            return battery_alert
        return None

    def _battery_zone(self, batt_v: float) -> str:
        if batt_v <= self.battery_danger_v:
            return "danger"
        if batt_v <= self.battery_warning_v:
            return "warning"
        return "normal"

    def _battery_alert_event(self, batt_v: float) -> str | None:
        zone = self._battery_zone(batt_v)
        severity = {"normal": 0, "warning": 1, "danger": 2}
        previous_zone = self.battery_alert_zone

        # Better/normalized voltage should update baseline without creating extra warnings.
        if severity[zone] < severity[previous_zone]:
            self.battery_alert_zone = zone
            self.last_battery_alert_v = batt_v
            return None

        # First entry into warning/danger zone should raise a single alert.
        if severity[zone] > severity[previous_zone]:
            self.battery_alert_zone = zone
            self.last_battery_alert_v = batt_v
            level = "critical" if zone == "danger" else "low"
            return (
                f"Battery {level}: {self._fmt(batt_v, 'batt_v')} V "
                f"({self._fmt(self.battery_percent(batt_v), 'percent')}%)"
            )

        # Same zone: only re-alert when voltage drops significantly.
        if zone in {"warning", "danger"} and batt_v <= self.last_battery_alert_v - self.battery_realert_drop_v:
            previous_v = self.last_battery_alert_v
            self.last_battery_alert_v = batt_v
            return (
                f"Battery drop: {self._fmt(previous_v, 'batt_v')} V -> {self._fmt(batt_v, 'batt_v')} V "
                f"({self._fmt(self.battery_percent(batt_v), 'percent')}%)"
            )

        if zone == "normal":
            self.last_battery_alert_v = batt_v
        return None

    # ---------- Refresh ----------
    def refresh_all_views(self):
        self.refresh_dashboard_cards(force=True)
        self.refresh_system_page(force=True)
        self.refresh_all_plots(force=True)

    def refresh_dashboard_cards(self, force: bool = False):
        if self.ui_profile.lazy_refresh_enabled and not force and not self._is_tab_visible("Dashboard"):
            return
        theme = get_theme(self.theme_name)
        batt_v = self.raw_batt_v[-1]
        rssi = self.raw_rssi[-1]
        snr = self.raw_snr[-1]
        front = self.raw_front_cm[-1]
        current = 0.45 + max(0, self.speed_slider.value() / 200)
        temp = self.raw_thermistor[-1]
        humidity = self.raw_humidity[-1]
        packet_rate = (1000 / max(1, self.update_interval_ms)) if self.connected else 0.0
        packet_loss = (self.dropped_packets / max(1, self.packet_counter)) * 100

        self.state_label.setText(self.rover_state.value)
        self.mode_label.setText(self.view_mode)
        self.command_label.setText(self.current_command)
        self.speed_state_label.setText(f"{self.speed_slider.value()}%")

        self.rssi_value.setText(f"RSSI  {self._fmt(rssi, 'rssi')} dBm")
        self.snr_value.setText(f"SNR   {self._fmt(snr, 'snr')} dB")
        if self.connected:
            self.packet_rate_value.setText(f"Packet Rate  {self._fmt(packet_rate, 'packet_rate')} Hz")
        else:
            self.packet_rate_value.setText("Packet Rate  --")
        if not self.connected:
            loss_text = "Loss --"
            loss_color = "#66788f"
        elif packet_loss < 1.0:
            loss_text = f"Loss {self._fmt(packet_loss, 'packet_loss')}%"
            loss_color = theme["success"]
        elif packet_loss <= 3.0:
            loss_text = f"Loss {self._fmt(packet_loss, 'packet_loss')}%"
            loss_color = theme["warning"]
        else:
            loss_text = f"Loss {self._fmt(packet_loss, 'packet_loss')}%"
            loss_color = theme["danger"]
        self.packet_loss_badge.setText(loss_text)
        self.packet_loss_badge.setStyleSheet(
            f"background-color:{loss_color}; color:#ffffff; border-radius:7px; padding:2px 8px; font-weight:800;"
        )
        self.link_offline_label.setVisible(not self.connected)
        self.render_link_state(rssi, packet_loss)

        self.batt_value.setText(
            f"Battery  {self._fmt(batt_v, 'batt_v')} V ({self._fmt(self.battery_percent(batt_v), 'percent')}%)"
        )
        self.current_value.setText(f"Current  {self._fmt(current, 'current')} A")
        self.temp_value.setText(f"Board Temp  {self._fmt(temp, 'temp')} °C")
        self.humidity_value.setText(f"Humidity  {self._fmt(humidity, 'humidity')} %RH")
        self.thermistor_value.setText(f"Thermistor  {self._fmt(temp, 'temp')} °C")

        self.front_distance_value.setText(f"Distance  {self._fmt(front, 'distance')} cm")
        self.front_status_value.setText(self.obstacle_short_text(front))

        alert_text, alert_level = self._effective_alert()
        self.alert_label.setText(alert_text)
        alert_color = theme["success"] if alert_level == "info" else theme["danger"] if alert_level == "danger" else theme["warning"]
        self.alert_strip.setStyleSheet(f"background-color:{alert_color}; border-radius:4px;")
        self.quick_link_state.setText(self.link_health_text(rssi, packet_loss))
        self.quick_sample_state.setText(f"Samples logged: {self.samples_logged}")
        self.quick_timeout_state.setText(f"Timeout count: {self.timeout_counter}")
        self._refresh_global_status_strip(batt_v)

        self.update_bars(rssi, batt_v, front)
        self.update_sensor_indicators(rssi, batt_v, front)

    def update_sensor_indicators(self, rssi: float, batt_v: float, front: float):
        colors = get_theme(self.theme_name)
        imu_state = "ok" if self.last_packet_age_ms < 600 else "special"
        imu_hint = "Streaming" if imu_state == "ok" else "No recent update"
        ultra_state = "danger" if front <= self.obstacle_danger_cm else "warning" if front <= self.obstacle_warning_cm else "ok"
        ultra_hint = self.obstacle_text(front)
        batt_state = "danger" if batt_v <= self.battery_danger_v else "warning" if batt_v <= self.battery_warning_v else "ok"
        batt_hint = f"{self._fmt(batt_v, 'batt_v')} V ({self._fmt(self.battery_percent(batt_v), 'percent')}%)"
        lora_state = "special" if not self.connected else "danger" if rssi <= -102 else "warning" if rssi <= -92 else "ok"
        lora_hint = self.link_health_text(rssi, (self.dropped_packets / max(1, self.packet_counter)) * 100)
        humidity = self.raw_humidity[-1]
        thermistor = self.raw_thermistor[-1]
        humid_state = "warning" if humidity >= 72 else "ok"
        humid_hint = f"{self._fmt(humidity, 'humidity')} %RH"
        therm_state = "warning" if thermistor >= 34 else "ok"
        therm_hint = f"{self._fmt(thermistor, 'temp')} °C"
        sd_state = "ok" if self.logging_enabled else "special"
        sd_hint = "Writing raw CSV" if self.logging_enabled else "Paused"
        mapping = {
            "IMU": (imu_state, imu_hint),
            "Ultrasonic": (ultra_state, ultra_hint),
            "Battery": (batt_state, batt_hint),
            "Humidity": (humid_state, humid_hint),
            "Thermistor": (therm_state, therm_hint),
            "LoRa": (lora_state, lora_hint),
            "SD": (sd_state, sd_hint),
        }
        for key, (state, hint) in mapping.items():
            self.sensor_rows[key].update_state(state, hint, colors)
            self.diag_rows[key].update_state(state, hint, colors)

    def render_link_state(self, rssi: float, packet_loss: float):
        if not self.connected:
            self.snr_hint.setText("--")
            self.link_offline_label.setText("No connection")
            self.link_offline_label.setVisible(True)
            return
        self.snr_hint.setText(self.link_health_text(rssi, packet_loss))
        self.link_offline_label.setVisible(False)

    def render_alert_state(self, text: str, level: str):
        label = {
            "info": "GOOD",
            "warning": "WARNING",
            "danger": "ALERT",
        }.get(level, "GOOD")
        self.status_alert.setText(f"Alert: {label} ({text})")
        if hasattr(self, "top_status_alert"):
            self.top_status_alert.setText(f"Alert: {label}")

    def _refresh_global_status_strip(self, batt_v: float):
        alert_text, alert_level = self._effective_alert()
        self.status_conn.setText("Conn: ON" if self.connected else "Conn: OFF")
        self.status_mode.setText(f"Mode: {self.view_mode}")
        self.status_batt.setText(
            f"Battery: {self._fmt(batt_v, 'batt_v')} V ({self._fmt(self.battery_percent(batt_v), 'percent')}%)"
        )
        self.render_alert_state(alert_text, alert_level)
        self.status_log.setText(f"Logging: {'On' if self.logging_enabled else 'Off'}")
        self.top_status_conn.setText(self.status_conn.text())
        self.top_status_mode.setText(self.status_mode.text())
        self.top_status_batt.setText(self.status_batt.text())
        self.top_status_log.setText(self.status_log.text())

    def update_bars(self, rssi: float, batt_v: float, front: float):
        theme = get_theme(self.theme_name)

        # RSSI bar
        rssi_ratio = min(1.0, max(0.0, (rssi + 120) / 60.0))
        rssi_color = self.link_color(rssi)
        self.rssi_bar.set_colors(rssi_color, theme["bar_empty"], theme["border"])
        self.rssi_bar.set_ratio(rssi_ratio)

        # Battery bar threshold-linked
        batt_ratio = min(1.0, max(0.0, (batt_v - 6.0) / 1.8))
        if batt_v <= self.battery_danger_v:
            batt_color = theme["danger"]
        elif batt_v <= self.battery_warning_v:
            batt_color = theme["warning"]
        else:
            batt_color = theme["success"]
        self.batt_bar.set_colors(batt_color, theme["bar_empty"], theme["border"])
        self.batt_bar.set_ratio(batt_ratio)

        # Obstacle bar
        safety_ratio = min(1.0, max(0.0, (front - 5.0) / max(1.0, self.obstacle_display_max_cm - 5.0)))
        if front <= self.obstacle_danger_cm:
            front_color = theme["danger"]
            self.front_status_value.setText("ALERT")
            self.front_status_value.setStyleSheet(f"color: white; background-color: {theme['danger']}; font-weight: 800; border-radius: 8px; padding: 4px 8px;")
            self.push_alert(f"Obstacle alert: {front:.0f} cm", "danger")
        elif front <= self.obstacle_warning_cm:
            front_color = theme["warning"]
            self.front_status_value.setText("WARNING")
            self.front_status_value.setStyleSheet(f"color: #111; background-color: {theme['warning']}; font-weight: 800; border-radius: 8px; padding: 4px 8px;")
            self.push_alert(f"Obstacle warning: {front:.0f} cm", "warning")
        else:
            front_color = theme["success"]
            self.front_status_value.setText("GOOD")
            self.front_status_value.setStyleSheet(f"color: #0a1; background-color: {theme['plot_bg']}; font-weight: 800; border-radius: 8px; padding: 4px 8px;")
        self.front_bar.set_colors(front_color, theme["bar_empty"], theme["border"])
        self.front_bar.set_ratio(safety_ratio)


    def _alert_priority(self, level: str) -> int:
        return {"info": 0, "warning": 1, "danger": 2}.get(level, 0)

    def push_alert(self, text: str, level: str = "info"):
        if not hasattr(self, "alert_hold_until"):
            self.current_alert_level = "info"
            self.current_alert_text = "Nominal"
            self.alert_hold_until = 0.0
        now = time.time()
        hold = 0.0 if level == "info" else 2.5 if level == "warning" else 3.0
        if now < self.alert_hold_until and self._alert_priority(level) < self._alert_priority(self.current_alert_level):
            return
        if now < self.alert_hold_until and self._alert_priority(level) == self._alert_priority(self.current_alert_level) and text == self.current_alert_text:
            return
        self.current_alert_text = text
        self.current_alert_level = level
        self.alert_hold_until = now + hold
        self.system_alert = text
        if level in {"warning", "danger"}:
            self._add_active_alert(text, level)
        if hasattr(self, "top_status_alert"):
            self._refresh_global_status_strip(self.raw_batt_v[-1])

    def _effective_alert(self) -> tuple[str, str]:
        if not hasattr(self, "alert_hold_until"):
            self.current_alert_level = "info"
            self.current_alert_text = "Nominal"
            self.alert_hold_until = 0.0
        now = time.time()
        if now < self.alert_hold_until:
            return self.current_alert_text, self.current_alert_level
        if self.current_alert_level != "info":
            self.current_alert_text = "Nominal"
            self.current_alert_level = "info"
            self.system_alert = "Nominal"
        return self.current_alert_text, self.current_alert_level

    def _add_active_alert(self, text: str, level: str):
        now = time.time()
        self.active_alerts[text] = (level, now)
        while len(self.active_alerts) > self.active_alert_limit:
            oldest = next(iter(self.active_alerts))
            self.active_alerts.pop(oldest, None)
        self._refresh_active_alerts_view()

    def _refresh_active_alerts_view(self):
        if not hasattr(self, "active_alerts_text"):
            return
        if not self.active_alerts:
            self.active_alerts_text.setPlainText("No active alerts.")
            return
        lines: list[str] = []
        for message, (level, ts) in list(self.active_alerts.items())[::-1]:
            stamp = time.strftime("%H:%M:%S", time.localtime(ts))
            tag = "ALERT" if level == "danger" else "WARN"
            lines.append(f"[{stamp}] {tag}: {message}")
        self.active_alerts_text.setPlainText("\n".join(lines))

    def acknowledge_alerts(self):
        self.active_alerts.clear()
        self.current_alert_text = "Nominal"
        self.current_alert_level = "info"
        self.alert_hold_until = 0.0
        self.system_alert = "Nominal"
        self._refresh_active_alerts_view()
        self.status_message.emit("Active alerts acknowledged.")

    @staticmethod
    def gradient_color_green_to_red(ratio: float) -> str:
        ratio = max(0.0, min(1.0, ratio))
        red = int(255 * (1 - ratio))
        green = int(255 * ratio)
        return f"#{red:02x}{green:02x}28"

    def link_color(self, rssi: float) -> str:
        theme = get_theme(self.theme_name)
        if rssi > -75:
            return theme["success"]
        if rssi > -90:
            return theme["warning"]
        return theme["danger"]

    def link_health_text(self, rssi: float, packet_loss_percent: float) -> str:
        if not self.connected:
            return "No connection"
        if rssi <= -102 or packet_loss_percent > 8:
            return "Weak link"
        if rssi <= -92 or packet_loss_percent > 3:
            return "Degraded link"
        return "Stable link"

    def obstacle_text(self, front_cm: float) -> str:
        if front_cm <= self.obstacle_danger_cm:
            return "Danger: stop or reverse"
        if front_cm <= self.obstacle_warning_cm:
            return "Caution: obstacle close"
        return "Path clear"

    def obstacle_short_text(self, front_cm: float) -> str:
        if front_cm <= self.obstacle_danger_cm:
            return "ALERT"
        if front_cm <= self.obstacle_warning_cm:
            return "WARNING"
        return "GOOD"

    def refresh_system_page(self, force: bool = False):
        if self.ui_profile.lazy_refresh_enabled and not force and not self._is_tab_visible("System"):
            return
        packet_rate = (1000 / max(1, self.update_interval_ms)) if self.connected else 0.0
        packet_loss = (self.dropped_packets / max(1, self.packet_counter)) * 100
        batt_v = self.raw_batt_v[-1]
        self._refresh_encryption_labels()
        self.diag_serial_label.setText(self.serial_state)
        self.diag_state_label.setText(self.rover_state.value)
        self.diag_battery_label.setText(
            f"{self._fmt(batt_v, 'batt_v')} V ({self._fmt(self.battery_percent(batt_v), 'percent')}%)"
        )
        self.diag_protocol_label.setText(self.protocol_version)
        self.diag_last_packet_label.setText(f"{self.last_packet_age_ms} ms")
        self.diag_packet_rate_label.setText(f"{self._fmt(packet_rate, 'packet_rate')} Hz")
        self.diag_packet_loss_label.setText(f"{self._fmt(packet_loss, 'packet_loss')}%")
        self.diag_ack_label.setText(
            f"{self._fmt(self.avg_ack_latency_ms, 'ack_latency')} ms "
            f"(last {self._fmt(self.last_ack_latency_ms, 'ack_latency')})"
        )
        self.diag_timeout_recent_label.setText(str(self.recent_timeouts))
        self.diag_dropped_label.setText(str(self.dropped_packets))
        self.diag_parse_label.setText(str(self.parse_errors))
        self.diag_timeout_label.setText(str(self.timeout_counter))
        self.logging_state_label.setText("ACTIVE" if self.logging_enabled else "PAUSED")
        self.logging_file_label.setText(self._compact_path_text(self.log_file_path))
        self.logging_file_label.setToolTip(self.log_file_path)
        self.logging_metadata_label.setText(self._compact_path_text(self.metadata_path))
        self.logging_metadata_label.setToolTip(self.metadata_path)
        self.logging_samples_label.setText(str(self.samples_logged))
        self._refresh_global_status_strip(batt_v)
        self.refresh_event_log()
        self.recent_timeouts = 0

    def refresh_all_plots(self, force: bool = False):
        self.refresh_imu_plots(force=force)
        self.refresh_secondary_plots(force=force)

    def refresh_imu_plots(self, force: bool = False):
        dashboard_visible = self._is_tab_visible("Dashboard")
        telemetry_visible = self._is_tab_visible("Telemetry")
        if self.ui_profile.lazy_refresh_enabled and not force and not (dashboard_visible or telemetry_visible):
            return
        if force or dashboard_visible:
            self.plot_imu(self.imu_canvas.ax)
            self.imu_canvas.draw_idle()
        if force or telemetry_visible:
            self.plot_imu(self.telemetry_imu_canvas.ax)
            self.telemetry_imu_canvas.draw_idle()

    def refresh_secondary_plots(self, force: bool = False):
        if self.ui_profile.lazy_refresh_enabled and not force and not self._is_tab_visible("Telemetry"):
            return
        self.plot_link(self.telemetry_link_canvas.ax)
        self.telemetry_link_canvas.draw_idle()
        if force or self.telemetry_environment_panel.isVisible():
            self.plot_environment(self.telemetry_environment_canvas.ax)
            self.telemetry_environment_canvas.draw_idle()
        if force or self.telemetry_distance_panel.isVisible():
            self.plot_distance(self.telemetry_distance_canvas.ax)
            self.telemetry_distance_canvas.draw_idle()

    def plot_imu(self, ax):
        theme = get_theme(self.theme_name)
        raw_x = list(self.raw_x)[-self.plot_history:]
        raw_y = list(self.raw_y)[-self.plot_history:]
        raw_z = list(self.raw_z)[-self.plot_history:]
        raw_m = list(self.raw_mag)[-self.plot_history:]
        fx, fy, fz, fm = self.get_imu_filtered_series()
        fx, fy, fz, fm = fx[-len(raw_x):], fy[-len(raw_x):], fz[-len(raw_x):], fm[-len(raw_x):]
        self._clear_extra_axes(ax)
        ax.clear()
        ax.set_facecolor(theme["plot_bg"])
        x_axis = list(range(len(raw_x)))
        if self.signal_view in ["Raw", "Overlay"]:
            ax.plot(x_axis, raw_x, color="#8fb7ff", linewidth=1.0, alpha=0.28)
            ax.plot(x_axis, raw_y, color="#9ae4ff", linewidth=1.0, alpha=0.28)
            ax.plot(x_axis, raw_z, color="#ffd37f", linewidth=1.0, alpha=0.28)
            ax.plot(x_axis, raw_m, color="#cccccc", linewidth=1.0, alpha=0.28)
        if self.signal_view in ["Filtered", "Overlay"]:
            ax.plot(x_axis, fx, color="#2aa8ff", linewidth=2.2, label="Xf")
            ax.plot(x_axis, fy, color="#17d1c1", linewidth=2.2, label="Yf")
            ax.plot(x_axis, fz, color="#ffb347", linewidth=2.2, label="Zf")
            ax.plot(x_axis, fm, color="#f4f4f4", linewidth=2.4, label="|a|f")
        self._style_axis(ax, theme, ylabel="g")
        ax.grid(True, alpha=0.20)
        self._apply_inline_legend(ax, theme)
        self._draw_line_style_key(ax, theme, show_filtered=self.signal_view in ["Filtered", "Overlay"],
                                  show_raw=self.signal_view in ["Raw", "Overlay"])

    def plot_link(self, ax):
        theme = get_theme(self.theme_name)
        raw_r = list(self.raw_rssi)[-self.plot_history:]
        filt_r = self.get_link_filtered_series()[-len(raw_r):]
        snr_raw = list(self.raw_snr)[-self.plot_history:]
        snr_f = self.moving_average(snr_raw, max(2, min(self.avg_window, 8)))
        self._clear_extra_axes(ax)
        ax.clear()
        ax.set_facecolor(theme["plot_bg"])
        x_axis = list(range(len(raw_r)))
        if self.signal_view in ["Raw", "Overlay"]:
            ax.plot(x_axis, raw_r, color="#7fa9ff", linewidth=1.0, alpha=0.30)
        if self.signal_view in ["Filtered", "Overlay"]:
            ax.plot(x_axis, filt_r, color="#2aa8ff", linewidth=2.0, label="RSSIf")
        ax2 = ax.twinx()
        ax2.set_facecolor("none")
        if self.signal_view in ["Raw", "Overlay"]:
            ax2.plot(x_axis, snr_raw, color="#8cf28d", linewidth=1.0, alpha=0.25)
        ax2.plot(x_axis, snr_f, color="#59e05d", linewidth=2.0, label="SNRf")
        self._style_axis(ax, theme, ylabel="RSSI (dBm)")
        self._style_axis(ax2, theme, ylabel="SNR (dB)")
        ax.grid(True, alpha=0.20)
        handles1, labels1 = ax.get_legend_handles_labels()
        handles2, labels2 = ax2.get_legend_handles_labels()
        leg = ax.legend(handles1 + handles2, labels1 + labels2, loc="upper right", bbox_to_anchor=(0.98, 0.98),
                        fontsize=8, frameon=True, borderpad=0.35, labelspacing=0.25, handlelength=1.6)
        leg.get_frame().set_facecolor(theme["panel"])
        leg.get_frame().set_edgecolor(theme["border"])
        leg.get_frame().set_alpha(0.88)
        for txt in leg.get_texts():
            txt.set_color(theme["text"])
        self._draw_line_style_key(ax, theme, show_filtered=True, show_raw=self.signal_view in ["Raw", "Overlay"])

    def plot_environment(self, ax):
        theme = get_theme(self.theme_name)
        history = min(self.plot_history, 80)
        humidity_raw = list(self.raw_humidity)[-history:]
        therm_raw = list(self.raw_thermistor)[-history:]
        humidity_f = self.moving_average(humidity_raw, max(2, min(self.avg_window, 8)))
        therm_f = self.moving_average(therm_raw, max(2, min(self.avg_window, 8)))
        self._clear_extra_axes(ax)
        ax.clear()
        ax.set_facecolor(theme["plot_bg"])
        x_axis = list(range(len(humidity_raw)))
        if self.signal_view in ["Raw", "Overlay"]:
            ax.plot(x_axis, humidity_raw, color="#52d8ff", linewidth=1.0, alpha=0.28)
        ax.plot(x_axis, humidity_f, color="#39c8ff", linewidth=2.1, label="Humf")
        ax2 = ax.twinx()
        ax2.set_facecolor("none")
        if self.signal_view in ["Raw", "Overlay"]:
            ax2.plot(x_axis, therm_raw, color="#ffb980", linewidth=1.0, alpha=0.28)
        ax2.plot(x_axis, therm_f, color="#ff9d2e", linewidth=2.1, label="Thermf")
        self._style_axis(ax, theme, ylabel="Humidity (%RH)")
        self._style_axis(ax2, theme, ylabel="Thermistor (°C)")
        if humidity_raw:
            hmin, hmax = min(humidity_raw + humidity_f), max(humidity_raw + humidity_f)
            margin = max(1.0, (hmax - hmin) * 0.25)
            ax.set_ylim(hmin - margin, hmax + margin)
        if therm_raw:
            tmin, tmax = min(therm_raw + therm_f), max(therm_raw + therm_f)
            margin = max(0.8, (tmax - tmin) * 0.35)
            ax2.set_ylim(tmin - margin, tmax + margin)
        ax.grid(True, alpha=0.20)
        handles1, labels1 = ax.get_legend_handles_labels()
        handles2, labels2 = ax2.get_legend_handles_labels()
        leg = ax.legend(handles1 + handles2, labels1 + labels2, loc="upper right", bbox_to_anchor=(0.98, 0.98),
                        fontsize=8, frameon=True, borderpad=0.35, labelspacing=0.25, handlelength=1.6)
        leg.get_frame().set_facecolor(theme["panel"])
        leg.get_frame().set_edgecolor(theme["border"])
        leg.get_frame().set_alpha(0.88)
        for txt in leg.get_texts():
            txt.set_color(theme["text"])
        self._draw_line_style_key(ax, theme, show_filtered=True, show_raw=self.signal_view in ["Raw", "Overlay"])

    def plot_distance(self, ax):
        theme = get_theme(self.theme_name)
        history = min(self.plot_history, 80)
        front_raw = list(self.raw_front_cm)[-history:]
        front_f = self.get_obstacle_filtered_series()[-len(front_raw):]
        self._clear_extra_axes(ax)
        ax.clear()
        ax.set_facecolor(theme["plot_bg"])
        x_axis = list(range(len(front_raw)))
        if self.signal_view in ["Raw", "Overlay"]:
            ax.plot(x_axis, front_raw, color="#f1c93b", linewidth=1.0, alpha=0.30)
        ax.plot(x_axis, front_f, color="#ff7a1a", linewidth=2.2, label="Df")
        self._style_axis(ax, theme, ylabel="Distance (cm)")
        ax.grid(True, alpha=0.20)
        self._apply_inline_legend(ax, theme)
        self._draw_line_style_key(ax, theme, show_filtered=True, show_raw=self.signal_view in ["Raw", "Overlay"])

    def _clear_extra_axes(self, ax):
        fig = ax.figure
        if fig is None:
            return
        for extra_ax in list(fig.axes):
            if extra_ax is not ax:
                try:
                    fig.delaxes(extra_ax)
                except Exception:
                    pass

    def _style_axis(self, ax, theme: dict, ylabel: str = "", xlabel: str = ""):
        ax.tick_params(colors=theme["text"])
        for spine in ax.spines.values():
            spine.set_color(theme["text"])
        ax.title.set_color(theme["text"])
        ax.xaxis.label.set_color(theme["text"])
        ax.yaxis.label.set_color(theme["text"])
        if ylabel:
            ax.set_ylabel(ylabel, color=theme["text"])
        if xlabel:
            ax.set_xlabel(xlabel, color=theme["text"])

    def _apply_inline_legend(self, ax, theme: dict):
        handles, labels = ax.get_legend_handles_labels()
        if not handles:
            return
        leg = ax.legend(
            loc="upper right",
            bbox_to_anchor=(0.98, 0.98),
            fontsize=8,
            frameon=True,
            borderpad=0.35,
            labelspacing=0.25,
            handlelength=1.6,
        )
        frame = leg.get_frame()
        frame.set_facecolor(theme["panel"])
        frame.set_edgecolor(theme["border"])
        frame.set_alpha(0.88)
        for txt in leg.get_texts():
            txt.set_color(theme["text"])

    def _draw_line_style_key(self, ax, theme: dict, show_filtered: bool = True, show_raw: bool = True):
        x0 = 0.03
        y = 0.06
        if show_raw:
            ax.plot([x0, x0 + 0.08], [y, y], transform=ax.transAxes, color=theme["text"],
                    linewidth=1.0, alpha=0.45, solid_capstyle="round", clip_on=False)
            ax.text(x0 + 0.09, y, "Raw", transform=ax.transAxes, color=theme["muted"],
                    fontsize=8, va="center", ha="left")
            y += 0.06
        if show_filtered:
            ax.plot([x0, x0 + 0.08], [y, y], transform=ax.transAxes, color=theme["text"],
                    linewidth=2.4, alpha=0.95, solid_capstyle="round", clip_on=False)
            ax.text(x0 + 0.09, y, "Filtered", transform=ax.transAxes, color=theme["muted"],
                    fontsize=8, va="center", ha="left")

    def _decimal_digits(self, metric: str) -> int:
        simple = {
            "rssi": 1,
            "snr": 1,
            "packet_rate": 2,
            "packet_loss": 2,
            "batt_v": 2,
            "current": 2,
            "temp": 1,
            "humidity": 1,
            "distance": 1,
            "ack_latency": 1,
            "percent": 0,
            "imu": 3,
            "timestamp": 3,
            "default": 2,
        }
        precise = {
            "rssi": 3,
            "snr": 3,
            "packet_rate": 3,
            "packet_loss": 4,
            "batt_v": 4,
            "current": 3,
            "temp": 2,
            "humidity": 2,
            "distance": 2,
            "ack_latency": 2,
            "percent": 1,
            "imu": 5,
            "timestamp": 6,
            "default": 4,
        }
        profile = precise if self.decimal_mode == "Precise" else simple
        return profile.get(metric, profile["default"])

    def _fmt(self, value: float, metric: str) -> str:
        return f"{value:.{self._decimal_digits(metric)}f}"

    def _round_monitor_number(self, key: str, value: float):
        int_keys = {"seq", "status_bits"}
        if key in int_keys:
            return int(round(value))

        key_map = {
            "timestamp": "timestamp",
            "rssi": "rssi",
            "snr": "snr",
            "packet_loss": "packet_loss",
            "batt_v": "batt_v",
            "distance_cm": "distance",
            "humidity": "humidity",
            "thermistor_c": "temp",
        }
        metric = key_map.get(key, "default")
        return round(float(value), self._decimal_digits(metric))

    def _format_decoded_json_for_display(self, kind: str, decoded_json: str) -> str:
        if kind.lower() != "telemetry":
            return decoded_json
        try:
            payload = json.loads(decoded_json)
        except Exception:
            return decoded_json

        if isinstance(payload, dict):
            out: dict = {}
            for key, value in payload.items():
                if key == "imu" and isinstance(value, list):
                    out[key] = [round(float(item), self._decimal_digits("imu")) for item in value]
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    out[key] = self._round_monitor_number(key, float(value))
                else:
                    out[key] = value
            return json.dumps(out, ensure_ascii=False, indent=2)
        return decoded_json

    @staticmethod
    def _compact_path_text(text: str, keep_tail: int = 38) -> str:
        if len(text) <= keep_tail + 3:
            return text
        return f"...{text[-keep_tail:]}"


    def battery_percent(self, batt_v: float) -> float:
        v_min = 6.4
        v_max = 8.4
        ratio = (batt_v - v_min) / (v_max - v_min)
        ratio = max(0.0, min(1.0, ratio))
        return ratio * 100.0

    def format_log_html(self, lines: list[str]) -> str:
        html = ["<div style='font-family:Segoe UI; font-size:13px;'>"]
        for line in lines:
            lower = line.lower()
            color = "#d8e6ff"
            if any(key in lower for key in ["danger", "critical", "error", "failed"]):
                color = "#ff6b6b"
            elif any(key in lower for key in ["warning", "weak", "loss"]):
                color = "#ffd166"
            safe = (line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            html.append(f"<div style='color:{color}; margin:1px 0;'>{safe}</div>")
        html.append("</div>")
        return "".join(html)

    def append_log_line(self, text: str):
        self.log_lines.appendleft(text)
        self._pending_log_refresh = True

    # ---------- Input ----------
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_F1:
            QMessageBox.information(
                self,
                "Keyboard Shortcuts",
                "W: Forward\nA: Left\nS: Backward\nD: Right\nSpace: Stop\nE: E-STOP",
            )
            event.accept()
            return
        key_map = {
            Qt.Key.Key_W: "FORWARD",
            Qt.Key.Key_A: "LEFT",
            Qt.Key.Key_S: "BACKWARD",
            Qt.Key.Key_D: "RIGHT",
            Qt.Key.Key_Space: "STOP",
        }
        if event.key() == Qt.Key.Key_E:
            self.trigger_estop()
            event.accept()
            return
        if event.key() in key_map:
            self.send_command(key_map[event.key()])
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        try:
            self.replay_timer.stop()
            self.save_metadata()
            self.worker_stop.emit()
            if hasattr(self, "worker_thread"):
                self.worker_thread.quit()
                self.worker_thread.wait(1000)
        except Exception as exc:  # pragma: no cover
            QMessageBox.warning(self, "Metadata", f"Could not save metadata: {exc}")
        super().closeEvent(event)
