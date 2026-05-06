# -*- coding: utf-8 -*-
"""
Configuration I/O — 配置文件序列化与反序列化

本模块只操作纯数据结构和 app 对象上的 UI 变量。
供 config_ui.ConfigUI 调用，实现配置逻辑与 UI 绑定的解耦。
"""
import json
import math
import os
import tkinter as tk

from config_schema import (
    SPECS_KEYS, DYN_ROW_FIELDS,
    _to_float, _safe_float,
    rows_to_dicts,
    build_specs_flat, build_protection_flat,
)


def save_config(app, path: str):
    """
    将 app 上的所有 UI 变量序列化并写入 JSON 文件。
    不处理异常，由调用方负责。
    """
    # ---- product_info 统一字典写 ----
    prod_info = {
        "product_name":           app._prod_name_var.get(),
        "product_type":          app._prod_type_vars.get("充电器") and "充电器" or "适配器",
        "input_voltage_lo":      _safe_float(app._input_voltage_lo_var.get()),
        "input_voltage_hi":      _safe_float(app._input_voltage_hi_var.get()),
        "output_voltage":        _safe_float(app._output_voltage_var.get()),
        "output_power":          _safe_float(app._output_power_var.get()),
        "power_segment":         bool(app._power_segment_var.get()),
        "hv_power":              _safe_float(app._hv_power_var.get()),
        "lv_power":              _safe_float(app._lv_power_var.get()),
        "load_startup_enabled":  bool(app._load_startup_var.get()),
        "load_startup_current":  _safe_float(app._load_startup_current_var.get()),
        "load_startup_voltage":  _safe_float(app._load_startup_voltage_var.get()),
        "specs_v2":              build_specs_flat(app._spec_vars, {}),
        "protection_logic_v2":   build_protection_flat(app._prot_vars, {}),
        "qc": {
            label: {"enabled": v["check"].get(), "value": v["entry"].get()}
            for label, v in app._qc_vars.items()
        },
        "pd": {
            label: {"enabled": v["check"].get(), "value": v["entry"].get()}
            for label, v in app._pd_vars.items()
        },
        "ufcs": {
            label: {"enabled": v["check"].get(), "value": v["entry"].get()}
            for label, v in app._ufcs_vars.items()
        },
    }

    test_params = {
        "osc_in_ch":      app._osc_in_ch_var.get().strip() or "CH4",
        "osc_in_attn":    _safe_float(app._osc_in_attn_var.get()),
        "osc_out_ch":     app._osc_out_ch_var.get().strip() or "CH2",
        "osc_out_attn":   _safe_float(app._osc_out_attn_var.get()),
        "pwr_in_v_ch":    app._pwr_in_v_ch_var.get().strip() or "CH1",
        "pwr_in_i_ch":    app._pwr_in_i_ch_var.get().strip() or "CH1",
        "pwr_out_v_ch":   app._pwr_out_v_ch_var.get().strip() or "CH1",
        "pwr_out_i_ch":   app._pwr_out_i_ch_var.get().strip() or "CH1",
        "eload_vout1_ch": app._eload_vout1_ch_var.get().strip() or "CH1",
        "eload_vout2_ch": app._eload_vout2_ch_var.get().strip() or "CH2",
        "dyn_large": rows_to_dicts(
            [app._dyn_large_tree.item(r)["values"] for r in app._dyn_large_tree.get_children()],
            DYN_ROW_FIELDS),
        "dyn_small": rows_to_dicts(
            [app._dyn_small_tree.item(r)["values"] for r in app._dyn_small_tree.get_children()],
            DYN_ROW_FIELDS),
        "warmup":      _safe_float(app._warmup_var.get()),
        "onoff_cycle": app._onoff_cycle_var.get(),
        "short_cycle": app._short_cycle_var.get(),
    }

    test_settings = {
        "osc_input_ch":    app._osc_in_ch_var.get().strip()   or "CH4",
        "osc_input_attn":  app._osc_in_attn_var.get().strip()  or "1.0",
        "osc_output_ch":   app._osc_out_ch_var.get().strip()  or "CH2",
        "osc_output_attn": app._osc_out_attn_var.get().strip() or "1.0",
        "osc_dynamic_ch":  app._osc_dyn_ch_var.get().strip()   or "CH2",
        "osc_dynamic_attn": app._osc_dyn_attn_var.get().strip() or "1.0",
    }

    # 全局测试条件：从 Treeview 逐行取出
    cond_rows = []
    for item in app._cond_tree.get_children():
        row = list(app._cond_tree.item(item)["values"])
        for idx in (1, 2, 4, 5):
            try:
                row[idx] = float(row[idx])
            except (ValueError, TypeError):
                pass
        cond_rows.append(row)

    cfg = {
        "_schema_version": "v2",
        "devices": {
            k: {
                "comm": app._comm_vars[k].get(),
                "addr": app._addr_vars[k].get(),
                "model": app._model_vars[k].get(),
            }
            for k in app.DEVICE_DEFS
        },
        "product_info": prod_info,
        "test_params": test_params,
        "test_settings": test_settings,
        "test_conditions_v2": rows_to_dicts(
            cond_rows, ["product_type", "vin", "freq", "proto", "vout", "iout"]),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

    app._last_config_path = path
    # 记录路径到自动加载文件
    last_path_file = os.path.join(os.path.dirname(__file__), ".last_config")
    with open(last_path_file, "w", encoding="utf-8") as f:
        f.write(path)


def load_config(app, path: str):
    """
    从 JSON 文件加载配置并写回到 app 上的 UI 变量。
    不弹对话框，由调用方负责异常提示。
    """
    from tkinter import messagebox

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 设备信息
    devs = cfg.get("devices", {})
    for k in app.DEVICE_DEFS:
        d = devs.get(k, {})
        app._comm_vars[k].set(d.get("comm", ""))
        app._addr_vars[k].set(d.get("addr", ""))
        app._model_vars[k].set(d.get("model", ""))

    # 产品信息
    pi = cfg.get("product_info", {})
    app._prod_name_var.set(pi.get("product_name", ""))
    app._input_voltage_lo_var.set(pi.get("input_voltage_lo", ""))
    app._input_voltage_hi_var.set(pi.get("input_voltage_hi", ""))
    app._output_voltage_var.set(pi.get("output_voltage", ""))
    app._output_power_var.set(pi.get("output_power", ""))
    app._power_segment_var.set(pi.get("power_segment", 0))
    app._hv_power_var.set(pi.get("hv_power", ""))
    app._lv_power_var.set(pi.get("lv_power", ""))
    from ui.pages._product_page import on_power_segment_toggle as _opst
    on_power_segment_toggle(app)   # 根据勾选状态刷新HV/LV读写框状态

    pt = pi.get("product_types", {})
    for label, var in app._prod_type_vars.items():
        var.set(pt.get(label, 0))

    app._load_startup_var.set(pi.get("load_startup_enabled", 0))
    app._load_startup_current_var.set(pi.get("load_startup_current", ""))
    app._load_startup_voltage_var.set(pi.get("load_startup_voltage", ""))

    # specs_v2: 扁平 float 字典
    specs_v2 = pi.get("specs_v2", {})
    for flat_key, label_text in SPECS_KEYS:
        v = app._spec_vars.get(label_text, {})
        if flat_key.endswith("_enable"):
            val = specs_v2.get(flat_key, 0)
            if "enable" in v:
                v["enable"].set(int(val) if not isinstance(val, float) and not isinstance(val, int) else int(val))
            continue
        lo_raw = specs_v2.get(f"{flat_key}_lo", None)
        hi_raw = specs_v2.get(f"{flat_key}_hi", None)
        if "lo" in v:
            v["lo"].set("" if (lo_raw is None or (isinstance(lo_raw, float) and math.isnan(lo_raw))) else str(lo_raw))
        if "hi" in v:
            v["hi"].set("" if (hi_raw is None or (isinstance(hi_raw, float) and math.isnan(hi_raw))) else str(hi_raw))

    # 产品类型：checkbutton式（保存的 string 转 IntVar）
    saved_type = pi.get("product_type", "")
    for label, var in app._prod_type_vars.items():
        var.set(1 if saved_type == label else 0)

    # protection_logic_v2: 扁平字典 {"保护名称_mode": "self"|"latch"}
    prot_v2 = pi.get("protection_logic_v2", {})
    for label, v in app._prot_vars.items():
        mode = prot_v2.get(f"{label}_mode", "")
        v["self"].set(1 if mode == "self" else 0)
        v["latch"].set(1 if mode == "latch" else 0)

    # 快充协议
    for proto_vars, proto_key in [
        (app._qc_vars,  "qc"),
        (app._pd_vars,  "pd"),
        (app._ufcs_vars, "ufcs"),
    ]:
        data = pi.get(proto_key, {})
        for label, v in proto_vars.items():
            d = data.get(label, {})
            v["check"].set(d.get("enabled", 0))
            v["entry"].set(d.get("value", ""))

    # 测试参数（示教通道优先，兼容旧格式）
    ts = cfg.get("test_settings", {})
    tp = cfg.get("test_params", {})
    app._osc_in_ch_var.set(ts.get("osc_input_ch", "CH4"))
    app._osc_in_attn_var.set(ts.get("osc_input_attn", "1.0"))
    app._osc_out_ch_var.set(ts.get("osc_output_ch", "CH2"))
    app._osc_out_attn_var.set(ts.get("osc_output_attn", "1.0"))
    app._osc_dyn_ch_var.set(ts.get("osc_dynamic_ch", "CH2"))
    app._osc_dyn_attn_var.set(ts.get("osc_dynamic_attn", "1.0"))
    app._pwr_in_v_ch_var.set(tp.get("pwr_in_v_ch", "CH1"))
    app._pwr_in_i_ch_var.set(tp.get("pwr_in_i_ch", "CH1"))
    app._pwr_out_v_ch_var.set(tp.get("pwr_out_v_ch", "CH1"))
    app._pwr_out_i_ch_var.set(tp.get("pwr_out_i_ch", "CH1"))
    app._eload_vout1_ch_var.set(tp.get("eload_vout1_ch", "CH1"))
    app._eload_vout2_ch_var.set(tp.get("eload_vout2_ch", "CH2"))

    # dyn_large/dyn_small
    app._dyn_large_tree.delete(*app._dyn_large_tree.get_children())
    for row in tp.get("dyn_large", []):
        if isinstance(row, dict):
            row = [row.get(f) for f in DYN_ROW_FIELDS]
        app._dyn_large_tree.insert("", "end", values=row)
    app._dyn_small_tree.delete(*app._dyn_small_tree.get_children())
    for row in tp.get("dyn_small", []):
        if isinstance(row, dict):
            row = [row.get(f) for f in DYN_ROW_FIELDS]
        app._dyn_small_tree.insert("", "end", values=row)

    app._warmup_var.set(tp.get("warmup", ""))
    app._onoff_cycle_var.set(tp.get("onoff_cycle", ""))
    app._short_cycle_var.set(tp.get("short_cycle", ""))

    # 恢复测试条件到 Treeview（恢复后触发刷新）
    tree = app._cond_tree
    tc_rows = cfg.get("test_conditions_v2", [])
    tree.delete(*tree.get_children())
    for idx, row in enumerate(tc_rows):
        tag = "odd" if idx % 2 == 0 else "even"
        vals = [row.get(f) for f in ["product_type", "vin", "freq", "proto", "vout", "iout"]]
        tree.insert("", "end", values=vals, tags=(tag,))

    # 恢复 _source_conditions（v2 dict 转回行元组）
    app._source_conditions = []
    for row in tc_rows:
        try:
            vin  = _to_float(row.get("vin"), 0)
            freq = _to_float(row.get("freq"), 60.0)
            proto = str(row.get("proto", "—")) or "—"
            vout = _to_float(row.get("vout"), None)
            iout = _to_float(row.get("iout"), None)
            raw_pt = str(row.get("product_type", "charger")) or "charger"
            ptype = "charger" if raw_pt in ("充电器", "charger") else "adapter"
            app._source_conditions.append((vin, freq, proto, vout, iout, ptype))
        except (ValueError, TypeError, IndexError):
            pass

    # 重新计算筛选条件并刷新树显示
    app._apply_filtered_conditions(refresh_all=True, update_tree=True)
    app._last_config_path = path
