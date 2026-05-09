# 测试平台架构与设计规则

> 本文档是测试平台架构的权威参考。新增功能或修改现有代码时，请务必遵循本文档规则。
> 最后更新：2026-05-09

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
    │       └── suite.run(instruments)
    │               └── case.run(instruments)
    │                       └── setup() → execute() → verify() → teardown()
    │
    └── _progress_callback / _log_callback → UI 进度条/日志

test_cases/base.py (基类 - TestCase / TestSuite)
    ├── setup()   ← 通用仪器初始化 + specs_v2 合并到 self.spec
    ├── execute() ← 抽象方法，子类实现
    ├── verify() ← 抽象方法，子类实现
    └── teardown() ← 可选重写

test_cases/{category}/xxxTest.py (用例层)
    └── 具体测试逻辑

report/ (报告生成层)
    ├── _mappings.py   ← 映射表 + 列定义
    ├── styles.py      ← Excel 样式函数
    ├── _data.py       ← _flatten() 纯数据变换
    ├── _xlsx_post.py  ← _fix_rels() + auto_generate()
    └── writer.py      ← 核心逻辑（generate_excel 等）
        └── report_generator.py ← 兼容垫片（from report import ...）

instrument_manager.py (仪器管理层)
    └── InstrumentManager  ← 统一连接/断开/仿真
```

### 1.2 项目文件结构

```
自动化测试平台/
├── config_ui.py              # Tkinter 主 UI
├── config_schema.py          # 配置结构定义（CASE_REGISTRY, DUT 模板等）
├── test_engine.py            # 测试执行引擎
├── instrument_manager.py     # 仪器管理器
├── logger_config.py         # 日志配置
├── report_generator.py       # 兼容垫片（入口）
├── report/                  # 报告生成模块
│   ├── __init__.py         # 包入口，re-export 公开 API
│   ├── _mappings.py        # 映射表 + 列定义（无外部依赖）
│   ├── styles.py            # Excel 样式函数
│   ├── _data.py             # _flatten() 纯数据变换
│   ├── _xlsx_post.py       # _fix_rels() + auto_generate()
│   └── writer.py            # 核心逻辑
├── test_cases/
│   ├── base.py             # TestCase / TestSuite 基类
│   ├── input_tests/        # 输入类测试用例
│   ├── output_tests/        # 输出类测试用例
│   ├── protection_tests/    # 保护功能测试用例
│   └── protocol_tests/      # 协议测试用例
├── instruments/             # 仪器驱动
│   ├── base.py
│   ├── ac_source/          # IT7321 / IT7322
│   ├── dc_source/          # IT6333A
│   ├── electronic_load/    # IT8511 / IT8512 / IT8701P
│   ├── oscilloscope/       # DSOX4024A
│   ├── power_meter/       # WT322E / WT333E
│   └── sniffer/            # IP2716 诱骗器
└── ui/
    └── results/            # 测试结果输出目录
```

---

## 二、用例注册表（CASE_REGISTRY）

位于 `config_schema.py`，是唯一的用例注册入口。

```python
CASE_REGISTRY = {
    # input_tests
    "InputVoltageRangeTest":    {"module": "...", "cn_name": "输入电压范围测试", "filter_mode": "voltage_segment"},
    "InputUnderVoltageTest":   {"module": "...", "cn_name": "输入欠压测试",        "filter_mode": "min_vin"},
    "InputDipTest":            {"module": "...", "cn_name": "输入跌落测试",        "filter_mode": "voltage_segment"},
    "InputNoLoadPowerTest":    {"module": "...", "cn_name": "输入空载功率测试",    "filter_mode": "passthrough"},
    "InputEfficiencyTest":     {"module": "...", "cn_name": "输入效率测试",        "filter_mode": "passthrough"},
    # output_tests
    "OutputPowerOnOffTest":    {"module": "...", "cn_name": "输出开关机测试",      "filter_mode": "passthrough"},
    "OutputRiseTimeTest":      {"module": "...", "cn_name": "输出电压上升时间测试", "filter_mode": "min_vout"},
    "OutputStartupDelayTest":   {"module": "...", "cn_name": "输出开机延迟时间测试", "filter_mode": "min_vout"},
    "OutputRippleNoiseTest":   {"module": "...", "cn_name": "输出纹波噪声测试",    "filter_mode": "passthrough"},
    "OutputRippleLoadScanTest":{"module": "...", "cn_name": "输出纹波负载扫描测试", "filter_mode": "passthrough"},
    "OutputRippleInputScanTest":{"module": "...","cn_name": "输出纹波输入扫描测试",  "filter_mode": "voltage_segment"},
    "OutputDynamicTest":       {"module": "...", "cn_name": "输出动态测试",        "filter_mode": "passthrough"},
    # protection_tests
    "OutputOcpProtectTest":    {"module": "...", "cn_name": "输出过流保护测试",    "filter_mode": "passthrough"},
    "OutputScpProtectTest":    {"module": "...", "cn_name": "输出短路保护测试",    "filter_mode": "passthrough"},
    # protocol_tests
    "PDProtocolTest":           {"module": "...", "cn_name": "PD协议",              "filter_mode": "passthrough"},
    "QCProtocolTest":          {"module": "...", "cn_name": "QC协议",              "filter_mode": "passthrough"},
    "AFCProtocolTest":         {"module": "...", "cn_name": "AFC协议",             "filter_mode": "passthrough"},
    "FCPProtocolTest":         {"module": "...", "cn_name": "FCP协议",             "filter_mode": "passthrough"},
}
```

- `module`：模块路径（相对于项目根目录）
- `cn_name`：中文显示名
- `filter_mode`：结果分组过滤模式
  - `voltage_segment`：按 (proto, vout, iout) 分组，取最高 Vin
  - `min_vin`：取最低 Vin
  - `min_vout`：取最低 Vout
  - `passthrough`：不做过滤

新增用例只需在此添加一行，`CASE_CN_NAMES`、`CASE_MODULE_MAP` 自动派生。

---

## 三、配置字典结构（`_build_test_engine_config` 返回值）

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
        "hv_power": float,
        "lv_power": float,
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
        "dyn_large": [[val, ...], ...],
        "dyn_small": [[val, ...], ...],
        "warmup": "10",
        "onoff_cycle": "10-10",
        "short_cycle": "10-10",
    },
    "test_cases": {
        "input_tests": {"InputVoltageRangeTest": True, ...},
        "output_tests": {...},
        ...
    },
}
```

