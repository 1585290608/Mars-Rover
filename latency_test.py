import argparse
import time
from collections import defaultdict, deque

import serial

from compact_protocol import REQUEST_TO_CODE, format_tx_text, is_compact_frame

DEFAULT_BAUD = 9600
DEFAULT_TIMEOUT_S = 6.0
DEFAULT_ATTEMPTS = 10
DEFAULT_REPEATS = 5
DEFAULT_INTERVAL_S = 0.25
DEFAULT_MODE = "sequential"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "PC LoRa latency test runner: every command is tested N times, repeated M rounds. "
            "Supports sequential mode (wait for response before next send) and interval mode (fixed send interval)."
        )
    )
    parser.add_argument("port", help="COM port for PC_Lora, e.g. COM8")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="Serial baud rate")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="Response timeout in seconds")
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS, help="Number of attempts per command per round")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS, help="Number of full rounds across all commands")
    parser.add_argument(
        "--interval",
        "--delay",
        dest="interval",
        type=float,
        default=DEFAULT_INTERVAL_S,
        help="Delay between attempts in seconds (in interval mode, fixed send interval)",
    )
    parser.add_argument(
        "--mode",
        choices=["sequential", "interval"],
        default=DEFAULT_MODE,
        help="Send mode: sequential waits for verified response before next send; interval sends at fixed interval.",
    )
    parser.add_argument("--csv", help="Optional CSV output path")
    return parser.parse_args()


def open_serial(port: str, baud: int) -> serial.Serial:
    conn = serial.Serial(port=port, baudrate=baud, timeout=0.2, write_timeout=1)
    try:
        conn.reset_input_buffer()
        conn.reset_output_buffer()
    except (serial.SerialException, OSError, AttributeError):
        pass
    return conn


def read_verified_responses(conn: serial.Serial, timeout_s: float) -> list[str]:
    deadline = time.monotonic() + timeout_s
    buffer = bytearray()
    payloads: list[str] = []

    while time.monotonic() < deadline:
        chunk = conn.read(1024)
        if not chunk:
            continue

        buffer.extend(chunk)
        while b"\n" in buffer:
            raw_line, _, rest = buffer.partition(b"\n")
            buffer[:] = rest
            try:
                line = raw_line.decode("utf-8", errors="replace").strip()
            except UnicodeDecodeError:
                continue

            if not line:
                continue

            if line.startswith("RX:"):
                payload = line[3:].strip()
                if payload.startswith(("RESP:", "DATA:")) or is_compact_frame(payload):
                    payloads.append(payload)

    return payloads


def read_verified_response(conn: serial.Serial, timeout_s: float) -> str | None:
    responses = read_verified_responses(conn, timeout_s)
    return responses[0] if responses else None


def run_round_sequential(
    conn: serial.Serial,
    commands: list[str],
    attempts: int,
    timeout_s: float,
    interval_s: float,
) -> dict[str, list[int | None]]:
    round_results: dict[str, list[int | None]] = {cmd: [] for cmd in commands}

    for command in commands:
        print(f"\n=== Command: {command} ===")
        for attempt in range(1, attempts + 1):
            wire_command, label = format_tx_text(command)
            if not wire_command:
                print(f"  [ERROR] Cannot encode command: {command}")
                round_results[command].append(None)
                continue

            try:
                conn.write((wire_command + "\n").encode("utf-8"))
                conn.flush()
            except (serial.SerialException, OSError) as exc:
                print(f"  [ERROR] Write failed for {command}: {exc}")
                round_results[command].append(None)
                continue

            start = time.monotonic()
            response = read_verified_response(conn, timeout_s)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            if response is None:
                print(f"  attempt {attempt:02d}: TIMEOUT (> {timeout_s:.1f}s)")
                round_results[command].append(None)
            else:
                print(f"  attempt {attempt:02d}: {elapsed_ms} ms -> {response}")
                round_results[command].append(elapsed_ms)

            time.sleep(interval_s)

    return round_results


