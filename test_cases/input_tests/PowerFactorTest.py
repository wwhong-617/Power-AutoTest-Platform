"""
PowerFactorTest - 功率因数测试
===============================

测试 DUT 在不同负载下的功率因数。

规格：
  - pf_min: 最低功率因数要求（通常 ≥ 0.9）
"""

import time
from ..base import TestCase
from typing import Dict, Any


class PowerFactorTest(TestCase):
    """
    功率因数测试。
    """

    def __init__(self):
        super().__init__(
            name="Power Factor Test",
            instruments=["AC_SOURCE", "ELOAD", "POWER_METER"],
            params={
                "input_voltage": 220.0,
                "input_freq": 50.0,
                "output_voltage": 12.0,
                "output_current": 3.0,
                "load_points": [25, 50, 75, 100],
                "settle_time": 2.0,
            },
            spec={
                "pf_min": 0.90,
            }
        )
        self.sub_results = []

    def setup(self, instruments: Dict[str, Any]):
        ac = instruments.get("AC_SOURCE")
        if ac:
            ac.set_voltage(self.params["input_voltage"])
            ac.set_frequency(self.params["input_freq"])
            ac.output_on()
        time.sleep(1)

    def execute(self, instruments: Dict[str, Any]):
        eload = instruments.get("ELOAD")
        pm = instruments.get("POWER_METER")
        self.sub_results = []
        full_iout = self.params["output_current"]

        for pct in self.params["load_points"]:
            i_load = full_iout * pct / 100.0
            if eload:
                eload.set_load(i_load)
                eload.input_on()
            time.sleep(self.params["settle_time"])

            pf = 0.0
            if pm:
                pf = pm.measure_power_factor()

            pass_flag = pf >= self.spec["pf_min"]
            self.sub_results.append({
                "input_cond":   "",
                "proto_label":  "",
                "output_cond":  f"{pct}%负载",
                "pf":           round(pf, 4),
                "overall_pass": pass_flag,
                "skipped":      False,
            })
            self.measurements[f"pf_{pct}"] = round(pf, 4)

            if eload:
                eload.input_off()
            time.sleep(0.5)

    def verify(self) -> bool:
        return all(r["overall_pass"] for r in self.sub_results)

    def teardown(self, instruments: Dict[str, Any]):
        eload = instruments.get("ELOAD")
        ac = instruments.get("AC_SOURCE")
        if eload:
            eload.input_off()
        if ac:
            ac.output_off()

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        return d
