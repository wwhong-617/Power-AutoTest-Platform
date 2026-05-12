# -*- coding: utf-8 -*-
"""
AN87330 Ainuo 协议帧调试脚本
直接连接串口，尝试各种设置帧格式，找到设备会应答的那个
"""
import serial
import time

BAUD = 38400
ADDR = 0x01
FRAME_HEAD = 0x7B
FRAME_TAIL = 0x7D

def modbus_crc(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])

def ainuo_cs(*bytes_ints):
    return sum(bytes_ints) & 0xFF

# ── 格式A: 查询帧（设备已知正常响应）─
def query_frame(ch=1):
    body = [ADDR, 0xF1, 0x00, ch]
    total = sum(body)  # 实际=0x09+0x01+0xF1+0x00+0x01=0xFC
    # 手册校验和 = sum(total_bytes + body) 低字节
    # total字段=0x0009, body=[01,F1,00,01], cs = (9+1+0xF1+0+1)=0xFC
    total_field = 0x0009
    cs = (total_field & 0xFF) + ((total_field >> 8) & 0xFF) + sum(body)
    return bytes([FRAME_HEAD, 0x00, 0x09] + body + [cs & 0xFF, FRAME_TAIL])

# ── 格式B: 设置帧 - 与查询帧结构完全一致（9字节）
# 7B | 00 09 | 01 | 5A | 00 | param_type | param_val | CS | 7D
def set_frame_v1(param_type=0x01, param_val=0x01):
    body = [ADDR, 0x5A, 0x00, param_type, param_val]
    total_field = 0x0009  # 与查询帧一致
    cs = (total_field & 0xFF) + ((total_field >> 8) & 0xFF) + sum(body)
    return bytes([FRAME_HEAD, 0x00, 0x09] + body + [cs & 0xFF, FRAME_TAIL])

# ── 格式C: 设置帧 - 去掉命令字(cmd)，总字节=9
# 7B | 00 09 | 01 | 5A | param_type | param_val | CS | 7D
def set_frame_v2(param_type=0x01, param_val=0x01):
    body = [ADDR, 0x5A, param_type, param_val]
    total_field = 0x0008
    cs = (total_field & 0xFF) + ((total_field >> 8) & 0xFF) + sum(body)
    return bytes([FRAME_HEAD, 0x00, 0x08] + body + [cs & 0xFF, FRAME_TAIL])

# ── 格式D: 设置帧 - 10字节(total=10)，保留cmd
# 7B | 00 0A | 01 | 5A | 00 | param_type | param_val | CS | 7D
def set_frame_v3(param_type=0x01, param_val=0x01):
    body = [ADDR, 0x5A, 0x00, param_type, param_val]
    total_field = 0x000A
    cs = (total_field & 0xFF) + ((total_field >> 8) & 0xFF) + sum(body)
    return bytes([FRAME_HEAD, 0x00, 0x0A] + body + [cs & 0xFF, FRAME_TAIL])

# ── Modbus RTU 格式（手册明确记载）
def modbus_write(addr=0x01, reg_hi=0x40, reg_lo=0x04, val_hi=0x00, val_lo=0x01):
    body = bytes([addr, 0x06, reg_hi, reg_lo, val_hi, val_lo])
    return body + modbus_crc(body)

def send_and_receive(ser, frame, name, timeout=2.0):
    ser.flushInput()
    ser.write(frame)
    time.sleep(0.3)
    chunks = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        n = ser.in_waiting
        if n > 0:
            chunks.append(ser.read(n))
            if sum(len(c) for c in chunks) >= 9:
                break
        time.sleep(0.05)
    data = b''.join(chunks)
    print(f"  {name}: TX={frame.hex().upper()} | RX={data.hex().upper() if data else '(无响应)'} | 长度={len(data)}")
    return data

def main():
    port = input("请输入 AN87330 串口端口号（如 COM3）: ").strip()
    if not port.startswith("COM"):
        port = "COM" + port

    try:
        ser = serial.Serial(
            port=port, baudrate=BAUD,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=3.0
        )
    except Exception as e:
        print(f"无法打开串口 {port}: {e}")
        return

    print(f"\n=== AN87330 通信测试 @ {port} {BAUD} 8N1 ===\n")

    # 先发查询帧验证设备在线
    print("【查询帧（设备已知正常）】")
    r = send_and_receive(ser, query_frame(1), "查询CH1")

    if not r or r[0] != FRAME_HEAD:
        print("设备不在线或协议不匹配，退出")
        ser.close()
        return

    print("\n【尝试各种 Ainuo 设置帧格式】")
    formats = [
        ("V1(9B,5A+00+type+val)",    set_frame_v1(0x01, 0x01)),
        ("V2(8B,5A+type+val无cmd)",   set_frame_v2(0x01, 0x01)),
        ("V3(10B,5A+00+type+val)",    set_frame_v3(0x01, 0x01)),
        ("V1电流量程(0x02,0x01)",       set_frame_v1(0x02, 0x01)),
        ("V2电流量程(无cmd)",           set_frame_v2(0x02, 0x01)),
        ("V1自动量程(0x01,0x08)",      set_frame_v1(0x01, 0x08)),
    ]
    for name, frame in formats:
        send_and_receive(ser, frame, name)
        time.sleep(0.3)

    print("\n【尝试 Modbus RTU 格式】")
    mb = modbus_write(0x01, 0x40, 0x04, 0x00, 0x01)  # 电压量程30V
    send_and_receive(ser, mb, "Modbus电压量程=30V(reg=4004h,val=1)")

    mb2 = modbus_write(0x01, 0x40, 0x05, 0x00, 0x05)  # 电流量程5A
    send_and_receive(ser, mb2, "Modbus电流量程=5A(reg=4005h,val=5)")

    # 再发一次查询，确认设备仍然在线
    print("\n【查询帧（结束后验证）】")
    send_and_receive(ser, query_frame(1), "查询CH1(后)")

    ser.close()
    print("\n完成")


if __name__ == "__main__":
    import serial
    main()
