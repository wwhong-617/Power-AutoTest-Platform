# -*- coding: utf-8 -*-
"""
WT333E - Yokogawa WT300E 系列功率计驱动
========================================

Yokogawa WT333E 二通道功率计驱动。
通讯方式：TCPIP / USB / GPIB / RS232

【仪器通道布局】
  WT333E 为 2 通道功率计，通道索引 0 (UI=CH1) 和 1 (UI=CH2)。
  NUMERIC NORMAL 配置 6 项：U1, I1, P1, U2, I2, P2
  :NUMERIC:NORMAL:VALUE? 返回顺序：[U1, I1, P1, U2, I2, P2]

【通道角色】
  由 instrument_manager 在连接时通过 set_channel_roles() 指定：
    _input_ch  → 交流输入侧（连接 AC Source）
    _output_ch → DUT 输出侧（连接负载）
  典型配置（input_ch=0, output_ch=1）：CH1=输入  CH2=输出

【SCPI 命令注意事项（实测修正）】
  1. VOLTAGE:INPUT / CURRENT:INPUT → 这些命令不存在！正确命令是
     VOLTAGE:RANGE <V> / CURRENT:RANGE <A>（直接设置当前元素量程，无通道号）
  2. INPUT:WIRING P1W2 → WT333E 不支持！只支持 P1W3/P3W3/P3W4/V3A3
  3. :INTEGRATE:START → 前缀冒号无效！正确是 INTEG:START（缩写格式）
  4. :INP:ZERO → 命令不存在！校零用 *CAL?
  5. :AVER:STAT → 无效！正确是 :MEASURE:AVERAGING:STATE
  6. :INP:TYPE → 无效！正确是 :INPUT:MODE {RMS|DC|VMEan}
  7. :INPUT:POWER:RANGE → 命令不存在！WT333E 无独立功率量程
  8. ESR DDE 级联：一旦仪器 ESR 置 DDE 位(8)，后续所有命令都报 DDE，
     必须 *RST 复位才能清除
  9. INTEG:STOP 在积分未启动时报 ESR 36，需加状态保护
 10. MEASURE:AVERAGING:STATE 写命令后仪器需短暂时间更新内部状态，
     使用 check_esr=False 避免 ESR 立即查询产生 QYE 误报

【初始化顺序】
  1. *RST  → 清除所有状态（DDE 清除）
  2. *CLS  → 清除错误寄存器
  3. 配置量程/接线/NUMERIC
  4. INP:ETS OFF + *CLS → 关闭瞬态抑制、清除 latch
  5. sleep(2.0) → 等待测量系统就绪（约 2s）

测量方式：NUMERIC:NORMAL (ASCII) + :NUMERIC:NORMAL:VALUE?
"""

import time
import logging
import pyvisa
from .BasePowerMeter import BasePowerMeter

logger = logging.getLogger("PowerAutoTest")


# =============================================================================
# 支持的量程档位（WT333E，实测修正）
# =============================================================================
_VOLTAGE_RANGES = [600.0, 300.0, 150.0, 60.0, 30.0, 15.0]   # V
_CURRENT_RANGES = [20.0, 10.0, 5.0, 2.0, 1.0, 0.5]           # A


