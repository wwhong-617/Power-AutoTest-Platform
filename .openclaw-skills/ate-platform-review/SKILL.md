---
name: ate-platform-review
description: 自动化测试平台（ATE平台）系统化代码检视。当需要对平台代码进行系统性审查、检查bug、验证修复、或审查PR/patch时激活。覆盖配置系统（save/load）、测试执行引擎、仪器驱动、报告生成四大模块的数据流追踪和已知bug模式检查。
---

# ATE 平台代码检视

## 核心方法论：三步法

**第一步：追踪数据流（Data Flow Trace）**
外部输入 → 模块边界 → 最终被使用处，全程追踪。

**第二步：对照 Bug 模式清单（Bug Pattern Check）**
对照 `references/bug-patterns.md` 中的历史 bug 模式，防止复发。

**第三步：验证模块接口（Module Interface）**
确认调用方和被调用方的契约一致（参数类型、返回值、异常）。

---

## 检视触发场景

| 用户说法 | 激活的检视线 |
|---------|------------|
| "检查 bug" / "有问题" | 数据流追踪 + Bug 模式 |
| "帮我检视代码" | 三步法完整执行 |
| "修完了，再检查一下" | 回归验证 + Bug 模式 |
| "配置导入有问题" | config_io 数据流专项 |
| "测试结果不对" | test_engine → report 模块接口 |
| "仪器报错" | instrument_manager 异常分流 |
| "报告格式不对" | report_writer → _mappings 接口 |

---

## 快速启动：每次检视的标准顺序

```
1. 明确检视范围（哪个模块？整平台？）
2. 读取 references/data-flow-trace.md，掌握该模块的数据流
3. 读取 references/bug-patterns.md，对照已知模式
4. 执行代码读和分析
5. 如需深度检查模块接口，读取 references/module-interfaces.md
6. 汇总发现：分类（P-1 严重 / P-2 一般 / P-3 建议）
```

---

## 数据流追踪关键路径

### 配置系统（最常出 bug）

```
UI 填写 → save_config() ──JSON──► load_config() ──► UI 更新
                                      │
                              ┌───────┴────────┐
                              ▼                ▼
                     _build_test_engine_config()  →  TestEngine
                              │
                              ▼
                        报告写入
```

**必须验证的对称性：**
- `save_config` 写入的 key = `load_config` 读取的 key
- `build_specs_flat` 的 flat_key 命名规则：`{flat_key}_lo` / `{flat_key}_hi`
- SPECS_KEYS 的 label_text 与 UI label 完全一致（全角/半角敏感）

### 测试执行引擎

```
_build_test_engine_config(checked_cases)
    ├── product_info（来自 _spec_vars）
    ├── test_params（来自 Treeview / _dyn_vars）
    └── case_params（来自 filtered_conditions）

→ TestEngine.run() → Case.run()
    ├── setup()：初始化仪器 + 缓存 test_conditions
    ├── execute()：使用缓存参数（setup 已缓存，不在 execute 中调用 .get()）
    └── teardown()：放电
```

---

## Bug 模式快速查

遇到问题时，先查 `references/bug-patterns.md`，按分类找历史模式：

| 分类 | 代表性 bug |
|-----|-----------|
| UI 绑定 | tk.StringVar/IntVar 的 truthy 判断错误 |
| 配置读写 | save/load key 不对称、类型不一致 |
| 执行时序 | 页面未建时就调用 _do_load_config |
| 异常处理 | 异常未分流，所有错误同一处理 |
| 仪器通信 | 通道号硬编码、IDN 验证失败信息不足 |
| 报告生成 | 列映射 key 错误、数据展开遗漏字段 |

---

## 输出格式

每次检视完成后，按以下格式报告：

```
## 检视报告：<范围>

### 🐛 Bug（影响功能）
- [B-1] <位置>：<描述>
  - 根因：<>
  - 修复建议：<>

### 💡 建议（改善代码）
- [S-1] <位置>：<描述>
  - 理由：<>
  - 建议：<>

### ✅ 已验证（确认无问题）
- <模块/路径>：<验证方法和结果>

---
严重程度：🐛 = 必须修 / 💡 = 建议修 / ✅ = 已确认
```
