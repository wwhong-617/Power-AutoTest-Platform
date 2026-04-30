# -*- coding: utf-8 -*-
"""
WT333E - Yokogawa WT300E 系列功率计驱动
========================================

Yokogawa WT333E 功率计驱动（二通道）。
通讯方式：TCPIP / USB

WT333E 为 2 通道功率计，通道索引 0 和 1。

测量方式：NUMERIC:NORMAL + :NUMERIC:NORMAL:VALUE? (ASCII格式)
  - NORMAL 配置 6项：U1, I1, P1, U2, I2, P2
  - :NUMERIC:NORMAL:VALUE? 返回 ASCII 格式 [U1, I1, P1, U2, I2, P2]
"""

import time
import logging
import pyvisa
from .BasePowerMeter import BasePowerMeter

logger = logging.getLogger("PowerAutoTest")


class WT333E(BasePowerMeter):
    """
    Yokogawa WT333E 功率计驱动。
    继承 BasePowerMeter，实现 WT300E 系列专用 SCPI 命令。
    WT333E 为 2 通道功率计，通道索引 0 和 1。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)
        self._model = "WT333E"
        self._integration_running = False
        self._integration_start_time = None
        self._integration_wh = {}
        self._integration_time = 0.0

    # ================================================================
    #  连接
    # ================================================================

    def connect(self) -> bool:
        """使用 NI VISA backend 建立连接"""
        if self._connected:
            return True
        try:
            rm = pyvisa.ResourceManager()
            self._resource = rm.open_resource(self._address)
            self._resource.timeout = self._timeout_ms
            self._resource.query_delay = 0.1
            self._idn = self._resource.query("*IDN?").strip()
            self._connected = True
            self._send_initial_commands()
            if not self._validate_identity():
                self._connected = False
                return False
            return True
        except Exception as e:
            print(f"    [WT333E] Connection failed: {e}")
            self._connected = False
            return False

    def _send_initial_commands(self):
        self.send_command("*CLS", check_esr=False)

    def _validate_identity(self) -> bool:
        if any(x in self._idn for x in ["WT333", "WT300E", "YOKOGAWA", "SIMULATION"]):
            return True
        return False

    # ================================================================
    #  核心读取
    # ================================================================

    def _fetch(self) -> list:
        """
        通过 :NUMERIC:NORMAL:VALUE? 读取当前测量值（NORMAL 模式）。

        NORMAL 配置 6项：U1, I1, P1, U2, I2, P2
        :NUMERIC:NORMAL:VALUE? 返回：[U1, I1, P1, U2, I2, P2] 共6个值

        Returns:
            list: [U1, I1, P1, U2, I2, P2] 共6个值
        """
        if not self._connected:
            return [0.0] * 6
        try:
            resp = self.query(":NUMERIC:NORMAL:VALUE?")
            result = []
            for p in resp.strip().split(","):
                p = p.strip()
                if p in ("NAN", "INF", "-INF", ""):
                    result.append(0.0)
                else:
                    try:
                        result.append(float(p))
                    except ValueError:
                        result.append(0.0)
            # 只取前6项（对应 NORMAL 模式配置的6项）
            return result[:6]
        except Exception:
            return [0.0] * 6

    # ================================================================
    #  1. 初始化
    # ================================================================

    def initialize(self):
        """
        功率计初始化：
          *RST → 通道量程配置 → NUMERIC:NORMAL 配置

        NORMAL 6项：U1, I1, P1, U2, I2, P2
        """
        self.send_command("*RST")
        time.sleep(0.5)
        self.send_command("*CLS", check_esr=False)

        # ---- CH1 通道配置（自动量程）----
        self.send_command("VOLTAGE:INPUT 1")
        self.send_command("CURRENT:INPUT 1")
        self.send_command("VOLTAGE:AUTO ON")
        self.send_command("CURRENT:AUTO ON")
        self.send_command("INPUT:WIRING SINGLE")

        # ---- CH2 通道配置（自动量程）----
        self.send_command("VOLTAGE:INPUT 2")
        self.send_command("CURRENT:INPUT 2")
        self.send_command("VOLTAGE:AUTO ON")
        self.send_command("CURRENT:AUTO ON")
        self.send_command("INPUT:WIRING SINGLE")

        # ---- NUMERIC NORMAL 配置（6项）----
        self.send_command(":NUMERIC:NORMAL:ITEM1 U,1")    # U1: CH1电压（输入）
        self.send_command(":NUMERIC:NORMAL:ITEM2 I,1")    # I1: CH1电流（输入）
        self.send_command(":NUMERIC:NORMAL:ITEM3 P,1")    # P1: CH1功率（输入）
        self.send_command(":NUMERIC:NORMAL:ITEM4 U,2")    # U2: CH2电压（输出）
        self.send_command(":NUMERIC:NORMAL:ITEM5 I,2")    # I2: CH2电流（输出）
        self.send_command(":NUMERIC:NORMAL:ITEM6 P,2")    # P2: CH2功率（输出）

        # ---- 前面板显示配置（4项：输入电压、输入功率、输出电压、输出电流）----
        self.send_command(":DISP:NORM:ITEM1 U,1")    # 输入电压 U1
        self.send_command(":DISP:NORM:ITEM2 P,1")    # 输入功率 P1
        self.send_command(":DISP:NORM:ITEM3 U,2")    # 输出电压 U2
        self.send_command(":DISP:NORM:ITEM4 I,2")    # 输出电流 I2

    # ================================================================
    #  私有工具
    # ================================================================

    def _normalize_ch(self, channel):
        """
        将 UI 通道标识转换为驱动内部 0 基索引。

        UI 字符串（推荐）："CH1" -> 0, "CH2" -> 1
        整数（兼容旧接口）：0 -> 0, 1 -> 1

        Returns:
            0 对应 UI CH1，1 对应 UI CH2
        """
        if isinstance(channel, str):
            return int(channel.replace("CH", "").replace("ch", "")) - 1
        return int(channel)

    # ================================================================
    #  2. 基础量程设置
    # ================================================================

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
          - 电压 × 1.1（留 1/10 裕量）后，在 _VOLTAGE_RANGES 中找 ≥ 该值 的最小档位
          - 若无满足条件的档，则用最大档（600V）

        Args:
            channel: "CH1"/"CH2" 字符串 或 0/1 整数
            voltage: 测试电压值（V）
        """
        ranges = sorted(self._VOLTAGE_RANGES)   # 升序 [15, 30, 60, 150, 300, 600]
        voltage_with_margin = voltage * 1.1
        candidates = [r for r in ranges if r >= voltage_with_margin]
        chosen = candidates[0] if candidates else ranges[-1]   # 无满足则用最大档
        self.set_voltage_range(channel, chosen)
        logger.info(
            f"[WT333E] CH{channel} 电压 {voltage}V → ×1.1={voltage_with_margin:.1f}V → 自动选档 {chosen}V"
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
          - 电流 × 1.4（留 2/5 裕量）后，在 _CURRENT_RANGES 中找 ≥ 该值 的最小档位
          - 若无满足条件的档，则用最大档（20A）

        Args:
            channel: "CH1"/"CH2" 字符串 或 0/1 整数
            current: 测试电流值（A）
        """
        ranges = sorted(self._CURRENT_RANGES)   # 升序 [0.5, 1, 2, 5, 10, 20]
        current_with_margin = current * 1.4
        candidates = [r for r in ranges if r >= current_with_margin]
        chosen = candidates[0] if candidates else ranges[-1]   # 无满足则用最大档
        self.set_current_range(channel, chosen)
        logger.info(
            f"[WT333E] CH{channel} 电流 {current}A → ×1.4={current_with_margin:.3f}A → 自动选档 {chosen}A"
        )

    def lock_minimum_current_range(self, channel=0) -> float:
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
        logger.info(f"[WT333E] CH{channel} 电流量程锁定最小档 → {chosen}A")
        return chosen

    def get_voltage_ranges(self, channel) -> list:
        """
        获取 WT333E 支持的电压量程档位列表（硬编码，不依赖 SCPI 查询）。

        电压档位（V）：600 / 300 / 150 / 60 / 30 / 15

        Args:
            channel: UI 通道标识（"CH1"/"CH2" 或 0/1），仅用于签名兼容

        Returns:
            [600.0, 300.0, 150.0, 60.0, 30.0, 15.0]
        """
        return [600.0, 300.0, 150.0, 60.0, 30.0, 15.0]

    def get_current_ranges(self, channel) -> list:
        """
        获取 WT333E 支持的电流量程档位列表（硬编码，不依赖 SCPI 查询）。

        电流档位（A）：20 / 10 / 5 / 2 / 1 / 0.5

        Args:
            channel: UI 通道标识（"CH1"/"CH2" 或 0/1），仅用于签名兼容

        Returns:
            [20.0, 10.0, 5.0, 2.0, 1.0, 0.5]
        """
        return [20.0, 10.0, 5.0, 2.0, 1.0, 0.5]

    def set_voltage_auto_range(self, channel, enabled: bool = True):
        """设置电压自动量程"""
        val = "ON" if enabled else "OFF"
        ch = self._normalize_ch(channel)
        self.send_command("VOLTAGE:INPUT %d" % (ch + 1))
        self.send_command("VOLTAGE:AUTO %s" % val)

    def set_current_auto_range(self, channel, enabled: bool = True):
        """设置电流自动量程"""
        val = "ON" if enabled else "OFF"
        ch = self._normalize_ch(channel)
        self.send_command("CURRENT:INPUT %d" % (ch + 1))
        self.send_command("CURRENT:AUTO %s" % val)

    def set_wiring_mode(self, mode: str):
        """设置接线模式（2通道统一设置）"""
        self.send_command("VOLTAGE:INPUT 1")
        self.send_command("INPUT:WIRING %s" % mode.upper())
        self.send_command("VOLTAGE:INPUT 2")
        self.send_command("INPUT:WIRING %s" % mode.upper())

    # ================================================================
    #  3. 基本测量
    # ================================================================
    # NORMAL: [U1, I1, P1, U2, I2, P2]
    # 索引:     0    1    2    3    4    5

    def measure_voltage(self, channel=0) -> float:
        """测量电压 (Vrms)。channel: CH1/CH2 字符串 或 0/1 整数，默认 CH1"""
        ch = self._normalize_ch(channel)
        vals = self._fetch()
        idx = 0 if ch == 0 else 3
        return abs(vals[idx]) if len(vals) > idx else 0.0

    def measure_current(self, channel=0) -> float:
        """测量电流 (Arms)。channel: CH1/CH2 字符串 或 0/1 整数，默认 CH1"""
        ch = self._normalize_ch(channel)
        vals = self._fetch()
        idx = 1 if ch == 0 else 4
        return abs(vals[idx]) if len(vals) > idx else 0.0

    def measure_power(self, channel=0) -> float:
        """测量有功功率 (W)。channel: CH1/CH2 字符串 或 0/1 整数，默认 CH1"""
        ch = self._normalize_ch(channel)
        vals = self._fetch()
        idx = 2 if ch == 0 else 5  # CH2 P2 在索引5
        return vals[idx] if len(vals) > idx else 0.0

    def measure_power_factor(self, channel=0) -> float:
        """测量功率因数 (PF)。通过 P/(V*I) 计算。channel: CH1/CH2 或 0/1"""
        ch = self._normalize_ch(channel)
        vals = self._fetch()
        if len(vals) < 5:
            return 0.0
        v = abs(vals[0]) if ch == 0 else abs(vals[3])
        i = abs(vals[1]) if ch == 0 else abs(vals[4])
        p = vals[2] if ch == 0 else 0.0
        apparent = v * i
        return abs(p) / apparent if apparent > 0 else 0.0

    def measure_frequency(self, channel=0) -> float:
        """测量频率 (Hz) - 本驱动未测频率，返回0"""
        return 0.0

    def measure_all_channels(self) -> dict:
        """
        一次性读取全部通道的测量值。

        Returns:
            dict: {
                0: {"voltage": float, "current": float, "power": float, "pf": float, "freq": float},
                1: {"voltage": float, "current": float, "power": float, "pf": float, "freq": float}
            }
        """
        vals = self._fetch()
        if len(vals) < 5:
            return {
                0: {"voltage": 0.0, "current": 0.0, "power": 0.0, "pf": 0.0, "freq": 0.0},
                1: {"voltage": 0.0, "current": 0.0, "power": 0.0, "pf": 0.0, "freq": 0.0},
            }

        u1, i1, p1 = vals[0], vals[1], vals[2]
        u2, i2 = vals[3], vals[4]

        def calc_pf(p, v, i):
            apparent = abs(v * i)
            return abs(p) / apparent if apparent > 0 else 0.0

        return {
            0: {
                "voltage": abs(u1),
                "current": abs(i1),
                "power":   p1,
                "pf":      calc_pf(p1, u1, i1),
                "freq":    0.0,
            },
            1: {
                "voltage": abs(u2),
                "current": abs(i2),
                "power":   0.0,
                "pf":      0.0,
                "freq":    0.0,
            },
        }

    # ================================================================
    #  4. 积分测试功能
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
            resp = self.query(":INTEGR:VAL? %d" % ch_yoko, delay_ms=200)
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
        wh = self.get_integrated_energy(0)
        t = self.get_integration_time()
        return {
            "running": self._integration_running,
            "wh": round(wh, 6),
            "time": round(t, 3),
            "limit": "none",
        }

    # ================================================================
    #  5. 谐波功能
    # ================================================================

    def set_harmonic_mode(self, enabled: bool = True):
        """开启/关闭谐波分析模式"""
        val = "ON" if enabled else "OFF"
        self.send_command(":HARM:MODE %s" % val)

    def set_harmonic_order_limit(self, max_order: int):
        """设置谐波分析最高次数"""
        self.send_command(":HARM:ORD %d" % max_order)

    def get_thd(self, channel: int) -> float:
        """获取电流总谐波畸变率 THD (%)"""
        if not self._connected:
            return 0.0
        try:
            ch_yoko = channel + 1
            resp = self.query(":HARM:THD? %d" % ch_yoko, delay_ms=200)
            return float(resp.strip())
        except Exception:
            return 0.0

    def get_harmonic_value(self, channel: int, order: int) -> float:
        """获取指定次谐波电流值"""
        if not self._connected:
            return 0.0
        try:
            ch_yoko = channel + 1
            resp = self.query(":HARM:DATA? %d,%d" % (ch_yoko, order), delay_ms=200)
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

    def reset_zero(self, channel):
        """校零。channel: CH1/CH2 字符串 或 0/1 整数"""
        ch_yoko = self._normalize_ch(channel) + 1
        self.send_command(":INP:ZERO %d" % ch_yoko)

    def set_average_filter(self, enabled: bool = True, count: int = 16):
        """设置平均滤波器"""
        stat = "ON" if enabled else "OFF"
        self.send_command(":AVER:STAT %s" % stat)
        self.send_command(":AVER:COUN %d" % count)

    def set_input_type(self, input_type: str):
        """设置输入类型 AC/DC/ACDC"""
        input_type = input_type.upper()
        valid = ["AC", "DC", "ACDC"]
        if input_type not in valid:
            raise ValueError("Invalid input type: %s" % input_type)
        self.send_command(":INP:TYPE %s" % input_type)

    def set_power_range(self, channel, range_value: float):
        """设置功率量程 (W)。channel: CH1/CH2 字符串 或 0/1 整数"""
        ch = self._normalize_ch(channel)
        self.send_command(":INP:POW:RANG CH%d, %s" % (ch + 1, range_value))
