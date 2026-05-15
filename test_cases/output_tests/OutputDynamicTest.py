# -*- coding: utf-8 -*-
"""
OutputDynamicTest - 输出动态测试
===============================

使用示波器测量 DUT 在动态负载变化时的输出电压最大/最小值，
判定是否在规格范围内。

测试流程：
  setup:
    - 合并 specs_v2 到 self.spec（大动态/小动态负载范围 %）
    - 缓存动态设置参数
    - 示波器初始化（DC 耦合 / 带宽限制 / VMAX/VMIN 测量）
  execute:
    1. 遍历测试条件（输入电压 × 频率 × 协议）
       1.1 开机自检
       1.2 功率分段降流计算
       1.3 自检失败则标记 SKIP，继续下一条件
       1.4 诱骗器协议配置
       1.5 大动态测试（遍历 dyn_large_settings 每条设置）
           - 示波器刻度/偏移/触发配置
           - 预热负载 → 进入 CC-Dynamic 动态模式
           - 等待稳定 → STOP → 读取 VMAX/VMIN → 保存波形
           - 判定规格上下限，记录结果
       1.6 小动态测试（遍历 dyn_small_settings，每条同上）
       1.7 放电下电
  verify: 所有动态场景均 PASS 才返回 True

报告字段（COLS 定义，序号/用例名称由 report_generator._flatten() 自动注入）：
  输入条件 / 协议 / 输出电压(V) / 输出电流(A) /
  动态场景 / 规格上限 / 规格下限 / 最大值 / 最小值 / 测试结论 / 测试波形 / 备注
"""

import time
import os
from ..base import TestCase
from typing import Dict, Any, List, Optional

sys_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys
sys.path.insert(0, sys_path)
from logger_config import info, warning


