#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Power Auto-Test Platform - Configuration UI v13
=================================================
重建版本：2026-04-14
"""
import os
import sys
# 确保项目根目录在 sys.path，让 import test_engine 和 test_cases 能正常工作
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import json
import time
import traceback
import warnings
import math

# 从 test_engine 导入用例注册表（唯一数据源）
from test_engine import TestEngine
from ui._engine_api import EngineAPI

# 导入配置 Schema（统一数据结构）
try:
    from config_schema import (
        SPECS_KEYS, PROTECTION_LOGIC_FIELDS, DYN_ROW_FIELDS, DYN_COLS,
        COND_FIELDS,
        _to_float, _to_int, _safe_float,
        rows_to_dicts, dicts_to_rows,
        build_specs_flat, build_protection_flat,
    )
    _SCHEMA_IMPORTED = True
except ImportError:
    _SCHEMA_IMPORTED = False

# ====================== 设备定义（供UI使用） ======================
DEVICE_DEFS = {
    "ac_source": {
        "label": "交流源 (AC Source)",
        "comm_options": ["USB", "LAN"],
        "model_options": ["IT7321", "IT7322"],
    },
    "electronic_load": {
        "label": "电子负载 (Electronic Load)",
        "comm_options": ["COM"],
        "model_options": ["IT8511", "IT8512", "IT8701P"],
    },
    "oscilloscope": {
        "label": "示波器 (Oscilloscope)",
        "comm_options": ["USB"],
        "model_options": ["DSOX4024A"],
    },
    "power_meter": {
        "label": "功率计 (Power Meter)",
        "comm_options": ["USB"],
        "model_options": ["WT333E", "WT322E"],
    },
    "sniffer": {
        "label": "协议诱骗器 (Sniffer)",
        "comm_options": ["COM"],
        "model_options": ["IP2716Sniffer"],
    },
    "dc_source": {
        "label": "直流源 (DC Source)",
        "comm_options": ["USB"],
        "model_options": ["IT6333A"],
    },
}
# ====================== 测试用例中英文映射 ======================
# 由 TestEngine.CASE_CN_NAMES 动态派生（唯一数据源），自动保持同步
CASE_NAME_MAP = {v: k for k, v in TestEngine.CASE_CN_NAMES.items()}

# ====================== ConfigUI 主类 ======================
class ConfigUI(EngineAPI):
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ATE自动化测试平台 v14")
        self.root.geometry("1100x700")
        self._inst_status = {k: "disconnected" for k in DEVICE_DEFS}
        self._instruments = {}
        self._scan_result = {}   # 扫描结果缓存 {key: {comm, addr, model}}
        self._comm_vars = {}
        self._addr_vars = {}
        self._model_vars = {}
        self._device_check_vars = {}  # 设备勾选状态 {key: IntVar}
        self._status_labels = {}
        self._engine = None          # TestEngine 实例
        self._test_thread = None     # 测试执行线程
        self._source_conditions = []  # 唯一事实数据源：生成或加载时写入，筛选时从它计算
        self._filtered_conditions = {}  # per-case 筛选条件 {case_key: [(vin,freq,...),...]}
        self._last_config_path = None  # 最近一次保存/加载的配置文件路径

        self._build_ui()
        # 启动时自动加载上次配置
    def _try_load_last_config(self):
        """读取上次保存的配置路径并自动加载"""
        last_path_file = os.path.join(os.path.dirname(__file__), ".last_config")
        try:
            if os.path.exists(last_path_file):
                with open(last_path_file, "r", encoding="utf-8") as f:
                    last_path = f.read().strip()
                if last_path and os.path.exists(last_path):
                    self._do_load_config(last_path)
                    self._log(f"已自动加载：{last_path}")
        except Exception as e:
            self._log(f"自动加载失败：{e}")
    def _load_config_file(self, path):
        """内部方法：直接加载指定路径的配置文件，不弹文件对话框（兼容旧调用）"""
        self._do_load_config(path)
    def _build_ui(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        f_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=f_menu)
        f_menu.add_command(label="导入配置...", command=self.load_config)
        f_menu.add_command(label="保存配置...", command=self.save_config)
        f_menu.add_separator()
        f_menu.add_command(label="退出", command=self.root.quit)
        # 设备上位机菜单（暂无效，等待后续开发）
        # dev_menu = tk.Menu(menubar, tearoff=0)
        # menubar.add_cascade(label="设备上位机", menu=dev_menu)
        # dev_menu.add_command(label="AC源", command=lambda: self._open_device_panel("AC_SOURCE"))
        # dev_menu.add_command(label="DC源", command=lambda: self._open_device_panel("DC_SOURCE"))
        # dev_menu.add_command(label="示波器", command=lambda: self._open_device_panel("OSC"))
        # dev_menu.add_command(label="功率计", command=lambda: self._open_device_panel("POWER_METER"))
        # dev_menu.add_command(label="电子负载", command=lambda: self._open_device_panel("ELOAD"))
        # dev_menu.add_command(label="诱骗器", command=lambda: self._open_device_panel("SNIFFER"))
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="平台应用指导书", command=self._open_help)
        # ---- Notebook（主页）----
        # 页面构建统一通过 ui/_pages 路由（建立调用模式，逐步迁移中）
        from ui._pages import (
            build_device_config_page,
            build_product_info_page,
            build_test_params_page,
            build_test_conditions_page,
            build_test_cases_page,
        )
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=6)
        page1 = ttk.Frame(nb)
        nb.add(page1, text="  设备配置  ")
        build_device_config_page(page1, self)
        page2 = ttk.Frame(nb)
        nb.add(page2, text="  产品信息配置  ")
        build_product_info_page(page2, self)
        page3 = ttk.Frame(nb)
        nb.add(page3, text="  测试参数配置  ")
        build_test_params_page(page3, self)
        page4 = ttk.Frame(nb)
        nb.add(page4, text="  测试条件  ")
        build_test_conditions_page(page4, self)
        page5 = ttk.Frame(nb)
        nb.add(page5, text="  测试用例  ")
        build_test_cases_page(page5, self)
        # 启动时自动加载上次配置
        self._try_load_last_config()
    def _open_device_panel(self, key):
        self._log("[OK] " + key)
    def _open_help(self):
        import webbrowser, os
        from tkinter import messagebox
        doc = os.path.join(os.path.dirname(__file__), "平台应用指导书.pdf")
        if os.path.exists(doc):
            webbrowser.open(doc)
        else:
            messagebox.showinfo("帮助", "手册未找到\n" + doc)
    def _on_device_check_changed(self, key):
        """勾选框状态变化时的回调（暂不需要特殊处理）"""
        pass

    def _on_power_segment_toggle(self):
        """高低压功率分段勾选框切换：启用/禁用HV/LV功率填写框"""
        if self._power_segment_var.get() == 1:
            self._hv_power_entry.config(state="normal")
            self._lv_power_entry.config(state="normal")
        else:
            self._hv_power_entry.config(state="disabled")
            self._lv_power_entry.config(state="disabled")
            self._hv_power_var.set("")
            self._lv_power_var.set("")

    # 扫描 / 连接 / 断开
    # ------------------------------------------------------------------
    def _scan_devices(self):
        self._log("=" * 40)
        self._log("开始扫描设备...")
        self._btn_connect.config(state="disabled")
        thread = threading.Thread(target=self._scan_bg, daemon=True)
        thread.start()
    def _scan_bg(self):
        from ui._scan import query_usb_idn, get_usb_visa, get_com_ports, match_idn, ack_verify_sniffer
        import serial
        try:
            checked = {k for k, v in self._device_check_vars.items() if v.get() == 1}
            self._log(f"勾选待扫设备: {checked}")

            scan_results = {}  # {dev_key: {'comm', 'addr', 'model'}}

            # ① USB VISA 扫描：扫全部USB设备，按类型记录
            self._log("=" * 40)
            self._log("[USB扫描] 扫全部USB VISA设备...")
            usb_visas = get_usb_visa()
            self._log(f"发现 {len(usb_visas)} 个USB VISA仪器")
            for addr in sorted(usb_visas):
                self._log(f"\n  查询: {addr}")
                idn = query_usb_idn(addr)
                if idn:
                    self._log(f"    IDN: {idn}")
                else:
                    self._log(f"    (无响应)")
                dev_key, model = match_idn(idn or "", addr)
                if dev_key:
                    scan_results[dev_key] = {'comm': 'USB', 'addr': addr, 'model': model}
                    if dev_key in checked:
                        self._log(f"    → [{dev_key}] {model}  [已勾选，已填入]")
                    else:
                        self._log(f"    → [{dev_key}] {model}  [未勾选]")
                else:
                    self._log(f"    → 未能识别")

            # ② COM口扫描：仅扫诱骗器（电子负载已在USB扫到则跳过）
            com_ports = get_com_ports()
            all_coms = sorted(com_ports.keys())
            self._log(f"\n[COM扫描] 端口:{', '.join(all_coms) if all_coms else '无'}")
            if "sniffer" in checked and "sniffer" not in scan_results:
                ch340_port = None
                for port, info in com_ports.items():
                    if '1A86:7523' in info.get('hwid', ''):
                        ch340_port = port
                        self._log(f"  [诱骗器] 通过硬件ID找到CH340: {port} ({info.get('desc','')})")
                        break
                if ch340_port:
                    if ack_verify_sniffer(ch340_port):
                        scan_results['sniffer'] = {'comm': 'COM', 'addr': ch340_port, 'model': 'IP2716Sniffer'}
                        self._log(f"    {ch340_port}: ACK验证成功 -> [sniffer] 已填入")
                    else:
                        self._log(f"    {ch340_port}: ACK验证失败(非诱骗器)")
                used_addrs = {v['addr'] for v in scan_results.values() if v.get('addr')}
                avail_coms = [c for c in all_coms if c not in used_addrs]
                self._log(f"  [ACK 查询诱骗器]: {', '.join(avail_coms) or '无'}")
                for port in avail_coms:
                    if "sniffer" in scan_results:
                        break
                    if ack_verify_sniffer(port):
                        scan_results['sniffer'] = {'comm': 'COM', 'addr': port, 'model': 'IP2716Sniffer'}
                        self._log(f"    {port}: 诱骗器识别成功 -> [sniffer] 已填入")
                    else:
                        self._log(f"    {port}: (无响应或非诱骗器)")
            else:
                if "sniffer" in scan_results:
                    self._log(f"  [诱骗器] 已在USB扫描中找到，跳过COM")
                else:
                    self._log(f"  [诱骗器] 未勾选，跳过")

            # 扫描完成：写入UI（异步，等UI更新完再提示）
            self._after(lambda results=scan_results: self._apply_all_scan_results(results))
        except Exception as e:
            self._log(f"扫描异常: {e}")
            traceback.print_exc()

    def _apply_scan_result(self, key, comm, addr, model):
        self._comm_vars[key].set(comm)
        self._addr_vars[key].set(addr)
        self._model_vars[key].set(model)
        self._scan_result[key] = {"comm": comm, "addr": addr, "model": model}
    def _apply_all_scan_results(self, results: dict):
        """扫描线程结束时批量写入所有结果到UI+缓存（主线程执行）"""
        checked = {k for k, v in self._device_check_vars.items() if v.get() == 1}
        for key, info in results.items():
            if key not in checked:
                self._log(f"  [{key}] {info['comm']} {info['addr']} {info['model']} [未勾选，跳过]")
                continue
            self._apply_scan_result(key, info['comm'], info['addr'], info['model'])
            self._log(f"  [{key}] {info['comm']} {info['addr']} {info['model']} 已填入")
        self._btn_connect.config(state="normal")
        not_found = checked - set(results.keys())
        if not_found:
            self._log(f"\n未找到勾选设备: {not_found}")
        self._log("\n扫描完成！请核对预填结果。")
    def _connect_devices(self):
        self._log("=" * 40)
        self._log("开始连接设备...")
        self._btn_connect.config(state="disabled")
        thread = threading.Thread(target=self._connect_bg, daemon=True)
        thread.start()
    def _connect_bg(self):
        try:
            config = {}
            for key in DEVICE_DEFS:
                # 只连接勾选的设备
                if key not in self._device_check_vars or self._device_check_vars[key].get() != 1:
                    continue
                model = self._model_vars[key].get().strip()
                comm  = self._comm_vars[key].get().strip()
                addr  = self._addr_vars[key].get().strip()
                config[key] = {
                    "enabled": bool(model),
                    "conn_type": comm,
                    "visa_address": addr,
                    "model": model,
                }
            from instrument_manager import InstrumentManager
            for k, v in config.items():
                tag = "enabled" if v["enabled"] else "disabled"
                self._after(lambda k=k, v=v, t=tag: self._log(
                    f"  [{k}] {t}: {v['conn_type']} {v['visa_address']} model={v.get('model','?')}"))
            mgr = InstrumentManager()
            mgr.load_from_config(config)
            results = mgr.connect_all()
            for key, ok in results.items():
                status = "connected" if ok else "failed"
                ui_key = self._inst_key_to_ui.get(key, key)
                self._after(lambda u=ui_key, s=status: self._update_status(u, s))
            # 记录仪器连接摘要到左侧配置日志
            self._after(lambda: self._log(mgr.summary()))
            # 记录仪器详细信息到右侧运行日志（仪器型号/地址/状态）
            self._after(lambda: self._log_instruments_to_run_log(mgr, results))
            self._instruments = mgr.get_instruments()
            self._instrument_manager = mgr
            self._after(lambda: self._btn_connect.config(state="normal"))
        except Exception as e:
            self._log(f"连接异常: {e}")
            self._after(lambda: self._btn_connect.config(state="normal"))
            traceback.print_exc()
    def _disconnect_devices(self):
        self._log("=" * 40)
        self._log("断开所有设备...")
        try:
            for key, inst in self._instruments.items():
                try:
                    inst.disconnect()
                except Exception:
                    pass
            self._instruments = {}
            for key in DEVICE_DEFS:
                self._update_status(key, "disconnected")
            self._log("全部设备已断开")
        except Exception as e:
            self._log(f"断开异常: {e}")
    def _update_status(self, key, status):
        self._inst_status[key] = status
        dot = self._status_labels.get(key)
        if not dot:
            return
        colors = {"connected": "#00AA00",
                  "failed": "#DD2222",
                  "disconnected": "#888888"}
        dot.config(fg=colors.get(status, "#888888"))
    # ------------------------------------------------------------------
    # 配置保存 / 加载
    # ------------------------------------------------------------------
    def _save_config_to_file(self, path):
        """将当前配置保存到指定文件路径（不弹对话框）"""
        # ---- product_info：统一类型写入 ----
        prod_info = {
            "product_name":           self._prod_name_var.get(),
            "product_type":           self._prod_type_vars.get("充电器", tk.IntVar(value=0)).get() and "充电器" or "适配器",
            "input_voltage_lo":       _safe_float(self._input_voltage_lo_var.get()),
            "input_voltage_hi":       _safe_float(self._input_voltage_hi_var.get()),
            "output_voltage":         _safe_float(self._output_voltage_var.get()),
            "output_power":           _safe_float(self._output_power_var.get()),
            "power_segment":          bool(self._power_segment_var.get()),
            "hv_power":               _safe_float(self._hv_power_var.get()),
            "lv_power":               _safe_float(self._lv_power_var.get()),
            "load_startup_enabled":   bool(self._load_startup_var.get()),
            "load_startup_current":   _safe_float(self._load_startup_current_var.get()),
            "load_startup_voltage":   _safe_float(self._load_startup_voltage_var.get()),
            # specs_v2: 扁平 float 字典（schema v2）
            "specs_v2":              build_specs_flat(self._spec_vars, {}),
            # protection_logic_v2: 扁平字典
            "protection_logic_v2":   build_protection_flat(self._prot_vars, {}),

            "qc": {
                label: {"enabled": v["check"].get(), "value": v["entry"].get()}
                for label, v in self._qc_vars.items()
            },
            "pd": {
                label: {"enabled": v["check"].get(), "value": v["entry"].get()}
                for label, v in self._pd_vars.items()
            },
            "ufcs": {
                label: {"enabled": v["check"].get(), "value": v["entry"].get()}
                for label, v in self._ufcs_vars.items()
            },
        }
        test_params = {
            "osc_in_ch":      self._osc_in_ch_var.get().strip() or "CH4",
            "osc_in_attn":    _safe_float(self._osc_in_attn_var.get()),
            "osc_out_ch":     self._osc_out_ch_var.get().strip() or "CH2",
            "osc_out_attn":   _safe_float(self._osc_out_attn_var.get()),
            "pwr_in_v_ch":    self._pwr_in_v_ch_var.get().strip() or "CH1",
            "pwr_in_i_ch":    self._pwr_in_i_ch_var.get().strip() or "CH1",
            "pwr_out_v_ch":   self._pwr_out_v_ch_var.get().strip() or "CH1",
            "pwr_out_i_ch":   self._pwr_out_i_ch_var.get().strip() or "CH1",
            "eload_vout1_ch": self._eload_vout1_ch_var.get().strip() or "CH1",
            "eload_vout2_ch": self._eload_vout2_ch_var.get().strip() or "CH2",
            # dyn_large/dyn_small: [{dict}] 格式（schema v2）
            "dyn_large": rows_to_dicts(
                [self._dyn_large_tree.item(r)["values"] for r in self._dyn_large_tree.get_children()],
                DYN_ROW_FIELDS),
            "dyn_small": rows_to_dicts(
                [self._dyn_small_tree.item(r)["values"] for r in self._dyn_small_tree.get_children()],
                DYN_ROW_FIELDS),
            "warmup":      _safe_float(self._warmup_var.get()),
            "onoff_cycle": self._onoff_cycle_var.get(),
            "short_cycle": self._short_cycle_var.get(),
        }
        # 示波器通道配置（与运行时的 test_settings 一致）
        test_settings = {
            "osc_input_ch":   self._osc_in_ch_var.get().strip()   or "CH4",
            "osc_input_attn":  self._osc_in_attn_var.get().strip()  or "1.0",
            "osc_output_ch":  self._osc_out_ch_var.get().strip()  or "CH2",
            "osc_output_attn": self._osc_out_attn_var.get().strip() or "1.0",
            "osc_dynamic_ch":   self._osc_dyn_ch_var.get().strip()   or "CH2",
            "osc_dynamic_attn":  self._osc_dyn_attn_var.get().strip() or "1.0",
        }
        # 全量条件（字符串行，供 UI 显示）
        cond_rows = []
        for item in self._cond_tree.get_children():
            row = list(self._cond_tree.item(item)["values"])
            # 数值列: vin(1), freq(2), vout(4), iout(5)
            for idx in (1, 2, 4, 5):
                try:
                    row[idx] = float(row[idx])
                except (ValueError, TypeError):
                    pass
            cond_rows.append(row)
        cfg = {
            "_schema_version": "v2",
            "devices": {
                k: {
                    "comm": self._comm_vars[k].get(),
                    "addr": self._addr_vars[k].get(),
                    "model": self._model_vars[k].get(),

                } for k in DEVICE_DEFS
            },
            "product_info": prod_info,
            "test_params": test_params,
            "test_settings": test_settings,
            # test_conditions_v2: [{dict}] 格式，用于恢复 UI 测试条件表格
            "test_conditions_v2": rows_to_dicts(cond_rows, ["product_type", "vin", "freq", "proto", "vout", "iout"]),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
            self._last_config_path = path
            # 记录路径供自动加载
            last_path_file = os.path.join(os.path.dirname(__file__), ".last_config")
            with open(last_path_file, "w", encoding="utf-8") as f:
                f.write(path)
        except Exception as e:
            raise e

    def save_config(self):
        """保存配置文件（弹对话框）"""
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            self._save_config_to_file(path)
            self._log(f"配置已保存: {path}")
        except Exception as e:
            messagebox.showerror("错误", str(e))
    def load_config(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        self._do_load_config(path)

    def _do_load_config(self, path):
        """内部方法：加载指定路径的配置文件，恢复所有状态"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # 设备信息
            devs = cfg.get("devices", {})
            for k in DEVICE_DEFS:
                d = devs.get(k, {})
                self._comm_vars[k].set(d.get("comm", ""))
                self._addr_vars[k].set(d.get("addr", ""))
                self._model_vars[k].set(d.get("model", ""))
            # 产品信息
            pi = cfg.get("product_info", {})
            self._prod_name_var.set(pi.get("product_name", ""))
            self._input_voltage_lo_var.set(pi.get("input_voltage_lo", ""))
            self._input_voltage_hi_var.set(pi.get("input_voltage_hi", ""))
            self._output_voltage_var.set(pi.get("output_voltage", ""))
            self._output_power_var.set(pi.get("output_power", ""))
            self._power_segment_var.set(pi.get("power_segment", 0))
            self._hv_power_var.set(pi.get("hv_power", ""))
            self._lv_power_var.set(pi.get("lv_power", ""))
            self._on_power_segment_toggle()   # 根据勾选状态刷新HV/LV填写框状态
            pt = pi.get("product_types", {})
            for label, var in self._prod_type_vars.items():
                var.set(pt.get(label, 0))
            self._load_startup_var.set(pi.get("load_startup_enabled", 0))
            self._load_startup_current_var.set(pi.get("load_startup_current", ""))
            self._load_startup_voltage_var.set(pi.get("load_startup_voltage", ""))
            # specs_v2: 扁平 float 字典
            specs_v2 = pi.get("specs_v2", {})
            for flat_key, label_text in SPECS_KEYS:
                v = self._spec_vars.get(label_text, {})
                # ---- enable-only 规格（6级/7级能效）----
                if flat_key.endswith("_enable"):
                    val = specs_v2.get(flat_key, 0)
                    if "enable" in v:
                        v["enable"].set(int(val) if not isinstance(val, float) and not isinstance(val, int) else int(val))
                    continue
                # ---- 普通 lo/hi 规格 ----
                # NaN → default（未配置）；数值 → 转为字符串
                lo_raw = specs_v2.get(f"{flat_key}_lo", None)
                hi_raw = specs_v2.get(f"{flat_key}_hi", None)
                if "lo" in v:
                    v["lo"].set("" if (lo_raw is None or (isinstance(lo_raw, float) and math.isnan(lo_raw))) else str(lo_raw))
                if "hi" in v:
                    v["hi"].set("" if (hi_raw is None or (isinstance(hi_raw, float) and math.isnan(hi_raw))) else str(hi_raw))
            # ---- 产品类型（checkbutton）: 根据 saved string 设置 IntVar ----
            saved_type = pi.get("product_type", "")
            for label, var in self._prod_type_vars.items():
                var.set(1 if saved_type == label else 0)
            # protection_logic_v2: 扁平字典 {"输入欠压保护_mode": "self"|"latch"}
            prot_v2 = pi.get("protection_logic_v2", {})
            for label, v in self._prot_vars.items():
                mode = prot_v2.get(f"{label}_mode", "")
                v["self"].set(1 if mode == "self" else 0)
                v["latch"].set(1 if mode == "latch" else 0)
            for proto_vars, proto_key in [
                (self._qc_vars, "qc"),
                (self._pd_vars, "pd"),
                (self._ufcs_vars, "ufcs"),
            ]:
                data = pi.get(proto_key, {})
                for label, v in proto_vars.items():
                    d = data.get(label, {})
                    v["check"].set(d.get("enabled", 0))
                    v["entry"].set(d.get("value", ""))
            # 测试参数（示波器从 test_settings 读，其他从 test_params 读）
            ts = cfg.get("test_settings", {})
            tp = cfg.get("test_params", {})
            self._osc_in_ch_var.set(ts.get("osc_input_ch", "CH4"))
            self._osc_in_attn_var.set(ts.get("osc_input_attn", "1.0"))
            self._osc_out_ch_var.set(ts.get("osc_output_ch", "CH2"))
            self._osc_out_attn_var.set(ts.get("osc_output_attn", "1.0"))
            self._osc_dyn_ch_var.set(ts.get("osc_dynamic_ch", "CH2"))
            self._osc_dyn_attn_var.set(ts.get("osc_dynamic_attn", "1.0"))
            self._pwr_in_v_ch_var.set(tp.get("pwr_in_v_ch", "CH1"))
            self._pwr_in_i_ch_var.set(tp.get("pwr_in_i_ch", "CH1"))
            self._pwr_out_v_ch_var.set(tp.get("pwr_out_v_ch", "CH1"))
            self._pwr_out_i_ch_var.set(tp.get("pwr_out_i_ch", "CH1"))
            self._eload_vout1_ch_var.set(tp.get("eload_vout1_ch", "CH1"))
            self._eload_vout2_ch_var.set(tp.get("eload_vout2_ch", "CH1"))
            # dyn_large/dyn_small: 支持 [{dict}] v2 和旧 [[values...]] 两种格式
            self._dyn_large_tree.delete(*self._dyn_large_tree.get_children())
            for row in tp.get("dyn_large", []):
                if isinstance(row, dict):
                    row = [row.get(f) for f in DYN_ROW_FIELDS]
                self._dyn_large_tree.insert("", "end", values=row)
            self._dyn_small_tree.delete(*self._dyn_small_tree.get_children())
            for row in tp.get("dyn_small", []):
                if isinstance(row, dict):
                    row = [row.get(f) for f in DYN_ROW_FIELDS]
                self._dyn_small_tree.insert("", "end", values=row)
            self._warmup_var.set(tp.get("warmup", ""))
            self._onoff_cycle_var.set(tp.get("onoff_cycle", ""))
            self._short_cycle_var.set(tp.get("short_cycle", ""))
            # 测试条件：恢复上方 Treeview（字符串行）
            tree = self._cond_tree
            # test_conditions_v2: [{dict}] 格式
            tc_rows = cfg.get("test_conditions_v2", [])
            # 恢复上方 Treeview（字符串行）
            tree.delete(*tree.get_children())
            for idx, row in enumerate(tc_rows):
                tag = "odd" if idx % 2 == 0 else "even"
                vals = [row.get(f) for f in ["product_type", "vin", "freq", "proto", "vout", "iout"]]
                tree.insert("", "end", values=vals, tags=(tag,))
            # 恢复 _source_conditions（从 v2 dict 列表重建数值元组）
            self._source_conditions = []
            for row in tc_rows:
                try:
                    vin  = _to_float(row.get("vin"), 0)
                    freq = _to_float(row.get("freq"), 60.0)
                    proto = str(row.get("proto", "—")) or "—"
                    vout = _to_float(row.get("vout"), None)
                    iout = _to_float(row.get("iout"), None)
                    raw_pt = str(row.get("product_type", "charger")) or "charger"
                    ptype = "charger" if raw_pt in ("充电器", "charger") else "adapter"
                    self._source_conditions.append((vin, freq, proto, vout, iout, ptype))
                except (ValueError, TypeError, IndexError):
                    pass
            # 从 _source_conditions 重新计算所有已注册用例的筛选条件（不刷新树，保持 checkbox 状态）
            self._apply_filtered_conditions(refresh_all=True, update_tree=True)
            self._last_config_path = path
            self._log(f"配置已加载: {path}")
            # 记录路径
            last_path_file = os.path.join(os.path.dirname(__file__), ".last_config")
            try:
                with open(last_path_file, "w", encoding="utf-8") as f:
                    f.write(path)
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _update_filtered_display_from_loaded(self):
        """根据已加载的 filtered_conditions 更新下方 Treeview 显示"""
        tree = self._filtered_cond_tree
        tree.delete(*tree.get_children())
        # 没有用例被选中时，提示用户选择，不显示残留数据
        has_checked = any(var.get() for var in self._case_vars.values())
        if not has_checked and not self._selected_case:
            tree.insert("", "end", values=("请在左侧选择测试用例", "", "", "", "", ""))
            return
        if not self._filtered_conditions:
            return
        seen = set()
        display_rows = []
        for case_key, rows in self._filtered_conditions.items():
            for row in rows:
                key = (row["vin"], row["freq"], row["proto"], row["vout"], row["iout"], row.get("product_type", "charger"))
                if key not in seen:
                    seen.add(key)
                    vin = row["vin"]
                    freq = row["freq"]
                    ov = row["vout"]
                    oi = row["iout"]
                    proto = str(row["proto"]) if row["proto"] else "—"
                    ptype = "充电器" if row.get("product_type") == "charger" else "适配器"
                    vin_str = str(int(vin)) if vin == int(vin) else str(vin)
                    freq_str = str(int(freq)) if freq == int(freq) else str(freq)
                    ov_str = str(int(ov)) if ov and ov == int(ov) else (str(ov) if ov else "—")
                    oi_str = str(round(oi, 2)) if oi else "—"
                    display_rows.append((ptype, vin_str, freq_str, proto, ov_str, oi_str))
        for row in display_rows:
            tree.insert("", "end", values=row)
        """测试参数配置页面
        左1/2：示波器通道设置 + 功率计通道设置
        右1/2：其他参数设置"""
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        # 左面板
        left_panel = ttk.Frame(container)
        left_panel.pack(side="left", fill="both", expand=True)
        # 右面板
        right_panel = ttk.Frame(container)
        right_panel.pack(side="right", fill="both", expand=True)
        # 强制左右各占 1/2 宽度
        def _adjust_split(event):
            total = event.width
            hw = max(200, total // 2)
            left_panel.config(width=hw)
            right_panel.config(width=hw)
        container.bind('<Configure>', _adjust_split)
        # ==================== 左面板：示波器通道 + 功率计通道 ====================
        # 示波器通道设置
        box_osc = ttk.LabelFrame(left_panel, text=" 示波器通道设置 ", padding=10)
        box_osc.pack(fill="x", padx=8, pady=(8, 6))
        self._osc_in_ch_var   = tk.StringVar(value="CH4")
        self._osc_out_ch_var  = tk.StringVar(value="CH2")
        self._osc_in_attn_var  = tk.StringVar(value="1.0")   # 衰减比例（探头衰减比）

        # 输入电压波形 + 衰减比例
        row_in = ttk.Frame(box_osc)
        row_in.pack(anchor="w", pady=2)
        ttk.Label(row_in, text="输入电压波形：", width=16, font=("Arial", 9)).pack(side="left")
        ttk.Combobox(row_in, textvariable=self._osc_in_ch_var,
                     values=["CH1","CH2","CH3","CH4"],
                     state="readonly", width=8).pack(side="left")
        ttk.Label(row_in, text="  衰减比例：", font=("Arial", 9)).pack(side="left")
        ttk.Entry(row_in, textvariable=self._osc_in_attn_var,
                  width=8).pack(side="left")

        # 输出电压波形 + 衰减比例
        row_out = ttk.Frame(box_osc)
        row_out.pack(anchor="w", pady=2)
        self._osc_out_attn_var = tk.StringVar(value="1.0")
        ttk.Label(row_out, text="输出电压波形：", width=16, font=("Arial", 9)).pack(side="left")
        ttk.Combobox(row_out, textvariable=self._osc_out_ch_var,
                     values=["CH1","CH2","CH3","CH4"],
                     state="readonly", width=8).pack(side="left")
        ttk.Label(row_out, text="  衰减比例：", font=("Arial", 9)).pack(side="left")
        ttk.Entry(row_out, textvariable=self._osc_out_attn_var, width=8).pack(side="left")
        # 动态电压波形通道 + 衰减比例
        self._osc_dyn_ch_var   = tk.StringVar(value="CH2")
        self._osc_dyn_attn_var = tk.StringVar(value="1.0")
        row_dyn = ttk.Frame(box_osc)
        row_dyn.pack(anchor="w", pady=2)
        ttk.Label(row_dyn, text="动态电压波形：", width=16, font=("Arial", 9)).pack(side="left")
        ttk.Combobox(row_dyn, textvariable=self._osc_dyn_ch_var,
                     values=["CH1","CH2","CH3","CH4"],
                     state="readonly", width=8).pack(side="left")
        ttk.Label(row_dyn, text="  衰减比例：", font=("Arial", 9)).pack(side="left")
        ttk.Entry(row_dyn, textvariable=self._osc_dyn_attn_var, width=8).pack(side="left")
        # 功率计通道设置
        box_pwr = ttk.LabelFrame(left_panel, text=" 功率计通道设置 ", padding=10)
        box_pwr.pack(fill="x", padx=8, pady=6)
        self._pwr_in_v_ch_var  = tk.StringVar(value="CH1")
        self._pwr_in_i_ch_var  = tk.StringVar(value="CH1")
        self._pwr_out_v_ch_var = tk.StringVar(value="CH1")
        self._pwr_out_i_ch_var = tk.StringVar(value="CH1")
        for lbl, var in [
            ("输入电压：", self._pwr_in_v_ch_var),
            ("输入电流：", self._pwr_in_i_ch_var),
            ("输出电压：", self._pwr_out_v_ch_var),
            ("输出电流：", self._pwr_out_i_ch_var),
        ]:
            row = ttk.Frame(box_pwr)
            row.pack(anchor="w", pady=2)
            ttk.Label(row, text=lbl, width=16, font=("Arial", 9)).pack(side="left")
            ttk.Combobox(row, textvariable=var, values=["CH1","CH2","CH3","CH4"],
                         state="readonly", width=8).pack(side="left")
        # 负载通道设置
        box_eload = ttk.LabelFrame(left_panel, text=" 负载通道设置 ", padding=10)
        box_eload.pack(fill="x", padx=8, pady=6)
        self._eload_vout1_ch_var = tk.StringVar(value="CH1")
        self._eload_vout2_ch_var = tk.StringVar(value="CH1")
        for lbl, var in [
            ("Vout1+ 通道：", self._eload_vout1_ch_var),
            ("Vout2+ 通道：", self._eload_vout2_ch_var),
        ]:
            row = ttk.Frame(box_eload)
            row.pack(anchor="w", pady=2)
            ttk.Label(row, text=lbl, width=16, font=("Arial", 9)).pack(side="left")
            ttk.Combobox(row, textvariable=var, values=["CH1","CH2","CH3","CH4"],
                         state="readonly", width=8).pack(side="left")
        # ==================== 左面板：其他参数设置 ====================
        box_other = ttk.LabelFrame(left_panel, text=" 其他参数设置 ", padding=10)
        box_other.pack(fill="x", padx=8, pady=(6, 8))
        self._warmup_var      = tk.StringVar()
        self._onoff_cycle_var = tk.StringVar()
        self._short_cycle_var = tk.StringVar()
        # 热机时间
        row = ttk.Frame(box_other)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="热机时间(min):", font=("Arial", 9)).pack(side="left")
        ttk.Entry(row, textvariable=self._warmup_var, width=20).pack(side="left", padx=(4, 0))
        # 反复开关机周期
        row = ttk.Frame(box_other)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="反复开关机周期(s):", font=("Arial", 9)).pack(side="left")
        ttk.Entry(row, textvariable=self._onoff_cycle_var, width=20).pack(side="left", padx=(4, 0))
        ttk.Label(row, text="例：10-10，开机10s关机10s",
                  font=("Arial", 8), foreground="#666666").pack(side="left", padx=(8, 0))
        # 反复短路周期
        row = ttk.Frame(box_other)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="反复短路周期(s):", font=("Arial", 9)).pack(side="left")
        ttk.Entry(row, textvariable=self._short_cycle_var, width=20).pack(side="left", padx=(4, 0))
        ttk.Label(row, text="例：10-10，开机10s短路10s",
                  font=("Arial", 8), foreground="#666666").pack(side="left", padx=(8, 0))

        # ==================== 右面板：动态测试设置 ====================
        def _build_dyn_box(parent, title, columns, tree_ref_attr):
            """构建一个动态测试设置框（表格+滚动条+添加/删除+双击编辑），与测试条件列表风格一致"""
            box = ttk.LabelFrame(parent, text=title, padding=5)
            box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

            # 表格区域（含滚动条）
            table_frame = ttk.Frame(box)
            table_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))
            tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=6)
            col_widths = [75, 90, 75, 90, 80, 70]
            for col, cw in zip(columns, col_widths):
                tree.heading(col, text=col)
                tree.column(col, width=cw, anchor="center")
            vsb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            tree.tag_configure("odd",  background="#F0F0F0")
            tree.tag_configure("even", background="#FFFFFF")
            setattr(self, tree_ref_attr, tree)

            # ---- 弹窗填写一行数据 ----
            def _popup_add_row():
                from tkinter import Toplevel
                top = Toplevel(self.root)
                top.title("添加动态测试参数")
                top.geometry("580x280")
                top.transient(self.root)
                top.grab_set()
                col_labels = ["UP(%)", "UP斜率(A/us)", "DOWN(%)", "DOWN斜率(A/us)", "频率(Hz)", "比例(%)"]
                entry_vars = {}
                for i, lbl in enumerate(col_labels):
                    row = ttk.Frame(top)
                    row.pack(fill="x", padx=12, pady=4)
                    ttk.Label(row, text=lbl, width=14).pack(side="left")
                    var = tk.StringVar()
                    ttk.Entry(row, textvariable=var, width=24).pack(side="left")
                    entry_vars[lbl] = var

                def do_add():
                    vals = [entry_vars[lbl].get().strip() for lbl in col_labels]
                    if not vals[0]:
                        messagebox.showwarning("提示", "UP(%) 不能为空", parent=top)
                        return
                    idx = len(tree.get_children())
                    tag = "odd" if idx % 2 == 0 else "even"
                    tree.insert("", "end", values=vals, tags=(tag,))
                    top.destroy()

                btn_row = ttk.Frame(top)
                btn_row.pack(pady=12)
                ttk.Button(btn_row, text="确定", command=do_add).pack(side="left", padx=8)
                ttk.Button(btn_row, text="取消", command=top.destroy).pack(side="left")

            # 按钮栏
            btn_bar = ttk.Frame(box)
            btn_bar.pack(fill="x", padx=4, pady=(4, 4))
            tk.Button(btn_bar, text="添加行", bg="#228B22", fg="white",
                       font=("Arial", 9), command=_popup_add_row).pack(side="left")
            tk.Button(btn_bar, text="删除所选", bg="#DC143C", fg="white",
                       font=("Arial", 9),
                       command=lambda _t=tree: [_t.delete(i) for i in _t.selection()]).pack(side="left", padx=(8, 0))

            # ---- 双击单元格进入编辑 ----
            def _start_edit(event):
                region = tree.identify_region(event.x, event.y)
                if region != "cell":
                    return
                col_id = tree.identify_column(event.x)
                col_idx = int(col_id.replace('#', '')) - 1
                row_id  = tree.identify_row(event.y)
                if not row_id:
                    return
                cur_val = tree.item(row_id, "values")[col_idx]

                rel_x, rel_y, w, h = tree.bbox(row_id, col_id)
                off_x = tree.winfo_x()
                off_y = tree.winfo_y()

                entry = ttk.Entry(table_frame)
                entry.place(x=rel_x + off_x, y=rel_y + off_y, width=w, height=h)
                entry.insert(0, cur_val)
                entry.select_all()
                entry.focus()

                def _save(event=None):
                    new_val = entry.get().strip()
                    values = list(tree.item(row_id, "values"))
                    values[col_idx] = new_val
                    tree.item(row_id, values=values)
                    entry.destroy()

                def _cancel(event=None):
                    entry.destroy()

                entry.bind("<Return>", _save)
                entry.bind("<KP_Enter>", _save)
                entry.bind("<Escape>", _cancel)
                entry.bind("<FocusOut>", _save)

            tree.bind("<Double-1>", _start_edit)
            return tree

        dyn_cols = ["UP(%)", "UP斜率(A/us)", "DOWN(%)", "DOWN斜率(A/us)", "频率(Hz)", "比例(%)"]
        _build_dyn_box(right_panel, " 大动态测试设置 ", dyn_cols, "_dyn_large_tree")
        _build_dyn_box(right_panel, " 小动态测试设置 ", dyn_cols, "_dyn_small_tree")

    def _build_test_conditions_page(self, parent):
        """测试条件页面：输入电压/频率/协议/输出电压电流"""
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        # 顶部操作区
        top_bar = ttk.Frame(container)
        top_bar.pack(fill="x", padx=8, pady=(8, 4))
        tk.Button(top_bar, text="生成测试条件", bg="#1E90FF", fg="white",
                  font=("Arial", 10), command=self._generate_test_conditions).pack(side="left")
        # 条件说明
        note = ttk.Label(top_bar, text=(
            "根据产品信息配置的协议/电压/功率自动生成测试条件列表。"
            "充电器含协议输出，适配器按功率/电压计算输出电流。"),
            font=("Arial", 8), foreground="#555555")
        note.pack(side="left", padx=(16, 0))
        # 添加 / 删除 按钮
        btn_bar = ttk.Frame(container)
        btn_bar.pack(fill="x", padx=8, pady=(0, 4))
        tk.Button(btn_bar, text="添加行", bg="#228B22", fg="white",
                  font=("Arial", 9), command=self._add_cond_row).pack(side="left")
        tk.Button(btn_bar, text="删除所选", bg="#DC143C", fg="white",
                  font=("Arial", 9), command=self._delete_cond_row).pack(side="left", padx=(8, 0))
        # 表格区域（Treeview）
        table_frame = ttk.Frame(container)
        table_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        columns = ("col_type", "col_in_v", "col_freq", "col_proto", "col_out_v", "col_out_i")
        self._cond_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=18)
        col_configs = [
            ("col_type",   "产品类型",   70),
            ("col_in_v",   "输入电压(V)",  110),
            ("col_freq",   "频率(Hz)",     70),
            ("col_proto",  "协议",         100),
            ("col_out_v",  "输出电压(V)",  110),
            ("col_out_i",  "输出电流(A)",  110),
        ]
        for col_id, heading, width in col_configs:
            self._cond_tree.heading(col_id, text=heading)
            self._cond_tree.column(col_id, width=width, anchor="center")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self._cond_tree.yview)
        self._cond_tree.configure(yscrollcommand=vsb.set)
        self._cond_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        # 交替行颜色（用 tag）
        self._cond_tree.tag_configure("odd",  background="#F0F0F0")
        self._cond_tree.tag_configure("even", background="#FFFFFF")
    def _generate_test_conditions(self):
        """根据产品信息配置生成全量测试条件

        生成两份数据：
        - self._source_conditions：唯一事实数据源，数值元组列表 [(vin, freq, proto_label, vout, iout, product_type), ...]
        - 写入 _cond_tree：字符串形式，供 UI 显示用
        """
        import re
        tree = self._cond_tree
        tree.delete(*tree.get_children())

        # ---- 读取产品类型 ----
        is_charger = self._prod_type_vars.get("充电器", tk.IntVar(value=0)).get()
        is_adapter = self._prod_type_vars.get("适配器", tk.IntVar(value=0)).get()
        if not is_charger and not is_adapter:
            messagebox.showwarning("提示", "请在【产品信息配置】中至少选择一个产品类型（充电器/适配器）")
            return

        # ---- 读取输入电压 ----
        in_lo_str = self._input_voltage_lo_var.get().strip()
        in_hi_str = self._input_voltage_hi_var.get().strip()
        if not in_lo_str and not in_hi_str:
            messagebox.showwarning("提示", "请在【产品信息配置】中填写输入电压范围")
            return
        in_lo = float(in_lo_str) if in_lo_str else None
        in_hi = float(in_hi_str) if in_hi_str else None
        if not in_lo:
            messagebox.showwarning("提示", "输入电压下限无效")
            return

        # ---- 检查哪些测试用例被选中 ----
                # ---- 输入电压列表（全量，筛选逻辑在各用例的 _filter_conditions_by_case 中处理）----
        in_voltages = [in_lo]
        in_voltages.extend([115, 230])
        if in_hi and in_hi not in in_voltages:
            in_voltages.append(in_hi)
        in_voltages = sorted(set([v for v in in_voltages if v]))
        # ---- 输出电压/功率 ----
        out_v = None
        out_p = None
        out_v_str = self._output_voltage_var.get().strip().replace("V", "").replace("v", "")
        out_p_str = self._output_power_var.get().strip().replace("W", "").replace("w", "")
        try:
            out_v = float(out_v_str) if out_v_str else None
        except ValueError:
            pass
        try:
            out_p = float(out_p_str) if out_p_str else None
        except ValueError:
            pass

        # ---- 收集充电器协议 ----
        charger_protocols = []
        for label, v in self._qc_vars.items():
            if v["check"].get():
                val = v["entry"].get().strip()
                if val:
                    charger_protocols.append(("QC", label, val))
        for label, v in self._pd_vars.items():
            if v["check"].get():
                val = v["entry"].get().strip()
                if val:
                    charger_protocols.append(("PD", label, val))
        for label, v in self._ufcs_vars.items():
            if v["check"].get():
                val = v["entry"].get().strip()
                if val:
                    charger_protocols.append(("UFCS", label, val))

        # ---- 解析协议字符串 ----
        def parse_proto(s):
            s2 = re.sub(r"^PPS-", "", s.strip(), flags=re.IGNORECASE)
            mv = re.search(r"(\d+(?:\.\d+)?)V", s2, re.IGNORECASE)
            mi = re.search(r"(\d+(?:\.\d+)?)A", s2, re.IGNORECASE)
            return (float(mv.group(1)) if mv else None,
                    float(mi.group(1)) if mi else None)

        # ---- 生成条件（存两份）----
        self._source_conditions = []  # 唯一事实数据源
        rows = []                  # 字符串行，供 UI 显示

        for vin in in_voltages:
            freq = 60.0 if vin < 180 else 50.0
            freq_str = str(int(freq))
            vin_str = str(int(vin)) if vin == int(vin) else str(vin)

            # --- 充电器 ---
            if is_charger:
                if charger_protocols:
                    for ptype, pname, pval in charger_protocols:
                        ov, oi = parse_proto(pval)
                        if ov is None:
                            continue
                        proto_label = f"{ptype}-{pname}"
                        self._source_conditions.append((vin, freq, proto_label, ov, oi, "charger"))
                        ov_str = str(int(ov)) if ov == int(ov) else str(ov)
                        oi_str = str(round(oi, 2)) if oi else ""
                        rows.append(("充电器", vin_str, freq_str, proto_label, ov_str, oi_str))
                else:
                    self._source_conditions.append((vin, freq, "—", None, None, "charger"))
                    rows.append(("充电器", vin_str, freq_str, "—", "—", "—"))

            # --- 适配器 ---
            if is_adapter:
                if out_v and out_p:
                    oi_calc = out_p / out_v
                    self._source_conditions.append((vin, freq, "—", out_v, oi_calc, "adapter"))
                    ov_str = str(int(out_v)) if out_v == int(out_v) else str(out_v)
                    rows.append(("适配器", vin_str, freq_str, "—", ov_str, str(round(oi_calc, 2))))
                elif out_v:
                    self._source_conditions.append((vin, freq, "—", out_v, None, "adapter"))
                    ov_str = str(int(out_v)) if out_v == int(out_v) else str(out_v)
                    rows.append(("适配器", vin_str, freq_str, "—", ov_str, "—"))

        # ---- 写入 Treeview ----
        for idx, row in enumerate(rows):
            tag = "odd" if idx % 2 == 0 else "even"
            tree.insert("", "end", values=row, tags=(tag,))
        self._log(f"测试条件已生成：共 {len(rows)} 条")
        # 强制刷新所有用例的筛选条件（不只是已勾选的）
        self._apply_filtered_conditions(refresh_all=True)
        self._save_config_to_file(self._last_config_path or "")
        self._log("测试条件已自动刷新并保存")

    def _add_cond_row(self):
        """手动添加一行测试条件（弹出对话框填写）"""
        from tkinter import Toplevel
        top = Toplevel(self.root)
        top.title("添加测试条件")
        top.geometry("480x260")
        top.transient(self.root)
        top.grab_set()
        fields = [
            ("产品类型",    "充电器"),
            ("输入电压(V)", ""),
            ("频率(Hz)",    ""),
            ("协议",        ""),
            ("输出电压(V)", ""),
            ("输出电流(A)", ""),
        ]
        entries = {}
        for i, (lbl, default) in enumerate(fields):
            row = ttk.Frame(top)
            row.pack(fill="x", padx=12, pady=4)
            ttk.Label(row, text=lbl, width=14).pack(side="left")
            if lbl == "产品类型":
                var = tk.StringVar(value=default)
                ttk.Combobox(row, textvariable=var, values=["充电器","适配器"],
                             state="readonly", width=20).pack(side="left")
                entries[lbl] = var
            else:
                var = tk.StringVar(value=default)
                ttk.Entry(row, textvariable=var, width=24).pack(side="left")
                entries[lbl] = var
        def do_add():
            raw_vals = [entries[f].get() for f, _ in fields]
            if not raw_vals[1].strip():
                messagebox.showwarning("提示", "输入电压不能为空", parent=top)
                return
            # 输出电流格式化保留1位小数
            vals = list(raw_vals)
            try:
                vals[5] = str(round(float(raw_vals[5]), 1))
            except ValueError:
                pass
            idx = len(self._cond_tree.get_children())
            tag = "odd" if idx % 2 == 0 else "even"
            self._cond_tree.insert("", "end", values=vals, tags=(tag,))
            self._rebuild_source_from_tree()
            self._apply_filtered_conditions(refresh_all=True)
            top.destroy()
            self._log("已添加测试条件：" + " / ".join(vals[:4]))
        btn_row = ttk.Frame(top)
        btn_row.pack(pady=12)
        tk.Button(btn_row, text="确认添加", bg="#228B22", fg="white",
                  font=("Arial", 9), command=do_add).pack(side="left", padx=8)
        tk.Button(btn_row, text="取消", bg="#CCCCCC",
                  font=("Arial", 9), command=top.destroy).pack(side="left")
    def _rebuild_source_from_tree(self):
        """
        从 _cond_tree（UI 显示树）重建 _source_conditions（数值元组数据源），
        保持两份数据同步。
        """
        def to_product_type(label: str) -> str:
            return "charger" if label in ("充电器", "charger") else "adapter"

        self._source_conditions = []
        for item in self._cond_tree.get_children():
            vals = self._cond_tree.item(item)["values"]
            if len(vals) < 6:
                continue
            prod_type_label, vin_s, freq_s, proto, vout_s, iout_s = vals[0], vals[1], vals[2], vals[3], vals[4], vals[5]
            try:
                vin = float(vin_s)
            except (ValueError, TypeError):
                vin = 0.0
            try:
                freq = float(freq_s)
            except (ValueError, TypeError):
                freq = 50.0
            try:
                vout = float(vout_s) if vout_s not in ("", "—") else None
            except (ValueError, TypeError):
                vout = None
            try:
                iout = float(iout_s) if iout_s not in ("", "—") else None
            except (ValueError, TypeError):
                iout = None
            self._source_conditions.append((vin, freq, str(proto), vout, iout, to_product_type(prod_type_label)))

    def _delete_cond_row(self):
        """删除 Treeview 中选中的行"""
        sel = self._cond_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中要删除的行")
            return
        for item in sel:
            self._cond_tree.delete(item)
        self._rebuild_source_from_tree()
        self._apply_filtered_conditions(refresh_all=True)
        self._log(f"已删除 {len(sel)} 条测试条件")
