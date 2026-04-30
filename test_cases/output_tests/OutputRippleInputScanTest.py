# -*- coding: utf-8 -*-
"""
OutputRippleInputScanTest - 输出纹波输入扫描测试
================================================

使用示波器测量 DUT 输出纹波峰峰值，固定在输入电压下限测试不同协议/输出条件，
在输入电压缓调扫描过程中记录最大纹波值及对应波形，最终判定纹波是否在规格内。

【test_conditions 格式】
  List[dict]，每项字段：vin / freq / proto / vout / iout

【测试流程（每个条件）】

  setup()     初始化示波器通道（AC 耦合 / 带宽限制 / 刻度 / 触发配置）
  execute()   遍历条件，逐条件执行以下步骤
  verify()    所有 sub_result 均 PASS 才返回 True

  每条件步骤：
    1. 开机自检（基类 startup_self_check，最多6次清除重试）
    2. 诱骗器协议配置（基类 _step_setup_sniffer）
    3. 电子负载设置到测试条件电流（功率分段后 iout_eff）
    4. 输入电压缓调扫描（Vin_cfg → Vin_lo → Vin_cfg，步进 5V，每步 1s）
       - Vin ≥ 180V → freq=50Hz；Vin < 180V → freq=60Hz
       - HV/LV 跨边界时分 5 步渐进切换负载电流
       - 示波器全程滚动（ROLL），扫描完成后 STOP，读取峰峰值
    5. 判定 PASS/FAIL，下电

  注意：本测试仅用示波器 CH2 测量输出纹波，输入电压由 AC 源实时调节，
        无需示波器单独配置输入电压通道。

【报告字段】
  序号 | 用例名称 | 输入条件 | 协议 | 输出电压(V) | 输出电流(A) |
  缓调范围&步进 | 纹波实测数据(mV) | 纹波要求 |
  测试结论 | 测试波形 | 备注
"""