def run_round_interval(
    conn: serial.Serial,
    commands: list[str],
    attempts: int,
    timeout_s: float,
    interval_s: float,
) -> dict[str, list[int | None]]:
    round_results: dict[str, list[int | None]] = {cmd: [] for cmd in commands}
    pending: deque[tuple[str, float]] = deque()

    for command in commands:
        print(f"\n=== Command: {command} ===")
        for attempt in range(1, attempts + 1):
            wire_command, label = format_tx_text(command)
            if not wire_command:
                print(f"  [ERROR] Cannot encode command: {command}")
                round_results[command].append(None)
                continue

            try:
                conn.write((wire_command + "\n").encode("utf-8"))
                conn.flush()
            except (serial.SerialException, OSError) as exc:
                print(f"  [ERROR] Write failed for {command}: {exc}")
                round_results[command].append(None)
                continue

            sent_at = time.monotonic()
            pending.append((command, sent_at))
            window_deadline = sent_at + interval_s

            while time.monotonic() < window_deadline:
                remaining = window_deadline - time.monotonic()
                responses = read_verified_responses(conn, remaining)
                for response in responses:
                    if pending:
                        pending_command, sent_time = pending.popleft()
                        latency_ms = int((time.monotonic() - sent_time) * 1000)
                        print(f"  attempt {attempt:02d}: {pending_command} -> {latency_ms} ms -> {response}")
                        round_results[pending_command].append(latency_ms)

            if not pending:
                continue

    # wait remaining pending responses after all sends
    while pending:
        command, sent_at = pending[0]
        elapsed = time.monotonic() - sent_at
        remaining = timeout_s - elapsed
        if remaining <= 0:
            while pending:
                cmd, _ = pending.popleft()
                print(f"  {cmd} timed out after {timeout_s:.1f}s")
                round_results[cmd].append(None)
            break

        responses = read_verified_responses(conn, remaining)
        if not responses:
            continue

        for response in responses:
            if pending:
                pending_command, sent_time = pending.popleft()
                latency_ms = int((time.monotonic() - sent_time) * 1000)
                print(f"  {pending_command} -> {latency_ms} ms -> {response}")
                round_results[pending_command].append(latency_ms)

    return round_results


def print_summary(all_results: dict[str, list[int | None]]) -> None:
    print("\n=== Latency Summary ===")
    header = f"{'Command':<12} {'Runs':>4} {'Success':>7} {'Avg(ms)':>8} {'Min(ms)':>8} {'Max(ms)':>8}"
    print(header)
    print("-" * len(header))

    for command, latencies in all_results.items():
        success_values = [value for value in latencies if value is not None]
        success_count = len(success_values)
        total_count = len(latencies)
        avg = int(sum(success_values) / success_count) if success_count else 0
        min_v = min(success_values) if success_values else 0
        max_v = max(success_values) if success_values else 0
        print(f"{command:<12} {total_count:>4} {success_count:>7} {avg:>8} {min_v:>8} {max_v:>8}")


def save_csv(path: str, all_results: dict[str, list[int | None]]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("command,attempt,latency_ms\n")
        for command, latencies in all_results.items():
            for idx, latency in enumerate(latencies, start=1):
                handle.write(f"{command},{idx},{'' if latency is None else latency}\n")
    print(f"Saved detailed CSV to: {path}")


def main() -> None:
    args = parse_args()
    commands = list(REQUEST_TO_CODE.keys())

    print(f"Opening serial port {args.port} @ {args.baud}...")
    with open_serial(args.port, args.baud) as conn:
        all_results: dict[str, list[int | None]] = defaultdict(list)

        for repeat in range(1, args.repeats + 1):
            print(f"\n########## Repeat {repeat}/{args.repeats} ##########")
            if args.mode == "sequential":
                round_results = run_round_sequential(conn, commands, args.attempts, args.timeout, args.interval)
            else:
                round_results = run_round_interval(conn, commands, args.attempts, args.timeout, args.interval)
            for command, values in round_results.items():
                all_results[command].extend(values)

        print_summary(all_results)

        if args.csv:
            save_csv(args.csv, all_results)


if __name__ == "__main__":
    main()
