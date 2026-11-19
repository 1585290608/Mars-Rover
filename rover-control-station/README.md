# Rover Control Station

D15 is the main desktop operator interface prototype for the Mars Rover project, developed in Python with PyQt6 and Matplotlib. It runs as a standalone application with its own entry point and dependencies. D15 identifies the original snapshot.

## Run

Requires Python 3.10 or newer. In this directory, run:

```sh
python -m pip install -r requirements.txt
python main.py
```

The Connect action in this snapshot starts the simulator. It generates telemetry and command acknowledgements to exercise the interface without physical equipment. Use Replay to review accelerometer data saved by the application.

The interface includes telemetry plots, command acknowledgement and retry handling, staggered refresh timers, alerts and an emergency-stop interface. Accelerometer samples are saved locally as CSV and session settings and notes as JSON in `session_logs/`. Starting a new logging run can replace the current CSV. Copy any session you want to keep before starting a new one.

The optional XOR mode is a protocol demonstration in the simulator. It is disabled by default and uses a public demonstration value.

For bench testing with the physical Arduino and LoRa hardware, use the separate [LoRa Debug & Fix application](../lora-test/README_EN.md).
