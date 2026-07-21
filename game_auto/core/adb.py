"""ADB 操作模块：截图、tap、swipe、启动应用"""
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
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

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

        self.run(["shell", "screencap", "-p", device_tmp])
        self.run(["pull", device_tmp, win_path])
        self.run(["shell", "rm", "-f", device_tmp])

        if os.path.exists(save_path):
            return save_path
        raise RuntimeError(f"截图保存失败: {save_path}")

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
