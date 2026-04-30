# -*- coding: utf-8 -*-
"""
BaseACSource - 交流源抽象基类
==============================

定义交流源统一抽象接口。
测试用例通过此基类操作交流源，换型号无需修改用例代码。

接口分类（5类）：
  1. 初始化 (Initialize)
  2. 开机 / 关机 (Output Control)
  3. 电压 & 频率 (Voltage & Frequency)
  4. 序列功能 (Sequence / List)
  5. 保护功能 (Protection)

各型号驱动继承此类，实现所有抽象方法。
"""

from abc import abstractmethod
from ..base import BaseInstrument


class BaseACSource(BaseInstrument):
    """
    交流源统一抽象接口。
    所有交流源驱动必须继承并实现以下抽象方法。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)
        self._stop_flag = False

    # ================================================================
    #  1. 初始化
    # ================================================================

    @abstractmethod
    def initialize(self):
        """
        交流源自检/初始化。
        典型实现：*RST 复位 → *CLS 清除状态 → 设置默认参数。
        """
        pass

    # ================================================================
    #  2. 开机 / 关机
    # ================================================================

    @abstractmethod
    def output_on(self):
        """开启输出。等效于面板 OUTPUT ON"""
        pass

    @abstractmethod
    def output_off(self):
        """关闭输出。等效于面板 OUTPUT OFF"""
        pass

    # ================================================================
    #  3. 电压 & 频率
    # ================================================================

    @abstractmethod
    def set_voltage(self, volts: float):
        """
        设置输出电压 (V)。

        Args:
            volts: 输出电压值（V），有效范围因型号而异
        """
        pass

    def set_voltage_range(self, range_mode: str):
        """
        设置输出电压档位（量程）。

        Args:
            range_mode: "LOW"（低档，通常≤150V）/ "HIGH"（高档，通常≤300V或600V）
        """
        pass

    @abstractmethod
    def set_frequency(self, hz: float):
        """
        设置输出频率 (Hz)。

        Args:
            hz: 输出频率值（Hz），通常 16~500Hz
        """
        pass

    @abstractmethod
    def measure_voltage(self) -> float:
        """测量输出电压 (V)"""
        pass

    @abstractmethod
    def measure_current(self) -> float:
        """测量输出电流 (A)"""
        pass

    @abstractmethod
    def measure_power(self) -> float:
        """测量有功功率 (W)"""
        pass

    # ================================================================
    #  4. 序列功能
    # ================================================================

    @abstractmethod
    def program_list(self, steps, cycles: int = 1):
        """
        编程列表序列（List 模式）。

        Args:
            steps: 序列列表，每项 (电压, 频率, 持续时间秒)
                   示例: [(220, 50, 10), (110, 60, 5), (230, 50, 8)]
            cycles: 重复次数（默认 1 次）
        """
        pass

    @abstractmethod
    def run_list(self, progress_callback=None):
        """
        启动已编程的列表序列。
        具体执行顺序和方式因型号而异（立即触发/外部触发）。

        Args:
            progress_callback: 回调函数 callback(step_index, total_steps, cycle, total_cycles)
        """
        pass

    @abstractmethod
    def stop(self):
        """
        停止当前正在执行的列表序列或反复开关机操作。
        """
        pass

    @abstractmethod
    def repeated_on_off(self, volts: float, hz: float,
                        on_time_s: float, off_time_s: float,
                        cycles: int = 1,
                        progress_callback=None):
        """
        反复开关机操作。

        Args:
            volts:      输出电压（V）
            hz:         输出频率（Hz）
            on_time_s:  每次开机维持时间（秒）
            off_time_s: 每次关机维持时间（秒）
            cycles:     开关次数
            progress_callback: 回调函数 callback(current_cycle, total_cycles, state)
                             state 为 "on" 或 "off"
        """
        pass

    @abstractmethod
    def input_transient(self, steps, cycles: int = 1, progress_callback=None):
        """
        输入跳变测试（电压阶跃 / 暂态切换）。
        与 program_list 的区别：此方法专注于电压跳变测试场景，
        参数更直观（跳变幅度/持续时间），且自动处理跳变边界。

        跳变类型（由 steps 参数描述）：
          - SAG   (电压暂降)：从基准电压快速下降到指定值再恢复
          - SWELL (电压突升)：从基准电压快速上升到指定值再恢复
          - INTERRUPT (电压中断)：输出短暂关闭后再恢复
          - STEP   (阶跃)：直接在两个电压电平之间切换

        Args:
            steps: 跳变序列，每项 (起始电压, 目标电压, 跳变持续时间秒)
                   格式一（3元素）：(start_v, end_v, duration_s)
                   示例: [(220, 180, 2.0), (180, 220, 2.0)]  → SAG 后再恢复
                   格式二（4元素，带跳变速率）：(start_v, end_v, rise_time_s, fall_time_s)
                   跳变方向由 start_v 和 end_v 的大小关系自动判断
            cycles: 重复次数（默认 1 次）
            progress_callback: 回调函数 callback(step_index, total_steps, cycle, total_cycles)

        示例：
            # SAG 测试：220V → 180V（持续1s）→ 220V
            ac.input_transient([(220, 180, 1.0), (180, 220, 1.0)], cycles=3)

            # 电压阶跃：110V → 264V → 110V
            ac.input_transient([(110, 264, 0.5), (264, 110, 0.5)])
        """
        pass

    # ================================================================
    #  5. 保护功能
    # ================================================================

    @abstractmethod
    def set_overvoltage_protection(self, volts: float, enabled: bool = True):
        """
        设置过压保护阈值。

        Args:
            volts:   过压保护阈值 (V)
            enabled: True = 开启保护，False = 关闭保护
        """
        pass

    @abstractmethod
    def set_overcurrent_protection(self, amps: float, enabled: bool = True):
        """
        设置过流保护阈值。

        Args:
            amps:    过流保护阈值 (A)
            enabled: True = 开启保护，False = 关闭保护
        """
        pass

    @abstractmethod
    def set_overpower_protection(self, watts: float, enabled: bool = True):
        """
        设置过功率保护阈值。

        Args:
            watts:   过功率保护阈值 (W)
            enabled: True = 开启保护，False = 关闭保护
        """
        pass

    @abstractmethod
    def get_protection_status(self) -> dict:
        """
        查询当前保护状态。

        Returns:
            dict: {
                "ovp":  bool,   # 过压保护是否触发
                "ocp":  bool,   # 过流保护是否触发
                "opp":  bool,   # 过功率保护是否触发
                "trip": bool,   # 是否处于保护跳脱状态
            }
        """
        pass

    @abstractmethod
    def set_max_voltage_limit(self, volts: float):
        """
        设置最大输出电压限制（Voltage Limit）。
        限制交流源的最大输出电压不得超过此值。

        Args:
            volts: 最大输出电压限制值 (V)
        """
        pass

    @abstractmethod
    def set_max_current_limit(self, amps: float):
        """
        设置最大输出电流限制（Current Limit）。
        限制交流源的最大输出电流不得超过此值。

        Args:
            amps: 最大输出电流限制值 (A)
        """
        pass

    @abstractmethod
    def clear_protection_alarm(self):
        """清除保护告警，恢复正常运行状态"""
        pass
