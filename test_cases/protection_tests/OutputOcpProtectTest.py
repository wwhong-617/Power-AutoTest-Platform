# -*- coding: utf-8 -*-
"""
VoutCurrentProtectTest - 输出过流保护测试
==========================================

【测试目标】
  验证 DUT 输出过流时的保护动作，测量实际 OCP 触发点，
  并在恢复后依据保护逻辑（锁死/自恢复）判定 PASS/FAIL。

【test_conditions 格式】
  (vin, freq, proto_label, vout_target, iout_target)

【保护逻辑】
  - latch（锁死）：OCP 触发后掉电，恢复时切换到开机带载电流后 Vout < 0.1×Vout_default
  - self（自恢复）：OCP 触发后掉电，恢复时 Vout 可恢复至 >0.9×Vout_default，重新诱骗协议调压后 PASS

【测试流程（每条条件）】

  setup()    打开示波器 CH2 通道
  步骤1  开机自检           → 基类 startup_self_check()
  步骤2  AC源调压           → _ac_set_voltage(vin_cfg, freq_cfg)
  步骤3  诱骗器协议         → 基类 _step_setup_sniffer()
  步骤4  读取输出电压基准   → _measure_vout() → Vout_test
  步骤5  计算 OCP 规格上限  → spec_hi = ocp_hi_pct × iout_target
  步骤6  示波器准备         → _osc_prepare(spec_hi)：自动档位+时基 → ROLL
  步骤7  示波器开始采集     → osc.run()（ROLL 模式已在步骤6设置好）
  步骤8  电子负载额定电流上电 → 基类 _step_setup_eload()
  步骤9  缓调负载电流       → _ramp_eload_find_ocp(spec_hi)
         · Vout < 0.1×Vout_target → OCP 触发，记录过流点
         · 达 spec_hi 未触发 → 未触发，判 FAIL
  步骤10 恢复测试            → _recover_test()：全程示波器采集
         · latch：Vout < 0.1×Vout_test → 锁死，判规格
         · self：  Vout > 0.9×Vout_test → 自恢复，重新诱骗调压，判 Vout 达标
  步骤11 示波器截图保存     → osc.stop() + osc.save_screenshot()（捕获完整流程）
  步骤12 记录 sub_result
  步骤13 下电              → 基类 _step_power_off()

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

    # ==================== 报告列定义 ====================
    COLS = [
                ("输入条件",          16),
                ("协议",              12),
                ("输出电压(V)",       14),
                ("输出电流(A)",       14),
                ("保护逻辑",          12),
                ("规格上限(A)",       12),
                ("规格下限(A)",       12),
                ("过流保护点(A)",     14),
                ("短路恢复情况",       16),
                ("测试结论",           11),
                ("测试波形",           18),
                ("备注",              28),
    ]

    # ==================== 测试常量 ====================
    MAX_OCP_RATIO     = 1.5    # 负载电流上限：额定电流的 1.5 倍
    RECOVER_WAIT      = 3.0    # s，恢复判定等待时间
    VOUT_DROP_RATIO   = 0.1    # Vout < Vout_target × 此值 → 掉电判定
    SELF_RECOVER_RATIO = 0.9   # Vout > Vout_default × 此值 → 自恢复判定
    LOAD_RAMP_STEP    = 0.01   # A，步进电流
    LOAD_RAMP_HOLD    = 1.5    # s，每步保持时间

    # ==================== __init__ ====================
    def __init__(
        self,
        input_voltage_min: float = 90.0,
        input_voltage_max: float = 264.0,
        vout_spec_min: float = None,
        vout_spec_max: float = None,
        product_type: str = "charger",
        test_conditions: List[dict] = None,
        settle_time: float = None,
        prot_vars: dict = None,   # {"输出过流保护": {"self": 0, "latch": 1}}
    ):
        self.product_type   = product_type
        self.settle_time    = settle_time if settle_time is not None else 2.0
        self.prot_vars      = prot_vars or {}
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
            },
        )

    # ==================== setup ====================
    def setup(self, instruments: Dict[str, Any]):
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

    # ==================== execute ====================
    def execute(self, instruments: Dict[str, Any]):
        ac    = self._ac(instruments)
        eload = self._eload(instruments)
        snf   = self._sniffer(instruments)
        osc   = self._osc(instruments)
        pm    = self._pwrmeter(instruments)

        conditions = self.test_conditions

        for cond in conditions:
            if len(cond) < 5:
                continue

            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            input_cond  = f"{vin_cfg}V_{freq_cfg}Hz"
            cond_label  = f"{proto_label}_Vout{vout_target}V_Iout{iout_target}A"

            # 功率分段
            iout_eff = self._get_effective_iout(float(vin_cfg), float(vout_target), float(iout_target))
            if iout_eff != float(iout_target):
                info(f"[OCP] 条件「{cond_label}」功率分段降流：Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # ── 步骤1：开机自检（用该条件电压，最多3次清除重试）──────
            startup_ok, vout_default, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            if not startup_ok:
                warning(f"[OCP] {cond_label} 开机自检失败: {fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self._add_result(
                    input_cond=input_cond, proto_label=proto_label,
                    vout_target=vout_target, iout_eff=iout_eff,
                    protect_mode="", spec_lo=0.0, spec_hi=0.0,
                    ocp_point=0.0, recover_status="SKIP",
                    test_pass=False, fail_reason=fail_reason, waveform="",
                )
                continue

            # ── 步骤2：诱骗器设置目标电压和协议（切换到测试条件） ────
            self._step_setup_sniffer(snf, proto_label, vout_target, iout_eff)
            time.sleep(2.0)   # 等待电压稳定

            # ── 步骤4：读取测试条件下的输出电压基准 ───────────────────
            vout_test = self._measure_vout(pm, vout_target)

            # ── 步骤5：计算 OCP 规格（用于时基/电流扫描和结果判定）───
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

            # ── 步骤6：示波器准备好再看波形 ──────────────────────────
            self._osc_prepare(osc, self.osc_output_ch, vout_test, spec_hi)

            # ── 步骤7：示波器开始采集 ────────────────────────────────
            # （ROLL 模式 + 时基已在步骤6 _osc_prepare() 中设置好）
            if osc:
                try:
                    osc.run()
                except Exception as e:
                    warning(f"[OCP] 示波器启动失败: {e}")

            # ── 步骤8：电子负载从额定电流开始拉载 ─────────────────────
            self._step_setup_eload(eload, iout_eff)

            # ── 步骤9：缓调负载电流，寻找 OCP 触发点 ─────────────────
            ocp_triggered, ocp_point, vout_at_trigger = self._ramp_eload_find_ocp(
                eload, pm, vout_target, iout_eff, spec_hi, cond_label
            )

            # ── 步骤10：恢复测试（示波器全程采集） ──────────────────
            recover_status, test_pass, fail_reason, spec_lo, spec_hi = \
                self._recover_test(
                    eload, pm, snf, vout_target, iout_eff,
                    vout_test, ocp_triggered, ocp_point,
                    spec_lo, spec_hi,
                    proto_label, cond_label
                )

            # ── 步骤11：示波器停止，保存完整波形 ────────────────────
            wave_path = ""
            if osc and getattr(osc, "_connected", False):
                osc.stop()
                wave_path = osc.save_screenshot(os.path.join(
                    self._get_waveform_dir(),
                    f"OCP_{input_cond}_{proto_label}_{vout_target}V_{iout_eff:.3f}A.png"
                ))

            # ── 步骤12：记录结果 ─────────────────────────────────────
            # protect_mode 来自 UI 配置（label），recover_status 是实测结果
            latch_on = self.protection_logic.get("输出过流保护_mode", "") == "latch"
            self_on  = self.protection_logic.get("输出过流保护_mode", "") == "self"
            protect_mode_ui = "锁死" if latch_on else ("自恢复" if self_on else "未知")
            self._add_result(
                input_cond=input_cond, proto_label=proto_label,
                vout_target=vout_target, iout_eff=iout_eff,
                protect_mode=protect_mode_ui,
                spec_lo=spec_lo, spec_hi=spec_hi,
                ocp_point=ocp_point,
                recover_status=recover_status,
                test_pass=test_pass, fail_reason=fail_reason,
                waveform=wave_path,
            )

            # ── 步骤13：下电 ───────────────────────────────────────
            self._step_discharge(ac, eload)

    # ==================== 步骤方法 ====================

    def _ac_set_voltage(self, ac, vin: float, freq: float):
        """AC 源设置指定输入电压和频率。"""
        if ac is None:
            return
        try:
            ac.set_voltage(vin)
            ac.set_frequency(freq)
        except Exception as e:
            warning(f"[OCP] AC 源电压设置失败: {e}")

    def _osc_prepare(self, osc, ch_out: int, vout_target: float, spec_hi: float):
        """
        示波器准备：自动适配电压档位和时基，再切 ROLL 模式。

        电压档位：auto_config_channel 根据 vout_target 自动算 scale
        时基：set_timebase_for_duration 根据总时长自动选标准档位
        """
        if osc is None:
            return
        try:
            # ── 动态计算总时长 ────────────────────────────────────────
            # i_rated = spec_hi / (ocp_hi_pct/100)，由 ocp_hi_pct 决定
            ocp_hi_pct = self.spec.get("输出过流点_pct_hi")
            if ocp_hi_pct and ocp_hi_pct > 0:
                i_rated = spec_hi / (ocp_hi_pct / 100.0)
            else:
                i_rated = spec_hi / self.MAX_OCP_RATIO
            num_steps = max(1, int((spec_hi - i_rated) / self.LOAD_RAMP_STEP))
            sweep_time = num_steps * self.LOAD_RAMP_HOLD
            total_time = sweep_time + self.RECOVER_WAIT + 5.0
            info(f"[OCP] 示波器：斜升{num_steps}步({i_rated}A→{spec_hi:.2f}A)"
                 f"={sweep_time}s 总窗口{total_time:.0f}s")

            # 必须先切 ROLL，set_timebase_for_duration 才能用 ROLL 档位表选时基
            osc.set_timebase_mode("ROLL")
            osc.set_timebase_for_duration(total_time)

            osc.auto_config_channel(ch_out, v_peak=float(vout_target), coupling="DC")
        except Exception as e:
            warning(f"[OCP] 示波器准备失败: {e}")

    def _measure_vout(self, pm, vout_target: float) -> float:
        """用功率计测量输出电压。"""
        if pm is None:
            return float(vout_target)
        try:
            return abs(pm.measure_voltage(channel="CH2"))
        except Exception:
            return float(vout_target)

    def _ramp_eload_find_ocp(
        self, eload, pm, vout_target, iout_eff, i_max, cond_label
    ) -> tuple:
        """
        缓调电子负载电流，寻找 OCP 触发点。

        电流范围：iout_eff → i_max（spec_hi）
        触发条件：Vout < 0.1×Vout_target

        返回：(ocp_triggered: bool, ocp_point: float|None, vout_at_trigger: float)
        """
        i_start = float(iout_eff)          # 实际起始电流（功率分段后）
        current = i_start

        while current <= i_max + 1e-9:
            if eload:
                try:
                    eload.set_mode_cc(round(current, 3))
                except Exception as e:
                    warning(f"[OCP] set_mode_cc({current:.3f}A) 异常: {e}，提前终止扫描")
                    return False, None, 0.0
            time.sleep(self.LOAD_RAMP_HOLD)

            vout = self._measure_vout(pm, vout_target)
            info(f"[OCP] {cond_label} I={current:.3f}A Vout={vout:.3f}V")

            if vout < float(vout_target) * self.VOUT_DROP_RATIO:
                info(f"[OCP] OCP 触发！I={current:.3f}A Vout={vout:.3f}V，等待10s观察保护状态")
                time.sleep(10.0)   # 观察过流保护后的输出状态
                return True, round(current, 3), round(vout, 3)

            current += self.LOAD_RAMP_STEP

        return False, None, 0.0

    def _recover_test(
        self, eload, pm, snf,
        vout_target, iout_eff,
        vout_default, ocp_triggered, ocp_point,
        spec_lo, spec_hi,
        proto_label, cond_label
    ) -> tuple:
        """
        过流后恢复测试。

        spec_lo / spec_hi 只读不入，只来自 UI 配置（execute 算好后传入）。
        latch 模式：负载→开机带载电流，等待3s，
                    Vout < 0.1×Vout_default → 锁死，判规格
        self 模式：负载→开机带载电流，等待3s，
                    Vout > 0.9×Vout_default → 自恢复，重新诱骗调压，判 PASS

        返回：(recover_status, test_pass, fail_reason, spec_lo, spec_hi)
        """
        if not ocp_triggered:
            return "未触发", False, f"过流点超出规格上限 {spec_hi:.3f}A", spec_lo, spec_hi

        # 保护逻辑
        latch_on = self.protection_logic.get("输出过流保护_mode", "") == "latch"
        self_on  = self.protection_logic.get("输出过流保护_mode", "") == "self"

        # 切换到开机带载电流
        if eload:
            eload.set_mode_cc(self.load_startup_current)
        time.sleep(self.RECOVER_WAIT)

        vout_recover = self._measure_vout(pm, vout_target)
        info(f"[OCP] 恢复判定 Vout={vout_recover:.3f}V（基准={vout_default:.3f}V）")

        # ── latch 判定 ─────────────────────────────────
        if vout_recover < vout_default * 0.1:
            recover_status = "锁死"
            if latch_on:
                ocp_pass = (spec_lo <= ocp_point <= spec_hi)
                fail_reason = "" if ocp_pass else (
                    f"OCP点{ocp_point:.3f}A超规格({spec_lo:.2f}~{spec_hi:.2f}A)")
                return recover_status, ocp_pass, fail_reason, spec_lo, spec_hi
            else:
                return recover_status, False, "保护逻辑为自恢复但实际为锁死", spec_lo, spec_hi

        # ── self 判定 ──────────────────────────────────
        recover_status = "自恢复"
        if self_on:
            self._step_setup_sniffer(snf, proto_label, vout_target, iout_eff)
            # sniffer 重新协议后 DUT 输出正常电压，切回正常带载电流
            if eload:
                eload.set_mode_cc(float(iout_eff))
            time.sleep(10.0)
            vout_final = self._measure_vout(pm, vout_target)
            passed = (vout_final >= float(vout_target) * self.SELF_RECOVER_RATIO)
            fail_reason = "" if passed else (
                f"自恢复后Vout={vout_final:.3f}V"
                f"<{self.SELF_RECOVER_RATIO*100:.0f}%×{vout_target}V目标")
            return recover_status, passed, fail_reason, spec_lo, spec_hi
        else:
            return recover_status, False, "保护逻辑为锁死但实际为自恢复", spec_lo, spec_hi

    # ==================== 结果记录 ====================
    def _add_result(
        self, input_cond, proto_label, vout_target, iout_eff,
        protect_mode, spec_lo, spec_hi, ocp_point, recover_status,
        test_pass, fail_reason, waveform,
    ):
        conclusion = "SKIP" if recover_status == "SKIP" else ("PASS" if test_pass else "FAIL")
        self.sub_results.append({
            "输入条件":        input_cond,
            "协议":            proto_label,
            "输出电压(V)":     vout_target,
            "输出电流(A)":     iout_eff,
            "保护逻辑":        protect_mode,
            "规格上限(A)":     spec_hi,
            "规格下限(A)":     spec_lo,
            "过流保护点(A)":   ocp_point,
            "短路恢复情况":     recover_status,
            "测试结论":        conclusion,
            "测试波形":        waveform,
            "备注":            fail_reason,
            "overall_pass":    test_pass,
            "fail_reason":     fail_reason,
        })

    # ==================== verify ====================
    def verify(self) -> bool:
        if not self.sub_results:
            return False
        return all(
            r["overall_pass"] or r.get("recover_status") == "SKIP"
            for r in self.sub_results
        )
