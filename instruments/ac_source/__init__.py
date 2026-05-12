# -*- coding: utf-8 -*-
"""
AC Source 交流源驱动包
"""

from .BaseACSource import BaseACSource
from .IT7321 import IT7321
from .IT7322 import IT7322
from .IT7821E import IT7821E

__all__ = ["BaseACSource", "IT7321", "IT7322", "IT7821E"]

# 型号 → 类名 映射
DRIVER_MAP = {
    "IT7321": IT7321,
    "IT7322": IT7322,
    "IT7821E": IT7821E,
}
