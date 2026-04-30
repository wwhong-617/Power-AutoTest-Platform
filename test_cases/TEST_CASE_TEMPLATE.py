# -*- coding: utf-8 -*-
"""
TEST_CASE_TEMPLATE - 新测试用例模板
=====================================

本文档是添加新测试用例的参考模板。基于 InputVoltageRangeTest 的最佳实践编写。

【重要规则】
1. test_conditions 是 list[dict]，字段：vin / freq / proto / vout / iout
   → 使用 cond.get("vin")，永远不要用 cond[0]
2. __init__ 中不要设置 self.test_conditions（会 shadow 基类字段）
3. setup() 必须缓存所有需要用到的 params 为 self.xxx
4. execute() 中永远不调用 self.params.get()，只读缓存的 self.xxx
5. spec 字段：_lo/_hi/_pct/_pct_enable 后缀，会自动从 specs_v2 合并
6. protection_logic 字段：格式为 "类别_mode"，值 = "self"/"latch"/""

【新增用例步骤】
1. 在 test_engine.py 的 CASE_REGISTRY 中添加一行
2. 在对应目录创建本文件副本，命名为 YourTestName.py
3. 继承 TestCase，实现 setup() / execute() / verify()
4. 如需特殊报告列，在用例类中定义 COLS 列表
"""

import sys
import os
import time
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from test_cases.base import TestCase
from logger_config import info, warning


