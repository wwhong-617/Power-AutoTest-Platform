# -*- coding: utf-8 -*-
"""
IT8511 - ITECH IT8500 系列电子负载驱动
========================================

ITECH IT8500 系列电子负载 SCPI 命令参考。
通讯方式：TCPIP / USB

SCPI 命令分类
══════════════════════════════════════════════════════

初始化
  *IDN?                      查询仪器身份
  *RST                       复位
  *CLS                       清除状态寄存器
  SYST:REM                   进入远程控制模式

负载 ON/OFF
  :SOUR:INP ON                开启负载输入
  :SOUR:INP OFF               关闭负载输入
  :SOUR:FUNC <mode>          设置模式：CC / CV / CR / CP
  :SOUR:CURR <value>          设置电流 (A)
  :SOUR:VOLT <value>          设置电压 (V)
  :SOUR:RES <value>           设置电阻 (Ω)
  :SOUR:POW <value>           设置功率 (W)
  :SOUR:CURR:SLOPE <value>   设置电流斜率 (A/s)
  :SOUR:CURR:PROT ON         开启电流保护

短路
  :SOUR:FUNC CR               切换到 CR 模式
  :SOUR:RES 0.1               设置最小电阻（约 0.1Ω，等效短路）
  :SOUR:INP ON/OFF            短路接通/断开

动态模式（CC-Dynamic）
  :SOUR:FUNC DYN              进入动态模式
  :SOUR:DYN:IH <value>        高电流电平 (A)
  :SOUR:DYN:IL <value>        低电流电平 (A)
  :SOUR:DYN:FREQ <value>      切换频率 (Hz)
  :SOUR:DYN:RISE <value>      上升时间 (s)
  :SOUR:DYN:FALL <value>      下降时间 (s)
  :SOUR:TRIG:SOUR IMM         触发源：立即
  :SOUR:FUNC:MODE DYN         选择动态模式

LIST 模式
  :SOUR:FUNC:MODE LIST        选择列表模式
  :LIST:POIN <n>              设置列表点数
  :LIST:CC <vals>            CC 电流序列
  :LIST:CV <vals>            CV 电压序列
  :LIST:CR <vals>            CR 电阻序列
  :LIST:CP <vals>            CP 功率序列
  :LIST:DWEL <vals>          每步持续时间 (s)
  :LIST:COUN <n>             重复次数
  :SOUR:TRIG:SOUR IMM         触发源：立即
  :SOUR:FUNC:MODE FIXED       恢复固定模式

负载扫描（CC-Sweep）
  :SOUR:FUNC SWEEP            进入扫描模式
  :SOUR:SWE:STAR <value>      扫描起始值 (A)
  :SOUR:SWE:STOP <value>      扫描终止值 (A)
  :SOUR:SWE:STEP <value>      步进幅度 (A)
  :SOUR:SWE:DWEL <value>      每步维持时间 (s)
  :SOUR:SWE:COUN <n>          扫描重复次数
  :SOUR:SWE:SLOPE <value>     扫描斜率 (A/s)
  :SOUR:TRIG:SOUR IMM         触发源：立即

测量
  :MEAS:VOLT?                 测量被测设备端电压 (V)
  :MEAS:CURR?                 测量拉载电流 (A)
"""

import time
from .BaseElectronicLoad import BaseElectronicLoad, LoadMode


