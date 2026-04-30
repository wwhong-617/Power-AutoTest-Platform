# -*- coding: utf-8 -*-
"""
BaseElectronicLoad - 电子负载抽象基类
======================================

定义电子负载统一抽象接口。
测试用例通过此基类操作电子负载，换型号无需修改用例代码。

接口分类（6类）：
  1. 初始化 (Initialize)
  2. 负载 ON/OFF (Load ON/OFF)
  3. 短路 ON/OFF (Short)
  4. 动态功能 (Dynamic)
  5. LIST 功能 (List)
  6. 负载扫描 (Sweep)

各型号驱动继承此类，实现所有抽象方法。
"""

from abc import abstractmethod
from enum import Enum
from ..base import BaseInstrument


class LoadMode(Enum):
    CC = "CC"   # 恒流
    CV = "CV"   # 恒压
    CR = "CR"   # 恒阻
    CP = "CP"   # 恒功


class BaseElectronicLoad(BaseInstrument):
    """
    电子负载统一抽象接口。
    所有电子负载驱动必须继承并实现以下抽象方法。

    公共方法说明：
    - send_command() / query()：继承自 BaseInstrument，用于发送 SCPI 命令
    - short_off()：必需实现，用于清除短路状态
    - input_on() / input_off()：必需实现，用于控制负载输入开关
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000, channel: int = 1):
        super().__init__(conn_type, address, timeout_ms)
        self._current_mode = LoadMode.CC
        self._channel = channel  # 通道号（多路负载如IT8701P需要）

    # ================================================================
    #  1. 初始化
    # ================================================================

    @abstractmethod
    def initialize(self):
        """
        电子负载初始化。
        典型实现：*RST 复位 → *CLS 清除状态 → 设置默认保护参数。
        """
        pass

    # ================================================================
    #  2. 负载 ON / OFF
    # ================================================================

    @abstractmethod
    def set_mode_cc(self, current: float, slew_rate: float = None):
        """
        设置恒流模式 (CC)，并可设置电流斜率。

        Args:
            current:   目标电流 (A)
            slew_rate: 可选，电流上升斜率 (A/s)，None = 使用默认值或当前设定
        """
        pass

    @abstractmethod
    def set_mode_cv(self, voltage: float):
        """
        设置恒压模式 (CV)。

        Args:
            voltage: 目标电压 (V)
        """
        pass

    @abstractmethod
    def set_mode_cr(self, resistance: float):
        """
        设置恒阻模式 (CR)。

        Args:
            resistance: 目标电阻 (Ω)
        """
        pass

    @abstractmethod
    def set_mode_cp(self, power: float):
        """
        设置恒功模式 (CP)。

        Args:
            power: 目标功率 (W)
        """
        pass

    @abstractmethod
    def set_load_slew_rate(self, rate: float):
        """
        设置负载电流/功率变化斜率 (A/s 或 W/s)。

        Args:
            rate: 斜率值 (A/s 或 W/s)
        """
        pass

    @abstractmethod
    def input_on(self):
        """开启负载输入。等效于面板 INP ON"""
        pass

    @abstractmethod
    def input_off(self):
        """关闭负载输入。等效于面板 INP OFF"""
        pass

    # ================================================================
    #  3. 短路 ON / OFF
    # ================================================================

    @abstractmethod
    def short_on(self) -> bool:
        """
        开启短路：将负载设为最小电阻，等效为输出短路。

        Returns:
            bool: 短路操作是否成功
        """
        pass

    @abstractmethod
    def short_off(self):
        """关闭短路：断开短路状态，恢复正常拉载"""
        pass

    # ================================================================
    #  4. 动态功能（Dynamic）
    # ================================================================

    @abstractmethod
    def set_dynamic_mode(self,
                        i_high: float,
                        i_low: float,
                        frequency: float,
                        rise_time: float = None,
                        fall_time: float = None):
        """
        配置动态拉载模式（CC-Dynamic）。
        负载在 i_high 和 i_low 两个电流值之间周期性切换。

        Args:
            i_high:     高电流电平 (A)
            i_low:      低电流电平 (A)
            frequency:  切换频率 (Hz)，即一个完整周期（高→低→高）的时长 = 1/frequency
            rise_time:  从 i_low 上升到 i_high 的时间 (s)，None = 使用默认值
            fall_time:  从 i_high 下降到 i_low 的时间 (s)，None = 使用默认值
        """
        pass

    @abstractmethod
    def run_dynamic(self, progress_callback=None):
        """
        启动动态拉载。
        启动后负载将在预先配置的两个电平之间持续切换。

        Args:
            progress_callback: 回调函数 callback(current_level, step_count)
                              返回 False 时停止
        """
        pass

    # ================================================================
    #  5. LIST 功能
    # ================================================================

    @abstractmethod
    def program_list(self, steps, mode: str = "CC", cycles: int = 1,
                     slew_rate: float = None):
        """
        编程 LIST 序列（列表模式）。

        Args:
            steps:     LIST 序列，每项 (负载值, 持续时间秒)
                       示例 CC 模式: [(1.0, 5), (2.0, 5), (0.5, 3)]
            mode:      负载模式，"CC" / "CV" / "CR" / "CP"
            cycles:    重复次数
            slew_rate: 可选，切换斜率 (A/s)，None = 使用当前斜率或默认值
        """
        pass

    @abstractmethod
    def run_list(self, progress_callback=None):
        """
        启动已编程的 LIST 序列。

        Args:
            progress_callback: 回调函数 callback(step_index, total_steps, cycle, total_cycles)
                             返回 False 时停止
        """
        pass

    @abstractmethod
    def stop(self):
        """
        停止当前正在执行的动态拉载、LIST 或 SWEEP 操作。
        """
        pass

    # ================================================================
    #  6. 负载扫描 (Sweep)
    # ================================================================

    @abstractmethod
    def set_sweep_mode(self,
                       start: float,
                       stop: float,
                       step: float,
                       dwell: float,
                       slew_rate: float = None,
                       mode: str = "CC"):
        """
        配置负载扫描模式（CC-Sweep）。
        负载从 start 值逐步变化到 stop 值（步进 + 维持）。

        Args:
            start:     扫描起始值 (A)
            stop:      扫描终止值 (A)
            step:      步进幅度 (A)
            dwell:     每步维持时间 (秒)
            slew_rate: 可选，扫描斜率 (A/s)
            mode:      扫描模式，"CC" / "CV" / "CR" / "CP"
        """
        pass

    @abstractmethod
    def run_sweep(self, cycles: int = 1, progress_callback=None):
        """
        启动负载扫描。

        Args:
            cycles:            扫描重复次数
            progress_callback:  回调函数 callback(current_value, step_index, total_steps, cycle, cycles)
                              返回 False 时停止
        """
        pass
