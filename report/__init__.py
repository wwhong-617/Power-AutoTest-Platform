# -*- coding: utf-8 -*-
"""report package - 报告生成模块拆分"""

from report.writer import generate_excel
from report._xlsx_post import auto_generate
from report._data import _flatten
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
