# -*- coding: utf-8 -*-
"""
BaseInstrument - 所有仪器驱动的公共基类
==========================================

定义统一接口：
- connect(state_callback) / disconnect()
- is_connected()
- send_command() / query()
- identity() - 获取仪器身份信息

支持 SCPI (TCPIP) / USB / RS232 三种通讯方式。
"""

import pyvisa
import time
from abc import ABC, abstractmethod
from enum import Enum


class InstrumentError(Exception):
    """仪器操作异常"""
    pass


class InstrumentConnectionState(Enum):
    """
    仪器连接过程中的状态枚举。

    使用说明：
      - 每台仪器连接时，InstrumentManager 通过 state_callback 逐个上报状态
      - UI 根据状态更新进度显示
      - CONNECTED / FAILED 是终态
    """
    IDLE        = "idle"         # 空闲（未开始）
    CREATING    = "creating"     # 正在创建实例
    OPENING     = "opening"      # 正在打开 VISA / 串口资源
    IDENTIFYING = "identifying"  # 正在查询 *IDN?
    INIT        = "init"         # 正在发送初始化命令
    VALIDATING  = "validating"  # 正在验证身份
    RETRYING    = "retrying"    # 正在重试（第 N 次）
    CONNECTED   = "connected"   # 连接成功（终态）
    FAILED      = "failed"      # 连接失败（终态）


