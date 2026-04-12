# LoRa Debug Report

Review date: 2026-04-12

## 1. Purpose

This document records the confirmed LoRa communication issues, observed behavior, root causes, fixes, and pending verification items for the `GUI-11` project. It is intended to help with:

- classroom/project reporting
- ongoing debugging
- comparison with older code versions
- alignment with official Arduino MKR WAN 1310 guidance

## 2. Official baseline references

This review mainly references the following official materials:

- Arduino MKR WAN 1310 hardware documentation
  - `https://docs.arduino.cc/hardware/mkr-wan-1310/`
- LoRa-Based Messaging with MKR WAN 1310
  - official approach: use the `LoRa` library for board-to-board transmission, include address fields in each packet, and verify packet destination before processing
- LoRa Sensor Data with MKR WAN 1310
  - official approach: use `LoRa.parsePacket()` to poll for packets and print `RSSI`
- `arduino-LoRa` repository
  - `https://github.com/sandeepmistry/arduino-LoRa`
- `arduino-LoRa` API documentation
  - `https://github.com/sandeepmistry/arduino-LoRa/blob/master/API.md`
- `MKRWAN` official example `DumbModemLoraSender`
  - used to confirm that MKR WAN 1310 supports a direct `LoRa` library mode

## 3. Current project link

The target project link is:

`GUI -> PC USB -> PC_Lora -> LoRa -> Rover_Lora -> UART -> Rover_R3`

Key files involved:

- `pc_lora/pc_lora.ino`
- `rover_lora/rover_lora.ino`
- `rover_r3/rover_r3.ino`
- `rover_r3_accel/rover_r3_accel.ino`
- `pc_lora_gui.py`
- `motor_test_gui.py`
- `compact_protocol.py`

## 4. Confirmed issues

### 4.1 `GUI-11` is not compatible with the old archive protocol

Root cause:

- user-provided old code:
  - `LORA_sender.zip`
  - `LoRa_Receiver.zip`
- current project code:
  - `GUI-11`

Observed behavior:

- the old code sends free-form text such as `Hello from MATLAB` and `Remote: Hello!`
- the current `GUI-11` sends `HELLO / STATUS / READ_ACCEL / LED_ON` and encodes them as `0A / 0B / 0C / 0D` on the wire

Impact:

- mixing old and new code causes protocol mismatch, resulting in communication failure or packets being discarded as invalid payloads

Conclusion:

- this is a highly probable direct cause of the communication failure

Status:

- confirmed

### 4.2 The old link was not a complete request-response path

Root cause:

- the old `LoRa_Receiver.zip` was mostly a one-way `LoRa -> Serial1` forwarder
- it did not form the closed loop required by the current GUI: remote response back to LoRa

Observed behavior:

- the GUI sends a command and the board appears to work, but the GUI keeps waiting for a real remote reply
- it eventually times out

Impact:

- even if the wireless side receives the packet, the GUI fails unless the response is returned as `RESP:` / `DATA:` to `PC_Lora`

Conclusion:

- the old receiver code does not meet the current GUI acceptance criteria

Status:

- confirmed

### 4.3 The original project MKR WAN 1310 LoRa implementation deviated from official board-to-board baseline

Root cause:

- official Arduino board-to-board tutorials use the `LoRa` library
- the original project `pc_lora/rover_lora` used the `MKRWAN` pipe interface

Risk:

- less standard than official examples
- harder to debug and compare with known working code
- difficult to distinguish protocol, library, or RF issues

Resolution:

- `pc_lora/rover_lora` has been changed to use the `LoRa` library for polling and transmissions

Status:

- fixed

### 4.4 Frequency mismatch risk

Root cause:

- the old `LORA_sender.zip` used `915E6`
- current project history used `EU868`
- Arduino official notes:
  - Europe uses `868E6`
  - North America uses `915E6`

Observed behavior:

- mismatched frequencies cause the devices to be unable to receive each other at all

Resolution:

- both MKR WAN 1310 firmwares now use a shared constant `LORA_FREQUENCY_HZ`
- the current default is `868E6`

Note:

- if testing in North America, both sides must be changed to `915E6`

Status:

- centralized configuration
- still needs regional validation

### 4.5 Missing address header meant poor noise rejection

Root cause:

- the earlier implementation did not include an address header like the official message service examples

Observed behavior:

