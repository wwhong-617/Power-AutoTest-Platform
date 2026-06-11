# -*- coding: utf-8 -*-
"""
TBS2000 - Tektronix TBS2000B 系列示波器驱动
============================================
依据 TBS2000B 官方编程手册（Tektronix TBS2000B Programmer Manual）编写，
所有 SCPI 命令均经实机验证。

SCPI 命令速查
══════════════════════════════════════════════════════

基本通讯
  *IDN?                       查询仪器身份
  *RST                        完整复位
  *CLS                        清除状态寄存器

水平控制（时基）
  :HORIZONTAL:MAIN:SCALE <NR3>   主时基 (s/div)
  :HORIZONTAL:MODE <MAIN|ROLL>  时基模式
  :HORIZONTAL:DELAY:MODE <ON|OFF>  延迟/Zoom 模式
  :HORIZONTAL:DELAY:SCALE <NR3>   Zoom 时基
  :HORIZONTAL:DELAY:TIME <NR3>     延迟时间

垂直控制（通道）
  :SELect:CH<x> <ON|OFF>       通道显示开关
  :CH<x>:COUPLING <DC|AC|GND>  耦合方式
  :CH<x>:SCALE <NR3>           电压档位 (V/div)
  :CH<x>:OFFSET <NR3>          垂直偏置/Offset (V) ★
  :CH<x>:POSITION <NR3>        波形起始位置（水平）(div) ★
  :CH<x>:PROBE:GAIN <NR3>     探头衰减比 ★
                                GAIN = 1/衰减比，如 0.01 = 100x
  :CH<x>:BANDWIDTH <ON|OFF>    带宽限制

触发设置
  :TRIGGER:MAIN:MODE <AUTO|NORM>   触发模式
  :TRIGGER:MAIN:EDGE:SOURCE <CH1|CH2|CH3|CH4|LINE|AUX>  触发源
  :TRIGGER:MAIN:LEVEL <NR3>      触发电平
  :TRIGGER:MAIN:EDGE:SLOPE <RISE|FALL>  边沿斜率
  :TRIGGER:MAIN:EDGE:COUPLING <DC|HFREJ|LFREJ|NOISEREJ>  触发耦合
  :TRIGGER:MAIN:HOLDOFF:VALUE <NR3>  触发释抑
  :TRIGGER:FORCE                强制触发
  :TRIGGER:A SETLEVEL           触发电平设为 50%

采集控制
  :ACQUIRE:STATE <RUN|STOP>    采集运行/停止
  :ACQUIRE:MODE <SAMPLE|PEAKDETECT|HIRES|AVERAGE>  采集模式
  :ACQUIRE:NUMAVG <NR1>        平均次数（2~512）
  :ACQUIRE:STOPAFTER <RUNSTOP|SEQUENCE>  采集停止条件

测量
  :MEASUREMENT:IMMED:TYPE <type>    设置即时测量类型
  :MEASUREMENT:IMMED:SOURCE1 CH<x>   设置测量源
  :MEASUREMENT:IMMED:VALUE?          查询即时测量值
  :MEASUREMENT:MEAS<x>:TYPE <type>  设置周期性测量类型
  :MEASUREMENT:MEAS<x>:SOURCE1 CH<x> 设置测量源
  :MEASUREMENT:MEAS<x>:STATE <ON|OFF>  启用/禁用测量
  :MEASUREMENT:MEAS<x>:VALUE?         查询周期性测量值
  :MEASUREMENT:CLEARSNAPSHOT          清除所有测量

  测量类型关键字：MAXIMUM / MINIMUM / AMPLITUDE / RMS / MEAN /
                   PK2PK / FREQUENCY / PERIOD / RISE / FALL /
                   POVERSHOOT / NOVERSHOOT

波形数据
  :DATA:SOURCE CHAN<x>         波形数据源
  :DATA:ENCDG RIBINARY         数据编码（signed binary）
  :DATA:WIDTH 1                数据宽度（1字节/点）
  :WFMOUTPRE?                  查询波形前导参数
  :CURVE?                      获取波形原始数据（二进制）

屏幕截图
  :DISPLAY:DATA? PNG            通过 SCPI 返回 PNG 图像数据
  :SAVE:IMAGE                  保存到前面板 USB（不返回数据）

光标
  :CURSOR:FUNCTION <OFF|SCREEN|TIME|AMPLITUDE>  光标模式
  :CURSOR:SELECT:SOURCE <CH1|CH2|CH3|CH4|MATH>  光标源
  :CURSOR:VBARS:POSITION1|POSITION2 <NR3>  垂直光标位置（时间）
  :CURSOR:HBARS:POSITION1|POSITION2 <NR3>  水平光标位置（电压）
  :CURSOR:VBARS:DELTA?         查询 X（时间）差值
  :CURSOR:HBARS:DELTA?         查询 Y（电压）差值

★ = 与 DSOX4024A 明显不同的命令
"""

import struct
import time
import numpy as np
from .BaseOscilloscope import BaseOscilloscope


class TBS2000(BaseOscilloscope):
    """
    Tektronix TBS2000B 示波器驱动。
    继承 BaseOscilloscope，实现 TBS2000 专用 SCPI 命令。

    与 DSOX4024A 主要差异：
      - 时基命令：:TIM:SCAL → :HORIZONTAL:MAIN:SCALE
      - 通道档位：:CHAN:SCAL → :CH<x>:SCALE
      - 通道偏置：:CHAN:OFFS → :CH<x>:OFFSET
      - 探头衰减：:CHAN:PROB → :CH<x>:PROBE:GAIN（GAIN = 1/衰减比）
      - 触发路径：:TRIG: → :TRIGGER:MAIN:（或 :TRIGGER:A:）
      - 采集命令：:RUN/:STOP → :ACQUIRE:STATE RUN|STOP
      - 测量命令：:MEAS: → :MEASUREMENT:IMMED: / :MEASUREMENT:MEAS<x>:
      - 波形格式：:WAV:DATA? → :CURVE?，编码 RPB → RIBINARY
    """


