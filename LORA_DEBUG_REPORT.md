# LoRa Debug Report

审阅日期：2026-04-12

## 1. 报告目的

本文件用于记录 `GUI-11` 项目目前为止已经确认的 LoRa 通信问题、现象、根因、修正措施与待验证项，方便后续：

- 课堂/项目汇报
- 继续调试
- 与旧版本代码对照
- 与官方 Arduino MKR WAN 1310 教程对齐

## 2. 参考的官方基线

本次审阅主要参考以下官方资料：

- Arduino MKR WAN 1310 Hardware 页面
  - `https://docs.arduino.cc/hardware/mkr-wan-1310/`
- LoRa-Based Messaging with MKR WAN 1310
  - 官方思路：使用 `LoRa` 库做板对板收发，包内增加地址字段，收包先检查地址，再处理消息
- LoRa Sensor Data with MKR WAN 1310
  - 官方思路：使用 `LoRa.parsePacket()` 轮询收包，并打印 `RSSI`
- `arduino-LoRa` 官方仓库
  - `https://github.com/sandeepmistry/arduino-LoRa`
- `arduino-LoRa` API 文档
  - `https://github.com/sandeepmistry/arduino-LoRa/blob/master/API.md`
- `MKRWAN` 官方示例中的 `DumbModemLoraSender`
  - 用于确认 MKR WAN 1310 官方也支持切换到 `LoRa` 库直连模式

## 3. 当前项目链路

当前项目目标链路是：

`GUI -> PC USB -> PC_Lora -> LoRa -> Rover_Lora -> UART -> Rover_R3`

当前代码中涉及的核心文件：

- `pc_lora/pc_lora.ino`
- `rover_lora/rover_lora.ino`
- `rover_r3/rover_r3.ino`
- `rover_r3_accel/rover_r3_accel.ino`
- `pc_lora_gui.py`
- `motor_test_gui.py`
- `compact_protocol.py`

## 4. 已确认问题

### 4.1 `GUI-11` 与旧压缩包代码不是同一套协议

问题来源：

- 用户提供旧代码：
  - `LORA_sender.zip`
  - `LoRa_Receiver.zip`
- 当前项目代码：
  - `GUI-11`

现象：

- 旧代码发送的是 `"Hello from MATLAB"`、`"Remote: Hello!"`、随机数等自由文本
- 当前 `GUI-11` 发送的是 `HELLO / STATUS / READ_ACCEL / LED_ON`，并在链路上编码成 `0A / 0B / 0C / 0D` 这类短码

影响：

- 新旧代码混用时，双方对消息格式理解不同，通信会直接失败，或者接收到后被当作无效载荷丢弃

结论：

- 这是导致通信失败的高概率直接原因

状态：

- 已确认

### 4.2 旧版链路不是完整“请求-回包”链路，GUI 会超时

问题来源：

- 旧 `LoRa_Receiver.zip` 基本是单向 `LoRa -> Serial1` 转发
- 它没有形成当前 GUI 所要求的“远端响应再回 LoRa”的闭环

现象：

- GUI 发送命令后，看起来板子在工作，但 GUI 一直等待真正的远端回包
- 最终表现为 timeout

影响：

- 即使无线侧收到了包，只要没有把 `RESP:` / `DATA:` 正确送回 `PC_Lora`，GUI 就会判定失败

结论：

- 旧版接收代码不满足当前 GUI 的验收标准

状态：

- 已确认

### 4.3 当前项目原来的 MKR WAN 1310 LoRa 实现偏离官方板对板基线

问题来源：

- Arduino 官方板对板教程使用 `LoRa` 库
- 项目原先的 `pc_lora/rover_lora` 使用 `MKRWAN` 的直包接口

风险：

- 与官方教程相比，不够标准
- 调试时很难直接对照官方示例
- 当出现问题时，不容易区分是协议问题、库问题还是射频问题

处理结果：

- 已将 `pc_lora/rover_lora` 改为使用 `LoRa` 库轮询收发

状态：

- 已修正

### 4.4 LoRa 频段存在明确失配风险

问题来源：

- 旧 `LORA_sender.zip` 使用 `915E6`
- 当前项目历史代码中使用的是 `EU868`
- Arduino 官方教程明确要求：
  - 欧洲使用 `868E6`
  - 北美使用 `915E6`

现象：

- 频段不一致时，设备之间会完全收不到包

处理结果：

- 两个 MKR WAN 1310 固件都统一改成常量配置：
  - `LORA_FREQUENCY_HZ`
- 当前默认值为：
  - `868E6`

注意：

- 如果实际测试地点在北美，必须将两端同时改成 `915E6`

状态：

- 已集中配置
- 仍需根据实际测试地区确认

### 4.5 无地址头时，无法有效区分环境噪音

问题来源：

- 早期实现没有像官方消息服务示例那样在包前加地址字段

现象：

- 可能收到周围其他 LoRa 网络的数据
- 收到的包即使不是发给本设备，也可能进入后续解析逻辑

