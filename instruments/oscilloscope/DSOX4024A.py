# -*- coding: utf-8 -*-
"""
DSOX4024A - Keysight InfiniiVision 4000X 示波器驱动
====================================================

SCPI 命令参考（按类别整理）
══════════════════════════════════════════════════════

初始化
  *IDN?                      查询仪器身份
  *RST                       完整复位（恢复出厂默认状态，约需 3s）
  *CLS                       清除状态寄存器
  :FAC                       出厂复位 → DSOX4024A 不支持，返回 ESR=+32

水平控制（时基）
  :TIM:SCAL <value>          时基 (s/div)，如 0.001=1ms/div，20=20s/div
  :TIMEBASE:DELAY <value>     时基偏移 / 水平位置 (s)（:TIM:DEL 为缩写）
  :TIM:MODE <MAIN|ROLL>      时基模式：MAIN 普通 / ROLL 滚动
  注意：时基 ≥ 1s/div 时自动进入 RTIM 滚动模式

垂直控制（通道）
  :CHAN<N>:DISP ON/OFF       通道显示开关
  :CHAN<N>:PROB <value>      探头衰减比（如 10 表示 10:1，200 表示 200:1）
  :CHAN<N>:SCAL <value>      电压档位 (V/div)，由 round_voltage_scale() 取整到有效值列表
  :CHAN<N>:OFFS <value>      垂直偏移 (V)
  :CHAN<N>:BWL ON/OFF        带宽限制：ON=25MHz，OFF=全带宽 200MHz
  :CHAN<N>:COUP DC/AC/GND   耦合方式

触发设置
  :TRIGGER:MODE <mode>          触发模式：AUTO / NORMAL / EDGE / PULSE / VIDEO
  :TRIGGER:EDGE:SOURCE <src>     触发源：CHAN1~4 / EXT
  :TRIGGER:EDGE:LEVEL <level>    触发电平 (V)
  :TRIGGER:EDGE:SLOPE <slope>    边沿斜率：POS (上升) / NEG (下降) / EITH (任一)
  :TRIGGER:EDGE:COUPLING <coupling> 触发耦合：DC / AC / LFR / HFR
  :TRIGGER:FORCE               强制触发
  :RSTATE?                     查询运行状态：RUN / STOP / SING

采集控制
  :RUN                        启动/恢复采集
  :STOP                       停止采集（停止后可查询 :MEAS:* 测量值）

测量
  :MEASURE:SOUR <source>       设置测量源
  :MEASure:VMAX? [CHAN<N>]     测量最大值
  :MEASure:VMIN? [CHAN<N>]     测量最小值
  :MEASure:VAMPlitude? [CHAN<N>] 测量幅值
  :MEASure:VRMS? [CHAN<N>]     测量有效值
  :MEASure:VAVerage? [CHAN<N>] 测量平均值
  :MEASure:FREQuency? [CHAN<N>] 测量频率
  :MEASure:OVERshoot? [CHAN<N>] 测量过冲百分比
  :MEASURE:PREshoot? [CHAN<N>] 测量下冲百分比
  :MEASure:RISetime? [CHAN<N>] 测量上升时间 (10%~90%)
  :MEASURE:CLE                 清除所有测量项

光标
  :MARK:MODE <mode>           光标模式：OFF / MANUAL / TRACK / DELTA
  :MARK:X1Y1source <src>      光标源（X1/Y1 关联）：CHAN1~4 / FUNC / MATH
  :MARK:X2Y2source <src>      光标源（X2/Y2 关联）：CHAN1~4 / FUNC / MATH
  :MARK:X1Position <val>       光标 X1 位置 (s)
  :MARK:Y1Position <val>       光标 Y1 位置 (V)
  :MARK:X2Position <val>       光标 X2 位置 (s)
  :MARK:Y2Position <val>       光标 Y2 位置 (V)
  :MARK:XDELta?               查询 X 方向差值（X2-X1）
  :MARK:YDELta?               查询 Y 方向差值（Y2-Y1）
  :MARK:HFRE?                 查询频率（根据光标差值计算）
  :MARK:VDIF?                 查询垂直电压差值

波形数据
  :WAV:SOUR CHAN<N>           波形数据源
  :WAVEFORM:POINTS:MODE <mode> 波形模式：NORMal / MAXimum / RAW
  :WAV:FORM BYTE               数据格式：BYTE / WORD / ASC
  :WAV:PRE?                   查询波形前导信息（10个参数）
  :WAV:DATA?                  获取波形原始数据（二进制，#NDDDD 格式）

屏幕截图
  :DISP:DATA? PNG             获取屏幕图像（PNG 格式，IEEE 488.2 二进制 block）

已验证行为
  ✓ :CHAN<N>:PROB <value>    正确设置探头衰减（不是 :ATTN）
  ✓ :TIM:MODE ROLL            强制进入滚动模式（需显式发送）
  ✓ :MEAS:VMAX?/VMIN?         STOP 后才能查询（ROLL 模式下超时）
  ✓ *CLS                       不应在 RTIM 模式测量前使用（会导致后续查询超时）
  ✗ :FAC                       不支持，返回 ESR=+32
  ✗ :CHAN<N>:ATTN <any>        命令格式错误，始终 ESR=+32

通讯方式：TCPIP / USB
"""

import struct
import time
import numpy as np
from .BaseOscilloscope import BaseOscilloscope


