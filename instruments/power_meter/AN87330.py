# -*- coding: utf-8 -*-
"""
AN87330 - 艾诺 AN87330 高精度三相功率分析仪驱动
================================================================

通讯方式：RS232 (COM)，地址=1，波特率=38400

【协议说明】
  查询帧（测量数据）：使用 Ainuo 私有二进制协议
  设置帧（量程/模式）：使用 Modbus RTU（寄存器 4004H/4005H 等）
  ——手册第31页明确：4004H=电压量程，4005H=电流量程，写单个寄存器（功能码 0x06）
================================================================

 Ainuo 协议帧格式（实测确定）
 ══════════════════════════════════════════════════════════════════════
 查询帧：7B | 00 09 | 01 | F1 | 00 | 01 | FC | 7D
           帧头  总=9    地址   类型   命令字 参数 校验和 帧尾
 总字节数=9（固定），校验和=sum(0x00,0x09,body)低字节

 响应帧（CH1 查询）：
   7B | 00 73 | 01 F1 00 01 | [108字节测量数据] | CS | 7D
     head    total=115  ↑前4字节为响应头：地址/功能码/命令字/参数
                        测量数据从 data[7] 开始！

 数据格式（6字节 big-endian ÷1000）：
   电压(V), 电流(mA), 视在功率(VA), 无功功率(var)
 8字节 big-endian ÷10000：有功功率(W)
 2字节 big-endian ÷10000：功率因数
 2字节 big-endian ÷10：相位角(°)
 4字节 big-endian ÷1000：频率(Hz)
"""

import struct
import time
import logging
from .BasePowerMeter import BasePowerMeter


def _modbus_crc(data: bytes) -> bytes:
    """计算 Modbus RTU CRC-16（低位在前，高位在后）。"""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])

logger = logging.getLogger("PowerAutoTest")


