# -*- coding: utf-8 -*-
"""
产品信息页面 - build_product_info_page

从 config_ui._build_product_info_page 迁出。
负责产品信息 + 规格要求 + 保护逻辑 + 快充协议 tab。

在 app 上创建以下属性：
  _prod_type_vars, _prod_name_var, _input_voltage_lo_var, _input_voltage_hi_var
  _output_voltage_min_var, _output_voltage_max_var, _output_power_var
  _power_segment_var, _hv_power_var, _lv_power_var
  _hv_power_entry, _lv_power_entry
  _load_startup_var, _load_startup_current_var, _load_startup_voltage_var
  _spec_vars, _prot_vars
  _qc_vars, _pd_vars, _ufcs_vars
"""
import tkinter as tk
from tkinter import ttk




def on_power_segment_toggle(app):
    """
    高压/低压功率分段勾选框切换：启用/禁用 HV/LV 功率填写框。
    供 ui/_config_io.py 加载配置后调用，也供 config_ui 自身调用。
    """
    if app._power_segment_var.get() == 1:
        app._hv_power_entry.config(state="normal")
        app._lv_power_entry.config(state="normal")
    else:
        app._hv_power_entry.config(state="disabled")
        app._lv_power_entry.config(state="disabled")
        app._hv_power_var.set("")
        app._lv_power_var.set("")


