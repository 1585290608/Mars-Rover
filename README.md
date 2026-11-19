# Mars Rover

Two independent desktop applications from the Cardiff University Mars Rover project.

| Application | Purpose | Run from its folder |
| --- | --- | --- |
| [Rover Control Station](rover-control-station/) (D15) | Main operator interface prototype for telemetry, session logging and replay | `python main.py` |
| [LoRa Debug & Fix](lora-test/README_EN.md) (GUI-11) | Hardware diagnostic tool for isolating faults in the LoRa and UART command-and-response chain | `python pc_lora_gui.py` |

## Rover Control Station

D15 is the PyQt6 and Matplotlib desktop interface. It has its own entry point and dependencies. This snapshot uses simulated telemetry and command acknowledgements and can replay accelerometer CSVs saved by the app. [Setup and features](rover-control-station/README.md)

## LoRa Debug & Fix

GUI-11 is a separate Tkinter tool built to diagnose the physical PC-to-rover link. It tests a small set of commands and counts only verified wireless replies. The rover-side trace shows whether the radio received the request, whether it was forwarded over UART, and whether the Uno replied. This made it possible to investigate the radio link and the onboard serial link separately.

During final integration, moving the rover-side UART to SoftwareSerial on the Uno R3’s D2/D3 pins at 4,800 baud restored remote command execution in about 10 minutes.

[Debug workflow and setup](lora-test/README_EN.md) · [中文说明](lora-test/README.md) · [Full debug report](lora-test/LORA_DEBUG_REPORT_EN.md)
