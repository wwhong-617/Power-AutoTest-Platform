# -*- coding: utf-8 -*-
"""
Configuration I/O — 配置文件序列化与反序列化

本模块只操作纯数据结构和 app 对象上的 UI 变量。
供 config_ui.ConfigUI 调用，实现配置逻辑与 UI 绑定的解耦。
"""
import json
import math
import os
from typing import List

# 项目根目录（兼容 config_ui.py 和 ui/ 子目录两种运行场景）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import tkinter as tk

from config_schema import (
    DEVICE_DEFS,
    SPECS_KEYS, DYN_ROW_FIELDS,
    _to_float, _safe_float,
    rows_to_dicts,
    build_specs_flat, build_protection_flat,
)


def _to_float(val):
    """
    将字符串转为 float，失败返回 None（区别于 _safe_float 的 0.0）。
    """
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def validate_config(app) -> List[str]:
    """
    保存前校验 UI 配置，返回错误信息列表。
    空列表 = 校验通过。
    """
    errors = []

    # ---- 输入电压范围：lo < hi ----
    lo = _to_float(app._input_voltage_lo_var.get())
    hi = _to_float(app._input_voltage_hi_var.get())
    if lo is not None and hi is not None and lo >= hi:
        errors.append("输入电压范围：最小值必须小于最大值")
    elif lo is None and app._input_voltage_lo_var.get().strip() != "":
        errors.append("输入电压范围-最小值：无效数值")
    elif hi is None and app._input_voltage_hi_var.get().strip() != "":
        errors.append("输入电压范围-最大值：无效数值")

    # ---- 输出电压范围：min < max ----
    vmin = _to_float(app._output_voltage_min_var.get())
    vmax = _to_float(app._output_voltage_max_var.get())
    if vmin is not None and vmax is not None and vmin >= vmax:
        errors.append("输出电压范围：最小值必须小于最大值")
    elif vmin is None and app._output_voltage_min_var.get().strip() != "":
        errors.append("输出电压范围-最小值：无效数值")
    elif vmax is None and app._output_voltage_max_var.get().strip() != "":
        errors.append("输出电压范围-最大值：无效数值")

    # ---- 产品规格要求 ----
    validate_specs(app, errors)

    return errors


def validate_specs(app, errors: list):
    """
    校验产品规格要求中的 lo/hi 数值。
    - 百分比项(lo/hi在0~100之间)
    - 非负项(lo/hi ≥ 0)
    - lo < hi(两者均填写时)
    """
    PCT_LABELS = {
        "开关机过冲（%）",
    }
    PCT_NEG_LABELS = {
        "电压精度（%）",
        "大动态负载范围（%）",
        "小动态负载范围（%）",
    }
    OCP_PCT_LABELS = {
        "输出过流点（%）",
    }

    for label_text, var_dict in app._spec_vars.items():
        lo_var = var_dict.get("lo")
        hi_var = var_dict.get("hi")
        if lo_var is None or hi_var is None:
            continue

        lo_raw = lo_var.get().strip()
        hi_raw = hi_var.get().strip()
        lo = _to_float(lo_raw)
        hi = _to_float(hi_raw)

        # 两者都为空 → 跳过
        if lo is None and hi is None:
            continue

        is_pct = label_text in PCT_LABELS
        is_pct_neg = label_text in PCT_NEG_LABELS
        is_ocp_pct = label_text in OCP_PCT_LABELS

        # lo 非空但无效
        if lo is None and lo_raw != "":
            errors.append(f"规格要求「{label_text}」下限：无效数值")
            lo = None  # 避免下面 lo >= hi 误报

        # hi 非空但无效
        if hi is None and hi_raw != "":
            errors.append(f"规格要求「{label_text}」上限：无效数值")
            hi = None

        # 百分比范围校验（0~100）
        if is_pct:
            if lo is not None and (lo < 0 or lo > 100):
                errors.append(f"规格要求「{label_text}」下限：有效范围0~100")
            if hi is not None and (hi < 0 or hi > 100):
                errors.append(f"规格要求「{label_text}」上限：有效范围0~100")

        # 百分比范围校验（-100~100）
        if is_pct_neg:
            if lo is not None and (lo < -100 or lo > 100):
                errors.append(f"规格要求「{label_text}」下限：有效范围-100~100")
            if hi is not None and (hi < -100 or hi > 100):
                errors.append(f"规格要求「{label_text}」上限：有效范围-100~100")

        # 输出过流点（100~200）
        elif is_ocp_pct:
            if lo is not None and (lo < 100 or lo > 200):
                errors.append(f"规格要求「{label_text}」下限：有效范围100~200")
            if hi is not None and (hi < 100 or hi > 200):
                errors.append(f"规格要求「{label_text}」上限：有效范围100~200")
        else:
            # 非负校验
            if lo is not None and lo < 0:
                errors.append(f"规格要求「{label_text}」下限：不能为负数")
            if hi is not None and hi < 0:
                errors.append(f"规格要求「{label_text}」上限：不能为负数")

        # lo < hi 校验（两者都有效才校验）
        if lo is not None and hi is not None and lo >= hi:
            errors.append(f"规格要求「{label_text}」：上限必须大于下限")


