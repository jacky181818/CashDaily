# CashDaily · 天天现金（美团小游戏）自动化脚本

基于 `ADB + OpenCV 模板匹配 + OCR` 的安卓游戏自动化引擎，用于自动完成美团小游戏「天天现金」的日常任务：一键合成、捕捉精灵、领取每日任务，以及处理主界面各类弹窗。

任务流程完全由 **YAML 配置驱动**，无需修改 Python 代码即可调整点击坐标、识别文字、循环与分支逻辑。

---

## 环境依赖

| 依赖 | 说明 |
| --- | --- |
| Python | 3.12 及以上 |
| ADB | Android Debug Bridge，需能连接手机/模拟器 |
| opencv-python | 模板匹配、颜色识别 |
| numpy | 图像处理 |
| Pillow | 截图读写 |
| pyyaml | 任务 YAML 解析 |
| `rapidocr-onnxruntime` | 轻量级 OCR 文字识别引擎。`config.yaml` 中 `ocr_enabled` 控制是否启用 |

安装依赖：

```bash
pip install opencv-python numpy Pillow pyyaml
# 如需 OCR 文字识别（检测弹窗标题/按钮文字），再安装：
pip install rapidocr-onnxruntime
# 或一次性安装所有依赖：
pip install -r requirements.txt
```

> 项目根目录提供了 `requirements.txt`，可直接 `pip install -r requirements.txt` 安装核心依赖。OCR 依赖（`rapidocr-onnxruntime`）需额外安装。

> OCR 是可选的：若 `ocr_enabled: false`，则模板匹配（`template` 类型）仍可正常工作，仅 `ocr` / `ocr_relative` 类型的查找会跳过。

---

## 目录结构

```
CashDaily/
├── game_auto/                 # 自动化工程根目录
│   ├── main.py                # 程序入口：python main.py --task <任务>.yaml
│   ├── config.yaml            # 全局配置（ADB 路径、设备、目录、OCR 开关等）
│   ├── core/                  # 引擎核心代码
│   │   ├── adb.py             # ADB 封装：截图 / tap / swipe / back / home
│   │   ├── finder.py          # 识别引擎：template / ocr / ocr_relative / color
│   │   ├── engine.py          # 任务引擎：步骤调度、循环、条件分支、子任务
│   │   ├── page.py            # 页面识别（两级判定：Activity 容器过滤 + 视觉细配）
│   │   └── logger.py          # 运行日志与截图归档
│   ├── tasks/                 # 任务 YAML（见下方「可用任务」）
│   │   └── popups/            # 弹窗子任务（离线收益 / 连续签到 / 限时福利）
│   ├── pages/                 # 页面识别配置（用于 ensure_page 导航）
│   └── templates/             # 模板图片（关闭按钮等，用于 template 匹配）
├── doc/                       # 项目文档
│   └── engine.md              # 引擎模块详细文档
├── .gitignore
├── requirements.txt           # Python 依赖清单
└── README.md
```

---

## 配置 `config.yaml`

```yaml
adb_path: "D:\\AppBundles\\Scrcpy\\adb.exe"   # ADB 可执行文件路径
device: null                                  # null=自动选择；或填写设备 ID
templates_dir: "templates"                    # 模板目录（相对 game_auto）
pages_dir: "pages"                            # 页面目录
tasks_dir: "tasks"                            # 任务目录
logs_dir: "logs"                              # 日志目录（运行期生成，已 gitignore）
default_retry: 3
default_timeout: 10
default_wait_after: 1.5
ocr_enabled: true                             # 是否启用 OCR 文字识别

# 美团包名 / 游戏主界面 Activity（用于「返回游戏主界面」识别与恢复）
meituan_package: "com.sankuai.meituan"
meituan_game_activity: "com.meituan.android.mgc.container.MGCGameActivity"

# 美团「首页/主页」Activity 类名关键字（两级判定中分类为「美团首页」时使用）
# 命中这些关键字的 Activity 视为美团首页，恢复时点击「天天现金」图标进入游戏。
meituan_home_activity_keywords:
  - "MainActivity"
  - "LauncherActivity"
  - "HomeActivity"
```

> 手机分辨率按 **720×1560** 设计，截图坐标即输入坐标，无需缩放。
>
> `meituan_game_activity` 即「天天现金」游戏主界面的 Activity（`MGCGameActivity`，**无后缀**）；美团「其他小游戏」通常是 `MGCGameActivity1` / `MGCGameActivity2`（带后缀），靠此区别判定是否需要点右上角圆圈按钮关闭浮层。

---

## 使用方式

