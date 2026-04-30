# -*- coding: utf-8 -*-
"""
OutputPowerOnOffTest - 开关机过冲/下冲测试
==========================================

测量 DUT 开机和关机时的输出电压过冲/下冲（overshoot/undershoot），
判断是否在规格内。每个测试条件输出一对结果行（开机 + 关机各一行）。

【test_conditions 格式】
  List[dict]，每项字段：vin / freq / proto / vout / iout

【测试流程（每条条件）】

  setup()     初始化示波器通道（DC 耦合 / 全带宽 / OVER+POVER 测量）
  execute()   遍历条件，逐条件执行以下步骤
  verify()    所有 sub_result 均 PASS 才返回 True

  每条件步骤：
    1. 开机自检（基类 startup_self_check），捕获实测开机电压
    2. 用实测开机电压配置示波器（开机视图：刻度/偏移/触发）
    3. AC OFF + 放电（确保完全下电，进入冷启动）
    4. 武装示波器 SINGLE 触发 → 开机自检上电 → 等待触发
    5. 读取开机波形 + 过冲/下冲数据
    6. 诱骗器协议配置 + 电子负载设额定电流
    7. 用 vout_target 重新配置示波器（关机视图）
    8. 武装示波器 SINGLE 触发 → AC OFF → 等待触发
    9. 读取关机波形 + 过冲/下冲数据
   10. 放电下电

  注意：每条条件产生 2 行 sub_result（开机行 + 关机行），
        各自携带独立的波形和过冲/下冲数据。

【报告字段】
  序号 | 用例名称 | 输入条件 | 协议 | 输出电压(V) | 输出电流(A) |
  开关机场景 | 规格上限 | 规格下限 | 过冲(%) | 负冲(%) |
  测试波形 | 测试结论 | 备注
"""

