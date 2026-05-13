# -*- coding: utf-8 -*-
"""
efficiency_chart.py - 效率曲线绘制模块
======================================

从 InputEfficiencyTest 的 JSON 结果中提取效率数据，
按输出电压(Vout)分组，每组画一张曲线图：
  X轴：负载点（100% → 75% → 50% → 25% → 10%）
  Y轴：效率(%)
  每条线：一个输入电压(Vin)

使用 matplotlib 生成 PNG 图片，供 report/writer.py 嵌入 Excel。
"""

import os
import re
import json
import logging
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")  # 无头模式，不弹窗
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 配置中文字体
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False  # 解决负号显示问题

logger = logging.getLogger("PowerAutoTest")

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 负载点定义（从大到小）
LOAD_POINTS = ["100%", "75%", "50%", "25%", "10%"]

# 颜色方案（不同 Vin 用不同颜色）
_LINE_COLORS = [
    "#1f77b4",  # 蓝色
    "#2ca02c",  # 绿色
    "#ff7f0e",  # 橙色
    "#d62728",  # 红色
    "#9467bd",  # #紫色
    "#8c564b",  # 棕色
    "#e377c2",  # 粉色
    "#7f7f7f",  # 灰色
    "#bcbd22",  # 橄榄绿
    "#17becf",  # 青色
]

# 标记样式
_LINE_MARKERS = ["o", "s", "^", "D", "v", "p", "h", "*"]


# ─────────────────────────────────────────────────────────────────────────────
# 公开 API
# ─────────────────────────────────────────────────────────────────────────────

def plot_efficiency_curves(results_data, output_dir):
    """
    主入口：根据效率测试结果生成所有效率曲线图。

    Args:
        results_data: JSON results dict（get_report_json 返回的原始字典）
        output_dir:   图片输出目录（通常为结果文件夹路径）

    Returns:
        list of (vout, chart_path): 生成的图片路径列表，按 Vout 升序排列
        如果没有效率测试数据，返回空列表
    """
    # 提取 InputEfficiencyTest 的 sub_results
    sub_results = _extract_efficiency_sub_results(results_data)
    if not sub_results:
        logger.warning("[efficiency_chart] 没有找到 InputEfficiencyTest 数据，跳过曲线生成")
        return []

    # 解析数据：按 Vout 分组
    grouped = _group_by_vout(sub_results)

    # 生成每张图（存放到 output_dir/效率曲线/ 子目录）
    chart_dir = os.path.join(output_dir, "效率曲线")
    os.makedirs(chart_dir, exist_ok=True)
    chart_paths = []
    for vout, vin_data in sorted(grouped.items(), key=lambda x: float(x[0])):
        # 选取第一个协议的名称用于标题（通常所有条件协议一致）
        first_proto = next(iter(vin_data.values()))[0].get("proto", "")
        chart_path = os.path.join(chart_dir, f"效率曲线_Vout{vout}V.png")
        _draw_single_vout_chart(vin_data, vout, chart_path, first_proto)
        chart_paths.append((vout, chart_path))
        logger.info(f"[efficiency_chart] 生成效率曲线: Vout={vout}V → {chart_path}")

    return chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# 内部实现
# ─────────────────────────────────────────────────────────────────────────────

def _extract_efficiency_sub_results(results_data):
    """
    从完整 JSON 结果中提取 InputEfficiencyTest 的 sub_results。
    返回所有 sub_result 条目列表（扁平）。
    """
    results = results_data.get("results", [])
    for r in results:
        if r.get("name") == "InputEfficiencyTest":
            return r.get("sub_results", [])
    return []


def _group_by_vout(sub_results):
    """
    将扁平 sub_results 按 Vout 分组。

    Returns:
        dict: {
            "5.2": {           # Vout 字符串（保留小数位）
                "100.0V_60Hz": [    # 输入条件字符串
                    {"proto": "PD-PDO1", "vin": 100.0, "load_point": "100%", "efficiency": 89.8},
                    {"proto": "PD-PDO1", "vin": 100.0, "load_point": "75%",  "efficiency": 90.56},
                    ...
                ],
                "176.0V_50Hz": [...],
                ...
            },
            "20.0": {...},
        }
    """
    grouped = defaultdict(lambda: defaultdict(list))

    for row in sub_results:
        # 解析输入条件字符串 → vin, freq
        input_cond = row.get("输入条件", "")
        vin, freq = _parse_input_cond(input_cond)

        # 解析负载点（去掉 % 转小数）
        load_point = row.get("负载点", "")
        # 直接保留字符串形式用于后续排序

        # 输出电压（保留原始精度字符串作为 key）
        vout = row.get("输出电压(V)", "")
        if vout is None:
            continue

        proto = row.get("协议", "")
        efficiency = row.get("效率(%)", 0)
        if efficiency == "" or efficiency == 0:
            efficiency = 0.0

        key = f"{vin}V_{int(freq)}Hz" if freq else f"{vin}V"
        grouped[str(vout)][key].append({
            "proto": proto,
            "vin": vin,
            "freq": freq,
            "load_point": load_point,
            "efficiency": float(efficiency),
        })

    # 对每个 Vout 下的每个 Vin 数据按负载点顺序排序（100% → 10%）
    for vout, vin_map in grouped.items():
        for vin_key, points in vin_map.items():
            # 建立负载点顺序映射
            order = {lp: i for i, lp in enumerate(LOAD_POINTS)}
            vin_map[vin_key] = sorted(points, key=lambda x: order.get(x["load_point"], 99))

    return grouped


