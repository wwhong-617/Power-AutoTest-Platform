# -*- coding: utf-8 -*-
"""
InputUnderVoltageTest - 输入欠压保护测试
==========================================

测试目标：
  验证 DUT 在输入电压跌落至欠压点时的保护行为（自恢复或锁死），
  以及输入电压回升至恢复点时输出是否按预期恢复。

test_conditions 格式（6 元组）：
  (vin_min, freq, proto_label, vout_target, iout_target, product_type)

保护逻辑：
  protection_mode = "self"（自恢复）：
    - 欠压点（uvp_point）必须在 brown_out [lo, hi] 范围内
    - 恢复点（recovery_point）必须在 brown_in [lo, hi] 范围内
  protection_mode = "latch"（锁死）：
    - 欠压点（uvp_point）必须在 brown_out [lo, hi] 范围内
    - 在 brown_in 范围内不得发生重启

sub_result 字段：
  input_cond, condition, proto_label, vout_target, iout_target,
  brown_out_hi, brown_out_lo, brown_in_hi, brown_in_lo,
  uvp_point, recovery_point,
  restart_in_fast_down, restart_in_fast_up, latch_restart_in_slow_up,
  overall_pass, fail_reason, waveform, skipped
"""

import time
import os
import sys
from ..base import TestCase
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class InputUnderVoltageTest(TestCase):
    """
  输入欠压保护测试（每条 test_condition 独立执行）。

  测试步骤：
    1. 开机自检（基类 startup_self_check，不下电）
    2. 示波器 ROLL 模式（估算扫描总时长设置时基）
    3. 诱骗器协议（charger 专用）
    4. 电子负载 CC 模式上电
    5. 电压扫描（4阶段）
    6. 示波器 STOP 冻结波形，保存截图
    7. 汇总判定

  电压扫描 4 阶段：
    ① 缓降：Vin_min → (brown_out_lo - 5V)，0.5V/步，2s/步
           检测输出 < Vout×70% → 记录 uvp_point，切换负载电流
    ② 快降：(brown_out_lo - 5V) → 0V，5V/步，1s/步
           检测快降过程中是否有重启
    ③ 快升：0V → (brown_in_lo - 5V)，5V/步，1s/步
           检测快升过程中是否有提前恢复
    ④ 缓升：(brown_in_lo - 5V) → Vin_min，0.5V/步，2s/步
           - self 模式：检测输出 > Vout×90% → 记录 recovery_point
           - latch 模式：检测输出 > Vout×70% → 判定重启（FAIL）

  判定逻辑：
    protection_mode = "self"：
      uvp_point ∈ [brown_out_lo, brown_out_hi]
      且 recovery_point ∈ [brown_in_lo, brown_in_hi] → PASS
    protection_mode = "latch"：
      uvp_point ∈ [brown_out_lo, brown_out_hi]
      且缓升过程无重启 → PASS
  """

    # ---------- 常量 ----------
    VOLTAGE_STEP_FINE    = 0.5   # 缓调步进（V）
    VOLTAGE_STEP_COARSE = 5.0   # 快调步进（V）
    SETTLE_TIME          = 2.0   # 缓调每步等待时间（秒）
    VOUT_DROPOUT_RATIO  = 0.7   # 输出掉电判定阈值：Vout × 此值
    VOUT_RECOVERY_RATIO = 0.9   # 输出恢复判定阈值：Vout × 此值

    # ---------- 报告列定义 ----------
    # 顺序即 Excel 列顺序，按 COLS 定义顺序渲染所有列
    COLS = [
                ("输入条件",          16),
                ("协议",              14),
                ("输出电压(V)",       14),
                ("输出电流(A)",       14),
                ("欠压点上限(V)",     15),
                ("欠压点下限(V)",     15),
                ("恢复点上限(V)",     15),
                ("恢复点下限(V)",     15),
                ("欠压点数据(V)",     15),
                ("恢复点数据(V)",     15),
                ("重启现象",           12),
                ("测试波形",           18),
                ("测试结论",           11),
                ("备注",              28),
    ]

    # ---------- __init__ ----------
    def __init__(self,
                 brown_out_lo: float = 60.0,
                 brown_out_hi: float = 70.0,
                 brown_in_lo: float = 70.0,
                 brown_in_hi: float = 80.0,
                 protection_mode: str = "self",
                 product_type: str = "charger",
                 test_conditions: List[dict] = None,
                 settle_time: float = None,
                 osc_waveform_dir: str = None):
        self.brown_out_lo    = brown_out_lo
        self.brown_out_hi    = brown_out_hi
        self.brown_in_lo     = brown_in_lo
        self.brown_in_hi     = brown_in_hi
        self.protection_mode = protection_mode
        self.product_type    = product_type
        self.test_conditions = test_conditions or []
        self.settle_time    = settle_time if settle_time is not None else self.SETTLE_TIME
        self.sub_results: List[dict] = []

        super().__init__(
            name="InputUnderVoltageTest",
            instruments=["AC_SOURCE", "ELOAD", "OSC", "SNIFFER", "POWER_METER"],
            params={
                "brown_out_lo":    brown_out_lo,
                "brown_out_hi":    brown_out_hi,
                "brown_in_lo":     brown_in_lo,
                "brown_in_hi":     brown_in_hi,
                "protection_mode": protection_mode,
                "product_type":    product_type,
                "test_conditions": test_conditions,
                "settle_time":     self.settle_time,
            },
            spec={
                "brown_out_lo": brown_out_lo,
                "brown_out_hi": brown_out_hi,
                "brown_in_lo":  brown_in_lo,
                "brown_in_hi":  brown_in_hi,
            }
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """初始化仪器状态（仅配置，不上电）。"""
        self.sub_results = []
        super().setup(instruments)

        # ---- 缓存 UI 参数 ----
        self.conditions         = self.test_conditions or self.params.get("test_conditions", [])
        self.osc_input_ch      = int(self.params.get("osc_input_ch",   4))
        self.osc_output_ch     = int(self.params.get("osc_output_ch",  2))
        self.pwr_out_v_ch      = self.params.get("pwr_out_v_ch", "CH1")
        self.load_startup_enabled  = bool(self.params.get("load_startup_enabled", 0))
        self.load_startup_current  = float(self.params.get("load_startup_current", 0.0))
        self.load_startup_voltage = float(self.params.get("load_startup_voltage", 5.0))
        self.vin_cfg_est = self.conditions[0]["vin"] if self.conditions else 90.0

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """
        主流程：逐条 test_conditions 执行，每条经 7 个步骤。

        步骤1：开机自检（不下电）
        步骤2：示波器 ROLL 模式
        步骤3：诱骗器协议
        步骤4：电子负载 CC 模式上电
        步骤5：电压扫描 4 阶段
        步骤6：示波器 STOP，保存波形
        步骤7：汇总判定，记录 sub_result
        """
        ac      = instruments.get("AC_SOURCE")
        eload   = instruments.get("ELOAD")
        osc     = instruments.get("OSC")
        sniffer = instruments.get("SNIFFER")
        pwr     = instruments.get("POWER_METER")


        for cond in self.conditions:
            if len(cond) < 5:
                continue

            vin_min, freq_cfg, proto_label, vout_target, iout_target = \
                cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            input_cond = f"{vin_min}V_{freq_cfg}Hz"
            cond_label = f"{proto_label}_Vout{vout_target}V_Iout{iout_target}A"

            # 功率分段
            iout_eff = self._get_effective_iout(float(vin_min), float(vout_target), float(iout_target))
            if iout_eff != float(iout_target):
                info(f"[IUVT] 条件「{cond_label}」功率分段降流：Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # ---- 步骤1：开机自检 ----
            startup_ok, _, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_min), freq=float(freq_cfg)
            )
            if not startup_ok:
                info(f"[IUVT] 条件「{cond_label}」{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self.sub_results.append(self._make_result(
                    input_cond=input_cond,
                    proto_label=proto_label,
                    vout_target=vout_target,
                    iout_target=iout_eff,
                    brown_out_hi=self.brown_out_hi,
                    brown_out_lo=self.brown_out_lo,
                    brown_in_hi=self.brown_in_hi,
                    brown_in_lo=self.brown_in_lo,
                    uvp_point=None,
                    recovery_point=None,
                    overall_pass=False,
                    fail_reason=fail_reason,
                    waveform=None,
                    skipped=True,
                ))
                continue

            # ---- 步骤2：示波器 ROLL 模式 ----
            self._step_setup_osc(osc, vout_target)

            # ---- 步骤3：诱骗器协议 ----
            sniffer_ok = self._step_setup_sniffer(sniffer, proto_label, vout_target, iout_eff)
            info(f"[IUVT] 诱骗器 {proto_label} {'成功' if sniffer_ok else '失败'}")

            # ---- 步骤4：电子负载 CC 模式上电（功率分段后电流）----
            self._step_setup_eload(eload, iout_eff)
            info(f"[IUVT] 电子负载 ON | Iout={iout_eff:.3f}A")

            # ---- 步骤5：电压扫描 4 阶段 ----
            uvp_point, recovery_point = self._step_voltage_sweep(
                ac, osc, eload, pwr, float(vin_min), vout_target)

            # ---- 步骤6：示波器 STOP 冻结波形，保存截图 ----
            # base._step_capture_and_measure 返回 (osc_vmax, osc_vmin, wave_path)
            _, _, wave_path = self._step_capture_and_measure(
                osc, self.osc_output_ch, input_cond, proto_label, vout_target, iout_target)

            # ---- 步骤7：汇总判定 ----
            overall_pass, fail_reason = self._judge(uvp_point, recovery_point, vout_target)

            self.sub_results.append(self._make_result(
                input_cond=input_cond,
                proto_label=proto_label,
                vout_target=vout_target,
                iout_target=iout_eff,
                brown_out_hi=self.brown_out_hi,
                brown_out_lo=self.brown_out_lo,
                brown_in_hi=self.brown_in_hi,
                brown_in_lo=self.brown_in_lo,
                uvp_point=uvp_point,
                recovery_point=recovery_point,
                overall_pass=overall_pass,
                fail_reason=fail_reason,
                waveform=wave_path,
                skipped=False,
            ))

            # ---- 本条条件结束：放电 ----
            self._step_discharge(ac, eload)

    # ---------- 步骤方法 ----------

    def _step_setup_osc(self, osc, vout: float):
        """
        步骤2：配置示波器 ROLL 模式，配合欠压测试四阶段扫描。

        - 先开启输入通道（Vin 监测）和输出通道（Vout 监测）
        - 时基根据估算扫描时间常数设置，配合欠压测试 4 阶段
        - ROLL 模式下示波器持续刷新，等待扫描期间持续采集
        """
        if osc is None:
            warning("[IUVT] 示波器未连接，跳过")
            return

        # 计算扫描时间常数
        descend_time = self.vin_cfg_est / self.VOLTAGE_STEP_FINE * self.settle_time
        ascend_time  = (self.vin_cfg_est - self.brown_in_lo + 10) / self.VOLTAGE_STEP_FINE * self.settle_time
        total_time  = descend_time + ascend_time
        timebase    = max(10.0, total_time / 10.0)
        
        # 设置输入通道
        osc.set_channel_config(channel=self.osc_input_ch, coupling="DC",
                              voltage_scale=50.0,
                              voltage_offset=0.0,
                              bandwidth_limit=True)
        osc.set_channel_on(self.osc_input_ch)
        # 设置输出通道
        osc.auto_config_channel(channel=self.osc_output_ch, v_peak=vout,
                              coupling="DC",
                              bandwidth_limit=True)
        osc.set_channel_on(self.osc_output_ch)
        
        osc.set_timebase_mode("ROLL")
        time.sleep(0.3)
        osc.set_timebase(timebase)
        time.sleep(0.5)
        info(f"[IUVT] 示波器 ROLL | 时基={timebase:.1f}s/div")
    def _step_voltage_sweep(self, ac, osc, eload, pwr,
                             vin_cfg: float, vout_target: float) -> tuple:
        """
        步骤5：电压扫描（4阶段）。

        监测输出电压（功率计通道1），检测欠压点和恢复点。
        返回 (uvp_point, recovery_point)。
        """
        brown_out_lo    = self.brown_out_lo
        brown_in_lo     = self.brown_in_lo
        dropout_thresh  = vout_target * self.VOUT_DROPOUT_RATIO
        recovery_thresh = self.load_startup_voltage * self.VOUT_RECOVERY_RATIO

        uvp_point      = None
        recovery_point = None
        self._restart_in_fast_down    = False
        self._restart_in_fast_up     = False
        self._latch_restart_in_slow_up = False

        osc.clear_screen()
        time.sleep(0.5)

        # ── ① 缓降：Vin_min → (brown_out_lo - 5V)，0.5V/步，2s/步 ────────
        descend_start = round(max(0, brown_out_lo - 5.0), 1)
        info(f"[IUVT] ①缓降 | {vin_cfg}V → {descend_start}V")
        vac = vin_cfg
        vout_now = None
        while vac > descend_start + 0.001:
            if self.is_stop_requested():
                self._emergency_off(ac)
                break
            while self.is_pause_requested() and not self.is_stop_requested():
                time.sleep(0.2)

            freq = 50.0 if vac >= 180 else 60.0
            if ac:
                ac.set_voltage(round(vac, 1))
                ac.set_frequency(freq)
            time.sleep(self.settle_time)

            try:
                vout_now = pwr.measure_voltage(self.pwr_out_v_ch) if pwr else None
            except Exception:
                vout_now = None

            if vout_now is not None and vout_now < dropout_thresh and uvp_point is None:
                uvp_point = round(vac, 2)
                info(f"[IUVT] 欠压点 | Vac={uvp_point}V | Vout={vout_now:.3f}V")
                if eload is not None:
                    if self.load_startup_enabled:
                        eload.set_mode_cc(self.load_startup_current)
                        info(f"[IUVT] 欠压后负载切换 → {self.load_startup_current}A")
                    else:
                        eload.set_mode_cc(0.0)
                        info("[IUVT] 欠压后负载切换 → 0A")
                break

            vac -= self.VOLTAGE_STEP_FINE

        # ── ② 快降：(brown_out_lo - 5V) → 0V，5V/步，1s/步 ─────────────
        info(f"[IUVT] ②快降 | {descend_start}V → 0V")
        vac = descend_start
        was_below  = (vout_now is not None and vout_now < dropout_thresh) \
                     if vout_now is not None else False
        above_count = 0
        while vac > 0.001:
            if self.is_stop_requested():
                self._emergency_off(ac)
                break
            vac = max(0, round(vac - self.VOLTAGE_STEP_COARSE, 1))
            if ac:
                ac.set_voltage(vac)
            time.sleep(1.0)

            try:
                vout_now = pwr.measure_voltage(self.pwr_out_v_ch) if pwr else None
            except Exception:
                vout_now = None

            if vout_now is not None:
                if vout_now < dropout_thresh:
                    above_count = 0
                    was_below   = True
                elif was_below and vout_now > dropout_thresh:
                    above_count += 1
                    was_below   = False
                    if above_count >= 2:
                        self._restart_in_fast_down = True
                        info(f"[IUVT] 快降过程检测到重启 | Vac≈{vac}V")
                        break

        # ── ③ 快升：0V → (brown_in_lo - 5V)，5V/步，1s/步 ───────────────
        rise_fast_target = round(max(0, brown_in_lo - 5.0), 1)
        info(f"[IUVT] ③快升 | 0V → {rise_fast_target}V")
        vac = 0.0
        was_above   = False
        below_count = 0
        while vac < rise_fast_target - 0.001:
            if self.is_stop_requested():
                self._emergency_off(ac)
                break
            vac = round(min(vac + self.VOLTAGE_STEP_COARSE, rise_fast_target), 1)
            freq = 50.0 if vac >= 180 else 60.0
            if ac:
                ac.set_voltage(vac)
                ac.set_frequency(freq)
            time.sleep(1.0)

            try:
                vout_now = pwr.measure_voltage(self.pwr_out_v_ch) if pwr else None
            except Exception:
                vout_now = None

            if vout_now is not None:
                if vout_now > recovery_thresh:
                    below_count = 0
                    was_above   = True
                elif was_above and vout_now < recovery_thresh:
                    below_count += 1
                    was_above   = False
                    if below_count >= 2:
                        self._restart_in_fast_up = True
                        info(f"[IUVT] 快升过程检测到重启 | Vac≈{vac}V")
                        break

        # ── ④ 缓升：(brown_in_lo - 5V) → Vin_min，0.5V/步，2s/步 ──────
        info(f"[IUVT] ④缓升 | {rise_fast_target}V → {vin_cfg}V")
        vac = rise_fast_target
        while vac < vin_cfg - 0.001:
            if self.is_stop_requested():
                self._emergency_off(ac)
                break
            while self.is_pause_requested() and not self.is_stop_requested():
                time.sleep(0.2)

            vac = round(min(vac + self.VOLTAGE_STEP_FINE, vin_cfg), 1)
            freq = 50.0 if vac >= 180 else 60.0
            if ac:
                ac.set_voltage(vac)
                ac.set_frequency(freq)
            time.sleep(self.settle_time)

            try:
                vout_now = pwr.measure_voltage(self.pwr_out_v_ch) if pwr else None
            except Exception:
                vout_now = None

            if self.protection_mode == "self":
                if vout_now is not None and vout_now > recovery_thresh and recovery_point is None:
                    recovery_point = round(vac, 2)
                    info(f"[IUVT] 恢复点 | Vac={recovery_point}V | Vout={vout_now:.3f}V")
            else:
                if vout_now is not None and vout_now > dropout_thresh:
                    info(f"[IUVT] 锁死缓升检测到重启 | Vac≈{vac}V | Vout={vout_now:.3f}V")
                    self._latch_restart_in_slow_up = True

        return uvp_point, recovery_point

    def _emergency_off(self, ac):
        """紧急下电（用户按停止键时调用）。"""
        if ac and getattr(ac, "_connected", False):
            try:
                ac.set_voltage(0)
            except Exception:
                pass

    # ---------- 判定 ----------

    def _judge(self, uvp_point, recovery_point, vout_target: float) -> tuple:
        """
        判定单条测试条件的结果。

        self 模式通过条件：
          - uvp_point 存在于 [brown_out_lo, brown_out_hi]
          - recovery_point 存在于 [brown_in_lo, brown_in_hi]

        latch 模式通过条件：
          - uvp_point 存在于 [brown_out_lo, brown_out_hi]
          - 缓升过程无重启（latch_restart_in_slow_up = False）
        """
        brown_out_lo = self.brown_out_lo
        brown_out_hi = self.brown_out_hi
        brown_in_lo  = self.brown_in_lo
        brown_in_hi  = self.brown_in_hi
        mode = self.protection_mode
        reasons = []

        if uvp_point is None:
            reasons.append("未触发欠压保护")
            return False, "; ".join(reasons)

        if not (brown_out_lo <= uvp_point <= brown_out_hi):
            reasons.append(
                f"欠压点({uvp_point}V)超出规格范围({brown_out_lo}~{brown_out_hi}V)"
            )

        if mode == "self":
            if recovery_point is None:
                reasons.append("自恢复模式未在恢复点恢复")
            elif not (brown_in_lo <= recovery_point <= brown_in_hi):
                reasons.append(
                    f"恢复点({recovery_point}V)超出规格范围({brown_in_lo}~{brown_in_hi}V)"
                )
        elif mode == "latch":
            if self._latch_restart_in_slow_up:
                reasons.append("锁死模式缓升过程发生重启")

        fail_reason  = "; ".join(reasons) if reasons else ""
        overall_pass = (len(reasons) == 0)
        return overall_pass, fail_reason

    # ---------- 结果构造 ----------

    def _make_result(self, *, input_cond: str,
                     proto_label: str, vout_target: float, iout_target: float,
                     brown_out_hi: float, brown_out_lo: float,
                     brown_in_hi: float, brown_in_lo: float,
                     uvp_point, recovery_point,
                     overall_pass: bool, fail_reason: str,
                     waveform: str, skipped: bool) -> dict:
        """
        组装单条测试结果（sub_result）。
        字段名即报告列名，直接对应 report_generator 的 COLS 定义。
        """
        # 重启现象：任意一种重启发生即为"有"
        has_restart = (
            getattr(self, '_restart_in_fast_down', False)
            or getattr(self, '_restart_in_fast_up', False)
            or getattr(self, '_latch_restart_in_slow_up', False)
        )
        return {
            "输入条件":       input_cond,
            "协议":           proto_label,
            "输出电压(V)":    vout_target,
            "输出电流(A)":    iout_target,
            "欠压点上限(V)":  brown_out_hi,
            "欠压点下限(V)":  brown_out_lo,
            "恢复点上限(V)":  brown_in_hi,
            "恢复点下限(V)":  brown_in_lo,
            "欠压点数据(V)":  uvp_point,
            "恢复点数据(V)":  recovery_point,
            "重启现象":       "有" if has_restart else "无",
            "测试波形":       waveform,
            "测试结论":       "SKIP" if skipped else ("PASS" if overall_pass else "FAIL"),
            "备注":           fail_reason,
            "overall_pass":   overall_pass,
            "fail_reason":   fail_reason,
            "skipped":       skipped,
        }

    # ---------- 结论 ----------

    def verify(self) -> bool:
        """所有条件 overall_pass 为 True 才 PASS。"""
        return bool(self.sub_results) and all(r["overall_pass"] for r in self.sub_results)

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

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"]    = self.sub_results
        d["product_type"]  = self.product_type
        d["protection_mode"] = self.protection_mode
        d["spec"] = {
            "brown_out_lo": self.brown_out_lo,
            "brown_out_hi": self.brown_out_hi,
            "brown_in_lo":  self.brown_in_lo,
            "brown_in_hi":  self.brown_in_hi,
        }
        passed = sum(1 for r in self.sub_results if r["overall_pass"])
        d["sweep_summary"] = {
            "conditions_tested":  len(self.sub_results),
            "passed_conditions": passed,
            "failed_conditions": len(self.sub_results) - passed,
        }
        return d
