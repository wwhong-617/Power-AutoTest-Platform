"""
BaseInstrument - 所有仪器驱动的公共基类
==========================================

定义统一接口：
- connect() / disconnect()
- is_connected()
- send_command() / query()
- identity() - 获取仪器身份信息

支持 SCPI (TCPIP) / USB / RS232 三种通讯方式。
"""

import pyvisa
import time
from abc import ABC, abstractmethod


class InstrumentError(Exception):
    """仪器操作异常"""
    pass


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
        self._idn = ""  # 仪器身份字符串

    # ---------------------- 公共接口 ----------------------

    @property
    def address(self) -> str:
        """返回仪器连接地址"""
        return self._address

    @property
    def idn(self) -> str:
        """返回仪器身份字符串（*IDN*）"""
        return self._idn
    def connect(self) -> bool:
        """
        建立连接并验证仪器身份。
        Returns:
            True=连接成功，False=失败
        """
        if self._connected:
            return True

        try:
            # USB 设备使用 NI VISA 后端（支持 USBTMC），
            # 其他类型使用 pyvisa-py 后端
            if self._conn_type == "USB":
                rm = pyvisa.ResourceManager()  # NI VISA 后端
            else:
                rm = pyvisa.ResourceManager("@py")  # pyvisa-py 后端
            self._resource = rm.open_resource(self._address)
            self._resource.timeout = self._timeout_ms

            # RS232 串口：配置波特率和换行符
            # IT8511 等设备要求：波特率 19200，换行符 LF (\n)
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

            # 读取身份信息
            self._idn = self._resource.query("*IDN?").strip()
            print(f"    [{self.__class__.__name__}] Connected: {self._idn}")

            # 标记为已连接，再发送初始化命令
            self._connected = True

            # 发送初始化命令（子类实现）
            self._send_initial_commands()

            # 验证身份（子类实现）
            if not self._validate_identity():
                self._connected = False
                raise InstrumentError(f"Unexpected device: {self._idn}")

            return True

        except Exception as e:
            print(f"    [{self.__class__.__name__}] Connection failed: {e}")
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

    def send_command(self, cmd: str, check_esr: bool = True):
        """
        发送 SCPI 命令（无返回值）。

        Args:
            cmd:       SCPI 命令字符串
            check_esr: 是否在写入后检查 *ESR? 确认命令执行结果。
                       写入成功后查询 ESR，ESR bit 5(命令错误) 或 bit 4(执行错误)
                       时记录警告（不抛异常），因为某些命令在特定仪器状态下会返回错误。
        """
        if not self._connected:
            raise InstrumentError("Not connected")
        try:
            self._resource.write(cmd)
            if check_esr:
                # 写入成功后，检查 ESR 确认命令被接受
                esr_str = self._resource.query("*ESR?").strip()
                # 忽略查询错误(bit4)，只关注命令错误(bit5)和执行错误(bit4的另一个组合)
                # ESR bit5=35 命令错误, bit4=34 执行错误, bit3=33 查询错误
                try:
                    esr_val = int(esr_str)
                    # bit5(Command Error) 或 bit4(Execution Error) -> 警告但不停止
                    if esr_val & 0x20 or esr_val & 0x10:
                        import logging
                        logging.getLogger("PowerAutoTest").warning(
                            f"[Instrument] ESR={esr_str} after: {cmd}"
                        )
                except (ValueError, Exception):
                    pass
        except InstrumentError:
            raise
        except Exception as e:
            raise InstrumentError(f"Send command failed: {cmd} -> {e}")

    def query(self, cmd: str, delay_ms: int = 0) -> str:
        """
        发送 SCPI 查询命令并返回响应
        Args:
            cmd:      SCPI 命令
            delay_ms: 读取前等待时间（毫秒）
        """
        if not self._connected:
            raise InstrumentError("Not connected")
        try:
            if delay_ms > 0:
                time.sleep(delay_ms / 1000)
            return self._resource.query(cmd).strip()
        except Exception as e:
            raise InstrumentError(f"Query failed: {cmd} -> {e}")

    def read_raw(self, size: int = None) -> bytes:
        """
        读取原始二进制数据（用于获取波形等二进制响应）。
        Returns:
            bytes: 原始二进制数据
        """
        if not self._connected:
            raise InstrumentError("Not connected")
        try:
            if size is None:
                return self._resource.read_raw()
            else:
                return self._resource.read_raw(size)
        except Exception as e:
            raise InstrumentError(f"read_raw failed: {e}")

    def clear(self):
        """
        清除仪器缓冲区，执行 VISA Device Clear（USBTMC）。
        用于清除残留协议错误，恢复正常通讯状态。
        """
        if self._resource is not None:
            try:
                self._resource.clear()
            except Exception:
                pass

    # ---------------------- 子类必须实现 ----------------------

    @abstractmethod
    def _send_initial_commands(self):
        """连接后发送初始化命令（重写实现）"""
        pass

    @abstractmethod
    def _validate_identity(self) -> bool:
        """
        验证仪器身份是否匹配。
        Returns:
            True=身份正确，False=不匹配
        """
        pass

    # ---------------------- 模拟模式（开发/无仪器时使用） ----------------------

    def enable_simulation(self, identity: str = "SIMULATION"):
        """
        启用模拟模式，不连接真实仪器。
        用于开发阶段或无仪器时调试。
        """
        self._connected = True
        self._idn = identity
        self._resource = None  # 模拟模式下 resource 为 None
        print(f"    [{self.__class__.__name__}] Simulation mode: {identity}")

    def _simulate_read_raw(self, size: int) -> bytes:
        """模拟读取原始数据（供子类在模拟模式下调用）"""
        return bytes(size)
