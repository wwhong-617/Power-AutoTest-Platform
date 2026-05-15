# -*- coding: utf-8 -*-
"""_xlsx_post.py - xlsx 后处理与入口"""

import os
import re
from report.writer import generate_excel

# ============================================================
# rels 绝对路径修复（openpyxl → 相对路径）
# ============================================================
# 简化版 rels 修复：仅处理内部超链接的 rels 条目创建
# ============================================================

def _fix_rels(xlsx_path: str):
    """
    openpyxl 3.x 的 Hyperlink 对象会生成 r:id，但不创建对应的 rels 条目。
    本函数遍历所有 worksheet，为内部超链接创建缺失的 rels 条目。
    """
    import shutil, zipfile, re

    # 读取 ZIP 内容
    with zipfile.ZipFile(xlsx_path, 'r') as z:
        names = z.namelist()
        files = {name: z.read(name) for name in names}

    new_files = {}  # filename -> content

    # 遍历所有 worksheet，找到有超链接的
    for name in names:
        if not name.startswith('xl/worksheets/sheet') or not name.endswith('.xml'):
            continue
        if b'<hyperlink' not in files[name]:
            continue

        # 计算对应的 rels 文件路径
        # xl/worksheets/sheet3.xml -> xl/worksheets/_rels/sheet3.xml.rels
        parts = name.rsplit('/', 1)
        rels_name = parts[0] + '/_rels/' + parts[1] + '.rels'

        # 提取所有超链接的 location（bytes模式）
        raw = files[name]
        hyperlink_locs = re.findall(b'<hyperlink[^>]*location="([^"]+)"[^>]*/>', raw)
        if not hyperlink_locs:
            continue

        # 收集已有的非超链接 rels 条目
        existing_rels = files.get(rels_name, b'')
        existing_entries = []
        if existing_rels:
            pos = 0
            while True:
                elem_start = existing_rels.find(b'<Relationship', pos)
                if elem_start < 0:
                    break
                elem_end = existing_rels.find(b'/>', elem_start)
                if elem_end < 0:
                    break
                elem_end += 2
                elem = existing_rels[elem_start:elem_end]
                # 保留非超链接的 relationship
                if b'hyperlink' not in elem:
                    existing_entries.append(elem)
                pos = elem_end

        # 为每个 location 创建 hyper link rels 条目
        rid_counter = 1
        hyperlink_entries = []
        for loc_bytes in hyperlink_locs:
            rid = f'rId{rid_counter}'
            rid_counter += 1
            loc_str = loc_bytes.decode('utf-8', errors='replace')
            entry = ('<Relationship Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
                     f'Target="{loc_str}" TargetMode="Internal" Id="{rid}"/>').encode('utf-8')
            hyperlink_entries.append(entry)

        # 构建新的 rels 内容
        all_entries = existing_entries + hyperlink_entries
        new_rels = b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + b''.join(all_entries) + b'</Relationships>'
        new_files[rels_name] = new_rels

    # Step 2: 修复图片路径（绝对路径 -> 相对路径）
    for name in names:
        if not name.endswith('.rels'):
            continue
        if name in new_files:
            continue  # 已在 Step 1 处理

        raw = files[name]
        changed = False

        # 修复绝对路径 /xl/media/ -> ../media/
        if b'Target="/xl/media/' in raw:
            raw = raw.replace(b'Target="/xl/media/', b'Target="../media/')
            changed = True

        # 移除不需要的 TargetMode="External"
        if b'TargetMode="External"' in raw:
            raw = raw.replace(b' TargetMode="External"', b'')
            changed = True

        if changed:
            new_files[name] = raw

    # 写入修改后的文件
    if new_files:
        tmp = xlsx_path + '.tmp'
        with zipfile.ZipFile(xlsx_path, 'r') as zin:
            original_names = set(zin.namelist())
            with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
                # 复制原有文件
                for item in zin.infolist():
                    if item.filename in new_files:
                        zout.writestr(item, new_files[item.filename])
                    else:
                        zout.writestr(item, zin.read(item.filename))
                # 写入新文件（如 sheet3.xml.rels）
                for fname, content in new_files.items():
                    if fname not in original_names:
                        zout.writestr(fname, content)
        shutil.move(tmp, xlsx_path)




def auto_generate(results_dir: str = None, dut_name: str = ""):
    if results_dir is None:
        results_dir = os.path.join(os.path.dirname(__file__), "results")
    json_files = []
    if os.path.isdir(results_dir):
        for f in os.listdir(results_dir):
            # 扫描 result 子目录下所有 JSON（测试结果或配置备份），取最新
            if f.endswith(".json"):
                json_files.append(os.path.join(results_dir, f))
    if not json_files:
        print("[ReportGenerator] results 目录没有找到测试结果文件")
        return None
    latest = max(json_files, key=os.path.getmtime)
    print(f"[ReportGenerator] 生成报告: {latest}")
    return generate_excel(latest, results_dir, dut_name)


if __name__ == "__main__":
    auto_generate()