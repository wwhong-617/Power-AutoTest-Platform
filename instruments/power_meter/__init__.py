# -*- coding: utf-8 -*-
"""
Power Meter 功率计驱动包
"""

from .BasePowerMeter import BasePowerMeter
from .WT322E import WT322E
from .WT333E import WT333E

__all__ = ["BasePowerMeter", "WT322E", "WT333E"]

DRIVER_MAP = {
    "WT333E": WT333E,
    "WT322E": WT322E,
}
