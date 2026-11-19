# Mars Rover

This repository contains two independent desktop applications from the Cardiff University Mars Rover project.

| Application | What it does | Run from its folder |
| --- | --- | --- |
| [Rover Control Station](rover-control-station/) | D15 operator interface prototype for viewing telemetry, tracking commands, logging sessions and replaying recorded accelerometer data | `python main.py` |
| [LoRa Test & Diagnostics](lora-test/) | GUI-11 hardware test utility for checking the PC-to-rover LoRa and UART link | `python pc_lora_gui.py` |

## Rover Control Station

The main desktop interface uses PyQt6 and Matplotlib. This snapshot uses simulated telemetry and command acknowledgements to exercise the interface. It also supports replay from an accelerometer CSV recorded by the app.

See the [Rover Control Station setup](rover-control-station/README.md).

## LoRa Test & Diagnostics

The separate Tkinter utility was used on physical hardware to check remote LED control, status replies and accelerometer readback. It contains the Arduino sketches, wiring notes and bench-test data. Testing the link independently helped locate an integration fault. Moving the rover-side UART to SoftwareSerial on the Uno R3’s D2/D3 pins at 4,800 baud restored remote command execution in about 10 minutes during final integration.

See the [LoRa test setup in English](lora-test/README_EN.md) or the [Chinese test notes](lora-test/README.md).