def build_product_info_page(parent, app):
    """
    产品信息配置页面。

    左1/2：产品类型 + 基础信息 + 产品规格要求
    右1/2：快充协议
    """
    container = ttk.Frame(parent)
    container.pack(fill="both", expand=True)

    # 左右面板
    left_panel = ttk.Frame(container)
    left_panel.pack(side="left", fill="both", expand=True)
    right_panel = ttk.Frame(container)
    right_panel.pack(side="right", fill="both", expand=True)

    def _adjust_split(event):
        total = event.width
        hw = max(200, total // 2)
        left_panel.config(width=hw)
        right_panel.config(width=hw)

    container.bind("<Configure>", _adjust_split)

    # ==================== 左面板 ====================
    _build_left_panel(app, left_panel)

    # ==================== 右面板：快充协议 ====================
    _build_right_panel(app, right_panel)


def _build_left_panel(app, left_panel):
    """左面板：产品类型 + 基础信息 + 规格要求 + 保护逻辑"""

    # ---- 产品类型 ----
    box_type = ttk.LabelFrame(left_panel, text=" 产品类型 ", padding=10)
    box_type.pack(fill="x", padx=8, pady=(8, 4))

    row1 = ttk.Frame(box_type)
    row1.pack(fill="x", padx=16, pady=(4, 2))

    app._prod_type_vars = {}
    for label in ["充电器", "适配器"]:
        var = tk.IntVar(value=0)
        app._prod_type_vars[label] = var
        tk.Checkbutton(row1, text=label, variable=var,
                       onvalue=1, offvalue=0, font=("Arial", 9)
                       ).pack(side="left", padx=(0, 12))

    ttk.Separator(row1, orient="vertical").pack(side="left", fill="y", padx=(8, 8))

    ttk.Label(row1, text="默认开机电压：", font=("Arial", 9)).pack(side="left")
    app._load_startup_voltage_var = tk.StringVar(value="")
    ttk.Entry(row1, textvariable=app._load_startup_voltage_var, width=7).pack(side="left")
    ttk.Label(row1, text=" V", font=("Arial", 9)).pack(side="left", padx=(0, 10))

    ttk.Separator(row1, orient="vertical").pack(side="left", fill="y", padx=(0, 8))

    app._load_startup_var = tk.IntVar(value=0)
    tk.Checkbutton(row1, text="是否带载开机", variable=app._load_startup_var,
                   onvalue=1, offvalue=0, font=("Arial", 9)).pack(side="left")
    app._load_startup_current_var = tk.StringVar(value="")
    ttk.Label(row1, text=" 电流：", font=("Arial", 9)).pack(side="left")
    ttk.Entry(row1, textvariable=app._load_startup_current_var, width=7).pack(side="left")
    ttk.Label(row1, text=" A", font=("Arial", 9)).pack(side="left")

    # ---- 基础信息 ----
    box_basic = ttk.LabelFrame(left_panel, text=" 基础信息 ", padding=10)
    box_basic.pack(fill="x", padx=8, pady=4)

    app._prod_name_var = tk.StringVar()
    app._input_voltage_lo_var = tk.StringVar()
    app._input_voltage_hi_var = tk.StringVar()
    app._output_voltage_min_var = tk.StringVar()
    app._output_voltage_max_var = tk.StringVar()
    app._output_power_var = tk.StringVar()
    app._power_segment_var = tk.IntVar(value=0)
    app._hv_power_var = tk.StringVar()
    app._lv_power_var = tk.StringVar()

    def _row_pack(parent, label_text, widget, side="left", padx_val=0):
        row = ttk.Frame(parent)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text=label_text, width=16, font=("Arial", 9)).pack(side="left")
        widget.pack(side=side, padx=padx_val)

    # 产品名称
    row = ttk.Frame(box_basic)
    row.pack(anchor="w", pady=2)
    ttk.Label(row, text="产品名称：", width=16, font=("Arial", 9)).pack(side="left")
    ttk.Entry(row, textvariable=app._prod_name_var, width=24).pack(side="left")

    # 输入电压范围
    row = ttk.Frame(box_basic)
    row.pack(anchor="w", pady=2)
    ttk.Label(row, text="输入电压范围(V)：", width=18, font=("Arial", 9)).pack(side="left")
    ttk.Entry(row, textvariable=app._input_voltage_lo_var, width=12).pack(side="left")
    ttk.Label(row, text=" ~ ", font=("Arial", 9)).pack(side="left")
    ttk.Entry(row, textvariable=app._input_voltage_hi_var, width=12).pack(side="left")

    # 输出电压范围
    row = ttk.Frame(box_basic)
    row.pack(anchor="w", pady=2)
    ttk.Label(row, text="输出电压范围(V)：", width=18, font=("Arial", 9)).pack(side="left")
    ttk.Entry(row, textvariable=app._output_voltage_min_var, width=10).pack(side="left")
    ttk.Label(row, text=" ~ ", font=("Arial", 9)).pack(side="left")
    ttk.Entry(row, textvariable=app._output_voltage_max_var, width=10).pack(side="left")
    # 输出功率规格
    row = ttk.Frame(box_basic)
    row.pack(anchor="w", pady=2)
    ttk.Label(row, text="输出功率规格(W)：", width=18, font=("Arial", 9)).pack(side="left")
    ttk.Entry(row, textvariable=app._output_power_var, width=24).pack(side="left")

    # 高低压功率分段
    row = ttk.Frame(box_basic)
    row.pack(anchor="w", pady=2)
    tk.Checkbutton(row, variable=app._power_segment_var, onvalue=1, offvalue=0,
                   text="高低压功率分段", font=("Arial", 9),
                   command=lambda: on_power_segment_toggle(app)).pack(side="left")

    # 高压段功率
    app._hv_power_row = ttk.Frame(box_basic)
    app._hv_power_row.pack(anchor="w", pady=2)
    ttk.Label(app._hv_power_row, text="高压段功率（W）：", width=16, font=("Arial", 9)).pack(side="left")
    app._hv_power_entry = ttk.Entry(app._hv_power_row, textvariable=app._hv_power_var,
                                     width=12, state="disabled")
    app._hv_power_entry.pack(side="left")

    # 低压段功率
    app._lv_power_row = ttk.Frame(box_basic)
    app._lv_power_row.pack(anchor="w", pady=2)
    ttk.Label(app._lv_power_row, text="低压段功率（W）：", width=16, font=("Arial", 9)).pack(side="left")
    app._lv_power_entry = ttk.Entry(app._lv_power_row, textvariable=app._lv_power_var,
                                     width=12, state="disabled")
    app._lv_power_entry.pack(side="left")

    # ---- 产品规格要求 ----
    box_spec = ttk.LabelFrame(left_panel, text=" 产品规格要求 ", padding=10)
    box_spec.pack(fill="x", padx=8, pady=(4, 8))

    app._spec_vars = {}

    # 平均能效要求（6级/7级）
    row = ttk.Frame(box_spec)
    row.pack(anchor="w", pady=2)
    ttk.Label(row, text="平均能效要求：", font=("Arial", 9)).pack(side="left")
    for label_text, spec_key in [("6级能效", "6级能效要求（%）"), ("7级能效", "7级能效要求（%）")]:
        var_en = tk.IntVar(value=0)
        app._spec_vars[spec_key] = {"enable": var_en}
        tk.Checkbutton(row, variable=var_en, onvalue=1, offvalue=0, width=3).pack(side="left")
        ttk.Label(row, text=label_text, font=("Arial", 9)).pack(side="left")

    # 其它产品规格（无勾选框，只有 lo/hi）
    for label_text in [
        "电压精度（%）", "大动态负载范围（%）", "小动态负载范围（%）",
        "开关机过冲（%）", "空载功耗（W）", "待机功耗（W）",
        "Brown-in（V）", "Brown-out（V）",
        "输出过压点（V）", "输出欠压点（V）", "输出过流点（%）",
        "纹波要求（mV）", "上升时间（ms）", "开机延迟时间（ms）",
    ]:
        row = ttk.Frame(box_spec)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text=label_text, font=("Arial", 9)).pack(side="left")
        right_box = ttk.Frame(row)
        right_box.pack(side="right")
        var_lo = tk.StringVar()
        var_hi = tk.StringVar()
        app._spec_vars[label_text] = {"lo": var_lo, "hi": var_hi}
        ttk.Entry(right_box, textvariable=var_lo, width=10).pack(side="left")
        ttk.Label(right_box, text="~", font=("Arial", 9)).pack(side="left")
        ttk.Entry(right_box, textvariable=var_hi, width=10).pack(side="left")

    # ---- 保护逻辑说明 ----
    box_prot = ttk.LabelFrame(left_panel, text=" 保护逻辑说明 ", padding=10)
    box_prot.pack(fill="x", padx=8, pady=(4, 8))

    app._prot_vars = {}
    for label_text, key_self, key_latch in [
        ("输入欠压保护", "uvp_self", "uvp_latch"),
        ("输出过压保护", "ovp_self", "ovp_latch"),
        ("输出过流保护", "ocp_self", "ocp_latch"),
    ]:
        row = ttk.Frame(box_prot)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text=label_text, font=("Arial", 9)).pack(side="left")
        right_box = ttk.Frame(row)
        right_box.pack(side="right")
        var_self = tk.IntVar(value=0)
        var_latch = tk.IntVar(value=0)
        app._prot_vars[label_text] = {"self": var_self, "latch": var_latch}
        tk.Checkbutton(right_box, text="自恢复", variable=var_self, onvalue=1, offvalue=0
                       ).pack(side="left", padx=(0, 8))
        tk.Checkbutton(right_box, text="锁死", variable=var_latch, onvalue=1, offvalue=0
                       ).pack(side="left")