class AN87330(BasePowerMeter):
    FRAME_HEAD = 0x7B
    FRAME_TAIL = 0x7D
    TYPE_QUERY = 0xF1
    TYPE_SET    = 0x5A    # 设置类命令

    CMD_MEASURE = 0x00
    CMD_ENERGY  = 0x01
    CMD_3PHASE  = 0x02
    CMD_MOTOR   = 0x03
    CMD_HARM    = 0x04

    # ─── 设置类命令参数（用于 SET_CMD 0x00） ─────────────────────────
    # 第七字节含义（见手册第46页）：
    #  0x01 = 电压量程：0=15V 1=30V 2=60V 3=100V 4=150V 5=300V 6=600V 7=1000V  >7=自动
    #  0x02 = 电流量程：0=100mA 1=200mA 2=500mA 3=1A 4=2A 5=5A 6=10A 7=20A  >7=自动
    SET_PARAM_VOLTAGE_RANGE = 0x01
    SET_PARAM_CURRENT_RANGE  = 0x02
    SET_PARAM_CURRENT_SOURCE  = 0x03
    SET_PARAM_CALC_PERIOD     = 0x04
    SET_PARAM_SYNC_SOURCE     = 0x05
    SET_PARAM_HARM_SOURCE     = 0x06
    SET_PARAM_HARM_SWITCH     = 0x07
    SET_PARAM_LINE_FILTER     = 0x08
    SET_PARAM_FREQ_FILTER    = 0x09
    SET_PARAM_WIRING_MODE    = 0x0A

    # ─── Modbus RTU 寄存器地址（用于设置量程） ─────────────────────────
    # 手册第31页：4004H=电压量程，4005H=电流量程（int32，每通道独立）
    # 通道 n (1/2/3) 的寄存器 = 0x4004 + (n-1)*0x10
    _MODBUS_VOLTAGE_RANGE_REG = 0x4004   # 电压量程寄存器（通道1）
    _MODBUS_CURRENT_RANGE_REG  = 0x4005   # 电流量程寄存器（通道1）
    _MODBUS_REG_CHANNEL_OFFSET = 0x10      # 通道间寄存器偏移（0x10=16）

    # 电压量程表（索引 = 命令值）
    _VOLTAGE_RANGES = [15, 30, 60, 100, 150, 300, 600, 1000]   # V
    # 电流量程表（索引 = 命令值）
    _CURRENT_RANGES  = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0]  # A

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 10000):
        super().__init__(conn_type, address, timeout_ms)
        self._model       = "AN87330"
        self._slave_addr  = 1
        self._baudrate    = 38400
        self._timeout_s   = timeout_ms / 1000.0  # 默认 10s（AN87330 回复约需 5s）
        self._serial      = None
        self._connected   = False
        self._wiring_mode = "3P4W"
        self._input_ch    = 1   # 交流输入侧通道（1=CH1），由 set_channel_roles() 设置
        self._output_ch   = 2   # DUT 输出侧通道（2=CH2），由 set_channel_roles() 设置

    # ─── 完整 override connect()，跳过父类的 SCPI *IDN? 流程 ──────────────────
    # AN87330 使用 Ainuo 私有二进制协议，非 SCPI，父类 connect() 的 *IDN?
    # 会失败抛异常导致后续逻辑无法执行。此处自行完成连接+验证全流程。
    def connect(self):
        import serial
        # 防止重复打开：如果端口已打开，直接跳过
        if self._serial is not None and self._serial.is_open:
            logger.info("[AN87330] Port already open, skipping reopen")
            self._connected = True
            return True
        # 将 VISA 地址格式（ASRL3::INSTR）转换为 COM 端口名（COM3）
        port = self._address
        if port.startswith("ASRL"):
            com_num = port.replace("ASRL", "").replace("::INSTR", "").strip()
            port = f"COM{com_num}"
        self._serial = serial.Serial(
            port=port,
            baudrate=self._baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self._timeout_s,
            write_timeout=self._timeout_s,
            rtscts=False,   # 禁用硬件流控，避免 pyserial 等 CTS 信号卡死
            dsrdtr=False,   # 禁用 DSR/DTR 流控
        )
        self._connected = self._serial.is_open
        logger.info("[AN87330] Connected to %s @ %d 8N1", self._address, self._baudrate)
        return True

    def disconnect(self):
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._connected = False
        logger.info("[AN87330] Disconnected")

    def is_connected(self) -> bool:
        return self._connected

    def _build_frame(self, cmd_word: int, param: bytes) -> bytes:
        """构造查询帧。实测确认：总字节数固定为 9。"""
        total = 9
        body = bytes([self._slave_addr, self.TYPE_QUERY, cmd_word]) + bytes(param)
        cs = (((total >> 8) & 0xFF) + (total & 0xFF) + sum(body)) & 0xFF
        frame = bytes([self.FRAME_HEAD,
                       (total >> 8) & 0xFF, total & 0xFF,
                       ]) + body + bytes([cs, self.FRAME_TAIL])
        return frame

    def _send_frame(self, frame: bytes) -> bytes:
        """
        发送帧并读取响应。AN87330 每次回复约需 5s，timeout 设 10s 留有裕量。

        响应帧：head(1) + len(2) + [响应头4字节] + [测量数据108字节] + cs(1) + tail(1)
        总帧长 = 117 字节。
        """
        self._serial.flushInput()
        self._serial.write(frame)

        # 等待设备处理（约 5s），轮询检查数据是否到达
        deadline = time.time() + self._timeout_s
        while time.time() < deadline:
            n = self._serial.in_waiting
            if n > 0:
                # 有数据到达，立即读取（read() 不再设 count，让 OS 决定）
                data = self._serial.read(n)
                if data and data[0] == self.FRAME_HEAD:
                    return data[3:]   # 跳过帧头 3 字节，返回测量数据
            time.sleep(0.05)   # 50ms 轮询

        # timeout 后最后一次尝试读取（设备可能刚好在边界到达）
        if self._serial.in_waiting > 0:
            data = self._serial.read(self._serial.in_waiting)
            if data and data[0] == self.FRAME_HEAD:
                return data[3:]

        raise IOError("AN87330: 查询超时（%ds），设备未在规定时间内响应" % self._timeout_s)

    def _build_set_frame(self, param_type: int, param_value: int) -> bytes:
        """
        构造设置帧（Ainuo 协议，设置类命令）。

        帧格式（实测 V3 格式有效，total=0x0A）：
          帧头(1) + 0x00(1) + 0x0A(1) + 地址(1) + 5A(1) + 00(1)
          + 参数类型(1) + 参数值(1) + 校验和(1) + 帧尾(1)
        """
        addr  = self._slave_addr
        ftype = self.TYPE_SET
        cmd   = 0x00   # 命令字
        body  = bytes([addr, ftype, cmd, param_type, param_value])
        # total 字段固定为 0x000A（10字节），实测设备接受此格式并返回确认
        total = 0x000A
        cs = ((total >> 8) & 0xFF) + (total & 0xFF) + sum(body)
        frame = bytes([self.FRAME_HEAD,
                       (total >> 8) & 0xFF, total & 0xFF,
                       ]) + body + bytes([cs & 0xFF, self.FRAME_TAIL])
        return frame

    def _send_set_frame(self, param_type: int, param_value: int) -> bool:
        """
        发送设置帧并验证应答。

        成功响应（9字节）：7B 00 09 ADDR 5A 00 00 CS 7D
        错误响应（9字节）：7B 00 09 ADDR 99 CMD ERR CS 7D  (ERR=04 表示超范围)

        Returns:
            True = 设置成功，False = 设置失败/设备未应答
        Raises:
            IOError: 通信错误
        """
        frame = self._build_set_frame(param_type, param_value)
        self._serial.flushInput()
        self._serial.write(frame)

        chunks = []
        deadline = time.time() + self._timeout_s
        while time.time() < deadline:
            n = self._serial.in_waiting
            if n > 0:
                chunks.append(self._serial.read(n))
                total_rcvd = sum(len(c) for c in chunks)
                if total_rcvd >= 9:  # 完整应答帧 9 字节
                    break
            time.sleep(0.05)  # 50ms 轮询间隔

        data = b''.join(chunks)
        if len(data) < 4 or data[0] != self.FRAME_HEAD:
            raise IOError("AN87330: 设置帧无响应或响应格式错误")
        if len(data) < 9:
            raise IOError(f"AN87330: 设置帧响应数据不完整（{len(data)} 字节）")

        # 成功响应（V3格式，9字节）：7B 00 09 ADDR 5A 00 STATUS CS 7D
        # 状态字节在 data[6]：00=成功，04=超范围
        # 错误响应：data[4] = 0x99
        if data[4] == 0x99:
            err_code = data[6] if len(data) > 6 else -1
            raise IOError(f"AN87330: 设置失败，错误码=0x{err_code:02X} "
                           f"（04=超范围, 01=功能码错误, 02=长度错误, 03=读取寄存器错误）")
        if data[6] == 0x00:
            return True
        raise IOError(f"AN87330: 设置帧未知响应: {data.hex().upper()}")

    # ─── Modbus RTU 设置方法（量程/模式设置使用） ──────────────────────────
    # 手册第31页：写单个寄存器（功能码 0x06）
    # 4004H=电压量程，4005H=电流量程（通道间寄存器偏移 0x10）

    def _modbus_reg_addr(self, base_reg: int, channel: int) -> int:
        """计算通道对应的 Modbus 寄存器地址。通道1→基址，通道2→基址+0x10，通道3→基址+0x20。"""
        ch = max(1, min(3, int(channel)))
        return base_reg + (ch - 1) * self._MODBUS_REG_CHANNEL_OFFSET

    def _build_modbus_write_frame(self, reg_addr: int, value: int) -> bytes:
        """构造 Modbus RTU 写单个寄存器帧（功能码 0x06）。"""
        body = bytes([self._slave_addr, 0x06,
                       (reg_addr >> 8) & 0xFF, reg_addr & 0xFF,
                       (value >> 8) & 0xFF, value & 0xFF])
        return body + _modbus_crc(body)

    def _send_modbus_frame(self, frame: bytes, min_len: int = 8) -> bytes:
        """
        发送 Modbus RTU 帧并读取响应。

        成功响应（8字节）：Addr+06+RegHi+RegLo+ValHi+ValLo+CRC
        错误响应（5字节）：Addr+86+ErrCode+CRC
        """
        self._serial.flushInput()
        self._serial.write(frame)
        time.sleep(0.3)

        chunks = []
        deadline = time.time() + self._timeout_s
        while time.time() < deadline:
            n = self._serial.in_waiting
            if n > 0:
                chunks.append(self._serial.read(n))
                if sum(len(c) for c in chunks) >= min_len:
                    break
            time.sleep(0.05)

        data = b''.join(chunks)
        if len(data) < 5:
            raise IOError(f"AN87330: Modbus 无响应（收到 {len(data)} 字节）")
        if data[1] == 0x86:
            raise IOError(f"AN87330: Modbus 错误码=0x{data[2]:#04x}")
        if data[1] != 0x06:
            raise IOError(f"AN87330: Modbus 功能码错误: 0x{data[1]:#04x}")
        # 验证 CRC
        resp_crc = data[-2:]
        calc_crc = _modbus_crc(data[:-2])
        if resp_crc != calc_crc:
            raise IOError(f"AN87330: Modbus CRC 错误")
        return data

    def _modbus_write_register(self, reg_addr: int, value: int) -> bool:
        """通过 Modbus RTU 写单个寄存器。"""
        frame = self._build_modbus_write_frame(reg_addr, value)
        logger.info(f"[AN87330] Modbus WR REG=0x{reg_addr:04X} VAL={value}")
        resp = self._send_modbus_frame(frame)
        ack_val = (resp[4] << 8) | resp[5]
        logger.info(f"[AN87330] Modbus ACK REG=0x{reg_addr:04X} VAL={ack_val}")
        return True

    def _modbus_read_register(self, reg_addr: int) -> int:
        """通过 Modbus RTU 读单个寄存器（功能码 0x03）。"""
        body = bytes([self._slave_addr, 0x03,
                      (reg_addr >> 8) & 0xFF, reg_addr & 0xFF,
                      0x00, 0x01])
        frame = body + _modbus_crc(body)
        self._serial.flushInput()
        self._serial.write(frame)
        time.sleep(0.3)
        chunks = []
        deadline = time.time() + self._timeout_s
        while time.time() < deadline:
            n = self._serial.in_waiting
            if n > 0:
                chunks.append(self._serial.read(n))
                if sum(len(c) for c in chunks) >= 7:
                    break
            time.sleep(0.05)
        data = b''.join(chunks)
        if len(data) < 7 or data[1] != 0x03:
            raise IOError(f"AN87330: Modbus 读寄存器失败: {data.hex().upper()}")
        return (data[4] << 8) | data[5]

    # ─── 数据解析 ─────────────────────────────────────────────

    @staticmethod
    def _be6(d):
        val = 0
        for b in d: val = (val << 8) | b
        return val / 1000.0

    @staticmethod
    def _be8(d):
        val = 0
        for b in d: val = (val << 8) | b
        return val / 10000.0

    @staticmethod
    def _be4(d):
        val = 0
        for b in d: val = (val << 8) | b
        return val / 1000.0

    @staticmethod
    def _be2_10k(d):
        return struct.unpack('>H', d)[0] / 10000.0

    @staticmethod
    def _be2_10(d):
        return struct.unpack('>H', d)[0] / 10.0

    def _validate_identity(self) -> bool:
        try:
            r = self._send_frame(self._build_frame(self.CMD_MEASURE, bytes([1])))
            return len(r) > 0
        except Exception:
            return False

    def _parse_channel(self, channel) -> int:
        """
        统一解析 channel 参数，支持以下格式：
          "CH1" / "ch1" / "1" / 1  → 1
          "CH2" / "ch2" / "2" / 2  → 2
          "CH3" / "ch3" / "3" / 3  → 3

        Returns:
            int: 通道号（1~3），超出范围则 clamp 到 1~3
        """
        if isinstance(channel, int):
            return max(1, min(3, channel))
        s = str(channel).upper().strip()
        # 去掉 "CH" / "CHANNEL" 前缀
        for prefix in ("CHANNEL", "CH"):
            if s.startswith(prefix):
                s = s[len(prefix):]
        try:
            return max(1, min(3, int(s.strip())))
        except ValueError:
            return 1  # 默认 CH1

    # ─── 初始化 ────────────────────────────────────────────

    def _send_initial_commands(self):
        """
        初始化命令：设置所有通道为自动量程，计算周期 0.1s（快速更新）。

        手册第46页 Ainuo 设置类命令参数：
          电压量程(01)：0-7=固定档，>7=自动量程
          电流量程(02)：0-7=固定档，>7=自动量程
          计算周期(04)：0=0.1s（推荐）, 1=0.2s, 2=0.5s, 3=1s, 4=2s, 5=5s, 6=10s

        注意：Ainuo 0x5A/0x00 命令无通道字段，电压/电流量程设置对所有通道同时生效。
        """
        # 电压量程自动（>7 = 自动）
        try:
            self._send_set_frame(self.SET_PARAM_VOLTAGE_RANGE, 8)
            logger.info("[AN87330] 电压量程 → 自动")
        except IOError as e:
            logger.warning(f"[AN87330] 电压量程设置失败: {e}")

        # 电流量程自动（>7 = 自动）
        try:
            self._send_set_frame(self.SET_PARAM_CURRENT_RANGE, 8)
            logger.info("[AN87330] 电流量程 → 自动")
        except IOError as e:
            logger.warning(f"[AN87330] 电流量程设置失败: {e}")

        # 计算周期 0.1s（最快数据更新）
        try:
            self._send_set_frame(self.SET_PARAM_CALC_PERIOD, 0)
            logger.info("[AN87330] 计算周期 → 0.1s")
        except IOError as e:
            logger.warning(f"[AN87330] 计算周期设置失败: {e}")

    def initialize(self):
        if not self._connected:
            self.connect()
        if self._validate_identity():
            logger.info("[AN87330] Identity validated, communication OK")
            self._send_initial_commands()
        else:
            logger.warning("[AN87330] Identity validation failed")

    # ─── 基础设置 ──────────────────────────────────────────

    def set_voltage_range(self, channel: int, range_value: float):
        """
        设置指定通道的电压量程档位（Modbus RTU 方式）。

        量程表（索引 = 命令值）：
          0 → 15V,  1 → 30V,  2 → 60V,  3 → 100V
          4 → 150V, 5 → 300V, 6 → 600V, 7 → 1000V

        Args:
            channel:      通道号（1/2/3）
            range_value:  目标电压量程（V），自动选择最接近的档位
        """
        ranges = sorted(self._VOLTAGE_RANGES)
        target = abs(range_value)
        candidates = [r for r in ranges if r >= target]
        chosen = candidates[0] if candidates else ranges[-1]
        idx = self._VOLTAGE_RANGES.index(chosen)
        ch = self._parse_channel(channel)
        self._send_set_frame(self.SET_PARAM_VOLTAGE_RANGE, idx)
        logger.info(f"[AN87330] CH{ch} 电压量程设置为 {chosen}V（档位 {idx}）")

    def set_voltage_range_auto(self, channel, voltage: float):
        """
        根据目标电压自动选择合适的电压档位并设置。

        选档规则：目标电压 × 1.1（留 10% 裕量）后在量程列表中
        选择 ≥ 该值的最小档位。若无满足条件则用最大档（1000V）。

        Args:
            channel:  通道号（1/2/3，对应 CH1/CH2/CH3）
            voltage:  目标电压（V）
        """
        ranges = sorted(self._VOLTAGE_RANGES)
        target = abs(voltage) * 1.1
        candidates = [r for r in ranges if r >= target]
        chosen = candidates[0] if candidates else ranges[-1]
        idx = self._VOLTAGE_RANGES.index(chosen)
        ch = self._parse_channel(channel)
        self._send_set_frame(self.SET_PARAM_VOLTAGE_RANGE, idx)
        logger.info(f"[AN87330] CH{ch} 电压 {voltage}V×1.1={target:.1f}V → 自动选档 {chosen}V（档位 {idx}）")

    def set_current_range(self, channel: int, range_value: float):
        """
        设置指定通道的电流量程档位。

        量程表（索引 = 命令值）：
          0 → 100mA,  1 → 200mA,  2 → 500mA,  3 → 1A
          4 → 2A,      5 → 5A,      6 → 10A,    7 → 20A

        Args:
            channel:      通道号（1/2/3，对应 CH1/CH2/CH3）
            range_value:  目标电流量程（A），自动选择最接近的档位
        """
        ranges = sorted(self._CURRENT_RANGES)
        target = abs(range_value)
        # 选择 ≥ target 的最小档位
        candidates = [r for r in ranges if r >= target]
        chosen = candidates[0] if candidates else ranges[-1]
        idx = self._CURRENT_RANGES.index(chosen)
        ch = self._parse_channel(channel)
        self._send_set_frame(self.SET_PARAM_CURRENT_RANGE, idx)
        logger.info(f"[AN87330] CH{ch} 电流量程设置为 {chosen}A（档位 {idx}）")

    def set_power_range(self, channel: int, range_value: float):
        """
        AN87330 不支持单独设置功率档位。
        功率范围由电压档位 × 电流档位自动决定。
        """
        logger.warning("[AN87330] 功率档位由电压×电流档位决定，不支持单独设置")

    def set_voltage_auto_range(self, channel: int, enabled: bool = True):
        """
        开启或关闭指定通道的电压自动量程。

        手册协议：参数值 > 7 即为自动量程，0~7 为具体档位。
        开启自动 → 发送 8（任意 >7 的值）
        关闭自动 → 需要指定具体档位（本方法设为 300V 常用档）

        Args:
            channel: 通道号（1/2/3）
            enabled: True = 开启自动量程，False = 关闭自动量程（切回手动）
        """
        ch = self._parse_channel(channel)
        if enabled:
            self._send_set_frame(self.SET_PARAM_VOLTAGE_RANGE, 8)   # 值 > 7 = 自动量程
            logger.info(f"[AN87330] CH{ch} 电压量程 → 自动量程")
        else:
            self._send_set_frame(self.SET_PARAM_VOLTAGE_RANGE, 5)   # 300V 常用档
            logger.info(f"[AN87330] CH{ch} 电压量程 → 手动 300V（关闭自动）")

    def set_current_auto_range(self, channel: int, enabled: bool = True):
        """
        开启或关闭指定通道的电流自动量程。

        手册协议：参数值 > 7 即为自动量程，0~7 为具体档位。
        开启自动 → 发送 8（任意 >7 的值）
        关闭自动 → 需要指定具体档位（本方法设为 5A 常用档）

        Args:
            channel: 通道号（1/2/3）
            enabled: True = 开启自动量程，False = 关闭自动量程（切回手动）
        """
        ch = self._parse_channel(channel)
        if enabled:
            self._send_set_frame(self.SET_PARAM_CURRENT_RANGE, 8)   # 值 > 7 = 自动量程
            logger.info(f"[AN87330] CH{ch} 电流量程 → 自动量程")
        else:
            self._send_set_frame(self.SET_PARAM_CURRENT_RANGE, 5)   # 5A 常用档
            logger.info(f"[AN87330] CH{ch} 电流量程 → 手动 5A（关闭自动）")

    def set_current_range_auto(self, channel: int, current: float):
        """
        根据目标电流自动选择合适的电流档位并设置。

        选档规则：目标电流 × 1.4（留 40% 裕量，与 WT333E 一致）
        后在量程列表中选择 ≥ 该值的最小档位。
        若无满足条件则用最大档（20A）。

        Args:
            channel: 通道号（1/2/3）
            current: 目标电流（A）
        """
        ranges = sorted(self._CURRENT_RANGES)
        target = abs(current) * 1.4
        candidates = [r for r in ranges if r >= target]
        chosen = candidates[0] if candidates else ranges[-1]
        idx = self._CURRENT_RANGES.index(chosen)
        ch = self._parse_channel(channel)
        self._send_set_frame(self.SET_PARAM_CURRENT_RANGE, idx)
        logger.info(f"[AN87330] CH{ch} 电流 {current}A×1.4={target:.3f}A → 自动选档 {chosen}A（档位 {idx}）")

    def lock_minimum_current_range(self, channel: int = 1) -> float:
        """
        重写父类方法：锁定 AN87330 的最小电流量程档位（0.1A = 档位0）。

        基类默认行为是锁 0.5A，但 AN87330 的最小档是 0.1A，
        对于待机功耗等小电流场景更应该用 0.1A 以获得更高分辨率。

        Args:
            channel: 通道号（1/2/3）

        Returns:
            实际设置的电流量程（A）
        """
        # AN87330 最小档 = 0.1A（档位0）
        min_range = min(self._CURRENT_RANGES)
        self.set_current_range(channel, min_range)
        logger.info(f"[AN87330] CH{self._parse_channel(channel)} 电流量程锁定最小档 {min_range*1000:.1f}mA")
        return min_range

    def set_wiring_mode(self, mode: str):
        if mode not in {"1P2W", "1P3W", "3P3W", "3V3A", "3P4W"}:
            raise ValueError("Unsupported wiring mode: " + mode)
        self._wiring_mode = mode
        logger.info("[AN87330] Wiring mode: %s", mode)

    def set_input_type(self, input_type: str):
        if input_type not in {"AC", "DC", "ACDC"}:
            raise ValueError("Unsupported input type: " + input_type)
        logger.info("[AN87330] Input type: %s", input_type)

    def set_average_filter(self, enabled: bool = True, count: int = 16):
        pass

    def reset_zero(self, channel: int):
        logger.info("[AN87330] Reset zero CH%d (manual)", channel)

    # ─── 常规测量（命令字 0x00）
    # 响应数据从第7字节开始（跳过响应头4字节）
    # 布局：U(6) I(6) P(8) PF(2) S(6) Q(6) 相位角(2)
    #       fV(4) fI(4) Urec(6) Udc(6) Upk+(6) Upk-(6) Upk(6)
    #       Irec(6) Idc(6) Ipk+(6) Ipk-(6) Ipk(6)
    # ────────────────────────────────────────────────────────

    def _query_ch(self, ch: int) -> dict:
        resp = self._send_frame(self._build_frame(self.CMD_MEASURE, bytes([ch])))
        # resp = data[3:] = [响应头4字节 | 测量数据]
        # 布局：[响应头4字节] U(6) I(6) P(8) PF(2) S(6) Q(6) 相位角(2)
        #                   fV(4) fI(4) Urec(6) Udc(6) Upk+(6) Upk-(6) Upk(6)
        #                   Irec(6) Idc(6) Ipk+(6) Ipk-(6) Ipk(6)
        d = resp
        if len(d) < 111:
            raise IOError("AN87330: CH%d response too short: %d bytes" % (ch, len(d)))
        return {
            "voltage":      self._be6(d[4:10]),
            "current":      self._be6(d[10:16]) / 1000.0,
            "power":        self._be8(d[16:24]),
            "pf":           self._be2_10k(d[24:26]),
            "apparent":     self._be8(d[26:34]),
            "reactive":     self._be8(d[34:40]),
            "phase":        self._be2_10(d[40:42]),
            "freq_v":       self._be4(d[42:46]),
            "freq_i":       self._be4(d[46:50]),
            "U_rectified":  self._be6(d[50:56]),
            "U_dc":         self._be6(d[56:62]),
            "U_peak_pos":   self._be6(d[62:68]),
            "U_peak_neg":   self._be6(d[68:74]),
            "U_peak":       self._be6(d[74:80]),
            "I_rectified":  self._be6(d[80:86]) / 1000.0,
            "I_dc":         self._be6(d[86:92]) / 1000.0,
            "I_peak_pos":   self._be6(d[92:98]) / 1000.0,
            "I_peak_neg":   self._be6(d[98:104]) / 1000.0,
            "I_peak":       self._be6(d[104:110]) / 1000.0,
        }

    def measure_voltage(self, channel: int = 0) -> float:
        return self._query_ch(channel + 1)["voltage"]

    def measure_current(self, channel: int = 0) -> float:
        return self._query_ch(channel + 1)["current"]

    def measure_power(self, channel: int = 0) -> float:
        return self._query_ch(channel + 1)["power"]

    def measure_input_power(self) -> float:
        """
        读取输入端功率。
        通道由 set_channel_roles(input_voltage_ch="CH1"/"CH2"/"CH3") 配置。
        InputEfficiencyTest 通过此方法读取 Pin。
        """
        return self._query_ch(self._input_ch)["power"]

    def measure_apparent_power(self, channel: int = 0) -> float:
        return self._query_ch(channel + 1)["apparent"]

    def measure_reactive_power(self, channel: int = 0) -> float:
        return self._query_ch(channel + 1)["reactive"]

    def measure_power_factor(self, channel: int = 0) -> float:
        return self._query_ch(channel + 1)["pf"]

    def measure_frequency(self, channel: int = 0) -> float:
        return self._query_ch(channel + 1)["freq_v"]

    def measure_all(self, channel: int = 0) -> dict:
        return self._query_ch(channel + 1)

    # ─── 输出侧测量（兼容 WT333E 惯例：CH2 = 输出）───────────────────────────

    def measure_output_voltage(self) -> float:
        """测量输出侧电压 (Vrms)，即 CH2"""
        return self._query_ch(2)["voltage"]

    def measure_output_current(self) -> float:
        """测量输出侧电流 (Arms)，即 CH2"""
        return self._query_ch(2)["current"]

    def measure_output_power(self) -> float:
        """测量输出侧功率 (W)，即 CH2"""
        return self._query_ch(2)["power"]

    def measure_output_power_factor(self) -> float:
        """测量输出侧功率因数，即 CH2"""
        return self._query_ch(2)["pf"]

    # ─── 通道角色配置（兼容 WT333E set_channel_roles 接口）───────────────

    def set_channel_roles(self, input_voltage_ch: str = None, output_voltage_ch: str = None):
        """
        设置 AN87330 的输入/输出通道角色，兼容 instrument_manager.apply_channel_roles() 调用。

        Args:
            input_voltage_ch:  交流输入侧通道，"CH1" / "CH2" / "CH3"（连接 AC Source）
            output_voltage_ch: DUT 输出侧通道，"CH1" / "CH2" / "CH3"（连接电子负载）
        """
        if input_voltage_ch is not None:
            self._input_ch = self._parse_channel(input_voltage_ch)
            logger.info(f"[AN87330] 输入通道 → CH{self._input_ch}")
        if output_voltage_ch is not None:
            self._output_ch = self._parse_channel(output_voltage_ch)
            logger.info(f"[AN87330] 输出通道 → CH{self._output_ch}")

    # ─── 三相汇总（命令字 0x02）──────────────────────────────

    def _query_3phase(self) -> dict:
        resp = self._send_frame(self._build_frame(self.CMD_3PHASE, bytes([0x00])))
        # resp = data[3:] = [响应头4字节 | 三相测量数据]
        d = resp
        logger.debug("[AN87330] 3P response: %d bytes, hex: %s", len(d), d.hex())
        if len(d) < 20:
            raise IOError("AN87330: 3P response too short: %d bytes" % len(d))
        # 三相汇总布局（待完全解析）：
        # [响应头4字节] UP1(6) UI1(6) IP1(6) PF1(2) UP2(6) UI2(6) IP2(6) PF2(2) ... 简化解析
        # 前 108 字节：3×(U6+I6+P8+PF2+S6+Q6+相位2) = 108 字节
        # 暂时返回空，后续按实测数据修正布局
        return {
            "voltage":  self._be6(d[4:10]) if len(d) > 10 else 0.0,
            "current": self._be6(d[10:16]) / 1000.0 if len(d) > 16 else 0.0,
            "power":   self._be6(d[16:22]) if len(d) > 22 else 0.0,
            "pf":      self._be2_10k(d[22:24]) if len(d) > 24 else 0.0,
            "apparent": 0.0,
            "reactive": 0.0,
            "energy_pos": 0.0,
            "energy_neg": 0.0,
            "energy": 0.0,
            "ah_pos": 0.0,
            "ah_neg": 0.0,
            "ah": 0.0,
        }

    def measure_3phase_voltage(self) -> float:
        return self._query_3phase()["voltage"]

    def measure_3phase_current(self) -> float:
        return self._query_3phase()["current"]

    def measure_3phase_power(self) -> float:
        return self._query_3phase()["power"]

    def measure_3phase_power_factor(self) -> float:
        return self._query_3phase()["pf"]

    # ─── 积分功能 ────────────────────────────────────────────

    def start_integration(self):
        logger.info("[AN87330] Integration start (manual on device)")

    def stop_integration(self):
        logger.info("[AN87330] Integration stop (manual on device)")

    def reset_integration(self):
        logger.info("[AN87330] Integration reset (manual on device)")

    def get_integrated_energy(self, channel: int = 3) -> float:
        return self._query_3phase()["energy"]

    def get_integration_time(self) -> float:
        resp = self._send_frame(self._build_frame(self.CMD_ENERGY, bytes([1])))
        if len(resp) < 28:
            return 0.0
        return resp[0] * 3600 + resp[1] * 60 + resp[2]

    def get_integration_status(self) -> dict:
        try:
            wh = self.get_integrated_energy(3)
            t = self.get_integration_time()
        except Exception:
            wh = 0.0
            t = 0.0
        return {"running": False, "wh": wh, "time": t, "limit": "none"}

    # ─── 谐波功能 ───────────────────────────────────────────

    def set_harmonic_mode(self, enabled: bool = True):
        logger.info("[AN87330] Harmonic mode %s (manual)", "enable" if enabled else "disable")

    def set_harmonic_order_limit(self, max_order: int):
        logger.info("[AN87330] Harmonic order limit %d (manual)", max_order)

    def get_thd(self, channel: int = 0) -> float:
        resp = self._send_frame(self._build_frame(self.CMD_HARM, bytes([channel + 1])))
        if len(resp) < 24:
            return 0.0
        return self._be4(resp[16:20])

    def get_harmonic_value(self, channel: int, order: int) -> float:
        return 0.0

    def get_all_harmonics(self, channel: int = 0) -> dict:
        resp = self._send_frame(self._build_frame(self.CMD_HARM, bytes([channel + 1])))
        if len(resp) < 24:
            return {"thd_u": 0.0, "thd_i": 0.0, "thd_p": 0.0,
                    "U_fundamental": 0.0, "I_fundamental": 0.0, "P_fundamental": 0.0}
        return {
            "U_fundamental": self._be4(resp[0:4]),
            "I_fundamental": self._be4(resp[4:8]),
            "P_fundamental": self._be4(resp[8:12]),
            "thd_u":         self._be4(resp[12:16]),
            "thd_i":         self._be4(resp[16:20]),
            "thd_p":         self._be4(resp[20:24]),
        }