- the system could receive packets from other nearby LoRa networks
- packets not addressed to the current device could still enter parsing logic

Impact:

- increased false positives
- confusing debug logs
- packets might appear to be received even when they were not intended for this link

Resolution:

- a 2-byte packet header was added:
  - `recipient`
  - `sender`
- the receiver checks `recipient` before accepting a packet
- non-matching packets are discarded with `TRACE:` logs

Status:

- fixed

### 4.6 Address filtering alone is not enough

Root cause:

- LoRa can still receive packets on the same frequency/parameters from other nearby devices

Observed behavior:

- packets are still received at the RF layer, but later discarded if not addressed to this device

Resolution:

- both sides now use a private `sync word`
  - current value: `0x34`

Effect:

- RF layer filters out many unrelated packets first
- address filtering provides a second layer of protection

Status:

- fixed

### 4.7 Rover_Lora -> Rover_R3 UART wiring and baud rate changed

Root cause:

- current `Rover_R3` uses:
  - `D2/D3`
  - `SoftwareSerial`
  - `4800 baud`
- the older approach looked more like `D0/D1` or `9600 baud`

Observed behavior:

- if still wired as before or using the wrong baud rate, common failures include:
  - garbage characters
  - lost bytes
  - `UNKNOWN=...`
  - GUI timeouts

Conclusion:

- this is a hardware/serial-layer issue that can directly cause communication failure

Status:

- confirmed
- requires real hardware testing with the new wiring

### 4.8 The GUI now only accepts verified remote replies

Root cause:

- current GUI design treats only the following formats as real remote replies:
  - `RX: RESP:...`
  - `RX: DATA:...`
  - `RX: <compact frame>`

Observed behavior:

- if local serial output prints `RESP:` without the `RX:` prefix, the GUI ignores it

Impact:

- this is intentional to avoid false positives when the full LoRa round-trip has not completed

Status:

- by design
- confirmed

### 4.9 `compact_protocol.py` decoding for `9D` was incomplete

Root cause:

- `9D` was mapped to `MMA8451_OFFLINE`
- the GUI expects `RESP:MMA8451_OFFLINE`

Impact:

- inconsistent GUI status display for that condition

Resolution:

- fixed to use `RESP:MMA8451_OFFLINE`

Status:

- fixed

### 4.10 Official `arduino-LoRa` requires specific Murata firmware

Root cause:

- `arduino-LoRa` README states:
  - MKR WAN 1300/1310 requires Murata module firmware `v1.1.6+`

Impact:

- older Murata firmware may cause direct `LoRa` mode to fail or behave unexpectedly

Resolution:

- current code logs `TRACE:MURATA_FW_REQ:1.1.6_PLUS` at startup

Status:

- risk documented
- not yet verified on actual hardware

### 4.11 Local environment cannot perform compile-level validation

Root cause:

- the current working environment does not have:
  - `arduino-cli`
  - `git`

Impact:

- this review is limited to static source analysis and code changes
- unable to complete:
  - compilation verification
  - board upload
  - `git diff` / commit history validation

Status:

- recorded

## 5. Completed code fixes

### 5.1 `pc_lora/pc_lora.ino`

Completed:

- changed from `MKRWAN` to `LoRa` library
- added frequency constant `LORA_FREQUENCY_HZ`
- added private `sync word`
- added local and remote addresses
- included `recipient`, `sender`, and `payload` in transmitted packets
- on receive, check address header and verify destination
- added `RSSI` and address-related `TRACE:` logs

### 5.2 `rover_lora/rover_lora.ino`

Completed:

- changed from `MKRWAN` to `LoRa` library
- added frequency constant `LORA_FREQUENCY_HZ`
- added private `sync word`
- added local and remote addresses
- on receive, check `recipient`
- when waiting for `R3` reply, drop new LoRa commands and log the event
- include address header in replies back to `PC_Lora`
- added `RSSI` and address-related `TRACE:` logs

### 5.3 `compact_protocol.py`

Completed:

- fixed `9D` decoding to `RESP:MMA8451_OFFLINE`

## 6. Current recommended parameters

Current default parameters:

- LoRa frequency: `868E6`
- LoRa sync word: `0x34`
- `PC_Lora` address: `0xBB`
- `Rover_Lora` address: `0xCC`
- `Rover_Lora <-> Rover_R3` UART: `4800 baud`
- `Rover_R3` bridge pins: `D2/D3`

