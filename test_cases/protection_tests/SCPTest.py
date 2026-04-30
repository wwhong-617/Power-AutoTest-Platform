"""
SCPTest - 短路保护测试
=======================

测试输出短路时 DUT 的保护动作。

规格：
  - 短路时 DUT 应在规定时间内关闭输出（通常 < 1s）
  - 短路解除后应自动恢复
"""

import time
from ..base import TestCase
from typing import Dict, Any


class SCPTest(TestCase):
    """
    短路保护测试。
    """

    def __init__(self):
        super().__init__(
            name="Short Circuit Protection Test",
            instruments=["AC_SOURCE", "ELOAD"],
            params={
                "input_voltage": 220.0,
                "input_freq": 50.0,
                "settle_time": 0.5,
                "recovery_delay": 2.0,
            },
            spec={
                "protection_time_max": 1.0,   # 秒
                "auto_recovery": True,
            }
        )

    def setup(self, instruments: Dict[str, Any]):
        ac = instruments.get("AC_SOURCE")
        if ac:
            ac.set_voltage(self.params["input_voltage"])
            ac.set_frequency(self.params["input_freq"])
            ac.output_on()
        time.sleep(1)

    def execute(self, instruments: Dict[str, Any]):
        eload = instruments.get("ELOAD")

        # 设置极低电阻模拟短路（恒阻模式）
        if eload:
            eload.set_mode_cr(0.01)  # 0.01 Ohm 短路
            eload.input_on()

        start_time = time.time()
        time.sleep(self.params["settle_time"])

        # 检测输出是否被关断（电压/电流降到0）
        v_meas = 0.0
        i_meas = 0.0
        if eload:
            v_meas = eload.measure_voltage()
            i_meas = eload.measure_current()

        protection_time = time.time() - start_time
        self.measurements["protection_time"] = round(protection_time, 3)
        self.measurements["short_voltage"] = round(v_meas, 4)
        self.measurements["short_current"] = round(i_meas, 4)
        self.measurements["protection_triggered"] = (v_meas < 0.5 and i_meas < 0.1)

        # 短路解除，测试恢复
        if eload:
            eload.set_mode_cr(1000)  # 解除短路（高阻）
        time.sleep(self.params["recovery_delay"])

        recovered = True
        if eload:
            v_recovered = eload.measure_voltage()
            recovered = (v_recovered > 5.0)  # 恢复到正常电压

        self.measurements["auto_recovery"] = recovered

    def verify(self) -> bool:
        t = self.measurements.get("protection_time", 999)
        triggered = self.measurements.get("protection_triggered", False)
        recovery = self.measurements.get("auto_recovery", False)
        return (triggered and t <= self.spec["protection_time_max"] and
                (not self.spec.get("auto_recovery", True) or recovery))

    def teardown(self, instruments: Dict[str, Any]):
        eload = instruments.get("ELOAD")
        ac = instruments.get("AC_SOURCE")
        if eload:
            eload.input_off()
        if ac:
            ac.output_off()
