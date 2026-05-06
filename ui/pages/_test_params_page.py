# -*- coding: utf-8 -*-
"""
测试参数页面 - build_test_params_page

从 config_ui._build_test_params_page 迁出。
负责示波器通道 + 功率计通道 + 电子负载通道 + 动态测试参数 tab。

在 app 上创建以下属性：
  _osc_in_ch_var, _osc_out_ch_var, _osc_in_attn_var
  _osc_out_attn_var, _osc_dyn_ch_var, _osc_dyn_attn_var
  _pwr_in_v_ch_var, _pwr_in_i_ch_var, _pwr_out_v_ch_var, _pwr_out_i_ch_var
  _eload_vout1_ch_var, _eload_vout2_ch_var
  _warmup_var, _onoff_cycle_var, _short_cycle_var
  _dyn_large_tree, _dyn_small_tree
"""
import tkinter as tk
from tkinter import ttk, messagebox


def build_test_params_page(parent, app):
    """
    测试参数配置页面。

    左1/2：示波器通道设置 + 功率计通道设置 + 负载通道设置 + 其他参数
    右1/2：大动态测试设置 + 小动态测试设置
    """
    container = ttk.Frame(parent)
    container.pack(fill="both", expand=True)

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

    # ==================== 右面板：动态测试设置 ====================
    _build_right_panel(app, right_panel)


def _build_left_panel(app, left_panel):
    """左面板：示波器通道 + 功率计通道 + 负载通道 + 其他参数"""

    # ---- 示波器通道设置 ----
    box_osc = ttk.LabelFrame(left_panel, text=" 示波器通道设置 ", padding=10)
    box_osc.pack(fill="x", padx=8, pady=(8, 6))

    app._osc_in_ch_var = tk.StringVar(value="CH4")
    app._osc_out_ch_var = tk.StringVar(value="CH2")
    app._osc_in_attn_var = tk.StringVar(value="1.0")
    app._osc_out_attn_var = tk.StringVar(value="1.0")
    app._osc_dyn_ch_var = tk.StringVar(value="CH2")
    app._osc_dyn_attn_var = tk.StringVar(value="1.0")

    def _osc_row(parent, label_text, var, values):
        row = ttk.Frame(parent)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text=label_text, width=16, font=("Arial", 9)).pack(side="left")
        ttk.Combobox(row, textvariable=var, values=values,
                     state="readonly", width=8).pack(side="left")
        ttk.Label(row, text="  衰减比例：", font=("Arial", 9)).pack(side="left")
        ttk.Entry(row, textvariable=app._osc_in_attn_var if "输入" in label_text else
                  app._osc_out_attn_var if "输出" in label_text else app._osc_dyn_attn_var,
                  width=8).pack(side="left")

    _osc_row(box_osc, "输入电压波形：", app._osc_in_ch_var, ["CH1","CH2","CH3","CH4"])
    _osc_row(box_osc, "输出电压波形：", app._osc_out_ch_var, ["CH1","CH2","CH3","CH4"])
    _osc_row(box_osc, "动态电压波形：", app._osc_dyn_ch_var, ["CH1","CH2","CH3","CH4"])

    # ---- 功率计通道设置 ----
    box_pwr = ttk.LabelFrame(left_panel, text=" 功率计通道设置 ", padding=10)
    box_pwr.pack(fill="x", padx=8, pady=6)

    app._pwr_in_v_ch_var = tk.StringVar(value="CH1")
    app._pwr_in_i_ch_var = tk.StringVar(value="CH1")
    app._pwr_out_v_ch_var = tk.StringVar(value="CH1")
    app._pwr_out_i_ch_var = tk.StringVar(value="CH1")

    for lbl, var in [
        ("输入电压：", app._pwr_in_v_ch_var),
        ("输入电流：", app._pwr_in_i_ch_var),
        ("输出电压：", app._pwr_out_v_ch_var),
        ("输出电流：", app._pwr_out_i_ch_var),
    ]:
        row = ttk.Frame(box_pwr)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text=lbl, width=16, font=("Arial", 9)).pack(side="left")
        ttk.Combobox(row, textvariable=var, values=["CH1","CH2","CH3","CH4"],
                     state="readonly", width=8).pack(side="left")

    # ---- 负载通道设置 ----
    box_eload = ttk.LabelFrame(left_panel, text=" 负载通道设置 ", padding=10)
    box_eload.pack(fill="x", padx=8, pady=6)

    app._eload_vout1_ch_var = tk.StringVar(value="CH1")
    app._eload_vout2_ch_var = tk.StringVar(value="CH1")

    for lbl, var in [
        ("Vout1+ 通道：", app._eload_vout1_ch_var),
        ("Vout2+ 通道：", app._eload_vout2_ch_var),
    ]:
        row = ttk.Frame(box_eload)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text=lbl, width=16, font=("Arial", 9)).pack(side="left")
        ttk.Combobox(row, textvariable=var, values=["CH1","CH2","CH3","CH4"],
                     state="readonly", width=8).pack(side="left")

    # ---- 其他参数设置 ----
    box_other = ttk.LabelFrame(left_panel, text=" 其他参数设置 ", padding=10)
    box_other.pack(fill="x", padx=8, pady=(6, 8))

    app._warmup_var = tk.StringVar()
    app._onoff_cycle_var = tk.StringVar()
    app._short_cycle_var = tk.StringVar()

    def _entry_row(parent, label_text, var, note=""):
        row = ttk.Frame(parent)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text=label_text, font=("Arial", 9)).pack(side="left")
        ttk.Entry(row, textvariable=var, width=20).pack(side="left", padx=(4, 0))
        if note:
            ttk.Label(row, text=note, font=("Arial", 8),
                      foreground="#666666").pack(side="left", padx=(8, 0))

    _entry_row(box_other, "热机时间(min):", app._warmup_var)
    _entry_row(box_other, "反复开关机周期(s):", app._onoff_cycle_var,
               "例：10-10，开机10s关机10s")
    _entry_row(box_other, "反复短路周期(s):", app._short_cycle_var,
               "例：10-10，开机10s短路10s")


