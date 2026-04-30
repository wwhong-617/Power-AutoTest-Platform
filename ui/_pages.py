# -*- coding: utf-8 -*-
"""
UI Page 构建器 - ConfigUI 的各个 Tab 页面构建逻辑

本文件负责所有页面（Tab）的 UI 控件创建。
每个方法签名为：build_xxx_page(parent, app)
  - parent: tkinter 父容器
  - app: ConfigUI 实例（用于访问 self._xxx 属性/方法）

当前状态：骨架文件，方法为 thin wrapper，逐步提取中。
完整拆分需要将各 page 方法中创建的实例变量（如 self._xxx_var）
迁移到 ui/_state.py 中统一管理。
"""
import tkinter as tk
from tkinter import ttk, messagebox


# ============================================================
# 页面 1：仪器连接配置
# ============================================================

def build_device_config_page(parent, app):
    """
    仪器连接配置 Tab。

    创建：
    - USB 扫描按钮 + 连接/断开按钮
    - DEVICE_DEFS 中每个设备的勾选框 + 地址输入框 + 型号下拉框
    - 内部调用 _build_device_frame() 为每个设备创建一行
    """
    app._build_device_config_page(parent)


# ============================================================
# 页面 2：产品信息
# ============================================================

def build_product_info_page(parent, app):
    """
    产品信息 Tab。

    创建：
    - 产品名称输入、产品类型单选（充电器/适配器）
    - 输入电压范围、输出电压/功率
    - 高压/低压功率段
    - 负载开机配置
    - specs/protection_logic 的动态编辑表格（参考 _build_test_params_page）
    """
    app._build_product_info_page(parent)


# ============================================================
# 页面 3：测试参数
# ============================================================

def build_test_params_page(parent, app):
    """
    测试参数 Tab。

    创建：
    - 示波器通道配置（输入/输出/动态通道 + 衰减比）
    - 功率计通道配置
    - 电子负载通道配置
    - 动态负载参数（大电流/小电流）
    - 预热时间、开关机周期、短路周期
    """
    app._build_test_params_page(parent)


# ============================================================
# 页面 4：测试条件
# ============================================================

def build_test_conditions_page(parent, app):
    """
    测试条件 Tab。

    创建：
    - 工具栏：自动生成、导入、导出按钮
    - 测试条件 Treeview（产品类型/Vin/Freq/协议/Vout/Iout）
    - 添加/删除/编辑行按钮
    - 协议类型解析
    - 内部调用 _add_cond_row() / _delete_cond_row()
    """
    app._build_test_conditions_page(parent)


# ============================================================
# 页面 5：测试用例
# ============================================================

def build_test_cases_page(parent, app):
    """
    测试用例 Tab。

    创建：
    - 4 个分类收拢区（输入测试/输出测试/保护测试/协议测试）
    - 每个用例的 Checkbox + 名称标签
    - 分类全选/取消全选按钮
    - 用例说明显示（Flow 文字）
    - 内部调用 _create_case_row() / on_check() / on_cat_click()
    """
    app._build_test_cases_page(parent)


# ============================================================
# 待提取的共享 UI 组件（可独立使用）
# ============================================================

def build_specs_table(parent, spec_vars, specs_flat, key, row_start=0):
    """
    通用 specs 动态表格构建器。

    Args:
        parent: tkinter 父容器
        spec_vars: {spec_key: {'check': IntVar, 'value': StringVar}}
        specs_flat: {key: default_value}
        key: spec 分类 key
        row_start: 起始行号
    """
    pass  # TODO: 从 _build_product_info_page / _build_test_params_page 提取


def build_dyn_load_table(parent, title, columns, tree, row_fields):
    """
    通用动态负载参数表格构建器。

    Args:
        parent: tkinter 父容器
        title: 表格标题
        columns: 列名列表
        tree: tkinter.Treeview 实例
        row_fields: 行数据字段列表
    """
    pass  # TODO: 从 _build_test_params_page 提取


def create_case_row(parent_frame, case_name, row_idx, app, var):
    """
    用例行创建：Checkbox + 名称 Label。

    Args:
        parent_frame: 分类 Frame
        case_name: 用例中文名
        row_idx: 行号
        app: ConfigUI 实例
        var: tk.BooleanVar（勾选状态）
    """
    pass  # TODO: 从 _build_test_cases_page 提取