def _parse_input_cond(input_cond: str):
    """
    从 "100.0V_60.0Hz" 格式解析出 (vin=float, freq=float)。
    """
    vin_match = re.search(r"([\d.]+)V", input_cond)
    freq_match = re.search(r"([\d.]+)Hz", input_cond)
    vin = float(vin_match.group(1)) if vin_match else 0.0
    freq = float(freq_match.group(1)) if freq_match else 0.0
    return vin, freq


def _draw_single_vout_chart(vin_data: dict, vout: str, output_path: str, proto: str):
    """
    画单张效率曲线图。

    Args:
        vin_data:    { "100.0V_60Hz": [{"load_point": "100%", "efficiency": 89.8}, ...], ... }
        vout:        输出电压字符串，如 "5.2"
        output_path: 图片保存路径
        proto:       协议名称，用于标题
    """
    # 建立图表
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)

    # X 轴：负载点（固定顺序）
    x_ticks = list(range(len(LOAD_POINTS)))
    x_labels = LOAD_POINTS

    # 获取所有 Vin 键并排序（按电压升序）
    vin_keys = sorted(vin_data.keys(), key=lambda k: float(re.search(r"([\d.]+)V", k).group(1)))

    # 绘制每条 Vin 曲线
    for idx, vin_key in enumerate(vin_keys):
        points = vin_data[vin_key]
        efficiencies = [p["efficiency"] for p in points]
        color = _LINE_COLORS[idx % len(_LINE_COLORS)]
        marker = _LINE_MARKERS[idx % len(_LINE_MARKERS)]

        # 从 vin_key 提取电压显示
        vin_match = re.search(r"([\d.]+)V", vin_key)
        vin_label = f"Vin={vin_match.group(1)}V" if vin_match else vin_key

        ax.plot(
            x_ticks,
            efficiencies,
            color=color,
            marker=marker,
            markersize=8,
            linewidth=2.0,
            label=vin_label,
        )

        # 在数据点上标注数值
        for xi, yi in zip(x_ticks, efficiencies):
            if yi > 0:
                ax.annotate(
                    f"{yi:.1f}",
                    (xi, yi),
                    textcoords="offset points",
                    xytext=(0, 8),
                    ha="center",
                    fontsize=7,
                    color=color,
                )

    # 坐标轴设置
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels, fontsize=11)
    ax.set_xlabel("负载点", fontsize=13, fontweight="bold")
    ax.set_ylabel("效率 (%)", fontsize=13, fontweight="bold")

    # Y 轴范围（留一定余量）
    all_effs = []
    for points in vin_data.values():
        all_effs.extend([p["efficiency"] for p in points])
    if all_effs:
        eff_min = max(0, min(all_effs) - 5)
        eff_max = min(100, max(all_effs) + 5)
        ax.set_ylim(eff_min, eff_max)

    # 网格线
    ax.grid(True, linestyle="--", alpha=0.4, color="#cccccc")
    ax.set_axisbelow(True)

    # 标题（包含 Vout + 协议）
    ax.set_title(
        f"效率曲线  Vout={vout}V" + (f"  ({proto})" if proto else ""),
        fontsize=14,
        fontweight="bold",
        pad=12,
    )

    # 图例（放在右上方或下方）
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.02, 1),
        fontsize=10,
        framealpha=0.9,
        title="输入电压",
        title_fontsize=11,
    )

    # 调整布局，留出图例空间
    plt.tight_layout()
    plt.subplots_adjust(right=0.82)

    # 保存
    fig.savefig(output_path, bbox_inches="tight", dpi=150)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# 独立调试入口（可单独运行）
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 调试：直接指定 JSON 路径生成曲线图
    import glob

    results_dirs = glob.glob(os.path.join(_PROJECT_ROOT, "ui", "results", "*效率*"))
    if not results_dirs:
        print("没有找到效率测试结果目录")
        exit(1)

    latest_dir = max(results_dirs, key=os.path.getmtime)
    json_files = glob.glob(os.path.join(latest_dir, "*.json"))
    if not json_files:
        print(f"目录 {latest_dir} 中没有 JSON 文件")
        exit(1)

    json_path = max(json_files, key=os.path.getmtime)
    print(f"读取: {json_path}")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    chart_paths = plot_efficiency_curves(data, latest_dir)
    print(f"\n生成 {len(chart_paths)} 张效率曲线图:")
    for vout, path in chart_paths:
        print(f"  Vout={vout}V → {path}")
