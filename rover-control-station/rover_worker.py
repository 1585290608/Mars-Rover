from __future__ import annotations

import math
import random
import time
from collections import deque

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from rover_core import CommandFrame, TelemetryFrame
from rover_protocol import (
    debug_packet_view,
    frame_to_json_text,
    parse_command,
    parse_telemetry,
    serialize_command,
    serialize_telemetry,
)


class SerialWorker(QObject):
    telemetry_received = pyqtSignal(object)
    ack_received = pyqtSignal(int, float)
    worker_event = pyqtSignal(str, str, str, object)
    link_state_changed = pyqtSignal(bool, str)
    protocol_trace = pyqtSignal(str, str, str)

    def __init__(self):
        super().__init__()
        self._running = False
        self._seq = 0
        self._demo_tick = 0
        self._packet_counter = 0
        self._dropped_packets = 0
        self._queue: deque[CommandFrame] = deque()
        self._pending_ack: list[tuple[float, int, float]] = []
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._on_tick)

    @pyqtSlot(str, int)
    def start_link(self, port: str, baud: int):
        self._running = True
        self._timer.start()
        self.worker_event.emit("info", "link", "LINK_UP", f"Link opened on {port} @ {baud}")
        self.link_state_changed.emit(True, f"Connected @ {port} / {baud}")

    @pyqtSlot()
    def stop_link(self):
        self._running = False
        self._timer.stop()
        self._queue.clear()
        self._pending_ack.clear()
        self.link_state_changed.emit(False, "Disconnected")
        self.worker_event.emit("warning", "link", "LINK_DOWN", "Link stopped")

    @pyqtSlot(object)
    def enqueue_command(self, frame: object):
        if not isinstance(frame, CommandFrame):
            return
        try:
            raw = serialize_command(frame)
            parsed = parse_command(raw)
            raw_hex, decoded_json = debug_packet_view(raw)
            self.protocol_trace.emit("command", raw_hex, decoded_json)
        except Exception as exc:
            self.worker_event.emit("danger", "protocol", "CMD_PARSE_FAIL", str(exc))
            return
        self._queue.append(parsed)

    def _on_tick(self):
        if not self._running:
            return

        self._demo_tick += 1
        phase = self._demo_tick / 9.0
        ax = 0.22 * math.sin(phase) + random.uniform(-0.03, 0.03)
        ay = 0.18 * math.cos(phase * 0.8) + random.uniform(-0.03, 0.03)
        az = 1.0 + 0.08 * math.sin(phase * 0.5) + random.uniform(-0.02, 0.02)
        mag = math.sqrt(ax * ax + ay * ay + az * az)
        rssi = -83 - 8 * math.sin(phase / 2.0) + random.uniform(-1.3, 1.3)
        snr = 10.5 + 2.0 * math.sin(phase / 3.0) + random.uniform(-0.3, 0.3)
        batt = max(6.25, 7.45 - self._demo_tick * 0.0025 + random.uniform(-0.01, 0.01))
        front = max(8, 58 + 20 * math.sin(phase / 1.8) + random.uniform(-3.0, 3.0))
        humidity = 49 + 7 * math.sin(phase / 4.0) + random.uniform(-0.8, 0.8)
        thermistor = 24 + 4 * math.sin(phase / 5.0 + 0.8) + random.uniform(-0.3, 0.3)

        if self._demo_tick % 36 == 0:
            front = random.choice([14, 18, 24])
        if self._demo_tick % 52 == 0:
            rssi -= 15
        if self._demo_tick % 71 == 0:
            self._dropped_packets += 1

        self._packet_counter += 1
        packet_loss = (self._dropped_packets / max(1, self._packet_counter)) * 100.0
        frame = TelemetryFrame(
            timestamp=time.time(),
            seq=self._seq,
            rssi=rssi,
            snr=snr,
            packet_loss=packet_loss,
            batt_v=batt,
            imu=(ax, ay, az, mag),
            distance_cm=front,
            humidity=humidity,
            thermistor_c=thermistor,
            status_bits=0,
        )
        self._seq += 1
        try:
            raw = serialize_telemetry(frame)
            parsed = parse_telemetry(raw)
            raw_hex, _ = debug_packet_view(raw)
            self.protocol_trace.emit("telemetry", raw_hex, frame_to_json_text(parsed))
        except Exception as exc:
            self.worker_event.emit("danger", "protocol", "TELEM_PARSE_FAIL", str(exc))
            return
        self.telemetry_received.emit(parsed)

        self._pump_commands()
        self._emit_acks()

    def _pump_commands(self):
        if not self._queue:
            return
        cmd = self._queue.popleft()
        # Simulate realistic ACK jitter and occasional missing ACK.
        if random.random() < 0.12:
            self.worker_event.emit("warning", "link", "ACK_LOST", f"No ACK for {cmd.name}#{cmd.cmd_id}")
            return
        latency_ms = random.uniform(70.0, 340.0)
        due = time.time() + latency_ms / 1000.0
        self._pending_ack.append((due, cmd.cmd_id, latency_ms))

    def _emit_acks(self):
        if not self._pending_ack:
            return
        now = time.time()
        ready = [item for item in self._pending_ack if item[0] <= now]
        self._pending_ack = [item for item in self._pending_ack if item[0] > now]
        for _, cmd_id, latency_ms in ready:
            self.ack_received.emit(cmd_id, latency_ms)
