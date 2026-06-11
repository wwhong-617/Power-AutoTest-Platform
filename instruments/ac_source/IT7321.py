# -*- coding: utf-8 -*-
"""
IT7321 - ITECH IT7300 系列交流源驱动
=====================================

ITECH IT7300 系列交流电源 SCPI 命令参考。
通讯方式：TCPIP / USB

IT7321 与 IT7322 同属 IT7300 系列，命令集完全兼容。
具体型号差异仅在功率等级，驱动接口一致。

SCPI 命令（按设备手册，更新版）
══════════════════════════════════════════════════════

通用
  *IDN?                      查询仪器身份
  *RST                       复位
  *CLS                       清除状态寄存器
  SYST:REM                   进入远程控制模式

输出控制
  OUTP ON | OFF              开启 / 关闭输出
  OUTP?                      查询输出状态 (0=OFF, 1=ON)

电压 & 频率
  SOUR:VOLT <value>          设置输出电压 (V)
  SOUR:VOLT?                  查询输出电压
  SOUR:FREQ <value>          设置输出频率 (Hz)
  SOUR:FREQ?                  查询输出频率
  RANGe HIGH|AUTO            电压电流量程（HIGH=高档位，AUTO=自动）

上下限（限值保护）
  CONF:VOLT:MAX <value>      设置电压上限
  CONF:VOLT:MIN <value>      设置电压下限
  CONF:FREQ:MAX <value>      设置频率上限
  CONF:FREQ:MIN <value>      设置频率下限

保护功能
  CONF:PROT:CURR:RMS <value> 设置过流保护阈值（RMS，有效值）
  CONF:PROT:CURR:RMS?        查询过流保护阈值
  CONF:PROT:CURR:RMS:MODE DELay|IMMediate  过流保护模式
  CONF:PROT:CURR:PEAK <value> 设置峰值过流保护阈值
  CONF:PROT:CURR:PEAK?       查询峰值过流保护阈值
  CONF:PROT:CURR:PEAK:MODE DELay|IMMediate  峰值过流保护模式
  PROTection:CLEar           清除保护状态（需先排除故障）
  STATus:QUEStionable:CONDition?  查询保护状态寄存器

测量
  MEAS:VOLT?                 测量输出电压 (V)
  MEAS:CURR?                 测量输出电流 (A)
  MEAS:POW?                  测量有功功率 (W)

LIST 序列
  LIST:STATe DISable|ENABle  LIST 模式开关
  LIST:STEP:COUNt <n>        设置 LIST 步数（1~100）
  LIST:STEP:VOLT <idx>,<val> 设置第 idx 步电压 (V)
  LIST:STEP:FREQ <idx>,<val> 设置第 idx 步频率 (Hz)
  LIST:STEP:DWEL <idx>,<val> 设置第 idx 步持续时间 (s)
  LIST:STEP:COUNt?           查询步数
  LIST:STEP:VOLT? <idx>      查询第 idx 步电压
  LIST:STEP:FREQ? <idx>      查询第 idx 步频率
  LIST:STEP:DWEL? <idx>      查询第 idx 步持续时间
  LIST:REPeat <n>            设置重复次数（1~10000）
  LIST:REPeat?               查询重复次数

状态寄存器
  *ESR?                      标准事件状态寄存器
  STATus:QUEStionable:CONDition?  查询条件寄存器
  STATus:QUEStionable:EVENt?     查询事件寄存器（读后清零）
"""

import time
from .BaseACSource import BaseACSource


