# -*- coding: utf-8 -*-
"""
RippleInputScanTest - 输出纹波输入扫描测试
==========================================

使用示波器测量 DUT 输出纹波峰峰值，固定在输入电压下限测试不同协议/输出条件，
记录全过程中最大纹波值及对应波形，最终判定纹波是否在规格内。

测试步骤：
  setup：示波器初始化（AC 耦合 / 带宽限制 / 刻度=纹波规格/3 / 偏移0 / 时基20ms）
  execute（每个条件）：
    1. 开机自检（最低输入电压）
    2. 诱骗器协议设置
    3. 电子负载设置到测试条件输出电流
    4. 输入电压缓调扫描（Vin_cfg → Vin_lo → Vin_cfg，步进 5V，每步 1s）
       - Vin ≥ 180V → freq=50Hz；Vin < 180V → freq=60Hz
       - 示波器全程滚动，扫描完成后 STOP，读取峰峰值，保存波形
    5. 判定 PASS/FAIL，下电

输出字段（COLS）：
  序号 / 用例名称 / 输入条件 / 协议 / 输出电压(V) / 输出电流(A) /
  缓调范围&步进 / 纹波实测数据(mV) / 纹波要求 / 测试结论 / 测试波形 / 备注
"""

import time
import os
from ..base import TestCase
from typing import Dict, Any, List, Optional

sys_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys
sys.path.insert(0, sys_path)
from logger_config import info, warning


