# -*- coding: utf-8 -*-
"""
RippleNoiseTest - 输出纹波测试
================================

使用示波器测量 DUT 输出纹波峰峰值,判断是否在规格内。

测试步骤:
  setup:示波器初始化(AC 耦合 / 带宽限制关 / 刻度 = 纹波规格/3 / 偏移0 / 时基20ms)
  execute:
    1. 开机自检
    2. 诱骗器协议设置
    3. 依次测试 0% / 50% / 100% 三个负载点
       - 每设置一个负载点,等待 2s 稳定 + 清屏后等 3s
       - 示波器清屏,等 1s,停止,读取纹波测量值
       - 保存波形
    4. 依据判定逻辑输出每个负载点的测试结论
    5. AC 源 OFF,电子负载短路(完全下电)

输出字段(COLS):
  序号 / 用例名称 / 输入条件 / 协议 / 输出电压(V) / 输出电流(A) /
  负载点 / 纹波要求 / 纹波实测值(mV) / 测试结论 / 测试波形 / 备注
"""

import time
import os
from ..base import TestCase
from typing import Dict, Any, List, Optional

sys_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys
sys.path.insert(0, sys_path)
from logger_config import info, warning


class OutputRippleNoiseTest(TestCase):
    """
    输出纹波测试。
    每个测试条件的每个负载点(0% / 50% / 100%)输出一行报告。
    """

    # 示波器时基(20ms/div,10 div = 200ms 窗口)
    TIME_BASE_S = 0.020

    # 负载点列表(%)
    LOAD_POINTS = [0, 50, 100]

    # 报告列定义
    COLS = [
                ("输入条件",          16),
                ("协议",              12),
                ("输出电压(V)",       13),
                ("输出电流(A)",       13),
                ("负载点",             9),
                ("纹波要求",          12),
                ("纹波实测值(mV)",    16),
                ("测试结论",           11),
                ("测试波形",           18),
                ("备注",              32),
    ]

    # ---------- __init__ ----------
    def __init__(self,
                 ripple_max_mv: float = 100.0,
                 product_type: str = "charger",
                 test_conditions: List[dict] = None,
                 osc_output_ch: int = 2,
                 osc_waveform_dir: str = ""):
        """
        Args:
            ripple_max_mv:   纹波规格上限(mVpp)
            product_type:    产品类型,"charger" 或 "adapter"
            test_conditions: 测试条件列表,每项为
                            (vin, freq, proto_label, vout_target, iout_target) 五元组
            osc_output_ch:  示波器输出通道编号(默认2)
            osc_waveform_dir: 波形保存目录
        """
        self.product_type = product_type
        self.test_conditions = test_conditions or []
        self.osc_waveform_dir = osc_waveform_dir
        self.sub_results: List[dict] = []

        super().__init__(
            name="OutputRippleNoiseTest",
            instruments=["AC_SOURCE", "ELOAD", "OSC", "SNIFFER", "POWER_METER"],
            params={
                "osc_output_ch":    osc_output_ch,
                "osc_waveform_dir": osc_waveform_dir,
                "product_type":     product_type,
                "test_conditions":  test_conditions,
                "timebase_s":       self.TIME_BASE_S,
            },
            spec={
                "纹波要求_mV_hi": ripple_max_mv,
            }
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """初始化仪器状态(仅配置,不上电)。"""
        self.sub_results = []
        super().setup(instruments)

        osc = instruments.get("OSC")
        if osc is None:
            warning("[Ripple] 示波器未连接")
            return

        ch = int(self.params.get("osc_output_ch", 2))

        # 时基(全局固定)
        osc.set_timebase(self.TIME_BASE_S)

        # 通道配置:AC 耦合,带宽限制开
        osc.set_channel_on(ch)
        osc.set_channel_coupling(ch, "AC")
        osc.set_bandwidth_limit(ch, "ON")
        scale_v = (self.spec.get("纹波要求_mV_hi", 100.0) / 1000.0) / 5.0   # mV → V,再除以 5(5 div 量程)
        osc.set_voltage_scale(ch, max(scale_v, 0.01))
        osc.set_channel_offset(ch, 0.0)

        # 触发配置:AUTO 模式,触发源为输出通道,上升下降沿双沿触发,电平 0V
        osc.set_trigger_mode("AUTO")
        osc.set_trigger_source(f"CHAN{ch}")
        osc.set_trigger_level(0.0)
        osc.set_trigger_slope("BOTH")

        # 配置 VPP 测量(峰峰值)
        osc.add_measurement(ch, "VPP")

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """执行输出纹波测试。"""
        ac      = instruments.get("AC_SOURCE")
        eload   = instruments.get("ELOAD")
        osc     = instruments.get("OSC")
        sniffer = instruments.get("SNIFFER")

        conditions = self.test_conditions or self.params.get("test_conditions") or []
        if not conditions:
            warning("[Ripple] 无测试条件，跳过执行")
            return

        ch = int(self.params.get("osc_output_ch", 2))
        ripple_spec = self.spec.get("纹波要求_mV_hi", 100.0)

        for cond_idx, cond in enumerate(conditions):
            if len(cond) < 5:
                continue

            # 解析 test_condition（5 元组）
            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = \
                cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            input_cond = f"{int(vin_cfg)}V_{int(freq_cfg)}Hz"

            # 更新当前 params（供 _save_waveform 命名使用）
            self.params["vin"]          = float(vin_cfg) if vin_cfg else 220.0
            self.params["freq"]        = float(freq_cfg) if freq_cfg else 50.0
            self.params["vout_target"] = float(vout_target) if vout_target else 5.0
            self.params["iout_target"] = float(iout_target) if iout_target else 3.0
            self.params["proto_label"] = str(proto_label) if proto_label else "PD-PDO1"

            cond_label = f"{proto_label}/{vout_target}V/{iout_target}A"

            # 提前计算功率分段后的有效电流
            iout_eff = self._get_effective_iout(float(vin_cfg), float(vout_target), float(iout_target))
            if iout_eff != iout_target:
                info(f"[Ripple] 功率分段降流：Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # ---- 步骤1：开机自检（用测试条件电压，最多3次清除重试）----
            startup_ok, measured_vout, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            self.measurements[f"startup_ok_c{cond_idx+1}"] = startup_ok
            if not startup_ok:
                info(f"[Ripple] 条件「{cond_label}」开机自检失败：{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                for pct in self.LOAD_POINTS:
                    self.sub_results.append(self._make_result(
                        input_cond=input_cond,
                        proto_label=proto_label,
                        vout_target=vout_target,
                        iout_target=iout_eff,
                        load_pct=pct,
                        ripple_spec=ripple_spec,
                        ripple_mv=0.0,
                        wave_path="",
                        overall_pass=False,
                        fail_reason=f"开机自检失败：{fail_reason}",
                        skipped=True,
                    ))
                continue

            # ---- 步骤2：自检通过后，启动示波器RUN ----
            if osc:
                osc.run()

            # ---- 步骤3：诱骗器协议设置 ----
            sniffer_ok = self._step_setup_sniffer(sniffer, proto_label, vout_target, iout_eff)
            time.sleep(2.0)
            if not sniffer_ok:
                warning(f"[Ripple] 条件「{cond_label}」诱骗器设置失败，继续执行")

            # ---- 步骤4：依次测试三个负载点 ----
            for pct in self.LOAD_POINTS:
                i_load = iout_eff * pct / 100.0

                # 设置电子负载
                if eload:
                    eload.set_mode_cc(i_load)
                    eload.input_on()

                # 等待 2s 电源稳定
                time.sleep(2.0)

                # 清屏，等 3s
                if osc:
                    osc.clear_screen()
                time.sleep(3.0)

                # 停止示波器并读取纹波
                ripple_mv = 0.0
                wave_path = ""
                if osc:
                    osc.stop()
                    time.sleep(0.3)
                    ripple_v = osc.get_measurement(f"CHAN{ch}", "VPP")
                    info(f"[Ripple] 负载 {pct}% | VPP={ripple_v*1000:.1f}mVpp")
                    if ripple_v is None:
                        ripple_v = 0.0
                    ripple_mv = ripple_v * 1000.0
                    wave_path = self._save_waveform(
                        osc, input_cond, proto_label,
                        vout_target, iout_eff, pct,
                        ripple_mv=ripple_mv,
                        ripple_spec=ripple_spec
                    )
                    # 重新运行示波器
                    osc.run()

                # 判定
                pass_flag = ripple_mv <= ripple_spec
                reason = "" if pass_flag else f"纹波{ripple_mv:.1f}mV > 规格{ripple_spec}mV"

                self.sub_results.append(self._make_result(
                    input_cond=input_cond,
                    proto_label=proto_label,
                    vout_target=vout_target,
                    iout_target=iout_eff,
                    load_pct=pct,
                    ripple_spec=ripple_spec,
                    ripple_mv=ripple_mv,
                    wave_path=wave_path,
                    overall_pass=pass_flag,
                    fail_reason=reason,
                    skipped=False,
                ))

            # ---- 步骤5：放电（DUT 完全下电）----
            self._step_discharge(ac, eload)

    # ---------- _make_result ----------
    def _make_result(self, *, input_cond: str,
                     proto_label: str, vout_target: float, iout_target: float,
                     load_pct: int, ripple_spec: float, ripple_mv: float,
                     wave_path: str,
                     overall_pass: bool, fail_reason: str,
                     skipped: bool) -> dict:
        """
        组装单条测试结果(sub_result)。

        字段名与 COLS 列头一致,供报告写入器直接查找。
        """
        return {
            "输入条件":          input_cond,
            "协议":              proto_label,
            "输出电压(V)":       vout_target,
            "输出电流(A)":       iout_target,
            "负载点":           f"{load_pct}%",
            "纹波要求":          ripple_spec,
            "纹波实测值(mV)":    round(ripple_mv, 2),
            "测试波形":          wave_path,
            "测试结论":          "SKIP" if skipped else ("PASS" if overall_pass else "FAIL"),
            "备注":              fail_reason,
            # 内部字段(供结论逻辑使用,不写入报告单元格)
            "overall_pass":     overall_pass,
            "skipped":          skipped,
        }

    # ---------- _save_waveform ----------
    def _save_waveform(self, osc, input_cond: str,
                       proto_label: str, vout: float, iout: float,
                       load_pct: int = 0,
                       ripple_mv: float = 0.0,
                       ripple_spec: float = 0.0) -> Optional[str]:
        """
        重写波形保存方法,文件名加入负载点信息。
        截图保存后用 PIL 在图上叠加测量值标注。
        格式:{用例名}_{输入条件}_{协议}_Vout{电压}V_Iout{电流}A_{负载点}pct.png
        """
        if osc is None:
            return None
        base_dir = self._get_waveform_dir()
        fname = (f"{self.name}_{input_cond}_{proto_label}"
                 f"_Vout{vout}V_Iout{iout}A_{load_pct}pct.png")
        fpath = os.path.join(base_dir, fname)
        try:
            return osc.save_screenshot(fpath)
        except Exception:
            return None

    # ---------- verify ----------
    def verify(self) -> bool:
        """所有负载点 overall_pass 为 True 才 PASS。"""
        return bool(self.sub_results) and all(r["overall_pass"] for r in self.sub_results)

    # ---------- teardown ----------
    def teardown(self, instruments: Dict[str, Any]):
        """恢复示波器普通模式（下电由 execute 末尾的 _step_discharge 处理）。"""
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