在 `game_auto/` 目录下运行入口脚本，通过 `--task` 指定任务 YAML：

```bash
cd game_auto
python main.py --task daily_routine.yaml          # 完整日常：启动→弹窗→合成→捕捉→合成→弹窗→领任务
python main.py --task merge_all.yaml              # 仅一键合成
python main.py --task catch_spirit.yaml           # 仅捕捉精灵
python main.py --task claim_daily_task.yaml       # 仅领取每日任务
python main.py --task handle_main_popups.yaml     # 仅处理主界面弹窗
```

### 可用任务

| 任务文件 | 作用 |
| --- | --- |
| `daily_routine.yaml` | 完整日常流程（子任务串联）：启动并进入 → 处理弹窗 → 一键合成 → 捕捉精灵 → 再次合成 → 再次处理弹窗 → 领取每日任务 |
| `launch_and_enter.yaml` | 启动美团并进入「天天现金」小程序 |
| `handle_main_popups.yaml` | 循环检测并分发三大主界面弹窗（离线收益 / 连续签到 / 限时福利） |
| `merge_all.yaml` | 一键合成（固定 20 轮循环，顺带关闭合成中可能弹出的广告 / 天降福利 / 评审得奖弹窗） |
| `catch_spirit.yaml` | 捕捉精灵：捕捉 → 去捕捉 → 确认 → 免费升级 → 浏览 → 返回主界面 |
| `claim_daily_task.yaml` | 领取每日任务：去领取奖励 + 各类浏览任务 |
| `main_three_tasks.yaml` | 从已处于的主界面直接执行 合成 → 捕捉 → 领任务（跳过启动/弹窗） |
| `claim_offline_income.yaml` | 领取离线收益（单次） |
| `claim_offline_income_continue.yaml` | 领取离线收益（连续签到后继续） |

弹窗子任务（`tasks/popups/`）由 `handle_main_popups.yaml` 自动调用，一般无需单独运行。

---

## 任务 YAML 结构

每个任务由若干 **步骤（step）** 组成，支持普通步骤、循环（`loop`）、条件分支（`if_found`）、子任务（`run_subtask`）、页面导航（`ensure_page`）。

### 步骤示例

```yaml
steps:
  - name: 点击一键合成
    find:                          # 查找目标（见下方「查找类型」）
      type: ocr
      text: "一键合成"
      threshold: 0.8
      roi: [0, 900, 720, 660]      # [x, y, w, h] 起始坐标 + 宽高
    action: tap                    # 找到后执行的动作
    wait_after: 2.0                # 动作后等待（秒）
    skip_if_not_found: true        # 找不到则跳过（不报错）
```

### 查找类型 `find.type`

| 类型 | 说明 | 关键字段 |
| --- | --- | --- |
| `template` | 图片模板匹配 | `template: xxx.png`, `process: raw`, `threshold` |
| `ocr` | OCR 文字识别 | `text`（字符串或字符串列表，列表时命中任一即返回）, `exact_match`, `roi`, `threshold` |
| `ocr_relative` | 相对锚点找文字（如「去完成」相对「任务名」） | `anchor_text`, `target_text`, `anchor_roi`, `x_range`, `y_range` |
| `color` | 颜色识别 | `target_color`, `roi` |
| `fixed` | 返回固定坐标（无需截图，用于已知的常驻按钮） | `coords: [x, y]` |

点击可通过 `offset_x` / `offset_y` 在识别结果坐标上做偏移（例如点击文字上方图标）。

### 动作 `action`

| 动作 | 说明 | 关键字段 |
| --- | --- | --- |
| `tap` | 点击识别目标 | `find` + `offset_x/offset_y` |
| `swipe` | 滑动 | `swipe_coords: [x1,y1,x2,y2,duration]` |
| `back` | 按返回键 | — |
| `home` | 按 HOME 键 | — |
| `wait` | 等待固定秒数 | `duration` |
| `browse` | 浏览式等待：在 `duration` 秒内循环上下来回滑动（模拟真人浏览，满足「浏览任务」计时） | `duration` |
| `scroll_find` | 滚动查找目标，找不到则上滑继续 | `find` + `max_swipes` + `swipe_coords`；`stop_scroll_if_found`（可选，提前终止信号） |
| `if_found` | 条件分支，命中 `find` 才执行 `then_steps` | `find` + `then_steps`；可选 `use_last_screenshot: true`（复用上一步截图，捕捉「点击后立即弹出、很快消失」的 toast，如「放置区已满」；未命中再新截一张兜底） |
| `run_subtask` | 调用子任务 | `task: xxx.yaml` |
| `ensure_page` | 确保当前在 `target_page`；不在则尝试导航回该页 | `target_page`, `max_back_attempts`, `entry_find`, `recovery` |
| `return_to_game_main` | 统一「返回天天现金游戏主界面」恢复（详见下文） | `home_find`（可选） |
| `return_to_task` | 返回每日任务弹窗（美团内按返回键；第三方 App 则 force-stop 后恢复） | — |
| `close_mgc_overlay` | 关闭美团「其他小游戏」同 Activity 浮层（圆圈按钮）；天天现金主游戏内自动跳过 | `find`（圆圈模板）, `close_coords` |
| `check` | 仅校验，配合 `break_loop_if_not_found` / `skip_if_not_found` | `find` |

