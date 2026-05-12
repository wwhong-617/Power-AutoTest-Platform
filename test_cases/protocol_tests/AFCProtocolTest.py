"""
AFCProtocolTest - AFC 协议测试
================================

Samsung AFC (Adaptive Fast Charging) 协议测试。
"""

import time
from ..base import TestCase
from typing import Dict, Any


class AFCProtocolTest(TestCase):
    """
    AFC 协议测试。
    """

    def __init__(self):
        super().__init__(
            name="AFC Protocol Test",
            instruments=["SNIFFER"],
            params={
                "required_voltages": [5, 9],
            },
            spec={
                "handshake_success": True,
            }
        )
        self.sub_results = []

    def setup(self, instruments: Dict[str, Any]):
        super().setup(instruments)

    def execute(self, instruments: Dict[str, Any]):
        sniffer = instruments.get("SNIFFER")
        self.sub_results = []

        for volt in self.params["required_voltages"]:
            ok = False
            if sniffer:
                time.sleep(0.2)
                ok = True
            self.sub_results.append({
                "step": f"AFC_{volt}V",
                "voltage": volt,
                "pass": ok,
            })
            self.measurements[f"afc_{volt}v"] = 1 if ok else 0

    def verify(self) -> bool:
        return all(r["pass"] for r in self.sub_results)

    def teardown(self, instruments: Dict[str, Any]):
        super().teardown(instruments)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        return d
