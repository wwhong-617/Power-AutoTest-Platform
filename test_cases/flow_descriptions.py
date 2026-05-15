# -*- coding: utf-8 -*-
"""
测试用例流程说明（纯数据，不含逻辑）

供 config_ui.ConfigUI._get_test_case_flow() 查表使用。
编辑本文件即可更新流程说明，无须改动 config_ui.py。

Key 与 CASE_CN_NAMES（config_schema.py）一一对应。
"""

FLOW_DESCRIPTIONS = {

    # ===== 输入类测试 =====

    "输入电压范围测试": (
        "测试策略（每条 test_condition 独立执行）：\n\n"
        "1. 开机自检：基类 startup_self_check，不下电\n\n"
        "2. 示波器 ROLL 模式：时基覆盖完整扫描时长\n\n"
        "3. 诱骗器协议：锁定目标协议（charger 专用）\n\n"
        "4. 电子负载 CC 模式上电（功率分段后电流）\n\n"
        "5. 电压往返扫描：先缓降（Vin_cfg→Vin_lo），再缓升（Vin_lo→Vin_cfg）\n"
        "    Vac≥180V → 50Hz；Vac<180V → 60Hz；功率随电压段切换；每步等待 settle_time\n\n"
        "6. 示波器 STOP 冻结波形，测量 Vmax/Vmin，保存波形截图，汇总判定\n\n"
        "7. 放电下电\n\n"
        "规格判定：Vmax ≤ Vout×110% 且 Vmin ≥ Vout×90%"
    ),

    "输入欠压测试": (
        "测试策略（每条 test_condition 独立执行）：\n\n"
        "1. 开机自检：基类 startup_self_check，不下电\n\n"
        "2. 示波器 ROLL 模式：时基覆盖完整扫描时长\n\n"
        "3. 诱骗器协议：锁定目标协议（charger 专用）\n\n"
        "4. 电子负载 CC 模式上电\n\n"
        "5. 电压扫描（4阶段）\n\n"
        "    ① 缓降：Vin_min → (brown_out_lo - 5V)，0.5V/步，2s/步\n"
        "        检测输出 < Vout×70% → 记录 uvp_point，切换负载电流\n\n"
        "    ② 快降：(brown_out_lo - 5V) → 0V，5V/步，1s/步\n"
        "        检测快降过程中是否有重启\n\n"
        "    ③ 快升：0V → (brown_in_lo - 5V)，5V/步，1s/步\n"
        "        检测快升过程中是否有提前恢复\n\n"
        "    ④ 缓升：(brown_in_lo - 5V) → Vin_min，0.5V/步，2s/步\n"
        "        - self 模式：检测输出 > Vout×90% → 记录 recovery_point\n"
        "        - latch 模式：检测输出 > Vout×70% → 判定重启（FAIL）\n\n"
        "6. 示波器 STOP 冻结波形，保存波形截图，汇总判定\n\n"
        "7. 放电下电\n\n"
        "规格判定：\n"
        "  self 模式：uvp_point∈[brown_out_lo, brown_out_hi] 且 recovery_point∈[brown_in_lo, brown_in_hi] → PASS\n"
        "  latch 模式：uvp_point∈[brown_out_lo, brown_out_hi] 且缓升过程无重启 → PASS"
    ),

    "输入跌落测试": (
        "测试策略（每条 test_condition 独立执行）：\n\n"
        "1. 开机自检：基类 startup_self_check，不下电\n\n"
        "2. 示波器 ROLL 模式：双通道配置 + 估算时基\n\n"
        "3. 诱骗器协议\n\n"
        "4. 电子负载 CC 模式上电（功率分段后电流）\n\n"
        "5. 输入跳变序列（Vin_lo ↔ Vin_cfg 循环，功率随电压段切换）\n\n"
        "6. 示波器 STOP 冻结波形，读取 Vmax/Vmin，保存截图，汇总判定\n\n"
        "7. 放电下电\n\n"
        "规格判定：Vmax ≤ Vout×110% 且 Vmin ≥ Vout×90%"
    ),

    "输入空载功率测试": (
        "测试策略（每条 test_condition 独立执行）：\n\n"
        "1. 开机自检\n\n"
        "2. 功率计电压档位设置（根据输入电压自动选档）\n\n"
        "3. 诱骗器协议\n\n"
        "4. 电子负载 ON/OFF（激活 DUT 进入正常工作状态）\n\n"
        "5. 等待稳定，功率计读取多组数据求平均\n\n"
        "6. 汇总判定：avg_power ∈ [空载功耗_W_lo, 空载功耗_W_hi] → PASS\n\n"
        "7. 功率计档位设回自动，放电下电\n\n"
        "规格来源：specs_v2[空载功耗_W_lo] / specs_v2[空载功耗_W_hi]"
    ),

    "输入效率测试": (
        "测试策略（每条 test_condition 独立执行，每条件含 5 个负载点）：\n\n"
        "1. 开机自检\n\n"
        "2. 诱骗器设置协议\n\n"
        "3. 电子负载 ON（功率分段后电流带载老化）\n\n"
        "4. 老化 20s\n\n"
        "5. 循环测 5 个负载点（100%→75%→50%→25%→10%）\n\n"
        "    每个负载点：电子负载设目标电流 → 等待10s → 功率计读取输入功率/电压/电流\n\n"
        "6. 计算 6 级平均能效（η25%+η50%+η75%+η100%）/4\n"
        "    计算 7 级平均能效（η10%+η25%+η50%+η75%+η100%）/5\n\n"
        "7. 汇总各点效率 + 6级/7级平均能效结论\n\n"
        "8. 放电下电\n\n"
        "规格判定：所有负载点 PASS 且 6级/7级平均能效达标 → 整体 PASS"
    ),

    "输入极轻载功耗测试": (
        "测试策略（每条 test_condition 独立执行）：\n\n"
        "1. 开机自检\n\n"
        "2. 诱骗器协议配置\n\n"
        "3. 功率计档位设置（根据输入电压&电流自动选择）\n\n"
        "4. 设置电子负载电流 = 极轻载功率 / Vout_target\n\n"
        "5. 等待稳定，功率计读取输入功率 10 次求平均\n\n"
        "6. 汇总判定：avg_power ∈ [极轻载功耗_W_lo, 极轻载功耗_W_hi] → PASS\n\n"
        "7. 功率计档位设回自动，放电下电\n\n"
        "规格来源：specs_v2[极轻载功耗_W_lo] / specs_v2[极轻载功耗_W_hi]"
    ),

    "待机功耗测试": (
        "测试策略（独立用例，无 test_conditions）：\n\n"
        "1. AC_SOURCE 设置输入电压/频率，输出 ON\n\n"
        "2. 等待 settle_time 稳定\n\n"
        "3. 功率计读取输入功率 Pin\n\n"
        "4. 汇总判定：Pin ≤ 待机功耗_W_lo → PASS\n\n"
        "5. 关闭 AC 输出\n\n"
        "规格来源：specs_v2[待机功耗_W_lo]（由引擎注入）"
    ),

    "功率因数测试": (
        "测试策略（独立用例，无 test_conditions，4 个固定负载点）：\n\n"
        "1. AC_SOURCE 设置输入电压/频率，输出 ON\n\n"
        "2. 对每个负载点（25%/50%/75%/100%）：\n"
        "    - 电子负载设目标电流，ON\n"
        "    - 等待 settle_time 稳定\n"
        "    - 功率计读取功率因数 PF\n"
        "    - 汇总判定：PF ≥ pf_min → PASS\n"
        "    - 电子负载 OFF\n\n"
        "3. 关闭仪器输出\n\n"
        "规格来源：spec[pf_min]"
    ),

    # ===== 输出类测试 =====

    "输出开关机测试": (
        "测试策略（每条 test_condition 独立执行，每条件输出 2 行：开机+关机）：\n\n"
        "1. 开机自检：基类 startup_self_check，捕获实测开机电压\n\n"
        "2. 用实测开机电压配置示波器（开机视图：刻度/偏移/触发）\n\n"
        "3. AC OFF + 放电（确保完全下电，进入冷启动）\n\n"
        "4. 武装示波器 SINGLE 触发 → 立即冷启动上电 → 等待触发\n\n"
        "5. 读取开机波形 + 过冲/下冲数据\n\n"
        "6. 诱骗器协议配置 + 电子负载设额定电流\n\n"
        "7. 用 vout_target 重新配置示波器（关机视图）\n\n"
        "8. 武装示波器 SINGLE 触发 → AC OFF → 等待触发\n\n"
        "9. 读取关机波形 + 过冲/下冲数据\n\n"
        "10. 放电下电\n\n"
        "规格判定：过冲≤overshoot_max_pct 且 下冲≤overshoot_max_pct → PASS"
    ),

    "输出纹波噪声测试": (
        "测试策略（每条 test_condition × 3 个负载点 0%/50%/100%）：\n\n"
        "1. 开机自检\n\n"
        "2. 诱骗器协议配置\n\n"
        "3. 设置目标负载电流，等待 2s 稳定\n\n"
        "4. 清屏，等 3s，示波器 STOP，读取 VPP，保存波形，示波器重新 RUN\n\n"
        "5. 汇总判定：纹波实测值 ≤ 纹波要求 → PASS\n\n"
        "（三个负载点之间不独立上下电，连续测量）"
    ),

    "输出纹波输入扫描测试": (
        "测试策略（每条 test_condition 独立执行）：\n\n"
        "1. 开机自检\n\n"
        "2. 启动示波器 RUN + 诱骗器协议配置\n\n"
        "3. 电子负载设置到测试条件电流（功率分段后 iout_eff）\n\n"
        "4. 输入电压缓调扫描（Vin_cfg → Vin_lo → Vin_cfg，步进 5V，每步 1s）\n"
        "    Vac≥180V → 50Hz；Vac<180V → 60Hz\n"
        "    HV/LV 跨边界时分 5 步渐进切换负载电流\n"
        "    示波器全程滚动（ROLL），扫描完成后 STOP，读取峰峰值，汇总判定\n\n"
        "5. 放电下电\n\n"
        "规格判定：纹波实测值 ≤ 纹波要求_mV_hi → PASS"
    ),

    "输出纹波负载扫描测试": (
        "测试策略（每条 test_condition 独立执行）：\n\n"
        "1. 开机自检\n\n"
        "2. 启动示波器 RUN + 诱骗器协议配置\n\n"
        "3. 负载电流缓调双向扫描（iout_eff → 0A → iout_eff，步进 0.05A，每步 1s）\n"
        "    示波器全程滚动（ROLL），扫描完成后 STOP，读取峰峰值，汇总判定\n\n"
        "4. 放电下电\n\n"
        "规格判定：纹波实测值 ≤ 纹波要求_mV_hi → PASS"
    ),

    "输出动态测试": (
        "测试策略（每条 test_condition × 大动态/小动态场景）：\n\n"
        "1. 开机自检\n\n"
        "2. 诱骗器协议配置\n\n"
        "3. 大动态测试：\n"
        "    - 示波器刻度/偏移/触发配置\n"
        "    - 预热负载 → 进入 CC-Dynamic 动态模式\n"
        "    - 等待稳定 → STOP → 读取 VMAX/VMIN → 保存波形 → 判定规格上下限\n\n"
        "4. 小动态测试（步骤同上）\n\n"
        "5. 放电下电\n\n"
        "规格判定：所有动态场景 Vmax≤规格上限 且 Vmin≥规格下限 → PASS"
    ),

    "输出电压上升时间测试": (
        "测试策略（每条 test_condition 独立执行）：\n\n"
        "1. 开机自检，捕获实测开机电压\n\n"
        "2. 用实测开机电压配置示波器（时基根据规格自适应）\n\n"
        "3. 放电下电（确保冷启动）\n\n"
        "4. 武装示波器 SINGLE 触发 → 开机自检上电 → 等待触发\n\n"
        "5. 读取上升时间数据 + 波形截图\n\n"
        "6. 放电下电\n\n"
        "规格判定：上升时间_ms_lo ≤ 实测值 ≤ 上升时间_ms_hi → PASS"
    ),

    "输出开机延迟时间测试": (
        "测试策略（每条 test_condition 独立执行）：\n\n"
        "1. 开机自检\n\n"
        "2. 配置示波器双通道（输入+输出）刻度\n\n"
        "3. 放电下电（冷启动）\n\n"
        "4. 武装 SINGLE 触发 → 开机自检上电 → 等待触发\n\n"
        "5. 采集输入+输出双通道波形 → 计算延迟（AC输入建立→Vout达90%）→ 保存截图\n\n"
        "6. 放电下电\n\n"
        "规格判定：开机延迟时间_ms_lo ≤ 实测值 ≤ 开机延迟时间_ms_hi → PASS"
    ),

    "输出电压精度测试": (
        "测试策略（独立用例）：\n\n"
        "1. AC_SOURCE 设置输入电压/频率，输出 ON\n\n"
        "2. 电子负载 CC 模式设目标电流，ON\n\n"
        "3. 等待稳定\n\n"
        "4. 功率计或电子负载读取输出电压\n\n"
        "5. 与标称电压比对，计算精度百分比\n\n"
        "6. 关闭仪器输出\n\n"
        "规格判定：|Vout - Vnominal| / Vnominal × 100% ≤ tolerance_pct → PASS"
    ),

    # ===== 保护功能测试 =====

    "输出过流保护测试": (
        "测试策略（每条 test_condition 独立执行）：\n\n"
        "1. 开机自检，捕获 vout_default\n\n"
        "2. 诱骗器协议配置\n\n"
        "3. 功率计实测 vout_test（斜升扫描初始读数参考）\n\n"
        "4. 计算 OCP 规格上下限（来自 specs_v2）\n\n"
        "5-6. 示波器 ROLL 模式 + 动态时基，开始采集\n\n"
        "7-8. 电子负载上电 → 缓调负载电流寻找 OCP 触发点\n"
        "    Vout < 0.1×vout_target → OCP 触发，记录过流点\n"
        "    达 spec_hi 未触发 → FAIL\n\n"
        "9. 恢复测试：\n"
        "    - latch 模式：Vout < 0.1×vout_default → PASS\n"
        "    - self 模式：重新诱骗协议调压至 vout_target，验证 Vout≥0.9×vout_target → PASS\n\n"
        "10-11. 示波器停止，保存波形，记录结果\n\n"
        "12. 放电下电"
    ),

    "输出短路保护测试": (
        "测试策略（每条 test_condition × 3 个负载点 100%/50%/0%）：\n\n"
        "1. 开机自检，捕获 Vout_default（实际输出电压基准）\n\n"
        "2. 诱骗器协议配置\n\n"
        "3. 示波器配置 SINGLE 触发（NORMAL 模式 / NEG 边沿）\n\n"
        "4. 电子负载设目标电流后短路（short_on）\n\n"
        "5. 示波器 ARM → 等5s → 短路 → 等5s → 短路保持 SHORT_ON_HOLD=5s\n\n"
        "6. 等待示波器触发完成，测量短路中电压\n\n"
        "7. 短路解除（short_off），停止采集，保存波形\n\n"
        "8. 等待 SHORT_OFF_HOLD，测量短路后电压\n\n"
        "9. 恢复判定（latch/self，基准 = Vout_default）：\n"
        "    - latch 模式：Vout < 0.1×Vout_default → PASS\n"
        "    - self 模式：Vout > 0.9×Vout_default → PASS\n\n"
        "10. 放电下电\n\n"
        "（三个负载点之间独立上下电，锁死产品不影响下一个负载点）"
    ),

    # ===== 协议测试 =====

    "PD协议": (
        "测试策略：\n\n"
        "1. 诱骗器模拟 PD Sink，监控 CC 线通讯\n\n"
        "2. 检查是否发出 Source_Capabilities\n\n"
        "3. 检查 PDO 档位（5V/9V/15V/20V）\n\n"
        "4. 执行电压切换请求（Request）\n\n"
        "规格判定：协议握手成功 + 所有请求档位正常响应 → PASS"
    ),

    "QC协议": (
        "测试策略：\n\n"
        "1. 诱骗器发送 QC2.0/3.0 指令\n\n"
        "2. 获取协议请求电压档位（5V/9V/12V）\n\n"
        "3. 验证各档位电压输出正确\n\n"
        "规格判定：QC 握手成功 + 各电压档位正常 → PASS"
    ),

    "AFC协议": (
        "测试策略：\n\n"
        "1. 诱骗器发送 AFC 指令\n\n"
        "2. 验证协议握手成功\n\n"
        "规格判定：AFC 握手成功 → PASS"
    ),

    "FCP协议": (
        "测试策略：\n\n"
        "1. 诱骗器发送 FCP 指令\n\n"
        "2. 验证协议握手成功\n\n"
        "规格判定：FCP 握手成功 → PASS"
    ),

}
