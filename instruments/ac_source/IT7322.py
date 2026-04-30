# -*- coding: utf-8 -*-
"""
IT7322 - ITECH IT7300 系列交流源驱动
=====================================

ITECH IT7300 系列交流电源 SCPI 命令参考。
通讯方式：TCPIP / USB

SCPI 命令分类
══════════════════════════════════════════════════════

初始化
  *IDN?                      查询仪器身份
  *RST                       复位
  *CLS                       清除状态寄存器
  SYST:REM                   进入远程控制模式

开机 / 关机
  OUTP ON                    开启输出
  OUTP OFF                   关闭输出

电压 & 频率
  SOUR:VOLT <value>          设置输出电压 (V)
  SOUR:FREQ <value>          设置输出频率 (Hz)
  [SOURce:]RANGe HIGH|AUTO   设置源档位（HIGH=高档位，AUTO=自动）
  MEAS:VOLT?                 测量输出电压 (V)
  MEAS:CURR?                 测量输出电流 (A)
  MEAS:POW?                  测量有功功率 (W)

序列功能（List 模式）
  LIST:POIN <n>              设置列表点数
  LIST:VOLT <v1>,<v2>,...   电压序列
  LIST:FREQ <f1>,<f2>,...   频率序列
  LIST:DWEL <t1>,<t2>,...   每步持续时间 (s)
  LIST:COUN <n>              重复次数
  SOUR:FUNC:MODE LIST        选择列表模式
  SOUR:TRIG:SOUR IMM         触发源：立即
  LIST:STEP <n>              每步采样点数（可选）
  SOUR:FUNC:MODE FIXED       恢复固定模式

保护功能
  OUTP:PROT:VOLT <value>     设置 OVP 阈值 (V)
  OUTP:PROT:VOLT:STAT ON/OFF OVP 使能
  OUTP:PROT:CURR <value>     设置 OCP 阈值 (A)
  OUTP:PROT:CURR:STAT ON/OFF OCP 使能
  OUTP:PROT:POW <value>      设置 OPP 阈值 (W)
  OUTP:PROT:POW:STAT ON/OFF OPP 使能
  OUTP:PROT:STAT?            查询保护状态
  OUTP:PROT:CLE              清除保护告警

状态查询
  STAT:OPER?                 查询工作状态寄存器
"""

import time
from .BaseACSource import BaseACSource


