# -*- coding: utf-8 -*-
"""
RippleLoadScanTest - 输出纹波负载扫描测试
==========================================

使用示波器测量 DUT 输出纹波峰峰值，负载电流从 0A 到额定值按步进扫描，
记录全过程中最大纹波值及对应波形，最终判定纹波是否在规格内。

测试步骤：
  setup：示波器初始化（AC 耦合 / 带宽限制 / 刻度=纹波规格/3 / 偏移0）
  execute：
    1. 开机自检
    2. AC 源切换至测试条件输入电压、频率
    3. 诱骗器协议设置
    4. 负载缓调扫描（示波器滚动，扫描结束后停止保存）
       - 初始带载 I_rated，稳定 1s
       - 下降：I_rated → 0A（步进 0.05A，每步 1s）
       - 上升：0A → I_rated（步进 0.05A，每步 1s）
       - 扫描完成：示波器 STOP，保存波形，读取峰峰值
    5. 依据最大纹波 < 纹波要求 判定 PASS/FAIL
    6. AC OFF，电子负载短路，完全下电

输出字段（COLS）：
  序号 / 用例名称 / 输入条件 / 协议 / 输出电压(V) / 输出电流(A) /
  测试电流 / 纹波实测数据 / 纹波要求 / 测试结论 / 测试波形 / 备注
"""

import time
import os
from ..base import TestCase
from typing import Dict, Any, List, Optional

sys_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys
sys.path.insert(0, sys_path)
from logger_config import info, warning


