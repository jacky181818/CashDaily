# Core 模块 API 参考

`game_auto.core` 包提供了自动化任务引擎的核心组件，基于 ADB + OCR/模板匹配实现 Android 设备的自动化操作。

## 模块概览

| 模块 | 说明 |
|------|------|
| `adb` | ADB 操作封装：截图、点击、滑动、应用管理 |
| `finder` | 三种定位策略：模板匹配、OCR 文字识别、颜色查找 |
| `page` | 页面识别和状态机（两级判定：Activity 容器过滤 + 视觉细配） |
| `engine` | 任务引擎：调度截图→识别→执行循环 |
| `logger` | 日志记录 + 截图归档 |

---

## adb 模块

### ADB 类

Android 调试桥（ADB）操作封装。通过 `subprocess` 调用本地 adb 可执行文件，提供截图、点击、滑动、应用启停、屏幕信息获取等常用操作。

#### 构造函数

```python
ADB(adb_path: str, device: str = None)
```

初始化 ADB 实例。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `adb_path` | `str` | — | adb 可执行文件的完整路径（如 `/usr/bin/adb`） |
| `device` | `str` | `None` | 目标设备序列号（对应 `adb -s <device>`）。为 `None` 时使用默认连接的设备 |

#### 公开方法

---

##### `run`

```python
run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess
```

执行任意 ADB 命令。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `args` | `list[str]` | — | ADB 子命令及参数列表，如 `["shell", "input", "tap", "100", "200"]` |
| `timeout` | `int` | `30` | 命令超时时间（秒） |

**返回值：** `subprocess.CompletedProcess` — 命令执行结果，包含 `stdout`、`stderr`、`returncode` 等属性。使用 `text=True` + `errors="replace"` 容错解码，避免非法多字节序列在中文 Windows（GBK）下触发 `UnicodeDecodeError`。

---

##### `get_state`

```python
get_state() -> str
```

获取设备连接状态。

**返回值：** `str` — 设备状态字符串，如 `"device"`、`"offline"`、`"unauthorized"` 等。

---

##### `is_connected`

```python
is_connected() -> bool
```

检查是否有设备处于已连接状态。通过解析 `adb devices` 输出判断是否存在非 offline 的设备。

**返回值：** `bool` — 如果至少有一个在线设备则返回 `True`，否则返回 `False`。

---

##### `screenshot`

```python
screenshot(save_path: str = None) -> str
```

截图并保存到本地。在设备上执行 `screencap`，通过 `adb pull` 拉取到本地，然后删除设备上的临时文件。若截图文件为空或不存在，最多自动重试 **3 次**。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `save_path` | `str` | `None` | 本地保存路径。为 `None` 时自动生成临时文件路径 |

**返回值：** `str` — 截图保存的本地文件路径。

**异常：** 重试 3 次后截图仍为空或保存失败时抛出 `RuntimeError`。

---

##### `tap`

```python
tap(x: int, y: int)
```

点击指定屏幕坐标。

| 参数 | 类型 | 说明 |
|------|------|------|
| `x` | `int` | 横坐标 |
| `y` | `int` | 纵坐标 |

**返回值：** 无。

---

##### `swipe`

```python
swipe(x1: int, y1: int, x2: int, y2: int, duration: int = 300)
```

从起点滑动到终点。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `x1` | `int` | — | 起点横坐标 |
| `y1` | `int` | — | 起点纵坐标 |
| `x2` | `int` | — | 终点横坐标 |
| `y2` | `int` | — | 终点纵坐标 |
| `duration` | `int` | `300` | 滑动持续时间（毫秒） |

**返回值：** 无。

---

##### `press_back`

```python
press_back()
```

模拟按下返回键（`KEYCODE_BACK`）。

**返回值：** 无。

---

##### `press_home`

```python
press_home()
```

模拟按下 HOME 键（`KEYCODE_HOME`）。

**返回值：** 无。

---

##### `start_app`

```python
start_app(package: str, activity: str, wait: bool = True)
```

启动指定应用的 Activity。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `package` | `str` | — | 应用包名 |
| `activity` | `str` | — | Activity 全类名 |
| `wait` | `bool` | `True` | 是否等待启动完成（`am start -W` 标志），超时 60 秒 |

**返回值：** 无。

---

##### `force_stop`

```python
force_stop(package: str)
```

强制停止指定应用。

