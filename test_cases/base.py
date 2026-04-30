"""
TestCase - 测试用例基类
=========================

定义统一测试用例接口：
- name            用例名称
- instruments     所需仪器列表
- params          测试参数
- spec           判定规格（上下限）
- result          执行结果（执行后填充）

执行流程：
  setup() → execute() → verify() → teardown()

判定结果：
  - PASS:   实测值在规格范围内
  - FAIL:   实测值超出规格范围
  - ERROR:  执行异常（仪器通讯失败等）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
import time
import os
import logging


def info(msg: str):
    logging.getLogger("PowerAutoTest").info(msg)


def warning(msg: str):
    logging.getLogger("PowerAutoTest").warning(msg)


class TestResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIP = "SKIP"


@dataclass
class TestCase:
    """
    测试用例基类。
    所有用例必须继承此类并实现：
    - name        用例名称
    - instruments 所需仪器类型列表
    - params      测试参数
    - spec        判定规格
    """
    test_conditions: list = field(default_factory=list)  # subclass: override in setup() via params
    name: str = ""
    instruments: List[str] = field(default_factory=list)  # 如 ["AC_SOURCE", "ELOAD", "POWER_METER"]
    params: Dict[str, Any] = field(default_factory=dict)
    spec: Dict[str, Any] = field(default_factory=dict)

    # 执行后填充
    result: TestResult = TestResult.SKIP
    measurements: Dict[str, float] = field(default_factory=dict)
    error_message: str = ""
    start_time: float = 0
    end_time: float = 0

    # 引擎引用（由 TestEngine 在执行前注入）
    _engine: Any = None

    def is_stop_requested(self) -> bool:
        """查询是否收到停止请求（由 TestEngine 注入）"""
        return getattr(self, "_engine", None) is not None and \
            getattr(self._engine, "_stop_requested", False)

    def is_pause_requested(self) -> bool:
        """查询是否收到暂停请求（由 TestEngine 注入）"""
        return getattr(self, "_engine", None) is not None and \
            getattr(self._engine, "_pause_requested", False)

    def setup(self, instruments: Dict[str, Any]):
        """
        用例初始化（通用仪器初始化，子类可覆盖）。
        """
        for key, inst in instruments.items():
            if inst and getattr(inst, "_connected", False):
                if not hasattr(inst, "initialize"):
                    continue
                try:
                    inst.initialize()
                except Exception:
                    pass

        # ---- 将 engine 注入的 specs_v2 合并到 self.spec（供各测试用例读取）----
        specs_injected = self.params.get("specs", {})
        for k, v in specs_injected.items():
            if k.endswith("_lo") or k.endswith("_hi") or k.endswith("_pct_enable") or k.endswith("_pct"):
                self.spec[k] = v

    @abstractmethod
    def execute(self, instruments: Dict[str, Any]):
        """
        执行测试逻辑。
        子类实现具体的测试步骤。
        """
        pass

    def verify(self) -> bool:
        """
        验证测试结果是否通过规格。
        Returns:
            True = PASS, False = FAIL
        """
        return True

    def teardown(self, instruments: Dict[str, Any]):
        """
        清理恢复。
        用例执行完后恢复仪器状态。
        """
        self.end_time = time.time()

    # =====================================================================
    # 通用步骤方法（所有输入/输出测试共用）
    # =====================================================================

    def _step_discharge(self, ac, elod, current=1.0, duration=1.0):
        """
        统一放电流程：AC OFF → 电子负载 CC 恒流放电 → OFF。

        Args:
            ac:       AC 源实例
            elod:     电子负载实例
            current:  放电电流（A），默认 1.0A
            duration: 放电持续时间（秒），默认 1.0s
        """
        if ac and getattr(ac, "_connected", False):
            try:
                ac.output_off()
            except Exception:
                pass

        if elod and getattr(elod, "_connected", False):
            try:
                elod.set_mode_cc(current)
                elod.input_on()
                time.sleep(duration)
                elod.input_off()
            except Exception:
                try:
                    elod.input_off()
                except Exception:
                    pass

    def _step_power_down(self, ac, elod):
        """
        完整下电流程（测试用例结束后调用）。

        AC源 OFF → 电子负载短路2s（放电） → 电子负载 OFF → 短路释放。
        """
        if ac and getattr(ac, "_connected", False):
            try:
                ac.output_off()
            except Exception:
                pass

        if elod and getattr(elod, "_connected", False):
            try:
                elod.short_on()
                time.sleep(2.0)
                elod.input_off()
                elod.short_off()
            except Exception:
                try:
                    elod.input_off()
                except Exception:
                    pass

    def _step_power_off(self, ac, elod):
        """
        紧急下电（开机自检失败时调用，仅关闭输出，不放电）。

        AC OFF + 电子负载 OFF。
        """
        if ac and getattr(ac, "_connected", False):
            try:
                ac.output_off()
            except Exception:
                pass
        if elod and getattr(elod, "_connected", False):
            try:
                elod.input_off()
            except Exception:
                pass

    # =====================================================================
    # 功率分段支持（高低压功率分段）
    # =====================================================================
    def _is_power_segment_enabled(self) -> bool:
        """判断是否启用了高低压功率分段"""
        try:
            return bool(self.params.get("power_segment", 0)) and float(self.params.get("hv_power", 0)) > 0
        except (TypeError, ValueError):
            return False

    def _get_effective_iout(self, vin_cfg: float, vout_target: float, iout_target: float) -> float:
        """
        根据功率分段计算实际可用的输出电流。

        规则：
          - 未启用功率分段 → 返回原 iout_target
          - vin >= 180V（高压段）→ 返回原 iout
          - vin < 180V（低压段）：原始功率 = Vout × iout_target >= lv_power → 降为 lv_power/Vout；否则不变
        """
        if not self._is_power_segment_enabled():
            return iout_target
        lv = float(self.params.get("lv_power", 0.0))
        if vin_cfg < 180:
            original_power = vout_target * iout_target
            if original_power >= lv:
                return min(iout_target, lv / vout_target)
        return iout_target

    # =====================================================================
    # 仪器获取 Helper（统一获取 + None 时自动记录警告）
    # =====================================================================
    def _osc(self, instruments) -> Any:
        """获取示波器（OSC），未连接时记录警告。"""
        inst = instruments.get("OSC")
        if inst is None:
            warning(f"[{self.name}] 示波器（OSC）未连接或 key 错误")
        return inst

    def _eload(self, instruments) -> Any:
        """获取电子负载（ELOAD），未连接时记录警告。"""
        inst = instruments.get("ELOAD")
        if inst is None:
            warning(f"[{self.name}] 电子负载（ELOAD）未连接或 key 错误")
        return inst

    def _ac(self, instruments) -> Any:
        """获取交流源（AC_SOURCE），未连接时记录警告。"""
        inst = instruments.get("AC_SOURCE")
        if inst is None:
            warning(f"[{self.name}] 交流源（AC_SOURCE）未连接或 key 错误")
        return inst

    def _dc(self, instruments) -> Any:
        """获取直流源（DC_SOURCE），未连接时记录警告。"""
        inst = instruments.get("DC_SOURCE")
        if inst is None:
            warning(f"[{self.name}] 直流源（DC_SOURCE）未连接或 key 错误")
        return inst

    def _pwrmeter(self, instruments) -> Any:
        """获取功率计（POWER_METER），未连接时记录警告。"""
        inst = instruments.get("POWER_METER")
        if inst is None:
            warning(f"[{self.name}] 功率计（POWER_METER）未连接或 key 错误")
        return inst

    def _sniffer(self, instruments) -> Any:
        """获取诱骗器（SNIFFER），未连接时记录警告。"""
        inst = instruments.get("SNIFFER")
        if inst is None:
            warning(f"[{self.name}] 诱骗器（SNIFFER）未连接或 key 错误")
        return inst

    # =====================================================================
    # 步骤方法
    # =====================================================================

    def _step_setup_sniffer(self, sniffer, proto_label: str, vout: float,
                           iout: float) -> bool:
        """
        诱骗器协议设置。

        仅 charger 产品需要；adapter 直接返回 True。
        返回：锁定成功 True，失败 False。
        """
        product_type = self.params.get("product_type", "charger")
        if product_type != "charger" or sniffer is None:
            return True
        ok = bool(sniffer.set_protocol(proto_label, vout, iout))
        time.sleep(0.5)   # 协议调压需要稳定时间
        return ok

    def _step_setup_eload(self, elod, iout: float):
        """
        电子负载 CC 模式上电。

        设置目标电流 iout(A)，然后 ON。
        """
        if elod is None:
            return
        elod.set_mode_cc(iout)
        elod.input_on()

    # =====================================================================
    # 示波器操作（通用）
    # =====================================================================

    # 纹波测试统一时基（20ms/div，10div=200ms窗口）
    RIPPLE_TIME_BASE_S = 0.020

    def _step_setup_osc_roll(self, osc,
                              vout: float,
                              duration_s: float,
                              ch_in: int = None,
                              ch_out: int = 2,
                              coupling_in: str = "DC",
                              coupling_out: str = "DC",
                              add_vmax_vmin: bool = True):
        """
        统一配置示波器 ROLL 模式（输入电压扫描类测试共用）。

        配置内容：
          - 输入通道（ch_in）：DC 耦合，带宽限制，衰减比 attn_in
          - 输出通道（ch_out）：auto_config_channel（波形占 4~5 格）
          - 可选添加 VMAX/VMIN 测量项
          - 时基 = max(1s, duration_s/10)，ROLL 模式
          - osc.run() 恢复采集

        适用于：IVRT / IDT / IUVT / RippleLoadScan / RippleInputScan

        Args:
            osc:           示波器实例
            vout:          输出电压峰值（用于 auto_config_channel 计算刻度）
            duration_s:     扫描总时长（用于计算 timebase）
            ch_in/ch_out:  输入/输出通道编号
            coupling_in:   输入通道耦合方式，默认 DC
            coupling_out:  输出通道耦合方式，默认 DC
            add_vmax_vmin: 是否添加 VMAX/VMIN 测量项
        """
        if osc is None:
            warning(f"[{self.name}] 示波器未连接，跳过 ROLL 配置")
            return

        attn_in  = float(self.params.get("osc_input_attn",  1.0))
        attn_out = float(self.params.get("osc_output_attn", 1.0))

        # 输入通道配置（ch_in 存在时才配置）
        if ch_in is not None:
            osc.set_channel_config(channel=ch_in,
                                   coupling=coupling_in,
                                   attenuation=attn_in,
                                   voltage_scale=100.0,
                                   voltage_offset=0.0,
                                   bandwidth_limit=True)
            osc.set_channel_on(ch_in)

        # 输出通道自动配置：波形占 4~5 格，底部留 1 格
        osc.set_channel_on(ch_out)
        osc.auto_config_channel(channel=ch_out,
                               v_peak=vout,
                               coupling=coupling_out,
                               attenuation=attn_out,
                               bandwidth_limit=True)

        # VMAX/VMIN 测量项
        if add_vmax_vmin:
            osc.add_measurement(ch_out, "VMAX")
            osc.add_measurement(ch_out, "VMIN")

        # 时基 = duration / 10（覆盖完整扫描时长），最低 1s/div
        timebase = max(1.0, duration_s / 10.0)
        osc.set_timebase_mode("ROLL")
        time.sleep(0.3)
        osc.set_timebase(timebase)
        time.sleep(0.5)
        info(f"[{self.name}] 示波器 ROLL | 时基={timebase:.1f}s/div | "
             f"ch_in={ch_in} ch_out={ch_out}")

    def _osc_wait_trigger(self, osc,
                          timeout_s: float = 5.0,
                          poll_interval: float = 0.3) -> bool:
        """
        轮询等待示波器 SINGLE 触发完成。

        适用于 PowerOnOff 等需要等触发后再动作的场景。
        轮询 :RSTate?，状态为 STOP 时认为触发成功。

        Args:
            osc:            示波器实例
            timeout_s:      超时时间（秒），默认 5s
            poll_interval:  轮询间隔（秒），默认 0.3s

        Returns:
            True = 触发成功（STOP），False = 超时
        """
        if osc is None:
            return False

        elapsed = 0.0
        while elapsed < timeout_s:
            try:
                state = osc.get_run_state().upper().strip()
            except Exception:
                state = ""
            if state == "STOP":
                info(f"[{self.name}] 触发完成 | elapsed={elapsed:.2f}s")
                return True
            time.sleep(poll_interval)
            elapsed += poll_interval

        warning(f"[{self.name}] 触发超时 | elapsed={elapsed:.2f}s >= {timeout_s}s")
        return False

    def _step_setup_osc_ripple(self, osc,
                                ch: int = 2,
                                coupling: str = "AC",
                                ripple_spec_mv: float = 100.0):
        """
        统一纹波测试的示波器配置。

        配置内容：
          - 时基固定 20ms/div（200ms窗口）
          - 通道 AC/DC 耦合 + 带宽限制
          - AUTO 触发 + 双沿
          - VPP 测量

        适用于：RippleNoise / RippleLoadScan / RippleInputScan

        Args:
            osc:             示波器实例
            ch:              测量通道编号，默认 2
            coupling:        耦合方式，默认 AC
            ripple_spec_mv:  纹波规格（mVpp），用于计算电压刻度
        """
        if osc is None:
            warning(f"[{self.name}] 示波器未连接，跳过纹波配置")
            return

        osc.set_timebase(self.RIPPLE_TIME_BASE_S)
        osc.set_channel_on(ch)
        osc.set_channel_coupling(ch, coupling)
        osc.set_bandwidth_limit(ch, True)
        scale_v = (ripple_spec_mv / 1000.0) / 5.0
        osc.set_voltage_scale(ch, max(scale_v, 0.001))
        osc.set_channel_offset(ch, 0.0)
        osc.set_trigger_mode("AUTO")
        osc.set_trigger_source(f"CHAN{ch}")
        osc.set_trigger_level(0.0)
        osc.set_trigger_slope("BOTH")
        osc.add_measurement(ch, "VPP")
        info(f"[{self.name}] 示波器纹波配置 | CH{ch} {coupling} "
             f"时基={self.RIPPLE_TIME_BASE_S*1000:.0f}ms/div 刻度={scale_v*1000:.1f}mV/div")

    def _step_capture_and_measure(self, osc, ch_out: int,
                                  input_cond: str,
                                  proto_label: str,
                                  vout_target: float,
                                  iout_target: float) -> Tuple[float, float, str]:
        """
        示波器 STOP 冻结波形，测量 Vmax/Vmin，保存截图。

        流程：
          1. osc.stop() 冻结波形
          2. 等待 1s 波形稳定
          3. 添加 VMAX/VMIN 测量项
          4. 等待 0.3s 测量面板刷新
          5. 查询 VMAX/VMIN
          6. 保存波形截图
          7. osc.run() 恢复采集

        返回：(osc_vmax, osc_vmin, wave_path)
        """
        osc_vmax = osc_vmin = 0.0
        wave_path = ""

        if osc is None:
            return osc_vmax, osc_vmin, wave_path

        try:
            osc.stop()
            info(f"[{self.name}] 示波器 STOP")
        except Exception as e:
            warning(f"[{self.name}] 示波器 STOP 失败: {e}")

        time.sleep(1.0)   # 等待波形稳定

        try:
            osc.add_measurement(ch_out, "VMAX")
            osc.add_measurement(ch_out, "VMIN")
            time.sleep(0.3)   # 等待测量面板刷新
            osc_vmax = osc.measure_voltage_max(ch_out)
            osc_vmin = osc.measure_voltage_min(ch_out)
            info(f"[{self.name}] 示波器测量 | Vmax={osc_vmax:.3f}V Vmin={osc_vmin:.3f}V")
        except Exception as e:
            warning(f"[{self.name}] 示波器测量失败: {e}")

        try:
            wave_path = self._save_waveform(osc, input_cond,
                                            proto_label, vout_target, iout_target)
        except Exception as e:
            warning(f"[{self.name}] 波形保存失败: {e}")

        time.sleep(2)
        osc.run()   # 恢复采集，为下一条条件准备
        return osc_vmax, osc_vmin, wave_path

    # =====================================================================
    # 工具方法
    # =====================================================================

    def _get_waveform_dir(self) -> str:
        """
        获取波形保存目录，不存在则自动创建。

        优先取 params["osc_waveform_dir"]，否则用项目 results/osc_waveforms。
        """
        d = self.params.get("osc_waveform_dir")
        if not d:
            d = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "results", "osc_waveforms"
            )
        os.makedirs(d, exist_ok=True)
        return d

    def _save_waveform(self, osc, input_cond: str,
                       proto_label: str, vout: float, iout: float) -> Optional[str]:
        """
        统一保存波形截图到测试报告目录。

        文件名格式：测试用例名称_输入条件_协议_输出电压_输出电流.png

        Returns:
            截图保存路径，失败返回 None。
        """
        if osc is None:
            return None

        base_dir = self._get_waveform_dir()
        fname = f"{self.name}_{input_cond}_{proto_label}_Vout{vout}V_Iout{iout}A.png"
        fpath = os.path.join(base_dir, fname)

        try:
            return osc.save_screenshot(fpath)
        except Exception:
            return None

    def startup_self_check(
        self,
        instruments: Dict[str, Any],
        vin: float = None,
        freq: float = None,
    ) -> Tuple[bool, float, str]:
        """
        开机自检（支持三次尝试，最多两次清除故障重试）。

        参数可传入 vin/freq 覆盖 self.params（用于测试条件上电）。
        逻辑：
          - load_startup_enabled=True → 电子负载带载（load_startup_current）；否则 CC=0A
          - AC ON → 等待 2s 稳定
          - 功率计测输出电压，实测 >= load_startup_voltage × 0.9 则通过
          - 每次失败 → 清除故障 → AC OFF → 等1s → AC ON → 再试
          - 第三次仍失败 → 返回 False
        """
        import logging
        logger = logging.getLogger("PowerAutoTest")

        # ---- 从 self.params 读取所有参数 ----
        load_startup_voltage = float(self.params.get("load_startup_voltage", 5.0))
        load_startup_current = float(self.params.get("load_startup_current", 0.0))
        load_startup_enabled = bool(self.params.get("load_startup_enabled", False))
        # vin/freq 优先用传入值，否则读 params
        _vin = float(vin if vin is not None else self.params.get("input_voltage_min", 90.0))
        _freq = float(freq if freq is not None else self.params.get("freq", 50.0))

        eload    = instruments.get("ELOAD")
        ac       = instruments.get("AC_SOURCE")
        pwrmeter = instruments.get("POWER_METER")

        def _do_check():
            """执行一次完整开机自检逻辑，返回 (ok, measured_vout, reason)"""
            logger.info(f"[StartupCheck] _do_check 开始...")
            if eload and getattr(eload, "_connected", False):
                try:
                    eload.send_command("*CLS")
                    time.sleep(0.1)
                    # 先显式切换到 CC 模式，确保退出动态模式
                    eload.send_command(":FUNC CURR")
                    time.sleep(0.05)
                    if load_startup_enabled:
                        eload.set_mode_cc(load_startup_current)
                    else:
                        eload.set_mode_cc(0.0)
                    eload.input_on()
                except Exception as e:
                    logger.warning(f"[StartupCheck] 配置电子负载失败: {e}")
            else:
                logger.warning(f"[StartupCheck] 电子负载未连接，跳过配置")

            if ac and getattr(ac, "_connected", False):
                try:
                    logger.info(f"[StartupCheck] AC 上电: {_vin}V / {_freq}Hz")
                    ac.set_voltage(_vin)
                    ac.set_frequency(_freq)
                    ac.output_on()
                    logger.info(f"[StartupCheck] AC OUTPUT ON 已发送")
                except Exception as e:
                    logger.warning(f"[StartupCheck] AC 源上电失败: {e}")
            else:
                logger.warning(f"[StartupCheck] AC 源未连接，跳过上电")

            logger.info(f"[StartupCheck] 准备测量输出电压，load_startup_voltage={load_startup_voltage}")
            threshold = load_startup_voltage * 0.90
            logger.info(f"[StartupCheck] threshold={threshold}")
            measured_vout = 0.0

            if pwrmeter and getattr(pwrmeter, "_connected", False):
                try:
                    pwr_ch_str = self.params.get("pwr_out_v_ch", "CH1")
                    time.sleep(2)
                    measured_vout = pwrmeter.measure_voltage(channel=pwr_ch_str)
                except Exception as e:
                    logger.warning(f"[StartupCheck] 功率计读取失败: {e}")

            if measured_vout >= threshold:
                return True, measured_vout, ""
            else:
                reason = f"输出电压 {measured_vout:.3f}V < {threshold:.3f}V（{load_startup_voltage}V×90%）"
                return False, measured_vout, reason

        def _clear_and_retry():
            """清除AC源故障，重新上电，等待稳定"""
            if ac and getattr(ac, "_connected", False):
                try:
                    ac.clear_protection_alarm()
                    time.sleep(0.5)
                    ac.output_off()
                    time.sleep(0.5)
                    ac.output_on()
                    logger.info("[StartupCheck] AC 已清除故障并重新上电，等待 2s 稳定")
                    time.sleep(2.0)
                except Exception as e:
                    logger.warning(f"[StartupCheck] AC 重新上电失败: {e}")

        # ---- 第1次尝试 ----
        ok, measured_vout, reason = _do_check()
        if ok:
            logger.info(f"[StartupCheck] 通过 | 实测 {measured_vout:.3f}V >= {load_startup_voltage * 0.90:.3f}V")
            return True, measured_vout, ""

        # ---- 第2次尝试（清除故障） ----
        logger.warning(f"[StartupCheck] 第1次失败: {reason}，清除故障重试...")
        _clear_and_retry()
        ok, measured_vout, reason = _do_check()
        if ok:
            logger.info(f"[StartupCheck] 第2次通过 | 实测 {measured_vout:.3f}V")
            return True, measured_vout, ""

        # ---- 第3次重试，清除后再试 ----
        logger.warning(f"[StartupCheck] 第2次失败: {reason}，再次清除保护...")
        _clear_and_retry()
        ok, measured_vout, reason = _do_check()
        if ok:
            logger.info(f"[StartupCheck] 第3次通过 | 实测 {measured_vout:.3f}V")
            return True, measured_vout, ""

        # ---- 第4次重试，清除后再试 ----
        logger.warning(f"[StartupCheck] 第3次失败: {reason}，再次清除保护...")
        _clear_and_retry()
        ok, measured_vout, reason = _do_check()
        if ok:
            logger.info(f"[StartupCheck] 第4次通过 | 实测 {measured_vout:.3f}V")
            return True, measured_vout, ""

        # ---- 第5次重试，清除后再试 ----
        logger.warning(f"[StartupCheck] 第4次失败: {reason}，再次清除保护...")
        _clear_and_retry()
        ok, measured_vout, reason = _do_check()
        if ok:
            logger.info(f"[StartupCheck] 第5次通过 | 实测 {measured_vout:.3f}V")
            return True, measured_vout, ""

        logger.warning(f"[StartupCheck] 第5次失败: {reason}")
        
        # ---- 第6次重试，清除后再试 ----
        logger.warning(f"[StartupCheck] 第5次失败: {reason}，再次清除保护...")
        _clear_and_retry()
        ok, measured_vout, reason = _do_check()
        if ok:
            logger.info(f"[StartupCheck] 第6次通过 | 实测 {measured_vout:.3f}V")
            return True, measured_vout, ""

        logger.warning(f"[StartupCheck] 第6次失败: {reason}")
        return False, measured_vout, reason

    def run(self, instruments: Dict[str, Any]) -> "TestCase":
        """
        运行完整测试流程。
        Returns:
            self（方便批量执行后收集结果）
        """
        try:
            self.setup(instruments)
            self.execute(instruments)
            passed = self.verify()
            self.result = TestResult.PASS if passed else TestResult.FAIL
        except Exception as e:
            self.result = TestResult.ERROR
            self.error_message = str(e)
        finally:
            self.teardown(instruments)
        return self

    @property
    def duration(self) -> float:
        """耗时（秒）"""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0.0

    def to_dict(self) -> dict:
        """导出结果为字典"""
        return {
            "name": self.name,
            "result": self.result.value,
            "measurements": self.measurements,
            "spec": self.spec,
            "duration_s": round(self.duration, 3),
            "error": self.error_message,
            "traceback": getattr(self, "traceback", ""),
            "sub_results": getattr(self, "sub_results", None),
        }


class TestSuite:
    """
    测试套件：管理多个 TestCase。
    """

    def __init__(self, name: str):
        self.name = name
        self.cases: List[TestCase] = []

    def add(self, case: TestCase):
        self.cases.append(case)

    def run(self, instruments: Dict[str, Any]) -> List[TestCase]:
        """
        顺序执行所有用例。
        Returns:
            结果列表
        """
        results = []
        for case in self.cases:
            case.run(instruments)
            results.append(case)
        return results

    def summary(self) -> dict:
        """汇总结果"""
        total = len(self.cases)
        passed = sum(1 for c in self.cases if c.result == TestResult.PASS)
        failed = sum(1 for c in self.cases if c.result == TestResult.FAIL)
        errors = sum(1 for c in self.cases if c.result == TestResult.ERROR)
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": f"{passed/total*100:.1f}%" if total else "0%",
        }