import time
import os
import sys
from typing import Dict, Any, List, Optional
from ..base import TestCase

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class OutputRippleInputScanTest(TestCase):
    """输出纹波输入扫描测试。"""

    # 示波器时基（20ms/div，10 div = 200ms 窗口）
    TIME_BASE_S = 0.020

    # 报告列定义（序号/用例名称由 report_generator._flatten() 自动注入）
    COLS = [
    # 注意：「测试结论」列不定义在 COLS 中，
    # 由 report_generator._flatten() 统一注入（prefix 列）。

        ("输入条件",         16),
        ("协议",             12),
        ("输出电压(V)",      13),
        ("输出电流(A)",      13),
        ("缓调范围&步进",   25),
        ("纹波实测数据(mV)", 16),
        ("纹波要求",         12),
        ("测试结论",       12),
        ("测试波形",          18),
        ("备注",             32),
    ]

    # ---------- __init__ ----------
    def __init__(
        self,
        ripple_max_mv: float = 100.0,
        product_type: str = "charger",
        test_conditions: List[dict] = None,
        osc_output_ch: int = 2,
        osc_waveform_dir: str = "",
    ):
        """
        Args:
            ripple_max_mv:    纹波规格上限（mVpp）
            product_type:     产品类型，"charger" 或 "adapter"
            test_conditions: 测试条件列表，每项 dict，
                           字段：vin / freq / proto / vout / iout
            osc_output_ch:   示波器输出通道编号（默认2）
            osc_waveform_dir: 波形保存目录
        """
        self.sub_results: List[dict] = []

        super().__init__(
            name="OutputRippleInputScanTest",
            instruments=["AC_SOURCE", "ELOAD", "OSC", "SNIFFER", "POWER_METER"],
            params={
                "osc_output_ch":    osc_output_ch,
                "osc_waveform_dir": osc_waveform_dir,
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
            warning("[RippleInputScan] 示波器未连接")
            return

        self.osc_output_ch = int(self.params.get("osc_output_ch", 2))
        self.osc_input_ch  = int(self.params.get("osc_input_ch",   4))
        ch = self.osc_output_ch

        # 时基（全局固定 20ms/div）
        osc.set_timebase(self.TIME_BASE_S)
        
        osc.set_channel_config(channel=self.osc_input_ch, coupling="DC",
                              voltage_scale=100.0,
                              voltage_offset=0.0,
                              bandwidth_limit=True)
        osc.set_channel_on(self.osc_input_ch)

        # 输出电压通道：AC 耦合，带宽限制开（测量纹波用 DC 会引入偏置）
        osc.set_channel_on(ch)
        osc.set_channel_coupling(ch, "AC")
        osc.set_bandwidth_limit(ch, True)   # bool，不是字符串
        scale_v = (self.spec.get("纹波要求_mV_hi", 100.0) / 1000.0) / 4.0
        osc.set_voltage_scale(ch, max(scale_v, 0.001))
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
        """执行输出纹波输入扫描测试。

        遍历 test_conditions，逐条件执行：开机自检 → 协议配置 →
        输入电压双向扫描（Vin_cfg → Vin_lo → Vin_cfg）→
        读取最大纹波 → 记录结果 → 下电。
        """
        ac    = self._ac(instruments)
        eload = self._eload(instruments)
        osc   = self._osc(instruments)
        snf   = self._sniffer(instruments)

        conditions = self.params.get("test_conditions", [])
        if not conditions:
            warning("[RippleInputScan] 无测试条件，跳过执行")
            return

        ripple_spec = self.spec.get("纹波要求_mV_hi", 100.0)

        # 获取 UI 配置的输入电压扫描下限
        product_info = self.params.get("product_info", {})
        vin_lo_ui = float(
            product_info.get("input_voltage_lo")
            or self.params.get("input_voltage_lo")
            or 90.0
        )

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
                info(f"[RippleInputScan] 条件「{cond_label}」功率分段降流："
                     f"Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # --- 步骤1：开机自检 ---
            startup_ok, _, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            if not startup_ok:
                info(f"[RippleInputScan] 条件「{cond_label}」开机自检失败："
                     f"{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self.sub_results.append(self._make_result(
                    input_cond=f"{int(vin_lo_ui)}~{int(vin_cfg)}V",
                    proto_label=proto_label,
                    vout_target=round(vout_target, 3),
                    iout_eff=round(iout_eff, 3),
                    test_vin_freq="N/A",
                    ripple_mv=0.0,
                    ripple_spec=ripple_spec,
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
                warning(f"[RippleInputScan] 条件「{cond_label}」"
                        f"诱骗器设置失败，继续执行")

            # --- 步骤3：电子负载设置（iout_eff）---
            if eload:
                eload.set_mode_cc(float(iout_eff))
                eload.input_on()
            time.sleep(1.0)

            # --- 步骤4：输入电压缓调扫描 ---
            self._run_vin_scan(
                ac, eload, osc,
                self.osc_output_ch,
                vin_lo_ui, float(vin_cfg),
                proto_label, float(vout_target), float(iout_target), float(iout_eff),
                ripple_spec,
            )

            # --- 步骤5：下电 ---
            self._step_discharge(ac, eload)

    # ---------- _run_vin_scan ----------
    def _run_vin_scan(
        self, ac, eload, osc, ch,
        vin_lo, vin_cfg,
        proto_label, vout_target, iout_target, iout_eff,
        ripple_spec,
    ):
        """
        输入电压缓调双向扫描：vin_cfg → vin_lo → vin_cfg，步进 5V，每步 1s。

        电压分段规则：Vin ≥ 180V → freq=50Hz；Vin < 180V → freq=60Hz。
        负载分段规则：HV 段用 iout_target，LV 段用 iout_eff，
                      HV↔LV 跨边界时分 10 步渐进切换。

        示波器全程 ROLL 滚动，扫描结束后 STOP，读取峰峰值。

        Args:
            vin_lo       : 输入电压扫描下限（UI 配置）
            vin_cfg      : 测试条件配置电压（扫描起点/终点）
        """
        step = 5.0

        def make_seq(start: float, end: float, step_v: float, desc: bool) -> list:
            """生成电压序列（包含端点）。"""
            direction = -int(step_v) if desc else int(step_v)
            vals = list(range(int(start), int(end) + direction, direction))
            last = int(end)
            if vals and vals[-1] != last:
                vals.append(last)
            return vals

        down_vals = make_seq(vin_cfg, vin_lo,  step, True)
        up_vals   = make_seq(vin_lo,  vin_cfg, step, False)
        total_s   = (len(down_vals) + len(up_vals)) * 1.0
        time_per_div = total_s / 4.0

        if osc:
            osc.set_timebase_mode("ROLL")
            osc.set_timebase(time_per_div)
            osc.clear_screen()
            osc.run()

        info(f"[RippleInputScan] 扫描 {len(down_vals)}+{len(up_vals)} 步，"
             f"每步=1s，总计={total_s:.0f}s，"
             f"范围={int(vin_lo)}~{int(vin_cfg)}V")

        def set_vin(vin: float) -> float:
            freq = 50.0 if vin >= 180.0 else 60.0
            if ac:
                ac.set_voltage(vin)
                ac.set_frequency(freq)
            return freq

        hv_crossed, lv_crossed = False, False
        prev_iout, prev_vin = None, None

        def set_eload_smooth(vin: float) -> float:
            nonlocal hv_crossed, lv_crossed, prev_iout, prev_vin
            if eload is None:
                return float(iout_target)
            i_target = self._get_effective_iout(vin, vout_target, iout_target)

            # HV→LV 下行跨越 180V
            if (prev_vin is not None
                    and prev_vin >= 180 > vin
                    and not hv_crossed
                    and prev_iout is not None):
                for s in range(1, 10):
                    eload.set_mode_cc(prev_iout + (i_target - prev_iout) * s / 10.0)
                    time.sleep(2)
                hv_crossed = True
            # LV→HV 上行跨越 180V
            elif (prev_vin is not None
                    and prev_vin < 180 <= vin
                    and not lv_crossed
                    and prev_iout is not None):
                for s in range(1, 10):
                    eload.set_mode_cc(prev_iout + (i_target - prev_iout) * s / 10.0)
                    time.sleep(2)
                lv_crossed = True
            else:
                eload.set_mode_cc(i_target)

            prev_iout = i_target
            prev_vin  = vin
            return i_target

        # ---- 下行 vin_cfg → vin_lo ----
        info(f"[RippleInputScan] 下行：{int(vin_cfg)}V → {int(vin_lo)}V")
        prev_vin = None
        for vin in down_vals:
            if self.is_stop_requested():
                break
            while self.is_pause_requested() and not self.is_stop_requested():
                time.sleep(0.2)
            freq = set_vin(vin)
            i_log = set_eload_smooth(vin)
            prev_vin = vin
            info(f"  Vin={int(vin)}V freq={int(freq)}Hz → I={i_log:.3f}A")
            time.sleep(1.0)

        # ---- 上行 vin_lo → vin_cfg ----
        info(f"[RippleInputScan] 上行：{int(vin_lo)}V → {int(vin_cfg)}V")
        hv_crossed, lv_crossed = False, False
        prev_vin = None
        for vin in up_vals:
            if self.is_stop_requested():
                break
            while self.is_pause_requested() and not self.is_stop_requested():
                time.sleep(0.2)
            freq = set_vin(vin)
            i_log = set_eload_smooth(vin)
            prev_vin = vin
            info(f"  Vin={int(vin)}V freq={int(freq)}Hz → I={i_log:.3f}A")
            time.sleep(1.0)

        # ---- 扫描完成，停止并读取纹波 ----
        ripple_mv, wave_path = 0.0, ""
        if osc:
            osc.stop()
            time.sleep(0.5)
            ripple_v = osc.get_measurement(f"CHAN{ch}", "VPP") or 0.0
            ripple_mv = ripple_v * 1000.0
            info(f"[RippleInputScan] 扫描完成 | VPP={ripple_mv:.1f}mVpp")
            wave_path = self._save_waveform(
                osc, vin_cfg, 50.0,
                proto_label, vout_target, iout_eff,
                ripple_mv, ripple_spec,
            )

        if eload:
            eload.input_off()

        # ---- 判定并记录 ----
        if ripple_mv <= 0:
            fail_reason = "未测得有效纹波数据"
            pass_flag   = False
        else:
            pass_flag = ripple_mv <= ripple_spec
            fail_reason = "" if pass_flag else (
                f"纹波{ripple_mv:.1f}mV > 规格{ripple_spec:.1f}mV")

        self.sub_results.append(self._make_result(
            input_cond=f"{int(vin_lo)}~{int(vin_cfg)}V",
            proto_label=proto_label,
            vout_target=round(vout_target, 3),
            iout_eff=round(iout_eff, 3),
            test_vin_freq=f"{int(vin_cfg)}V→{int(vin_lo)}V→{int(vin_cfg)}V/{int(step)}V",
            ripple_mv=ripple_mv,
            ripple_spec=ripple_spec,
            wave_path=wave_path,
            overall_pass=pass_flag,
            fail_reason=fail_reason,
            skipped=False,
        ))

    # ---------- _make_result ----------
    def _make_result(
        self, *, input_cond: str,
        proto_label: str, vout_target: float, iout_eff: float,
        test_vin_freq: str,
        ripple_mv: float, ripple_spec: float,
        wave_path: str,
        overall_pass: bool, fail_reason: str,
        skipped: bool,
    ) -> dict:
        """
        组装单条 sub_result，字段名与 COLS 列头一一对应
        （序号/用例名称由 report_generator._flatten() 注入，此处不重复）。
        """
        return {
            "输入条件":             input_cond,
            "协议":                 proto_label,
            "输出电压(V)":          vout_target,
            "输出电流(A)":          iout_eff,
            "缓调范围&步进":       test_vin_freq,
            "纹波实测数据(mV)":    round(ripple_mv, 2),
            "纹波要求":             ripple_spec,
            "测试波形":             wave_path,
            "测试结论":             "SKIP" if skipped else ("PASS" if overall_pass else "FAIL"),
            "备注":                 fail_reason,
            # 内部字段（供 verify() 判定使用，不写入报告）
            "overall_pass":        overall_pass,
            "skipped":            skipped,
        }

    # ---------- _save_waveform ----------
    def _save_waveform(
        self, osc,
        vin: float, freq: float,
        proto_label: str, vout: float, iout_eff: float,
        ripple_mv: float = 0.0,
        ripple_spec: float = 0.0,
    ) -> Optional[str]:
        """
        波形保存，文件名格式：
        {用例名}_Vin{电压}V_Freq{频率}Hz_{协议}_Vout{电压}V_Iout{电流}A.png
        """
        if osc is None:
            return None
        base_dir = self._get_waveform_dir()
        fname = (f"{self.name}_Vin{int(vin)}V_Freq{int(freq)}Hz"
                 f"_{proto_label}_Vout{vout}V_Iout{iout_eff}A.png")
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
