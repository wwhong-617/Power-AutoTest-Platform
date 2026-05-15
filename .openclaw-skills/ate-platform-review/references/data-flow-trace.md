# 数据流追踪参考

> 平台核心数据流的全路径文档。检视代码时优先加载此文件，建立全局视野。

---

## 配置系统（最复杂，数据分歧最多）

### save_config 写入路径

```
UI（_spec_vars, _prod_name_var, _qc_vars, _pd_vars, ...）
    │
    ▼ save_config()  [ui/_config_io.py]
    │
    ├─► product_info 字典
    │       ├── product_name        ← _prod_name_var.get()
    │       ├── product_type        ← _prod_type_vars["充电器"].get() == 1 ? "充电器" : "适配器"
    │       ├── specs_v2            ← build_specs_flat(_spec_vars, {})
    │       │       生成格式：{flat_key}_lo / {flat_key}_hi
    │       │       查找逻辑：SPECS_KEYS = [(flat_key, label_text), ...]
    │       │       flat_key 例："Brown_in_V"，label_text 例："Brown-in（V）"
    │       │       输出 key：Brown_in_V_lo / Brown_in_V_hi
    │       ├── protection_logic_v2 ← build_protection_flat(_prot_vars, {})
    │       ├── qc                  ← _qc_vars {label: {check, entry}}
    │       └── pd / ufcs           ← 同上
    │
    ├─► test_params 字典
    │       ├── osc_in_ch / osc_out_ch        ← StringVar
    │       ├── pwr_in_v_ch / pwr_in_i_ch    ← StringVar
    │       ├── eload_vout1_ch / eload_vout2_ch
    │       ├── dyn_large / dyn_small         ← Treeview → rows_to_dicts
    │       └── startup                        ← 同上
    │
    └─► checked_cases 列表
            ← _case_vars {case_cn_name: {check: IntVar}}
            → 写入 JSON "cases": [case_cn_name, ...]
```

### load_config 读取路径

```
JSON 文件
    │
    ▼ load_config()  [ui/_config_io.py]
    │
    ├─► product_info
    │       ├── _prod_name_var.set(json["product_name"])
    │       ├── _prod_type_vars["充电器"].set(1 if json["product_type"]=="充电器" else 0)
    │       │
    │       ├── specs_v2 → _spec_vars 映射（最复杂）
    │       │       遍历 SPECS_KEYS：
    │       │       flat_key, label_text = SPECS_KEYS[i]
    │       │       lo_raw = json_specs_v2.get(f"{flat_key}_lo")
    │       │       hi_raw = json_specs_v2.get(f"{flat_key}_hi")
    │       │       v["lo"].set(空字符串 if NaN/None else str(val))
    │       │       v["hi"].set(空字符串 if NaN/None else str(val))
    │       │
    │       ├── protection_logic_v2 → _prot_vars
    │       └── qc/pd/ufcs → 遍历 _qc_vars / _pd_vars / _ufcs_vars
    │
    ├─► test_params → 各 StringVar / Treeview
    │       ├── dyn_large / dyn_small：rows_to_dicts → 清空 Treeview → 批量插入
    │       └── startup：同上
    │
    └─► cases → _case_vars 勾选状态
            遍历 json["cases"]，设置对应 case 的 IntVar = 1
```

### ⚠️ save/load 对称性检查点

```
SPECS_KEYS flat_key  ──build_specs_flat()──►  JSON key
                                    ↓
                              JSON 保存
                                    ↓
                        get(f"{flat_key}_lo")
                                    ↓
                        _spec_vars[label_text]["lo"].set()

结论：flat_key 是 JSON 的 key，label_text 是 UI 的 key
若 build_specs_flat 写 key = f"{flat_key}_lo"，load 时必须查同样的 key
```

---

## 测试执行引擎数据流

```
用户点"运行测试"
    │
    ▼ _build_test_engine_config(checked_cases)  [ui/_engine_api.py]
    │
    ├─► product_info（来自 UI 变量）
    │       ├── specs_v2（来自 _spec_vars，load_config 已写入）
    │       ├── power_segment
    │       ├── hv_power / lv_power
    │       └── ultra_light_power
    │
    ├─► test_params（来自 UI 变量）
    │       ├── osc_channel_config
    │       ├── power meter channel config
    │       └── electronic load channel config
    │
    └─► case_params（来自 filtered_conditions）
            ├── conditions：_source_conditions（来自生成或加载）
            └── specs：product_info["specs_v2"]
                    │
                    ▼ TestEngine.run_case(key, params)
                            │
                            ▼ Case.run()
                                    │
                                    ├── setup()
                                    │       ├── initialize_all_instruments()
                                    │       ├── apply_channel_roles()
                                    │       └── self._cached_params = self.params  ← 缓存
                                    │
                                    ├── execute()  ← 不调用 self.params.get()，用缓存
                                    │       └── 测试逻辑，使用 self._cached_voltage 等
                                    │
                                    └── teardown()
                                            └── _step_discharge(current=2.0)
```

---

## 报告生成数据流

```
TestEngine 测试完成 → results/
    │
    ▼ report_generator.generate(...)  [report/__init__.py]
            │
            ▼ report_writer.write(result_dir, case_results, config)
                    │
                    ├─► _mappings.py
                    │       CASE_COLS   ← 用例列定义（key = case_key）
                    │       COL_KEYS    ← 全局列名常量
                    │       COLUMN_MAP  ← 列索引映射
                    │
                    ├─► _data.py
                    │       _flatten()  ← 将 result dict 展开为行
                    │       sub_results 字段名必须与 COLUMN_KEYS 一致
                    │
                    └─► _xlsx_post.py
                            合并单元格、列宽、sheet 名
```

---

## 仪器管理数据流

```
initialize_all_instruments()
    │
    ▼ instrument_manager.create_instrument(key, model, comm, addr)
            │
            ├─► 查找 DEVICE_DEFS[key]["model"] 对应的驱动类
            │
            ├─► visa.open() → 仪器对象
            │
            ├─► idn = query("*IDN?")
            │
            ├─► 驱动类的 __init__(resource, address)
            │       │
            │       ├─► base.__init__() → _idn 验证
            │       │       若 IDN 不匹配：raise InstrumentError（已修复错误信息）
            │       │
            │       └─► 子类特有初始化
            │
            └─► 返回仪器实例
                    │
                    ▼ apply_channel_roles(pwrmeter, config)
                            │
                            ├─► WT333E：直接设置 self._input_ch / self._output_ch
                            │
                            └─► AN87330：调用 self.set_channel_roles(input_voltage_ch, output_voltage_ch)
                                    │
                                    └─► self._parse_channel(channel)  # CH1/CH2/数字 1/2 均可
```

---

## 模块边界（检视接口时查这里）

| 模块 | 文件 | 核心输入 | 核心输出 |
|-----|------|---------|---------|
| 配置UI | config_ui.py | 用户UI操作 | 配置文件JSON |
| 配置IO | ui/_config_io.py | app对象, 路径 | save/load JSON |
| 配置Schema | config_schema.py | _spec_vars, SPECS_KEYS | specs_v2字典 |
| 测试引擎 | test_engine.py | case_params | results/目录 |
| 仪器管理 | instrument_manager.py | DEVICE_DEFS, 驱动类 | 仪器实例 |
| 报告生成 | report/writer.py | case_results, config | xlsx文件 |
