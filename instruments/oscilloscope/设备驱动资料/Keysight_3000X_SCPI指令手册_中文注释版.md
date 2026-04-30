# Keysight InfiniiVision 3000X 系列示波器 SCPI 指令手册

> **仪器型号**: Keysight InfiniiVision 3000X 系列示波器（DSO/MSO-X3012A ~ X3104A）
> **手册来源**: 9018-06894 Programmer's Guide, Rev 02.66.0000
> **适用场景**: SCPI 程控自动化测试、电源开发验证、ATE 系统集成
> **注释说明**: 已分类整理，每条指令附中文功能说明与典型用法

---

## 📋 目录

1. [语法基础与约定](#1-语法基础与约定)
2. [通用指令 Common (*) - IEEE 488.2](#2-通用指令-common-)
3. [根级指令 Root (:)](#3-根级指令-root-)
4. [采集指令 :ACQuire](#4-采集指令-acquire)
5. [通道指令 :CHANnel](#5-通道指令-channel)
6. [时基指令 :TIMebase](#6-时基指令-timebase)
7. [触发指令 :TRIGger](#7-触发指令-trigger)
8. [波形指令 :WAVeform](#8-波形指令-waveform)
9. [测量指令 :MEASure](#9-测量指令-measure)
10. [数学运算 :FUNCtion](#10-数学运算-function)
11. [串行解码 :SBUS](#11-串行解码-sbus)
12. [搜索指令 :SEARch](#12-搜索指令-search)
13. [显示指令 :DISPlay](#13-显示指令-display)
14. [系统指令 :SYSTem](#14-系统指令-system)
15. [存储指令 :SAVE / :RECall](#15-存储指令-save--recall)
16. [函数发生器 :WGEN](#16-函数发生器-wgen)
17. [参考波形 :WMEMory](#17-参考波形-wmemory)
18. [程控示例（电源测试）](#18-程控示例电源测试应用)

---

## 1. 语法基础与约定

### 1.1 符号说明

| 符号 | 含义 | 示例 |
|------|------|------|
| `:` | 命令路径分隔符 | `:ACQuire:TYPE` |
| `*` | IEEE 488.2 通用指令前缀 | `*RST`, `*IDN?` |
| `<n>` | 数字参数，NR1 整型 | `CHANnel1`, `CHANnel2` |
| `<value>` | 数值参数，NR3 科学计数 | `1.5E-3` |
| `[ ]` | 可选语法项 | `[:ACQuire:TYPE]` |
| `{ }` | 枚举选项，`\|` 表示或 | `{ON \| OFF}` |
| `?` | 查询指令后缀 | `*IDN?`, `:CHAN1?` |
| `" "` | 字符串参数引号 | `:CHAN1:LABEL "Vin"` |

### 1.2 数值格式

| 格式 | 说明 | 示例 |
|------|------|------|
| **NR1** | 整型 | `100`, `256`, `0` |
| **NR3** | 科学计数（浮点） | `1.5E-3`, `2.0E+6` |
| **字符串** | ASCII 字符串引号 | `"myfile.csv"` |
| **definite block** | 二进制数据块 | `#800001000<data>` |

### 1.3 命令行格式

```
# 设置命令（无返回值）
:CHANnel1:SCALe 0.5

# 查询命令（返回数值/字符串）
:CHANnel1:SCALe?

# 组合命令（分号分隔）
:RST; :CHANnel1:SCALe 1; :TIMebase:SCALe 0.001; :TRIGger:MODE EDGE
```

---

## 2. 通用指令 Common (*)

> **来源**: IEEE 488.2 标准，所有 SCPI 仪器通用
> **功能**: 仪器识别、状态查询、复位、保存/调用设置

### 2.1 核心通用指令速查表

| 指令 | 功能 | 用法 |
|------|------|------|
| `*IDN?` | 查询仪器标识（型号/序列号/固件） | 获取仪器信息 |
| `*RST` | 恢复出厂默认设置 | 程控前初始化 |
| `*CLS` | 清除状态寄存器和错误队列 | 清除历史错误 |
| `*OPC?` | 等待所有操作完成，返回 "1" | 同步等待 |
| `*WAI` | 等待当前命令执行完毕 | 命令串行执行 |
| `*TRG` | 软件触发（等价前面板 Force Trigger） | 强制触发采集 |
| `*SAV <n>` | 保存当前设置为内部位置 0-9 | 快速保存设置 |
| `*RCL <n>` | 调用内部位置 0-9 的保存设置 | 快速恢复设置 |
| `*ESR?` | 查询标准事件状态寄存器 | 获取错误类型 |
| `*STB?` | 查询状态字节 | 获取服务请求状态 |
| `*OPT?` | 查询已安装的选件/许可证 | 确认功能可用性 |
| `*TST?` | 仪器自检，返回 0=通过 | 自检查询 |
| `*LRN?` | 获取当前完整设置（learn string） | 设置备份/克隆 |

### 2.2 详细说明

#### *IDN? — 仪器身份识别
```
功能: 查询仪器型号、序列号、固件版本
返回: AGILENT TECHNOLOGIES,<model>,<serial>,<firmware>
示例:
  myScope.WriteString("*IDN?")
  → "AGILENT TECHNOLOGIES,DSO-X3104A,MY12345678,02.66.0000"
```

#### *RST — 恢复出厂设置
```
功能: 将示波器恢复到出厂默认状态（清除当前设置）
用法: 程控测试开始前执行，确保每次测试环境一致
示例:
  myScope.WriteString("*RST")
```

#### *SAV / *RCL — 保存/调用设置
```
功能: 将当前设置保存到内部寄存器（0-9），或从中恢复
用法: 常用测试场景的快速切换（如 brown-in/out 测试固定设置）
示例:
  myScope.WriteString("*SAV 1")     # 保存到位置1
  myScope.WriteString("*RCL 1")     # 从位置1恢复
```

#### *CLS — 清除状态
```
功能: 清除所有状态寄存器和错误队列
用法: 在测试循环开始前执行，避免历史错误残留
示例:
  myScope.WriteString("*CLS")
```

#### *OPC? — 操作完成查询
```
功能: 等待所有挂起操作完成，返回 "1"
用法: 确保采集完成后再读取数据（替代固定延时）
示例:
  myScope.WriteString(":DIGitize")
  myScope.WriteString("*OPC?")
  → "1"  # 表示采集完成
```

---

## 3. 根级指令 Root (:)

> **来源**: SCPI 标准根级命令，影响示波器基本运行状态
> **功能**: 运行控制、自动设置、通道显示控制、状态查询

### 3.1 运行控制

| 指令 | 功能 | 典型用法 |
|------|------|---------|
| `:RUN` | 启动示波器连续采集 | 开始测试 |
| `:STOP` | 停止采集 | 冻结数据 |
| `:SINGle` | 单次触发采集（Single 模式） | 捕获单次事件 |
| `:DIGitize` | 触发采集并传输数据 | 自动采集波形 |
| `:TRIGger:FORCe` | 强制触发（不等触发条件） | 手动强制触发 |
| `:AUToscale` | 自动设置（等价按 AutoScale 键） | 快速初始化 |
| `:RSTate?` | 查询当前运行状态（RUN/STOP/SING） | 状态监控 |

#### :DIGitize — 触发采集
```
功能: 触发一次采集，等采集完成（等价于运行+单次触发）
语法: :DIGitize [<source>[,...,<source>]]
参数: source ::= {CHANnel<n> | FUNCtion | MATH | SBUS{1|2}}
      MSO型号额外支持: DIGital<d> | POD{1|2} | BUS{1|2}
示例（电源测试场景）:
  :DIGitize CHANnel1              # 仅采集通道1
  :DIGitize CHANnel1,CHANnel2     # 同时采集通道1和2
```

#### :AUToscale — 自动设置
```
功能: 自动分析信号并设置最佳时基/垂直/触发参数
用法: 接入新信号后快速建立显示
示例:
  :AUToscale                       # 对所有活动信号自动设置
  :AUToscale CHANnel1             # 仅对通道1自动设置
```

#### :RUN / :STOP / :SINGle — 运行控制
```
:RUN         → 启动连续采集（等价按 Run 键）
:STOP        → 停止采集
:SINGle      → 单次触发模式（采集一次后停止）
:RSTate?     → 查询当前状态，返回 {RUN | STOP | SING}
```

### 3.2 通道显示控制

| 指令 | 功能 |
|------|------|
| `:VIEW <source>` | 显示指定通道（等同于开启） |
| `:BLANk <source>` | 关闭（隐藏）指定通道 |
| `:STATus? <source>` | 查询通道状态（返回 0/1 = 关闭/开启） |

```
示例:
  :VIEW CHANnel1           # 显示通道1
  :BLANk CHANnel3          # 隐藏通道3
  :STATus? CHANnel2        # 查询通道2是否显示
```

---

## 4. 采集指令 :ACQuire

> **功能**: 设置示波器的采集模式、采样率、平均次数、分段存储等

### 4.1 采集模式

| 指令 | 功能 | 选项说明 |
|------|------|---------|
| `:ACQuire:TYPE` | 设置采集类型 | `NORMal` 普通 / `AVERage` 平均 / `HRESolution` 高分辨率 / `PEAK` 峰值检测 |
| `:ACQuire:MODE` | 设置采集模式 | `RTIMe` 实时 / `SEGMented` 分段存储（需 SGM 选件） |
| `:ACQuire:COUNt` | 设置平均次数 | 2~65536（仅 AVERage 模式有效） |
| `:ACQuire:SRATe?` | 查询当前实际采样率 | 返回 samples/s |
| `:ACQuire:POINts?` | 查询当前存储点数 | 返回整型点数 |

#### :ACQuire:TYPE — 采集类型详解

```
NORMal（普通模式）        → 默认模式，适合大多数信号
AVERage（平均模式）       → 对周期性信号降噪，提升信噪比
  设置: :ACQuire:TYPE AVER; :ACQuire:COUNt 256
HRESolution（高分辨率）   → 等效过采样平滑，适合低频/慢速信号
PEAK（峰值检测）          → 捕获窄脉冲/毛刺（500us/div 及更慢时基）
```

```
电源测试典型设置:
  # 低噪声测量：平均模式，256次平均
  :ACQuire:TYPE AVER; :ACQuire:COUNt 256
  
  # 捕获开关尖峰：峰值检测模式
  :ACQuire:TYPE PEAK
  
  # 慢速纹波测量：高分辨率模式
  :ACQuire:TYPE HRESolution
```

### 4.2 分段存储（需 SGM 选件）

| 指令 | 功能 | 参数 |
|------|------|------|
| `:ACQuire:SEGMented:COUNt` | 设置分段数量 | 2~1000 |
| `:ACQuire:SEGMented:ANAllyze` | 分析所有分段 | 无参数 |
| `:ACQuire:SEGMented:INDex` | 设置/查询当前显示的分段索引 | 1~分段数 |
| `:ACQuire:SEGMented:COUNt?` | 查询已采集分段数 | — |

```
分段存储应用（电源启动/关断序列捕获）:
  :ACQuire:MODE SEGMented
  :ACQuire:SEGMented:COUNt 100    # 采集100段
  :DIGitize                       # 开始采集
  *OPC?                           # 等待完成
  :ACQuire:SEGMented:COUNt?       # 查询已采集段数
```

---

## 5. 通道指令 :CHANnel

> **功能**: 控制各模拟通道的垂直（Y轴）参数：量程、偏移、耦合、探头、带宽限制、标签

### 5.1 垂直设置

| 指令 | 功能 | 参数说明 |
|------|------|---------|
| `:CHANnel<n>:SCALe` | 设置每格电压（V/div） | 值 + 单位 {V \| mV} |
| `:CHANnel<n>:RANGe` | 设置满量程电压范围（10div） | 值 + 单位 {V \| mV} |
| `:CHANnel<n>:OFFSet` | 设置垂直偏置（中心值） | 值 + 单位 {V \| mV} |
| `:CHANnel<n>:UNITs` | 设置垂直单位 | `{VOLT \| AMPere}` |
| `:CHANnel<n>:VERNier` | 细调刻度开关 | `{0 \| OFF \| 1 \| ON}` |

```
注意: SCALe 和 RANGe 是同一个参数的两面
  SCALe = RANGe / 10
  例如: RANGe 40V → SCALe 4V/div

电源测试典型设置:
  :CHANnel1:SCALe 0.5         # 通道1设为 500mV/div（测原边电流→分流电阻）
  :CHANnel2:SCALe 10          # 通道2设为 10V/div（测输出电压）
  :CHANnel3:SCALe 5           # 通道3设为 5V/div（测MOSFET Vds）
```

### 5.2 耦合与滤波

| 指令 | 功能 | 选项 |
|------|------|------|
| `:CHANnel<n>:COUPling` | 输入耦合 | `{DC \| AC \| DC50}` |
| `:CHANnel<n>:INVert` | 波形反转 | `{0 \| OFF \| 1 \| ON}` |
| `:CHANnel<n>:BANDwidth` | 带宽限制 | `{20E6 \| 25E6}` Hz |
| `:CHANnel<n>:PROTection` | 过压保护状态 | `{NORM \| TRIP}` |

```
耦合说明:
  DC  → 直流耦合，所有频率通过（最常用）
  AC  → 交流耦合，隔直（测纹波时使用）
  DC50 → 50Ω终端（高频信号）

  # 测输出纹波（需隔直）
  :CHANnel2:COUPling AC
  :CHANnel2:SCALe 0.02       # 20mV/div 观察纹波细节
  
  # 测Vds波形（全频率成分）
  :CHANnel1:COUPling DC
```

### 5.3 探头设置

| 指令 | 功能 | 参数 |
|------|------|------|
| `:CHANnel<n>:PROBe` | 设置探头衰减比 | 数值（如 10 表示 10:1） |
| `:CHANnel<n>:PROBe:CALibration` | 探头校准 | 无（执行探头补偿） |
| `:CHANnel<n>:PROBe:SKEw` | 探头 skew 校正 | -100ns ~ +100ns |
| `:CHANnel<n>:PROBe:ID?` | 查询探头 ID | 返回探头类型字符串 |
| `:CHANnel<n>:PROBe:STYPe` | 探头类型 | `{DIFFerential \| SINGle}` |

```
示例:
  :CHANnel1:PROBe 10         # 10:1 无源探头
  :CHANnel2:PROBe 1          # 1:1 探头（直接通过）
  :CHANnel1:PROBe:SKEW 5E-9  # 校正5ns skew（多探头同步测量）
```

### 5.4 通道标签与显示

| 指令 | 功能 | 参数 |
|------|------|------|
| `:CHANnel<n>:LABel` | 设置通道标签（显示在屏幕上） | 字符串（最多10字符） |
| `:CHANnel<n>:DISPlay` | 通道显示开关 | `{0 \| OFF \| 1 \| ON}` |

```
电源测试通道标签示例:
  :CHANnel1:LABEL "Isense"     # 电流检测
  :CHANnel2:LABEL "Vout"       # 输出电压
  :CHANnel3:LABEL "Vds"        # MOSFET漏极电压
  :CHANnel4:LABEL "Vg"         # 栅极驱动
```

---

## 6. 时基指令 :TIMebase

> **功能**: 控制水平（X轴）参数：时基范围、扫描速度、延迟、参考点、XY模式

### 6.1 时基模式

| 指令 | 功能 | 选项 |
|------|------|------|
| `:TIMebase:MODE` | 时基模式 | `MAIN` 主时基 / `WINDow` 延迟时基 / `XY` X-Y模式 / `ROLL` 滚动模式 |

```
MAIN    → 常规时基（默认）
WINDow  → 窗口/延迟时基（对某段波形放大查看）
XY      → X-Y 模式（通道1=X，通道2=Y，用于李萨如图形）
ROLL    → 滚动模式（从右向左滚动，无触发，适合超低频信号）
```

### 6.2 时间设置

| 指令 | 功能 | 参数说明 |
|------|------|---------|
| `:TIMebase:SCALe` | 设置时基（秒/div） | 值 + 单位（s/ms/us/ns） |
| `:TIMebase:RANGe` | 设置10格总时间范围 | 值（= SCALe × 10） |
| `:TIMebase:POSition` | 触发点相对屏幕中心的位置 | 秒（可正可负） |
| `:TIMebase:REFerence` | 触发参考点 | `{LEFT \| CENTer \| RIGHt}` |

```
注意: SCALe 和 RANGe 的关系
  RANGe = SCALe × 10

电源测试时基设置示例:
  # 观察启动过程（秒级）
  :TIMebase:SCALe 0.5           # 500ms/div，全屏5秒
  
  # 观察开关周期（kHz级）
  :TIMebase:SCALe 0.001         # 1ms/div ≈ 100kHz方波一个周期
  :TIMebase:SCALe 1E-6         # 1us/div ≈ 100kHz方波一个周期
  
  # 观察开关尖峰（MHz级）
  :TIMebase:SCALe 1E-9         # 1ns/div，观察MOSFET开关瞬态
```

---

## 7. 触发指令 :TRIGger

> **功能**: 设置触发条件，捕获特定信号事件
> **触发类型**: Edge / Glitch / Pattern / TV / Delay / EBurst / OR / Runt / Hold / Transition / Serial / USB

### 7.1 触发模式选择

| 指令 | 功能 | 说明 |
|------|------|------|
| `:TRIGger:MODE` | 选择触发类型 | 见下方选项 |
| `:TRIGger:SWEep` | 扫描模式 | `{AUTO \| NORMal}` |

```
触发类型选项:
  EDGE    → 边沿触发（最常用）
  GLITch  → 脉宽触发（捕获异常脉宽）
  PATTern → 模式触发（多通道组合条件）
  TV      → TV 触发（视频信号）
  DELay   → 延迟触发（A触发后B触发）
  EBURst  → Nth 边沿突发触发
  OR      → 或触发（多通道任一满足）
  RUNT    → 矮脉冲触发（欠幅脉冲）
  SHOLd   → 建立/保持时间触发
  TRANsition → 转换时间（上升/下降沿速率）
  SBUS{1|2} → 串行解码触发（I2C/SPI/UART/CAN等）
  USB     → USB 协议触发
```

### 7.2 边沿触发（最常用）

| 指令 | 功能 | 参数 |
|------|------|------|
| `:TRIGger:MODE EDGE` | 设置边沿触发模式 | — |
| `:TRIGger:EDGE:SOURce` | 触发源 | `{CHANnel<n> \| EXTernal \| LINE \| WGEN}` |
| `:TRIGger:EDGE:LEVel` | 触发电压阈值 | 数值 |
| `:TRIGger:EDGE:SLOPe` | 触发边沿方向 | `{POSitive \| NEGative \| EITHer}` |
| `:TRIGger:EDGE:COUPling` | 触发耦合 | `{DC \| AC \| LFR \| HFR}` |

```
边沿触发详解:
  SOURce    → 触发信号来源通道
  LEVel     → 触发电平（单位随通道单位）
  SLOPe     → POS=上升沿 / NEG=下降沿 / EITHer=任一边沿
  COUPling  → DC=直流 / AC=交流 / LFR=低频抑制 / HFR=高频抑制

电源测试边沿触发示例:
  # 在输出电压上升沿触发（捕获启动瞬态）
  :TRIGger:MODE EDGE
  :TRIGger:EDGE:SOURce CHANnel2
  :TRIGger:EDGE:LEVel 5
  :TRIGger:EDGE:SLOPe POS
  
  # 在Vds下降沿触发（MOSFET关断瞬间）
  :TRIGger:MODE EDGE
  :TRIGger:EDGE:SOURce CHANnel3
  :TRIGger:EDGE:LEVel 10
  :TRIGger:EDGE:SLOPe NEG
```

### 7.3 脉宽触发（Glitch）

| 指令 | 功能 | 参数 |
|------|------|------|
| `:TRIGger:GLITch:POLarity` | 极性 | `{POS \| NEG}` 正/负脉宽 |
| `:TRIGger:GLITch:WIDTh` | 脉宽值 | 时间值 |
| `:TRIGger:GLITch:QUALifier` | 条件 | `{LESS \| GREATER \| RANGe}` 小于/大于/范围内 |

```
脉宽触发应用（电源保护测试）:
  # 捕获 < 1us 的异常窄脉冲（可能的过流信号）
  :TRIGger:MODE GLITch
  :TRIGger:GLITch:SOURce CHANnel1
  :TRIGger:GLITch:POLarity POS
  :TRIGger:GLITch:QUALifier LESS
  :TRIGger:GLITch:WIDTh 1E-6    # 1微秒
  
  # 捕获 > 10ms 的异常宽脉冲（可能的卡死信号）
  :TRIGger:GLITch:QUALifier GREATER
  :TRIGger:GLITch:WIDTh 0.01   # 10毫秒
```

### 7.4 矮脉冲触发（Runt）

| 指令 | 功能 | 参数 |
|------|------|------|
| `:TRIGger:RUNT:WIDTh` | 矮脉宽阈值 | 时间 |
| `:TRIGger:RUNT:HIGH` | 高阈值 | 电压 |
| `:TRIGger:RUNT:LOW` | 低阈值 | 电压 |
| `:TRIGger:RUNT:POLarity` | 极性 | `{POS \| NEG \| EITHer}` |

```
Runt 触发应用:
  # 捕获幅度未达到正常高电平的异常脉冲（如过驱导致的削顶）
  :TRIGger:MODE RUNT
  :TRIGger:RUNT:SOURce CHANnel2
  :TRIGger:RUNT:HIGH 4.5       # 高阈值 4.5V
  :TRIGger:RUNT:LOW 0.5        # 低阈值 0.5V
  :TRIGger:RUNT:POLarity POS
```

### 7.5 触发辅助设置

| 指令 | 功能 | 说明 |
|------|------|------|
| `:TRIGger:HOLDoff` | 触发释抑时间（防止重复触发） | 40ns ~ 10s |
| `:TRIGger:HFReject` | 高频抑制滤波 | `{ON \| OFF}`，抑制>50kHz |
| `:TRIGger:NREJect` | 噪声抑制 | `{ON \| OFF}`，提高触发稳定性 |
| `:TRIGger:LEVel:ASETup` | 自动设置所有通道触发电平 | 自动设置为信号的50%值 |

```
触发释抑（HOLDoff）在多周期信号中的应用:
  # 波形有多个过零点，但只希望在第一个过零点触发
  :TRIGger:HOLDoff 0.0001      # 100us 释抑时间（约等于信号周期）
```

---

## 8. 波形指令 :WAVeform

> **功能**: 读取示波器采集的波形数据（电压-时间原始采样点）

### 8.1 数据读取流程

```
Step 1: 选择数据源
  :WAVeform:SOURce CHANnel1

Step 2: 设置数据格式
  :WAVeform:FORMat BYTE        # BYTE=1字节/点（常用）/ WORD=2字节 / ASCII=文本

Step 3: 设置传输点数
  :WAVeform:POINts 1000        # 传输1000个点

Step 4: 设置点数模式
  :WAVeform:POINts:MODE NORMal  # NORMal=屏幕点 / MAXimum=最大 / RAW=原始

Step 5: 读取前导码（解码波形数据用）
  :WAVeform:PREamble?          # 返回: format,type,points,count,xincr,xorig,xref,yincr,yorig,yref

Step 6: 读取波形数据
  :WAVeform:DATA?              # 返回二进制数据块
```

### 8.2 核心波形指令

| 指令 | 功能 | 返回值 |
|------|------|-------|
| `:WAVeform:SOURce` | 选择数据来源通道 | — |
| `:WAVeform:FORMat` | 数据格式 | `BYTE`/`WORD`/`ASCII` |
| `:WAVeform:POINts` | 传输点数 | 100~8000000 |
| `:WAVeform:POINts:MODE` | 点数模式 | `NORMal`/`MAXimum`/`RAW` |
| `:WAVeform:PREamble?` | 获取波形解码参数 | 9个数值 |
| `:WAVeform:DATA?` | 读取原始采样数据 | 二进制块 |
| `:WAVeform:COUNt?` | 获取当前采集次数 | 1~65536 |
| `:WAVeform:XINCrement?` | X轴（时间）步进 | 秒/点 |
| `:WAVeform:YINCrement?` | Y轴（电压）步进 | V/点 |
| `:WAVeform:TYPE?` | 采集类型 | `NORM`/`PEAK`/`AVER`/`HRES` |

### 8.3 波形数据换算公式

```
从 PREAMBLE 获取:
  xincrement → X轴每点时间间隔（秒）
  xorigin    → X轴起始时间（秒）
  xreference → X轴参考点（通常=0）
  yincrement → Y轴每点电压（伏）
  yorigin    → Y轴零点电压（伏）
  yreference → Y轴参考点（通常=127或0）

电压换算:
  voltage = (data_value - yreference) × yincrement + yorigin

时间换算:
  time_point[n] = (n - xreference) × xincrement + xorigin
```

### 8.4 Python 程控读取示例

```python
import visa

class Keysight3000X:
    def __init__(self, addr='USB0::0x0957::0x17A4::MY12345678::INSTR'):
        self.rm = visa.ResourceManager()
        self.scope = self.rm.open_resource(addr)
        self.scope.timeout = 10000

    def read_waveform(self, channel=1):
        self.scope.write(f':WAVeform:SOURce CHANnel{channel}')
        self.scope.write(':WAVeform:FORMat BYTE')
        self.scope.write(':WAVeform:POINts:MODE NORMal')
        self.scope.write(':WAVeform:POINts 1000')
        
        # 读取前导码
        preamble = self.scope.query(':WAVeform:PREamble?')
        fmt, typ, pts, cnt, xinc, xorg, xref, yinc, yorg, yref = \
            [float(x) for x in preamble.strip().split(',')]
        
        # 读取数据
        raw = self.scope.query_binary_values(':WAVeform:DATA?', datatype='B')
        
        # 转换为电压-时间
        times = [(i - xref) * xinc + xorg for i in range(len(raw))]
        volts = [(v - yref) * yinc + yorg for v in raw]
        
        return times, volts

    def close(self):
        self.scope.close()
```

---

## 9. 测量指令 :MEASure

> **功能**: 自动测量波形参数（频率、幅值、上升时间、功率等）

### 9.1 基础测量

| 测量项 | 指令 | 说明 |
|--------|------|------|
| 频率 | `:MEASure:FREQuency` | 信号频率（Hz） |
| 周期 | `:MEASure:PERiod` | 信号周期（s） |
| 峰峰值 | `:MEASure:VPP` | Vmax - Vmin |
| 幅值 | `:MEASure:VAMPlitude` | 顶端值 - 底端值 |
| 最大值 | `:MEASure:VMAX` | 波形最大值 |
| 最小值 | `:MEASure:VMIN` | 波形最小值 |
| 平均值 | `:MEASure:VAVerage` | 整周期平均值（DC） |
| RMS | `:MEASure:VRMS` | 有效值 |
| 占空比（正） | `:MEASure:DUTYcycle` | 正脉宽/周期 |
| 占空比（负） | `:MEASure:NDUTy` | 负脉宽/周期 |
| 正脉宽 | `:MEASure:PWIDth` | 正脉冲宽度（s） |
| 负脉宽 | `:MEASure:NWIDth` | 负脉冲宽度（s） |
| 上升时间 | `:MEASure:RISetime` | 10%~90% 上升时间 |
| 下降时间 | `:MEASure:FALLtime` | 90%~10% 下降时间 |
| 过冲（正） | `:MEASure:OVERshoot` | 正过冲百分比 |
| 过冲（负） | `:MEASure:PERshoot` | 负过冲百分比 |
| 尖峰宽度 | `:MEASure:BWIDth` | 突发脉冲宽度 |
| 相位 | `:MEASure:PHASe` | 两通道相位差 |

```
基础测量用法:
  :MEASure:FREQuency CHANnel1           # 测量通道1频率
  :MEASure:VPP CHANnel2                 # 测量通道2峰峰值
  :MEASure:RISetime CHANnel1            # 测量通道1上升时间
  :MEASure:VRMS CHANnel1                # 测量通道1 RMS电压

电源测试典型测量:
  # 测量开关频率
  :MEASure:FREQuency CHANnel3           # MOSFET驱动频率
  
  # 测量输出电压纹波
  :MEASure:VPP CHANnel2                 # 输出电压峰峰值
  
  # 测量MOSFET开关上升时间
  :MEASure:RISetime CHANnel1            # Isense 上升时间
  :MEASure:FALLtime CHANnel1            # Isense 下降时间
```

### 9.2 阈值设置（测量参考电平）

| 指令 | 功能 | 说明 |
|------|------|------|
| `:MEASure:DEFine:THResholds` | 设置测量阈值模式 | `{STANdard \| PERCent \| ABSolute}` |
| `:MEASure:DEFine:THResholds,THResholds[,<source>]` | 设置具体阈值 | 上/中/下阈值 |

```
阈值设置:
  STANdard → 默认阈值（10%/50%/90%）
  PERCent  → 自定义百分比阈值
  ABSolute → 绝对电压阈值

  # 设置为 20%/50%/80% 阈值
  :MEASure:DEFine:THResholds PERCent,80,50,20
```

### 9.3 延迟与相位测量

| 指令 | 功能 |
|------|------|
| `:MEASure:DELay` | 两通道间时间延迟 |
| `:MEASure:DEFine:DELay` | 自定义延迟测量条件（边沿选择） |

```
延迟测量应用（信号同步分析）:
  # 测量Vg和Vds之间的延迟（MOSFET开关延迟）
  :MEASure:DELay CHANnel4,CHANnel3     # 通道4相对通道3的延迟
  
  # 自定义延迟条件：上升沿第2个交点
  :MEASure:DEFine:DELay +,2,+ ,2       # 源1上升沿第2次 × 源2上升沿第2次
```

### 9.4 计数器（精确频率计）

| 指令 | 功能 | 返回值 |
|------|------|-------|
| `:MEASure:COUNter` | 硬件计数器测频 | 频率（Hz），精度高于自动测量 |

```
精确频率计数:
  :MEASure:COUNter CHANnel1
  → 返回精确频率值（如 99.847E+3 Hz）
  
  # 用于精确测量开关频率稳定性
```

### 9.5 自动清零测量

| 指令 | 功能 |
|------|------|
| `:MEASure:CLEar` | 清除所有自动测量结果 |
| `:MEASure:CLEar ALL` | 清除所有测量项 |

---

## 10. 数学运算 :FUNCtion

> **功能**: 在线数学运算、FFT频谱分析、滤波等

### 10.1 运算类型

| 运算 | 指令 | 说明 |
|------|------|------|
| 加法 | `ADD` | 两通道相加 |
| 减法 | `SUBTract` | 两通道相减 |
| 乘法 | `MULTiply` | 两通道相乘 |
| 除法 | `DIVide` | 两通道相除（需高级数学选件） |
| 积分 | `INTegrate` | 积分运算（面积） |
| 微分 | `DIFF` | 微分运算（斜率） |
| FFT | `FFT` | 频谱分析 |
| 绝对值 | `ABSolute` | 绝对值 |
| 平方 | `SQUare` | 平方 |
| 对数 | `LOG` / `LN` | 对数运算 |
| 低通滤波 | `LOWPass` | 低通滤波器 |
| 高通滤波 | `HIGHpass` | 高通滤波器 |

### 10.2 FFT 频谱分析

| 指令 | 功能 | 参数 |
|------|------|------|
| `:FUNCtion:OPERation FFT` | 选择FFT运算 | — |
| `:FUNCtion:FFT:SPAN` | 频率跨度 | Hz |
| `:FUNCtion:FFT:CENTer` | 中心频率 | Hz |
| `:FUNCtion:FFT:VTYPe` | 垂直单位 | `{DB \| LINEAR}` |
| `:FUNCtion:FFT:WINDow` | 窗函数 | `{RECT \| HANN \| FLATtop \| BHARris}` |

```
FFT应用示例（电源EMI分析）:
  # 分析开关频率及其谐波
  :FUNCtion:OPERation FFT
  :FUNCtion:SOURce1 CHANnel2           # 对输出电压做FFT
  :FUNCtion:FFT:SPAN 1E6               # 跨度 1MHz
  :FUNCtion:FFT:CENTer 500E3           # 中心 500kHz
  :FUNCtion:FFT:WINDow HANNing         # 汉宁窗（频率精度）
```

### 10.3 微分与积分（功率分析）

```
积分应用 — 计算能量:
  # 对电流积分求电荷量（Q = ∫I dt）
  :FUNCtion:OPERation INTegrate
  :FUNCtion:SOURce1 CHANnel1           # 对电流波形积分
  
微分应用 — 计算功率斜率:
  # 对电压微分求dV/dt
  :FUNCtion:OPERation DIFF
  :FUNCtion:SOURce1 CHANnel2           # 对输出电压微分
```

---

## 11. 串行解码 :SBUS

> **功能**: I2C / SPI / UART(COM) / CAN / LIN / FlexRay / I2S / ARINC429 / MIL-1553 串行协议解码与触发

### 11.1 支持的协议

| 协议 | 触发前缀 | 说明 |
|------|---------|------|
| I2C | `:SBUS<n>:IIC` | 内部集成电路 |
| SPI | `:SBUS<n>:SPI` | 串行外设接口 |
| UART/RS232 | `:SBUS<n>:UART` | 通用异步收发 |
| CAN | `:SBUS<n>:CAN` | 控制器局域网 |
| LIN | `:SBUS<n>:LIN` | 局部互连网络 |
| FlexRay | `:SBUS<n>:FLEX` | 汽车高速网络 |
| I2S | `:SBUS<n>:I2S` | 音频接口 |
| ARINC429 | `:SBUS<n>:A429` | 航空电子 |
| MIL-1553 | `:SBUS<n>:M1553` | 军用数据总线 |

### 11.2 I2C 解码设置

```
I2C 解码触发示例:
  :SBUS1:SOURce CHANnel1               # I2C 数据线
  :SBUS1:IIC:CLOCk CHANnel2            # I2C 时钟线
  
  # 设置触发地址和数据
  :SBUS1:IIC:TRIGger:TYPE WRITe7       # 触发7位写操作
  :SBUS1:IIC:TRIGger:PATTern:ADDRess "0x68"  # 地址 0x68（MPU6050传感器）
  
  # 读取解码结果
  :LISTer?
```

### 11.3 UART 解码设置

```
UART 解码示例:
  :SBUS1:SOURce CHANnel1
  :SBUS1:UART:BAUD 115200              # 波特率 115200
  :SBUS1:UART:TRIGger:TYPE DATA        # 数据触发
  :SBUS1:UART:TRIGger:DATA "55"       # 触发数据 0x55
```

---

## 12. 搜索指令 :SEARch

> **功能**: 在捕获的波形中搜索特定事件（边沿/毛刺/矮脉冲/转换时间）

### 12.1 搜索类型

| 类型 | 说明 | 关键参数 |
|------|------|---------|
| `:SEARch:EDGE` | 边沿搜索 | 源、斜率、电平 |
| `:SEARch:GLITch` | 毛刺搜索 | 源、极性、脉宽条件 |
| `:SEARch:RUNT` | 矮脉冲搜索 | 高低阈值、脉宽 |
| `:SEARch:TRANsition` | 转换时间搜索 | 斜率、时间范围 |

### 12.2 搜索设置

```
搜索示例 — 查找所有过压事件:
  :SEARch:MODE EDGE
  :SEARch:EDGE:SOURce CHANnel2
  :SEARch:EDGE:SLOPe POS
  :SEARch:EDGE:LEVel 5.5              # 高于5.5V的上升沿
  
  # 搜索毛刺（<100ns的窄脉冲）
  :SEARch:MODE GLITch
  :SEARch:GLITch:SOURce CHANnel1
  :SEARch:GLITch:WIDTh:QUALifier LESS
  :SEARch:GLITch:WIDTh 100E-9         # <100ns
  
  # 查询搜索结果数量
  :SEARch:COUNt?                       # 返回匹配事件数
```

---

## 13. 显示指令 :DISPlay

> **功能**: 控制屏幕显示效果：网格、颜色、亮度、格式

### 13.1 显示控制

| 指令 | 功能 | 选项 |
|------|------|------|
| `:DISPlay:LABel` | 显示通道标签 | `{0 \| OFF \| 1 \| ON}` |
| `:DISPlay:GRATICule` | 网格显示模式 | `{GRID \| GRIDONLY \| LINE \| DOTmatrix \| NOGRID \| XYY1}` |
| `:DISPlay:PERSistence` | 余辉时间 | `{AUTO \| OFF \| INFinite \| <seconds>}` |
| `:DISPlay:INTENSITY` | 显示亮度 | `{GRATICULE \| WAVEFORM \| 0~100}` |
| `:DISPlay:COLOR` | 波形颜色方案 | `{NORMal \| TEMPerature}` |

```
显示设置:
  # 网格: 8×10格
  :DISPlay:GRATICule GRID
  
  # 无限余辉（观察抖动/偶发事件）
  :DISPlay:PERSistence INFinite
  
  # 自动余辉（随时间自然消退）
  :DISPlay:PERSistence AUTO
  
  # 波形亮度: 80%
  :DISPlay:INTENSITY:WAVEFORM 80
```

---

## 14. 系统指令 :SYSTem

> **功能**: 系统级操作：错误查询、日期时间、固件信息、远程日志

### 14.1 系统信息

| 指令 | 功能 | 返回值 |
|------|------|-------|
| `:SYSTem:ERRor?` | 读取错误队列（先进先出） | 代码+描述 |
| `:SYSTem:DATE?` | 查询日期 | `year,month,day` |
| `:SYSTem:TIME?` | 查询时间 | `hours,minutes,seconds` |
| `:SYSTem:DIDentifier?` | 查询主机ID | 字符串 |
| `:SYSTem:SETup?` | 获取完整设置（learn string） | 二进制块 |
| `:SYSTem:DSP` | 屏幕显示消息 | 字符串 |

```
错误查询（调试必备）:
  :SYSTem:ERRor?
  → "-221,Settings conflict"       # 设置冲突错误
  → "+0,No error"                   # 无错误
  
  # 建议在每次SCPI命令后查询一次错误队列

日期时间设置:
  :SYSTem:DATE 2026,4,23
  :SYSTem:TIME 10,30,0
```

---

## 15. 存储指令 :SAVE / :RECall

> **功能**: 保存和加载示波器设置、屏幕图像、波形数据、参考波形

### 15.1 保存类型

| 指令 | 保存内容 | 格式 |
|------|---------|------|
| `:SAVE:SETup` | 仪器设置 | `.scp` |
| `:SAVE:IMAGe` | 屏幕图像 | `{TIFF \| BMP \| PNG}` |
| `:SAVE:WAVeform` | 波形数据 | `{CSV \| BINary \| ASCiixy}` |
| `:SAVE:MULTi` | 多屏幕截图 | — |
| `:SAVE:POWer` | 功率测量报告 | — |
| `:SAVE:WMEMory` | 参考波形 | — |
| `:SAVE:ARBitrary` | 任意波形 | — |

### 15.2 保存示例

```
保存设置到USB:
  :SAVE:SETup:STARt "\\usb\\my_flyback_setup.scp"
  
保存屏幕截图:
  :SAVE:IMAGe:STARt "\\usb\\brownout_test.png"
  :SAVE:IMAGe:FORMat PNG
  
保存波形数据（CSV格式）:
  :SAVE:WAVeform:FORMat CSV
  :SAVE:WAVeform:STARt "\\usb\\Vds_waveform.csv"
  :SAVE:WAVeform:SOURce CHANnel3
  
保存到内部位置:
  :SAVE:SETup 1                    # 保存到内部位置1
  :RECall:SETup 1                   # 从位置1恢复
```

---

## 16. 函数发生器 :WGEN

> **功能**: 内置波形发生器（需 WAVEGEN 选件）：生成正弦/方波/三角/噪声/直流/Arb信号

### 16.1 波形输出

| 指令 | 功能 | 参数 |
|------|------|------|
| `:WGEN:FUNCtion` | 波形类型 | `SINusoid / SQUare / RAMP / PULSe / NOISe / DC / SINC / ARBitrary` |
| `:WGEN:FREQuency` | 频率 | Hz |
| `:WGEN:PERiod` | 周期 | 秒 |
| `:WGEN:VOLTage` | 幅值 | V |
| `:WGEN:VOLTage:OFFSet` | 直流偏置 | V |
| `:WGEN:OUTPut` | 输出开关 | `{0 \| OFF \| 1 \| ON}` |
| `:WGEN:OUTPut:LOAD` | 终端负载 | `{ONEMeg \| FIFTy}` |

### 16.2 方波特殊参数

| 指令 | 功能 | 参数 |
|------|------|------|
| `:WGEN:FUNCtion:SQUare:DCYCle` | 占空比 | 20%~80% |

```
函数发生器应用（被测电路激励）:
  # 输出 100kHz 方波，幅值 3.3V
  :WGEN:FUNCtion SQUare
  :WGEN:FREQuency 100E3
  :WGEN:VOLTage 1.65              # 幅值 1.65V（峰峰值3.3V）
  :WGEN:VOLTage:OFFSet 1.65       # 偏置 1.65V（正向0~3.3V）
  :WGEN:FUNCtion:SQUare:DCYCle 50 # 50%占空比
  :WGEN:OUTPut ON
  
  # 输出直流电平（偏置调节）
  :WGEN:FUNCtion DC
  :WGEN:VOLTage:OFFSet 2.5        # 2.5V直流
  :WGEN:OUTPut ON
```

---

## 17. 参考波形 :WMEMory

> **功能**: 存储和调用参考波形，用于对比分析

| 指令 | 功能 | 参数 |
|------|------|------|
| `:WMEMory<r>:SAVE` | 保存波形到参考位置 | 源通道 |
| `:WMEMory<r>:DISPlay` | 显示参考波形 | `{0 \| OFF \| 1 \| ON}` |
| `:WMEMory<r>:CLEar` | 清除参考波形 | — |
| `:WMEMory<r>:LABel` | 设置参考波形标签 | 字符串 |
| `:WMEMory<r>:YRANGe` | 参考波形垂直范围 | 电压值 |
| `:WMEMory<r>:YSCALe` | 参考波形每格电压 | 电压值 |
| `:WMEMory<r>:SKEW` | 参考波形时间偏移 | 秒 |

```
参考波形对比（Golden Reference）:
  # 保存当前波形作为参考
  :WMEMory1:SAVE CHANnel2          # 将通道2波形保存到参考1
  
  # 显示参考波形
  :WMEMory1:DISPlay ON
  
  # 设置参考波形标签
  :WMEMory1:LABEL "Golden_Vout"    # 标记为标准输出
  
  # 对比测试: 后续测量波形将叠加显示在参考波形上
```

---

## 18. 程控示例（电源测试应用）

### 18.1 Brown-in / Brown-out 测试完整流程

```python
import visa
import time

class FlybackTest:
    def __init__(self, addr='USB0::0x0957::0x17A4::MY12345678::INSTR'):
        self.rm = visa.ResourceManager()
        self.scope = self.rm.open_resource(addr)
        self.scope.timeout = 15000

    def init_scope(self):
        """示波器初始化"""
        self.scope.write('*RST')                # 恢复出厂设置
        self.scope.write('*CLS')               # 清除错误
        time.sleep(0.5)
        
        # 通道1: 原边电流（分流电阻检测）
        self.scope.write(':CHANnel1:LABEL "Isense"')
        self.scope.write(':CHANnel1:SCALe 0.1')    # 100mV/div
        self.scope.write(':CHANnel1:COUPling DC')
        self.scope.write(':CHANnel1:BANDwidth 20E6')
        
        # 通道2: 输出电压
        self.scope.write(':CHANnel2:LABEL "Vout"')
        self.scope.write(':CHANnel2:SCALe 5')      # 5V/div
        self.scope.write(':CHANnel2:COUPling DC')
        
        # 通道3: Vds
        self.scope.write(':CHANnel3:LABEL "Vds"')
        self.scope.write(':CHANnel3:SCALe 100')    # 100V/div
        self.scope.write(':CHANnel3:COUPling DC')
        
        # 时基: 500us/div（全屏5ms）
        self.scope.write(':TIMebase:SCALe 500E-6')
        
        # 触发: 输出电压上升沿，阈值 2.5V
        self.scope.write(':TRIGger:MODE EDGE')
        self.scope.write(':TRIGger:EDGE:SOURce CHANnel2')
        self.scope.write(':TRIGger:EDGE:LEVel 2.5')
        self.scope.write(':TRIGger:EDGE:SLOPe POS')
        
        # 平均模式降噪
        self.scope.write(':ACQuire:TYPE AVER')
        self.scope.write(':ACQuire:COUNt 64')
        print("示波器初始化完成")

    def measure_brownout(self):
        """Brown-out 测试: 电压跌落响应"""
        self.scope.write(':AUToscale')          # 自动设置
        
        # 触发: Vout 下降沿（brown-out）
        self.scope.write(':TRIGger:EDGE:SLOPe NEG')  # 下降沿
        self.scope.write(':TRIGger:MODE EDGE')
        
        # 采集
        self.scope.write(':DIGitize CHANnel1,CHANnel2,CHANnel3')
        self.scope.write('*OPC?')
        
        # 测量启动恢复时间
        freq = self.scope.query(':MEASure:FREQuency? CHANnel3')
        vpp  = self.scope.query(':MEASure:VPP? CHANnel2')
        rise = self.scope.query(':MEASure:RISetime? CHANnel2')
        
        print(f"Brown-out 响应: 频率={freq}Hz, Vpp={vpp}V, 启动时间={rise}s")
        
        # 保存波形
        self.scope.write(':SAVE:WAVeform:FORMat CSV')
        self.scope.write(':SAVE:WAVeform:SOURce CHANnel2')
        self.scope.write(':SAVE:WAVeform:STARt "\\\\usb\\\\brownout.csv"')
        
        # 保存截图
        self.scope.write(':SAVE:IMAGe:STARt "\\\\usb\\\\brownout.png"')
        
        return {'freq': freq, 'vpp': vpp, 'rise_time': rise}

    def measure_brownin(self):
        """Brown-in 测试: 电压回升恢复"""
        self.scope.write(':TRIGger:MODE EDGE')
        self.scope.write(':TRIGger:EDGE:SLOPe POS')  # 上升沿
        
        self.scope.write(':DIGitize CHANnel1,CHANnel2,CHANnel3')
        self.scope.write('*OPC?')
        
        # 测量上升时间（恢复时间）
        rise = self.scope.query(':MEASure:RISetime? CHANnel2')
        delay = self.scope.query(':MEASure:DELay? CHANnel2,CHANnel3')
        
        print(f"Brown-in 响应: 恢复时间={rise}s, Vout-Vds延迟={delay}s")
        
        return {'rise_time': rise, 'delay': delay}

    def close(self):
        self.scope.close()

# 使用示例
scope = FlybackTest()
scope.init_scope()
scope.measure_brownout()
scope.measure_brownin()
scope.close()
```

### 18.2 MOSFET 开关损耗测试

```python
    def measure_switching_loss(self):
        """测量 MOSFET 开关损耗"""
        # 设置为峰值检测（捕获开关尖峰）
        self.scope.write(':ACQuire:TYPE PEAK')
        
        # 高采样率（观察瞬态）
        self.scope.write(':TIMebase:SCALe 50E-9')   # 50ns/div
        
        # 触发于 Vds 下降沿
        self.scope.write(':TRIGger:MODE EDGE')
        self.scope.write(':TRIGger:EDGE:SOURce CHANnel3')
        self.scope.write(':TRIGger:EDGE:SLOPe NEG')
        self.scope.write(':TRIGger:EDGE:LEVel 50')  # 半压点触发
        
        self.scope.write(':DIGitize CHANnel1,CHANnel3')
        self.scope.write('*OPC?')
        
        # 读取波形数据做积分计算
        self.scope.write(':WAVeform:SOURce CHANnel1')
        self.scope.write(':WAVeform:FORMat BYTE')
        self.scope.write(':WAVeform:POINts:MODE RAW')
        
        # 对 Isense 积分 → 开通能量
        self.scope.write(':FUNCtion:OPERation INTegrate')
        self.scope.write(':FUNCtion:SOURce1 CHANnel1')
        
        print("开关损耗测量完成")

    def save_golden_ref(self):
        """保存Golden参考波形"""
        # 保存当前正常输出波形作为参考
        self.scope.write(':TIMebase:SCALe 1E-3')
        self.scope.write(':ACQuire:TYPE AVER')
        self.scope.write(':ACQuire:COUNt 128')
        self.scope.write(':DIGitize CHANnel2')
        self.scope.write('*OPC?')
        
        self.scope.write(':WMEMory1:SAVE CHANnel2')
        self.scope.write(':WMEMory1:LABEL "Golden_Vout"')
        self.scope.write(':WMEMory1:DISPlay ON')
        print("Golden参考波形已保存")
```

### 18.3 快速状态轮询

```python
    def get_test_status(self):
        """获取示波器当前状态"""
        state  = self.scope.query(':RSTate?')           # 运行状态
        sample = self.scope.query(':ACQuire:SRATe?')    # 采样率
        points = self.scope.query(':ACQuire:POINts?')   # 存储点数
        trig   = self.scope.query(':TRIGger:MODE?')     # 触发模式
        
        return {
            'state': state.strip(),
            'sample_rate': sample.strip(),
            'points': points.strip(),
            'trigger_mode': trig.strip()
        }
```

---

## 附录 A: 命令快速索引（按功能）

### A.1 程控初始化必读

| 指令 | 用途 |
|------|------|
| `*IDN?` | 确认连接正确 |
| `*RST` | 初始化环境 |
| `*CLS` | 清除历史错误 |
| `:SYSTem:ERRor?` | 检查错误队列 |

### A.2 采集相关

| 指令 | 说明 |
|------|------|
| `:DIGitize` | 触发采集 |
| `:RUN` / `:STOP` / `:SINGle` | 运行控制 |
| `:ACQuire:TYPE` | 采集类型 |
| `:ACQuire:COUNt` | 平均次数 |

### A.3 波形读取

| 指令 | 说明 |
|------|------|
| `:WAVeform:SOURce` | 选择通道 |
| `:WAVeform:PREamble?` | 读取参数 |
| `:WAVeform:DATA?` | 读取数据 |

### A.4 自动测量

| 测量对象 | 推荐指令 |
|---------|---------|
| 频率 | `:MEASure:FREQuency` |
| 上升/下降时间 | `:MEASure:RISetime` / `:MEASure:FALLtime` |
| RMS/平均值 | `:MEASure:VRMS` / `:MEASure:VAVerage` |
| 峰峰值 | `:MEASure:VPP` |
| 占空比 | `:MEASure:DUTYcycle` |

### A.5 触发相关

| 场景 | 推荐指令 |
|------|---------|
| 常规捕获 | `:TRIGger:MODE EDGE` |
| 毛刺/异常脉冲 | `:TRIGger:MODE GLITch` |
| 欠幅脉冲 | `:TRIGger:MODE RUNT` |
| 串行协议 | `:TRIGger:MODE SBUS1` |
| 多周期波形 | `:TRIGger:HOLDoff` |

---

## 附录 B: 选件/许可证速查

```
*OPT? 返回字段说明:
  MSO         → 混合信号示波器（带数字通道）
  EMBD        → 嵌入式串行（I2C/SPI）
  AUTO        → 汽车串行（CAN/LIN/FlexRay）
  COMP        → RS-232/UART 串行
  FLEX        → FlexRay 协议
  PWR         → 功率测量应用（DSOX3PWR）
  SGM         → 分段存储
  MASK        → 模板测试
  BW20/BW50   → 带宽升级（100→200MHz / 350→500MHz）
  AUDIO       → I2S 音频协议
  WAVEGEN     → 函数发生器
  AERO        → MIL-STD-1553 / ARINC 429
  VID         → 扩展视频触发
  ADVMATH     → 高级数学运算
  DVM         → 数字电压表
  D3000AUTA   → 汽车软件包
  D3000GENA   → 通用软件包
  D3000AERA   → 航空软件包
  D3000PWRA   → 电源测试软件包
```

---

> **整理说明**: 本文档从 Keysight InfiniiVision 3000X 系列示波器 Programmer's Guide (9018-06894 Rev 02.66.0000) 中提取并分类整理，添加了中文功能注释和电源测试场景示例。原始指令参数请以官方手册为准。
