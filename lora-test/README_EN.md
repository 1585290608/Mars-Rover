# GUI/11 LoRa Control Test

This folder is now used to verify the following actual link:

`GUI -> PC USB -> PC_Lora -> LoRa -> Rover_Lora -> UART -> Rover_R3`

Only when this full chain works should the GUI show "received response" and latency.

## Recommended test focus

For this round of debugging, only two function categories are suggested:

- `accelerometer`
- `LED`

Motor-related commands are still present in firmware, but the GUI no longer places them in the main test button by default to avoid interfering with the current link validation.

## Compact command protocol

Version `11` now uses a fixed short-code protocol. The idea is similar to the fixed opcodes in `Final1`, but it uses two-digit hexadecimal text codes instead, which are easier for serial debugging.

Request codes:

- `0A` = `HELLO`
- `0B` = `STATUS`
- `0C` = `READ_ACCEL`
- `0D` = `LED_ON`
- `0E` = `LED_OFF`
- `10` = `FORWARD`
- `11` = `BACKWARD`
- `12` = `LEFT`
- `13` = `RIGHT`
- `14` = `STOP`
- `15` = `PING`

Response codes:

- `8A` = `HELLO_OK`
- `8B|...` = `STATUS`, followed by a payload
- `8C|...` = `ACCEL`, followed by 3-axis data
- `8D` = `LED=ON`
- `8E` = `LED=OFF`
- `9C` = `ACCEL_OFFLINE`
- `9D` = `MMA8451_OFFLINE`
- `9E` = `ACCEL_OK`
- `9F|...` = error or unknown command
- `A0` = `R3_BOOT_OK`

The GUI buttons still show human-readable command labels, but the wire format is the short code. For example:

- GUI `HELLO` sends `0A` on the wire
- GUI `STATUS` sends `0B`
- R3 returns `8A`, and the GUI automatically displays `RESP:HELLO_OK`

Compatibility notes:

- You can enter `HELLO` in the GUI custom command field.
- You can also enter `0A` directly.
- Both `PC_Lora` and `Rover_R3` currently accept text commands and short-code commands.

## Key fixes in this release

- `pc_lora_gui.py` now only treats `RX: RESP:...` or `RX: DATA:...` from the PC_Lora serial port as verified remote replies.
- `motor_test_gui.py` also only trusts actual remote data returned by `PC_Lora`.
- `rover_lora/rover_lora.ino` now disables direct USB -> Serial1 -> R3 bypass.
- `Rover_Lora` still powers from USB when connected to a computer, but it now only outputs local `TRACE:` watch logs and will not falsely claim LoRa success because of the local USB connection.
- `rover_r3_accel/rover_r3_accel.ino` fixed its previous compile issue and completed motor/LED/status command support.

## Directory overview

- `pc_lora_gui.py`
  - single-serial GUI; only connects to `PC_Lora`.
  - default buttons are limited to `HELLO / STATUS / READ_ACCEL / LED_ON / LED_OFF`.
  - this is the most direct tool for final link validation.
- `motor_test_gui.py`
  - dual-serial GUI.
  - `PC_Lora` is the only control entry.
  - `Rover_Lora` is only used for USB local monitoring and should not be used as a direct control path.
  - currently it also keeps only sensor and LED quick command buttons.
- `pc_lora/pc_lora.ino`
  - PC-side LoRa board.
  - forwards text commands from the PC to LoRa.
  - only prints actually received LoRa packets as `RX: ...`.
- `rover_lora/rover_lora.ino`
  - rover-side LoRa bridge board.
  - forwards received LoRa commands to `Rover_R3`.
  - only forwards `RESP:` / `DATA:` from `Rover_R3` back to LoRa.
  - USB serial is only for monitoring.
- `rover_r3/rover_r3.ino`
  - base R3 firmware.
  - supports LED, forward, backward, left, right, stop, status.
  - `READ_ACCEL` returns `RESP:ACCEL_OFFLINE`.
