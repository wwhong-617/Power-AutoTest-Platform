# -*- coding: utf-8 -*-
"""
Oscilloscope 示波器驱动包
"""

from .BaseOscilloscope import BaseOscilloscope
from .DSOX4024A import DSOX4024A

__all__ = ["BaseOscilloscope", "DSOX4024A"]

DRIVER_MAP = {
    "DSOX4024A": DSOX4024A,
}
