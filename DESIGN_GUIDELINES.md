# 设计准则 - 测试用例 / UI / 报告 新增规范

> 每次新增测试用例、UI 筛选逻辑、报告字段之前，先读本文件。
> 严格按此清单逐项检查，避免遗漏。

---

## 一、新增测试用例（TestCase）

### 1.1 注册表（七处必须同时更新）

假设新增用例：`MyNewTest`

| 位置 | 文件 | 内容 |
|------|------|------|
| `CASE_REGISTRY` | `test_engine.py` | `"MyNewTest": "test_cases.category.MyNewTest"` |
| `CASE_CN_NAMES` | `test_engine.py` | `"MyNewTest": "我的新测试"` |
| `CASE_NAME_MAP` | `config_ui.py` | `"我的新测试": "MyNewTest"` |
| `_test_case_defs` | `config_ui.py` 第1511行附近 | 在对应分类列表中加入中文用例名 |
| `__init__.py` | `test_cases/category/__init__.py` | 添加 `from .MyNewTest import MyNewTest` 和 `__all__` 声明 |
| `instruments` 列表 | `config_ui.py` (设备勾选框) | 如果有新增仪器类型需要加 |

**注意**：UI checkbox 显示名 与 `CASE_CN_NAMES` 中文名 必须完全一致。
如果 UI checkbox 叫"新测试"，注册表也必须是"新测试"，不能一个带"测试"一个不带。

### 1.1.5 `_test_case_defs` 硬编码列表（config_ui.py）

`config_ui.py` 第 1511 行附近有一个 `_test_case_defs` 字典，
**按用例分类硬编码了 UI 左侧导航栏的显示列表**：

```python
self._test_case_defs = {
    "输入测试": ["输入电压范围", "输入欠压保护", ...],
    "输出测试": [...],
    "保护测试": ["输出过流保护"],          # ← 必须与 CASE_CN_NAMES 一致
    "协议测试": [...],
    "极限测试": [...],
}
```

**新增 / 删除 / 重命名测试用例时，必须同步修改此处。**

| 操作 | 需改位置 |
|------|---------|
| 新增用例 | ① `CASE_REGISTRY` ② `CASE_CN_NAMES` ③ `CASE_NAME_MAP` ④ `_test_case_defs` 对应分类列表 |
| 删除用例 | ① `CASE_REGISTRY` ② `CASE_CN_NAMES` ③ `CASE_NAME_MAP` ④ `_test_case_defs` 中移除 |
| 重命名用例 | ①②③④全部更新名称 |

❌ **常见错误**：只更新了注册表，忘记更新 `_test_case_defs`，导致 UI 重启后导航栏仍显示旧名称。

### 1.2 测试用例文件
- 路径：`test_cases/{category}/MyNewTest.py`
- 继承 `TestCase`
- 实现 `setup()` / `execute()` / `verify()`
- `instruments: List[str]` 列出需要的仪器类型（AC_SOURCE / ELOAD / OSC / SNIFFER / POWER_METER）
- `COLS` 和 `_make_result` dict key 必须完全一致

### 1.3 `__init__.py` 导出声明

新增用例文件后，必须同步更新对应目录的 `__init__.py`，否则 `TestEngine` 动态 import 会报 `No module named 'xxx'`。

```python
# test_cases/{category}/__init__.py
from .MyNewTest import MyNewTest
__all__ = ["MyNewTest", ...]
```

删除用例文件后，也必须同步从 `__init__.py` 中移除对应的 import 和 `__all__` 条目。

| 操作 | `__init__.py` 是否需要改 |
|------|--------------------------|
| 新增用例 | ✅ 必须添加 import 和 `__all__` |
| 删除用例 | ✅ 必须移除 import 和 `__all__` |
| 重命名用例 | ✅ 删除旧条目，添加新条目 |

### 1.3 报表字段规范
- `COLS` 定义列头 `(中文名, 宽度)`
- `_make_result()` 返回 dict，key 名必须与 `COLS` 列头中文名一致
- 测试用例内部字段（如 `overall_pass`）不要放进 `COLS`

---

## 二、新增 UI 筛选逻辑

假设新用例 `MyNewTest` 需要从全量条件中筛选出特定子集：

### 2.1 config_ui.py - `_filter_conditions_by_case`

在函数里加分支：

```python
elif case_key == "MyNewTest":
    # 筛选逻辑
    return filtered_conditions
```

**注意**：`case_key` 是英文用例名，从 `_case_cn_to_en` 查表得到。
如果 UI checkbox 名与 `CASE_CN_NAMES` 注册名不一致（如"输出纹波输入扫描" vs "输出纹波输入扫描测试"），`_case_cn_to_en` 构建时必须注册两种变体：

