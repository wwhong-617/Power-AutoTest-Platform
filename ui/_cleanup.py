#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cleanup config_ui.py: remove json import, dead dev_menu block, _open_device_panel"""
content = open(r'D:\injoinic--job\自动化测试平台开发\自动化测试平台\config_ui.py', encoding='utf-8').read()
original = content

# 1. Remove import json (not used)
content = content.replace('\nimport json\n', '\n', 1)
print('import json removed')

# 2. Remove the entire commented dev_menu block + preceding comment line
# Start: the line '# 设备上位机菜单（暂无效，等待后续开发）' 
# End: just before 'help_menu = tk.Menu(menubar, tearoff=0)'
d1 = content.find('# 设备上位机菜单（暂无效，等待后续开发）')
d2 = content.find('help_menu = tk.Menu(menubar, tearoff=0)')
before_dev = content.rfind('\n', 0, d1) + 1  # +1 to keep one leading newline
after_dev = d2
content = content[:before_dev] + content[after_dev:]
print(f'dev_menu block removed ({d2 - d1} chars)')

# 3. Remove _open_device_panel method
o1 = content.find('    def _open_device_panel(self, key):')
o2 = content.find('    def _open_help(', o1)
before_open = content.rfind('\n', 0, o1) + 1
after_open = o2
content = content[:before_open] + '\n' + content[after_open:]
print(f'_open_device_panel removed')

open(r'D:\injoinic--job\自动化测试平台开发\自动化测试平台\config_ui.py', 'w', encoding='utf-8').write(content)
print(f'Done. {len(original)} -> {len(content)} bytes ({len(original)-len(content)} removed)')
