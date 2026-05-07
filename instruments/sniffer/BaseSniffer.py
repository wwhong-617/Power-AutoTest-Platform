# -*- coding: utf-8 -*-
"""
BaseSniffer - 诱骗器/协议测试板抽象基类
========================================

定义诱骗器统一抽象接口。
测试用例通过此基类操作诱骗器，换型号无需修改用例代码。

接口分类（4类）：
  1. 初始化 (Initialize)
  2. PD 协议申请 (PD Protocol)
  3. QC 协议申请 (QC Protocol)
  4. UFCS 协议申请 (UFCS Protocol)

通讯参数（英集芯 IP2716 方案）：
  波特率 19200 / LSB / 无奇偶校验 / 1停止位
  二进制帧格式：HEADER(0x7B) + SLAVE_ADDR + LENGTH + COMMAND + DATA(N) + CHECKSUM

各型号驱动继承此类，实现所有抽象方法。
"""

import struct
import time
import serial
from abc import ABC, abstractmethod
import sys
sys.path.insert(0, r'D:\injoinic--job\自动化测试平台开发\自动化测试平台')
from instruments.base import InstrumentConnectionState


class SnifferError(Exception):
    """诱骗器操作异常"""
    pass


class BaseSniffer(ABC):
    """
    诱骗器统一抽象接口。
    所有诱骗器驱动必须继承并实现以下抽象方法。
    """

    # 协议固定值
    HEADER = 0x7B
    CMD_ACK = 0x01

    def __init__(self, port: str, slave_addr: int = 1, timeout_ms: int = 1000, debug: bool = False):
        """
        Args:
            port:       串口名，如 "COM3"
            slave_addr: 设备地址 (1~255)，默认 1
            timeout_ms: 串口超时（毫秒）
            debug:      True = 打印调试信息（TX/RX 原始字节）
        """
        self._port = port
        self._slave_addr = slave_addr
        self._timeout_ms = timeout_ms
        self._serial = None
        self._connected = False
        self._debug = debug
        self._ack_timeout_ms = 1500
        self._state_callback = None

    # ================================================================
    #  连接管理
    # ================================================================

    def set_state_callback(self, callback):
        """设置状态回调函数。callback: (key, state, detail) -> None"""
        self._state_callback = callback

    def _report(self, state: InstrumentConnectionState, detail: str = ""):
        """通过回调上报状态（无回调时静默）"""
        if self._state_callback:
            try:
                self._state_callback(self.__class__.__name__, state, detail)
            except Exception:
                pass

    def connect(self, state_callback=None) -> bool:
        """
        建立 RS232 连接并验证设备。

        Args:
            state_callback: 可选的状态回调 (key, state, detail) -> None

        Returns:
            True = 成功，False = 失败
        """
        if state_callback is not None:
            self._state_callback = state_callback

        if self._connected:
            self._report(InstrumentConnectionState.CONNECTED,
                         f"已连接（重复调用）: {self._port}")
            return True

        try:
            # ── 1. 打开串口 ───────────────────────────
            self._report(InstrumentConnectionState.OPENING,
                         f"打开 {self._port} @ 19200")

            self._serial = serial.Serial(
                port=self._port,
                baudrate=19200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self._timeout_ms / 1000,
                write_timeout=self._timeout_ms / 1000,
                dsrdtr=False,
                rtscts=False,
            )
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()

            # ── 2. 启动后台接收线程 ────────────────────
            import queue, threading
            self._recv_queue = queue.Queue()
            self._recv_thread_running = True

            def recv_loop():
                while self._recv_thread_running and self._serial.is_open:
                    try:
                        if self._serial.in_waiting > 0:
                            data = self._serial.read(self._serial.in_waiting)
                            if data:
                                self._recv_queue.put(data)
                                if self._debug:
                                    print(f"  [RX queue] {data.hex().upper()}")
                        else:
                            time.sleep(0.01)
                    except Exception:
                        break

            self._recv_thread = threading.Thread(target=recv_loop, daemon=True)
            self._recv_thread.start()

            # ── 3. 发送初始化命令 ──────────────────────────
            self._report(InstrumentConnectionState.INIT, "发送初始化命令")
            self._send_initial_commands()

            # ── 4. 验证身份 ──────────────────────────────
            self._report(InstrumentConnectionState.VALIDATING,
                         f"验证设备 @ {self._port}")
            if not self._validate_identity():
                self._report(InstrumentConnectionState.FAILED,
                             f"设备验证失败: {self._port}")
                self._disconnectSilently()
                return False

            # ── 5. 完成 ────────────────────────────────
            self._connected = True
            self._report(InstrumentConnectionState.CONNECTED,
                         f"{self.__class__.__name__} @ {self._port} (addr={self._slave_addr})")
            return True

        except Exception as e:
            self._report(InstrumentConnectionState.FAILED, f"{e}")
            self._disconnectSilently()
            return False

    def disconnect(self):
        """关闭串口连接"""
        self._disconnectSilently()

    def is_connected(self) -> bool:
        return self._connected

    def enable_simulation(self, slave_addr: int = 1):
        """启用模拟模式，不连接真实设备（用于开发/调试）"""
        self._connected = True
        self._slave_addr = slave_addr
        self._serial = None
        self._report(InstrumentConnectionState.CONNECTED,
                     f"{self.__class__.__name__} [模拟模式] addr={slave_addr}")

    # ================================================================
    #  1. 初始化
    # ================================================================

    @abstractmethod
    def _send_initial_commands(self):
        """连接后发送初始化命令"""
        pass

    @abstractmethod
    def _validate_identity(self) -> bool:
        """验证设备身份，返回 True = 通过"""
        pass

    @abstractmethod
    def fw_self_test(self) -> bool:
        """
        固件自检。

        Returns:
            True = PASS，False = FAIL 或超时
        """
        pass

    # ================================================================
    #  2. PD 协议申请
    # ================================================================

    @abstractmethod
    def set_pd_mode(self) -> bool:
        """
        配置为 PD 快充模式。
        切换到 PD 模式后需等待 ≥500ms 再发送档位请求。
        """
        pass

    @abstractmethod
    def set_pd_position(self, position: int) -> bool:
        """
        申请 PD 档位。

        Args:
            position: 档位号 1~7（对应 PDO 第1~7档）
                      1 = 5V, 2 = 9V, 3 = 12V, 4 = 15V, 5 = 20V 等（具体电压由 DUT 的 PDO 决定）
        Returns:
            True = 成功，False = 失败
        """
        pass

    @abstractmethod
    def set_pd_pps_voltage_step(self, direction: str = "UP") -> bool:
        """
        PPS 电压微调（每次 ±100mV）。

        Args:
            direction: "UP" = 升压 (+100mV)，"DOWN" = 降压 (-100mV)
        """
        pass

    @abstractmethod
    def set_pd_pps_current_step(self, direction: str = "UP") -> bool:
        """
        PPS 电流微调（每次 ±50mA）。

        Args:
            direction: "UP" = 增大 (+50mA)，"DOWN" = 减小 (-50mA)
        """
        pass

    # ================================================================
    #  3. QC 协议申请
    # ================================================================

    @abstractmethod
    def set_qc_mode(self) -> bool:
        """
        配置为 QC 快充模式。
        切换到 QC 模式后需等待 ≥500ms 再发送电压请求。
        """
        pass

    @abstractmethod
    def set_qc_voltage(self, voltage: float) -> bool:
        """
        申请 QC 固定电压档位。

        Args:
            voltage: 目标电压 (V)，支持 5V / 9V / 12V / 20V（QC2.0）
                     或 3.3V~12V 之间 0.2V 步进（QC3.0）

        Returns:
            True = 成功，False = 失败
        """
        pass

    @abstractmethod
    def set_qc3_voltage_adjust(self, direction: str = "UP") -> bool:
        """
        QC3.0 恒压模式下电压微调（每次 ±0.2V）。

        Args:
            direction: "UP" = 升压 (+0.2V)，"DOWN" = 降压 (-0.2V)
        """
        pass

    @abstractmethod
    def set_qc3_exit(self) -> bool:
        """退出 QC3.0 恒压模式，返回 QC2.0 状态"""
        pass

    # ================================================================
    #  4. UFCS 协议申请
    # ================================================================

    @abstractmethod
    def set_ufcs_mode(self) -> bool:
        """
        配置为 UFCS 快充模式。
        切换到 UFCS 模式后需等待 ≥500ms 再发送档位请求。
        """
        pass

    @abstractmethod
    def set_ufcs_position(self, position: int = 1) -> bool:
        """
        申请 UFCS 档位。

        Args:
            position: 档位号（默认 1），具体电压由 DUT 的 UFCS 档位决定
        """
        pass

    @abstractmethod
    def set_ufcs_voltage_step(self, direction: str = "UP") -> bool:
        """
        UFCS 电压微调（每次 ±100mV）。

        Args:
            direction: "UP" = 升压 (+100mV)，"DOWN" = 降压 (-100mV)
        """
        pass

    @abstractmethod
    def set_ufcs_current_step(self, direction: str = "UP") -> bool:
        """
        UFCS 电流微调（每次 ±100mA）。

        Args:
            direction: "UP" = 增大 (+100mA)，"DOWN" = 减小 (-100mA)
        """
        pass

    @abstractmethod
    def get_ufcs_source_info(self) -> dict:
        """
        查询 UFCS Source 端信息（电压 / 电流 / 温度）。

        Returns:
            dict: {
                "voltage_mv": int,   电压 (mV)
                "current_ma": int,   电流 (mA)
                "temp_int":   int,   内部温度 (℃)
                "temp_usb":   int,   USB 口温度 (℃)
            }
        """
        pass

    # ================================================================
    #  协议帧工具（子类可用）
    # ================================================================

    def _build_frame(self, command: int, data: bytes = b"") -> bytes:
        """
        构建协议帧。
        帧格式：HEADER + SLAVE_ADDR + LENGTH + COMMAND + DATA(N) + CHECKSUM
        CHECKSUM = 所有字节之和的低8位
        """
        length = 1 + len(data)
        payload = bytes([self._slave_addr, length, command]) + data
        checksum = (self.HEADER + sum(payload)) & 0xFF
        return bytes([self.HEADER]) + payload + bytes([checksum])

    def _send_frame(self, frame: bytes):
        """发送协议帧（直接二进制）"""
        if not self._connected:
            raise SnifferError("Not connected")
        if self._debug:
            print(f"  [TX] {frame.hex().upper()}")
        self._serial.write(frame)
        self._serial.flush()

    def _send_and_wait_ack(self, frame: bytes, timeout_ms: int = None) -> bool:
        """
        发送帧并等待 ACK 回复。
        直接同步读取，兼容 pyserial 3.x。
        超时或错误返回 False（不抛异常）。
        """
        import time as time_module
        try:
            self._send_frame(frame)
            timeout_sec = (timeout_ms or self._ack_timeout_ms) / 1000.0
            self._serial.timeout = timeout_sec
            deadline = time_module.time() + timeout_sec

            while True:
                remaining = deadline - time_module.time()
                if remaining <= 0:
                    if self._debug:
                        print(f"  [RX] timeout")
                    return False
                self._serial.timeout = remaining

                ch = self._serial.read(1)
                if not ch:
                    continue
                if ch[0] == self.HEADER:
                    rest = self._serial.read(4)
                    if len(rest) == 4:
                        if self._debug:
                            print(f"  [RX] {(ch + rest).hex().upper()}")
                        if rest[2] == self.CMD_ACK:
                            return True
                if time_module.time() >= deadline:
                    if self._debug:
                        print(f"  [RX] timeout")
                    return False
        except SnifferError as e:
            if self._debug:
                print(f"  [RX] error: {e}")
            return False

    # ================================================================
    #  内部工具
    # ================================================================

    def _disconnectSilently(self):
        """关闭连接（不抛异常）"""
        try:
            self._recv_thread_running = False
            if hasattr(self, '_recv_thread'):
                self._recv_thread.join(timeout=0.3)
        except Exception:
            pass
        try:
            if self._serial and self._serial.is_open:
                self._serial.close()
        except Exception:
            pass
        self._serial = None
        self._connected = False

    def __del__(self):
        self._disconnectSilently()
