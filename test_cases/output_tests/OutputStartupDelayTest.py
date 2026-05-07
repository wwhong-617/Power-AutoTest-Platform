# -*- coding: utf-8 -*-
"""
OutputStartupDelayTest - 输出开机延迟时间测试
============================================

测量 DUT 开机时，从 AC 输入电压建立到输出电压达到目标值 90% 的时间。
每次触发同时采集输入通道 + 输出通道波形，在 Python 中分析计算延迟。

【test_conditions 格式】
  List[dict]，每项字段：vin / freq / proto / vout / iout

【测试流程（每条条件）】
  setup()     初始化示波器双通道（输入 + 输出）+ 边沿触发
  execute()   遍历条件，逐条件执行以下步骤
  verify()    所有 sub_result 均 PASS 才返回 True

  每条件步骤：
    1. startup_self_check() 验证能开机
    2. 配置示波器时基和双通道刻度
    3. _step_discharge() 放电下电（冷启动）
    4. 武装 SINGLE 触发 → startup_self_check() 上电 → 等待触发
    5. 采集输入+输出双通道波形 → 计算延迟 → 保存截图
    6. _step_discharge() 放电下电

【报告字段】
  序号 | 用例名称 | 输入条件 | 协议 | 输出电压(V) | 输出电流(A) |
  规格上限 | 规格下限 | 开机延迟时间(ms) | 测试结论 | 测试波形 | 备注
"""

