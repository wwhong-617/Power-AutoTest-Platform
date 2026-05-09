# -*- coding: utf-8 -*-
"""
WT322E - Yokogawa WT300E 系列功率计驱动
========================================

Yokogawa WT322E 功率计驱动（二通道）。
通讯方式：TCPIP / USB

WT322E 与 WT333E 同属 WT300E 系列，命令集基本兼容。
通道索引 WT322E 使用 1/2（Yokogawa 原生），驱动内部自动映射。

SCPI 命令分类
══════════════════════════════════════════════════════

初始化
  *IDN? / *RST / *CLS / FORMAT DATA REAL / SYST:REM

基础设置（量程）
  :VOLTAGE:RANGE CH<ch>, <val>   电压量程 (V)
  :VOLTAGE:AUTO CH<ch>, <ON|OFF> 电压自动量程
  :CURRENT:RANGE CH<ch>, <val>   电流量程 (A)
  :CURRENT:AUTO CH<ch>, <ON|OFF> 电流自动量程
  :INP:POW:RANG <val>            功率量程 (W)

测试设置
  :INP:MODE <mode>          接线模式：1P2W / 1P3W / 3P3W / 3P4W
  :INP:TYPE <type>          输入类型：AC / DC / ACDC
  :AVER:STAT <ON|OFF>       平均滤波器开关
  :AVER:COUN <n>            平均次数
  :INP:ZERO <ch>            校零（ch = 1/2）

测量
  :NUMERIC:NORMAL:VALUE? <ch>  查询指定通道全部值
  :INP:CHAN <n>             选择通道 (1/2)
  VOLTAGE?                  查询电压（需先选通道）
  CURRENT?                  查询电流
  POWER?                   查询有功功率
  PF?                       查询功率因数
  FREQUENCY?                查询频率

积分功能
  :INTEGR:START             启动积分
  :INTEGR:STOP              停止积分
  :INTEGR:RESET             重置积分
  :INTEGR:VAL? <ch>         查询积分能量值 (Wh)
  :INTEGR:TIME?             查询积分时间 (s)

谐波功能
  :HARM:MODE <ON|OFF>       开启/关闭谐波分析
  :HARM:ORD <n>             设置最高谐波次数
  :HARM:THD? <ch>           查询 THD (%)
  :HARM:DATA? <ch>,<order>  查询指定次谐波值
"""

import time
import logging
from .BasePowerMeter import BasePowerMeter

logger = logging.getLogger("PowerAutoTest")