| 参数 | 类型 | 说明 |
|------|------|------|
| `package` | `str` | 应用包名 |

**返回值：** 无。

---

##### `get_screen_size`

```python
get_screen_size() -> tuple[int, int]
```

获取设备屏幕物理尺寸。通过解析 `wm size` 输出中的 `Physical size` 行获取。

**返回值：** `tuple[int, int]` — `(宽, 高)`，如 `(720, 1560)`。解析失败时返回默认值 `(720, 1560)`。

---

##### `get_current_package`

```python
get_current_package() -> str
```

获取当前前台应用的包名。通过解析 `dumpsys window` 输出中的 `mCurrentFocus` 行获取。

**返回值：** `str` — 当前前台应用包名（如 `"com.sankuai.meituan"`）。无法获取时返回空字符串。

---

##### `get_current_activity`

```python
get_current_activity() -> tuple[str, str]
```

获取当前前台应用的包名和 Activity 全类名。通过解析 `dumpsys window` 输出中的 `mCurrentFocus` 行获取。

**返回值：** `tuple[str, str]` — `(包名, Activity全类名)`。

**示例：**
```
mCurrentFocus=Window{9afc764 u0 com.sankuai.meituan/com.meituan.android.mgc.container.MGCGameActivity}
→ 返回 ("com.sankuai.meituan", "com.meituan.android.mgc.container.MGCGameActivity")
```

无法获取时返回 `("", "")`。

> **注意：** 天天现金主游戏为 `MGCGameActivity`（无后缀）；美团其他小游戏为 `MGCGameActivity1` / `MGCGameActivity2` 等（带数字后缀），可用于区分当前是否在天天现金主游戏内。

---

##### `bring_to_front`

```python
bring_to_front(package: str, game_activity: str = None, retries: int = 3) -> bool
```

把指定应用的游戏页面带回前台。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `package` | `str` | — | 应用包名 |
| `game_activity` | `str` | `None` | 游戏 Activity 全类名。指定时优先使用 `am start` 带 `REORDER_TO_FRONT`（`0x20000000`）标志直接启动 |
| `retries` | `int` | `3` | 最大重试次数 |

**返回值：** `bool` — 是否成功将目标应用带到前台。

**恢复策略（每次重试）：**
1. **优先 `am start`**：直接启动游戏 Activity，若实例已存在（singleTask/singleInstance）则保留任务栈与弹窗状态，仅置顶
2. **兜底 `monkey`**：通过 `monkey -p <pkg> -c LAUNCHER` 启动 Launcher Activity
3. 每次尝试后核验当前前台包名，确保真正回到目标应用

---

## finder 模块

### FinderResult 类

屏幕元素查找结果的数据类，封装一次查找操作的结果信息。

#### 构造函数

```python
FinderResult(x: int, y: int, confidence: float, method: str, detail: str = "")
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `x` | `int` | — | 目标中心点的 x 坐标（屏幕绝对坐标）。未找到时为 0 |
| `y` | `int` | — | 目标中心点的 y 坐标（屏幕绝对坐标）。未找到时为 0 |
| `confidence` | `float` | — | 匹配置信度（0.0 ~ 1.0）。未找到时为 0 |
| `method` | `str` | — | 查找方法标识（`"template"` / `"ocr"` / `"ocr_relative"` / `"color"` / `"activity"` / `"fixed"`） |
| `detail` | `str` | `""` | 查找过程的详细描述信息，用于日志和调试 |

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `x` | `int` | 目标中心点的 x 坐标 |
| `y` | `int` | 目标中心点的 y 坐标 |
| `confidence` | `float` | 匹配置信度 |
| `method` | `str` | 查找方法标识 |
| `detail` | `str` | 详细描述信息 |
| `found` | `bool`（只读属性） | 是否找到目标，等价于 `confidence > 0` |

---

### Finder 类

屏幕元素定位器，提供三种查找策略的统一入口：模板匹配（找图）、OCR 文字识别（找字）、颜色查找（找色）。支持 ROI 区域限制、多尺度模板匹配、透明背景处理、相对 OCR 定位等高级功能。OCR 功能基于 RapidOCR（ONNX Runtime），按需延迟初始化。

#### 构造函数

```python
Finder(templates_dir: str, threshold: float = 0.55, ocr_enabled: bool = False)
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `templates_dir` | `str` | — | 模板图片文件所在目录路径 |
| `threshold` | `float` | `0.55` | 默认匹配置信度阈值，低于此值视为未匹配 |
| `ocr_enabled` | `bool` | `False` | 是否启用 OCR 功能。为 `True` 时在首次调用 OCR 方法时初始化引擎 |

