# 测试平台架构与设计规则

> 本文档是测试平台架构的权威参考。新增功能或修改现有代码时，请务必遵循本文档规则。

---

## 一、系统架构

### 1.1 整体数据流

```
config_ui.py (UI 层)
    ├── 收集所有 UI 控件值（tk Variables）
    └── 调用 EngineAPI._build_test_engine_config()
            └── 构建完整配置字典 config_dict
                    │
                    ▼
test_engine.py (引擎层 - TestEngine)
    ├── __init__(config, instruments)
    ├── load_cases_from_config(test_cases_config)
    │       └── _load_single_case() → 动态 import + 实例化
    │               └── _create_fresh_instance()  ← 唯一配置入口
    │                       └── _inject_common_params()  ← 注入所有参数
    │
    ├── run_all() / run_single()
    │       └── case.run(instruments)
    │               └── setup() → execute() → verify() → teardown()
    │
    └── _progress_callback / _log_callback → UI 进度条/日志

test_cases/base.py (基类 - TestCase)
    ├── setup()  ← 通用仪器初始化 + specs_v2 合并到 self.spec
    ├── execute() ← 抽象方法，子类实现
    └── verify() ← 子类实现判定逻辑

test_cases/input_tests/InputVoltageRangeTest.py (用例层)
    └── 具体测试逻辑
```

### 1.2 配置字典结构（`_build_test_engine_config` 返回值）

```python
{
    "product_info": {
        "product_name": str,
        "input_voltage_lo": float,
        "input_voltage_hi": float,
        "output_voltage": float,
        "output_power": float,
        "product_type": "charger" | "adapter",
        "load_startup_enabled": bool,
        "load_startup_current": float,
        "load_startup_voltage": float,
        "power_segment": int,          # 0=禁用, 1=启用
        "hv_power": float,            # 高压段功率
        "lv_power": float,            # 低压段功率
        "specs_v2": {                  # 扁平字典，key 带后缀
            "电压精度_lo": float,
            "电压精度_hi": float,
            "6级能效要求_pct_enable": float,  # 0 或 1
            ...
        },
        "protection_logic_v2": {       # 扁平字典
            "输入欠压保护_mode": "self" | "latch" | "",
            "输出过压保护_mode": ...,
            "输出过流保护_mode": ...,
        },
    },
    "dut": {
        "name": str,
        "output_voltage": float,
        "output_power": float,
        "input_voltage_min": float,
        "input_voltage_max": float,
    },
    "test_conditions": [cond_dict, ...],   # 本次运行的所有条件
    "filtered_conditions_v2": {             # 按 case_key 分组
        "InputVoltageRangeTest": [cond_dict, ...],
        "InputUnderVoltageTest": [cond_dict, ...],
        ...
    },
    "test_settings": {
        "osc_input_ch": "CH4",
        "osc_input_attn": 1.0,
        "osc_output_ch": "CH2",
        "osc_output_attn": 1.0,
        "osc_dynamic_ch": "CH2",
        "osc_dynamic_attn": 1.0,
    },
    "test_params": {
        "pwr_in_v_ch": "CH1",
        "pwr_in_i_ch": "CH1",
        "pwr_out_v_ch": "CH1",
        "pwr_out_i_ch": "CH1",
        "eload_vout1_ch": "CH1",
        "eload_vout2_ch": "CH2",
        "dyn_large": [[val, ...], ...],   # tree values
        "dyn_small": [[val, ...], ...],
        "warmup": "10",
        "onoff_cycle": "10-10",
        "short_cycle": "10-10",
    },
    "test_cases": {                         # 启用的用例列表
        "input_tests": {"InputVoltageRangeTest": True, ...},
        "output_tests": {...},
        ...
    },
}
```

### 1.3 执行流程

1. **UI 收集**：用户填写配置 → `EngineAPI._build_test_engine_config(checked_cases)` 构建完整配置
2. **引擎初始化**：`TestEngine(cfg, instruments)` 持有配置和仪器引用
3. **用例加载**：`load_cases_from_config()` → 对每个启用的 case_key：
   - `_load_single_case()` 动态 import 模块类
   - `_create_fresh_instance()` 创建新实例（避免复用同一实例导致状态污染）
   - `_inject_common_params()` 将 config 中的值注入 `case.params`
