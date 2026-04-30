# -*- coding: utf-8 -*-
"""
NoLoadPowerTest - 输入空载功耗测试
===================================

【测试目标】
  验证 DUT 在空载（无负载）状态下的输入功率是否满足规格要求。

【测试条件格式】
  (vin, freq, proto_label, vout_target, iout_target, product_type)
  例: (220.0, 50.0, "PD", 20.0, 3.25, "charger")

【判定逻辑】
  avg_power ∈ [noload_power_lo, noload_power_hi] → PASS

【功率计档位设置】
  - setup：电流量程锁定最小档（0.5A），用于小电流精度
  - 每条条件前：电压档位根据实际 AC 输入电压由驱动自动选择
  - 驱动自动选档：set_voltage_range_auto(ch, vin) → 选 ≥ vin 的最小档

【sub_result 字段】
  input_cond, proto_label, vout_target, iout_target,
  spec_min, spec_max,
  avg_power_w, min_power_w, max_power_w,
  sniffer_ok, overall_pass, fail_reason, waveform, skipped
"""

import time
import os
import sys
import numpy as np
from typing import Dict, Any, List
from ..base import TestCase

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class InputNoLoadPowerTest(TestCase):
    """
    输入空载功耗测试（每条 test_condition 独立执行）。

    仪器依赖：AC_SOURCE / POWER_METER / SNIFFER / ELOAD
    """

    # ─────────────────────────────────────────────────────────────────
    # 常量
    # ─────────────────────────────────────────────────────────────────
    DEFAULT_LOAD_CURRENT       = 0.5    # A（带载电流，用于激活 DUT）
    DEFAULT_LOAD_ON_TIME       = 10.0   # s（带载时间）
    DEFAULT_SETTLE_TIME       = 10.0   # s（功率计稳定等待时间）
    DEFAULT_MEASURE_COUNT     = 10      # 功率计读取次数
    DEFAULT_MEASURE_INTERVAL  = 1.0    # s（每次读取间隔）
    DEFAULT_SETTLE_BEFORE_LOAD = 2.0   # s（带载前等待时间）

    # ---------- 报告列定义 ----------
    # 顺序即 Excel 列顺序，按 COLS 定义顺序渲染所有列
    COLS = [
                ("输入条件",          16),
                ("协议",              14),
                ("输出电压(V)",       14),
                ("规格下限",          11),
                ("规格上限",          11),
                ("平均功率(W)",       15),
                ("最小功率(W)",       15),
                ("最大功率(W)",       15),
                ("测试结论",           11),
                ("备注",              28),
    ]

    # ─────────────────────────────────────────────────────────────────
    # 公开属性
    # ─────────────────────────────────────────────────────────────────
    def __init__(
        self,
        test_conditions: List[dict] = None,
        product_type: str = "charger",
        input_voltage_min: float = 90.0,
        noload_power_lo: float = 0.0,
        noload_power_hi: float = 0.15,
        # __init__ param names kept for backward compatibility; spec dict keys must match UI specs_v2 flat keys
    ):
        self.product_type = product_type
        self.test_conditions = test_conditions or []
        self.input_voltage_min = input_voltage_min
        self.sub_results: List[dict] = []

        super().__init__(
            name="InputNoLoadPowerTest",
            instruments=["AC_SOURCE", "POWER_METER", "SNIFFER", "ELOAD"],
            params={
                "product_type":       product_type,
                "test_conditions":   test_conditions or [],
                "input_voltage_min": input_voltage_min,
                "load_current":      self.DEFAULT_LOAD_CURRENT,
                "load_on_time":      self.DEFAULT_LOAD_ON_TIME,
                "settle_time":       self.DEFAULT_SETTLE_TIME,
                "measure_count":     self.DEFAULT_MEASURE_COUNT,
                "measure_interval":  self.DEFAULT_MEASURE_INTERVAL,
                "settle_time_before_load": self.DEFAULT_SETTLE_BEFORE_LOAD,
            },
            spec={
                "空载功耗_W_lo": noload_power_lo,
                "空载功耗_W_hi": noload_power_hi,
            },
        )

    # =================================================================
    # setup — 仪器初始化 + 功率计最小电流量程预设置
    # =================================================================
    def setup(self, instruments: Dict[str, Any]):
        """
        设备初始化 + 功率计量程设置。

        - 电流量程：锁定最小档（0.5A），用于待机功耗小电流测量精度
        - 电压档位：在每条条件测量前由 _step_load_condition 根据实际 AC 电压设置
        """
        self.sub_results = []
        super().setup(instruments)

        # ---- 缓存 UI 参数 ----
        self.pwr_in_v_ch     = self.params.get("pwr_in_v_ch", "CH1")
        self.load_current    = float(self.params.get("load_current", self.DEFAULT_LOAD_CURRENT))
        self.load_on_time    = float(self.params.get("load_on_time", self.DEFAULT_LOAD_ON_TIME))
        self.settle_time     = float(self.params.get("settle_time", self.DEFAULT_SETTLE_TIME))
        self.measure_count   = int(self.params.get("measure_count", self.DEFAULT_MEASURE_COUNT))
        self.measure_interval = float(self.params.get("measure_interval", self.DEFAULT_MEASURE_INTERVAL))

        pm = instruments.get("POWER_METER")
        if pm:
            try:
                chosen = pm.lock_minimum_current_range(channel=self.pwr_in_v_ch)
                info(f"[NLT] 功率计电流量程锁定最小档 {chosen * 1000:.1f}mA ({self.pwr_in_v_ch})")
            except Exception as e:
                warning(f"[NLT] 功率计电流量程设置失败: {e}")

    # =================================================================
    # execute — 主流程
    #
    #  ┌─────────────────────────────────────────────────────────────┐
    #  │  主测试循环（每条条件执行一次）                              │
    #  │    ① 开机自检                                          │
    #  │    ② 加载测试条件（AC 电压/频率 + 功率计电压档位）        │
    #  │    ③ 诱骗器协议                                        │
    #  │    ④ 电子负载 ON/OFF（激活 DUT）                        │
    #  │    ⑤ 等待稳定，功率计读取多组数据                        │
    #  │    ⑥ 判定：avg_power ∈ [lo, hi] → PASS/FAIL          │
    #  │    ⑦ 放电（下电）                                        │
    #  └─────────────────────────────────────────────────────────────┘
    # =================================================================
    def execute(self, instruments: Dict[str, Any]):
        ac   = instruments.get("AC_SOURCE")
        elod = instruments.get("ELOAD")
        pwr  = instruments.get("POWER_METER")
        snif = instruments.get("SNIFFER")

        conditions = self.test_conditions or self.params.get("test_conditions") or []
        if not conditions:
            warning("[NLT] 无测试条件，跳过执行")
            return

        for cond in conditions:
            if len(cond) < 5:
                continue

            (
                vin_cfg, freq_cfg, proto_label,
                vout_target, iout_target,
            ) = cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]

            input_cond = f"{vin_cfg}V_{freq_cfg}Hz"

            # 提前计算功率分段后的有效电流
            iout_eff = self._get_effective_iout(float(vin_cfg), float(vout_target), float(iout_target))
            if iout_eff != iout_target:
                info(f"[NLT] 功率分段降流：Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # ① 开机自检（用测试条件电压，最多3次清除重试）
            startup_ok, _, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            if not startup_ok:
                info(f"[NLT] 条件「{input_cond}」开机自检失败: {fail_reason}，跳过")
                self._step_discharge(ac, elod)
                self.sub_results.append(
                    self._make_result(
                        input_cond=input_cond,
                        proto_label=proto_label,
                        vout_target=vout_target,
                        avg_power=0.0,
                        min_power=0.0,
                        max_power=0.0,
                        overall_pass=False,
                        fail_reason=fail_reason,
                        skipped=True,
                    )
                )
                continue

            # ② 加载测试条件 + 功率计电压档位
            self._step_load_condition(vin_cfg, pwr)

            # ③ 诱骗器协议
            sniffer_ok = self._step_setup_sniffer(snif, proto_label, vout_target, iout_eff)
            info(f"[NLT] 诱骗器 {proto_label} {'成功' if sniffer_ok else '失败'}")

            # ④ 电子负载 ON/OFF（激活 DUT 进入正常工作状态，功率分段后电流）
            self._step_eload_on_off(elod, iout_eff)

            # ⑤ 等待稳定，功率计读取多组数据
            avg_power, min_power, max_power = self._step_measure_power(pwr)

            # ⑥ 判定
            lo = self.spec.get("空载功耗_W_lo", 0.0)
            hi = self.spec.get("空载功耗_W_hi", 0.15)
            passed = (lo <= avg_power <= hi)
            fail_reason = (
                "" if passed
                else f"空载功率{avg_power}W超出范围[{lo}, {hi}]"
            )

            self.sub_results.append(
                self._make_result(
                    input_cond=input_cond,
                    proto_label=proto_label,
                    vout_target=vout_target,
                    avg_power=avg_power,
                    min_power=min_power,
                    max_power=max_power,
                    overall_pass=passed,
                    fail_reason=fail_reason,
                    skipped=False,
                )
            )

            # ⑦ 放电（下电）
            self._step_discharge(ac, elod)

    # =================================================================
    # 步骤方法
    # =================================================================

    def _step_load_condition(self, vin: float, pm=None):
        """
        步骤②：功率计电压档位设置——

        AC 电压/频率已在 startup_self_check 中设置，本方法仅配置功率计电压档位。

        Args:
            vin:  输入电压（V）（仅用于功率计档位选择）
            pm:   功率计仪器（可选）
        """
        if pm is not None:
            try:
                pm.set_voltage_range_auto(self.pwr_in_v_ch, float(vin))
                info(f"[NLT] 功率计电压档位 → {vin}V ({self.pwr_in_v_ch})")
            except Exception as e:
                warning(f"[NLT] 功率计电压档位设置失败: {e}")

    def _step_eload_on_off(self, elod, iout: float):
        """
        步骤④：电子负载 ON（带载 DEFAULT_LOAD_ON_TIME 秒），然后 OFF。

        用于激活 DUT，使其进入正常工作状态。
        """
        if elod is None:
            return
        try:
            elod.set_mode_cc(iout)
            elod.input_on()
            info(f"[NLT] 电子负载 ON | I={iout}A | 等待{self.load_on_time}s")
            time.sleep(self.load_on_time)
            elod.input_off()
            info("[NLT] 电子负载 OFF")
        except Exception as e:
            warning(f"[NLT] 电子负载控制异常: {e}")

    def _step_measure_power(self, pm) -> tuple:
        """
        步骤⑤：等待 settle_time 稳定后，功率计读取 measure_count 组功率数据，
        求平均 / 最小 / 最大。

        Args:
            pm: 功率计仪器

        Returns:
            (avg_power, min_power, max_power) — 单位 W
        """
        time.sleep(self.settle_time)

        power_samples = []
        if pm:
            for i in range(self.measure_count):
                if self.is_stop_requested():
                    break
                while self.is_pause_requested() and not self.is_stop_requested():
                    time.sleep(0.2)
                try:
                    p = pm.measure_power(channel=self.pwr_in_v_ch)
                    power_samples.append(p)
                    if i % 5 == 0:
                        info(f"[NLT] 功率采样 {i + 1}/{self.measure_count} | {p:.4f}W ({self.pwr_in_v_ch})")
                except Exception:
                    pass
                time.sleep(self.measure_interval)

        if power_samples:
            avg_p = round(float(np.mean(power_samples)), 4)
            min_p = round(float(np.min(power_samples)), 4)
            max_p = round(float(np.max(power_samples)), 4)
        else:
            avg_p = min_p = max_p = 0.0

        info(
            f"[NLT] 功率测量完成 | avg={avg_p}W min={min_p}W max={max_p}W | "
            f"样本数={len(power_samples)}"
        )
        return avg_p, min_p, max_p

    # =================================================================
    # 工具方法
    # =================================================================

    def _make_result(
        self,
        *,
        input_cond: str,
        proto_label: str,
        vout_target,
        avg_power: float,
        min_power: float,
        max_power: float,
        overall_pass: bool,
        fail_reason: str,
        skipped: bool,
    ) -> dict:
        """
        组装单条测试结果（sub_result）。
        字段名即报告列名，直接对应 report_generator 的 COLS 定义。
        """
        lo = self.spec.get("空载功耗_W_lo", 0.0)
        hi = self.spec.get("空载功耗_W_hi", 0.15)
        return {
            "输入条件":       input_cond,
            "南议":          proto_label,
            "输出电压(V)":   vout_target,
            "规格下限":      lo,
            "规格上限":      hi,
            "平均功率(W)":   avg_power,
            "最小功率(W)":   min_power,
            "最大功率(W)":   max_power,
            "测试结论":      "SKIP" if skipped else ("PASS" if overall_pass else "FAIL"),
            "备注":          fail_reason,
            "overall_pass":  overall_pass,
            "fail_reason":   fail_reason,
            "skipped":       skipped,
        }

    # =================================================================
    # 结论
    # =================================================================
    def verify(self) -> bool:
        """所有条件 overall_pass 为 True 才 PASS。"""
        return bool(self.sub_results) and all(
            r["overall_pass"] for r in self.sub_results
        )

    def teardown(self, instruments: Dict[str, Any]):
        """关闭仪器输出，恢复电子负载。"""
        self._step_discharge(
            instruments.get("AC_SOURCE"),
            instruments.get("ELOAD"),
        )

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"]   = self.sub_results
        d["product_type"] = self.product_type
        passed = sum(1 for r in self.sub_results if r["overall_pass"])
        d["sweep_summary"] = {
            "conditions_tested":  len(self.sub_results),
            "passed_conditions": passed,
            "failed_conditions": len(self.sub_results) - passed,
        }
        return d
