# -*- coding: utf-8 -*-
"""
AC Source 交流源驱动包
"""

from .BaseACSource import BaseACSource
from .IT7321 import IT7321
from .IT7322 import IT7322

__all__ = ["BaseACSource", "IT7321", "IT7322"]

# 型号 → 类名 映射
DRIVER_MAP = {
    "IT7321": IT7321,
    "IT7322": IT7322,
}