class OutputRippleLoadScanTest(TestCase):
    """
    输出纹波负载扫描测试。
    每个测试条件输出 1 行（最大纹波行），附最终结论。
    """

    # 示波器时基（20ms/div，10 div = 200ms 窗口）
    TIME_BASE_S = 0.020

    # 负载扫描步进（A）
    LOAD_STEP_A = 0.05

    # 每步稳定等待时间（s）
    STEP_WAIT_S = 1.0

    # 报告列定义
    COLS = [
                ("输入条件",          16),
                ("协议",              12),
                ("输出电压(V)",       13),
                ("输出电流(A)",       13),
                ("缓调范围&步进",     18),
                ("纹波要求",          12),
                ("纹波实测数据(mV)",  16), 
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
            name="OutputRippleLoadScanTest",
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
            warning("[RippleLoadScan] 示波器未连接")
            return

        ch = int(self.params.get("osc_output_ch", 2))

        # 时基（全局固定）
        osc.set_timebase(self.TIME_BASE_S)

        # 通道配置：AC 耦合，带宽限制开
        osc.set_channel_on(ch)
        osc.set_channel_coupling(ch, "AC")
        osc.set_bandwidth_limit(ch, "ON")
        scale_v = (self.spec.get("纹波要求_mV_hi", 100.0) / 1000.0) / 4.0
        osc.set_voltage_scale(ch, max(scale_v, 0.001))
        osc.set_channel_offset(ch, 0.0)

        # 触发配置：AUTO 模式
        osc.set_trigger_mode("AUTO")
        osc.set_trigger_source(f"CHAN{ch}")
        osc.set_trigger_level(0.0)
        osc.set_trigger_slope("BOTH")

        # 配置 VPP 测量（峰峰值）
        osc.add_measurement(ch, "VPP")

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """执行输出纹波负载扫描测试。"""
        ac      = instruments.get("AC_SOURCE")
        eload   = instruments.get("ELOAD")
        osc     = instruments.get("OSC")
        sniffer = instruments.get("SNIFFER")

        conditions = self.test_conditions or self.params.get("test_conditions") or []
        if not conditions:
            warning("[RippleLoadScan] 无测试条件，跳过执行")
            return

        ch = int(self.params.get("osc_output_ch", 2))
        ripple_spec = self.spec.get("纹波要求_mV_hi", 100.0)

        for cond_idx, cond in enumerate(conditions):
            if len(cond) < 5:
                continue

            # 解析 test_condition（5 元组）
            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = \
                cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            input_cond = f"{int(vin_cfg)}V_{int(freq_cfg)}Hz"
            cond_label = f"{proto_label}/{vout_target}V/{iout_target}A"

            # 更新当前 params（供 _save_waveform 命名使用）
            self.params["vin"]         = float(vin_cfg) if vin_cfg else 220.0
            self.params["freq"]        = float(freq_cfg) if freq_cfg else 50.0
            self.params["vout_target"] = float(vout_target) if vout_target else 5.0
            self.params["iout_target"] = float(iout_target) if iout_target else 3.0
            self.params["proto_label"] = str(proto_label) if proto_label else "PD-PDO1"

            # 提前计算功率分段后的有效电流
            iout_eff = self._get_effective_iout(float(vin_cfg), float(vout_target), float(iout_target))
            if iout_eff != iout_target:
                info(f"[RippleLoadScan] 功率分段降流：Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # ---- 步骤1：开机自检（用测试条件电压，最多3次清除重试）----
            startup_ok, _, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            self.measurements[f"startup_ok_c{cond_idx+1}"] = startup_ok
            if not startup_ok:
                info(f"[RippleLoadScan] 条件「{cond_label}」开机自检失败：{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self.sub_results.append(self._make_result(
                    input_cond=input_cond,
                    proto_label=proto_label,
                    vout_target=vout_target,
                    iout_eff=iout_eff,
                    test_current="N/A",
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
            sniffer_ok = self._step_setup_sniffer(sniffer, proto_label, vout_target, iout_target)
            time.sleep(2.0)
            if not sniffer_ok:
                warning(f"[RippleLoadScan] 条件「{cond_label}」诱骗器设置失败，继续执行")

            # ---- 步骤4：负载电流扫描（0A → iout_eff，步进 0.05A）----
            self._run_load_scan(
                ac, eload, osc, ch,
                input_cond, proto_label,
                vout_target, iout_eff,
                ripple_spec
            )

            # ---- 步骤5：放电下电 ----
            self._step_discharge(ac, eload)

    def _run_load_scan(self, ac, eload, osc, ch,
                       input_cond, proto_label,
                       vout_target, iout_eff,
                       ripple_spec):
        """
        负载缓调扫描（已预判功率分段）：Iout_eff → 0A → Iout_eff，步进 0.05A，每步 1s。
        示波器全程滚动（RUN），扫描结束后暂停并读取峰峰值。
        """
        i_rated = float(iout_eff)
        if i_rated <= 0:
            warning("[RippleLoadScan] 额定输出电流 <= 0，跳过扫描")
            return

        step = self.LOAD_STEP_A

        # 计算扫描总时长，动态设置示波器时基（8格显示完整扫描过程）
        # 总时长 = (下降步数 + 上升步数) × 每步时长
        # 下降步数 = I_rated/step，上升步数 = I_rated/step
        num_steps_down = max(1, int(round(i_rated / step)))
        num_steps_up = num_steps_down
        total_scan_s = (num_steps_down + num_steps_up) * self.STEP_WAIT_S
        # 8格显示，time_per_div = 总时长 / 8
        time_per_div = total_scan_s / 8.0

        if osc:
            osc.set_timebase_mode("ROLL")
            osc.set_timebase(time_per_div)
            osc.clear_screen()
            osc.run()

        info(f"[RippleLoadScan] 扫描总时长={total_scan_s:.0f}s，时基={time_per_div:.1f}s/div（8格）")

        # 下降序列：I_rated → 0（含0）
        down_currents = [round(i_rated * i / num_steps_down, 4) for i in range(num_steps_down, -1, -1)]
        # 上升序列：0 → I_rated（不含0，避开重复）
        up_currents = [round(i_rated * i / num_steps_up, 4) for i in range(1, num_steps_up + 1)]

        # 初始负载设为额定值
        if eload:
            eload.set_mode_cc(i_rated)
            eload.input_on()

        info(f"[RippleLoadScan] 扫描开始：I_rated={i_rated}A，步进={step}A，每步={self.STEP_WAIT_S}s")
        info(f"[RippleLoadScan] 下降 {len(down_currents)} 步 + 上升 {len(up_currents)} 步")

        # ---- 阶段1：下降 I_rated → 0A ----
        for i_load in down_currents:
            if eload:
                eload.set_mode_cc(i_load)
            time.sleep(self.STEP_WAIT_S)

        # ---- 阶段2：上升 0A → I_rated ----
        for i_load in up_currents:
            if eload:
                eload.set_mode_cc(i_load)
            time.sleep(self.STEP_WAIT_S)

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
            info(f"[RippleLoadScan] 扫描完成 | VPP={ripple_mv:.1f}mVpp")

            wave_path = self._save_waveform(
                osc, input_cond, proto_label,
                vout_target, iout_eff,
                i_rated, ripple_mv, ripple_spec
            )

        # 关闭负载
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
        self.measurements["max_test_current"] = i_rated

        self.sub_results.append(self._make_result(
            input_cond=input_cond,
            proto_label=proto_label,
            vout_target=vout_target,
            iout_eff=iout_eff,
            test_current=f"0~{i_rated}A/{step}A",
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
                     test_current: str, ripple_mv: float, ripple_spec: float,
                     wave_path: str,
                     overall_pass: bool, fail_reason: str,
                     skipped: bool) -> dict:
        """
        组装单条测试结果（sub_result）。
        字段名与 COLS 列头一致，供报告写入器直接查找。
        """
        return {
            "输入条件":           input_cond,
            "协议":               proto_label,
            "输出电压(V)":        vout_target,
            "输出电流(A)":        iout_eff,
            "缓调范围&步进":       test_current,
            "纹波实测数据(mV)":   round(ripple_mv, 2),
            "纹波要求":           ripple_spec,
            "测试波形":           wave_path,
            "测试结论":           "SKIP" if skipped else ("PASS" if overall_pass else "FAIL"),
            "备注":               fail_reason,
            # 内部字段（供结论逻辑使用，不写入报告单元格）
            "overall_pass":      overall_pass,
            "skipped":           skipped,
        }

    # ---------- _save_waveform ----------
    def _save_waveform(self, osc, input_cond: str,
                       proto_label: str, vout: float, iout: float,
                       test_current: float,
                       ripple_mv: float = 0.0,
                       ripple_spec: float = 0.0) -> Optional[str]:
        """
        波形保存，文件名加入扫描电流信息。
        格式：{用例名}_{输入条件}_{协议}_Vout{电压}V_Iout{电流}A_I{扫描电流}A.png
        """
        if osc is None:
            return None
        base_dir = self._get_waveform_dir()
        fname = (f"{self.name}_{input_cond}_{proto_label}"
                 f"_Vout{vout}V_Iout{iout}A_I{test_current:.1f}A.png")
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