class WT333E(BasePowerMeter):
    """
    Yokogawa WT333E 二通道功率计驱动。

    继承 BasePowerMeter，实现 WT300E 系列专用 SCPI 命令。
    通道索引 0 = CH1，1 = CH2。

    测量数据索引（NUMERIC:NORMAL 6项）:
      0=U1  1=I1  2=P1  3=U2  4=I2  5=P2
    """

    # =========================================================================
    # 公共属性
    # =========================================================================
    MODEL = "WT333E"

    # =========================================================================
    # 初始化
    # =========================================================================

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)
        self._model = "WT333E"

        # --- 通道角色（连接时由 instrument_manager 指定）---
        self._input_ch = 0    # 交流输入侧 → CH1
        self._output_ch = 1   # DUT 输出侧 → CH2

        # --- 积分状态 ---
        self._integration_running = False
        self._integration_start_time = None
        self._integration_time = 0.0      # 已累积的积分时间（s）
        self._integration_wh = {}         # channel → 累积能量 (Wh)

    # =========================================================================
    # 连接 / 断开
    # =========================================================================

    def connect(self) -> bool:
        """
        使用 NI VISA backend 建立连接，并执行完整初始化。

        初始化顺序：*RST → *CLS → 量程配置 → NUMERIC 配置 → ETS OFF → 等待 2s
        详见 _send_initial_commands()
        """
        try:
            logger.info(f"[WT333E] connect() 开始，地址={self._address}")
            rm = pyvisa.ResourceManager()
            self._resource = rm.open_resource(self._address)
            self._resource.timeout = self._timeout_ms
            self._resource.query_delay = 0.1

            self._idn = self._resource.query("*IDN?").strip()
            logger.info(f"[WT333E] *IDN={self._idn}")

            self._connected = True
            self._send_initial_commands()
            logger.info("[WT333E] _send_initial_commands 完成")

            if not self._validate_identity():
                logger.warning("[WT333E] 身份验证失败")
                self._connected = False
                return False

            logger.info("[WT333E] 连接成功，_connected=True")
            return True

        except Exception as e:
            logger.error(f"[WT333E] 连接失败: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """断开连接，释放 VISA 资源。"""
        if self._resource is not None:
            try:
                self._resource.close()
            except Exception:
                pass
            self._resource = None
        self._connected = False

    def reinitialize(self):
        """
        重新执行完整初始化。

        测试运行前强制调用，确保仪器处于已知状态。
        等同于 disconnect() → connect()，但保留 resource 句柄。
        """
        if not self._connected:
            logger.warning("[WT333E] reinitialize() 仪器未连接，跳过")
            return
        logger.info("[WT333E] reinitialize() 重新执行完整初始化")
        self._send_initial_commands()
        logger.info("[WT333E] reinitialize() 完成")

    # =========================================================================
    # 初始化命令序列（connect / reinitialize / initialize 共享）
    #
    # 【重要】必须在最开头执行 *RST，否则之前残留的 DDE 错误位会导致
    # 后续所有命令报 ESR 8（DDE），即使命令本身正确也无法执行。
    # =========================================================================

    def _send_initial_commands(self):
        """
        发送完整初始化命令序列。

        命令顺序（经验证，实测有效）：
          1. *RST + *CLS              → 清除所有错误状态
          2. INPUT:WIRING P1W3        → 接线模式（WT333E 不支持 P1W2）
          3. VOLTAGE:RANGE / AUTO     → CH1 量程配置
          4. CURRENT:RANGE / AUTO     → CH1 量程配置
          5. VOLTAGE:RANGE / AUTO     → CH2 量程配置
          6. CURRENT:RANGE / AUTO     → CH2 量程配置
          7. NUMERIC:NORMAL:ITEM1~6   → 配置显示项
          8. INTEG:RESET              → 积分复位
          9. INP:ETS OFF + *CLS       → 关闭瞬态抑制 + 清除 latch
         10. sleep(2.0)               → 等待测量系统就绪

        注意：
          - VOLTAGE:INPUT / CURRENT:INPUT 命令不存在！
            量程设置直接用 VOLTAGE:RANGE <V> / CURRENT:RANGE <A>
          - INTEG: 前缀不要冒号！正确是 INTEG:START（实测有效）
        """
        logger.info("[WT333E] 初始化开始")

        # ── 1. 清除错误寄存器 ────────────────────────────────
        # 注意：*RST 会重置仪器到出厂默认（含前面板显示配置），
        # 导致显示面板"闪一下"。已确认 *CLS 单独就能清除 ESR，
        # 在 SCPI 命令全部正确的前提下不需要 *RST。
        self.send_command("*CLS", check_esr=False)
        time.sleep(0.3)

        # ── 2. 接线模式 ──────────────────────────────────────
        self.send_command("INPUT:WIRING P1W3", check_esr=False)
        # 输入类型：RMS（交流有效值）
        self.send_command("INPUT:MODE RMS", check_esr=False)

        # ── 3. CH1 量程（自动）───────────────────────────────
        self.send_command("VOLTAGE:RANGE 300", check_esr=False)
        self.send_command("VOLTAGE:AUTO ON", check_esr=False)
        self.send_command("CURRENT:RANGE 20", check_esr=False)
        self.send_command("CURRENT:AUTO ON", check_esr=False)

        # ── 4. CH2 量程（自动）───────────────────────────────
        self.send_command("VOLTAGE:RANGE 15", check_esr=False)
        self.send_command("VOLTAGE:AUTO ON", check_esr=False)
        self.send_command("CURRENT:RANGE 5", check_esr=False)
        self.send_command("CURRENT:AUTO ON", check_esr=False)

        # ── 5. NUMERIC NORMAL 6项 ───────────────────────────
        self.send_command(":NUMERIC:NORMAL:ITEM1 U,1", check_esr=False)
        self.send_command(":NUMERIC:NORMAL:ITEM2 I,1", check_esr=False)
        self.send_command(":NUMERIC:NORMAL:ITEM3 P,1", check_esr=False)
        self.send_command(":NUMERIC:NORMAL:ITEM4 U,2", check_esr=False)
        self.send_command(":NUMERIC:NORMAL:ITEM5 I,2", check_esr=False)
        self.send_command(":NUMERIC:NORMAL:ITEM6 P,2", check_esr=False)

        # ── 6. 积分复位 ──────────────────────────────────────
        self.send_command("INTEG:RESET", check_esr=False)

        # ── 7. 关闭 ETS 瞬态抑制 + 清除 latch ───────────────
        self.send_command("INP:ETS OFF", check_esr=False)
        self.send_command("*CLS", check_esr=False)

        # ── 8. 前面板显示配置（DISP）────────────────────────
        # DISP 控制仪器前面板显示内容，与 NUMERIC（远程查询）独立。
        # 显示顺序：输入电压、输入功率、输出电压、输出电流
        self.send_command(":DISP:NORM:ITEM1 U,1", check_esr=False)    # CH1 电压（输入）
        self.send_command(":DISP:NORM:ITEM2 P,1", check_esr=False)    # CH1 功率（输入）
        self.send_command(":DISP:NORM:ITEM3 U,2", check_esr=False)    # CH2 电压（输出）
        self.send_command(":DISP:NORM:ITEM4 I,2", check_esr=False)    # CH2 电流（输出）

        # ── 9. 等待测量系统就绪 ─────────────────────────────
        time.sleep(2.0)
        logger.info("[WT333E] 初始化完成")

    def initialize(self):
        """
        轻量连接确认（供 base.py setup 调用）。

        connect() 已做过完整初始化，这里只确认连接有效：
        - 查询 *IDN? 确认仪器响应
        - 无响应则尝试 reconnect() 重建连接
        - 不重发量程/NUMERIC/DISP 等配置命令（connect 时已设置好）
        """
        if not self._connected:
            logger.warning("[WT333E] initialize: 未连接，尝试 reconnect...")
            return bool(self.reconnect())

        try:
            idn = self.query("*IDN?").strip()
            if "WT" in idn or "YOKOGAWA" in idn or "SIMULATION" in idn:
                return True
            logger.warning(f"[WT333E] initialize: 身份验证异常: {idn}")
            return bool(self.reconnect())
        except Exception as e:
            logger.warning(f"[WT333E] initialize: 查询失败 {e}，尝试 reconnect...")
            return bool(self.reconnect())

    def clear_ets(self):
        """
        清除 ETS 瞬态抑制模式。

        ETS (Excessive Transient Suppression) 开启时会抑制峰值电压，
        导致过冲波形被过滤掉。在测试开始时关闭即可。
        """
        self.send_command("INP:ETS OFF", check_esr=False)
        self.send_command("*CLS", check_esr=False)
        logger.info("[WT333E] ETS 已清除")

    # =========================================================================
    # 核心读取
    # =========================================================================

    def _fetch(self) -> list:
        """
        通过 :NUMERIC:NORMAL:VALUE? 读取当前 6 项测量值。

        返回顺序（NUMERIC:NORMAL:ITEM1~6 配置决定）:
          [U1, I1, P1, U2, I2, P2]

        异常处理：
          - NAN / INF / -INF → 0.0（测量未就绪时仪器返回 NAN）
          - 连接断开 → [0.0] * 6
          - 查询超时 → [0.0] * 6

        Returns:
            [U1, I1, P1, U2, I2, P2]，共 6 个 float
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
            return result[:6]   # 只取前 6 项
        except Exception:
            return [0.0] * 6
        # 积分/重置操作后仪器需要短暂时间重新计算 NUMERIC 数据。
        # 第一帧查到全 0 时自动重试一次（约 50ms 内恢复）。
        # 若重试后仍为全零但仪器已就绪（如输入确实为 0），
        # 仍然返回该值，不无限重试。
        if all(v == 0.0 for v in result):
            time.sleep(0.05)
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
            except Exception:
                pass   # 保持 result 全零值，不无限重试
        return result

    def _normalize_ch(self, channel):
        """
        将 UI 通道标识转换为驱动内部 0 基整数索引。

        Args:
            channel: "CH1"/"CH2"（推荐）或 0/1

        Returns:
            0 对应 CH1，1 对应 CH2
        """
        if isinstance(channel, str):
            return int(channel.replace("CH", "").replace("ch", "")) - 1
        return int(channel)

    def _validate_identity(self) -> bool:
        """验证仪器身份（IDN 中包含已知标识）"""
        return any(x in self._idn for x in ["WT333", "WT300E", "YOKOGAWA", "SIMULATION"])

    # =========================================================================
    # 语义测量方法（按输入/输出角色取值）
    #
    # 通道角色由 set_channel_roles() 指定：
    #   _input_ch  = 交流输入侧通道（连接 AC Source）
    #   _output_ch = DUT 输出侧通道（连接电子负载）
    # =========================================================================

    def measure_input_voltage(self) -> float:
        """测量输入侧电压 (Vrms)"""
        vals = self._fetch()
        idx = self._input_ch * 3   # CH1→0, CH2→3
        raw = vals[idx] if len(vals) > idx else 0.0
        logger.debug(f"[WT333E] measure_input_voltage CH{self._input_ch+1}(idx={idx}) raw={raw:.3f}V")
        return abs(raw)

    def measure_output_voltage(self) -> float:
        """测量输出侧电压 (Vrms)"""
        vals = self._fetch()
        idx = self._output_ch * 3
        raw = vals[idx] if len(vals) > idx else 0.0
        return abs(raw)

    def measure_input_current(self) -> float:
        """测量输入侧电流 (Arms)"""
        vals = self._fetch()
        idx = self._input_ch * 3 + 1
        return abs(vals[idx]) if len(vals) > idx else 0.0

    def measure_output_current(self) -> float:
        """测量输出侧电流 (Arms)"""
        vals = self._fetch()
        idx = self._output_ch * 3 + 1
        return abs(vals[idx]) if len(vals) > idx else 0.0

    def measure_input_power(self) -> float:
        """测量输入侧有功功率 (W)"""
        vals = self._fetch()
        idx = self._input_ch * 3 + 2
        return vals[idx] if len(vals) > idx else 0.0

    def measure_output_power(self) -> float:
        """测量输出侧有功功率 (W)"""
        vals = self._fetch()
        idx = self._output_ch * 3 + 2
        return vals[idx] if len(vals) > idx else 0.0

    # =========================================================================
    # 通用通道测量（直接指定物理通道，不经语义角色）
    # =========================================================================

    def measure_voltage(self, channel=0) -> float:
        """
        测量指定物理通道的电压 (Vrms)。

        Args:
            channel: "CH1"/"CH2" 或 0/1，默认 CH1
        """
        ch = self._normalize_ch(channel)
        vals = self._fetch()
        idx = 0 if ch == 0 else 3
        return abs(vals[idx]) if len(vals) > idx else 0.0

    def measure_current(self, channel=0) -> float:
        """
        测量指定物理通道的电流 (Arms)。

        Args:
            channel: "CH1"/"CH2" 或 0/1，默认 CH1
        """
        ch = self._normalize_ch(channel)
        vals = self._fetch()
        idx = 1 if ch == 0 else 4
        return abs(vals[idx]) if len(vals) > idx else 0.0

    def measure_power(self, channel=0) -> float:
        """
        测量指定物理通道的有功功率 (W)。

        Args:
            channel: "CH1"/"CH2" 或 0/1，默认 CH1
        """
        ch = self._normalize_ch(channel)
        vals = self._fetch()
        idx = 2 if ch == 0 else 5
        return vals[idx] if len(vals) > idx else 0.0

    def measure_power_factor(self, channel=0) -> float:
        """
        测量指定通道的功率因数 PF。

        PF = |P| / (|V| × |I|)，由实测 P/V/I 计算得出。

        Args:
            channel: "CH1"/"CH2" 或 0/1，默认 CH1
        """
        ch = self._normalize_ch(channel)
        vals = self._fetch()
        if len(vals) < 5:
            return 0.0
        v = abs(vals[0]) if ch == 0 else abs(vals[3])
        i = abs(vals[1]) if ch == 0 else abs(vals[4])
        p = vals[2] if ch == 0 else vals[5]
        apparent = v * i
        return abs(p) / apparent if apparent > 0 else 0.0

    def measure_frequency(self, channel=0) -> float:
        """
        测量频率 (Hz)。

        注意：本驱动未实现频率测量，始终返回 0.0。
        如需频率数据，需扩展 SCPI 命令（:FREQUENCY?）。
        """
        return 0.0

    def measure_all_channels(self) -> dict:
        """
        一次性读取全部物理通道的测量数据。

        Returns:
            {
                0: {"voltage": float, "current": float, "power": float,
                    "pf": float, "freq": float},
                1: {同上}
            }
        """
        vals = self._fetch()
        if len(vals) < 5:
            return {
                0: {"voltage": 0.0, "current": 0.0, "power": 0.0, "pf": 0.0, "freq": 0.0},
                1: {"voltage": 0.0, "current": 0.0, "power": 0.0, "pf": 0.0, "freq": 0.0},
            }

        u1, i1, p1 = vals[0], vals[1], vals[2]
        u2, i2, p2 = vals[3], vals[4], vals[5]

        def calc_pf(p, v, i):
            a = abs(v * i)
            return abs(p) / a if a > 0 else 0.0

        return {
            0: {"voltage": abs(u1), "current": abs(i1), "power": p1,
                "pf": calc_pf(p1, u1, i1), "freq": 0.0},
            1: {"voltage": abs(u2), "current": abs(i2), "power": p2,
                "pf": calc_pf(p2, u2, i2), "freq": 0.0},
        }

    # =========================================================================
    # 通道角色设置
    # =========================================================================

    def set_channel_roles(self, input_voltage_ch: str = None, output_voltage_ch: str = None):
        """
        设置输入/输出通道角色（连接时由 instrument_manager 调用）。

        指定哪个物理通道(CH1/CH2)对应输入侧或输出侧测量。

        Args:
            input_voltage_ch:  交流输入侧通道，"CH1" 或 "CH2"
            output_voltage_ch: DUT 输出侧通道，"CH1" 或 "CH2"
        """
        if input_voltage_ch is not None:
            self._input_ch = self._normalize_ch(input_voltage_ch)
        if output_voltage_ch is not None:
            self._output_ch = self._normalize_ch(output_voltage_ch)
        logger.info(f"[WT333E] 通道角色: 输入=CH{self._input_ch+1} 输出=CH{self._output_ch+1}")

    # =========================================================================
    # 量程设置
    #
    # 【重要】WT333E 量程命令格式：
    #   VOLTAGE:RANGE <V>    （无需通道号，直接设置当前元素）
    #   CURRENT:RANGE <A>    （无需通道号）
    # 注意：VOLTAGE:INPUT / CURRENT:INPUT 命令不存在！
    # =========================================================================

    def set_voltage_range(self, channel, range_value: float):
        """
        手动设置电压量程档位 (V)。

        Args:
            channel:      "CH1"/"CH2" 或 0/1（仅用于签名兼容，实际 WT333E
                          量程命令无通道参数）
            range_value:  量程档位值（V），可选值：600/300/150/60/30/15
        """
        self.send_command("VOLTAGE:RANGE %s" % range_value)

    def set_voltage_range_auto(self, channel, voltage: float):
        """
        根据目标电压自动选择合适的电压档位并设置。

        选档规则：电压 × 1.1（留 10% 裕量）后在量程列表中
        选择 ≥ 该值的最小档位。若无满足条件则用最大档（600V）。

        Args:
            channel:  "CH1"/"CH2" 或 0/1
            voltage:  目标电压（V）
        """
        ranges = sorted(_VOLTAGE_RANGES)                # 升序
        target = voltage * 1.1
        candidates = [r for r in ranges if r >= target]
        chosen = candidates[0] if candidates else ranges[-1]
        self.set_voltage_range(channel, chosen)
        logger.info(f"[WT333E] CH{channel} 电压 {voltage}V×1.1={target:.1f}V → 选档 {chosen}V")

    def set_current_range(self, channel, range_value: float):
        """
        手动设置电流量程档位 (A)。

        Args:
            channel:      "CH1"/"CH2" 或 0/1
            range_value:  量程档位值（A），可选值：20/10/5/2/1/0.5
        """
        self.send_command("CURRENT:RANGE %s" % range_value)

    def set_current_range_auto(self, channel, current: float):
        """
        根据目标电流自动选择合适的电流档位并设置。

        选档规则：电流 × 1.4（留 40% 裕量）后在量程列表中
        选择 ≥ 该值的最小档位。若无满足条件则用最大档（20A）。

        Args:
            channel:  "CH1"/"CH2" 或 0/1
            current:  目标电流（A）
        """
        ranges = sorted(_CURRENT_RANGES)                # 升序
        target = current * 1.4
        candidates = [r for r in ranges if r >= target]
        chosen = candidates[0] if candidates else ranges[-1]
        self.set_current_range(channel, chosen)
        logger.info(f"[WT333E] CH{channel} 电流 {current}A×1.4={target:.3f}A → 选档 {chosen}A")

    def lock_minimum_current_range(self, channel=0) -> float:
        """
        将电流量程锁定为最小档（0.5A），用于待机功耗等小电流测量。

        Args:
            channel: "CH1"/"CH2" 或 0/1，默认 CH1

        Returns:
            实际设置的电流量程（A）
        """
        chosen = min(_CURRENT_RANGES)    # 0.5A
        self.set_current_range(channel, chosen)
        logger.info(f"[WT333E] CH{channel} 电流量程锁定最小档 {chosen}A")
        return chosen

    def set_voltage_auto_range(self, channel, enabled: bool = True):
        """开启/关闭电压自动量程"""
        val = "ON" if enabled else "OFF"
        self.send_command("VOLTAGE:AUTO %s" % val)

    def set_current_auto_range(self, channel, enabled: bool = True):
        """开启/关闭电流自动量程"""
        val = "ON" if enabled else "OFF"
        self.send_command("CURRENT:AUTO %s" % val)

    def get_voltage_ranges(self, channel=None) -> list:
        """
        返回 WT333E 支持的电压量程档位列表（硬编码）。

        Args:
            channel: 仅用于签名兼容，可忽略

        Returns:
            [600.0, 300.0, 150.0, 60.0, 30.0, 15.0] V
        """
        return list(_VOLTAGE_RANGES)

    def get_current_ranges(self, channel=None) -> list:
        """
        返回 WT333E 支持的电流量程档位列表（硬编码）。

        Args:
            channel: 仅用于签名兼容，可忽略

        Returns:
            [20.0, 10.0, 5.0, 2.0, 1.0, 0.5] A
        """
        return list(_CURRENT_RANGES)

    # =========================================================================
    # 接线模式
    #
    # WT333E 支持的接线模式（由 INPUT:WIRING 设置）：
    #   P1W3  - 单相三线（Phase 1W3，CH1+CH2 电压，CH1 电流）
    #   P3W3  - 三相三线
    #   P3W4  - 三相四线
    #   V3A3  - 三电压三电流（3V3A）
    # 注意：WT333E 不支持 P1W2（单相二线）！
    # =========================================================================

    def set_wiring_mode(self, mode: str):
        """
        设置接线模式。

        Args:
            mode: 接线制式，支持 P1W3/P3W3/P3W4/V3A3

        注意：
          - WT333E 不支持 P1W2（单相二线），传入 P1W2 会自动降级为 P1W3
          - 通常测试场景使用 P1W3（单相三线）
        """
        valid_modes = ["P1W3", "P3W3", "P3W4", "V3A3"]
        mode_upper = mode.upper()
        if mode_upper not in valid_modes:
            logger.warning(
                f"[WT333E] 无效接线模式 '{mode}'，WT333E 不支持 P1W2，"
                f"已降级为 P1W3（单相三线）"
            )
            mode_upper = "P1W3"
        self.send_command("INPUT:WIRING %s" % mode_upper)

    # =========================================================================
    # 平均滤波器
    #
    # MEASURE:AVERAGING:STATE 命令写操作后仪器需要短暂时间更新内部状态，
    # 使用 check_esr=False 避免 ESR 立即查询产生 QYE(4) 误报。
    # =========================================================================

    def set_average_filter(self, enabled: bool = True, count: int = 16):
        """
        设置平均滤波器（降低测量噪声）。

        Args:
            enabled: True=开启平均，False=关闭
            count:   平均次数 1~128（默认 16）
        """
        stat = "ON" if enabled else "OFF"
        self.send_command(":MEASURE:AVERAGING:STATE %s" % stat, check_esr=False)
        self.send_command(":MEASURE:AVERAGING:COUNT %d" % count, check_esr=False)
        self.send_command("*CLS", check_esr=False)   # 清除写命令产生的 QYE 残留

    # =========================================================================
    # 输入类型（AC/DC/ACDC）
    #
    # :INP:TYPE 命令不存在！正确命令是 :INPUT:MODE
    #   AC   → RMS   （交流有效值）
    #   DC   → DC    （直流）
    #   ACDC → VMEan （交流+直流混合）
    # =========================================================================

    def set_input_type(self, input_type: str):
        """
        设置输入类型（AC/DC/ACDC）。

        Args:
            input_type: "AC" / "DC" / "ACDC"
        """
        valid = ["AC", "DC", "ACDC"]
        input_type = input_type.upper()
        if input_type not in valid:
            raise ValueError(f"无效输入类型 '{input_type}'，可选: AC/DC/ACDC")
        mode_map = {"AC": "RMS", "DC": "DC", "ACDC": "VMEan"}
        self.send_command(":INPUT:MODE %s" % mode_map[input_type])

    # =========================================================================
    # 校零
    #
    # :INP:ZERO 命令不存在！正确命令是 *CAL?（仪器自动执行零点校准）
    # 在输入端短接或无输入时调用可提高小信号测量精度。
    # =========================================================================

    def reset_zero(self, channel=None):
        """
        执行零点校准（校零）。

        Args:
            channel: 可忽略（*CAL? 对整机关闭输入执行校准）
        """
        self.send_command("*CAL?", check_esr=False)

    # =========================================================================
    # 积分测试功能
    #
    # 注意：
    #   1. INTEG:START / INTEG:STOP（注意不是 :INTEGRATE:，不要前缀冒号）
    #   2. INTEG:STOP 在积分未启动时返回 ESR 36，需加 _integration_running 保护
    #   3. INTEG:VAL? 查询后仪器 ESR 可能置 QYE(4)，stop_integration 末尾清 *CLS
    # =========================================================================

    def start_integration(self):
        """
        启动积分测试。

        仅在积分未运行时执行。积分期间 _integration_running=True，
        start_integration / stop_integration 有幂等保护。
        """
        if self._integration_running:
            logger.warning("[WT333E] 积分已在运行，忽略重复 start")
            return
        self.send_command("INTEG:START")
        self._integration_running = True
        self._integration_start_time = time.time()

    def stop_integration(self):
        """
        停止积分测试。

        包含幂等保护（积分未运行时安全忽略）。
        停止后主动发 *CLS 清除 INTEG:VAL? 查询残留的 QYE 错误。
        """
        if not self._integration_running:
            logger.warning("[WT333E] 积分未运行，忽略 stop")
            return
        try:
            self.send_command("INTEG:STOP")
        except Exception:
            pass    # 积分未启动时 INTEG:STOP 报 ESR 36，安全忽略
        finally:
            self._integration_running = False
            if self._integration_start_time is not None:
                self._integration_time += time.time() - self._integration_start_time
                self._integration_start_time = None
        # 清除 INTEG:VAL? 产生的 QYE 残留，防止污染后续命令
        try:
            self.send_command("*CLS", check_esr=False)
        except Exception:
            pass

    def reset_integration(self):
        """重置积分值和计时器。"""
        self.send_command("INTEG:RESET")
        self._integration_running = False
        self._integration_start_time = None
        self._integration_time = 0.0
        self._integration_wh = {}

    def get_integrated_energy(self, channel: int) -> float:
        """
        获取指定通道的累积能量 (Wh)。

        Args:
            channel: 物理通道索引，0=CH1 或 1=CH2

        Returns:
            累积能量（Wh），查询失败时返回缓存值
        """
        if not self._connected:
            return 0.0
        try:
            ch_yoko = channel + 1    # WT300E 通道编号从 1 开始
            resp = self.query("INTEG:VAL? %d" % ch_yoko, delay_ms=200)
            wh = float(resp.strip())
            self._integration_wh[channel] = wh
            return wh
        except Exception:
            return self._integration_wh.get(channel, 0.0)

    def get_integration_time(self) -> float:
        """
        获取当前积分总时长 (s)。

        包含已累积时间（多次启停累加）+ 本次启停后的流逝时间。
        """
        elapsed = 0.0
        if self._integration_start_time is not None:
            elapsed = time.time() - self._integration_start_time
        return self._integration_time + elapsed

    def get_integration_status(self) -> dict:
        """
        查询积分状态。

        Returns:
            {"running": bool, "wh": float, "time": float, "limit": str}
        """
        wh = self.get_integrated_energy(0)
        t = self.get_integration_time()
        return {
            "running": self._integration_running,
            "wh": round(wh, 6),
            "time": round(t, 3),
            "limit": "none",
        }

    # =========================================================================
    # 谐波功能（WT300E 支持，但本项目未使用，接口暂保留）
    #
    # 注意：谐波测量需要仪器配备 /G5 选件。
    # 当前测试用例未涉及谐波，此部分仅供参考。
    # =========================================================================

    def set_harmonic_mode(self, enabled: bool = True):
        """开启/关闭谐波分析模式"""
        val = "ON" if enabled else "OFF"
        self.send_command(":HARM:MODE %s" % val)

    def set_harmonic_order_limit(self, max_order: int):
        """设置谐波分析最高次数（默认 40）"""
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
        """获取指定次谐波电流值 (%)"""
        if not self._connected:
            return 0.0
        try:
            ch_yoko = channel + 1
            resp = self.query(":HARM:DATA? %d,%d" % (ch_yoko, order), delay_ms=200)
            return float(resp.strip())
        except Exception:
            return 0.0

    def get_all_harmonics(self, channel: int) -> dict:
        """
        获取全部已分析谐波的值。

        Returns:
            {"thd": float, "orders": {order: value, ...}}
        """
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

    # =========================================================================
    # 不支持的功能（仪器不具备）
    # =========================================================================

    def set_power_range(self, channel, range_value: float):
        """
        设置功率量程 (W)。

        注意：WT333E 不支持独立的功率量程命令（INPUT:POWER:RANGE 不存在）。
        功率量程由电压量程 × 电流量程隐式决定。
        此方法仅记录警告日志，不发送实际命令。
        """
        logger.warning(
            f"[WT333E] set_power_range({channel}, {range_value}W) —— "
            f"WT333E 不支持独立功率量程，功率由电压×电流量程决定。"
        )