def save_config(app, path: str):
    """
    将 app 上的所有 UI 变量序列化并写入 JSON 文件。
    不处理异常，由调用方负责。
    """
    # ---- product_info 统一字典写 ----
    prod_info = {
        "product_name":           app._prod_name_var.get(),
        "product_type":          "充电器" if app._prod_type_vars.get("充电器", tk.IntVar()).get() == 1 else "适配器",
        "input_voltage_min":      _safe_float(app._input_voltage_lo_var.get()),
        "input_voltage_max":      _safe_float(app._input_voltage_hi_var.get()),
        "output_voltage_min":   _safe_float(app._output_voltage_min_var.get()),
        "output_voltage_max":   _safe_float(app._output_voltage_max_var.get()),
        "output_power":          _safe_float(app._output_power_var.get()),
        "power_segment":         bool(app._power_segment_var.get()),
        "hv_power":              _safe_float(app._hv_power_var.get()),
        "lv_power":              _safe_float(app._lv_power_var.get()),
        "load_startup_enabled":  bool(app._load_startup_var.get()),
        "load_startup_current":  _safe_float(app._load_startup_current_var.get()),
        "load_startup_voltage":  _safe_float(app._load_startup_voltage_var.get()),
        "ultra_light_power":     _safe_float(app._ultra_light_power_var.get()),
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
            for k in DEVICE_DEFS
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
    # 记录路径到自动加载文件（写入项目根目录，与 _try_load_last_config 读取位置一致）
    last_path_file = os.path.join(_PROJECT_ROOT, ".last_config")
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
    for k in DEVICE_DEFS:
        d = devs.get(k, {})
        app._comm_vars[k].set(d.get("comm", ""))
        app._addr_vars[k].set(d.get("addr", ""))
        app._model_vars[k].set(d.get("model", ""))

    # 产品信息
    pi = cfg.get("product_info", {})
    app._prod_name_var.set(pi.get("product_name", ""))
    app._input_voltage_lo_var.set(pi.get("input_voltage_min", ""))
    app._input_voltage_hi_var.set(pi.get("input_voltage_max", ""))
    # 输出电压：双字段，兼容旧配置只有单一 output_voltage
    app._output_voltage_min_var.set(pi.get("output_voltage_min", ""))
    app._output_voltage_max_var.set(
        pi.get("output_voltage_max", "") or pi.get("output_voltage", "")
    )
    app._output_power_var.set(pi.get("output_power", ""))
    app._power_segment_var.set(pi.get("power_segment", 0))
    app._hv_power_var.set(pi.get("hv_power", ""))
    app._lv_power_var.set(pi.get("lv_power", ""))
    from ui.pages._product_page import on_power_segment_toggle
    on_power_segment_toggle(app)   # 根据勾选状态刷新HV/LV读写框状态

    pt = pi.get("product_types", {})
    for label, var in app._prod_type_vars.items():
        var.set(pt.get(label, 0))

    app._load_startup_var.set(pi.get("load_startup_enabled", 0))
    app._load_startup_current_var.set(pi.get("load_startup_current", ""))
    app._load_startup_voltage_var.set(pi.get("load_startup_voltage", ""))
    app._ultra_light_power_var.set(pi.get("ultra_light_power", ""))

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

    # 恢复 _source_conditions（dict 列表，与 UI 展示树同步）
    app._source_conditions = []
    for row in tc_rows:
        try:
            # JSON 数据已是 float，直接转换
            vin  = float(row.get("vin", 0))
            freq = float(row.get("freq", 60))
            proto = str(row.get("proto", "") or "")
            vout_raw = row.get("vout")
            vout = float(vout_raw) if vout_raw is not None else None
            iout_raw = row.get("iout")
            iout = float(iout_raw) if iout_raw is not None else None
            raw_pt = str(row.get("product_type", "charger")) or "charger"
            ptype = "charger" if raw_pt in ("充电器", "charger") else "adapter"
            app._source_conditions.append({"vin": vin, "freq": freq, "proto": proto, "vout": vout, "iout": iout, "product_type": ptype})
        except (ValueError, TypeError, IndexError):
            pass


    # 重新计算筛选条件并刷新树显示
    app._apply_filtered_conditions(refresh_all=True, update_tree=True)
    app._last_config_path = path
    # 同步更新 .last_config（写入项目根目录）
    last_path_file = os.path.join(_PROJECT_ROOT, ".last_config")
    with open(last_path_file, "w", encoding="utf-8") as f:
        f.write(path)
