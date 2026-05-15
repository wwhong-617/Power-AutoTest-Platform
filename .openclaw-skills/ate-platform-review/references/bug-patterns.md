# Bug 模式清单（按类别）

> 来自平台历史发现 P-1～P-15 的根因模式总结。遇到新问题时先查这里。

---

## 🔴 UI 绑定类（P-1 高危）

### 模式：tk.IntVar / tk.StringVar 的 truthy 判断错误

**错误模式：**
```python
# IntVar 对象永远 truthy（除非值为 0），永远走 and 分支
app._prod_type_vars.get("充电器") and "充电器" or "适配器"
# 永远返回 "充电器"，无论勾选状态

# 正确做法
"充电器" if app._prod_type_vars.get("充电器", tk.IntVar()).get() == 1 else "适配器"
```

**搜索关键词：** `"and .* or"` 模式、`.get()` 后直接做布尔判断

---

## 🟡 配置读写类（P-2 高危）

### 模式 A：save/load key 不对称

**常见场景：**
- save 时写 `specs_v2["Brown_in_V_lo"]`，load 时查 `specs_v2["Brown_in_V_hi"]`
- save 时用 `flat_key`（含下划线），load 时用 label_text（含连字符/空格）

**验证方法：** 对照 `SPECS_KEYS` 的 flat_key 和 label_text，确认：
- `build_specs_flat()` 写入的 key 格式
- `load_config` 读取时用的 lookup key

### 模式 B：NaN / None 写入后无法还原

```python
# save 时，若值为空写入 None
specs_v2[f"{flat_key}_lo"] = None  # 写入 JSON → null

# load 时，None 无法还原为空字符串
v['lo'].set(loaded_specs_v2.get(f'{flat_key}_lo'))  # set(None) = 空值，可接受
```

### 模式 C：页面未建时就加载配置

```python
class ConfigUI(EngineAPI):
    def __init__(self, root):
        ...
        self._do_load_config(last_path)   # ❌ 页面还没构建
        ...
        self._build_ui()                   # ✅ 页面在这里才构建
```

**正确顺序：** `_build_ui()` → 所有页面构建完成 → `_try_load_last_config()`

---

## 🟠 异常处理类（P-3 高危）

### 模式：所有异常同一处理

**错误模式：**
```python
except Exception as e:
    _log("ERROR", f"仪器操作失败：{e}")
    # VISA timeout 和 IDN 验证失败都走同一分支
```

**正确做法：三分流**
```python
except pyvisa.errors.VisaIOError as e:
    # VISA 超时：可重试，带 backoff
    ...
except InstrumentError:
    # 永久失败（IDN 不匹配）：不重试
    ...
except Exception as e:
    # 其他未知异常：记录，不重试
    ...
```

**导入：** `import pyvisa.errors`

---

## 🔵 仪器通信类（P-4 中危）

### 模式：通道号硬编码

**错误模式：**
```python
# 所有仪器都用 CH1/CH2，无法动态配置
self.write(f":MEASURE{ch} ...")
```

**正确做法：** 在仪器类中用 `self._input_ch` / `self._output_ch` 成员变量，通过 `set_channel_roles()` 配置

### 模式：IDN 验证失败信息不足

**错误模式：**
```python
# base.py 只说"身份验证失败"，不包含地址和实际收到的 IDN
raise Exception("身份验证失败")
```

**正确做法：**
```python
raise InstrumentError(
    f"身份验证失败 [{cls_name}@{self._address}]\n"
    f"  实测IDN: {self._idn}"
)
```

---

## 🟢 报告生成类（P-5 中危）

### 模式：列映射 key 与数据展开不一致

**常见场景：**
- `writer.py` 写 `"输入功率(W)"` 列，但 `_data.py` 的 `_flatten()` 展开时字段名叫 `input_power`
- 新增测试用例后，`_mappings.py` 漏加 CASE_COLS 条目

**验证方法：** 对照 `_mappings.py` 的 CASE_COLS 与 `_flatten()` 输出的字段名

### 模式：sub_results 展开遗漏

```python
# 每个测试用例的 sub_results 格式必须一致
# 若某个用例返回的 sub_item 缺少字段，_flatten() 展开时会丢数据
sub_item = {
    "vin": ...,        # 隐含在输入条件字符串里
    "vout": ...,
    "iout": ...,
    "负载点": ...,     # ❌ 用了中文 key
    "效率(%)": ...,    # ❌ 与英文 key 风格不一致
}
# 正确：所有字段名与 _mappings.py 的 COLUMN_KEYS 对齐
```

---

## ⚪ 测试执行类（P-6 一般）

### 模式：execute() 中调用 self.params.get()

**错误模式：**
```python
def execute(self):
    voltage = self.params.get("voltage")  # ❌ execute 中实时获取
    # 若 setup() 未正确缓存，运行时参数可能已变
```

**正确做法（DESIGN_RULES.md 规则）：**
```python
def setup(self):
    self._cached_voltage = self.params["voltage"]  # ✅ setup 中缓存

def execute(self):
    voltage = self._cached_voltage  # ✅ 使用缓存
```

### 模式：duration 包含 teardown 放电时间

**根因：** `end_time = time.time()` 放在 `teardown()` 中

**正确做法：**
```python
def run(self):
    self.start_time = time.time()    # ✅ 开始计时
    try:
        self.setup()
        self.execute()
    finally:
        self.end_time = time.time()  # ✅ 在 finally，teardown 之前
        self.teardown()
```

---

## 历史 Bug 详情（P-1 ~ P-15）

| ID | 文件 | 描述 | 类别 | 状态 |
|----|------|------|------|------|
| P-1 | instrument_manager.py | 三分异常分流（VisaIOError 重试） | 异常处理 | ✅ 已修复 |
| P-3 | AN87330.py | 通道号硬编码（input_ch=1, output_ch=2） | 仪器通信 | ✅ 已修复 |
| P-4 | _engine_api.py:139 | ultra_light_power IntVar truthy | UI绑定 | ✅ 已修复 |
| P-5 | test_engine.py | efficiency_min 死代码 | 测试执行 | ✅ 已修复 |
| P-6 | config_ui.py | _do_load_config 无 return | 配置读写 | ✅ 已修复 |
| P-7 | test_engine.py | FINISHED 状态缺失 | 测试执行 | ✅ 已修复 |
| P-8 | base.py | duration 包含 teardown 时间 | 测试执行 | ✅ 已修复 |
| P-9 | config_schema.py | build_specs_flat fallback 不一致 | 配置读写 | ✅ 已修复 |
| P-10 | base.py | 放电电流 3.0A → 2.0A | 测试执行 | ✅ 已修复 |
| P-11 | config_ui.py | load_config isinstance + DYN_ROW_FIELDS | 配置读写 | ✅ 已修复 |
| P-13 | _engine_api.py | get("充电器").get() == 1 判断 | UI绑定 | ✅ 确认无问题 |
| P-14 | 全部 | CASE_COLS = None | 报告生成 | ✅ 确认无问题 |
| P-15 | base.py | IDN 验证错误信息不足 | 仪器通信 | ✅ 已修复 |
| P-16 | _config_io.py | product_type IntVar truthy | UI绑定 | ✅ 已修复 |
