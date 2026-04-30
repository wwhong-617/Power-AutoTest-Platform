# -*- coding: utf-8 -*-
"""
IT8701P 电子负载驱动（ITECH IT8700P 系列）

兼容 IT8700P / IT8700P+ / IT8700Pplus 系列
与 IT8511 的 API 兼容，但 SCPI 命令格式不同：

IT8511 动态命令: DYN:HIGH / DYN:LOW / DYN:FREQ / DYN:MODE
IT8701P 动态命令: CURR:TRAN:ALEV / CURR:TRAN:BLEV / CURR:TRAN:AWID / CURR:TRAN:BWID / TRAN

通信: USB (ITECH USBTMC)
地址示例: USB0::0x2EC7::0x8700::800828011777420010::INSTR
"""
import time
import logging
from typing import Optional, List, Dict, Any
from .BaseElectronicLoad import BaseElectronicLoad, LoadMode

logger = logging.getLogger("PowerAutoTest")


class IT8701P(BaseElectronicLoad):
    """
    ITECH IT8701P / IT8700P 系列电子负载

    支持 CC/CV/CR/CP 模式，支持瞬态（动态）带载。
    与 IT8511 API 兼容，动态参数通过 set_dynamic_mode() 设置。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000, channel: int = 1):
        super().__init__(conn_type, address, timeout_ms, channel=channel)
        self._model = "IT8701P"
        self._idn = ""
        self._stop_flag = False

    # ================================================================
    #  2. 通用仪器接口
    # ================================================================

    def initialize(self) -> bool:
        try:
            self._idn = self.query("*IDN?")
            if not self._idn or "ITECH" not in self._idn:
                logger.warning(f"WARNING: Unexpected IDN: {self._idn!r}")
            logger.info(f"IT8701P connected: {self._idn}")

            # 远程模式
            self.send_command(":SYST:REM")

            # 清错误队列
            self.send_command(":CLS", check_esr=False)

            # 默认关闭瞬态
            self.send_command(":TRAN OFF")

            # 关闭输入
            self.send_command(":SOUR:INP OFF")

            # 选择负载通道
            self.select_channel(self._channel)

            self._current_mode = LoadMode.CC
            return True

        except Exception as e:
            logger.error(f"IT8701P init FAILED: {e}")
            return False

    def _send_initial_commands(self):
        self.send_command("*CLS", check_esr=False)
        self.send_command(":SYST:REM")

    def _validate_identity(self) -> bool:
        if any(x in self._idn for x in ["IT8701P", "IT8700P", "ITECH", "SIMULATION"]):
            return True
        return False

    def close(self):
        try:
            self.send_command(":TRAN OFF")
            self.send_command(":SOUR:INP OFF")
            self.send_command(":CLS", check_esr=False)
        except Exception:
            pass
        super().close()

    def select_channel(self, channel: int):
        """
        选择负载通道（IT8701P 多路负载需要）
        发送 :CHAN <num> 选择通道
        """
        self.send_command(f":CHAN {channel}")
        self._channel = channel
        logger.info(f"[IT8701P] select_channel={channel}")

    def get_idn(self) -> str:
        return self._idn

    def reset(self):
        self.send_command("*RST")
        time.sleep(0.5)
        self.send_command(":CLS", check_esr=False)

    # ================================================================
    #  3. 输入控制
    # ================================================================

    def input_on(self):
        """开启负载输入"""
        self.send_command("INPut ON")

    def input_off(self):
        """关闭负载输入"""
        self.send_command("INPut OFF")

    def get_input_status(self) -> bool:
        """返回负载输入状态（True=ON, False=OFF）"""
        try:
            resp = self.query(":SOUR:INP?")
            return resp in ("1", "ON")
        except Exception:
            return False

    # ================================================================
    #  4. 模式设置
    # ================================================================

    def set_mode(self, mode: str):
        """
        设置负载模式。
        IT8701P 支持: CC, CV, CR, CP
        """
        self.select_channel(self._channel)
        mode_map = {
            "CC": "CURR",
            "CV": "VOLT",
            "CR": "RES",
            "CP": "POW",
        }
        scpi_mode = mode_map.get(mode.upper(), mode.upper())
        self.send_command(f":FUNC {scpi_mode}")
        self._current_mode = LoadMode[mode.upper()]

    def set_mode_cc(self, current: float, slew_rate: float = None):
        """设置恒流模式 (CC)，并可设置电流斜率"""
        self.select_channel(self._channel)
        self.send_command(":CLS", check_esr=False)
        self.send_command(":FUNC CURR")
        self.send_command(f":CURR {current}")
        self.send_command(":CURR:PROT ON")
        if slew_rate is not None and slew_rate > 0:
            slew_ua = slew_rate / 1_000_000  # A/s → A/μs
            self.send_command(f":CURR:SLEW {slew_ua:.6f}")
        self._current_mode = LoadMode.CC

    def set_mode_cv(self, voltage: float):
        """设置恒压模式 (CV)"""
        self.select_channel(self._channel)
        self.send_command(":CLS", check_esr=False)
        self.send_command(":FUNC VOLT")
        self.send_command(f":VOLT {voltage}")
        self._current_mode = LoadMode.CV

    def set_mode_cr(self, resistance: float):
        """设置恒阻模式 (CR)"""
        self.select_channel(self._channel)
        self.send_command(":CLS", check_esr=False)
        self.send_command(":FUNC RES")
        self.send_command(f":RES {resistance}")
        self._current_mode = LoadMode.CR

    def set_mode_cp(self, power: float):
        """设置恒功模式 (CP)"""
        self.select_channel(self._channel)
        self.send_command(":CLS", check_esr=False)
        self.send_command(":FUNC POW")
        self.send_command(f":POW {power}")
        self._current_mode = LoadMode.CP

    def set_load_slew_rate(self, rate: float):
        """设置负载斜率 (A/s)"""
        self.select_channel(self._channel)
        slew_ua = rate / 1_000_000  # A/s → A/μs
        self.send_command(f":CURR:SLEW {slew_ua:.6f}")

    # ================================================================
    #  5. 电流/电压/电阻/功率设置
    # ================================================================

    def set_current(self, current: float):
        """设置 CC 模式电流 (A)"""
        self.select_channel(self._channel)
        self.send_command(f":CURR {current}")

    def set_voltage(self, voltage: float):
        """设置 CV 模式电压 (V)"""
        self.select_channel(self._channel)
        self.send_command(f":VOLT {voltage}")

    def set_resistance(self, resistance: float):
        """设置 CR 模式电阻 (Ω)"""
        self.select_channel(self._channel)
        self.send_command(f":RES {resistance}")

    def set_power(self, power: float):
        """设置 CP 模式功率 (W)"""
        self.select_channel(self._channel)
        self.send_command(f":POW {power}")

    # ================================================================
    #  6. 瞬态（动态带载）- 与 IT8511 set_dynamic_mode 兼容
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
        设置动态（瞬态）带载模式（连续 Toggle 模式）。

        IT8701P 使用 CURR:TRAN 命令:
        - CURR:TRAN:MODE CONTinuous : 连续模式
        - CURR:TRAN:ALEV <I>      : A电平（高端电流）
        - CURR:TRAN:BLEV <I>      : B电平（低端电流）
        - CURR:TRAN:AWID <sec>    : A电平持续时间
        - CURR:TRAN:BWID <sec>    : B电平持续时间
        - CURR:TRAN:ASLE <A/μs>  : A点斜率
        - CURR:TRAN:BSLE <A/μs>  : B点斜率
        - TRAN ON                 : 开启瞬态

        Args:
            i_high:     高电流电平 (A)
            i_low:      低电流电平 (A)
            frequency:  切换频率 (Hz)，用于计算周期
            slew_rate_a: A点切换斜率 (A/s)
            slew_rate_b: B点切换斜率 (A/s)
            high_dwell: 高电流持续时间 (s)
            low_dwell:  低电流持续时间 (s)
        """
        # 先选通道
        self.select_channel(self._channel)

        # 设置 CC 模式
        self.send_command("*CLS", check_esr=False)
        self.send_command("CURRent")

        # 瞬态模式（连续）
        self.send_command("CURRent:TRANsient:MODE CONTinuous")

        # 动态电平
        self.send_command(f"CURRent:TRANsient:ALEVel {i_high}")
        self.send_command(f"CURRent:TRANsient:BLEVel {i_low}")

        # 根据频率和占空比计算脉宽
        if high_dwell is not None and low_dwell is not None:
            t_high = high_dwell
            t_low = low_dwell
        elif frequency is not None and frequency > 0:
            t_high = 0.5 / frequency
            t_low = 0.5 / frequency
        else:
            t_high = 0.01
            t_low = 0.01

        self.send_command(f"CURRent:TRANsient:AWIDth {t_high}")
        self.send_command(f"CURRent:TRANsient:BWIDth {t_low}")

        # A/B 点斜率
        if slew_rate_a is not None and slew_rate_a > 0:
            self.send_command(f"CURRent:TRANsient:ASLEw {slew_rate_a:.6f}")
        if slew_rate_b is not None and slew_rate_b > 0:
            self.send_command(f"CURRent:TRANsient:BSLEw {slew_rate_b:.6f}")

        # 清错误队列
        self.send_command("*CLS", check_esr=False)

        time.sleep(0.05)
     
        self._current_mode = LoadMode.CC
        logger.info(
            f"[IT8701P] dynamic mode: I_HIGH={i_high}A I_LOW={i_low}A "
            f"T_HIGH={t_high*1000:.1f}ms T_LOW={t_low*1000:.1f}ms "
            f"SLEW_A={slew_rate_a or 'default'} SLEW_B={slew_rate_b or 'default'} MODE=CONT"
        )

    def trigger(self, state="ON"):
        """
        触发瞬态模式。

        Args:
            state: "ON" 开启瞬态（触发动态负载）
                   "OFF" 关闭瞬态
        """
        self.send_command(f":TRAN {state}")

    def run_dynamic(self, progress_callback=None):
        """
        启动动态拉载（瞬态模式）。
        """
        self._stop_flag = False
        self.trigger("ON")
        time.sleep(0.05)
        self.input_on()
        self.send_command("TRIGger:IMMediate")
        self._stop_flag = True

    # ================================================================
    #  9. LIST 功能
    # ================================================================

    def program_list(self, steps, mode: str = "CC", cycles: int = 1,
                     slew_rate: float = None):
        """
        编程 LIST 序列（IT8701P）。

        IT8701P LIST 命令:
          :FUNC:MODE LIST
          :LIST:POIN <n>
          :LIST:{MODE} <vals>
          :LIST:DWEL <vals>
          :LIST:COUN <n>
        """
        if not steps:
            return
        self.select_channel(self._channel)
        self.send_command(":FUNC:MODE LIST")
        n = len(steps)
        self.send_command(f":LIST:POIN {n}")

        mode_cmd_map = {"CC": "CURR", "CV": "VOLT", "CR": "RES", "CP": "POW"}
        scpi_mode = mode_cmd_map.get(mode.upper(), "CURR")

        vals = ",".join(str(v) for v, _ in steps)
        dwellies = ",".join(str(d) for _, d in steps)
        self.send_command(f":LIST:{scpi_mode} {vals}")
        self.send_command(f":LIST:DWEL {dwellies}")
        self.send_command(f":LIST:COUN {cycles}")

        if slew_rate is not None and slew_rate > 0:
            slew_ua = slew_rate / 1_000_000
            self.send_command(f":LIST:{scpi_mode}:SLEW {slew_ua:.6f}")

        logger.info(f"[IT8701P] program_list: {n} points, mode={scpi_mode}, cycles={cycles}")

    def run_list(self, progress_callback=None):
        """启动 LIST 序列"""
        self._stop_flag = False
        self.select_channel(self._channel)
        self.send_command(":TRAN ON")
        self.input_on()
        step_count = 0
        while not self._stop_flag:
            try:
                curr = self.measure_current()
                step_count += 1
                if progress_callback and progress_callback(curr, step_count) is False:
                    self._stop_flag = True
                    break
                time.sleep(0.1)
            except Exception:
                break
        self._stop_flag = True

    def stop(self):
        """停止当前操作"""
        self._stop_flag = True
        self.send_command(":TRAN OFF")
        self.input_off()

    # ================================================================
    #  10. SWEEP 功能
    # ================================================================

    def set_sweep_mode(self,
                       start: float,
                       stop: float,
                       step: float,
                       dwell: float,
                       slew_rate: float = None,
                       mode: str = "CC"):
        """
        配置负载扫描模式（IT8701P）。

        IT8701P SWEEP 命令:
          :FUNC:MODE SWEEP
          :SWE:POIN <n>
          :SWE:{MODE}:STAR <val>
          :SWE:{MODE}:STOP <val>
          :SWE:{MODE}:STEP <val>
          :SWE:DWEL <val>
          :SWE:COUN 1
        """
        self.select_channel(self._channel)
        self.send_command(":FUNC:MODE SWEEP")

        mode_cmd_map = {"CC": "CURR", "CV": "VOLT", "CR": "RES", "CP": "POW"}
        scpi_mode = mode_cmd_map.get(mode.upper(), "CURR")

        # 计算扫描点数
        if step > 0:
            n = max(2, int(round((stop - start) / step)) + 1)
        else:
            n = 2
        self.send_command(f":SWE:POIN {n}")
        self.send_command(f":SWE:{scpi_mode}:STAR {start}")
        self.send_command(f":SWE:{scpi_mode}:STOP {stop}")
        self.send_command(f":SWE:{scpi_mode}:STEP {step}")
        self.send_command(f":SWE:DWEL {dwell}")
        self.send_command(":SWE:COUN 1")

        if slew_rate is not None and slew_rate > 0:
            slew_ua = slew_rate / 1_000_000
            self.send_command(f":SWE:{scpi_mode}:SLEW {slew_ua:.6f}")

        logger.info(f"[IT8701P] set_sweep_mode: {scpi_mode} {start}→{stop} step={step} dwell={dwell}")

    def run_sweep(self, cycles: int = 1, progress_callback=None):
        """启动负载扫描"""
        self._stop_flag = False
        self.select_channel(self._channel)
        self.send_command(":TRAN ON")
        self.input_on()
        step_count = 0
        while not self._stop_flag:
            try:
                curr = self.measure_current()
                step_count += 1
                if progress_callback and progress_callback(curr, step_count) is False:
                    self._stop_flag = True
                    break
                time.sleep(0.1)
            except Exception:
                break
        self._stop_flag = True

    # ================================================================
    #  7. 短路功能
    # ================================================================

    def short_on(self) -> bool:
        """开启短路"""
        self.send_command(":CLS", check_esr=False)
        self.send_command(":SOUR:INP OFF")
        self.send_command(":SOUR:INP:SHOR ON")
        return True

    def short_off(self):
        """关闭短路"""
        self.send_command(":SOUR:INP:SHOR OFF")

    # ================================================================
    #  8. 测量
    # ================================================================

    def measure_voltage(self) -> float:
        """测量输入电压 (V)"""
        try:
            resp = self.query(":MEAS:VOLT?")
            return float(resp)
        except Exception as e:
            logger.warning(f"measure_voltage failed: {e}")
            return 0.0

    def measure_current(self) -> float:
        """测量输入电流 (A)"""
        try:
            resp = self.query(":MEAS:CURR?")
            return float(resp)
        except Exception as e:
            logger.warning(f"measure_current failed: {e}")
            return 0.0

    def measure_power(self) -> float:
        """测量功率 (W)"""
        try:
            resp = self.query(":MEAS:POW?")
            return float(resp)
        except Exception as e:
            logger.warning(f"measure_power failed: {e}")
            return 0.0

    # ================================================================
    #  9. 保护
    # ================================================================

    def clear_protection(self):
        """清除保护状态"""
        self.send_command(":CLS", check_esr=False)
        self.send_command("*CLS", check_esr=False)

    # ================================================================
    #  10. 辅助
