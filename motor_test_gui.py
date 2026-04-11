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


class MotorTestGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PC_Lora Sensor / LED Control + Rover_Lora Monitor")
        self.geometry("1080x680")
        self.minsize(980, 620)

        self.pc_lora_conn = None
        self.rover_lora_conn = None
        self.pc_lora_rx_buffer = bytearray()
        self.rover_lora_rx_buffer = bytearray()

        self.pc_lora_port_var = tk.StringVar()
        self.rover_lora_port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value="9600")
        self.status_var = tk.StringVar(value="PC_Lora: disconnected | Rover_Lora monitor: disconnected")
        self.pc_lora_resp_var = tk.StringVar(value="PC_Lora: no verified response")
        self.rover_r3_resp_var = tk.StringVar(value="Rover_R3: no verified response")
        self.last_latency_var = tk.StringVar(value="Latency: N/A")
        self.led_var = tk.BooleanVar(value=False)
        self.led_state_var = tk.StringVar(value="OFF")
        self.custom_var = tk.StringVar()

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

        top = ttk.LabelFrame(self, text="Serial Ports")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        top.columnconfigure(1, weight=1)
        top.columnconfigure(4, weight=1)

        ttk.Label(top, text="PC_Lora control port").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.pc_lora_port_box = ttk.Combobox(top, textvariable=self.pc_lora_port_var, state="normal")
        self.pc_lora_port_box.grid(row=0, column=1, padx=8, pady=8, sticky="ew")

        ttk.Label(top, text="Rover_Lora monitor port").grid(row=0, column=3, padx=8, pady=8, sticky="w")
        self.rover_lora_port_box = ttk.Combobox(top, textvariable=self.rover_lora_port_var, state="normal")
        self.rover_lora_port_box.grid(row=0, column=4, padx=8, pady=8, sticky="ew")

        ttk.Label(top, text="Baud").grid(row=1, column=0, padx=8, pady=0, sticky="w")
        ttk.Entry(top, width=10, textvariable=self.baud_var).grid(row=1, column=1, padx=8, pady=(0, 8), sticky="w")
        ttk.Label(top, text="Manual COM entry supported, for example COM8").grid(
            row=1,
            column=4,
            padx=8,
            pady=(0, 8),
            sticky="w",
        )

        ttk.Button(top, text="Refresh", command=self.refresh_ports).grid(row=0, column=2, padx=6, pady=8)
        ttk.Button(top, text="Connect PC_Lora", command=self.connect_pc_lora).grid(row=0, column=5, padx=6, pady=8)
        ttk.Button(top, text="Connect Rover monitor", command=self.connect_rover_lora).grid(row=1, column=5, padx=6, pady=(0, 8))
        ttk.Button(top, text="Disconnect All", command=self.disconnect_all).grid(row=0, column=6, rowspan=2, padx=(6, 10), pady=8, sticky="ns")

        status = ttk.Frame(self)
        status.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        status.columnconfigure(1, weight=1)
        status.columnconfigure(3, weight=1)

        ttk.Label(status, text="Status").grid(row=0, column=0, padx=(0, 8), sticky="w")
        ttk.Label(status, textvariable=self.status_var).grid(row=0, column=1, sticky="w")
        ttk.Label(status, textvariable=self.pc_lora_resp_var).grid(row=0, column=2, padx=(20, 8), sticky="w")
        ttk.Label(status, textvariable=self.rover_r3_resp_var).grid(row=0, column=3, sticky="w")

        ttk.Label(status, text="Accel").grid(row=0, column=4, padx=(20, 8), sticky="w")
        self.accel_indicator = tk.Label(status, text="UNKNOWN", width=10, bg="#FFD700")
        self.accel_indicator.grid(row=0, column=5, sticky="w")
        ttk.Label(status, text="Verified link").grid(row=0, column=6, padx=(20, 8), sticky="w")
        self.lora_indicator = tk.Label(status, text="WARN", width=10, bg="#FFD700")
        self.lora_indicator.grid(row=0, column=7, sticky="w")
        ttk.Label(status, text="R3 LED").grid(row=0, column=8, padx=(20, 8), sticky="w")
        self.led_indicator = tk.Label(status, text="OFF", width=10, bg="#FF0000")
        self.led_indicator.grid(row=0, column=9, sticky="w")
        ttk.Label(status, textvariable=self.last_latency_var).grid(row=0, column=10, padx=(20, 8), sticky="w")
        ttk.Button(status, text="Clear Log", command=self.clear_log).grid(row=0, column=11, padx=(20, 0), sticky="e")

        content = ttk.Frame(self)
        content.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        content.columnconfigure(0, weight=0)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        controls = ttk.Frame(content)
        controls.grid(row=0, column=0, sticky="nsw", padx=(0, 12))

        note = ttk.Label(
            controls,
            text=(
                "Current test scope: accelerometer and LED only. "
                "Wire protocol uses compact opcodes like 0A / 0B. "
                "Only PC_Lora lines formatted as RX: RESP:... or RX: DATA:... "
                "count as real rover replies."
            ),
            wraplength=300,
            justify="left",
        )
        note.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        command_box = ttk.LabelFrame(controls, text="Command")
        command_box.grid(row=1, column=0, sticky="ew")
        command_box.columnconfigure(0, weight=1)
        ttk.Entry(command_box, textvariable=self.custom_var).grid(row=0, column=0, padx=8, pady=8, sticky="ew")

        send_frame = ttk.Frame(command_box)
        send_frame.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")
        send_frame.columnconfigure(0, weight=1)
        send_frame.columnconfigure(1, weight=1)
        ttk.Button(send_frame, text="Send via PC_Lora", command=self.send_to_pc_lora).grid(row=0, column=0, padx=4, sticky="ew")
        ttk.Button(send_frame, text="Rover_Lora monitor only", state="disabled").grid(row=0, column=1, padx=4, sticky="ew")

        quick = ttk.LabelFrame(controls, text="Quick Commands")
        quick.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        for idx, cmd in enumerate(SENSOR_LED_QUICK_COMMANDS):
            row = idx // 2
            col = idx % 2
            ttk.Button(
                quick,
                text=button_label(cmd),
                command=lambda c=cmd: self.send_to_pc_lora(c),
            ).grid(row=row, column=col, padx=6, pady=6, sticky="ew")

        led_frame = ttk.LabelFrame(controls, text="R3 LED Control")
        led_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(
            led_frame,
            text="LED On",
            variable=self.led_var,
            command=self.on_led_toggle,
        ).grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ttk.Label(led_frame, textvariable=self.led_state_var).grid(row=0, column=1, padx=8, pady=8, sticky="w")

        log_frame = ttk.LabelFrame(content, text="Serial Log")
        log_frame.grid(row=0, column=1, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set, state="disabled")

    def refresh_ports(self) -> None:
        if list_ports is None:
            self.pc_lora_port_box["values"] = ()
            self.rover_lora_port_box["values"] = ()
            return

        ports = [f"{port.device} ({port.description})" for port in list_ports.comports()]
        self.pc_lora_port_box["values"] = ports
        self.rover_lora_port_box["values"] = ports
        if ports:
            if not self.pc_lora_port_var.get():
                self.pc_lora_port_var.set(ports[0])
            if not self.rover_lora_port_var.get():
                self.rover_lora_port_var.set(ports[0])
        self.log("Ports refreshed: " + (", ".join(ports) if ports else "none found"))

    def connect_pc_lora(self) -> None:
        if self.pc_lora_conn is not None:
            self.log("Closing existing PC_Lora connection before reconnect", "debug")
            self._close_conn("PC_Lora")
        self.pc_lora_conn = self._connect_port(self.pc_lora_port_var.get(), "PC_Lora")
        self._update_status()

    def connect_rover_lora(self) -> None:
        if self.rover_lora_conn is not None:
            self.log("Closing existing Rover_Lora monitor connection before reconnect", "debug")
            self._close_conn("Rover_Lora")
        self.rover_lora_conn = self._connect_port(self.rover_lora_port_var.get(), "Rover_Lora monitor")
        self._update_status()

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

    def _close_conn(self, label: str) -> None:
        if label == "PC_Lora":
            conn = self.pc_lora_conn
            self.pc_lora_conn = None
            self.pc_lora_rx_buffer.clear()
        else:
            conn = self.rover_lora_conn
            self.rover_lora_conn = None
            self.rover_lora_rx_buffer.clear()

        if conn is not None:
            try:
                conn.close()
            except (SerialException, OSError):
                pass

    def disconnect_all(self) -> None:
        self._close_conn("PC_Lora")
        self._close_conn("Rover_Lora")
        self._clear_pending("Disconnected")
        self.set_indicator(self.lora_indicator, "warn")
        self._update_status()
        self.log("Disconnected all ports")

    def _update_status(self) -> None:
        pc_state = "connected" if self.pc_lora_conn else "disconnected"
        rover_state = "connected" if self.rover_lora_conn else "disconnected"
        self.status_var.set(f"PC_Lora: {pc_state} | Rover_Lora monitor: {rover_state}")

    def send_to_pc_lora(self, command: str | None = None) -> None:
        if command is None:
            command = self.custom_var.get().strip()
        self._send_command(self.pc_lora_conn, command, "PC_Lora")

    def send_to_rover_lora(self, command: str | None = None) -> None:
        _ = command
        self.log("Direct USB send to Rover_Lora is disabled. Use PC_Lora only.", "error")

    def _send_command(self, conn, command: str, label: str) -> None:
        if conn is None:
            messagebox.showwarning("Not connected", f"Connect the {label} port first.")
            return
        if not command:
            return

        try:
            wire_command, tx_text = format_tx_text(command)
            conn.write((wire_command + "\n").encode("utf-8"))
            conn.flush()
            self.pending_command = tx_text or wire_command
            self.pending_started_at = time.monotonic()
            self.last_latency_var.set("Latency: waiting")
            self.set_indicator(self.lora_indicator, "warn")
            self.log(f"{label} TX: {tx_text or wire_command}")
        except (SerialException, OSError) as exc:
            self.log(f"{label} send failed: {exc}", "error")
            self._close_conn("PC_Lora")
            self._clear_pending("Disconnected after send failure")
            self.set_indicator(self.lora_indicator, "bad")
            self._update_status()

    def on_led_toggle(self) -> None:
        if self.led_var.get():
            self.send_to_pc_lora("LED_ON")
        else:
            self.send_to_pc_lora("LED_OFF")

    def poll_serial(self) -> None:
        self._poll_conn(self.pc_lora_conn, self.pc_lora_rx_buffer, "PC_Lora")
        self._poll_conn(self.rover_lora_conn, self.rover_lora_rx_buffer, "Rover_Lora")
        self._check_timeout()
        self.after(100, self.poll_serial)

    def _poll_conn(self, conn, buffer: bytearray, label: str) -> None:
        if conn is None:
            return

        try:
            waiting = conn.in_waiting
            chunk = conn.read(waiting or 1)
        except (SerialException, OSError) as exc:
            self.log(f"{label} read failed: {exc}", "error")
            if label == "PC_Lora":
                self._close_conn("PC_Lora")
                self._clear_pending("Disconnected after read failure")
                self.set_indicator(self.lora_indicator, "bad")
            else:
                self._close_conn("Rover_Lora")
            self._update_status()
            return

        if chunk:
            buffer.extend(chunk)
            while b"\n" in buffer:
                raw_line, _, rest = buffer.partition(b"\n")
                buffer[:] = rest
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line:
                    self.handle_line(line, label)

    def _check_timeout(self) -> None:
        if not self.pending_command or self.pending_started_at is None:
            return

        elapsed_ms = int((time.monotonic() - self.pending_started_at) * 1000)
        if elapsed_ms < COMMAND_TIMEOUT_MS:
            return

        self.pc_lora_resp_var.set(f"PC_Lora: TIMEOUT waiting for {self.pending_command}")
        self.rover_r3_resp_var.set(f"Rover_R3: no verified reply to {self.pending_command}")
        self.last_latency_var.set(f"Latency: timeout > {COMMAND_TIMEOUT_MS} ms")
        self.set_indicator(self.lora_indicator, "bad")
        self.log(f"Timeout waiting for verified rover reply to {self.pending_command}", "error")
        self._clear_pending()

    def _clear_pending(self, latency_text: str | None = None) -> None:
        self.pending_command = ""
        self.pending_started_at = None
        if latency_text is not None:
            self.last_latency_var.set(f"Latency: {latency_text}")

    def handle_line(self, line: str, label: str) -> None:
        if label == "PC_Lora":
            self._handle_pc_lora_line(line)
            return

        self.log(f"Rover_Lora monitor: {line}", "monitor")

    def _handle_pc_lora_line(self, line: str) -> None:
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
            self.log(f"PC_Lora ignored remote non-payload: {payload}", "debug")
            return

        if normalized.startswith("TX:") or normalized.startswith("TRACE:"):
            self.log(f"PC_Lora local: {normalized}", "debug")
            return

        if normalized.startswith("RESP:") or normalized.startswith("DATA:"):
            self.log(f"PC_Lora ignored unscoped line: {normalized}", "debug")
            return

        self.log(f"PC_Lora local: {normalized}", "debug")

    def _handle_verified_remote_payload(self, payload: str, raw_payload: str | None = None) -> None:
        self.pc_lora_resp_var.set(f"PC_Lora: {payload}")
        self.rover_r3_resp_var.set(f"Rover_R3: {payload}")

        if self.pending_started_at is not None:
            elapsed_ms = int((time.monotonic() - self.pending_started_at) * 1000)
            self.last_latency_var.set(f"Latency: {elapsed_ms} ms")
        else:
            self.last_latency_var.set("Latency: remote event")

        self._clear_pending()
        self.set_indicator(self.lora_indicator, "good")
        self._update_state_from_payload(payload)
        if raw_payload and raw_payload != payload:
            self.log(f"Verified remote: {raw_payload} => {payload}", "remote")
        else:
            self.log(f"Verified remote: {payload}", "remote")

    def _update_state_from_payload(self, payload: str) -> None:
        if payload.startswith("RESP:"):
            resp = payload[5:].strip()

            if "ACCEL_OK" in resp or "IMU=ON" in resp:
                self.set_indicator(self.accel_indicator, "good")
            elif "MMA8451_OFFLINE" in resp or "ACCEL_OFFLINE" in resp or "IMU=OFF" in resp:
                self.set_indicator(self.accel_indicator, "bad")
            elif "ACCEL:" in resp:
                self.set_indicator(self.accel_indicator, "good")

            if "LED=ON" in resp:
                self.led_state_var.set("ON")
                self.led_indicator.configure(text="ON", bg="#00FF00")
                self.led_var.set(True)
            elif "LED=OFF" in resp:
                self.led_state_var.set("OFF")
                self.led_indicator.configure(text="OFF", bg="#FF0000")
                self.led_var.set(False)

        if payload.startswith("DATA:"):
            self.set_indicator(self.accel_indicator, "warn")

    def set_indicator(self, widget: tk.Label, state: str) -> None:
        colors = {
            "good": ("OK", "#00FF00"),
            "warn": ("WARN", "#FFD700"),
            "bad": ("FAIL", "#FF0000"),
            "unknown": ("UNKNOWN", "#FFFF00"),
        }
        text, color = colors.get(state, colors["unknown"])
        widget.configure(text=text, bg=color)

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def log(self, message: str, level: str = "info") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        prefix = {
            "info": "INFO",
            "error": "ERROR",
            "debug": "DEBUG",
            "remote": "REMOTE",
            "monitor": "MONITOR",
        }.get(level, "LOG")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {prefix}: {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def on_close(self) -> None:
        self.disconnect_all()
        self.destroy()


if __name__ == "__main__":
    app = MotorTestGUI()
    app.mainloop()
