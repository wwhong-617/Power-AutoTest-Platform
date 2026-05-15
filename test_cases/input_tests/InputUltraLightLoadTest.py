# -*- coding: utf-8 -*-
"""
InputUltraLightLoadTest - 输入极轻载功耗测试
============================================

【测试目标】
  在极轻载功率场景下，测量 DUT 的输入功耗，判断是否在规格范围内。

【测试条件格式】
  {vin, freq, proto, vout, iout}
  例: {"vin": 220.0, "freq": 50.0, "proto": "PD", "vout": 20.0, "iout": 3.25}

【判定逻辑】
  avg_power ∈ [极轻载功耗_lo, 极轻载功耗_hi] → PASS

【负载电流设定】
  Iload = 极轻载功率(W) / Vout_target

【sub_result 字段】
  输入条件, 协议, 输出电压(V), 输出电流(A),
  极轻载功率(W), 设定电流(A),
  规格上限, 规格下限, 实测功耗(W),
  测试结论, 备注, overall_pass, fail_reason, skipped
"""

import time
import os
import sys
import numpy as np
from typing import Dict, Any, List
from ..base import TestCase

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class InputUltraLightLoadTest(TestCase):
    """
    输入极轻载功耗测试（每条 test_condition 独立执行）。

    仪器依赖：AC_SOURCE / POWER_METER / SNIFFER / ELOAD / OSC
    """

    # ─────────────────────────────────────────────────────────────────
    # 常量
    # ─────────────────────────────────────────────────────────────────
    DEFAULT_SETTLE_TIME      = 10.0   # s（功率计稳定等待时间）
    DEFAULT_MEASURE_COUNT    = 10      # 功率计读取次数
    DEFAULT_MEASURE_INTERVAL = 1.0    # s（每次读取间隔）

    # ---------- 报告列定义 ----------
    # 顺序即 Excel 列顺序
    # 注意：「测试结论」列不定义在 COLS 中，
    # 由 report_generator._flatten() 统一注入（prefix 列）。
    COLS = [
        ("输入条件",          16),
        ("协议",              14),
        ("输出电压(V)",       14),
        ("输出电流(A)",       14),
        ("极轻载功率(W)",     14),
        ("设定电流(A)",       12),
        ("规格上限",          11),
        ("规格下限",          11),
        ("实测功耗(W)",       15),
        ("测试结论",          12),
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
        ultra_light_power: float = 0.0,
        ultra_light_power_lo: float = 0.0,
        ultra_light_power_hi: float = 0.15,
    ):
        self.product_type = product_type
        self.sub_results: List[dict] = []

        super().__init__(
            name="InputUltraLightLoadTest",
            instruments=["AC_SOURCE", "POWER_METER", "SNIFFER", "ELOAD", "OSC"],
            params={
                "product_type":      product_type,
                "test_conditions":  test_conditions,
                "input_voltage_min": input_voltage_min,
                "ultra_light_power": ultra_light_power,
                "settle_time":       self.DEFAULT_SETTLE_TIME,
                "measure_count":    self.DEFAULT_MEASURE_COUNT,
                "measure_interval": self.DEFAULT_MEASURE_INTERVAL,
            },
            spec={
                "极轻载功耗_W_lo": ultra_light_power_lo,
                "极轻载功耗_W_hi": ultra_light_power_hi,
            },
        )

    # =================================================================
    # setup — 仪器初始化 + 缓存 UI 参数
    # =================================================================
    def setup(self, instruments: Dict[str, Any]):
        """
        设备初始化 + 参数缓存。
        """
        self.sub_results = []
        super().setup(instruments)

        # ---- 缓存 UI 参数 ----
        self.pwr_in_v_ch      = self.params.get("pwr_in_v_ch", "CH1")
        self.pwr_in_i_ch      = self.params.get("pwr_in_i_ch", "CH1")
        self.pwr_out_v_ch     = self.params.get("pwr_out_v_ch", "CH2")
        self.pwr_out_i_ch     = self.params.get("pwr_out_i_ch", "CH2")
        self.ultra_light_power = float(self.params.get("ultra_light_power", 0.0))
        self.settle_time      = float(self.params.get("settle_time", self.DEFAULT_SETTLE_TIME))
        self.measure_count    = int(self.params.get("measure_count", self.DEFAULT_MEASURE_COUNT))
        self.measure_interval = float(self.params.get("measure_interval", self.DEFAULT_MEASURE_INTERVAL))
        self.test_conditions  = self.test_conditions or self.params.get("test_conditions", [])

        info(f"[ULT] 极轻载功率设定: {self.ultra_light_power}W")

    # =================================================================
    # execute — 主流程
    #
    #  ① 开机自检
    #  ② 诱骗器协议配置
    #  ③ 设置功率计档位（根据输入电压/电流自动选择）
    #  ④ 设置电子负载电流 = 极轻载功率 / Vout_target
    #  ⑤ 等待 10s 稳定
    #  ⑥ 读取功率计输入功率 10 次求平均
    #  ⑦ 判定：avg_power ∈ [lo, hi] → PASS / FAIL
    #  ⑧ 功率计档位设回自动
    #  ⑨ _step_discharge(ac, eload)
    # =================================================================
    def execute(self, instruments: Dict[str, Any]):
        ac    = instruments.get("AC_SOURCE")
        eload = instruments.get("ELOAD")
        pwr   = instruments.get("POWER_METER")
        snif  = instruments.get("SNIFFER")

        conditions = self.test_conditions
        if not conditions:
            warning("[ULT] 无测试条件，跳过执行")
            return

        for cond in conditions:
            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = (
                cond.get("vin"), cond.get("freq"), cond.get("proto", ""),
                cond.get("vout"), cond.get("iout"),
            )

            input_cond  = f"{vin_cfg}V_{freq_cfg}Hz"
            output_cond = f"{proto_label}_Vout{vout_target}V_Iout{iout_target}A"

            # 功率分段后的有效电流
            iout_eff = self._get_effective_iout(float(vin_cfg), float(vout_target), float(iout_target))
            if iout_eff != iout_target:
                info(f"[ULT] 功率分段降流：Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # 设定电流 = 极轻载功率 / Vout_target
            vout_f = float(vout_target)
            if vout_f <= 0:
                info(f"[ULT] 条件「{output_cond}」Vout 无效，跳过")
                self._step_discharge(ac, eload)
                self._add_result(
                    input_cond=input_cond, proto_label=proto_label,
                    vout_target=vout_f, iout_target=iout_target,
                    iout_eff=iout_eff,
                    avg_power=0.0,
                    skipped=True, fail_reason="Vout无效",
                )
                continue

            iout_set = round(self.ultra_light_power / vout_f, 3)

            # ① 开机自检
            startup_ok, _, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            if not startup_ok:
                info(f"[ULT] 条件「{output_cond}」开机自检失败: {fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self._add_result(
                    input_cond=input_cond, proto_label=proto_label,
                    vout_target=vout_f, iout_target=iout_target,
                    iout_eff=iout_eff,
                    avg_power=0.0,
                    skipped=True, fail_reason=fail_reason,
                )
                continue

            # ② 诱骗器协议配置
            self._step_setup_sniffer(snif, proto_label, vout_target, iout_eff)

            # ③ 设置功率计档位（根据输入电压 & 输入电流自动选择）
            self._set_power_meter_ranges(pwr, float(vin_cfg), iout_set)

            # ④ 设置电子负载电流
            if eload and getattr(eload, "_connected", False):
                eload.set_mode_cc(float(iout_set))
                eload.input_on()
                info(f"[ULT] 电子负载 ON | I={iout_set:.3f}A（极轻载功率 {self.ultra_light_power}W / Vout {vout_f}V）")

            # ⑤ 等待稳定
            info(f"[ULT] 条件「{output_cond}」等待 {self.settle_time}s 稳定...")
            time.sleep(self.settle_time)

            # ⑥ 读取功率计输入功率
            avg_power = self._measure_input_power(pwr)

            # ⑦ 判定
            lo = self.spec.get("极轻载功耗_W_lo", 0.0)
            hi = self.spec.get("极轻载功耗_W_hi", 0.15)
            passed = (lo <= avg_power <= hi)
            reason = "" if passed else f"极轻载功耗{avg_power:.4f}W超出范围[{lo}, {hi}]"

            info(f"[ULT] 条件「{output_cond}」实测功耗={avg_power:.4f}W | 规格=[{lo}, {hi}] | {'PASS' if passed else 'FAIL'}")

            self._add_result(
                input_cond=input_cond, proto_label=proto_label,
                vout_target=vout_f, iout_target=iout_target,
                iout_eff=iout_eff,
                avg_power=avg_power,
                skipped=False, fail_reason=reason,
            )

            # ⑧ 功率计档位设回自动
            self._reset_power_meter_ranges(pwr)

            # ⑨ 放电下电
            self._step_discharge(ac, eload)

    # =================================================================
    # 步骤方法
    # =================================================================

    def _set_power_meter_ranges(self, pm, vin: float, iout_set: float):
        """
        步骤③：设置功率计电压/电流量程档位。

        参考 InputEfficiencyTest 的档位选择策略：
        - CH1（输入电压通道）：set_voltage_range_auto(ch, vin)
        - CH1 电流量程：根据最大输出功率估算 Input = Pin = Vout × Iout / 效率
        - CH2（输出电压通道）：set_voltage_range_auto(ch, vout_target)
        """
        if pm is None:
            return
        try:
            # CH1 输入电压档位
            if hasattr(pm, "set_voltage_range_auto"):
                pm.set_voltage_range_auto(self.pwr_in_v_ch, float(vin))

            # CH1 输入电流量程：估算 Pin = Vout × Iout_set / 预设效率
            estimated_pin = float(vin) * iout_set * 0.4 / 0.86 if iout_set > 0 else 0.5
            if hasattr(pm, "set_current_range_auto"):
                pm.set_current_range_auto(self.pwr_in_i_ch, max(estimated_pin / float(vin), 0.1))

            info(f"[ULT] 功率计档位设置完成 | Vin={vin}V Iout_set={iout_set:.3f}A")
        except Exception as e:
            warning(f"[ULT] 功率计档位设置失败: {e}")

    def _reset_power_meter_ranges(self, pm):
        """
        步骤⑧：功率计档位设回自动。
        """
        if pm is None:
            return
        try:
            if hasattr(pm, "set_voltage_range_auto"):
                pm.set_voltage_range_auto(self.pwr_in_v_ch, 300.0)
            if hasattr(pm, "set_current_range_auto"):
                pm.set_current_range_auto(self.pwr_in_i_ch, 20.0)
            info("[ULT] 功率计档位已恢复自动")
        except Exception as e:
            warning(f"[ULT] 功率计档位恢复失败: {e}")

    def _measure_input_power(self, pm) -> float:
        """
        步骤⑥：读取功率计输入功率，循环 measure_count 次求平均。
        """
        samples = []
        if pm:
            for i in range(self.measure_count):
                if self.is_stop_requested():
                    break
                while self.is_pause_requested() and not self.is_stop_requested():
                    time.sleep(0.2)
                try:
                    p = pm.measure_input_power()
                    samples.append(p)
                    if i % 5 == 0:
                        info(f"[ULT] 功率采样 {i + 1}/{self.measure_count} | {p:.4f}W")
                except Exception as e:
                    warning(f"[ULT] 功率读取异常: {e}")
                time.sleep(self.measure_interval)

        if samples:
            return round(float(np.mean(samples)), 4)
        return 0.0

    # =================================================================
    # 工具方法
    # =================================================================

    def _add_result(
        self,
        *,
        input_cond: str,
        proto_label: str,
        vout_target: float,
        iout_target: float,
        iout_eff: float,
        avg_power: float,
        skipped: bool,
        fail_reason: str,
    ):
        """组装单条 sub_result。"""
        lo = self.spec.get("极轻载功耗_W_lo", 0.0)
        hi = self.spec.get("极轻载功耗_W_hi", 0.15)
        iout_set = round(self.ultra_light_power / vout_target, 3) if vout_target > 0 else 0.0

        self.sub_results.append({
            "输入条件":       input_cond,
            "协议":          proto_label,
            "输出电压(V)":   round(vout_target, 3),
            "输出电流(A)":   round(float(iout_target), 3),
            "极轻载功率(W)": self.ultra_light_power,
            "设定电流(A)":   iout_set,
            "规格上限":      hi,
            "规格下限":      lo,
            "实测功耗(W)":   avg_power,
            "测试结论":      "SKIP" if skipped else ("PASS" if (lo <= avg_power <= hi) else "FAIL"),
            "备注":          fail_reason,
            # 内部字段
            "overall_pass":   (lo <= avg_power <= hi) if not skipped else False,
            "fail_reason":    fail_reason,
            "skipped":        skipped,
        })

    # =================================================================
    # 结论
    # =================================================================
    def verify(self) -> bool:
        """所有条件 overall_pass 为 True 才 PASS。"""
        if not self.sub_results:
            return False
        return all(r["overall_pass"] for r in self.sub_results)

    def teardown(self, instruments: Dict[str, Any]):
        """关闭仪器输出，恢复电子负载。"""
        self._step_discharge(
            instruments.get("AC_SOURCE"),
            instruments.get("ELOAD"),
        )

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"]   = self.sub_results
        d["product_type"]  = self.product_type
        passed = sum(1 for r in self.sub_results if r["overall_pass"])
        d["sweep_summary"] = {
            "conditions_tested":  len(self.sub_results),
            "passed_conditions": passed,
            "failed_conditions": len(self.sub_results) - passed,
        }
        return d
