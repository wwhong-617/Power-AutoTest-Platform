# -*- coding: utf-8 -*-
"""
测试用例页面 - build_test_cases_page

从 config_ui._build_test_cases_page 迁出。
负责测试用例 tab 的 UI 控件创建：
  - 左侧：用例树（Canvas + 分类收拢/展开）
  - 中间：测试详情（名称/条件/步骤）
  - 右侧：运行控制（按钮/进度条/日志）

在 app 上创建以下属性：
  _test_case_defs, _case_cn_to_en, _case_vars, _case_name_labels
  _selected_case, _cat_case_frames, _cat_expanded, _cat_triangle_labels
  _case_name_var, _filtered_cond_tree, _case_step_text
  _btn_run, _btn_pause, _btn_stop
  _case_progress, _case_progress_label, _run_log

注意：事件处理方法保留在 config_ui.py：
  _select_all_cases, _invert_all_cases, _get_test_case_flow,
  _filter_conditions_by_case, _apply_filtered_conditions
"""
import tkinter as tk
from test_engine import TestEngine, CASE_CN_NAMES
from tkinter import ttk


def build_test_cases_page(parent, app):
    """
    测试用例页面。

    左1/4：用例树（5大类，可收拢展开）
    中2/4：测试详情（名称/条件/步骤）
    右1/4：运行控制（按钮/进度条/运行日志）
    """
    container = ttk.Frame(parent)
    container.pack(fill="both", expand=True)

    left_panel = ttk.Frame(container)
    middle_panel = ttk.Frame(container)
    right_panel = ttk.Frame(container)
    left_panel.pack(side="left", fill="both", expand=True)
    middle_panel.pack(side="left", fill="both", expand=True)
    right_panel.pack(side="right", fill="both", expand=True)

    def _adjust(event):
        total = max(800, event.width)
        lw = max(180, total // 4)
        mw = max(350, total // 2)
        rw = total - lw - mw
        left_panel.config(width=lw)
        middle_panel.config(width=mw)
        right_panel.config(width=rw)

    container.bind("<Configure>", _adjust)

    _build_left_panel(app, left_panel)
    _build_middle_panel(app, middle_panel)
    _build_right_panel(app, right_panel)

    # 初始化 Treeview：默认显示提示行
    app._filtered_cond_tree.delete(*app._filtered_cond_tree.get_children())
    app._filtered_cond_tree.insert("", "end",
                                   values=("请在左侧选择测试用例", "", "", "", "", ""))


def _build_left_panel(app, left_panel):
    """左面板：测试用例树（Canvas + 分类收拢/展开）"""
    ttk.Label(left_panel, text="测试用例", font=("Arial", 10, "bold")
              ).pack(anchor="w", padx=6, pady=(6, 2))

    btn_bar = ttk.Frame(left_panel)
    btn_bar.pack(fill="x", padx=6, pady=(0, 4))

    tk.Button(btn_bar, text="全选", bg="#1E90FF", fg="white",
              font=("Arial", 8),
              command=app._select_all_cases).pack(side="left", padx=(0, 4))

    tk.Button(btn_bar, text="反选", bg="#FF8C00", fg="white",
              font=("Arial", 8),
              command=app._invert_all_cases).pack(side="left")

    # Canvas 结构
    case_canvas_frame = tk.Frame(left_panel, bg="#F5F5F5")
    case_canvas_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    case_canvas = tk.Canvas(case_canvas_frame, bg="#F5F5F5", highlightthickness=0)
    case_scroll = ttk.Scrollbar(case_canvas_frame, orient="vertical",
                                  command=case_canvas.yview)
    case_canvas.configure(yscrollcommand=case_scroll.set)
    scroll_inner = tk.Frame(case_canvas, bg="#F5F5F5")

    case_canvas.pack(side="left", fill="both", expand=True)
    case_scroll.pack(side="right", fill="y")

    # ---- 用例分类初始化 ----
    app._test_case_defs = {}
    for en_key, cn_name in CASE_CN_NAMES.items():
        if "极限" in cn_name:
            category = "极限测试"
        elif "保护" in cn_name:
            category = "保护测试"
        elif cn_name.startswith("输入"):
            category = "输入测试"
        elif cn_name.startswith("输出"):
            category = "输出测试"
        elif "协议" in cn_name:
            category = "协议测试"
        else:
            category = "其他"
        if category not in app._test_case_defs:
            app._test_case_defs[category] = []
        app._test_case_defs[category].append(cn_name)

    app._case_cn_to_en = {}
    for en_key, cn_name in CASE_CN_NAMES.items():
        app._case_cn_to_en[cn_name] = en_key
        if cn_name.endswith("测试"):
            app._case_cn_to_en[cn_name[:-2]] = en_key

    app._case_vars = {}
    app._case_name_labels = {}
    app._selected_case = None
    app._cat_case_frames = {}
    app._cat_expanded = {}
    app._cat_triangle_labels = {}

    ROW_H = 26
    CAT_PAD = 4
    CB_PADX = 6

    # ---- 创建用例行 ----
    def _create_case_row(parent_frame, case_name):
        row = tk.Frame(parent_frame, bg="#F5F5F5")
        row.pack(fill="x")
        var = tk.BooleanVar(value=False)
        app._case_vars[case_name] = var

        def on_check():
            app._apply_filtered_conditions()

        cb = tk.Checkbutton(row, text="", variable=var, onvalue=True, offvalue=False,
                            command=on_check, bg="#F5F5F5", anchor="w")
        cb.pack(side="left", padx=(CB_PADX, 2))

        lbl = tk.Label(row, text=case_name, font=("Arial", 9),
                       bg="#F5F5F5", anchor="w", cursor="hand2")
        lbl.pack(side="left", fill="x", expand=True, padx=(0, 4))

        def on_name_click(e, name=case_name):
            app._selected_case = name
            for n, lbl_el in app._case_name_labels.items():
                lbl_el.config(bg="#D0E8FF" if n == name else "#F5F5F5",
                              fg="#1A1A1A" if n == name else "#444444")
            app._case_name_var.set(name)
            app._case_step_text.config(state="normal")
            app._case_step_text.delete("1.0", "end")
            app._case_step_text.insert("end", app._get_test_case_flow(name))
            app._case_step_text.config(state="disabled")
            en_key = app._case_cn_to_en.get(name, name)
            # 勾选对应 checkbox，触发 on_check 刷新过滤结果
            app._case_vars[name].set(True)
            app._apply_filtered_conditions(selected_case=en_key)

        lbl.bind("<Button-1>", on_name_click)
        app._case_name_labels[case_name] = lbl
        return row

    # ---- 分类和用例行 ----
    for category, cases in app._test_case_defs.items():
        app._cat_case_frames[category] = {}
        app._cat_expanded[category] = False

        cat_container = tk.Frame(scroll_inner, bg="#E0E0E0")
        cat_container.pack(fill="x", pady=(CAT_PAD, 0))

        cat_header = tk.Frame(cat_container, bg="#E0E0E0")
        cat_header.pack(fill="x")

        tri_lbl = tk.Label(cat_header, text="▶", font=("Arial", 8),
                           bg="#E0E0E0", anchor="w", cursor="hand2", width=2)
        tri_lbl.pack(side="left", padx=(6, 2))
        app._cat_triangle_labels[category] = tri_lbl

        cat_lbl = tk.Label(cat_header, text=category, font=("Arial", 9, "bold"),
                           bg="#E0E0E0", anchor="w")
        cat_lbl.pack(side="left", fill="x", expand=True, padx=(0, 4), pady=2)

        case_container = tk.Frame(cat_container, bg="#F5F5F5")

        def on_cat_click(e, case_container=case_container, tri=tri_lbl, cat=category):
            expanded = app._cat_expanded[cat]
            app._cat_expanded[cat] = not expanded
            tri.config(text="▼" if not expanded else "▶")
            if expanded:
                case_container.pack_forget()
            else:
                case_container.pack(fill="x", pady=(0, 0))
            scroll_inner.update_idletasks()
            case_canvas.configure(scrollregion=case_canvas.bbox("all"))

        cat_lbl.bind("<Button-1>", on_cat_click)
        tri_lbl.bind("<Button-1>", on_cat_click)

        for case_name in cases:
            row = _create_case_row(case_container, case_name)
            app._cat_case_frames[category][case_name] = row

    # Canvas 滚动配置
    def _on_frame_configure(e):
        case_canvas.configure(scrollregion=case_canvas.bbox("all"))

    scroll_inner.bind("<Configure>", _on_frame_configure)

    def _on_canvas_configure(e):
        case_canvas.itemconfig(scroll_window, width=e.width)

    scroll_window = case_canvas.create_window((0, 0), window=scroll_inner, anchor="nw")
    case_canvas.bind("<Configure>", _on_canvas_configure)
    case_canvas.yview_moveto(0)


def _build_middle_panel(app, middle_panel):
    """中间面板：测试详情（名称/条件/步骤）"""
    ttk.Label(middle_panel, text="测试详情", font=("Arial", 10, "bold")
              ).pack(anchor="w", padx=6, pady=(6, 4))

    detail_frame = ttk.LabelFrame(middle_panel, text=" 测试详情 ", padding=8)
    detail_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    # 测试名称
    name_row = ttk.Frame(detail_frame)
    name_row.pack(fill="x", pady=(0, 6))
    ttk.Label(name_row, text="测试名称：", font=("Arial", 9)).pack(side="left")
    app._case_name_var = tk.StringVar()
    ttk.Entry(name_row, textvariable=app._case_name_var,
              font=("Arial", 9)).pack(side="left", fill="x", expand=True, padx=(4, 0))

    # 测试条件
    cond_header = ttk.Frame(detail_frame)
    cond_header.pack(fill="x", pady=(4, 2))
    ttk.Label(cond_header, text="测试条件：", font=("Arial", 9)).pack(side="left")

    cond_tree_frame = ttk.Frame(detail_frame)
    cond_tree_frame.pack(fill="both", expand=True, pady=(0, 6))

    cond_cols = ("col_type", "col_in_v", "col_freq", "col_proto", "col_out_v", "col_out_i")
    app._filtered_cond_tree = ttk.Treeview(cond_tree_frame, columns=cond_cols,
                                           show="headings", height=2)
    for col_id, heading, width in [
        ("col_type", "类型", 70), ("col_in_v", "输入电压(V)", 100),
        ("col_freq", "频率(Hz)", 70), ("col_proto", "协议", 100),
        ("col_out_v", "输出电压(V)", 100), ("col_out_i", "输出电流(A)", 100)]:
        app._filtered_cond_tree.heading(col_id, text=heading)
        app._filtered_cond_tree.column(col_id, width=width, anchor="center")

    cond_y = ttk.Scrollbar(cond_tree_frame, orient="vertical",
                             command=app._filtered_cond_tree.yview)
    app._filtered_cond_tree.configure(yscrollcommand=cond_y.set)
    app._filtered_cond_tree.pack(side="left", fill="both", expand=True)
    cond_y.pack(side="right", fill="y")

    # 测试步骤
    step_lbl = ttk.Label(detail_frame, text="测试步骤：", font=("Arial", 9))
    step_lbl.pack(anchor="w", pady=(4, 2))

    app._case_step_text = tk.Text(detail_frame, font=("Arial", 9),
                                    height=12, wrap="word", bg="#F8F8F8",
                                    state="disabled")
    step_scroll = ttk.Scrollbar(detail_frame, orient="vertical",
                                  command=app._case_step_text.yview)
    app._case_step_text.configure(yscrollcommand=step_scroll.set)
    app._case_step_text.pack(side="left", fill="both", expand=True)
    step_scroll.pack(side="right", fill="y")


def _build_right_panel(app, right_panel):
    """右侧面板：运行控制（按钮/进度条/运行日志）"""
    ttk.Label(right_panel, text="测试运行", font=("Arial", 10, "bold")
              ).pack(anchor="w", padx=6, pady=(6, 4))

    # 操作按钮
    btn_box = ttk.Frame(right_panel)
    btn_box.pack(fill="x", padx=6, pady=(0, 6))

    app._btn_run = tk.Button(btn_box, text="运行", bg="#228B22", fg="white",
                              font=("Arial", 10, "bold"), width=7,
                              command=app._run_tests)
    app._btn_run.pack(side="left", padx=(0, 4))

    app._btn_pause = tk.Button(btn_box, text="暂停", bg="#FF8C00", fg="white",
                                font=("Arial", 10), width=7,
                                command=app._pause_tests, state="disabled")
    app._btn_pause.pack(side="left", padx=(0, 4))

    app._btn_stop = tk.Button(btn_box, text="停止", bg="#DC143C", fg="white",
                               font=("Arial", 10), width=7,
                               command=app._stop_tests, state="disabled")
    app._btn_stop.pack(side="left")

    # 进度条
    prog_frame = ttk.Frame(right_panel)
    prog_frame.pack(fill="x", padx=6, pady=(0, 6))

    ttk.Label(prog_frame, text="运行进度：", font=("Arial", 8)).pack(anchor="w")
    app._case_progress = ttk.Progressbar(prog_frame, mode="determinate")
    app._case_progress.pack(fill="x", pady=(2, 0))
    app._case_progress_label = ttk.Label(prog_frame, text="0 / 0",
                                          font=("Arial", 8))
    app._case_progress_label.pack(anchor="e")

    # 运行日志
    log_box = ttk.LabelFrame(right_panel, text=" 运行日志 ", padding=4)
    log_box.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    app._run_log = tk.Text(log_box, font=("Courier New", 8),
                            bg="black", fg="#00FF00",
                            insertbackground="white", wrap="word", height=20)
    run_y = ttk.Scrollbar(log_box, orient="vertical",
                            command=app._run_log.yview)
    app._run_log.configure(yscrollcommand=run_y.set)
    app._run_log.pack(side="left", fill="both", expand=True)
    run_y.pack(side="right", fill="y")