4. **运行**：`run_all()` 遍历 suite，调用 `case.run(instruments)`：
   - `setup()` → `execute()` → `verify()` → `teardown()`
5. **结果回调**：`_progress_callback` 将实时进度和测量数据推送至 UI

---

## 二、用例注册表（CASE_REGISTRY）

位于 `test_engine.py`，是唯一的用例注册入口。

```python
CASE_REGISTRY = {
    "InputVoltageRangeTest": {
        "module": "test_cases.input_tests.InputVoltageRangeTest",
        "voltage_segment": True,   # True = 按 (proto,vout,iout) 分组取最高 Vin
        "cn_name": "输入电压范围测试",
    },
    ...
}
```

新增用例只需在此添加一行，所有映射（`CASE_CN_NAMES`、`CASE_MODULE_MAP`）自动派生。

---

## 三、引擎参数注入规则（`_inject_common_params`）

`TestEngine._inject_common_params(case, case_key)` 在每次创建用例实例时调用，将配置透传到 `case.params`。

| `case.params` key | 数据来源 | 说明 |
|---|---|---|
| `osc_input_ch` | `test_settings.osc_input_ch` | 示波器输入通道（去"CH"前缀）|
| `osc_input_attn` | `test_settings.osc_input_attn` | 示波器输入衰减 |
| `osc_output_ch` | `test_settings.osc_output_ch` | 示波器输出通道 |
| `osc_output_attn` | `test_settings.osc_output_attn` | 示波器输出衰减 |
| `osc_dynamic_ch` | `test_settings.osc_dynamic_ch` | 示波器动态通道 |
| `osc_dynamic_attn` | `test_settings.osc_dynamic_attn` | 示波器动态衰减 |
| `pwr_in_i_ch` | `test_params.pwr_in_i_ch` | 功率计输入电流通道 |
| `pwr_in_v_ch` | `test_params.pwr_in_v_ch` | 功率计输入电压通道 |
| `pwr_out_v_ch` | `test_params.pwr_out_v_ch` | 功率计输出电压通道 |
| `pwr_out_i_ch` | `test_params.pwr_out_i_ch` | 功率计输出电流通道 |
| `load_startup_enabled` | `product_info.load_startup_enabled` | 带载开机使能 |
| `load_startup_current` | `product_info.load_startup_current` | 带载开机电流 |
| `load_startup_voltage` | `product_info.load_startup_voltage` | 带载开机电压 |
| `dut_name` | `dut.name` | DUT 名称 |
| `dut_model` | `dut.model` | DUT 型号 |
| `input_voltage` | `dut.output_voltage` | 输入电压（注意：实际是 output_voltage 字段）|
| `output_voltage` | `dut.output_voltage` | 输出电压 |
| `output_current` | `dut.output_current` | 输出电流 |
| `efficiency_min` | `dut.target_efficiency` | 目标效率（spec.efficiency_min 为空时）|
| `input_voltage_lo` | `product_info.input_voltage_lo` | 输入电压下限 |
| `input_voltage_hi` | `product_info.input_voltage_hi` | 输入电压上限 |
| `power_segment` | `product_info.power_segment` | 功率分段标志（0/1）|
| `hv_power` | `product_info.hv_power` | 高压段功率 |
| `lv_power` | `product_info.lv_power` | 低压段功率 |
| `dyn_large_settings` | `test_params.dyn_large` | 大动态测试参数 |
| `dyn_small_settings` | `test_params.dyn_small` | 小动态测试参数 |
| `result_dir` | `_result_dir`（引擎设置）| 结果保存目录 |
| `osc_waveform_dir` | `result_dir/测试波形` | 波形保存目录 |
| `test_conditions` | `filtered_conditions_v2[case_key]` | **用例专用**：该用例的条件列表 |
| `product_type` | `product_info.product_type` | "charger" 或 "adapter" |
| `test_params` | `test_params`（整个字典）| 透传 test_params |
| `product_info` | `product_info`（整个字典）| 透传 product_info |
| `specs` | `product_info.specs_v2` | 规格字典（用于 InputEfficiencyTest 等）|
| `protection_logic` | `product_info.protection_logic_v2` | 保护逻辑字典 |
| `warmup` | `test_params.warmup` | 预热时间字符串 |