影响：

- 增加误判概率
- 调试时日志混乱
- 可能出现“看起来收到了，但不是自己的包”

处理结果：

- 已按官方思路增加 2 字节包头：
  - `recipient`
  - `sender`
- 收包端先判断 `recipient`
- 不是发给自己的包，直接丢弃并输出 `TRACE:`

状态：

- 已修正

### 4.6 仅靠地址过滤还不够，射频层仍可能收到外部网络包

问题来源：

- LoRa 默认仍可能接收到同频段、同参数附近的其他设备数据

现象：

- 即使上层有地址头，还是会先“收到包”，只是之后再丢弃

处理结果：

- 两端已增加私有 `sync word`
  - 当前设为 `0x34`

作用：

- 射频层先过滤掉不属于本私有网络的大量包
- 地址头再做第二层过滤

状态：

- 已修正

### 4.7 `Rover_Lora -> Rover_R3` 的 UART 接线与波特率与旧版本不同

问题来源：

- 当前 `Rover_R3` 使用：
  - `D2/D3`
  - `SoftwareSerial`
  - `4800 baud`
- 旧思路更像把桥接放在 `D0/D1` 或 `9600 baud`

现象：

- 如果仍按旧接线或旧波特率连接，容易出现：
  - 乱码
  - 丢字节
  - `UNKNOWN=...`
  - GUI timeout

结论：

- 这属于足以直接导致通信失败的硬件/串口层问题

状态：

- 已确认
- 需要实机严格按新接线测试

### 4.8 GUI 只认“真实远端回包”，不会再接受本地串口假阳性

问题来源：

- 当前 GUI 设计上只把以下格式当作真实远端回包：
  - `RX: RESP:...`
  - `RX: DATA:...`
  - `RX: <compact frame>`

现象：

- 如果只是本地串口打印了 `RESP:`，但前面没有 `RX:`，GUI 会忽略

影响：

- 这不是 bug，而是为了避免“没走完整 LoRa 链路却显示成功”的假阳性

状态：

- 设计如此
- 已确认

### 4.9 `compact_protocol.py` 对 `9D` 的解码不完整

问题来源：

- 原先 `9D` 被映射为：
  - `MMA8451_OFFLINE`
- 而 GUI 的状态处理更稳定的路径是：
  - `RESP:MMA8451_OFFLINE`

影响：

- 可能导致某些 GUI 状态显示不一致

处理结果：

- 已修正为：
  - `RESP:MMA8451_OFFLINE`

状态：

- 已修正

### 4.10 官方 `arduino-LoRa` 对 MKR WAN 1300/1310 有固件前提

问题来源：

- `arduino-LoRa` 官方 README 明确说明：
  - MKR WAN 1300/1310 需要 Murata 模块固件 `v1.1.6+`

影响：

- 如果板载 Murata 固件版本过旧，可能导致 LoRa 直连模式异常或不可用

处理结果：

- 当前代码在启动日志中增加：
  - `TRACE:MURATA_FW_REQ:1.1.6_PLUS`

状态：

- 风险已记录
- 尚未在实机上验证固件版本

### 4.11 本地环境无法做编译级验证

问题来源：

- 当前工作环境中未找到：
  - `arduino-cli`
  - `git`

影响：

- 本次只能进行静态审阅和源码修改
- 无法在当前环境直接完成：
  - 编译验证
  - 板卡上传
  - `git diff`/提交记录核对

状态：

- 已记录

## 5. 已完成的代码修正

### 5.1 `pc_lora/pc_lora.ino`

已完成：

- 从 `MKRWAN` 改为 `LoRa` 库
- 增加频段常量 `LORA_FREQUENCY_HZ`
- 增加私有 `sync word`
- 增加本机地址与远端地址
- 发包时写入：
  - `recipient`
  - `sender`
  - `payload`
- 收包时先读取地址头，再检查：
  - 目标地址是否匹配
- 增加 `RSSI` 和地址相关 `TRACE:` 日志

### 5.2 `rover_lora/rover_lora.ino`

已完成：

- 从 `MKRWAN` 改为 `LoRa` 库
- 增加频段常量 `LORA_FREQUENCY_HZ`
- 增加私有 `sync word`
- 增加本机地址与远端地址
- 收包时先判 `recipient`
- 忙于等待 `R3` 回复时，丢弃新的 LoRa 指令并打日志
- 回包时同样带地址头发回 `PC_Lora`
- 增加 `RSSI` 和地址相关 `TRACE:` 日志

### 5.3 `compact_protocol.py`

已完成：

- `9D` 解码改为：
  - `RESP:MMA8451_OFFLINE`

## 6. 当前推荐参数

当前代码默认参数如下：

- LoRa 频段：`868E6`
- LoRa Sync Word：`0x34`
- `PC_Lora` 地址：`0xBB`
- `Rover_Lora` 地址：`0xCC`
- `Rover_Lora <-> Rover_R3` UART：`4800 baud`
- `Rover_R3` 串口桥引脚：`D2/D3`

