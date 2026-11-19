# LoRa Debug & Fix

GUI-11 是一个独立的 Python/Tkinter 实车诊断工具，用来排查 Mars Rover 的 LoRa 和 UART 通信故障。它检查的是完整的请求和回复路径。命令由 PC 发出，经两块 LoRa 板和车端 UART 到达 Uno R3，回复再返回 PC。[English guide](README_EN.md)

[Rover Control Station（D15）](../rover-control-station/) 是另一个独立的主操作界面原型。两个程序有各自的启动入口和依赖。

## 怎么定位故障

1. 在 `lora-test/` 运行 `pc_lora_gui.py`，连接 PC 端 LoRa 板。先发 `HELLO` 或 `STATUS`，核对 Uno 能否收到命令并经完整链路返回有效回复。
2. 再用 `READ_ACCEL` 检查传感器读回，用 `LED_ON` 和 `LED_OFF` 检查实车指令执行。默认测试集中在通信链路，便于排除运动相关因素。
3. GUI 只把 PC 端日志中的 `RX: RESP:...` 和 `RX: DATA:...` 计作有效回复并记录延迟。车端 USB 保留 `TRACE:` 日志供排查，USB 直通命令旁路已关闭，因此本地回显不会被计作无线通信成功。
4. 如果超时，可以对照车端记录定位环节。`LORA_RX` 表示车端 LoRa 已接收请求，`UART_TX` 表示请求已转发给 Uno，`R3_RX` 表示车端桥接板收到了 Uno 的一行数据，`R3_TIMEOUT` 表示在时限内未收到它认可的回复。

## 最终集成时采用的修复

单独验证无线链路后，排查范围收窄到车端 UART。实际修复是将车端 UART 改到 Uno R3 的 D2/D3，用 SoftwareSerial 以 4,800 baud 通信，将 D0/D1 留给 USB 调试。这个改动在最终集成时约 10 分钟恢复了远程指令执行。电机负载下的共享电池供电路径是一个可能诱因。

## 启动诊断工具

在 `lora-test/` 中运行：

```sh
python -m pip install -r requirements.txt
python pc_lora_gui.py
```

工具可以记录超时，并把命令往返延迟测试导出为 CSV。[接线说明](WIRING_AND_SENSORS.md) · [完整排障报告](LORA_DEBUG_REPORT.md) · [台架测试数据](latency_data/)

## 紧凑命令协议

这版 `11` 现在已经加入固定短码协议，思路和 `Final1` 的固定 opcode 一样，但这里用更直观的两位十六进制文本码，方便串口联调。

请求码：

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

响应码：

- `8A` = `HELLO_OK`
- `8B|...` = `STATUS`，后面跟状态载荷
- `8C|...` = `ACCEL`，后面跟三轴数据
- `8D` = `LED=ON`
- `8E` = `LED=OFF`
- `9C` = `ACCEL_OFFLINE`
- `9D` = `MMA8451_OFFLINE`
- `9E` = `ACCEL_OK`
- `9F|...` = 错误或未知命令
- `A0` = `R3_BOOT_OK`

当前 GUI 按钮仍显示人类可读命令，但在线路上传输的会是短码，例如：

- GUI `HELLO` -> 线上发 `0A`
- GUI `STATUS` -> 线上发 `0B`
- R3 返回 `8A`，GUI 会自动显示为 `RESP:HELLO_OK`

兼容性说明：

- 你仍然可以在 GUI 自定义输入框里输入 `HELLO`
- 也可以直接输入 `0A`
- `PC_Lora` 和 `Rover_R3` 当前都会同时兼容文本命令与短码命令

## 本次修复的关键点

- `pc_lora_gui.py` 现在只把 `PC_Lora` 串口收到的 `RX: RESP:...` 或 `RX: DATA:...` 认定为真实远端回复。
- `motor_test_gui.py` 现在也只信任 `PC_Lora` 返回的真实远端数据。
- `rover_lora/rover_lora.ino` 已禁用 `USB -> Serial1 -> R3` 的直通旁路。
- `Rover_Lora` 连接到电脑 USB 后仍然会被供电，但它现在只输出本地 `TRACE:` 监看信息，不会再因为本地 USB 连接而伪造一条“LoRa 测试成功”。
- `rover_r3_accel/rover_r3_accel.ino` 修复了原来的编译问题，并补齐了电机/LED/状态命令。