#### 公开方法

---

##### `find_template`

```python
find_template(
    screenshot_path: str,
    template_name: str,
    roi: tuple = None,
    threshold: float = None,
    scales: list = None,
    process: str = "raw"
) -> FinderResult | None
```

**多尺度模板匹配**：在截图中查找指定模板图片。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `screenshot_path` | `str` | — | 截图文件路径 |
| `template_name` | `str` | — | 模板图片文件名（相对于 `templates_dir`） |
| `roi` | `tuple` | `None` | 搜索区域限制 `(x, y, w, h)`，为 `None` 时搜索全图 |
| `threshold` | `float` | `None` | 匹配置信度阈值，为 `None` 时使用构造函数中的默认阈值 |
| `scales` | `list` | `None` | 缩放比例列表，为 `None` 时使用 `[0.9, 0.95, 1.0, 1.05, 1.1]` |
| `process` | `str` | `"raw"` | 预处理方式：`"raw"` 原图直接匹配；`"transparent"` 先透明化再匹配（从四角 floodFill 去除背景） |

**返回值：** `FinderResult | None` — 匹配结果。坐标为模板在截图中的中心点（已加上 ROI 偏移）。未达阈值时返回 `confidence=0` 的结果。alpha 通道全透明时返回 `None`。

**异常：** 模板文件不存在时抛出 `FileNotFoundError`；无法读取模板或截图时抛出 `RuntimeError`。

**匹配流程：**
1. 加载模板图片，分离 alpha 通道
2. 可选透明化处理（`process="transparent"`，从四角 floodFill 去除背景）
3. 裁剪到非透明内容区域
4. 对每个缩放比例执行 `cv2.matchTemplate`（`TM_CCOEFF_NORMED`），透明区域用均值填充
5. 取所有尺度中最高分数的匹配位置，计算中心坐标

---

##### `find_ocr`

```python
find_ocr(
    screenshot_path: str,
    target_text: str | list[str],
    roi: tuple = None,
    threshold: float = 0.5,
    exact_match: bool = False
) -> FinderResult | None
```

**OCR 文字查找**：使用 RapidOCR 识别截图中的文字，查找包含目标文本的位置。支持多关键词匹配（列表中任意一个命中即返回）。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `screenshot_path` | `str` | — | 截图文件路径 |
| `target_text` | `str \| list[str]` | — | 要查找的文字。传入列表时命中任意一个即返回 |
| `roi` | `tuple` | `None` | 搜索区域限制 `(x, y, w, h)` |
| `threshold` | `float` | `0.5` | OCR 识别的最低置信度阈值 |
| `exact_match` | `bool` | `False` | 是否要求文本完全相等。`False` 时使用包含匹配（`target in text`），`True` 时要求 `target == text`。用于避免 "去捕捉" 误匹配 "浏览去捕捉" 等情况 |

**返回值：** `FinderResult | None` — 匹配结果。坐标为 OCR 识别框的中心点（已加上 ROI 偏移）。在所有候选中取置信度最高的匹配。

**异常：** 无法读取截图时抛出 `RuntimeError`；RapidOCR 未安装时抛出 `RuntimeError`。

---

##### `find_ocr_relative`

```python
find_ocr_relative(
    screenshot_path: str,
    anchor_text: str,
    target_text: str,
    anchor_roi: tuple = None,
    y_range: int = 60,
    x_range: tuple = (0, 720),
    threshold: float = 0.5,
    anchor_threshold: float = None,
    exact_match: bool = False,
    anchor_same_line: str = None
) -> FinderResult
```

