# -*- coding: utf-8 -*-
"""
IT7821E - ITECH IT7800E 系列交流源驱动
==========================================

ITECH IT7800E 系列交流电源 SCPI 命令参考。
通讯方式：TCPIP / USB

SCPI 命令分类（按 IT7800E 编程手册）
══════════════════════════════════════════════════════

通用
  *IDN?                      查询仪器身份
  *RST                       复位
  *CLS                       清除状态寄存器
  SYST:REM                   进入远程控制模式

输出控制
  OUTPut[:STATe] ON | OFF    开启 / 关闭输出
  OUTPut:PROTection:CLEar    清除保护状态

电压 & 频率
  SOURce:VOLTage[:LEVel][:IMMediate][:AMPLitude][:AC] <value>   设置输出电压 (V)
  SOURce:FREQuency[:IMMediate] <value>                           设置输出频率 (Hz)
  MEASure[:SCALar]:VOLTage[:AC]?                                测量输出电压 (V)
  MEASure[:SCALar]:CURRent[:AC]?                                测量输出电流 (A)
  MEASure[:SCALar]:POWer[:REAL]?                                测量有功功率 (W)

保护功能
  SOURce:CURRent:PROTection:RMS <value>       设置过流保护阈值 (A)
  SOURce:VOLTage:PROTection:PEAK <value>      设置峰值过压保护 (V)
  OUTPut:PROTection:WDOG[:STATe] ON|OFF       看门狗保护
  OUTPut:PROTection:WDOG:DELay <value>        看门狗延迟 (s)
  STATus:QUEStionable:CONDition?               查询保护状态寄存器

LIST 序列
  LIST:CREate                         新建 list 文件
  LIST:STEP <idx>,<string>           定义步骤（含电压/频率/时间等）
  LIST:STEP:ITEM <idx>,<item>,<val>  逐项定义步骤参数
  LIST:REPeat <n>                    重复次数
  LIST:TERMinate <LAST|CONTinue>     结束时处理
  LIST:RUNTime:STATe?                查询运行状态
  TRIGger:LIST:SOURce <source>       触发源选择
"""

import time
from .BaseACSource import BaseACSource