class OutputRippleInputScanTest(TestCase):
    """
    输出纹波输入扫描测试。
    每个测试条件输出 1 行（最大纹波行），附最终结论。
    """

    # 示波器时基（20ms/div，10 div = 200ms 窗口）
    TIME_BASE_S = 0.020

    # 报告列定义
    COLS = [
                ("输入条件",          16),
                ("协议",              12),
                ("输出电压(V)",       13),
                ("输出电流(A)",       13),
                ("缓调范围&步进",   18),
                ("纹波实测数据(mV)",  16),
                ("纹波要求",          12),
                ("测试结论",           11),
                ("测试波形",           18),
                ("备注",              32),
    ]

    # ---------- __init__ ----------
    def __init__(self,
                 ripple_max_mv: float = 100.0,
                 product_type: str = "charger",
                 test_conditions: List[dict] = None,
                 osc_output_ch: int = 2,
                 osc_waveform_dir: str = ""):
        """
        Args:
            ripple_max_mv:   纹波规格上限（mVpp）
            product_type:    产品类型，"charger" 或 "adapter"
            test_conditions: 测试条件列表，每项为
                            (vin, freq, proto_label, vout_target, iout_target) 五元组
            osc_output_ch:   示波器输出通道编号（默认2）
            osc_waveform_dir: 波形保存目录
        """
        self.product_type = product_type
        self.test_conditions = test_conditions or []
        self.osc_waveform_dir = osc_waveform_dir
        self.sub_results: List[dict] = []

        super().__init__(
            name="OutputRippleInputScanTest",
            instruments=["AC_SOURCE", "ELOAD", "OSC", "SNIFFER", "POWER_METER"],
            params={
                "osc_output_ch":     osc_output_ch,
                "osc_waveform_dir":  osc_waveform_dir,
                "product_type":      product_type,
                "test_conditions":   test_conditions,
                "timebase_s":        self.TIME_BASE_S,
            },
            spec={
                "纹波要求_mV_hi": ripple_max_mv,
            }
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """初始化仪器状态（仅配置，不上电）。"""
        self.sub_results = []
        super().setup(instruments)

        osc = instruments.get("OSC")
        if osc is None:
            warning("[RippleInputScan] 示波器未连接")
            return

        self.osc_output_ch = int(self.params.get("osc_output_ch", 2))

        # 时基（全局固定）
        osc.set_timebase(self.TIME_BASE_S)

        # ---- 输入电压通道（DC 耦合，带宽限制）----
        osc.set_channel_config(channel=ch_in, coupling="DC",
                              attenuation=in_attn,
                              voltage_scale=100.0,
                              voltage_offset=0.0,
                              bandwidth_limit=True)
        osc.set_channel_on(ch_in)

        # ---- 输出电压通道（AC 耦合，带宽限制）----
        osc.set_channel_on(ch_out)
        osc.set_channel_coupling(ch_out, "AC")
        osc.set_bandwidth_limit(ch_out, "ON")
        scale_v = (self.spec.get("纹波要求_mV_hi", 100.0) / 1000.0) / 4.0
        osc.set_voltage_scale(ch_out, max(scale_v, 0.001))
        osc.set_channel_offset(ch_out, 0.0)

        # 触发配置：AUTO 模式
        osc.set_trigger_mode("AUTO")
        osc.set_trigger_source(f"CHAN{ch_out}")
        osc.set_trigger_level(0.0)
        osc.set_trigger_slope("BOTH")

        # 配置 VPP 测量（峰峰值）
        osc.add_measurement(ch_out, "VPP")

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """执行输出纹波输入扫描测试。"""
        ac      = instruments.get("AC_SOURCE")
        eload   = instruments.get("ELOAD")
        osc     = instruments.get("OSC")
        sniffer = instruments.get("SNIFFER")

        conditions = self.test_conditions
        if not conditions:
            warning("[RippleInputScan] 无测试条件，跳过执行")
            return

        ripple_spec = self.spec.get("纹波要求_mV_hi", 100.0)

        # 获取 UI 配置的输入电压范围（扫描范围）
        product_info = self.params.get("product_info", {})
        vin_lo_ui = float(product_info.get("input_voltage_lo") or
                          self.params.get("input_voltage_lo") or 90.0)
        vin_hi = float(product_info.get("input_voltage_hi") or
                      self.params.get("input_voltage_hi") or 264.0)

        for cond_idx, cond in enumerate(conditions):
            if len(cond) < 5:
                continue

            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = \
                cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            input_cond = f"{int(vin_cfg)}V_{int(freq_cfg)}Hz"
            cond_label = f"{proto_label}/{vout_target}V/{iout_target}A"

            # 更新当前 params（供 _save_waveform 命名使用）
            self.params["vin"] = float(vin_cfg) if vin_cfg else 220.0
            self.params["freq"] = float(freq_cfg) if freq_cfg else 50.0
            self.params["vout_target"] = float(vout_target) if vout_target else 5.0
            self.params["iout_target"] = float(iout_target) if iout_target else 3.0
            self.params["proto_label"] = str(proto_label) if proto_label else "PD-PDO1"

            # 提前计算功率分段后的有效电流
            iout_eff = self._get_effective_iout(float(vin_cfg), float(vout_target), float(iout_target))
            if iout_eff != float(iout_target):
                info(f"[RippleInputScan] 条件「{cond_label}」功率分段降流：Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # ---- 步骤1：开机自检（用该条件电压，最多3次清除重试）----
            startup_ok, measured_vout, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            self.measurements[f"startup_ok_c{cond_idx+1}"] = startup_ok
            if not startup_ok:
                info(f"[RippleInputScan] 条件「{cond_label}」开机自检失败：{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self.sub_results.append(self._make_result(
                    input_cond=f"{int(vin_lo_ui)}~{int(vin_cfg)}V",
                    proto_label=proto_label,
                    vout_target=vout_target,
                    iout_eff=iout_eff,
                    test_vin_freq="N/A",
                    ripple_mv=0.0,
                    ripple_spec=ripple_spec,
                    wave_path="",
                    overall_pass=False,
                    fail_reason=f"开机自检失败：{fail_reason}",
                    skipped=True,
                ))
                continue

            # ---- 步骤2：自检通过后，启动示波器RUN ----
            if osc:
                osc.run()

            # ---- 步骤3：诱骗器协议设置 ----
            sniffer_ok = self._step_setup_sniffer(sniffer, proto_label, vout_target, iout_eff)
            time.sleep(2.0)
            if not sniffer_ok:
                warning(f"[RippleInputScan] 条件「{cond_label}」诱骗器设置失败，继续执行")

            # ---- 步骤4：电子负载设置（功率分段后电流）----
            if eload:
                eload.set_mode_cc(float(iout_eff))
                eload.input_on()
            time.sleep(1.0)

            # ---- 步骤5：输入电压缓调扫描（vin_cfg → vin_lo，功率随电压段切换）----
            self._run_vin_scan(
                ac, eload, osc, self.osc_output_ch,
                vin_lo_ui, float(vin_cfg),
                proto_label, vout_target, iout_target, iout_eff,
                ripple_spec
            )

            # ---- 步骤6：放电下电 ----
            self._step_discharge(ac, eload)

    # ---------- _run_vin_scan ----------
    def _run_vin_scan(self, ac, eload, osc, ch,
                      vin_lo, vin_cfg,
                      proto_label, vout_target, iout_target, iout_eff,
                      ripple_spec):
        """
        输入电压缓调扫描（已预判功率分段）：vin_cfg → vin_lo → vin_cfg，双向。
        - Vin ≥ 180V：HV段，保持 iout_target
        - Vin < 180V：LV段，切换到降功率电流 iout_eff
        示波器全程滚动（RUN），扫描结束后暂停并读取峰峰值。
        """
        step = 5.0

        def vin_segments_desc(start, end, step):
            """生成降序电压序列（包含端点）"""
            vals = list(range(int(start), int(end) - 1, -int(step)))
            if vals[-1] != int(end):
                vals.append(int(end))
            return vals

        def vin_segments_asc(start, end, step):
            """生成升序电压序列（包含端点）"""
            vals = list(range(int(start), int(end) + 1, int(step)))
            if vals[-1] != int(end):
                vals.append(int(end))
            return vals

        # 双向扫描序列：下行 vin_cfg→vin_lo + 上行 vin_lo→vin_cfg
        down_vals = vin_segments_desc(vin_cfg, vin_lo, step)
        up_vals   = vin_segments_asc(vin_lo, vin_cfg, step)
        total_scan_s = (len(down_vals) + len(up_vals)) * 1.0
        time_per_div = total_scan_s / 8.0

        if osc:
            osc.set_timebase_mode("ROLL")
            osc.set_timebase(time_per_div)
            osc.clear_screen()
            osc.run()

        info(f"[RippleInputScan] 扫描 {len(down_vals)}+{len(up_vals)} 步，每步=1s，总计={total_scan_s:.0f}s，范围={int(vin_lo)}~{int(vin_cfg)}V")

        def set_vin(vin):
            freq = 50.0 if vin >= 180.0 else 60.0
            if ac:
                ac.set_voltage(vin)
                ac.set_frequency(freq)
            return freq

        hv_crossed = [False]   # HV→LV 已跨越
        lv_crossed = [False]   # LV→HV 已跨越
        prev_iout = [None]

        def set_eload_by_vin(vin, prev_vin):
            """根据当前输入电压设置电子负载，HV/LV分段按 180V；跨边界时逐步过渡。"""
            if eload:
                i_target = self._get_effective_iout(vin, vout_target, iout_target)
                # 检测 HV→LV 下行跨越 180V
                cross_hv = (prev_vin is not None and prev_vin >= 180 and vin <= 180 and not hv_crossed[0])
                # 检测 LV→HV 上行跨越 180V
                cross_lv = (prev_vin is not None and prev_vin <= 180 and vin >= 180 and not lv_crossed[0])
                if cross_hv and prev_iout[0] is not None:
                    delta = i_target - prev_iout[0]
                    steps = 5
                    step_size = delta / steps
                    for s in range(steps):
                        i_step = prev_iout[0] + step_size * (s + 1)
                        eload.set_mode_cc(float(i_step))
                        time.sleep(0.5)
                    hv_crossed[0] = True
                elif cross_lv and prev_iout[0] is not None:
                    delta = i_target - prev_iout[0]
                    steps = 5
                    step_size = delta / steps
                    for s in range(steps):
                        i_step = prev_iout[0] + step_size * (s + 1)
                        eload.set_mode_cc(float(i_step))
                        time.sleep(0.5)
                    lv_crossed[0] = True
                else:
                    eload.set_mode_cc(float(i_target))
                prev_iout[0] = i_target
                return i_target
            return None

        # ---- 下行 vin_cfg → vin_lo ----
        info(f"[RippleInputScan] 下行扫描开始：{int(vin_cfg)}V → {int(vin_lo)}V")
        prev_vin = None
        for vin in down_vals:
            freq = set_vin(vin)
            i_log = set_eload_by_vin(vin, prev_vin)
            prev_vin = vin
            info(f"  Vin={int(vin)}V freq={int(freq)}Hz → eload={'%.3f' % i_log}A")
            time.sleep(1.0)

        # ---- 上行 vin_lo → vin_cfg ----
        info(f"[RippleInputScan] 上行扫描开始：{int(vin_lo)}V → {int(vin_cfg)}V")
        prev_vin = None
        for vin in up_vals:
            # 上行（LV→HV）：先设置负载（触发渐进过渡），再设置电压
            i_log = set_eload_by_vin(vin, prev_vin)
            prev_vin = vin
            freq = set_vin(vin)
            info(f"  Vin={int(vin)}V freq={int(freq)}Hz → eload={'%.3f' % i_log}A")
            time.sleep(1.0)

        # ---- 扫描完成，停止示波器 ----
        ripple_mv = 0.0
        wave_path = ""
        if osc:
            osc.stop()
            time.sleep(0.5)
            ripple_v = osc.get_measurement(f"CHAN{ch}", "VPP")
            if ripple_v is None:
                ripple_v = 0.0
            ripple_mv = ripple_v * 1000.0
            info(f"[RippleInputScan] 扫描完成 | VPP={ripple_mv:.1f}mVpp")
            wave_path = self._save_waveform(
                osc, vin_cfg, 50.0,
                proto_label, vout_target, iout_eff,
                ripple_mv, ripple_spec
            )

        # 关闭电子负载
        if eload:
            eload.input_off()

        # ---- 判定并记录结果 ----
        pass_flag = ripple_mv <= ripple_spec
        if ripple_mv <= 0:
            fail_reason = "未测得有效纹波数据"
        elif not pass_flag:
            fail_reason = f"纹波{ripple_mv:.1f}mV > 规格{ripple_spec:.1f}mV"
        else:
            fail_reason = ""

        self.measurements["max_ripple_mv"] = ripple_mv

        self.sub_results.append(self._make_result(
            input_cond=f"{int(vin_lo)}~{int(vin_cfg)}V",
            proto_label=proto_label,
            vout_target=vout_target,
            iout_eff=iout_eff,
            test_vin_freq=f"{int(vin_cfg)}V→{int(vin_lo)}V→{int(vin_cfg)}V/{int(step)}V",
            ripple_mv=ripple_mv,
            ripple_spec=ripple_spec,
            wave_path=wave_path,
            overall_pass=pass_flag,
            fail_reason=fail_reason,
            skipped=False,
        ))

    # ---------- _make_result ----------
    def _make_result(self, *, input_cond: str,
                     proto_label: str, vout_target: float, iout_eff: float,
                     test_vin_freq: str,
                     ripple_mv: float, ripple_spec: float,
                     wave_path: str,
                     overall_pass: bool, fail_reason: str,
                     skipped: bool) -> dict:
        """
        组装单条测试结果（sub_result）。
        字段名与 COLS 列头一致，供报告写入器直接查找。
        """
        return {
            "输入条件":              input_cond,
            "协议":                  proto_label,
            "输出电压(V)":           vout_target,
            "输出电流(A)":           iout_eff,
            "缓调范围&步进":        test_vin_freq,
            "纹波实测数据(mV)":      round(ripple_mv, 2),
            "纹波要求":              ripple_spec,
            "测试波形":              wave_path,
            "测试结论":              "SKIP" if skipped else ("PASS" if overall_pass else "FAIL"),
            "备注":                  fail_reason,
            # 内部字段（供结论逻辑使用，不写入报告单元格）
            "overall_pass":         overall_pass,
            "skipped":              skipped,
        }

    # ---------- _save_waveform ----------
    def _save_waveform(self, osc,
                       vin: float, freq: float,
                       proto_label: str, vout: float, iout_eff: float,
                       ripple_mv: float = 0.0,
                       ripple_spec: float = 0.0) -> Optional[str]:
        """
        波形保存，文件名加入输入电压和频率信息。
        格式：{用例名}_Vin{电压}V_Freq{频率}Hz_{协议}_Vout{电压}V_Iout{电流}A.png
        """
        if osc is None:
            return None
        base_dir = self._get_waveform_dir()
        fname = (f"{self.name}_Vin{int(vin)}V_Freq{int(freq)}Hz"
                 f"_{proto_label}_Vout{vout}V_Iout{iout_eff}A.png")
        fpath = os.path.join(base_dir, fname)
        try:
            return osc.save_screenshot(fpath)
        except Exception:
            return None

    # ---------- verify ----------
    def verify(self) -> bool:
        """最大纹波 < 纹波规格 才 PASS。"""
        return bool(self.sub_results) and all(r["overall_pass"] for r in self.sub_results)

    # ---------- teardown ----------
    def teardown(self, instruments: Dict[str, Any]):
        """关闭仪器输出，恢复示波器普通模式。"""
        self._step_discharge(
            instruments.get("AC_SOURCE"),
            instruments.get("ELOAD"),
        )
        osc = instruments.get("OSC")
        if osc:
            try:
                osc.set_timebase_mode("MAIN")
            except Exception:
                pass

    # ---------- to_dict ----------
    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        return d