**相对 OCR 查找**：先找到锚点文字（anchor），再在锚点附近区域查找目标文字（target）。典型用途：在每日任务弹窗中，先定位任务名称（如"浏览优惠活动"），再找到同一行右侧的"去完成"按钮。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `screenshot_path` | `str` | — | 截图文件路径 |
| `anchor_text` | `str` | — | 锚点文字（始终使用包含匹配，因为可能带"剩余XX次"等后缀） |
| `target_text` | `str` | — | 目标文字 |
| `anchor_roi` | `tuple` | `None` | 查找锚点的 ROI 区域 `(x, y, w, h)` |
| `y_range` | `int` | `60` | 目标必须在锚点垂直方向 ±y_range 像素范围内 |
| `x_range` | `tuple` | `(0, 720)` | 目标的 x 坐标范围 `(x_min, x_max)` |
| `threshold` | `float` | `0.5` | 目标的最低置信度阈值 |
| `anchor_threshold` | `float` | `None` | 锚点的最低置信度阈值，为 `None` 时与 `threshold` 相同 |
| `exact_match` | `bool` | `False` | 对目标是否使用精确匹配 |
| `anchor_same_line` | `str` | `None` | 可选同行共存验证：要求锚点同一行（y 坐标 ±15px 内）还必须存在此文本，否则不算匹配。用于区分 OCR 拆分为多段的同名任务（如 "下单领奖励" 同行有 "浏览得精灵球" 才是目标任务） |

**返回值：** `FinderResult` — 匹配结果。找到时坐标为目标文字的中心点；未找到时 `confidence=0`。

**查找流程：**
1. 在 `anchor_roi` 区域内查找 `anchor_text`（包含匹配）
2. （可选）验证 `anchor_same_line` 共存条件：查找该文本并验证 y 坐标差 ≤ 15px
3. 根据锚点位置计算目标搜索 ROI：`x_range` × `(anchor_y ± y_range)`
4. 在计算出的 ROI 内查找 `target_text`

---

##### `find_color`

```python
find_color(
    screenshot_path: str,
    target_color: tuple,
    roi: tuple = None,
    tolerance: int = 30,
    min_ratio: float = 0.01
) -> FinderResult
```

**颜色查找**：在 ROI 区域内查找目标颜色的聚集位置。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `screenshot_path` | `str` | — | 截图文件路径 |
| `target_color` | `tuple` | — | 目标颜色 `(R, G, B)` |
| `roi` | `tuple` | `None` | 搜索区域限制 `(x, y, w, h)` |
| `tolerance` | `int` | `30` | 颜色容差（每个通道 ±tolerance） |
| `min_ratio` | `float` | `0.01` | 目标颜色像素的最小面积占比，低于此值视为未找到 |

**返回值：** `FinderResult` — 匹配结果。`confidence` 字段存储的是颜色面积占比（ratio），坐标为颜色聚集区域的质心（通过 `cv2.moments` 计算）。

**异常：** 无法读取截图时抛出 `RuntimeError`。

---

## page 模块

### PageConfig 类

单个页面的配置信息，从 YAML 文件加载。包含页面名称、识别规则、动作列表以及 Activity 容器约束等信息。Activity 约束用于两级判定的第一级过滤。

#### 构造函数

```python
PageConfig(data: dict)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `data` | `dict` | 从 YAML 文件解析的页面配置字典，必须包含 `name` 字段 |

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 页面唯一名称 |
| `description` | `str` | 页面描述 |
| `identify` | `list[dict]` | 页面识别规则列表。每条规则可以是 `template`、`ocr`、`color` 或 `activity` 类型 |
| `actions` | `list[dict]` | 该页面上可执行的动作列表 |
| `package` | `str \| None` | 包名精确匹配约束（第一级过滤） |
| `activity` | `str \| None` | Activity 类名（basename）精确匹配约束 |
| `activity_suffix` | `str \| None` | Activity 类名（basename）前缀匹配约束 |
| `activity_not` | `list[str]` | Activity 类名（basename）排除列表 |
| `activity_only` | `bool` | 是否为"纯 Activity 识别"页面。当所有 `identify` 规则都是 `activity` 类型时为 `True`，此类页面在第二级兜底阶段才参与判定，避免遮蔽具体弹窗页 |

---

### PageManager 类

页面管理器：加载所有页面配置并执行两级页面识别。

**两级判定流程：**
1. **第一级（Activity 容器过滤）**：根据页面配置的 `package`、`activity`、`activity_suffix`、`activity_not` 约束过滤不匹配的页面
2. **第二级（视觉细配）**：先对非纯 Activity 页面做视觉匹配（模板/OCR/颜色），都未命中时再对纯 Activity 页面做兜底匹配

#### 构造函数

```python
PageManager(pages_dir: str, get_activity_callback=None)
```

初始化页面管理器并自动加载目录下所有 `.yaml` / `.yml` 页面配置文件。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pages_dir` | `str` | — | 页面配置 YAML 文件所在目录路径 |
| `get_activity_callback` | `callable` | `None` | 可选回调函数，调用后返回 `(包名, Activity全类名)` 元组。通常传入 `adb.get_current_activity`，避免 PageManager 直接依赖 ADB |

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `pages_dir` | `str` | 页面配置目录路径 |
| `get_activity_callback` | `callable \| None` | 获取当前 Activity 的回调函数 |
| `pages` | `dict[str, PageConfig]` | 已加载的页面配置字典，键为页面名称 |

