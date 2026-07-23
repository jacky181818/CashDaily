# Engine 模块文档

> 任务引擎，调度 **截图 → 识别 → 执行** 循环，是整个自动化框架的核心调度器。

---

## 目录

- [概述](#概述)
- [类说明](#类说明)
  - [TaskConfig — 任务配置](#taskconfig--任务配置)
  - [Engine — 任务引擎](#engine--任务引擎)
- [Engine 初始化配置](#engine-初始化配置)
- [任务 YAML 配置说明](#任务-yaml-配置说明)
  - [顶层字段](#顶层字段)
  - [两种执行模式](#两种执行模式)
- [步骤（Step）配置详解](#步骤step配置详解)
  - [页面步骤](#页面步骤)
  - [直接步骤 — action 类型一览](#直接步骤--action-类型一览)
- [查找规则（find）配置](#查找规则find配置)
- [循环步骤（loop）配置](#循环步骤loop配置)
- [Activity 分类与恢复机制](#activity-分类与恢复机制)
- [核心流程图](#核心流程图)

---

## 概述

`engine.py` 提供了一个基于 YAML 配置驱动的任务执行引擎。它通过 ADB 截图、Finder 图像识别（模板匹配 / OCR / 颜色检测）、PageManager 页面管理三大组件协同工作，实现对手机 App 的自动化操作。

**核心循环**：截图 → 识别当前页面/目标元素 → 执行动作（点击/滑动/返回等） → 验证结果

---

## 类说明

### TaskConfig — 任务配置

从 YAML 文件加载的任务配置对象。

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 任务名称（必填） |
| `steps` | `list[dict]` | 步骤列表（普通模式） |
| `pre_commands` | `list[str]` | 执行前的 `adb shell` 命令列表 |
| `precondition` | `dict` | 前置条件，满足才执行任务 |
| `sub_tasks` | `list[str]` | 子任务文件列表（workflow 模式） |

### Engine — 任务引擎

核心调度类，负责加载任务、执行步骤、处理异常恢复。

**构造参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `adb` | ADB 实例 | 提供截图、点击、滑动、返回等 ADB 操作 |
| `finder` | Finder 实例 | 提供模板匹配、OCR、颜色检测等图像识别能力 |
| `page_manager` | PageManager 实例 | 管理页面配置，识别当前页面 |
| `logger` | Logger 实例 | 日志记录与截图保存 |
| `config` | `dict` | 全局配置字典 |

---

## Engine 初始化配置

通过 `config` 字典传入的全局配置项：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `default_retry` | `int` | `3` | 等待页面出现的默认重试次数 |
| `default_timeout` | `float` | `10` | 等待页面出现的默认超时时间（秒） |
| `default_wait_after` | `float` | `1.5` | 每个动作执行后的默认等待时间（秒） |
| `meituan_package` | `str` | `com.sankuai.meituan` | 美团 App 包名 |
| `meituan_game_activity` | `str` | `com.meituan.android.mgc.container.MGCGameActivity` | 天天现金游戏主 Activity |
| `meituan_home_activity_keywords` | `list[str]` | `["MainActivity", "LauncherActivity", "HomeActivity"]` | 美团首页 Activity 关键字列表 |

---

## 任务 YAML 配置说明

### 顶层字段

```yaml
name: "任务名称"              # 必填

pre_commands:                  # 可选：执行前的 adb shell 命令
  - "am start -n com.example/.MainActivity"

precondition:                  # 可选：前置条件
  find:                        # 查找规则（同 find 配置）
    type: ocr
    text: "目标文字"
  on_fail: skip                # 不满足时的行为：skip（跳过任务）/ 其他值（标记失败）

steps: [...]                   # 普通模式：步骤列表
# 或
sub_tasks:                     # workflow 模式：子任务文件列表
  - "sub_task_1.yaml"
  - "sub_task_2.yaml"
```

### 两种执行模式

| 模式 | 触发条件 | 说明 |
|------|----------|------|
| **普通步骤模式** | 配置了 `steps` | 按顺序执行每个步骤，任一步骤失败则任务失败 |
| **子任务串联模式（workflow）** | 配置了 `sub_tasks` 且提供了 `tasks_dir` | 依次加载并执行子任务 YAML 文件，单个子任务失败不阻断后续子任务 |

---

## 步骤（Step）配置详解

### 页面步骤

当步骤包含 `page` 字段时，引擎会先等待目标页面出现，再执行该页面配置中定义的动作。

```yaml
- page: "daily_task_popup"     # 目标页面名称
  name: "打开每日任务弹窗"      # 步骤描述（可选）
  fallback:                     # 页面未找到时的回退策略（可选）
    action: back               # back（按返回键重试）/ skip（跳过）/ abort（终止，默认）
    retry: 1                   # 回退重试次数
```

### 直接步骤 — action 类型一览

当步骤不包含 `page` 字段时，直接执行指定的 `action`。

#### 通用字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `action` | `str` | `tap` | 动作类型 |
| `name` | `str` | `"未命名"` | 步骤描述 |
| `wait_before` | `float` | `0` | 执行前等待时间（秒） |
| `wait_after` | `float` | `default_wait` | 执行后等待时间（秒） |
| `skip_if_not_found` | `bool` | `false` | 目标未找到时是否跳过（而非失败） |

#### action: `tap`

查找目标并点击。

```yaml
- action: tap
  name: "点击领取按钮"
  find:
    type: ocr
    text: "领取"
  offset_x: 0                  # 点击 X 偏移（可选）
  offset_y: -20                # 点击 Y 偏移（可选，如点击文字上方的图标）
```

#### action: `back`

按下返回键（KEYCODE_BACK）。

```yaml
- action: back
  name: "返回上一页"
```

#### action: `home`

按下 HOME 键。

```yaml
- action: home
  name: "回到桌面"
```

#### action: `wait`

纯等待，不执行任何操作。

```yaml
- action: wait
  name: "等待加载"
  duration: 5                  # 等待秒数（默认使用 wait_after）
```

#### action: `swipe`

直接滑动（无需先查找目标）。

```yaml
- action: swipe
  name: "向上滑动"
  swipe_coords: [360, 1000, 360, 400, 300]  # [x1, y1, x2, y2, duration_ms]
```

#### action: `browse`

浏览任务：在指定时间内持续上下滑动，模拟用户浏览行为。

```yaml
- action: browse
  name: "浏览页面"
  duration: 12                 # 浏览持续时间（秒，默认 12）
```

#### action: `scroll_find`

滚动查找：在可滚动区域内查找目标，找不到则上滑一页继续。

```yaml
- action: scroll_find
  name: "查找去领取按钮"
  find:                        # 查找规则
    type: ocr
    text: "去领取"
  # 或使用简写形式：
  anchor_text: "签到任务"       # 锚点文字
  target_text: "去领取"         # 目标文字
  max_swipes: 10               # 最大滑动次数（默认 10）
  swipe_coords: [360, 1400, 360, 700, 300]  # 滑动参数（默认向上滑一页）
  action_on_found: tap         # 找到后的动作：tap（默认）/ check
  offset_x: 0                 # tap 时的 X 偏移
  offset_y: 0                 # tap 时的 Y 偏移
  swipe_wait: 1.0             # 每次滑动后等待时间（秒）
  stop_scroll_if_found:        # 可选：停止滑动的检测规则
    type: ocr                  # 当前屏主规则未命中时，若此规则命中则立即停止滑动并返回 False
    text: "去完成"             # 用途：查找"去领取"时，若当前屏有"去完成"说明已全部领完
    roi: [25, 680, 670, 870]
    threshold: 0.5
```

**`stop_scroll_if_found`**：当前屏主规则未命中时，若检测到此规则命中，则立即停止滑动并返回 `False`（不点击）。典型用途：查找"去领取"时，若当前屏有"去完成"说明"去领取"已全部领完，无需继续滑动，直接跳出让后续步骤处理"去完成"任务。

#### action: `check`

只查找不操作，用于检测 toast、弹窗等信号。

```yaml
- action: check
  name: "检测完成提示"
  find:
    type: ocr
    text: "任务完成"
```

#### action: `if_found`

条件分支：如果找到目标则执行 `then_steps`，否则执行 `else_steps`。

```yaml
- action: if_found
  name: "检查是否已满"
  find:
    type: ocr
    text: "已满"
  use_last_screenshot: true    # 复用上一张截图（捕捉快速消失的 toast）
  fresh_retry_wait: 1.0        # 复用截图未命中时，新截图前的等待时间（秒）
  then_steps:                  # 条件满足时执行
    - action: back
      name: "返回"
  else_steps:                  # 条件不满足时执行（可选）
    - action: tap
      name: "继续操作"
      find: { type: ocr, text: "继续" }
```

#### action: `wait_until_found`

循环等待目标出现，找到后执行 `then_steps`。适用于广告倒计时等场景。

```yaml
- action: wait_until_found
  name: "等待广告结束"
  find:
    type: ocr
    text: "点击立得丰富奖励"
  interval: 1.0                # 检测间隔（秒，默认 1.0）
  timeout: 15.0                # 超时时间（秒，默认 15.0）
  timeout_action: skip         # 超时行为：fail（默认）/ skip
  then_steps:
    - action: tap
      name: "点击领取"
      find: { type: ocr, text: "点击立得丰富奖励" }
```

#### action: `ensure_page`

确保当前在目标页面，如果不在则通过返回 + 重入导航。

```yaml
- action: ensure_page
  name: "确保在每日任务弹窗"
  target_page: "daily_task_popup"   # 目标页面名称
  max_back_attempts: 3              # 最大返回键次数（默认 3）
  entry_find:                       # 入口按钮查找规则（可选）
    type: ocr
    text: "每日任务"
  entry_wait: 2                     # 点击入口后等待时间（秒，默认 2）
  recovery: return_to_game_main     # 导航失败时的恢复策略（可选）
```

**导航策略**：
1. 截图识别当前页面，如果已在目标页面则直接返回
2. 优先尝试通过 `entry_find` 入口按钮直接进入（避免按返回键关闭 App）
3. 如果入口按钮未找到（可能被弹窗遮挡），按返回键清除遮挡后重试
4. 每次按返回键后都检查是否到达目标页面，并尝试 `entry_find`
5. 若设置了 `recovery: return_to_game_main`，导航失败时先恢复到游戏主界面再重试

#### action: `return_to_task`

从浏览/任务页面返回每日任务弹窗。先确保回到游戏主界面，再由后续步骤重新打开弹窗。

```yaml
- action: return_to_task
  name: "返回每日任务弹窗"
```

#### action: `return_to_game_main`

统一"返回游戏主界面"恢复，确保回到天天现金游戏主界面（MGCGameActivity）。

```yaml
- action: return_to_game_main
  name: "返回游戏主界面"
  max_attempts: 15             # 最大尝试次数（默认 15）
  home_entry_find:             # 美团首页时点击进入游戏的查找规则（可选）
    type: ocr
    text: "天天现金"
```

#### action: `close_mgc_overlay`

关闭美团其他小游戏内的同 Activity 浮层圆圈按钮。

```yaml
- action: close_mgc_overlay
  name: "关闭小游戏浮层"
  find:
    template: "close_btn_mgc_overlay.png"
    roi: [600, 20, 720, 120]
    threshold: 0.8
  close_coords: [655, 72]     # 关闭按钮的固定坐标
  package: "com.sankuai.meituan"  # 美团包名（可选，使用全局配置）
```

**智能判别逻辑**：
- 天天现金主游戏（MGCGameActivity，无后缀）→ 跳过（圆圈按钮会关闭游戏）
- 美团其他小游戏（MGCGameActivity1/2，带后缀）→ 检测并点击关闭
- 非美团 App → 跳过

#### action: `run_subtask`

执行另一个子任务 YAML 文件。

```yaml
- action: run_subtask
  name: "执行签到子任务"
  task: "checkin.yaml"         # 子任务文件名
  tasks_dir: "./tasks"         # 子任务目录（可选，默认使用当前运行上下文）
```

---

## 查找规则（find）配置

所有需要定位 UI 元素的步骤都通过 `find` 字段指定查找规则。支持以下类型：

### type: `template` — 模板匹配

```yaml
find:
  type: template
  template: "close_btn.png"    # 模板图片文件名
  roi: [x, y, w, h]           # 搜索区域（可选）
  threshold: 0.8               # 匹配阈值（可选）
  process: raw                 # 图像预处理方式（默认 raw）
```

### type: `ocr` — OCR 文字识别

```yaml
find:
  type: ocr
  text: "领取"                 # 目标文字
  roi: [x, y, w, h]           # 搜索区域（可选）
  threshold: 0.6               # 置信度阈值（可选）
  exact_match: false           # 是否精确匹配（默认 false，支持包含匹配）
```

### type: `ocr_relative` — OCR 相对定位

先找到锚点文字，再在锚点附近查找目标文字。适用于列表中同一行的关联元素。

```yaml
find:
  type: ocr_relative
  anchor_text: "签到任务"       # 锚点文字
  target_text: "去领取"         # 目标文字
  anchor_roi: [25, 680, 670, 870]  # 锚点搜索区域（可选）
  y_range: 60                  # Y 轴容差范围（默认 60）
  x_range: [0, 720]           # X 轴搜索范围（默认 [0, 720]）
  threshold: 0.6               # 置信度阈值（可选）
  anchor_threshold: 0.6        # 锚点置信度阈值（可选）
  exact_match: false           # 是否精确匹配（默认 false）
```

### type: `color` — 颜色检测

```yaml
find:
  type: color
  color: [255, 0, 0]          # 目标颜色 RGB
  roi: [x, y, w, h]           # 搜索区域（可选）
  tolerance: 30                # 颜色容差（默认 30）
  min_ratio: 0.01             # 最小匹配比例（默认 0.01）
```

### type: `fixed` — 固定坐标

直接返回指定坐标，始终 `found=True`。用于位置固定的 UI 元素。

```yaml
find:
  type: fixed
  coords: [655, 72]           # 固定坐标 [x, y]
```

---

## 循环步骤（loop）配置

在步骤中使用 `loop` 字段可定义循环执行的子步骤。

```yaml
- name: "重复领取奖励"
  loop: 5                      # 循环次数
  loop_break_on_fail: true     # 子步骤失败时是否中断循环（默认 true）
  loop_steps:                  # 循环内的子步骤列表
    - action: tap
      name: "点击领取"
      find: { type: ocr, text: "领取" }
    - action: wait
      name: "等待刷新"
      duration: 2
```

### 循环控制字段

在 `loop_steps` 的子步骤中可使用以下控制字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `break_loop_if_not_found` | `bool` | 目标未找到时正常结束整个循环（非失败） |
| `break_loop_if_found` | `bool` | 目标找到时正常结束整个循环（用于检测完成信号） |
| `skip_if_not_found` | `bool` | 子步骤失败时跳过，继续外层循环的下一次迭代 |

---

## Activity 分类与恢复机制

引擎内置了基于 Android Activity 的智能分类与恢复机制，用于处理自动化过程中跳转到非预期页面的情况。

### Activity 分类

| 分类 | 判定条件 | 恢复策略 |
|------|----------|----------|
| `third_party` | 包名不是美团 | `force-stop` 强制关闭 |
| `cash_daily_game` | MGCGameActivity（无后缀） | 已在目标，无需恢复 |
| `other_mini_game` | MGCGameActivity1/2...（带后缀） | 点击圆圈按钮关闭浮层 |
| `meituan_home` | Activity 含 MainActivity/Launcher/Home | 点击"天天现金"图标进入游戏 |
| `meituan_other` | 美团其他页面 | 按返回键 |

### 恢复流程（`return_to_game_main`）

1. 获取当前 Activity，分类判定
2. 根据分类执行对应恢复策略
3. 循环直到回到 `cash_daily_game` 或达到最大尝试次数
4. 兜底：通过 `am start` 直接将游戏 Activity 置顶/重启

---

## 核心流程图

```
run_task(task)
  │
  ├── 执行 pre_commands（adb shell 命令）
  │
  ├── 检查 precondition（前置条件）
  │     ├── 满足 → 继续
  │     └── 不满足 → skip / fail
  │
  ├── [workflow 模式] sub_tasks?
  │     └── 依次加载并执行子任务 YAML
  │
  └── [普通模式] 遍历 steps
        │
        ├── loop 步骤?
        │     └── _execute_loop → 循环执行 loop_steps
        │
        └── 普通步骤 → _process_step
              │
              ├── 有 page? → _wait_for_page → _execute_actions
              │
              └── 无 page? → 根据 action 类型分发
                    ├── tap / swipe    → find → 执行动作
                    ├── back / home    → 按键
                    ├── wait / browse  → 等待/滑动
                    ├── scroll_find    → 滚动查找
                    ├── check          → 只查找不操作
                    ├── if_found       → 条件分支
                    ├── wait_until_found → 循环等待
                    ├── ensure_page    → 导航到目标页面
                    ├── return_to_task → 返回任务弹窗
                    ├── return_to_game_main → 恢复到游戏主界面
                    ├── close_mgc_overlay  → 关闭浮层
                    └── run_subtask    → 执行子任务文件
```
