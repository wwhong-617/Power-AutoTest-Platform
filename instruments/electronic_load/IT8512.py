# -*- coding: utf-8 -*-
"""
IT8512 - ITECH IT8500 系列电子负载驱动
========================================

ITECH IT8512+ 系列电子负载驱动。
通讯方式：TCPIP / USB

IT8512 与 IT8511 同属 IT8500 系列，命令集完全兼容。
具体型号差异仅在功率等级，驱动接口一致。

SCPI 命令分类（与 IT8511 相同）
══════════════════════════════════════════════════════

初始化
  *IDN? / *RST / *CLS / SYST:REM

负载 ON/OFF
  :SOUR:INP ON/OFF            负载输入开关
  :SOUR:FUNC <mode>          模式：CC / CV / CR / CP
  :SOUR:CURR <value>          电流 (A)
  :SOUR:VOLT <value>          电压 (V)
  :SOUR:RES <value>           电阻 (Ω)
  :SOUR:POW <value>           功率 (W)
  :SOUR:CURR:SLOPE <value>   电流斜率 (A/s)
  :SOUR:CURR:PROT ON         电流保护

短路
  :SOUR:INP:SHOR <bool>     短路开/关

动态模式（CC-Dynamic）
  :SOUR:FUNC DYN              进入动态模式
  :SOUR:DYN:IH <val>         高电流 (A)
  :SOUR:DYN:IL <val>         低电流 (A)
  :SOUR:DYN:FREQ <val>       频率 (Hz)
  :SOUR:DYN:RISE <val>       上升时间 (s)
  :SOUR:DYN:FALL <val>       下降时间 (s)
  :SOUR:FUNC:MODE DYN

LIST 模式
  :SOUR:FUNC:MODE LIST
  :LIST:POIN <n> / :LIST:CC|CV|CR|CP <vals>
  :LIST:DWEL <vals> / :LIST:COUN <n>
  :SOUR:TRIG:SOUR IMM
  :SOUR:FUNC:MODE FIXED

负载扫描（CC-Sweep）
  :SOUR:FUNC SWEEP
  :SOUR:SWE:STAR/STOP/STEP/DWEL/COUN/SLOPE <val>
  :SOUR:TRIG:SOUR IMM

测量
  :MEAS:VOLT?                 电压 (V)
  :MEAS:CURR?                 电流 (A)
"""

import time
from typing import Optional
from .BaseElectronicLoad import BaseElectronicLoad, LoadMode