`ensure_page` 的 `recovery` 字段可设为 `return_to_game_main`：当导航失败（例如误按返回键回到美团首页、或跳到第三方 App）时，先执行统一恢复把界面拉回 `MGCGameActivity`，再重试一次导航，从而避免任务卡死。

### `scroll_find` 示例

```yaml
  - name: 滚动查找去领取
    action: scroll_find
    find:
      type: ocr
      text: "去领取"
      roi: [25, 680, 670, 870]
    max_swipes: 5
    swipe_coords: [360, 1200, 360, 800, 300]
    swipe_wait: 1.0
    stop_scroll_if_found:          # 可选：停止滑动的检测规则
      type: ocr                    # 当前屏主规则未命中时，若此规则命中则立即停止滑动
      text: "去完成"               # 用途：查找"去领取"时，若当前屏有"去完成"说明已全部领完
      roi: [25, 680, 670, 870]
```

### 循环与分支

```yaml
  - name: 循环领取
    loop: 50                       # 循环次数
    loop_break_on_fail: false
    loop_steps:
      - name: 点击去领取
        find: { type: ocr, text: "去领取", exact_match: true }
        action: tap
        break_loop_if_not_found: true   # 找不到目标 → 正常结束循环
```

- 任务级 `precondition`：前置条件，满足才执行（如「大量精灵」出现才捕捉）。
- 任务级 `sub_tasks`：workflow 模式，按顺序串联多个子任务。

---

## 模板与页面

- **`templates/`**：用于 `template` 类型匹配的图片（如关闭按钮 `close_btn_daily_task.png`、`close_btn_mgc_overlay.png` 圆圈按钮）。`process: raw` + `threshold: 0.85` 对非透明、渐变背景图标更稳定。
- **`pages/`**：页面识别配置，`identify` 用于判断当前处于哪个页面，`ensure_page` 据此导航（如 `daily_task_popup`）。

### 两级页面识别（Activity 容器过滤 + 视觉细配）

天天现金里的所有弹窗（每日任务、恭喜获得、浏览弹窗、离线收益等）**都共享同一个 `MGCGameActivity`**。因此单纯靠文字/图标很容易把「美团首页或其他小游戏里出现的相同字样」误判成天天现金弹窗。为此 `PageManager` 采用两级识别：

1. **第一级（容器过滤，粗、快、100% 可靠）**：页面可声明 `package` / `activity` / `activity_suffix` / `activity_not` 约束。引擎先通过一次 `adb.get_current_activity()` 取当前 `(pkg, act)`，basename 不满足约束的页面**直接跳过**，不做任何截图匹配。这一步彻底杜绝跨容器误判。
2. **第二级（视觉细配，必要）**：
   - 先对**普通弹窗页**做模板/OCR/颜色匹配；
   - 全部未命中时，再用**纯 Activity 页面**（如 `cash_daily_game`，`activity: MGCGameActivity`）兜底，识别出「游戏主界面（无弹窗）」。纯 Activity 页延迟到最后参与，避免遮蔽具体弹窗。

页面 YAML 示例（弹窗页带容器约束）：

```yaml
name: daily_task_popup
package: "com.sankuai.meituan"          # 第一级：只在美团内识别
activity: "MGCGameActivity"             # 第一级：且必须在天天现金主游戏 Activity 内
identify:
  - type: ocr
    text: "每日任务"
    roi: [500, 1400, 180, 120]
    threshold: 0.4
```

纯 Activity 兜底页示例：

```yaml
name: cash_daily_game
description: 天天现金游戏主界面（无弹窗）
activity: "MGCGameActivity"
identify:
  - type: activity                     # 无需截图，仅看 Activity
    activity: "MGCGameActivity"
```

> `get_current_activity()` 返回的是**完整类名**（含 `.`，如 `com.meituan.android.mgc.container.MGCGameActivity`），取 basename 一律用最后一个 `.` 切分，不能用 `/`。

