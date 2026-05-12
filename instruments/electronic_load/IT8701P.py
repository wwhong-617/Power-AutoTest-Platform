# -*- coding: utf-8 -*-
"""
IT8701P 电子负载驱动（ITECH IT8700P 系列）
=============================================

适用型号: IT8700P / IT8700P+ / IT8700Pplus
通信方式: USB (ITECH USBTMC)

地址示例:
  USB0::0x2EC7::0x8700::800828011777420010::INSTR

命令规范（按 IT8700P 编程手册）:
  FUNC CURR/VOLT/RES/POW     — 设置负载模式
  INPut ON/OFF               — 开启/关闭负载输入
  INPut:STATe?               — 查询输入状态
  INPut:SHORt ON/OFF         — 短路功能
  CURR/SOURce                — CC 模式电流设置
  CURR:TRAN:MODE/ALEV/BLEV  — 瞬态动态带载
  CURR:SLEW:POSitive/NEGative — 斜率设置
  TRAN ON/OFF                — 瞬态开启/关闭
  TRIGger:IMMediate          — 触发
  MEASure:VOLTage/CURRent/POW — 测量
  PROTection:CLEar            — 清除保护
  *RST / *CLS / *IDN?        — 通用命令
  :CHAN <n>                  — 通道选择

不支持的功能（IT8701P 无此命令，报 Invalid command）:
  FUNC:MODE LIST / FUNC:MODE SWEEP — 改用 CURR:TRAN 动态模式
"""
import time
import logging
from typing import Optional
from .BaseElectronicLoad import BaseElectronicLoad, LoadMode

logger = logging.getLogger("PowerAutoTest")


