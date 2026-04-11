import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from compact_protocol import (
    SENSOR_LED_QUICK_COMMANDS,
    button_label,
    decode_response_frame,
    format_tx_text,
    is_compact_frame,
)

try:
    import serial
    from serial import SerialException
    from serial.tools import list_ports
except ModuleNotFoundError as exc:
    serial = None
    list_ports = None
    SERIAL_IMPORT_ERROR = exc

    class SerialException(Exception):
        pass
else:
    SERIAL_IMPORT_ERROR = None


COMMAND_TIMEOUT_MS = 4000


class PCLoraGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PC LoRa Sensor / LED GUI")
        self.geometry("900x540")
        self.minsize(860, 520)

        self.conn = None
        self.rx_buffer = bytearray()

        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value="9600")
        self.status_var = tk.StringVar(value="Disconnected")
        self.last_resp_var = tk.StringVar(value="No verified rover response yet")
        self.last_latency_var = tk.StringVar(value="Latency: N/A")
        self.led_state_var = tk.StringVar(value="LED: OFF")
        self.accel_value_var = tk.StringVar(value="ACCEL: N/A")
        self.accel_ind_state = tk.StringVar(value="UNKNOWN")
        self.command_var = tk.StringVar()

        self.pending_command = ""
        self.pending_started_at = None

        self._build_ui()
        self.refresh_ports()
        self.after(100, self.poll_serial)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        if SERIAL_IMPORT_ERROR is not None:
            self.log(
                "pyserial is not installed. Run: pip install -r requirements.txt",
                "error",
            )

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        port_frame = ttk.LabelFrame(self, text="PC LoRa Port")
        port_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        port_frame.columnconfigure(1, weight=1)

        ttk.Label(port_frame, text="Serial Port").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.port_box = ttk.Combobox(port_frame, textvariable=self.port_var, state="normal")
        self.port_box.grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        ttk.Button(port_frame, text="Refresh", command=self.refresh_ports).grid(row=0, column=2, padx=6, pady=8)
        ttk.Button(port_frame, text="Connect", command=self.connect_port).grid(row=0, column=3, padx=6, pady=8)
        ttk.Button(port_frame, text="Disconnect", command=self.disconnect_port).grid(row=0, column=4, padx=6, pady=8)

        ttk.Label(port_frame, text="Baud").grid(row=1, column=0, padx=8, pady=(0, 8), sticky="w")
        ttk.Entry(port_frame, width=10, textvariable=self.baud_var).grid(row=1, column=1, padx=8, pady=(0, 8), sticky="w")
        ttk.Label(port_frame, text="Supports manual COM entry, for example COM8").grid(
            row=1,
            column=2,
            columnspan=3,
            padx=8,
            pady=(0, 8),
            sticky="w",
        )

        status_frame = ttk.Frame(self)
        status_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        status_frame.columnconfigure(1, weight=1)

        ttk.Label(status_frame, text="Status:").grid(row=0, column=0, padx=(0, 8), sticky="w")
        ttk.Label(status_frame, textvariable=self.status_var).grid(row=0, column=1, sticky="w")
        ttk.Label(status_frame, textvariable=self.led_state_var).grid(row=0, column=2, padx=(20, 8), sticky="w")
        self.led_indicator = tk.Label(status_frame, text="OFF", width=8, bg="#FF0000")
        self.led_indicator.grid(row=0, column=3, sticky="w")
        ttk.Label(status_frame, textvariable=self.accel_value_var).grid(row=0, column=4, padx=(20, 8), sticky="w")
        self.accel_indicator = tk.Label(status_frame, textvariable=self.accel_ind_state, width=8, bg="#FFD700")
        self.accel_indicator.grid(row=0, column=5, sticky="w")
        ttk.Label(status_frame, text="Last verified response:").grid(row=0, column=6, padx=(20, 8), sticky="w")
        ttk.Label(status_frame, textvariable=self.last_resp_var).grid(row=0, column=7, sticky="w")
        ttk.Label(status_frame, textvariable=self.last_latency_var).grid(row=0, column=8, padx=(20, 8), sticky="w")
        ttk.Button(status_frame, text="Clear Log", command=self.clear_log).grid(row=0, column=9, padx=(20, 0), sticky="e")

        body = ttk.Frame(self)
        body.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)

        command_frame = ttk.LabelFrame(body, text="Command")
        command_frame.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        command_frame.columnconfigure(0, weight=1)

        ttk.Label(
            command_frame,
            text="Current test scope: accelerometer and LED only. Wire protocol uses compact opcodes like 0A / 0B.",
            wraplength=220,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, padx=8, pady=(8, 0), sticky="w")

        ttk.Entry(command_frame, textvariable=self.command_var).grid(row=1, column=0, padx=8, pady=8, sticky="ew")
        ttk.Button(command_frame, text="Send", command=self.send_command).grid(row=1, column=1, padx=8, pady=8)

        quick_frame = ttk.LabelFrame(command_frame, text="Quick Commands")
        quick_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        for idx, cmd in enumerate(SENSOR_LED_QUICK_COMMANDS):
            row = idx // 2
            col = idx % 2
            ttk.Button(
                quick_frame,
                text=button_label(cmd),
                command=lambda c=cmd: self.send_command(c),
            ).grid(row=row, column=col, padx=6, pady=6, sticky="ew")

        tx_frame = ttk.LabelFrame(body, text="PC -> LoRa Sent")
        tx_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 6))
        tx_frame.columnconfigure(0, weight=1)
        tx_frame.rowconfigure(0, weight=1)

        self.tx_text = tk.Text(tx_frame, wrap="word", height=10)
        self.tx_text.grid(row=0, column=0, sticky="nsew")
        tx_scroll = ttk.Scrollbar(tx_frame, orient="vertical", command=self.tx_text.yview)
        tx_scroll.grid(row=0, column=1, sticky="ns")
        self.tx_text.configure(yscrollcommand=tx_scroll.set, state="disabled")

        rx_frame = ttk.LabelFrame(body, text="Verified / Debug Log")
        rx_frame.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        rx_frame.columnconfigure(0, weight=1)
        rx_frame.rowconfigure(0, weight=1)

        self.rx_text = tk.Text(rx_frame, wrap="word", height=10)
        self.rx_text.grid(row=0, column=0, sticky="nsew")
        rx_scroll = ttk.Scrollbar(rx_frame, orient="vertical", command=self.rx_text.yview)
        rx_scroll.grid(row=0, column=1, sticky="ns")
        self.rx_text.configure(yscrollcommand=rx_scroll.set, state="disabled")

    def refresh_ports(self) -> None:
        if list_ports is None:
            self.port_box["values"] = ()
            return

        ports = [f"{port.device} ({port.description})" for port in list_ports.comports()]
        self.port_box["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])
        self.log("Ports refreshed: " + (", ".join(ports) if ports else "none found"))

    def connect_port(self) -> None:
        if self.conn is not None:
            self.log("Closing existing PC_Lora connection before reconnect", "debug")
            self._close_conn()
        self.conn = self._connect_port(self.port_var.get(), "PC_Lora")
        self._update_status()

    def disconnect_port(self) -> None:
        self._close_conn()
        self._clear_pending("Disconnected")
        self._update_status()
        self.log("Disconnected PC_Lora")

    def _close_conn(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except (SerialException, OSError):
                pass
        self.conn = None
        self.rx_buffer.clear()

    def _connect_port(self, selection: str, label: str):
        if serial is None:
            messagebox.showerror("Missing dependency", "pyserial is not installed.")
            return None

        if not selection.strip():
            messagebox.showwarning("Port needed", f"Pick or type a COM port for {label} first.")
            return None

        port = selection.split()[0]
        try:
            baud = int(self.baud_var.get().strip())
        except ValueError:
            messagebox.showwarning("Bad baud", "Baud must be an integer.")
            return None

        try:
            conn = serial.Serial(port=port, baudrate=baud, timeout=0, write_timeout=0.5)
            try:
                conn.reset_input_buffer()
                conn.reset_output_buffer()
            except (SerialException, OSError, AttributeError):
                pass
            self.log(f"{label} connected to {port} @ {baud}")
            return conn
        except (SerialException, OSError, ValueError) as exc:
            messagebox.showerror("Connect failed", str(exc))
            self.log(f"{label} connect failed: {exc}", "error")
            return None

    def _update_status(self) -> None:
        self.status_var.set("Connected" if self.conn else "Disconnected")

    def send_command(self, command: str | None = None) -> None:
        if self.conn is None:
            messagebox.showwarning("Not connected", "Connect the PC_Lora port first.")
            return

        if command is None:
            command = self.command_var.get().strip()

        if not command:
            return

        try:
            wire_command, tx_text = format_tx_text(command)
            self.conn.write((wire_command + "\n").encode("utf-8"))
            self.conn.flush()
            self.pending_command = tx_text or wire_command
            self.pending_started_at = time.monotonic()
            self.last_latency_var.set("Latency: waiting")
            self.log_tx(tx_text or wire_command)
        except (SerialException, OSError) as exc:
            self.log_rx(f"Send failed: {exc}", "error")
            self._close_conn()
            self._clear_pending("Disconnected after send failure")
            self._update_status()

    def poll_serial(self) -> None:
        if self.conn is not None:
            try:
                waiting = self.conn.in_waiting
                chunk = self.conn.read(waiting or 1)
            except (SerialException, OSError) as exc:
                self.log(f"Read failed: {exc}", "error")
                self._close_conn()
                self._clear_pending("Disconnected after read failure")
                self._update_status()
            else:
                if chunk:
                    self.rx_buffer.extend(chunk)
                    while b"\n" in self.rx_buffer:
                        raw_line, _, rest = self.rx_buffer.partition(b"\n")
                        self.rx_buffer[:] = rest
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if line:
                            self.handle_response(line)

        self._check_timeout()
        self.after(100, self.poll_serial)

    def _check_timeout(self) -> None:
        if not self.pending_command or self.pending_started_at is None:
            return

        elapsed_ms = int((time.monotonic() - self.pending_started_at) * 1000)
        if elapsed_ms < COMMAND_TIMEOUT_MS:
            return

        self.last_resp_var.set(f"TIMEOUT waiting for {self.pending_command}")
        self.last_latency_var.set(f"Latency: timeout > {COMMAND_TIMEOUT_MS} ms")
        self.log_rx(f"Timeout waiting for verified rover reply to {self.pending_command}", "error")
        self._clear_pending()

    def _clear_pending(self, latency_text: str | None = None) -> None:
        self.pending_command = ""
        self.pending_started_at = None
        if latency_text is not None:
            self.last_latency_var.set(f"Latency: {latency_text}")

    def clear_log(self) -> None:
        self.tx_text.configure(state="normal")
        self.tx_text.delete("1.0", "end")
        self.tx_text.configure(state="disabled")
        self.rx_text.configure(state="normal")
        self.rx_text.delete("1.0", "end")
        self.rx_text.configure(state="disabled")

    def log_tx(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.tx_text.configure(state="normal")
        self.tx_text.insert("end", f"[{timestamp}] TX: {message}\n")
        self.tx_text.see("end")
        self.tx_text.configure(state="disabled")

    def log_rx(self, message: str, level: str = "info") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        prefix = {
            "info": "INFO",
            "remote": "REMOTE",
            "error": "ERROR",
            "debug": "DEBUG",
        }.get(level, "LOG")
        self.rx_text.configure(state="normal")
        self.rx_text.insert("end", f"[{timestamp}] {prefix}: {message}\n")
        self.rx_text.see("end")
        self.rx_text.configure(state="disabled")

    def log(self, message: str, level: str = "info") -> None:
        self.log_rx(message, level)

    def set_indicator(self, widget: tk.Label, state: str) -> None:
        colors = {
            "good": ("OK", "#00FF00"),
            "warn": ("WARN", "#FFD700"),
            "bad": ("FAIL", "#FF0000"),
            "unknown": ("UNKNOWN", "#FFFF00"),
        }
        text, color = colors.get(state, colors["unknown"])
        widget.configure(text=text, bg=color)

    def _is_float(self, value: str) -> bool:
        try:
            float(value)
            return True
        except ValueError:
            return False

    def handle_response(self, line: str) -> None:
        normalized = line.strip()

        if normalized.startswith("RX:"):
            payload = normalized[3:].strip()
            if payload.startswith("RESP:") or payload.startswith("DATA:"):
                self._handle_verified_remote_payload(payload)
                return
            if is_compact_frame(payload):
                decoded = decode_response_frame(payload)
                self._handle_verified_remote_payload(decoded, raw_payload=payload)
                return
            self.log_rx(f"Ignored remote non-payload line: {payload}", "debug")
            return

        if normalized.startswith("TX:") or normalized.startswith("TRACE:"):
            self.log_rx(normalized, "debug")
            return

        if normalized.startswith("RESP:") or normalized.startswith("DATA:"):
            self.log_rx(f"Ignored unscoped local line: {normalized}", "debug")
            return

        self.log_rx(normalized, "debug")

    def _handle_verified_remote_payload(self, payload: str, raw_payload: str | None = None) -> None:
        self.last_resp_var.set(payload)

        if self.pending_started_at is not None:
            elapsed_ms = int((time.monotonic() - self.pending_started_at) * 1000)
            self.last_latency_var.set(f"Latency: {elapsed_ms} ms")
        else:
            self.last_latency_var.set("Latency: remote event")

        self._clear_pending()
        if raw_payload and raw_payload != payload:
            self.log_rx(f"{raw_payload} => {payload}", "remote")
        else:
            self.log_rx(payload, "remote")
        self._update_remote_state(payload)

    def _update_remote_state(self, payload: str) -> None:
        if payload.startswith("RESP:"):
            resp = payload[5:].strip()

            if "LED=ON" in resp:
                self.led_state_var.set("LED: ON")
                self.led_indicator.configure(text="ON", bg="#00FF00")
            elif "LED=OFF" in resp:
                self.led_state_var.set("LED: OFF")
                self.led_indicator.configure(text="OFF", bg="#FF0000")

            if resp.startswith("ACCEL:"):
                accel_text = resp.split(":", 1)[1].strip()
                self._update_accel_from_text(accel_text)
                return

            if "ACCEL_OK" in resp or "IMU=ON" in resp:
                self.accel_value_var.set("ACCEL: OK")
                self.set_indicator(self.accel_indicator, "good")
                return

            if "MMA8451_OFFLINE" in resp or "ACCEL_OFFLINE" in resp or "IMU=OFF" in resp:
                self.accel_value_var.set("ACCEL: OFFLINE")
                self.set_indicator(self.accel_indicator, "bad")
                return

        if payload.startswith("DATA:"):
            self._update_accel_from_text(payload[5:].strip())

    def _update_accel_from_text(self, accel_text: str) -> None:
        cleaned = accel_text.replace(",", " ").replace(";", " ")
        parts = [part for part in cleaned.split() if part]
        if len(parts) == 3 and all(self._is_float(part) for part in parts):
            ax, ay, az = [float(part) for part in parts]
            self.accel_value_var.set(f"ACCEL: {ax:.3f}, {ay:.3f}, {az:.3f}")
            self.set_indicator(self.accel_indicator, "good")
            return

        self.accel_value_var.set(f"ACCEL: {accel_text}")
        self.set_indicator(self.accel_indicator, "warn")

    def on_close(self) -> None:
        self._close_conn()
        self.destroy()


if __name__ == "__main__":
    app = PCLoraGUI()
    app.mainloop()
