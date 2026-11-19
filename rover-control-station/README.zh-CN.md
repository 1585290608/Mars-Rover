[English](README.md) · **简体中文**

# Rover Control Station

D15 是 Mars Rover 项目的主操作界面原型，使用 Python、PyQt6 和 Matplotlib。程序有独立的启动入口和依赖。D15 是原始开发版本的编号。

## 启动

需要 Python 3.10 或以上版本。在这个目录中运行：

```sh
python -m pip install -r requirements.txt
python main.py
```

当前版本的 **Connect** 按钮启动模拟器。它生成遥测和指令确认数据，便于在桌面测试界面。**Replay** 可回放软件记录的加速度计数据。

界面支持遥测图表、指令确认与重试、分级刷新、警报和紧急停止界面。采样数据以 CSV 保存，会话设置和备注以 JSON 保存，文件在 `session_logs/` 下。开始新一轮记录可能覆盖当前 CSV，需要保留的会话可以先复制出来。

协议模拟器中的可选 XOR 模式用于展示数据编码，默认关闭，使用公开的演示值。

对实车 Arduino 和 LoRa 硬件进行台架联调时，请使用独立的 [LoRa Debug & Fix 工具](../lora-test/README.zh-CN.md)。
