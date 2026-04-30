# -*- coding: utf-8 -*-
"""
设备扫描工具函数（无 UI 依赖，可独立测试）
"""
import ctypes
import serial
import time


# ============================================================
# USB VISA 设备扫描
# ============================================================

def query_usb_idn(addr):
    """对指定 USB VISA 地址发送 *IDN? 并返回响应字符串"""
    backends = [
        r'C:\Windows\System32\visa32.dll',
        '@py',
    ]
    for backend in backends:
        try:
            import pyvisa
            rm = pyvisa.ResourceManager(backend)
            instr = rm.open_resource(addr, timeout=3000)
            idn = instr.query('*IDN?').strip()
            instr.close()
            rm.close()
            return idn
        except Exception:
            continue
    return None


def get_usb_visa():
    """用 ctypes NI VISA DLL 枚举所有 USB 仪器地址，返回 [addr, ...]"""
    results = []
    try:
        dll = ctypes.CDLL(r'C:\Windows\System32\visa32.dll')
        dll.viOpenDefaultRM.restype = ctypes.c_int
        dll.viOpenDefaultRM.argtypes = [ctypes.POINTER(ctypes.c_uint32)]
        dll.viFindRsrc.restype = ctypes.c_int
        dll.viFindRsrc.argtypes = [ctypes.c_uint32, ctypes.c_char_p,
                                    ctypes.POINTER(ctypes.c_uint32),
                                    ctypes.POINTER(ctypes.c_uint32),
                                    ctypes.c_char_p]
        dll.viFindNext.restype = ctypes.c_int
        dll.viFindNext.argtypes = [ctypes.c_uint32, ctypes.c_char_p]
        dll.viClose.restype = ctypes.c_int
        dll.viClose.argtypes = [ctypes.c_uint32]
        rm = ctypes.c_uint32()
        ret = dll.viOpenDefaultRM(ctypes.byref(rm))
        if ret != 0:
            return results
        vi = ctypes.c_uint32()
        cnt = ctypes.c_uint32()
        desc = ctypes.create_string_buffer(256)
        r = dll.viFindRsrc(rm, b'USB?*',
                            ctypes.byref(vi),
                            ctypes.byref(cnt), desc)
        if r == 0:
            seen = set()
            for _ in range(cnt.value):
                addr = desc.value.decode()
                if addr and addr not in seen:
                    seen.add(addr)
                    results.append(addr)
                if _ < cnt.value - 1:
                    dll.viFindNext(vi, desc)
        dll.viClose(vi)
        dll.viClose(rm)
    except Exception:
        pass
    return results


def get_com_ports():
    """返回 {port: {'desc': str, 'hwid': str}}"""
    ports = {}
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            ports[str(p.device)] = {
                'desc': str(p.description),
                'hwid': str(p.hwid),
            }
    except Exception:
        pass
    return ports


# ============================================================
# IDN 识别
# ============================================================

IDN_MAP = [
    ("DSOX4024A",   "oscilloscope",    "DSOX4024A"),
    ("DSOX4034A",   "oscilloscope",    "DSOX4034A"),
    ("DSOX4054A",   "oscilloscope",    "DSOX4054A"),
    ("WT333E",      "power_meter",     "WT333E"),
    ("WT322E",      "power_meter",     "WT322E"),
    ("IT6333A",     "dc_source",       "IT6333A"),
    ("IT6332A",     "dc_source",       "IT6332A"),
    ("IT7321",      "ac_source",       "IT7321"),
    ("IT7322",      "ac_source",       "IT7322"),
    ("0x6300",      "dc_source",       "IT6333A"),
    ("0x7300",      "ac_source",       "IT7321"),
    ("0x8700",      "electronic_load", "IT8701P"),
    ("DSO-X 4024A", "oscilloscope",    "DSOX4024A"),
]


def match_idn(idn_str, addr):
    """返回 (dev_key, model) 或 (None, None)"""
    s = (idn_str + addr).upper()
    for kw, dev_key, model in IDN_MAP:
        if kw.upper() in s:
            return dev_key, model
    return None, None


# ============================================================
# 诱骗器 ACK 验证
# ============================================================

ACK = bytes([0x7B, 0x01, 0x01, 0x01, 0x7E])


def ack_verify_sniffer(port, baudrate=19200, timeout=1.0):
    """对指定 COM 端口发送 ACK 验证是否为 IP2716 诱骗器"""
    try:
        ser = serial.Serial(port, baudrate=baudrate, timeout=timeout, write_timeout=timeout)
        ser.flushInput()
        ser.write(ACK)
        time.sleep(0.4)
        resp = ser.read(10)
        ser.close()
        return resp == ACK
    except Exception:
        return False