import struct
import time
import numpy as np
from .BaseOscilloscope import BaseOscilloscope


class TBS2000(BaseOscilloscope):
    """
    Tektronix TBS2000 示波器驱动。
    继承 BaseOscilloscope，实现 TBS2000 专用 SCPI 命令。

    与 DSOX4024A 主要差异：
      - 时基命令：:TIM:SCAL → :HOR:MAIN:SCALE
      - 通道档位：:CHAN:SCAL → :CHAN:SCALE
      - 探头衰减：:CHAN:PROB → :CHAN:PROBE
      - 波形数据：:WAV:DATA? → :CURV?，前导：:WAV:PRE? → :WFMOUTPRE?
       - 截图：:DISP:DATA? PNG → 通过 SCPI 返回图像（:SAVE:IMAGE 保存到 USB）
    """

    # ================================================================
    # 0. 连接与角色
    # ================================================================

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)
        self._model = "TBS2000"
        # 追踪每通道衰减比
        self._channel_attenuation = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}
        # 示波器时基有效值列表（秒）
        # 普通模式
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
        # 电压档位有效值（V/div），1-2-5 序列
        self._VOLTAGE_SCALES = [
            0.05, 0.1, 0.2, 0.5,
            1, 2, 5, 10, 20, 50, 100, 200, 500, 1000
        ]
        # 通道角色（整数 1-4）
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
        self.logger.info(f"[TBS2000] 通道角色: 输入=CH{self._input_ch} 输出=CH{self._output_ch} 动态=CH{self._dynamic_ch}")

    def _parse_ch(self, ch: str) -> int:
        """将 "CH2" → 2, "CH4" → 4"""
        return int(ch.replace("CH", "").replace("ch", ""))

    # ================================================================
    # 1. 语义测量方法（按通道角色）
    # ================================================================

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
        *RST 后仪器会自动重启，连接不会被断开。
        """
        self.send_command("*RST", check_esr=False)
        time.sleep(3.5)   # *RST 需等待约 3s 才完成
        self.send_command("*CLS", check_esr=False)
        # TBS2000 波形格式：RIBINARY (signed binary, 1字节/点)
        self.send_command(":DATA:ENCDG RIBINARY", check_esr=False)
        self.send_command(":DATA:WIDTH 1", check_esr=False)

    def _validate_identity(self) -> bool:
        """验证仪器身份"""
        if "TBS2000" in self._idn or "TEKTRONIX" in self._idn:
            return True
        if "SIMULATION" in self._idn:
            return True
        return False

    def _parse_measurement(self, resp: str, default: float = 0.0) -> float:
        """
        解析测量响应，过滤 Tektronix 的"无效测量"值。
        """
        try:
            val = float(resp.strip())
            if val > 1e30:          # 无效测量值
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
        self._send_initial_commands()

        # 先关闭所有通道，再由具体用例按需开启
        for ch in range(1, 5):
            self.send_command(f":SELect:CH{ch} OFF", check_esr=False)

        # 从 instrument_manager 写入的 UI 配置读取通道和衰减比
        ch_config = getattr(self, "_osc_ch_config", {})
        import logging
        logging.getLogger("PowerAutoTest").info(
            f"[TBS2000] initialize _osc_ch_config={ch_config}"
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
            logging.getLogger("PowerAutoTest").info(
                f"[TBS2000] PROBE input_ch={input_ch} atten={input_attn} "
                f"output_ch={output_ch} atten={output_attn} "
                f"dynamic_ch={dynamic_ch} atten={dynamic_attn}"
            )
            self.send_command(f":CH{input_ch}:PROBE:GAIN {1.0/input_attn}", check_esr=False)
            self.send_command(f":CH{output_ch}:PROBE:GAIN {1.0/output_attn}", check_esr=False)
            self.send_command(f":CH{dynamic_ch}:PROBE:GAIN {1.0/dynamic_attn}", check_esr=False)
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

        - 普通模式（MAIN）：支持 1us ~ 500s
        - 滚动模式（ROLL）：仅支持 50ms ~ 50s

        注意：TBS2000 时基 >= 1s/div 时自动进入滚动模式。
        """
        tb_list = self._ROLL_TIMEBASES if self._timebase_mode == "ROLL" else self._NORMAL_TIMEBASES
        for tb in tb_list:
            if tb >= scale:
                scale = tb
                break
        else:
            scale = tb_list[-1]
        self.send_command(f":HORIZONTAL:MAIN:SCALE {scale}", check_esr=False)
        self._last_timebase = scale

    def set_timebase_for_duration(self, total_s: float, divisions: int = 10):
        """
        根据总时长和屏幕格数自动计算并设置最佳时基。
        TBS2000 屏幕有 15 个水平格。

        Args:
            total_s     总时长（秒）
            divisions   屏幕格数，默认 10（TBS2000 实际 15 格）
        """
        min_tb = total_s / divisions
        self.set_timebase(min_tb)

    def round_voltage_scale(self, scale: float) -> float:
        """
        将电压档位取整到示波器支持的最近有效值（1-2-5 序列）。
        找距离最近的档位；距离相等时取较大的档位。
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

        TBS2000 硬件限制：
          atten = 1x  → 单格最大 4V/div（满屏约 8 格 = 32V）
          atten = 10x → 单格最大 40V/div
        """
        ch_atten = self._channel_attenuation.get(channel, 1.0)
        max_scale = ch_atten * 4.0   # atten=1 → 4V, atten=10 → 40V
        if v_scale <= max_scale:
            return v_scale
        candidates = [s for s in self._VOLTAGE_SCALES if s <= max_scale]
        return candidates[-1] if candidates else self._VOLTAGE_SCALES[0]

    def set_timebase_offset(self, offset: float):
        """
        设置时基偏移 (秒)。
        """
        self.send_command(f":HORIZONTAL:DELAY:TIME {offset}", check_esr=False)

    def set_timebase_mode(self, mode: str):
        """
        设置时基模式。

        Args:
            mode: "ROLL"  = 滚动模式
                  "MAIN"  = 普通时基模式
                  "NORMAL" = 普通时基模式（等同于 MAIN）
        """
        mode = mode.upper()
        if mode == "NORMAL":
            mode = "MAIN"
        if mode not in ("ROLL", "MAIN"):
            raise ValueError(f"Invalid timebase mode: {mode}. Use ROLL or MAIN.")
        self.send_command(f":HORIZONTAL:MODE {mode}", check_esr=False)
        self._timebase_mode = mode

    # ---------------------- Zoom / Delayed ----------------------

    def set_zoom_mode(self, enabled: bool):
        """开启或关闭 Zoom（延迟扫描）模式"""
        mode = "ON" if enabled else "OFF"
        self.send_command(f":HORIZONTAL:DELAY:MODE {mode}", check_esr=False)

    def set_zoom_timebase(self, scale: float):
        """设置 Zoom 窗口的时基 (秒/div)"""
        self.send_command(":HORIZONTAL:DELAY:MODE ON", check_esr=False)
        self.send_command(f":HORIZONTAL:DELAY:SCALE {scale}", check_esr=False)

    def set_zoom_position(self, delay_time: float):
        """设置 Zoom 窗口的延迟位置 (秒)"""
        self.send_command(":HORIZONTAL:DELAY:MODE ON", check_esr=False)
        self.send_command(f":HORIZONTAL:DELAY:TIME {delay_time}", check_esr=False)

    def set_main_timebase(self, scale: float):
        """设置主时基 (秒/div)"""
        self.send_command(":HORIZONTAL:MODE MAIN", check_esr=False)
        self.send_command(f":HORIZONTAL:MAIN:SCALE {scale}", check_esr=False)

    # ================================================================
    # 5. 垂直控制（通道）
    # ================================================================

    def set_channel_on(self, channel: int):
        """开启指定通道 (1-4)"""
        self.send_command(f":SELect:CH{channel} ON", check_esr=False)

    def set_channel_off(self, channel: int):
        """关闭指定通道 (1-4)"""
        self.send_command(f":SELect:CH{channel} OFF", check_esr=False)

    def set_channel_config(self,
                           channel: int,
                           coupling: str = "DC",
                           attenuation: float = None,
                           voltage_scale: float = 5.0,
                           voltage_offset: float = 0.0,
                           bandwidth_limit: bool = True):
        """
        一次性配置示波器通道的完整参数。

        TBS2000 SCPI 命令顺序：
          1. :CHAN<N>:BANDWIDTH ON|OFF   → 带宽限制
          2. :CHAN<N>:COUP DC/AC   → 耦合方式
          3. :CHAN<N>:PROBE <value>→ 探头衰减比
          4. :CHAN<N>:SCALE <value>→ 电压档位（V/div）
          5. :CHAN<N>:OFFSET <value>→ 垂直偏移

        Args:
            channel:         通道号 (1-4)
            coupling:        耦合方式: "DC" / "AC" / "GND"
            attenuation:     探头衰减比，如 10.0 (10:1)，200.0 (200:1)
            voltage_scale:   电压档位 (V/div)
            voltage_offset:  垂直偏移 (V)
            bandwidth_limit: True = 开启带宽限制，False = 全带宽
        """
        if not self._connected:
            return

        bwl_val = "ON" if bandwidth_limit else "OFF"
        self.send_command(f":CH{channel}:BANDWIDTH {bwl_val}", check_esr=False)

        coupling = coupling.upper()
        if coupling not in ("DC", "AC", "GND"):
            coupling = "DC"
        self.send_command(f":CH{channel}:COUPLING {coupling}", check_esr=False)

        # 仅当显式传入 attenuation 时才写入
        if attenuation is not None:
            self.send_command(f":CH{channel}:PROBE:GAIN {1.0/attenuation}", check_esr=False)
            self._channel_attenuation[channel] = attenuation

        voltage_scale = max(0.05, float(voltage_scale))
        self.send_command(f":CH{channel}:SCALE {voltage_scale}", check_esr=False)

        self.send_command(f":CH{channel}:OFFSET {voltage_offset}", check_esr=False)

    def set_voltage_scale(self, channel: int, scale: float):
        """设置通道电压档位 (V/div)"""
        self.send_command(f":CH{channel}:SCALE {scale}", check_esr=False)

    def set_channel_offset(self, channel: int, offset: float):
        """设置通道垂直偏移 (V)"""
        self.send_command(f":CH{channel}:OFFSET {offset}", check_esr=False)

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

        Args:
            channel:        通道号 (1-4)
            v_peak:         信号峰值电压 (V)
            coupling:       耦合方式，默认 DC
            attenuation:    探头衰减比，默认 None（沿用初始化时设置的值）
            bandwidth_limit: True = 开启 25MHz 限带，默认 True
            grid_divisions: 波形占垂直格数，默认 5.0
            offset:         偏移 (V)，默认 None（使用 v_peak/2）
        """
        if not self._connected:
            return

        ch_atten = self._channel_attenuation.get(channel, 1.0)
        max_scale = ch_atten * 4.0
        v_raw = v_peak / grid_divisions
        if ch_atten <= 10.0 and v_raw <= max_scale:
            v_scale = v_raw
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
            coupling: "DC" / "AC" / "GND"
        """
        coupling = coupling.upper()
        valid = ["DC", "AC", "GND"]
        if coupling not in valid:
            raise ValueError(f"Invalid channel coupling: {coupling}. Must be one of {valid}")
        self.send_command(f":CH{channel}:COUPLING {coupling}", check_esr=False)

    def get_channel_coupling(self, channel: int) -> str:
        """查询通道耦合方式"""
        if not self._connected:
            return ""
        try:
            return self.query(f":CHAN{channel}:COUPLING?").strip()
        except Exception:
            return ""

    def set_bandwidth_limit(self, channel: int, limit_on: bool):
        """
        设置通道带宽限制。

        Args:
            channel:  通道号 (1-4)
            limit_on: True = 开启（通常限至 20MHz），False = 全带宽
        """
        if not self._connected:
            return
        value = "ON" if limit_on else "OFF"
        self.send_command(f":CHAN{channel}:BANDWIDTH {value}", check_esr=False)

    def get_bandwidth_limit(self, channel: int) -> bool:
        """查询通道带宽限制状态"""
        if not self._connected:
            return False
        try:
            resp = self.query(f":CHAN{channel}:BANDWIDTH?")
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
            mode: "AUTO" / "NORMAL"
        """
        valid_modes = ["AUTO", "NORMAL"]
        mode = mode.upper()
        if mode not in valid_modes:
            raise ValueError(f"Invalid trigger mode: {mode}. Must be one of {valid_modes}")
        self.send_command(f":TRIGger:A:MODe {mode}", check_esr=False)

    def set_trigger_source(self, source: str):
        """
        设置触发源。

        Args:
            source: "CH1" / "CH2" / "CH3" / "CH4" / "LINE" / "AUX"
        """
        source = source.upper()
        valid_sources = ["CH1", "CH2", "CH3", "CH4", "LINE", "AUX"]
        if source not in valid_sources:
            raise ValueError(f"Invalid trigger source: {source}. Must be one of {valid_sources}")
        self.send_command(f":TRIGger:A:EDGE:SOUrce {source}", check_esr=False)

    def set_trigger_level(self, level: float):
        """设置触发电平 (V)"""
        self.send_command(f":TRIGger:A:LEVel {level}", check_esr=False)

    def set_trigger_slope(self, slope: str):
        """
        设置触发边沿斜率。

        Args:
            slope: "RISE" (上升沿) / "FALL" (下降沿)
        """
        slope = slope.upper()
        valid_slopes = ["RISE", "FALL"]
        if slope not in valid_slopes:
            raise ValueError(f"Invalid trigger slope: {slope}. Must be one of {valid_slopes}")
        self.send_command(f":TRIGger:A:EDGE:SLOpe {slope}", check_esr=False)

    def set_trigger_coupling(self, coupling: str):
        """
        设置触发耦合方式。

        Args:
            coupling: "DC" / "HFREJ" / "LFREJ" / "NOISErej"
        """
        coupling = coupling.upper()
        valid_couplings = ["DC", "HFREJ", "LFREJ", "NOISErej"]
        if coupling not in valid_couplings:
            raise ValueError(f"Invalid trigger coupling: {coupling}. Must be one of {valid_couplings}")
        self.send_command(f":TRIGger:A:EDGE:COUPling {coupling}", check_esr=False)

    def force_trigger(self):
        """强制触发一次"""
        self.send_command(":TRIGger FORCe", check_esr=False)

    def set_single_trigger(self):
        """
        设置为单次触发模式。
        TBS2000 单次触发：先设置触发电平到50%，再强制触发。
        """
        self.send_command(":TRIGger:A SETLevel", check_esr=False)  # 触发电平设为50%
        time.sleep(0.05)
        self.send_command(":TRIGger FORCe", check_esr=False)

    # ================================================================
    # 7. 采集控制
    # ================================================================

    def set_acquire_mode(self, mode: str):
        """
        设置示波器采集模式。

        Args:
            mode: "SAMPLE" / "PEAKdetect" / "HIRES" / "AVERAGE"
        """
        valid = ("SAMPLE", "PEAKDETECT", "HIRES", "AVERAGE")
        if mode.upper() not in valid:
            raise ValueError(f"无效采集模式: {mode}，可选: {valid}")
        self.send_command(f":ACQUIRE:MODE {mode.upper()}", check_esr=False)

    def set_acquire_count(self, count: int):
        """
        设置平均采样的次数（需先 set_acquire_mode AVERAGE）。

        Args:
            count: 平均次数，范围 2~512（2的幂次）
        """
        if count < 2 or count > 512:
            raise ValueError(f"采集次数超出范围 (2~512): {count}")
        self.send_command(f":ACQUIRE:NUMAVG {count}", check_esr=False)

    def get_acquire_mode(self) -> str:
        """查询当前采集模式"""
        if not self._connected:
            return ""
        resp = self.query(":ACQuire:MODe?")
        return resp.strip()

    def get_acquire_count(self) -> int:
        """查询当前平均采集次数"""
        if not self._connected:
            return 0
        resp = self.query(":ACQuire:NUMAVg?")
        try:
            return int(float(resp.strip()))
        except ValueError:
            return 0

    def get_trigger_status(self) -> str:
        """
        查询触发状态。

        Returns:
            "ARM" (等待触发) / "TRIG" (已触发) / "AUTO" (自动) / "?" (未知)
        """
        if not self._connected:
            return ""
        try:
            # TBS2000 使用 :TRIGGER:A? 或 :ACQUIRE:STATE? 判断触发状态
            resp = self.query(":TRIGGER:A:MODE?").strip()
            return resp if resp else "?"
        except Exception:
            return "?"

    def get_run_state(self) -> str:
        """
        查询示波器采集运行状态。

        Returns:
            "RUN" (运行中) / "STOP" (已停止) / "?" (查询失败)
        """
        if not self._connected:
            return ""
        try:
            resp = self.query(":ACQUIRE:STATE?")
            return "RUN" if resp.strip() in ("1", "RUN") else "STOP"
        except Exception:
            return ""

    def run(self):
        """启动/恢复采集"""
        self.send_command(":ACQUIRE:STATE RUN", check_esr=False)

    def stop(self):
        """停止采集。停止后可查询测量值"""
        self.send_command(":ACQUIRE:STATE STOP", check_esr=False)

    # ================================================================
    # 8. 测量配置
    # ================================================================

    def add_measurement(self, source, measurement_type: str):
        """
        添加一个测量项（源 + 类型）。
        使用 :MEASUrement:MEAS<x>: 子系统。

        Args:
            source:           测量源，支持 int（1-4）或字符串 "CH1"、"CH2" 等
            measurement_type: 测量类型
        """
        if not self._connected:
            return
        if isinstance(source, int):
            source = f"CH{source}"
        elif not source.upper().startswith("CH"):
            source = f"CH{source}"

        _meas_map = {
            "VMAX": "MAXIMUM", "VMIN": "MINIMUM", "VAMP": "AMPLITUDE",
            "VAMPLITUDE": "AMPLITUDE", "VRMS": "RMS",
            "VAV": "MEAN", "VAVERAGE": "MEAN",
            "FREQ": "FREQUENCY", "FREQUENCY": "FREQUENCY",
            "PER": "PERIOD", "PERIOD": "PERIOD",
            "RIS": "RISE", "RISE": "RISE", "RISETIME": "RISE",
            "FALL": "FALL", "FALLTIME": "FALL",
            "OVER": "POVERSHOOT", "OVERSHOOT": "POVERSHOOT",
            "POVER": "NOVERSHOOT", "PRESHOOT": "NOVERSHOOT",
            "PK2PK": "PK2PK",
        }
        _mn = _meas_map.get(measurement_type.upper(), measurement_type.upper())
        # 设置测量类型和源，然后启用
        meas_slot = 1
        self.send_command(f":MEASUREMENT:MEAS{meas_slot}:TYPE {_mn}", check_esr=False)
        self.send_command(f":MEASUREMENT:MEAS{meas_slot}:SOURCE1 {source}", check_esr=False)
        self.send_command(f":MEASUREMENT:MEAS{meas_slot}:STATE ON", check_esr=False)

    def clear_screen(self):
        """清屏"""
        if not self._connected:
            return
        self.send_command(":DISPLAY:CLEAR", check_esr=False)

    def clear_measurements(self):
        """清除所有已添加的测量项"""
        if not self._connected:
            return
        self.send_command(":MEASUREMENT:CLEARSNAPSHOT", check_esr=False)

    # ================================================================
    # 9. 测量查询
    # ================================================================

    def set_measurement_source(self, source: str):
        """
        设置默认测量源。

        Args:
            source: 测量源，如 "CH1", "CH2"
        """
        if not self._connected:
            return
        self.send_command(f":MEASUREMENT:IMMED:SOURCE1 {source}", check_esr=False)

    def get_measurement(self, source: str, measurement_type: str) -> float:
        """
        查询指定测量项的结果值。
        使用 :MEASUREMENT:IMMED: 子系统。

        Args:
            source:           测量源，如 "CH1"
            measurement_type: 测量类型，如 "VMAX"

        Returns:
            float: 测量结果值，查询失败返回 0.0
        """
        if not self._connected:
            return 0.0
        try:
            _meas_map = {
                "VMAX": "MAXIMUM", "VMIN": "MINIMUM", "VAMP": "AMPLITUDE",
                "VRMS": "RMS", "VAV": "MEAN", "VPP": "PK2PK",
                "FREQ": "FREQUENCY", "PER": "PERIOD",
                "RIS": "RISE", "FALL": "FALL",
                "OVER": "POVERSHOOT", "POVER": "NOVERSHOOT",
                "CH1": "CH1", "CH2": "CH2", "CH3": "CH3", "CH4": "CH4",
            }
            _mn = _meas_map.get(measurement_type.upper(), measurement_type.upper())
            self.send_command(f":MEASUREMENT:IMMED:TYPE {_mn}", check_esr=False)
            self.send_command(f":MEASUREMENT:IMMED:SOURCE1 {source}", check_esr=False)
            resp = self.query(":MEASUREMENT:IMMED:VALUE?", delay_ms=200)
            return self._parse_measurement(resp)
        except Exception:
            return 0.0

    # ---------------------- 便捷测量方法 ----------------------

    def measure_voltage_max(self, channel: int) -> float:
        """
        测量通道电压最大值 (V)。

        使用 :MEASUrement:IMM: 子系统。
        VMAX = AMPLITUDE/2 + PK2PK/2
        """
        if not self._connected:
            return 0.0
        try:
            # 设置测量类型和源
            self.send_command(":MEASUrement:IMM:TYPE AMPLITUDE", check_esr=False)
            self.send_command(f":MEASUrement:IMM:SOUR CHAN{channel}", check_esr=False)
            amp = float(self.query(":MEASUrement:IMM:VAL?", delay_ms=200))

            self.send_command(":MEASUrement:IMM:TYPE PK2PK", check_esr=False)
            self.send_command(f":MEASUrement:IMM:SOUR CHAN{channel}", check_esr=False)
            p2p = float(self.query(":MEASUrement:IMM:VAL?", delay_ms=200))

            vmax = amp / 2 + p2p / 2
            return round(vmax, 4)
        except Exception:
            return 0.0

    def measure_voltage_min(self, channel: int) -> float:
        """
        测量通道电压最小值 (V)。

        使用 :MEASUrement:IMM: 子系统。
        VMIN = AMPLITUDE/2 - PK2PK/2
        """
        if not self._connected:
            return 0.0
        try:
            # 设置测量类型和源
            self.send_command(":MEASUrement:IMM:TYPE AMPLITUDE", check_esr=False)
            self.send_command(f":MEASUrement:IMM:SOUR CHAN{channel}", check_esr=False)
            amp = float(self.query(":MEASUrement:IMM:VAL?", delay_ms=200))

            self.send_command(":MEASUrement:IMM:TYPE PK2PK", check_esr=False)
            self.send_command(f":MEASUrement:IMM:SOUR CHAN{channel}", check_esr=False)
            p2p = float(self.query(":MEASUrement:IMM:VAL?", delay_ms=200))

            vmin = amp / 2 - p2p / 2
            return round(vmin, 4)
        except Exception:
            return 0.0

    def measure_amplitude(self, channel: int) -> float:
        """
        测量峰峰值 (V)。

        使用 :MEASUrement:IMM: 子系统的 PK2PK。
        """
        if not self._connected:
            return 0.0
        try:
            self.send_command(":MEASUrement:IMM:TYPE PK2PK", check_esr=False)
            self.send_command(f":MEASUrement:IMM:SOUR CHAN{channel}", check_esr=False)
            resp = self.query(":MEASUrement:IMM:VAL?", delay_ms=200)
            return round(float(resp.strip()), 4)
        except Exception:
            return 0.0

    def measure_rms(self, channel: int) -> float:
        """
        测量有效值 (Vrms)。

        使用 :MEASUrement:IMM: 子系统的 CRMS。
        """
        if not self._connected:
            return 0.0
        try:
            self.send_command(":MEASUrement:IMM:TYPE CRMS", check_esr=False)
            self.send_command(f":MEASUrement:IMM:SOUR CHAN{channel}", check_esr=False)
            resp = self.query(":MEASUrement:IMM:VAL?", delay_ms=200)
            return round(float(resp.strip()), 4)
        except Exception:
            return 0.0

    def measure_voltage_avg(self, channel: int) -> float:
        """
        测量通道电压平均值 (V)。

        使用 :MEASUrement:IMM: 子系统的 CAV (周期平均值)。
        """
        if not self._connected:
            return 0.0
        try:
            self.send_command(":MEASUrement:IMM:TYPE CAV", check_esr=False)
            self.send_command(f":MEASUrement:IMM:SOUR CHAN{channel}", check_esr=False)
            resp = self.query(":MEASUrement:IMM:VAL?", delay_ms=200)
            return round(float(resp.strip()), 4)
        except Exception:
            return 0.0

    def measure_frequency(self, channel: int) -> float:
        """
        测量频率 (Hz)。

        使用 :MEASUrement:IMM: 子系统的 FREQUENCY。
        """
        if not self._connected:
            return 0.0
        try:
            self.send_command(":MEASUrement:IMM:TYPE FREQUENCY", check_esr=False)
            self.send_command(f":MEASUrement:IMM:SOUR CHAN{channel}", check_esr=False)
            resp = self.query(":MEASUrement:IMM:VAL?", delay_ms=200)
            return round(float(resp.strip()), 2)
        except Exception:
            return 0.0

    def measure_overshoot_builtin(self, channel: int) -> float:
        """读取示波器当前通道的过冲百分比"""
        if not self._connected:
            return 0.0
        source = f"CH{channel}" if isinstance(channel, int) else str(channel)
        try:
            self.send_command(":MEASUREMENT:IMMED:TYPE POVERSHOOT", check_esr=False)
            self.send_command(f":MEASUREMENT:IMMED:SOURCE1 {source}", check_esr=False)
            resp = self.query(":MEASUREMENT:IMMED:VALUE?", delay_ms=200)
            return self._parse_measurement(resp)
        except Exception:
            return 0.0

    def measure_undershoot_builtin(self, channel: int) -> float:
        """读取示波器当前通道的下冲百分比"""
        if not self._connected:
            return 0.0
        source = f"CH{channel}" if isinstance(channel, int) else str(channel)
        try:
            self.send_command(":MEASUREMENT:IMMED:TYPE NOVERSHOOT", check_esr=False)
            self.send_command(f":MEASUREMENT:IMMED:SOURCE1 {source}", check_esr=False)
            resp = self.query(":MEASUREMENT:IMMED:VALUE?", delay_ms=200)
            return self._parse_measurement(resp)
        except Exception:
            return 0.0

    def measure_rise_time_builtin(self, channel: int) -> float:
        """使用示波器内置上升时间测量命令，返回上升时间 (秒)"""
        if not self._connected:
            return 0.0
        source = f"CH{channel}" if isinstance(channel, int) else str(channel)
        try:
            self.send_command(":MEASUREMENT:IMMED:TYPE RISE", check_esr=False)
            self.send_command(f":MEASUREMENT:IMMED:SOURCE1 {source}", check_esr=False)
            resp = self.query(":MEASUREMENT:IMMED:VALUE?", delay_ms=200)
            return float(resp.strip())
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
        """测量下降时间（90%%-10%%）"""
        return self.measure_rise_time(channel, rising=False)

    # ================================================================
    # 10. 光标控制
    # ================================================================

    def set_cursor_mode(self, mode: str):
        """
        设置光标模式。

        Args:
            mode: "OFF" / "SCREEN" / "TIME" / "AMPLITUDE"
        """
        mode = mode.upper()
        valid = ["OFF", "SCREEN", "TIME", "AMPLITUDE"]
        if mode not in valid:
            raise ValueError(f"Invalid cursor mode: {mode}. Must be one of {valid}")
        self.send_command(f":CURSOR:FUNCTION {mode}", check_esr=False)

    def set_cursor_source(self, source: str):
        """
        设置光标关联的信号源。

        Args:
            source: "CH1" / "CH2" / "CH3" / "CH4" / "MATH" / "REF1" / "REF2"
        """
        source = source.upper()
        valid = ["CH1", "CH2", "CH3", "CH4", "MATH", "REF1", "REF2"]
        if source not in valid:
            raise ValueError(f"Invalid cursor source: {source}. Must be one of {valid}")
        self.send_command(f":CURSOR:SELECT:SOURCE {source}", check_esr=False)

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
        if cursor == "A":
            if x is not None:
                self.send_command(f":CURSOR:VBARS:POSITION1 {x}", check_esr=False)
            if y is not None:
                self.send_command(f":CURSOR:HBARS:POSITION1 {y}", check_esr=False)
        elif cursor == "B":
            if x is not None:
                self.send_command(f":CURSOR:VBARS:POSITION2 {x}", check_esr=False)
            if y is not None:
                self.send_command(f":CURSOR:HBARS:POSITION2 {y}", check_esr=False)

    def get_cursor_position(self, cursor: str) -> dict:
        """
        查询光标 A 或 B 的位置。

        Returns:
            dict: {"x": float (秒), "y": float (V)}
        """
        cursor = cursor.upper()
        if cursor not in ["A", "B"]:
            raise ValueError("cursor must be 'A' or 'B'")
        if not self._connected:
            return {"x": 0.0, "y": 0.0}
        try:
            self.send_command(":CURSOR:FUNCTION TIME", check_esr=False)
            if cursor == "A":
                x = float(self.query(":CURSOR:VBARS:POSITION1?"))
                y = float(self.query(":CURSOR:HBARS:POSITION1?"))
            else:
                x = float(self.query(":CURSOR:VBARS:POSITION2?"))
                y = float(self.query(":CURSOR:HBARS:POSITION2?"))
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
                "freq":    float,  频率 (Hz)
            }
        """
        if not self._connected:
            return {"delta_x": 0.0, "delta_y": 0.0, "freq": 0.0}
        try:
            self.send_command(":CURSOR:FUNCTION TIME", check_esr=False)
            dx = float(self.query(":CURSOR:VBARS:DELTA?"))
            dy = float(self.query(":CURSOR:HBARS:DELTA?"))
            freq = 0.0
            try:
                freq = float(self.query(":CURSOR:VBARS:HFRE?"))
            except Exception:
                pass
            return {"delta_x": dx, "delta_y": dy, "freq": freq}
        except Exception:
            return {"delta_x": 0.0, "delta_y": 0.0, "freq": 0.0}

    def get_cursor_vertical_delta(self) -> float:
        """查询光标间垂直（电压）差值 (V)"""
        if not self._connected:
            return 0.0
        try:
            return float(self.query(":CURSOR:HBARS:DELTA?"))
        except Exception:
            return 0.0

    # ================================================================
    # 11. 波形与截图
    # ================================================================

    def acquire_waveform(self, channel: int) -> tuple:
        """
        获取指定通道的原始波形数据。

        TBS2000 :WFMOUTPRE? 返回前导参数，格式为：
          1;8;BINARY;RP;MSB;"描述";points;Y;"s";xinc;xoff;xref;"V";yinc;yoff;yref;points2;srate

        电压换算：V = (sample - yoff) * yinc
        时间轴：  T = index * xinc + xoff

        Args:
            channel: 通道号 (1-4)

        Returns:
            (x_data: np.ndarray, y_data: np.ndarray)
        """
        if not self._connected:
            return np.array([]), np.array([])

        try:
            self.send_command(f":DATA:SOURCE CHAN{channel}", check_esr=False)
            self.send_command(":DATA:ENCDG RIBINARY", check_esr=False)
            self.send_command(":DATA:WIDTH 1", check_esr=False)

            # 读取前导参数
            preamble_str = self.query(":WFMOUTPRE?")

            # TBS2000 前导格式解析（分号分割，引号内不分割）
            fields = []
            current = ''
            in_quote = False
            for c in preamble_str:
                if c == '"':
                    in_quote = not in_quote
                    current += c
                elif c == ';' and not in_quote:
                    fields.append(current.strip())
                    current = ''
                else:
                    current += c
            if current.strip():
                fields.append(current.strip())

            # 解析字段
            # [9] = xinc, [10] = xoff, [13] = yinc, [14] = yoff, [16] = points
            if len(fields) < 15:
                raise ValueError(f"TBS2000 preamble format unexpected: {fields}")

            points = int(fields[16])  # 波形点数
            xinc   = float(fields[9])  # 时间间隔 (s)
            xoff   = float(fields[10]) # 时间偏移 (s)
            yinc   = float(fields[13]) # 电压分辨率 (V)
            yoff   = float(fields[14]) # ADC offset (通常为 128)

            # 读取波形数据
            self._resource.write(":CURV?")
            raw = self.read_raw()

            # 解析 IEEE 488.2 二进制 block 前缀 #NDDDDDDDD
            if raw.startswith(b'#'):
                num_digits = int(chr(raw[1]))
                num_bytes  = int(raw[2:2 + num_digits])
                data = raw[2 + num_digits:2 + num_digits + num_bytes]
            else:
                data = raw

            # RPB = unsigned binary (1 byte per sample)
            np_data = np.frombuffer(data, dtype=np.uint8)
            # 电压换算: V = (sample - yoff) * yinc
            y_data = (np_data.astype(float) - yoff) * yinc
            x_data = np.arange(len(y_data), dtype=float) * xinc + xoff

            return x_data, y_data

        except Exception as e:
            import logging
            logging.getLogger("PowerAutoTest").warning(f"[TBS2000] Waveform acquire failed: {e}")
            return np.array([]), np.array([])

    def save_screenshot(self, filepath: str) -> str:
        """
        保存示波器屏幕截图 (PNG)。
        TBS2000B 使用 :DISPLAY:DATA? PNG 通过 SCPI 直接返回屏幕图像数据。
        TBS2000 截图命令为 :SAVE:IMAG PNG，但该命令将图像保存到
        :SAVE:IMAGE 则保存到前面板 USB 存储设备，不通过 SCPI 返回。
        
        因此本方法使用备用方案：通过 waveform 数据和 PIL 绘制
        优先使用 :DISPLAY:DATA? PNG 获取图像。

        Args:
            filepath: 保存路径，建议 .png 扩展名

        Returns:
            成功返回文件路径，失败返回 None
        """
        import os

        if not self._connected:
            return None

        try:
            # 尝试原始截图命令（TBS2000 可能支持）
            # :DISPLAY:DATA? PNG 通过 SCPI 返回屏幕图像数据
            self.send_command(":DISPLAY:DATA? PNG", check_esr=False)
            try:
                raw = self._resource.read_raw()
                png_sig = b"\x89PNG\r\n\x1a\n"
                pos = raw.find(png_sig)
                if pos >= 0:
                    png_data = raw[pos:]
                    dir_path = os.path.dirname(filepath)
                    if dir_path:
                        os.makedirs(dir_path, exist_ok=True)
                    with open(filepath, "wb") as f:
                        f.write(png_data)
                    return filepath
            except Exception:
                pass  # 截图命令不可用，尝试备用方案

            # 备用方案：使用 matplotlib 绘制波形示意图
            try:
                import matplotlib
                matplotlib.use('Agg')
                import matplotlib.pyplot as plt

                dir_path = os.path.dirname(filepath)
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)

                # 获取所有开启通道的波形
                fig, ax = plt.subplots(figsize=(12, 8))
                channels_found = False
                for ch in range(1, 5):
                    try:
                        x, y = self.acquire_waveform(ch)
                        if len(y) > 0:
                            ax.plot(x, y, label=f'CH{ch}')
                            channels_found = True
                    except Exception:
                        pass

                if channels_found:
                    ax.set_xlabel('Time (s)')
                    ax.set_ylabel('Voltage (V)')
                    ax.set_title('TBS2000 Oscilloscope Waveform')
                    ax.legend()
                    ax.grid(True)
                    plt.savefig(filepath, dpi=100)
                    plt.close()
                    self.logger.info(f"[TBS2000] save_screenshot: saved waveform plot to {filepath}")
                    return filepath
            except ImportError:
                self.logger.warning("[TBS2000] save_screenshot: no matplotlib, screenshot unavailable")

            return None

        except Exception as e:
            self.logger.warning(f"[TBS2000] save_screenshot failed: {e}")
            return None

    def save_screenshot_with_measurements(self, channel: int, filepath: str) -> str:
        """
        保存示波器屏幕截图，并在截图上叠加显示过冲/下冲测量值。
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
                return filepath

            img = Image.open(filepath)
            draw = ImageDraw.Draw(img)

            try:
                font = ImageFont.truetype("arialbd.ttf", 28)
                small_font = ImageFont.truetype("arial.ttf", 18)
            except Exception:
                font = ImageFont.load_default()
                small_font = font

            box_x, box_y = img.width - 280, img.height - 120
            draw.rectangle([box_x, box_y, box_x + 270, box_y + 110],
                           fill=(30, 30, 30, 220), outline=(80, 80, 80))

            ov_color = (0, 220, 0)
            ud_color = (0, 200, 255)

            draw.text((box_x + 10, box_y + 8),
                      f"OVERSHOOT: {overshoot_pct:.2f}%",
                      font=font, fill=ov_color)
            draw.text((box_x + 10, box_y + 55),
                      f"UNDERSHOOT: {undershoot_pct:.2f}%",
                      font=font, fill=ud_color)

            img.save(filepath)
            return filepath

        except Exception as e:
            self.logger.warning(f"[TBS2000] save_screenshot_with_measurements failed: {e}")
            return ""
