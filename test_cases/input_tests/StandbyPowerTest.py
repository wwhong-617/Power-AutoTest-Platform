# -*- coding: utf-8 -*-
"""
StandbyPowerTest - 待机功耗测试
================================

测试 DUT 在无负载（待机）状态下的输入功率。

规格：
  - standby_power_max: 最大待机功耗（W），典型值 0.3~0.5W

注意：本测试为独立用例，spec 直接定义在 __init__ 里。
  若由引擎注入 specs_v2["待机功耗_lo"]，可覆盖默认值。
"""

import time
from ..base import TestCase
from typing import Dict, Any


class StandbyPowerTest(TestCase):
    """
    待机功耗测试。

    在无负载条件下，测量 DUT 输入功率 Pin，与待机功耗规格比对。
    """

    # ---------- 报告列定义 ----------
    COLS = [
    # 注意：「测试结论」列不定义在 COLS 中，
    # 由 report_generator._flatten() 统一注入（prefix 列）。

        ("输入条件",      16),
        ("协议",          14),
        ("输出电压(V)",   14),
        ("输出电流(A)",   14),
        ("待机功耗(W)",   15),
        ("规格上限",      11),
        ("备注",         28),
    ]

    # ---------- __init__ ----------
    def __init__(self,
                 input_voltage: float = 220.0,
                 input_freq: float = 50.0,
                 settle_time: float = 3.0,
                 standby_power_max: float = 0.50):
        self._input_voltage      = input_voltage
        self._input_freq         = input_freq
        self._settle_time       = settle_time
        self._standby_power_max  = standby_power_max
        self.sub_results         = []

        super().__init__(
            name="StandbyPowerTest",
            instruments=["AC_SOURCE", "POWER_METER"],
            params={
                "input_voltage":     input_voltage,
                "input_freq":         input_freq,
                "settle_time":        settle_time,
                "standby_power_max":  standby_power_max,
            },
            spec={
                # key 命名遵循 base.py setup() 的合并规则（_lo/_hi），便于引擎注入覆盖
                "待机功耗_lo": standby_power_max,
            }
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """缓存参数，建立 AC_SOURCE 基础配置。"""
        super().setup(instruments)
        self.ac = instruments.get("AC_SOURCE")
        self.pm = instruments.get("POWER_METER")

        if self.ac:
            self.ac.set_voltage(self._input_voltage)
            self.ac.set_frequency(self._input_freq)
            self.ac.output_on()
        time.sleep(1)

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """
        测量待机功耗：
          1. 等待稳定（settle_time）
          2. 读取功率计输入功率 Pin
          3. 记录 sub_result
        """
        self.sub_results = []
        time.sleep(self._settle_time)

        pin = 0.0
        if self.pm:
            pin = self.pm.measure_power()  # WT333E，默认 channel=0

        self.measurements["standby_power_w"] = round(pin, 4)

        # 规格取 self.spec["待机功耗_lo"]（来自引擎注入或 __init__ 默认值）
        spec_max = self.spec.get("待机功耗_W_lo", self._standby_power_max)
        pass_flag = pin <= spec_max

        self.sub_results.append({
            "输入条件":    f"{self._input_voltage}V_{self._input_freq}Hz",
            "协议":        "",
            "输出电压(V)": "",
            "输出电流(A)": "",
            "待机功耗(W)": round(pin, 4),
            "规格上限":    spec_max,
            "测试结论":    "PASS" if pass_flag else "FAIL",
            "备注":        "" if pass_flag else f"Pin={pin:.4f}W > {spec_max}W",
            "overall_pass": pass_flag,
            "skipped":     False,
        })

    # ---------- verify ----------
    def verify(self) -> bool:
        """待机功耗不超过规格上限即 PASS。"""
        return bool(self.sub_results) and all(r["overall_pass"] for r in self.sub_results)

    # ---------- teardown ----------
    def teardown(self, instruments: Dict[str, Any]):
        """关闭 AC 输出。"""
        ac = instruments.get("AC_SOURCE")
        if ac:
            ac.output_off()

    # ---------- to_dict ----------
    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        return d
