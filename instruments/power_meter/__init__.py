# -*- coding: utf-8 -*-
"""
Power Meter 功率计驱动包
"""

from .BasePowerMeter import BasePowerMeter
from .WT322E import WT322E
from .WT333E import WT333E
from .AN87330 import AN87330

__all__ = ["BasePowerMeter", "WT322E", "WT333E", "AN87330"]

DRIVER_MAP = {
    "WT333E": WT333E,
    "WT322E": WT322E,
    "AN87330": AN87330,
}
