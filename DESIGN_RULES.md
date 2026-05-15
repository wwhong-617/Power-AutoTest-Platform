# 测试平台架构与设计规则

> 本文档是测试平台架构的权威参考。新增功能或修改现有代码时，请务必遵循本文档规则。
> 最后更新：2026-05-16

---

## 一、架构总览

### 1.1 文件结构

```
自动化测试平台/
├── config_ui.py              # Tkinter 主 UI
├── config_schema.py          # CASE_REGISTRY、用例注册表
├── test_engine.py            # 测试引擎（加载、运行、参数注入）
├── instrument_manager.py     # 仪器连接管理
├── report_generator.py       # 报告入口（兼容垫片）
├── report/                   # 报告生成模块
│   ├── _mappings.py          # 列定义、映射表
│   ├── writer.py             # 核心生成逻辑
│   ├── styles.py             # Excel 样式
│   ├── _data.py              # 数据展开
│   └── _xlsx_post.py         # xlsx 后处理
├── test_cases/
│   ├── base.py               # TestCase / TestSuite 基类
│   ├── input_tests/          # 输入类测试
│   ├── output_tests/         # 输出类测试
│   ├── protection_tests/     # 保护功能测试
│   └── protocol_tests/       # 协议测试
├── instruments/              # 仪器驱动
│   ├── base.py               # 基类（InstrumentError, InstrumentConnectionState）
│   ├── ac_source/            # IT7321 / IT7322
│   ├── dc_source/            # IT6333A
│   ├── electronic_load/      # IT8511 / IT8512 / IT8701P
│   ├── oscilloscope/         # DSOX4024A
│   ├── power_meter/          # WT322E / WT333E / AN87330
│   └── sniffer/              # IP2716 诱骗器
└── ui/
    ├── _engine_api.py        # 配置构建（_build_test_engine_config）
    ├── _config_io.py         # 配置持久化（save/load）
    └── results/              # 测试结果输出目录
```

### 1.2 数据流

```
config_ui.py
    └─ EngineAPI._build_test_engine_config()
            └─ test_engine.TestEngine
                    ├─ load_cases_from_config() → 动态加载用例类
                    │       └─ _create_fresh_instance() → _inject_common_params()
                    ├─ run_all() / run_single()
                    │       └─ case.run(instruments) → setup / execute / verify / teardown
                    └─ _progress_callback → UI 进度/日志
```

### 1.3 报告生成

```
report_generator.py（兼容垫片）
    └─ report/
            ├─ _mappings.py   # GLOBAL_COLS、CASE_NAME_CN_MAP
            ├─ writer.py      # generate_excel() + _write_case_sheet()
            ├─ styles.py      # 样式函数
            ├─ _data.py       # _flatten()
            └─ _xlsx_post.py  # _fix_rels() + auto_generate()
```

---

## 二、用例注册表

位于 `config_schema.py`，是唯一的用例注册入口。新增用例只需在此添加一行。

```python
CASE_REGISTRY = {
    "InputVoltageRangeTest":  {"module": "...", "cn_name": "输入电压范围测试",     "filter_mode": "voltage_segment"},
    "InputEfficiencyTest":   {"module": "...", "cn_name": "输入效率测试",         "filter_mode": "passthrough"},
    "OutputPowerOnOffTest":  {"module": "...", "cn_name": "输出开关机测试",       "filter_mode": "passthrough"},
    "OutputRippleNoiseTest": {"module": "...", "cn_name": "输出纹波噪声测试",     "filter_mode": "passthrough"},
    # ... 其他用例
}
```

`filter_mode` 说明：
- `voltage_segment`：按 (proto, vout, iout) 分组，取最高 Vin
- `min_vin`：取最低 Vin
- `min_vout`：取最低 Vout
- `passthrough`：不做过滤

---

## 三、核心黄金规则

### 规则 0：`setup()` 中必须显式缓存 `test_conditions`

常见 bug：`__init__` 接收 `test_conditions=None`，基类 `field(default_factory=list)` 被覆盖，execute 始终拿到空列表。

```python
def setup(self, instruments):
    super().setup(instruments)
    self.test_conditions = self.test_conditions or self.params.get("test_conditions", [])
```

### 规则 1：`test_conditions` 是 `list[dict]`，不是 tuple

```python
for cond in self.test_conditions:   # ✅ dict 访问
    vin = cond.get("vin")
```

### 规则 2：`setup()` 必须缓存所有参数，execute() 永远不调用 `self.params.get()`

