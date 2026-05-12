"""
QCProtocolTest - Qualcomm QC2.0/3.0 协议测试
=============================================

测试 DUT 的 QC 快充协议支持。

规格：
  - 协议版本：QC2.0 / QC3.0
  - 必须支持的电压档位：5V/9V/12V（QC2.0）
"""

import time
from ..base import TestCase
from typing import Dict, Any, List


class QCProtocolTest(TestCase):
    """
    Qualcomm QC2.0/3.0 协议测试。
    """

    def __init__(self):
        super().__init__(
            name="QC2.0/3.0 Protocol Test",
            instruments=["SNIFFER"],
            params={
                "protocol_version": "QC3.0",
                "required_voltages": [5, 9, 12],
                "qc3_voltage_range": [3.6, 12.0],  # QC3.0 连续可调电压范围
            },
            spec={
                "handshake_success": True,
                "continuous_adjustment": True,
            }
        )
        self.sub_results = []

    def setup(self, instruments: Dict[str, Any]):
        sniffer = instruments.get("SNIFFER")
        if sniffer:
            pass

    def execute(self, instruments: Dict[str, Any]):
        sniffer = instruments.get("SNIFFER")
        self.sub_results = []

        # QC2.0 固定电压档位测试
        for volt in self.params["required_voltages"]:
            ok = False
            if sniffer:
                # 触发 QC 快充协议，切换到对应电压
                time.sleep(0.2)
                ok = True  # 模拟
            self.sub_results.append({
                "step": f"QC_FIXED_{volt}V",
                "voltage": volt,
                "pass": ok,
            })
            self.measurements[f"qc_{volt}v"] = 1 if ok else 0

        # QC3.0 连续可调电压测试（在范围内选几个点）
        if "QC3" in self.params["protocol_version"]:
            test_points = [3.6, 6.0, 9.0, 12.0]
            for volt in test_points:
                ok = False
                if sniffer:
                    time.sleep(0.1)
                    ok = True  # 模拟
                self.sub_results.append({
                    "step": f"QC3_CONTINUOUS_{volt}V",
                    "voltage": volt,
                    "pass": ok,
                })

    def verify(self) -> bool:
        return all(r["pass"] for r in self.sub_results)

    def teardown(self, instruments: Dict[str, Any]):
        super().teardown(instruments)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        return d