---

## 四、UI 参数新增规则

当需要在 UI 上新增一个可配置的参数时，需要按以下步骤在三个文件中添加代码：

### 步骤 1：在 `config_ui.py` 创建 tk Variable

在 `__init__` 方法中创建 tk 变量（如 `tk.StringVar`、`tk.IntVar`、`tk.DoubleVar`）。

```python
# 示例：在 __init__ 中
self._my_param_var = tk.StringVar(value="default_value")
```

然后在 UI 的 `__init__` 或专门的方法中用这个变量绑定控件。

### 步骤 2：在 `_engine_api._build_test_engine_config` 中添加到 config

在 `_build_test_engine_config` 中，找到合适的 section（`product_info` / `test_settings` / `test_params`），将变量值加入返回字典：

```python
# 示例：加入 product_info
"product_info": {
    ...
    "my_param": self._my_param_var.get(),
},

# 或 test_params
"test_params": {
    ...
    "my_param": self._my_param_var.get(),
},
```

### 步骤 3：如果引擎需要将该参数传给用例，在 `_inject_common_params` 中注入

```python
case.params["my_param"] = self.config.get("test_params", {}).get("my_param", default_value)
```

### 步骤 4：如果用例需要使用该参数，在用例的 `setup()` 中缓存

```python
def setup(self, instruments):
    super().setup(instruments)
    self.my_param = self.params.get("my_param", default_value)
```

---

## 五、测试用例添加规则

### 5.1 在 CASE_REGISTRY 中注册

在 `test_engine.py` 的 `CASE_REGISTRY` 字典中添加一行：

```python
"MyNewTest": {
    "module": "test_cases.category_tests.MyNewTest",
    "voltage_segment": False,   # True = 按 (proto,vout,iout) 分组取最高 Vin
    "cn_name": "我的新测试",
},
```

### 5.2 创建用例文件

在对应目录下创建文件，如 `test_cases/category_tests/MyNewTest.py`：

```python
# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from test_cases.base import TestCase
from logger_config import info

class MyNewTest(TestCase):
    def __init__(self, ...):
        # 不要在这里设置 self.test_conditions！
        super().__init__(name="MyNewTest", ...)
    
    def setup(self, instruments):
        super().setup(instruments)
        # 缓存所有需要的参数
        self.xxx = self.params.get("xxx", default)
    
    def execute(self, instruments):
        # 实现测试逻辑
        pass
    
    def verify(self) -> bool:
        return True
```

---

## 六、测试用例内部参数调用规则

### ⚠️ 核心黄金规则

#### 1. `test_conditions` 是 list[dict]，不是 tuple

```python
# ✅ 正确：dict 访问
for cond in self.test_conditions:
    vin = cond.get("vin")
    freq = cond.get("freq")
    proto = cond.get("proto")
    vout = cond.get("vout")
    iout = cond.get("iout")

# ❌ 错误：索引访问
for cond in self.test_conditions:
    vin = cond[0]   # 永远不要这样写
```

#### 2. `setup()` 必须缓存所有参数，execute() 永远不调用 `self.params.get()`

```python
# ✅ 正确
def setup(self, instruments):
    super().setup(instruments)
    self.vin_lo = float(self.params.get("input_voltage_lo", 90.0))
    self.osc_ch = int(self.params.get("osc_output_ch", 2))
    self.osc_attn = float(self.params.get("osc_output_attn", 1.0))
    self.test_conditions = self.test_conditions or self.params.get("test_conditions", [])

def execute(self, instruments):
    for cond in self.test_conditions:
        vin = cond.get("vin")
        # 使用 self.vin_lo, self.osc_ch ... 而不是 self.params.get()
```

#### 3. `__init__` 中不要设置 `self.test_conditions`

