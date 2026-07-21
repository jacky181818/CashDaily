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
| paddleocr（可选） | 文字识别（OCR）。`config.yaml` 中 `ocr_enabled` 控制是否启用 |

安装依赖：

```bash
pip install opencv-python numpy Pillow pyyaml
# 如需 OCR 文字识别（检测弹窗标题/按钮文字），再安装：
pip install paddleocr
```

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
│   │   ├── page.py            # 页面配置管理（page_manager）
│   │   └── logger.py          # 运行日志与截图归档
│   ├── tasks/                 # 任务 YAML（见下方「可用任务」）
│   │   └── popups/            # 弹窗子任务（离线收益 / 连续签到 / 限时福利）
│   ├── pages/                 # 页面识别配置（用于 ensure_page 导航）
│   └── templates/             # 模板图片（关闭按钮等，用于 template 匹配）
├── .gitignore
└── README.md
```

---

## 配置 `config.yaml`

```yaml
adb_path: "D:\\AppBundles\\Scrcpy\\adb.exe"   # ADB 可执行文件路径
device: null                                  # null=自动选择；或填写设备 ID
templates_dir: "templates"                    # 模板目录（相对 game_auto）
pages_dir: "tasks/../pages"                   # 页面目录
tasks_dir: "tasks"                            # 任务目录
logs_dir: "logs"                              # 日志目录（运行期生成，已 gitignore）
default_retry: 3
default_timeout: 10
default_wait_after: 1.5
ocr_enabled: true                             # 是否启用 OCR 文字识别
```

> 手机分辨率按 **720×1560** 设计，截图坐标即输入坐标，无需缩放。

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
| `ocr` | OCR 文字识别 | `text`, `exact_match`, `roi`, `threshold` |
| `ocr_relative` | 相对锚点找文字（如「去完成」相对「任务名」） | `anchor_text`, `target_text`, `anchor_roi`, `x_range`, `y_range` |
| `color` | 颜色识别 | `target_color`, `roi` |

点击可通过 `offset_x` / `offset_y` 在识别结果坐标上做偏移（例如点击文字上方图标）。

### 动作 `action`

`tap` · `swipe`（需 `swipe_coords: [x1,y1,x2,y2,duration]`）· `back` · `home` · `wait`（需 `duration`）· `if_found`（配合 `then_steps` 条件分支）· `run_subtask`（配合 `task: xxx.yaml` 调用子任务）· `ensure_page`（配合 `target_page` 导航）· `check`（仅校验，配合 `break_loop_if_not_found` / `skip_if_not_found`）。

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

- **`templates/`**：用于 `template` 类型匹配的图片（如关闭按钮 `close_btn_daily_task.png`）。`process: raw` + `threshold: 0.85` 对非透明、渐变背景图标更稳定。
- **`pages/`**：页面识别配置，`identify` 用于判断当前处于哪个页面，`ensure_page` 据此导航（如 `daily_task_popup`）。

---

## 注意事项

1. 运行前请确保：手机已开启 USB 调试、ADB 已连接（`adb devices` 可见）、游戏已安装或可通过美团小程序进入。
2. 主界面存在一块**滚动轮播区域**（约 `x:120, y:280`，宽高 ~450×220），内容为「重置专属奖励 / 从美团币入口访问 / 幸运红包 / 惊喜礼包」——**它不是弹窗，无法关闭**。所有 OCR 检测的 `roi` 必须避开该区域（`y < 530`），且不能用轮播文字作为弹窗判定特征。
3. 主界面弹窗只处理「离线收益 / 连续签到 / 限时福利」三大类，判定依据是弹窗**标题文字**；「恭喜获得 / 开心收下 / 立即领取」属于子任务内部弹窗，由各自子任务处理。
4. 运行日志与截图保存在 `game_auto/logs/`（`logs_YYYYMMDD_HHMMSS/`），已加入 `.gitignore`，不纳入版本库。

---

## 重新生成调试素材

运行期产生的调试截图、日志、`__pycache__` 等均不提交。如需清理本地产物：

```bash
# 已通过 .gitignore 忽略，正常 git 不会跟踪它们
git status        # 确认只有源码与模板被跟踪
```
