"""
StandbyPowerTest - 待机功耗测试
================================

测试 DUT 在无负载（待机）状态下的输入功率。

规格：
  - standby_power_max: 最大待机功耗（W）
"""

import time
from ..base import TestCase
from typing import Dict, Any


class StandbyPowerTest(TestCase):
    """
    待机功耗测试。
    """

    def __init__(self):
        super().__init__(
            name="Standby Power Test",
            instruments=["AC_SOURCE", "POWER_METER"],
            params={
                "input_voltage": 220.0,
                "input_freq": 50.0,
                "settle_time": 3.0,
            },
            spec={
                "standby_power_max": 0.5,   # W（常规充电器待机要求）
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
        pm = instruments.get("POWER_METER")
        time.sleep(self.params["settle_time"])

        pin = 0.0
        if pm:
            pin = pm.measure_power()

        self.measurements["standby_power_w"] = round(pin, 4)

    def verify(self) -> bool:
        standby = self.measurements.get("standby_power_w", 999)
        return standby <= self.spec["standby_power_max"]

    def teardown(self, instruments: Dict[str, Any]):
        ac = instruments.get("AC_SOURCE")
        if ac:
            ac.output_off()
