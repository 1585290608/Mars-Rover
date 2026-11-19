from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from rover_core import CommandFrame, TelemetryFrame


# Optional XOR demonstration for the simulated protocol.
ENABLE_XOR_CIPHER = False
DEMO_XOR_MASK = b"rover-control-station-demo"


OPCODE_TO_NAME = {
    0b0000: "HEARTBEAT",
    0b0001: "STOP",
    0b0010: "ESTOP",
    0b0011: "FWD",
    0b0100: "BACK",
    0b0101: "LEFT",
    0b0110: "RIGHT",
    0b0111: "SPEED",
    0b1000: "ACK",
    0b1001: "NACK",
}
NAME_TO_OPCODE = {name: opcode for opcode, name in OPCODE_TO_NAME.items()}


def set_encryption_enabled(enabled: bool):
    global ENABLE_XOR_CIPHER
    ENABLE_XOR_CIPHER = bool(enabled)


def is_encryption_enabled() -> bool:
    return ENABLE_XOR_CIPHER


def encryption_mode_name() -> str:
    return "XOR" if ENABLE_XOR_CIPHER else "NONE"


def _crc16(data: bytes) -> int:
    poly = 0x1021
    crc = 0xFFFF
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _xor_cipher(data: bytes, key: bytes = DEMO_XOR_MASK) -> bytes:
    if not key:
        return data
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _encode_body(body: bytes) -> bytes:
    if not ENABLE_XOR_CIPHER:
        return body
    return _xor_cipher(body)


def _decode_body(body: bytes) -> bytes:
    if not ENABLE_XOR_CIPHER:
        return body
    return _xor_cipher(body)


def _pack_payload(obj: dict[str, Any]) -> bytes:
    body = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    crc = _crc16(body)
    encoded = _encode_body(body)
    return encoded + b"|" + f"{crc:04X}".encode("ascii")


def _unpack_payload(packet: bytes) -> dict[str, Any]:
    try:
        encoded_body, crc_text = packet.rsplit(b"|", 1)
    except ValueError as exc:
        raise ValueError("Malformed packet") from exc
    body = _decode_body(encoded_body)
    expected = int(crc_text.decode("ascii"), 16)
    actual = _crc16(body)
    if expected != actual:
        raise ValueError("CRC mismatch")
    return json.loads(body.decode("utf-8"))


def serialize_command(frame: CommandFrame) -> bytes:
    payload = {
        "opcode": NAME_TO_OPCODE.get(frame.name, 0b1001),
        "cmd_id": frame.cmd_id,
        "name": frame.name,
        "params": frame.params,
        "created_at": frame.created_at,
        "deadline_ms": frame.deadline_ms,
        "retry_count": frame.retry_count,
        "max_retries": frame.max_retries,
        "protocol_version": frame.protocol_version,
    }
    return _pack_payload(payload)


def parse_command(packet: bytes) -> CommandFrame:
    data = _unpack_payload(packet)
    opcode = int(data["opcode"])
    name = OPCODE_TO_NAME.get(opcode, str(data.get("name", "NACK")))
    return CommandFrame(
        cmd_id=int(data["cmd_id"]),
        name=name,
        params=dict(data.get("params", {})),
        created_at=float(data.get("created_at", 0.0)),
        deadline_ms=int(data.get("deadline_ms", 1200)),
        retry_count=int(data.get("retry_count", 0)),
        max_retries=int(data.get("max_retries", 2)),
        protocol_version=str(data.get("protocol_version", "1.0")),
    )


def serialize_telemetry(frame: TelemetryFrame) -> bytes:
    payload = {
        "timestamp": frame.timestamp,
        "seq": frame.seq,
        "rssi": frame.rssi,
        "snr": frame.snr,
        "packet_loss": frame.packet_loss,
        "batt_v": frame.batt_v,
        "imu": list(frame.imu),
        "distance_cm": frame.distance_cm,
        "humidity": frame.humidity,
        "thermistor_c": frame.thermistor_c,
        "status_bits": frame.status_bits,
        "protocol_version": frame.protocol_version,
    }
    return _pack_payload(payload)


def parse_telemetry(packet: bytes) -> TelemetryFrame:
    data = _unpack_payload(packet)
    imu = data.get("imu", [0.0, 0.0, 1.0, 1.0])
    if not isinstance(imu, list) or len(imu) != 4:
        raise ValueError("Invalid IMU payload")
    return TelemetryFrame(
        timestamp=float(data["timestamp"]),
        seq=int(data["seq"]),
        rssi=float(data["rssi"]),
        snr=float(data["snr"]),
        packet_loss=float(data["packet_loss"]),
        batt_v=float(data["batt_v"]),
        imu=(float(imu[0]), float(imu[1]), float(imu[2]), float(imu[3])),
        distance_cm=float(data["distance_cm"]),
        humidity=float(data["humidity"]),
        thermistor_c=float(data["thermistor_c"]),
        status_bits=int(data.get("status_bits", 0)),
        protocol_version=str(data.get("protocol_version", "1.0")),
    )


def debug_packet_view(packet: bytes) -> tuple[str, str]:
    """Return (raw_hex, decoded_json_text) for UI debugging panels."""
    raw_hex = packet.hex(" ").upper()
    decoded = _unpack_payload(packet)
    decoded_json = json.dumps(decoded, ensure_ascii=False, indent=2)
    return raw_hex, decoded_json


def frame_to_json_text(frame: CommandFrame | TelemetryFrame) -> str:
    """Render dataclass frames into stable JSON for decoded signal display."""
    return json.dumps(asdict(frame), ensure_ascii=False, indent=2)