#### 公开方法

---

##### `identify_current_page`

```python
identify_current_page(finder: Finder, screenshot_path: str, threshold: float = None) -> str | None
```

两级识别当前页面。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `finder` | `Finder` | — | Finder 实例，用于执行视觉匹配 |
| `screenshot_path` | `str` | — | 当前截图文件路径 |
| `threshold` | `float` | `None` | 匹配置信度阈值，为 `None` 时使用规则自身或 Finder 默认值 |

**返回值：** `str | None` — 识别到的页面名称，未识别到任何页面时返回 `None`。

**识别流程：**
1. 通过 `get_activity_callback` 获取当前 `(包名, Activity全类名)`，提取 Activity basename
2. **第一轮**：遍历所有非 `activity_only` 页面，先检查 Activity 容器约束（第一级过滤），通过后逐条执行 `identify` 规则做视觉匹配（第二级），任一规则命中即返回该页面名称
3. **第二轮（兜底）**：遍历所有 `activity_only` 页面，同样先检查 Activity 约束，通过后执行 Activity 类型规则匹配

---

## engine 模块

### TaskConfig 类

任务配置信息，从 YAML 文件加载。支持两种执行模式：普通步骤模式和子任务串联模式（workflow）。

#### 构造函数

```python
TaskConfig(data: dict)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `data` | `dict` | 从 YAML 文件解析的任务配置字典，必须包含 `name` 字段 |

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 任务名称 |
| `steps` | `list[dict]` | 步骤列表，每个步骤为一个字典（普通步骤模式） |
| `pre_commands` | `list[str]` | 执行前的 adb shell 命令列表 |
| `precondition` | `dict \| None` | 前置条件配置（包含 `find` 查找规则和 `on_fail` 失败策略），满足才执行任务 |
| `sub_tasks` | `list[str]` | 子任务文件名列表（workflow 模式） |

---

### Engine 类

任务执行引擎，调度"截图 → 页面识别 → 动作执行"的自动化循环。是整个自动化框架的核心调度器。

#### 构造函数

```python
Engine(adb: ADB, finder: Finder, page_manager: PageManager, logger: Logger, config: dict)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `adb` | `ADB` | ADB 实例，提供设备操作能力 |
| `finder` | `Finder` | Finder 实例，提供屏幕元素定位能力 |
| `page_manager` | `PageManager` | PageManager 实例，提供页面识别能力 |
| `logger` | `Logger` | Logger 实例，提供日志记录能力 |
| `config` | `dict` | 全局配置字典 |

**config 支持的配置键：**

| 键 | 类型 | 默认值 | 说明 |
|----|------|--------|------|
| `default_retry` | `int` | `3` | 默认重试次数 |
| `default_timeout` | `int` | `10` | 默认超时时间（秒） |
| `default_wait_after` | `float` | `1.5` | 默认动作后等待时间（秒） |
| `meituan_package` | `str` | `"com.sankuai.meituan"` | 美团应用包名 |
| `meituan_game_activity` | `str` | `"com.meituan.android.mgc.container.MGCGameActivity"` | 天天现金游戏 Activity 全类名 |
| `meituan_home_activity_keywords` | `list[str]` | `["MainActivity", "LauncherActivity", "HomeActivity"]` | 美团首页 Activity 关键字列表 |

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `adb` | `ADB` | ADB 实例 |
| `finder` | `Finder` | Finder 实例 |
| `page_manager` | `PageManager` | PageManager 实例 |
| `logger` | `Logger` | Logger 实例 |
| `config` | `dict` | 全局配置字典 |
| `default_retry` | `int` | 默认重试次数 |
| `default_timeout` | `int` | 默认超时时间（秒） |
| `default_wait` | `float` | 默认动作后等待时间（秒） |
| `screenshot_cache` | `str \| None` | 最近一次截图的文件路径缓存 |

#### 公开方法

---

