#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys

# ====== Step 1: Add on_power_segment_toggle to _product_page.py ======
content = open(r'D:\injoinic--job\自动化测试平台开发\自动化测试平台\ui\pages\_product_page.py', encoding='utf-8').read()
new_func = '''

def on_power_segment_toggle(app):
    """
    高压/低压功率分段勾选框切换：启用/禁用 HV/LV 功率填写框。
    供 ui/_config_io.py 加载配置后调用，也供 config_ui 自身调用。
    """
    if app._power_segment_var.get() == 1:
        app._hv_power_entry.config(state="normal")
        app._lv_power_entry.config(state="normal")
    else:
        app._hv_power_entry.config(state="disabled")
        app._lv_power_entry.config(state="disabled")
        app._hv_power_var.set("")
        app._lv_power_var.set("")


'''
insert_after = 'from tkinter import ttk'
idx = content.find(insert_after)
end_of_imports = content.find('\n', idx) + 1
while end_of_imports < len(content) and content[end_of_imports] == '\n':
    end_of_imports += 1
content = content[:end_of_imports] + new_func + content[end_of_imports:]
open(r'D:\injoinic--job\自动化测试平台开发\自动化测试平台\ui\pages\_product_page.py', 'w', encoding='utf-8').write(content)
print('Step 1 done')

# ====== Step 2: Update _config_io.py to use the new function ======
content2 = open(r'D:\injoinic--job\自动化测试平台开发\自动化测试平台\ui\_config_io.py', encoding='utf-8').read()
old = 'app._on_power_segment_toggle()'
new = 'from ui.pages._product_page import on_power_segment_toggle as _opst\n    on_power_segment_toggle(app)'
if old in content2:
    content2 = content2.replace(old, new, 1)
    open(r'D:\injoinic--job\自动化测试平台开发\自动化测试平台\ui\_config_io.py', 'w', encoding='utf-8').write(content2)
    print('Step 2 done: updated _config_io.py')
else:
    print('Step 2 FAILED: could not find target in _config_io.py')

# ====== Step 3: Remove _on_power_segment_toggle from config_ui.py ======
content3 = open(r'D:\injoinic--job\自动化测试平台开发\自动化测试平台\config_ui.py', encoding='utf-8').read()
# Find method
si = content3.find('    def _on_power_segment_toggle(self):')
ei = content3.find('    # 扫描', si)  # next section comment
before = content3.rfind('\n', 0, si) + 1
content3 = content3[:before] + content3[ei:]
open(r'D:\injoinic--job\自动化测试平台开发\自动化测试平台\config_ui.py', 'w', encoding='utf-8').write(content3)
print('Step 3 done: removed _on_power_segment_toggle from config_ui.py')
print(f'config_ui.py now: {len(content3)} bytes')
