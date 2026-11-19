from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any


PROTOCOL_VERSION = "1.0"


class RoverState(Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    ARMED = "ARMED"
    RUNNING = "RUNNING"
    FAULT = "FAULT"
    ESTOP = "ESTOP"


@dataclass(slots=True)
class TelemetryFrame:
    timestamp: float
    seq: int
    rssi: float
    snr: float
    packet_loss: float
    batt_v: float
    imu: tuple[float, float, float, float]
    distance_cm: float
    humidity: float
    thermistor_c: float
    status_bits: int = 0
    protocol_version: str = PROTOCOL_VERSION


@dataclass(slots=True)
class CommandFrame:
    cmd_id: int
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    deadline_ms: int = 1200
    retry_count: int = 0
    max_retries: int = 2
    protocol_version: str = PROTOCOL_VERSION


@dataclass(slots=True)
class EventRecord:
    time: float
    level: str
    source: str
    code: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class UIRuntimeProfile:
    target_resolution: tuple[int, int] = (1366, 768)
    compact_mode_threshold: tuple[int, int] = (1500, 860)
    lazy_refresh_enabled: bool = True
    font_scale_min: float = 1.0
    panel_min_widths: dict[str, int] = field(
        default_factory=lambda: {
            "dashboard": 1360,
            "telemetry": 1220,
            "system": 1180,
            "settings": 1180,
        }
    )
