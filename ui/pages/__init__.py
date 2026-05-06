# -*- coding: utf-8 -*-
"""
UI 页面模块 - config_ui 各 Tab 页面构建逻辑

各模块职责：
  _device_page.py      - 仪器连接 tab
  _product_page.py     - 产品信息 + 规格 + 保护逻辑 + 快充协议 tab
  _test_params_page.py - 示波器/功率计/eload通道 + 动态测试参数 tab
  _conditions_page.py  - 测试条件 Treeview + 生成/添加/删除 tab
  _cases_page.py       - 测试用例树 + 详情面板 + 运行控制/日志/进度条 tab

每个方法签名：build_xxx_page(parent, app)
  - parent: tkinter 父容器
  - app: ConfigUI 实例（用于访问/写入 app._xxx 属性）
"""

from ui.pages._device_page import build_device_config_page
from ui.pages._product_page import build_product_info_page
from ui.pages._test_params_page import build_test_params_page
from ui.pages._conditions_page import build_test_conditions_page
from ui.pages._cases_page import build_test_cases_page

__all__ = [
    "build_device_config_page",
    "build_product_info_page",
    "build_test_params_page",
    "build_test_conditions_page",
    "build_test_cases_page",
]