class YourTestNameTest(TestCase):
    """
    【中文用例名称】

    测试目标：
      - 描述测试验证什么

    test_conditions 格式（list[dict]）：
      [{vin, freq, proto, vout, iout}, ...]

    报告列（可选）：在 COLS 中定义，按顺序渲染
    COLS = [
        ("列标题", 宽度),
        ...
    ]
    """

    # ============================================================
    # 报告列定义（可选）
    # 顺序即 Excel 列顺序，按 COLS 顺序渲染所有列
    # ============================================================
    COLS = [
        ("输入条件",     16),
        ("协议",         14),
        ("输出电压(V)",  14),
        ("输出电流(A)",  14),
        ("规格下限",     11),
        ("规格上限",     11),
        ("实测值",       12),
        ("测试结论",     11),
        ("备注",         28),
    ]

    # ============================================================
    # __init__
    # ============================================================
    def __init__(self,
                 input_voltage_lo: float = 90.0,
                 input_voltage_hi: float = 264.0,
                 vout_spec_min: float = None,
                 vout_spec_max: float = None,
                 product_type: str = "charger",
                 test_conditions: List[dict] = None,
                 # ↓↓↓ 新参数在此添加，不要写 test_conditions ↓↓↓
                 your_param: float = None):
        """
        Args:
            input_voltage_lo:  输入电压下限（来自 UI 或配置）
            input_voltage_hi: 输入电压上限
            vout_spec_min:    输出电压规格下限（可选）
            vout_spec_max:    输出电压规格上限（可选）
            product_type:     "charger" 或 "adapter"
            test_conditions:  测试条件列表（list[dict]，由引擎注入）
            your_param:       你的新参数（示例）
        """
        # ⚠️ 重要：不要写 self.test_conditions = test_conditions or []
        # 这会 shadow 基类的 test_conditions 字段，导致 setup() 逻辑出错
        # test_conditions 由 setup() 通过 self.params.get("test_conditions", []) 获取

        super().__init__(
            name="YourTestNameTest",          # 英文类名 = CASE_REGISTRY 中的 key
            instruments=["AC_SOURCE", "ELOAD", "OSC", "SNIFFER", "POWER_METER"],
            params={
                "input_voltage_lo": input_voltage_lo,
                "input_voltage_hi": input_voltage_hi,
                "product_type": product_type,
                # ⚠️ 不要在这里传 test_conditions，
                # 让 setup() 从 self.params 读取
            },
            spec={
                "vout_min": vout_spec_min,
                "vout_max": vout_spec_max,
            }
        )

        # 新参数可以在此缓存（但不要缓存 test_conditions）
        self.your_param = your_param
        self.sub_results: List[dict] = []

    # ============================================================
    # setup() - 初始化（仅配置仪器，不上电）
    # ============================================================
    def setup(self, instruments: Dict[str, Any]):
        """
        初始化仪器状态，缓存所有需要用到的参数。

        【必须做的两件事】
        1. 调用 super().setup(instruments)
           → 初始化仪器连接
           → 将 specs_v2 合并到 self.spec
        2. 从 self.params 读取并缓存所有需要用到的参数

        【禁止事项】
        - 不要在这里上电（开机自检除外）
        - execute() 中永远不调用 self.params.get()
        - 不要设置 self.test_conditions（本类 __init__ 和基类已有）
        """
        self.sub_results = []
        super().setup(instruments)

        # ---- 缓存 UI / 引擎参数 ----
        # （这些值由 _inject_common_params 注入到 self.params）

        # 示波器通道（不带"CH"前缀）
        self.osc_input_ch   = int(self.params.get("osc_input_ch",   4))
        self.osc_output_ch  = int(self.params.get("osc_output_ch",  2))
        self.osc_dynamic_ch = int(self.params.get("osc_dynamic_ch", 2))

        # 示波器衰减
        self.osc_input_attn   = float(self.params.get("osc_input_attn",   1.0))
        self.osc_output_attn  = float(self.params.get("osc_output_attn",  1.0))
        self.osc_dynamic_attn = float(self.params.get("osc_dynamic_attn", 1.0))

        # 功率计通道
        self.pwr_in_v_ch  = self.params.get("pwr_in_v_ch",  "CH1")
        self.pwr_in_i_ch  = self.params.get("pwr_in_i_ch",  "CH1")
        self.pwr_out_v_ch = self.params.get("pwr_out_v_ch", "CH1")
        self.pwr_out_i_ch = self.params.get("pwr_out_i_ch", "CH1")

        # 产品信息
        self.input_voltage_lo = float(self.params.get("input_voltage_lo", 90.0))
        self.input_voltage_hi = float(self.params.get("input_voltage_hi", 264.0))
        self.product_type     = self.params.get("product_type", "charger")

        # 带载开机
        self.load_startup_enabled = bool(self.params.get("load_startup_enabled", False))
        self.load_startup_current = float(self.params.get("load_startup_current", 0.0))
        self.load_startup_voltage = float(self.params.get("load_startup_voltage", 5.0))

        # 功率分段
        self.power_segment = int(self.params.get("power_segment", 0))
        self.hv_power      = float(self.params.get("hv_power", 0.0))
        self.lv_power      = float(self.params.get("lv_power", 0.0))

        # 测试条件（由 filtered_conditions_v2[case_key] 注入）
        # 不要在 __init__ 中设置 self.test_conditions！
        # 使用 getattr + params.get 双重保护
        self.test_conditions = getattr(self, "test_conditions", []) or \
                               self.params.get("test_conditions", [])

        # 保护逻辑（来自 protection_logic_v2）
        # 格式：key = "类别_mode"，值 = "self"/"latch"/""
        self.protection_logic = self.params.get("protection_logic", {})

        # 预热时间（来自 test_params.warmup）
        self.warmup_time = self.params.get("warmup", "10")

        # 规格（由 base.py setup() 从 specs_v2 合并而来）
        # 使用 self.spec.get("字段名_lo") / self.spec.get("字段名_hi")
        # 例如：self.spec.get("电压精度_lo")

        # 自定义参数（示例）
        self.your_param = self.params.get("your_param", self.your_param)

        info(f"[YourTest] setup 完成 | "
             f"input_voltage={self.input_voltage_lo}~{self.input_voltage_hi}V | "
             f"product_type={self.product_type} | "
             f"conditions={len(self.test_conditions)} 条")

    # ============================================================
    # execute() - 测试主流程
    # ============================================================
    def execute(self, instruments: Dict[str, Any]):
        """
        执行测试逻辑。

        【标准流程模板】
        1. 获取仪器引用
        2. 遍历 test_conditions
        3. 每条条件：
           a. 开机自检（startup_self_check）
           b. 配置仪器
           c. 执行测量
           d. 记录结果（_add_result / _make_result）
           e. 放电下电
        4. 如需暂停/停止检查，在循环中调用 is_stop_requested() / is_pause_requested()

        【禁止事项】
        - 不要在循环内调用 self.params.get()，只读 setup() 缓存的 self.xxx
        - 不要用 cond[0] 访问条件，用 cond.get("vin")
        """
        ac      = instruments.get("AC_SOURCE")
        eload   = instruments.get("ELOAD")
        osc     = instruments.get("OSC")
        sniffer = instruments.get("SNIFFER")
        pwrmeter = instruments.get("POWER_METER")

        for cond in self.test_conditions:
            # ---- 获取当前条件参数（必须用 dict.get）----
            vin    = float(cond.get("vin",   0))
            freq   = float(cond.get("freq",  50.0))
            proto  = str(cond.get("proto",  ""))
            vout   = float(cond.get("vout",  5.0))
            iout   = float(cond.get("iout",  1.0))

            # 跳过无效条件
            if vin <= 0:
                warning(f"[YourTest] 无效条件 vin={vin}，跳过")
                continue

            input_cond = f"{int(vin)}V_{int(freq)}Hz"
            cond_label = f"{proto}_Vout{vout}V_Iout{iout}A"

            # ---- 暂停/停止检查 ----
            if self.is_stop_requested():
                info("[YourTest] 收到停止信号，终止执行")
                break
            while self.is_pause_requested() and not self.is_stop_requested():
                time.sleep(0.2)
            if self.is_stop_requested():
                break

            # ---- 步骤1：开机自检（可选）----
            startup_ok, measured_vout, fail_reason = self.startup_self_check(
                instruments, vin=vin, freq=freq
            )
            if not startup_ok:
                info(f"[YourTest] 条件「{cond_label}」开机失败：{fail_reason}，跳过")
                self._step_discharge(ac, eload)
                self._add_result(
                    input_cond=input_cond,
                    proto_label=proto,
                    vout_target=vout,
                    iout_target=iout,
                    spec_min=0,   # 根据实际修改
                    spec_max=999,  # 根据实际修改
                    measured=0.0,
                    overall_pass=False,
                    fail_reason=fail_reason,
                    skipped=True,
                )
                continue

            # ---- 步骤2：配置仪器（根据需要选择）----
            # 示波器 ROLL 模式（电压扫描类）
            # self._step_setup_osc_roll(osc, vout, duration_s, ch_in, ch_out)

            # 示波器纹波模式（纹波测试类）
            # self._step_setup_osc_ripple(osc, ch, "AC", ripple_spec_mv)

            # 诱骗器协议（charger 产品需要）
            # sniffer_ok = self._step_setup_sniffer(sniffer, proto, vout, iout)

            # 电子负载 CC 模式
            # self._step_setup_eload(eload, iout)

            # ---- 步骤3：执行测量 ----
            # （根据实际测试逻辑填充）

            measured = 0.0  # 示例占位

            # ---- 步骤4：汇总判定 ----
            spec_min = 0.0   # 根据实际修改
            spec_max = 999.0 # 根据实际修改
            is_pass = (spec_min <= measured <= spec_max)
            fail_reason = "" if is_pass else f"实测 {measured} 不在 [{spec_min}, {spec_max}] 范围内"

            self._add_result(
                input_cond=input_cond,
                proto_label=proto,
                vout_target=vout,
                iout_target=iout,
                spec_min=spec_min,
                spec_max=spec_max,
                measured=measured,
                overall_pass=is_pass,
                fail_reason=fail_reason,
                skipped=False,
            )

            # ---- 步骤5：放电下电 ----
            self._step_discharge(ac, eload, current=1.0, duration=1.0)

    # ============================================================
    # _add_result() - 记录单条测试结果
    # ============================================================
    def _add_result(self, *, input_cond: str,
                    proto_label: str, vout_target: float, iout_target: float,
                    spec_min: float, spec_max: float,
                    measured: float,
                    overall_pass: bool,
                    fail_reason: str,
                    skipped: bool):
        """
        将单条测试结果追加到 self.sub_results。

        字段名即报告列名，直接对应 report_generator 的 COLS 定义。

        Args:
            input_cond:     输入条件描述字符串（如 "220V_50Hz"）
            proto_label:    协议标签（如 "PD"、"QC3.0"）
            vout_target:    目标输出电压（V）
            iout_target:    目标输出电流（A）
            spec_min:       规格下限
            spec_max:       规格上限
            measured:       实测值
            overall_pass:   是否通过
            fail_reason:    失败原因（"" 表示通过）
            skipped:        是否跳过
        """
        result = {
            # ---- 报告列（与 COLS 定义对应）----
            "输入条件":     input_cond,
            "协议":         proto_label,
            "输出电压(V)":  vout_target,
            "输出电流(A)":  iout_target,
            "规格下限":     spec_min,
            "规格上限":     spec_max,
            "实测值":       measured,
            "测试结论":     "SKIP" if skipped else ("PASS" if overall_pass else "FAIL"),
            "备注":         fail_reason,
            # ---- 内部字段（用于 verify() 汇总）----
            "overall_pass": overall_pass,
            "fail_reason":  fail_reason,
            "skipped":      skipped,
        }
        self.sub_results.append(result)
        info(f"[YourTest] 结果 | {input_cond} | {proto_label} | "
             f"Vout={vout_target}V Iout={iout_target}A | "
             f"{'SKIP' if skipped else ('PASS' if overall_pass else 'FAIL')} | "
             f"{fail_reason}")

    # ============================================================
    # verify() - 汇总判定
    # ============================================================
    def verify(self) -> bool:
        """
        汇总所有 sub_results，返回整体 PASS/FAIL。

        规则：所有非跳过条件 overall_pass 为 True 才 PASS。
        如需特殊判定逻辑，在此覆盖。
        """
        if not self.sub_results:
            return False
        non_skipped = [r for r in self.sub_results if not r.get("skipped", False)]
        if not non_skipped:
            return False  # 全部跳过视为 FAIL
        return all(r["overall_pass"] for r in non_skipped)

    # ============================================================
    # teardown() - 清理恢复
    # ============================================================
    def teardown(self, instruments: Dict[str, Any]):
        """
        测试结束后恢复仪器状态。

        统一使用 _step_power_down() 进行完整下电：
        AC OFF → 短路放电2s → 负载 OFF → 短路释放
        """
        self._step_power_down(
            instruments.get("AC_SOURCE"),
            instruments.get("ELOAD"),
        )

        # 如有示波器，恢复普通模式
        osc = instruments.get("OSC")
        if osc:
            try:
                osc.set_timebase_mode("MAIN")
            except Exception:
                pass

    # ============================================================
    # to_dict() - 导出结果（供报告生成器使用）
    # ============================================================
    def to_dict(self) -> dict:
        """
        导出完整结果字典。

        子类覆盖时先调用 super().to_dict()，再补充 sub_results 等字段。
        """
        d = super().to_dict()
        d["sub_results"] = self.sub_results
        d["product_type"] = self.product_type

        # 汇总统计
        non_skipped = [r for r in self.sub_results if not r.get("skipped", False)]
        passed = sum(1 for r in non_skipped if r["overall_pass"])
        d["summary"] = {
            "conditions_tested": len(non_skipped),
            "passed_conditions": passed,
            "failed_conditions": len(non_skipped) - passed,
        }
        return d

    # ============================================================
    # 常用步骤方法速查（来自 base.py）
    # ============================================================
    #
    # self._step_discharge(ac, eload, current=1.0, duration=1.0)
    #     → AC OFF → 电子负载 CC 放电 → OFF
    #
    # self._step_power_down(ac, eload)
    #     → AC OFF → 短路放电2s → 负载 OFF → 短路释放
    #
    # self._step_power_off(ac, eload)
    #     → AC OFF + 负载 OFF（紧急下电，不放电）
    #
    # self.startup_self_check(instruments, vin=None, freq=None)
    #     → 开机自检（最多6次尝试），返回 (ok, measured_vout, reason)
    #
    # self._step_setup_sniffer(sniffer, proto_label, vout, iout)
    #     → 设置诱骗器协议（charger 专用），返回 bool
    #
    # self._step_setup_eload(eload, iout)
    #     → 电子负载 CC 模式上电
    #
    # self._step_setup_osc_roll(osc, vout, duration_s, ch_in, ch_out, ...)
    #     → 示波器 ROLL 模式（电压扫描类测试）
    #
    # self._step_setup_osc_ripple(osc, ch, coupling, ripple_spec_mv)
    #     → 示波器纹波模式（纹波测试）
    #
    # self._step_capture_and_measure(osc, ch_out, input_cond, proto, vout, iout)
    #     → 示波器 STOP → 测量 Vmax/Vmin → 保存波形 → 恢复采集
    #     → 返回 (osc_vmax, osc_vmin, wave_path)
    #
    # self._is_power_segment_enabled()
    #     → 判断是否启用高低压功率分段
    #
    # self._get_effective_iout(vin_cfg, vout_target, iout_target)
    #     → 根据功率分段计算实际输出电流
    #
    # self.is_stop_requested()
    #     → 查询是否收到停止请求
    #
    # self.is_pause_requested()
    #     → 查询是否收到暂停请求
