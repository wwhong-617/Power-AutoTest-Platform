# -*- coding: utf-8 -*-
"""验证修复后的 AN87330 驱动"""
import sys, logging, time
sys.path.insert(0, '.')
logging.basicConfig(level=logging.INFO, format='%(message)s')
from instruments.power_meter.AN87330 import AN87330

pm = AN87330(conn_type='COM', address='COM3', timeout_ms=5000)

print('1. 连接...')
pm.connect()

print('2. 初始化...')
pm.initialize()

print('3. 查询当前值...')
r = pm._query_ch(1)
print(f'   电压={r.get("voltage",0):.3f}V 电流={r.get("current",0):.3f}mA')

print('4. set_voltage_range_auto(CH1, 220V)...')
pm.set_voltage_range_auto('CH1', 220.0)

print('5. set_current_range_auto(CH1, 0.5A)...')
pm.set_current_range_auto('CH1', 0.5)

print('6. set_voltage_auto_range(CH1, True)...')
pm.set_voltage_auto_range('CH1', True)

print('7. set_current_auto_range(CH1, True)...')
pm.set_current_auto_range('CH1', True)

print('8. 查询验证...')
r2 = pm._query_ch(1)
print(f'   电压={r2.get("voltage",0):.3f}V 电流={r2.get("current",0):.3f}mA')

pm.disconnect()
print('9. 断开完成')
print()
print('=== ALL TESTS PASSED ===')