##### `load_task`

```python
load_task(task_path: str) -> TaskConfig
```

从 YAML 文件加载任务配置。

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_path` | `str` | 任务配置 YAML 文件路径 |

**返回值：** `TaskConfig` — 解析后的任务配置对象。

---

##### `run_task`

```python
run_task(task: TaskConfig, tasks_dir: str = None) -> bool
```

执行完整任务，支持普通步骤和子任务串联两种模式。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `task` | `TaskConfig` | — | 任务配置对象 |
| `tasks_dir` | `str` | `None` | 任务文件所在目录，用于子任务串联模式中定位子任务文件 |

**返回值：** `bool` — 任务是否执行成功。

**执行流程：**
1. 开始日志会话
2. 执行 `pre_commands` 前置命令（每条命令后等待 5 秒）
3. 检查 `precondition` 前置条件（不满足时根据 `on_fail` 策略 skip 或 fail）
4. 若有 `sub_tasks` 且提供了 `tasks_dir`，进入**子任务串联模式**：依次加载并递归执行每个子任务文件，子任务失败不阻断后续子任务
5. 否则进入**普通步骤模式**：按顺序执行 `steps` 列表中的每个步骤，支持循环步骤（`loop`）和普通步骤

#### 内部方法说明

以下为 Engine 的关键内部方法，虽非公开 API，但对理解引擎行为至关重要。

---

##### `_execute_loop`

```python
_execute_loop(step: dict) -> bool
```

执行循环步骤。

| 步骤配置键 | 类型 | 默认值 | 说明 |
|------------|------|--------|------|
| `loop` | `int` | `1` | 循环次数 |
| `loop_steps` | `list[dict]` | `[]` | 每次迭代要执行的子步骤列表 |
| `name` | `str` | `"循环"` | 循环名称 |
| `loop_break_on_fail` | `bool` | `True` | 子步骤失败时是否中断循环 |

**子步骤特殊标志：**
- `break_loop_if_not_found`：目标未找到时正常结束循环（不视为失败）
- `break_loop_if_found`：目标找到时立即结束循环（用于检测 toast 等完成信号）
- `skip_if_not_found`：子步骤失败时跳过，继续外层循环

**返回值：** `bool` — 至少完成一次迭代则返回 `True`。

---

##### `_process_step`

```python
_process_step(step: dict) -> bool
```

处理单个步骤（普通步骤或循环子步骤）。根据步骤配置中的 `action` 类型分发到不同的处理逻辑。

**支持的 action 类型：**

| action 类型 | 说明 |
|-------------|------|
| `tap` | 截图→查找目标→点击目标坐标。支持 `offset_x`/`offset_y` 点击偏移 |
| `back` | 按返回键（`KEYCODE_BACK`） |
| `wait` | 等待指定 `duration` 秒 |
| `browse` | 浏览任务：在 `duration` 秒内持续上下滑动，模拟浏览行为 |
| `home` | 按 HOME 键 |
| `swipe` | 直接滑动，使用 `swipe_coords` 指定坐标 `[x1, y1, x2, y2, duration]` |
| `scroll_find` | 滚动查找：在可滚动区域内查找目标，找不到就上滑一页继续（详见 `_do_scroll_find`） |
| `ensure_page` | 确保在目标页面，不在则通过返回+重入导航。支持 `recovery="return_to_game_main"` 兜底恢复 |
| `return_to_task` | 从浏览/任务页面返回每日任务弹窗，内部调用 `_return_to_game_main` |
| `return_to_game_main` | 统一恢复到天天现金游戏主界面（详见 `_return_to_game_main`） |
| `close_mgc_overlay` | 关闭美团其他小游戏内的浮层圆圈按钮。会判断当前 Activity 避免误关天天现金主游戏 |
| `if_found` | 条件分支：查找目标，找到执行 `then_steps`，未找到执行 `else_steps`。支持 `use_last_screenshot` 复用上一张截图捕捉 toast |
| `wait_until_found` | 循环等待目标出现（按 `interval` 间隔截图检测，超过 `timeout` 后根据 `timeout_action` 决定 fail 或 skip），找到后执行 `then_steps` |
| `run_subtask` | 加载并执行另一个子任务文件（递归调用 `run_task`） |
| `check` | 只查找不操作：截图→查找目标→返回是否找到。用于检测 toast、弹窗等信号 |

**通用步骤配置键：**

| 键 | 类型 | 默认值 | 说明 |
|----|------|--------|------|
| `page` | `str` | — | 页面步骤：等待并识别指定页面，然后执行页面动作 |
| `action` | `str` | `"tap"` | 动作类型 |
| `name` | `str` | — | 步骤名称（用于日志） |
| `find` | `dict` | — | 查找规则（`type`、`template`/`text`/`color` 等） |
| `wait_before` | `float` | `0` | 执行动作前等待时间（秒） |
| `wait_after` | `float` | `default_wait` | 执行动作后等待时间（秒） |
| `skip_if_not_found` | `bool` | `False` | 目标未找到时是否跳过（返回 `True`） |
| `fallback` | `dict` | — | 页面步骤的失败回退策略（`action`: `"back"`/`"skip"`/`"abort"`，`retry`: 重试次数） |

---

##### `_do_scroll_find`

```python
_do_scroll_find(step: dict, wait_after: float, step_name: str) -> bool
```

滚动查找：在可滚动区域内查找目标，若当前屏未找到则上滑一页继续。

| 步骤配置键 | 类型 | 默认值 | 说明 |
|------------|------|--------|------|
| `find` | `dict` | — | 查找规则（ocr/ocr_relative/template/color/fixed） |
| `anchor_text` | `str` | — | 简写模式：锚点文字（自动构造 `ocr_relative` 规则） |
| `target_text` | `str` | — | 简写模式：目标文字 |
| `anchor_same_line` | `str` | `None` | 要求锚点同一行还必须存在此文本（同行验证） |
| `max_swipes` | `int` | `10` | 最大滑动次数 |
| `swipe_coords` | `list` | `[360, 1400, 360, 700, 300]` | 滑动参数 `[x1, y1, x2, y2, duration]` |
| `action_on_found` | `str` | `"tap"` | 找到后的动作：`"tap"` 点击 / `"check"` 仅检测 |
| `offset_x` | `int` | `0` | tap 时的 x 偏移 |
| `offset_y` | `int` | `0` | tap 时的 y 偏移 |
| `swipe_wait` | `float` | `1.0` | 每次滑动后的等待时间（秒） |
| `reset_scroll` | `dict` | `None` | 开始查找前先将列表滑回顶部的配置（`swipes`：滑动次数，`swipe_coords`：滑动参数，`swipe_wait`：等待时间） |
| `stop_scroll_if_found` | `dict` | `None` | 停止滑动的检测规则。主规则未命中时，若此规则命中则立即停止滑动并返回 `False`。用途：查找"去领取"时，若当前屏有"去完成"说明已全部领完 |

**返回值：** `bool` — 找到目标返回 `True`，滑动完毕仍未找到返回 `False`。

---

##### `_ensure_page`

```python
_ensure_page(target_page: str, max_back: int = 3, entry_find: dict = None, entry_wait: float = 2) -> bool
```

确保当前在目标页面，如果不在则通过返回+重入导航。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `target_page` | `str` | — | 目标页面名称 |
| `max_back` | `int` | `3` | 最大按返回键次数 |
| `entry_find` | `dict` | `None` | 入口按钮的查找规则，用于直接点击进入目标页面 |
| `entry_wait` | `float` | `2` | 点击入口按钮后的等待时间（秒） |

**返回值：** `bool` — 是否成功到达目标页面。

**导航策略：**
1. 截图识别当前页面，已在目标页面则直接返回
2. 优先尝试 `entry_find` 入口按钮直接进入（避免不必要的返回键）
3. 若入口未找到（可能被弹窗遮挡），按返回键清除遮挡后重试
4. 每次按返回键后都检查是否到达目标页面，并再次尝试 `entry_find`

---

##### `_return_to_game_main`

```python
_return_to_game_main(step: dict, max_attempts: int = None) -> bool
```

统一恢复：确保当前处于天天现金游戏主界面（MGCGameActivity）。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `step` | `dict` | — | 步骤配置，可包含 `home_entry_find`（美团首页入口查找规则）和 `max_attempts` |
| `max_attempts` | `int` | `None` | 最大尝试次数，为 `None` 时从 `step` 中读取，默认 15 |

**返回值：** `bool` — 是否成功恢复到游戏主界面。

**按 Activity 分类循环处理：**

| 分类 | 处理策略 |
|------|----------|
| `third_party`（第三方 App） | `force-stop` 关闭 |
| `other_mini_game`（美团其他小游戏） | 点圆圈按钮关闭浮层 |
| `meituan_home`（美团首页） | 点击"天天现金"图标（OCR 失败则 `am start` 置顶游戏页） |
| `meituan_other`（美团其他页面） | 按返回键 |
| `cash_daily_game`（天天现金游戏） | 成功，结束循环 |

**兜底：** 循环未恢复时，通过 `bring_to_front` 直接把游戏 Activity 置顶/重启。

---

##### `_classify_activity`

```python
_classify_activity(pkg: str, act_base: str) -> str
```

将当前 `(包名, Activity basename)` 分类为恢复策略所用的类别。

| 参数 | 类型 | 说明 |
|------|------|------|
| `pkg` | `str` | 当前前台应用包名 |
| `act_base` | `str` | 当前 Activity 类名的 basename（最后一个 `.` 之后的部分） |

**返回值：** `str` — 分类结果，取值如下：

| 返回值 | 说明 | 判定条件 |
|--------|------|----------|
| `"third_party"` | 第三方 App（非美团） | `pkg != meituan_package` |
| `"cash_daily_game"` | 天天现金主游戏 | `act_base == "MGCGameActivity"`（无后缀） |
| `"other_mini_game"` | 美团其他小游戏 | `act_base` 以 `"MGCGameActivity"` 开头（带数字后缀） |
| `"meituan_home"` | 美团首页/主页 | `act_base` 包含 `MainActivity`/`LauncherActivity`/`HomeActivity` 关键字 |
| `"meituan_other"` | 美团其他页面 | 以上均不匹配 |

---

## logger 模块

### Logger 类

日志记录器，负责任务执行过程中的日志输出和截图归档。每次任务执行会创建一个独立的会话目录（格式：`{task_name}_{YYYYMMDD_HHMMSS}`），日志文件和截图均保存在该目录下。

#### 构造函数

```python
Logger(logs_dir: str)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `logs_dir` | `str` | 日志根目录路径，每次会话会在此目录下创建子目录 |

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `logs_dir` | `str` | 日志根目录路径 |
| `log_file` | `str \| None` | 当前会话的日志文件路径（`log.txt`）；会话未开始时为 `None` |
| `step_count` | `int` | 当前会话已记录的步骤计数 |