import time
import os
import sys
from typing import Dict, Any, List
from ..base import TestCase

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class OutputStartupDelayTest(TestCase):
    """输出开机延迟时间测试。"""

    TRIGGER_TIMEOUT = 5.0    # 示波器触发等待超时（s）
    TRIGGER_WAIT_S  = 0.3    # 轮询触发状态间隔（s）
    TIME_BASE_S     = 0.80 # 示波器时基 800ms/div（总窗口 8000ms）

    # 报告列定义
    COLS = [
        ("输入条件",      16),
        ("协议",          12),
        ("输出电压(V)",   13),
        ("输出电流(A)",  13),
        ("规格上限",     11),
        ("规格下限",     11),
        ("开机延迟时间(ms)", 16),
        ("测试结论",      12),
        ("测试波形",      18),
        ("备注",          28),
    ]

    # ---------- __init__ ----------
    def __init__(
        self,
        startup_delay_ms_lo: float = 0.0,
        startup_delay_ms_hi: float = 500.0,
        product_type: str = "charger",
        test_conditions: List[dict] = None,
        osc_input_ch: int = 4,
        osc_output_ch: int = 2,
    ):
        """
        Args:
            startup_delay_ms_lo:  开机延迟规格下限（ms）
            startup_delay_ms_hi:  开机延迟规格上限（ms）
            product_type:         产品类型，"charger" 或 "adapter"
            test_conditions:       测试条件列表，每项 dict，
                                  字段：vin / freq / proto / vout / iout
            osc_input_ch:         示波器输入电压通道编号（默认4）
            osc_output_ch:        示波器输出电压通道编号（默认2）
        """
        self.sub_results: List[dict] = []

        super().__init__(
            name="OutputStartupDelayTest",
            instruments=["AC_SOURCE", "ELOAD", "OSC", "POWER_METER"],
            params={
                "osc_input_ch":   osc_input_ch,
                "osc_output_ch":  osc_output_ch,
                "product_type":    product_type,
                "test_conditions": test_conditions,
            },
            spec={
                "开机延迟时间_ms_lo": startup_delay_ms_lo,
                "开机延迟时间_ms_hi": startup_delay_ms_hi,
            },
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """示波器初始化：双通道 DC 耦合 + 边沿触发（输入通道）。"""
        self.sub_results = []
        super().setup(instruments)

        self.osc_input_ch  = int(self.params.get("osc_input_ch", 4))
        self.osc_output_ch = int(self.params.get("osc_output_ch", 2))
        osc = instruments.get("OSC")
        if osc is None:
            warning("[SSD] 示波器未连接，跳过公共配置")
            return

        # 时基（默认固定）
        osc.set_timebase(self.TIME_BASE_S)

        # --- 输入通道 ---
        osc.set_channel_on(self.osc_input_ch)
        osc.set_channel_coupling(self.osc_input_ch, "DC")
        osc.set_bandwidth_limit(self.osc_input_ch, False)

        # --- 输出通道 ---
        osc.set_channel_on(self.osc_output_ch)
        osc.set_channel_coupling(self.osc_output_ch, "DC")
        osc.set_bandwidth_limit(self.osc_output_ch, False)

        # 触发：输入通道，边沿触发
        osc.set_trigger_mode("EDGE")
        osc.set_trigger_source(f"CHAN{self.osc_input_ch}")
        osc.set_trigger_slope("POS")

        info(f"[SSD] 示波器公共配置完成 | 输入CH{self.osc_input_ch} 输出CH{self.osc_output_ch} "
             f"时基={self.TIME_BASE_S*1000:.1f}ms/div 触发=CH{self.osc_input_ch}边沿")

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """执行输出开机延迟时间测试。"""
        ac    = self._ac(instruments)
        eload = self._eload(instruments)
        osc   = self._osc(instruments)

        conditions = self.params.get("test_conditions", [])
        if not conditions:
            warning("[SSD] 无测试条件，跳过执行")
            return

        spec_hi = self.spec.get("开机延迟时间_ms_hi", 500.0)
        spec_lo = self.spec.get("开机延迟时间_ms_lo", 0.0)

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
                info(f"[SSD] 条件「{cond_label}」功率分段降流："
                     f"Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # --- 步骤1：开机自检 ---
            startup_ok, _, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            if not startup_ok:
                info(f"[SSD] 条件「{cond_label}」开机自检失败：{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self._skip_condition(
                    input_cond, proto_label, vout_target, iout_eff,
                    spec_lo, spec_hi, fail_reason,
                )
                continue

            # --- 步骤2：配置示波器 ---
            self._osc_prepare(osc, float(vin_cfg), float(vout_target), freq_cfg)

            # --- 步骤3：放电下电（冷启动）---
            self._step_discharge(ac, eload)

            # --- 步骤4：武装 SINGLE 触发 → 开机自检上电 → 等待触发 ---
            if osc:
                osc.set_single_trigger()
                time.sleep(1.0)

            cold_ok, _, cold_fail = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )

            if osc:
                info(f"[SSD] 等待触发 | timeout={self.TRIGGER_TIMEOUT}s")
                triggered = self._osc_wait_trigger(
                    osc, timeout_s=self.TRIGGER_TIMEOUT,
                    poll_interval=self.TRIGGER_WAIT_S,
                )
                if not triggered:
                    osc.stop()
            # 开机延迟时间时基比较大，示波器波形保存需要时间，增加2s等待时间
            time.sleep(2.0)

            # --- 步骤5：采集双通道波形 → 计算延迟 ---
            delay_ms, waveform = self._measure_delay(
                osc, float(vin_cfg), float(vout_target),
                input_cond, proto_label, float(vout_target), float(iout_eff),
            )

            # --- 步骤6：放电下电 ---
            self._step_discharge(ac, eload)

            # --- 记录结果 ---
            self._record_result(
                input_cond, proto_label, vout_target, iout_eff,
                spec_lo, spec_hi, delay_ms, waveform,
            )

    # ---------- _osc_prepare ----------
    def _osc_prepare(self, osc, vin: float, vout_target: float, freq: float):
        """
        配置示波器时基和双通道刻度。

        Args:
            vin:         输入电压（VAC）
            vout_target: 目标输出电压（V）
            freq:        频率（Hz）
        """
        if osc is None:
            return

        # 时基固定 800ms/div（8000ms 总窗口，足够覆盖开机延迟）
        osc.set_timebase(self.TIME_BASE_S)

        # 输入通道刻度：按输入电压峰值 / 4格
        vin_peak = vin * 1.414 * 2
        scale_in = osc.round_voltage_scale(vin_peak / 4.0)
        osc.set_voltage_scale(self.osc_input_ch, scale_in)
        osc.set_channel_offset(self.osc_input_ch, 0.0)

        # 输出通道刻度：按目标电压 / 4格
        scale_out = osc.round_voltage_scale(vout_target / 4.0)
        osc.set_voltage_scale(self.osc_output_ch, scale_out)
        osc.set_channel_offset(self.osc_output_ch, scale_out * 2)

        # 触发：输入通道边沿，触发电平设为输入电压的 50%
        trigger_level = vin_peak * 0.5
        osc.set_trigger_level(trigger_level)

        info(f"[SSD] 示波器配置 | 时基={self.TIME_BASE_S*1000:.1f}ms/div "
             f"输入刻度={scale_in:.2f}V/div 触发={trigger_level:.1f}V")

    # ---------- _osc_wait_trigger ----------
    def _osc_wait_trigger(self, osc, timeout_s: float, poll_interval: float) -> bool:
        """轮询等待示波器 SINGLE 触发完成。"""
        if osc is None:
            return False
        elapsed = 0.0
        while elapsed < timeout_s:
            try:
                state = osc.get_run_state().upper().strip()
            except Exception:
                state = ""
            if state == "STOP":
                info(f"[SSD] 触发完成 | elapsed={elapsed:.2f}s")
                return True
            elapsed += poll_interval
            time.sleep(poll_interval)
        warning(f"[SSD] 触发超时 | {elapsed:.1f}s 未触发")
        return False

    # ---------- _measure_delay ----------
    def _measure_delay(self, osc, vin: float, vout_target: float,
                       input_cond: str, proto: str,
                       vout: float, iout: float) -> tuple:
        """
        采集输入+输出双通道波形，计算开机延迟时间。

        延迟定义：输入电压上电时刻 → 输出电压达到 vout_target × 90% 时刻

        Returns:
            (delay_ms, waveform_path)
        """
        import numpy as np

        delay_ms = 0.0
        wf = ""

        if osc is None:
            return delay_ms, wf

        # 采集输入通道波形
        try:
            x_in, y_in = osc.acquire_waveform(self.osc_input_ch)
        except Exception as e:
            warning(f"[SSD] 输入通道波形采集失败: {e}")
            x_in, y_in = np.array([]), np.array([])

        # 采集输出通道波形
        try:
            x_out, y_out = osc.acquire_waveform(self.osc_output_ch)
        except Exception as e:
            warning(f"[SSD] 输出通道波形采集失败: {e}")
            x_out, y_out = np.array([]), np.array([])

        # 计算延迟
        if len(x_in) > 0 and len(x_out) > 0:
            try:
                delay_s = self._calc_startup_delay(x_in, y_in, x_out, y_out, vout_target)
                delay_ms = delay_s * 1000.0
                info(f"[SSD] 开机延迟 | {delay_ms:.3f}ms")
            except Exception as e:
                warning(f"[SSD] 延迟计算异常: {e}")

        # 保存波形截图
        wf = self._save_waveform(osc, input_cond, proto, vout, iout)
        try:
            osc.run()   # 恢复采集
        except Exception:
            pass

        return delay_ms, wf

    # ---------- _calc_startup_delay ----------
    def _calc_startup_delay(self, x_in, y_in, x_out, y_out, vout_target: float) -> float:
        """
        从双通道波形数据计算开机延迟时间。

        算法：
          1. 找输入波形首次越过 10% 峰值的位置 → T_on（AC 上电时刻）
          2. 找输出波形首次达到 vout_target × 90% 的位置 → T_90%（输出建立时刻）
          3. 延迟 = T_90% - T_on

        Args:
            x_in, y_in:  输入通道 (时间, 电压)
            x_out, y_out: 输出通道 (时间, 电压)
            vout_target: 目标输出电压（V）

        Returns:
            delay_s: 延迟时间（秒）
        """
        import numpy as np

        if len(x_in) == 0 or len(x_out) == 0:
            return 0.0

        v_target_90 = vout_target * 0.90
        v_in_max = np.max(y_in)
        v_in_threshold = v_in_max * 0.10   # 10% of Vin peak as threshold

        # --- 找 T_on：输入电压首次越过阈值的时刻 ---
        above_threshold = np.where(y_in >= v_in_threshold)[0]
        if len(above_threshold) == 0:
            return 0.0
        t_on_idx = above_threshold[0]
        t_on = float(x_in[t_on_idx])

        # --- 找 T_90%：输出电压首次达到 vout_target×90% 的时刻 ---
        # 使用滑动平均平滑输出波形，避免噪声导致误判
        window = min(50, len(y_out) // 20)
        if window < 3:
            window = 3
        y_smooth = np.convolve(y_out, np.ones(window) / window, mode='same')
        above_90 = np.where(y_smooth >= v_target_90)[0]
        if len(above_90) == 0:
            return 0.0
        t_90_idx = above_90[0]
        t_90 = float(x_out[t_90_idx])

        delay = t_90 - t_on
        return max(0.0, delay)

    # ---------- _save_waveform ----------
    def _save_waveform(self, osc, input_cond: str, proto: str,
                       vout: float, iout: float) -> str:
        """
        保存双通道波形截图。
        文件名：{用例名}_{输入条件}_{协议}_Vout{V}V_Iout{I}A_delay.png
        """
        if osc is None:
            return ""

        base_dir = self._get_waveform_dir()
        os.makedirs(base_dir, exist_ok=True)

        fname = (f"{self.name}_{input_cond}_{proto}_"
                 f"Vout{vout}V_Iout{iout}A_delay.png")
        fpath = os.path.join(base_dir, fname)
        try:
            result = osc.save_screenshot(fpath)
            if result:
                info(f"[SSD] 波形已保存: {fname}")
                return result
            warning(f"[SSD] 波形截图驱动返回 None: {fpath}")
            return ""
        except Exception as e:
            warning(f"[SSD] 波形截图异常: {e}")
            return ""

    # ---------- _record_result ----------
    def _record_result(
        self, input_cond, proto_label, vout_target, iout_eff,
        spec_lo, spec_hi, delay_ms, waveform,
    ):
        """记录单条测试结果。"""
        if delay_ms <= 0:
            conclusion = "SKIP"
            fail_reason = "延迟时间计算失败"
            passed = False
        elif spec_lo <= delay_ms <= spec_hi:
            conclusion = "PASS"
            fail_reason = ""
            passed = True
        else:
            conclusion = "FAIL"
            fail_reason = f"延迟={delay_ms:.3f}ms 超范围[{spec_lo:.1f}~{spec_hi:.1f}]ms"
            passed = False

        self.sub_results.append(self._make_result(
            input_cond=input_cond,
            proto_label=proto_label,
            vout_target=round(vout_target, 3),
            iout_eff=round(iout_eff, 3),
            spec_lo=spec_lo,
            spec_hi=spec_hi,
            delay_ms=round(delay_ms, 3),
            waveform=waveform,
            conclusion=conclusion,
            fail_reason=fail_reason,
            passed=passed,
        ))

    # ---------- _skip_condition ----------
    def _skip_condition(self, input_cond, proto_label, vout_target, iout_eff,
                        spec_lo, spec_hi, fail_reason):
        """记录跳过条件的结果。"""
        self.sub_results.append(self._make_result(
            input_cond=input_cond,
            proto_label=proto_label,
            vout_target=round(vout_target, 3),
            iout_eff=round(iout_eff, 3),
            spec_lo=spec_lo,
            spec_hi=spec_hi,
            delay_ms=0.0,
            waveform="",
            conclusion="SKIP",
            fail_reason=fail_reason,
            passed=False,
        ))

    # ---------- _make_result ----------
    def _make_result(
        self, *, input_cond: str,
        proto_label: str, vout_target: float, iout_eff: float,
        spec_lo: float, spec_hi: float,
        delay_ms: float, waveform: str,
        conclusion: str, fail_reason: str,
        passed: bool,
    ) -> dict:
        return {
            "输入条件":        input_cond,
            "协议":            proto_label,
            "输出电压(V)":     vout_target,
            "输出电流(A)":    iout_eff,
            "规格上限":        spec_hi,
            "规格下限":        spec_lo,
            "开机延迟时间(ms)": delay_ms,
            "测试结论":        conclusion,
            "测试波形":        waveform,
            "备注":            fail_reason,
            # 内部字段
            "_pass":           passed,
        }

    # ---------- verify ----------
    def verify(self) -> bool:
        """所有 sub_result 均 PASS 才返回 True。"""
        return bool(self.sub_results) and all(
            r["_pass"] or r["测试结论"] == "SKIP"
            for r in self.sub_results
        )

    # ---------- to_dict ----------
    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        return d
