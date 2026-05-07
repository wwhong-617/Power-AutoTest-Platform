# -*- coding: utf-8 -*-
"""
测试条件过滤纯函数（无 UI 依赖，可独立测试）

过滤策略通过 CASE_REGISTRY[case_key]["filter_mode"] 声明式配置，
代码不再硬编码 case_key 字符串。
"""

from collections import defaultdict


# ============================================================
# 行 <-> dict 转换
# ============================================================

def row_to_dict(row):
    """将条件行转为 dict。输入可以是 (tuple) 或 (dict)"""
    if isinstance(row, dict):
        return row
    # tuple/list: (vin, freq, proto, vout, iout, product_type)
    try:
        return {
            "vin":   row[0] if len(row) > 0 else None,
            "freq":  row[1] if len(row) > 1 else None,
            "proto": row[2] if len(row) > 2 else "",
            "vout":  row[3] if len(row) > 3 else None,
            "iout":  row[4] if len(row) > 4 else None,
            "product_type": row[5] if len(row) > 5 else "",
        }
    except (IndexError, KeyError):
        return {}


# ============================================================
# 内部策略实现（无 UI 依赖，纯函数）
# ============================================================

def _filter_min_vin(all_conditions):
    """
    filter_mode="min_vin"：取每 (proto,vout,iout) 分组内 Vin 最低的那条。
    若多条 Vin 相同，取 vout 最高。
    """
    if not all_conditions:
        return all_conditions
    rows_as_dicts = [row_to_dict(r) for r in all_conditions]
    min_vin = min(r["vin"] for r in rows_as_dicts if r.get("vin") is not None)
    min_vin_rows = [r for r in rows_as_dicts if r.get("vin") is not None
                    and abs(r["vin"] - min_vin) < 0.01]
    best_row = max(min_vin_rows,
                   key=lambda r: float(r["vout"]) if r.get("vout") is not None else 0)
    return [best_row]


def _filter_min_vout(all_conditions):
    """
    filter_mode="min_vout"：取 vout 最低的那条，返回所有 vout 与之一致的条件。
    """
    if not all_conditions:
        return all_conditions
    rows_as_dicts = [row_to_dict(r) for r in all_conditions]
    min_vout = min(r["vout"] for r in rows_as_dicts if r.get("vout") is not None)
    return [r for r in rows_as_dicts
            if r.get("vout") is not None and abs(r["vout"] - min_vout) < 0.01]


def _filter_voltage_segment(all_conditions):
    """
    filter_mode="voltage_segment"：按 (proto,vout,iout) 分组，每组取 Vin 最高的那条。
    """
    if not all_conditions:
        return all_conditions
    groups = defaultdict(list)
    for row in all_conditions:
        d = row_to_dict(row)
        if not all(d.get(k) for k in ("vin", "freq", "proto", "vout", "iout")):
            continue
        key = (str(d["proto"]), str(d["vout"]), str(d["iout"]))
        groups[key].append(d)
    result = []
    for rows in groups.values():
        best = max(rows, key=lambda r: float(r["vin"]) if r.get("vin") else 0)
        result.append(best)
    return result


def _filter_passthrough(all_conditions):
    """filter_mode="passthrough"：全量转 dict。"""
    return [row_to_dict(r) for r in all_conditions]


# ============================================================
# 主入口（策略分发）
# ============================================================

def filter_conditions_by_case(case_key, all_conditions, case_registry):
    """
    根据 CASE_REGISTRY[case_key]["filter_mode"] 路由到对应策略函数。

    支持的 filter_mode：
        passthrough     - 全量转 dict（默认）
        min_vin         - 每组取 Vin 最低
        min_vout        - 取 vout 最低的多条
        voltage_segment - 每组取 Vin 最高

    Args:
        case_key:       英文用例名，如 "InputVoltageRangeTest"
        all_conditions: List[dict] 或 List[tuple]，全量条件
        case_registry:  CASE_REGISTRY（dict）

    Returns:
        List[dict] - 过滤/转换后的条件列表
    """
    mode = case_registry.get(case_key, {}).get("filter_mode", "passthrough")

    if mode == "min_vin":
        return _filter_min_vin(all_conditions)
    elif mode == "min_vout":
        return _filter_min_vout(all_conditions)
    elif mode == "voltage_segment":
        return _filter_voltage_segment(all_conditions)
    else:
        return _filter_passthrough(all_conditions)