## 目录说明

- `pc_lora_gui.py`
  - 单串口 GUI，只连接 `PC_Lora`。
  - 当前默认按钮只保留 `HELLO / STATUS / READ_ACCEL / LED_ON / LED_OFF`。
  - 用它做最终链路验证最直接。
- `motor_test_gui.py`
  - 双串口 GUI。
  - `PC_Lora` 是唯一控制入口。
  - `Rover_Lora` 只用于 USB 本地监看，不允许直接下发命令。
  - 当前也只保留传感器与 LED 相关快捷按钮。
- `pc_lora/pc_lora.ino`
  - PC 侧 LoRa 板。
  - 把 PC 发来的文本命令通过 LoRa 发出去。
  - 只把真正收到的 LoRa 回包打印成 `RX: ...`。
- `rover_lora/rover_lora.ino`
  - 车端 LoRa 桥接板。
  - 接收 LoRa 命令后转发给 `Rover_R3`。
  - 只把 `Rover_R3` 返回的 `RESP:` / `DATA:` 再发回 LoRa。
  - USB 串口只做监看。
- `rover_r3/rover_r3.ino`
  - 基础版 R3 固件。
  - 支持 LED、前进、后退、左转、右转、停止、状态。
  - `READ_ACCEL` 会返回 `RESP:ACCEL_OFFLINE`。
- `rover_r3_accel/rover_r3_accel.ino`
  - 带 MMA8451 的 R3 固件。
  - 在基础版上增加 `READ_ACCEL` 与 IMU 状态。
- `WIRING_AND_SENSORS.md`
  - 接线和传感器说明。

## 真实回复的判定规则

为了避免“没给车端 LoRa 供电，GUI 却显示已收到”的假象，当前版本采用下面规则：

- 可信回复：
  - `RX: RESP:...`
  - `RX: DATA:...`
- 不计为真实回复：
  - `TRACE:...`
  - `TX:...`
  - 任何没有 `RX:` 前缀的本地串口输出
  - `Rover_Lora` USB 监看口里的内容

这意味着：

- 如果 `Rover_Lora` 没上电，或者没有真正通过 LoRa 回包，`pc_lora_gui.py` 不会再虚报 `received`。
- GUI 的延迟只会在收到真实远端回复后才更新。
- 超时后会显示 timeout，而不是假装成功。

## 接线

### 1. PC_Lora

- `PC USB -> PC_Lora USB`
- 波特率：`9600`
- 频率：代码默认 `868E6`

### 2. Rover_Lora 与 Rover_R3

- `Rover_R3 D2 (SoftwareSerial RX) <- Rover_Lora TX`
- `Rover_R3 D3 (SoftwareSerial TX) -> Rover_Lora RX`
- `Rover_R3 GND <-> Rover_Lora GND`

说明：

- `Rover_R3` 现在不再用 `D0/D1` 和 `Rover_Lora` 通信。
- `D0/D1` 留给 USB 串口调试，所以你可以开 Arduino Serial Monitor 看日志，不会再和 LoRa 桥冲突。
- 如果你还按旧接法把 `Rover_Lora` 连在 `D0/D1`，就会出现你截图那种丢字节、乱码、`UNKNOWN=...`、GUI 超时的问题。
- `Rover_Lora <-> Rover_R3` 这一段 UART 现在使用 `4800 baud`，这是为了让 `UNO + SoftwareSerial` 更稳定。

### 3. 单 L298N 电机控制

当前 `Rover_R3` 两个固件都按单 `L298N` 简化接线工作：

- `D8 -> IN1`
- `D9 -> IN2`
- `D10 -> IN3`
- `D11 -> IN4`
- `R3 GND -> L298N GND`

左右三轮直接桥接成左右两侧：

- `OUT1/OUT2` 负责左侧前中后轮
- `OUT3/OUT4` 负责右侧前中后轮