### 统一返回游戏主界面 `return_to_game_main`

游戏任务执行过程中可能因「返回键」「第三方 App 跳转」等偏离游戏主界面。为此提供统一恢复动作，按当前 Activity 分类循环处理，直到回到 `MGCGameActivity`：

| 当前状态（Activity 类别） | 恢复动作 |
| --- | --- |
| 已在 `MGCGameActivity`（天天现金主游戏） | 已是目标，直接成功 |
| 第三方 App（如京东 `BabelActivity`、淘宝） | `force-stop` 直接关闭该 App（不置后台） |
| 美团其他小游戏浮层（`MGCGameActivity1/2`） | 点右上角圆圈按钮关闭浮层（**天天现金主游戏内的圆圈按钮是「关闭游戏」，绝不点**） |
| 美团首页（`MainActivity` 等） | 点击「天天现金」图标进入游戏；OCR 失败则 `am start` 置顶游戏页 |
| 美团其他页面（如 `MSVPageActivity`） | 按返回键 |
| 以上循环仍无法恢复 | `am start` 重新进入游戏；再不行则放弃（交由 `ensure_page`/`launch_and_enter` 重新进入） |

你之前遇到的跳转链 `京东(Babel) → 美团(MSV) → 京东(Babel)` 现在会被正确处理：force-stop 京东 → 对美团中转页按返回键 → 直到回到游戏主界面。`launch_and_enter.yaml` 在点击「天天现金」后会用 `return_to_game_main` 校验是否真的进入了 `MGCGameActivity`；`claim_daily_task.yaml` 中所有 `ensure_page(daily_task_popup)` 都挂了 `recovery: return_to_game_main` 兜底。

---

## 注意事项

1. 运行前请确保：手机已开启 USB 调试、ADB 已连接（`adb devices` 可见）、游戏已安装或可通过美团小程序进入。
2. 主界面存在一块**滚动轮播区域**（约 `x:120, y:280`，宽高 ~450×220），内容为「重置专属奖励 / 从美团币入口访问 / 幸运红包 / 惊喜礼包」——**它不是弹窗，无法关闭**。所有 OCR 检测的 `roi` 必须避开该区域（`y < 530`），且不能用轮播文字作为弹窗判定特征。
3. 主界面弹窗只处理「离线收益 / 连续签到 / 限时福利」三大类，判定依据是弹窗**标题文字**；「恭喜获得 / 开心收下 / 立即领取」属于子任务内部弹窗，由各自子任务处理。
4. 运行日志与截图保存在 `game_auto/logs/`（`logs_YYYYMMDD_HHMMSS/`），已加入 `.gitignore`，不纳入版本库。
5. **第三方 App 跳转**：每日任务「去完成」常会拉起京东/淘宝等第三方 App。`return_to_game_main` / `return_to_task` 会直接 `force-stop` 关闭第三方 App（而非置于后台），再用 `am start -f 0x20000000` 把美团游戏任务栈置顶，回到 `MGCGameActivity`。`get_current_activity()` 在 `force-stop` 瞬间可能返回旧焦点，故恢复采用「重试 + 核验」而非乐观判断。**切勿在美团其他小游戏（`MGCGameActivity1/2`）里点圆圈按钮**——那只会关闭浮层；而在天天现金主游戏（`MGCGameActivity`）里同一个圆圈按钮是「关闭整个游戏」，引擎已自动跳过。

---

## 调试手段

### 获取当前活动的 Activity

```bash
adb shell dumpsys window | findstr "mCurrentFocus"
```

### OCR 识别图片内容

```bash
python -c "from rapidocr_onnxruntime import RapidOCR; ocr = RapidOCR(); result, _ = ocr(r'截图路径.png'); [print(f'{item[1]:20s} conf={item[2]:.3f} box={item[0]}') for item in (result or [])]"
```

示例（替换为实际截图路径）：

```bash
python -c "from rapidocr_onnxruntime import RapidOCR; ocr = RapidOCR(); result, _ = ocr(r'D:\MyFavorite\workspace\junan\src\CashDaily\game_auto\logs\一键合成_20260723_154334\010_if_found_检测并关闭评审得奖弹窗.png'); [print(f'{item[1]:20s} conf={item[2]:.3f} box={item[0]}') for item in (result or [])]"
```

---

## 重新生成调试素材

运行期产生的调试截图、日志、`__pycache__` 等均不提交。如需清理本地产物：

```bash
# 已通过 .gitignore 忽略，正常 git 不会跟踪它们
git status        # 确认只有源码与模板被跟踪
```