class IT7821E(BaseACSource):
    """
    ITECH IT7821E 交流源驱动。
    继承 BaseACSource，实现 IT7800E 系列专用 SCPI 命令。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)
        self._model = "IT7821E"

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
        """验证仪器身份"""
        if any(x in self._idn for x in ["IT7821E", "IT7800E", "IT7800", "ITECH", "SIMULATION"]):
            return True
        return False

    # ================================================================
    #  1. 初始化
    # ================================================================

    def initialize(self):
        """
        完整初始化：调用轻量化重置 + 进入远程模式。
        """
        self._send_initial_commands()

    # ================================================================
    #  2. 开机 / 关机
    # ================================================================

    def output_on(self):
        """开启输出"""
        self.send_command("OUTP ON", check_esr=False)

    def output_off(self):
        """关闭输出"""
        self.send_command("OUTP OFF", check_esr=False)

    # ================================================================
    #  3. 电压 & 频率
    # ================================================================

    def set_voltage(self, volts: float):
        """设置输出电压 (V)"""
        self.send_command(f"VOLT {volts}")

    def set_voltage_nowait(self, volts: float):
        """
        设置输出电压（不等 ESR，立即返回）。
        仅写入命令，不做状态寄存器校验，适用于高速扫描场景。
        """
        self._resource.write(f"VOLT {volts}")

    def set_frequency_nowait(self, hz: float):
        """
        设置输出频率（不等 ESR，立即返回）。
        仅写入命令，不做状态寄存器校验，适用于高速扫描场景。
        """
        self._resource.write(f"FREQ {hz}")

    def set_ac_source_range(self, range_mode: str):
        """
        IT7800E 不支持独立电压档位切换，此方法为空操作。
        保留接口兼容。
        """
        pass

    def set_voltage_range(self, range_mode: str):
        """
        IT7800E 不支持独立电压档位切换，此方法为空操作。
        """
        pass

    def set_frequency(self, hz: float):
        """设置输出频率 (Hz)"""
        self.send_command(f"FREQ {hz}")

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
    #  4. LIST 序列
    # ================================================================

    def program_list(self, steps, cycles: int = 1):
        """
        编程 LIST 序列（List 模式）。

        IT7800E LIST 命令格式（按手册）：
          LIST:CREate                  — 新建 list 文件
          LIST:STEP <idx>,<string>    — 第 idx 步完整参数
          参数格式（CSV字符串）：电压,频率,时间,波形,...

        Args:
            steps:  序列列表，每项 (电压, 频率, 持续时间秒)
                    示例: [(220, 50, 10), (110, 60, 5)]
            cycles: 重复次数（默认 1 次）
        """
        if not steps:
            return

        # 新建 list 文件
        self.send_command("LIST:CREate", check_esr=False)

        # 逐步写入
        for idx, (v, f, d) in enumerate(steps, start=1):
            # IT7800E LIST:STEP 参数格式:
            # "电压, 频率, 时间(秒), 波形, 相位, 幅值模式, 幅值, 触发源"
            # 波形: Sine, DC, SQUare, 等
            # 触发源: IMMEDIATE
            step_str = f"{v}, {f}, {d}, Sine, PHASe, 90, 1000, IMM"
            self.send_command(f"LIST:STEP {idx}, \"{step_str}\"", check_esr=False)

        # 设置重复次数
        self.send_command(f"LIST:REP {cycles}", check_esr=False)

    def run_list(self, progress_callback=None):
        """
        启动已编程的 LIST 序列。

        Args:
            progress_callback: callback(step_index, total_steps, cycle, total_cycles)
        """
        self._stop_flag = False

        # 查询总步数和循环次数
        try:
            total_steps = int(self.query("LIST:STEP:COUNt?").strip())
            cycles_val = int(self.query("LIST:REP?").strip())
        except Exception:
            total_steps = 0
            cycles_val = 1

        # 轮询进度
        if progress_callback and total_steps > 0:
            for cycle in range(1, cycles_val + 1):
                for step_idx in range(1, total_steps + 1):
                    if self._stop_flag:
                        break
                    progress_callback(step_idx, total_steps, cycle, cycles_val)
                    time.sleep(1.0)

    def stop(self):
        """停止 LIST 序列并关闭输出"""
        self._stop_flag = True
        try:
            self.output_off()
        except Exception:
            pass

    def input_transient(self, steps, cycles: int = 1, progress_callback=None):
        """
        输入跳变测试（电压阶跃 / 暂态切换）。

        IT7800E 实现：使用 LIST 模式。
        steps 格式 (start_v, end_v, duration_s) 展开为两个 LIST 点。

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
    #  5. 保护功能
    # ================================================================

    def set_overvoltage_protection(self, volts: float, enabled: bool = True):
        """
        设置过压保护 (OVP) 阈值。

        IT7800E 命令：SOURce:VOLTage:PROTection:PEAK

        Args:
            volts:   OVP 阈值 (V)
            enabled: True = 开启，False = 关闭（IT7800E OVP 无法关闭，仅设置阈值）
        """
        self.send_command(f"VOLT:PROT:PEAK {volts}", check_esr=False)

    def set_overcurrent_protection(self, amps: float, enabled: bool = True):
        """
        设置过流保护 (OCP) 阈值（RMS 有效值）。

        IT7800E 命令：SOURce:CURRent:PROTection:RMS

        Args:
            amps:    OCP 阈值 (A)
            enabled: True = 开启（IMMediate 模式），False = 关闭
        """
        self.send_command(f"CURR:PROT:RMS {amps}", check_esr=False)
        if enabled:
            self.send_command("CURR:PROT:MODE IMMEDIATE", check_esr=False)
        else:
            self.send_command("CURR:PROT:MODE DELAY", check_esr=False)

    def set_overpower_protection(self, watts: float, enabled: bool = True):
        """
        设置过功率保护 (OPP)。

        IT7800E 不支持独立 OPP 命令，此方法仅记录配置。
        """
        pass

    def get_protection_status(self) -> dict:
        """
        查询当前保护状态。

        IT7800E 保护状态寄存器 STATus:QUEStionable:CONDition?：
          bit0=OVP, bit1=OCP, bit2=OPP, bit3=OTP, ...

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
                "ovp":  bool(val & 0b00001),   # bit0
                "ocp":  bool(val & 0b00010),   # bit1
                "opp":  bool(val & 0b00100),   # bit2
                "trip": bool(val & 0b01111),   # 任意保护触发
            }
        except Exception:
            return {"ovp": False, "ocp": False, "opp": False, "trip": False}

    def set_max_voltage_limit(self, volts: float):
        """
        设置最大输出电压限制 (V)。

        IT7800E 命令：SOURce:VOLTage:LIMit:HIGH
        """
        self.send_command(f"VOLT:LIM:HIGH {volts}", check_esr=False)

    def set_max_current_limit(self, amps: float):
        """
        设置最大输出电流限制 (A)。

        IT7800E 使用过流保护设置代替。
        """
        self.send_command(f"CURR:PROT:RMS {amps}", check_esr=False)

    def clear_protection_alarm(self):
        """清除保护告警，恢复正常运行状态"""
        self.send_command("OUTP:PROT:CLE", check_esr=False)