```python
def setup(self, instruments):
    super().setup(instruments)
    self.vin_lo = float(self.params.get("input_voltage_min", 90.0))  # ✅ 缓存

def execute(self, instruments):
    value = self.vin_lo   # ✅ 用缓存的属性
```

### 规则 3：`__init__` 中不要设置 `self.test_conditions`

基类已有 `test_conditions: list = field(default_factory=list)`。在 `__init__` 中赋值会遮蔽（shadow）基类字段，导致 `setup()` 中的缓存逻辑失效。

### 规则 4：仪器驱动中的 logger 必须定义为 `self.logger`

```python
def __init__(self, ...):
    import logging
    self.logger = logging.getLogger("PowerAutoTest")   # ✅ 实例变量
    # ❌ logger = logging.getLogger(...)  ← 局部变量，实例方法无法访问
```

### 规则 5：示波器 SINGLE 触发必须在动作事件发生的同时或之前 ARM

```python
# ✅ 正确：短路与 ARM 几乎同时发生
eload.short_on()
osc.set_single_trigger()
time.sleep(0.05)

# ❌ 错误：ARM 后空等 3s 再施加短路（错过触发边沿）
osc.set_single_trigger()
time.sleep(3.0)
eload.short_on()
```

### 规则 6：触发等待轮询期间不得有阻塞性 sleep，轮询与动作不能分离

### 规则 7：git merge/conflict 后必须确保文件可解析

```bash
python -m py_compile your_file.py   # 提交前必做检查
```

### 规则 8：所有仪器通信调用必须设置 timeout

```python
resource.timeout = 5000   # ms，不得依赖系统默认超时
```

### 规则 9：含阻塞 I/O 的仪器调用必须加超时保护，不得在主测试线程直接执行

### 规则 10：每个测试的 `setup()` 必须显式将示波器切回 MAIN 模式

```python
def setup(self, instruments):
    osc = instruments.get("OSC")
    if osc:
        osc.set_timebase_mode("MAIN")
        osc.set_timebase(self.TIME_BASE_S)
```

### 规则 11：`teardown()` 必须恢复仪器到已知默认状态

```python
def teardown(self, instruments):
    osc = instruments.get("OSC")
    if osc:
        for ch in range(1, 5):
            osc.set_channel_off(ch)
        osc.clear_measurements()
```

### 规则 12：所有从 `product_info` 传给用例的参数，必须在 `_inject_common_params` 中显式注入

详见第六节「UI 参数链路」。参数链路六个步骤缺一不可。

---

## 四、字段命名规范

### 4.1 specs_v2 字段

| 后缀 | 含义 | 示例 |
|---|---|---|
| `_lo` | 下限值（规格阈值）| `待机功耗_W_lo` |
| `_hi` | 上限值（规格阈值）| `电压精度_hi` |
| `_pct` | 百分比值 | `纹波_pct` |
| `_pct_enable` | 使能标志（0/1）| `6级能效要求_pct_enable` |

### 4.2 UI/物理参数字段

物理/UI 范围用 `_min` / `_max`，不用 `_lo` / `_hi`：

```python
# ✅ input_voltage_min / input_voltage_max  — UI/物理范围
# ❌ input_voltage_lo / input_voltage_hi    — 规格阈值才用 _lo/_hi
```

### 4.3 protection_logic_v2 字段

格式：`{UI显示名称}_mode`，值：`"self"`（自恢复）、`"latch"`（锁死）或 `""`（未配置）。

### 4.4 test_conditions 固定字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `vin` | float | 输入电压（Vac）|
| `freq` | float | 输入频率（Hz）|
| `proto` | str | 协议标签，如 `"PD"`, `"QC3.0"` |
| `vout` | float | 输出电压（V）|
| `iout` | float | 输出电流（A）|

### 4.5 示波器/功率计通道字段

| params key | 说明 |
|---|---|
| `osc_input_ch` | 输入通道（数字，不带"CH"前缀）|
| `osc_output_ch` | 输出通道 |
| `osc_dynamic_ch` | 动态测试通道 |
| `osc_*_attn` | 各通道衰减比 |
| `pwr_in_v_ch` | 功率计输入电压通道 |
| `pwr_in_i_ch` | 功率计输入电流通道 |
| `pwr_out_v_ch` | 功率计输出电压通道 |
| `pwr_out_i_ch` | 功率计输出电流通道 |

### 4.6 报告 COLS 定义规范

`writer.py` 的 `_get_case_cols()` 通过正则解析源码，不经过 Python import 链。COLS 必须严格遵循以下格式，否则静默 fallback 到 GLOBAL_COLS：

