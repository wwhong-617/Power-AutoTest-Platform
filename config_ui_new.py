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
from tkinter import ttk, messagebox
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
        # 各 Tab 页面构建逻辑已拆分到 ui/pages/ 目录下的独立模块
        from ui.pages import (
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
    def _build_test_cases_page(self, parent):
        """测试用例页面
        左1/4：测试用例树（5大类）
        中2/4：测试详情（名称/步骤/条件）
        右1/4：测试运行（按钮/日志/进度）"""
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        # 三个面板容器
        left_panel   = ttk.Frame(container)
        middle_panel = ttk.Frame(container)
        right_panel  = ttk.Frame(container)
        left_panel.pack(side="left", fill="both", expand=True)
        middle_panel.pack(side="left", fill="both", expand=True)
        right_panel.pack(side="right", fill="both", expand=True)
        # 动态分配宽度：左1/4 中2/4 右1/4
        def _adjust(event):
            total = max(800, event.width)
            lw = max(180, total // 4)
            mw = max(350, total // 2)
            rw = total - lw - mw
            left_panel.config(width=lw)
            middle_panel.config(width=mw)
            right_panel.config(width=rw)
        container.bind('<Configure>', _adjust)
        # ==================== 左面板：测试用例树 ====================
        ttk.Label(left_panel, text="测试用例", font=("Arial", 10, "bold")
                 ).pack(anchor="w", padx=6, pady=(6, 2))
        btn_bar = ttk.Frame(left_panel)
        btn_bar.pack(fill="x", padx=6, pady=(0, 4))
        tk.Button(btn_bar, text="全选", bg="#1E90FF", fg="white",
                  font=("Arial", 8), command=self._select_all_cases).pack(side="left", padx=(0, 4))
        tk.Button(btn_bar, text="反选", bg="#FF8C00", fg="white",
                  font=("Arial", 8), command=self._invert_all_cases).pack(side="left")
        # 刷新按钮已合并至生成测试条件按钮中
        # ========== 左面板：测试用例树（Canvas，每行 checkbox + 名称完全分离）==========
        case_canvas_frame = tk.Frame(left_panel, bg="#F5F5F5")
        case_canvas_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        case_canvas = tk.Canvas(case_canvas_frame, bg="#F5F5F5", highlightthickness=0)
        case_scroll = ttk.Scrollbar(case_canvas_frame, orient="vertical", command=case_canvas.yview)
        case_canvas.configure(yscrollcommand=case_scroll.set)

        scroll_inner = tk.Frame(case_canvas, bg="#F5F5F5")
        case_canvas.pack(side="left", fill="both", expand=True)
        case_scroll.pack(side="right", fill="y")

        # 5大类测试用例定义
        # 从 TestEngine 动态生成分类字典（单一数据源）
        # 分类由中文名推导：输入XX→输入测试，输出XX→输出测试，XX保护→保护测试，XX协议→协议测试
        self._test_case_defs = {}
        for en_key, cn_name in TestEngine.CASE_CN_NAMES.items():
            if "保护" in cn_name:
                category = "保护测试"
            elif cn_name.startswith("输入"):
                category = "输入测试"
            elif cn_name.startswith("输出"):
                category = "输出测试"
            elif "协议" in cn_name:
                category = "协议测试"
            else:
                category = "其他"
            if category not in self._test_case_defs:
                self._test_case_defs[category] = []
            self._test_case_defs[category].append(cn_name)

        # 中文->英文，直接从 TestEngine CASE_CN_NAMES 取得（单一数据源）
        # 同时注册"xxx测试"和"xxx"两种中文名，方便 UI checkbox 状态记忆
        self._case_cn_to_en = {}
        for en_key, cn_name in TestEngine.CASE_CN_NAMES.items():
            self._case_cn_to_en[cn_name] = en_key
            if cn_name.endswith("测试"):
                self._case_cn_to_en[cn_name[:-2]] = en_key  # 去掉"测试"后缀也注册一条

        self._case_vars = {}  # case_name -> tk.BooleanVar
        self._case_name_labels = {}  # case_name -> tk.Label (for highlight)
        self._selected_case = None  # 当前选中的用例名称
        self._cat_case_frames = {}  # category -> {case_name: row_frame}
        self._cat_expanded = {}  # category -> bool (默认 False 收拢)
        self._cat_triangle_labels = {}  # category -> tk.Label (三角符号)

        ROW_H = 26  # 每行高度
        CAT_PAD = 4  # 分类上下间距
        CB_PADX = 6  # checkbox 左边距

        def _create_case_row(parent_frame, case_name, row_idx):
            """创建一行：checkbox + 名称label"""
            row = tk.Frame(parent_frame, bg="#F5F5F5")
            row.pack(fill="x")

            var = tk.BooleanVar(value=False)
            self._case_vars[case_name] = var

            def on_check():
                # 勾选后立即刷新筛选条件
                self._apply_filtered_conditions()

            cb = tk.Checkbutton(row, text="",
                               variable=var, onvalue=True, offvalue=False,
                               command=on_check,
                               bg="#F5F5F5", anchor="w")
            cb.pack(side="left", padx=(CB_PADX, 2))

            lbl = tk.Label(row, text=case_name, font=("Arial", 9),
                          bg="#F5F5F5", anchor="w", cursor="hand2")
            lbl.pack(side="left", fill="x", expand=True, padx=(0, 4))

            def on_name_click(e, name=case_name):
                # 点击名称：刷新详情 + 刷新筛选条件，不动 checkbox
                self._selected_case = name
                for n, l in self._case_name_labels.items():
                    l.config(bg="#D0E8FF" if n == name else "#F5F5F5",
                             fg="#1A1A1A" if n == name else "#444444")
                self._case_name_var.set(name)
                self._case_step_text.config(state="normal")
                self._case_step_text.delete("1.0", "end")
                self._case_step_text.insert("end", self._get_test_case_flow(name))
                self._case_step_text.config(state="disabled")
                en_key = self._case_cn_to_en.get(name, name)
                self._apply_filtered_conditions(selected_case=en_key)

            lbl.bind("<Button-1>", on_name_click)
            self._case_name_labels[case_name] = lbl
            return row

        # 创建所有分类和用例行（默认收拢，点击三角展开）
        # 结构：scroll_inner > cat_container > (cat_header + case_container > case_rows)
        for category, cases in self._test_case_defs.items():
            self._cat_case_frames[category] = {}
            self._cat_expanded[category] = False

            # 分类容器（整个分类的根节点，永远显示）
            cat_container = tk.Frame(scroll_inner, bg="#E0E0E0")
            cat_container.pack(fill="x", pady=(CAT_PAD, 0))

            # 分类表头（三角 + 名称，永远显示）
            cat_header = tk.Frame(cat_container, bg="#E0E0E0")
            cat_header.pack(fill="x")

            tri_lbl = tk.Label(cat_header, text="▶", font=("Arial", 8),
                              bg="#E0E0E0", anchor="w", cursor="hand2", width=2)
            tri_lbl.pack(side="left", padx=(6, 2))
            self._cat_triangle_labels[category] = tri_lbl

            cat_lbl = tk.Label(cat_header, text=category, font=("Arial", 9, "bold"),
                              bg="#E0E0E0", anchor="w")
            cat_lbl.pack(side="left", fill="x", expand=True, padx=(0, 4), pady=2)

            # 用例行容器（展开/收拢只控制这个容器）
            case_container = tk.Frame(cat_container, bg="#F5F5F5")
            # 默认收拢，不显示

            # 点击分类表头：只隐藏/显示 case_container
            def on_cat_click(e, case_container=case_container, tri=tri_lbl, cat=category):
                expanded = self._cat_expanded[cat]
                self._cat_expanded[cat] = not expanded
                tri.config(text="▼" if not expanded else "▶")
                if expanded:
                    case_container.pack_forget()
                else:
                    case_container.pack(fill="x", pady=(0, 0))
                scroll_inner.update_idletasks()
                case_canvas.configure(scrollregion=case_canvas.bbox("all"))

            cat_lbl.bind("<Button-1>", on_cat_click)
            tri_lbl.bind("<Button-1>", on_cat_click)

            # 用例行（放入 case_container 子容器）
            for case_name in cases:
                row = _create_case_row(case_container, case_name, 0)
                self._cat_case_frames[category][case_name] = row

        # Canvas 滚动配置
        def _on_frame_configure(e):
            case_canvas.configure(scrollregion=case_canvas.bbox("all"))

        scroll_inner.bind("<Configure>", _on_frame_configure)

        def _on_canvas_configure(e):
            case_canvas.itemconfig(scroll_window, width=e.width)

        scroll_window = case_canvas.create_window((0, 0), window=scroll_inner, anchor="nw")
        case_canvas.bind("<Configure>", _on_canvas_configure)
        case_canvas.yview_moveto(0)
        # ==================== 中间面板：测试详情 ====================
        ttk.Label(middle_panel, text="测试详情", font=("Arial", 10, "bold")
                 ).pack(anchor="w", padx=6, pady=(6, 4))
        detail_frame = ttk.LabelFrame(middle_panel, text=" 测试详情 ", padding=8)
        detail_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        # 测试名称
        name_row = ttk.Frame(detail_frame)
        name_row.pack(fill="x", pady=(0, 6))
        ttk.Label(name_row, text="测试名称：", font=("Arial", 9)).pack(side="left")
        self._case_name_var = tk.StringVar()
        self._case_name_entry = ttk.Entry(name_row, textvariable=self._case_name_var,
                                          font=("Arial", 9))
        self._case_name_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        # 测试条件（只读 Treeview 显示）
        cond_header = ttk.Frame(detail_frame)
        cond_header.pack(fill="x", pady=(4, 2))
        cond_lbl = ttk.Label(cond_header, text="测试条件：", font=("Arial", 9))
        cond_lbl.pack(side="left")
        cond_lbl.pack(side="left")
        cond_tree_frame = ttk.Frame(detail_frame)
        cond_tree_frame.pack(fill="both", expand=True, pady=(0, 6))
        cond_cols = ("col_type", "col_in_v", "col_freq", "col_proto", "col_out_v", "col_out_i")
        self._filtered_cond_tree = ttk.Treeview(cond_tree_frame, columns=cond_cols,
                                                show="headings", height=2)
        for col_id, heading, width in [
            ("col_type", "类型", 70), ("col_in_v", "输入电压(V)", 100),
            ("col_freq", "频率(Hz)", 70), ("col_proto", "协议", 100),
            ("col_out_v", "输出电压(V)", 100), ("col_out_i", "输出电流(A)", 100)]:
            self._filtered_cond_tree.heading(col_id, text=heading)
            self._filtered_cond_tree.column(col_id, width=width, anchor="center")
        cond_y = ttk.Scrollbar(cond_tree_frame, orient="vertical", command=self._filtered_cond_tree.yview)
        self._filtered_cond_tree.configure(yscrollcommand=cond_y.set)
        self._filtered_cond_tree.pack(side="left", fill="both", expand=True)
        cond_y.pack(side="right", fill="y")
        # 测试步骤（只读显示）
        step_lbl = ttk.Label(detail_frame, text="测试步骤：", font=("Arial", 9))
        step_lbl.pack(anchor="w", pady=(4, 2))
        self._case_step_text = tk.Text(detail_frame, font=("Arial", 9),
                                       height=12, wrap="word", bg="#F8F8F8",
                                       state="disabled")
        step_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self._case_step_text.yview)
        self._case_step_text.configure(yscrollcommand=step_scroll.set)
        self._case_step_text.pack(side="left", fill="both", expand=True)
        step_scroll.pack(side="right", fill="y")
        # ==================== 右侧面板：测试运行 ====================
        ttk.Label(right_panel, text="测试运行", font=("Arial", 10, "bold")
                 ).pack(anchor="w", padx=6, pady=(6, 4))
        # 操作按钮
        btn_box = ttk.Frame(right_panel)
        btn_box.pack(fill="x", padx=6, pady=(0, 6))
        self._btn_run  = tk.Button(btn_box, text="运行", bg="#228B22", fg="white",
                                    font=("Arial", 10, "bold"), width=7,
                                    command=self._run_tests)
        self._btn_run.pack(side="left", padx=(0, 4))
        self._btn_pause = tk.Button(btn_box, text="暂停", bg="#FF8C00", fg="white",
                                     font=("Arial", 10), width=7,
                                     command=self._pause_tests, state="disabled")
        self._btn_pause.pack(side="left", padx=(0, 4))
        self._btn_stop  = tk.Button(btn_box, text="停止", bg="#DC143C", fg="white",
                                     font=("Arial", 10), width=7,
                                     command=self._stop_tests, state="disabled")
        self._btn_stop.pack(side="left")
        # 进度条
        prog_frame = ttk.Frame(right_panel)
        prog_frame.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(prog_frame, text="运行进度：", font=("Arial", 8)).pack(anchor="w")
        self._case_progress = ttk.Progressbar(prog_frame, mode="determinate")
        self._case_progress.pack(fill="x", pady=(2, 0))
        self._case_progress_label = ttk.Label(prog_frame, text="0 / 0",
                                               font=("Arial", 8))
        self._case_progress_label.pack(anchor="e")
        # 运行日志
        log_box = ttk.LabelFrame(right_panel, text=" 运行日志 ", padding=4)
        log_box.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self._run_log = tk.Text(log_box, font=("Courier New", 8),
                                 bg="black", fg="#00FF00",
                                 insertbackground="white",
                                 wrap="word", height=20)
        run_y = ttk.Scrollbar(log_box, orient="vertical", command=self._run_log.yview)
        self._run_log.configure(yscrollcommand=run_y.set)
        self._run_log.pack(side="left", fill="both", expand=True)
        run_y.pack(side="right", fill="y")

        # 初始化 Treeview：默认显示提示行，待用户选择用例后才刷新
        tree = self._filtered_cond_tree
        tree.delete(*tree.get_children())
        tree.insert("", "end", values=("请在左侧选择测试用例", "", "", "", "", ""))

    def _clear_skip_flag(self):
        """延迟清除跳过标志，允许后续选择操作正常更新详情面板"""
        self._skip_detail_update_iid = None


    def _select_all_cases(self):
        for name, var in self._case_vars.items():
            var.set(True)
        self._apply_filtered_conditions()
    def _invert_all_cases(self):
        for name, var in self._case_vars.items():
            var.set(not var.get())
        self._apply_filtered_conditions()

    # _refresh_test_conditions 已合并至生成测试条件，无须单独指定

    def _get_test_case_flow(self, case_name):
        """返回测试用例顶部的简要流程说明（只读显示）"""
        flows = {
            "输入电压范围": (
                "测试策略（每条 test_condition 独立执行）：\n\n"
                "1. 开机自检：基类 startup_self_check，不下电\n\n"
                "2. 示波器 ROLL 模式：时基覆盖完整扫描时长\n\n"
                "3. 诱骗器协议：锁定目标协议（charger 专用）\n\n"
                "4. 电子负载 CC 模式上电\n\n"
                "5. 电压往返扫描：缓升（Vin_min→Vin_max）→ 缓降（Vin_max→Vin_min）Vac≥180V → 50Hz；Vac<180V → 60Hz；每步等待 settle_time\n\n"
                "6. 示波器 STOP 冻结波形，测量 Vmax/Vmin，保存波形截图\n\n"
                "7. 汇总：Vmax ≤ Vout×110% 且 Vmin ≥ Vout×90% → PASS\n\n"
                "规格判定：Vmax ≤ 目标×110% 且 Vmin ≥ 目标×90%"
            ),
            "输入欠压保护": (
                "测试策略（每条 test_condition 独立执行）：\n\n"
                "1. 开机自检：基类 startup_self_check，不下电\n\n"
                "2. 示波器 ROLL 模式：时基覆盖完整扫描时长\n\n"
                "3. 诱骗器协议：锁定目标协议（charger 专用）\n\n"
                "4. 电子负载 CC 模式上电\n\n"
                "5. 电压扫描（4阶段）\n\n"
                "① 缓降：Vin_min → (brown_out_lo - 5V)，0.5V/步，2s/步，检测输出 < Vout×70% → 记录 uvp_point，切换负载电流\n\n"
                "② 快降：(brown_out_lo - 5V) → 0V，5V/步，1s/步，检测快降过程中是否有重启\n\n"
                "③ 快升：0V → (brown_in_lo - 5V)，5V/步，1s/步，检测快升过程中是否有提前恢复\n\n"
                "④ 缓升：(brown_in_lo - 5V) → Vin_min，0.5V/步，2s/步\n\n"
                "- self 模式：检测输出 > Vout×90% → 记录 recovery_point\n\n"
                "- latch 模式：检测输出 > Vout×70% → 判定重启（FAIL）\n\n"
                "6. 示波器 STOP 冻结波形，保存波形截图\n\n"
                "7. 汇总判定\n\n"
                "规格判定：\n\n"
                "一、自恢复模式--到达欠压保护点，能正确掉电保护无重启现象；达到恢复保护点，能正常开机工作\n\n"
                "二、锁死模式--到达欠压保护点，能正确掉电保护无重启现象；无恢复点，恢复达正常输入电压范围，电源锁死"
            ),
            "输出电压精度": (
                "测试目标：验证 DUT 在不同输入/负载条件下输出电压精度。\n\n"
                "流程：设置输入电压/电流 → 功率计读取输出电压 → 与规格对比计算精度"
            ),
            "输出纹波测试": (
                "测试目标：验证 DUT 输出纹波噪声是否在规格内。\n\n"
                "流程：示波器 DC 耦合检测输出纹波 → 记录峰峰值 → 与规格对比"
            ),
            "输出动态测试": (
                "测试目标：验证 DUT 负载动态变化时输出电压的稳定性。\n\n"
                "流程：电子负载快速变化 → 示波器抓取波形 → 记录恢复时间与过冲幅度 → 与规格对比"
            ),
            "输出过流保护": (
                "测试目标：验证 DUT 输出过流保护功能。\n\n"
                "流程：逐步增加负载电流 → 监测保护触发点 → 记录 OCP 电流值 → 验证恢复时间"
            ),
            "过压保护(OVP)": (
                "测试目标：验证 DUT 输出过压保护功能。\n\n"
                "流程：逐步增加输出电压 → 监测保护触发点 → 记录 OVP 电压值 → 等待恢复"
            ),
            "QC2.0协议": (
                "测试目标：验证 DUT 的 QC2.0 快充协议支持。\n\n"
                "流程：诱骗器触发 QC2.0 → 读取协议握手结果 → 验证各电压档位（5V/9V/12V/20V）"
            ),
            "PD协议": (
                "测试目标：验证 DUT 的 PD 快充协议支持。\n\n"
                "流程：诱骗器触发 PD → 读取 PDO 握手结果 → 验证各档位电压"
            ),
        }
        return flows.get(case_name, f"测试用例：{case_name}\n请参考测试用例代码顶部的流程说明")
    def _get_default_condition(self, category, case_name):
        return (
            f"测试分类：{category}\n"
            f"测试用例：{case_name}\n"
            f"参考规格要求：见【产品规格要求】页"
        )

    def _filter_conditions_by_case(self, case_key, all_conditions):
        from ui._conditions import filter_conditions_by_case
        return filter_conditions_by_case(case_key, all_conditions, TestEngine.CASE_REGISTRY)

    def _apply_filtered_conditions(self, selected_case=None, refresh_all=False, update_tree=True):
        """
        根据每个测试用例的 case_key（英文名）从全量条件中筛选出专属条件，
        存入 self._filtered_conditions = {case_key: [(vin, freq, proto_label, vout, iout, product_type), ...]}
        同时更新下方 Treeview 的显示（update_tree=True 时）。

        Args:
            selected_case: 英文 case_key，仅刷新这一个用例（点击名称时传入）
            refresh_all:   True = 强制刷新所有已注册用例的筛选结果（生成条件后调用）
            update_tree:  True = 同时刷新树显示；False = 仅更新 _filtered_conditions 不动树
        """
        # 点击名称时：树只跟随点击的用例，不受 checkbox 影响
        if selected_case:
            checked_keys = [selected_case]
        elif refresh_all:
            # 生成条件后：强制刷新所有已注册用例，不依赖 checkbox 状态
            checked_keys = list(self._case_cn_to_en.values())
        else:
            checked_keys = [name for name, var in self._case_vars.items() if var.get()]

        # 每次从 _source_conditions 重新计算（唯一事实来源），不依赖旧缓存
        for case_key in checked_keys:
            en_key = self._case_cn_to_en.get(case_key, case_key)
            filtered = self._filter_conditions_by_case(en_key, self._source_conditions)
            self._filtered_conditions[en_key] = filtered


        # ---- 更新下方 Treeview 显示 ----
        if not update_tree:
            return  # 仅更新 _filtered_conditions，不动树

        tree = self._filtered_cond_tree
        tree.delete(*tree.get_children())

        if not checked_keys:
            tree.insert("", "end", values=("请在左侧选择测试用例", "", "", "", "", ""))
            return

        seen = set()
        display_rows = []
        for case_key in checked_keys:
            en_key = self._case_cn_to_en.get(case_key, case_key)
            for row in self._filtered_conditions.get(en_key, []):
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

        if not display_rows:
            tree.insert("", "end", values=("无匹配的测试条件", "", "", "", "", ""))
            return

        for row in display_rows:
            tree.insert("", "end", values=row)

    def _log(self, msg: str):
        """向顶部日志区域写入带时间戳的消息"""
        ts = time.strftime("%H:%M:%S")
        self._log_text.insert("end", f"[{ts}] {msg}\n")
        self._log_text.see("end")

    def _after(self, func):
        self.root.after(0, func)

    def _append_run_log(self, msg):
        """线程安全地向底部运行日志插入内容"""
        def _inner():
            self._run_log.insert("end", msg)
            self._run_log.see("end")
        self.root.after(0, _inner)

    def _log_instruments_to_run_log(self, mgr, results):
        """将仪器连接详细信息输出到右侧运行日志（仪器型号/地址/状态）"""
        self._append_run_log("\n========== 仪器连接详情 ==========\n")
        for key, ok in results.items():
            inst = mgr.get_instruments().get(key)
            addr = getattr(inst, "address", "N/A") if inst else "N/A"
            idn = getattr(inst, "idn", "") if inst else ""
            status = "✅ 已连接" if ok else "❌ 连接失败"
            line = f"  [{status}] {key}  @ {addr}"
            if idn:
                line += f"  ({idn})"
            self._append_run_log(line + "\n")
        total = len(results)
        connected = sum(1 for v in results.values() if v)
        self._append_run_log(f"  合计: {connected}/{total} 台已连接\n")
        self._append_run_log("=" * 40 + "\n\n")

def main():
    root = tk.Tk()
    app = ConfigUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