def _build_right_panel(app, right_panel):
    """右面板：大动态测试设置 + 小动态测试设置"""

    dyn_cols = ["UP(%)", "UP斜率(A/us)", "DOWN(%)", "DOWN斜率(A/us)", "频率(Hz)", "比例(%)"]

    _build_dyn_box(app, right_panel, " 大动态测试设置 ", dyn_cols, "_dyn_large_tree")
    _build_dyn_box(app, right_panel, " 小动态测试设置 ", dyn_cols, "_dyn_small_tree")


def _build_dyn_box(app, parent, title, columns, tree_ref_attr):
    """
    构建动态测试设置框（表格 + 滚动条 + 添加/删除 + 双击编辑）。
    """
    box = ttk.LabelFrame(parent, text=title, padding=5)
    box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # 表格区域
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
    setattr(app, tree_ref_attr, tree)

    # 弹窗添加行
    def _popup_add_row():
        from tkinter import Toplevel
        top = Toplevel(app.root)
        top.title("添加动态测试参数")
        top.geometry("580x280")
        top.transient(app.root)
        top.grab_set()

        col_labels = ["UP(%)", "UP斜率(A/us)", "DOWN(%)", "DOWN斜率(A/us)", "频率(Hz)", "比例(%)"]
        entry_vars = {}
        for lbl in col_labels:
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
              command=lambda _t=tree: [_t.delete(i) for i in _t.selection()]
              ).pack(side="left", padx=(8, 0))

    # 双击编辑单元格
    def _start_edit(event):
        region = tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col_id = tree.identify_column(event.x)
        col_idx = int(col_id.replace("#", "")) - 1
        row_id = tree.identify_row(event.y)
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