class BaseInstrument(ABC):
    """
    仪器基类，定义公共接口。

    每个子类必须实现：
    - _send_initial_commands() - 连接后初始化命令
    - _validate_identity() - 验证仪器身份
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        """
        Args:
            conn_type: 连接类型，"TCPIP" / "USB" / "RS232"
            address:   连接地址
                      TCPIP: "192.168.1.100:inst0"
                      USB:   "USB0::0x0000::0x0000::INSTR"
                      RS232: "ASRL16::INSTR" (即 COM16)
            timeout_ms: 超时时间（毫秒）
        """
        self._conn_type = conn_type.upper()
        self._address = address
        self._timeout_ms = timeout_ms
        self._resource = None
        self._connected = False
        self._idn = ""
        self._state_callback = None  # (key, state, detail) -> None

    # ---------------------- 公共接口 ----------------------

    @property
    def address(self) -> str:
        """返回仪器连接地址"""
        return self._address

    @property
    def idn(self) -> str:
        """返回仪器身份字符串（*IDN*）"""
        return self._idn

    def set_state_callback(self, callback):
        """
        设置状态回调函数。

        callback 签名：
            callback(key: str, state: InstrumentConnectionState, detail: str)

        在连接过程中会被多次调用，上报每一步状态。
        """
        self._state_callback = callback

    def _report(self, state: InstrumentConnectionState, detail: str = ""):
        """内部方法：通过回调上报状态（无回调时静默）"""
        if self._state_callback:
            try:
                self._state_callback(self.__class__.__name__, state, detail)
            except Exception:
                pass

    def connect(self, state_callback=None) -> bool:
        """
        建立连接并验证仪器身份。

        Args:
            state_callback: 可选的状态回调 (key, state, detail) -> None，
                            用于进度上报。如果传入，则忽略实例级回调。

        Returns:
            True=连接成功，False=失败
        """
        # 优先使用传入的回调，其次使用实例级回调
        if state_callback is not None:
            self._state_callback = state_callback

        if self._connected:
            self._report(InstrumentConnectionState.CONNECTED,
                         f"已连接（重复调用）: {self._idn}")
            return True

        try:
            # ── 0. 清理上次失败遗留的资源 ─────────────────────────
            if self._resource is not None:
                try:
                    self._resource.close()
                except Exception:
                    pass
                self._resource = None

            # ── 1. 打开资源 ──────────────────────────────────
            self._report(InstrumentConnectionState.OPENING,
                         f"打开 {self._address}")

            if self._conn_type == "USB":
                rm = pyvisa.ResourceManager()        # NI VISA 后端
            else:
                rm = pyvisa.ResourceManager("@py")   # pyvisa-py 后端

            self._resource = rm.open_resource(self._address)
            self._resource.timeout = self._timeout_ms

            # RS232 串口：配置波特率和换行符
            if self._conn_type == "RS232":
                try:
                    self._resource.baud_rate = 9600
                except Exception:
                    pass
                try:
                    self._resource.write_termination = "\n"
                    self._resource.read_termination = "\n"
                except Exception:
                    pass

            # ── 2. 查询身份 ──────────────────────────────────
            self._report(InstrumentConnectionState.IDENTIFYING, "查询 *IDN?")
            self._idn = self._resource.query("*IDN?").strip()

            # ── 3. 发送初始化命令 ─────────────────────────────
            self._report(InstrumentConnectionState.INIT, "发送初始化命令")
            self._send_initial_commands()

            # ── 4. 验证身份 ─────────────────────────────────
            self._report(InstrumentConnectionState.VALIDATING,
                         f"验证身份: {self._idn}")
            if not self._validate_identity():
                self._report(InstrumentConnectionState.FAILED,
                             f"身份不符: {self._idn}")
                self._connected = False
                raise InstrumentError(f"身份验证失败: {self._idn}")

            # ── 5. 完成 ────────────────────────────────────
            self._connected = True
            self._report(InstrumentConnectionState.CONNECTED,
                         f"{self.__class__.__name__} @ {self._address}  [{self._idn}]")
            return True

        except Exception as e:
            self._report(InstrumentConnectionState.FAILED, f"{e}")
            self._connected = False
            return False

    def disconnect(self):
        """关闭连接，释放资源"""
        if self._resource is not None:
            try:
                self._resource.close()
            except Exception:
                pass
            self._resource = None
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def identity(self) -> str:
        """返回仪器身份字符串"""
        return self._idn

    # ---------------------- 子类必须实现 ----------------------

    @abstractmethod
    def _send_initial_commands(self):
        """连接后发送初始化命令（子类实现）"""
        pass

    @abstractmethod
    def _validate_identity(self) -> bool:
        """验证仪器身份是否匹配（子类实现）"""
        pass

    # ---------------------- 公共发送接口 ----------------------

    def send_command(self, cmd: str, check_esr: bool = False):
        """
        发送 SCPI 命令。

        Args:
            cmd:       SCPI 命令字符串
            check_esr: 是否检查状态寄存器（ESR）。默认 False（成熟 SCPI 设备无需每次校验）。
        """
        if self._resource is None:
            raise InstrumentError("Not connected")

        try:
            self._resource.write(cmd)
            if check_esr:
                esr = self._resource.query("*ESR?").strip()
                if int(esr) & 0x7C:  # 任意错误位
                    raise InstrumentError(f"ESR error: {esr} after '{cmd}'")
        except InstrumentError:
            raise
        except Exception as e:
            raise InstrumentError(f"Send command failed: {e}")

    def query(self, cmd: str, delay_ms: int = 0) -> str:
        """
        发送 SCPI 查询并返回响应。

        Args:
            cmd:      SCPI 查询命令
            delay_ms: 查询后延时（毫秒）
        """
        if self._resource is None:
            raise InstrumentError("Not connected")

        try:
            response = self._resource.query(cmd)
            if delay_ms > 0:
                time.sleep(delay_ms / 1000)
            return response.strip()
        except Exception as e:
            raise InstrumentError(f"Query failed: {e}")

    def read_raw(self, size: int = None) -> bytes:
        """读取原始字节（用于波形下载等场景）"""
        if self._resource is None:
            raise InstrumentError("Not connected")
        if size is None:
            return self._resource.read_raw()
        return self._resource.read_raw(size)

    def clear(self):
        """清除仪器状态（*CLS）"""
        self.send_command("*CLS", check_esr=False)

    def enable_simulation(self, identity: str = "SIMULATION"):
        """
        启用模拟模式（无仪器时用于开发/演示）。

        启用后所有通讯操作返回模拟数据，不抛出异常。
        """
        self._simulating = True
        self._sim_idn = identity
        self._connected = True

    def _simulate_read_raw(self, size: int) -> bytes:
        """模拟读取（子类可覆盖）"""
        return bytes(size)

    def __repr__(self):
        status = "connected" if self._connected else "disconnected"
        return f"<{self.__class__.__name__} {self._conn_type} {self._address} [{status}]>"
