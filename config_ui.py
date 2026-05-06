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
import time
import traceback

# 从 test_engine 导入用例注册表（唯一数据源）
from test_engine import TestEngine
from test_cases.flow_descriptions import FLOW_DESCRIPTIONS
from ui._engine_api import EngineAPI

# 配置持久化（序列化/反序列化）
from ui._config_io import save_config, load_config

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
        save_config(self, path)

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
            load_config(self, path)
            self._log(f"配置已加载: {path}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

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

    def _get_test_case_flow(self, case_name):
        """返回测试用例顶部的简要流程说明（只读显示）"""
        return FLOW_DESCRIPTIONS.get(
            case_name,
            f"未找到用例 {case_name} 的流程说明\n请参考测试用例页面侧边栏的流程说明"
        )

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
        根据用户选中的用例，从全局测试条件中筛选出每个用例专属的条件子集。

        结果写入 self._filtered_conditions = {case_key: [row_dict, ...]}
        同时刷新下方 Treeview 显示（update_tree=True 时）。

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

        # ---- 刷新下方 Treeview 显示 ----
        if not update_tree:
            return

        display_rows = self._build_filtered_display_rows(checked_keys)
        tree = self._filtered_cond_tree
        tree.delete(*tree.get_children())

        if not checked_keys:
            tree.insert("", "end", values=("请在左侧选择测试用例", "", "", "", "", ""))
            return

        if not display_rows:
            tree.insert("", "end", values=("无匹配的测试条件", "", "", "", "", ""))
            return

        for row in display_rows:
            tree.insert("", "end", values=row)

    def _build_filtered_display_rows(self, checked_keys):
        """
        将 self._filtered_conditions 中指定用例的行合并、去重、格式化，
        返回 [(ptype, vin_str, freq_str, proto, ov_str, oi_str), ...]
        """
        seen = set()
        display_rows = []
        for case_key in checked_keys:
            en_key = self._case_cn_to_en.get(case_key, case_key)
            for row in self._filtered_conditions.get(en_key, []):
                key = (row["vin"], row["freq"], row["proto"],
                       row["vout"], row["iout"], row.get("product_type", "charger"))
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
        return display_rows

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
