# -*- coding: utf-8 -*-
"""
BaseOscilloscope - 示波器基类
==============================

定义示波器统一抽象接口。
测试用例通过此基类操作示波器，换型号无需修改用例代码。

接口分类（5类）：
  1. 初始化 (Initialize)
  2. 水平控制 (Horizontal / Timebase)
  3. 垂直控制 (Vertical / Channel)
  4. 触发设置 (Trigger)
  5. 测量与光标 (Measurements & Cursors)

各型号驱动继承此类，实现所有抽象方法。
"""

from abc import abstractmethod
from ..base import BaseInstrument


class BaseOscilloscope(BaseInstrument):
    """
    示波器统一抽象接口。
    所有示波器驱动必须继承并实现以下抽象方法。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)

    # ============================================================
    #  1. 初始化
    # ============================================================

    @abstractmethod
    def initialize(self):
        """
        示波器初始化。
        典型实现：*RST 复位 → 等待 → 关闭所有通道。
        等效于面板 Default Setup 按键效果。
        """
        pass

    # ============================================================
    #  2. 水平控制（时基）
    # ============================================================

    @abstractmethod
    def set_timebase(self, scale: float):
        """
        设置主时基 (秒/div)。

        Args:
            scale: 时基值，如 0.001=1ms/div，1.0=1s/div，20=20s/div
        """
        pass

    @abstractmethod
    def set_timebase_offset(self, offset: float):
        """
        设置时基偏移（水平位置）(秒)。
        即触发点相对于屏幕中心的时间偏移。

        Args:
            offset: 时间偏移（秒），正值=向右，负值=向左
        """
        pass

    @abstractmethod
    def set_timebase_mode(self, mode: str):
        """
        设置时基模式。

        Args:
            mode: "ROLL" = 滚动模式，"MAIN" = 普通模式
        """
        pass

    # ============================================================
    #  3. 垂直控制（通道）
    # ============================================================

    @abstractmethod
    def set_channel_on(self, channel: int):
        """开启指定通道 (1-4)"""
        pass

    @abstractmethod
    def set_channel_off(self, channel: int):
        """关闭指定通道 (1-4)"""
        pass

    @abstractmethod
    def set_channel_config(self,
                           channel: int,
                           coupling: str = "DC",
                           attenuation: float = 1.0,
                           voltage_scale: float = 5.0,
                           voltage_offset: float = 0.0,
                           bandwidth_limit: bool = True):
        """
        一次性配置示波器通道的完整参数。

        Args:
            channel:        通道号 (1-4)
            coupling:       耦合方式: "DC" / "AC" / "GND"
            attenuation:    探头衰减比，如 10.0 (10:1)，100.0 (100:1)
            voltage_scale:  电压档位 (V/div)
            voltage_offset: 垂直偏移 (V)
            bandwidth_limit: True = 开启带宽限制，False = 全带宽
        """
        pass

    @abstractmethod
    def set_voltage_scale(self, channel: int, scale: float):
        """
        设置通道电压档位 (V/div)。

        Args:
            channel: 通道号 (1-4)
            scale:   档位值，如 1.0=1V/div，100.0=100V/div
        """
        pass

    @abstractmethod
    def set_channel_offset(self, channel: int, offset: float):
        """
        设置通道垂直偏移 (V)。

        Args:
            channel: 通道号 (1-4)
            offset:  偏移电压 (V)
        """
        pass

    @abstractmethod
    def set_channel_coupling(self, channel: int, coupling: str):
        """
        设置通道耦合方式。

        Args:
            channel: 通道号 (1-4)
            coupling: "DC" (直流) / "AC" (交流) / "GND" (接地)
        """
        pass

    @abstractmethod
    def set_bandwidth_limit(self, channel: int, limit_on: bool):
        """
        设置通道带宽限制。

        Args:
            channel:  通道号 (1-4)
            limit_on: True = 开启（通常限至 25MHz），False = 全带宽
        """
        pass

    # ============================================================
    #  4. 触发设置
    # ============================================================

    @abstractmethod
    def set_trigger_mode(self, mode: str):
        """
        设置触发模式。

        Args:
            mode: "AUTO" / "NORMAL" / "EDGE" / "PULSE" / "VIDEO"
        """
        pass

    @abstractmethod
    def set_trigger_source(self, source: str):
        """
        设置触发源。

        Args:
            source: "CHAN1" / "CHAN2" / "CHAN3" / "CHAN4" / "EXT"
        """
        pass

    @abstractmethod
    def set_trigger_level(self, level: float):
        """
        设置触发电平 (V)。

        Args:
            level: 触发电压阈值 (V)
        """
        pass

    @abstractmethod
    def set_trigger_slope(self, slope: str):
        """
        设置触发边沿斜率。

        Args:
            slope: "POS" (上升沿) / "NEG" (下降沿) / "BOTH"
        """
        pass

    @abstractmethod
    def force_trigger(self):
        """强制触发一次"""
        pass

    @abstractmethod
    def run(self):
        """
        启动/恢复采集。等效于面板 RUN 按键。
        在 STOP 后调用可恢复示波器采集。
        """
        pass

    @abstractmethod
    def stop(self):
        """
        停止采集。等效于面板 STOP 按键。
        停止后可查询测量值。
        """
        pass

    # ============================================================
    #  5. 测量与光标
    # ============================================================

    @abstractmethod
    def add_measurement(self, source: str, measurement_type: str):
        """
        添加一个测量项（测量源 + 测量类型）。

        常见 measurement_type 值：
          - "VMAX"   - 最大值
          - "VMIN"   - 最小值
          - "VAMP"   - 峰峰值
          - "VAV"    - 平均值
          - "VRMS"   - 有效值
          - "FREQ"   - 频率
          - "PER"    - 周期
          - "RISE"   - 上升时间
          - "FALL"   - 下降时间
          - "PDUT"   - 正占空比

        Args:
            source:          测量源，如 "CHAN1"、"CHAN2"
            measurement_type: 测量类型，如 "VMAX"、"FREQ"
        """
        pass

    @abstractmethod
    def clear_measurements(self):
        """清除所有已添加的测量项"""
        pass

    @abstractmethod
    def get_measurement(self, source: str, measurement_type: str) -> float:
        """
        查询指定测量项的结果值。

        Args:
            source:          测量源，如 "CHAN1"
            measurement_type: 测量类型，如 "VMAX"

        Returns:
            float: 测量结果值（V/Hz等），查询失败返回 0.0
        """
        pass

    # ---------------------- 光标 ----------------------

    @abstractmethod
    def set_cursor_mode(self, mode: str):
        """
        设置光标模式。

        Args:
            mode: "OFF" (关闭) / "MANUAL" (手动) / "TRACK" (跟踪) / "DELTA" (增量)
        """
        pass

    @abstractmethod
    def set_cursor_source(self, source: str):
        """
        设置光标关联的信号源。

        Args:
            source: "CHAN1" / "CHAN2" / "CHAN3" / "CHAN4" / "FUNC" / "MATH"
        """
        pass

    @abstractmethod
    def set_cursor_position(self, cursor: str, x: float = None, y: float = None):
        """
        设置光标位置。

        Args:
            cursor: 光标标识，"A" 或 "B"
            x: 光标 X 位置（秒），None 表示不改变
            y: 光标 Y 位置（V），None 表示不改变
        """
        pass

    @abstractmethod
    def get_cursor_position(self, cursor: str) -> dict:
        """
        查询光标位置。

        Args:
            cursor: 光标标识，"A" 或 "B"

        Returns:
            dict: {"x": float (秒), "y": float (V)}
        """
        pass

    @abstractmethod
    def get_cursor_delta(self) -> dict:
        """
        查询两个光标之间的差值。

        Returns:
            dict: {
                "delta_x": float,   # 时间差 (秒)
                "delta_y": float,   # 电压差 (V)
                "freq":   float     # 换算频率 (Hz)，delta_x 不为 0 时有效
            }
        """
        pass

    # ---------------------- 波形 ----------------------

    @abstractmethod
    def save_screenshot(self, filepath: str) -> str:
        """
        保存示波器屏幕截图。

        Args:
            filepath: 保存路径，建议 .png 扩展名

        Returns:
            成功返回文件路径，失败返回 None
        """
        pass

    @abstractmethod
    def acquire_waveform(self, channel: int):
        """
        获取指定通道的原始波形数据。

        Args:
            channel: 通道号 (1-4)

        Returns:
            (x_data, y_data): 时间数组 (秒) 和电压数组 (V)
            如果获取失败，返回 (empty_array, empty_array)
        """
        pass
