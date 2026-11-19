[English](README.md) · **简体中文**

# Mars Rover

卡迪夫大学 Mars Rover 项目的两套独立桌面软件。

| 软件 | 用途 | 在各自目录运行 |
| --- | --- | --- |
| [Rover Control Station](rover-control-station/README.zh-CN.md)（D15） | 主操作界面原型，用于查看遥测、记录会话和回放数据 | `python main.py` |
| [LoRa Debug & Fix](lora-test/README.zh-CN.md)（原 GUI-11） | 实车排障工具，用于定位 LoRa 与 UART 指令和回复链路中的故障 | `python pc_lora_gui.py` |

## Rover Control Station

D15 使用 Python、PyQt6 和 Matplotlib。当前版本使用模拟遥测和指令确认来测试界面，也可以回放软件记录的加速度计 CSV 数据。[启动与功能说明](rover-control-station/README.zh-CN.md)

## LoRa Debug & Fix

GUI-11 使用 Python 和 Tkinter，独立验证从电脑到车端、再到 Uno R3 的完整指令往返链路。工具只把经无线返回的真实回复计为成功，并用车端日志区分无线接收、UART 转发和 Uno 回复三个环节。

最终集成时，我将 Uno R3 的车端 UART 移到 D2/D3，使用 4,800 baud 的 SoftwareSerial，在约 10 分钟内恢复了远程指令执行。

[排障流程与启动说明](lora-test/README.zh-CN.md) · [英文技术报告](lora-test/LORA_DEBUG_REPORT_EN.md)