If testing in North America, set both sides to:

- `LORA_FREQUENCY_HZ = 915E6`

## 7. Recommended retest sequence

### 7.1 Verify the two MKR WAN 1310 wireless boards

Check `PC_Lora` startup logs for:

- `TRACE:LORA_INIT_OK`
- `TRACE:LIB:ARDUINO_LORA`
- `TRACE:LORA_FREQUENCY_HZ:...`
- `TRACE:LORA_SYNC_WORD:0x34`
- `TRACE:LOCAL_ADDRESS:...`

Check `Rover_Lora` startup logs for:

- `TRACE:LORA_INIT_OK`
- `TRACE:LIB:ARDUINO_LORA`
- `TRACE:LORA_FREQUENCY_HZ:...`
- `TRACE:LORA_SYNC_WORD:0x34`
- `TRACE:LOCAL_ADDRESS:...`

### 7.2 Verify address filtering

After sending `HELLO`, you should see:

- `PC_Lora`:
  - `TRACE:LOCAL_TX:TO=0xCC,FROM=0xBB,...`
- `Rover_Lora`:
  - `TRACE:LORA_RX_META:TO=0xCC,FROM=0xBB,RSSI=...`
  - `TRACE:LORA_RX:0A` or `TRACE:LORA_RX:HELLO`

### 7.3 Verify the `Rover_R3` UART bridge

After sending `HELLO`, `Rover_Lora` should also show:

- `TRACE:UART_TX:...`
- `TRACE:R3_RX:8A` or `TRACE:R3_RX:RESP:HELLO_OK`

### 7.4 Verify the GUI

The GUI should only count success when it receives:

- `RX: RESP:...`
- `RX: DATA:...`
- `RX: 8A`
- `RX: 8B|...`
- `RX: 8C|...`

If the GUI times out, isolate the failure:

- if `PC_Lora` has no `LORA_RX_META`, check frequency, antenna, sync word, addresses, and firmware consistency
- if `Rover_Lora` has `LORA_RX_META` but no `R3_RX`, check the UART bridge wiring and baud rate

## 8. Latest conclusions

- `pc_lora_gui.py` now includes latency testing and `Export CSV` for system-level performance validation.
- The most reliable validation path is: connect only `PC_Lora`, and use the GUI to send `HELLO / STATUS / READ_ACCEL / LED_ON / LED_OFF`.
- `Rover_R3` and `Rover_Lora` UART must use `D2/D3` at `4800 baud`.
- the UNO R3 built-in `3.3V` output is not recommended to power the LoRa module directly; use an external regulated supply if possible.
- the GUI now clearly defines that only `RX: RESP:...` and `RX: DATA:...` are real remote replies.

## 9. Follow-up recommendations

- use `pc_lora_gui.py` `interval` mode for high-load send testing and watch for packet loss or latency increase.
- for long-term stability, fix the LoRa module power supply first; if instability continues, switch to an independent `3.3V` module and retest.
- if testing in North America, remember to set both ends to `915E6`.
- verify the command mapping in `compact_protocol.py` so that `READ_ACCEL`, `LED_ON`, and `LED_OFF` short codes match the `Rover_R3` firmware.
- if `R3_RX` responds but `PC_Lora` does not show `RX:`, check whether the reply is actually transmitted back over LoRa.

## 10. Pending verification items

- whether all physical boards have been updated to the patched firmware
- whether both MKR WAN 1310 units are configured for the same regional frequency
- whether the Murata firmware is `1.1.6+`
- whether address filtering and sync word are sufficient to reduce environmental noise in real use
- whether `rover_r3_accel` can reliably return `8C|x,y,z` when the real accelerometer is connected

## 11. Conclusion

So far, the LoRa failure is most likely not a single bug but a combination of version and link conditions:

- protocol incompatibility between old and new code
- mismatch between the official board-to-board baseline and the project’s original implementation
- potential frequency mismatch
- changed rover UART wiring/baud rate
- missing address filtering in the older design
- GUI now only accepts true remote replies

The completed fixes are focused on bringing the two MKR WAN 1310 boards closer to the official implementation:

- direct `LoRa` library usage
- `parsePacket()` receive polling
- address header filtering
- `RSSI` debug output
- private `sync word`

These changes should significantly improve noise rejection and make link failure points easier to diagnose, but real hardware tests are still needed to confirm end-to-end stability.
