"""ADB 操作模块：截图、tap、swipe、启动应用"""
import re
import subprocess
import os
import time
import tempfile
from pathlib import Path


class ADB:
    def __init__(self, adb_path: str, device: str = None):
        self.adb_path = adb_path
        self.device = device

    def _cmd(self, args: list[str]) -> list[str]:
        cmd = [self.adb_path]
        if self.device:
            cmd += ["-s", self.device]
        cmd += args
        return cmd

    def run(self, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        cmd = self._cmd(args)
        # 用 text=True + errors="replace" 容错解码，避免 dumpsys 等输出中的非法
        # 多字节序列在中文 Windows(GBK)下触发 UnicodeDecodeError 导致 stdout 为 None
        return subprocess.run(cmd, capture_output=True, text=True,
                              errors="replace", timeout=timeout)

    def get_state(self) -> str:
        r = self.run(["get-state"])
        return r.stdout.strip()

    def is_connected(self) -> bool:
        r = self.run(["devices"])
        lines = r.stdout.strip().splitlines()
        # 第二行开始是设备列表
        for line in lines[1:]:
            if "device" in line and not "offline" in line:
                return True
        return False

    def screenshot(self, save_path: str = None) -> str:
        """截图并保存到本地，返回文件路径"""
        if save_path is None:
            save_path = os.path.join(tempfile.gettempdir(), f"_adb_screenshot_{int(time.time())}.png")

        device_tmp = "/sdcard/_auto_capture_tmp.png"
        # 用 cygpath 转换路径（Windows Git Bash 环境）
        win_path = save_path
        if os.name == "nt" or "mingw" in os.environ.get("MSYSTEM", "").lower():
            try:
                result = subprocess.run(
                    ["cygpath", "-w", save_path],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    win_path = result.stdout.strip()
            except Exception:
                pass

        max_retries = 3
        for attempt in range(max_retries):
            self.run(["shell", "screencap", "-p", device_tmp])
            self.run(["pull", device_tmp, win_path])
            self.run(["shell", "rm", "-f", device_tmp])

            if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                return save_path

            # 截图为空或不存在，等待后重试
            if attempt < max_retries - 1:
                print(f"[ADB] 截图为空，第 {attempt + 1} 次重试...")
                time.sleep(1)

        raise RuntimeError(f"截图保存失败（重试 {max_retries} 次后仍为空）: {save_path}")

    def tap(self, x: int, y: int):
        """点击指定坐标"""
        self.run(["shell", "input", "tap", str(x), str(y)])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300):
        """滑动"""
        self.run(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])

    def press_back(self):
        """按返回键"""
        self.run(["shell", "input", "keyevent", "4"])

    def press_home(self):
        """按 HOME 键"""
        self.run(["shell", "input", "keyevent", "3"])

    def start_app(self, package: str, activity: str, wait: bool = True):
        """启动应用"""
        if wait:
            self.run(["shell", "am", "start", "-W", "-n", f"{package}/{activity}"], timeout=60)
        else:
            self.run(["shell", "am", "start", "-n", f"{package}/{activity}"])

    def force_stop(self, package: str):
        """强制停止应用"""
        self.run(["shell", "am", "force-stop", package])

    def get_screen_size(self) -> tuple[int, int]:
        """获取屏幕尺寸"""
        r = self.run(["shell", "wm", "size"])
        # 输出格式: Physical size: 720x1560
        for line in r.stdout.splitlines():
            if "Physical" in line:
                parts = line.split(":")[-1].strip().split("x")
                return int(parts[0]), int(parts[1])
        return 720, 1560  # 默认值

    def get_current_package(self) -> str:
        """返回当前前台应用的包名（解析 dumpsys window 的 mCurrentFocus）

        示例输出: mCurrentFocus=Window{5fa1443 u0 com.sankuai.meituan/...}
        返回: com.sankuai.meituan
        """
        # dumpsys window 输出很大且可能含非法字节；errors="replace" 已容错，
        # 这里再用 or "" 防御极端情况下 stdout 为 None
        r = self.run(["shell", "dumpsys", "window"])
        out = r.stdout or ""
        for line in out.splitlines():
            if "mCurrentFocus" in line:
                m = re.search(r"(\S+)/", line.strip())
                if m:
                    return m.group(1)
        return ""

    def get_current_activity(self) -> tuple[str, str]:
        """返回当前前台应用的 (包名, Activity 全类名)，解析 dumpsys window 的 mCurrentFocus

        示例输出: mCurrentFocus=Window{9afc764 u0 com.sankuai.meituan/com.meituan.android.mgc.container.MGCGameActivity}
        返回: ("com.sankuai.meituan", "com.meituan.android.mgc.container.MGCGameActivity")

        注意：天天现金主游戏为 MGCGameActivity（无后缀）；美团其他小游戏为
        MGCGameActivity1 / MGCGameActivity2 等（带数字后缀），window id 会变，
        但 Activity 类名稳定，可用于区分“当前是否在天天现金主游戏内”。
        """
        r = self.run(["shell", "dumpsys", "window"])
        out = r.stdout or ""
        for line in out.splitlines():
            if "mCurrentFocus" in line:
                m = re.search(r"(\S+)/(\S+)", line.strip())
                if m:
                    pkg = m.group(1)
                    act = m.group(2).rstrip("}")
                    return (pkg, act)
        return ("", "")

    def bring_to_front(self, package: str, game_activity: str = None, retries: int = 3):
        """把美团游戏页（MGCGameActivity，每日任务弹窗所在）带回前台。

        注意：monkey -p <pkg> -c LAUNCHER 会把该 App 的 LAUNCHER 主页（MainActivity）
        带到前台，而非游戏页，所以这里**优先**用 am start 直接启动游戏 Activity：
          - 若游戏 Activity 为 singleTask/singleInstance（美团游戏通常如此），则保留
            现有任务栈与每日任务弹窗状态，仅把它置顶；
          - 若实例已被回收，则重启游戏，由后续 ensure_page 重新打开每日任务弹窗。
        monkey 仅作为兜底手段（极少走到）。

        容错：force-stop 后第三方 App 可能重启抢占焦点、或 dumpsys 在 force-stop 瞬间
        返回旧焦点，因此这里**多次重试**并核验当前包名，确保真的回到美团再返回成功。
        """
        for attempt in range(retries):
            # 方式一：优先 am start 直接启动游戏 Activity（带 REORDER_TO_FRONT 标志，
            # 实例已存在时不重建，保留弹窗状态）
            if game_activity:
                self.run(["shell", "am", "start",
                          "-n", f"{package}/{game_activity}",
                          "-f", "0x20000000"], timeout=30)
            time.sleep(2.5)
            pkg, _ = self.get_current_activity()
            if pkg == package:
                return True
            # 方式二：兜底 monkey 启动 launcher activity
            self.run(["shell", "monkey", "-p", package,
                      "-c", "android.intent.category.LAUNCHER", "1"], timeout=30)
            time.sleep(2.5)
            if self.get_current_package() == package:
                return True
        return self.get_current_package() == package
