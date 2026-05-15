# 模块接口边界参考

> 各模块之间的调用契约。检视跨模块调用时查这里，防止接口不一致引入bug。

---

## config_schema.py ↔ _config_io.py

### build_specs_flat()

**签名：**
```python
def build_specs_flat(spec_vars: dict, protection_vars: dict) -> dict
```

**输入：** `app._spec_vars`，格式：
```python
{
    "Brown-in（V）": {"lo": StringVar, "hi": StringVar},
    "待机功耗（W）": {"lo": StringVar, "hi": StringVar, "enable": IntVar},
    ...
}
```

**输出：** specs_v2 字典，写入 JSON：
```python
{
    "Brown_in_V_lo": 0.42,   # float 或 None
    "Brown_in_V_hi": 0.55,
    ...
}
```

**关键规则：**
- key 格式：`{flat_key}_lo` / `{flat_key}_hi`
- flat_key 来自 SPECS_KEYS 的第一项（无空格/连字符）
- 值类型：float，NaN 时写入 `None`（JSON = null）

---

## save_config / load_config

### save_config()

```python
def save_config(app, path: str) -> None
```

**契约：** 将 app 上所有 UI 变量序列化为 JSON 文件，不抛异常。

### load_config()

```python
def load_config(app, path: str) -> None
```

**契约：** 从 JSON 文件恢复所有 UI 变量，不弹对话框。

**关键规则：**
- 若 JSON key 在 spec_vars 中找不到对应 label_text，静默跳过
- `build_specs_flat` fallback：先查 `specs_raw.get(label_text)`，再查 `specs_raw.get(flat_key)`（P-9 修复）

---

## _build_test_engine_config()

**签名：**
```python
def _build_test_engine_config(self, checked_cases: list[str]) -> dict
```

**输出结构：**
```python
{
    "product_info": {
        "product_name": str,
        "product_type": "charger" | "adapter",
        "specs_v2": dict,        # build_specs_flat() 输出
        "power_segment": bool,
        "hv_power": float,
        "lv_power": float,
        "ultra_light_power": float,
        ...
    },
    "test_params": {
        "osc_in_ch": str,        # "CH1"~"CH4"
        "eload_vout1_ch": str,
        "eload_vout2_ch": str,
        "dyn_large": [dict, ...], # rows_to_dicts 输出
        ...
    },
    "case_params": {
        key: {
            "conditions": [dict, ...],  # [{vin, freq, proto, vout, iout}, ...]
            "specs": dict              # specs_v2 子集
        }
    }
}
```

---

## TestEngine.run_case()

```python
def run_case(self, case_key: str, params: dict) -> dict
```

**params 输入：**
```python
{
    "conditions": [...],   # 测试条件列表
    "specs": {...}        # 产品规格（6级/7级能效判断用）
}
```

**输出：** result dict，包含 `case_key`, `pass`, `sub_results`, `error` 等。

---

## Case 基类（test_cases/base.py）

### setup()

**必须做的事情：**
1. `self._input_ch` / `self._output_ch` 缓存（功率计通道角色）
2. `self._cached_params = self.params`（参数缓存）
3. 所有 `self.params["xxx"]` 在 setup 中一次性读取并缓存

### execute()

**规则：** 只使用 setup 中缓存的变量，**不调用 `self.params.get()`**。

### sub_results 字段规范

每个测试用例的 `sub_results` 中的字段名必须与 `report/_mappings.py` 的 `COLUMN_KEYS` 一致：

| 字段 | 类型 | 说明 |
|-----|------|------|
| `vin` | str | 隐含在输入条件字符串里 |
| `vout` | float | 输出电压 |
| `iout` | float | 输出电流 |
| `负载点` | str | "100%" / "75%" 等 |
| `效率(%)` | float | 实测效率 |

---

## instrument_manager.apply_channel_roles()

```python
def apply_channel_roles(pwrmeter, config: dict) -> None
```

**config 格式：**
```python
{
    "pwr_in_v_ch": "CH1",
    "pwr_in_i_ch": "CH1",
    "pwr_out_v_ch": "CH2",
    "pwr_out_i_ch": "CH2",
}
```

**WT333E：** 直接写 `pwrmeter._input_ch = 1`（假设 CH1）

**AN87330：** 调用 `pwrmeter.set_channel_roles(input_voltage_ch, output_voltage_ch)`
- 输入电压通道 → `self._input_ch`
- 输出电压通道 → `self._output_ch`
- 内部调用 `_parse_channel("CH1")` → 返回 `1`

---

## 仪器驱动基类（instruments/base.py）

### 验证失败异常

```python
class InstrumentError(Exception):
    """永久性仪器故障，不重试"""
    pass
```

**IDN 验证错误信息格式：**
```python
f"身份验证失败 [{cls_name}@{self._address}]\n  实测IDN: {self._idn}"
```
