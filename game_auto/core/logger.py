"""Logger 模块：日志记录 + 截图归档"""
import os
import time
import shutil
from datetime import datetime


class Logger:
    def __init__(self, logs_dir: str):
        self.logs_dir = logs_dir
        self.log_file = None
        self.step_count = 0
        self._session_dir = None

    def start_session(self, task_name: str):
        """开始新的执行会话"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_dir = os.path.join(self.logs_dir, f"{task_name}_{timestamp}")
        os.makedirs(self._session_dir, exist_ok=True)
        self.log_file = os.path.join(self._session_dir, "log.txt")
        self.step_count = 0
        self.info(f"========== 开始任务: {task_name} ==========")

    def info(self, msg: str):
        """记录信息日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        print(line)
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def step(self, page_name: str, action_name: str, result: str):
        """记录步骤执行结果"""
        self.step_count += 1
        self.info(f"步骤 #{self.step_count}: [{page_name}] {action_name} → {result}")

    def save_screenshot(self, src_path: str, label: str = ""):
        """归档截图到日志目录"""
        if not self._session_dir:
            return
        ext = os.path.splitext(src_path)[1]
        filename = f"{self.step_count:03d}_{label}{ext}"
        dst = os.path.join(self._session_dir, filename)
        try:
            shutil.copy2(src_path, dst)
            self.info(f"截图归档: {filename}")
        except Exception as e:
            self.info(f"截图归档失败: {e}")

    def end_session(self, success: bool, summary: str = ""):
        """结束会话"""
        status = "成功" if success else "失败"
        self.info(f"========== 任务结束: {status} ========== {summary}")
        # 清理会话状态，避免子任务嵌套时 log_file 指向已关闭的旧目录
        self.log_file = None
        self._session_dir = None
