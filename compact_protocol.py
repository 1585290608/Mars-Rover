REQUEST_TO_CODE = {
    "HELLO": "0A",
    "STATUS": "0B",
    "READ_ACCEL": "0C",
    "LED_ON": "0D",
    "LED_OFF": "0E",
    "FORWARD": "10",
    "BACKWARD": "11",
    "LEFT": "12",
    "RIGHT": "13",
    "STOP": "14",
    "PING": "15",
}

CODE_TO_REQUEST = {code: name for name, code in REQUEST_TO_CODE.items()}

STATIC_RESPONSE_TEXT = {
    "8A": "RESP:HELLO_OK",
    "8D": "RESP:LED=ON",
    "8E": "RESP:LED=OFF",
    "90": "RESP:FORWARD",
    "91": "RESP:BACKWARD",
    "92": "RESP:LEFT",
    "93": "RESP:RIGHT",
    "94": "RESP:STOP",
    "9C": "RESP:ACCEL_OFFLINE",
    "9D": "MMA8451_OFFLINE",
    "9E": "RESP:ACCEL_OK",
    "A0": "RESP:R3_BOOT_OK",
}

SENSOR_LED_QUICK_COMMANDS = [
    "HELLO",
    "STATUS",
    "READ_ACCEL",
    "LED_ON",
    "LED_OFF",
]


def normalize_token(text: str) -> str:
    return text.strip().upper()


def is_compact_frame(text: str) -> bool:
    token = normalize_token(text)
    if len(token) < 2:
        return False
    code = token[:2]
    if not all(ch in "0123456789ABCDEF" for ch in code):
        return False
    return len(token) == 2 or token[2] == "|"


def encode_command(command: str) -> tuple[str, str]:
    normalized = normalize_token(command)
    if normalized in REQUEST_TO_CODE:
        return REQUEST_TO_CODE[normalized], normalized
    if is_compact_frame(normalized):
        return normalized, CODE_TO_REQUEST.get(normalized[:2], normalized)
    return command.strip(), command.strip()


def format_tx_text(command: str) -> tuple[str, str]:
    wire, label = encode_command(command)
    if not wire:
        return "", ""
    if label and label != wire:
        return wire, f"{label} -> {wire}"
    return wire, wire


def decode_response_frame(payload: str) -> str:
    raw = payload.strip()
    if not is_compact_frame(raw):
        return raw

    code = raw[:2].upper()
    extra = raw[3:] if len(raw) > 2 and raw[2] == "|" else ""

    if code == "8B":
        return f"RESP:STATUS:{extra}" if extra else "RESP:STATUS"
    if code == "8C":
        return f"RESP:ACCEL:{extra}" if extra else "RESP:ACCEL"
    if code == "9F":
        return f"RESP:ERROR:{extra}" if extra else "RESP:ERROR"

    return STATIC_RESPONSE_TEXT.get(code, raw)


def button_label(command: str) -> str:
    code = REQUEST_TO_CODE.get(command)
    if code is None:
        return command
    return f"{command} / {code}"
