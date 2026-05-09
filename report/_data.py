# -*- coding: utf-8 -*-
"""_data.py - 纯数据展开函数"""

from report._mappings import _cn

# ============================================================
# 数据展开
# ============================================================

def _warn_missing_fields(name_en: str, sr: dict):
    """
    检查 sub_result 是否包含 GLOBAL_COLS 中定义的标准字段（可选）。
    由于不同用例使用不同字段子集，不再强制要求。
    此函数在新架构下已不再调用，保留以备将来审计用。
    """
    pass  # 新架构下不做强制检查，用例自行负责输出正确字段


def _flatten(r: dict):
    """
    将一个 result（一个测试用例）的 sub_results 展开为行列表。

    统一策略：sub_result 的字段名 = GLOBAL_COLS 列头（完全一致），
    不再进行任何映射转换。用例负责输出正确字段名。

    不在 GLOBAL_COLS 中的字段会被 _write_case_sheet 自动忽略。
    """
    name_en = r.get("name", "")
    name_cn = _cn(name_en)
    case_result = r.get("result", "")
    sub_results = r.get("sub_results", [])
    rows = []
    seq = 0
    if sub_results:
        for sr in sub_results:
            seq += 1
            skipped = sr.get("skipped", False)
            sub_pass = sr.get("overall_pass", None)
            if skipped:
                conclusion = "SKIP"
            elif sub_pass is True:
                conclusion = "PASS"
            elif sub_pass is False:
                conclusion = "FAIL"
            else:
                conclusion = case_result

            # 剥离 sweep_points（大数组，不写入报告）
            sr_clean = {k: v for k, v in sr.items() if k != "sweep_points"}

            # 统一字段：序号、用例名称（中文）和测试结论由 _flatten 统一注入
            row = {
                "序号": seq,
                "用例名称": name_cn,
                # "测试结论": conclusion,
            }

            # 用例直接输出的字段（字段名即 GLOBAL_COLS 列头）
            row.update(sr_clean)

            rows.append(row)
    return rows