class OutputDynamicTest(TestCase):
    """
    输出动态测试。
    每个测试条件的每个动态场景输出一行 sub_result。
    """

    # 动态拉载稳定等待时间（s）
    STEP_WAIT_S = 5.0

    # 报告列定义（序号/用例名称由 report_generator._flatten() 自动注入）
    COLS = [
    # 注意：「测试结论」列不定义在 COLS 中，
    # 由 report_generator._flatten() 统一注入（prefix 列）。

        ("输入条件",   16),
        ("协议",       12),
        ("输出电压(V)", 13),
        ("输出电流(A)", 13),
        ("动态场景",    12),
        ("规格上限",    10),
        ("规格下限",    10),
        ("最大值",      10),
        ("最小值",      10),
        ("测试结论",       12),
        ("测试波形",    18),
        ("备注",       32),
    ]

    # ---------- __init__ ----------
    def __init__(self,
                 product_type: str = "charger",
                 test_conditions: List[dict] = None,
                 dyn_large_settings: List[list] = None,
                 dyn_small_settings: List[list] = None,
                 dyn_large_spec: dict = None,
                 dyn_small_spec: dict = None,
                 osc_dynamic_ch: int = 2,
                 osc_waveform_dir: str = ""):
        """
        Args:
            product_type:       产品类型，"charger" 或 "adapter"
            test_conditions:    测试条件列表，每项为 dict，
                               字段：vin / freq / proto / vout / iout
            dyn_large_settings: 大动态参数列表，每项为
                                 [UP(%), UP斜率(A/μs), DOWN(%),
                                  DOWN斜率(A/μs), 频率(Hz), 比例(%)]
            dyn_small_settings: 小动态参数列表，同上格式
            dyn_large_spec:    保留参数（兼容旧接口），规格现由 specs_v2 注入
            dyn_small_spec:    同上
            osc_dynamic_ch:    示波器动态波形通道编号（默认 2）
            osc_waveform_dir:  波形保存目录
        """
        super().__init__(
            name="OutputDynamicTest",
            instruments=["AC_SOURCE", "ELOAD", "OSC", "SNIFFER", "POWER_METER"],
            params={
                "osc_dynamic_ch":     osc_dynamic_ch,
                "osc_waveform_dir":  osc_waveform_dir,
                "product_type":       product_type,
                "test_conditions":    test_conditions,
                "dyn_large_settings": dyn_large_settings or [],
                "dyn_small_settings": dyn_small_settings or [],
            },
        )
        self.sub_results: List[dict] = []

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """通用仪器初始化 + 参数缓存。"""
        self.sub_results = []
        super().setup(instruments)

        # test_conditions：从 engine 注入的 params 读取（不在 __init__ 中赋值，避免遮蔽基类字段）
        self.test_conditions = getattr(self, "test_conditions", []) or self.params.get("test_conditions", [])

        # specs_v2 中的 UI 规格（大动态/小动态负载范围 %）已在 base.setup() 合并到 self.spec
        # 格式：{"大动态负载范围_pct_hi": float, "大动态负载范围_pct_lo": float, ...}
        self.large_hi = self.spec.get("大动态负载范围_pct_hi", 10.0)
        self.large_lo = self.spec.get("大动态负载范围_pct_lo", 10.0)
        self.small_hi = self.spec.get("小动态负载范围_pct_hi", 5.0)
        self.small_lo = self.spec.get("小动态负载范围_pct_lo", 5.0)

        self.osc_dynamic_ch = int(self.params.get("osc_dynamic_ch", 2))
        self.dyn_large_settings = self.params.get("dyn_large_settings", [])
        self.dyn_small_settings = self.params.get("dyn_small_settings", [])

        # 示波器初始化（不上电，仅配置通道和测量项）
        osc = instruments.get("OSC")
        if osc is None:
            warning("[OutputDynamic] 示波器未连接")
            return

        dyn_ch = self.osc_dynamic_ch
        osc.set_channel_on(dyn_ch)
        osc.set_channel_coupling(dyn_ch, "DC")
        osc.set_bandwidth_limit(dyn_ch, True)
        osc.add_measurement(dyn_ch, "VMAX")
        osc.add_measurement(dyn_ch, "VMIN")

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """执行输出动态测试。"""
        ac      = instruments.get("AC_SOURCE")
        eload   = instruments.get("ELOAD")
        osc     = instruments.get("OSC")
        sniffer = instruments.get("SNIFFER")

        conditions = self.test_conditions or self.params.get("test_conditions") or []
        if not conditions:
            warning("[OutputDynamic] 无测试条件，跳过执行")
            return

        ch = self.osc_dynamic_ch

        for cond_idx, cond in enumerate(conditions):
            # 解析测试条件 dict
            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = \
                cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            input_cond = f"{int(vin_cfg)}V_{int(freq_cfg)}Hz"
            cond_label = f"{proto_label}/{vout_target}V/{iout_target}A"

            # 功率分段降流
            iout_eff = self._get_effective_iout(float(vin_cfg), float(vout_target), float(iout_target))
            if iout_eff != iout_target:
                info(f"[OutputDynamic] 功率分段降流：Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # 开机自检
            startup_ok, _, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            if not startup_ok:
                info(f"[OutputDynamic] 条件「{cond_label}」开机自检失败：{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                # 自检失败：该条件下的所有大小动态场景均标记 SKIP
                for scenario, settings in [("大动态", self.dyn_large_settings),
                                          ("小动态", self.dyn_small_settings)]:
                    for seq_idx in range(len(settings)):
                        self.sub_results.append(self._make_result(
                            input_cond=input_cond,
                            proto_label=proto_label,
                            vout_target=round(vout_target, 3),
                            iout_eff=round(iout_eff, 3),
                            scenario=scenario,
                            scenario_index=seq_idx + 1,
                            spec_hi=0.0,
                            spec_lo=0.0,
                            v_max=0.0,
                            v_min=0.0,
                            wave_path="",
                            overall_pass=False,
                            fail_reason=f"开机自检失败：{fail_reason}",
                            skipped=True,
                        ))
                continue

            # 诱骗器协议配置
            sniffer_ok = self._step_setup_sniffer(sniffer, proto_label, vout_target, iout_eff)
            time.sleep(2.0)
            if not sniffer_ok:
                warning(f"[OutputDynamic] 条件「{cond_label}」诱骗器设置失败，继续执行")

            # 取 setup() 中缓存的 UI 规格（大动态/小动态负载范围 %）
            large_hi = self.large_hi
            large_lo = self.large_lo
            small_hi = self.small_hi
            small_lo = self.small_lo

            # 大动态测试
            info(f"[OutputDynamic] 开始大动态测试，共 {len(self.dyn_large_settings)} 条设置")
            for seq_idx, dyn_row in enumerate(self.dyn_large_settings):
                self._run_single_dynamic_test(
                    ac, eload, osc, ch,
                    input_cond, proto_label,
                    vout_target, iout_eff,
                    dyn_row,
                    scenario="大动态",
                    scenario_index=seq_idx + 1,
                    large_hi=large_hi, large_lo=large_lo,
                    small_hi=0.0, small_lo=0.0,
                )

            # 小动态测试
            info(f"[OutputDynamic] 开始小动态测试，共 {len(self.dyn_small_settings)} 条设置")
            for seq_idx, dyn_row in enumerate(self.dyn_small_settings):
                info(f"[OutputDynamic] 小动态 {seq_idx+1}: {dyn_row}")
                self._run_single_dynamic_test(
                    ac, eload, osc, ch,
                    input_cond, proto_label,
                    vout_target, iout_eff,
                    dyn_row,
                    scenario="小动态",
                    scenario_index=seq_idx + 1,
                    large_hi=0.0, large_lo=0.0,
                    small_hi=small_hi, small_lo=small_lo,
                )

            self._step_discharge(ac, eload)

    # ---------- _run_single_dynamic_test ----------
    def _run_single_dynamic_test(self, ac, eload, osc, ch,
                                 input_cond, proto_label,
                                 vout_target, iout_eff,
                                 dyn_row: list,
                                 scenario: str,
                                 scenario_index: int,
                                 large_hi: float, large_lo: float,
                                 small_hi: float, small_lo: float):
        """
        执行单条动态测试场景。

        Args:
            dyn_row: [UP(%), UP斜率(A/μs), DOWN(%),
                      DOWN斜率(A/μs), 频率(Hz), 比例(%)]
            large_hi/lo: 大动态负载范围 %（来自 UI specs_v2）
            small_hi/lo: 小动态负载范围 %（来自 UI specs_v2）
        """
        info(f"[_run_single_dynamic_test] {scenario}{scenario_index} | dyn_row={dyn_row}")
        if len(dyn_row) < 6:
            warning(f"[OutputDynamic] 动态参数不足6个，跳过「{scenario}{scenario_index}」")
            return

        # 解析动态参数行
        up_pct, up_slope, down_pct, down_slope, freq_hz, ratio_pct = dyn_row
        try:
            up_pct     = float(up_pct)
            up_slope   = float(up_slope) if up_slope else 0.0
            down_pct   = float(down_pct)
            down_slope = float(down_slope) if down_slope else 0.0
            freq_hz    = float(freq_hz) if freq_hz else 1.0
            ratio_pct  = float(ratio_pct) if ratio_pct else 50.0
        except (ValueError, TypeError):
            warning(f"[OutputDynamic] 动态参数解析失败，跳过「{scenario}{scenario_index}」")
            return

        # 计算动态电流电平、 dwell 时间、斜率
        i_rated = float(iout_eff)
        i_high  = i_rated * up_pct / 100.0
        i_low   = i_rated * down_pct / 100.0
        slew_rate = up_slope if up_slope > 0 else None
        high_dwell = ratio_pct / 100.0 / freq_hz
        low_dwell  = (100.0 - ratio_pct) / 100.0 / freq_hz

        # 计算电压规格上下限（% → V）
        vout_v = float(vout_target)
        if large_hi > 0:
            hi_pct = large_hi
            lo_pct = large_lo
        else:
            hi_pct = small_hi
            lo_pct = small_lo
        spec_hi = vout_v * (1.0 + hi_pct / 100.0)
        spec_lo = vout_v * (1.0 - abs(lo_pct) / 100.0)
        v_peak_for_scale = vout_v * abs(hi_pct) / 100.0

        # 示波器配置（刻度、触发）
        if osc and vout_target:
            info(f"[OutputDynamic] osc_auto: ch={ch}, v_peak={v_peak_for_scale}, vout={vout_v}")
            osc.auto_config_channel(ch, v_peak=v_peak_for_scale * 2, coupling="DC",
                                   bandwidth_limit=True, grid_divisions=4.0,
                                   offset=vout_target)
            period = 1.0 / max(freq_hz, 0.001)
            time_per_div = period * 10.0 / 8.0
            osc.set_timebase(time_per_div)
            elapsed = 0.0
            while elapsed < 1.0:
                if self.is_stop_requested():
                    break
                while self.is_pause_requested() and not self.is_stop_requested():
                    time.sleep(0.2)
                time.sleep(0.2)
                elapsed += 0.2
            osc.set_trigger_mode("AUTO")
            osc.set_trigger_source(f"CHAN{ch}")
            osc.set_trigger_level(vout_v)
            osc.set_trigger_slope("BOTH")
            osc.run()   # 启动示波器采集

        # 电子负载：预热 → 进入动态模式
        if eload:
            eload.set_mode_cc(i_low)
            eload.input_on()
            elapsed = 0.0
            while elapsed < 1.0:
                if self.is_stop_requested():
                    break
                while self.is_pause_requested() and not self.is_stop_requested():
                    time.sleep(0.2)
                time.sleep(0.2)
                elapsed += 0.2

            eload.set_dynamic_mode(
                i_high=i_high,
                i_low=i_low,
                frequency=freq_hz,
                slew_rate_a=slew_rate,
                slew_rate_b=slew_rate,
                high_dwell=high_dwell,
                low_dwell=low_dwell,
            )
            eload.run_dynamic()

        elapsed = 0.0
        while elapsed < self.STEP_WAIT_S:
            if self.is_stop_requested():
                break
            while self.is_pause_requested() and not self.is_stop_requested():
                time.sleep(0.2)
            time.sleep(0.2)
            elapsed += 0.2

        # 测量：冻结波形 → 读 VMAX/VMIN → 保存 → 恢复采集
        v_max = 0.0
        v_min = 0.0
        wave_path = ""

        if osc:
            osc.stop()
            time.sleep(0.3)
            v_max_raw = osc.get_measurement(f"CHAN{ch}", "VMAX")
            v_min_raw = osc.get_measurement(f"CHAN{ch}", "VMIN")
            v_max = float(v_max_raw) if v_max_raw is not None else 0.0
            v_min = float(v_min_raw) if v_min_raw is not None else 0.0
            info(f"[OutputDynamic] {scenario}{scenario_index} | VMAX={v_max:.3f}V VMIN={v_min:.3f}V")
            wave_path = self._save_waveform(osc, input_cond, proto_label,
                                            vout_target, iout_eff,
                                            scenario, scenario_index)
            osc.run()   # 恢复示波器采集

        # 判定：VMAX 和 VMIN 均在 [spec_lo, spec_hi] 区间内才 PASS
        pass_flag = (spec_lo <= v_min <= spec_hi) and (spec_lo <= v_max <= spec_hi)
        reasons = []
        if v_max > spec_hi:
            reasons.append(f"VMAX={v_max:.3f}V > 上限={spec_hi:.3f}V")
        if v_min < spec_lo:
            reasons.append(f"VMIN={v_min:.3f}V < 下限={spec_lo:.3f}V")
        fail_reason = "; ".join(reasons) if reasons else ""

        self.sub_results.append(self._make_result(
            input_cond=input_cond,
            proto_label=proto_label,
            vout_target=round(vout_target, 3),
            iout_eff=round(iout_eff, 3),
            scenario=f"{scenario}{scenario_index}",
            scenario_index=scenario_index,
            spec_hi=spec_hi,
            spec_lo=spec_lo,
            v_max=v_max,
            v_min=v_min,
            wave_path=wave_path,
            overall_pass=pass_flag,
            fail_reason=fail_reason,
            skipped=False,
        ))

    # ---------- _make_result ----------
    def _make_result(self, *, input_cond: str = "",
                     proto_label: str = "", vout_target: float = 0.0, iout_eff: float = 0.0,
                     scenario: str = "", scenario_index: int = None,
                     spec_hi: float = 0.0, spec_lo: float = 0.0,
                     v_max: float = 0.0, v_min: float = 0.0,
                     wave_path: str = "",
                     overall_pass: bool = False, fail_reason: str = "",
                     skipped: bool = False) -> dict:
        """
        组装单条 sub_result，字段名与 COLS 列头一一对应（序号/用例名称由
        report_generator._flatten() 注入，此处不重复）。
        """
        return {
            "输入条件":     input_cond,
            "协议":         proto_label,
            "输出电压(V)":  vout_target,
            "输出电流(A)":  iout_eff,
            "动态场景":     scenario,
            "规格上限":     spec_hi,
            "规格下限":     spec_lo,
            "最大值":       round(v_max, 4),
            "最小值":       round(v_min, 4),
            "测试波形":     wave_path,
            "测试结论":     "SKIP" if skipped else ("PASS" if overall_pass else "FAIL"),
            "备注":         fail_reason,
            # 内部字段（供 verify() 判定使用，不写入报告）
            "overall_pass": overall_pass,
            "skipped":     skipped,
        }

    # ---------- _save_waveform ----------
    def _save_waveform(self, osc, input_cond: str,
                       proto_label: str, vout: float, iout: float,
                       scenario: str, scenario_index: int) -> Optional[str]:
        """
        保存示波器波形截图。

        文件名格式：{用例名}_{输入条件}_{协议}{动态场景编号}.png
        必须与 report_generator._wf_discovery() 的 pattern 保持一致：
          pattern = f"{case_name_en}_{input_cond}_{proto_label}{label_suffix}.png"
        保存路径：self._get_waveform_dir()（由 base.py 提供，默认 results/测试波形/）
        """
        if osc is None:
            return None
        base_dir = self._get_waveform_dir()
        # 与 report_generator._wf_discovery() pattern 保持一致
        label_suffix = f"_{scenario}{scenario_index}" if scenario else ""
        fname = f"{self.name}_{input_cond}_{proto_label}{label_suffix}.png"
        fpath = os.path.join(base_dir, fname)
        try:
            return osc.save_screenshot(fpath)
        except Exception:
            return None

    # ---------- verify ----------
    def verify(self) -> bool:
        """所有 sub_result 均 PASS 才返回 True。"""
        return bool(self.sub_results) and all(r["overall_pass"] for r in self.sub_results)

    # ---------- teardown ----------
    def teardown(self, instruments: Dict[str, Any]):
        """放电下电，清理示波器通道和测量项，恢复普通模式。"""
        self._step_discharge(
            instruments.get("AC_SOURCE"),
            instruments.get("ELOAD"),
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

    # ---------- to_dict ----------
    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        return d