#### 公开方法

---

##### `start_session`

```python
start_session(task_name: str)
```

开始新的执行会话。在 `logs_dir` 下创建 `{task_name}_{YYYYMMDD_HHMMSS}` 子目录，并初始化日志文件。

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_name` | `str` | 任务名称，用于生成会话目录名 |

**返回值：** 无。

---

##### `info`

```python
info(msg: str)
```

记录信息日志。同时输出到控制台（`print`）和日志文件（如果会话已开始）。

| 参数 | 类型 | 说明 |
|------|------|------|
| `msg` | `str` | 日志消息内容 |

**返回值：** 无。

**输出格式：** `[HH:MM:SS] <msg>`

---

##### `step`

```python
step(page_name: str, action_name: str, result: str)
```

记录步骤执行结果。自动递增 `step_count` 计数器。

| 参数 | 类型 | 说明 |
|------|------|------|
| `page_name` | `str` | 页面名称 |
| `action_name` | `str` | 动作名称 |
| `result` | `str` | 执行结果描述 |

**返回值：** 无。

**输出格式：** `[HH:MM:SS] 步骤 #N: [page_name] action_name → result`

---

##### `save_screenshot`

```python
save_screenshot(src_path: str, label: str = "")
```

归档截图到当前会话的日志目录。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `src_path` | `str` | — | 源截图文件路径 |
| `label` | `str` | `""` | 截图标签，用于生成归档文件名 |

**返回值：** 无。

**归档文件名格式：** `{step_count:03d}_{label}.png`（如 `005_after_tap.png`）。会话未开始时不执行任何操作。

---

##### `end_session`

```python
end_session(success: bool, summary: str = "")
```

结束当前会话。记录任务结束日志并清理会话状态（`log_file` 和 `_session_dir` 置为 `None`），避免子任务嵌套时指向已关闭的旧目录。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `success` | `bool` | — | 任务是否成功 |
| `summary` | `str` | `""` | 任务执行摘要 |

**返回值：** 无。

**输出格式：** `[HH:MM:SS] ========== 任务结束: 成功/失败 ========== <summary>`
