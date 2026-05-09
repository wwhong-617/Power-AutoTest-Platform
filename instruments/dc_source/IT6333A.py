# -*- coding: utf-8 -*-
"""
ITECH IT6333A 直流电源驱动
============================

ITECH Electronics IT6333A 直流稳压电源。
通讯方式：USB (ITECH USBTMC) / TCPIP / RS232

已验证 SCPI 命令（ firmware 1.11-1.08）：
- VOLT <val>       设置电压 (V)
- VOLT?            查询电压设定值
- CURR <val>       设置限流 (A)
- CURR?            查询限流设定值
- OUTP ON/OFF      输出开关
- OUTP?            查询输出状态 (0=off, 1=on)
- MEAS?            测量所有值
- MEAS:VOLT?       测量输出电压 (V)
- MEAS:CURR?       测量输出电流 (A)
- MEAS:POW?        测量输出功率 (W)
- DISP ON/OFF      显示器控制

注意：IT6333A 支持三通道输出（CH1/CH2/CH3），
本驱动默认操作 CH1（主输出）。
"""

import time
from .BaseDCSource import BaseDCSource


class IT6333A(BaseDCSource):
    """
    ITECH IT6333A 直流电源驱动。
    继承自 BaseDCSource。
    """

    def __init__(self, conn_type: str, address: str, timeout_ms: int = 5000):
        super().__init__(conn_type, address, timeout_ms)
        self._model = "IT6333A"

    # ---------------------- 私有实现 ----------------------

    def _send_initial_commands(self):
        """
        轻量化初始化：*RST + *CLS。
        IT6333A 通过 USB/TCPIP 自动进入远程模式，无需 SYST:REM。
        """
        self.send_command("*RST", check_esr=False)
        time.sleep(0.5)
        self.send_command("*CLS", check_esr=False)
        time.sleep(0.05)

    def initialize(self):
        """
        完整初始化：调用轻量化重置。
        """
        self._send_initial_commands()

    def _validate_identity(self) -> bool:
        """验证仪器身份"""
        idn = self._idn
        if "IT6333A" in idn or "ITECH" in idn:
            return True
        if "SIMULATION" in idn:
            return True
        return False

    # ---------------------- 电压/电流 ----------------------

    def set_voltage(self, volts: float):
        """
        设置输出电压 (V)。
        IT6333A 电压范围：0 ~ 15V（CH1/CH2），0 ~ 5V（CH3）
        """
        self.send_command(f"VOLT {volts}")

    def set_current(self, amps: float):
        """
        设置限流值 (A)。
        IT6333A 电流范围：0 ~ 3A（各通道）
        """
        self.send_command(f"CURR {amps}")

    def get_voltage_setting(self) -> float:
        """查询电压设定值 (V)"""
        try:
            resp = self.query("VOLT?")
            return float(resp.strip())
        except Exception:
            return 0.0

    def get_current_setting(self) -> float:
        """查询限流设定值 (A)"""
        try:
            resp = self.query("CURR?")
            return float(resp.strip())
        except Exception:
            return 0.0

    # ---------------------- 输出控制 ----------------------

    def output_on(self):
        """开启输出"""
        self.send_command("OUTP ON", check_esr=False)

    def output_off(self):
        """关闭输出"""
        self.send_command("OUTP OFF", check_esr=False)

    def get_output_status(self) -> int:
        """
        查询输出状态。
        返回: 1=输出开启, 0=输出关闭
        """
        try:
            resp = self.query("OUTP?")
            return int(resp.strip())
        except Exception:
            return 0

    # ---------------------- 测量 ----------------------

    def measure_voltage(self) -> float:
        """
        测量输出电压 (V)。
        """
        try:
            resp = self.query("MEAS:VOLT?", delay_ms=300)
            return float(resp.strip())
        except Exception:
            return 0.0

    def measure_current(self) -> float:
        """
        测量输出电流 (A)。
        """
        try:
            resp = self.query("MEAS:CURR?", delay_ms=300)
            return float(resp.strip())
        except Exception:
            return 0.0

    def measure_power(self) -> float:
        """
        测量输出功率 (W)。
        """
        try:
            resp = self.query("MEAS:POW?", delay_ms=300)
            return float(resp.strip())
        except Exception:
            return 0.0

    def get_mode(self) -> str:
        """
        查询当前工作模式。
        返回: "VOLT" (恒压) / "LIST" (列表扫描) / "FIX" (固定)
        """
        try:
            resp = self.query("SOUR:FUNC:MODE?")
            return resp.strip()
        except Exception:
            return ""

    def measure_all(self) -> dict:
        """
        测量电压、电流、功率。
        返回: {"voltage": float, "current": float, "power": float}
        """
        v = self.measure_voltage()
        i = self.measure_current()
        p = self.measure_power()
        return {"voltage": v, "current": i, "power": p}

    # ---------------------- 显示控制 ----------------------

    def display_on(self):
        """开启前面板显示"""
        self.send_command("DISP ON", check_esr=False)

    def display_off(self):
        """关闭前面板显示（节省屏）"""
        self.send_command("DISP OFF", check_esr=False)

    # ---------------------- 通道选择（多通道支持） ----------------------

    def select_channel(self, channel: int):
        """
        选择活动通道 (1/2/3)。
        IT6333A 为三通道电源，本方法切换当前操作通道。
        注意：部分固件版本可能不支持此命令。
        """
        if channel not in (1, 2, 3):
            raise ValueError("Channel must be 1, 2 or 3")
        self.send_command(f"INST:OUTP {channel}")

    def get_selected_channel(self) -> int:
        """
        查询当前选中的通道。
        返回: 1, 2 或 3
        """
        try:
            resp = self.query("INST:OUTP?")
            return int(resp.strip())
        except Exception:
            return 1

    # ---------------------- 保护（部分固件支持） ----------------------

    def set_ovp_level(self, volts: float):
        """
        设置过压保护电平 (V)。
        注意：部分固件版本可能不支持此命令。
        """
        self.send_command(f"OUTP:OVP {volts}")

    def get_ovp_level(self) -> float:
        """查询过压保护电平 (V)"""
        try:
            resp = self.query("OUTP:OVP?")
            return float(resp.strip())
        except Exception:
            return 0.0

    def set_ocp_level(self, amps: float):
        """
        设置过流保护电平 (A)。
        注意：部分固件版本可能不支持此命令。
        """
        self.send_command(f"OUTP:OCP {amps}")

    def get_ocp_level(self) -> float:
        """查询过流保护电平 (A)"""
        try:
            resp = self.query("OUTP:OCP?")
            return float(resp.strip())
        except Exception:
            return 0.0

    # ---------------------- List 动态扫描模式 ----------------------

    def list_configure(self, voltages: list, currents: list = None,
                       dwell_times: list = None, repeat_count: int = 1):
        """
        配置 List 扫描序列。

        Args:
            voltages:    电压列表 [V1, V2, V3, ...]，最多 N 个点
            currents:    电流列表 [A1, A2, A3, ...]，与电压对应
            dwell_times: 每点停留时间列表 [s1, s2, s3, ...]，单位秒
            repeat_count: 重复次数，默认 1
        """
        n = len(voltages)

        # 设置点数
        self.send_command(f"LIST:POIN {n}")

        # 设置电压列表（逗号分隔）
        volt_str = ",".join(str(v) for v in voltages)
        self.send_command(f"LIST:VOLT {volt_str}")

        # 设置电流列表（可选）
        if currents:
            curr_str = ",".join(str(c) for c in currents)
            self.send_command(f"LIST:CURR {curr_str}")

        # 设置停留时间（可选）
        if dwell_times:
            dwell_str = ",".join(str(d) for d in dwell_times)
            self.send_command(f"LIST:DWEL {dwell_str}")

        # 设置重复次数
        self.send_command(f"LIST:COUN {repeat_count}")

    def list_start(self):
        """
        启动 List 扫描。
        必须在 list_configure() 之后调用。
        """
        self.send_command("SOUR:FUNC:MODE LIST", check_esr=False)
        self.send_command("OUTP ON", check_esr=False)

    def list_stop(self):
        """
        停止 List 扫描。
        """
        self.send_command("OUTP OFF", check_esr=False)
        self.send_command("SOUR:FUNC:MODE VOLT", check_esr=False)

    def list_query_voltages(self) -> list:
        """查询已配置的电压列表"""
        try:
            resp = self.query("LIST:VOLT?")
            return [float(v) for v in resp.strip().split(",")]
        except Exception:
            return []

    def list_query_currents(self) -> list:
        """查询已配置的电流列表"""
        try:
            resp = self.query("LIST:CURR?")
            return [float(c) for c in resp.strip().split(",")]
        except Exception:
            return []

    def list_query_dwell_times(self) -> list:
        """查询已配置的停留时间列表"""
        try:
            resp = self.query("LIST:DWEL?")
            return [float(d) for d in resp.strip().split(",")]
        except Exception:
            return []

    def list_query_repeat_count(self) -> int:
        """查询重复次数"""
        try:
            resp = self.query("LIST:COUN?")
            return int(resp.strip())
        except Exception:
            return 1

    def list_query_points(self) -> int:
        """查询 List 点数"""
        try:
            resp = self.query("LIST:POIN?")
            return int(resp.strip())
        except Exception:
            return 0

    def list_abort(self):
        """
        中断 List 扫描并恢复到 CV 模式。
        """
        self.send_command("OUTP OFF", check_esr=False)
        self.send_command("SOUR:FUNC:MODE VOLT", check_esr=False)
