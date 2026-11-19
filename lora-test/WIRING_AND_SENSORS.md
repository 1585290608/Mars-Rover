# GUI/11 Wiring and Sensors

这份文档与 `README.md` 保持一致，默认验证的真实链路是：

`PC USB -> PC_Lora -> LoRa -> Rover_Lora -> UART -> Rover_R3`

当前链路上的命令已经支持紧凑短码，例如：

- `0A` = `HELLO`
- `0B` = `STATUS`
- `0C` = `READ_ACCEL`
- `0D` = `LED_ON`
- `0E` = `LED_OFF`

对应返回示例：

- `8A`
- `8B|LED=OFF,IMU=ON,MOTION=STOP`
- `8C|0.012,-0.034,9.801`

## 1. 链路职责

- `PC_Lora`
  - 接收 PC GUI 的串口文本命令
  - 通过 LoRa 发给车端
- `Rover_Lora`
  - 接收 LoRa 包
  - 转发给 `Rover_R3`
  - 把 `Rover_R3` 返回的 `RESP:` / `DATA:` 再发回 LoRa
  - USB 口仅用于本地监看
- `Rover_R3`
  - 执行 LED、运动、状态、加速度计命令

## 2. PC_Lora 接线

- `PC USB -> PC_Lora USB`
- 串口波特率：`9600`
- LoRa 频率：`868E6`

## 3. Rover_Lora 与 Rover_R3 串口接线

使用 `SoftwareSerial`：

- `Rover_R3 D2 (RX) <- Rover_Lora TX`
- `Rover_R3 D3 (TX) -> Rover_Lora RX`
- `Rover_R3 GND <-> Rover_Lora GND`

说明：

- 这套接法不再占用 R3 的 USB 调试串口。
- `D0/D1` 可以继续给 Arduino IDE Serial Monitor 使用。
- 如果你还按旧接法把 `Rover_Lora` 接在 `D0/D1`，会出现串口冲突、乱码、丢字节和假超时。
- `Rover_Lora <-> Rover_R3` 这一段串口现在固定 `4800 baud`，专门为了提高 `UNO SoftwareSerial` 的稳定性。

## 4. 单 L298N 电机接线

当前 `11/rover_r3.ino` 和 `11/rover_r3_accel.ino` 都按单 `L298N` 模式工作：

- `D8 -> IN1`
- `D9 -> IN2`
- `D10 -> IN3`
- `D11 -> IN4`
- `R3 GND -> L298N GND`

左右轮组桥接方式：

- `OUT1/OUT2` 负责左侧前、中、后轮
- `OUT3/OUT4` 负责右侧前、中、后轮

电源说明：

- `ENA/ENB` 建议保留跳帽或固定高电平
- 电机主电源单独接 `L298N`
- `R3 GND`、`Rover_Lora GND`、`L298N GND`、电机电源负极必须共地

## 5. MMA8451 接线

如果使用 `rover_r3_accel/rover_r3_accel.ino`：

- `5V -> VIN`
- `GND -> GND`
- `A4 -> SDA`
- `A5 -> SCL`

没有接传感器时，R3 会返回：

- `RESP:MMA8451_OFFLINE`
- `RESP:ACCEL_OFFLINE`

## 6. LED

- 使用板载 `D13` LED
- 或外接 LED 到 `D13`，串联限流电阻后接地

## 7. GUI 中哪些算真实回复

只认下面两种：

- `RX: RESP:...`
- `RX: DATA:...`

下面这些都只是本地日志或监看信息，不代表链路真的走通：

- `TRACE:...`
- `TX:...`
- `Rover_Lora` USB 监看口输出
- 没有 `RX:` 前缀的裸 `RESP:` / `DATA:`

## 8. 推荐测试顺序

1. 先烧录 `pc_lora/pc_lora.ino`
2. 再烧录 `rover_lora/rover_lora.ino`
3. R3 选择烧录 `rover_r3/rover_r3.ino` 或 `rover_r3_accel/rover_r3_accel.ino`
4. 打开 `pc_lora_gui.py`
5. 只连接 `PC_Lora`，发送 `HELLO`
6. 如果车端没上电，应看到 timeout，而不是 fake receive
7. 给 `Rover_Lora` 和 `Rover_R3` 上电后，再发 `HELLO`
8. 收到 `RX: RESP:HELLO_OK` 后，再继续测 `STATUS`、`FORWARD`、`STOP`

## 9. 双串口监看模式

`motor_test_gui.py` 可以同时连接：

- `PC_Lora` 控制口
- `Rover_Lora` USB 监看口

但要注意：

- 只有 `PC_Lora` 能发命令
- `Rover_Lora` USB 口不能再直接下发命令
- `Rover_Lora` 监看口输出只用于排错，不作为链路成功判据