---

## 四、执行流程

1. **UI 收集**：用户填写配置 → `EngineAPI._build_test_engine_config(checked_cases)` 构建完整配置
2. **引擎初始化**：`TestEngine(cfg, instruments)` 持有配置和仪器引用
3. **用例加载**：`load_cases_from_config()` → 对每个启用的 case_key：
   - `_load_single_case()` 动态 import 模块类
   - `_create_fresh_instance()` 创建新实例（避免复用同一实例导致状态污染）
   - `_inject_common_params()` 将配置透传到 `case.params`
4. **运行**：`run_all()` 遍历 suite，调用 `case.run(instruments)`：
   - `setup()` → `execute()` → `verify()` → `teardown()`
5. **结果回调**：`_progress_callback` 将实时进度和测量数据推送至 UI
6. **报告生成**：`generate_excel()` 读取 JSON 结果，输出 Excel 报告

---

## 五、引擎参数注入规则（`_inject_common_params`）

`TestEngine._inject_common_params(case, case_key)` 在每次创建用例实例时调用。

| `case.params` key | 数据来源 | 说明 |
|---|---|---|
| `osc_input_ch` | `test_settings.osc_input_ch` | 示波器输入通道 |
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
| `output_voltage` | `dut.output_voltage` | 输出电压 |
| `output_current` | `dut.output_current` | 输出电流 |
| `efficiency_min` | `dut.target_efficiency` | 目标效率 |
| `input_voltage_lo` | `product_info.input_voltage_lo` | 输入电压下限 |
| `input_voltage_hi` | `product_info.input_voltage_hi` | 输入电压上限 |
| `power_segment` | `product_info.power_segment` | 功率分段标志 |
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
| `specs` | `product_info.specs_v2` | 规格字典 |
| `protection_logic` | `product_info.protection_logic_v2` | 保护逻辑字典 |
| `warmup` | `test_params.warmup` | 预热时间字符串 |

---

## 六、仪器驱动架构

### 驱动模型映射

`InstrumentManager._get_model_class_map()` 动态构建 `{category: {model_name: DriverClass}}`。

| 类别 | 型号 | 驱动文件 |
|---|---|---|
| `AC_SOURCE` | IT7321, IT7322 | `instruments/ac_source/IT7321.py` |
| `DC_SOURCE` | IT6333A | `instruments/dc_source/IT6333A.py` |
| `ELECTRONIC_LOAD` | IT8511, IT8512, IT8701P | `instruments/electronic_load/IT8511.py` 等 |
| `OSCILLOSCOPE` | DSOX4024A | `instruments/oscilloscope/DSOX4024A.py` |
| `POWER_METER` | WT322E, WT333E | `instruments/power_meter/WT322E.py` 等 |
| `SNIFFER` | IP2716 | `instruments/sniffer/IP2716.py` |

### 仿真模式

无仪器时调用 `instrument_manager.enable_simulation_mode()`，所有仪器返回模拟数据，不尝试真实连接。

---

## 七、报告生成架构

```
report_generator.py  ← 兼容垫片（re-export report 包 API）
       ↓
report/__init__.py  ← 包入口
       ↓
report/
  ├── _mappings.py    映射表 + 列定义（GLOBAL_COLS, CASE_NAME_CN_MAP 等）
  ├── styles.py       _mkstyle() / _rfill() / _fmt()
  ├── _data.py        _flatten() 纯数据变换
  ├── _xlsx_post.py   _fix_rels() + auto_generate()
  └── writer.py       generate_excel() + _write_case_sheet() + _write_waveform_sheet()
```

**生成流程**：
1. `generate_excel(results_path)` 读取 JSON 结果
2. 写入 Sheet 1（汇总）
3. 遍历结果调用 `_write_case_sheet()` 写入每个用例 Sheet
4. 调用 `_write_waveform_sheet()` 写入波形 Sheet
5. 保存后调用 `_fix_rels()` 修复 openpyxl 超链接 rels 问题

