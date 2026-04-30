# -*- coding: utf-8 -*-
"""
PowerFactorTest - 功率因数测试
===============================

测试 DUT 在不同负载下的功率因数。

规格：
  - pf_min: 最低功率因数要求（通常 ≥ 0.9）

注意：本测试为独立用例，不走 test_conditions 引擎注入系统，
  参数直接定义在 __init__ 的 params 里。
"""

import time
from ..base import TestCase
from typing import Dict, Any


class PowerFactorTest(TestCase):
    """
    功率因数测试。

    每条测试条件（由 test_conditions 注入或 params 默认值）执行 4 个负载点：
    25% / 50% / 75% / 100%，测量各点功率因数，与 pf_min 规格比对。
    """

    # ---------- 报告列定义 ----------
    COLS = [
    # 注意：「测试结论」列不定义在 COLS 中，
    # 由 report_generator._flatten() 统一注入（prefix 列）。

        ("输入条件",    16),
        ("协议",        14),
        ("输出电压(V)", 14),
        ("输出电流(A)", 14),
        ("负载点",       8),
        ("功率因数",    12),
        ("规格下限",    11),
        ("备注",       28),
    ]

    # ---------- __init__ ----------
    def __init__(self,
                 input_voltage: float = 220.0,
                 input_freq: float = 50.0,
                 output_voltage: float = 12.0,
                 output_current: float = 3.0,
                 load_points: list = None,
                 settle_time: float = 2.0,
                 pf_min: float = 0.90):
        self._input_voltage  = input_voltage
        self._input_freq     = input_freq
        self._output_voltage = output_voltage
        self._output_current = output_current
        self._load_points    = load_points or [25, 50, 75, 100]
        self._settle_time    = settle_time
        self._pf_min         = pf_min
        self.sub_results      = []

        super().__init__(
            name="PowerFactorTest",
            instruments=["AC_SOURCE", "ELOAD", "POWER_METER"],
            params={
                "input_voltage":  input_voltage,
                "input_freq":     input_freq,
                "output_voltage": output_voltage,
                "output_current": output_current,
                "load_points":    self._load_points,
                "settle_time":    settle_time,
                "pf_min":         pf_min,
            },
            spec={
                "pf_min": pf_min,
            }
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """缓存参数，建立 AC_SOURCE 基础配置。"""
        super().setup(instruments)
        self.ac   = instruments.get("AC_SOURCE")
        self.eload = instruments.get("ELOAD")
        self.pm   = instruments.get("POWER_METER")

        if self.ac:
            self.ac.set_voltage(self._input_voltage)
            self.ac.set_frequency(self._input_freq)
            self.ac.output_on()
        time.sleep(1)

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """主流程：对每个负载点测功率因数。"""
        self.sub_results = []

        for pct in self._load_points:
            i_load = self._output_current * pct / 100.0

            if self.eload:
                self.eload.set_mode_cc(float(i_load))   # IT8701P CC 模式
                self.eload.input_on()
            time.sleep(self._settle_time)

            pf = 0.0
            if self.pm:
                pf = self.pm.measure_power_factor()

            pass_flag = pf >= self._pf_min
            self.sub_results.append({
                "输入条件":    f"{self._input_voltage}V_{self._input_freq}Hz",
                "协议":        "",
                "输出电压(V)": self._output_voltage,
                "输出电流(A)": round(i_load, 3),
                "负载点":      f"{pct}%",
                "功率因数":    round(pf, 4),
                "规格下限":    self._pf_min,
                "测试结论":    "PASS" if pass_flag else "FAIL",
                "备注":        "" if pass_flag else f"PF={pf:.4f} < {self._pf_min}",
                "overall_pass": pass_flag,
                "skipped":     False,
            })
            self.measurements[f"pf_{pct}"] = round(pf, 4)

            if self.eload:
                self.eload.input_off()
            time.sleep(0.5)

    # ---------- verify ----------
    def verify(self) -> bool:
        """所有负载点 PASS 才整体 PASS。"""
        return bool(self.sub_results) and all(r["overall_pass"] for r in self.sub_results)

    # ---------- teardown ----------
    def teardown(self, instruments: Dict[str, Any]):
        """关闭仪器输出。"""
        eload = instruments.get("ELOAD")
        ac    = instruments.get("AC_SOURCE")
        if eload:
            eload.input_off()
        if ac:
            ac.output_off()

    # ---------- to_dict ----------
    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        return d
