# -*- coding: utf-8 -*-
"""
OutputRippleLoadScanTest - 输出纹波负载扫描测试
==============================================

使用示波器测量 DUT 输出纹波峰峰值，负载电流从 0A 到额定值按步进扫描，
记录全过程中最大纹波值及对应波形，最终判定纹波是否在规格内。

【test_conditions 格式】
  List[dict]，每项字段：vin / freq / proto / vout / iout

【测试流程（每个条件）】

  setup()     初始化示波器通道（AC 耦合 / 带宽限制 / 刻度 / AUTO 触发）
  execute()   遍历条件，逐条件执行以下步骤
  verify()    所有 sub_result 均 PASS 才返回 True

  每条件步骤：
    1. 开机自检（基类 startup_self_check，最多6次清除重试）
    2. 诱骗器协议配置（基类 _step_setup_sniffer）
    3. 示波器准备（动态时基，8格显示完整扫描窗口）
    4. 负载电流缓调扫描
       - 初始带载 iout_eff，稳定 1s
       - 下降：iout_eff → 0A（步进 0.05A，每步 1s）
       - 上升：0A → iout_eff（步进 0.05A，每步 1s）
       - 示波器全程滚动，扫描完成后 STOP，读取峰峰值
    5. 判定 PASS/FAIL，下电

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


class OutputRippleLoadScanTest(TestCase):
    """输出纹波负载扫描测试。"""

    # 示波器时基（20ms/div，10 div = 200ms 窗口）
    TIME_BASE_S = 0.020
    # 负载扫描步进（A）
    LOAD_STEP_A = 0.05
    # 每步稳定等待时间（s）
    STEP_WAIT_S = 1.0

    # 报告列定义（序号/用例名称由 report_generator._flatten() 自动注入）
    COLS = [
    # 注意：「测试结论」列不定义在 COLS 中，
    # 由 report_generator._flatten() 统一注入（prefix 列）。

        ("输入条件",          16),
        ("协议",              12),
        ("输出电压(V)",       13),
        ("输出电流(A)",       13),
        ("缓调范围&步进",    25),
        ("纹波实测数据(mV)", 16),
        ("纹波要求",          12),
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
            name="OutputRippleLoadScanTest",
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
            warning("[RippleLoadScan] 示波器未连接")
            return

        ch = int(self.params.get("osc_output_ch", 2))

        # 时基（全局固定 20ms/div）
        osc.set_timebase(self.TIME_BASE_S)

        # 通道配置：AC 耦合，带宽限制开
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
        """执行输出纹波负载扫描测试。

        遍历 test_conditions，逐条件执行：开机自检 → 协议配置 →
        负载双向扫描（iout_eff → 0 → iout_eff）→ 读取最大纹波 →
        记录结果 → 下电。
        """
        ac    = self._ac(instruments)
        eload = self._eload(instruments)
        osc   = self._osc(instruments)
        snf   = self._sniffer(instruments)

        conditions = self.params.get("test_conditions", [])
        if not conditions:
            warning("[RippleLoadScan] 无测试条件，跳过执行")
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
                info(f"[RippleLoadScan] 条件「{cond_label}」功率分段降流："
                     f"Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # --- 步骤1：开机自检 ---
            startup_ok, _, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            if not startup_ok:
                info(f"[RippleLoadScan] 条件「{cond_label}」开机自检失败："
                     f"{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self.sub_results.append(self._make_result(
                    input_cond=input_cond,
                    proto_label=proto_label,
                    vout_target=round(vout_target, 3),
                    iout_eff=round(iout_eff, 3),
                    test_current="N/A",
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
                warning(f"[RippleLoadScan] 条件「{cond_label}」"
                        f"诱骗器设置失败，继续执行")

            # --- 步骤3~4：负载电流缓调扫描 ---
            self._run_load_scan(
                ac, eload, osc, ch,
                input_cond, proto_label,
                vout_target, iout_eff,
                ripple_spec,
            )

            # --- 步骤5：下电 ---
            self._step_discharge(ac, eload)

    # ---------- _run_load_scan ----------
    def _run_load_scan(
        self, ac, eload, osc, ch,
        input_cond, proto_label,
        vout_target, iout_eff,
        ripple_spec,
    ):
        """
        负载电流缓调双向扫描：iout_eff → 0A → iout_eff，
        步进 0.05A，每步 1s。

        示波器全程 ROLL 滚动，扫描结束后 STOP，读取峰峰值。

        Args:
            iout_eff : 有效负载电流（功率分段后）
        """
        i_rated = float(iout_eff)
        if i_rated <= 0:
            warning("[RippleLoadScan] 额定输出电流 <= 0，跳过扫描")
            return

        step = self.LOAD_STEP_A

        # 动态计算扫描总时长，设置示波器时基（8格显示完整扫描过程）
        num_down = max(1, int(round(i_rated / step)))
        num_up   = num_down
        total_s  = (num_down + num_up) * self.STEP_WAIT_S
        time_per_div = total_s / 8.0

        if osc:
            osc.set_timebase_mode("ROLL")
            osc.set_timebase(time_per_div)
            osc.clear_screen()
            osc.run()

        info(f"[RippleLoadScan] 扫描总时长={total_s:.0f}s，"
             f"时基={time_per_div:.1f}s/div（8格），"
             f"下降{num_down}步+上升{num_up}步")

        # 下降序列：i_rated → 0（含0）
        down = [round(i_rated * i / num_down, 4)
                for i in range(num_down, -1, -1)]
        # 上升序列：0 → i_rated（不含0，避开重复）
        up   = [round(i_rated * i / num_up, 4)
                for i in range(1, num_up + 1)]

        # 初始负载设为额定值
        if eload:
            eload.set_mode_cc(i_rated)
            eload.input_on()

        info(f"[RippleLoadScan] 扫描开始：I={i_rated}A，"
             f"步进={step}A，每步={self.STEP_WAIT_S}s")

        # ---- 阶段1：下降 i_rated → 0A（支持暂停/停止）----
        for i_load in down:
            if self.is_stop_requested():
                break
            while self.is_pause_requested() and not self.is_stop_requested():
                time.sleep(0.2)
            if eload:
                eload.set_mode_cc(i_load)
            time.sleep(self.STEP_WAIT_S)

        # ---- 阶段2：上升 0A → i_rated（支持暂停/停止）----
        for i_load in up:
            if self.is_stop_requested():
                break
            while self.is_pause_requested() and not self.is_stop_requested():
                time.sleep(0.2)
            if eload:
                eload.set_mode_cc(i_load)
            time.sleep(self.STEP_WAIT_S)

        # ---- 扫描完成，停止并读取纹波 ----
        ripple_mv, wave_path = 0.0, ""
        if osc:
            osc.stop()
            time.sleep(0.5)
            ripple_v = osc.get_measurement(f"CHAN{ch}", "VPP") or 0.0
            ripple_mv = ripple_v * 1000.0
            info(f"[RippleLoadScan] 扫描完成 | VPP={ripple_mv:.1f}mVpp")
            wave_path = self._save_waveform(
                osc, input_cond, proto_label,
                vout_target, iout_eff,
                i_rated, ripple_mv, ripple_spec,
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
            input_cond=input_cond,
            proto_label=proto_label,
            vout_target=round(vout_target, 3),
            iout_eff=round(iout_eff, 3),
            test_current=f"0~{i_rated}A/{step}A",
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
        test_current: str,
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
            "缓调范围&步进":       test_current,
            "纹波实测数据(mV)":    round(ripple_mv, 2),
            "纹波要求":             ripple_spec,
            "测试波形":             wave_path,
            "测试结论":             "SKIP" if skipped else ("PASS" if overall_pass else "FAIL"),
            "备注":                 fail_reason,
            # 内部字段（供 verify() 判定使用，不写入报告）
            "overall_pass":         overall_pass,
            "skipped":            skipped,
        }

    # ---------- _save_waveform ----------
    def _save_waveform(
        self, osc, input_cond: str,
        proto_label: str, vout: float, iout: float,
        test_current: float,
        ripple_mv: float = 0.0,
        ripple_spec: float = 0.0,
    ) -> Optional[str]:
        """
        波形保存，文件名格式：
        {用例名}_{输入条件}_{协议}_Vout{电压}V_Iout{电流}A_I{扫描电流}A.png
        """
        if osc is None:
            return None
        base_dir = self._get_waveform_dir()
        fname = (f"{self.name}_{input_cond}_{proto_label}"
                 f"_Vout{vout}V_Iout{iout}A_I{test_current}.png")
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
