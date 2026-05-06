# -*- coding: utf-8 -*-
"""
仪器连接页面 - build_device_config_page

从 config_ui._build_device_config_page 迁出。
负责仪器连接 tab 的 UI 控件创建。
"""
import tkinter as tk
from tkinter import ttk, scrolledtext


# 设备定义（与 config_ui.py 保持一致）
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


def build_device_config_page(parent, app):
    """
    仪器连接 tab。

    在 app 上创建以下属性：
      _comm_vars[key], _addr_vars[key], _model_vars[key]
      _device_check_vars[key]
      _status_labels[key]
      _log_text
      _btn_connect
      _inst_key_to_ui
    """
    dev_keys = list(DEVICE_DEFS.keys())

    # 右：操作/状态/日志面板（固定 2/5 宽度）
    right_frame = ttk.Frame(parent)
    right_frame.pack(side="right", fill="y")

    # 左：设备配置列表（3/5 宽度）
    left_frame = ttk.Frame(parent)
    left_frame.pack(side="left", fill="both", expand=True)

    ttk.Label(left_frame, text="设备配置",
              font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 6))

    dev_frame = ttk.Frame(left_frame)
    dev_frame.pack(fill="both", expand=True)

    for idx, key in enumerate(dev_keys):
        _build_device_frame(app, dev_frame, key, idx)

    # 动态分配左右面板宽度比例：左3/5，右2/5
    def _adjust_split(event):
        total = event.width
        rw = max(220, int(total * 2 // 5))
        lw = total - rw
        right_frame.config(width=rw)
        left_frame.config(width=lw)

    parent.bind("<Configure>", _adjust_split)

    # InstrumentManager inst_key -> UI key 映射（写入 app 实例）
    app._inst_key_to_ui = {
        "OSC":          "oscilloscope",
        "ELOAD":        "electronic_load",
        "POWER_METER":  "power_meter",
        "SNIFFER":      "sniffer",
        "AC_SOURCE":    "ac_source",
        "DC_SOURCE":    "dc_source",
    }

    # ---- 操作按钮 ----
    btn_box = ttk.LabelFrame(right_frame, text="操作", padding=8)
    btn_box.pack(fill="x", pady=(0, 6), ipadx=4)

    tk.Button(btn_box, text="扫描设备", bg="#1E90FF", fg="white",
              font=("Arial", 9), width=20,
              command=app._scan_devices).pack(anchor="w", pady=2)

    app._btn_connect = tk.Button(btn_box, text="连接设备", bg="#228B22", fg="white",
                                  font=("Arial", 9), width=20,
                                  command=app._connect_devices)
    app._btn_connect.pack(anchor="w", pady=2)

    tk.Button(btn_box, text="断开连接", bg="#DC143C", fg="white",
              font=("Arial", 9), width=20,
              command=app._disconnect_devices).pack(anchor="w", pady=2)

    # ---- 连接状态 ----
    status_box = ttk.LabelFrame(right_frame, text="连接状态", padding=6)
    status_box.pack(fill="x", pady=(0, 6))

    for key, dev_def in DEVICE_DEFS.items():
        row_s = ttk.Frame(status_box)
        row_s.pack(anchor="w", pady=1)
        ttk.Label(row_s, text=dev_def["label"],
                  width=20, font=("Arial", 8)).pack(side="left")
        dot = tk.Label(row_s, text="●", fg="gray", bg="#D9D9D9",
                       font=("Arial", 10, "bold"))
        dot.pack(side="right")
        app._status_labels[key] = dot

    # ---- 日志 ----
    log_box = ttk.LabelFrame(right_frame, text="日志", padding=4)
    log_box.pack(fill="both", expand=True)

    app._log_text = scrolledtext.ScrolledText(
        log_box, font=("Courier New", 8), height=20, wrap="word",
        bg="black", fg="#00FF00", insertbackground="white")
    app._log_text.pack(fill="both", expand=True)


def _build_device_frame(app, parent, key, row, column=0):
    """为单个设备创建一行 UI：勾选 + 通信方式 + 地址 + 型号"""
    dev_def = DEVICE_DEFS[key]

    frame = ttk.LabelFrame(parent, text=f" {dev_def['label']} ", padding=6)
    frame.grid(row=row, column=column, sticky="ew", padx=4, pady=4)
    parent.rowconfigure(row, weight=1)

    # 勾选框
    title_row = ttk.Frame(frame)
    title_row.pack(fill="x", pady=1)
    check_var = tk.IntVar(value=1)
    app._device_check_vars[key] = check_var
    tk.Checkbutton(title_row, variable=check_var,
                   command=lambda k=key: app._on_device_check_changed(k)
                   ).pack(side="left", padx=(0, 4))

    # 通信方式
    row_f = ttk.Frame(frame)
    row_f.pack(fill="x", pady=1)
    ttk.Label(row_f, text="通信方式", width=10).pack(side="left")
    comm_var = tk.StringVar(value="")
    app._comm_vars[key] = comm_var
    ttk.Combobox(row_f, textvariable=comm_var,
                 values=dev_def["comm_options"],
                 state="readonly", width=12).pack(side="left")

    # 通信地址
    row_a = ttk.Frame(frame)
    row_a.pack(fill="x", pady=1)
    ttk.Label(row_a, text="通信地址", width=10).pack(side="left")
    addr_var = tk.StringVar(value="")
    app._addr_vars[key] = addr_var
    ttk.Entry(row_a, textvariable=addr_var, width=55).pack(side="left", fill="x", expand=True)

    # 设备型号
    row_m = ttk.Frame(frame)
    row_m.pack(fill="x", pady=1)
    ttk.Label(row_m, text="设备型号", width=10).pack(side="left")
    model_var = tk.StringVar(value="")
    app._model_vars[key] = model_var
    ttk.Combobox(row_m, textvariable=model_var,
                 values=dev_def["model_options"],
                 state="readonly", width=10).pack(side="left")
