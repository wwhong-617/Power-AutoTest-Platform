# -*- coding: utf-8 -*-
"""
InputDipTest - 输入跌落测试
===========================

测试目标：
  验证 DUT 在输入电压从下限往上限跳变过程中，输出电压始终保持在
  Vout×90%~Vout×110% 范围内，示波器 ROLL 模式捕获完整波形。

test_conditions 格式（dict）：
  {vin, freq, proto, vout, iout}

sub_result 字段：
  input_cond, condition, proto_label, vout_target, iout_target,
  spec_min, spec_max,
  osc_vmax, osc_vmin, osc_pass,
  dip_sequence,          # 跌落序列描述字符串，如 "90V&2s~240V&2s+10"
  overall_pass, fail_reason, waveform, skipped
"""

import time
import os
import sys
from ..base import TestCase
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from logger_config import info, warning, error


class InputDipTest(TestCase):
    """
  输入跌落测试（每条 test_condition 独立执行）。

  测试步骤：
    1. 开机自检（基类 startup_self_check，不下电）
    2. 示波器 ROLL 模式（双通道配置 + 估算时基）
    3. 诱骗器协议
    4. 电子负载 CC 模式上电
    5. 输入跳变序列（Vin_min ↔ Vin_max 循环）
    6. 示波器 STOP 冻结波形，读取 Vmax/Vmin，保存截图
    7. 汇总判定：Vmax ≤ Vout×110% 且 Vmin ≥ Vout×90% → PASS
  """

    # ---------- 常量 ----------
    name = "InputDipTest"
    instruments = ["AC_SOURCE", "ELOAD", "OSC", "SNIFFER", "POWER_METER"]

    DEFAULT_PARAMS = {
        "dip_cycles":  10,
        "settle_time":  2.0,
    }

    # ---------- 报告列定义 ----------
    # 顺序即 Excel 列顺序，按 COLS 定义顺序渲染所有列
    COLS = [
                ("输入条件",          16),
                ("协议",              14),
                ("输出电压(V)",       14),
                ("输出电流(A)",       14),
                ("规格下限",          11),
                ("规格上限",          11),
                ("最大值",            12),
                ("最小值",            12),
                ("输入跳变序列",       28),
                ("测试波形",           18),
                ("测试结论",           11),
                ("备注",              28),
    ]

    # ---------- __init__ ----------
    def __init__(self, test_conditions=None):
        super().__init__(name=self.name, instruments=self.instruments)
        # 合并默认参数（不覆盖引擎通过 kwargs 注入的值）
        for k, v in self.DEFAULT_PARAMS.items():
            self.params.setdefault(k, v)
        # test_conditions 若未传入，则从引擎注入的 self.params 读取
        self.test_conditions = (
            test_conditions
            if test_conditions is not None
            else self.params.get("test_conditions") or []
        )
        self.spec = {}
        self.sub_results: List[dict] = []
        self.product_type = ""

    # ---------- setup ----------
    def setup(self, instruments: Dict[str, Any]):
        """初始化仪器状态（仅配置，不上电）。"""
        self.sub_results = []
        super().setup(instruments)

        # ---- 缓存 UI 参数 ----
        self.osc_input_ch    = int(self.params.get("osc_input_ch",   4))
        self.osc_output_ch   = int(self.params.get("osc_output_ch",  2))
        self.dip_cycles      = int(self.params.get("dip_cycles",   10))
        self.settle_time     = float(self.params.get("settle_time", 2.0))
        self.vin_lo_ui       = float(self.params.get("input_voltage_lo") or 90.0)

    # ---------- execute ----------
    def execute(self, instruments: Dict[str, Any]):
        """
        主流程：逐条 test_conditions 执行，每条经 7 个步骤。

        步骤1：开机自检
        步骤2：示波器 ROLL 模式
        步骤3：诱骗器协议
        步骤4：电子负载 CC 模式上电
        步骤5：输入跳变序列（vin_lo_ui ↔ vin_cfg，功率随电压段切换）
        步骤6：示波器 STOP，读取 Vmax/Vmin，保存波形
        步骤7：放电（下电）
        """
        ac      = instruments.get("AC_SOURCE")
        eload   = instruments.get("ELOAD")
        osc     = instruments.get("OSC")
        sniffer = instruments.get("SNIFFER")

        conditions = self.test_conditions
        info(f"[IDT] execute 进入 | test_conditions 数量={len(conditions)}")

        if not conditions:
            warning("[IDT] 无测试条件，跳过执行")
            return

        for cond in conditions:
            if len(cond) < 5:
                continue

            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = \
                cond["vin"], cond["freq"], cond["proto"], cond["vout"], cond["iout"]
            cond_label = f"{proto_label}/Vout{vout_target}V/Iout{iout_target}A"

            vout_spec_min = round(float(vout_target) * 0.9, 3)
            vout_spec_max = round(float(vout_target) * 1.1, 3)

            # 提前计算功率分段后的有效电流
            # 降功率判断以跌落目标电压 vin_lo_ui 为准，而非起始电压 vin_cfg
            iout_eff = self._get_effective_iout(self.vin_lo_ui, float(vout_target), float(iout_target))
            if iout_eff != float(iout_target):
                info(f"[IDT] 条件「{cond_label}」功率分段降流：Iout={iout_eff:.3f}A（原设定 {iout_target}A）")

            # ---- 步骤1：开机自检（用该条件电压，最多3次清除重试）----
            info(f"[IDT] 开始条件: {input_cond}")
            startup_ok, measured_vout, fail_reason = self.startup_self_check(
                instruments, vin=float(vin_cfg), freq=float(freq_cfg)
            )
            info(f"[IDT] startup_self_check 结果: ok={startup_ok} vout={measured_vout:.3f}V")
            if not startup_ok:
                info(f"[IDT] 条件「{cond_label}」{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self.sub_results.append(self._make_result(
                    input_cond=f"{int(self.vin_lo_ui)}V~{int(float(vin_cfg))}V",
                    proto_label=proto_label,
                    vout_target=vout_target,
                    iout_target=iout_eff,
                    spec_min=vout_spec_min,
                    spec_max=vout_spec_max,
                    osc_vmax=0.0,
                    osc_vmin=0.0,
                    osc_pass=False,
                    dip_sequence="",
                    fail_reason=fail_reason,
                    skipped=True,
                ))
                continue

            # ---- 步骤2：示波器 ROLL 模式 ----
            self._step_setup_osc(osc, float(vout_target))

            # ---- 步骤3：诱骗器协议 ----
            sniffer_ok = self._step_setup_sniffer(sniffer, proto_label, vout_target, iout_eff)
            info(f"[IDT] 诱骗器协议: {proto_label} | {'成功' if sniffer_ok else '失败'}")

            # ---- 步骤4：电子负载 CC 模式上电（功率分段后电流）----
            self._step_setup_eload(eload, iout_eff)
            info(f"[IDT] 电子负载 ON | I={iout_eff:.3f}A")

            # ---- 步骤5：输入跳变序列（vin_max → vin_lo → vin_max，功率随电压段切换）----
            try:
                self._step_dip_recover(osc, ac, eload, self.vin_lo_ui, float(vin_cfg),
                                         iout_target, iout_eff)
            except Exception as e:
                import traceback as tb
                error(f"[IDT] _step_dip_recover 异常: {e}\n{tb.format_exc()}")
                raise

            dip_sequence = f"{int(self.vin_lo_ui)}V&{int(self.settle_time)}s~{int(float(vin_cfg))}V&{int(self.settle_time)}s+{self.dip_cycles}"

            # ---- 步骤6：示波器 STOP 冻结波形，读取 Vmax/Vmin，保存截图 ----
            try:
                osc_vmax, osc_vmin, wave_path = self._step_capture_and_measure(
                    osc, self.osc_output_ch, input_cond, proto_label, vout_target, iout_target)
            except Exception as e:
                import traceback as tb
                error(f"[IDT] _step_capture_and_measure 异常: {e}\n{tb.format_exc()}")
                raise

            osc_pass = (osc_vmax <= vout_spec_max and osc_vmin >= vout_spec_min)
            osc_fail_reason = ""
            if not osc_pass:
                if osc_vmax > vout_spec_max:
                    osc_fail_reason += f"Vmax={osc_vmax}V超过规格上限{vout_spec_max}V；"
                if osc_vmin < vout_spec_min:
                    osc_fail_reason += f"Vmin={osc_vmin}V低于规格下限{vout_spec_min}V；"

            overall_pass = osc_pass and sniffer_ok
            final_fail_reason = osc_fail_reason if not osc_pass else (
                "诱骗器协议异常" if not sniffer_ok else "")

            self.sub_results.append(self._make_result(
                input_cond=f"{int(self.vin_lo_ui)}~{int(float(vin_cfg))}V",
                proto_label=proto_label,
                vout_target=vout_target,
                iout_target=iout_eff,
                spec_min=vout_spec_min,
                spec_max=vout_spec_max,
                osc_vmax=osc_vmax,
                osc_vmin=osc_vmin,
                osc_pass=osc_pass,
                dip_sequence=dip_sequence,
                waveform=wave_path,
                fail_reason=final_fail_reason,
                skipped=False,
            ))

            # ---- 步骤7：放电（下电）----
            self._step_discharge(ac, eload)

    # ---------- 步骤方法 ----------

    def _step_setup_osc(self, osc, vout: float):
        """
        步骤2：配置示波器双通道 + ROLL 模式。

        - 开启输入通道（Vin 监测）和输出通道（Vout 监测），全带宽（跌落瞬态需捕捉高频成分）
        - VMAX/VMIN 测量项（在 auto_config_channel 后单独添加）
        - 时基根据跳变总时长估算（cycles × 2×settle_time）
        - ROLL 模式：示波器滚动刷新，扫描期间持续采集
        """
        if osc is None:
            return

        try:
            # 设置输入通道
            osc.set_channel_config(channel=self.osc_input_ch, coupling="DC",
                              voltage_scale=100.0,
                              voltage_offset=0.0,
                              bandwidth_limit=False)
            osc.set_channel_on(self.osc_input_ch)
            # 设置输出通道
            osc.auto_config_channel(channel=self.osc_output_ch, v_peak=vout,
                              coupling="DC",
                              bandwidth_limit=False)
            osc.set_channel_on(self.osc_output_ch)
            info(f"[IDT] 示波器通道已开启: CH{self.osc_input_ch}(输入) + CH{self.osc_output_ch}(输出)")

            osc.add_measurement(f"CHAN{self.osc_output_ch}", "VMAX")
            osc.add_measurement(f"CHAN{self.osc_output_ch}", "VMIN")
            info(f"[IDT] 示波器测量项: CHAN{self.osc_output_ch} VMAX/VMIN")

            total_duration_s = self.dip_cycles * (2.0 * self.settle_time + 1.0)

            osc.set_timebase_mode("ROLL")
            time.sleep(0.3)
            osc.set_timebase_for_duration(total_duration_s, divisions=10)
            time.sleep(0.5)

        except Exception as e:
            warning(f"[IDT] 示波器设置失败: {e}")

    def _step_dip_recover(self, osc, ac, eload, vin_lo, vin_hi,
                            iout_target, iout_eff):
        """
        步骤5：输入跌落序列（循环 cycles 次）。

        入口即清屏。
        每次循环：
          下行跌落 vin_hi → vin_lo：
            - vin_lo < 180V 时，先切降功率负载 iout_eff，再跌落电压
          上行恢复 vin_lo → vin_hi：
            - 先完成电压跳变
            - vin_lo < 180V 时，电压进入 HV 区（≥180V）后切回满载 iout_target
        支持暂停/停止。

        Args:
            osc:         示波器（可 None）
            ac:          交流源
            eload:       电子负载
            vin_lo:      跌落目标电压（低压下限）
            vin_hi:      恢复目标电压（高压上限）
            iout_target: 满载电流（A），HV 区恢复时切回
            iout_eff:   有效电流（A），LV 降功率段使用
        """
        if eload is None:
            return
        # 跳变前示波器清屏
        if osc:
            osc.clear_screen()        
            time.sleep(0.5)              

        # 降功率预判：vin_lo < 180V → 低压区全程降功率
        derate_in_lo = float(vin_lo) < 180.0
        # 补全第一个step时间
        time.sleep(self.settle_time)

        for cycle in range(1, int(self.dip_cycles) + 1):
            if self.is_stop_requested():
                break
            while self.is_pause_requested() and not self.is_stop_requested():
                time.sleep(0.2)

            info(f"[IDT] ====== 循环 {cycle}/{self.dip_cycles} ======")

            # ---- 下行跌落 vin_hi → vin_lo ----
            info(f"[IDT] 下行跌落：{int(vin_hi)}V → {int(vin_lo)}V")

            # 跌落前降功率
            if derate_in_lo:
                eload.set_mode_cc(float(iout_eff))
                info(f"[IDT] C{cycle} 跌落前降功率 → {iout_eff:.3f}A")

            # 立即跌落
            freq_lo = 50.0 if float(vin_lo) >= 180.0 else 60.0
            ac.set_voltage(float(vin_lo))
            ac.set_frequency(freq_lo)
            info(f"[IDT] C{cycle} 电压跌落 → {int(vin_lo)}V/{int(freq_lo)}Hz")
            time.sleep(self.settle_time)

            if self.is_stop_requested():
                break

            # ---- 上行恢复 vin_lo → vin_hi ----
            info(f"[IDT] 上行恢复：{int(vin_lo)}V → {int(vin_hi)}V")

            # 立即跳回
            freq_hi = 50.0 if float(vin_hi) >= 180.0 else 60.0
            ac.set_voltage(float(vin_hi))
            ac.set_frequency(freq_hi)
            info(f"[IDT] C{cycle} 电压恢复 → {int(vin_hi)}V/{int(freq_hi)}Hz")

            # vin_lo < 180V 时，电压进入 HV 区（≥180V）后切回满载
            if derate_in_lo:
                # 等待电压回升并检测 vac >= 180V 后再切满载
                for _ in range(20):
                    if self.is_stop_requested():
                        break
                    time.sleep(0.2)
                    try:
                        vac_now = ac.measure_voltage()
                        if vac_now is not None and vac_now >= 180.0:
                            eload.set_mode_cc(float(iout_target))
                            info(f"[IDT] C{cycle} 进入 HV 区（{vac_now:.1f}V）→ 满载 {iout_target}A")
                            break
                    except Exception:
                        pass

            time.sleep(self.settle_time)

    # _step_capture_and_measure 继承自 base.py（统一版本）

    # ---------- 工具 ----------

    def _make_result(self, *, input_cond: str,
                     proto_label: str, vout_target: float, iout_target: float,
                     spec_min: float, spec_max: float,
                     osc_vmax: float, osc_vmin: float, osc_pass: bool,
                     dip_sequence: str, waveform: str = "",
                     fail_reason: str = "", skipped: bool = False) -> dict:
        """
        组装单条测试结果（sub_result）。
        字段名即报告列名，直接对应 report_generator 的 COLS 定义。
        """
        return {
            "输入条件":       input_cond,
            "协议":          proto_label,
            "输出电压(V)":   vout_target,
            "输出电流(A)":   iout_target,
            "规格下限":      spec_min,
            "规格上限":      spec_max,
            "最大值":        osc_vmax,
            "最小值":        osc_vmin,
            "输入跳变序列":  dip_sequence,
            "测试波形":      waveform,
            "测试结论":      "SKIP" if skipped else ("PASS" if osc_pass else "FAIL"),
            "备注":          fail_reason,
            "overall_pass":  not skipped and osc_pass,
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
        d["sub_results"]  = self.sub_results
        d["product_type"] = self.product_type
        passed = sum(1 for r in self.sub_results if r["overall_pass"])
        d["sweep_summary"] = {
            "conditions_tested":  len(self.sub_results),
            "passed_conditions": passed,
            "failed_conditions": len(self.sub_results) - passed,
        }
        return d