```python
self._case_cn_to_en = {}
for en, cn in TestEngine.CASE_CN_NAMES.items():
    self._case_cn_to_en[cn] = en
    if cn.endswith("测试"):
        self._case_cn_to_en[cn[:-2]] = en  # 也去掉"测试"后缀注册一份
```

### 2.2 筛选逻辑原则
- 筛选在 UI 勾选时触发，调用 `_apply_filtered_conditions()`
- 筛选结果存在 `self._filtered_conditions[en_key]`
- Treeview 显示时只读 `_filtered_conditions` 当前勾选 case 的数据
- 切换勾选时旧 case 数据必须清理（防止残留全量数据）

---

## 三、新增报告字段

### 3.1 测试用例侧
- `COLS` 加一项：`("新字段名", 宽度)`
- `_make_result()` dict 加一个 key：`"新字段名": value`
- 类型必须一致（数字→数字，字符串→字符串）

### 3.2 报告生成侧（report_generator）
- `COLS` 定义顺序和列名必须与测试用例 `COLS` 完全一致
- 报告写入时按 `COLS` 顺序写入，不要硬编码列索引

---

## 四、仪器调用常见遗漏

### 4.1 诱骗器（Sniffer）
- 调用 `sniffer.set_protocol()` 前先判断 `sniffer is not None`
- 产品类型为 `"adapter"` 时跳过诱骗器（直接 return True）

### 4.2 示波器
- 滚动模式：`osc.set_timebase_mode("ROLL")` → `osc.set_timebase(...)` → `osc.run()`
- 停止：`osc.stop()` → `osc.get_measurement(...)` → `osc.run()` 恢复

### 4.3 电子负载
- `eload.input_on()` / `eload.input_off()` 配对使用
- 动态模式前：`eload.set_dynamic_mode(...)` 配置，再 `eload.run_dynamic()`
- 场景结束后：`eload.trigger("OFF")` → `eload.input_off()`

---

## 五、UI 参数使用规范

### 5.1 不得硬编码任何 UI 可配置参数

❌ **错误示例**：
```python
osc.set_channel_on(2)          # 硬编码通道2
pm.measure_voltage(channel=2)  # 硬编码通道2
```

✅ **正确做法**：所有通道号、规格值、阈值等全部从 `self.params` 读取：
```python
ch_out = int(self.params.get("osc_output_ch", 2))   # 从 UI 参数读
pm.measure_voltage(channel=ch_out)
```

### 5.2 常用 UI 参数（由 `_inject_common_params` 注入）

| 参数 key | 类型 | 说明 |
|---------|------|------|
| `osc_input_ch` | int | 示波器输入通道（CH1） |
| `osc_output_ch` | int | 示波器输出通道（CH2） |
| `osc_dynamic_ch` | int | 示波器动态测试通道 |
| `osc_input_attn` | float | 输入通道衰减倍数 |
| `osc_output_attn` | float | 输出通道衰减倍数 |
| `pwr_in_i_ch` | int | 功率计输入电流通道 |
| `pwr_out_v_ch` | int | 功率计输出电压通道 |
| `pwr_out_i_ch` | int | 功率计输出电流通道 |
| `load_startup_enabled` | bool | 是否带载开机 |
| `load_startup_current` | float | 开机带载电流（A） |
| `load_startup_voltage` | float | 开机目标电压（V） |
| `input_voltage_min/max` | float | DUT 输入电压范围 |
| `product_type` | str | charger / adapter |

所有用例的 `execute()` 中需要用到的通道号，必须通过 `int(self.params.get("osc_output_ch", 2))` 读取，**禁止写死数字**。

---

## 七、设备驱动注意事项

### 7.1 驱动存放位置
```
instruments/
  base.py                    # 驱动基类 InstrumentBase（abstract）
  electronic_load/
    __init__.py             # 导出各驱动类
    BaseElectronicLoad.py   # 电子负载基类（公共方法）
    IT8511.py               # IT8511/IT8512 驱动
    IT8701P.py              # IT8701P 驱动
  oscilloscope/
    DSOX4024A.py           # Keysight 示波器驱动
  sniffer/
    IP2716Sniffer.py        # 诱骗器驱动
  ac_source/
    IT7321.py               # 交流源驱动
  dc_source/
    IT6333A.py              # 直流源驱动
  power_meter/
    WT333E.py               # 功率计驱动
```

### 7.2 instrument_manager.py 驱动选择
- 驱动选择逻辑在 `instrument_manager.py` 的 `_create_driver()` 方法中
- 新增仪器型号时，在此添加 `elif` 分支，按 `config["model"]` 选择对应驱动类
- **注意**：只有 `electronic_load` 需要传 `channel` 参数，其他仪器类型不需要

