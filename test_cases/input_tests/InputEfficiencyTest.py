# -*- coding: utf-8 -*-
"""
EfficiencyTest - 能效测试
=========================

【测试目标】
  在额定输入电压/频率/协议条件下，测量 DUT 在不同负载点（10%~100%）下的
  输入功率、输出电压/电流，计算各点效率及 6 级/7 级平均能效，与规格比对后
  给出 PASS/FAIL 结论。

【效率公式】
  η = (Vout × Iout) / Pin × 100%

【测试条件格式】
  {vin, freq, proto, vout, iout}
  例: {"vin": 220.0, "freq": 50.0, "proto": "PD", "vout": 20.0, "iout": 3.25}

【负载点】
  100% → 75% → 50% → 25% → 10%  （从大到小，减少电子负载开关动作）

【能效等级】
  - 6 级平均：η25% + η50% + η75% + η100% 的算术平均
  - 7 级平均：η10% + η25% + η50% + η75% + η100% 的算术平均

【规格来源】
  - 6 级规格：UI 产品规格页面 "6级能效要求（%）" 字段
  - 7 级规格：UI 产品规格页面 "7级能效要求（%）" 字段
  - 均支持回退到 "效率（%）" 通用字段，再回退到硬编码默认值 88%~95%

【功率计档位选择】
  由驱动层自动完成（见 WT333E/WT322E set_voltage_range_auto /
  set_current_range_auto），用例只传测试电压/电流值，驱动根据
  硬编码档位表 [600/300/150/60/30/15]V、[20/10/5/2/1/0.5]A
  自动选≥测试值的最小档并设置。

【报告输出（16 列）】
  序号 | 输入条件 | 输出条件 | 负载点 | 效率下限 | 效率上限 |
  输入功率(W) | 输出电压(V) | 输出电流(A) | 效率(%) | 测试结论 |
  6级平均能效(%) | 6级能效结论 | 7级平均能效(%) | 7级能效结论 | 备注

  - 6 级平均能效数值填在 50% 负载点行，其余行为 0
  - 7 级平均能效数值填在 10% 负载点行，其余行为 0
  - 所有负载点均 PASS 才算整体 PASS
"""

import time
import logging
import numpy as np
from typing import Dict, Any, List

from ..base import TestCase, TestResult

logger = logging.getLogger("PowerAutoTest")


