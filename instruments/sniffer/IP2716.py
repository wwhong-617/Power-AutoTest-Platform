# -*- coding: utf-8 -*-
"""
IP2716Sniffer - 英集芯 IP2716 协议诱骗器驱动
==============================================

基于 Excel: 诱骗器IP2716通讯协议指令表.xlsx

支持协议：
  PD 快充  (COMMAND 0x50): Position 1~7 + PPS 升压/降压/微调
  QC 快充  (COMMAND 0x30): QC2.0 5V/9V/12V/20V + QC3.0 升压/降压
  UFCS 快充 (COMMAND 0x60): Position 1 档位 + 电压/电流微调

通讯参数：19200 波特率 / 8N1 / 二进制帧

用法示例：
  sniffer = IP2716Sniffer(port="COM13", slave_addr=1)
  sniffer.connect()

  # PD 20V
  sniffer.set_pd_mode()
  time.sleep(0.6)
  sniffer.set_pd_position(IP2716Sniffer.PD_POSITION_4)

  # QC 20V
  sniffer.set_qc_mode()
  time.sleep(0.6)
  sniffer.set_qc_voltage(IP2716Sniffer.QC2_0_20V)

  # UFCS
  sniffer.set_ufcs_mode()
  sniffer.set_ufcs_position()

  sniffer.disconnect()
"""

import time
from .BaseSniffer import BaseSniffer, SnifferError
from . import protocol_IP2716 as P