class IT8512(BaseElectronicLoad):
    """
    ITECH IT8512+ 电子负载驱动。
    继承 BaseElectronicLoad，实现 IT8500 系列专用 SCPI 命令。
    IT8512 与 IT8511 命令集完全兼容。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)
        self._model = "IT8512+"
        self._stop_flag = False

    # ================================================================
    #  私有工具
    # ================================================================

    def _send_initial_commands(self):
        self.send_command("*CLS", check_esr=False)
        self.send_command("SYST:REM")

    def _validate_identity(self) -> bool:
        if any(x in self._idn for x in ["IT8512", "IT8500", "ITECH", "SIMULATION"]):
            return True
        return False

    # ================================================================
    #  1. 初始化
    # ================================================================

    def initialize(self):
        """电子负载初始化：*RST → *CLS → SYST:REM"""
        self.send_command("*RST")
        time.sleep(0.5)
        self.send_command("*CLS", check_esr=False)
        self.send_command("SYST:REM")

    # ================================================================
    #  2. 负载 ON / OFF
    # ================================================================

    def set_mode_cc(self, current: float, slew_rate: float = None):
        """设置恒流模式 (CC)"""
        self.send_command(":SOUR:FUNC CC")
        self.send_command(f":SOUR:CURR {current}")
        self.send_command(":SOUR:CURR:PROT ON")
        if slew_rate is not None:
            self.send_command(f":SOUR:CURR:SLOPE {slew_rate}")
        self._current_mode = LoadMode.CC

    def set_mode_cv(self, voltage: float):
        """设置恒压模式 (CV)"""
        self.send_command(":SOUR:FUNC CV")
        self.send_command(f":SOUR:VOLT {voltage}")
        self._current_mode = LoadMode.CV

    def set_mode_cr(self, resistance: float):
        """设置恒阻模式 (CR)"""
        self.send_command(":SOUR:FUNC CR")
        self.send_command(f":SOUR:RES {resistance}")
        self._current_mode = LoadMode.CR

    def set_mode_cp(self, power: float):
        """设置恒功模式 (CP)"""
        self.send_command(":SOUR:FUNC CP")
        self.send_command(f":SOUR:POW {power}")
        self._current_mode = LoadMode.CP

    def set_load_slew_rate(self, rate: float):
        """设置负载电流斜率 (A/s)"""
        self.send_command(f":SOUR:CURR:SLOPE {rate}")

    def input_on(self):
        """开启负载输入"""
        self.send_command(":SOUR:INP ON")

    def input_off(self):
        """关闭负载输入"""
        self.send_command(":SOUR:INP OFF")

    def trigger(self, state="ON"):
        """
        触发瞬态模式。

        Args:
            state: "ON" 开启瞬态
                   "OFF" 关闭瞬态
        """
        self.send_command(":TRIG")

    # ================================================================
    #  3. 短路 ON / OFF
    # ================================================================

    def short_on(self) -> bool:
        """
        开启短路：使用 :SOUR:INP:SHOR ON 专用命令。
        """
        self.send_command(":SOUR:INP OFF")       # 先关断
        self.send_command("*CLS", check_esr=False)                 # 清保护
        self.send_command(":SOUR:INP:SHOR ON")   # 激活短路功能
        self.send_command(":SOUR:INP ON")        # 闭合输入，短路生效
        time.sleep(0.3)
        return True

    def short_off(self):
        """关闭短路：:SOUR:INP:SHOR OFF 解除短路模式"""
        self.send_command(":SOUR:INP OFF")        # 先关断
        self.send_command(":SOUR:INP:SHOR OFF")  # 解除短路
        self.send_command("*CLS", check_esr=False)                 # 清保护

    # ================================================================
    #  4. 动态功能（Dynamic）
    # ================================================================

    def set_dynamic_mode(
        self,
        i_high: float,
        i_low: float,
        frequency: Optional[float] = None,
        slew_rate_a: Optional[float] = None,
        slew_rate_b: Optional[float] = None,
        high_dwell: Optional[float] = None,
        low_dwell: Optional[float] = None,
    ):
        """
        配置动态拉载模式（CC-Dynamic）。

        IT8500 系列动态命令：
          :SOUR:FUNC DYN                  → 进入动态模式
          :SOUR:DYN:IH <val>              → 高电流 (A)
          :SOUR:DYN:IL <val>              → 低电流 (A)
          :SOUR:DYN:FREQ <val>            → 切换频率 (Hz)
          :SOUR:DYN:HIGH:DWEL <sec>       → 高电流持续时间 (s)
          :SOUR:DYN:LOW:DWEL <sec>        → 低电流持续时间 (s)
          :SOUR:DYN:SLEW:RISE <A/μs>      → A点上升斜率
          :SOUR:DYN:SLEW:FALL <A/μs>      → B点下降斜率
          :SOUR:TRIG                      → 触发

        与 IT8701P 驱动接口兼容。

        Args:
            i_high:     高电流电平 (A)
            i_low:      低电流电平 (A)
            frequency:  切换频率 (Hz)，与 dwell 二选一
            slew_rate_a: A点(上升)斜率 (A/s)，自动转换 A/μs
            slew_rate_b: B点(下降)斜率 (A/s)，自动转换 A/μs
            high_dwell: 高电流持续时间 (s)，与 frequency 二选一
            low_dwell:  低电流持续时间 (s)，与 frequency 二选一
        """
        # 清错误队列
        self.send_command("*CLS", check_esr=False)

        # 进入动态模式
        self.send_command(":SOUR:FUNC DYN")

        # 电平设置
        self.send_command(f":SOUR:DYN:IH {i_high}")
        self.send_command(f":SOUR:DYN:IL {i_low}")

        # 持续时间（优先用 dwell，否则用 frequency 计算等宽方波）
        if high_dwell is not None and low_dwell is not None:
            self.send_command(f":SOUR:DYN:HIGH:DWEL {high_dwell}")
            self.send_command(f":SOUR:DYN:LOW:DWEL {low_dwell}")
        elif frequency is not None and frequency > 0:
            t = 0.5 / frequency
            self.send_command(f":SOUR:DYN:HIGH:DWEL {t}")
            self.send_command(f":SOUR:DYN:LOW:DWEL {t}")

        # 斜率设置（slew_rate 单位 A/s → 转换 A/μs）
        if slew_rate_a is not None and slew_rate_a > 0:
            self.send_command(f":SOUR:DYN:SLEW:RISE {slew_rate_a / 1_000_000:.6f}")
        if slew_rate_b is not None and slew_rate_b > 0:
            self.send_command(f":SOUR:DYN:SLEW:FALL {slew_rate_b / 1_000_000:.6f}")

        # 清错误队列
        self.send_command("*CLS", check_esr=False)

        self._current_mode = LoadMode.CC

    def trigger(self, state="ON"):
        """
        触发瞬态模式。

        Args:
            state: "ON" 开启瞬态
                   "OFF" 关闭瞬态
        """
        self.send_command(":TRIG")

    def run_dynamic(self, progress_callback=None):
        """
        启动动态拉载（瞬态模式）。

        动态拉载由硬件持续运行，run_dynamic 仅负责触发和开启负载输入。
        停止请调用 stop()。
        """
        self._stop_flag = False
        self.trigger()
        time.sleep(0.05)
        self.input_on()
        # 注意：不要在这里设置 self._stop_flag = True，
        # 否则动态拉载会在触发后立即被标记为停止

    # ================================================================
    #  5. LIST 功能
    # ================================================================

    def program_list(self, steps, mode: str = "CC", cycles: int = 1,
                     slew_rate: float = None):
        """编程 LIST 序列"""
        if not steps:
            return
        n = len(steps)
        vals = ",".join(str(s[0]) for s in steps)
        dwel = ",".join(str(s[1]) for s in steps)

        self.send_command(f":SOUR:FUNC:MODE LIST")
        self.send_command(f":LIST:POIN {n}")
        self.send_command(f":LIST:{mode.upper()} {vals}")
        self.send_command(f":LIST:DWEL {dwel}")
        self.send_command(f":LIST:COUN {cycles}")
        if slew_rate is not None:
            self.send_command(f":SOUR:CURR:SLOPE {slew_rate}")

    def run_list(self, progress_callback=None):
        """启动已编程的 LIST 序列"""
        self._stop_flag = False
        self.send_command(":SOUR:TRIG:SOUR IMM")
        self.input_on()

        if progress_callback:
            try:
                n = int(self.query(":LIST:POIN?").strip())
                cnt = int(self.query(":LIST:COUN?").strip())
                for cycle in range(1, cnt + 1):
                    for step_idx in range(1, n + 1):
                        if self._stop_flag:
                            break
                        stop = progress_callback(step_idx, n, cycle, cnt)
                        if stop is False:
                            self._stop_flag = True
                            break
                        time.sleep(0.5)
            except Exception:
                pass

    def stop(self):
        """停止当前正在执行的操作"""
        self._stop_flag = True
        try:
            self.input_off()
            self.send_command(":SOUR:FUNC:MODE FIXED")
        except Exception:
            pass

    # ================================================================
    #  6. 负载扫描 (Sweep)
    # ================================================================

    def set_sweep_mode(self,
                       start: float,
                       stop: float,
                       step: float,
                       dwell: float,
                       slew_rate: float = None,
                       mode: str = "CC"):
        """配置负载扫描模式（CC-Sweep）"""
        self.send_command(":SOUR:FUNC SWEEP")
        self.send_command(f":SOUR:SWE:STAR {start}")
        self.send_command(f":SOUR:SWE:STOP {stop}")
        self.send_command(f":SOUR:SWE:STEP {step}")
        self.send_command(f":SOUR:SWE:DWEL {dwell}")
        if slew_rate is not None:
            self.send_command(f":SOUR:SWE:SLOPE {slew_rate}")
        self._current_mode = LoadMode.CC

    def run_sweep(self, cycles: int = 1, progress_callback=None):
        """启动负载扫描"""
        self._stop_flag = False
        self.send_command(f":SOUR:SWE:COUN {cycles}")
        self.send_command(":SOUR:TRIG:SOUR IMM")
        self.input_on()

        total_steps = 0
        try:
            step_val = float(self.query(":SOUR:SWE:STEP?").strip())
            star_val = float(self.query(":SOUR:SWE:STAR?").strip())
            stop_val = float(self.query(":SOUR:SWE:STOP?").strip())
            if step_val > 0:
                total_steps = int(abs(stop_val - star_val) / step_val) + 1
        except Exception:
            total_steps = 0

        for cycle in range(1, cycles + 1):
            if self._stop_flag:
                break
            step_idx = 0
            while not self._stop_flag:
                curr = self.measure_current()
                step_idx += 1
                if progress_callback:
                    stop_cb = progress_callback(curr, step_idx, total_steps, cycle, cycles)
                    if stop_cb is False:
                        self._stop_flag = True
                        break
                time.sleep(0.1)
                if total_steps > 0 and step_idx > total_steps * 2 + 10:
                    break

    # ================================================================
    #  测量
    # ================================================================

    def measure_voltage(self) -> float:
        """测量被测设备端电压 (V)"""
        if not self._connected:
            return 0.0
        try:
            return float(self.query(":MEAS:VOLT?"))
        except Exception:
            return 0.0

    def measure_current(self) -> float:
        """测量拉载电流 (A)"""
        if not self._connected:
            return 0.0
        try:
            return float(self.query(":MEAS:CURR?"))
        except Exception:
            return 0.0
