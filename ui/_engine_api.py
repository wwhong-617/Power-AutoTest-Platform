# -*- coding: utf-8 -*-
"""
测试执行引擎 API - ConfigUI 的执行逻辑封装
继承此类以获得测试运行能力
"""
import os
import time
import traceback
import threading


class EngineAPI:
    """
    提供 test_engine 相关的执行逻辑。
    使用方式：class ConfigUI(EngineAPI):
        ...

    子类需要提供以下 self 属性：
        _osc_in_ch_var, _osc_out_ch_var, _osc_dyn_ch_var
        _osc_in_attn_var, _osc_out_attn_var, _osc_dyn_attn_var
        _pwr_in_v_ch_var, _pwr_in_i_ch_var, _pwr_out_v_ch_var, _pwr_out_i_ch_var
        _eload_vout1_ch_var, _eload_vout2_ch_var
        _dyn_large_tree, _dyn_small_tree
        _warmup_var, _onoff_cycle_var, _short_cycle_var
        _load_startup_var, _load_startup_current_var, _load_startup_voltage_var
        _power_segment_var, _hv_power_var, _lv_power_var
        _spec_vars, _prot_vars
        _prod_name_var, _input_voltage_lo_var, _input_voltage_hi_var
        _output_voltage_var, _output_power_var
        _prod_type_vars, _filtered_conditions
        _test_case_defs, _case_cn_to_en, _case_vars
        _instrument_manager, _instruments
        _engine, _test_thread
        _btn_run, _btn_pause, _btn_stop
        _case_progress, _case_progress_label
        _append_run_log(msg), _after(func)
        root
    """

    # ---------------------- 配置构建 ----------------------

    def _build_test_engine_config(self, checked_cases):
        """
        构建 TestEngine 所需的完整配置字典。

        checked_cases: 中文 case 名称列表（来自 _case_vars checkbox 勾选结果）
        """
        from collections import defaultdict
        from config_schema import build_specs_flat, build_protection_flat, DYN_ROW_FIELDS
        from test_engine import TestEngine

        # ---- 产品信息 ----
        prod_name = self._prod_name_var.get().strip() or "Unknown"
        input_lo  = float(self._input_voltage_lo_var.get() or 90.0)
        input_hi  = float(self._input_voltage_hi_var.get() or 264.0)
        output_voltage = float(self._output_voltage_var.get() or 12.0)
        output_power  = float(self._output_power_var.get() or 65.0)
        is_charger = bool(self._prod_type_vars.get("充电器", None) and
                          self._prod_type_vars["充电器"].get() == 1)
        product_type = "charger" if is_charger else "adapter"

        # ---- 构建 test_cases_config：{category: {case_key: True}} ----
        category_map = {
            "输入测试": "input_tests",
            "输出测试": "output_tests",
            "保护测试": "protection_tests",
            "协议测试": "protocol_tests",
        }
        test_cases_config = {}
        for cn in checked_cases:
            eng_key = self._case_cn_to_en.get(cn, "")
            if not eng_key:
                continue
            cat = None
            for ui_cat, cases in self._test_case_defs.items():
                if cn in cases:
                    cat = category_map.get(ui_cat)
                    break
            if cat and eng_key:
                test_cases_config.setdefault(cat, {})[eng_key] = True

        # ---- 构建 test_conditions ----
        test_conditions = []
        filtered_count = 0
        for cn in checked_cases:
            en_key = self._case_cn_to_en.get(cn, cn)
            rows = self._filtered_conditions.get(en_key, []) or self._filtered_conditions.get(cn, [])
            if TestEngine.CASE_REGISTRY.get(en_key, {}).get("voltage_segment"):
                groups = defaultdict(list)
                for row in rows:
                    if not all(k in row for k in ("vin", "freq", "proto", "vout", "iout")):
                        continue
                    key = (str(row["proto"]), str(row["vout"]), str(row["iout"]))
                    groups[key].append(row)
                for key, grp in groups.items():
                    best = max(grp, key=lambda r: float(r["vin"]) if r["vin"] else 0)
                    test_conditions.append(best)
                    filtered_count += 1
            else:
                test_conditions.extend(rows)

        if filtered_count > 0:
            self._filter_note = f"（{filtered_count} 个输出组合已过滤为最高输入电压条件）"
        else:
            self._filter_note = ""

        # ---- 测试参数 ----
        test_settings = {
            "osc_input_ch":    self._osc_in_ch_var.get().strip()   or "CH4",
            "osc_input_attn":  float(self._osc_in_attn_var.get().strip()   or 1.0),
            "osc_output_ch":   self._osc_out_ch_var.get().strip()  or "CH2",
            "osc_output_attn": float(self._osc_out_attn_var.get().strip()  or 1.0),
            "osc_dynamic_ch":  self._osc_dyn_ch_var.get().strip()   or "CH2",
            "osc_dynamic_attn": float(self._osc_dyn_attn_var.get().strip() or 1.0),
        }
        test_params = {
            "pwr_in_v_ch":  self._pwr_in_v_ch_var.get().strip() or "CH1",
            "pwr_in_i_ch":  self._pwr_in_i_ch_var.get().strip() or "CH1",
            "pwr_out_v_ch": self._pwr_out_v_ch_var.get().strip() or "CH1",
            "pwr_out_i_ch": self._pwr_out_i_ch_var.get().strip() or "CH1",
            "eload_vout1_ch": self._eload_vout1_ch_var.get().strip() or "CH1",
            "eload_vout2_ch": self._eload_vout2_ch_var.get().strip() or "CH2",
            "dyn_large":    [self._dyn_large_tree.item(r)["values"]
                             for r in self._dyn_large_tree.get_children()],
            "dyn_small":    [self._dyn_small_tree.item(r)["values"]
                             for r in self._dyn_small_tree.get_children()],
            "warmup":      self._warmup_var.get(),
            "onoff_cycle": self._onoff_cycle_var.get(),
            "short_cycle": self._short_cycle_var.get(),
        }

        return {
            "product_info": {
                "product_name": prod_name,
                "input_voltage_lo": input_lo,
                "input_voltage_hi": input_hi,
                "output_voltage": output_voltage,
                "output_power": output_power,
                "product_type": product_type,
                "load_startup_enabled": self._load_startup_var.get(),
                "load_startup_current": self._load_startup_current_var.get(),
                "load_startup_voltage": self._load_startup_voltage_var.get(),
                "power_segment": self._power_segment_var.get(),
                "hv_power": self._hv_power_var.get(),
                "lv_power": self._lv_power_var.get(),
                "specs_v2": build_specs_flat(self._spec_vars, {}),
                "protection_logic_v2": build_protection_flat(self._prot_vars, {}),
            },
            "dut": {
                "name": prod_name,
                "output_voltage": output_voltage,
                "output_power": output_power,
                "input_voltage_min": input_lo,
                "input_voltage_max": input_hi,
            },
            "adapter": {
                "output_voltage": output_voltage,
                "input_voltage_min": input_lo,
                "input_voltage_max": input_hi,
            },
            "test_conditions": test_conditions,
            "filtered_conditions_v2": self._filtered_conditions,
            "test_settings": test_settings,
            "test_params": test_params,
            "test_cases": test_cases_config,
        }

    # ---------------------- 测试执行 ----------------------

    def _run_tests(self):
        """启动测试执行（后台线程）"""
        from tkinter import messagebox
        checked = [name for name, var in self._case_vars.items() if var.get()]
        if not checked:
            messagebox.showwarning("提示", "请先在左侧勾选要运行的测试用例")
            return
        if not self._instruments:
            messagebox.showwarning("提示", "请先在【仪器连接】页面连接设备")
            return

        self._append_run_log("[%s] 开始运行 %d 个用例：%s\n" % (
            time.strftime("%H:%M:%S"), len(checked), ", ".join(checked)))
        self._btn_run.config(state="disabled")
        self._btn_pause.config(state="normal")
        self._btn_stop.config(state="normal")
        self._case_progress.config(mode="determinate")
        self._case_progress["value"] = 0
        self._case_progress_label.config(text="0 / %d" % len(checked))

        # 确保所有勾选用例的条件已填充
        self._apply_filtered_conditions(refresh_all=True, update_tree=False)

        cfg = self._build_test_engine_config(checked)
        self._last_test_config = cfg

        # 补救：OSC 通道配置
        osc = self._instruments.get("OSC")
        if osc:
            osc._osc_ch_config = {
                "osc_input_ch":    self._osc_in_ch_var.get().strip()   or "CH4",
                "osc_output_ch":   self._osc_out_ch_var.get().strip()  or "CH2",
                "osc_dynamic_ch":  self._osc_dyn_ch_var.get().strip()   or "CH1",
                "osc_input_attn":  float(self._osc_in_attn_var.get().strip()  or "1.0"),
                "osc_output_attn": float(self._osc_out_attn_var.get().strip() or "1.0"),
                "osc_dynamic_attn": float(self._osc_dyn_attn_var.get().strip() or "1.0"),
            }
            osc.initialize()

        from test_engine import TestEngine
        self._engine = TestEngine(cfg, self._instruments, instrument_manager=self._instrument_manager)

        import datetime
        prod_name = cfg.get("product_info", {}).get("product_name", "Unknown")
        result_dir = os.path.join(
            os.path.dirname(__file__),
            "results",
            datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + prod_name
        )
        os.makedirs(result_dir, exist_ok=True)
        self._engine.set_result_dir(result_dir)
        self._append_run_log(f"[结果目录] {result_dir}\n")

        # 进度回调
        def on_progress(case_name, result, idx, total, case=None):
            pct = int(idx / total * 100)
            self._case_progress["value"] = pct
            self._case_progress_label.config(text="%d / %d" % (idx, total))
            line = f"  -> [{idx}/{total}] {case_name}: {result}"
            dur = 0.0
            meas = {}
            params = {}
            if case is not None:
                try:
                    dur = getattr(case, "duration", 0.0) or 0.0
                    meas = getattr(case, "measurements", {}) or {}
                    params = getattr(case, "params", {}) or {}
                except Exception:
                    pass
            extra = ""
            if meas:
                items = [f"{k}={v:.4g}" for k, v in list(meas.items())[:3]]
                extra = " " + " ".join(items)
            self._append_run_log(f"{line}{extra}\n")

        def on_log(level, msg):
            self._append_run_log(f"[{level}] {msg}\n")

        self._engine.set_progress_callback(on_progress)
        self._engine.set_log_callback(on_log)

        cfg_cases = cfg.get("test_cases", {})
        self._engine.load_cases_from_config(cfg_cases)

        self._test_thread = threading.Thread(target=self._run_tests_thread, daemon=True)
        self._test_thread.start()

    def _run_tests_thread(self):
        try:
            results = self._engine.run_all()
            summary = self._engine.get_summary()
            self._after(lambda: self._on_tests_finished(summary))
        except Exception as e:
            self._append_run_log(f"[ERROR] 测试执行异常: {e}\n")
            traceback.print_exc()
            self._after(lambda: self._on_tests_finished(None))

    def _on_tests_finished(self, summary):
        import datetime, json
        if summary:
            self._append_run_log(
                "\n[%s] 全部完成！ "
                "通过 %d / %d (%.1f%%)\n" % (
                    time.strftime("%H:%M:%S"),
                    summary["passed"],
                    summary["total"],
                    float(summary["pass_rate"].replace("%", ""))
                )
            )
            try:
                result_dir = self._engine._result_dir
                prod_name = self._prod_name_var.get().strip() or "Unknown"
                json_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + prod_name + ".json"
                json_path = os.path.join(result_dir, json_name)
                self._engine.export_results(json_path)
                self._append_run_log(f"[JSON已保存] {json_path}\n")

                try:
                    from report_generator import generate_excel
                    dut_name = self._prod_name_var.get().strip() or "DUT"
                    xlsx_path = generate_excel(json_path, result_dir, dut_name)
                    self._append_run_log(f"[Excel报告已生成] {xlsx_path}\n")
                except Exception as e2:
                    self._append_run_log(f"[ERROR] 生成Excel报告失败: {e2}\n")
            except Exception as e:
                self._append_run_log(f"[ERROR] 保存结果失败: {e}\n")
        else:
            self._append_run_log("\n[%s] 测试已停止\n" % time.strftime("%H:%M:%S"))

        self._case_progress["value"] = 100
        self._btn_run.config(state="normal")
        self._btn_pause.config(state="disabled")
        self._btn_stop.config(state="disabled")
        self._test_thread = None

    def _pause_tests(self):
        if self._engine and self._engine.state.value in ("RUNNING", "PAUSED"):
            if self._engine.state.value == "RUNNING":
                self._engine.pause()
                self._append_run_log(f"[{time.strftime('%H:%M:%S')}] 测试已暂停\n")
                self._btn_run.config(state="normal")
                self._btn_pause.config(state="disabled")
            else:
                self._engine.resume()
                self._append_run_log(f"[{time.strftime('%H:%M:%S')}] 测试已恢复\n")
                self._btn_run.config(state="disabled")
                self._btn_pause.config(state="normal")

    def _stop_tests(self):
        if self._engine:
            self._engine.stop()
            self._append_run_log(f"[{time.strftime('%H:%M:%S')}] 停止请求已发送\n")

    def _export_partial_results(self):
        if not self._engine:
            return
        try:
            import datetime
            result_dir = self._engine._result_dir
            prod_name = self._prod_name_var.get().strip() or "Unknown"
            path = os.path.join(result_dir, datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + prod_name + "_partial.json")
            self._engine.export_results(path)
            self._append_run_log(f"[部分结果已导出] {path}\n")
        except Exception as e:
            self._append_run_log(f"[ERROR] 导出失败: {e}\n")