说明：

- `ENA/ENB` 建议保留跳帽或固定高电平。
- 电机主电源单独供给 `L298N`。
- 所有地必须共地。

### 4. MMA8451

如果使用 `rover_r3_accel/rover_r3_accel.ino`：

- `5V -> VIN`
- `GND -> GND`
- `A4 -> SDA`
- `A5 -> SCL`

## 推荐烧录组合

有两种常用组合：

1. 基础运动链路测试
   - `PC_Lora` 烧录 `pc_lora/pc_lora.ino`
   - `Rover_Lora` 烧录 `rover_lora/rover_lora.ino`
   - `Rover_R3` 烧录 `rover_r3/rover_r3.ino`
2. 带加速度计测试
   - `PC_Lora` 烧录 `pc_lora/pc_lora.ino`
   - `Rover_Lora` 烧录 `rover_lora/rover_lora.ino`
   - `Rover_R3` 烧录 `rover_r3_accel/rover_r3_accel.ino`

## 推荐测试顺序

1. 先只连接 `PC_Lora`，运行 `python pc_lora_gui.py`
2. 发送 `HELLO`
3. 如果没有真实回包，应看到 timeout，而不是 fake receive
4. 给 `Rover_Lora` 和 `Rover_R3` 上电后，再次发送 `HELLO`
5. 收到 `RX: RESP:HELLO_OK` 后，再测 `STATUS`
6. 再测 `READ_ACCEL`
7. 最后测 `LED_ON / LED_OFF`

如果你想同时看车端本地日志，可以再运行 `motor_test_gui.py` 并连接 `Rover_Lora` 的 USB 监看口；但请记住，它只是监看，不是控制路径。

如果你想看 `Rover_R3` 的本地调试日志，也可以同时打开 Arduino IDE 的 Serial Monitor。现在日志会显示：

- `DEBUG:R3 accel bridge on SoftwareSerial D2/D3`
- `DEBUG:R3 bridge baud=4800`
- `DEBUG:CMD=STATUS`
- `RESP:...`

## 当前状态与推荐流程

1. 运行 `python pc_lora_gui.py`，只连接 `PC_Lora`。
2. 从串口列表选择 `PC_Lora` COM 端口，波特率保持 `9600`。
3. 首先测试 `HELLO`，确认真实远端回包 `RX: RESP:HELLO_OK`。
4. 继续测试 `STATUS`、`READ_ACCEL`、`LED_ON`、`LED_OFF`。
5. 如果没有真正上电 `Rover_Lora`/`Rover_R3`，GUI 应显示超时而不是假接收。

## 延迟测试与 CSV 导出

- `pc_lora_gui.py` 已集成延迟测试功能。
- 测试模式有：
  - `sequential`：等候每条指令回复后再发送下一条。
  - `interval`：按固定时间间隔发送，用于高压力发送测试。
- 测试完成后，可点击 `Export CSV` 将每次尝试和延迟结果保存为 `.csv`。
- 这可以用于对比不同命令、间隔和重试次数下的表现。

## 重要硬件提醒

- `UNO R3` 的 `3.3V` 引脚通常不能稳定为 LoRa 模块供电，建议使用独立的 `3.3V` 稳压模块或专用电源。
- `Rover_R3` 与 `Rover_Lora` 的 UART 通信必须使用 `D2`/`D3`，波特率为 `4800`。请不要把 `Rover_Lora` 直连到 `D0`/`D1`，那是 USB 串口调试口，会造成串口冲突和丢包。
- `Rover_Lora` 的 USB 仅用于监看 `TRACE:` 日志，不应作为 LoRa 控制路径。
- `PC_Lora` 的 USB 供电应稳定，GUI 的主链路是 `PC -> PC_Lora -> LoRa -> Rover_Lora`。

## 关键判断规则

- 只有 `RX: RESP:...` 和 `RX: DATA:...` 才被视作真实远端回复。
- `TRACE:`、`TX:` 和未带 `RX:` 前缀的本地串口输出都不计为成功。
- 这保证 GUI 不会因为本地串口日志而误报“已收到”。
