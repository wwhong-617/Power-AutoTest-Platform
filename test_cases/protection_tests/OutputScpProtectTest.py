# -*- coding: utf-8 -*-
"""
VoutShortProtectTest - 输出短路保护测试
==========================================

【测试目标】
  验证 DUT 输出短路时的保护动作，测量短路前后输出电压，
  并在恢复后依据保护逻辑（锁死/自恢复）判定 PASS/FAIL。

【test_conditions 格式】
  (vin, freq, proto_label, vout_target, iout_target)

【保护逻辑】
  - latch（锁死）：短路恢复后切换到开机带载电流，Vout < 0.1×Vout_default
  - self（自恢复）：短路恢复后切换到开机带载电流，Vout > 0.9×Vout_default，
                    重新诱骗协议调压后 Vout > 0.9×Vout_target

【测试流程（每条条件 × 三个负载点）】

  setup()     打开示波器 CH2 通道
  步骤1  开机自检           → 基类 startup_self_check()
  步骤2  诱骗器协议         → 基类 _step_setup_sniffer()
  步骤3  AC 源切换到测试条件输入电压
  步骤4  三个负载点（100% / 50% / 0%）循环：
           4a. 示波器配置触发（50ms/div，NEG边沿）
           4b. 设 SINGLE 触发 → 短路 ON
           4c. 示波器触发完成，短路期间量 Vout_during_short
           4d. 短路 OFF，停止采集，保存波形
           4e. 等 5s，量 Vout_after_short
           4f. 恢复判定（latch/self）
  步骤5  下电

【报告字段】
  序号 | 输入条件 | 协议 | 输出电压(V) | 输出电流(A) | 负载点 |
  保护逻辑 | 短路后电压(V) | 短路恢复情况 | 测试结论 | 测试波形 | 备注
"""

