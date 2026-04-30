# -*- coding: utf-8 -*-
"""
OutputScpProtectTest - 输出短路保护测试
========================================

【测试目标】
  验证 DUT 输出短路时的保护动作，测量短路前后输出电压，
  并在恢复后依据保护逻辑（锁死/自恢复）判定 PASS/FAIL。

【test_conditions 格式】
  List[dict]，每项字段：vin / freq / proto / vout / iout

【保护逻辑】
  - latch（锁死）：短路恢复后 Vout < 0.1×Vout_default → 锁死 PASS
  - self（自恢复）：短路恢复后 Vout > 0.9×Vout_default → 自恢复 PASS

  注意：恢复判定电压基准为开机自检后实测的 Vout_default，
        而非测试条件中的 vout_target。

【测试流程（每条条件 × 三个负载点）】

  setup()       初始化示波器通道（MAIN 模式）
  execute()     遍历条件 → 每个条件测 100%/50%/0% 三个负载点
  verify()      所有 sub_result 均 PASS 才返回 True

  每负载点步骤：
    1. 开机自检（基类 startup_self_check），捕获 Vout_default
    2. 诱骗器协议配置（基类 _step_setup_sniffer）
    3. 示波器配置 SINGLE 触发（NORMAL 模式 / NEG 边沿）
    4. 电子负载设目标电流后短路（short_on）
    5. 等待示波器触发完成，测量短路中电压
    6. 短路解除（short_off），停止采集，保存波形
    7. 等待 SHORT_OFF_HOLD，测量短路后电压
    8. 恢复判定（latch/self，基准 = Vout_default）
    9. 放电下电

  三个负载点之间独立上下电，锁死产品不会影响下一个负载点的测试。

【报告字段】
  序号 | 用例名称 | 输入条件 | 协议 | 输出电压(V) | 输出电流(A) |
  负载点 | 保护逻辑 | 短路后电压(V) | 短路恢复后电压(V) |
  短路恢复情况 | 测试结论 | 测试波形 | 备注
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

    # 报告列定义（序号/用例名称由 report_generator._flatten() 自动注入）
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

    # 示波器时基 50ms/div（10div=500ms 总窗口）
    TIME_BASE_S     = 0.05
    # 短路保持时间（s）
    SHORT_ON_HOLD   = 5.0
    # 短路解除后等待时间（s）
    SHORT_OFF_HOLD  = 5.0
    # 恢复判定等待时间（s）
    RECOVER_WAIT    = 3.0
    # 自恢复判据：Vout > 0.9×Vout_default
    RECOVER_SELF_RATIO   = 0.9
    # 锁死判据：Vout < 0.1×Vout_default
    RECOVER_LATCH_RATIO  = 0.1

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
            vout_spec_min/max     : 输出电压规格上下限
            product_type          : 产品类型，"charger" 或 "adapter"
            test_conditions       : 测试条件列表，每项 dict，
                                   字段：vin / freq / proto / vout / iout
            settle_time           : 等待时间（s），默认 2.0
            prot_vars             : 保护配置 dict，字段：输出过流保护_mode
        """
        self.settle_time = settle_time if settle_time is not None else 2.0
        self.prot_vars   = prot_vars or {}
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

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """通用仪器初始化 + 参数缓存。"""
        self.sub_results = []
        super().setup(instruments)

        self.osc_output_ch = int(self.params.get("osc_output_ch", 2))
        self.test_conditions = getattr(self, "test_conditions", []) or self.params.get("test_conditions", [])
        self.protection_logic = self.params.get("protection_logic", {})
        self.load_startup_current = float(self.params.get("load_startup_current", 0.1))

        # 初始化示波器：MAIN 模式（每个负载点独立触发，不再复用 ROLL）
        osc = instruments.get("OSC")
        if osc and getattr(osc, "_connected", False):
            osc.set_channel_on(self.osc_output_ch)
            osc.set_timebase(self.TIME_BASE_S)
            osc.set_timebase_mode("MAIN")

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """执行输出短路保护测试。

        遍历 test_conditions，每条件测三个负载点（100% / 50% / 0%），
        三点之间独立上下电，避免锁死产品影响后续测试。
        """
        ac    = self._ac(instruments)
        eload = self._eload(instruments)

        load_ratios = [1.0, 0.5, 0.0]   # 100% / 50% / 0%

        for cond in self.test_conditions:
            if len(cond) < 5:
                continue

            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = (
                cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            )
            input_cond = f"{int(vin_cfg)}V_{int(freq_cfg)}Hz"
            cond_label = f"{proto_label}/{vout_target}V/{iout_target}A"

            for idx, ratio in enumerate(load_ratios):
                # 负载点之间独立上下电
                if idx > 0:
                    self._step_discharge(ac, eload)
                    time.sleep(2.0)
                self._test_single_loadpoint(
                    instruments,
                    vin_cfg, freq_cfg, proto_label,
                    vout_target, iout_target, ratio,
                    input_cond, cond_label,
                )

            self._step_discharge(ac, eload)

    # ---------- _test_single_loadpoint ----------
    def _test_single_loadpoint(
        self, instruments,
        vin_cfg, freq_cfg, proto_label,
        vout_target, iout_target, ratio,
        input_cond, cond_label,
    ):
        """
        测试单个负载点的短路保护。

        流程：开机自检 → 协议配置 → 示波器触发准备 →
              短路 → 测量短路中电压 → 解除短路 → 测量短路后电压 →
              恢复判定 → 记录结果

        Args:
            ratio: 负载比例，1.0=100%, 0.5=50%, 0.0=0%（空载）
        """
        ac    = instruments.get("AC_SOURCE")
        eload = instruments.get("ELOAD")
        snf   = instruments.get("SNIFFER")
        osc   = instruments.get("OSC")
        pm    = instruments.get("POWER_METER")

        load_label = f"{int(ratio * 100)}%"
        info(f"[SCP] {cond_label} 负载点 {load_label}")

        # 功率分段降流
        iout_eff = self._get_effective_iout(
            float(vin_cfg), float(vout_target), float(iout_target)
        )
        if iout_eff != iout_target:
            info(f"[SCP] 条件「{cond_label}」功率分段降流："
                 f"Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

        # --- 步骤1：开机自检，捕获 Vout_default（实际输出电压基准）---
        startup_ok, vout_default, fail_reason = self.startup_self_check(
            instruments, vin=float(vin_cfg), freq=float(freq_cfg)
        )
        if not startup_ok:
            warning(f"[SCP] {cond_label} {load_label} 开机自检失败："
                    f"{fail_reason}，跳过")
            self._step_discharge(ac, eload)
            self._add_result(
                input_cond=input_cond, proto_label=proto_label,
                vout_target=vout_target, iout_target=iout_eff,
                load_ratio=load_label, protect_mode="",
                vout_short=0.0, vout_after_short=0.0,
                recover_status="SKIP",
                test_pass=False, fail_reason=fail_reason, waveform="",
            )
            return

        # --- 步骤2：诱骗器协议配置 ---
        self._step_setup_sniffer(snf, proto_label, vout_target, iout_eff)
        time.sleep(2.0)

        # --- 步骤3：示波器配置 SINGLE 触发（NORMAL 模式 / NEG 边沿）---
        self._osc_arm_short_trigger(osc, self.osc_output_ch, vout_target)

        # --- 步骤4：电子负载设目标电流后短路 ---
        i_set_eff = float(iout_eff) * ratio
        if eload:
            eload.set_mode_cc(round(i_set_eff, 3))
            eload.input_on()
        time.sleep(1.0)

        # 示波器等待 SINGLE 触发，电子负载随后短路
        if osc:
            osc.set_single_trigger()
            time.sleep(3.0)
        if eload:
            eload.short_on()
            time.sleep(self.SHORT_ON_HOLD)

        # --- 步骤5：等待示波器触发完成，测量短路中电压 ---
        self._osc_wait_trigger_done(osc)
        vout_during_short = self._measure_vout_by_eload(eload, vout_target)
        info(f"[SCP] {cond_label} {load_label} "
             f"短路中 Vout={vout_during_short:.3f}V")

        # --- 步骤6：短路解除，停止采集，保存波形 ---
        if eload:
            eload.short_off()
            eload.set_mode_cc(self.load_startup_current)   # 切小电流再恢复
        wave_path = ""
        if osc and getattr(osc, "_connected", False):
            try:
                osc.stop()
                wave_path = osc.save_screenshot(os.path.join(
                    self._get_waveform_dir(),
                    f"{self.name}_{input_cond}_{proto_label}_"
                    f"{vout_target}V_{iout_eff:.3f}A_{int(ratio*100)}pct.png"
                ))
                osc.run()   # 恢复采集（下一个负载点继续用）
            except Exception as e:
                warning(f"[SCP] 示波器截图失败: {e}")

        # --- 步骤7：等待后测量短路解除后电压 ---
        time.sleep(self.SHORT_OFF_HOLD)
        vout_after_short = self._measure_vout_by_eload(eload, vout_target)
        info(f"[SCP] {cond_label} {load_label} "
             f"短路解除后 Vout={vout_after_short:.3f}V")

        # --- 步骤8：恢复判定（基准 = Vout_default，非 vout_target）---
        recover_status, test_pass, fail_reason = self._recover_test(
            eload, pm, snf,
            vout_default, vout_target, vout_after_short,
            proto_label,
        )

        # --- 步骤9：记录结果 ---
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

    # ---------- _recover_test ----------
    def _recover_test(
        self, eload, pm, snf,
        vout_default, vout_target, vout_after_short,
        proto_label,
    ) -> tuple:
        """
        短路恢复判定。

        短路解除后，将 eload 切到开机小电流，等待 RECOVER_WAIT，
        重新诱骗协议（vout_target），然后依据保护逻辑（latch/self）判定：

          latch：Vout < 0.1×vout_default → 锁死 PASS
                 Vout ≥ 0.1×vout_default → 锁死异常 FAIL
          self ：Vout > 0.9×vout_default → 自恢复 PASS
                 Vout ≤ 0.9×vout_default → 自恢复异常 FAIL

        注意：恢复电压判定基准为开机自检后实测的 vout_default，
              而非测试条件中的 vout_target。

        Args:
            vout_default     : 开机自检后实测的输出电压（基准）
            vout_target      : 测试条件目标电压（供 sniffer 重新诱骗用）
            vout_after_short : 短路解除 + SHORT_OFF_HOLD 后的实测电压

        Returns: (recover_status, test_pass, fail_reason)
        """
        latch_on = self.protection_logic.get("输出过流保护_mode", "") == "latch"
        self_on  = self.protection_logic.get("输出过流保护_mode", "") == "self"

        # 短路解除后先切小电流，避免大电流影响恢复判定
        if eload:
            eload.set_mode_cc(self.load_startup_current)
        # 重新诱骗协议，模拟真实恢复场景
        if snf:
            snf.set_protocol(proto_label, vout_target, 0.1)
        time.sleep(self.RECOVER_WAIT)
        vout_recover = self._measure_vout_by_eload(eload, vout_default)
        info(f"[SCP] 恢复电压 Vout={vout_recover:.3f}V"
             f"（基准={vout_default:.3f}V）")

        if self_on:
            if vout_recover > self.RECOVER_SELF_RATIO * vout_default:
                return "自恢复", True, ""
            return (
                "自恢复异常",
                False,
                f"自恢复异常：Vout={vout_recover:.3f}V"
                f"（需>{self.RECOVER_SELF_RATIO*100:.0f}%×{vout_default:.3f}V）",
            )
        elif latch_on:
            if vout_recover < self.RECOVER_LATCH_RATIO * vout_default:
                return "锁死", True, ""
            return (
                "锁死异常",
                False,
                f"锁死异常：Vout={vout_recover:.3f}V"
                f"（需<{self.RECOVER_LATCH_RATIO*100:.0f}%×{vout_default:.3f}V）",
            )
        return "未知", False, "保护逻辑未配置（latch/self 均未勾选）"

    # ---------- 示波器触发方法 ----------
    def _osc_arm_short_trigger(self, osc, ch_out: int, vout_target: float):
        """
        配置示波器触发捕获短路时刻波形。

        NORMAL 模式（每次手动触发）；时基 50ms/div（10div=500ms 窗口）；
        SINGLE 触发；CHAN{ch_out} / NEG 边沿 / 触发电平 Vout×0.3。
        """
        if osc is None:
            return
        try:
            osc.set_timebase_mode("NORMAL")
            osc.set_timebase(self.TIME_BASE_S)
            osc.set_channel_on(ch_out)
            osc.auto_config_channel(ch_out, v_peak=vout_target * 1.5, coupling="DC")
            osc.set_trigger_source(f"CHAN{ch_out}")
            osc.set_trigger_coupling("DC")
            osc.set_trigger_slope("NEG")
            osc.set_trigger_level(vout_target * 0.3)
            info(f"[SCP] 示波器触发配置 | NORMAL | "
                 f"时基={self.TIME_BASE_S}s/div | "
                 f"触发电平={vout_target*0.3:.3f}V")
        except Exception as e:
            warning(f"[SCP] 示波器触发配置失败: {e}")

    def _osc_wait_trigger_done(self, osc, timeout_s: float = 10.0) -> bool:
        """
        轮询等待示波器 SINGLE 触发完成。

        DSOX4024A SINGLE 模式触发状态：ARM（等待）/ STOP（已触发）。

        Returns:
            True = 触发成功，False = 超时未触发
        """
        if osc is None:
            return False
        elapsed, interval = 0.0, 0.2
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

    # ---------- 测量方法 ----------
    def _measure_vout(self, pm, vout_target: float) -> float:
        """用功率计测量输出电压（备选路径）。"""
        if pm is None:
            return float(vout_target)
        try:
            return abs(pm.measure_voltage(channel="CH2"))
        except Exception:
            return float(vout_target)

    def _measure_vout_by_eload(self, eload, vout_target: float) -> float:
        """用电子负载测量输出电压（主选，比功率计更可靠）。"""
        if eload is None:
            return float(vout_target)
        try:
            return abs(float(eload.measure_voltage()))
        except Exception:
            return float(vout_target)

    # ---------- _add_result ----------
    def _add_result(
        self, input_cond, proto_label, vout_target, iout_target,
        load_ratio, protect_mode, vout_short, vout_after_short,
        recover_status, test_pass, fail_reason, waveform,
    ):
        """
        组装单条 sub_result，字段名与 COLS 列头一一对应
        （序号/用例名称由 report_generator._flatten() 注入，此处不重复）。
        """
        conclusion = "SKIP" if recover_status == "SKIP" else (
            "PASS" if test_pass else "FAIL")
        self.sub_results.append({
            "输入条件":          input_cond,
            "协议":              proto_label,
            "输出电压(V)":       vout_target,
            "输出电流(A)":       iout_target,
            "负载点":            load_ratio or "",
            "保护逻辑":          protect_mode,
            "短路后电压(V)":     vout_short,
            "短路恢复后电压(V)": vout_after_short,
            "短路恢复情况":      recover_status,
            "测试结论":          conclusion,
            "测试波形":          waveform,
            "备注":              fail_reason,
            # 内部字段（供 verify() 判定使用，不写入报告）
            "overall_pass":      test_pass,
            "fail_reason":      fail_reason,
        })

    # ---------- verify ----------
    def verify(self) -> bool:
        """所有 sub_result 均 PASS 才返回 True。"""
        return bool(self.sub_results) and all(
            r["overall_pass"] or r.get("短路恢复情况") == "SKIP"
            for r in self.sub_results
        )

    # ---------- to_dict ----------
    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        return d
