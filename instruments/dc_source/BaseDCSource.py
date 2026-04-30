# -*- coding: utf-8 -*-
"""
BaseDCSource - 直流电源基类
============================

定义直流电源通用接口：
- set_voltage(volts)       设置输出电压
- set_current(amps)       设置限流值
- output_on() / output_off()  输出开关
- measure_voltage()        测量输出电压
- measure_current()        测量输出电流
- measure_power()        测量输出功率
"""


from abc import abstractmethod
from ..base import BaseInstrument


class BaseDCSource(BaseInstrument):
    """
    直流电源基类，继承自 BaseInstrument。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)

    # ---------------------- 公共接口 ----------------------

    @abstractmethod
    def set_voltage(self, volts: float):
        """设置输出电压 (V)"""
        pass

    @abstractmethod
    def set_current(self, amps: float):
        """设置限流值 (A)"""
        pass

    @abstractmethod
    def output_on(self):
        """开启输出"""
        pass

    @abstractmethod
    def output_off(self):
        """关闭输出"""
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
        """测量输出功率 (W)"""
        pass
