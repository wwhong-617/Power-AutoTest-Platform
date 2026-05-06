# -*- coding: utf-8 -*-
"""
测试条件页面 - build_test_conditions_page

从 config_ui._build_test_conditions_page 迁出。
负责测试条件 tab 的 UI 控件创建（Treeview + 操作按钮）。

注意：以下事件处理方法保留在 config_ui.py 中：
  - _generate_test_conditions()
  - _add_cond_row()
  - _rebuild_source_from_tree()
  - _delete_cond_row()
因为它们依赖大量 app 实例属性，迁出反而增加耦合。
"""
import tkinter as tk
from tkinter import ttk


def build_test_conditions_page(parent, app):
    """
    测试条件 tab：生成测试条件 + 添加/删除行 + Treeview 显示。
    """
    container = ttk.Frame(parent)
    container.pack(fill="both", expand=True)

    # ---- 顶部操作区 ----
    top_bar = ttk.Frame(container)
    top_bar.pack(fill="x", padx=8, pady=(8, 4))

    tk.Button(top_bar, text="生成测试条件", bg="#1E90FF", fg="white",
              font=("Arial", 10),
              command=app._generate_test_conditions).pack(side="left")

    ttk.Label(top_bar, text=(
        "根据产品信息配置的协议/电压/功率自动生成测试条件列表。"
        "充电器含协议输出，适配器按功率/电压计算输出电流。"),
              font=("Arial", 8), foreground="#555555").pack(side="left", padx=(16, 0))

    # ---- 添加/删除 按钮 ----
    btn_bar = ttk.Frame(container)
    btn_bar.pack(fill="x", padx=8, pady=(0, 4))

    tk.Button(btn_bar, text="添加行", bg="#228B22", fg="white",
              font=("Arial", 9),
              command=app._add_cond_row).pack(side="left")

    tk.Button(btn_bar, text="删除所选", bg="#DC143C", fg="white",
              font=("Arial", 9),
              command=app._delete_cond_row).pack(side="left", padx=(8, 0))

    # ---- 表格区域（Treeview）----
    table_frame = ttk.Frame(container)
    table_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))

    columns = ("col_type", "col_in_v", "col_freq", "col_proto", "col_out_v", "col_out_i")
    app._cond_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=18)

    col_configs = [
        ("col_type",   "产品类型",     70),
        ("col_in_v",   "输入电压(V)", 110),
        ("col_freq",   "频率(Hz)",     70),
        ("col_proto",  "协议",         100),
        ("col_out_v",  "输出电压(V)", 110),
        ("col_out_i",  "输出电流(A)", 110),
    ]

    for col_id, heading, width in col_configs:
        app._cond_tree.heading(col_id, text=heading)
        app._cond_tree.column(col_id, width=width, anchor="center")

    vsb = ttk.Scrollbar(table_frame, orient="vertical",
                         command=app._cond_tree.yview)
    app._cond_tree.configure(yscrollcommand=vsb.set)
    app._cond_tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    app._cond_tree.tag_configure("odd",  background="#F0F0F0")
    app._cond_tree.tag_configure("even", background="#FFFFFF")