class IT8511(BaseElectronicLoad):
    """
    ITECH IT8511 电子负载驱动。
    继承 BaseElectronicLoad，实现 IT8500 系列专用 SCPI 命令。
    IT8511 与 IT8512+ 命令集基本兼容。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000, channel: int = 1):
        super().__init__(conn_type, address, timeout_ms, channel=channel)
        self._model = "IT8511"
        self._stop_flag = False

    # ================================================================
    #  私有工具
    # ================================================================

    def _send_initial_commands(self):
        self.send_command("*CLS", check_esr=False)
        self.send_command("SYST:REM", check_esr=False)

    def _validate_identity(self) -> bool:
        if any(x in self._idn for x in ["IT8511", "IT8500", "ITECH", "SIMULATION"]):
            return True
        return False

    # ================================================================
    #  1. 初始化
    # ================================================================

    def initialize(self):
        """
        电子负载初始化：*RST 复位 → *CLS 清除状态 → SYST:REM 进入远程。
        """
        self.send_command("*RST", check_esr=False)
        time.sleep(0.5)
        self.send_command("*CLS", check_esr=False)
        self.send_command("SYST:REM", check_esr=False)

    # ================================================================
    #  2. 负载 ON / OFF
    # ================================================================

    def set_mode_cc(self, current: float, slew_rate: float = None):
        """
        设置恒流模式 (CC)，并可设置电流斜率。

        Args:
            current:   目标电流 (A)
            slew_rate: 可选，电流上升斜率 (A/s)
        """
        self.send_command(":SOUR:FUNC CC", check_esr=False)
        self.send_command(f":SOUR:CURR {current}")
        self.send_command(":SOUR:CURR:PROT ON", check_esr=False)
        if slew_rate is not None:
            self.send_command(f":SOUR:CURR:SLOPE {slew_rate}")
        self._current_mode = LoadMode.CC

    def set_mode_cv(self, voltage: float):
        """设置恒压模式 (CV)"""
        self.send_command(":SOUR:FUNC CV", check_esr=False)
        self.send_command(f":SOUR:VOLT {voltage}")
        self._current_mode = LoadMode.CV

    def set_mode_cr(self, resistance: float):
        """设置恒阻模式 (CR)"""
        self.send_command(":SOUR:FUNC CR", check_esr=False)
        self.send_command(f":SOUR:RES {resistance}")
        self._current_mode = LoadMode.CR

    def set_mode_cp(self, power: float):
        """设置恒功模式 (CP)"""
        self.send_command(":SOUR:FUNC CP", check_esr=False)
        self.send_command(f":SOUR:POW {power}")
        self._current_mode = LoadMode.CP

    def set_load_slew_rate(self, rate: float):
        """
        设置负载电流/功率变化斜率 (A/s)。
        """
        self.send_command(f":SOUR:CURR:SLOPE {rate}")

    def input_on(self):
        """开启负载输入"""
        self.send_command(":SOUR:INP ON", check_esr=False)

    def input_off(self):
        """关闭负载输入"""
        self.send_command(":SOUR:INP OFF", check_esr=False)

    # ================================================================
    #  3. 短路 ON / OFF
    # ================================================================

    def short_on(self) -> bool:
        """
        开启短路：使用 :SOUR:INP:SHOR ON 专用命令。
        """
        self.send_command(":SOUR:INP OFF", check_esr=False)       # 先关断
        self.send_command("*CLS", check_esr=False)                 # 清保护
        self.send_command(":SOUR:INP:SHOR ON", check_esr=False)   # 激活短路功能
        self.send_command(":SOUR:INP ON", check_esr=False)        # 闭合输入，短路生效
        time.sleep(0.3)
        return True

    def short_off(self):
        """关闭短路：:SOUR:INP:SHOR OFF 解除短路模式"""
        self.send_command(":SOUR:INP OFF", check_esr=False)        # 先关断
        self.send_command(":SOUR:INP:SHOR OFF", check_esr=False)  # 解除短路
        self.send_command("*CLS", check_esr=False)                 # 清保护

    def set_dynamic_mode(self,
                        i_high: float,
                        i_low: float,
                        frequency: float = None,
                        slew_rate: float = None,
                        high_dwell: float = None,
                        low_dwell: float = None,
                        slew_rate_a: float = None,
                        slew_rate_b: float = None):
        """
        配置动态拉载模式（CC-Dynamic）。

        IT8500 命令（按编程手册 DYN 子系统）：
          DYN:HIGH <val>              → 高电流电平 (A)
          DYN:LOW <val>               → 低电流电平 (A)
          DYN:HIGH:DWEL <time>        → 高电流停留时间 (s)
          DYN:LOW:DWEL <time>         → 低电流停留时间 (s)
          DYN:SLEW[:BOTH] <rate>      → 上升/下降斜率 (A/μs)，同时设置
          DYN:SLEW:RISE <rate>        → 上升斜率 (A/s)
          DYN:SLEW:FALL <rate>        → 下降斜率 (A/s)
          DYN:MODE FREQ               → 频率模式（连续切换）
          DYN:MODE TOGG               → 翻转模式（触发切换）

        Args:
            i_high:     高电流电平 (A)
            i_low:      低电流电平 (A)
            frequency:  切换频率 (Hz)，FREQ 模式下用于计算周期
            slew_rate:  切换斜率 (A/μs)，设置上升/下降速度
            high_dwell: 高电流持续时间 (s)
            low_dwell:  低电流持续时间 (s)
            slew_rate_a: A点斜率 (A/s)，优先级高于 slew_rate
            slew_rate_b: B点斜率 (A/s)
        """
        # 先清错误队列（防止之前的错误状态导致后续命令超时）
        self.send_command(":CLS", check_esr=False)

        # 设置 CC 模式
        self.send_command(":FUNC CC", check_esr=False)

        # 设置动态参数
        self.send_command(f"DYN:HIGH {i_high}")
        self.send_command(f"DYN:LOW {i_low}")
        if high_dwell is not None:
            self.send_command(f"DYN:HIGH:DWEL {high_dwell}")
        if low_dwell is not None:
            self.send_command(f"DYN:LOW:DWEL {low_dwell}")

        # 斜率设置（IT8511 单位为 A/μs）
        if slew_rate_a is not None and slew_rate_b is not None:
            # 分别设置 A点(上升)/B点(下降) 斜率
            self.send_command(f"DYN:SLEW:RISE {slew_rate_a / 1_000_000:.6f}")
            self.send_command(f"DYN:SLEW:FALL {slew_rate_b / 1_000_000:.6f}")
        elif slew_rate is not None:
            self.send_command(f"DYN:SLEW {slew_rate}")

        self.send_command("DYN:MODE CONTINUOUS", check_esr=False)
        if frequency is not None:
            self.send_command(f"DYN:FREQ {frequency}")

        # 再次清错误队列
        self.send_command(":CLS", check_esr=False)

        # 触发（对应 trigger()）
        self.send_command(":TRIG", check_esr=False)

        self._current_mode = LoadMode.CC

    def trigger(self, state="ON"):
        """
        触发瞬态模式。

        Args:
            state: "ON" 开启瞬态
                   "OFF" 关闭瞬态
        """
        self.send_command(":TRIG", check_esr=False)

    def run_dynamic(self, progress_callback=None):
        """
        启动动态拉载（瞬态模式）。

        动态拉载由硬件持续运行，run_dynamic 仅负责触发和开启负载输入。
        停止请调用 stop()。
        """
        self._stop_flag = False
        self.trigger("ON")
        time.sleep(0.05)
        self.input_on()
        # 注意：不要在这里设置 self._stop_flag = True，
        # 否则动态拉载会在触发后立即被标记为停止

    # ================================================================
    #  5. LIST 功能
    # ================================================================

    def program_list(self, steps, mode: str = "CC", cycles: int = 1,
                     slew_rate: float = None):
        """
        编程 LIST 序列（列表模式）。

        IT8500 命令：
          :SOUR:FUNC:MODE LIST
          :LIST:POIN <n>
          :LIST:CC/CV/CR/CP <vals>
          :LIST:DWEL <vals>
          :LIST:COUN <n>

        Args:
            steps:     LIST 序列，每项 (负载值, 持续时间秒)
                       示例 CC: [(1.0, 5), (2.0, 5), (0.5, 3)]
            mode:      负载模式，"CC" / "CV" / "CR" / "CP"
            cycles:    重复次数
            slew_rate: 可选，切换斜率 (A/s)
        """
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
        """
        启动已编程的 LIST 序列。

        Args:
            progress_callback: callback(step_index, total_steps, cycle, total_cycles)
                             返回 False 时停止
        """
        self._stop_flag = False
        self.send_command(":SOUR:TRIG:SOUR IMM", check_esr=False)
        self.input_on()

        # IT8500 LIST 由硬件控制时序，这里轮询进度
        if progress_callback:
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

    def stop(self):
        """
        停止当前正在执行的动态拉载、LIST 或 SWEEP 操作。
        """
        self._stop_flag = True
        try:
            self.input_off()
            self.send_command(":SOUR:FUNC:MODE FIXED", check_esr=False)
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
        """
        配置负载扫描模式（CC-Sweep）。

        IT8500 命令：
          :SOUR:FUNC SWEEP            → 进入扫描模式
          :SOUR:SWE:STAR <val>       → 起始值
          :SOUR:SWE:STOP <val>       → 终止值
          :SOUR:SWE:STEP <val>       → 步进
          :SOUR:SWE:DWEL <val>        → 每步维持时间
          :SOUR:SWE:SLOPE <val>       → 扫描斜率
          :SOUR:SWE:COUN <val>        → 重复次数（由 run_sweep 传入）

        Args:
            start:     扫描起始值 (A)
            stop:      扫描终止值 (A)
            step:      步进幅度 (A)
            dwell:     每步维持时间 (秒)
            slew_rate: 可选，扫描斜率 (A/s)
            mode:      扫描模式，"CC" / "CV" / "CR" / "CP"
        """
        self.send_command(":SOUR:FUNC SWEEP", check_esr=False)
        self.send_command(f":SOUR:SWE:STAR {start}")
        self.send_command(f":SOUR:SWE:STOP {stop}")
        self.send_command(f":SOUR:SWE:STEP {step}")
        self.send_command(f":SOUR:SWE:DWEL {dwell}")
        if slew_rate is not None:
            self.send_command(f":SOUR:SWE:SLOPE {slew_rate}")
        self._current_mode = LoadMode.CC

    def run_sweep(self, cycles: int = 1, progress_callback=None):
        """
        启动负载扫描。

        Args:
            cycles:            扫描重复次数
            progress_callback: callback(current_value, step_index, total_steps, cycle, cycles)
                             返回 False 时停止
        """
        self._stop_flag = False
        self.send_command(f":SOUR:SWE:COUN {cycles}")
        self.send_command(":SOUR:TRIG:SOUR IMM", check_esr=False)
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
                    stop = progress_callback(curr, step_idx, total_steps, cycle, cycles)
                    if stop is False:
                        self._stop_flag = True
                        break
                time.sleep(0.1)
                # 简单退出：当 step_idx 超过预期总步数的 2 倍时退出（防止无限循环）
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