---

## 八、用例添加规则

### 8.1 在 CASE_REGISTRY 中注册

在 `config_schema.py` 的 `CASE_REGISTRY` 字典中添加一行：

```python
"MyNewTest": {
    "module": "test_cases.category_tests.MyNewTest",
    "cn_name": "我的新测试",
    "filter_mode": "passthrough",
},
```

### 8.2 创建用例文件

```python
# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from test_cases.base import TestCase

class MyNewTest(TestCase):
    def __init__(self):
        super().__init__(
            name="MyNewTest",
            instruments=["AC_SOURCE", "ELOAD", "POWER_METER"],
            params={},
        )

    def setup(self, instruments):
        super().setup(instruments)
        # ✅ 必须：从 params 缓存，不要在 execute() 里直接读 self.params
        self.test_conditions = self.test_conditions or self.params.get("test_conditions", [])
        self.xxx = self.params.get("xxx", default_value)

    def execute(self, instruments):
        # 实现测试逻辑
        pass

    def verify(self) -> bool:
        return True
```

---

## 九、核心黄金规则

### 规则 0：`setup()` 中必须显式缓存 `test_conditions`

**常见 bug：`__init__` 接收 `test_conditions=None`，父类 `field(default_factory=list)` 被 `None` 覆盖，execute 始终拿到空列表。**

```python
def setup(self, instruments):
    super().setup(instruments)
    # ✅ 必须：重新从 params 读取并缓存
    self.test_conditions = self.test_conditions or self.params.get("test_conditions", [])
```

### 规则 1：`test_conditions` 是 `list[dict]`，不是 tuple

```python
# ✅ 正确：dict 访问
for cond in self.test_conditions:
    vin = cond.get("vin")

# ❌ 错误：索引访问
vin = cond[0]
```

### 规则 2：`setup()` 必须缓存所有参数，execute() 永远不调用 `self.params.get()`

```python
def setup(self, instruments):
    super().setup(instruments)
    self.vin_lo = float(self.params.get("input_voltage_lo", 90.0))
    self.osc_ch = int(self.params.get("osc_output_ch", 2))

def execute(self, instruments):
    # ✅ 使用 self.vin_lo 而不是 self.params.get("input_voltage_lo")
```

### 规则 3：`__init__` 中不要设置 `self.test_conditions`

基类已有 `test_conditions: list = field(default_factory=list)`。在 `__init__` 中写 `self.test_conditions = ...` 会遮蔽（shadow）基类字段，导致 `setup()` 中的缓存逻辑失效。

---

## 十、字段命名规范

### 10.1 specs_v2 字段命名

| 后缀 | 含义 | 示例 |
|---|---|---|
| `_lo` | 下限值 | `电压精度_lo` = 0.5 |
| `_hi` | 上限值 | `电压精度_hi` = 5.0 |
| `_pct` | 百分比值 | `纹波_pct` = 5.0 |
| `_pct_enable` | 使能标志（0/1）| `6级能效要求_pct_enable` = 1 |

### 10.2 protection_logic_v2 字段命名

格式：`{UI显示名称}_mode`，值可能是 `"self"`（自恢复）、`"latch"`（锁死）或 `""`（未配置）。

### 10.3 test_conditions 固定字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `vin` | float | 输入电压（Vac）|
| `freq` | float | 输入频率（Hz）|
| `proto` | str | 协议标签，如 `"PD"`, `"QC3.0"` |
| `vout` | float | 输出电压（V）|
| `iout` | float | 输出电流（A）|

### 10.4 示波器/功率计通道字段

| params key | 来源 | 说明 |
|---|---|---|
| `osc_input_ch` | test_settings | 输入通道（不带"CH"前缀的数字）|
| `osc_output_ch` | test_settings | 输出通道 |
| `osc_dynamic_ch` | test_settings | 动态测试通道 |
| `osc_*_attn` | test_settings | 各通道衰减比 |
| `pwr_in_v_ch` | test_params | 功率计输入电压通道 |
| `pwr_in_i_ch` | test_params | 功率计输入电流通道 |
| `pwr_out_v_ch` | test_params | 功率计输出电压通道 |
| `pwr_out_i_ch` | test_params | 功率计输出电流通道 |

---

## 十一、UI 参数新增规则

当需要在 UI 上新增一个可配置的参数时，需要按以下步骤在三个文件中添加代码：

### 步骤 1：在 `config_ui.py` 创建 tk Variable

```python
self._my_param_var = tk.StringVar(value="default_value")
```

### 步骤 2：在 `_engine_api._build_test_engine_config` 中添加到 config

```python
"product_info": {
    "my_param": self._my_param_var.get(),
},
```

### 步骤 3：在 `_inject_common_params` 中注入（如果需要传给用例）

```python
case.params["my_param"] = self.config.get("product_info", {}).get("my_param", default_value)
```

### 步骤 4：在用例的 `setup()` 中缓存

```python
self.my_param = self.params.get("my_param", default_value)
```