class IT7322(BaseACSource):
    """
    ITECH IT7322 交流源驱动。
    继承 BaseACSource，实现 IT7322 专用 SCPI 命令。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)
        self._model = "IT7322"

    # ================================================================
    #  私有工具
    # ================================================================

    def _send_initial_commands(self):
        """发送初始化命令"""
        self.send_command("*CLS", check_esr=False)
        self.send_command("SYST:REM")

    def _validate_identity(self) -> bool:
        """验证仪器身份"""
        if any(x in self._idn for x in ["IT7322", "IT7300", "ITECH", "SIMULATION"]):
            return True
        return False

    # ================================================================
    #  1. 初始化
    # ================================================================

    def initialize(self):
        """
        交流源初始化：*RST 复位 → *CLS 清除状态 → SYST:REM 进入远程 → 电流量程设为 HIGH。

        IT7322 为全范围线性源，0~300V 直接输出，无需电压档位切换。
        电流量程默认设为 HIGH 档位，以支持较大电流输出。
        """
        self.send_command("*RST")
        time.sleep(0.5)
        self.send_command("*CLS", check_esr=False)
        self.send_command("SYST:REM")
        self.set_ac_source_range("HIGH")

    # ================================================================
    #  2. 开机 / 关机
    def set_ac_source_range(self, range_mode: str):
        """
        设置交流源档位。

        Args:
            range_mode: "HIGH" = 高档位，"AUTO" = 自动档位

        IT7300 系列命令：[SOURce:]RANGe HIGH|AUTO
        - HIGH：  高档位，适用较大功率/电流输出
        - AUTO：  自动档位，仪器根据负载自动选择合适档位
        """
        mode = range_mode.upper()
        if mode not in ("HIGH", "AUTO"):
            return
        self.send_command(f"RANGe {mode}")

    def set_voltage_range(self, range_mode: str):
        """
        设置输出电压档位（量程）。

        IT7322 为全范围线性源，不支持电压档位切换，此方法为空操作。
        """
        pass

    # ================================================================

    def output_on(self):
        """开启输出"""
        self.send_command("OUTP ON")

    def output_off(self):
        """关闭输出"""
        self.send_command("OUTP OFF")

    # ================================================================
    #  3. 电压 & 频率
    # ================================================================

    def set_voltage(self, volts: float):
        """设置输出电压 (V)"""
        self.send_command(f"SOUR:VOLT {volts}")

    def set_frequency(self, hz: float):
        """设置输出频率 (Hz)"""
        self.send_command(f"SOUR:FREQ {hz}")

    def measure_voltage(self) -> float:
        """测量输出电压 (V)"""
        if not self._connected:
            return 0.0
        try:
            return float(self.query("MEAS:VOLT?"))
        except Exception:
            return 0.0

    def measure_current(self) -> float:
        """测量输出电流 (A)"""
        if not self._connected:
            return 0.0
        try:
            return float(self.query("MEAS:CURR?"))
        except Exception:
            return 0.0

    def measure_power(self) -> float:
        """测量有功功率 (W)"""
        if not self._connected:
            return 0.0
        try:
            return float(self.query("MEAS:POW?"))
        except Exception:
            return 0.0

    # ================================================================
    #  4. 序列功能
    # ================================================================

    def program_list(self, steps, cycles: int = 1):
        """
        编程列表序列（List 模式）。

        Args:
            steps:  序列列表，每项 (电压, 频率, 持续时间秒)
                    示例: [(220, 50, 10), (110, 60, 5)]
            cycles: 重复次数（默认 1 次）
        """
        if not steps:
            return
        n = len(steps)
        voltages  = ",".join(str(s[0]) for s in steps)
        freqs    = ",".join(str(s[1]) for s in steps)
        dwell    = ",".join(str(s[2]) for s in steps)

        self.send_command(f"LIST:POIN {n}")
        self.send_command(f"LIST:VOLT {voltages}")
        self.send_command(f"LIST:FREQ {freqs}")
        self.send_command(f"LIST:DWEL {dwell}")
        self.send_command(f"LIST:COUN {cycles}")
        self.send_command("SOUR:FUNC:MODE LIST")

    def run_list(self, progress_callback=None):
        """
        启动已编程的列表序列。

        Args:
            progress_callback: callback(step_index, total_steps, cycle, total_cycles)
        """
        self._stop_flag = False
        self.send_command("SOUR:TRIG:SOUR IMM")
        self.output_on()

        # 等待序列执行完毕（IT7300 列表模式由硬件控制时序）
        # 这里轮询等待，用于回调进度
        # 注：列表总时长 = sum(dwell_times) * cycles
        if progress_callback:
            # 简单实现：每秒回调一次
            total_steps = int(self.query("LIST:POIN?").strip())
            cycles_val  = int(self.query("LIST:COUN?").strip())
            for cycle in range(1, cycles_val + 1):
                for step_idx in range(1, total_steps + 1):
                    if self._stop_flag:
                        break
                    progress_callback(step_idx, total_steps, cycle, cycles_val)
                    time.sleep(1.0)

    def stop(self):
        """
        停止当前正在执行的列表序列或反复开关机操作。
        """
        self._stop_flag = True
        try:
            self.output_off()
            self.send_command("SOUR:FUNC:MODE FIXED")
        except Exception:
            pass

    def input_transient(self, steps, cycles: int = 1, progress_callback=None):
        """
        输入跳变测试（电压阶跃 / 暂态切换）。

        IT7300 实现：使用 LIST 模式实现跳变序列。
        steps 格式 (start_v, end_v, duration_s) 展开为两个列表点：
          - (start_v, duration_s)：维持在起始电压
          - (end_v,   duration_s)：跳变至目标电压后再维持
        这意味着一次完整的跳变占 2 个列表点。

        Args:
            steps:  跳变序列，每项 (起始电压, 目标电压, 持续时间秒)
                    示例: [(220, 180, 1.0), (180, 220, 1.0)]
                    → 等效于：220V维持1s → 跳变到180V维持1s → 跳变回220V维持1s
            cycles: 重复次数（默认 1 次）
            progress_callback: callback(step_index, total_steps, cycle, total_cycles)
        """
        if not steps:
            return

        # 将 (start_v, end_v, duration_s) 展开为 IT7300 LIST 格式 (voltage, freq, dwell)
        # 跳变本身是瞬态的（由仪器内部 slew rate 决定），持续时间体现在两端的维持阶段
        list_steps = []
        for start_v, end_v, duration_s in steps:
            # 起始电压维持 duration_s
            list_steps.append((start_v, duration_s))
            # 目标电压立即跳变，然后维持 duration_s
            list_steps.append((end_v,   duration_s))

        # 转换为 program_list 需要的 (voltage, freq, dwell) 格式
        # 频率使用当前设定值（IT7300 LIST 每个点可独立设频率，这里统一用 50Hz）
        prog_steps = [(v, 50.0, d) for v, d in list_steps]
        self.program_list(prog_steps, cycles=cycles)
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
    #  5. 保护功能
    # ================================================================

    def set_overvoltage_protection(self, volts: float, enabled: bool = True):
        """
        设置过压保护 (OVP) 阈值。

        Args:
            volts:   OVP 阈值 (V)
            enabled: True = 开启，False = 关闭
        """
        self.send_command(f"OUTP:PROT:VOLT {volts}")
        self.send_command("OUTP:PROT:VOLT:STAT ON" if enabled else "OUTP:PROT:VOLT:STAT OFF")

    def set_overcurrent_protection(self, amps: float, enabled: bool = True):
        """
        设置过流保护 (OCP) 阈值。

        Args:
            amps:    OCP 阈值 (A)
            enabled: True = 开启，False = 关闭
        """
        self.send_command(f"OUTP:PROT:CURR {amps}")
        self.send_command("OUTP:PROT:CURR:STAT ON" if enabled else "OUTP:PROT:CURR:STAT OFF")

    def set_overpower_protection(self, watts: float, enabled: bool = True):
        """
        设置过功率保护 (OPP) 阈值。

        Args:
            watts:   OPP 阈值 (W)
            enabled: True = 开启，False = 关闭
        """
        self.send_command(f"OUTP:PROT:POW {watts}")
        self.send_command("OUTP:PROT:POW:STAT ON" if enabled else "OUTP:PROT:POW:STAT OFF")

    def get_protection_status(self) -> dict:
        """
        查询当前保护状态。

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
            resp = self.query("OUTP:PROT:STAT?")
            # 返回值格式：bit0=OVP, bit1=OCP, bit2=OPP, bit4=trip
            val = int(resp.strip())
            return {
                "ovp":  bool(val & 0b0001),
                "ocp":  bool(val & 0b0010),
                "opp":  bool(val & 0b0100),
                "trip": bool(val & 0b1000),
            }
        except Exception:
            return {"ovp": False, "ocp": False, "opp": False, "trip": False}

    def set_max_voltage_limit(self, volts: float):
        """
        设置最大输出电压限制 (V)。
        IT7300 系列命令：SOUR:VOLT:LIM <value>
        """
        self.send_command(f"SOUR:VOLT:LIM {volts}")

    def set_max_current_limit(self, amps: float):
        """
        设置最大输出电流限制 (A)。
        IT7300 系列命令：SOUR:CURR:LIM <value>
        """
        self.send_command(f"SOUR:CURR:LIM {amps}")

    def clear_protection_alarm(self):
        """清除保护告警，恢复正常运行状态"""
        self.send_command("OUTP:PROT:CLE")
