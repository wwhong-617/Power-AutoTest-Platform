"""
OVPTest - 过压保护测试
=======================

测试输出过压时 DUT 的保护动作。

测试步骤：
1. 设置输入电压为额定值
2. 电子负载逐步升高输出电压（模拟输出过压）
3. 监测 DUT 是否触发 OVP（关闭输出或限流）
4. 验证触发电压点在规格范围内

规格：
  - ovp_threshold_min: 最小 OVP 触发电压（V）
  - ovp_threshold_max: 最大 OVP 触发电压（V）
"""

import time
from ..base import TestCase
from typing import Dict, Any


class OVPTest(TestCase):
    """
    过压保护测试。
    """

    def __init__(self):
        super().__init__(
            name="Over Voltage Protection Test",
            instruments=["AC_SOURCE", "ELOAD"],
            params={
                "input_voltage": 220.0,
                "input_freq": 50.0,
                "output_voltage": 12.0,    # 标称输出
                "ovp_start_pct": 110,       # 从标称110%开始逐步加压
                "ovp_step_pct": 5,          # 步进5%
                "ovp_max_pct": 150,         # 最大加到150%
                "settle_time": 1.0,
            },
            spec={
                "ovp_threshold_min": 13.2,  # V（+10%）
                "ovp_threshold_max": 15.6,  # V（+30%）
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
        v_nom = self.params["output_voltage"]
        start_pct = self.params["ovp_start_pct"]
        step_pct = self.params["ovp_step_pct"]
        max_pct = self.params["ovp_max_pct"]

        ovp_triggered = False
        ovp_voltage = 0.0
        pct = start_pct

        while pct <= max_pct and not ovp_triggered:
            v_target = v_nom * pct / 100.0
            if eload:
                # 模拟输出电压逐步升高（通过改变负载拉高压）
                eload.set_mode_cv(v_target)
                eload.input_on()
            time.sleep(self.params["settle_time"])

            # 判断是否触发 OVP（DUT 输出降低或关闭）
            v_meas = 0.0
            if eload:
                v_meas = eload.measure_voltage()

            # 如果实测电压明显低于目标电压，说明 OVP 触发
            if v_meas < v_target * 0.8:
                ovp_triggered = True
                ovp_voltage = v_target
                break

            pct += step_pct

        self.measurements["ovp_triggered"] = ovp_triggered
        self.measurements["ovp_voltage"] = round(ovp_voltage, 3)

    def verify(self) -> bool:
        if not self.measurements.get("ovp_triggered", False):
            return False
        ovp_v = self.measurements.get("ovp_voltage", 0)
        return (self.spec["ovp_threshold_min"] <= ovp_v <= self.spec["ovp_threshold_max"])

    def teardown(self, instruments: Dict[str, Any]):
        eload = instruments.get("ELOAD")
        ac = instruments.get("AC_SOURCE")
        if eload:
            eload.input_off()
            eload.set_mode_cc(0.1)  # 恢复 CC 模式
        if ac:
            ac.output_off()