class IT8701P(BaseElectronicLoad):
    """
    ITECH IT8701P / IT8700P 系列电子负载。

    支持 CC / CV / CR / CP 模式，支持瞬态（动态）带载。
    与 IT8511 API 兼容，动态参数通过 set_dynamic_mode() 设置。
    """

    # =====================================================================
    #  初始化与通用接口
    # =====================================================================

    def __init__(self, conn_type: str, address: str,
                 timeout_ms: int = 5000, channel: int = 1):
        super().__init__(conn_type, address, timeout_ms, channel=channel)
        self._model = "IT8701P"
        self._idn = ""
        self._stop_flag = False

    # ---------------------------------------------------------------------
    #  _send_initial_commands — 轻量化初始化
    #
    #  *RST + *CLS + SYST:REM。
    #  connect() 时调用一次，确保仪器干净在线。
    # ---------------------------------------------------------------------
    def _send_initial_commands(self):
        """
        轻量化初始化：*RST + *CLS + SYST:REM。
        """
        logger.info("[IT8701P] _send_initial_commands 开始")
        self.send_command("*RST", check_esr=False)
        time.sleep(0.5)
        self.send_command("*CLS", check_esr=False)
        self.send_command(":SYST:REM", check_esr=False)
        logger.info("[IT8701P] _send_initial_commands 完成")

    # ---------------------------------------------------------------------
    #  initialize — 完整初始化
    #
    #  调用轻量化重置 + 瞬态关闭 + 输入关闭 + 通道选择。
    # ---------------------------------------------------------------------
    def initialize(self) -> bool:
        """
        完整初始化：调用轻量化重置 + TRAN OFF + INP OFF + 通道选择。
        """
        if not self._connected:
            logger.warning("[IT8701P] initialize: 未连接，跳过")
            return False
        logger.info("[IT8701P] initialize: 开始完整初始化")
        self._send_initial_commands()
        self.send_command("TRAN OFF", check_esr=False)
        self.send_command("INPut OFF", check_esr=False)
        self.select_channel(self._channel)
        logger.info("[IT8701P] initialize 完成")
        return True

    def _validate_identity(self) -> bool:
        return any(x in self._idn
                   for x in ["IT8701P", "IT8700P", "ITECH", "SIMULATION"])

    # ---------------------------------------------------------------------
    #  close — 关闭负载（安全下电）
    # ---------------------------------------------------------------------
    def close(self):
        try:
            self.send_command("TRAN OFF", check_esr=False)
            self.send_command("INPut OFF", check_esr=False)
            self.send_command("*CLS", check_esr=False)
        except Exception:
            pass
        super().close()

    def reset(self):
        """仪器复位"""
        self.send_command("*RST", check_esr=False)
        time.sleep(0.5)
        self.send_command("*CLS", check_esr=False)

    # ---------------------------------------------------------------------
    #  以下为 BaseElectronicLoad 要求的抽象方法 stub
    #  IT8701P 不支持 LIST/SWEEP 硬件指令，测试用例用纯循环方式代替。
    # -----------------------------------------------------------------------
    def program_list(self, steps, mode: str = "CC", cycles: int = 1,
                     slew_rate: float = None):
        """LIST 编程（stub）"""
        pass

    def run_list(self, progress_callback=None):
        """启动 LIST（stub）"""
        pass

    def stop(self):
        """停止负载（stub）"""
        self.send_command("TRAN OFF", check_esr=False)
        self.send_command("INPut OFF", check_esr=False)

    def set_sweep_mode(self, start: float, stop: float, step: float,
                       dwell: float, slew_rate: float = None, mode: str = "CC"):
        """扫描模式配置（stub）"""
        pass

    def run_sweep(self, cycles: int = 1, progress_callback=None):
        """启动扫描（stub）"""
        pass

    def select_channel(self, channel: int):
        """选择负载通道（多路负载时）"""
        self.send_command(f":CHAN {channel}", check_esr=False)
        self._channel = channel
        logger.info(f"[IT8701P] select_channel={channel}")

    def get_idn(self) -> str:
        return self._idn

    # =====================================================================
    #  输入控制
    # =====================================================================

    def input_on(self):
        """开启负载输入"""
        self.send_command("INPut ON", check_esr=False)

    def input_off(self):
        """关闭负载输入"""
        self.send_command("INPut OFF", check_esr=False)

    def get_input_status(self) -> bool:
        """返回负载输入状态（True=ON, False=OFF）"""
        try:
            resp = self.query("INPut:STATe?")
            return resp in ("1", "ON")
        except Exception:
            return False

    # =====================================================================
    #  负载模式设置
    # =====================================================================

    def set_mode(self, mode: str):
        """设置负载模式（CC / CV / CR / CP）"""
        self.select_channel(self._channel)
        mode_map = {"CC": "CURR", "CV": "VOLT", "CR": "RES", "CP": "POW"}
        scpi_mode = mode_map.get(mode.upper(), mode.upper())
        self.send_command(f"FUNC {scpi_mode}", check_esr=False)
        self._current_mode = LoadMode[mode.upper()]

    def set_mode_cc(self, current: float, slew_rate: float = None):
        """
        设置恒流模式 (CC)，包含完整初始化（通道/模式/保护/斜率）。
        适用于扫描前一次性设置，或更换电流值时连同模式参数一起更新。

        Args:
            current:    目标电流（A）
            slew_rate:  可选，电流斜率（A/s），自动转换为 A/μs
        """
        self.select_channel(self._channel)
        self.send_command("*CLS", check_esr=False)
        self.send_command("FUNC CURR", check_esr=False)
        self.send_command(f"CURR {current}", check_esr=False)
        self.send_command("CURR:PROT ON", check_esr=False)
        if slew_rate is not None and slew_rate > 0:
            self.send_command(f"CURR:SLEW:POSitive {slew_rate / 1_000_000:.6f}")
        self._current_mode = LoadMode.CC

    def set_load_current(self, current: float):
        """
        仅更新负载电流值，不重新配置模式/通道/保护。
        用于扫描过程中快速更新电流（每点调用），避免冗余命令。

        Args:
            current: 目标电流（A）
        """
        self.send_command(f"CURR {current}", check_esr=False)

    def set_mode_cv(self, voltage: float):
        """设置恒压模式 (CV)"""
        self.select_channel(self._channel)
        self.send_command("*CLS", check_esr=False)
        self.send_command("FUNC VOLT", check_esr=False)
        self.send_command(f"VOLT {voltage}", check_esr=False)
        self._current_mode = LoadMode.CV

    def set_mode_cr(self, resistance: float):
        """设置恒阻模式 (CR)"""
        self.select_channel(self._channel)
        self.send_command("*CLS", check_esr=False)
        self.send_command("FUNC RES", check_esr=False)
        self.send_command(f"RES {resistance}", check_esr=False)
        self._current_mode = LoadMode.CR

    def set_mode_cp(self, power: float):
        """设置恒功模式 (CP)"""
        self.select_channel(self._channel)
        self.send_command("*CLS", check_esr=False)
        self.send_command("FUNC POW", check_esr=False)
        self.send_command(f"POW {power}", check_esr=False)
        self._current_mode = LoadMode.CP

    def set_load_slew_rate(self, rate: float):
        """
        设置电流斜率（A/s）。

        单位自动转换为 A/μs（仪器接受 A/μs）。
        仅设置正向（上升）斜率。
        """
        self.select_channel(self._channel)
        self.send_command(f"CURR:SLEW:POSitive {rate / 1_000_000:.6f}")

    # =====================================================================
    #  电流 / 电压 / 电阻 / 功率 直接设置
    # =====================================================================

    def set_current(self, current: float):
        """设置 CC 模式电流（A）"""
        self.select_channel(self._channel)
        self.send_command(f"CURR {current}", check_esr=False)

    def set_voltage(self, voltage: float):
        """设置 CV 模式电压（V）"""
        self.select_channel(self._channel)
        self.send_command(f"VOLT {voltage}", check_esr=False)

    def set_resistance(self, resistance: float):
        """设置 CR 模式电阻（Ω）"""
        self.select_channel(self._channel)
        self.send_command(f"RES {resistance}", check_esr=False)

    def set_power(self, power: float):
        """设置 CP 模式功率（W）"""
        self.select_channel(self._channel)
        self.send_command(f"POW {power}", check_esr=False)

    # =====================================================================
    #  瞬态动态带载（CURR:TRAN 模式）
    #
    #  IT8701P 使用 CURR:TRAN 命令实现动态带载：
    #    FUNC CURR                       — CC 模式
    #    CURR:TRAN:MODE CONTinuous      — 连续 Toggle 模式
    #    CURR:TRAN:ALEV <I>            — A 电平（高端电流）
    #    CURR:TRAN:BLEV <I>            — B 电平（低端电流）
    #    CURR:TRAN:AWID <sec>           — A 电平持续时间
    #    CURR:TRAN:BWID <sec>           — B 电平持续时间
    #    CURR:SLEW:POSitive <A/μs>    — 上升斜率
    #    CURR:SLEW:NEGative <A/μs>    — 下降斜率
    #    TRAN ON                         — 开启瞬态
    #
    #  注意：FUNC:MODE LIST / SWEEP 在 IT8701P 上不存在（报 Invalid），
    #  如需动态带载，请使用 set_dynamic_mode() + trigger()。
    # =====================================================================

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
        配置动态（瞬态）带载参数（连续 Toggle 模式）。

        配置完成后调用 trigger("ON") + input_on() 启动动态拉载。

        Args:
            i_high:     高电流电平（A）
            i_low:      低电流电平（A）
            frequency:  可选，切换频率（Hz），50% 占空比
            slew_rate_a: 可选，A→B 下降斜率（A/s）
            slew_rate_b: 可选，B→A 上升斜率（A/s）
            high_dwell: 可选，A 电平持续时间（s）
            low_dwell:  可选，B 电平持续时间（s）
        """
        self.select_channel(self._channel)
        self.send_command("*CLS", check_esr=False)
        self.send_command("FUNC CURR", check_esr=False)
        self.send_command("CURR:TRAN:MODE CONTinuous", check_esr=False)
        self.send_command(f"CURR:TRAN:ALEV {i_high}", check_esr=False)
        self.send_command(f"CURR:TRAN:BLEV {i_low}", check_esr=False)

        if high_dwell is not None and low_dwell is not None:
            t_high, t_low = high_dwell, low_dwell
        elif frequency is not None and frequency > 0:
            t_high = t_low = 0.5 / frequency
        else:
            t_high = t_low = 0.01

        self.send_command(f"CURR:TRAN:AWID {t_high}", check_esr=False)
        self.send_command(f"CURR:TRAN:BWID {t_low}", check_esr=False)

        if slew_rate_a is not None and slew_rate_a > 0:
            self.send_command(f"CURR:SLEW:POSitive {slew_rate_a / 1_000_000:.6f}",
                              check_esr=False)
        if slew_rate_b is not None and slew_rate_b > 0:
            self.send_command(f"CURR:SLEW:NEGative {slew_rate_b / 1_000_000:.6f}",
                              check_esr=False)

        self.send_command("*CLS", check_esr=False)
        time.sleep(0.05)

        self._current_mode = LoadMode.CC
        logger.info(
            f"[IT8701P] dynamic: I_HIGH={i_high}A I_LOW={i_low}A "
            f"T_HIGH={t_high*1000:.1f}ms T_LOW={t_low*1000:.1f}ms "
            f"SLEW_A={slew_rate_a or 'default'} SLEW_B={slew_rate_b or 'default'}"
        )

    def trigger(self, state: str = "ON"):
        """触发瞬态（TRAN ON）或停止（TRAN OFF）"""
        self.send_command(f"TRAN {state}", check_esr=False)

    def run_dynamic(self, progress_callback=None):
        """
        启动动态拉载。

        执行顺序: TRAN ON → 等待 50ms → INPut ON → TRIG:IMM
        """
        self._stop_flag = False
        self.trigger("ON")
        time.sleep(0.05)
        self.input_on()
        self.send_command("TRIGger:IMMediate", check_esr=False)
        self._stop_flag = True
        if progress_callback:
            progress_callback(None, 0)

    # =====================================================================
    #  短路功能
    # =====================================================================

    def short_on(self) -> bool:
        """开启短路（先关闭输入，再激活短路）"""
        self.send_command("*CLS", check_esr=False)
        self.send_command("INPut OFF", check_esr=False)
        self.send_command("INPut:SHORt ON", check_esr=False)
        return True

    def short_off(self):
        """关闭短路"""
        self.send_command("INPut:SHORt OFF", check_esr=False)

    # =====================================================================
    #  测量
    # =====================================================================

    def measure_voltage(self) -> float:
        """测量输入电压（V）"""
        try:
            return float(self.query(":MEAS:VOLT?"))
        except Exception as e:
            logger.warning(f"[IT8701P] measure_voltage failed: {e}")
            return 0.0

    def measure_current(self) -> float:
        """测量输入电流（A）"""
        try:
            return float(self.query(":MEAS:CURR?"))
        except Exception as e:
            logger.warning(f"[IT8701P] measure_current failed: {e}")
            return 0.0

    def measure_power(self) -> float:
        """测量有功功率（W）"""
        try:
            return float(self.query(":MEAS:POW?"))
        except Exception as e:
            logger.warning(f"[IT8701P] measure_power failed: {e}")
            return 0.0

    # =====================================================================
    #  保护
    # =====================================================================

    def clear_protection(self):
        """清除保护状态（PROTection:CLEar）"""
        self.send_command("PROTection:CLEar", check_esr=False)
        self.send_command("*CLS", check_esr=False)

    # =====================================================================
    #  停止
    # =====================================================================

    def stop(self):
        """停止瞬态 / 动态拉载，并关闭输入"""
        self._stop_flag = True
        self.send_command("TRAN OFF", check_esr=False)
        self.input_off()
