# -*- coding: utf-8 -*-
"""
IP2716 协议指令表（来自 诱骗器IP2716通讯协议指令表.xlsx）
=============================================================

协议帧格式:
    HEADER(0x7B) + SLAVE_ADDR + LENGTH + COMMAND + DATA0 + CHECKSUM

    CHECKSUM = HEADER + SLAVE_ADDR + LENGTH + COMMAND + DATA0 的字节和（取低8位）

===================================================================
PD 快充指令 (COMMAND = 0x50)
===================================================================
帧格式 (各字段为 hex):
  HEADER  SLAVE_ADDR  LENGTH  COMMAND  DATA0  CHECKSUM  含义
  ----------------------------------------------------------------
  7B      01          1       50      -      CD        配置为PD快充模式
  7B      01          2       50      00     CE        第1档
  7B      01          2       50      01     CF        第2档
  7B      01          2       50      02     D0        第3档
  7B      01          2       50      03     D1        第4档
  7B      01          2       50      04     D2        第5档
  7B      01          2       50      05     D3        第6档
  7B      01          2       50      06     D4        第7档 (PPS档)
  7B      01          2       50      07     D5        PPS 升压 +100mV
  7B      01          2       50      08     D6        PPS 降压 -100mV
  7B      01          2       50      09     D7        PPS 电流 +50mA
  7B      01          2       50      0A     D8        PPS 电流 -50mA

  注意: 切换模式后需等待 500ms 以上再发送档位请求
  注意: Position 档位对应的具体电压由 DUT 的 PDO 决定

===================================================================
QC 快充指令 (COMMAND = 0x30)
===================================================================
  HEADER  SLAVE_ADDR  LENGTH  COMMAND  DATA0  CHECKSUM  含义
  ----------------------------------------------------------------
  7B      01          1       30      -      AD        配置为QC快充模式
  7B      01          2       30      00     AE        QC2.0 5V
  7B      01          2       30      01     AF        QC2.0 9V
  7B      01          2       30      02     B0        QC2.0 12V
  7B      01          2       30      03     B1        QC2.0 20V
  7B      01          2       30      04     B2        QC3.0 ENTER（进入恒压）
  7B      01          2       30      05     B3        QC3.0 EXIT
  7B      01          2       30      06     B4        QC3.0 升压（步进0.2V）
  7B      01          2       30      07     B5        QC3.0 降压

===================================================================
UFCS 快充指令 (COMMAND = 0x60)
===================================================================
  HEADER  SLAVE_ADDR  LENGTH  COMMAND  DATA0  CHECKSUM  含义
  ----------------------------------------------------------------
  7B      01          1       60      -      DD        配置为UFCS快充模式
  7B      01          2       60      01     DF        Position 1 档位
  7B      01          2       60      07     E5        UFCS 升压 +100mV
  7B      01          2       60      08     E6        UFCS 降压 -100mV
  7B      01          2       60      09     E7        UFCS 电流 +100mA
  7B      01          2       60      0A     E8        UFCS 电流 -100mA

===================================================================
"""

# ==================== PD 协议常量 ====================
PD_CMD          = 0x50   # PD 快充模式命令
PD_MODE_CFG     = None   # 无 DATA 时为配置模式命令

# PD 档位（具体电压由 DUT 的 PDO 决定，诱骗器只请求档位）
PD_POSITION_1   = 0x00   # 第1档
PD_POSITION_2   = 0x01   # 第2档
PD_POSITION_3   = 0x02   # 第3档
PD_POSITION_4   = 0x03   # 第4档
PD_POSITION_5   = 0x04   # 第5档
PD_POSITION_6   = 0x05   # 第6档
PD_POSITION_7   = 0x06   # 第7档 (PPS)

# PPS 微调
PD_PPS_VOLT_UP   = 0x07   # PPS 升压 +100mV
PD_PPS_VOLT_DOWN = 0x08   # PPS 降压 -100mV
PD_PPS_CURR_UP   = 0x09   # PPS 电流 +50mA
PD_PPS_CURR_DOWN = 0x0A   # PPS 电流 -50mA

# ==================== QC 协议常量 ====================
QC_CMD          = 0x30   # QC 快充模式命令
QC2_0_5V        = 0x00   # QC2.0 5V
QC2_0_9V        = 0x01   # QC2.0 9V
QC2_0_12V       = 0x02   # QC2.0 12V
QC2_0_20V       = 0x03   # QC2.0 20V
QC3_ENTER       = 0x04   # QC3.0 ENTER（进入恒压模式）
QC3_EXIT        = 0x05   # QC3.0 EXIT
QC3_VOLT_UP     = 0x06   # QC3.0 升压（步进0.2V）
QC3_VOLT_DOWN   = 0x07   # QC3.0 降压

# ==================== UFCS 协议常量 ====================
UFCS_CMD        = 0x60   # UFCS 快充模式命令
UFCS_POSITION_1 = 0x01   # Position 1 档位（DATA=0x01）
UFCS_VOLT_UP    = 0x07   # UFCS 升压 +100mV
UFCS_VOLT_DOWN  = 0x08   # UFCS 降压 -100mV
UFCS_CURR_UP    = 0x09   # UFCS 电流 +100mA
UFCS_CURR_DOWN  = 0x0A   # UFCS 电流 -100mA

# ==================== 通用常量 ====================
HEADER          = 0x7B   # 帧头固定值
ACK             = 0x01   # 应答命令

# 预设快捷调用表（直接索引：PD_PRESET[0x03] → PD_POSITION_4）
PD_PRESET = {
    0x00: PD_POSITION_1,   # 第1档
    0x01: PD_POSITION_2,   # 第2档
    0x02: PD_POSITION_3,   # 第3档
    0x03: PD_POSITION_4,   # 第4档
    0x04: PD_POSITION_5,
    0x05: PD_POSITION_6,
    0x06: PD_POSITION_7,
}