def _build_right_panel(app, right_panel):
    """右面板：快充协议（QC / PD / UFCS）"""

    box_proto = ttk.LabelFrame(right_panel, text=" 快充协议 ", padding=10)
    box_proto.pack(fill="x", padx=8, pady=8)

    # QC
    box_qc = ttk.LabelFrame(box_proto, text=" QC ", padding=6)
    box_qc.pack(fill="x", padx=4, pady=4)
    app._qc_vars = {}
    for label_text, default_val in [
        ("QC2.0-5V",  "5V3A"),
        ("QC2.0-9V",  "9V2A"),
        ("QC2.0-12V", "12V1.5A"),
        ("QC2.0-20V", "20V0.9A"),
        ("QC3.0",     ""),
    ]:
        row = ttk.Frame(box_qc)
        row.pack(anchor="w", pady=1)
        cv = tk.IntVar(value=0)
        ev = tk.StringVar(value=default_val)
        app._qc_vars[label_text] = {"check": cv, "entry": ev}
        tk.Checkbutton(row, text=label_text, variable=cv, onvalue=1, offvalue=0
                       ).pack(side="left")
        ttk.Entry(row, textvariable=ev, width=14).pack(side="right")

    # PD
    box_pd = ttk.LabelFrame(box_proto, text=" PD ", padding=6)
    box_pd.pack(fill="x", padx=4, pady=4)
    app._pd_vars = {}
    for label_text, default_val in [
        ("PDO1", "5V3A"),
        ("PDO2", "9V3A"),
        ("PDO3", "15V3A"),
        ("PDO4", "20V3.25A"),
        ("PDO5", "PPS-10V6.6A"),
        ("PDO6", "PPS-11V6.1A"),
        ("PDO7", "PPS-20V3.25A"),
    ]:
        row = ttk.Frame(box_pd)
        row.pack(anchor="w", pady=1)
        cv = tk.IntVar(value=0)
        ev = tk.StringVar(value=default_val)
        app._pd_vars[label_text] = {"check": cv, "entry": ev}
        tk.Checkbutton(row, text=label_text, variable=cv, onvalue=1, offvalue=0
                       ).pack(side="left")
        ttk.Entry(row, textvariable=ev, width=14).pack(side="right")

    # UFCS
    box_ufcs = ttk.LabelFrame(box_proto, text=" UFCS ", padding=6)
    box_ufcs.pack(fill="x", padx=4, pady=4)
    app._ufcs_vars = {}
    for label_text in ["UFCS1档", "UFCS2档", "UFCS3档",
                        "UFCS4档", "UFCS5档", "UFCS6档", "UFCS7档"]:
        row = ttk.Frame(box_ufcs)
        row.pack(anchor="w", pady=1)
        cv = tk.IntVar(value=0)
        ev = tk.StringVar(value="")
        app._ufcs_vars[label_text] = {"check": cv, "entry": ev}
        tk.Checkbutton(row, text=label_text, variable=cv, onvalue=1, offvalue=0
                       ).pack(side="left")
        ttk.Entry(row, textvariable=ev, width=18).pack(side="right")
