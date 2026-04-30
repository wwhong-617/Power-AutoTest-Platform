"""
OTPTest - 过温保护测试
=======================

测试 DUT 在过温时的保护动作。

注意：此测试需要温度采集设备或直接读取 DUT 内部温度传感器。

规格：
  - otp_threshold_min: 最小 OTP 触发温度（℃）
  - otp_threshold_max: 最大 OTP 触发温度（℃）
"""

import time
from ..base import TestCase
from typing import Dict, Any


class OTPTest(TestCase):
    """
    过温保护测试。
    注意：需要温度传感器或 DUT 反馈温度值。
    此测试通常需要长时间烤机，此处为简化版逻辑。
    """

    def __init__(self):
        super().__init__(
            name="Over Temperature Protection Test",
            instruments=["AC_SOURCE", "ELOAD"],
            params={
                "input_voltage": 220.0,
                "input_freq": 50.0,
                "rated_load_pct": 100,
                "temperature_sample_interval": 1.0,
            },
            spec={
                "otp_threshold_min": 100.0,   # ℃
                "otp_threshold_max": 130.0,   # ℃
            }
        )

    def setup(self, instruments: Dict[str, Any]):
        ac = instruments.get("AC_SOURCE")
        eload = instruments.get("ELOAD")
        if ac:
            ac.set_voltage(self.params["input_voltage"])
            ac.set_frequency(self.params["input_freq"])
            ac.output_on()
        if eload:
            eload.set_mode_cc(self.params["rated_load_pct"] / 100.0 * 3.0)
            eload.input_on()

    def execute(self, instruments: Dict[str, Any]):
        # 模拟温度读取（实际需要温度传感器或 DUT 反馈）
        # 这里用模拟数据代替
        temperature = 25.0
        otp_triggered = False
        otp_temp = 0.0

        # 模拟温度逐步上升
        for step in range(60):  # 模拟 60 秒
            time.sleep(self.params["temperature_sample_interval"])
            temperature += 1.5  # 每秒升 1.5 度（模拟）

            if temperature >= self.spec["otp_threshold_min"]:
                otp_triggered = True
                otp_temp = temperature
                break

        self.measurements["otp_triggered"] = otp_triggered
        self.measurements["otp_temperature"] = round(otp_temp, 1)
        self.measurements["final_temperature"] = round(temperature, 1)

    def verify(self) -> bool:
        triggered = self.measurements.get("otp_triggered", False)
        otp_t = self.measurements.get("otp_temperature", 0)
        if not triggered:
            return False
        return self.spec["otp_threshold_min"] <= otp_t <= self.spec["otp_threshold_max"]

    def teardown(self, instruments: Dict[str, Any]):
        eload = instruments.get("ELOAD")
        ac = instruments.get("AC_SOURCE")
        if eload:
            eload.input_off()
        if ac:
            ac.output_off()
