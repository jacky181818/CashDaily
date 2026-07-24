"""game_auto.core 包初始化模块。

本包提供游戏自动化的核心组件，包括：

- ADB: Android 调试桥操作（截图、点击、滑动、应用管理等）
- Finder / FinderResult: 屏幕元素定位（模板匹配、OCR 文字识别、颜色查找）
- PageManager / PageConfig: 页面识别与状态管理（两级判定：Activity 过滤 + 视觉匹配）
- Engine / TaskConfig: 任务引擎，调度"截图 → 识别 → 执行"自动化循环
- Logger: 日志记录与截图归档
"""
from .adb import ADB
from .finder import Finder, FinderResult
from .page import PageManager, PageConfig
from .engine import Engine, TaskConfig
from .logger import Logger
