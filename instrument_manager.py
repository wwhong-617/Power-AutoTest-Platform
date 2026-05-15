#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instrument Manager - 仪器管理器
================================

统一管理所有仪器的连接/断开/重连。

仪器 Key 映射（与 config_ui.py 和 test_cases/base.py 一致）：
    "OSC"           - 示波器
    "ELOAD"         - 电子负载
    "POWER_METER"   - 功率计
    "SNIFFER"       - 协议诱骗器
    "AC_SOURCE"     - 交流源
    "DC_SOURCE"    - 直流电源

用法示例：
    from instrument_manager import InstrumentManager

    mgr = InstrumentManager()
    mgr.load_from_config(config)       # 从 UI 配置加载
    results = mgr.connect_all()         # 连接所有仪器
    print(mgr.summary())               # 连接结果汇总

    instruments = mgr.get_instruments() # 获取仪器字典

    mgr.disconnect_all()               # 断开所有仪器
"""

import time
from typing import Dict, Any, List, Optional, Tuple

from logger_config import logger, info, warning, error
from instruments.base import InstrumentConnectionState, InstrumentError

# =====================================================================
# 动态仪器驱动映射
# 每个仪器子包的 __init__.py 提供 DRIVER_MAP = {"型号": Class, ...}
# _get_model_class_map() 在首次调用时构建并缓存 {category: {model: Class}}
# =====================================================================

_MODEL_CLASS_MAP = None  # 类级别缓存


def _get_model_class_map():
    """
    构建并缓存 {category: {model_name: DriverClass}} 映射表。
    从各仪器子包的 __init__.py 动态读取 DRIVER_MAP。
    """
    global _MODEL_CLASS_MAP
    if _MODEL_CLASS_MAP is not None:
        return _MODEL_CLASS_MAP

    _MODEL_CLASS_MAP = {}
    category_modules = {
        "electronic_load": "instruments.electronic_load",
        "ac_source":      "instruments.ac_source",
        "dc_source":      "instruments.dc_source",
        "power_meter":    "instruments.power_meter",
        "oscilloscope":   "instruments.oscilloscope",
        "sniffer":        "instruments.sniffer",
    }

    for cat, mod_path in category_modules.items():
        try:
            mod = __import__(mod_path, fromlist=["DRIVER_MAP"])
            driver_map = getattr(mod, "DRIVER_MAP", {})
            _MODEL_CLASS_MAP[cat] = driver_map
        except Exception as e:
            warning(f"[InstrumentManager] 加载 {cat} 驱动映射失败: {e}")
            _MODEL_CLASS_MAP[cat] = {}

    return _MODEL_CLASS_MAP


class InstrumentManager:
    """
    仪器管理器。
    负责：根据配置创建仪器实例、连接、持有引用、按 Key 分发。
    """

    # 仪器配置 key → (驱动模块路径, instrument_key, is_sniffer)
    # class 名不再写死，由 _get_model_class_map()[category][model] 动态解析
    _CATEGORY_DRIVER_MAP = {
        "oscilloscope":    ("instruments.oscilloscope",    "OSC",           False),
        "electronic_load": ("instruments.electronic_load",  "ELOAD",         False),
        "power_meter":    ("instruments.power_meter",     "POWER_METER",   False),
        "sniffer":         ("instruments.sniffer",         "SNIFFER",       True),
        "ac_source":      ("instruments.ac_source",       "AC_SOURCE",     False),
        "dc_source":      ("instruments.dc_source",       "DC_SOURCE",     False),
    }

    # 所有合法的仪器 key
    VALID_KEYS = {v[1] for v in _CATEGORY_DRIVER_MAP.values()}

    def __init__(self):
        self._instruments: Dict[str, Any] = {}       # key -> instance
        self._config: Dict[str, Any] = {}           # 原始配置副本
        self._connection_results: Dict[str, bool] = {}  # key -> connected?
        self._simulation_mode = False
        self._connection_callback = None  # (key, state, detail) -> None

    def set_connection_callback(self, callback):
        """
        设置连接进度回调。

        callback 签名：
            callback(key: str, state: InstrumentConnectionState, detail: str)

        在连接过程中会被多次调用，上报每台仪器每一步的状态。
        """
        self._connection_callback = callback

    def load_from_config(self, config: Dict[str, Any]):
        """
        从 UI 配置字典加载仪器信息。
        config 格式参考 test_config.json 中的仪器配置段。
        """
        self._config = config
        info(f"[InstrumentManager] 开始加载仪器配置")

        model_map = _get_model_class_map()

        for cfg_key, (mod_path, inst_key, is_sniffer) in self._CATEGORY_DRIVER_MAP.items():
            inst_cfg = config.get(cfg_key, {})
            if not inst_cfg:
                warning(f"[InstrumentManager] {cfg_key} 无配置，跳过")
                continue

            # 检查是否启用（有些仪器在 config 中可能没有 enabled 字段，默认 True）
            enabled = inst_cfg.get("enabled", True)
            if enabled is False:
                info(f"[InstrumentManager] {cfg_key} 未启用，跳过")
                continue

            # 兼容新旧两种配置格式：
            #   新格式：conn_type / visa_address（config_ui 扫描后写入）
            #   旧格式：comm / addr（直接编辑配置文件时使用）
            conn_type = inst_cfg.get("conn_type", "").strip()
            if not conn_type:
                conn_type = inst_cfg.get("comm", "").strip()
            address = inst_cfg.get("visa_address", "").strip()
            if not address:
                address = inst_cfg.get("addr", "").strip()

            if not address:
                warning(f"[InstrumentManager] {cfg_key} 无地址，跳过")
                continue

            # 根据配置的 model 查找对应的驱动类名（从动态 DRIVER_MAP 查询）
            model = inst_cfg.get("model", "")
            cat_map = model_map.get(cfg_key, {})
            if model and model in cat_map:
                actual_cls_name = model
                info(f"[InstrumentManager] {cfg_key} 型号: {model} -> {actual_cls_name}")
            elif cat_map:
                first_cls = next(iter(cat_map.keys()))
                actual_cls_name = first_cls
                info(f"[InstrumentManager] {cfg_key} 型号 \"{model}\" 未映射，降级使用: {first_cls}")
            else:
                warning(f"[InstrumentManager] {cfg_key} 无可用驱动类，跳过")
                continue

            # 创建仪器实例
            self._create_instrument(cfg_key, mod_path, actual_cls_name, inst_key,
                                   is_sniffer, conn_type, address, inst_cfg)

            # 示波器额外写入通道配置（从 UI test_settings 读取）
            if cfg_key == "oscilloscope":
                osc = self._instruments.get("OSC")
                if osc:
                    ts = config.get("test_settings", {})
                    osc._osc_ch_config = {
                        "osc_input_ch":    ts.get("osc_input_ch",    "CH4"),
                        "osc_output_ch":   ts.get("osc_output_ch",   "CH2"),
                        "osc_dynamic_ch":  ts.get("osc_dynamic_ch",  "CH1"),
                        "osc_input_attn":   float(ts.get("osc_input_attn",   "1.0")),
                        "osc_output_attn":  float(ts.get("osc_output_attn",  "1.0")),
                        "osc_dynamic_attn": float(ts.get("osc_dynamic_attn",  "1.0")),
                    }
                    info(f"[InstrumentManager] OSC 通道配置已写入: {osc._osc_ch_config}")
                    info(f"[InstrumentManager] 原始 test_settings: osc_input_ch={ts.get('osc_input_ch')}, osc_input_attn={ts.get('osc_input_attn')}, osc_output_ch={ts.get('osc_output_ch')}, osc_output_attn={ts.get('osc_output_attn')}")

    def _create_instrument(self, cfg_key: str, mod_path: str, cls_name: str,
                          inst_key: str, is_sniffer: bool,
                          conn_type: str, address: str, inst_cfg: Dict):
        """动态加载并创建仪器实例"""
        try:
            # 动态 import 驱动模块
            mod = __import__(mod_path, fromlist=[cls_name])
            driver_cls = getattr(mod, cls_name)

            if is_sniffer:
                # IP2716Sniffer 使用 pyserial，接口特殊：port, slave_addr, timeout_ms
                port = self._normalize_com_port(address)
                slave_addr = inst_cfg.get("slave_addr", 1)
                timeout_ms = inst_cfg.get("timeout_ms", 2000)

                if self._simulation_mode:
                    inst = driver_cls(port=port, slave_addr=slave_addr,
                                      timeout_ms=timeout_ms, simulation=True)
                else:
                    inst = driver_cls(port=port, slave_addr=slave_addr,
                                      timeout_ms=timeout_ms)
                info(f"[InstrumentManager] {inst_key} 实例已创建: {driver_cls.__name__} @ {port}")

            else:
                # 标准 SCPI 仪器：conn_type, visa_address, timeout_ms
                visa_addr = self._make_visa_address(conn_type, address, cfg_key)
                timeout_ms = inst_cfg.get("timeout_ms", 5000)

                if self._simulation_mode:
                    if cfg_key == "electronic_load":
                        inst = driver_cls(conn_type=conn_type.upper(),
                                          address=visa_addr, timeout_ms=timeout_ms,
                                          channel=inst_cfg.get("channel", 1))
                        inst.enable_simulation(f"SIMULATION_{inst_key}")
                    else:
                        inst = driver_cls(conn_type=conn_type.upper(),
                                          address=visa_addr, timeout_ms=timeout_ms)
                        inst.enable_simulation(f"SIMULATION_{inst_key}")
                else:
                    if cfg_key == "electronic_load":
                        inst = driver_cls(conn_type=conn_type.upper(),
                                          address=visa_addr, timeout_ms=timeout_ms,
                                          channel=inst_cfg.get("channel", 1))
                    else:
                        inst = driver_cls(conn_type=conn_type.upper(),
                                          address=visa_addr, timeout_ms=timeout_ms)
                    info(f"[InstrumentManager] {inst_key} 实例已创建: {driver_cls.__name__}")

            self._instruments[inst_key] = inst

        except Exception as e:
            error(f"[InstrumentManager] 创建 {cfg_key} 失败: {e}")
            import traceback
            traceback.print_exc()

    def _normalize_com_port(self, address: str) -> str:
        """
        将配置中的 COM 地址正规化。
        "COM3" -> "COM3"
        "3"    -> "COM3"
        "com5" -> "COM5"
        """
        addr = address.strip().upper()
        if not addr.startswith("COM"):
            addr = f"COM{addr}"
        return addr

    def _make_visa_address(self, conn_type: str, address: str, cfg_key: str) -> str:
        """
        将配置地址转换为 VISA 地址字符串。
        """
        ct = conn_type.upper()
        addr = address.strip()

        if ct == "TCPIP":
            # TCPIP: "192.168.1.100" -> "TCPIP0::192.168.1.100::inst0::INSTR"
            return f"TCPIP0::{addr}::inst0::INSTR"
        elif ct == "USB":
            # USB 地址通常已经是一个完整的 VISA 地址字符串
            return addr
        elif ct == "COM":
            # RS232: "COM3" -> "ASRL3::INSTR"
            com_num = addr.upper().replace("COM", "").strip()
            return f"ASRL{com_num}::INSTR"
        else:
            return addr

    def connect_all(self, timeout_ms: int = 5000, retries: int = 3,
                     delay_ms: int = 2000) -> Dict[str, bool]:
        """
        连接所有已加载的仪器。
        失败时自动重试（USB 仪器枚举可能有短暂延迟）。
        Returns:
            dict: {instrument_key: connected_bool}
        """
        total = len(self._instruments)
        info(f"[InstrumentManager] 开始连接仪器（共 {total} 台）")
        self._connection_results = {}

        for idx, (key, inst) in enumerate(self._instruments.items(), 1):
            # ── 注册状态回调 ───────────────────────────────
            inst.set_state_callback(
                lambda k, s, d, _key=key: self._on_instrument_state(_key, s, d)
            )

            try:
                if self._simulation_mode:
                    self._connection_results[key] = True
                    self._on_instrument_state(key, InstrumentConnectionState.CONNECTED,
                                             f"{key} [模拟模式]")
                else:
                    ok = self.connect_with_retry(key, retries=retries, delay_ms=delay_ms)
                    self._connection_results[key] = ok
                    if ok:
                        info(f"[InstrumentManager] {key} 连接成功")
                    else:
                        warning(f"[InstrumentManager] {key} 连接失败")

            except Exception as e:
                error(f"[InstrumentManager] {key} 连接异常: {e}")
                self._connection_results[key] = False
                self._on_instrument_state(key, InstrumentConnectionState.FAILED, f"{e}")

            # 每个仪器之间稍作间隔，避免 USB 枚举冲突
            time.sleep(0.3)

        return self._connection_results

    def _on_instrument_state(self, key: str, state: InstrumentConnectionState, detail: str):
        """
        仪器状态回调——将仪器层的 InstrumentConnectionState 转换为 logger + UI callback。
        """
        # 写 logger
        state_label = state.value
        if state == InstrumentConnectionState.CONNECTED:
            info(f"[InstrumentManager] {key}: {state_label} - {detail}")
        elif state == InstrumentConnectionState.FAILED:
            warning(f"[InstrumentManager] {key}: {state_label} - {detail}")
        else:
            info(f"[InstrumentManager] {key}: {state_label} - {detail}")

        # 推 UI callback
        if self._connection_callback:
            try:
                self._connection_callback(key, state, detail)
            except Exception:
                pass

    def connect_with_retry(self, key: str, retries: int = 3,
                           delay_ms: int = 2000) -> bool:
        """
        对指定仪器带重试的连接。
        指数退避：1s → 2s → 4s
        每一步状态都会通过 inst.connect(state_callback) 实时上报。
        """
        for attempt in range(1, retries + 1):
            inst = self._instruments.get(key)
            if not inst:
                error(f"[InstrumentManager] {key} 不存在")
                return False

            if self._simulation_mode:
                return True

            # 状态上报：开始第 N 次尝试
            detail = f"第 {attempt}/{retries} 次尝试"
            self._on_instrument_state(key, InstrumentConnectionState.RETRYING
                                     if attempt > 1 else InstrumentConnectionState.OPENING,
                                     detail)

            try:
                ok = inst.connect()  # 内部通过 state_callback 实时上报各步骤
                if ok:
                    # 连接成功（终态由 inst.connect() 内部上报，这里只打日志）
                    return True
                # connect() 成功返回 True；返回 False 在新逻辑中不再出现
                warning(f"[InstrumentManager] {key} 第 {attempt} 次返回 False")
            except InstrumentError as e:
                # 永久性错误（如身份验证失败），不重试
                error(f"[InstrumentManager] {key} 永久性错误，不重试: {e}")
                self._on_instrument_state(key, InstrumentConnectionState.FAILED, f"{e}")
                return False
            except Exception as e:
                # 暂时性错误（USB枚举延迟/VISA超时等），继续重试
                error(f"[InstrumentManager] {key} 第 {attempt} 次异常: {e}")
                if attempt < retries:
                    wait_s = delay_ms * attempt / 1000.0
                    self._on_instrument_state(key, InstrumentConnectionState.RETRYING,
                                             f"等待 {wait_s:.1f}s 后重试...")
                    time.sleep(wait_s)

        self._on_instrument_state(key, InstrumentConnectionState.FAILED,
                                  "多次重试后仍失败")
        error(f"[InstrumentManager] {key} 多次重试后仍失败")
        return False

    def disconnect_all(self):
        """断开所有仪器连接"""
        info(f"[InstrumentManager] 断开所有仪器")
        for key, inst in self._instruments.items():
            try:
                inst.disconnect()
                info(f"[InstrumentManager] {key} 已断开")
            except Exception as e:
                warning(f"[InstrumentManager] 断开 {key} 异常: {e}")
        self._instruments.clear()
        self._connection_results.clear()

    def get_instruments(self) -> Dict[str, Any]:
        """
        获取仪器实例字典。
        Key 与 test_cases/base.py 中 TestCase.instruments 一致。
        Returns:
            {"ELOAD": instance, "OSC": instance, ...}
        """
        return self._instruments.copy()

    def get(self, key: str) -> Optional[Any]:
        """
        按 key 获取单个仪器实例。
        key 不在 VALID_KEYS 中时会记录警告，帮助发现 key 拼写错误。
        Returns:
            仪器实例，或 None（未连接 / key 不存在）
        """
        if key not in self.VALID_KEYS:
            warning(f"[InstrumentManager] 未知仪器 key: \"{key}\" "
                    f"（有效值: {sorted(self.VALID_KEYS)}）")
        return self._instruments.get(key)

    def is_all_connected(self) -> bool:
        return all(self._connection_results.values()) if self._connection_results else False

    def apply_channel_roles(self, channel_config: dict):
        """
        将 UI 通道配置写入已连接的仪器对象。
        在仪器连接后、测试运行前调用。

        channel_config 格式（所有键可选）：
            pwr_in_v_ch     -> WT333E 输入电压/电流/功率通道（字符串"CH1"/"CH2"）
            pwr_out_v_ch    -> WT333E 输出电压/电流/功率通道
            osc_input_ch    -> 示波器输入通道（字符串"CH1"~"CH4"）
            osc_output_ch   -> 示波器输出通道
            osc_dynamic_ch  -> 示波器动态通道
            eload_vout1_ch  -> 电子负载电压采样通道
        """
        import logging
        logger = logging.getLogger("PowerAutoTest")

        # ---- WT333E 功率计 ----
        pwrmeter = self._instruments.get("WT333E") or self._instruments.get("POWER_METER")
        if pwrmeter and hasattr(pwrmeter, "set_channel_roles"):
            inp = channel_config.get("pwr_in_v_ch", "CH1")
            out = channel_config.get("pwr_out_v_ch", "CH2")
            pwrmeter.set_channel_roles(input_voltage_ch=inp, output_voltage_ch=out)
            logger.info(f"[InstrumentManager] WT333E 通道角色: 输入={inp} 输出={out}")

        # ---- 示波器 ----
        osc = self._instruments.get("OSC")
        if osc and hasattr(osc, "set_channel_roles"):
            osc_cfg = {
                "input_ch":  channel_config.get("osc_input_ch",   "CH4"),
                "output_ch": channel_config.get("osc_output_ch",   "CH2"),
                "dynamic_ch": channel_config.get("osc_dynamic_ch",  "CH1"),
            }
            osc.set_channel_roles(**osc_cfg)
            logger.info(f"[InstrumentManager] 示波器通道: {osc_cfg}")

    def summary(self) -> Dict[str, Any]:
        """返回连接结果摘要"""
        total = len(self._connection_results)
        connected = sum(1 for v in self._connection_results.values() if v)
        return {
            "total": total,
            "connected": connected,
            "failed": total - connected,
            "is_all_ok": total > 0 and connected == total,
            "simulation": self._simulation_mode,
            "details": self._connection_results.copy(),
        }

    def enable_simulation_mode(self):
        """
        启用模拟模式。
        所有仪器以模拟模式运行，不连接真实设备。
        用于开发调试或无仪器时测试执行流程。
        """
        info(f"[InstrumentManager] 启用模拟模式")
        self._simulation_mode = True

        for key, inst in self._instruments.items():
            try:
                if hasattr(inst, 'enable_simulation'):
                    inst.enable_simulation(f"SIMULATION_{key}")
                info(f"[InstrumentManager] {key} 模拟模式已启用")
            except Exception as e:
                warning(f"[InstrumentManager] {key} 模拟模式启用失败: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect_all()