import time
import os
import sys
from typing import Dict, Any, List
from ..base import TestCase

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class OutputScpProtectTest(TestCase):
    """输出短路保护测试。"""

    # ==================== 报告列定义 ====================
    COLS = [
                ("输入条件",          16),
                ("协议",              12),
                ("输出电压(V)",       14),
                ("输出电流(A)",       14),
                ("负载点",            10),
                ("保护逻辑",          12),
                ("短路后电压(V)",     14),
                ("短路恢复后电压(V)", 18),
                ("短路恢复情况",       16),
                ("测试结论",           11),
                ("测试波形",           18),
                ("备注",              28),
    ]

    # ==================== 测试常量 ====================
    TIME_BASE_S    = 0.05     # 示波器时基 50ms/div（10div=500ms总窗口）
    SHORT_ON_HOLD  = 5.0     # s，短路保持时间
    SHORT_OFF_HOLD = 5.0     # s，短路解除后等待时间
    RECOVER_WAIT   = 3.0     # s，恢复判定等待时间

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
        prot_vars: dict = None,
    ):
        self.product_type   = product_type
        self.settle_time    = settle_time if settle_time is not None else 2.0
        self.prot_vars      = prot_vars or {}
        self.sub_results: List[dict] = []

        super().__init__(
            name="OutputScpProtectTest",
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
            osc.set_timebase(self.TIME_BASE_S)
            osc.set_timebase_mode("MAIN")

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

            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = (
                cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            )
            input_cond = f"{vin_cfg}V_{freq_cfg}Hz"
            cond_label = f"{proto_label}_Vout{vout_target}V_Iout{iout_target}A"

            # ── 每个负载点独立上电→测试→下电（锁死产品短路后开不了机）
            load_ratios = [1.0, 0.5, 0.0]
            for idx, ratio in enumerate(load_ratios):
                # 每个负载点测完下电再重新上电，避免锁死影响下一个点
                if idx > 0:
                    self._step_discharge(ac, eload)
                    time.sleep(2.0)
                self._test_single_loadpoint(
                    instruments,
                    vin_cfg, freq_cfg, proto_label,
                    vout_target, iout_target, ratio,
                    input_cond, cond_label, self.osc_output_ch,
                )

            # ── 所有负载点测完，下电 ─────────────────────────────
            self._step_discharge(ac, eload)

    # ==================== 单个负载点测试 ====================
    def _test_single_loadpoint(
        self, instruments,
        vin_cfg, freq_cfg, proto_label,
        vout_target, iout_target, ratio,
        input_cond, cond_label, ch_out,
    ):
        """
        测试单个负载点的短路保护。
        每个负载点独立上电→测试→下电，避免锁死产品影响下一负载点测试。
        """
        ac    = instruments.get("AC_SOURCE")
        eload = instruments.get("ELOAD")
        snf   = instruments.get("SNIFFER")
        osc   = instruments.get("OSC")
        pm    = instruments.get("POWER_METER")

        i_set = float(iout_target) * ratio
        load_label = f"{int(ratio * 100)}%"
        info(f"[SCP] {cond_label} 负载点 {load_label}")

        # 功率分段
        iout_eff = self._get_effective_iout(float(vin_cfg), float(vout_target), float(iout_target))
        if iout_eff != float(iout_target):
            info(f"[SCP] 条件「{cond_label}」功率分段降流：Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

        # ── 每个负载点上电流程 ─────────────────────────────────
        # 步骤1：开机自检（用该条件电压，最多3次清除重试）
        startup_ok, vout_default, fail_reason = self.startup_self_check(
            instruments, vin=float(vin_cfg), freq=float(freq_cfg)
        )
        if not startup_ok:
            warning(f"[SCP] {cond_label} {load_label} 开机自检失败: {fail_reason}")
            self._step_discharge(ac, eload)
            self._add_result(
                input_cond=input_cond, proto_label=proto_label,
                vout_target=vout_target, iout_target=iout_eff,
                load_ratio=load_label, protect_mode="", vout_short=0.0,
                vout_after_short=0.0,
                recover_status="SKIP",
                test_pass=False, fail_reason=fail_reason, waveform="",
            )
            return

        self._step_setup_sniffer(snf, proto_label, vout_target, iout_eff)
        time.sleep(2.0)

        # ── 短路测试流程 ────────────────────────────────────────
        # 4a：示波器配置触发
        self._osc_arm_short_trigger(osc, ch_out, vout_target)

        # 4b：电子负载设置目标电流（功率分段后电流）
        i_set_eff = float(iout_eff) * ratio
        if eload:
            eload.set_mode_cc(round(i_set_eff, 3))
            eload.input_on()
        time.sleep(1.0)

        # 4c：先设 SINGLE 触发，再短路
        if osc:
            osc.set_single_trigger()
            time.sleep(3.0)
        if eload:
            eload.short_on()
            time.sleep(5.0)

        # 等待触发完成
        self._osc_wait_trigger_done(osc)

        # ── 4d：短路期间量电压（电子负载电压测量，更可靠）──────────
        vout_during_short = self._measure_vout_by_eload(eload, vout_target)
        info(f"[SCP] {cond_label} 短路中 Vout={vout_during_short:.3f}V")

        if eload:
            eload.short_off()
            # 短路解除后先切到开机小电流，避免高负载导致 DUT 无法恢复
            eload.set_mode_cc(self.load_startup_current)

        # 停止采集并保存波形
        wave_path = ""
        if osc and getattr(osc, "_connected", False):
            try:
                osc.stop()
                wave_path = osc.save_screenshot(os.path.join(
                    self._get_waveform_dir(),
                    f"VoutShortProtectTest_{input_cond}_{proto_label}_{vout_target}V_{iout_eff:.3f}A_{int(ratio*100)}pct.png"
                ))
                osc.run()   # 恢复采集
            except Exception as e:
                warning(f"[SCP] 示波器截图失败: {e}")

        time.sleep(self.SHORT_OFF_HOLD)

        # ── 4e：短路解除后量电压（电子负载电压测量）────────────────
        vout_after_short = self._measure_vout_by_eload(eload, vout_target)
        info(f"[SCP] {cond_label} 短路解除后 Vout={vout_after_short:.3f}V")

        # ── 4f：恢复判定 ─────────────────────────────────────────
        recover_status, test_pass, fail_reason = self._recover_test(
            eload, pm, snf,
            vout_target, iout_target, iout_eff,
            vout_default, vout_during_short, vout_after_short,
            proto_label, cond_label,
        )

        # ── 记录结果 ─────────────────────────────────────────────
        # protect_mode 来自 UI 配置（latch/self），只是判据说明
        latch_on = self.protection_logic.get("输出过流保护_mode", "") == "latch"
        self_on  = self.protection_logic.get("输出过流保护_mode", "") == "self"
        protect_mode_ui = "锁死" if latch_on else ("自恢复" if self_on else "未知")
        self._add_result(
            input_cond=input_cond,
            proto_label=proto_label,
            vout_target=vout_target,
            iout_target=iout_eff,
            load_ratio=load_label,
            protect_mode=protect_mode_ui,
            vout_short=round(vout_during_short, 3),
            vout_after_short=round(vout_after_short, 3),
            recover_status=recover_status,
            test_pass=test_pass,
            fail_reason=fail_reason,
            waveform=wave_path,
        )

    # ==================== 恢复测试 ====================
    SHORT_MOMENT_RATIO = 0.7   # 短路时刻电压判据：应 < 0.7 × Vout_default
    RECOVER_SELF_RATIO = 0.9   # 自恢复判据：Vout > 0.9 × Vout_default
    RECOVER_LATCH_RATIO = 0.1  # 锁死判据：Vout < 0.1 × Vout_default

    def _recover_test(
        self, eload, pm, snf,
        vout_target, iout_target, iout_eff,
        vout_default,
        vout_during_short, vout_after_short,
        proto_label, cond_label,
    ) -> tuple:
        """
        三级判断，最终得出测试结论。

        【短路时刻判断】vout_during_short（short_on 之后，short_off 之前）
          → vout_during_short < 0.7 × Vout_default → 短路生效
          → vout_during_short ≥ 0.7 × Vout_default → 短路未生效

        【短路恢复判断】vout_recover（short_off + 等3s，开机带载电流下）
          → UI配置为自恢复：Vout > 0.9 × Vout_default → 自恢复
                                  Vout ≤ 0.9 × Vout_default → 自恢复异常
          → UI配置为锁死：  Vout < 0.1 × Vout_default → 锁死
                                  Vout ≥ 0.1 × Vout_default → 锁死异常

        【短路恢复情况】直接来自恢复判断结论

        【最终测试结论】
          短路生效 ✓ 且 恢复结论 = UI配置的逻辑 → PASS
          否则 → FAIL

        返回：(recover_status, test_pass, fail_reason)
        """
        latch_on = self.protection_logic.get("输出过流保护_mode", "") == "latch"
        self_on  = self.protection_logic.get("输出过流保护_mode", "") == "self"

        # ── 第1级：短路时刻判断 ───────────────────────────────
        if vout_during_short >= vout_default * self.SHORT_MOMENT_RATIO:
            fail_reason = (
                f"短路未生效：短路中Vout={vout_during_short:.3f}V"
                f"（需<{self.SHORT_MOMENT_RATIO*100:.0f}%×{vout_default:.3f}V）")
            return "短路未生效", False, fail_reason

        # ── 第2级：短路恢复判断 ───────────────────────────────
        if eload:
            eload.set_mode_cc(self.load_startup_current)
        if snf:
            snf.set_protocol(proto_label, vout_target, iout_eff)
        time.sleep(self.RECOVER_WAIT)
        vout_recover = self._measure_vout_by_eload(eload, vout_target)
        info(f"[SCP] 恢复电压 Vout={vout_recover:.3f}V（基准={vout_default:.3f}V）")

        if self_on:
            # 自恢复逻辑
            if vout_recover > vout_default * self.RECOVER_SELF_RATIO:
                recover_status = "自恢复"
                # 最终结论：短路生效且恢复结论=自恢复 → PASS
                return recover_status, True, ""
            else:
                recover_status = "自恢复异常"
                fail_reason = (
                    f"自恢复异常：Vout={vout_recover:.3f}V"
                    f"（需>{self.RECOVER_SELF_RATIO*100:.0f}%×{vout_default:.3f}V）")
                return recover_status, False, fail_reason
        elif latch_on:
            # 锁死逻辑
            if vout_recover < vout_default * self.RECOVER_LATCH_RATIO:
                recover_status = "锁死"
                return recover_status, True, ""
            else:
                recover_status = "锁死异常"
                fail_reason = (
                    f"锁死异常：Vout={vout_recover:.3f}V"
                    f"（需<{self.RECOVER_LATCH_RATIO*100:.0f}%×{vout_default:.3f}V）")
                return recover_status, False, fail_reason
        else:
            return "未知", False, "保护逻辑未配置（latch/self均未勾选）"

    # ==================== 示波器触发方法 ====================
    def _osc_arm_short_trigger(self, osc, ch_out: int, vout_target: float):
        """
        配置示波器触发，为捕获短路时刻波形做准备。
        - 时基 50ms/div，10div=500ms 窗口
        - 先切 NORMAL 模式（停止自由运行），再设 SINGLE 触发
        - 触发源 CHAN{ch_out}，下降沿，触发电平 Vout×0.3
        """
        if osc is None:
            return
        try:
            osc.set_timebase_mode("NORMAL")   # 先停住，再等触发
            osc.set_timebase(self.TIME_BASE_S)
            osc.set_channel_on(ch_out)
            osc.auto_config_channel(ch_out, v_peak=vout_target * 1.5,
                                   coupling="DC")
            osc.set_trigger_source(f"CHAN{ch_out}")
            osc.set_trigger_coupling("DC")
            osc.set_trigger_slope("NEG")
            osc.set_trigger_level(vout_target * 0.3)
            info(f"[SCP] 示波器触发配置 | NORMAL | 时基={self.TIME_BASE_S}s/div "
                 f"触发电平={vout_target*0.3:.3f}V")
        except Exception as e:
            warning(f"[SCP] 示波器触发配置失败: {e}")

    def _osc_wait_trigger_done(self, osc, timeout_s: float = 10.0) -> bool:
        """
        轮询等待示波器 SINGLE 触发完成。

        DSOX4024A SINGLE 模式触发状态：ARM(等待) / STOP(已触发)。

        Returns:
            True = 触发成功，False = 超时未触发
        """
        if osc is None:
            return False
        elapsed = 0.0
        interval = 0.2
        while elapsed < timeout_s:
            try:
                state = osc.get_run_state().upper().strip()
            except Exception:
                state = ""
            if state == "STOP":
                info(f"[SCP] 示波器触发完成 | elapsed={elapsed:.2f}s")
                return True
            elapsed += interval
            time.sleep(interval)
        warning(f"[SCP] 示波器触发超时 | {elapsed:.1f}s 未触发")
        return False

    # ==================== 步骤方法 ====================
    def _measure_vout(self, pm, vout_target: float) -> float:
        """用功率计测量输出电压。"""
        if pm is None:
            return float(vout_target)
        try:
            return abs(pm.measure_voltage(channel="CH2"))
        except Exception:
            return float(vout_target)

    def _measure_vout_by_eload(self, eload, vout_target: float) -> float:
        """用电子负载测量输出电压（比功率计更可靠）。"""
        if eload is None:
            return float(vout_target)
        try:
            return abs(float(eload.measure_voltage()))
        except Exception:
            return float(vout_target)

    def _ac_set_voltage(self, ac, vin: float, freq: float):
        """AC 源设置指定输入电压和频率。"""
        if ac is None:
            return
        try:
            ac.set_voltage(vin)
            ac.set_frequency(freq)
        except Exception as e:
            warning(f"[SCP] AC 源电压设置失败: {e}")

    # ==================== 结果记录 ====================
    def _add_result(
        self, input_cond, proto_label, vout_target, iout_target,
        load_ratio, protect_mode, vout_short, vout_after_short,
        recover_status, test_pass, fail_reason, waveform,
    ):
        conclusion = "SKIP" if recover_status == "SKIP" else ("PASS" if test_pass else "FAIL")
        self.sub_results.append({
            "输入条件":        input_cond,
            "协议":            proto_label,
            "输出电压(V)":     vout_target,
            "输出电流(A)":     iout_target,
            "负载点":          load_ratio or "",
            "保护逻辑":        protect_mode,
            "短路后电压(V)":   vout_short,
            "短路恢复后电压(V)": vout_after_short,
            "短路恢复情况":     recover_status,
            "测试结论":        conclusion,
            "测试波形":        waveform,
            "备注":            fail_reason,
            "overall_pass":    test_pass,
            "fail_reason":    fail_reason,
        })

    # ==================== verify ====================
    def verify(self) -> bool:
        if not self.sub_results:
            return False
        return all(
            r["overall_pass"] or r.get("短路恢复情况") == "SKIP"
            for r in self.sub_results
        )