基类 `TestCase` 已有 `test_conditions: list = field(default_factory=list)` 字段。
在 `__init__` 中写 `self.test_conditions = ...` 会**遮蔽（shadow）基类字段**，导致 `setup()` 中的逻辑无法正常工作。

正确做法：让 `setup()` 处理它：

```python
# ✅ 正确
def setup(self, instruments):
    super().setup(instruments)
    self.test_conditions = self.test_conditions or self.params.get("test_conditions", [])
    # 如果 test_conditions 仍然为空（比如用例没有条件），使用 getattr
    self.test_conditions = getattr(self, "test_conditions", []) or self.params.get("test_conditions", [])

# ❌ 错误：__init__ 中不要写
def __init__(self, ...):
    self.test_conditions = test_conditions or []  # 这样会 shadow 基类字段！
```

#### 4. 规格（spec）字段命名：`_lo` / `_hi` / `_pct` / `_pct_enable` 后缀

`base.py setup()` 会自动将 `specs_v2` 中以 `_lo`、`_hi`、`_pct_enable`、`_pct` 结尾的 key 合并到 `self.spec`。

```python
# specs_v2 中的 key（如 "电压精度_lo", "电压精度_hi"）
# 自动合并到 self.spec["电压精度_lo"], self.spec["电压精度_hi"]

# 使用时
vout_min = self.spec.get("电压精度_lo")
vout_max = self.spec.get("电压精度_hi")
```

#### 5. 保护逻辑（protection_logic）命名：`类别_mode`

`PROTECTION_LOGIC_FIELDS` 中定义的字段，格式为 `{UI标签}_mode`，值可能是 `"self"`、`"latch"` 或 `""`。

```python
# 获取输出过流保护模式
ocp_mode = self.protection_logic.get("输出过流保护_mode", "")
# ocp_mode = "self"（自恢复）或 "latch"（锁死）或 ""（未配置）
```

---

## 七、字段命名规范

### 7.1 specs_v2（产品规格）字段命名

扁平的 `specs_v2` 字典中，key 的命名规则：

| 后缀 | 含义 | 示例 |
|---|---|---|
| `_lo` | 下限值 | `电压精度_lo` = 0.5 |
| `_hi` | 上限值 | `电压精度_hi` = 5.0 |
| `_pct` | 百分比值（无 lo/hi 之分）| `电压精度_pct` = 5.0 |
| `_pct_enable` | 百分比规格的使能标志（0/1）| `6级能效要求_pct_enable` = 1 |

### 7.2 protection_logic_v2（保护逻辑）字段命名

格式：`{UI显示名称}_mode`

| UI 标签 | config key | 有效值 |
|---|---|---|
| 输入欠压保护 | `输入欠压保护_mode` | `"self"` / `"latch"` / `""` |
| 输出过压保护 | `输出过压保护_mode` | 同上 |
| 输出过流保护 | `输出过流保护_mode` | 同上 |

### 7.3 test_conditions 字段

固定五个字段（参见 `config_schema.COND_FIELDS`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `vin` | float | 输入电压（Vac）|
| `freq` | float | 输入频率（Hz）|
| `proto` | str | 协议标签，如 `"PD"`, `"QC3.0"` |
| `vout` | float | 输出电压（V）|
| `iout` | float | 输出电流（A）|

### 7.4 示波器通道字段

| `case.params` key | 来源 | 说明 |
|---|---|---|
| `osc_input_ch` | test_settings | 输入通道（不带"CH"前缀的数字）|
| `osc_output_ch` | test_settings | 输出通道 |
| `osc_dynamic_ch` | test_settings | 动态测试通道 |
| `osc_input_attn` | test_settings | 输入通道衰减比 |
| `osc_output_attn` | test_settings | 输出通道衰减比 |
| `osc_dynamic_attn` | test_settings | 动态通道衰减比 |

### 7.5 功率计通道字段

| `case.params` key | 来源 |
|---|---|
| `pwr_in_v_ch` | test_params |
| `pwr_in_i_ch` | test_params |
| `pwr_out_v_ch` | test_params |
| `pwr_out_i_ch` | test_params |
