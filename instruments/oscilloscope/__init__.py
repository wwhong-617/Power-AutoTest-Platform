# -*- coding: utf-8 -*-
"""
Oscilloscope 示波器驱动包
"""

from .BaseOscilloscope import BaseOscilloscope
from .DSOX4024A import DSOX4024A
from .TBS2000 import TBS2000

__all__ = ["BaseOscilloscope", "DSOX4024A", "TBS2000"]

DRIVER_MAP = {
    "DSOX4024A": DSOX4024A,
    "TBS2000":   TBS2000,
}
