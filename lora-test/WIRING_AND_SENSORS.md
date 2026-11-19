# LoRa Debug & Fix wiring and sensors

The hardware path runs from the PC over USB to `PC_Lora`, over LoRa to `Rover_Lora`, and over UART to `Rover_R3`. The Uno executes the command and returns its response over the same chain.

## Board roles and settings

| Board | Role | Link settings |
| --- | --- | --- |
| `PC_Lora` | Accepts test commands from the GUI and sends them over LoRa | USB serial at 9,600 baud, radio firmware configured for 868 MHz |
| `Rover_Lora` | Bridges the radio link to the Uno and forwards its replies | UART at 4,800 baud, USB for trace monitoring |
| `Rover_R3` | Executes commands and reads back status or sensor data | SoftwareSerial on D2 (RX) and D3 (TX), USB debug on D0/D1 |

The rover-side UART uses a common ground. The MKR WAN 1310 uses 3.3 V I/O. Use suitable logic-level translation where needed, including on the Uno D3 TX to MKR RX path. See the [MKR WAN 1310 datasheet](https://docs.arduino.cc/resources/datasheets/ABX00029-datasheet.pdf).

## Motor board and sensors

| Device | Connections |
| --- | --- |
| Single L298N | Uno D8–D11 to IN1–IN4. OUT1/OUT2 serve the left wheel group and OUT3/OUT4 serve the right wheel group. The motor supply connects to the L298N and shares a ground reference with the rover controller. |
| MMA8451 accelerometer breakout | Uno A4 to SDA, A5 to SCL, and common ground. Use the power input and voltage specified for the breakout. The bench setup used a breakout with a 5 V-compatible VIN input. |
| LED | The board’s D13 LED provides a visible command check. |

The motion and accelerometer firmware variants are [rover_r3](rover_r3/rover_r3.ino) and [rover_r3_accel](rover_r3_accel/rover_r3_accel.ino). If the accelerometer is unavailable, the sensor firmware reports `RESP:MMA8451_OFFLINE` or `RESP:ACCEL_OFFLINE`.

## Verify the link

Start with `HELLO`, then check `STATUS`, `READ_ACCEL`, and LED on/off. The GUI counts `RX: RESP:...` and `RX: DATA:...` as verified remote replies. In the dual-serial GUI, the PC-side LoRa board is the command source and the rover-side USB connection is a trace monitor.

See the [diagnostic workflow and setup](README.md) for the firmware combinations, command codes and test sequence.