class DSOX4024A(BaseOscilloscope):
    """
    Keysight DSOX4024A 示波器驱动。
    继承 BaseOscilloscope，实现 DSOX4024A 专用 SCPI 命令。
    """

    import time   # 模块级导入，供 _verify 等方法使用

    # ================================================================
    # 0. 连接与角色
    # ================================================================

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)
        self._model = "DSOX4024A"
        # 追踪每通道衰减比（:PROB 命令只写不读，本地维护）
        self._channel_attenuation = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}
        # 示波器时基有效值列表（秒）
        # 普通模式：含微秒档位
        self._NORMAL_TIMEBASES = [
            1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6,
            100e-6, 200e-6, 500e-6,
            1e-3, 2e-3, 5e-3, 10e-3, 20e-3, 50e-3,
            100e-3, 200e-3, 500e-3,
            1, 2, 5, 10, 20, 50, 100, 200, 500
        ]
        # 滚动模式：仅支持以下档位
        self._ROLL_TIMEBASES = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50]
        self._timebase_mode = "MAIN"
        # 电压档位有效值（V/div），1-2-5 序列，上限 1000V
        self._VOLTAGE_SCALES = [
            0.05, 0.1, 0.2, 0.5,
            1, 2, 5, 10, 20, 50, 100, 200, 500, 1000
        ]
        # 通道角色（整数 1-4，由 instrument_manager.connect_all 后写入）
        self._input_ch   = 4   # AC 输入电压通道
        self._output_ch  = 2   # DUT 输出电压通道
        self._dynamic_ch = 1   # 动态带载电压通道

    def set_channel_roles(self, input_ch: str = None, output_ch: str = None, dynamic_ch: str = None):
        """
        设置通道角色（由 instrument_manager 在测试运行前调用）。
        参数为字符串如 "CH2"，内部转为整数 2。
        """
        if input_ch is not None:
            self._input_ch = self._parse_ch(input_ch)
        if output_ch is not None:
            self._output_ch = self._parse_ch(output_ch)
        if dynamic_ch is not None:
            self._dynamic_ch = self._parse_ch(dynamic_ch)
        import logging
        self.logger = logging.getLogger("PowerAutoTest")
        self.logger.info(f"[DSOX4024A] 通道角色: 输入=CH{self._input_ch} 输出=CH{self._output_ch} 动态=CH{self._dynamic_ch}")

    def _parse_ch(self, ch: str) -> int:
        """将 "CH2" → 2, "CH4" → 4"""
        return int(ch.replace("CH", "").replace("ch", ""))

    # ================================================================
    # 1. 语义测量方法（按通道角色）
    # ================================================================
    # 内部所有 measure_voltage_* 方法统一用 self._output_ch

    def measure_output_voltage_max(self) -> float:
        """测量输出通道电压最大值 (V)"""
        return self.measure_voltage_max(self._output_ch)

    def measure_output_voltage_min(self) -> float:
        """测量输出通道电压最小值 (V)"""
        return self.measure_voltage_min(self._output_ch)

    def measure_input_voltage_max(self) -> float:
        """测量输入通道电压最大值 (V)"""
        return self.measure_voltage_max(self._input_ch)

    def measure_input_voltage_min(self) -> float:
        """测量输入通道电压最小值 (V)"""
        return self.measure_voltage_min(self._input_ch)

    def measure_dynamic_voltage_max(self) -> float:
        """测量动态通道电压最大值 (V)"""
        return self.measure_voltage_max(self._dynamic_ch)

    def measure_dynamic_voltage_min(self) -> float:
        """测量动态通道电压最小值 (V)"""
        return self.measure_voltage_min(self._dynamic_ch)

    # ================================================================
    # 2. 私有工具
    # ================================================================

    def _send_initial_commands(self):
        """
        轻量化初始化：*RST + *CLS + 波形数据格式。
        """
        self.send_command("*RST", check_esr=False)
        time.sleep(3.0)   # *RST 需等待约 3s 才完成
        self.send_command("*CLS", check_esr=False)
        self.send_command(":WAV:FORM BYTE", check_esr=False)

    def _validate_identity(self) -> bool:
        """验证仪器身份"""
        if "DSOX4024" in self._idn or "KEYSIGHT" in self._idn or "AGILENT" in self._idn:
            return True
        if "SIMULATION" in self._idn:
            return True
        return False

    def _parse_measurement(self, resp: str, default: float = 0.0) -> float:
        """
        解析测量响应，过滤 Keysight 的"无效测量"值 (+9.9E+37)。
        """
        try:
            val = float(resp.strip())
            if val > 1e30:          # +9.9E+37 表示测量无效
                return default
            return val
        except Exception:
            return default

    # ================================================================
    # 3. 初始化
    # ================================================================

    def initialize(self):
        """
        完整初始化：调用轻量化重置 + 关闭所有通道 + 配置衰减比。
        attn 由 instrument_manager 在创建仪器时从 UI test_settings 写入 _osc_ch_config。
        """
        import time
        self._send_initial_commands()

        # 先关闭所有通道，再由具体用例按需开启
        for ch in range(1, 5):
            self.send_command(f":CHAN{ch}:DISP OFF", check_esr=False)

        # 从 instrument_manager 写入的 UI 配置读取通道和衰减比
        ch_config = getattr(self, "_osc_ch_config", {})
        import logging
        logging.getLogger("PowerAutoTest").info(
            f"[DSOX4024A] initialize _osc_ch_config={ch_config}"
        )
        if ch_config:
            input_ch    = int(ch_config.get("osc_input_ch",    "CH4").upper().replace("CH", ""))
            output_ch   = int(ch_config.get("osc_output_ch",   "CH2").upper().replace("CH", ""))
            dynamic_ch  = int(ch_config.get("osc_dynamic_ch",  "CH1").upper().replace("CH", ""))
            input_attn   = float(ch_config.get("osc_input_attn",   1.0))
            output_attn  = float(ch_config.get("osc_output_attn",  1.0))
            dynamic_attn = float(ch_config.get("osc_dynamic_attn", 1.0))
            self._channel_attenuation[input_ch]   = input_attn
            self._channel_attenuation[output_ch]  = output_attn
            self._channel_attenuation[dynamic_ch] = dynamic_attn
            import logging
            logging.getLogger("PowerAutoTest").info(
                f"[DSOX4024A] PROB input_ch={input_ch} atten={input_attn} output_ch={output_ch} atten={output_attn} dynamic_ch={dynamic_ch} atten={dynamic_attn}"
            )
            self.send_command(f":CHAN{input_ch}:PROB {input_attn}", check_esr=False)
            self.send_command(f":CHAN{output_ch}:PROB {output_attn}", check_esr=False)
            self.send_command(f":CHAN{dynamic_ch}:PROB {dynamic_attn}", check_esr=False)

        else:
            # 未配置时，默认所有通道衰减为 1.0
            for ch in range(1, 5):
                self._channel_attenuation[ch] = 1.0

    # ================================================================
    # 4. 时基控制
    # ================================================================

    def set_timebase(self, scale: float):
        """
        设置时基 (秒/div)，自动取整到当前模式支持的最近有效值。

        - 普通模式（MAIN）：支持 1us ~ 500s（含微秒档位）
        - 滚动模式（ROLL）：仅支持 50ms, 100ms, 200ms, 500ms, 1s, 2s, 5s, 10s, 20s, 50s

        注意：时基 >= 1s/div 时示波器自动进入 RTIM 滚动模式。
        若需要在较快时基下强制滚动模式，需额外调用 set_timebase_mode("ROLL")。
        """
        # 向上取整到当前模式的有效时基列表
        tb_list = self._ROLL_TIMEBASES if self._timebase_mode == "ROLL" else self._NORMAL_TIMEBASES
        for tb in tb_list:
            if tb >= scale:
                scale = tb
                break
        else:
            scale = tb_list[-1]
        self.send_command(f":TIM:SCAL {scale}", check_esr=False)
        self._last_timebase = scale   # 记录最终设置的时基值（由 set_timebase 取整后）

    def set_timebase_for_duration(self, total_s: float, divisions: int = 10):
        """
        根据总时长和屏幕格数自动计算并设置最佳时基。

        用法：测试用例只管传总时长，示波器驱动决定最终时基值。

        参数：
            total_s     总时长（秒）
            divisions   屏幕格数，默认10（DSOX4024A 为10格）
        """
        min_tb = total_s / divisions
        self.set_timebase(min_tb)

    def round_voltage_scale(self, scale: float) -> float:
        """
        将电压档位取整到示波器支持的最近有效值（1-2-5 序列）。
        找距离最近的档位；距离相等时取较大的档位（向上取）。
        例如：100V -> 100V（正好）, 75V -> 100V, 30V -> 20V, 88V -> 100V, 0.15V -> 0.2V
        """
        scales = self._VOLTAGE_SCALES
        best = scales[0]
        best_diff = abs(scale - best)
        EPS = 1e-9
        for s in scales[1:]:
            diff = abs(scale - s)
            if diff < best_diff - EPS or (abs(diff - best_diff) < EPS and s > best):
                best_diff = diff
                best = s
        return best

    def _clamp_voltage_scale(self, channel: int, v_scale: float) -> float:
        """
        按通道衰减比限制最大电压档位，超限时 round DOWN 到最近兼容档位。

        Keysight DSOX4024A 硬件限制：
          atten = 1x  → 单格最大 5V/div（满屏 8 格 = 40V）
          atten = 10x → 单格最大 50V/div
        其他衰减比按线性插值。

        例如：atten=1，v_scale=6.0 → 超出 5V 上限 → round DOWN 到 5V/div
        """
        ch_atten = self._channel_attenuation.get(channel, 1.0)
        max_scale = ch_atten * 5.0   # atten=1 → 5V, atten=10 → 50V
        if v_scale <= max_scale:
            return v_scale
        # 超出上限，round DOWN 到 1-2-5 序列中最大的不超过 max_scale 的档位
        candidates = [s for s in self._VOLTAGE_SCALES if s <= max_scale]
        return candidates[-1] if candidates else self._VOLTAGE_SCALES[0]

    def set_timebase_offset(self, offset: float):
        """
        设置时基偏移 (秒)。
        即触发位置相对于屏幕中心的时间偏移。
        """
        self.send_command(f":TIM:DEL {offset}", check_esr=False)

    def set_timebase_mode(self, mode: str):
        """
        设置时基模式。

        Args:
            mode: "ROLL"  = 滚动模式（时基 >= 1s/div 自动进入，也可显式设置）
                  "MAIN"  = 普通时基模式
                  "NORMAL" = 普通时基模式（等同于 MAIN）
        """
        mode = mode.upper()
        if mode == "NORMAL":
            mode = "MAIN"
        if mode not in ("ROLL", "MAIN"):
            raise ValueError(f"Invalid timebase mode: {mode}. Use ROLL or MAIN.")
        self.send_command(f":TIM:MODE {mode}", check_esr=False)
        self._timebase_mode = mode

    # ---------------------- 延迟扫描（Zoom） ----------------------

    def set_zoom_mode(self, enabled: bool):
        """开启或关闭 Zoom（延迟扫描/展开）模式"""
        mode = "DELAYED" if enabled else "NORMAL"
        self.send_command(f":TIM:MODE {mode}", check_esr=False)

    def set_zoom_timebase(self, scale: float):
        """设置 Zoom 窗口的时基 (秒/div)"""
        self.send_command(":TIM:MODE DELAYED", check_esr=False)
        self.send_command(f":TIM:SCAL {scale}", check_esr=False)

    def set_zoom_position(self, delay_time: float):
        """设置 Zoom 窗口的延迟位置 (秒)"""
        self.send_command(":TIM:MODE DELAYED", check_esr=False)
        self.send_command(f":TIM:DEL {delay_time}", check_esr=False)

    def set_main_timebase(self, scale: float):
        """设置主时基 (秒/div)"""
        self.send_command(":TIM:MODE NORMAL", check_esr=False)
        self.send_command(f":TIM:SCAL {scale}", check_esr=False)

    # ================================================================
    # 5. 垂直控制（通道）
    # ================================================================

    def set_channel_on(self, channel: int):
        """开启指定通道 (1-4)"""
        self.send_command(f":CHAN{channel}:DISP ON", check_esr=False)

    def set_channel_off(self, channel: int):
        """关闭指定通道 (1-4)"""
        self.send_command(f":CHAN{channel}:DISP OFF", check_esr=False)

    def set_channel_config(self,
                           channel: int,
                           coupling: str = "DC",
                           attenuation: float = None,
                           voltage_scale: float = 5.0,
                           voltage_offset: float = 0.0,
                           bandwidth_limit: bool = True):
        """
        一次性配置示波器通道的完整参数，写入后批量检查 ESR 是否有错误。

        DSOX4024A SCPI 命令顺序：
          1. :CHAN<N>:BWL ON/OFF   → 带宽限制
          2. :CHAN<N>:COUP DC/AC   → 耦合方式
          3. :CHAN<N>:PROB <value> → 探头衰减比（注意：用 PROB 不是 ATTN）
          4. :CHAN<N>:SCAL <value>→ 电压档位（无硬性上限，由 _VOLTAGE_SCALES 列表决定）
          5. :CHAN<N>:OFFS <value>→ 垂直偏移

        Args:
            channel:         通道号 (1-4)
            coupling:        耦合方式: "DC" / "AC" / "GND"
            attenuation:     探头衰减比，如 10.0 (10:1)，200.0 (200:1)
            voltage_scale:   电压档位 (V/div)，由 round_voltage_scale() 取整到 _VOLTAGE_SCALES 列表
            voltage_offset:  垂直偏移 (V)
            bandwidth_limit: True = 开启 25MHz 限带，False = 全带宽 200MHz
        """
        if not self._connected:
            return

        bwl_val = "ON" if bandwidth_limit else "OFF"
        self.send_command(f":CHAN{channel}:BWL {bwl_val}", check_esr=False)

        coupling = coupling.upper()
        if coupling not in ("DC", "AC", "GND"):
            coupling = "DC"
        self.send_command(f":CHAN{channel}:COUP {coupling}", check_esr=False)

        # 仅当显式传入 attenuation 时才写入，否则跳过（保持 initialize 设的值）
        if attenuation is not None:
            self.send_command(f":CHAN{channel}:PROB {attenuation}", check_esr=False)
            self._channel_attenuation[channel] = attenuation

        # 下限保护（防零/负），上限由 _VOLTAGE_SCALES 列表决定，不再硬限制 5V
        voltage_scale = max(0.05, float(voltage_scale))
        self.send_command(f":CHAN{channel}:SCAL {voltage_scale}", check_esr=False)

        self.send_command(f":CHAN{channel}:OFFS {voltage_offset}", check_esr=False)

        # 批量检查 ESR，若有错误位则记录警告（Keysight 命令可靠，错误罕见）
        try:
            esr = self.query("*ESR?").strip()
            esr_val = int(esr)
            if esr_val != 0:
                import logging
                logging.getLogger("PowerAutoTest").warning(
                    f"[DSOX4024A] set_channel_config CH{channel} ESR={esr_val}（命令执行有误）"
                )
        except Exception:
            pass

    def set_voltage_scale(self, channel: int, scale: float):
        """设置通道电压档位 (V/div)"""
        self.send_command(f":CHAN{channel}:SCAL {scale}", check_esr=False)

    def set_channel_offset(self, channel: int, offset: float):
        """设置通道垂直偏移 (V)"""
        self.send_command(f":CHAN{channel}:OFFS {offset}", check_esr=False)

    def auto_config_channel(self,
                            channel: int,
                            v_peak: float,
                            coupling: str = "DC",
                            attenuation: float = None,
                            bandwidth_limit: bool = True,
                            grid_divisions: float = 5.0,
                            offset: float = None):
        """
        自动计算电压档位和偏移，使波形占指定格数、底部留 1 格空隙。

        屏幕 8 格（垂直），波形目标：底部 1 格空隙 + 波形占 grid_divisions 格。

        刻度公式：v_scale = v_peak / grid_divisions
          → 信号 0~v_peak 占 grid_divisions 格，底部留 1 格
        偏移公式：v_offset = offset（若指定）或 v_peak / 2
          → 默认信号中心 (v_peak/2) 对准屏幕垂直中心（4 格处）

        Args:
            channel:        通道号 (1-4)
            v_peak:         信号峰值电压 (V)，用于计算刻度和偏移
            coupling:       耦合方式，默认 DC
            attenuation:    探头衰减比，默认 None（沿用初始化时设置的值）
            bandwidth_limit: True = 开启 25MHz 限带，默认 True
            grid_divisions: 波形占垂直格数，默认 5.0（占 5 格 + 底部 1 格空隙）
            offset:         偏移 (V)，默认 None（使用 v_peak/2）
        """
        if not self._connected:
            return

        # attenuation=None 时不操作，沿用 initialize() 或上一次设置的值
        import logging
        logging.getLogger("PowerAutoTest").info(
            f"[DSOX4024A] auto_config ch={channel} v_peak={v_peak} atten={attenuation}"
        )

        # 衰减比 ≤10x 且计算值在硬件直接设置范围内 → 直接用计算值（不取整）
        # 衰减比 >10x 或计算值超出范围 → round 到标准档位后 clamp
        ch_atten = self._channel_attenuation.get(channel, 1.0)
        max_scale = ch_atten * 5.0   # atten=1x→5V, atten=10x→50V
        v_raw = v_peak / grid_divisions
        if ch_atten <= 10.0 and v_raw <= max_scale:
            v_scale = v_raw          # 直接设置，不需要取整
        else:
            v_scale = self.round_voltage_scale(v_raw)
            v_scale = self._clamp_voltage_scale(channel, v_scale)

        v_offset = offset if offset is not None else (v_scale * 2)

        self.set_channel_config(
            channel=channel,
            coupling=coupling,
            attenuation=attenuation,
            voltage_scale=v_scale,
            voltage_offset=v_offset,
            bandwidth_limit=bandwidth_limit
        )

    def set_channel_coupling(self, channel: int, coupling: str):
        """
        设置通道耦合方式。

        Args:
            channel: 通道号 (1-4)
            coupling: "DC" (直流) / "AC" (交流) / "GND" (接地)
        """
        coupling = coupling.upper()
        valid = ["DC", "AC", "GND"]
        if coupling not in valid:
            raise ValueError(f"Invalid channel coupling: {coupling}. Must be one of {valid}")
        self.send_command(f":CHAN{channel}:COUP {coupling}", check_esr=False)

    def get_channel_coupling(self, channel: int) -> str:
        """查询通道耦合方式，返回 "DC" / "AC" / "GND" """
        if not self._connected:
            return ""
        try:
            return self.query(f":CHAN{channel}:COUP?").strip()
        except Exception:
            return ""

    def set_bandwidth_limit(self, channel: int, limit_on: bool):
        """
        设置通道带宽限制。

        Args:
            channel:  通道号 (1-4)
            limit_on: True = 开启（通常限至 25MHz），False = 全带宽 200MHz
        """
        if not self._connected:
            return
        value = "ON" if limit_on else "OFF"
        self.send_command(f":CHAN{channel}:BWL {value}", check_esr=False)

    def get_bandwidth_limit(self, channel: int) -> bool:
        """查询通道带宽限制状态。True = 开启，False = 关闭"""
        if not self._connected:
            return False
        try:
            resp = self.query(f":CHAN{channel}:BWL?")
            return resp.strip() not in ("0", "OFF")
        except Exception:
            return False

    # ================================================================
    # 6. 触发设置
    # ================================================================

    def set_trigger_mode(self, mode: str):
        """
        设置触发模式。

        Args:
            mode: "AUTO" / "NORMAL" / "EDGE" / "PULSE" / "VIDEO"
        """
        valid_modes = ["AUTO", "NORMAL", "EDGE", "PULSE", "VIDEO"]
        mode = mode.upper()
        if mode not in valid_modes:
            raise ValueError(f"Invalid trigger mode: {mode}. Must be one of {valid_modes}")
        self.send_command(f":TRIGGER:MODE {mode}", check_esr=False)

    def set_trigger_source(self, source: str):
        """
        设置触发源。

        Args:
            source: "CHAN1" / "CHAN2" / "CHAN3" / "CHAN4" / "EXT"
        """
        source = source.upper()
        valid_sources = ["CHAN1", "CHAN2", "CHAN3", "CHAN4", "EXT"]
        if source not in valid_sources:
            raise ValueError(f"Invalid trigger source: {source}. Must be one of {valid_sources}")
        self.send_command(f":TRIGGER:EDGE:SOURCE {source}", check_esr=False)

    def set_trigger_level(self, level: float):
        """设置触发电平 (V)"""
        self.send_command(f":TRIGGER:EDGE:LEVEL {level}", check_esr=False)

    def set_trigger_slope(self, slope: str):
        """
        设置触发边沿斜率。

        Args:
            slope: "POS" (上升沿) / "NEG" (下降沿) / "BOTH" (双向)
        """
        slope = slope.upper()
        valid_slopes = ["POS", "NEG", "BOTH"]
        if slope not in valid_slopes:
            raise ValueError(f"Invalid trigger slope: {slope}. Must be one of {valid_slopes}")
        self.send_command(f":TRIGGER:EDGE:SLOPE {slope}", check_esr=False)

    def set_trigger_coupling(self, coupling: str):
        """
        设置触发耦合方式。

        Args:
            coupling: "DC" / "AC" / "LFREJ" (低频抑制) / "HFREJ" (高频抑制)
        """
        coupling = coupling.upper()
        valid_couplings = ["DC", "AC", "LFREJ", "HFREJ"]
        if coupling not in valid_couplings:
            raise ValueError(f"Invalid trigger coupling: {coupling}. Must be one of {valid_couplings}")
        self.send_command(f":TRIGGER:EDGE:COUPLING {coupling}", check_esr=False)

    def force_trigger(self):
        """强制触发一次（用于手动触发采集）"""
        self.send_command(":TRIGGER:FORCE", check_esr=False)

    def set_single_trigger(self):
        """
        设置为单次触发模式（SINGLE Sequenced Acquisition）。
        触发一次后停止采集，等待 :RUN 重新启动。

        注意：DSOX4000A 的 SINGLE 不是 :TRIG:MODE 的参数，
        需用独立的 :SINGLE 命令。
        """
        self.send_command(":SINGLE", check_esr=False)

    # ================================================================
    # 7. 采集控制
    # ================================================================

    def set_acquire_mode(self, mode: str):
        """
        设置示波器采集模式。

        Args:
            mode: 采集模式，可选：
                "NORMAL"      - 普通采样
                "AVERAGE"     - 平均采样（需配合 set_acquire_count）
                "PEAK"        - 峰值检测
                "HRESOLUTION"  - 高分辨率（EGA）
        """
        valid = ("NORMAL", "AVERAGE", "PEAK", "HRESOLUTION")
        if mode.upper() not in valid:
            raise ValueError(f"无效采集模式: {mode}，可选: {valid}")
        self.send_command(f":ACQUIRE:TYPE {mode.upper()}", check_esr=False)

    def set_acquire_count(self, count: int):
        """
        设置平均采样的次数（需先 set_acquire_mode AVERAGE）。

        Args:
            count: 平均次数，范围 2~65536。
                  越大噪声过滤越好，但等待时间越长。
        """
        if count < 2 or count > 65536:
            raise ValueError(f"采集次数超出范围 (2~65536): {count}")
        self.send_command(f":ACQUIRE:COUNT {count}", check_esr=False)

    def get_acquire_mode(self) -> str:
        """查询当前采集模式。"""
        if not self._connected:
            return ""
        resp = self.query(":ACQUIRE:TYPE?")
        return resp.strip()

    def get_acquire_count(self) -> int:
        """查询当前平均采集次数。"""
        if not self._connected:
            return 0
        resp = self.query(":ACQUIRE:COUNT?")
        try:
            return int(float(resp.strip()))
        except ValueError:
            return 0

    def get_trigger_status(self) -> str:
        """
        查询触发状态（:TRIG:STAT?）。

        Returns:
            "ARM"  (等待触发) / "TRIG" (已触发) / "VERF" (验证中) / "OFF"
        """
        if not self._connected:
            return ""
        try:
            return self.query(":TRIG:STAT?").strip()
        except Exception:
            return ""

    def get_run_state(self) -> str:
        """
        查询示波器采集运行状态（:RSTate?）。
        比 :TRIG:STAT? 更可靠，用于判断 SINGLE 触发是否已完成。

        Returns:
            "ARM" (等待触发) / "STOP" (已停止/已触发) / "RUN" (运行中)
            查询失败返回空字符串。
        """
        if not self._connected:
            return ""
        try:
            return self.query(":RSTate?").strip()
        except Exception:
            return ""

    # ---------------------- 采集控制 ----------------------

    def run(self):
        """启动/恢复采集。等效于面板 RUN 按键"""
        self.send_command(":RUN", check_esr=False)

    def stop(self):
        """停止采集。等效于面板 STOP 按键。停止后可查询测量值"""
        self.send_command(":STOP", check_esr=False)

    # ================================================================
    # 8. 测量配置
    # ================================================================

    # ---------------------- 测量接口（BaseOscilloscope 抽象接口） ----------------------

    def add_measurement(self, source, measurement_type: str):
        """
        添加一个测量项（源 + 类型）。

        Args:
            source:           测量源，支持 int（1-4）或字符串 "CHAN1"、"CHAN2" 等
            measurement_type: 测量类型，
                              支持：VMAX / VMIN / VAMP / VRMS / VAV / OVERSHOOT / PRESHOOT /
                                   FREQ / PER / RISE / FALL
        """
        if not self._connected:
            return
        # 自动加 CHAN 前缀（支持 int 或字符串）
        if isinstance(source, int):
            source = f"CHAN{source}"
        elif not source.upper().startswith("CHAN"):
            source = f"CHAN{source}"
        # 格式：:MEASURE:<TYPE> <SOURCE>，例如 :MEASURE:OVERSHOOT CHAN2
        _meas_map = {
            "VMAX":"VMAX","VMIN":"VMIN","VAMP":"VAMPlitude",
            "VAMPLITUDE":"VAMPlitude","VRMS":"VRMS",
            "VAV":"VAVerage","VAVERAGE":"VAVerage",
            "FREQUENCY":"FREQuency","FREQ":"FREQuency",
            "PERIOD":"PERiod","VPP":"VPP",
            "DUTYCYCLE":"DUTYcycle","DUTY":"DUTYcycle",
            "NDUTY":"NDUTy","NDUT":"NDUTy",
            "PWIDTH":"PWIDth","NWIDTH":"NWIDth","PWID":"PWIDth","NWID":"NWIDth",
            "RISETIME":"RISetime","RIS":"RISetime",
            "FALLTIME":"FALLtime","FALL":"FALLtime",
            "OVER":"OVERshoot","OVERSHOOT":"OVERshoot","OVERS":"OVERshoot",
            "POVER":"PREShoot","PERSHOOT":"PREShoot","PRESHOOT":"PREShoot","PERS":"PREShoot",
            "UND":"PREShoot","BWIDTH":"BWIDth","BWID":"BWIDth","PHASE":"PHASe",
        }
        _mn = _meas_map.get(measurement_type.upper(), measurement_type.upper())
        meas_cmd = f":MEASure:{_mn} {source}"
        self.send_command(meas_cmd, check_esr=False)

    def clear_screen(self):
        """清屏，清除示波器屏幕上所有波形和测量数据（:DISP:CLEAR）"""
        if not self._connected:
            return
        self.send_command(":DISP:CLEAR", check_esr=False)

    def clear_measurements(self):
        """清除所有已添加的测量项"""
        if not self._connected:
            return
        self.send_command(":MEASURE:CLE", check_esr=False)

    # ================================================================
    # 9. 测量查询
    # ================================================================

    def set_measurement_source(self, source: str):
        """
        设置默认测量源，后续 :MEAS:VMAX? / :MEAS:VMIN? 等查询都基于该源。

        Args:
            source: 测量源，如 "CHAN1", "CHAN2", "FUNC", "WMEM1"
        """
        if not self._connected:
            return
    def get_measurement(self, source: str, measurement_type: str) -> float:
        """
        查询指定测量项的结果值。

        Args:
            source:           测量源，如 "CHAN1"
            measurement_type: 测量类型，如 "VMAX"、"VMIN"、"FREQ"

        Returns:
            float: 测量结果值，查询失败返回 0.0
        """
        if not self._connected:
            return 0.0
        try:
            _meas_map = {
                "VMAX":"VMAX",
                "VMIN":"VMIN",
                "VRMS":"VRMS",
                "VPP":"VPP",
                "OVER":"OVERShoot",
                "POVER":"PREShoot",
                "VAV":"VAVerage",
                "VAMP":"VAMPlitude",
                "FREQ":"FREQuency",
                "PERIOD":"PERiod",
                "DUTY":"DUTYcycle",
                "NDUTY":"NDUTy",
                "PWIDTH":"PWIDth",
                "NWIDTH":"NWIDth",
                "RIS":"RISetime",
                "FALL":"FALLtime",
                "BWID":"BWIDth",
                "PHASE":"PHASe",
                "CH1":"CHANnel1",
                "CH2":"CHANnel2",
                "CH3":"CHANnel3",
                "CH4":"CHANnel4",
            }
            _mn = _meas_map.get(measurement_type.upper(), measurement_type.upper())
            resp = self.query(f":MEASure:{_mn}? {source}", delay_ms=200)
            return self._parse_measurement(resp)
        except Exception:
            return 0.0

    # ---------------------- 便捷测量方法（DSOX4024A 额外提供） ----------------------

    def measure_voltage_max(self, channel: int) -> float:
        """测量通道电压最大值 (V)"""
        if not self._connected:
            return 0.0
        try:
            resp = self.query(f":MEASure:VMAX? CHANnel{channel}", delay_ms=200)
            return self._parse_measurement(resp)
        except Exception:
            return 0.0

    def measure_voltage_min(self, channel: int) -> float:
        """测量通道电压最小值 (V)"""
        if not self._connected:
            return 0.0
        try:
            resp = self.query(f":MEASure:VMIN? CHANnel{channel}", delay_ms=200)
            return self._parse_measurement(resp)
        except Exception:
            return 0.0

    def measure_amplitude(self, channel: int) -> float:
        """测量峰峰值 (V)"""
        if not self._connected:
            return 0.0
        try:
            resp = self.query(f":MEASure:VAMPlitude? CHANnel{channel}", delay_ms=200)
            return self._parse_measurement(resp)
        except Exception:
            return 0.0

    def measure_rms(self, channel: int) -> float:
        """测量有效值 (Vrms)"""
        if not self._connected:
            return 0.0
        try:
            resp = self.query(f":MEASure:VRMS? CHANnel{channel}", delay_ms=200)
            return self._parse_measurement(resp)
        except Exception:
            return 0.0

    def measure_voltage_avg(self, channel: int) -> float:
        """测量通道电压平均值 (V)"""
        if not self._connected:
            return 0.0
        try:
            resp = self.query(f":MEASure:VAVerage? CHANnel{channel}", delay_ms=200)
            return self._parse_measurement(resp)
        except Exception:
            return 0.0

    def measure_frequency(self, channel: int) -> float:
        """测量频率 (Hz)"""
        if not self._connected:
            return 0.0
        try:
            resp = self.query(f":MEASure:FREQuency? CHANnel{channel}", delay_ms=200)
            return self._parse_measurement(resp, default=0.0)
        except Exception:
            return 0.0

    def measure_overshoot_builtin(self, channel: int) -> float:
        """
        读取示波器当前通道的过冲百分比（Overshoot）。
        使用 :MEASURE:OVERSHOOT? <source> 直接在查询命令中指定通道。
        """
        if not self._connected:
            return 0.0
        source = f"CHAN{channel}" if isinstance(channel, int) else str(channel)
        try:
            resp = self.query(f":MEASure:OVERshoot? {source}", delay_ms=200)
            return self._parse_measurement(resp)
        except Exception:
            return 0.0

    def measure_undershoot_builtin(self, channel: int) -> float:
        """
        读取示波器当前通道的下冲百分比（Undershoot）。
        使用 :MEASURE:PRESHOOT? <source> 直接在查询命令中指定通道。
        """
        if not self._connected:
            return 0.0
        source = f"CHAN{channel}" if isinstance(channel, int) else str(channel)
        try:
            resp = self.query(f":MEASure:PREShoot? {source}", delay_ms=200)
            return self._parse_measurement(resp)
        except Exception:
            return 0.0

    def measure_rise_time_builtin(self, channel: int) -> float:
        """使用示波器内置上升时间测量命令，返回上升时间 (秒)"""
        if not self._connected:
            return 0.0
        try:
            resp = self.query(f":MEASure:RISetime? CHANnel{channel}", delay_ms=200)
            return float(resp)
        except Exception:
            return 0.0

    # ---------------------- 软件计算测量（波形数据） ----------------------

    def measure_overshoot_on(self, channel: int,
                             settled_pct: float = 10.0,
                             sample_rate: float = 1e9) -> dict:
        """
        软件计算：测量开机过冲（Overshoot）。

        抓取波形，找到稳定值，然后计算过冲幅度与百分比。
        后 80%% 样本用于计算稳定值，前 20%% 中的最大值作为峰值。

        Args:
            channel:      测量通道 (1-4)
            settled_pct:   稳定区间百分比容差（默认 10%%，未使用，供参考）
            sample_rate:   示波器采样率 (Hz)，默认 1GSa/s（仅备注）

        Returns:
            dict: {
                "overshoot_v":   float,  过冲电压幅度 (V)
                "overshoot_pct": float,  过冲百分比 (%%)
                "peak_v":        float,  峰值电压 (V)
                "settled_v":     float,  稳定电压 (V)
                "x_data": np.ndarray,    时间轴 (秒)
                "y_data": np.ndarray,    电压轴 (伏特)
            }
        """
        x, y = self.acquire_waveform(channel)
        if len(y) == 0:
            return {"overshoot_v": 0.0, "overshoot_pct": 0.0,
                    "peak_v": 0.0, "settled_v": 0.0, "x_data": x, "y_data": y}
        n = len(y)
        tail = y[int(n * 0.80):]
        settled_v = float(np.mean(tail))
        peak_v = float(np.max(y))
        overshoot_v = peak_v - settled_v
        overshoot_pct = (overshoot_v / settled_v * 100.0) if settled_v != 0 else 0.0
        return {
            "overshoot_v":   round(overshoot_v, 4),
            "overshoot_pct": round(overshoot_pct, 2),
            "peak_v":        round(peak_v, 4),
            "settled_v":     round(settled_v, 4),
            "x_data":        x,
            "y_data":       y,
        }

    def measure_undershoot_off(self, channel: int) -> dict:
        """
        软件计算：测量关机下冲（Undershoot）。

        前 20%% 样本计算关机前的稳定值，剩余部分找最小值。

        Returns:
            dict: {
                "undershoot_v":   float,  下冲电压幅度 (V)
                "undershoot_pct": float,  下冲百分比 (%%)
                "dip_v":          float,  最低点电压 (V)
                "steady_v":       float,  稳定电压 (V)
                "x_data": np.ndarray,     时间轴 (秒)
                "y_data": np.ndarray,     电压轴 (伏特)
            }
        """
        x, y = self.acquire_waveform(channel)
        if len(y) == 0:
            return {"undershoot_v": 0.0, "undershoot_pct": 0.0,
                    "dip_v": 0.0, "steady_v": 0.0, "x_data": x, "y_data": y}
        n = len(y)
        head = y[:int(n * 0.20)]
        steady_v = float(np.mean(head))
        dip_v = float(np.min(y))
        undershoot_v = steady_v - dip_v
        undershoot_pct = (undershoot_v / steady_v * 100.0) if steady_v != 0 else 0.0
        return {
            "undershoot_v":   round(undershoot_v, 4),
            "undershoot_pct": round(undershoot_pct, 2),
            "dip_v":          round(dip_v, 4),
            "steady_v":       round(steady_v, 4),
            "x_data":         x,
            "y_data":        y,
        }

    def measure_rise_time(self, channel: int, rising: bool = True,
                          ref_upper: float = 90.0, ref_lower: float = 10.0) -> dict:
        """
        软件计算：测量上升/下降时间（10%%-90%% 或自定义参考电平）。

        Args:
            channel:      测量通道 (1-4)
            rising:       True=上升沿，False=下降沿
            ref_upper:    上参考电平 (%%)，默认 90%%
            ref_lower:    下参考电平 (%%)，默认 10%%

        Returns:
            dict: {
                "rise_time": float,  上升/下降时间 (秒)
                "upper_v":   float,  上参考电平对应电压 (V)
                "lower_v":   float,  下参考电平对应电压 (V)
                "upper_x":   float,  上穿越点时间 (秒)
                "lower_x":   float,  下穿越点时间 (秒)
                "x_data": np.ndarray, "y_data": np.ndarray
            }
        """
        x, y = self.acquire_waveform(channel)
        if len(y) == 0:
            return {"rise_time": 0.0, "upper_v": 0.0, "lower_v": 0.0,
                    "upper_x": 0.0, "lower_x": 0.0, "x_data": x, "y_data": y}
        v_max = float(np.max(y))
        v_min = float(np.min(y))
        v_pp = v_max - v_min
        upper_v = v_min + ref_upper / 100.0 * v_pp
        lower_v = v_min + ref_lower / 100.0 * v_pp
        if not rising:
            upper_v, lower_v = lower_v, upper_v
        above_lower = np.where(y >= lower_v)[0]
        above_upper = np.where(y >= upper_v)[0]
        if len(above_lower) == 0 or len(above_upper) == 0:
            return {"rise_time": 0.0, "upper_v": upper_v, "lower_v": lower_v,
                    "upper_x": 0.0, "lower_x": 0.0, "x_data": x, "y_data": y}
        if rising:
            lower_idx = above_lower[0]
            candidates = above_upper[above_upper > lower_idx]
            if len(candidates) == 0:
                return {"rise_time": 0.0, "upper_v": upper_v, "lower_v": lower_v,
                        "upper_x": 0.0, "lower_x": 0.0, "x_data": x, "y_data": y}
            upper_idx = candidates[0]
        else:
            upper_idx = above_upper[0] if len(above_upper) > 0 else 0
            candidates = above_lower[above_lower > upper_idx]
            if len(candidates) == 0:
                return {"rise_time": 0.0, "upper_v": upper_v, "lower_v": lower_v,
                        "upper_x": 0.0, "lower_x": 0.0, "x_data": x, "y_data": y}
            lower_idx = candidates[0]
        lower_x = float(x[lower_idx])
        upper_x = float(x[upper_idx])
        rise_time = upper_x - lower_x
        return {
            "rise_time": round(rise_time, 9),
            "upper_v":   round(upper_v, 5),
            "lower_v":   round(lower_v, 5),
            "upper_x":   round(upper_x, 9),
            "lower_x":   round(lower_x, 9),
            "x_data":    x,
            "y_data":   y,
        }

    def measure_fall_time(self, channel: int) -> dict:
        """测量下降时间（90%%-10%%）。内部调用 measure_rise_time(rising=False)"""
        return self.measure_rise_time(channel, rising=False)

    # ---------------------- 光标（BaseOscilloscope 抽象接口） ----------------------

    def set_cursor_mode(self, mode: str):
        """
        设置光标模式。

        Args:
            mode: "OFF" (关闭) / "MANUAL" (手动) / "TRACK" (追踪) / "DELTA" (增量)
        """
        mode = mode.upper()
        valid = ["OFF", "MANUAL", "TRACK", "DELTA"]
        if mode not in valid:
            raise ValueError(f"Invalid cursor mode: {mode}. Must be one of {valid}")
        self.send_command(f":MARK:MODE {mode}", check_esr=False)

    def set_cursor_source(self, source: str):
        """
        设置光标关联的信号源。

        Args:
            source: "CHAN1" / "CHAN2" / "CHAN3" / "CHAN4" / "FUNC" / "MATH"
        """
        source = source.upper()
        valid = ["CHAN1", "CHAN2", "CHAN3", "CHAN4", "FUNC", "MATH"]
        if source not in valid:
            raise ValueError(f"Invalid cursor source: {source}. Must be one of {valid}")
        self.send_command(f":MARK:X1Y1source {source}", check_esr=False)

    def set_cursor_position(self, cursor: str, x: float = None, y: float = None):
        """
        设置光标位置。

        Args:
            cursor: 光标标识，"A" 或 "B"
            x: 光标 X 位置 (秒)，None 表示不改变
            y: 光标 Y 位置 (V)，None 表示不改变
        """
        cursor = cursor.upper()
        if cursor not in ["A", "B"]:
            raise ValueError("cursor must be 'A' or 'B'")
        # 光标 A -> X1/Y1，光标 B -> X2/Y2
        if cursor == "A":
            if x is not None:
                self.send_command(f":MARK:X1Position {x}", check_esr=False)
            if y is not None:
                self.send_command(f":MARK:Y1Position {y}", check_esr=False)
        elif cursor == "B":
            if x is not None:
                self.send_command(f":MARK:X2Position {x}", check_esr=False)
            if y is not None:
                self.send_command(f":MARK:Y2Position {y}", check_esr=False)

    def get_cursor_position(self, cursor: str) -> dict:
        """
        查询光标 A 或 B 的位置。

        Args:
            cursor: "A" 或 "B"

        Returns:
            dict: {"x": float (秒), "y": float (V)}
        """
        cursor = cursor.upper()
        if cursor not in ["A", "B"]:
            raise ValueError("cursor must be 'A' or 'B'")
        if not self._connected:
            return {"x": 0.0, "y": 0.0}
        try:
            self.send_command(":MARK:MODE DELTA", check_esr=False)
            if cursor == "A":
                x = float(self.query(":MARK:X1Position?"))
                y = float(self.query(":MARK:Y1Position?"))
            else:
                x = float(self.query(":MARK:X2Position?"))
                y = float(self.query(":MARK:Y2Position?"))
            return {"x": x, "y": y}
        except Exception:
            return {"x": 0.0, "y": 0.0}

    def get_cursor_delta(self) -> dict:
        """
        查询两个光标之间的差值。

        Returns:
            dict: {
                "delta_x": float,  时间差 (秒)
                "delta_y": float,  电压差 (V)
                "freq":    float,  频率 (Hz)，delta_x 不为 0 时有效
            }
        """
        if not self._connected:
            return {"delta_x": 0.0, "delta_y": 0.0, "freq": 0.0}
        try:
            self.send_command(":MARK:MODE DELTA", check_esr=False)
            dx = float(self.query(":MARK:XDELta?"))
            dy = float(self.query(":MARK:YDELta?"))
            freq = 0.0
            try:
                freq = float(self.query(":MARK:HFRE?"))
            except Exception:
                pass
            return {"delta_x": dx, "delta_y": dy, "freq": freq}
        except Exception:
            return {"delta_x": 0.0, "delta_y": 0.0, "freq": 0.0}

    # ---------------------- 光标额外方法（DSOX4024A 额外提供） ----------------------

    def get_cursor_vertical_delta(self) -> float:
        """查询光标间垂直（电压）差值 (V)"""
        if not self._connected:
            return 0.0
        try:
            return float(self.query(":MARK:VDIF?"))
        except Exception:
            return 0.0

    # ================================================================
    # 10. 光标控制
    # ================================================================

    # ================================================================
    # 11. 波形与截图
    # ================================================================

    def acquire_waveform(self, channel: int) -> tuple:
        """
        获取指定通道的原始波形数据。

        DSOX4000X :WAV:PRE? 返回 10 个前导参数：
          format, type, points, count, xinc, xoff, xref, yinc, yoff, yref

        电压换算：V = (sample - yref) * yinc + yoff
        时间轴：  T = index * xinc + xoff

        Args:
            channel: 通道号 (1-4)

        Returns:
            (x_data: np.ndarray, y_data: np.ndarray)
            x_data: 时间轴 (秒)
            y_data: 电压轴 (伏特)
        """
        if not self._connected:
            return np.array([]), np.array([])

        try:
            self.send_command(f":WAV:SOUR CHAN{channel}", check_esr=False)
            self.send_command(":WAVEFORM:POINTS:MODE RAW", check_esr=False)
            self.send_command(":WAV:FORM BYTE", check_esr=False)

            preamble_str = self.query(":WAV:PRE?")
            vals = [v.strip() for v in preamble_str.split(",")]
            wform_format = int(vals[0])   # 0=BYTE, 1=WORD, 2=ASC
            points       = int(vals[2])   # 采样点数
            xinc         = float(vals[4]) # 时间间隔 (s)
            xoff         = float(vals[5]) # 时间偏移 (s)
            xref         = float(vals[6]) # 时间参考
            yinc         = float(vals[7]) # 电压分辨率 (V/level)
            yoff         = float(vals[8]) # 电压偏移 (V)
            yref         = int(float(vals[9])) # ADC offset

            self._resource.write(":WAV:DATA?")
            raw = self.read_raw()

            # 解析 IEEE 488.2 二进制 block 前缀 #NDDDDDDDD
            if raw.startswith(b'#'):
                num_digits = int(chr(raw[1]))
                num_bytes  = int(raw[2:2 + num_digits])
                data = raw[2 + num_digits:2 + num_digits + num_bytes]
            else:
                data = raw

            if wform_format == 0:    # BYTE (unsigned 8-bit)
                np_data = np.frombuffer(data, dtype=np.uint8)
            elif wform_format == 1: # WORD (unsigned 16-bit)
                np_data = np.frombuffer(data, dtype=np.uint16)
            else:                    # ASCII
                np_data = np.fromstring(data, sep=',')

            y_data = (np_data.astype(float) - yref) * yinc + yoff
            x_data = np.arange(len(y_data), dtype=float) * xinc + xoff

            return x_data, y_data

        except Exception as e:
            self.logger.warning(f"[DSOX4024A] Waveform acquire failed: {e}")
            return np.array([]), np.array([])

    def save_screenshot(self, filepath: str) -> str:
        """
        保存示波器屏幕截图 (PNG)。

        使用 :DISP:DATA? PNG 命令获取屏幕图像（IEEE 488.2 二进制 block），
        自动剥离前缀并保存为 PNG 文件。

        Args:
            filepath: 保存路径，建议 .png 扩展名

        Returns:
            成功返回文件路径，失败返回 None
        """
        import os

        if not self._connected:
            return None

        try:
            self.send_command(":DISP:DATA? PNG", check_esr=False)   # check_esr=False 避免读 ESR 时读到二进制数据
            time.sleep(0.3)   # 等待示波器准备图像数据
            raw = self._resource.read_raw()

            # 找到 PNG 签名 \x89PNG\r\n\x1a\n 的位置
            png_sig = b"\x89PNG\r\n\x1a\n"
            pos = raw.find(png_sig)

            if pos < 0:
                self.logger.warning(f"[DSOX4024A] save_screenshot: PNG signature not found")
                return None

            png_data = raw[pos:]

            dir_path = os.path.dirname(filepath)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)

            with open(filepath, "wb") as f:
                f.write(png_data)

            return filepath

        except Exception as e:
            self.logger.warning(f"[DSOX4024A] save_screenshot failed: {e}")
            return None

    def save_screenshot_with_measurements(self, channel: int, filepath: str) -> str:
        """
        保存示波器屏幕截图，并在截图上叠加显示过冲/下冲测量值。
        测量值从波形数据计算得出，不依赖示波器测量面板显示状态。

        过冲/下冲计算逻辑：
          VMAX    = max(波形数据)
          VMIN    = min(波形数据)
          Vsettd  = 后20%%数据段的平均值（稳态值）
          Overshoot%% = (VMAX - Vsettled) / Vsettled * 100
          Undershoot%%= (Vsettled - VMIN) / Vsettled * 100

        Args:
            channel:  示波器通道号 (1-4)
            filepath: 保存路径，建议 .png 扩展名

        Returns:
            成功返回文件路径，失败返回空字符串
        """
        import os
        try:
            # 1. 获取波形数据
            x_data, y_data = self.acquire_waveform(channel)
            if len(y_data) == 0:
                return ""

            vmax = float(np.max(y_data))
            vmin = float(np.min(y_data))
            settled_region = y_data[int(len(y_data) * 0.8):]
            vsettled = float(np.mean(settled_region)) if len(settled_region) > 0 else vmax

            if vsettled <= 0:
                vsettled = vmax * 0.5

            overshoot_pct = (vmax - vsettled) / vsettled * 100.0
            undershoot_pct = (vsettled - vmin) / vsettled * 100.0

            # 2. 先保存原始截图
            result = self.save_screenshot(filepath)
            if result is None:
                return ""

            # 3. 用 PIL 在截图上叠加数值标注
            try:
                from PIL import Image, ImageDraw, ImageFont
            except ImportError:
                return filepath   # PIL 不可用时返回原始截图

            img = Image.open(filepath)
            draw = ImageDraw.Draw(img)

            # 字体设置（尝试系统字体）
            try:
                font = ImageFont.truetype("arialbd.ttf", 28)
                small_font = ImageFont.truetype("arial.ttf", 18)
            except Exception:
                font = ImageFont.load_default()
                small_font = font

            # 在右下角绘制测量值框
            box_x, box_y = img.width - 280, img.height - 120
            draw.rectangle([box_x, box_y, box_x + 270, box_y + 110],
                           fill=(30, 30, 30, 220), outline=(80, 80, 80))

            ov_color = (0, 220, 0)   # 绿色
            ud_color = (0, 200, 255) # 浅蓝色

            draw.text((box_x + 10, box_y + 8),
                      f"OVERSHOOT: {overshoot_pct:.2f}%",
                      font=font, fill=ov_color)
            draw.text((box_x + 10, box_y + 55),
                      f"UNDERSHOOT: {undershoot_pct:.2f}%",
                      font=font, fill=ud_color)

            img.save(filepath)
            return filepath

        except Exception as e:
            self.logger.warning(f"[DSOX4024A] save_screenshot_with_measurements failed: {e}")
            return ""
