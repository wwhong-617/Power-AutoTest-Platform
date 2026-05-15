# -*- coding: utf-8 -*-
"""
_mappings.py - 报告生成器映射表与列定义
=========================================
所有映射常量、列定义集中于此。
"""

# 从 config_schema 导入用例注册表（唯一数据源）
from config_schema import CASE_REGISTRY, CASE_CN_NAMES

# ============================================================
# 映射表
# ============================================================

# 英文 key -> 中文显示名（只取 tuple 第0项，兼容旧版字符串）
def _display_name(en: str) -> str:
    v = CASE_CN_NAMES.get(en, en)
    return v[0] if isinstance(v, tuple) else v

# 英文 key -> 中文名（短名，用于内部 key）
CASE_NAME_CN_MAP = {en: _display_name(en) for en in CASE_CN_NAMES}

# 中文显示名（含"测试"后缀）-> 分类
_CASE_CN_TO_CATEGORY = {
    "输入":    "输入测试",
    "输出":    "输出测试",
    "协议":    "协议测试",
}

def _cat(cn: str) -> str:
    """
    根据中文名推断分类。
    先检查是否为保护类（关键词在任意位置），再按前缀匹配输入/输出/协议。
    """
    # 保护类关键词：可能在名字中间，不只是前缀
    for kw in ["过流", "过压", "欠压", "过温", "短路"]:
        if kw in cn:
            return "保护功能测试"
    # 输入/输出/协议：按前缀匹配
    for prefix, category in _CASE_CN_TO_CATEGORY.items():
        if cn.startswith(prefix):
            return category
    return "其他"

CASE_TO_CATEGORY = {en: _cat(cn) for en, cn in CASE_NAME_CN_MAP.items()}

def _cn(en: str) -> str:
    return CASE_NAME_CN_MAP.get(en, en)

# ============================================================
# 列定义
# ============================================================

DEFAULT_COLS = [
    ("序号",      6),
    ("输入电压",  12),
    ("频率",       8),
    ("协议",      12),
    ("输出电压",  12),
    ("输出电流",  12),
    ("规格上限",  13),
    ("规格下限",  13),
    ("最大值",    13),
    ("有效值",    13),
    ("最小值",    13),
    ("测试结论",  13),
    ("测试波形",  12),
    ("备注",      32),
]

GLOBAL_COLS = [
    ("序号",               6),
    ("用例名称",          18),
    ("输入条件",          18),
    ("协议",              14),
    ("输出电压(V)",       14),
    ("输出电流(A)",       14),
    ("最大值",            13),
    ("最小值",            13),
    ("有效值",            13),
    ("纹波要求",          13),
    ("纹波实测值(mV)",    16),
    ("效率(%)",           10),
    ("测试结论",          12),
    ("备注",              32),
]

def _get_cols(case_name_en: str = None):
    return GLOBAL_COLS
