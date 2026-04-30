# -*- coding: utf-8 -*-
"""
Electronic Load 电子负载驱动包
"""

from .BaseElectronicLoad import BaseElectronicLoad, LoadMode
from .IT8511 import IT8511
from .IT8512 import IT8512
from .IT8701P import IT8701P

__all__ = ["BaseElectronicLoad", "LoadMode", "IT8511", "IT8512", "IT8701P"]

# 型号 → 类名 映射（供 InstrumentManager 动态实例化）
DRIVER_MAP = {
    "IT8511":  IT8511,
    "IT8512":  IT8512,
    "IT8701P": IT8701P,
}