### 7.3 驱动基类必须实现的方法
所有驱动继承 `InstrumentBase`，子类必须实现：
- `_send_initial_commands()` — 初始化命令（如 `*CLS`、`*RST`）
- `_validate_identity()` — 身份验证（查 IDN）
- `initialize()` — 连接后初始化

电子负载基类 `BaseElectronicLoad` 额外要求：
- `set_mode_cc(current)` — 设置 CC 模式
- `input_on()` / `input_off()` — 开关输入
- `set_dynamic_mode(...)` — 配置动态拉载参数
- `run_dynamic()` — 启动动态拉载
- `trigger(state)` — 触发控制（`"ON"` / `"OFF"`）

### 7.4 SCPI 命令规范
- **严格按用户提供的原始字符串使用**，不擅自缩写或替换
- 例：用户说 `INPut ON` → 就用 `INPut ON`，不能写成 `:SOUR:INP ON`
- 关键字全大写：`CURRent`、 `TRANsient`、 `CONTinuous`
- 参数单位确认：用户说 A/μs 就传 A/μs，不要自作主张换算

### 7.5 电子负载动态模式驱动实现规范
```
set_dynamic_mode():
  :CHAN <ch>          # 选通道
  *CLS                 # 清错误队列
  :FUNC CC             # 设 CC 模式（IT8701P）
  :CURR <i_high>      # 设高端电流
  :CURR:TRAN:MODE CONTinuous   # 设瞬态模式
  :CURR:TRAN:ALEV <i_high>    # 高电流
  :CURR:TRAN:ALEV <i_low>     # 低电流（BLEV）
  :CURR:TRAN:AWID <t_high>    # 高电平宽度
  :CURR:TRAN:BWID <t_low>     # 低电平宽度
  :CURR:TRAN:ASLE <slew_a>    # 上升斜率（A/μs）
  :CURR:TRAN:BSLE <slew_b>    # 下降斜率（A/μs）
  *CLS

run_dynamic():
  trigger("ON")               # :TRAN ON
  time.sleep(0.05)
  input_on()                   # INPut ON（精确字符串）
  # 发 TrigImm：IT8701P 用 TRIG:IMM，IT8511 用 :TRIG
  # 不等待校验，直接返回
  return

cleanup（场景切换）:
  trigger("OFF")
  input_off()
```

### 7.6 新增驱动检查项
```
□ instrument_manager.py 的 _create_driver() 是否加了 elif 分支
□ __init__.py 是否导出新驱动类（from .NewDriver import NewDriver）
□ 驱动类的 instruments 列表是否包含新增仪器类型
□ config_ui.py 设备勾选框是否包含新仪器类型
□ SCPI 命令是否与用户提供的规格完全一致（大小写、空格）
□ 参数单位是否与用户规格一致（不要擅自换算）
□ 动态模式：trigger("ON") / trigger("OFF") 是否配对使用
```

---

## 八、配置文件 / JSON 结构

### 5.1 product_info 规格 key 命名
- UI 保存的 key 与测试用例读取的 key 必须完全一致
- 例：UI 保存 `"大动态负载范围（%）"`，测试用例也必须读 `"大动态负载范围（%）"`
- 避免全角/半角括号混用：`（` vs `(` 是不同字符

### 5.2 测试条件格式
- 全量条件：`[(vin, freq, proto_label, vout, iout, product_type), ...]`
- 筛选后条件格式不变，只做行过滤

---

## 八、新功能检查清单

每次新增后逐项确认：

**注册与映射（test_engine.py / config_ui.py）**
```
□ CASE_REGISTRY（test_engine.py）
□ CASE_CN_NAMES（test_engine.py）
□ CASE_NAME_MAP（config_ui.py）
□ _case_cn_to_en 映射（config_ui.py）— checkbox 名与注册名不一致时加双注册
□ _filter_conditions_by_case 分支（config_ui.py）
□ 清理旧数据（_filtered_conditions）
```

**测试用例**
```
□ COLS 定义（测试用例 .py）
□ _make_result dict key 与 COLS 列头一致
□ 报告写入器 COLS 顺序一致性
```

**仪器调用**
```
□ 仪器 None 判断（sniffer / eload / osc）
□ 产品类型判断（charger vs adapter）
□ 电子负载 input_on/input_off 配对
□ 动态模式 trigger("OFF") + input_off() 清理
□ 示波器滚动模式 set_timebase_mode("ROLL") 先于 set_timebase()
```

**设备驱动**
```
□ instrument_manager.py 的 _create_driver() 加 elif 分支
□ 驱动 __init__.py 导出（from .NewDriver import NewDriver）
□ SCPI 命令与用户规格完全一致（不擅自缩写）
□ 参数单位不换算（用户说 A/μs 就传 A/μs）
□ config_ui.py 设备勾选框包含新仪器类型
```
