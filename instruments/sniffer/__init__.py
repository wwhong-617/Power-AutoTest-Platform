# -*- coding: utf-8 -*-
"""
诱骗器 / 协议测试板 驱动包
支持芯片：IP2716
"""

from .IP2716 import IP2716Sniffer

__all__ = [
    "IP2716Sniffer",   # 英集芯 IP2716（基于 Excel 指令表）
]

DRIVER_MAP = {
    "IP2716Sniffer": IP2716Sniffer,
}
