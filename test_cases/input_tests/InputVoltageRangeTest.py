# -*- coding: utf-8 -*-
"""
InputVoltageRangeTest - 输入电压范围测试
==========================================

测试目标：
  验证 DUT 在 90Vac~264Vac 范围内输入电压缓调往返扫描时，
  输出电压保持稳定。示波器 ROLL 模式捕获完整扫描波形，
  判定 Vmax ≤ Vout×110% 且 Vmin ≥ Vout×90%。

test_conditions 格式（List[dict]）：
  [{"vin": float, "freq": float, "proto": str,
    "vout": float, "iout": float, "product_type": str}, ...]
"""

import time
import os
import sys
from ..base import TestCase
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class InputVoltageRangeTest(TestCase):
    """
    输入电压范围测试（每条 test_condition 独立执行）。

    测试步骤：
      1. 开机自检（基类 startup_self_check，不下电）
      2. 示波器 ROLL 模式（时基覆盖完整扫描时长）
      3. 诱骗器协议（charger 专用）
      4. 电子负载 CC 模式上电
      5. 电压往返扫描：先缓降（Vin_cfg→Vin_lo），再缓升（Vin_lo→Vin_cfg）
         Vac≥180V → 50Hz；Vac<180V → 60Hz；功率随电压段切换；每步等待 settle_time
      6. 示波器 STOP 冻结波形，测量 Vmax/Vmin，保存波形截图
      7. 汇总判定（Vmax≤Vout×110% 且 Vmin≥Vout×90%）
      8. 放电下电
    """

    # ---------- 常量 ----------
    VOLTAGE_STEP        = 5.0    # Vac 步进（V）
    FREQ_THRESHOLD      = 180.0  # Vac 分界线：≥180V → 50Hz
    DEFAULT_SETTLE_TIME = 2.0    # 每步稳定等待时间（秒）

    # ---------- 报告列定义 ----------
    # 顺序即 Excel 列顺序，按 COLS 定义顺序渲染所有列
    COLS = [
    # 注意：「测试结论」列不定义在 COLS 中，
    # 由 report_generator._flatten() 统一注入（prefix 列）。

                ("输入条件",       16),
                ("协议",           14),
                ("输出电压(V)",    14),
                ("输出电流(A)",    14),
                ("电压范围(V)",    16),
                ("规格下限",       11),
                ("规格上限",       11),
                ("最大值",         12),
                ("最小值",         12),
                ("测试结论",       12),
                ("测试波形",        18),
                ("备注",           28),
    ]

    # ---------- __init__ ----------
    # 注意：不要在这里设置 self.test_conditions！
    # 基类 TestCase 已有 dataclass 字段，__init__ 设置会遮蔽该字段，
    # 导致 setup() 中的缓存逻辑失效。
    # test_conditions 由引擎通过 params 注入，在 setup() 中缓存。
    def __init__(self,
                 input_voltage_min: float = 90.0,
                 input_voltage_max: float = 264.0,
                 vout_spec_min: float = None,
                 vout_spec_max: float = None,
                 product_type: str = "charger",
                 test_conditions: List[dict] = None,
                 settle_time: float = None):
        self.product_type = product_type
        self.settle_time  = settle_time if settle_time is not None else self.DEFAULT_SETTLE_TIME
        self.sub_results: List[dict] = []

        super().__init__(
            name="InputVoltageRangeTest",
            instruments=["AC_SOURCE", "ELOAD", "OSC", "SNIFFER", "POWER_METER"],
            params={
                "input_voltage_min": input_voltage_min,
                "input_voltage_max": input_voltage_max,
                "settle_time":      self.settle_time,
                "product_type":      product_type,
                "test_conditions":  test_conditions,
            },
            spec={
                "vout_min": vout_spec_min,
                "vout_max": vout_spec_max,
            }
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """初始化仪器状态（仅配置，不上电）。"""
        self.sub_results = []
        super().setup(instruments)

        # ---- 缓存 UI 参数 ----
        self.vin_lo_ui       = float(self.params.get("input_voltage_min", 90.0))
        self.osc_input_ch   = int(self.params.get("osc_input_ch",   4))
        self.osc_output_ch  = int(self.params.get("osc_output_ch",  2))
        self.test_conditions = self.test_conditions or self.params.get("test_conditions", [])
    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """
        主流程：逐条 test_conditions 执行，每条经 8 个步骤。

        步骤1：开机自检（不下电）
        步骤2：示波器 ROLL 模式
        步骤3：诱骗器协议
        步骤4：电子负载 CC 模式上电
        步骤5：电压往返扫描（先缓降 v_high→v_low，再缓升 v_low→v_high）
        步骤6：示波器 STOP，测量 Vmax/Vmin，保存波形
        步骤7：汇总判定，记录 sub_result
        步骤8：放电（下电）
        """
        ac      = instruments.get("AC_SOURCE")
        eload   = instruments.get("ELOAD")
        osc     = instruments.get("OSC")
        sniffer = instruments.get("SNIFFER")

        for cond in self.test_conditions:
            if len(cond) < 5:
                continue

            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            input_cond = f"{vin_cfg}V_{freq_cfg}Hz"
            cond_label = f"{proto_label}_Vout{vout_target}V_Iout{iout_target}A"
            spec_min   = round(vout_target * 0.90, 3)
            spec_max   = round(vout_target * 1.10, 3)
            # 功率分段：条件级 iout_eff（用于开机自检和扫描前的诱骗器/eload 初始化）
            # 扫描过程中每个 vac 点由 _step_voltage_sweep 内部按实时电压重算
            iout_eff = self._get_effective_iout(float(vin_cfg), float(vout_target), float(iout_target))

            # ---- 步骤1：开机自检（用该条件电压，最多3次清除重试）----
            startup_ok, _, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            if not startup_ok:
                info(f"[IVRT] 条件「{cond_label}」{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self.sub_results.append(self._make_result(
                    input_cond=input_cond,
                    proto_label=proto_label,
                    vout_target=round(vout_target, 3),
                    iout_target=round(iout_eff, 3),
                    voltage_range=f"{int(self.vin_lo_ui)}~{int(vin_cfg)}",
                    spec_min=spec_min,
                    spec_max=spec_max,
                    osc_vmax=0.0,
                    osc_vmin=0.0,
                    waveform=None,
                    sniffer_ok=False,
                    overall_pass=False,
                    fail_reason=fail_reason,
                    skipped=True,
                ))
                continue

            # ---- 步骤2：示波器 ROLL 模式 ----
            sweep_pts = self._get_voltage_sweep(float(vin_cfg), self.vin_lo_ui)
            sweep_dur = len(sweep_pts) * self.settle_time
            self._step_setup_osc(osc, vout_target, sweep_dur, vin_cfg=vin_cfg)

            # ---- 步骤3：诱骗器协议 ----
            sniffer_ok = self._step_setup_sniffer(sniffer, proto_label, vout_target, iout_eff)
            info(f"[IVRT] 诱骗器 {proto_label} {'成功' if sniffer_ok else '失败'}")

            # ---- 步骤4：电子负载 CC 模式上电（功率分段后电流）----
            self._step_setup_eload(eload, iout_eff)
            info(f"[IVRT] 电子负载 ON | Iout={iout_eff:.3f}A")

            # ---- 步骤5：电压往返扫描（vin_cfg→vin_lo→vin_cfg，功率随电压段切换）----
            # 扫描方向：条件最高电压（vin_cfg）→ 输入电压下限（vin_lo）→ 条件最高电压（vin_cfg）
            self._step_voltage_sweep(osc, ac, eload, sweep_pts, iout_target, vout_target)

            # ---- 步骤6：示波器 STOP 冻结波形，测量 Vmax/Vmin ----
            osc_vmax, osc_vmin, wave_path = self._step_capture_and_measure(
                osc, self.osc_output_ch, input_cond, proto_label, vout_target, iout_target)
            info(f"[IVRT] 示波器测量 | Vmax={osc_vmax:.3f}V Vmin={osc_vmin:.3f}V")

            # ---- 步骤7：汇总判定 ----
            osc_oos = (osc_vmax > spec_max or osc_vmin < spec_min)
            overall_pass = not osc_oos and sniffer_ok
            fail_reason = self._build_fail_reason(osc_oos, sniffer_ok)

            self.sub_results.append(self._make_result(
                input_cond=input_cond,
                proto_label=proto_label,
                vout_target=round(vout_target, 3),
                iout_target=round(iout_eff, 3),
                voltage_range=f"{int(self.vin_lo_ui)}~{int(vin_cfg)}",
                spec_min=spec_min,
                spec_max=spec_max,
                osc_vmax=round(osc_vmax, 3),
                osc_vmin=round(osc_vmin, 3),
                waveform=wave_path,
                sniffer_ok=sniffer_ok,
                overall_pass=overall_pass,
                fail_reason=fail_reason,
                skipped=False,
            ))

            # ---- 步骤8：放电（下电）----
            self._step_discharge(ac, eload, current=1.0, duration=1.0)

    # ---------- 步骤方法 ----------

    def _step_setup_osc(self, osc, vout: float, sweep_duration_s: float, vin_cfg: float = None):
        """
        步骤2：配置示波器 ROLL 模式。

        - 输入通道：测 AC 输入电压（正弦波，offset=0），用 auto_config_channel 自动量程
        - 输出通道：测 DUT 输出电压，用 auto_config_channel 自动量程
        - 带宽限制：输入通道限 25MHz（滤 DUT 开关噪声，不影响慢变扫描信号）
        - 时基 = sweep_duration / 10（配合扫描时间常数）
        - ROLL 模式：示波器持续刷新，等待扫描期间持续采集

        Args:
            vin_cfg: 本次扫描的最高条件电压（V），用于计算输入通道量程峰值
        """
        if osc is None:
            warning("[IVRT] 示波器未连接，跳过")
            return

        # 输入通道测 AC 输入电压，v_peak = vin_cfg × √2 × 2（扫描时最高电压，确保不削顶）
        # vin_cfg 为 None 时退化为最保守估算（使用 UI 设定的最低电压）
        if vin_cfg is None:
            vin_cfg = self.vin_lo_ui
        vin_peak = vin_cfg * 1.414 * 2
        osc.auto_config_channel(channel=self.osc_input_ch, v_peak=vin_peak,
                              coupling="DC",
                              bandwidth_limit=True,
                              offset=0.0)   # 正弦波中心在 0V
        osc.set_channel_on(self.osc_input_ch)

        osc.auto_config_channel(channel=self.osc_output_ch, v_peak=vout,
                              coupling="DC",
                              bandwidth_limit=True)
        osc.set_channel_on(self.osc_output_ch)

        timebase = sweep_duration_s / 10.0
        osc.set_timebase_mode("ROLL")
        time.sleep(0.3)
        osc.set_timebase(timebase)
        time.sleep(0.5)
        info(f"[IVRT] 示波器 ROLL | 时基={timebase:.1f}s/div | Vin_peak≈{vin_peak:.1f}V")

    def _step_voltage_sweep(self, osc, ac, eload, sweep_points: list,
                             iout_target: float, vout_target: float):
        """
        步骤5：输入电压往返扫描。

        sweep_points 顺序：先缓降（v_high→v_low），再缓升（v_low→v_high）。
        每步根据当前电压判定频率（≥180V→50Hz，<180V→60Hz）。
        功率随电压段自动切换（≥180V 满载，<180V 降功率）。
        每步等待 settle_time 稳定。
        支持暂停/停止。
        """
        if osc is None:
            warning("[IVRT] 示波器未连接，跳过清屏")
        else:
            osc.clear_screen()
        time.sleep(0.5)
        info(f"[IVRT] 电压扫描 | {sweep_points[0]}V→{sweep_points[-1]}V | {len(sweep_points)}点")

        for idx, vac in enumerate(sweep_points):
            if self.is_stop_requested():
                info("[IVRT] 扫描停止（用户请求）")
                if ac:
                    ac.set_voltage(0)
                break
            while self.is_pause_requested() and not self.is_stop_requested():
                time.sleep(0.2)
            if self.is_stop_requested():
                break

            freq = self._get_freq(vac)

            # 功率分段：先切负载，再切电压（避免降压瞬间大功率触发保护）
            # iout_eff 必须按当前 vac 实时计算，不能用扫描前按条件电压算好的固定值
            iout_eff = self._get_effective_iout(vac, vout_target, iout_target)
            if eload:
                eload.set_load_current(float(iout_eff))

            if ac:
                ac.set_voltage_nowait(vac)
                ac.set_frequency_nowait(freq)

            eload_label = f"满载{iout_target}A" if vac >= 180.0 else f"降功率{iout_eff:.3f}A"
            if idx % 10 == 0 or idx == len(sweep_points) - 1:
                info(f"[IVRT] 扫描 {idx+1}/{len(sweep_points)} | Vac={vac}V/{int(freq)}Hz → {eload_label}")

            time.sleep(self.settle_time)

        info("[IVRT] 电压扫描完成")

    # ---------- 工具方法 ----------

    def _get_voltage_sweep(self, v_high: float, v_low: float) -> List[float]:
        """
        生成往返扫描序列（从高电压往低电压扫，再从低往高扫回来）。

        - 缓降：v_high → v_low，步进 VOLTAGE_STEP（5V）
        - 缓升：v_low → v_high，步进 VOLTAGE_STEP（5V）
        返回 [降序列, 升序列]，共约 2×(vin_range/5) 个点
        """
        fwd, bwd = [], []
        step = self.VOLTAGE_STEP
        # fwd：从 v_low 往 v_high 升（递增）
        v = float(v_low)
        while v <= float(v_high) + 0.001:
            fwd.append(round(v, 1))
            v += step
        # bwd：从 v_high 往 v_low 降（递减）
        v = float(v_high)
        while v >= float(v_low) - 0.001:
            bwd.append(round(v, 1))
            v -= step
        # 先降（bwd：v_high→v_low），再升（fwd：v_low→v_high）
        return bwd + fwd

    def _get_freq(self, vac: float) -> float:
        """Vac ≥ 180V → 50Hz，否则 60Hz。"""
        return 50.0 if vac >= self.FREQ_THRESHOLD else 60.0

    def _build_fail_reason(self, osc_oos: bool, sniffer_ok: bool) -> str:
        """汇总失败原因：诱骗器锁定失败 / Vmax/Vmin 超规格。"""
        reasons = []
        if not sniffer_ok:
            reasons.append("诱骗器锁定失败")
        if osc_oos:
            reasons.append("Vmax/Vmin 超规格")
        return "; ".join(reasons)

    def _make_result(self, *, input_cond: str,
                     proto_label: str, vout_target: float, iout_target: float,
                     voltage_range: str,
                     spec_min: float, spec_max: float,
                     osc_vmax: float, osc_vmin: float,
                     waveform: str,
                     sniffer_ok: bool, overall_pass: bool,
                     fail_reason: str, skipped: bool) -> dict:
        """
        组装单条测试结果（sub_result）。
        字段名即报告列名，直接对应 report_generator 的 COLS 定义。
        """
        return {
            "输入条件":       input_cond,
            "协议":           proto_label,
            "输出电压(V)":    vout_target,
            "输出电流(A)":    iout_target,
            "电压范围(V)":    voltage_range,
            "规格下限":       spec_min,
            "规格上限":       spec_max,
            "最大值":         osc_vmax,
            "最小值":         osc_vmin,
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
        """关闭仪器输出，清理示波器通道和测量项，恢复普通模式。"""
        self._step_discharge(
            instruments.get("AC_SOURCE"),
            instruments.get("ELOAD"),
            current=1.0,
            duration=1.0,
        )
        osc = instruments.get("OSC")
        if osc:
            try:
                for ch in range(1, 5):
                    osc.set_channel_off(ch)
                osc.clear_measurements()
                osc.set_timebase_mode("MAIN")
            except Exception:
                pass

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"]  = self.sub_results
        d["product_type"] = self.product_type
        passed = sum(1 for r in self.sub_results if r["overall_pass"])
        d["sweep_summary"] = {
            "conditions_tested":  len(self.sub_results),
            "passed_conditions": passed,
            "failed_conditions": len(self.sub_results) - passed,
        }
        return d
