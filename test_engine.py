#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TestEngine - 测试执行引擎
===========================

将 TestSuite + TestCase 真正跑起来，并支持进度回调、暂停恢复。

Phase 1 核心模块。

主要功能：
- 根据配置加载测试用例（动态 import）
- 批量执行 / 单用例执行
- 进度回调（供 UI 进度条使用）
- 暂停 / 恢复 / 停止
- 执行结果汇总

用法示例：
    from test_engine import TestEngine

    engine = TestEngine(config, instruments_dict)
    engine.load_cases_from_config(config["test_cases"])

    # 带进度回调
    def on_progress(case_name, result, index, total):
        print(f"[{index}/{total}] {case_name}: {result}")
    engine.set_progress_callback(on_progress)

    # 批量执行
    results = engine.run_all()

    # 汇总
    summary = engine.get_summary()
    print(summary)
"""

import time
import threading
import os
import importlib
import pkgutil
from typing import Dict, Any, List, Optional, Callable
from enum import Enum

from test_cases.base import TestSuite, TestCase, TestResult
from logger_config import logger, info, warning, error

# 可导入的测试用例模块前缀
TEST_CASE_MODULE_PREFIX = "test_cases."


class EngineState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    FINISHED = "FINISHED"


class TestEngine:
    """
    测试执行引擎。

    管理 TestSuite 的加载和执行，支持：
    - 动态从配置加载测试用例
    - 批量执行和单个执行
    - 进度回调（实时推送 UI 更新）
    - 暂停 / 恢复 / 停止控制
    """

    # ============================================================
    # 用例注册表（唯一数据源）
    # - key: 用例英文名
    # - value: dict，字段：
    #     module: str，模块路径
    #     voltage_segment: bool，是否按 (proto,vout,iout) 分组后取最高 Vin
    #     cn_name: str，中文显示名
    # 注意：新增用例只需在此处添加一行，其他映射表自动同步
    # ============================================================
    CASE_REGISTRY = {
        # input_tests
        "InputVoltageRangeTest":    {"module": "test_cases.input_tests.InputVoltageRangeTest",    "voltage_segment": True,  "cn_name": "输入电压范围测试"},
        "InputUnderVoltageTest":   {"module": "test_cases.input_tests.InputUnderVoltageTest",   "voltage_segment": False, "cn_name": "输入欠压测试"},
        "InputDipTest":            {"module": "test_cases.input_tests.InputDipTest",            "voltage_segment": True,  "cn_name": "输入跌落测试"},
        "InputNoLoadPowerTest":    {"module": "test_cases.input_tests.InputNoLoadPowerTest",    "voltage_segment": False, "cn_name": "输入空载功率测试"},
        "InputEfficiencyTest":     {"module": "test_cases.input_tests.InputEfficiencyTest",     "voltage_segment": False, "cn_name": "输入效率测试"},
        # output_tests
        "OutputPowerOnOffTest":    {"module": "test_cases.output_tests.OutputPowerOnOffTest",    "voltage_segment": False, "cn_name": "输出开关机测试"},
        "OutputRippleNoiseTest":   {"module": "test_cases.output_tests.OutputRippleNoiseTest",   "voltage_segment": False, "cn_name": "输出纹波噪声测试"},
        "OutputRippleLoadScanTest": {"module": "test_cases.output_tests.OutputRippleLoadScanTest", "voltage_segment": False, "cn_name": "输出纹波负载扫描测试"},
        "OutputRippleInputScanTest": {"module": "test_cases.output_tests.OutputRippleInputScanTest", "voltage_segment": True,  "cn_name": "输出纹波输入扫描测试"},
        "OutputDynamicTest":       {"module": "test_cases.output_tests.OutputDynamicTest",       "voltage_segment": False, "cn_name": "输出动态测试"},
        # protection_tests
        "OutputOcpProtectTest":    {"module": "test_cases.protection_tests.OutputOcpProtectTest",    "voltage_segment": False, "cn_name": "输出过流保护测试"},
        "OutputScpProtectTest":    {"module": "test_cases.protection_tests.OutputScpProtectTest",    "voltage_segment": False, "cn_name": "输出短路保护测试"},
        # protocol_tests
        "PDProtocolTest":   {"module": "test_cases.protocol_tests.PDProtocolTest",   "voltage_segment": False, "cn_name": "PD协议"},
        "QCProtocolTest":  {"module": "test_cases.protocol_tests.QCProtocolTest",  "voltage_segment": False, "cn_name": "QC协议"},
        "AFCProtocolTest": {"module": "test_cases.protocol_tests.AFCProtocolTest", "voltage_segment": False, "cn_name": "AFC协议"},
        "FCPProtocolTest": {"module": "test_cases.protocol_tests.FCPProtocolTest", "voltage_segment": False, "cn_name": "FCP协议"},
    }

    # 从 REGISTRY 派生：case_key -> 中文名
    CASE_CN_NAMES = {k: v["cn_name"] for k, v in CASE_REGISTRY.items()}

    # 从 REGISTRY 派生：case_key -> 模块路径字符串（兼容旧接口）
    CASE_MODULE_MAP = {k: v["module"] for k, v in CASE_REGISTRY.items()}

    def __init__(self, config: Dict[str, Any], instruments: Dict[str, Any], instrument_manager=None):
        """
        Args:
            config:     完整配置字典（来自 test_config.json）
            instruments: 仪器实例字典，key 如 "ELOAD", "OSC"
        """
        self.config = config
        self.instruments = instruments
        self.suite = TestSuite("Auto Test Suite")

        # 状态控制
        self._state = EngineState.IDLE
        self._stop_requested = False
        self._pause_requested = False
        self._stop_event = threading.Event()

        # 仪器管理器引用（用于 stop 时断开所有仪器）
        self._instrument_mgr = instrument_manager

        # 进度回调
        self._progress_callback: Optional[Callable] = None
        self._log_callback: Optional[Callable] = None

        # 执行结果（持久化）
        self._results: List[TestCase] = []

        # 用例对象池（已加载的用例实例）
        self._case_instances: Dict[str, TestCase] = {}

        # 结果文件夹路径（由 config_ui 注入）
        self._result_dir: str = None

        info("[TestEngine] 初始化完成")

    # ---------------------- 配置加载 ----------------------

    def load_cases_from_config(self, test_cases_config: Dict[str, Dict[str, bool]]):
        """
        根据配置加载测试用例。

        Args:
            test_cases_config 格式：
            {
                "input_tests": {"EfficiencyTest": True, "StandbyPowerTest": False},
                "output_tests": {"RippleNoiseTest": True},
                ...
            }
        """
        info("[TestEngine] 开始加载测试用例")

        total_loaded = 0
        for category, cases in test_cases_config.items():
            if not isinstance(cases, dict):
                continue
            for case_key, enabled in cases.items():
                if not enabled:
                    continue  # 未启用的跳过

                case = self._load_single_case(case_key)
                if case:
                    self.suite.add(case)
                    total_loaded += 1
                    info(f"[TestEngine] 加载用例: {case.name}")

        info(f"[TestEngine] 共加载 {total_loaded} 个测试用例")

    def _load_single_case(self, case_key: str) -> Optional[TestCase]:
        """
        动态加载单个测试用例。
        
        流程：
        1. 若已有模板，直接创建新实例返回
        2. 若无模板，创建并存储（不配置），然后创建新实例返回
        
        注意：配置只在 _create_fresh_instance 中进行，此处不配置模板。
        """
        if case_key in self._case_instances:
            return self._create_fresh_instance(self._case_instances[case_key])

        module_path = self.CASE_MODULE_MAP.get(case_key)
        if not module_path:
            warning(f"[TestEngine] 未知用例: {case_key}，跳过")
            return None

        try:
            mod = importlib.import_module(module_path)
            class_name = module_path.rsplit(".", 1)[-1]
            cls = getattr(mod, class_name, None)
            if cls is None:
                warning(f"[TestEngine] 模块 {module_path} 中未找到类 {class_name}")
                return None

            instance = cls()
            self._case_instances[case_key] = instance
            return self._create_fresh_instance(instance)

        except Exception as e:
            error(f"[TestEngine] 加载用例 {case_key} 失败: {e}")
            return None

    def _create_fresh_instance(self, template: TestCase) -> TestCase:
        """
        从模板创建新实例（避免重复使用同一个实例导致状态污染）。
        
        这是唯一的配置入口：所有用例配置都在此处进行。
        新增用例需在此添加对应的配置调用。
        """
        case_key = None
        for k, v in self.CASE_REGISTRY.items():
            if v["module"].rsplit(".", 1)[-1] == template.__class__.__name__:
                case_key = k
                break

        if case_key:
            try:
                mod_path = self.CASE_MODULE_MAP[case_key]
                mod = importlib.import_module(mod_path)
                cls = getattr(mod, template.__class__.__name__)
                instance = cls()
                instance.name = case_key  # 让 to_dict() 能拿到正确的英文名，供报告生成器查找 COLS

                # 统一注入所有参数（通用 + 专用）
                self._inject_common_params(instance, case_key)

                return instance
            except Exception as e:
                warning(f"[TestEngine] 创建用例实例失败: {e}")

        return template  # 兜底返回模板

    def _inject_common_params(self, case: TestCase, case_key: str = None):
        """
        引擎只做透传：将 v2 原始配置塞入 case.params，
        各 case 自己解析需要什么参数。
        """
        test_settings = self.config.get("test_settings", {})
        test_params   = self.config.get("test_params", {})
        product_info  = self.config.get("product_info", {})
        # config_ui 保存的是 test_conditions_v2（per-case 字典），引擎直接按 case_key 取用
        all_conditions = self.config.get("test_conditions_v2", {})

        # ---- 通用参数（所有 case 都有）----
        for ch_key, attn_key, param_ch, param_attn in [
            ("osc_input_ch",   "osc_input_attn",   "osc_input_ch",   "osc_input_attn"),
            ("osc_output_ch",  "osc_output_attn",  "osc_output_ch",  "osc_output_attn"),
            ("osc_dynamic_ch", "osc_dynamic_attn", "osc_dynamic_ch", "osc_dynamic_attn"),
        ]:
            ch   = test_settings.get(ch_key,   "CH2")
            attn = float(test_settings.get(attn_key, "1.0"))
            case.params[param_ch]   = ch.upper().replace("CH", "")
            case.params[param_attn] = attn

        for k in (("pwr_in_i_ch",  "pwr_in_i_ch"),
                  ("pwr_in_v_ch",  "pwr_in_v_ch"),
                  ("pwr_out_v_ch", "pwr_out_v_ch"),
                  ("pwr_out_i_ch", "pwr_out_i_ch")):
            case.params[k[1]] = test_params.get(k[0], "CH1")

        case.params["load_startup_enabled"] = bool(product_info.get("load_startup_enabled", False))
        case.params["load_startup_current"] = float(product_info.get("load_startup_current", 0.0) or 0.0)
        case.params["load_startup_voltage"] = float(product_info.get("load_startup_voltage", 0.0) or 0.0)

        dut = self.config.get("dut", {})
        if dut:
            case.params.setdefault("dut_name",       dut.get("name", ""))
            case.params.setdefault("dut_model",      dut.get("model", ""))
            case.params.setdefault("input_voltage",  dut.get("output_voltage", 220))
            case.params.setdefault("output_voltage", dut.get("output_voltage", 12.0))
            case.params.setdefault("output_current", dut.get("output_current", 3.0))
            if "efficiency_min" in case.spec and not case.spec.get("efficiency_min"):
                case.spec["efficiency_min"] = dut.get("target_efficiency", 85.0)

        case.params.setdefault("input_voltage_lo", float(product_info.get("input_voltage_lo", 90.0)))
        case.params.setdefault("input_voltage_hi", float(product_info.get("input_voltage_hi", 264.0)))

        case.params["power_segment"] = int(product_info.get("power_segment", 0) or 0)
        case.params["hv_power"] = float(product_info.get("hv_power") or 0.0)
        case.params["lv_power"] = float(product_info.get("lv_power") or 0.0)

        # ---- 动态测试参数 ----
        case.params["dyn_large_settings"] = test_params.get("dyn_large", [])
        case.params["dyn_small_settings"] = test_params.get("dyn_small", [])

        if self._result_dir:
            case.params["result_dir"] = self._result_dir
            case.params["osc_waveform_dir"] = os.path.join(self._result_dir, "测试波形")

        # ---- 用例专用透传（直接塞原始 v2 数据，不解析）----
        if case_key is None:
            return

        # 条件已由 _build_test_engine_config 按 case_key 分好，直接取用
        cond_list = all_conditions.get(case_key, [])

        # config_ui 存的是 dict列表，直接送
        case.params["test_conditions"] = cond_list
        case.params["product_type"]    = product_info.get("product_type", "charger")
        case.params["test_params"]     = test_params
        case.params["product_info"]     = product_info
        # InputEfficiencyTest needs the raw specs_v2 dict for 6级/7级能效判断
        case.params["specs"]            = product_info.get("specs_v2", {})
        # protection_logic_v2: {"输出过流保护_mode": "self"|"latch"|"", ...}
        case.params["protection_logic"] = self.config.get("product_info", {}).get("protection_logic_v2", {})
        # warmup from test_params, lifted to top-level for convenience
        case.params["warmup"]          = test_params.get("warmup", "10")

    def set_progress_callback(self, callback: Callable):
        """设置进度回调: callback(case_name, result, index, total, case)
        新版传入TestCase实例，包含measurements、duration、params等详细信息"""
        self._progress_callback = callback

    def set_log_callback(self, callback: Callable):
        """设置日志回调: callback(level, message)"""
        self._log_callback = callback

    def set_result_dir(self, result_dir: str):
        """设置结果文件夹路径（供测试用例保存波形等文件）"""
        self._result_dir = result_dir

    def run_all(self) -> List[TestCase]:
        """
        批量执行所有用例。
        Returns:
            结果列表
        """
        if self._state == EngineState.RUNNING:
            warning("[TestEngine] 引擎已在运行中，忽略重复调用")
            return self._results

        self._state = EngineState.RUNNING
        self._stop_requested = False
        self._pause_requested = False
        self._stop_event.clear()
        self._results = []

        total = len(self.suite.cases)
        info(f"[TestEngine] 开始批量执行，共 {total} 个用例")

        for idx, case in enumerate(self.suite.cases, 1):
            if self._stop_requested or self._stop_event.is_set():
                info(f"[TestEngine] 收到停止信号，终止执行")
                self._state = EngineState.STOPPED
                break

            # 暂停逻辑
            while self._pause_requested and not self._stop_requested and not self._stop_event.is_set():
                time.sleep(0.2)

            # 执行单个用例
            self._run_single_case(case, idx, total)

        if not self._stop_requested and not self._stop_event.is_set():
            self._state = EngineState.FINISHED
            info(f"[TestEngine] 全部执行完成")

        # 所有退出路径统一重置为 IDLE，允许下次重新运行
        if self._state != EngineState.RUNNING:
            self._state = EngineState.IDLE

        return self._results

    def run_single(self, case_key: str) -> Optional[TestCase]:
        """
        执行指定用例。
        Args:
            case_key: 用例名称（英文名）
        Returns:
            TestCase 实例或 None
        """
        if self._state == EngineState.RUNNING:
            warning("[TestEngine] 引擎已在运行中，忽略重复调用")
            return None

        self._state = EngineState.RUNNING
        self._stop_requested = False
        self._stop_event.clear()

        case = self._load_single_case(case_key)
        if case is None:
            error(f"[TestEngine] 用例 {case_key} 加载失败")
            self._state = EngineState.IDLE
            return None

        self._run_single_case(case, 1, 1)
        self._state = EngineState.IDLE
        return case

    def _run_single_case(self, case: TestCase, idx: int, total: int):
        """执行单个用例（内部方法）"""
        name = case.name
        info(f"[TestEngine] [{idx}/{total}] 执行: {name}")

        if self._log_callback:
            self._log_callback("INFO", f"[{idx}/{total}] 开始: {name}")

        try:
            case._engine = self   # 注入引擎引用，供用例查询暂停/停止状态
            case.run(self.instruments)
            result = case.result.value

            # 如果是 ERROR 状态但没有异常上抛，说明 case.run() 内部已捕获，打印 error_message
            if result == "ERROR" and getattr(case, "error_message", None):
                error(f"[TestEngine] [{idx}/{total}] 完成: {name} -> ERROR | {case.error_message}")
                if self._log_callback:
                    self._log_callback("ERROR", f"[{idx}/{total}] {name} ERROR: {case.error_message}")
            else:
                info(f"[TestEngine] [{idx}/{total}] 完成: {name} -> {result}")
                if self._log_callback:
                    self._log_callback("INFO", f"[{idx}/{total}] {name}: {result}")

        except Exception as e:
            import traceback as tb
            tb_str = tb.format_exc()
            case.result = TestResult.ERROR
            case.error_message = str(e)
            case.traceback = tb_str
            error(f"[TestEngine] [{idx}/{total}] 异常: {name} -> {e}\n{tb_str}")
            if self._log_callback:
                self._log_callback("ERROR", f"[{idx}/{total}] {name} 异常: {e}")

        self._results.append(case)

        if self._progress_callback:
            try:
                self._progress_callback(name, case.result.value, idx, total, case)
            except Exception as e:
                warning(f"[TestEngine] 进度回调异常: {e}")

    def pause(self):
        """请求暂停（下一个用例开始前生效）"""
        if self._state == EngineState.RUNNING:
            self._pause_requested = True
            self._state = EngineState.PAUSED
            info("[TestEngine] 暂停请求已发送")

    def resume(self):
        """恢复执行"""
        if self._state == EngineState.PAUSED:
            self._pause_requested = False
            self._state = EngineState.RUNNING
            info("[TestEngine] 恢复执行")

    def stop(self):
        """请求停止（设置停止事件并断开所有仪器，立即中断当前操作）"""
        self._stop_requested = True
        self._pause_requested = False
        self._stop_event.set()
        # 立即断开所有仪器，中断任何阻塞的 VISA 操作
        if self._instrument_mgr:
            self._instrument_mgr.disconnect_all()
        info("[TestEngine] 停止请求已发送，仪器正在断开")

    @property
    def state(self) -> EngineState:
        return self._state

    # ---------------------- 结果汇总 ----------------------

    def get_summary(self) -> Dict[str, Any]:
        """获取执行结果汇总"""
        if not self._results:
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "pass_rate": "0%",
                "state": self._state.value,
            }

        total = len(self._results)
        passed = sum(1 for c in self._results if c.result == TestResult.PASS)
        failed = sum(1 for c in self._results if c.result == TestResult.FAIL)
        errors = sum(1 for c in self._results if c.result == TestResult.ERROR)
        skipped = sum(1 for c in self._results if c.result == TestResult.SKIP)

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "pass_rate": f"{passed/total*100:.1f}%" if total else "0%",
            "state": self._state.value,
        }

    def get_results(self) -> List[Dict[str, Any]]:
        """获取所有用例的执行结果（字典格式，方便 UI 展示）"""
        return [case.to_dict() for case in self._results]

    def export_results(self, path: str):
        """将结果导出为 JSON 文件"""
        import json
        data = {
            "summary": self.get_summary(),
            "results": self.get_results(),
            "export_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        info(f"[TestEngine] 结果已导出: {path}")
