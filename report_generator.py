# -*- coding: utf-8 -*-
"""
report_generator.py - 兼容垫片
==============================
所有逻辑已迁移至 report/ 包。
本文件保留以确保现有 import 链路无需修改。

请改为直接 import：
    from report.generator import generate_excel, auto_generate
    from report import auto_generate
"""

import os
import sys

if os.path.dirname(__file__) not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))

# 旧路径 → 新路径映射
from report.generator import generate_excel, auto_generate
from report._mappings import (
    _display_name, _cat, _cn, _get_cols, _get_case_cols,
    CASE_NAME_CN_MAP, CASE_TO_CATEGORY,
    GLOBAL_COLS, CASE_REGISTRY, CASE_CN_NAMES,
)
from report.writer import _flatten
from report.styles import _mkstyle, _rfill, _rfont, _fmt

__all__ = [
    "generate_excel",
    "auto_generate",
    "_display_name",
    "_cat",
    "_cn",
    "_get_cols",
    "_get_case_cols",
    "_flatten",
    "_warn_missing_fields",
    "_mkstyle",
    "_rfill",
    "_rfont",
    "_fmt",
    "GLOBAL_COLS",
    "CASE_REGISTRY",
    "CASE_CN_NAMES",
    "CASE_NAME_CN_MAP",
    "CASE_TO_CATEGORY",
]


def _warn_missing_fields(name_en: str, sr: dict):
    """兼容：已废弃，不再强制检查字段"""
    pass
