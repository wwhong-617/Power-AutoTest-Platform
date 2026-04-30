# -*- coding: utf-8 -*-
"""
测试条件过滤纯函数（无 UI 依赖，可独立测试）
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


def dict_to_row(d):
    """将 dict 转回 (vin, freq, proto, vout, iout, product_type) tuple 格式"""
    if not isinstance(d, dict):
        return d
    return (d.get("vin"), d.get("freq"), d.get("proto", ""),
            d.get("vout"), d.get("iout"), d.get("product_type", ""))


# ============================================================
# 条件过滤
# ============================================================

def filter_conditions_by_case(case_key, all_conditions, case_registry):
    """
    根据 case_key 从全量条件中筛选专属条件。

    筛选策略：
    - InputUnderVoltageTest：取 (proto, vout, iout) 分组内 Vin 最低的那条
    - voltage_segment=True 的用例：按 (proto, vout, iout) 分组，每组取 Vin 最高
    - 其他用例：全量转 dict

    Args:
        case_key:      英文用例名，如 "InputVoltageRangeTest"
        all_conditions: List[dict] 或 List[tuple]，全量条件
        case_registry:  TestEngine.CASE_REGISTRY（dict）

    Returns:
        List[dict] - 筛选后的条件列表
    """
    def row_to_dict_inner(row):
        return row_to_dict(row)

    # InputUnderVoltageTest：取每组最低 Vin
    if case_key == "InputUnderVoltageTest":
        if not all_conditions:
            return all_conditions
        rows_as_dicts = [row_to_dict_inner(r) for r in all_conditions]
        min_vin = min(r["vin"] for r in rows_as_dicts if r.get("vin"))
        min_vin_rows = [r for r in rows_as_dicts if abs(r["vin"] - min_vin) < 0.01]
        best_row = max(min_vin_rows, key=lambda r: float(r["vout"]) if r["vout"] else 0)
        return [best_row]

    # voltage_segment 用例：按 (proto, vout, iout) 分组，每组取 Vin 最高
    if case_registry.get(case_key, {}).get("voltage_segment"):
        if not all_conditions:
            return all_conditions
        groups = defaultdict(list)
        for row in all_conditions:
            d = row_to_dict_inner(row)
            if not all(d.get(k) for k in ("vin", "freq", "proto", "vout", "iout")):
                continue
            key = (str(d["proto"]), str(d["vout"]), str(d["iout"]))
            groups[key].append(d)
        result = []
        for key, rows in groups.items():
            best = max(rows, key=lambda r: float(r["vin"]) if r["vin"] else 0)
            result.append(best)
        return result

    # 其他用例：全量转 dict
    return [row_to_dict_inner(r) for r in all_conditions]
