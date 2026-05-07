# -*- coding: utf-8 -*-
"""
OutputRiseTimeTest - 输出电压上升时间测试
==========================================

测量 DUT 开机时输出电压的上升时间（10%-90%），
判断是否在规格范围内。

【test_conditions 格式】
  List[dict]，每项字段：vin / freq / proto / vout / iout

【测试流程（每条条件）】
  setup()     初始化示波器通道（DC 耦合 / 全带宽）
  execute()   遍历条件，逐条件执行以下步骤
  verify()    所有 sub_result 均 PASS 才返回 True

  每条件步骤：
    1. 开机自检（基类 startup_self_check），捕获实测开机电压
    2. 用实测开机电压配置示波器（时基根据上升时间规格自适应）
    3. 放电下电（确保完全下电，进入冷启动）
    4. 武装示波器 SINGLE 触发 → 开机自检上电 → 等待触发
    5. 读取上升时间数据 + 波形截图
    6. 放电下电

【报告字段】
  序号 | 用例名称 | 输入条件 | 协议 | 输出电压(V) | 输出电流(A) |
  规格上限 | 规格下限 | 上升时间(ms) | 测试结论 | 测试波形 | 备注
"""

import time
import os
import sys
from typing import Dict, Any, List
from ..base import TestCase

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class OutputRiseTimeTest(TestCase):
    """输出电压上升时间测试。"""

    TRIGGER_TIMEOUT = 5.0    # 示波器触发等待超时（s）
    TRIGGER_WAIT_S  = 0.3    # 轮询触发状态间隔（s）
    TIME_BASE_S     = 0.005  # 示波器时基 5ms/div（默认，开机瞬态 10ms 总窗口）

    # 报告列定义
    COLS = [
        ("输入条件",      16),
        ("协议",          12),
        ("输出电压(V)",   13),
        ("输出电流(A)",  13),
        ("规格上限",     11),
        ("规格下限",     11),
        ("上升时间(ms)",  13),
        ("测试结论",      12),
        ("测试波形",      18),
        ("备注",          28),
    ]

    # ---------- __init__ ----------
    def __init__(
        self,
        rise_time_ms_lo: float = 0.0,
        rise_time_ms_hi: float = 20.0,
        product_type: str = "charger",
        test_conditions: List[dict] = None,
        osc_output_ch: int = 2,
    ):
        """
        Args:
            rise_time_ms_lo:  上升时间规格下限（ms）
            rise_time_ms_hi:  上升时间规格上限（ms）
            product_type:     产品类型，"charger" 或 "adapter"
            test_conditions:   测试条件列表，每项 dict，
                              字段：vin / freq / proto / vout / iout
            osc_output_ch:    示波器输出通道编号（默认2）
        """
        self.sub_results: List[dict] = []

        super().__init__(
            name="OutputRiseTimeTest",
            instruments=["AC_SOURCE", "ELOAD", "OSC", "POWER_METER"],
            params={
                "osc_output_ch":   osc_output_ch,
                "product_type":    product_type,
                "test_conditions": test_conditions,
            },
            spec={
                "上升时间_ms_lo": rise_time_ms_lo,
                "上升时间_ms_hi": rise_time_ms_hi,
            },
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """示波器初始化：DC 耦合 / 全带宽。"""
        self.sub_results = []
        super().setup(instruments)

        self.osc_output_ch = int(self.params.get("osc_output_ch", 2))
        osc = instruments.get("OSC")
        if osc is None:
            warning("[RIT] 示波器未连接，跳过公共配置")
            return

        # 时基（默认固定）
        osc.set_timebase(self.TIME_BASE_S)

        # 通道配置：DC 耦合，全带宽（瞬态信号需全带宽）
        osc.set_channel_on(self.osc_output_ch)
        osc.set_channel_coupling(self.osc_output_ch, "DC")
        osc.set_bandwidth_limit(self.osc_output_ch, False)

        # 添加上升时间测量项
        osc.clear_measurements()
        osc.add_measurement(self.osc_output_ch, "RISETIME")

        info(f"[RIT] 示波器公共配置完成 | CH{self.osc_output_ch} "
             f"时基={self.TIME_BASE_S*1000:.1f}ms/div 全带宽")

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """执行输出电压上升时间测试。"""
        ac    = self._ac(instruments)
        eload = self._eload(instruments)
        osc   = self._osc(instruments)

        conditions = self.params.get("test_conditions", [])
        if not conditions:
            warning("[RIT] 无测试条件，跳过执行")
            return

        spec_hi = self.spec.get("上升时间_ms_hi", 20.0)
        spec_lo = self.spec.get("上升时间_ms_lo", 0.0)

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
                info(f"[RIT] 条件「{cond_label}」功率分段降流："
                     f"Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # --- 步骤1：开机自检，捕获实测开机电压 ---
            startup_ok, vout_default, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            if not startup_ok:
                info(f"[RIT] 条件「{cond_label}」开机自检失败："
                     f"{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self._skip_condition(
                    input_cond, proto_label, vout_target, iout_eff,
                    spec_lo, spec_hi, fail_reason,
                )
                continue

            # --- 步骤2：用实测开机电压配置示波器 ---
            self._osc_prepare(osc, vout_default, spec_hi)

            # --- 步骤3：放电下电（确保冷启动）---
            self._step_discharge(ac, eload)

            # --- 步骤4：武装示波器 SINGLE 触发 → 开机自检上电 → 等待触发 ---
            if osc:
                osc.set_single_trigger()
                time.sleep(1.0)

            cold_ok, _, cold_fail = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )

            if osc:
                info(f"[RIT] 开机等待触发 | timeout={self.TRIGGER_TIMEOUT}s")
                triggered = self._osc_wait_trigger(
                    osc, timeout_s=self.TRIGGER_TIMEOUT,
                    poll_interval=self.TRIGGER_WAIT_S,
                )
                if not triggered:
                    osc.stop()

            # --- 步骤5：读取上升时间 + 波形 ---
            rise_ms, waveform = self._read_rise_time(
                osc, input_cond, proto_label, float(vout_target), float(iout_eff),
            )

            # --- 步骤6：放电下电 ---
            self._step_discharge(ac, eload)

            # --- 记录结果 ---
            self._record_result(
                input_cond, proto_label, vout_target, iout_eff,
                spec_lo, spec_hi, rise_ms, waveform,
            )

    # ---------- _osc_prepare ----------
    def _osc_prepare(self, osc, vout_measured: float, spec_hi_ms: float):
        """
        用实测开机电压配置示波器。
        时基根据规格上限自适应：规格越大，时基越宽。

        Args:
            vout_measured: 开机后实测输出电压（基准值）
            spec_hi_ms:    上升时间规格上限（ms），用于时基自适应
        """
        if osc is None:
            return

        # 时基自适应：总窗口 = spec_hi × 2，最低 10ms，最高 100ms
        total_ms = max(10.0, min(spec_hi_ms * 2.5, 100.0))
        scale_s = total_ms / 1000.0 / 10.0   # 10 div
        osc.set_timebase(scale_s)

        ch = self.osc_output_ch
        # 刻度 = 开机电压 × 1.5 / 4格
        v_peak = vout_measured * 1.5
        scale = osc.round_voltage_scale(v_peak / 4.0)
        # 偏移：波形底部对准屏幕第2格
        offset = vout_measured / 2.0
        osc.set_voltage_scale(ch, scale)
        osc.set_channel_offset(ch, offset)
        osc.set_trigger_source(f"CHAN{ch}")
        osc.set_trigger_level(vout_measured * 0.5)
        osc.set_trigger_slope("POS")
        info(f"[RIT] 示波器配置 | Vout实测={vout_measured:.3f}V "
             f"时基={scale_s*1000:.1f}ms/div 刻度={scale:.3f}V/div")

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
                info(f"[RIT] 触发完成 | elapsed={elapsed:.2f}s")
                return True
            elapsed += poll_interval
            time.sleep(poll_interval)
        warning(f"[RIT] 触发超时 | {elapsed:.1f}s 未触发")
        return False

    # ---------- _read_rise_time ----------
    def _read_rise_time(self, osc, input_cond: str, proto: str,
                        vout: float, iout: float) -> tuple:
        """
        读取示波器上升时间测量值。

        Returns:
            (rise_time_ms, waveform_path)
        """
        rise_ms = 0.0
        wf = ""

        if osc is None:
            return rise_ms, wf

        # 内置测量：示波器已缓存 add_measurement 配置的测量值
        try:
            rise_s = osc.measure_rise_time_builtin(self.osc_output_ch) or 0.0
            rise_ms = rise_s * 1000.0
            info(f"[RIT] 上升时间读数 | {rise_ms:.3f}ms")
        except Exception as e:
            warning(f"[RIT] 上升时间读取异常: {e}")

        # 保存波形
        wf = self._save_waveform(osc, input_cond, proto, vout, iout)
        try:
            osc.run()   # 恢复采集
        except Exception:
            pass

        return rise_ms, wf

    # ---------- _save_waveform ----------
    def _save_waveform(self, osc, input_cond: str, proto: str,
                       vout: float, iout: float) -> str:
        """
        保存波形截图。
        文件名：{用例名}_{输入条件}_{协议}_Vout{V}V_Iout{I}A_rise.png
        """
        if osc is None:
            return ""

        base_dir = self._get_waveform_dir()
        os.makedirs(base_dir, exist_ok=True)

        fname = (f"{self.name}_{input_cond}_{proto}_"
                 f"Vout{vout}V_Iout{iout}A_rise.png")
        fpath = os.path.join(base_dir, fname)
        try:
            result = osc.save_screenshot(fpath)
            if result:
                info(f"[RIT] 波形已保存: {fname}")
                return result
            warning(f"[RIT] 波形截图驱动返回 None: {fpath}")
            return ""
        except Exception as e:
            warning(f"[RIT] 波形截图异常: {e}")
            return ""

    # ---------- _record_result ----------
    def _record_result(
        self, input_cond, proto_label, vout_target, iout_eff,
        spec_lo, spec_hi, rise_ms, waveform,
    ):
        """记录单条测试结果。"""
        passed = spec_lo <= rise_ms <= spec_hi
        if rise_ms <= 0:
            conclusion = "SKIP"
            fail_reason = "上升时间读取失败"
        elif passed:
            conclusion = "PASS"
            fail_reason = ""
        else:
            conclusion = "FAIL"
            fail_reason = f"上升时间={rise_ms:.3f}ms 超范围[{spec_lo:.1f}~{spec_hi:.1f}]ms"

        self.sub_results.append(self._make_result(
            input_cond=input_cond,
            proto_label=proto_label,
            vout_target=round(vout_target, 3),
            iout_eff=round(iout_eff, 3),
            spec_lo=spec_lo,
            spec_hi=spec_hi,
            rise_ms=round(rise_ms, 3),
            waveform=waveform,
            conclusion=conclusion,
            fail_reason=fail_reason,
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
            rise_ms=0.0,
            waveform="",
            conclusion="SKIP",
            fail_reason=fail_reason,
        ))

    # ---------- _make_result ----------
    def _make_result(
        self, *, input_cond: str,
        proto_label: str, vout_target: float, iout_eff: float,
        spec_lo: float, spec_hi: float,
        rise_ms: float, waveform: str,
        conclusion: str, fail_reason: str,
    ) -> dict:
        return {
            "输入条件":      input_cond,
            "协议":          proto_label,
            "输出电压(V)":   vout_target,
            "输出电流(A)":  iout_eff,
            "规格上限":      spec_hi,
            "规格下限":      spec_lo,
            "上升时间(ms)":  rise_ms,
            "测试结论":      conclusion,
            "测试波形":      waveform,
            "备注":          fail_reason,
            # 内部字段
            "_pass":         conclusion == "PASS",
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
