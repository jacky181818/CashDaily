"""game_auto 主入口"""
import os
import sys
import yaml
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 将 game_auto 目录加入 Python 路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.adb import ADB
from core.finder import Finder
from core.page import PageManager
from core.engine import Engine
from core.logger import Logger


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="game_auto 游戏自动化引擎")
    parser.add_argument("--task", "-t", type=str, default=None,
                        help="指定任务文件名（如 claim_offline_income.yaml）")
    args = parser.parse_args()

    config_path = os.path.join(BASE_DIR, "config.yaml")
    config = load_config(config_path)

    # 解析路径（相对于 BASE_DIR）
    templates_dir = os.path.join(BASE_DIR, config["templates_dir"])
    pages_dir = os.path.join(BASE_DIR, config["pages_dir"])
    tasks_dir = os.path.join(BASE_DIR, config["tasks_dir"])
    logs_dir = os.path.join(BASE_DIR, config["logs_dir"])

    os.makedirs(logs_dir, exist_ok=True)

    # 初始化各模块
    adb = ADB(config["adb_path"], config.get("device"))
    finder = Finder(templates_dir, config.get("default_threshold", 0.55),
                    ocr_enabled=config.get("ocr_enabled", False))
    page_manager = PageManager(pages_dir)
    logger = Logger(logs_dir)

    # 检查设备连接
    if not adb.is_connected():
        print("[错误] 没有连接的 ADB 设备")
        sys.exit(1)

    state = adb.get_state()
    print(f"[ADB] 设备状态: {state}")

    # 创建引擎
    engine = Engine(adb, finder, page_manager, logger, config)

    # 选择任务
    task_files = [f for f in os.listdir(tasks_dir)
                  if f.endswith(".yaml") or f.endswith(".yml")]

    if not task_files:
        print("[错误] 没有可用的任务配置")
        sys.exit(1)

    if args.task:
        if args.task in task_files:
            selected = task_files.index(args.task)
            print(f"\n命令行指定任务: {args.task}")
        else:
            print(f"[错误] 找不到任务文件: {args.task}")
            print(f"可用任务: {', '.join(task_files)}")
            sys.exit(1)
    else:
        print("\n可用任务:")
        for i, f in enumerate(task_files):
            task_path = os.path.join(tasks_dir, f)
            with open(task_path, "r", encoding="utf-8") as tf:
                td = yaml.safe_load(tf)
            print(f"  {i+1}. {td.get('name', f)} ({f})")

        # 如果只有一个任务，直接运行
        if len(task_files) == 1:
            selected = 0
            print(f"\n自动选择: {task_files[0]}")
        else:
            try:
                selected = int(input("\n请输入任务编号: ")) - 1
            except (ValueError, EOFError):
                selected = 0

    task_path = os.path.join(tasks_dir, task_files[selected])
    task = engine.load_task(task_path)

    print(f"\n开始执行任务: {task.name}")
    success = engine.run_task(task, tasks_dir)

    if success:
        print("\n✓ 任务执行成功!")
    else:
        print("\n✗ 任务执行失败!")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