class IP2716Sniffer(BaseSniffer):
    """
    英集芯 IP2716 协议诱骗器。

    注意：PD Position 是档位号，具体电压由 DUT 的 PDO 决定。
    诱骗器只负责请求对应档位。
    """

    # ---------- 快捷常量 ----------
    # PD 档位
    PD_POSITION_1 = P.PD_POSITION_1   # 0x00
    PD_POSITION_2 = P.PD_POSITION_2
    PD_POSITION_3 = P.PD_POSITION_3
    PD_POSITION_4 = P.PD_POSITION_4   # 通常 20V
    PD_POSITION_5 = P.PD_POSITION_5
    PD_POSITION_6 = P.PD_POSITION_6
    PD_POSITION_7 = P.PD_POSITION_7   # PPS 档
    PD_PPS_VOLT_UP   = P.PD_PPS_VOLT_UP
    PD_PPS_VOLT_DOWN = P.PD_PPS_VOLT_DOWN
    PD_PPS_CURR_UP   = P.PD_PPS_CURR_UP
    PD_PPS_CURR_DOWN = P.PD_PPS_CURR_DOWN

    # QC 电压档位
    QC2_0_5V  = P.QC2_0_5V
    QC2_0_9V  = P.QC2_0_9V
    QC2_0_12V = P.QC2_0_12V
    QC2_0_20V = P.QC2_0_20V
    QC3_ENTER    = P.QC3_ENTER
    QC3_EXIT     = P.QC3_EXIT
    QC3_VOLT_UP  = P.QC3_VOLT_UP
    QC3_VOLT_DOWN = P.QC3_VOLT_DOWN

    # UFCS
    UFCS_POSITION_1 = P.UFCS_POSITION_1
    UFCS_VOLT_UP   = P.UFCS_VOLT_UP
    UFCS_VOLT_DOWN = P.UFCS_VOLT_DOWN
    UFCS_CURR_UP   = P.UFCS_CURR_UP
    UFCS_CURR_DOWN = P.UFCS_CURR_DOWN

    def __init__(self, port: str = None, slave_addr: int = 1,
                 timeout_ms: int = 1000, simulation: bool = False,
                 debug: bool = False):
        """
        Args:
            port:       串口名，如 "COM13"
            slave_addr: 设备地址 (1~255)，拨码开关决定
            timeout_ms: 串口超时（毫秒）
            simulation: True = 直接进入模拟模式
            debug:      True = 打印 TX/RX 原始字节
        """
        super().__init__(port=port, slave_addr=slave_addr,
                         timeout_ms=timeout_ms, debug=debug)
        if simulation:
            self.enable_simulation(slave_addr=slave_addr)

    # ================================================================
    #  私有工具
    # ================================================================

    def _send_initial_commands(self):
        """清缓冲区"""
        if self._serial is None:
            return
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()

    def _validate_identity(self) -> bool:
        """
        IP2716 没有独立身份查询命令。
        只要串口能打开就认为连接正常。
        """
        return True

    # ================================================================
    #  1. 初始化
    # ================================================================

    def initialize(self) -> bool:
        """
        完整初始化：清缓冲区 + 固件自检。
        """
        self._send_initial_commands()
        return self.fw_self_test()

    def fw_self_test(self) -> bool:
        """
        固件自检。
        发送: 7B [ADDR] 09 1F [8字节0] [CHECKSUM]
        期望回复: 7B [ADDR] 02 1F [RESULT] [CHECKSUM]
                  RESULT = 0xFF → PASS，0x00 → FAIL

        Returns:
            True = PASS，False = FAIL 或超时
        """
        frame = self._build_frame(0x1F, bytes([0] * 8))
        self._send_frame(frame)

        try:
            deadline = time.time() + (self._ack_timeout_ms / 1000)
            while time.time() < deadline:
                ch = self._serial.read(1)
                if ch and ch[0] == self.HEADER:
                    rest = self._serial.read(4)
                    if len(rest) >= 4 and rest[0] == self._slave_addr and rest[2] == 0x1F:
                        result = rest[3]
                        if self._debug:
                            print(f"  [fw_self_test] result=0x{result:02X}")
                        return result == 0xFF
                time.sleep(0.01)
        except Exception as e:
            if self._debug:
                print(f"  [fw_self_test] error: {e}")
        finally:
            try:
                self._serial.reset_input_buffer()
            except Exception:
                pass
        return False

    # ================================================================
    #  2. PD 协议申请
    # ================================================================

    def set_pd_mode(self) -> bool:
        """
        配置为 PD 快充模式。
        切换后需等待 ≥500ms 再发送档位请求。

        发送: 7B [ADDR] 01 50 [CHECKSUM]
        """
        frame = self._build_frame(P.PD_CMD)
        return self._send_and_wait_ack(frame)

    def set_pd_position(self, position: int) -> bool:
        """
        申请 PD 档位（需先 set_pd_mode）。

        Args:
            position: PD_POSITION_1~7 (0x00~0x06)
                      PD_POSITION_1 = 第1档，PD_POSITION_4 = 第4档 等

        Returns:
            True = 成功，False = 失败
        """
        frame = self._build_frame(P.PD_CMD, bytes([position]))
        return self._send_and_wait_ack(frame)

    def set_pd_pps_voltage_step(self, direction: str = "UP") -> bool:
        """
        PPS 电压微调（需先 set_pd_mode + set_pd_position(PD_POSITION_7)）。

        Args:
            direction: "UP" = 升压 (+100mV)，"DOWN" = 降压 (-100mV)
        """
        direction = direction.upper()
        cmd = P.PD_PPS_VOLT_UP if direction == "UP" else P.PD_PPS_VOLT_DOWN
        frame = self._build_frame(P.PD_CMD, bytes([cmd]))
        return self._send_and_wait_ack(frame)

    def set_pd_pps_current_step(self, direction: str = "UP") -> bool:
        """
        PPS 电流微调（需先 set_pd_mode + set_pd_position(PD_POSITION_7)）。

        Args:
            direction: "UP" = 增大 (+50mA)，"DOWN" = 减小 (-50mA)
        """
        direction = direction.upper()
        cmd = P.PD_PPS_CURR_UP if direction == "UP" else P.PD_PPS_CURR_DOWN
        frame = self._build_frame(P.PD_CMD, bytes([cmd]))
        return self._send_and_wait_ack(frame)

    # ================================================================
    #  3. QC 协议申请
    # ================================================================

    def set_qc_mode(self) -> bool:
        """
        配置为 QC 快充模式。
        切换后需等待 ≥500ms 再发送电压请求。

        发送: 7B [ADDR] 01 30 [CHECKSUM]
        """
        frame = self._build_frame(P.QC_CMD)
        return self._send_and_wait_ack(frame)

    def set_qc_voltage(self, voltage: float) -> bool:
        """
        申请 QC 固定电压档位（需先 set_qc_mode）。

        Args:
            voltage: QC2_0_5V / QC2_0_9V / QC2_0_12V / QC2_0_20V
                     或 QC3_ENTER / QC3_EXIT / QC3_VOLT_UP / QC3_VOLT_DOWN

        Returns:
            True = 成功，False = 失败
        """
        frame = self._build_frame(P.QC_CMD, bytes([int(voltage)]))
        return self._send_and_wait_ack(frame)

    def set_qc3_voltage_adjust(self, direction: str = "UP") -> bool:
        """
        QC3.0 恒压模式下电压微调（步进 0.2V，需先 set_qc_mode + set_qc_voltage(QC3_ENTER)）。

        Args:
            direction: "UP" = 升压 (+0.2V)，"DOWN" = 降压 (-0.2V)
        """
        direction = direction.upper()
        cmd = P.QC3_VOLT_UP if direction == "UP" else P.QC3_VOLT_DOWN
        frame = self._build_frame(P.QC_CMD, bytes([cmd]))
        return self._send_and_wait_ack(frame)

    def set_qc3_exit(self) -> bool:
        """
        退出 QC3.0 恒压模式，返回 QC2.0 状态。
        发送: 7B [ADDR] 02 30 05 [CHECKSUM]
        """
        frame = self._build_frame(P.QC_CMD, bytes([P.QC3_EXIT]))
        return self._send_and_wait_ack(frame)

    # ================================================================
    #  4. UFCS 协议申请
    # ================================================================

    def set_ufcs_mode(self) -> bool:
        """
        配置为 UFCS 快充模式。
        切换后需等待 ≥500ms 再发送档位请求。

        发送: 7B [ADDR] 01 60 [CHECKSUM]
        """
        frame = self._build_frame(P.UFCS_CMD)
        return self._send_and_wait_ack(frame)

    def set_ufcs_position(self, position: int = 1) -> bool:
        """
        申请 UFCS 档位（需先 set_ufcs_mode）。

        Args:
            position: 档位号（默认 1），目前 IP2716 支持 Position 1
        """
        frame = self._build_frame(P.UFCS_CMD, bytes([position]))
        return self._send_and_wait_ack(frame)

    def set_ufcs_voltage_step(self, direction: str = "UP") -> bool:
        """
        UFCS 电压微调（需先 set_ufcs_mode + set_ufcs_position）。

        Args:
            direction: "UP" = 升压 (+100mV)，"DOWN" = 降压 (-100mV)
        """
        direction = direction.upper()
        cmd = P.UFCS_VOLT_UP if direction == "UP" else P.UFCS_VOLT_DOWN
        frame = self._build_frame(P.UFCS_CMD, bytes([cmd]))
        return self._send_and_wait_ack(frame)

    def set_ufcs_current_step(self, direction: str = "UP") -> bool:
        """
        UFCS 电流微调（需先 set_ufcs_mode + set_ufcs_position）。

        Args:
            direction: "UP" = 增大 (+100mA)，"DOWN" = 减小 (-100mA)
        """
        direction = direction.upper()
        cmd = P.UFCS_CURR_UP if direction == "UP" else P.UFCS_CURR_DOWN
        frame = self._build_frame(P.UFCS_CMD, bytes([cmd]))
        return self._send_and_wait_ack(frame)

    def get_ufcs_source_info(self) -> dict:
        """
        查询 UFCS Source 端信息。

        IP2716 回复帧: HEADER ADDR LEN CMD DATA(4) CHECKSUM
          DATA[0,1] = 电压（10mV/step）
          DATA[2,3] = 电流（10mA/step）
          DATA[4]   = 内部温度 (℃)
          DATA[5]   = USB 口温度 (℃)

        Returns:
            dict: {
                "voltage_mv": int,  电压 (mV)
                "current_ma": int,  电流 (mA)
                "temp_int":   int,  内部温度 (℃)
                "temp_usb":   int,  USB 口温度 (℃)
            }
        """
        frame = self._build_frame(P.UFCS_CMD, bytes([0x0B]))
        self._send_frame(frame)

        try:
            deadline = time.time() + (self._ack_timeout_ms / 1000)
            while time.time() < deadline:
                ch = self._serial.read(1)
                if ch and ch[0] == self.HEADER:
                    rest = self._serial.read(5)  # ADDR + LEN + CMD + DATA(2)
                    if len(rest) >= 5 and rest[2] == 0x5A:
                        data = rest[3:5]
                        voltage = (data[0] << 8) | data[1]
                        remaining = self._serial.read(2)  # DATA(2) + CHECKSUM
                        if len(remaining) >= 2:
                            current = (remaining[0] << 8) | remaining[1]
                            return {
                                "voltage_mv": voltage * 10,   # 10mV/step → mV
                                "current_ma": current * 10,   # 10mA/step → mA
                                "temp_int":   0,
                                "temp_usb":   0,
                            }
                time.sleep(0.01)
        except Exception as e:
            if self._debug:
                print(f"  [get_ufcs_source_info] error: {e}")

        return {"voltage_mv": 0, "current_ma": 0, "temp_int": 0, "temp_usb": 0}

    # ================================================================
    #  便捷组合流程
    # ================================================================

    def apply_pd20v(self) -> bool:
        """
        一键设置 PD 第4档（完整流程）。
        流程：set_pd_mode → 等待 550ms → set_pd_position(PD_POSITION_4)
        """
        if not self.set_pd_mode():
            return False
        time.sleep(0.55)
        return self.set_pd_position(self.PD_POSITION_4)

    def apply_qc20v(self) -> bool:
        """
        一键设置 QC 20V（完整流程）。
        流程：set_qc_mode → 等待 550ms → set_qc_voltage(QC2_0_20V)
        """
        if not self.set_qc_mode():
            return False
        time.sleep(0.55)
        return self.set_qc_voltage(self.QC2_0_20V)

    def set_protocol(self, proto_label: str, vout: float = None, iout: float = None) -> bool:
        """
        统一协议配置入口。

        支持的 proto_label：
          PD:       "PD-PDO1" ~ "PD-PDO7"，"PDO4" 等
          QC 2.0:  "QC2.0-5V" / "QC2.0-9V" / "QC2.0-12V" / "QC2.0-20V"
          QC 3.0:  "QC3.0"
          UFCS:    "UFCS"
          普通:    "-" / "normal" / "" → 5V 默认模式

        Args:
            proto_label: 协议标签
            vout:        目标电压（V），仅 UFCS 预留
            iout:        目标电流（A），暂未使用

        Returns:
            True = 配置成功，False = 失败
        """
        pl = proto_label.strip()

        # 普通模式
        if pl in ("-", "normal", "", "None"):
            frame = self._build_frame(0x20)
            return self._send_and_wait_ack(frame)

        # PD 协议
        if pl.startswith("PD"):
            for i in range(7, 0, -1):
                if f"PDO{i}" in pl or f"PD-{i}" in pl or f"_PD{i}" in pl:
                    position = getattr(self, f"PD_POSITION_{i}", self.PD_POSITION_1)
                    break
            else:
                position = self.PD_POSITION_1
            if not self.set_pd_mode():
                return False
            time.sleep(0.6)
            return self.set_pd_position(position)

        # QC 协议
        if pl.startswith("QC"):
            volt_map = {
                "5V":  self.QC2_0_5V,
                "9V":  self.QC2_0_9V,
                "12V": self.QC2_0_12V,
                "20V": self.QC2_0_20V,
            }
            volt_val = self.QC2_0_5V
            for vk, vv in volt_map.items():
                if vk in pl:
                    volt_val = vv
                    break
            if not self.set_qc_mode():
                return False
            time.sleep(0.6)
            return self.set_qc_voltage(volt_val)

        # UFCS 协议
        if "UFCS" in pl:
            if not self.set_ufcs_mode():
                return False
            time.sleep(0.6)
            return self.set_ufcs_position(1)

        # 未知 → 普通模式
        frame = self._build_frame(0x20)
        return self._send_and_wait_ack(frame)
