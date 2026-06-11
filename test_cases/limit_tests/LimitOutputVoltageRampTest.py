# -*- coding: utf-8 -*-
"""
OutputVoltageRampTest - 反复调压极限测试
========================================

测量 DUT 在反复调压过程中的输出电压稳定性。
每轮测试执行两个调压序列（Seq1 + Seq2），循环 N 轮，全部 PASS 才算整体 PASS。
每轮结束时保存一次波形（包含 Seq1+Seq2 完整调压过程）。

【test_conditions 格式】
  List[dict]，每项字段：vin / freq / proto / vout / iout

【调压序列格式】
  ramp_seq1 / ramp_seq2：协议档位字符串，例 "PD-PDO1;PD-PDO3"
  分号分隔两个档位，诱骗器依次切换到对应协议档位

【测试流程（每条条件）】

  setup()       缓存调压序列1/2、循环次数
  execute()     遍历条件，逐条件执行以下步骤
  verify()      所有 sub_result 均 PASS 才返回 True

  每条件步骤：
    1. 适配器 → SKIP
    2. startup_self_check()
    3. 设置示波器 ROLL 模式（时基适配完整调压过程，垂直刻度按最大输出电压设置）
    4. 循环 N 次：
         4.1 配置诱骗器 Seq1 → CC 带载 2s → 功率计读取 Vout → 判定
         4.2 配置诱骗器 Seq2 → CC 带载 10s → 功率计读取 Vout → 判定
         4.3 示波器 STOP，保存波形（Seq1+Seq2 完整过程）
         4.4 放电下电（准备下一循环）
    5. 放电下电

【报告字段】
  序号 | 用例名称 | 输入条件 | 调压序列 | 循环次数 | 序列1数据 | 序列2数据 |
  测试结论 | 测试波形 | 备注
"""

import time
import os
import sys
import re
from typing import Dict, Any, List
from ..base import TestCase

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning


class LimitOutputVoltageRampTest(TestCase):
    """反复调压极限测试。"""

    # 示波器单次触发等待超时（s）
    TRIGGER_TIMEOUT = 5.0

    # 调压序列带载时长（s），后续可迁到 UI 参数
    RAMP_SEQ1_DURATION = 2.0   # Seq1 带载时长
    RAMP_SEQ2_DURATION = 10.0  # Seq2 带载时长

    # 报告列定义
    COLS = [
        ("输入条件",    18),
        ("调压序列",   24),
        ("循环次数",   10),
        ("序列1数据",  22),
        ("序列2数据",  22),
        ("测试结论",   12),
        ("测试波形",   18),
        ("备注",       28),
    ]

    # ---------- __init__ ----------
    def __init__(
        self,
        product_type: str = "charger",
        test_conditions: List[dict] = None,
        osc_output_ch: int = 2,
    ):
        self.sub_results: List[dict] = []

        super().__init__(
            name="LimitOutputVoltageRampTest",
            instruments=["AC_SOURCE", "ELOAD", "SNIFFER", "OSC", "POWER_METER"],
            params={
                "osc_output_ch":    osc_output_ch,
                "product_type":     product_type,
                "test_conditions":  test_conditions,
            },
            spec={},
        )

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """缓存调压序列参数。"""
        self.sub_results = []
        super().setup(instruments)

        # ---- 调压序列（格式："QC2.0-5V" / "PD-PDO1" 等）----
        # 目标电压从序列字符串中解析，如 "QC2.0-5V" → 5.0V
        test_params = self.params.get("test_params", {})
        self._ramp_seq1 = test_params.get("反复调压序列1", "")
        self._ramp_seq2 = test_params.get("反复调压序列2", "")
        self._ramp_seq1_vout = self._parse_voltage_from_seq(self._ramp_seq1)
        self._ramp_seq2_vout = self._parse_voltage_from_seq(self._ramp_seq2)
        self._ramp_cycles = int(test_params.get("反复调压次数", 1) or 1)

        # Seq1/Seq2 带载时长（后续可从 UI 参数读取）
        self._ramp_seq1_dur = self.RAMP_SEQ1_DURATION
        self._ramp_seq2_dur = self.RAMP_SEQ2_DURATION

        # ---- 从 product_info 解析各序列档位电流 ----
        # product_info["qc"] 格式：{"QC2.0-5V": {"value": "5V3A"}, ...}
        product_info = self.params.get("product_info", {})
        qc_config = product_info.get("qc", {})
        # 调试：打印 qc keys 和 raw value
        info(f"[Ramp] qc keys: {list(qc_config.keys())}")
        info(f"[Ramp] ramp_seq1={self._ramp_seq1!r} ramp_seq2={self._ramp_seq2!r}")
        seq1_raw = qc_config.get(self._ramp_seq1, {}).get("value", "<NOT_FOUND>")
        seq2_raw = qc_config.get(self._ramp_seq2, {}).get("value", "<NOT_FOUND>")
        info(f"[Ramp] qc[{self._ramp_seq1!r}] = {seq1_raw!r}  qc[{self._ramp_seq2!r}] = {seq2_raw!r}")
        # 解析出的电流若失败则用 test_condition 的 iout（后续可迁到 UI 参数）
        self._ramp_seq1_iout = self._parse_step_current(seq1_raw if seq1_raw != "<NOT_FOUND>" else "")
        self._ramp_seq2_iout = self._parse_step_current(seq2_raw if seq2_raw != "<NOT_FOUND>" else "")
        self._osc_output_ch = int(self.params.get("osc_output_ch", 2))

        info(f"[Ramp] 调压序列1={self._ramp_seq1}({self._ramp_seq1_vout}V/{self._ramp_seq1_iout}A) | "
             f"序列2={self._ramp_seq2}({self._ramp_seq2_vout}V/{self._ramp_seq2_iout}A) | "
             f"循环次数={self._ramp_cycles}")

        # ---- 示波器公共配置 ----
        osc = self._osc(instruments)
        if osc is None:
            warning("[Ramp] 示波器未连接，跳过公共配置")
            return

        osc.set_timebase_mode("MAIN")   # 先切回 MAIN，再切 ROLL（ROLL 下改时基有延迟）
        osc.set_channel_on(self._osc_output_ch)
        osc.set_channel_coupling(self._osc_output_ch, "DC")
        osc.set_bandwidth_limit(self._osc_output_ch, False)   # 全带宽

        info(f"[Ramp] 示波器公共配置完成 | CH{self._osc_output_ch}")

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """执行反复调压极限测试。"""
        ac     = self._ac(instruments)
        eload  = self._eload(instruments)
        osc    = self._osc(instruments)
        snf    = self._sniffer(instruments)
        pwrmtr = self._pwrmeter(instruments)

        conditions = self.params.get("test_conditions", [])
        if not conditions:
            warning("[Ramp] 无测试条件，跳过执行")
            return

        # 适配器：跳过
        product_type = self.params.get("product_type", "charger")
        if product_type == "adapter":
            warning("[Ramp] 适配器不涉及调压测试，跳过")
            self._skip_all(conditions)
            return

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
                info(f"[Ramp] 条件「{cond_label}」功率分段降流："
                     f"Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # --- 步骤1：示波器 ROLL 模式配置（一次性） ---
            # 时基 = (Seq1时长 + Seq2时长) / 8div
            self._osc_prepare_roll(osc,
                                   self._ramp_seq1_vout,
                                   self._ramp_seq2_vout,
                                   self._ramp_seq1_dur,
                                   self._ramp_seq2_dur)

            # --- 步骤2：循环 N 次 ---
            for cycle_idx in range(1, self._ramp_cycles + 1):
                info(f"[Ramp] ===== 循环 {cycle_idx}/{self._ramp_cycles} =====")

                # 每次循环开始前：开机自检 + 清屏 + 启动示波器滚动
                startup_ok, vout_default, fail_reason = self.startup_self_check(
                    instruments, vin=float(vin_cfg), freq=float(freq_cfg)
                )
                if not startup_ok:
                    info(f"[Ramp] 循环 {cycle_idx} 开机自检失败：{fail_reason}，跳过本循环")
                    self._step_discharge(ac, eload)
                    self._skip_condition(input_cond, fail_reason)
                    continue

                if osc and getattr(osc, "_connected", False):
                    osc.clear_screen()
                    osc.run()

                # 序列1：配置诱骗器 → 带载（档位电流） → 测量 → 判定 → 保存波形
                seq1_current = self._ramp_seq1_iout if self._ramp_seq1_iout > 0 else iout_eff
                seq1_pass, seq1_vout = self._do_ramp_sequence(
                    instruments,
                    seq_label="Seq1",
                    ramp_seq=self._ramp_seq1,
                    vout_target=self._ramp_seq1_vout,
                    load_current=seq1_current,
                    load_duration=self._ramp_seq1_dur,
                    input_cond=input_cond,
                    cycle_idx=cycle_idx,
                )

                # 序列2：配置诱骗器 → 带载（档位电流） → 测量 → 判定 → 保存波形
                seq2_current = self._ramp_seq2_iout if self._ramp_seq2_iout > 0 else iout_eff
                seq2_pass, seq2_vout = self._do_ramp_sequence(
                    instruments,
                    seq_label="Seq2",
                    ramp_seq=self._ramp_seq2,
                    vout_target=self._ramp_seq2_vout,
                    load_current=seq2_current,
                    load_duration=self._ramp_seq2_dur,
                    input_cond=input_cond,
                    cycle_idx=cycle_idx,
                )

                # 本轮整体 PASS = 序列1 PASS 且 序列2 PASS
                cycle_pass = seq1_pass and seq2_pass
                fail_reason = "" if cycle_pass else (
                    f"Seq1={seq1_vout:.3f}V/fail; " if not seq1_pass else ""
                ) + (
                    f"Seq2={seq2_vout:.3f}V/fail" if not seq2_pass else ""
                )

                ramp_seq_full = f"{self._ramp_seq1};{self._ramp_seq2}"
                if self._ramp_seq1_vout > 0:
                    seq1_data = f"{self._ramp_seq1_vout:.3f}V→{seq1_vout:.3f}V {'PASS' if seq1_pass else 'FAIL'}"
                else:
                    seq1_data = f"{seq1_vout:.3f}V {'PASS' if seq1_pass else 'FAIL'}"
                if self._ramp_seq2_vout > 0:
                    seq2_data = f"{self._ramp_seq2_vout:.3f}V→{seq2_vout:.3f}V {'PASS' if seq2_pass else 'FAIL'}"
                else:
                    seq2_data = f"{seq2_vout:.3f}V {'PASS' if seq2_pass else 'FAIL'}"

                # ---- 循环结束时：示波器 STOP，保存完整波形（Seq1+Seq2 全过程）----
                wave_path = ""
                if osc and getattr(osc, "_connected", False):
                    try:
                        osc.stop()
                        time.sleep(0.5)
                        wave_path = self._save_waveform(
                            osc,
                            input_cond=input_cond,
                            ramp_seq_full=ramp_seq_full,
                            cycle_idx=cycle_idx,
                        )
                    except Exception as e:
                        warning(f"[Ramp] C{cycle_idx} 波形保存失败: {e}")

                self.sub_results.append({
                    "输入条件":    input_cond,
                    "调压序列":   ramp_seq_full,
                    "循环次数":   cycle_idx,
                    "序列1数据":  seq1_data,
                    "序列2数据":  seq2_data,
                    "测试结论":   "PASS" if cycle_pass else "FAIL",
                    "测试波形":   wave_path,
                    "备注":       fail_reason,
                    # 内部字段
                    "overall_pass":  cycle_pass,
                    "skipped":       False,
                })

                # --- 本循环结束：下电，准备下一循环 ---
                self._step_discharge(ac, eload)

            # --- 条件结束：完整放电下电 ---
            self._step_discharge(ac, eload)

    # ---------- _do_ramp_sequence ----------
    def _do_ramp_sequence(
        self,
        instruments: Dict[str, Any],
        seq_label: str,
        ramp_seq: str,
        input_cond: str,
        vout_target: float,
        load_current: float,
        load_duration: float,
        cycle_idx: int,
    ) -> tuple:
        """
        执行一次调压序列（一个协议档位）。

        流程：
          1. 配置诱骗器（电压由协议档位决定）
          2. 电子负载 CC 带载 load_current
          3. 功率计读取实测输出电压
          4. 判定：Vout >= Vout_target × 0.9

        Returns:
            (pass: bool, measured_vout: float)
        """
        eload  = self._eload(instruments)
        osc    = self._osc(instruments)
        snf    = self._sniffer(instruments)
        pwrmtr = self._pwrmeter(instruments)

        # ---- 解析协议档位并配置诱骗器 ----
        proto_label = ramp_seq.strip()
        if proto_label:
            ok = self._step_setup_sniffer(snf, proto_label, vout_target, load_current)
            if not ok:
                warning(f"[Ramp] {seq_label} 诱骗器配置失败：{proto_label}")
                return False, 0.0
            info(f"[Ramp] {seq_label} 诱骗器已配置：{proto_label}")

        # ---- 等待调压稳定 1.5s ----
        time.sleep(1.5)

        # ---- 电子负载 CC 带载 ----
        self._step_setup_eload(eload, load_current)
        time.sleep(load_duration)

        # ---- 功率计读取输出电压 ----
        vout_measured = 0.0
        if pwrmtr and getattr(pwrmtr, "_connected", False):
            try:
                # WT333E 读取输出电压（V）
                vout_measured = pwrmtr.measure_output_voltage()
                info(f"[Ramp] {seq_label} 功率计实测 Vout={vout_measured:.3f}V")
            except Exception as e:
                warning(f"[Ramp] {seq_label} 功率计读取失败: {e}")

        # ---- 判定 ----
        vout_min_threshold = vout_target * 0.9
        seq_pass = bool(vout_measured >= vout_min_threshold)
        verdict = "PASS" if seq_pass else "FAIL"
        info(f"[Ramp] {seq_label} 判定：实测={vout_measured:.3f}V "
             f"阈值={vout_min_threshold:.3f}V → {verdict}")

        # 波形在循环结束时统一保存，此处不保存
        return seq_pass, vout_measured

    # ---------- _osc_prepare_roll ----------
    def _osc_prepare_roll(self, osc, seq1_vout: float, seq2_vout: float,
                          seq1_dur: float, seq2_dur: float):
        """
        配置示波器 ROLL 模式，时基适配完整调压过程。

        时基 = (Seq1时长 + Seq2时长) / 8div
        示例：Seq1=2s + Seq2=10s → (2+10)/8 = 1.5s/div
        垂直刻度按两序列中最大电压 × 1.3（留 overshoot 余量）。
        """
        if osc is None:
            return

        # 时基 = (Seq1时长 + Seq2时长) / 8div
        timebase = (seq1_dur + seq2_dur) / 8.0

        # 垂直刻度：两序列中最大电压 × 1.3 / 5格
        v_max = max(seq1_vout, seq2_vout)
        v_peak = v_max * 1.3
        scale = osc.round_voltage_scale(v_peak / 5.0)
        offset = v_max / 2.0

        osc.stop()
        osc.set_timebase_mode("ROLL")
        time.sleep(0.3)
        osc.set_timebase(timebase)
        time.sleep(0.5)
        osc.set_voltage_scale(self._osc_output_ch, scale)
        osc.set_channel_offset(self._osc_output_ch, offset)
        osc.set_trigger_mode("AUTO")
        osc.set_trigger_source(f"CHAN{self._osc_output_ch}")
        osc.set_trigger_level(v_max * 0.5)
        osc.set_trigger_slope("BOTH")

        info(f"[Ramp] 示波器 ROLL | 时基={timebase:.1f}s/div | "
             f"刻度={scale:.3f}V/div | Vout最大={v_max:.1f}V")

    # ---------- _save_waveform ----------
    def _save_waveform(self, osc, input_cond: str,
                       ramp_seq_full: str, cycle_idx: int) -> str:
        """
        保存示波器当前波形截图。

        文件名：{用例名}_{输入条件}_{调压序列}_C{循环次数}_{Seq序号}.png
        """
        if osc is None:
            return ""

        osc_dir = self.params.get("osc_waveform_dir", "")
        if not osc_dir:
            osc_dir = os.path.join(
                self.params.get("result_dir", ""),
                "测试波形"
            )
        os.makedirs(osc_dir, exist_ok=True)

        # 清理文件名特殊字符
        ramp_seq_clean = ramp_seq_full.replace(";", "_").replace("/", "_").replace(" ", "_")
        filename = (
            f"反复调压极限测试_{input_cond}_{ramp_seq_clean}"
            f"_C{cycle_idx}.png"
        )
        filepath = os.path.join(osc_dir, filename)

        try:
            osc.save_screenshot(filepath)
            info(f"[Ramp] 波形已保存: {filepath}")
            return filepath
        except Exception as e:
            warning(f"[Ramp] 波形保存失败: {e}")
            return ""

    # ---------- _parse_voltage_from_seq ----------
    def _parse_voltage_from_seq(self, seq: str) -> float:
        """
        从序列字符串解析目标电压。
        支持格式："QC2.0-5V" → 5.0, "PD-PDO1" → 0.0（PDO电压由DUT决定，无法预知）
        """
        if not seq:
            return 0.0
        m = re.search(r'(\d+(?:\.\d+)?)V', seq, re.IGNORECASE)
        return float(m.group(1)) if m else 0.0

    # ---------- _parse_step_current ----------
    def _parse_step_current(self, value_str: str) -> float:
        """
        从协议档位配置字符串解析电流。
        支持格式："5V3A" → 3.0, "12V1.5A" → 1.5, "9V2A" → 2.0, "12V 4.2A" → 4.2
        解析失败返回 0.0（调用方需用条件级 iout 作为 fallback）。
        """
        if not value_str:
            return 0.0
        # 去掉所有空格后再匹配，避免 "12V 4.2A" 这类格式干扰
        s = value_str.replace(' ', '')
        m = re.search(r'(\d+(?:\.\d+)?)A', s, re.IGNORECASE)
        return float(m.group(1)) if m else 0.0

    # ---------- _skip_condition ----------
    def _skip_condition(self, input_cond: str, fail_reason: str):
        """记录一条 SKIP 结果（开机自检失败等异常情况）。"""
        ramp_seq_full = f"{self._ramp_seq1};{self._ramp_seq2}"
        self.sub_results.append({
            "输入条件":   input_cond,
            "调压序列":  ramp_seq_full,
            "循环次数":  "-",
            "序列1数据": fail_reason,
            "序列2数据": "SKIP",
            "测试结论":  "SKIP",
            "测试波形":  "",
            "备注":      fail_reason,
            "overall_pass": False,
            "skipped":    True,
        })

    # ---------- _skip_all ----------
    def _skip_all(self, conditions: List[dict]):
        """适配器场景：所有条件标记为 SKIP。"""
        for cond in conditions:
            vin_cfg = cond.get("vin", 0)
            freq_cfg = cond.get("freq", 0)
            input_cond = f"{int(vin_cfg)}V_{int(freq_cfg)}Hz"
            ramp_seq_full = f"{self._ramp_seq1};{self._ramp_seq2}"
            self.sub_results.append({
                "输入条件":   input_cond,
                "调压序列":  ramp_seq_full,
                "循环次数":  "-",
                "序列1数据": "适配器不涉及",
                "序列2数据": "SKIP",
                "测试结论":  "SKIP",
                "测试波形":  "",
                "备注":      "适配器不涉及调压测试",
                "overall_pass": False,
                "skipped":    True,
            })

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

    # ---------- teardown ----------
    def teardown(self, instruments: Dict[str, Any]):
        """放电下电，关闭示波器通道。"""
        self._step_discharge(
            instruments.get("AC_SOURCE"),
            instruments.get("ELOAD"),
        )
        osc = instruments.get("OSC")
        if osc:
            try:
                for ch in range(1, 5):
                    osc.set_channel_off(ch)
            except Exception:
                pass
