# 电源自动化测试平台

基于 Python + pyvisa + Tkinter 的电源自动化测试平台，支持快充协议（PD/QC/AFC/FCP）及电气性能测试。

## 技术栈

- Python 3.8+
- pyvisa + pyvisa-py（仪器控制 via LAN/USB）
- Tkinter（配置工具 UI）
- pyserial（串口通信）
- numpy + openpyxl（数据处理和 Excel 报告）

## 目录结构

```
自动化测试平台/
├── instrument_manager.py   # 仪器管理器
├── logger_config.py       # 统一日志系统
├── test_engine.py         # 测试执行引擎
├── config_ui.py           # 配置工具 UI
├── report_generator.py     # Excel 报告生成器
├── drivers/               # 仪器驱动
├── test_cases/            # 测试用例
│   ├── input_tests/       # 输入测试（IVRT/IUVT/IDT/能效/待机功耗等）
│   ├── output_tests/      # 输出测试（纹波/动态/开关机/电压精度等）
│   ├── protection_tests/   # 保护测试（OCP/OVP/OTP/SCP）
│   └── protocol_tests/    # 协议测试（PD/QC/AFC/FCP）
└── results/               # 测试结果（.gitkeep）
```

## 测试用例

### 输入测试
- InputVoltageRangeTest - 输入电压范围测试
- InputDipTest - 输入跌落测试
- InputUnderVoltageTest - 输入欠压保护测试
- InputEfficiencyTest - 能效测试（6级/7级平均能效）
- InputNoLoadPowerTest - 空载功耗测试
- PowerFactorTest - 功率因数测试
- StandbyPowerTest - 待机功耗测试

### 输出测试
- OutputRippleNoiseTest - 输出纹波噪声测试
- OutputRippleLoadScanTest - 输出纹波负载扫描测试
- OutputRippleInputScanTest - 输出纹波输入扫描测试
- OutputDynamicTest - 输出动态测试
- OutputVoltageAccuracyTest - 输出电压精度测试
- OutputPowerOnOffTest - 开关机过冲/下冲测试

### 保护测试
- OVPTest - 过压保护测试
- OTPTest - 过温保护测试
- OutputOcpProtectTest - 输出过流保护测试
- OutputScpProtectTest - 输出短路保护测试

### 协议测试
- PDProtocolTest - USB PD3.0 协议测试
- QCProtocolTest - QC 协议测试
- AFCProtocolTest - AFC 协议测试
- FCPProtocolTest - FCP 协议测试

## 仪器支持

- IT7321/IT7322 - 交流源
- IT6333A - 直流电源
- IT8511/IT8512 - 电子负载
- WT333E/WT322E - 功率计
- DSOX4024A - 示波器
- IP2716Sniffer - 诱骗器

## 使用方法

```bash
# 安装依赖
pip install pyvisa pyvisa-py pyserial numpy openpyxl

# 运行配置工具
python config_ui.py
```

## License

Private - All rights reserved