class InputEfficiencyTest(TestCase):
    """
    能效测试用例。

    每个测试条件（vin, freq, proto, vout, iout）执行 5 个负载点
    （10% / 25% / 50% / 75% / 100%），计算各点效率及 6 级/7 级平均效率。

    仪器依赖：AC_SOURCE / ELOAD / SNIFFER / POWER_METER
    """

    # ─────────────────────────────────────────────────────────────────
    # 负载点定义（从大到小，减少电子负载开关动作）
    # ─────────────────────────────────────────────────────────────────
    LOAD_POINTS = [1.00, 0.75, 0.50, 0.25, 0.10]   # 100%, 75%, 50%, 25%, 10%

    # 能效测试输入电流量程估算参数
    _PF = 0.4          # 预设功率因数
    _EFFICIENCY = 0.86 # 预设效率
    _IIN_SPIKE = 1.414 # 电流尖峰系数（×√2）

    # ---------- 报告列定义 ----------
    # 顺序即 Excel 列顺序，按 COLS 定义顺序渲染所有列
    # 注意：「测试结论」列不定义在 COLS 中，
    # 由 report_generator._flatten() 统一注入（prefix 列），
    # 避免与 _merge_efficiency_avg_cells 的 prefix_len 计算冲突。
    COLS = [
        ("输入条件",          16),
        ("协议",              14),
        ("输出电压(V)",       14),
        ("输出电流(A)",       14),
        ("负载点",             8),
        ("Iout设定(A)",       12),
        ("输入功率(W)",       15),
        ("测量电压(V)",       14),
        ("测量电流(A)",       14),
        ("效率(%)",           10),
        ("6级平均能效(%)",    15),
        ("6级能效结论",       12),
        ("7级平均能效(%)",    15),
        ("7级能效结论",       12),
        ("平均能效要求(%)",   18),
        ("测试结论",       12),
        ("备注",              28),
    ]

    # ─────────────────────────────────────────────────────────────────
    # 公开属性
    # ─────────────────────────────────────────────────────────────────
    def __init__(
        self,
        input_voltage_min: float = 90.0,
        input_voltage_max: float = 264.0,
        vout_spec_min: float = None,
        vout_spec_max: float = None,
        product_type: str = "charger",
        test_conditions: List[tuple] = None,
    ):
        self.product_type = product_type
        self.test_conditions = None   # 避免 setup() 访问未定义属性 AttributeError
        self.sub_results: List[dict] = []

        super().__init__(
            name="InputEfficiencyTest",
            instruments=["AC_SOURCE", "ELOAD", "SNIFFER", "POWER_METER"],
            params={
                "input_voltage_lo": input_voltage_min,
                "input_voltage_hi": input_voltage_max,
                "product_type": product_type,
                "test_conditions": test_conditions,
            },
            spec={
                "vout_min": vout_spec_min,
                "vout_max": vout_spec_max,
            },
        )

    # =================================================================
    # setup — 仪器初始化
    # =================================================================
    def setup(self, instruments: Dict[str, Any]):
        self.sub_results = []
        super().setup(instruments)

        # ---- 缓存 UI 参数 ----
        # 注意值由字典流到字典值，不是 tuple 是 dict
        self.test_conditions = self.test_conditions or self.params.get("test_conditions", [])
        self.warmup = float(self.params.get("warmup", 10.0))
        self.input_voltage_lo = float(self.params.get("input_voltage_lo", 90.0))
        self.input_voltage_hi = float(self.params.get("input_voltage_hi", 264.0))
        self.power_segment = int(self.params.get("power_segment", 0))
        self.hv_power = float(self.params.get("hv_power", 0.0))
        self.lv_power = float(self.params.get("lv_power", 0.0))
        self.osc_input_ch = int(self.params.get("osc_input_ch", 4))
        self.osc_output_ch = int(self.params.get("osc_output_ch", 2))

    # =================================================================
    # execute — 主流程
    #
    #  ┌─────────────────────────────────────────────────────────────┐
    #  │  热机阶段（一次）                                           │
    #  │    _find_warmup_condition()  筛选热机条件                   │
    #  │    _do_warmup()             热机 → _step_discharge()      │
    #  ├─────────────────────────────────────────────────────────────┤
    #  │  主测试循环（每个条件执行一次）                               │
    #  │    ① 开机自检（AC源配置输入电压/频率，等待输出稳定）          │
    #  │    ② 诱骗器设置协议+输出电压                                │
    #  │    ③ 电子负载 ON（带载老化 20s）                           │
    #  │    ④ 循环测 5 个负载点（100%→10%）                        │
    #  │    ⑤ 计算 6 级/7 级平均能效                                │
    #  │    ⑥ 填 sub_results（含结论）                              │
    #  │    ⑦ _step_discharge()                                     │
    #  └─────────────────────────────────────────────────────────────┘
    # =================================================================
    def execute(self, instruments: Dict[str, Any]):
        ac      = instruments.get("AC_SOURCE")
        eload   = instruments.get("ELOAD")
        sniffer = instruments.get("SNIFFER")
        pm      = instruments.get("POWER_METER")

        conditions = self.test_conditions
        if not conditions:
            logger.warning("[EfficiencyTest] 没有测试条件，跳过")
            return

        # ── 热机阶段 ──
        warmup_cond = self._find_warmup_condition(conditions)
        if warmup_cond:
            warmup_ok = self._do_warmup(warmup_cond, instruments)
            if not warmup_ok:
                logger.warning("[EfficiencyTest] 热机失败，跳过全部测试")
                return

        # ── 主测试循环 ──
        for cond in conditions:
            vin_cfg, freq_cfg, proto_label, vout_target, iout_target = \
                cond.get("vin"), cond.get("freq"), cond.get("proto", ""), \
                cond.get("vout"), cond.get("iout")

            input_cond  = f"{vin_cfg}V_{freq_cfg}Hz"
            output_cond = f"{proto_label}_Vout{vout_target}V_Iout{iout_target}A"

            # 提前计算 effective iout（startup 失败时也要用）
            iout_eff = self._get_effective_iout(vin_cfg, vout_target, iout_target)

            # 缓存当前条件的 vout_target，供 _measure_load_point 读取
            self.vout_target = round(vout_target, 3)

            # ① 开机自检（直接用当前条件的输入电压/频率）
            startup_ok, _, fail_reason = self.startup_self_check(
                instruments, vin=vin_cfg, freq=freq_cfg
            )
            if not startup_ok:
                logger.warning(
                    f"[EfficiencyTest] 条件 {output_cond} 开机自检失败: {fail_reason}"
                )
                self._step_discharge(ac, eload)
                self._add_all_loadpoint_results(
                    input_cond=input_cond,
                    output_cond=output_cond,
                    proto_label=proto_label,
                    vout_target=round(vout_target, 3),
                    iout_eff=iout_eff,
                    skipped=True,
                    reason=fail_reason,
                )
                continue

            # ② 诱骗器设置协议（自检通过后，确保用正确协议输出）
            self._step_setup_sniffer(sniffer, proto_label, vout_target, iout_target)

            # ③ 电子负载 ON（带载老化——用功率分段后的实际电流）
            if eload and getattr(eload, "_connected", False):
                eload.set_mode_cc(float(iout_eff))
                eload.input_on()
                if iout_eff != iout_target:
                    logger.info(
                        f"[EfficiencyTest] 功率分段降流老化：Iout={iout_eff:.3f}A "
                        f"（原设定 {iout_target}A）"
                    )

            # ④ 老化 20s
            logger.info(f"[EfficiencyTest] {output_cond} 老化 20s (Iout={iout_eff:.3f}A)...")
            time.sleep(20.0)

            # ⑥ 循环测 5 个负载点（100% → 10%，从大到小）
            load_results = []
            for ratio in self.LOAD_POINTS:
                iout_set = round(iout_eff * ratio, 3)
                res = self._measure_load_point(
                    instruments,
                    load_ratio=ratio,
                    iout_set=iout_set,
                    input_cond=input_cond,
                    output_cond=output_cond,
                    proto_label=proto_label,
                    vin_cfg=vin_cfg,
                )
                time.sleep(10.0)
                load_results.append(res)

            # ⑦ 计算 6 级平均（25/50/75/100%）和 7 级平均（10~100%）
            avg_6l = self._calc_avg_efficiency(
                [r for r in load_results if r["load_ratio"] in (0.25, 0.50, 0.75, 1.00)]
            )
            avg_7l = self._calc_avg_efficiency(load_results)

            # ⑧ 填 sub_results（含各点结论 + 平均能效 + 能效等级结论）
            self._add_loadpoint_results_with_avg(
                load_results=load_results,
                input_cond=input_cond,
                proto_label=proto_label,
                vout_target=round(vout_target, 3),
                iout_eff=iout_eff,
                avg_6l=avg_6l,
                avg_7l=avg_7l,
            )

            # ⑨ 该条件结束，标准下电
            self._step_discharge(ac, eload)

    # =================================================================
    # 功率分段辅助方法
    # =================================================================
    # =================================================================
    # 热机阶段
    # =================================================================

    def _find_warmup_condition(self, conditions: List[tuple]):
        logger.info(
            f"[_find_warmup_condition] power_segment={self.power_segment} "
            f"hv_power={self.hv_power} lv_power={self.lv_power}"
        )
        """
        从条件列表中筛选热机用的条件：

        筛选步骤：
          1. 仅保留输入电压 >= input_voltage_min 的条件
          2. 在满足 1 的条件中，优先选 PD 协议中输出电压最高的挡位
          3. 无 PD 协议时，选任意协议中输出电压最高的

        Returns:
            选中的条件 dict，无可用条件时返回 None
        """
        input_voltage_min = self.input_voltage_lo

        # 步骤 1：输入电压下限筛选（len(dict) 无法判断字段完整性，改用字段非 None 检查）
        valid_conds = [
            c for c in conditions
            if c.get("vin") is not None and c.get("vout") is not None
               and float(c.get("vin", 0)) >= input_voltage_min
        ]
        if not valid_conds:
            valid_conds = conditions

        # 功率分段启用时：优先选高压段条件（vin >= 180V），确保锁定 HV 功率段
        # 如果没有 HV 段条件，则用 LV 段最高功率条件
        if self._is_power_segment_enabled():
            hv_conds = [c for c in valid_conds if float(c.get("vin", 0)) >= 180]
            if hv_conds:
                valid_conds = hv_conds
                logger.info(
                    f"[EfficiencyTest] 功率分段已启用，筛选 HV 热机条件："
                    f"候选 {len(hv_conds)} 个（Vin≥180V）"
                )
            else:
                # HV 段为空，找 LV 段最高功率条件
                lv_conds = [c for c in valid_conds if float(c.get("vin", 0)) < 180]
                if lv_conds:
                    # 按功率 Vout×Iout 排序，选最大
                    chosen_lv = max(lv_conds, key=lambda c: float(c.get("vout", 0)) * float(c.get("iout", 0)))
                    valid_conds = [chosen_lv]
                    logger.info(
                        f"[EfficiencyTest] 功率分段 HV 段无候选，回选 LV 段最高功率条件："
                        f"{chosen_lv.get('proto', '')} {chosen_lv.get('vout')}V/{chosen_lv.get('iout')}A "
                        f"（功率={float(chosen_lv.get('vout', 0))*float(chosen_lv.get('iout', 0)):.0f}W）"
                    )

        # 步骤 2：在有效条件中找 PD 协议 + 输出电压最高的
        pd_conds = [(c, float(c.get("vout", 0))) for c in valid_conds if "PD" in str(c.get("proto", ""))]
        if not pd_conds:
            pd_conds = [(c, float(c.get("vout", 0))) for c in valid_conds]
        if not pd_conds:
            return None

        chosen_cond = max(pd_conds, key=lambda x: x[1])[0]
        logger.info(
            f"[EfficiencyTest] 热机条件筛选：Vin≥{input_voltage_min}V，"
            f"选中 {chosen_cond.get('proto', '')} {chosen_cond.get('vout')}V（候选 {len(pd_conds)} 个）"
        )
        return chosen_cond

    def _do_warmup(self, cond: tuple, instruments: Dict[str, Any]):
        """
        按筛选出的热机条件执行热机流程：

          ① 开机自检（用热机条件的输入电压，负载电流用UI配置值）
          ② 自检通过后，调诱骗器到热机输出电压
          ③ 切换到热机电流
          ④ 等待热机时间（self.params["warmup"]，由 UI 界面配置）
          ⑤ _step_discharge() 标准下电流程
          ⑥ 等待 2s 后返回

        热机时间默认 10min，UI 界面可配置。

        Returns:
            True = 热机成功，False = 开机自检失败，跳过全部测试
        """
        ac      = instruments.get("AC_SOURCE")
        eload   = instruments.get("ELOAD")
        sniffer = instruments.get("SNIFFER")

        vin_cfg, freq_cfg, proto_label, vout_target, iout_target = (
            cond.get("vin"), cond.get("freq"), cond.get("proto", ""),
            cond.get("vout"), cond.get("iout")
        )

        logger.info(
            f"[EfficiencyTest] 热机开始: Vin={vin_cfg}V / F={freq_cfg}Hz / "
            f"{proto_label} / Vout={vout_target}V / Iout={iout_target}A"
        )

        # ① 开机自检（直接用热机条件的输入电压/频率）
        logger.info(f"[EfficiencyTest] 热机开机自检...")
        startup_ok, _, fail_reason = self.startup_self_check(
            instruments, vin=vin_cfg, freq=freq_cfg
        )
        if not startup_ok:
            logger.warning(
                f"[EfficiencyTest] 热机开机自检失败: {fail_reason}，跳过热机和后续测试"
            )
            self._step_discharge(ac, eload)
            return False

        # ② 自检通过后，先调诱骗器到热机输出电压，再切热机电流
        self._step_setup_sniffer(sniffer, proto_label, vout_target, iout_target)

        # ③ 切换到热机电流（功率分段后）
        iout_warmup = self._get_effective_iout(vin_cfg, vout_target, iout_target)
        if eload and getattr(eload, "_connected", False):
            eload.set_mode_cc(float(iout_warmup))
            eload.input_on()
            logger.info(
                f"[EfficiencyTest] 热机电流切换至 {iout_warmup:.3f}A"
                + (f"（功率分段降流，原设定 {iout_target}A）" if iout_warmup != iout_target else "")
            )

        # ④ 等待热机时间（UI 配置，默认 10min）
        warmup_time = self.warmup * 60
        logger.info(f"[EfficiencyTest] 热机进行中 {warmup_time}s...")
        time.sleep(warmup_time)

        # ⑤ 标准下电流程
        self._step_discharge(ac, eload)

        # ⑥ 等待 2s 后再继续
        time.sleep(2.0)
        return True

    # =================================================================
    # 单个负载点测量
    #
    #   ① 电子负载设目标电流（CC 模式）
    #   ② 驱动自动选择并设置功率计电压/电流档位
    #      · CH1 电压：set_voltage_range_auto(ch, vin)
    #      · CH1 电流：set_current_range_auto(ch, max_pout/0.4/vin/0.4)
    #      · CH2 电压：set_voltage_range_auto(ch, vout)
    #      · CH2 电流：set_current_range_auto(ch, iout_set)
    #   ③ 读取功率计：Pin(CH1) → 循环10次均值
    #   ④ 读取功率计：Vout(CH2) + Iout(CH2)
    #   ⑤ 计算效率 η = (Vout × Iout) / Pin × 100%
    #   ⑥ 返回结果字典
    # =================================================================
    def _measure_load_point(
        self,
        instruments: Dict[str, Any],
        load_ratio: float,
        iout_set: float,
        input_cond: str,
        output_cond: str,
        proto_label: str,
        vin_cfg: float = None,
    ) -> dict:
        """
        测量单个负载点的效率并返回结果。

        测量分两步：
          第一步：根据输入电压/输入电流设置CH1采样范围，读取输入功率Pin
          第二步：根据输出电压/输出电流设置CH2采样范围，读取输出电压Vout和输出电流Iout

        Args:
            instruments:    仪器字典 {AC_SOURCE, ELOAD, SNIFFER, POWER_METER}
            load_ratio:    负载比例（0.10 ~ 1.00）
            iout_set:      额定输出电流（A）
            vin_cfg:       当前测试条件输入电压（V，用于输入端范围选择）
            input_cond:     仅用于日志
            output_cond:    仅用于日志
            proto_label:    仅用于日志

        Returns:
            dict: {load_ratio, iout_set, pin, vout, iout, efficiency}
        """
        # 步驌一：设置负载模式
        eload = instruments.get("ELOAD")
        if eload and getattr(eload, "_connected", False):
            eload.set_mode_cc(iout_set)

        pwr_in_ch  = self.params.get("pwr_in_v_ch", "CH1")
        pwr_out_ch = self.params.get("pwr_out_v_ch", "CH2")
        pin  = 0.0
        vout = 0.0
        iout = 0.0

        pm = instruments.get("POWER_METER")
        if pm and getattr(pm, "_connected", False):

            # ===== 第一步: 输入端(CH1) - 设置范围 + 读Pin =====
            # 根据输入电压选择输入端电压橱位
            if vin_cfg:
                pm.set_voltage_range_auto(pwr_in_ch, float(vin_cfg))
            # 根据换算的等效输入电流选择输入端电流量程
            max_pout = float(self.vout_target) * float(iout_set)
            # (Pout/效率/Vin/pf) × 1.414（电流尖峰系数）
            if vin_cfg:
                equiv_iin = (max_pout / self._EFFICIENCY / vin_cfg / self._PF) * self._IIN_SPIKE
            else:
                equiv_iin = 0.0
            pm.set_current_range_auto(pwr_in_ch, equiv_iin)

            # 第一步等待稳定 10s（支持暂停/停止）
            stable_sec = 10.0
            logger.info(f"[EfficiencyTest] 第一步等待稳定 {stable_sec}s ...")
            elapsed = 0.0
            while elapsed < stable_sec:
                if self.is_stop_requested():
                    break
                while self.is_pause_requested() and not self.is_stop_requested():
                    time.sleep(0.2)
                time.sleep(0.2)
                elapsed += 0.2

            # 读取输入功率(Pin) — 循环10次求平均（支持暂停/停止）
            pin_samples = []
            for _ in range(10):
                if self.is_stop_requested():
                    break
                while self.is_pause_requested() and not self.is_stop_requested():
                    time.sleep(0.2)
                try:
                    p = abs(pm.measure_power(channel=pwr_in_ch))
                    pin_samples.append(p)
                except Exception:
                    pass
                time.sleep(0.5)
            if pin_samples:
                pin = round(float(np.mean(pin_samples)), 3)
                logger.info(f"[EfficiencyTest] 负载点 {load_ratio*100:.0f}% | Pin={pin:.3f}W [CH1 输入端，10次均值，样本={len(pin_samples)}]")
            else:
                pin = 0.0
                logger.warning(f"[EfficiencyTest] Pin 读取失败，10次均无数据")

            # ===== 第二步: 输出端(CH2) - 设置范围 + 读Vout+Iout =====
            # 根据输出电压/电流选择输出端CH2范围
            pm.set_voltage_range_auto(pwr_out_ch, float(self.vout_target))
            pm.set_current_range_auto(pwr_out_ch, float(iout_set))

            # 第二步等待稳定 10s（支持暂停/停止）
            elapsed = 0.0
            while elapsed < 10.0:
                if self.is_stop_requested():
                    break
                while self.is_pause_requested() and not self.is_stop_requested():
                    time.sleep(0.2)
                time.sleep(0.2)
                elapsed += 0.2

            # 读取输出电压和电流（支持暂停/停止）
            if not self.is_stop_requested():
                try:
                    vout = abs(pm.measure_voltage(channel=pwr_out_ch))
                    iout = abs(pm.measure_current(channel=pwr_out_ch))
                    logger.info(f"[EfficiencyTest] 负载点 {load_ratio*100:.0f}% | Vout={vout:.3f}V Iout={iout:.3f}A [CH2 输出端]")
                except Exception as e:
                    logger.warning(f"[EfficiencyTest] Vout/Iout 读取失败: {e}")

        # 计算效率
        if pin > 0:
            efficiency = round((vout * iout) / pin * 100.0, 2)
        else:
            efficiency = 0.0

        logger.info(
            f"[EfficiencyTest] 负载点 {load_ratio*100:.0f}% | "
            f"Pin={pin:.3f}W Vout={vout:.3f}V Iout={iout:.3f}A η={efficiency:.3f}%"
        )

        return {
            "load_ratio": load_ratio,
            "iout_set":   iout_set,
            "pin":        pin,
            "vout":       vout,
            "iout":       iout,
            "efficiency": efficiency,
        }

    def _calc_avg_efficiency(self, load_results: List[dict]) -> float:
        """
        计算一组负载结果的平均效率（%）。

        仅统计 efficiency > 0 的有效结果。
        """
        effs = [r["efficiency"] for r in load_results if r["efficiency"] > 0]
        if not effs:
            return 0.0
        return round(sum(effs) / len(effs), 2)

    def _is_spec_valid(self, spec: dict) -> bool:
        """
        判断规格是否有效配置（不是 NA/空值）。
        spec 格式：{"lo": float|None, "hi": float|None}
        """
        if spec.get("lo") is None and spec.get("hi") is None:
            return False
        try:
            lo = float(spec.get("lo", 0))
            hi = float(spec.get("hi", 0))
            # lo==0 and hi==0 表示 UI 填了 0 或留空，等效于未配置
            return not (lo == 0 and hi == 0)
        except (ValueError, TypeError):
            return False

    def _is_6l_enabled(self) -> bool:
        """判断 UI 是否勾选 6 级能效。"""
        return bool(self.spec.get("6级能效要求_pct_enable", 0))


    def _is_7l_enabled(self) -> bool:
        """判断 UI 是否勾选 7 级能效。"""
        return bool(self.spec.get("7级能效要求_pct_enable", 0))


    def _calc_6l_spec(self, pout: float) -> float:
        """
        根据输出功率计算 6 级能效下限要求（%）。

        公式：
          0 < Pout ≤ 1W    : η ≥ 0.5 × Pout + 0.16
          1W < Pout ≤ 49W  : η ≥ 0.071 × ln(Pout) - 0.0014 × Pout + 0.67
          Pout > 49W       : η ≥ 0.88
        """
        import math
        if pout <= 0:
            return 0.0
        if pout <= 1.0:
            return 0.5 * pout + 0.16
        elif pout <= 49.0:
            return 0.071 * math.log(pout) - 0.0014 * pout + 0.67
        else:
            return 0.88

    def _calc_7l_spec(self, pout: float) -> float:
        """
        根据输出功率计算 7 级能效下限要求（%）。

        公式：
          Pout ≤ 49W   : η ≥ 0.071 × ln(Pout) - 0.00115 × Pout + 0.61
          Pout > 49W  : η ≥ 0.89
        """
        import math
        if pout <= 0:
            return 0.0
        if pout <= 49.0:
            return 0.071 * math.log(pout) - 0.00115 * pout + 0.61
        else:
            return 0.89

    # =================================================================
    # 结果记录
    # =================================================================

    def _add_all_loadpoint_results(
        self,
        input_cond: str,
        output_cond: str,
        proto_label: str,
        vout_target: float,
        iout_eff: float,
        skipped: bool,
        reason: str,
    ):
        """
        当测试条件失败（开机自检失败等）时，填入 5 个负载点的 SKIP 结果。
        """
        for ratio in self.LOAD_POINTS:
            self.sub_results.append(
                self._make_result(
                    input_cond=input_cond,
                    proto_label=proto_label,
                    vout_target=vout_target,
                    iout_target=iout_eff,
                    load_ratio=ratio,
                    iout_set=round(iout_eff * ratio, 3),
                    pin=0.0,
                    vout=0.0,
                    iout=0.0,
                    efficiency=0.0,
                    overall_pass=False,
                    fail_reason=reason,
                    skipped=skipped,
                    avg_6l=0.0,
                    avg_7l=0.0,
                    avg_pass_6l=False,
                    avg_pass_7l=False,
                    avg_req_6l_str="",
                    avg_req_7l_str="",
                )
            )

    def _add_loadpoint_results_with_avg(
        self,
        load_results: list,
        input_cond: str,
        proto_label: str,
        vout_target: float,
        iout_eff: float,
        avg_6l: float,
        avg_7l: float,
    ):
        """
        将 5 个负载点测量结果及 6 级/7 级平均能效填入 sub_results。

        判定规则：
          - 单负载点：用 6 级规格判定 PASS/FAIL
          - 6 级平均能效（avg_6l）：填入 50% 行，其余行为 0
          - 7 级平均能效（avg_7l）：填入 10% 行，其余行为 0
          - 如果 6 级/7 级规格为 NA（未勾选/未配置），对应结论列为 NA，不参与 overall_pass

        avg_req 显示规则（"平均能效要求"列）：
          - idx==2（50% 负载点）：显示 6 级平均能效要求，格式 "6级能效 XX.X%"
          - idx==0（100% 负载点）：显示 7 级平均能效要求，格式 "7级能效 XX.X%"
          - 其余行：显示 6 级平均能效要求（与 50% 行相同）
        """
        # 按输出功率计算规格（仅下限有意义，上限固定 100.0）
        # 使用 iout_eff（功率分段后的实际电流）计算输出功率
        pout = vout_target * iout_eff
        calc_6l = self._calc_6l_spec(pout) if self._is_6l_enabled() else None
        calc_7l = self._calc_7l_spec(pout) if self._is_7l_enabled() else None

        # 6级结论：公式计算有效则判定，否则 None（报告显示 NA）
        avg_pass_6l = (
            (avg_6l >= calc_6l)
            if (calc_6l is not None and avg_6l > 0)
            else None
        )

        # 7级结论
        avg_pass_7l = (
            (avg_7l >= calc_7l)
            if (calc_7l is not None and avg_7l > 0)
            else None
        )

        for idx, res in enumerate(load_results):
            eff = res["efficiency"]

            # 10% 负载点（idx==0）：仅由 7 级平均能效结论决定
            is_10pct = (res["load_ratio"] == 0.10)

            if is_10pct:
                # 10% 负载点：仅跟随 7 级平均结论（6 级不考核 10%）
                overall_pass = avg_pass_7l
                if overall_pass is False:
                    fail_reason = (
                        f"7级平均能效{avg_7l:.3f}%低于要求{calc_7l:.1f}%"
                        if calc_7l is not None else "7级平均能效未达标"
                    )
                else:
                    fail_reason = ""
            else:
                # 100% / 75% / 50% / 25% 负载点：跟随勾选的平均能效结论
                # 优先级：7级 > 6级（7级优先，更严格）
                if self._is_7l_enabled():
                    overall_pass = avg_pass_7l
                    if overall_pass is False:
                        fail_reason = (
                            f"7级平均能效{avg_7l:.3f}%低于要求{calc_7l:.1f}%"
                            if calc_7l is not None else "7级平均能效未达标"
                        )
                    else:
                        fail_reason = ""
                elif self._is_6l_enabled():
                    overall_pass = avg_pass_6l
                    if overall_pass is False:
                        fail_reason = (
                            f"6级平均能效{avg_6l:.3f}%低于要求{calc_6l:.1f}%"
                            if calc_6l is not None else "6级平均能效未达标"
                        )
                    else:
                        fail_reason = ""
                else:
                    # 均未勾选，所有负载点判 PASS
                    overall_pass = True
                    fail_reason = ""

            # avg_req 显示值：6 级要求填入 50% 行（idx==2），7 级填入 10% 行（idx==0）
            # calc_6l/calc_7l 是小数（如 0.785），需 ×100 转百分比
            avg_req_str_6l = f"6级能效 {calc_6l*100:.2f}%" if calc_6l is not None else ""
            avg_req_str_7l = f"7级能效 {calc_7l*100:.2f}%" if calc_7l is not None else ""

            self.sub_results.append(
                self._make_result(
                    input_cond=input_cond,
                    proto_label=proto_label,
                    vout_target=vout_target,
                    iout_target=iout_eff,
                    load_ratio=res["load_ratio"],
                    iout_set=res["iout_set"],
                    pin=res["pin"],
                    vout=res["vout"],
                    iout=res["iout"],
                    efficiency=res["efficiency"],
                    overall_pass=overall_pass,
                    fail_reason=fail_reason,
                    skipped=False,
                    avg_6l=avg_6l if idx == 2 else 0.0,
                    avg_pass_6l=avg_pass_6l if idx == 2 else None,
                    avg_7l=avg_7l if idx == 0 else 0.0,
                    avg_pass_7l=avg_pass_7l if idx == 0 else None,
                    avg_req_6l_str=avg_req_str_6l if idx == 2 else "",
                    avg_req_7l_str=avg_req_str_7l if idx == 0 else "",
                )
            )

    def _make_result(
        self,
        *,
        input_cond: str,
        proto_label: str,
        vout_target: float,
        iout_target: float,
        load_ratio: float,
        iout_set: float,
        pin: float,
        vout: float,
        iout: float,
        efficiency: float,
        overall_pass: bool,
        fail_reason: str,
        skipped: bool,
        avg_6l: float,
        avg_7l: float,
        avg_pass_6l,  # bool or None（None 表示未配置6级规格）
        avg_pass_7l,  # bool or None（None 表示未配置7级规格）
        avg_req_6l_str: str = "",
        avg_req_7l_str: str = "",
    ) -> dict:
        """
        组装单条测试结果（sub_result）。
        字段名即报告列名，直接对应 report_generator 的 COLS 定义。
        """
        return {
            "输入条件":           input_cond,
            "协议":              proto_label,
            "输出电压(V)":      vout_target,
            "输出电流(A)":      iout_target,
            "负载点":           f"{float(load_ratio)*100:.0f}%",
            "Iout设定(A)":      iout_set,
            "输入功率(W)":      pin,
            "测量电压(V)":      vout,
            "测量电流(A)":      iout,
            "效率(%)":          efficiency,
            "6级平均能效(%)":   avg_6l,
            "6级能效结论":      "PASS" if avg_pass_6l is True else ("FAIL" if avg_pass_6l is False else "NA"),
            "7级平均能效(%)":   avg_7l,
            "7级能效结论":      "PASS" if avg_pass_7l is True else ("FAIL" if avg_pass_7l is False else "NA"),
            "平均能效要求(%)":  avg_req_6l_str or avg_req_7l_str,
            "测试结论":        "SKIP" if skipped else ("PASS" if overall_pass is True else ("NA" if overall_pass is None else "FAIL")),
            "备注":            fail_reason,
            "overall_pass":    overall_pass,
            "fail_reason":     fail_reason,
            "skipped":         skipped,
        }

    # =================================================================
    # verify — 整体 PASS 判定
    # =================================================================
    def verify(self) -> bool:
        """
        能效测试整体 PASS 条件：
          - 所有负载点 overall_pass 为 True 或 SKIP
          - overall_pass 为 None（7 级未勾选时的 10% 点）不参与判定，视为通过
          - overall_pass 为 False 立即判 FAIL
        """
        if not self.sub_results:
            return False
        for r in self.sub_results:
            if r["skipped"]:
                continue
            if r["overall_pass"] is False:
                return False
            # overall_pass is True or None (NA) → continue
        return True
