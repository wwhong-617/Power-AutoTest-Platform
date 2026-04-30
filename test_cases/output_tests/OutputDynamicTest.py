# -*- coding: utf-8 -*-
"""
DynamicOutputTest - 输出动态测试
================================

使用示波器测量 DUT 在动态负载变化时的输出电压最大/最小值，
判定是否在规格范围内。

测试步骤：
  setup：示波器初始化（DC 耦合 / 带宽限制使能）
  execute：
    1. 开机自检
    2. AC 源切换至测试条件输入电压
    3. 诱骗器协议
    4. 大动态测试场景（遍历 UI 大动态测试设置列表）
       - 配置示波器刻度/偏移/触发
       - 设置电子负载动态模式（CC-Dynamic）
       - 等 5s 稳定后 STOP → 读取 VMAX/VMIN → 保存波形
       - 判定并记录结果
    5. 小动态测试场景（遍历 UI 小动态测试设置列表）
       - 同上
    6. 放电下电

输出字段（COLS）：
  序号 / 用例名称 / 输入条件 / 协议 / 输出电压(V) / 输出电流(A) /
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
    每个测试条件的每个动态场景输出一行报告。
    """

    # 每步稳定等待时间（s）
    STEP_WAIT_S = 5.0

    # 报告列定义
    COLS = [
                ("输入条件",          16),
                ("协议",              12),
                ("输出电压(V)",       13),
                ("输出电流(A)",       13),
                ("动态场景",           12),
                ("规格上限",          10),
                ("规格下限",          10),
                ("最大值",             10),
                ("最小值",            10),
                ("测试结论",           11),
                ("测试波形",           18),
                ("备注",              32),
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
            product_type:        产品类型，"charger" 或 "adapter"
            test_conditions:     测试条件列表，每项为
                                 (vin, freq, proto_label, vout_target, iout_target) 五元组
            dyn_large_settings:  大动态设置列表，每项为
                                 [UP(%), UP斜率(A/us), DOWN(%), DOWN斜率(A/us), 频率(Hz), 比例(%)]
            dyn_small_settings:  小动态设置列表，同上
            dyn_large_spec:      大动态规格，{"hi": float, "lo": float}（电压 mV）
            dyn_small_spec:      小动态规格，{"hi": float, "lo": float}（电压 mV）
            osc_dynamic_ch:       示波器动态电压波形通道编号（默认2）
            osc_waveform_dir:    波形保存目录
        """
        super().__init__(
            name="OutputDynamicTest",
            instruments=["AC_SOURCE", "ELOAD", "OSC", "SNIFFER", "POWER_METER"],
            params={
                "osc_dynamic_ch":    osc_dynamic_ch,
                "osc_waveform_dir":  osc_waveform_dir,
                "product_type":      product_type,
                "test_conditions":   test_conditions,
                "dyn_large_settings": dyn_large_settings or [],
                "dyn_small_settings": dyn_small_settings or [],
            },
            spec={
                "动态大功率_V_hi": 10.0,
                "动态大功率_V_lo": 10.0,
                "动态小功率_V_hi": 5.0,
                "动态小功率_V_lo": 5.0,
            },
        )
        self.product_type = product_type
        self.test_conditions = test_conditions or []
        self.sub_results: List[dict] = []

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """初始化仪器状态（仅配置，不上电）。"""
        self.sub_results = []
        super().setup(instruments)

        self.osc_dynamic_ch = int(self.params.get("osc_dynamic_ch", 2))
        self.dyn_large_settings = self.params.get("dyn_large_settings", [])
        self.dyn_small_settings = self.params.get("dyn_small_settings", [])

        osc = instruments.get("OSC")
        if osc is None:
            warning("[DynamicOutput] 示波器未连接")
            return

        dyn_ch = self.osc_dynamic_ch
        osc.set_channel_on(dyn_ch)
        osc.set_channel_coupling(dyn_ch, "DC")
        osc.set_bandwidth_limit(dyn_ch, "ON")
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
            warning("[DynamicOutput] 无测试条件，跳过执行")
            return

        ch = self.osc_dynamic_ch

        for cond_idx, cond in enumerate(conditions):
            if len(cond) < 5:
                continue

            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = \
                cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            input_cond = f"{int(vin_cfg)}V_{int(freq_cfg)}Hz"
            cond_label = f"{proto_label}/{vout_target}V/{iout_target}A"

            self.params["vin"]         = float(vin_cfg) if vin_cfg else 220.0
            self.params["freq"]        = float(freq_cfg) if freq_cfg else 50.0
            self.params["vout_target"] = float(vout_target) if vout_target else 5.0
            self.params["iout_target"] = float(iout_target) if iout_target else 3.0
            self.params["proto_label"]  = str(proto_label) if proto_label else "PD-PDO1"

            iout_eff = self._get_effective_iout(float(vin_cfg), float(vout_target), float(iout_target))
            if iout_eff != iout_target:
                info(f"[DynamicOutput] 功率分段降流：Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            startup_ok, measured_vout, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            self.measurements[f"startup_ok_c{cond_idx+1}"] = startup_ok
            if not startup_ok:
                info(f"[DynamicOutput] 条件「{cond_label}」开机自检失败：{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                for scenario, settings in [("大动态", self.dyn_large_settings),
                                           ("小动态", self.dyn_small_settings)]:
                    for seq_idx in range(len(settings)):
                        self.sub_results.append(self._make_result(
                            input_cond=input_cond,
                            proto_label=proto_label,
                            vout_target=vout_target,
                            iout_eff=iout_eff,
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

            if osc:
                osc.run()

            sniffer_ok = self._step_setup_sniffer(sniffer, proto_label, vout_target, iout_eff)
            time.sleep(2.0)
            if not sniffer_ok:
                warning(f"[DynamicOutput] 条件「{cond_label}」诱骗器设置失败，继续执行")

            large_hi = self.spec.get("动态大功率_V_hi", 10.0)
            large_lo = self.spec.get("动态大功率_V_lo", 10.0)
            small_hi = self.spec.get("动态小功率_V_hi", 5.0)
            small_lo = self.spec.get("动态小功率_V_lo", 5.0)

            info(f"[DynamicOutput] 开始大动态测试，共 {len(self.dyn_large_settings)} 条设置")
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

            info(f"[DynamicOutput] 开始小动态测试，共 {len(self.dyn_small_settings)} 条设置")
            for seq_idx, dyn_row in enumerate(self.dyn_small_settings):
                info(f"[DynamicOutput] 小动态 {seq_idx+1}: {dyn_row}")
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
        dyn_row: [UP(%), UP斜率(A/us), DOWN(%), DOWN斜率(A/us), 频率(Hz), 比例(%)]
        """
        info(f"[_run_single_dynamic_test] {scenario}{scenario_index} 开始 | dyn_row={dyn_row}")
        if len(dyn_row) < 6:
            warning(f"[DynamicOutput] 动态参数不足6个，跳过「{scenario}{scenario_index}」")
            return

        up_pct, up_slope, down_pct, down_slope, freq_hz, ratio_pct = dyn_row
        try:
            up_pct      = float(up_pct)
            up_slope    = float(up_slope) if up_slope else 0.0
            down_pct    = float(down_pct)
            down_slope  = float(down_slope) if down_slope else 0.0
            freq_hz     = float(freq_hz) if freq_hz else 1.0
            ratio_pct   = float(ratio_pct) if ratio_pct else 50.0
        except (ValueError, TypeError):
            warning(f"[DynamicOutput] 动态参数解析失败，跳过「{scenario}{scenario_index}」")
            return

        i_rated = float(iout_eff)
        i_high = i_rated * up_pct / 100.0
        i_low  = i_rated * down_pct / 100.0
        slew_rate = up_slope if up_slope > 0 else None
        high_dwell = ratio_pct / 100.0 / freq_hz
        low_dwell  = (100.0 - ratio_pct) / 100.0 / freq_hz

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

        if osc and vout_target:
            info(f"[DynamicOutput] osc_auto: ch={ch}, v_peak={v_peak_for_scale}, vout={vout_v}")
            osc.auto_config_channel(ch, v_peak=v_peak_for_scale * 2, coupling="DC", bandwidth_limit=True, grid_divisions=5.0, offset=vout_target - v_peak_for_scale * 0.5)
            period = 1.0 / max(freq_hz, 0.001)
            time_per_div = period * 10.0 / 8.0
            osc.set_timebase(time_per_div)
            time.sleep(1)
            osc.set_trigger_mode("AUTO")
            osc.set_trigger_source(f"CHAN{ch}")
            osc.set_trigger_level(vout_v)
            osc.set_trigger_slope("BOTH")
            osc.run()

        if eload:
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

        time.sleep(self.STEP_WAIT_S)

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
            info(f"[DynamicOutput] {scenario}{scenario_index} | VMAX={v_max:.3f}V VMIN={v_min:.3f}V")
            wave_path = self._save_waveform(
                osc, input_cond, proto_label,
                vout_target, iout_eff,
                scenario, scenario_index,
            )
            osc.run()

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
            vout_target=vout_target,
            iout_eff=iout_eff,
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
        组装单条测试结果（sub_result）。
        字段名与 COLS 列头一致，供报告写入器直接查找。
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
            # 内部字段
            "overall_pass": overall_pass,
            "skipped":     skipped,
        }

    # ---------- _save_waveform ----------
    def _save_waveform(self, osc, input_cond: str,
                       proto_label: str, vout: float, iout: float,
                       scenario: str, scenario_index: int) -> Optional[str]:
        """
        波形保存，文件名加入动态场景信息。
        格式：{用例名}-{输入条件}-{协议}-{输出电压}V-{输出电流}A-{动态场景}.png
        """
        if osc is None:
            return None
        base_dir = self._get_waveform_dir()
        fname = (f"{self.name}-{input_cond}-{proto_label}-"
                 f"{vout}V-{iout}A-{scenario}{scenario_index}.png")
        fpath = os.path.join(base_dir, fname)
        try:
            return osc.save_screenshot(fpath)
        except Exception:
            return None

    # ---------- verify ----------
    def verify(self) -> bool:
        """所有动态场景 PASS 才 PASS。"""
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
