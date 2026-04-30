# -*- coding: utf-8 -*-
"""
OutputRippleNoiseTest - 输出纹波测试
====================================

使用示波器测量 DUT 输出纹波峰峰值，判断是否在规格内。
每个测试条件的每个负载点（0% / 50% / 100%）输出一行报告。

【test_conditions 格式】
  List[dict]，每项字段：vin / freq / proto / vout / iout

【测试流程（每个条件 × 三个负载点）】

  setup()     初始化示波器通道（AC 耦合 / 带宽限制 / 刻度 / AUTO 触发 / VPP）
  execute()   遍历条件 → 每个条件测 0%/50%/100% 三个负载点
  verify()    所有 sub_result 均 PASS 才返回 True

  每负载点步骤：
    1. 开机自检（基类 startup_self_check，最多6次清除重试）
    2. 诱骗器协议配置（基类 _step_setup_sniffer）
    3. 设置目标负载电流，等待 2s 稳定
    4. 清屏，等 3s，示波器 STOP，读取 VPP
    5. 保存波形，示波器重新 RUN
    6. 判定 PASS/FAIL

  三个负载点之间不独立上下电（与 SCP/OCP 不同），连续测量更省时间。

【报告字段】
  序号 | 用例名称 | 输入条件 | 协议 | 输出电压(V) | 输出电流(A) |
  负载点 | 纹波要求 | 纹波实测值(mV) |
  测试结论 | 测试波形 | 备注
"""