class IT7321(BaseACSource):
    """
    ITECH IT7321 交流源驱动。
    继承 BaseACSource，实现 IT7321 专用 SCPI 命令。
    IT7321 与 IT7322 同属 IT7300 系列，命令集完全兼容。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)
        self._model = "IT7321"

    # ================================================================
    #  私有工具
    # ================================================================

    def _send_initial_commands(self):
        """
        轻量化初始化：*RST + *CLS + SYST:REM。
        """
        self.send_command("*RST", check_esr=False)
        time.sleep(0.5)
        self.send_command("*CLS", check_esr=False)
        self.send_command("SYST:REM")

    def _validate_identity(self) -> bool:
        """验证仪器身份。"""
        if any(x in self._idn for x in ["IT7321", "IT7300", "ITECH", "SIMULATION"]):
            return True
        return False

    # ================================================================
    #  1. 初始化
    # ================================================================

    def initialize(self):
        """
        完整初始化：调用轻量化重置 + 电流量程设为 HIGH。
        """
        self._send_initial_commands()
        self.set_ac_source_range("HIGH")

    # ================================================================
    #  2. 开机 / 关机
    # ================================================================

    def output_on(self):
        """开启输出。"""
        self.send_command("OUTP ON", check_esr=False)

    def output_off(self):
        """关闭输出。"""
        self.send_command("OUTP OFF", check_esr=False)

    # ================================================================
    #  3. 电压 & 频率
    # ================================================================

    def set_voltage(self, volts: float):
        """设置输出电压 (V)。"""
        self.send_command(f"SOUR:VOLT {volts}")

    def set_voltage_nowait(self, volts: float):
        """
        设置输出电压（不等 ESR，立即返回）。
        仅写入命令，不做状态寄存器校验，适用于高速扫描场景。
        """
        self._resource.write(f"SOUR:VOLT {volts}")

    def set_ac_source_range(self, range_mode: str):
        """
        设置交流源档位。

        Args:
            range_mode: "HIGH" = 高档位，"AUTO" = 自动档位
        """
        mode = range_mode.upper()
        if mode not in ("HIGH", "AUTO"):
            return
        self.send_command(f"RANGe {mode}")

    def set_voltage_range(self, range_mode: str):
        """
        IT7321 为全范围线性源，不支持独立电压档位切换，此方法为空操作。
        """
        pass

    def set_frequency(self, hz: float):
        """设置输出频率 (Hz)。"""
        self.send_command(f"SOUR:FREQ {hz}")

    def set_frequency_nowait(self, hz: float):
        """
        设置输出频率（不等 ESR，立即返回）。
        仅写入命令，不做状态寄存器校验，适用于高速扫描场景。
        """
        self._resource.write(f"SOUR:FREQ {hz}")

    def measure_voltage(self) -> float:
        """测量输出电压 (V)。"""
        if not self._connected:
            return 0.0
        try:
            return float(self.query("MEAS:VOLT?"))
        except Exception:
            return 0.0

    def measure_current(self) -> float:
        """测量输出电流 (A)。"""
        if not self._connected:
            return 0.0
        try:
            return float(self.query("MEAS:CURR?"))
        except Exception:
            return 0.0

    def measure_power(self) -> float:
        """测量有功功率 (W)。"""
        if not self._connected:
            return 0.0
        try:
            return float(self.query("MEAS:POW?"))
        except Exception:
            return 0.0

    # ================================================================
    #  4. LIST 序列
    # ================================================================

    def program_list(self, steps, cycles: int = 1):
        """
        编程 LIST 序列（List 模式）。

        IT7300 LIST 命令格式（按手册）：
          LIST:STEP:COUNt <n>    — 设置总步数
          LIST:STEP:VOLT <idx>,<val> — 第 idx 步电压
          LIST:STEP:FREQ <idx>,<val> — 第 idx 步频率
          LIST:STEP:DWEL <idx>,<val> — 第 idx 步持续时间 (s)
          LIST:REPeat <n>        — 重复次数

        Args:
            steps:  序列列表，每项 (电压, 频率, 持续时间秒)
                    示例: [(220, 50, 10), (110, 60, 5)]
            cycles: 重复次数（默认 1 次）
        """
        if not steps:
            return

        # 关闭 LIST 模式（安全）
        self.send_command("LIST:STAT DIS", check_esr=False)

        # 设置总步数
        n = len(steps)
        self.send_command(f"LIST:STEP:COUN {n}", check_esr=False)

        # 逐步写入
        for idx, (v, f, d) in enumerate(steps):
            self.send_command(f"LIST:STEP:VOLT {idx},{v}", check_esr=False)
            self.send_command(f"LIST:STEP:FREQ {idx},{f}", check_esr=False)
            self.send_command(f"LIST:STEP:DWEL {idx},{d}", check_esr=False)

        # 设置重复次数
        self.send_command(f"LIST:REP {cycles}", check_esr=False)

    def run_list(self, progress_callback=None):
        """
        启动已编程的 LIST 序列。

        Args:
            progress_callback: callback(step_index, total_steps, cycle, total_cycles)
        """
        self._stop_flag = False

        # 启用 LIST 模式并开启输出
        self.send_command("LIST:STAT ENAB", check_esr=False)
        self.output_on()

        # 轮询进度（注：IT7300 LIST 由硬件控制时序，软件轮询仅供参考）
        if progress_callback:
            try:
                total_steps = int(self.query("LIST:STEP:COUN?").strip())
                cycles_val  = int(self.query("LIST:REP?").strip())
                for cycle in range(1, cycles_val + 1):
                    for step_idx in range(total_steps):
                        if self._stop_flag:
                            break
                        progress_callback(step_idx, total_steps, cycle, cycles_val)
                        time.sleep(1.0)
            except Exception:
                pass

    def stop(self):
        """停止 LIST 序列并关闭输出。"""
        self._stop_flag = True
        try:
            self.send_command("LIST:STAT DIS", check_esr=False)
            self.output_off()
        except Exception:
            pass

    def input_transient(self, steps, cycles: int = 1, progress_callback=None):
        """
        输入跳变测试（电压阶跃 / 暂态切换）。

        IT7300 实现：使用 LIST 模式。
        steps 格式 (start_v, end_v, duration_s) 展开为两个 LIST 点：
          - (start_v, duration_s)
          - (end_v,   duration_s)

        Args:
            steps:  跳变序列，每项 (起始电压, 目标电压, 持续时间秒)
                    示例: [(220, 180, 1.0), (180, 220, 1.0)]
            cycles: 重复次数（默认 1 次）
            progress_callback: callback(step, total_steps, cycle, total_cycles)
        """
        if not steps:
            return

        list_steps = []
        for start_v, end_v, duration_s in steps:
            list_steps.append((start_v, 50.0, duration_s))
            list_steps.append((end_v,   50.0, duration_s))

        self.program_list(list_steps, cycles=cycles)
        self.run_list(progress_callback=progress_callback)

    def repeated_on_off(self, volts: float, hz: float,
                        on_time_s: float, off_time_s: float,
                        cycles: int = 1,
                        progress_callback=None):
        """
        反复开关机操作。

        Args:
            volts:      输出电压（V）
            hz:         输出频率（Hz）
            on_time_s:  每次开机维持时间（秒）
            off_time_s: 每次关机维持时间（秒）
            cycles:     开关次数
            progress_callback: callback(current_cycle, total_cycles, state)
        """
        self._stop_flag = False
        self.set_voltage(volts)
        self.set_frequency(hz)

        for i in range(1, cycles + 1):
            if self._stop_flag:
                break
            self.output_on()
            if progress_callback:
                progress_callback(i, cycles, "on")
            time.sleep(on_time_s)

            if self._stop_flag:
                break
            self.output_off()
            if progress_callback:
                progress_callback(i, cycles, "off")
            if i < cycles:
                time.sleep(off_time_s)

    # ================================================================
    #  5. 保护功能（IT7321 支持）
    # ================================================================

    def set_overvoltage_protection(self, volts: float, enabled: bool = True):
        """
        设置过压保护 (OVP) 阈值。

        IT7321 不支持独立 OVP 命令，使用电压上限 CONF:VOLT:MAX 作为限值。

        Args:
            volts:   OVP 阈值 (V)
            enabled: True = 开启，False = 关闭
        """
        self.send_command(f"CONF:VOLT:MAX {volts}", check_esr=False)

    def set_overcurrent_protection(self, amps: float, enabled: bool = True):
        """
        设置过流保护 (OCP) 阈值（RMS 有效值）。

        IT7300 命令：CONF:PROT:CURR:RMS

        Args:
            amps:    OCP 阈值 (A)
            enabled: True = 开启（IMMediate 模式），False = 关闭
        """
        self.send_command(f"CONF:PROT:CURR:RMS {amps}", check_esr=False)
        if enabled:
            self.send_command("CONF:PROT:CURR:RMS:MODE IMMEDIATE", check_esr=False)
        else:
            self.send_command("CONF:PROT:CURR:RMS:MODE DELAY", check_esr=False)

    def set_overpower_protection(self, watts: float, enabled: bool = True):
        """
        设置过功率保护 (OPP)。

        IT7321 不支持独立 OPP 命令，此方法仅记录配置，不执行实际操作。
        """
        pass

    def get_protection_status(self) -> dict:
        """
        查询当前保护状态。

        IT7300 保护状态寄存器 STATus:QUEStionable:CONDition?：
          bit0=OCP RMS, bit1=OCP PEAK, bit2=OVP, bit3=OPP, bit4=OTP, bit5=foldback

        Returns:
            dict: {
                "ovp":  bool,   过压保护是否触发
                "ocp":  bool,   过流保护是否触发
                "opp":  bool,   过功率保护是否触发
                "trip": bool,   是否处于保护跳脱状态
            }
        """
        if not self._connected:
            return {"ovp": False, "ocp": False, "opp": False, "trip": False}
        try:
            resp = self.query("STAT:QUES:COND?")
            val = int(resp.strip())
            return {
                "ovp":  bool(val & 0b00100),   # bit2
                "ocp":  bool(val & 0b00011),   # bit0=RMS, bit1=PEAK
                "opp":  bool(val & 0b01000),   # bit3
                "trip": bool(val & 0b11111),   # 任意保护触发
            }
        except Exception:
            return {"ovp": False, "ocp": False, "opp": False, "trip": False}

    def set_max_voltage_limit(self, volts: float):
        """
        设置最大输出电压限制 (V)。

        IT7300 命令：CONF:VOLTage:MAXimum
        """
        self.send_command(f"CONF:VOLT:MAX {volts}", check_esr=False)

    def set_max_current_limit(self, amps: float):
        """
        设置最大输出电流限制 (A)。

        IT7321 不支持独立电流限值命令，使用过流保护 CONF:PROT:CURR:RMS 代替。
        """
        self.send_command(f"CONF:PROT:CURR:RMS {amps}", check_esr=False)

    def clear_protection_alarm(self):
        """清除保护告警，恢复正常运行状态。"""
        self.send_command("*CLS", check_esr=False)
        time.sleep(0.1)
        self.send_command("PROTection:CLEar", check_esr=False)