```python
COLS = [
    ("列名", 6),       # ✅ 双引号，列宽为整数常量
    ("列名", 12.0),    # ❌ 小数列宽 → \d+ 匹配不到
    ('列名', 6),         # ❌ 单引号 → 正则不匹配
    ("列名", WIDTH),   # ❌ 变量名 → 正则匹配不到
]
```

---

## 五、用例添加规则

### 5.1 注册

在 `config_schema.py` 的 `CASE_REGISTRY` 中添加一行。

### 5.2 创建用例文件

```python
# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from test_cases.base import TestCase

class MyNewTest(TestCase):
    COLS = [
        ("输入条件", 16),
        ("协议",     12),
        # ... 列定义（双引号，列宽整数字面量）
        ("备注",     28),
    ]

    def __init__(self):
        super().__init__(
            name="MyNewTest",
            instruments=["AC_SOURCE", "ELOAD"],
            params={},
        )

    def setup(self, instruments):
        super().setup(instruments)
        # ✅ 必须缓存 test_conditions 和所有参数
        self.test_conditions = self.test_conditions or self.params.get("test_conditions", [])

    def execute(self, instruments):
        pass

    def verify(self) -> bool:
        return True
```

---

## 六、UI 参数链路

新增一个从 UI 到用例的参数，需要完整走过以下六个环节：

```
① UI 页面（tk Variable）
    ↓ save_config()
② ui/_config_io.py（prod_info 字典）
    ↓ _build_test_engine_config()
③ ui/_engine_api.py（product_info dict）
    ↓ _inject_common_params()
④ test_engine.py（注入 case.params）
    ↓ setup() 缓存
⑤ test_cases/xxxTest.py（self.属性）
    ↓ execute() 使用
⑥ 测试逻辑
```

**任意一环遗漏，参数就传不到用例。**

`product_info` 字段注入示例（`test_engine.py`）：
```python
case.params["my_param"] = float(
    self.config.get("product_info", {}).get("my_param", 0.0) or 0.0
)
```

规格类参数（specs_v2 中的 lo/hi 值）不需要单独注入，已通过 `specs` key 透传，用例直接读：
```python
self.spec.get("极轻载功耗_W_lo", 0.0)
```

---

## 七、仪器驱动架构

### 驱动映射

| 类别 | 型号 | 驱动文件 |
|---|---|---|
| `AC_SOURCE` | IT7321, IT7322 | `instruments/ac_source/IT7321.py` |
| `DC_SOURCE` | IT6333A | `instruments/dc_source/IT6333A.py` |
| `ELECTRONIC_LOAD` | IT8511, IT8512, IT8701P | `instruments/electronic_load/` |
| `OSCILLOSCOPE` | DSOX4024A | `instruments/oscilloscope/DSOX4024A.py` |
| `POWER_METER` | WT322E, WT333E | `instruments/power_meter/WT322E.py` |
| `SNIFFER` | IP2716 | `instruments/sniffer/IP2716.py` |

### 仿真模式

`instrument_manager.enable_simulation_mode()` 使所有仪器返回模拟数据，不尝试真实连接。

### 连接与重试

`connect_with_retry()` 重试逻辑：
- `InstrumentError`（身份验证失败等永久错误）→ **立即失败，不重试**
- 其他 `Exception`（USB 枚举延迟、VISA 超时等暂时性错误）→ 等 2s → 4s → 6s 重试

---

## 八、已知 Bug 与教训（按时间顺序）

> 以下记录真实发生的问题及提炼的规则，新增代码必须避免重蹈覆辙。

**B-01 ~ B-07** 已在代码中修复，详见各文件的 commit 历史。

| 编号 | 文件 | 问题 | 提炼规则 |
|---|---|---|---|
| 12.1 | DSOX4024A | `logger` 定义为局部变量，实例方法抛出 `NameError` | 规则 4 |
| 12.2 | OutputScpProtectTest | 示波器 ARM 后空等 3s 再施加短路，错过触发边沿 | 规则 5 |
| 12.3 | AN87330 | git conflict markers 未清除导致文件不可解析 | 规则 7 |
| 12.4 | IT7821E | `set_voltage` 阻塞 8 分钟，无超时保护 | 规则 8-9 |
| 12.5 | OutputPowerOnOffTest | `teardown()` 未恢复示波器 ROLL 模式，切用例后抓不到波形 | 规则 10-11 |
| — | `_inject_common_params` | 参数链路第 4 环遗漏，`ultra_light_power` 传不到用例 | 规则 12 |
