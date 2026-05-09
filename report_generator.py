# -*- coding: utf-8 -*-
"""
report_generator.py - 兼容垫片
==============================
所有逻辑已拆分至 report/ 包（_mappings / styles / _data / _xlsx_post / writer）。
本文件保留以确保现有 import 链路无需修改。
"""
from report import generate_excel, auto_generate, _flatten
from report._mappings import (
    _display_name, _cat, _cn, _get_cols,
    CASE_NAME_CN_MAP, CASE_TO_CATEGORY,
    GLOBAL_COLS, CASE_REGISTRY, CASE_CN_NAMES,
)
from report.styles import _mkstyle, _rfill, _fmt

__all__ = [
    "generate_excel",
    "auto_generate",
    "_flatten",
    "_display_name",
    "_cat",
    "_cn",
    "_get_cols",
    "_mkstyle",
    "_rfill",
    "_fmt",
    "GLOBAL_COLS",
    "CASE_REGISTRY",
    "CASE_CN_NAMES",
    "CASE_NAME_CN_MAP",
    "CASE_TO_CATEGORY",
]
