# -*- coding: utf-8 -*-
import math

"""
config_schema.py - 配置数据结构规范
===================================

定义配置文件的统一数据结构，所有读写统一按此规范。
新增/修改字段必须遵守本规范。

类型约定：
  float   → Python float（或自动转换的数值字符串）
  int     → Python int
  str     → Python str
  bool    → Python bool（JSON 中为 true/false）
  list    → Python list
  dict    → Python dict

Schema 版本：v2（2026-04-28）
- specs 从 {"名称": {"lo": str, "hi": str}} 改为 flat dict + 类型后缀
- dyn_large/dyn_small 从 [[values...]] 改为 [{dict}]
- test_conditions 从 [(row)] 改为 [{dict}]
"""

# =====================================================================
# product_info
# =====================================================================
PRODUCT_INFO_FIELDS = {
    # 基础信息
    "product_name":          str,
    "product_type":          str,   # "charger" | "adapter"
    "input_voltage_lo":      float,
    "input_voltage_hi":      float,
    "output_voltage":        float,
    "output_power":          float,
    # 功率分段
    "power_segment":         bool,
    "hv_power":             float,
    "lv_power":             float,
    # 带载开机
    "load_startup_enabled":  bool,
    "load_startup_current":  float,
    "load_startup_voltage":  float,
}

# =====================================================================
# specs - 扁平字典，key 加单位后缀避免歧义
# =====================================================================
# 所有规格值均为 float，不再有字符串
# key 格式："名称_单位"
SPECS_KEYS = [
    # 能效级别 enable 标识，无数值
    ("6级能效要求_pct_enable", "6级能效要求（%）"),
    ("7级能效要求_pct_enable", "7级能效要求（%）"),
    # 通用规格
    ("电压精度_pct",        "电压精度（%）"),
    ("大动态负载范围_pct",   "大动态负载范围（%）"),
    ("小动态负载范围_pct",   "小动态负载范围（%）"),
    ("开关机过冲_pct",       "开关机过冲（%）"),
    ("空载功耗_W",          "空载功耗（W）"),
    ("待机功耗_W",          "待机功耗（W）"),
    ("Brown_in_V",          "Brown-in（V）"),
    ("Brown_out_V",         "Brown-out（V）"),
    ("输出过压点_V",         "输出过压点（V）"),
    ("输出欠压点_V",         "输出欠压点（V）"),
    ("输出过流点_pct",       "输出过流点（%）"),
    ("纹波要求_mV",         "纹波要求（mV）"),
]

# =====================================================================
# protection_logic - 扁平字典
# =====================================================================
PROTECTION_LOGIC_FIELDS = [
    # (flat_key, ui_label)
    ("输入欠压保护_mode",    "输入欠压保护"),
    ("输出过压保护_mode",    "输出过压保护"),
    ("输出过流保护_mode",    "输出过流保护"),
]
# mode 值："self" | "latch"

# =====================================================================
# test_params
# =====================================================================
TEST_PARAMS_FIELDS = {
    # 示波器通道
    "osc_input_ch":      str,   # "CH4"
    "osc_input_attn":    float,
    "osc_output_ch":     str,   # "CH2"
    "osc_output_attn":   float,
    "osc_dynamic_ch":    str,
    "osc_dynamic_attn":  float,
    # 功率计通道
    "pwr_in_v_ch":       str,
    "pwr_in_i_ch":       str,
    "pwr_out_v_ch":      str,
    "pwr_out_i_ch":      str,
    # 电子负载通道
    "eload_vout1_ch":    str,
    "eload_vout2_ch":    str,
    # 动态测试（list of dict）
    "dyn_large":         list,  # [{up_pct, up_slew, down_pct, down_slew, freq, ratio}, ...]
    "dyn_small":         list,  # 同上
    # 时间参数
    "warmup":            float,
    "onoff_cycle":       str,   # "10-10" 格式：开X秒-关X秒
    "short_cycle":       str,   # "10-10" 格式：短路X秒-断路X秒
}

# dyn_large / dyn_small 列表中每条记录的字段
DYN_ROW_FIELDS = [
    "up_pct",    # UP(%)       float
    "up_slew",   # UP斜率(A/us) float
    "down_pct",  # DOWN(%)     float
    "down_slew", # DOWN斜率(A/us) float
    "freq",      # 频率(Hz)    float
    "ratio",     # 比例(%)     float
]
DYN_COLS = ["UP(%)", "UP斜率(A/us)", "DOWN(%)", "DOWN斜率(A/us)", "频率(Hz)", "比例(%)"]

