# -*- coding: utf-8 -*-
"""
OutputOcpProtectTest - 输出过流保护测试
========================================

【测试目标】
  验证 DUT 输出过流时的保护动作，测量实际 OCP 触发点，
  并在恢复后依据保护逻辑（锁死/自恢复）判定 PASS/FAIL。

【test_conditions 格式】
  List[dict]，每项字段：vin / freq / proto / vout / iout

【保护逻辑】
  - latch（锁死）：OCP 触发后掉电，恢复时 Vout < 0.1×Vout_default → 锁死 PASS
  - self（自恢复）：
      1. OCP 触发后掉电，恢复时 Vout > 0.9×Vout_default → 自恢复
      2. 重新诱骗协议调压至 vout_target，验证 Vout ≥ 0.9×vout_target → PASS

【电压基准说明】
  - vout_default：开机自检后实测的真实输出电压（用于 latch 恢复判定）
  - vout_target：测试条件中的目标输出电压（用于 self 重新诱骗及达标判定）
  - vout_test   ：协议配置后功率计实测电压（斜升扫描初始读数参考）

【测试流程（每条条件）】

  setup()       初始化示波器通道（ROLL 模式）
  execute()     遍历条件，逐条件执行以下步骤
  verify()      所有 sub_result 均 PASS 才返回 True

  每条件步骤：
    1. 开机自检（基类 startup_self_check，最多6次清除重试），捕获 vout_default
    2. 诱骗器协议配置（基类 _step_setup_sniffer）
    3. 功率计实测 vout_test（斜升扫描初始读数参考）
    4. 计算 OCP 规格上下限（来自 specs_v2）
    5. 示波器准备（ROLL 模式 + 动态时基 + 自动档位）
    6. 示波器开始采集
    7. 电子负载从额定电流上电
    8. 缓调负载电流寻找 OCP 触发点
       - Vout < 0.1×vout_target → OCP 触发，记录过流点
       - 达 spec_hi 未触发 → FAIL
    9. 恢复测试（latch/self）
    10. 示波器停止，保存波形
    11. 记录 sub_result
    12. 放电下电

【报告字段】
  序号 | 用例名称 | 输入条件 | 协议 | 输出电压(V) | 输出电流(A) |
  保护逻辑 | 规格上限(A) | 规格下限(A) | 过流保护点(A) |
  短路恢复情况 | 测试结论 | 测试波形 | 备注
"""