如果在北美测试，推荐同时将两端改成：

- `LORA_FREQUENCY_HZ = 915E6`

## 7. 推荐复测顺序

### 7.1 先验证两块 MKR WAN 1310 的无线链路

检查 `PC_Lora` 启动日志是否有：

- `TRACE:LORA_INIT_OK`
- `TRACE:LIB:ARDUINO_LORA`
- `TRACE:LORA_FREQUENCY_HZ:...`
- `TRACE:LORA_SYNC_WORD:0x34`
- `TRACE:LOCAL_ADDRESS:...`

检查 `Rover_Lora` 启动日志是否有：

- `TRACE:LORA_INIT_OK`
- `TRACE:LIB:ARDUINO_LORA`
- `TRACE:LORA_FREQUENCY_HZ:...`
- `TRACE:LORA_SYNC_WORD:0x34`
- `TRACE:LOCAL_ADDRESS:...`

### 7.2 再验证地址过滤是否工作

发送 `HELLO` 后，应看到：

- `PC_Lora`：
  - `TRACE:LOCAL_TX:TO=0xCC,FROM=0xBB,...`
- `Rover_Lora`：
  - `TRACE:LORA_RX_META:TO=0xCC,FROM=0xBB,RSSI=...`
  - `TRACE:LORA_RX:0A` 或 `TRACE:LORA_RX:HELLO`

### 7.3 再验证 `Rover_R3` 串口桥

发送 `HELLO` 后，`Rover_Lora` 应继续看到：

- `TRACE:UART_TX:...`
- `TRACE:R3_RX:8A` 或 `TRACE:R3_RX:RESP:HELLO_OK`

### 7.4 最后验证 GUI

GUI 应只在收到以下格式时判成功：

- `RX: RESP:...`
- `RX: DATA:...`
- `RX: 8A`
- `RX: 8B|...`
- `RX: 8C|...`

如果 GUI timeout，需要按链路分段判断：

- `PC_Lora` 没有 `LORA_RX_META`
  - 先查频段、天线、Sync Word、地址、两端固件是否一致
- `Rover_Lora` 有 `LORA_RX_META` 但没有 `R3_RX`

## 8. 当前最新结论

- `pc_lora_gui.py` 已集成延迟测试与 `Export CSV`，可用于系统级性能验证。
- 当前最可靠的链路验证方式是：只连 `PC_Lora`，用 GUI 发送 `HELLO` / `STATUS` / `READ_ACCEL` / `LED_ON` / `LED_OFF`。
- `Rover_R3` 与 `Rover_Lora` 的 UART 必须走 `D2/D3`，并使用 `4800 baud`。
- `UNO R3` 自带 `3.3V` 输出不宜直接驱动 LoRa 模块，建议外部稳压电源。
- GUI 的判定规则已明确：仅 `RX: RESP:...` 和 `RX: DATA:...` 视作真实远端回复。

## 9. 后续建议

- 使用 `pc_lora_gui.py` 的 `interval` 模式进行高压力发送测试，观察是否会出现丢包或延迟增大。
- 若需要长期稳定运行，优先解决 LoRa 模块电源问题；如果仍不稳定，改成独立 `3.3V` 模块后重测。
- 若测试地点在北美，记得统一改成 `915E6` 单频段。
- 核对 `compact_protocol.py` 中的命令映射，确保 `READ_ACCEL`、`LED_ON`、`LED_OFF` 对应的短码与 `Rover_R3` 固件一致。
  - 先查 `Rover_Lora <-> Rover_R3` 接线和 `4800 baud`
- `R3_RX` 有响应但 `PC_Lora` 没有 `RX:`
  - 查回包是否成功发回 LoRa

## 8. 后续待验证项

- 是否所有实物板卡都已更新为本次修改后的固件
- 是否两块 MKR WAN 1310 的实际测试区域与频段设置一致
- Murata 固件是否已达到 `1.1.6+`
- 实机情况下地址过滤与 `sync word` 是否足以显著降低环境噪音
- `rover_r3_accel` 在真实传感器接入时是否能稳定返回 `8C|x,y,z`

## 9. 结论

到目前为止，LoRa 通信失败最可能的主因不是单一 bug，而是多个版本与链路条件叠加：

- 新旧代码协议不兼容
- 官方板对板基线与项目原实现不一致
- 频段可能不一致
- 车端 UART 接线/波特率已经改变
- 原来缺少官方消息服务示例中的地址过滤思路
- GUI 现在只认可真正的远端回包

当前已经完成的修正，重点在于把两块 MKR WAN 1310 的无线层改回官方教程更接近的实现方式：

- `LoRa` 库直连
- `parsePacket()` 轮询收包
- 地址头过滤
- `RSSI` 调试信息
- 私有 `sync word`

这些修正能显著提高“区分噪音”和“定位链路断点”的能力，但仍需要实机测试确认最终通信是否稳定。
