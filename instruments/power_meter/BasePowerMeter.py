# -*- coding: utf-8 -*-
"""
BasePowerMeter - 功率计抽象基类
================================

定义功率计统一抽象接口。
测试用例通过此基类操作功率计，换型号无需修改用例代码。

接口分类（4类）：
  1. 基础设置 (Basic Setup)
  2. 测试设置 (Test Setup)
  3. 积分测试功能 (Integration Test)
  4. 谐波电流测试功能 (Harmonic Current Test)

各型号驱动继承此类，实现所有抽象方法。
"""

from abc import abstractmethod
from ..base import BaseInstrument


class BasePowerMeter(BaseInstrument):
    """
    功率计统一抽象接口。
    所有功率计驱动必须继承并实现以下抽象方法。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)

    # ================================================================
    #  1. 基础设置
    # ================================================================

    @abstractmethod
    def initialize(self):
        """
        功率计初始化。
        典型实现：*RST 复位 → *CLS 清除状态 → 配置默认量程/模式。
        """
        pass

    @abstractmethod
    def set_voltage_range(self, channel: int, range_value: float):
        """
        设置电压量程。

        Args:
            channel:    通道号（0-indexed，0=CH1，1=CH2）
            range_value: 量程值 (V)，如 250、500、1000
        """
        pass

    @abstractmethod
    def set_current_range(self, channel: int, range_value: float):
        """
        设置电流量程。

        Args:
            channel:     通道号（0-indexed，0=CH1，1=CH2）
            range_value: 量程值 (A)，如 0.5、1、5、20
        """
        pass

    @abstractmethod
    def set_power_range(self, channel: int, range_value: float):
        """
        设置功率量程。

        Args:
            channel:     通道号
            range_value: 量程值 (W)
        """
        pass

    @abstractmethod
    def set_voltage_auto_range(self, channel: int, enabled: bool = True):
        """
        设置电压电流量程自动模式。

        Args:
            channel: 通道号
            enabled: True = 自动量程，False = 手动量程
        """
        pass

    @abstractmethod
    def set_current_auto_range(self, channel: int, enabled: bool = True):
        """
        设置电流量程自动模式。

        Args:
            channel: 通道号
            enabled: True = 自动量程，False = 手动量程
        """
        pass

    # ================================================================
    #  2. 测试设置
    # ================================================================

    @abstractmethod
    def set_wiring_mode(self, mode: str):
        """
        设置接线模式（功率计采样方式）。

        Args:
            mode: "1P2W" (单相两线) /
                  "1P3W" (单相三线) /
                  "3P3W" (三相三线) /
                  "3P4W" (三相四线)
        """
        pass

    @abstractmethod
    def set_input_type(self, input_type: str):
        """
        设置输入类型。

        Args:
            input_type: "AC" (交流) / "DC" (直流) / "ACDC" (交直流)
        """
        pass

    @abstractmethod
    def set_average_filter(self, enabled: bool = True, count: int = 16):
        """
        设置平均滤波器。

        Args:
            enabled: True = 开启平均，False = 关闭
            count:   平均次数，通常 4 / 8 / 16 / 32 / 64
        """
        pass

    @abstractmethod
    def reset_zero(self, channel: int):
        """
        校零（消除当前偏置）。

        Args:
            channel: 通道号，校零后该通道归零
        """
        pass

    # ================================================================
    #  3. 积分测试功能
    # ================================================================

    @abstractmethod
    def start_integration(self):
        """
        启动积分测试（开始累积能量测量）。
        通常与 stop_integration() 配对使用。
        """
        pass

    @abstractmethod
    def stop_integration(self):
        """
        停止积分测试（停止累积能量测量）。
        停止后可查询积分结果。
        """
        pass

    @abstractmethod
    def reset_integration(self):
        """
        重置积分值（清零累积能量）。
        """
        pass

    @abstractmethod
    def get_integrated_energy(self, channel: int) -> float:
        """
        获取累积能量 (Wh)。

        Args:
            channel: 通道号

        Returns:
            float: 累积电能 (Wh)
        """
        pass

    @abstractmethod
    def get_integration_time(self) -> float:
        """
        获取当前积分时长 (s)。

        Returns:
            float: 从 start_integration 到当前或上一次 stop_integration 的累计秒数
        """
        pass

    @abstractmethod
    def get_integration_status(self) -> dict:
        """
        查询积分状态。

        Returns:
            dict: {
                "running": bool,     # 积分是否正在进行
                "wh":     float,    # 当前累积能量 (Wh)
                "time":   float,    # 当前累计时间 (s)
                "limit":  str,      # "none" / "wh" / "time" / "both"，是否设置了限制
            }
        """
        pass

    # ================================================================
    #  4. 谐波电流测试功能
    # ================================================================

    @abstractmethod
    def set_harmonic_mode(self, enabled: bool = True):
        """
        开启或关闭谐波分析模式。

        Args:
            enabled: True = 开启谐波分析，False = 关闭
        """
        pass

    @abstractmethod
    def set_harmonic_order_limit(self, max_order: int):
        """
        设置谐波分析最高次数。

        Args:
            max_order: 最高分析谐波次数，通常 2~50
        """
        pass

    @abstractmethod
    def get_thd(self, channel: int) -> float:
        """
        获取电流总谐波畸变率 THD (%)。

        Args:
            channel: 通道号

        Returns:
            float: THD 值 (%)
        """
        pass

    @abstractmethod
    def get_harmonic_value(self, channel: int, order: int) -> float:
        """
        获取指定次谐波电流值。

        Args:
            channel: 通道号
            order:   谐波次数（如 3 = 第3次谐波，即 150Hz @ 50Hz）

        Returns:
            float: 该次谐波的电流值 (A) 或百分比 (% 相对于基波)
        """
        pass

    @abstractmethod
    def get_all_harmonics(self, channel: int) -> dict:
        """
        获取全部已分析谐波的值。

        Args:
            channel: 通道号

        Returns:
            dict: {
                "thd":    float,                # THD (%)
                "orders": {<order>: <value>, ...},  # 各次谐波值 dict
            }
        """
        pass

    # ================================================================
    #  5. 通用辅助方法（提供默认实现，子类可覆盖）
    # ================================================================

    def lock_minimum_current_range(self, channel: int = 1) -> float:
        """
        将电流量程锁定为最小档位（0.5A），用于待机功耗等小电流测量。

        默认实现：
          1. 查询仪器支持的所有电流量程档位
          2. 取最小档位设进去并返回

        子类如有更高效或更准确的实现，可覆盖此方法。

        Args:
            channel: 通道号（索引因型号而异）

        Returns:
            实际设置的电流量程（A）
        """
        # 尝试查询当前档的 LOW 值
        try:
            low = self.query(":CURRENT:RANGE:LOW?").strip()
            chosen = float(low)
        except Exception:
            chosen = None

        # 如果 LOW 查询失败，尝试直接读当前档位值
        if chosen is None:
            try:
                cur = self.query(":CURRENT:RANGE?").strip()
                chosen = float(cur)
            except Exception:
                chosen = None

        # 无法获取时用最小档 0.5A
        if chosen is None:
            chosen = 0.5

        self.set_current_range(channel, chosen)
        return chosen
