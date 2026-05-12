"""
OutputVoltageAccuracyTest - 输出电压精度测试
=============================================

在额定输入、额定负载下测量输出电压精度。

规格：
  - vout_nominal: 标称输出电压（V）
  - tolerance:    允许偏差（%，如 ±5%）
"""

import time
from ..base import TestCase
from typing import Dict, Any


class OutputVoltageAccuracyTest(TestCase):
    """
    输出电压精度测试。
    """

    def __init__(self):
        super().__init__(
            name="Output Voltage Accuracy Test",
            instruments=["AC_SOURCE", "ELOAD", "POWER_METER"],
            params={
                "input_voltage": 220.0,
                "input_freq": 50.0,
                "output_current": 3.0,
                "settle_time": 2.0,
            },
            spec={
                "vout_nominal": 12.0,
                "tolerance_pct": 5.0,   # ±5%
            }
        )

    def setup(self, instruments: Dict[str, Any]):
        super().setup(instruments)
        ac = instruments.get("AC_SOURCE")
        eload = instruments.get("ELOAD")
        if ac:
            ac.set_voltage(self.params["input_voltage"])
            ac.set_frequency(self.params["input_freq"])
            ac.output_on()
        if eload:
            eload.set_mode_cc(self.params["output_current"])
            eload.input_on()
        time.sleep(1)

    def execute(self, instruments: Dict[str, Any]):
        eload = instruments.get("ELOAD")
        time.sleep(self.params["settle_time"])

        vout = 0.0
        if eload:
            vout = eload.measure_voltage()

        self.measurements["vout"] = round(vout, 4)

    def verify(self) -> bool:
        vnom = self.spec["vout_nominal"]
        tol = self.spec["tolerance_pct"]
        vout = self.measurements.get("vout", 0)
        vmax = vnom * (1 + tol / 100)
        vmin = vnom * (1 - tol / 100)
        return vmin <= vout <= vmax

    def teardown(self, instruments: Dict[str, Any]):
        eload = instruments.get("ELOAD")
        ac = instruments.get("AC_SOURCE")
        if eload:
            eload.input_off()
        if ac:
            ac.output_off()