- `rover_r3_accel/rover_r3_accel.ino`
  - R3 firmware with MMA8451 support.
  - adds `READ_ACCEL` and IMU status.
- `WIRING_AND_SENSORS.md`
  - wiring and sensor descriptions.

## Verified response rules

To avoid false positives such as "GUI shows success even though the rover is not powered", the current version uses these rules:

- trusted replies:
  - `RX: RESP:...`
  - `RX: DATA:...`
- not counted as a real reply:
  - `TRACE:...`
  - `TX:...`
  - any local serial output without `RX:` prefix
  - contents from the `Rover_Lora` USB monitor port

This means:

- if `Rover_Lora` is not powered or the LoRa packet never completes the round trip, `pc_lora_gui.py` will not falsely report received data.
- GUI latency is only updated after a real remote reply arrives.
- timeouts are displayed as timeouts, not as fake success.

## Wiring

### 1. PC_Lora

- `PC USB -> PC_Lora USB`
- baud rate: `9600`
- frequency: code defaults to `868E6`

### 2. Rover_Lora and Rover_R3

- `Rover_R3 D2 (SoftwareSerial RX) <- Rover_Lora TX`
- `Rover_R3 D3 (SoftwareSerial TX) -> Rover_Lora RX`
- `Rover_R3 GND <-> Rover_Lora GND`

Notes:

- `Rover_R3` now uses `D2/D3` instead of `D0/D1` for communication with `Rover_Lora`.
- `D0/D1` are reserved for USB serial debugging, so you can open the Arduino Serial Monitor without conflicting with the LoRa bridge.
- If you still wire `Rover_Lora` to `D0/D1`, you may see lost bytes, garbage, `UNKNOWN=...`, and GUI timeouts.
- `Rover_Lora <-> Rover_R3` UART now uses `4800 baud`, which is more stable for UNO + SoftwareSerial.

### 3. Single L298N motor control

Current `Rover_R3` wiring assumes simplified single L298N control:

- `D8 -> IN1`
- `D9 -> IN2`
- `D10 -> IN3`
- `D11 -> IN4`
- `R3 GND -> L298N GND`

Notes:

- keep `ENA/ENB` jumpers installed or tied high.
- motor power should be supplied separately to the L298N.
- all grounds must be common.

### 4. MMA8451

If using `rover_r3_accel/rover_r3_accel.ino`:

- `5V -> VIN`
- `GND -> GND`
- `A4 -> SDA`
- `A5 -> SCL`

## Recommended firmware combinations

Two common setups:

1. Basic motion link test
   - flash `pc_lora/pc_lora.ino` to `PC_Lora`
   - flash `rover_lora/rover_lora.ino` to `Rover_Lora`
   - flash `rover_r3/rover_r3.ino` to `Rover_R3`
2. Accelerometer test
   - flash `pc_lora/pc_lora.ino` to `PC_Lora`
   - flash `rover_lora/rover_lora.ino` to `Rover_Lora`
   - flash `rover_r3_accel/rover_r3_accel.ino` to `Rover_R3`

## Recommended test sequence

1. Run `python pc_lora_gui.py` with only `PC_Lora` connected.
2. Send `HELLO`.
3. If there is no real reply, you should see a timeout rather than a false positive.
4. Once you get `RX: RESP:HELLO_OK`, test `STATUS`.
5. Then test `READ_ACCEL`.
6. Finally test `LED_ON` and `LED_OFF`.

If you want to view rover-side local logs at the same time, run `motor_test_gui.py` and connect to `Rover_Lora` USB monitor. Remember, that monitor is for observation only, not the control path.

If you want to view `Rover_R3` local debug logs, open the Arduino IDE Serial Monitor. The logs should show:

- `DEBUG:R3 accel bridge on SoftwareSerial D2/D3`
- `DEBUG:R3 bridge baud=4800`
- `DEBUG:CMD=STATUS`
- `RESP:...`
