# -*- coding: utf-8 -*-
import serial, time

BAUD = 38400
ADDR = 0x01
FRAME_HEAD = 0x7B
FRAME_TAIL = 0x7D

def modbus_crc(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001: crc = (crc >> 1) ^ 0xA001
            else: crc >>= 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])

def send_recv(ser, frame, name, timeout=2.0):
    ser.flushInput()
    ser.write(frame)
    time.sleep(0.3)
    chunks = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        n = ser.in_waiting
        if n > 0:
            chunks.append(ser.read(n))
            if sum(len(c) for c in chunks) >= 9: break
        time.sleep(0.05)
    data = b''.join(chunks)
    rx = data.hex().upper() if data else 'NO_RESPONSE'
    print(f'{name}: TX={frame.hex().upper()} | RX={rx} | len={len(data)}')
    return data

# 查询帧（已知工作）
def q_frame(ch=1):
    body = [ADDR, 0xF1, 0x00, ch]
    total_f = 0x0009
    cs = (total_f & 0xFF) + ((total_f>>8)&0xFF) + sum(body)
    return bytes([FRAME_HEAD,0x00,0x09]+body+[cs&0xFF,FRAME_TAIL])

# 设置帧V1: 9字节 total=9 5A+00+type+val
def s_v1(pt=0x01,pv=0x01):
    body = [ADDR,0x5A,0x00,pt,pv]
    total_f = 0x0009
    cs = (total_f&0xFF)+((total_f>>8)&0xFF)+sum(body)
    return bytes([FRAME_HEAD,0x00,0x09]+body+[cs&0xFF,FRAME_TAIL])

# 设置帧V2: 8字节 无cmd
def s_v2(pt=0x01,pv=0x01):
    body = [ADDR,0x5A,pt,pv]
    total_f = 0x0008
    cs = (total_f&0xFF)+((total_f>>8)&0xFF)+sum(body)
    return bytes([FRAME_HEAD,0x00,0x08]+body+[cs&0xFF,FRAME_TAIL])

# 设置帧V3: 10字节 total=10 有cmd
def s_v3(pt=0x01,pv=0x01):
    body = [ADDR,0x5A,0x00,pt,pv]
    total_f = 0x000A
    cs = (total_f&0xFF)+((total_f>>8)&0xFF)+sum(body)
    return bytes([FRAME_HEAD,0x00,0x0A]+body+[cs&0xFF,FRAME_TAIL])

# Modbus写寄存器
def mb_write(reg_hi,reg_lo,val_hi,val_lo):
    body = bytes([ADDR,0x06,reg_hi,reg_lo,val_hi,val_lo])
    return body + modbus_crc(body)

port = 'COM3'
ser = serial.Serial(port=port, baudrate=BAUD, bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=3.0)
print(f'=== AN87330 @ {port} {BAUD} ===')

print()
print('-- Query frame (known working) --')
send_recv(ser, q_frame(1), 'Query CH1')

print()
print('-- Ainuo SET frames (various formats) --')
send_recv(ser, s_v1(0x01,0x01), 'V1:9B 5A+00+type+val (Vrange=30V)')
send_recv(ser, s_v2(0x01,0x01), 'V2:8B 5A+type+val (no cmd)')
send_recv(ser, s_v3(0x01,0x01), 'V3:10B 5A+00+type+val')
send_recv(ser, s_v1(0x01,0x08), 'V1: auto range (type=1,val=8)')
send_recv(ser, s_v2(0x01,0x08), 'V2: auto range (no cmd)')
send_recv(ser, s_v1(0x02,0x05), 'V1: IRange=5A (type=2,val=5)')

print()
print('-- Modbus RTU --')
send_recv(ser, mb_write(0x40,0x04,0x00,0x01), 'Modbus: VRange=30V(reg=4004h,val=1)')
send_recv(ser, mb_write(0x40,0x05,0x00,0x05), 'Modbus: IRange=5A(reg=4005h,val=5)')

print()
print('-- Post-test query --')
send_recv(ser, q_frame(1), 'Query CH1(after)')

ser.close()
print()
print('DONE')