# =====================================================================
# test_conditions / filtered_conditions
# =====================================================================
COND_FIELDS = [
    "vin",           # 输入电压 float
    "freq",          # 频率   float
    "proto",         # 协议   str
    "vout",          # 输出电压 float
    "iout",          # 输出电流 float
    "product_type",  # 产品类型 str
]

# =====================================================================
# 工具函数
# =====================================================================


def _to_float(val, default=None):
    """将值转为 float，失败返回 default。空字符串 → NaN（区分"未配置"和"配置为0"）。"""
    if val is None or val == "":
        return math.nan
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _to_int(val, default=None):
    """将值转为 int，失败返回 default。"""
    if val is None or val == "":
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_float(val):
    """安全转 float，空/无效返回 0.0（与 _to_float 的 NaN 语义不同）。"""
    if val is None or val == "":
        return 0.0
    return _to_float(val, 0.0)


def rows_to_dicts(rows, fields):
    """
    将 [[val, ...]] 列表转换为 [{field: val}, ...] 列表。
    rows: list of list
    fields: list of str
    """
    result = []
    for row in rows:
        d = {}
        for i, field in enumerate(fields):
            if i < len(row):
                d[field] = row[i]
            else:
                d[field] = None
        result.append(d)
    return result


def dicts_to_rows(dicts, fields):
    """
    将 [{field: val}, ...] 列表转换回 [[val, ...]] 列表（用于 UI 树控件）。
    """
    result = []
    for d in dicts:
        row = [d.get(f) for f in fields]
        result.append(row)
    return result


def build_specs_flat(spec_vars, specs_raw):
    """
    将 UI 的 spec_vars（中文 key）转换为扁平 float 字典。
    spec_vars: {label_text: {"lo": StringVar, "hi": StringVar, "enable": IntVar}}
    specs_raw:  加载配置时的原始 specs 字典（仅用于旧配置降级读取）
    返回: {flat_key: float_value, ...}

    特殊逻辑：
    - "_enable" 后缀：仅保存 enable 标志（能效勾选规格）
    - NaN：用 math.nan 标记"未配置"，区分"配置为0"
    """
    out = {}
    for flat_key, label_text in SPECS_KEYS:
        v = spec_vars.get(label_text, {})

        # ---- enable-only 规格（如 6级/7级能效）----
        if flat_key.endswith("_enable"):
            enable_var = v.get("enable")
            if enable_var is not None:
                out[flat_key] = float(enable_var.get())
            continue

        # ---- 普通 lo/hi 规格 ----
        lo_raw = v["lo"].get() if "lo" in v else None
        hi_raw = v["hi"].get() if "hi" in v else None
        lo_val = _to_float(lo_raw, math.nan)
        hi_val = _to_float(hi_raw, math.nan)

        # 降级：从 specs_raw 读取（覆盖 NaN）
        if (math.isnan(lo_val) or math.isnan(hi_val)) and label_text in specs_raw:
            raw = specs_raw[label_text]
            if math.isnan(lo_val):
                lo_val = _to_float(raw.get("lo"), math.nan)
            if math.isnan(hi_val):
                hi_val = _to_float(raw.get("hi"), math.nan)

        # 只有非 NaN 值才写入（区分"未配置"和"配置为0"）
        if not math.isnan(lo_val):
            out[f"{flat_key}_lo"] = lo_val
        if not math.isnan(hi_val):
            out[f"{flat_key}_hi"] = hi_val

    return out


def build_protection_flat(prot_vars, prot_raw):
    """
    将保护逻辑转为扁平字典。
    prot_vars: {label_text: {"self": IntVar, "latch": IntVar}}
    prot_raw:  加载配置时的原始 protection_logic 字典
    返回: {flat_key: "self"|"latch"|"", ...}
    """
    out = {}
    for flat_key, label_text in PROTECTION_LOGIC_FIELDS:
        v = prot_vars.get(label_text, {})
        # 优先从 Tk 变量读当前 UI 值
        if "self" in v and v["self"].get():
            out[flat_key] = "self"
        elif "latch" in v and v["latch"].get():
            out[flat_key] = "latch"
        else:
            # 降级：从 prot_raw（已加载的旧配置）读取
            if label_text in prot_raw:
                raw = prot_raw[label_text]
                if raw.get("self"):
                    out[flat_key] = "self"
                elif raw.get("latch"):
                    out[flat_key] = "latch"
                else:
                    out[flat_key] = ""
            else:
                out[flat_key] = ""
    return out