import time
import os
import sys
from typing import Dict, Any, List, Optional
from ..base import TestCase

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class OutputRippleNoiseTest(TestCase):
    """输出纹波测试。"""

    # 示波器时基（20ms/div，10 div = 200ms 窗口）
    TIME_BASE_S = 0.020
    # 负载点列表（%）
    LOAD_POINTS = [0, 50, 100]

    # 报告列定义（序号/用例名称由 report_generator._flatten() 自动注入）
    COLS = [
    # 注意：「测试结论」列不定义在 COLS 中，
    # 由 report_generator._flatten() 统一注入（prefix 列）。

        ("输入条件",          16),
        ("协议",              12),
        ("输出电压(V)",       13),
        ("输出电流(A)",       13),
        ("负载点",             9),
        ("纹波要求",          12),
        ("纹波实测值(mV)",   16),
        ("测试结论",       12),
        ("测试波形",           18),
        ("备注",              32),
    ]

    # ---------- __init__ ----------
    def __init__(
        self,
        ripple_max_mv: float = 100.0,
        product_type: str = "charger",
        test_conditions: List[dict] = None,
        osc_output_ch: int = 2,
    ):
        """
        Args:
            ripple_max_mv:   纹波规格上限（mVpp）
            product_type:    产品类型，"charger" 或 "adapter"
            test_conditions: 测试条件列表，每项 dict，
                           字段：vin / freq / proto / vout / iout
            osc_output_ch:  示波器输出通道编号（默认2）
        """
        self.sub_results: List[dict] = []

        super().__init__(
            name="OutputRippleNoiseTest",
            instruments=["AC_SOURCE", "ELOAD", "OSC", "SNIFFER", "POWER_METER"],
            params={
                "osc_output_ch":    osc_output_ch,
                "product_type":     product_type,
                "test_conditions":  test_conditions,
                "timebase_s":       self.TIME_BASE_S,
            },
            spec={
                "纹波要求_mV_hi": ripple_max_mv,
            },
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """示波器初始化：AC 耦合 / 带宽限制 / 刻度 / AUTO 触发 / VPP 测量。"""
        self.sub_results = []
        super().setup(instruments)

        osc = instruments.get("OSC")
        if osc is None:
            warning("[Ripple] 示波器未连接")
            return

        ch = int(self.params.get("osc_output_ch", 2))

        # 时基（全局固定 20ms/div）
        osc.set_timebase(self.TIME_BASE_S)

        # 通道配置：AC 耦合，带宽限制开
        osc.set_channel_on(ch)
        osc.set_channel_coupling(ch, "AC")
        osc.set_bandwidth_limit(ch, True)   # bool，不是字符串
        scale_v = (self.spec.get("纹波要求_mV_hi", 100.0) / 1000.0) / 5.0
        osc.set_voltage_scale(ch, max(scale_v, 0.01))
        osc.set_channel_offset(ch, 0.0)

        # 触发配置：AUTO 模式，双沿触发
        osc.set_trigger_mode("AUTO")
        osc.set_trigger_source(f"CHAN{ch}")
        osc.set_trigger_level(0.0)
        osc.set_trigger_slope("BOTH")

        # 配置 VPP 测量（峰峰值）
        osc.add_measurement(ch, "VPP")

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """执行输出纹波测试。

        遍历 test_conditions，每条件测三个负载点（0%/50%/100%），
        连续上电测量，不独立下电（省时间）。
        """
        ac    = self._ac(instruments)
        eload = self._eload(instruments)
        osc   = self._osc(instruments)
        snf   = self._sniffer(instruments)

        conditions = self.params.get("test_conditions", [])
        if not conditions:
            warning("[Ripple] 无测试条件，跳过执行")
            return

        ch = int(self.params.get("osc_output_ch", 2))
        ripple_spec = self.spec.get("纹波要求_mV_hi", 100.0)

        for cond in conditions:
            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = (
                cond["vin"], cond["freq"], cond["proto"],
                cond["vout"], cond["iout"],
            )
            input_cond = f"{int(vin_cfg)}V_{int(freq_cfg)}Hz"
            cond_label = f"{proto_label}/{vout_target}V/{iout_target}A"

            # 功率分段降流
            iout_eff = self._get_effective_iout(
                float(vin_cfg), float(vout_target), float(iout_target)
            )
            if iout_eff != iout_target:
                info(f"[Ripple] 条件「{cond_label}」功率分段降流："
                     f"Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # --- 步骤1：开机自检 ---
            startup_ok, _, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            if not startup_ok:
                info(f"[Ripple] 条件「{cond_label}」开机自检失败："
                     f"{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                for pct in self.LOAD_POINTS:
                    self.sub_results.append(self._make_result(
                        input_cond=input_cond,
                        proto_label=proto_label,
                        vout_target=round(vout_target, 3),
                        iout_target=round(iout_eff, 3),
                        load_pct=pct,
                        ripple_spec=ripple_spec,
                        ripple_mv=0.0,
                        wave_path="",
                        overall_pass=False,
                        fail_reason=f"开机自检失败：{fail_reason}",
                        skipped=True,
                    ))
                continue

            # --- 步骤2：启动示波器 + 诱骗器协议配置 ---
            if osc:
                osc.run()
            sniffer_ok = self._step_setup_sniffer(
                snf, proto_label, float(vout_target), float(iout_eff)
            )
            time.sleep(2.0)
            if not sniffer_ok:
                warning(f"[Ripple] 条件「{cond_label}」诱骗器设置失败，继续执行")

            # --- 步骤3~6：依次测试三个负载点 ---
            for pct in self.LOAD_POINTS:
                i_load = iout_eff * pct / 100.0

                if eload:
                    eload.set_mode_cc(i_load)
                    eload.input_on()
                time.sleep(2.0)

                if osc:
                    osc.clear_screen()
                time.sleep(3.0)

                # STOP，读取纹波
                ripple_mv, wave_path = 0.0, ""
                if osc:
                    osc.stop()
                    time.sleep(0.3)
                    ripple_v = osc.get_measurement(f"CHAN{ch}", "VPP") or 0.0
                    ripple_mv = ripple_v * 1000.0
                    info(f"[Ripple] 负载 {pct}% | VPP={ripple_mv:.1f}mVpp")
                    wave_path = self._save_waveform(
                        osc, input_cond, proto_label,
                        vout_target, iout_eff, pct,
                        ripple_mv, ripple_spec,
                    )
                    osc.run()   # 恢复采集，下一个负载点继续

                # 判定
                pass_flag = ripple_mv <= ripple_spec
                fail_reason = "" if pass_flag else (
                    f"纹波{ripple_mv:.1f}mV > 规格{ripple_spec}mV")

                self.sub_results.append(self._make_result(
                    input_cond=input_cond,
                    proto_label=proto_label,
                    vout_target=round(vout_target, 3),
                    iout_target=round(iout_eff, 3),
                    load_pct=pct,
                    ripple_spec=ripple_spec,
                    ripple_mv=ripple_mv,
                    wave_path=wave_path,
                    overall_pass=pass_flag,
                    fail_reason=fail_reason,
                    skipped=False,
                ))

            # 全部负载点测完，下电
            self._step_discharge(ac, eload)

    # ---------- _make_result ----------
    def _make_result(
        self, *, input_cond: str,
        proto_label: str, vout_target: float, iout_target: float,
        load_pct: int,
        ripple_spec: float, ripple_mv: float,
        wave_path: str,
        overall_pass: bool, fail_reason: str,
        skipped: bool,
    ) -> dict:
        """
        组装单条 sub_result，字段名与 COLS 列头一一对应
        （序号/用例名称由 report_generator._flatten() 注入，此处不重复）。
        """
        return {
            "输入条件":          input_cond,
            "协议":              proto_label,
            "输出电压(V)":       vout_target,
            "输出电流(A)":       iout_target,
            "负载点":           f"{load_pct}%",
            "纹波要求":          ripple_spec,
            "纹波实测值(mV)":   round(ripple_mv, 2),
            "测试波形":          wave_path,
            "测试结论":          "SKIP" if skipped else ("PASS" if overall_pass else "FAIL"),
            "备注":              fail_reason,
            # 内部字段（供 verify() 判定使用，不写入报告）
            "overall_pass":      overall_pass,
            "skipped":          skipped,
        }

    # ---------- _save_waveform ----------
    def _save_waveform(
        self, osc, input_cond: str,
        proto_label: str, vout: float, iout: float,
        load_pct: int = 0,
        ripple_mv: float = 0.0,
        ripple_spec: float = 0.0,
    ) -> Optional[str]:
        """
        波形保存，文件名格式：
        {用例名}_{输入条件}_{协议}_Vout{电压}V_Iout{电流}A_{负载点}pct.png
        """
        if osc is None:
            return None
        base_dir = self._get_waveform_dir()
        fname = (f"{self.name}_{input_cond}_{proto_label}"
                 f"_Vout{vout}V_Iout{iout}A_{load_pct}pct.png")
        try:
            return osc.save_screenshot(os.path.join(base_dir, fname))
        except Exception:
            return None

    # ---------- verify ----------
    def verify(self) -> bool:
        """所有 sub_result 均 PASS 才返回 True。"""
        return bool(self.sub_results) and all(
            r["overall_pass"] or r.get("skipped")
            for r in self.sub_results
        )

    # ---------- to_dict ----------
    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        return d
