# -*- coding: utf-8 -*-
"""
PowerOnOffTest - 开关机测试
===========================

测量DUT开机和关机时的输出电压过冲/下冲（overshoot/undershoot），判断是否在规格内。

test_conditions 格式（6 元组）：
  (vin, freq, proto_label, vout_target, iout_target, product_type)

波形文件名规则（与 base._save_waveform 一致）：
  {用例名}_{输入条件}_{协议}_Vout{电压}V_Iout{电流}A_{startup/shutdown}.png
  示例：PowerOnOffTest_Vin90V_Freq60Hz_PD-PDO1_Vout5V_Iout3A_startup.png
"""

import time
import os
import sys
from ..base import TestCase
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class OutputPowerOnOffTest(TestCase):
    """
  开关机过冲/下冲测试（每条 test_condition 独立执行）。

  测试步骤：
    1. 开机自检（基类 startup_self_check，测得实际开机电压）
    2. 用实测开机电压配置示波器（刻度/偏移/触发）
    3. 放电（确保冷启动）
    4. 武装示波器 → AC ON → 等待触发 → 读取开机波形
    5. 诱骗器协议 + 电子负载 CC 模式（额定 Iout）
    6. 等待 DUT 输出稳定
    7. 用 vout_target 重新配置示波器（关机参数）
    8. 武装示波器 → AC OFF → 等待触发 → 读取关机波形
    9. 放电（下电）+ 恢复示波器时基
  """

    # ---------- 常量 ----------
    TRIGGER_TIMEOUT = 5.0     # 示波器触发等待超时（秒）
    TRIGGER_WAIT_S  = 0.3     # 轮询触发状态间隔（秒），关机瞬态需细粒度
    TIME_BASE_S     = 0.005  # 示波器时基 5ms/div（10div=50ms总窗口）

    # ---------- 报告列定义 ----------
    # 顺序即 Excel 列顺序；序号由报告写入器填充
    # 与报告生成器对齐：序号-用例名称-输入条件-协议-输出电压(V)-输出电流(A)-规格上限-规格下限-过冲(%)-负冲(%)-测试波形-测试结论-备注
    COLS = [
                ("输入条件",          16),
                ("协议",              12),
                ("输出电压(V)",       13),
                ("输出电流(A)",       13),
                ("开关机场景",        12),
                ("规格上限",          11),
                ("规格下限",          11),
                ("过冲(%)",           12),
                ("负冲(%)",           12),
                ("测试波形",           18),
                ("测试结论",           11),
                ("备注",              28),
    ]

    # ---------- __init__ ----------
    def __init__(self,
                 overshoot_max_pct: float = 20.0,
                 product_type: str = "charger",
                 test_conditions: List[dict] = None,
                 osc_output_ch: int = 2,
                 osc_waveform_dir: str = ""):
        self.product_type     = product_type
        self.test_conditions = test_conditions or []
        self.osc_waveform_dir = osc_waveform_dir
        self.sub_results: List[dict] = []

        super().__init__(
            name="OutputPowerOnOffTest",
            instruments=["AC_SOURCE", "ELOAD", "OSC", "SNIFFER", "POWER_METER"],
            params={
                "osc_output_ch":    osc_output_ch,
                "osc_waveform_dir": osc_waveform_dir,
                "product_type":     product_type,
                "test_conditions":  test_conditions,
                "timebase_s":       self.TIME_BASE_S,
                "trigger_wait_s":   self.TRIGGER_WAIT_S,
            },
            spec={
                # 开关机过冲/下冲共用同一个规格上限
                "开关机过冲_pct_hi": overshoot_max_pct,
            }
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """
        初始化仪器状态（仅配置，不上电）。
        示波器公共配置（通道/时基/测量）在 setup 中一次性完成。
        """
        self.sub_results = []
        super().setup(instruments)

        # ---- 缓存 UI 参数 ----
        self.osc_output_ch = int(self.params.get("osc_output_ch", 2))

        osc = instruments.get("OSC")
        if osc is None:
            warning("[POOT] 示波器未连接，跳过公共配置")
            return

        # 时基（全局，每个条件通用）
        osc.set_timebase(self.TIME_BASE_S)

        # 通道开关 + 耦合 + 带宽（全局通用）
        osc.set_channel_on(self.osc_output_ch)
        osc.set_channel_coupling(self.osc_output_ch, "DC")
        osc.set_bandwidth_limit(self.osc_output_ch, "OFF")

        # 测量项（全局通用，每个条件都测过冲/下冲）
        osc.clear_measurements()
        osc.add_measurement(self.osc_output_ch, "OVER")
        osc.add_measurement(self.osc_output_ch, "POVER")

        info(f"[POOT] 示波器公共配置完成 | CH{self.osc_output_ch} 时基={self.TIME_BASE_S*1000:.1f}ms/div")

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        ac      = instruments.get("AC_SOURCE")
        eload   = instruments.get("ELOAD")
        osc     = instruments.get("OSC")
        sniffer = instruments.get("SNIFFER")

        conditions = self.test_conditions or self.params.get("test_conditions") or []
        if not conditions:
            warning("[POOT] 无测试条件，跳过执行")
            return

        spec_max = self.spec.get("开关机过冲_pct_hi", self.spec.get("overshoot_max_pct", 20.0))

        for cond_idx, cond in enumerate(conditions):
            if len(cond) < 5:
                continue

            # 解析 test_condition（6 元组）
            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = \
                cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            input_cond = f"{int(vin_cfg)}V_{int(freq_cfg)}Hz"

            # 更新当前 params（供 _save_waveform 命名使用）
            self.params["vin"]          = float(vin_cfg) if vin_cfg else 220.0
            self.params["freq"]         = float(freq_cfg) if freq_cfg else 50.0
            self.params["vout_target"] = float(vout_target) if vout_target else 5.0
            self.params["iout_target"] = float(iout_target) if iout_target else 3.0
            self.params["proto_label"]  = str(proto_label) if proto_label else "PD-PDO1"

            # 提前计算功率分段后的有效电流
            iout_eff = self._get_effective_iout(float(vin_cfg), float(vout_target), float(iout_target))
            if iout_eff != iout_target:
                info(f"[POOT] 功率分段降流：Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            cond_label = f"{proto_label}/{vout_target}V/{iout_target}A"

            # ---- 步骤1：开机自检（用测试条件电压，最多3次清除重试）----
            startup_ok, measured_vout, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            self.measurements[f"startup_ok_c{cond_idx+1}"] = startup_ok
            if not startup_ok:
                info(f"[POOT] 条件「{cond_label}」开机自检失败：{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                fail_msg = f"开机自检失败：{fail_reason}"
                # 开机行 + 关机行均标记为 SKIP
                self.sub_results.append(self._make_result(
                    input_cond=input_cond, proto_label=proto_label,
                    vout_target=vout_target, iout_eff=iout_eff,
                    spec_max=spec_max, spec_min=0.0,
                    scene="开机", ov_pct=0.0, ud_pct=0.0,
                    waveform="", overall_pass=False,
                    fail_reason=fail_msg, skipped=True,
                ))
                self.sub_results.append(self._make_result(
                    input_cond=input_cond, proto_label=proto_label,
                    vout_target=vout_target, iout_eff=iout_eff,
                    spec_max=spec_max, spec_min=0.0,
                    scene="关机", ov_pct=0.0, ud_pct=0.0,
                    waveform="", overall_pass=False,
                    fail_reason=fail_msg, skipped=True,
                ))
                continue

            # ---- 步骤2：用实测开机电压配置示波器（开机视图）----
            self._step_osc_prepare_startup(osc, measured_vout)

            # ---- 步骤3：自检后先 AC OFF，再放电（确保完全下电进入冷启动）----
            if ac:
                ac.output_off()
            self._step_discharge(ac, eload)

            # ---- 步骤4：武装示波器 → startup_self_check 上电（带重试）→ 等待触发 → 读取开机波形 ----
            if osc:
                osc.set_single_trigger()
                time.sleep(1)

            cold_startup_ok, _, _ = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )

            if not cold_startup_ok:
                # 冷启动自检失败，与步骤1自检失败同逻辑
                info("[POOT] 冷启动自检失败，跳过开关机波形采集")
                self._step_discharge(ac, eload)
                fail_msg = "冷启动自检失败"
                self.sub_results.append(self._make_result(
                    input_cond=input_cond, proto_label=proto_label,
                    vout_target=vout_target, iout_eff=iout_eff,
                    spec_max=spec_max, spec_min=0.0,
                    scene="开机", ov_pct=0.0, ud_pct=0.0,
                    waveform="", overall_pass=False,
                    fail_reason=fail_msg, skipped=True,
                ))
                self.sub_results.append(self._make_result(
                    input_cond=input_cond, proto_label=proto_label,
                    vout_target=vout_target, iout_eff=iout_eff,
                    spec_max=spec_max, spec_min=0.0,
                    scene="关机", ov_pct=0.0, ud_pct=0.0,
                    waveform="", overall_pass=False,
                    fail_reason=fail_msg, skipped=True,
                ))
                continue

            # ---- 正常流程：采集开机波形 ----
            if osc:
                info(f"[POOT] 开机等待触发 | timeout={self.TRIGGER_TIMEOUT}s")
                startup_triggered = self._osc_wait_trigger(osc, timeout_s=self.TRIGGER_TIMEOUT,
                                                          poll_interval=self.TRIGGER_WAIT_S)
                if not startup_triggered:
                    osc.stop()
                    self.measurements[f"c{cond_idx+1}_startup_triggered"] = False

            time.sleep(1.0)

            startup_ov = 0.0
            startup_ud = 0.0
            startup_wf = ""
            if osc:
                if startup_triggered:
                    osc.stop()
                    time.sleep(0.3)
                    startup_ov = osc.measure_overshoot_builtin(self.osc_output_ch)
                    startup_ud = osc.measure_undershoot_builtin(self.osc_output_ch)
                    startup_wf = osc.save_screenshot(self._get_waveform_path("startup"))
                    osc.run()
                else:
                    startup_ov = 999.0
                    startup_ud = 999.0
                    startup_wf = self._save_waveform(osc, "startup")

            # ---- 步骤5：诱骗器协议 + 电子负载 CC 模式（功率分段后电流）----
            self._step_setup_sniffer(sniffer, proto_label, vout_target, iout_target)
            self._step_setup_eload(eload, iout_eff)
            time.sleep(1.5)

            # ---- 步骤6：用 vout_target 重新配置示波器（关机视图）----
            self._step_osc_prepare_shutdown(osc, vout_target)

            # ---- 步骤7：示波器 ARM → AC OFF → 等待触发 → 读取关机波形 ----
            if osc:
                osc.set_single_trigger()
                time.sleep(2)

            if ac:
                ac.output_off()

            shutdown_triggered = False
            if osc:
                info(f"[POOT] 关机等待触发 | timeout={self.TRIGGER_TIMEOUT}s")
                shutdown_triggered = self._osc_wait_trigger(osc, timeout_s=self.TRIGGER_TIMEOUT,
                                                           poll_interval=self.TRIGGER_WAIT_S)
                if not shutdown_triggered:
                    osc.stop()
                    self.measurements[f"c{cond_idx+1}_shutdown_triggered"] = False

            time.sleep(1.0)

            shutdown_ov = 0.0
            shutdown_ud = 0.0
            shutdown_wf = ""
            if osc:
                if shutdown_triggered:
                    osc.stop()
                    time.sleep(0.3)
                    shutdown_ov = osc.measure_overshoot_builtin(self.osc_output_ch)
                    shutdown_ud = osc.measure_undershoot_builtin(self.osc_output_ch)
                    shutdown_wf = osc.save_screenshot(self._get_waveform_path("shutdown"))
                    osc.run()
                else:
                    osc.stop()
                    shutdown_ov = 999.0
                    shutdown_ud = 999.0
            else:
                shutdown_ov = 999.0
                shutdown_ud = 999.0

            # ---- 步骤8：汇总判定（开机行和关机行分别判定）----
            pass_startup = (startup_ov <= spec_max and startup_ud <= spec_max
                           and startup_triggered)
            pass_shutdown = (shutdown_ov <= spec_max and shutdown_ud <= spec_max
                            and shutdown_triggered)

            startup_fail = []
            if startup_ov > spec_max:
                startup_fail.append(f"开正过冲{startup_ov:.2f}%>{spec_max}%")
            if startup_ud > spec_max:
                startup_fail.append(f"开负过冲{startup_ud:.2f}%>{spec_max}%")
            if not startup_triggered:
                startup_fail.append("开机触发超时")

            shutdown_fail = []
            if shutdown_ov > spec_max:
                shutdown_fail.append(f"关正过冲{shutdown_ov:.2f}%>{spec_max}%")
            if shutdown_ud > spec_max:
                shutdown_fail.append(f"关负过冲{shutdown_ud:.2f}%>{spec_max}%")
            if not shutdown_triggered:
                shutdown_fail.append("关机触发超时")

            # 开机行
            self.sub_results.append(self._make_result(
                input_cond=input_cond, proto_label=proto_label,
                vout_target=vout_target, iout_eff=iout_eff,
                spec_max=spec_max, spec_min=0.0,
                scene="开机",
                ov_pct=startup_ov, ud_pct=startup_ud,
                waveform=startup_wf,
                overall_pass=pass_startup,
                fail_reason="; ".join(startup_fail),
                skipped=False,
            ))
            # 关机行
            self.sub_results.append(self._make_result(
                input_cond=input_cond, proto_label=proto_label,
                vout_target=vout_target, iout_eff=iout_eff,
                spec_max=spec_max, spec_min=0.0,
                scene="关机",
                ov_pct=shutdown_ov, ud_pct=shutdown_ud,
                waveform=shutdown_wf,
                overall_pass=pass_shutdown,
                fail_reason="; ".join(shutdown_fail),
                skipped=False,
            ))

            # ---- 步骤9：放电下电 ----
            self._step_discharge(ac, eload)

    # ---------- 步骤方法 ----------

    def _step_osc_prepare_startup(self, osc, startup_vout: float):
        """
        步骤2：用实测开机电压配置示波器，为捕获开机波形做准备。
        刻度/偏移基于实测开机电压 startup_vout；触发双沿，level = startup_vout * 0.5。
        注意：这里只配置参数，最后由调用方统一调用 set_single_trigger() 武装。
        """
        if osc is None:
            warning("[POOT] 示波器未连接")
            return

        ch = self.osc_output_ch
        # v_peak 取 1.5 倍，覆盖开机 Overshoot
        osc.auto_config_channel(ch, v_peak=startup_vout * 1.1,
                                coupling="DC",
                                bandwidth_limit=True, grid_divisions=5.0)
        osc.set_trigger_source(f"CHAN{ch}")
        osc.set_trigger_coupling("DC")
        osc.set_trigger_slope("POS")
        osc.set_trigger_level(startup_vout * 0.5)
        info(f"[POOT] 示波器开机视图 | Vstartup={startup_vout:.3f}V 触发={startup_vout*0.5:.3f}V")

    def _step_osc_prepare_shutdown(self, osc, vout_target: float):
        """
        步骤6：用目标输出电压配置示波器，为捕获关机波形做准备。
        关机前 DUT 已完成调压，稳定输出在 vout_target。
        触发仅下降沿，level = vout_target * 0.3（偏低阈值确保能触发）。
        """
        if osc is None:
            return

        ch = self.osc_output_ch
        osc.auto_config_channel(ch, v_peak=vout_target * 1.1,
                                coupling="DC",
                                bandwidth_limit=True, grid_divisions=5.0)
        osc.set_trigger_source(f"CHAN{ch}")
        osc.set_trigger_coupling("DC")
        osc.set_trigger_slope("NEG")
        osc.set_trigger_level(vout_target * 0.3)
        info(f"[POOT] 示波器关机视图 | Vout={vout_target:.3f}V 触发={vout_target*0.3:.3f}V")

    # ---------- 工具方法 ----------

    def _save_waveform(self, osc, label: str) -> str:
        """
        保存示波器波形截图，返回文件路径。
        命名规则（与 base._save_waveform 一致）：
          {用例名}_{输入条件}_{协议}_Vout{电压}V_Iout{电流}A_{startup/shutdown}.png
        失败时返回空字符串。
        """
        if osc is None:
            warning("[POOT] 示波器未连接，无法保存波形")
            return ""

        wf_dir = self._get_waveform_dir()
        os.makedirs(wf_dir, exist_ok=True)

        input_cond = f"{int(self.params.get('vin', 0))}V_{int(self.params.get('freq', 0))}Hz"
        proto      = self.params.get("proto_label", "unknown")
        vout       = self.params.get("vout_target", 0)
        iout       = self.params.get("iout_target", 0)

        fname = f"PowerOnOffTest_{input_cond}_{proto}_Vout{vout}V_Iout{iout}A_{label}.png"
        fpath = os.path.join(wf_dir, fname)

        try:
            result = osc.save_screenshot(fpath)
            if result is None:
                warning(f"[POOT] 波形截图保存失败（驱动返回 None）: {fpath}")
                return ""
            info(f"[POOT] 波形截图已保存: {fname}")
            return result
        except Exception as e:
            warning(f"[POOT] 波形截图保存异常: {e}")
            return ""

    def _get_waveform_path(self, label: str) -> str:
        """
        生成波形截图文件路径（不保存，供 save_screenshot_with_measurements 使用）。
        """
        wf_dir = self._get_waveform_dir()
        os.makedirs(wf_dir, exist_ok=True)
        input_cond = f"{int(self.params.get('vin', 0))}V_{int(self.params.get('freq', 0))}Hz"
        proto      = self.params.get("proto_label", "unknown")
        vout       = self.params.get("vout_target", 0)
        iout       = self.params.get("iout_target", 0)
        fname = f"PowerOnOffTest_{input_cond}_{proto}_Vout{vout}V_Iout{iout}A_{label}.png"
        return os.path.join(wf_dir, fname)

    # ---------- _make_result ----------
    def _make_result(self, *, input_cond: str,
                     proto_label: str, vout_target: float, iout_eff: float,
                     spec_max: float, spec_min: float,
                     scene: str, ov_pct: float, ud_pct: float,
                     waveform: str, overall_pass: bool, fail_reason: str,
                     skipped: bool) -> dict:
        """
        组装单条测试结果（sub_result）。每条 test_condition 产生 2 行：
        开机行（scene="开机"）和关机行（scene="关机"），各带 1 张波形。

        返回字段说明：
          - 字段名与 COLS 列头一致（供报告写入器直接查找）
          - 内部字段（overall_pass/skip/fail_reason）不写入报告单元格
        """
        return {
            "输入条件":          input_cond,
            "协议":              proto_label,
            "输出电压(V)":       vout_target,
            "输出电流(A)":       iout_eff,
            "开关机场景":        scene,
            "规格上限":          spec_max,
            "规格下限":          spec_min,
            "过冲(%)":           ov_pct,
            "负冲(%)":           ud_pct,
            "测试波形":          waveform,
            "测试结论":          "SKIP" if skipped else ("PASS" if overall_pass else "FAIL"),
            "备注":              fail_reason,
            # 内部字段（供结论逻辑使用，不写入报告单元格）
            "overall_pass":     overall_pass,
            "skipped":           skipped,
        }

    # ---------- verify ----------
    def verify(self) -> bool:
        """所有条件 overall_pass 为 True 才 PASS。"""
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
        """返回完整结果字典，供报告生成器使用。"""
        d = super().to_dict()
        d["sub_results"]   = self.sub_results
        d["product_type"]  = self.product_type
        passed = sum(1 for r in self.sub_results if r["overall_pass"])
        d["sweep_summary"] = {
            "conditions_tested":  len(self.sub_results),
            "passed_conditions": passed,
            "failed_conditions": len(self.sub_results) - passed,
        }
        return d