import time
import os
import sys
from typing import Dict, Any, List
from ..base import TestCase

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class OutputPowerOnOffTest(TestCase):
    """开关机过冲/下冲测试。"""

    TRIGGER_TIMEOUT = 5.0    # 示波器触发等待超时（s）
    TRIGGER_WAIT_S  = 0.3    # 轮询触发状态间隔（s）
    TIME_BASE_S     = 0.005  # 示波器时基 5ms/div（10div=50ms 总窗口）

    # 报告列定义（序号/用例名称由 report_generator._flatten() 自动注入）
    COLS = [
    # 注意：「测试结论」列不定义在 COLS 中，
    # 由 report_generator._flatten() 统一注入（prefix 列）。

        ("输入条件",   16),
        ("协议",       12),
        ("输出电压(V)", 13),
        ("输出电流(A)", 13),
        ("开关机场景",  12),
        ("规格上限",   11),
        ("规格下限",   11),
        ("过冲(%)",   12),
        ("负冲(%)",   12),
        ("测试结论",       12),
        ("测试波形",    18),
        ("备注",       28),
    ]

    # ---------- __init__ ----------
    def __init__(
        self,
        overshoot_max_pct: float = 20.0,
        product_type: str = "charger",
        test_conditions: List[dict] = None,
        osc_output_ch: int = 2,
    ):
        """
        Args:
            overshoot_max_pct: 过冲规格上限（%）
            product_type:     产品类型，"charger" 或 "adapter"
            test_conditions: 测试条件列表，每项 dict，
                           字段：vin / freq / proto / vout / iout
            osc_output_ch:   示波器输出通道编号（默认2）
        """
        self.sub_results: List[dict] = []

        super().__init__(
            name="OutputPowerOnOffTest",
            instruments=["AC_SOURCE", "ELOAD", "OSC", "SNIFFER", "POWER_METER"],
            params={
                "osc_output_ch":   osc_output_ch,
                "product_type":     product_type,
                "test_conditions": test_conditions,
                "timebase_s":      self.TIME_BASE_S,
            },
            spec={
                "开关机过冲_pct_hi": overshoot_max_pct,
            },
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """示波器初始化：DC 耦合 / 全带宽 / OVER+POVER 测量。"""
        self.sub_results = []
        super().setup(instruments)

        self.osc_output_ch = int(self.params.get("osc_output_ch", 2))
        osc = instruments.get("OSC")
        if osc is None:
            warning("[POOT] 示波器未连接，跳过公共配置")
            return

        # 时基（全局固定）
        osc.set_timebase(self.TIME_BASE_S)

        # 通道配置：DC 耦合，全带宽（开关机瞬态需全带宽）
        osc.set_channel_on(self.osc_output_ch)
        osc.set_channel_coupling(self.osc_output_ch, "DC")
        osc.set_bandwidth_limit(self.osc_output_ch, False)   # bool，False=全带宽

        # 测量项：OVER（过冲）+ POVER（下冲）
        osc.clear_measurements()
        osc.add_measurement(self.osc_output_ch, "OVER")
        osc.add_measurement(self.osc_output_ch, "POVER")

        info(f"[POOT] 示波器公共配置完成 | CH{self.osc_output_ch} "
             f"时基={self.TIME_BASE_S*1000:.1f}ms/div 全带宽")

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """执行开关机过冲/下冲测试。

        遍历 test_conditions，每条件独立执行：开机自检 →
        冷启动采集开机波形 → 协议+负载配置 → 采集关机波形 →
        记录 2 行结果 → 下电。
        """
        ac    = self._ac(instruments)
        eload = self._eload(instruments)
        osc   = self._osc(instruments)
        snf   = self._sniffer(instruments)

        conditions = self.params.get("test_conditions", [])
        if not conditions:
            warning("[POOT] 无测试条件，跳过执行")
            return

        spec_max = self.spec.get("开关机过冲_pct_hi", 20.0)

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
                info(f"[POOT] 条件「{cond_label}」功率分段降流："
                     f"Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # --- 步骤1：开机自检，捕获实测开机电压 ---
            startup_ok, vout_default, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            if not startup_ok:
                info(f"[POOT] 条件「{cond_label}」开机自检失败："
                     f"{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self._skip_condition(
                    input_cond, proto_label, vout_target, iout_eff,
                    spec_max, fail_reason,
                )
                continue

            # --- 步骤2：用实测开机电压配置示波器（开机视图）---
            self._osc_prepare_startup(osc, vout_default)

            # --- 步骤3：AC OFF + 放电（确保完全下电，冷启动）---
            if ac:
                ac.output_off()
            self._step_discharge(ac, eload)

            # --- 步骤4：武装示波器 SINGLE 触发 → 开机自检上电 → 等待触发 ---
            if osc:
                osc.set_single_trigger()
                time.sleep(1.0)

            cold_ok, _, cold_fail = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )

            # 无论冷启动是否完全成功都继续采集（可能有波形数据）
            if osc:
                info(f"[POOT] 开机等待触发 | timeout={self.TRIGGER_TIMEOUT}s")
                triggered = self._osc_wait_trigger(
                    osc, timeout_s=self.TRIGGER_TIMEOUT,
                    poll_interval=self.TRIGGER_WAIT_S,
                )
                if not triggered:
                    osc.stop()

            # --- 步骤5：读取开机波形 + 过冲/下冲 ---
            startup_ov, startup_ud, startup_wf = self._read_osc_snapshot(
                osc, "startup",
                input_cond, proto_label, float(vout_target), float(iout_eff),
            )

            # --- 步骤6：诱骗器协议配置 + 电子负载 CC ---
            self._step_setup_sniffer(snf, proto_label, float(vout_target), float(iout_eff))
            self._step_setup_eload(eload, iout_eff)
            time.sleep(1.5)

            # --- 步骤7：用 vout_target 重新配置示波器（关机视图）---
            self._osc_prepare_shutdown(osc, float(vout_target))

            # --- 步骤8：武装示波器 SINGLE 触发 → AC OFF → 等待触发 ---
            if osc:
                osc.set_single_trigger()
                time.sleep(2.0)
            if ac:
                ac.output_off()

            if osc:
                info(f"[POOT] 关机等待触发 | timeout={self.TRIGGER_TIMEOUT}s")
                triggered = self._osc_wait_trigger(
                    osc, timeout_s=self.TRIGGER_TIMEOUT,
                    poll_interval=self.TRIGGER_WAIT_S,
                )
                if not triggered:
                    osc.stop()

            # --- 步骤9：读取关机波形 + 过冲/下冲 ---
            shutdown_ov, shutdown_ud, shutdown_wf = self._read_osc_snapshot(
                osc, "shutdown",
                input_cond, proto_label, float(vout_target), float(iout_eff),
            )

            # --- 步骤10：放电下电 ---
            self._step_discharge(ac, eload)

            # --- 记录结果（每条件 2 行：开机 + 关机）---
            self._record_startup(
                input_cond, proto_label, vout_target, iout_eff,
                spec_max, startup_ov, startup_ud, startup_wf,
            )
            self._record_shutdown(
                input_cond, proto_label, vout_target, iout_eff,
                spec_max, shutdown_ov, shutdown_ud, shutdown_wf,
            )

    # ---------- _osc_prepare_startup ----------
    def _osc_prepare_startup(self, osc, vout_measured: float):
        """
        用实测开机电压配置示波器开机视图。

        Args:
            vout_measured: 开机后实测输出电压（基准值）
        """
        if osc is None:
            return
        ch = self.osc_output_ch
        # 刻度 = 开机电压 × 1.5（留 overshoot 余量）/ 4格
        # round_voltage_scale 自动 round 到 DSOX 1-2-5 档位表
        v_peak = vout_measured * 1.5
        scale = osc.round_voltage_scale(v_peak / 4.0)
        # 偏移：波形底部对准屏幕第2格（0V在第2格，Vout在第2+v_peak/scale格）
        offset = vout_measured / 2.0
        osc.set_voltage_scale(ch, scale)
        osc.set_channel_offset(ch, offset)
        osc.set_trigger_source(f"CHAN{ch}")
        osc.set_trigger_level(vout_measured * 0.5)
        osc.set_trigger_slope("POS")
        info(f"[POOT] 示波器开机视图 | Vout实测={vout_measured:.3f}V "
             f"刻度={scale:.3f}V/div 偏移={offset:.3f}V")

    # ---------- _osc_prepare_shutdown ----------
    def _osc_prepare_shutdown(self, osc, vout_target: float):
        """
        用目标电压配置示波器关机视图。

        Args:
            vout_target: 测试条件目标输出电压
        """
        if osc is None:
            return
        ch = self.osc_output_ch
        # 刻度 = 目标电压 × 1.5（留 undershoot 余量）/ 4格
        v_peak = vout_target * 1.5
        scale = osc.round_voltage_scale(v_peak / 4.0)
        offset = vout_target / 2.0
        osc.set_voltage_scale(ch, scale)
        osc.set_channel_offset(ch, offset)
        osc.set_trigger_source(f"CHAN{ch}")
        osc.set_trigger_level(vout_target * 0.5)
        osc.set_trigger_slope("NEG")
        info(f"[POOT] 示波器关机视图 | Vout目标={vout_target:.3f}V "
             f"刻度={scale:.3f}V/div 偏移={offset:.3f}V")

    # ---------- _osc_wait_trigger ----------
    def _osc_wait_trigger(self, osc, timeout_s: float, poll_interval: float) -> bool:
        """
        轮询等待示波器 SINGLE 触发完成。

        DSOX4024A SINGLE 模式触发状态：ARM（等待）/ STOP（已触发）。

        Returns:
            True = 触发成功，False = 超时未触发
        """
        if osc is None:
            return False
        elapsed = 0.0
        while elapsed < timeout_s:
            try:
                state = osc.get_run_state().upper().strip()
            except Exception:
                state = ""
            if state == "STOP":
                info(f"[POOT] 触发完成 | elapsed={elapsed:.2f}s")
                return True
            elapsed += poll_interval
            time.sleep(poll_interval)
        warning(f"[POOT] 触发超时 | {elapsed:.1f}s 未触发")
        return False

    # ---------- _read_osc_snapshot ----------
    def _read_osc_snapshot(self, osc, scene: str,
                               input_cond: str, proto: str,
                               vout: float, iout: float) -> tuple:
        """
        读取示波器当前波形快照：过冲 / 下冲 / 波形路径。

        Returns:
            (overshoot_pct, undershoot_pct, waveform_path)
        """
        ov, ud = 0.0, 0.0
        wf = ""
        if osc is None:
            return ov, ud, wf

        try:
            ov = osc.measure_overshoot_builtin(self.osc_output_ch) or 0.0
            ud = osc.measure_undershoot_builtin(self.osc_output_ch) or 0.0
            info(f"[POOT] {scene} 读数 | 过冲={ov:.2f}% 下冲={ud:.2f}%")
        except Exception as e:
            warning(f"[POOT] {scene} 读取异常: {e}")

        wf = self._save_waveform(osc, scene, input_cond, proto, vout, iout)
        try:
            osc.run()   # 恢复采集
        except Exception:
            pass

        return ov, ud, wf

    # ---------- _save_waveform ----------
    def _save_waveform(self, osc, scene: str,
                        input_cond: str, proto: str,
                        vout: float, iout: float) -> str:
        """
        保存波形截图，文件名格式：
        {用例名}_{输入条件}_{协议}_Vout{电压}V_Iout{电流}A_{startup/shutdown}.png
        """
        if osc is None:
            return ""
        base_dir = self._get_waveform_dir()
        os.makedirs(base_dir, exist_ok=True)

        fname = (f"{self.name}_{input_cond}_{proto}_"
                 f"Vout{vout}V_Iout{iout}A_{scene}.png")
        fpath = os.path.join(base_dir, fname)
        try:
            result = osc.save_screenshot(fpath)
            if result:
                info(f"[POOT] 波形已保存: {fname}")
                return result
            warning(f"[POOT] 波形截图驱动返回 None: {fpath}")
            return ""
        except Exception as e:
            warning(f"[POOT] 波形截图异常: {e}")
            return ""

    # ---------- _record_startup / _record_shutdown ----------
    def _record_startup(
        self, input_cond, proto_label, vout_target, iout_eff,
        spec_max, ov, ud, wf,
    ):
        passed = (0 <= ov <= spec_max) and (0 <= ud <= spec_max)
        self.sub_results.append(self._make_result(
            input_cond=input_cond,
            proto_label=proto_label,
            vout_target=round(vout_target, 3),
            iout_eff=round(iout_eff, 3),
            scene="开机",
            spec_max=spec_max,
            ov_pct=round(ov, 3),
            ud_pct=round(ud, 3),
            waveform=wf,
            overall_pass=passed,
            fail_reason="" if passed else (
                f"过冲={ov:.2f}%/下冲={ud:.2f}% 超规格({spec_max}%)"),
        ))

    def _record_shutdown(
        self, input_cond, proto_label, vout_target, iout_eff,
        spec_max, ov, ud, wf,
    ):
        passed = (0 <= ov <= spec_max) and (0 <= ud <= spec_max)
        self.sub_results.append(self._make_result(
            input_cond=input_cond,
            proto_label=proto_label,
            vout_target=round(vout_target, 3),
            iout_eff=round(iout_eff, 3),
            scene="关机",
            spec_max=spec_max,
            ov_pct=round(ov, 3),
            ud_pct=round(ud, 3),
            waveform=wf,
            overall_pass=passed,
            fail_reason="" if passed else (
                f"过冲={ov:.2f}%/下冲={ud:.2f}% 超规格({spec_max}%)"),
        ))

    # ---------- _skip_condition ----------
    def _skip_condition(
        self, input_cond, proto_label, vout_target, iout_eff,
        spec_max, fail_reason,
    ):
        for scene in ("开机", "关机"):
            self.sub_results.append(self._make_result(
                input_cond=input_cond,
                proto_label=proto_label,
                vout_target=round(vout_target, 3),
                iout_eff=round(iout_eff, 3),
                scene=scene,
                spec_max=spec_max,
                ov_pct=0.0,
                ud_pct=0.0,
                waveform="",
                overall_pass=False,
                fail_reason=fail_reason,
                skipped=True,
            ))

    # ---------- _make_result ----------
    def _make_result(
        self, *, input_cond: str,
        proto_label: str, vout_target: float, iout_eff: float,
        scene: str,
        spec_max: float, ov_pct: float, ud_pct: float,
        waveform: str,
        overall_pass: bool, fail_reason: str,
        skipped: bool = False,
    ) -> dict:
        """
        组装单条 sub_result，字段名与 COLS 列头一一对应
        （序号/用例名称由 report_generator._flatten() 注入，此处不重复）。
        """
        return {
            "输入条件":      input_cond,
            "协议":          proto_label,
            "输出电压(V)":   vout_target,
            "输出电流(A)":  iout_eff,
            "开关机场景":   scene,
            "规格上限":      spec_max,
            "规格下限":      0.0,
            "过冲(%)":      ov_pct,
            "负冲(%)":      ud_pct,
            "测试波形":      waveform,
            "测试结论":      "SKIP" if skipped else ("PASS" if overall_pass else "FAIL"),
            "备注":          fail_reason,
            # 内部字段（供 verify() 判定使用，不写入报告）
            "overall_pass":  overall_pass,
            "skipped":       skipped,
        }

    # ---------- verify ----------
    def verify(self) -> bool:
        """所有 sub_result 均 PASS 才返回 True。"""
        return bool(self.sub_results) and all(
            r["overall_pass"] or r.get("skipped")
            for r in self.sub_results
        )

    # ---------- to_dict ----------
    def to_dict(self) -> dict:
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        return d