import time
import os
import sys
from typing import Dict, Any, List
from ..base import TestCase

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class OutputOcpProtectTest(TestCase):
    """输出过流保护测试。"""

    # 报告列定义（序号/用例名称由 report_generator._flatten() 自动注入）
    COLS = [
    # 注意：「测试结论」列不定义在 COLS 中，
    # 由 report_generator._flatten() 统一注入（prefix 列）。

        ("输入条件",      16),
        ("协议",          12),
        ("输出电压(V)",   14),
        ("输出电流(A)",   14),
        ("保护逻辑",      12),
        ("规格上限(A)",   12),
        ("规格下限(A)",   12),
        ("过流保护点(A)", 14),
        ("短路恢复情况",   16),
        ("测试结论",       12),
        ("测试波形",       18),
        ("备注",          28),
    ]

    # 负载电流上限：额定电流的 1.5 倍（当 specs_v2 无 ocp_hi_pct 时使用）
    MAX_OCP_RATIO     = 1.5
    RECOVER_WAIT       = 3.0    # s，恢复判定等待时间
    VOUT_DROP_RATIO   = 0.1    # 扫描时 Vout < vout_target × 此值 → 过流触发
    SELF_RECOVER_RATIO = 0.9    # self: Vout > vout_target × 此值 → 达标
    LOAD_RAMP_STEP     = 0.01   # A，步进电流
    LOAD_RAMP_HOLD     = 1.5    # s，每步保持时间

    # ---------- __init__ ----------
    def __init__(
        self,
        input_voltage_min: float = 90.0,
        input_voltage_max: float = 264.0,
        vout_spec_min: float = None,
        vout_spec_max: float = None,
        product_type: str = "charger",
        test_conditions: List[dict] = None,
        settle_time: float = None,
        prot_vars: dict = None,
    ):
        """
        Args:
            input_voltage_min/max : 输入电压范围（AC 源）
            vout_spec_min/max    : 输出电压规格上下限
            product_type         : 产品类型，"charger" 或 "adapter"
            test_conditions      : 测试条件列表，每项 dict，
                                  字段：vin / freq / proto / vout / iout
            settle_time          : 等待时间（s），默认 2.0
            prot_vars            : 保护配置 dict，字段：输出过流保护_mode
        """
        self.settle_time = settle_time if settle_time is not None else 2.0
        self.prot_vars   = prot_vars or {}
        self.sub_results: List[dict] = []

        super().__init__(
            name="OutputOcpProtectTest",
            instruments=["AC_SOURCE", "ELOAD", "SNIFFER", "OSC", "POWER_METER"],
            params={
                "input_voltage_min": input_voltage_min,
                "input_voltage_max": input_voltage_max,
                "vout_spec_min":    vout_spec_min,
                "vout_spec_max":    vout_spec_max,
                "product_type":     product_type,
                "settle_time":      self.settle_time,
                "test_conditions":  test_conditions,
            },
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """通用仪器初始化 + 参数缓存。"""
        self.sub_results = []
        super().setup(instruments)

        self.osc_output_ch = int(self.params.get("osc_output_ch", 2))
        self.test_conditions = getattr(self, "test_conditions", []) or self.params.get("test_conditions", [])
        self.protection_logic = self.params.get("protection_logic", {})
        self.load_startup_current = float(self.params.get("load_startup_current", 0.1))

        osc = instruments.get("OSC")
        if osc and getattr(osc, "_connected", False):
            osc.set_channel_on(self.osc_output_ch)
            osc.set_timebase_mode("ROLL")

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """执行输出过流保护测试。

        遍历 test_conditions，逐条件执行：开机自检 → 协议配置 →
        OCP 扫描 → 恢复判定（latch/self）→ 保存波形 → 记录结果。
        """
        ac    = self._ac(instruments)
        eload = self._eload(instruments)
        snf   = self._sniffer(instruments)
        osc   = self._osc(instruments)
        pm    = self._pwrmeter(instruments)

        for cond in self.test_conditions:
            if len(cond) < 5:
                continue

            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = (
                cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            )
            input_cond = f"{int(vin_cfg)}V_{int(freq_cfg)}Hz"
            cond_label = f"{proto_label}/{vout_target}V/{iout_target}A"

            # 功率分段降流
            iout_eff = self._get_effective_iout(
                float(vin_cfg), float(vout_target), float(iout_target)
            )
            if iout_eff != iout_target:
                info(f"[OCP] 条件「{cond_label}」功率分段降流："
                     f"Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # --- 步骤1：开机自检，捕获 vout_default ---
            startup_ok, vout_default, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            if not startup_ok:
                warning(f"[OCP] {cond_label} 开机自检失败：{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self._add_result(
                    input_cond=input_cond, proto_label=proto_label,
                    vout_target=round(vout_target, 3), iout_eff=round(iout_eff, 3),
                    protect_mode="", spec_lo=0.0, spec_hi=0.0,
                    ocp_point=0.0, recover_status="SKIP",
                    test_pass=False, fail_reason=fail_reason, waveform="",
                )
                continue

            # --- 步骤2：诱骗器协议配置 ---
            self._step_setup_sniffer(snf, proto_label, vout_target, iout_eff)
            time.sleep(2.0)

            # --- 步骤3：功率计实测 vout_test（斜升扫描初始读数参考）---
            vout_test = self._measure_vout(pm, vout_target)

            # --- 步骤4：计算 OCP 规格上下限 ---
            ocp_lo_pct = self.spec.get("输出过流点_pct_lo")
            ocp_hi_pct = self.spec.get("输出过流点_pct_hi")
            if ocp_lo_pct is not None and ocp_lo_pct > 0:
                spec_lo = ocp_lo_pct / 100.0 * float(iout_eff)
            else:
                spec_lo = 0.0
            if ocp_hi_pct is not None and ocp_hi_pct > 0:
                spec_hi = ocp_hi_pct / 100.0 * float(iout_eff)
            else:
                spec_hi = float(iout_eff) * self.MAX_OCP_RATIO

            # --- 步骤5~6：示波器准备 + 开始采集 ---
            self._osc_prepare(osc, self.osc_output_ch, vout_test, spec_hi)
            if osc:
                try:
                    osc.run()
                except Exception as e:
                    warning(f"[OCP] 示波器启动失败: {e}")

            # --- 步骤7~8：电子负载上电 + 缓调电流寻找 OCP 触发点 ---
            self._step_setup_eload(eload, iout_eff)
            ocp_triggered, ocp_point, vout_at_trigger = self._ramp_eload_find_ocp(
                eload, pm, vout_target, iout_eff, spec_hi, cond_label
            )

            # --- 步骤9：恢复测试（latch/self）---
            recover_status, test_pass, fail_reason, spec_lo, spec_hi = \
                self._recover_test(
                    eload, pm, snf,
                    vout_default, vout_target, iout_eff,
                    ocp_triggered, ocp_point,
                    spec_lo, spec_hi,
                    proto_label,
                )

            # --- 步骤10~11：保存波形 + 记录结果 ---
            wave_path = ""
            if osc and getattr(osc, "_connected", False):
                osc.stop()
                wave_path = osc.save_screenshot(os.path.join(
                    self._get_waveform_dir(),
                    f"{self.name}_{input_cond}_{proto_label}_"
                    f"{vout_target}V_{iout_eff:.3f}A.png"
                ))

            latch_on = self.protection_logic.get("输出过流保护_mode", "") == "latch"
            self_on  = self.protection_logic.get("输出过流保护_mode", "") == "self"
            protect_mode_ui = "锁死" if latch_on else ("自恢复" if self_on else "未知")
            self._add_result(
                input_cond=input_cond, proto_label=proto_label,
                vout_target=round(vout_target, 3), iout_eff=round(iout_eff, 3),
                protect_mode=protect_mode_ui,
                spec_lo=spec_lo, spec_hi=spec_hi,
                ocp_point=ocp_point,
                recover_status=recover_status,
                test_pass=test_pass, fail_reason=fail_reason,
                waveform=wave_path,
            )

            # --- 步骤12：下电 ---
            self._step_discharge(ac, eload)

    # ---------- _osc_prepare ----------
    def _osc_prepare(self, osc, ch_out: int, vout_test: float, spec_hi: float):
        """
        示波器准备：动态计算总扫描时长，配置 ROLL 模式和时基。

        时长 = 斜升步数×每步时间 + 恢复等待 + 5s 余量。
        先切 ROLL 模式，set_timebase_for_duration 才会使用 ROLL 档位表选时基。
        """
        if osc is None:
            return
        try:
            ocp_hi_pct = self.spec.get("输出过流点_pct_hi")
            if ocp_hi_pct and ocp_hi_pct > 0:
                i_rated = spec_hi / (ocp_hi_pct / 100.0)
            else:
                i_rated = spec_hi / self.MAX_OCP_RATIO
            num_steps  = max(1, int((spec_hi - i_rated) / self.LOAD_RAMP_STEP))
            sweep_time = num_steps * self.LOAD_RAMP_HOLD
            total_time = sweep_time + self.RECOVER_WAIT + 5.0
            info(f"[OCP] 示波器：斜升{num_steps}步({i_rated:.2f}A→{spec_hi:.2f}A) "
                 f"={sweep_time}s 总窗口{total_time:.0f}s")

            osc.set_timebase_mode("ROLL")
            osc.set_timebase_for_duration(total_time)
            osc.auto_config_channel(ch_out, v_peak=float(vout_test), coupling="DC")
        except Exception as e:
            warning(f"[OCP] 示波器准备失败: {e}")

    # ---------- _measure_vout ----------
    def _measure_vout(self, pm, vout_target: float) -> float:
        """用功率计测量输出电压（备选：pm 为 None 时回退 vout_target）。"""
        if pm is None:
            return float(vout_target)
        try:
            return abs(pm.measure_voltage(channel="CH2"))
        except Exception:
            return float(vout_target)

    # ---------- _ramp_eload_find_ocp ----------
    def _ramp_eload_find_ocp(
        self, eload, pm, vout_target, iout_eff, i_max, cond_label
    ) -> tuple:
        """
        缓调电子负载电流，寻找 OCP 触发点。

        电流从 iout_eff 起逐渐增加至 i_max（spec_hi），
        触发条件：Vout < vout_target × VOUT_DROP_RATIO。
        OCP 触发后等待 10s 观察保护状态。

        Returns:
            (ocp_triggered: bool, ocp_point: float|None, vout_at_trigger: float)
        """
        current = float(iout_eff)
        while current <= i_max + 1e-9:
            if self.is_stop_requested():
                return False, None, 0.0
            while self.is_pause_requested() and not self.is_stop_requested():
                time.sleep(0.2)
            if eload:
                try:
                    eload.set_mode_cc(round(current, 3))
                except Exception as e:
                    warning(f"[OCP] set_mode_cc({current:.3f}A) 异常: {e}，提前终止扫描")
                    return False, None, 0.0

            elapsed = 0.0
            while elapsed < self.LOAD_RAMP_HOLD:
                if self.is_stop_requested():
                    return False, None, 0.0
                while self.is_pause_requested() and not self.is_stop_requested():
                    time.sleep(0.2)
                time.sleep(0.2)
                elapsed += 0.2

            vout = self._measure_vout(pm, vout_target)
            info(f"[OCP] {cond_label} I={current:.3f}A Vout={vout:.3f}V")

            if vout < float(vout_target) * self.VOUT_DROP_RATIO:
                info(f"[OCP] OCP 触发！I={current:.3f}A Vout={vout:.3f}V，等待10s观察保护状态")
                elapsed = 0.0
                while elapsed < 10.0:
                    if self.is_stop_requested():
                        return False, None, 0.0
                    while self.is_pause_requested() and not self.is_stop_requested():
                        time.sleep(0.2)
                    time.sleep(0.2)
                    elapsed += 0.2
                return True, round(current, 3), round(vout, 3)

            current += self.LOAD_RAMP_STEP

        return False, None, 0.0

    # ---------- _recover_test ----------
    def _recover_test(
        self, eload, pm, snf,
        vout_default, vout_target, iout_eff,
        ocp_triggered, ocp_point,
        spec_lo, spec_hi,
        proto_label,
    ) -> tuple:
        """
        过流后恢复测试，分两级判定：

        【第1级 - 恢复电压判定】（触发 OCP 后立即执行）
          latch：Vout < 0.1×vout_default → 锁死 PASS/FAIL
          self ：Vout > 0.9×vout_default → 进入第2级
                 Vout ≤ 0.9×vout_default → 自恢复异常 FAIL

        【第2级 - 重新诱骗达标判定】（仅 self 模式，第1级通过后执行）
          重新诱骗协议调压至 vout_target，
          Vout ≥ 0.9×vout_target → 自恢复 PASS
          Vout < 0.9×vout_target → 自恢复异常 FAIL

        未触发 OCP：直接返回 FAIL（过流点超出规格上限）。

        Args:
            vout_default : 开机自检后实测的输出电压（恢复判定基准）
            vout_target  : 测试条件目标电压（重新诱骗目标 + 达标判定基准）
            iout_eff     : 有效负载电流

        Returns:
            (recover_status, test_pass, fail_reason, spec_lo, spec_hi)
        """
        if not ocp_triggered:
            return "未触发", False, (
                f"过流点超出规格上限 {spec_hi:.3f}A"), spec_lo, spec_hi

        latch_on = self.protection_logic.get("输出过流保护_mode", "") == "latch"
        self_on  = self.protection_logic.get("输出过流保护_mode", "") == "self"

        # 恢复第1步：切小电流，等待稳定（支持暂停/停止）
        if eload:
            eload.set_mode_cc(self.load_startup_current)
        elapsed = 0.0
        while elapsed < self.RECOVER_WAIT:
            if self.is_stop_requested():
                return "SKIP", False, "用户停止", spec_lo, spec_hi
            while self.is_pause_requested() and not self.is_stop_requested():
                time.sleep(0.2)
            time.sleep(0.2)
            elapsed += 0.2
        vout_recover = self._measure_vout(pm, vout_default)
        info(f"[OCP] 恢复电压 Vout={vout_recover:.3f}V"
             f"（基准={vout_default:.3f}V）")

        # latch 模式：恢复电压判定
        if vout_recover < vout_default * 0.1:
            recover_status = "锁死"
            if latch_on:
                ocp_pass = (spec_lo <= ocp_point <= spec_hi)
                fail_reason = "" if ocp_pass else (
                    f"OCP点{ocp_point:.3f}A超规格("
                    f"{spec_lo:.2f}~{spec_hi:.2f}A)")
                return recover_status, ocp_pass, fail_reason, spec_lo, spec_hi
            return recover_status, False, "保护逻辑为自恢复但实际为锁死", spec_lo, spec_hi

        # self 模式：恢复电压判定通过，进入重新诱骗达标验证
        recover_status = "自恢复"
        if self_on:
            self._step_setup_sniffer(snf, proto_label, vout_target, iout_eff)
            if eload:
                eload.set_mode_cc(float(iout_eff))
            elapsed = 0.0
            while elapsed < 10.0:
                if self.is_stop_requested():
                    return "SKIP", False, "用户停止", spec_lo, spec_hi
                while self.is_pause_requested() and not self.is_stop_requested():
                    time.sleep(0.2)
                time.sleep(0.2)
                elapsed += 0.2
            vout_final = self._measure_vout(pm, vout_target)
            passed = (vout_final >= float(vout_target) * self.SELF_RECOVER_RATIO)
            fail_reason = "" if passed else (
                f"自恢复后Vout={vout_final:.3f}V"
                f"<{self.SELF_RECOVER_RATIO*100:.0f}%×{vout_target}V目标")
            return recover_status, passed, fail_reason, spec_lo, spec_hi
        return recover_status, False, "保护逻辑为锁死但实际为自恢复", spec_lo, spec_hi

    # ---------- _add_result ----------
    def _add_result(
        self, input_cond, proto_label, vout_target, iout_eff,
        protect_mode, spec_lo, spec_hi, ocp_point, recover_status,
        test_pass, fail_reason, waveform,
    ):
        """
        组装单条 sub_result，字段名与 COLS 列头一一对应
        （序号/用例名称由 report_generator._flatten() 注入，此处不重复）。
        """
        conclusion = "SKIP" if recover_status == "SKIP" else (
            "PASS" if test_pass else "FAIL")
        self.sub_results.append({
            "输入条件":        input_cond,
            "协议":            proto_label,
            "输出电压(V)":     vout_target,
            "输出电流(A)":     iout_eff,
            "保护逻辑":        protect_mode,
            "规格上限(A)":     spec_hi,
            "规格下限(A)":     spec_lo,
            "过流保护点(A)":   ocp_point,
            "短路恢复情况":    recover_status,
            "测试结论":        conclusion,
            "测试波形":        waveform,
            "备注":            fail_reason,
            # 内部字段（供 verify() 判定使用，不写入报告）
            "overall_pass":    test_pass,
            "fail_reason":   fail_reason,
        })

    # ---------- verify ----------
    def verify(self) -> bool:
        """所有 sub_result 均 PASS 才返回 True。"""
        return bool(self.sub_results) and all(
            r["overall_pass"] or r.get("recover_status") == "SKIP"
            for r in self.sub_results
        )

    # ---------- to_dict ----------
    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        return d