class WT322E(BasePowerMeter):
    """
    Yokogawa WT322E 功率计驱动。
    继承 BasePowerMeter，实现 WT300E 系列专用 SCPI 命令。
    WT322E 与 WT333E 命令集基本兼容，通道索引使用 1/2。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)
        self._model = "WT322E"
        self._current_channel = 1
        self._integration_running = False
        self._integration_start_time = None
        self._integration_time = 0.0
        self._integration_wh = {}

    # ================================================================
    #  私有工具
    # ================================================================

    def _send_initial_commands(self):
        """
        轻量化初始化：*RST + *CLS。
        WT322E 通过 USB/TCPIP 自动进入远程模式，无需 SYST:REM。
        """
        self.send_command("*RST", check_esr=False)
        time.sleep(0.5)
        self.send_command("*CLS", check_esr=False)

    def _validate_identity(self) -> bool:
        if any(x in self._idn for x in ["WT322", "WT300E", "YOKOGAWA", "SIMULATION"]):
            return True
        return False

    def _normalize_ch(self, channel) -> int:
        """
        将 UI 通道标识转换为 Yokogawa 原生 1 基索引。

        UI 字符串（推荐）："CH1" → Yokogawa 1, "CH2" → Yokogawa 2
        整数（兼容旧接口）：0 → Yokogawa 1, 1 → Yokogawa 2

        Returns:
            Yokogawa 通道号：1 对应 UI CH1，2 对应 UI CH2
        """
        if isinstance(channel, str):
            # "CH1" → 1, "CH2" → 2
            return int(channel.replace("CH", "").replace("ch", ""))
        # 旧接口直接传整数 0/1（旧行为是 +1 转 Yokogawa 通道）
        return int(channel) + 1

    def _select_channel(self, channel):
        """
        选择测量通道。WT322E Yokogawa 通道索引为 1/2。
        channel: "CH1"/"CH2"（推荐）或直接传 Yokogawa 通道号 1/2。
        """
        # 统一 UI "CH1" → Yokogawa 1, "CH2" → Yokogawa 2
        ch_yoko = self._normalize_ch(channel)
        if self._current_channel != ch_yoko:
            self.send_command(f"INP:CHAN {ch_yoko}")
            self._current_channel = ch_yoko

    def _query(self, cmd: str, delay_ms: int = 100) -> str:
        if not self._connected:
            return "0"
        try:
            return self.query(cmd, delay_ms=delay_ms)
        except Exception:
            return "0"

    # ================================================================
    #  1. 基础设置
    # ================================================================

    def initialize(self):
        """
        完整初始化：调用轻量化重置 + FORMAT + 默认量程。
        """
        self._send_initial_commands()
        self.send_command("FORMAT DATA REAL")
        self.set_voltage_auto_range(0, True)
        self.set_voltage_auto_range(1, True)
        self.set_current_auto_range(0, True)
        self.set_current_auto_range(1, True)

    # ── 支持的量程档位（硬编码）───────────────────────────────
    # 电压档位（V）
    _VOLTAGE_RANGES = [600.0, 300.0, 150.0, 60.0, 30.0, 15.0]
    # 电流档位（A）
    _CURRENT_RANGES = [20.0, 10.0, 5.0, 2.0, 1.0, 0.5]

    def set_voltage_range(self, channel, range_value: float):
        """
        设置电压量程为指定档位值（V）。
        channel: "CH1"/"CH2" 字符串 或 0/1 整数
        range_value: 量程档位值，如 300.0
        """
        ch = self._normalize_ch(channel)
        self.send_command("VOLTAGE:INPUT %d" % (ch + 1))
        self.send_command("VOLTAGE:RANGE %s" % range_value)

    def set_voltage_range_auto(self, channel, voltage: float):
        """
        根据测试电压值自动选择合适的电压档位并设置。

        选档规则：
          - 在 _VOLTAGE_RANGES 中找 ≥ voltage 的最小档位
          - 若无满足条件的档，则用最大档（600V）

        Args:
            channel: "CH1"/"CH2" 字符串 或 0/1 整数
            voltage: 测试电压值（V）
        """
        ranges = sorted(self._VOLTAGE_RANGES)   # 升序 [15, 30, 60, 150, 300, 600]
        candidates = [r for r in ranges if r >= voltage]
        chosen = candidates[0] if candidates else ranges[-1]   # 无满足则用最大档
        self.set_voltage_range(channel, chosen)
        logger.info(
            f"[WT322E] CH{channel} 电压 {voltage}V → 自动选档 {chosen}V"
        )

    def set_current_range(self, channel, range_value: float):
        """
        设置电流量程为指定档位值（A）。
        channel: "CH1"/"CH2" 字符串 或 0/1 整数
        range_value: 量程档位值，如 5.0
        """
        ch = self._normalize_ch(channel)
        self.send_command("CURRENT:INPUT %d" % (ch + 1))
        self.send_command("CURRENT:RANGE %s" % range_value)

    def set_current_range_auto(self, channel, current: float):
        """
        根据测试电流值自动选择合适的电流档位并设置。

        选档规则：
          - 在 _CURRENT_RANGES 中找 ≥ current 的最小档位
          - 若无满足条件的档，则用最大档（20A）

        Args:
            channel: "CH1"/"CH2" 字符串 或 0/1 整数
            current: 测试电流值（A）
        """
        ranges = sorted(self._CURRENT_RANGES)   # 升序 [0.5, 1, 2, 5, 10, 20]
        candidates = [r for r in ranges if r >= current]
        chosen = candidates[0] if candidates else ranges[-1]   # 无满足则用最大档
        self.set_current_range(channel, chosen)
        logger.info(
            f"[WT322E] CH{channel} 电流 {current}A → 自动选档 {chosen}A"
        )

    def lock_minimum_current_range(self, channel=1) -> float:
        """
        将电流量程锁定为最小档位（0.5A），用于待机功耗等小电流测量。

        基于硬编码 _CURRENT_RANGES：
          - 最小档为 0.5A（500mA），直接锁定该档

        Args:
            channel: UI 通道标识，"CH1"/"CH2" 字符串 或 0/1 整数，默认 CH1

        Returns:
            实际设置的电流量程档位，A 为单位
        """
        ranges = sorted(self._CURRENT_RANGES)   # 升序 [0.5, 1, 2, 5, 10, 20]
        chosen = ranges[0]   # 最小档 0.5A
        self.set_current_range(channel, chosen)
        logger.info(f"[WT322E] CH{channel} 电流量程锁定最小档 → {chosen}A")
        return chosen

    def set_power_range(self, channel, range_value: float):
        """设置功率量程 (W)。channel: "CH1"/"CH2" 或 0/1（WT322E 功率量程为仪器级，不区分通道）"""
        # WT322E 功率量程无通道参数，全局生效
        self.send_command(f":INP:POW:RANG {range_value}")

    def set_voltage_auto_range(self, channel, enabled: bool = True):
        """设置电压自动量程。channel: "CH1"/"CH2" 或 0/1（WT322E 通道格式：CH1 / CH2）"""
        val = "ON" if enabled else "OFF"
        ch = self._normalize_ch(channel)
        self.send_command(f":VOLTAGE:AUTO CH{ch}, {val}")

    def set_current_auto_range(self, channel, enabled: bool = True):
        """设置电流自动量程。channel: "CH1"/"CH2" 或 0/1（WT322E 通道格式：CH1 / CH2）"""
        val = "ON" if enabled else "OFF"
        ch = self._normalize_ch(channel)
        self.send_command(f":CURRENT:AUTO CH{ch}, {val}")

    def get_voltage_ranges(self, channel) -> list:
        """
        获取 WT322E 支持的电压量程档位列表（硬编码，不依赖 SCPI 查询）。

        电压档位（V）：600 / 300 / 150 / 60 / 30 / 15

        Args:
            channel: UI 通道标识（"CH1"/"CH2" 或 0/1），仅用于签名兼容

        Returns:
            [600.0, 300.0, 150.0, 60.0, 30.0, 15.0]
        """
        return [600.0, 300.0, 150.0, 60.0, 30.0, 15.0]

    def get_current_ranges(self, channel) -> list:
        """
        获取 WT322E 支持的电流量程档位列表（硬编码，不依赖 SCPI 查询）。

        电流档位（A）：20 / 10 / 5 / 2 / 1 / 0.5

        Args:
            channel: UI 通道标识（"CH1"/"CH2" 或 0/1），仅用于签名兼容

        Returns:
            [20.0, 10.0, 5.0, 2.0, 1.0, 0.5]
        """
        return [20.0, 10.0, 5.0, 2.0, 1.0, 0.5]

    # ================================================================
    #  2. 测试设置
    # ================================================================

    def set_wiring_mode(self, mode: str):
        """设置接线模式：1P2W / 1P3W / 3P3W / 3P4W"""
        mode = mode.upper()
        valid = ["1P2W", "1P3W", "3P3W", "3P4W"]
        if mode not in valid:
            raise ValueError(f"Invalid wiring mode: {mode}")
        self.send_command(f":INP:MODE {mode}")

    def set_input_type(self, input_type: str):
        """设置输入类型：AC / DC / ACDC"""
        input_type = input_type.upper()
        valid = ["AC", "DC", "ACDC"]
        if input_type not in valid:
            raise ValueError(f"Invalid input type: {input_type}")
        self.send_command(f":INP:TYPE {input_type}")

    def set_average_filter(self, enabled: bool = True, count: int = 16):
        """设置平均滤波器"""
        stat = "ON" if enabled else "OFF"
        self.send_command(f":AVER:STAT {stat}")
        self.send_command(f":AVER:COUN {count}")

    def reset_zero(self, channel):
        """校零。channel: "CH1"/"CH2" 或 0/1"""
        ch_yoko = self._normalize_ch(channel)
        self.send_command(f":INP:ZERO {ch_yoko}")

    # ================================================================
    #  3. 积分测试功能
    # ================================================================

    def start_integration(self):
        """启动积分测试"""
        self.send_command(":INTEGR:START")
        self._integration_running = True
        self._integration_start_time = time.time()

    def stop_integration(self):
        """停止积分测试"""
        self.send_command(":INTEGR:STOP")
        self._integration_running = False
        if self._integration_start_time is not None:
            self._integration_time += time.time() - self._integration_start_time
            self._integration_start_time = None

    def reset_integration(self):
        """重置积分值"""
        self.send_command(":INTEGR:RESET")
        self._integration_running = False
        self._integration_start_time = None
        self._integration_time = 0.0
        self._integration_wh = {}

    def get_integrated_energy(self, channel: int) -> float:
        """获取累积能量 (Wh)"""
        if not self._connected:
            return 0.0
        try:
            ch_yoko = channel + 1
            resp = self.query(f":INTEGR:VAL? {ch_yoko}", delay_ms=200)
            wh = float(resp.strip())
            self._integration_wh[channel] = wh
            return wh
        except Exception:
            return self._integration_wh.get(channel, 0.0)

    def get_integration_time(self) -> float:
        """获取当前积分时长 (s)"""
        elapsed = 0.0
        if self._integration_start_time is not None:
            elapsed = time.time() - self._integration_start_time
        return self._integration_time + elapsed

    def get_integration_status(self) -> dict:
        """查询积分状态"""
        return {
            "running": self._integration_running,
            "wh": round(self.get_integrated_energy(0), 6),
            "time": round(self.get_integration_time(), 3),
            "limit": "none",
        }

    # ================================================================
    #  4. 谐波电流测试功能
    # ================================================================

    def set_harmonic_mode(self, enabled: bool = True):
        """开启或关闭谐波分析模式"""
        val = "ON" if enabled else "OFF"
        self.send_command(f":HARM:MODE {val}")

    def set_harmonic_order_limit(self, max_order: int):
        """设置谐波分析最高次数"""
        self.send_command(f":HARM:ORD {max_order}")

    def get_thd(self, channel: int) -> float:
        """获取电流 THD (%)"""
        if not self._connected:
            return 0.0
        try:
            ch_yoko = channel + 1
            resp = self.query(f":HARM:THD? {ch_yoko}", delay_ms=200)
            return float(resp.strip())
        except Exception:
            return 0.0

    def get_harmonic_value(self, channel: int, order: int) -> float:
        """获取指定次谐波电流值 (A)"""
        if not self._connected:
            return 0.0
        try:
            ch_yoko = channel + 1
            resp = self.query(f":HARM:DATA? {ch_yoko},{order}", delay_ms=200)
            return float(resp.strip())
        except Exception:
            return 0.0

    def get_all_harmonics(self, channel: int) -> dict:
        """获取全部已分析谐波的值"""
        if not self._connected:
            return {"thd": 0.0, "orders": {}}

        thd = self.get_thd(channel)

        try:
            max_order = int(self.query(":HARM:ORD?", delay_ms=100).strip())
        except Exception:
            max_order = 40

        orders = {}
        for order in range(2, max_order + 1):
            try:
                val = self.get_harmonic_value(channel, order)
                if val > 0:
                    orders[order] = val
            except Exception:
                pass

        return {"thd": thd, "orders": orders}

    # ================================================================
    #  基本测量（便捷方法）
    # ================================================================

    def measure_voltage(self, channel: int = 0) -> float:
        """测量电压 (Vrms)。channel: 0=CH1, 1=CH2"""
        self._select_channel(channel)
        try:
            return abs(float(self.query("VOLTAGE?", delay_ms=100)))
        except Exception:
            return 0.0

    def measure_current(self, channel: int = 0) -> float:
        """测量电流 (Arms)。channel: 0=CH1, 1=CH2"""
        self._select_channel(channel)
        try:
            return abs(float(self.query("CURRENT?", delay_ms=100)))
        except Exception:
            return 0.0

    def measure_power(self, channel: int = 0) -> float:
        """测量有功功率 (W)。channel: 0=CH1, 1=CH2"""
        self._select_channel(channel)
        try:
            return float(self.query("POWER?", delay_ms=100))
        except Exception:
            return 0.0

    def measure_power_factor(self, channel: int = 0) -> float:
        """测量功率因数 (PF)。channel: 0=CH1, 1=CH2"""
        self._select_channel(channel)
        try:
            return float(self.query("PF?", delay_ms=100))
        except Exception:
            return 0.0

    def measure_frequency(self, channel: int = 0) -> float:
        """测量频率 (Hz)"""
        self._select_channel(channel)
        try:
            return float(self.query("FREQUENCY?", delay_ms=100))
        except Exception:
            return 0.0

    def measure_all_channels(self) -> dict:
        """一次性读取全部通道测量值"""
        result = {}
        for ch in [1, 2]:
            self._select_channel(ch)
            result[ch - 1] = {
                "voltage": self.measure_voltage(ch),
                "current": self.measure_current(ch),
                "power":   self.measure_power(ch),
                "pf":      self.measure_power_factor(ch),
                "freq":    self.measure_frequency(ch),
            }
        return result
