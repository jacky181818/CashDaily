"""Engine 模块：任务引擎，调度截图 → 识别 → 执行循环"""
import yaml
import os
import time
from .finder import FinderResult


class TaskConfig:
    """任务配置信息，从 YAML 文件加载。

    支持两种执行模式：
    - 普通步骤模式：按 ``steps`` 列表顺序执行每个步骤。
    - 子任务串联模式（workflow）：按 ``sub_tasks`` 列表依次加载并执行子任务文件。

    Attributes:
        name: 任务名称。
        steps: 步骤列表，每个步骤为一个字典。
        pre_commands: 执行前的 adb shell 命令列表。
        precondition: 前置条件配置，满足才执行任务。
        sub_tasks: 子任务文件名列表（workflow 模式）。
    """

    def __init__(self, data: dict):
        """初始化任务配置。

        Args:
            data: 从 YAML 文件加载的任务配置字典，必须包含 ``name`` 键。
        """
        self.name = data["name"]
        self.steps = data.get("steps", [])
        self.pre_commands = data.get("pre_commands", [])  # 执行前的 adb shell 命令
        self.precondition = data.get("precondition")  # 前置条件：满足才执行任务
        self.sub_tasks = data.get("sub_tasks", [])  # 子任务列表（workflow模式）


class Engine:
    """任务执行引擎，调度"截图 → 页面识别 → 动作执行"的自动化循环。

    Engine 是整个自动化框架的核心调度器，负责：
    - 加载和执行任务配置（普通步骤 / 子任务串联 / 循环步骤）
    - 页面等待与识别，根据当前页面执行对应动作
    - 多种动作类型支持（tap、swipe、back、browse、scroll_find、ensure_page 等）
    - 异常恢复（返回游戏主界面、关闭浮层、force-stop 第三方应用等）
    - 条件分支（if_found）和循环等待（wait_until_found）

    Attributes:
        adb: ADB 实例，用于设备操作。
        finder: Finder 实例，用于屏幕元素定位。
        page_manager: PageManager 实例，用于页面识别。
        logger: Logger 实例，用于日志记录。
        config: 全局配置字典。
        default_retry: 默认重试次数。
        default_timeout: 默认超时时间（秒）。
        default_wait: 默认动作后等待时间（秒）。
        screenshot_cache: 最近一次截图的文件路径缓存。
    """

    def __init__(self, adb, finder, page_manager, logger, config: dict):
        """初始化任务引擎。

        Args:
            adb: ADB 实例，提供设备操作能力。
            finder: Finder 实例，提供屏幕元素定位能力。
            page_manager: PageManager 实例，提供页面识别能力。
            logger: Logger 实例，提供日志记录能力。
            config: 全局配置字典，可包含 ``default_retry``、``default_timeout``、
                    ``default_wait_after``、``meituan_package``、``meituan_game_activity`` 等键。
        """
        self.adb = adb
        self.finder = finder
        self.page_manager = page_manager
        self.logger = logger
        self.config = config
        self.default_retry = config.get("default_retry", 3)
        self.default_timeout = config.get("default_timeout", 10)
        self.default_wait = config.get("default_wait_after", 1.5)
        self.screenshot_cache = None

    def load_task(self, task_path: str) -> TaskConfig:
        """加载任务配置"""
        with open(task_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return TaskConfig(data)

    def run_task(self, task: TaskConfig, tasks_dir: str = None) -> bool:
        """执行完整任务（支持普通步骤和子任务串联两种模式）"""
        self._current_tasks_dir = tasks_dir
        self.logger.start_session(task.name)

        # 执行前置命令
        for cmd in task.pre_commands:
            self.logger.info(f"执行前置命令: {cmd}")
            self.adb.run(["shell", cmd], timeout=60)
            time.sleep(5)  # 等待应用启动

        # 检查前置条件
        if task.precondition:
            find_spec = task.precondition.get("find")
            on_fail = task.precondition.get("on_fail", "skip")
            self.logger.info(f"检查前置条件: {find_spec}")

            screenshot_path = self._take_screenshot()
            self.logger.save_screenshot(screenshot_path, "precondition")
            result = self._execute_find_action(find_spec, "tap", {}, screenshot_path)

            if result is None or not result.found:
                self.logger.info(f"前置条件不满足 (on_fail={on_fail})")
                if on_fail == "skip":
                    self.logger.end_session(True, "前置条件不满足，跳过任务")
                    return True
                else:
                    self.logger.end_session(False, "前置条件不满足")
                    return False
            else:
                self.logger.info(f"前置条件满足: {result.detail}")

        # 子任务串联模式（workflow）
        if task.sub_tasks and tasks_dir:
            return self._run_sub_tasks(task, tasks_dir)

        # 普通步骤模式
        for i, step in enumerate(task.steps):
            step_desc = step.get("name", step.get("page", f"步骤{i+1}"))
            self.logger.info(f"--- 步骤 {i+1}/{len(task.steps)}: {step_desc} ---")

            # 检查是否为循环步骤
            loop_count = step.get("loop")
            if loop_count is not None:
                loop_result = self._execute_loop(step)
                # 循环失败不终止任务，继续后续步骤
                if not loop_result:
                    self.logger.info(f"循环步骤未完全完成，继续后续步骤")
                continue

            # 普通步骤
            success = self._process_step(step)
            if not success:
                self.logger.end_session(False, f"步骤 {step_desc} 失败")
                return False

        self.logger.end_session(True, f"完成 {len(task.steps)} 个步骤")
        return True

    def _execute_loop(self, step: dict) -> bool:
        """执行循环步骤"""
        loop_count = step.get("loop", 1)
        loop_steps = step.get("loop_steps", [])
        loop_name = step.get("name", "循环")
        loop_break_on_fail = step.get("loop_break_on_fail", True)

        completed_iterations = 0
        break_outer = False
        for iteration in range(loop_count):
            self.logger.info(f"=== {loop_name} 迭代 {iteration+1}/{loop_count} ===")
            iteration_success = True

            for j, sub_step in enumerate(loop_steps):
                sub_desc = sub_step.get("name", sub_step.get("page", f"子步骤{j+1}"))
                self.logger.info(f"  子步骤 {j+1}/{len(loop_steps)}: {sub_desc}")

                success = self._process_step(sub_step)
                if not success:
                    # 检查是否为 break_loop_if_not_found（目标未找到时正常结束循环）
                    if sub_step.get("break_loop_if_not_found", False):
                        self.logger.info(f"  目标未找到，触发 break_loop_if_not_found，正常结束循环")
                        iteration_success = False
                        break_outer = True
                        break  # 结束当前迭代

                    # 检查是否为 skip_if_not_found（子步骤失败时跳过，继续外层循环）
                    if sub_step.get("skip_if_not_found", False):
                        self.logger.info(f"  子步骤 {sub_desc} 失败，但 skip_if_not_found=True，继续外层循环")
                        continue

                    self.logger.info(f"  子步骤 {sub_desc} 失败")
                    iteration_success = False
                    break

                # 检查是否为 break_loop_if_found（目标找到时结束循环）
                # 用于检测 toast 等信号，找到则表示循环完成
                if sub_step.get("break_loop_if_found", False):
                    self.logger.info(f"  目标已找到，触发 break_loop_if_found，正常结束循环")
                    iteration_success = True
                    break_outer = True
                    break  # 结束当前迭代

            if iteration_success:
                completed_iterations += 1
            elif loop_break_on_fail:
                self.logger.info(f"循环 {loop_name} 在迭代 {iteration+1} 中断")
                break
            # 如果 loop_break_on_fail=False，继续下一次迭代

            if break_outer:
                self.logger.info(f"循环 {loop_name} 触发 break_loop_if_found，完全结束")
                break

        self.logger.info(f"循环 {loop_name} 结束，共完成 {completed_iterations}/{loop_count} 次迭代")
        return completed_iterations > 0

    def _process_step(self, step: dict) -> bool:
        """处理单个步骤（普通步骤或循环子步骤）"""
        page_name = step.get("page")

        if page_name:
            # 页面步骤：识别页面并执行动作
            identified = self._wait_for_page(page_name)
            if not identified:
                fallback = step.get("fallback", {})
                fb_action = fallback.get("action", "abort")
                fb_retry = fallback.get("retry", 1)

                if fb_action == "back":
                    for _ in range(fb_retry):
                        self.adb.press_back()
                        time.sleep(1)
                    identified = self._wait_for_page(page_name)
                elif fb_action == "skip":
                    self.logger.info(f"跳过页面步骤: {page_name}")
                    return True
                elif fb_action == "abort":
                    self.logger.info(f"无法到达页面 {page_name}")
                    return False

                if not identified:
                    self.logger.info(f"fallback 后仍无法到达 {page_name}")
                    return False

            page_config = self.page_manager.pages.get(page_name)
            if page_config:
                success = self._execute_actions(page_config)
                if not success:
                    return False
            return True

        else:
            # 直接步骤：执行动作
            action_type = step.get("action", "tap")
            step_name = step.get("name", "未命名")
            wait_before = step.get("wait_before", 0)
            wait_after = step.get("wait_after", self.default_wait)
            skip_if_not_found = step.get("skip_if_not_found", False)

            # wait_before: 执行动作前先等待
            if wait_before > 0:
                self.logger.info(f"[等待] {wait_before} 秒 ({step_name})")
                time.sleep(wait_before)

            if action_type == "back":
                self.adb.press_back()
                self.logger.step("直接", step_name, "按下返回键 KEYCODE_BACK")
                time.sleep(wait_after)
                screenshot_after = self._take_screenshot()
                self.logger.save_screenshot(screenshot_after, f"after_{step_name}")
                return True

            elif action_type == "return_to_task":
                # 从浏览/任务页面返回每日任务弹窗：统一走“返回游戏主界面”逻辑。
                # _return_to_game_main 会按 Activity 分类处理
                # 第三方App(force-stop) / 其他小游戏(圆圈关闭) / 美团首页(点天天现金) /
                # 美团其他页面(返回键)，直到回到 MGCGameActivity 游戏主界面；
                # 之后由后续 ensure_page 重新打开每日任务弹窗。
                step_name = step.get("name", "返回每日任务弹窗")
                self.logger.step("直接", step_name,
                                 "返回每日任务弹窗：先确保回到游戏主界面")
                self._return_to_game_main(step)
                time.sleep(wait_after)
                screenshot_after = self._take_screenshot()
                self.logger.save_screenshot(screenshot_after, f"after_{step_name}")
                return True

            elif action_type == "close_mgc_overlay":
                # 关闭美团“其他小游戏”内的同 Activity 浮层圆圈按钮
                # 关键判别：当前是否在【天天现金主游戏】内？
                #   - 天天现金主游戏 Activity = meituan_game_activity（MGCGameActivity，无后缀）
                #     此时圆圈按钮是“关闭整个天天现金游戏”的按钮，绝不能点 → 直接跳过
                #   - 美团其他小游戏 Activity = MGCGameActivity1 / MGCGameActivity2（带后缀）
                #     此时返回键关不掉，需要点圆圈按钮关闭浮层、回到天天现金 → 检测并点击
                #   - 第三方 App（已不在美团）→ return_to_game_main 已处理，这里跳过
                meituan_pkg = step.get(
                    "package",
                    self.config.get("meituan_package", "com.sankuai.meituan"))
                main_activity = self.config.get(
                    "meituan_game_activity",
                    "com.meituan.android.mgc.container.MGCGameActivity")

                cur_pkg, cur_act = self.adb.get_current_activity()
                if cur_pkg == meituan_pkg and cur_act == main_activity:
                    self.logger.step(
                        "直接", step_name,
                        "当前已在天天现金主游戏内(MGCGameActivity)，圆圈按钮会关闭游戏，跳过")
                    return True
                if cur_pkg != meituan_pkg:
                    self.logger.step(
                        "直接", step_name,
                        f"当前不在美团App内({cur_pkg})，无需关闭浮层，跳过")
                    return True

                # 在美团其他小游戏（MGCGameActivity1/...）内：检测并点击圆圈关闭浮层
                self._do_close_mgc_overlay(step, wait_after, step_name)
                screenshot_after = self._take_screenshot()
                self.logger.save_screenshot(screenshot_after, f"after_{step_name}")
                return True

            elif action_type == "wait":
                duration = step.get("duration", wait_after)
                self.logger.step("直接", step_name, f"等待 {duration} 秒")
                time.sleep(duration)
                return True

            elif action_type == "browse":
                # 浏览任务：在 duration 秒内持续上下滑动，让页面判定浏览有效
                # （仅等待不滑动，屏幕内容不动，任务不会被记为完成）
                duration = float(step.get("duration", 12))
                self.logger.step("直接", step_name, f"浏览中持续上下滑动 {duration} 秒")
                start = time.time()
                toggle = True
                while time.time() - start < duration:
                    if toggle:
                        self.adb.swipe(360, 1000, 360, 400, 300)
                    else:
                        self.adb.swipe(360, 400, 360, 1000, 300)
                    toggle = not toggle
                    time.sleep(0.8)
                time.sleep(wait_after)
                screenshot_after = self._take_screenshot()
                self.logger.save_screenshot(screenshot_after, f"after_{step_name}")
                return True

            elif action_type == "home":
                self.adb.press_home()
                self.logger.step("直接", step_name, "按下 HOME 键")
                time.sleep(wait_after)
                screenshot_after = self._take_screenshot()
                self.logger.save_screenshot(screenshot_after, f"after_{step_name}")
                return True

            elif action_type == "swipe":
                # 直接滑动（无需先查找目标）
                coords = step.get("swipe_coords")
                if coords:
                    self.adb.swipe(*coords)
                    self.logger.step("直接", step_name, f"swipe {coords}")
                time.sleep(wait_after)
                screenshot_after = self._take_screenshot()
                self.logger.save_screenshot(screenshot_after, f"after_{step_name}")
                return True

            elif action_type == "scroll_find":
                # 滚动查找：在可滚动区域内查找目标，找不到就上滑一页继续
                return self._do_scroll_find(step, wait_after, step_name)

            elif action_type == "ensure_page":
                # 确保当前在目标页面，如果不在则通过返回+重入导航
                target_page = step.get("target_page")
                max_back = step.get("max_back_attempts", 3)
                entry_find = step.get("entry_find")
                entry_wait = step.get("entry_wait", 2)
                ok = self._ensure_page(target_page, max_back, entry_find, entry_wait)
                # 改进点2/3：若反复按返回仍到不了目标（如误回 MainActivity / 卡第三方App），
                # 先执行 return_to_game_main 统一恢复回 MGCGameActivity，再重试一次导航。
                if not ok and step.get("recovery") == "return_to_game_main":
                    self.logger.info(f"ensure_page: 导航失败，执行 return_to_game_main 兜底恢复")
                    self._return_to_game_main(step)
                    ok = self._ensure_page(target_page, max_back, entry_find, entry_wait)
                return ok

            elif action_type == "return_to_game_main":
                # 改进点3：统一“返回游戏主界面”恢复（详见 _return_to_game_main）
                step_name = step.get("name", "返回游戏主界面")
                self.logger.step("直接", step_name,
                                 "确保回到天天现金游戏主界面(MGCGameActivity)")
                ok = self._return_to_game_main(step)
                time.sleep(wait_after)
                screenshot_after = self._take_screenshot()
                self.logger.save_screenshot(screenshot_after, f"after_{step_name}")
                return ok

            elif action_type == "if_found":
                # 条件分支：如果找到目标，执行 then_steps 子步骤
                find_spec = step.get("find")
                then_steps = step.get("then_steps", [])
                if not find_spec or not then_steps:
                    return True
                # use_last_screenshot: 复用上一张截图（通常是前一步 tap 后的截图），
                # 用于捕捉“点击后立即弹出、又很快消失”的 toast（如“放置区精灵已满”）。
                # 若复用截图未命中，再新截一张兜底（toast 可能稍晚出现），避免漏检。
                use_last = step.get("use_last_screenshot", False)
                if use_last and self.screenshot_cache:
                    screenshot_path = self.screenshot_cache
                    self.logger.save_screenshot(screenshot_path, f"if_found_{step_name}_reuse")
                else:
                    screenshot_path = self._take_screenshot()
                    self.logger.save_screenshot(screenshot_path, f"if_found_{step_name}")
                result = self._execute_find_action(find_spec, "check", step, screenshot_path)
                if (not result or not result.found) and use_last and self.screenshot_cache:
                    # 复用截图未命中：toast 可能稍晚出现，新截一张兜底
                    time.sleep(step.get("fresh_retry_wait", 1.0))
                    screenshot_path = self._take_screenshot()
                    self.logger.save_screenshot(screenshot_path, f"if_found_{step_name}_retry")
                    result = self._execute_find_action(find_spec, "check", step, screenshot_path)
                if result and result.found:
                    self.logger.step("直接", step_name, "条件满足，执行 then_steps")
                    for t_step in then_steps:
                        t_desc = t_step.get("name", "未命名")
                        self.logger.info(f"  if_found 子步骤: {t_desc}")
                        success = self._process_step(t_step)
                        if not success:
                            self.logger.info(f"  if_found 子步骤 {t_desc} 失败")
                            return False
                    return True
                else:
                    self.logger.step("直接", step_name, "条件未满足，执行 else_steps")
                    else_steps = step.get("else_steps", [])
                    for e_step in else_steps:
                        e_desc = e_step.get("name", "未命名")
                        self.logger.info(f"  if_found else 子步骤: {e_desc}")
                        success = self._process_step(e_step)
                        if not success:
                            self.logger.info(f"  if_found else 子步骤 {e_desc} 失败")
                            return False
                    return True

            elif action_type == "wait_until_found":
                # 循环等待目标出现，找到后执行 then_steps
                # 用于处理广告倒计时：等待 "点击立得丰富奖励" 文字出现后再点击
                find_spec = step.get("find")
                then_steps = step.get("then_steps", [])
                interval = float(step.get("interval", 1.0))
                timeout = float(step.get("timeout", 15.0))
                timeout_action = step.get("timeout_action", "fail")  # fail / skip

                if not find_spec:
                    return True

                start = time.time()
                found = False
                result = None
                while time.time() - start < timeout:
                    screenshot_path = self._take_screenshot()
                    self.logger.save_screenshot(screenshot_path, f"wait_until_found_{step_name}")
                    result = self._execute_find_action(find_spec, "check", step, screenshot_path)
                    if result and result.found:
                        found = True
                        self.logger.step("直接", step_name,
                                         f"找到目标 @ ({result.x}, {result.y}) 置信度 {result.confidence:.3f} [{result.detail}]")
                        break
                    remaining = max(0, timeout - (time.time() - start))
                    self.logger.info(f"wait_until_found: 未找到目标，{interval}秒后重试 (剩余 {remaining:.1f}s)")
                    time.sleep(interval)

                if not found:
                    msg = f"wait_until_found: 超时 ({timeout}秒) 未找到目标"
                    self.logger.step("直接", step_name, msg)
                    if timeout_action == "skip":
                        return True
                    return False

                # 执行 then_steps
                for t_step in then_steps:
                    t_desc = t_step.get("name", "未命名")
                    self.logger.info(f"  wait_until_found 子步骤: {t_desc}")
                    success = self._process_step(t_step)
                    if not success:
                        self.logger.info(f"  wait_until_found 子步骤 {t_desc} 失败")
                        return False
                return True

            elif action_type == "run_subtask":
                # 执行另一个子任务文件
                sub_task_file = step.get("task")
                if not sub_task_file:
                    self.logger.info("run_subtask 缺少 task 参数")
                    return False
                tasks_dir = step.get("tasks_dir")
                if tasks_dir is None:
                    # 尝试从运行上下文推断
                    tasks_dir = getattr(self, "_current_tasks_dir", None)
                if tasks_dir is None:
                    self.logger.info("run_subtask 缺少 tasks_dir")
                    return False
                sub_task_path = os.path.join(tasks_dir, sub_task_file)
                if not os.path.exists(sub_task_path):
                    self.logger.info(f"子任务文件不存在: {sub_task_path}")
                    return False
                sub_task = self.load_task(sub_task_path)
                self.logger.info(f"run_subtask: 加载子任务 {sub_task.name}")
                success = self.run_task(sub_task, tasks_dir)
                self.logger.info(f"run_subtask: {sub_task.name} 执行{'成功' if success else '失败'}")
                return success

            elif action_type == "check":
                # 只查找不操作：截图 → 查找目标 → 返回是否找到
                # 用于检测 toast、弹窗等信号文字
                find_spec = step.get("find")
                if find_spec:
                    screenshot_path = self._take_screenshot()
                    self.logger.save_screenshot(screenshot_path, f"check_{step_name}")
                    result = self._execute_find_action(find_spec, "check", step, screenshot_path)
                    if result is None or not result.found:
                        self.logger.step("直接", step_name, "检测未找到目标")
                        return False
                    self.logger.step("直接", step_name,
                                     f"检测到目标 @ ({result.x}, {result.y}) 置信度 {result.confidence:.3f} [{result.detail}]")
                    return True
                return False

            else:
                # tap / swipe 等需要 find 的动作
                find_spec = step.get("find")
                if find_spec:
                    screenshot_path = self._take_screenshot()
                    self.logger.save_screenshot(screenshot_path, f"step_{step_name}")

                    result = self._execute_find_action(find_spec, action_type, step, screenshot_path)
                    if result is None or not result.found:
                        if skip_if_not_found:
                            self.logger.step("直接", step_name, "未找到目标，跳过")
                            return True
                        self.logger.step("直接", step_name, f"未找到目标")
                        return False

                    self.logger.step("直接", step_name,
                                     f"找到目标 @ ({result.x}, {result.y}) 置信度 {result.confidence:.3f} [{result.detail}]")

                    # 执行动作
                    if action_type == "tap":
                        # 支持点击偏移（如点击文字上方的图标）
                        offset_x = step.get("offset_x", 0)
                        offset_y = step.get("offset_y", 0)
                        tap_x = result.x + offset_x
                        tap_y = result.y + offset_y
                        self.adb.tap(tap_x, tap_y)
                        self.logger.info(f"tap ({tap_x}, {tap_y}) [偏移: ({offset_x}, {offset_y})]")
                    elif action_type == "swipe":
                        coords = step.get("swipe_coords")
                        if coords:
                            self.adb.swipe(*coords)

                    time.sleep(wait_after)

                    # 存截图验证
                    screenshot_after = self._take_screenshot()
                    self.logger.save_screenshot(screenshot_after, f"after_{step_name}")

                return True

    def _run_sub_tasks(self, task: TaskConfig, tasks_dir: str) -> bool:
        """执行子任务串联（workflow模式）：依次加载并执行每个子任务"""
        completed_tasks = 0
        for i, sub_task_file in enumerate(task.sub_tasks):
            self.logger.info(f"===== 子任务 {i+1}/{len(task.sub_tasks)}: {sub_task_file} =====")

            sub_task_path = os.path.join(tasks_dir, sub_task_file)
            if not os.path.exists(sub_task_path):
                self.logger.info(f"子任务文件不存在: {sub_task_path}, 跳过")
                continue

            sub_task = self.load_task(sub_task_path)
            self.logger.info(f"加载子任务: {sub_task.name}")

            # 执行子任务（递归调用 run_task）
            success = self.run_task(sub_task, tasks_dir)

            if success:
                completed_tasks += 1
                self.logger.info(f"子任务 {sub_task.name} 执行成功")
            else:
                self.logger.info(f"子任务 {sub_task.name} 执行失败")
                # 子任务失败时，根据配置决定是否继续
                # 默认继续执行后续子任务（非关键任务失败不应阻断整个流程）
                continue

        self.logger.info(f"子任务串联完成: {completed_tasks}/{len(task.sub_tasks)} 个成功")
        self.logger.end_session(completed_tasks > 0,
                                f"完成 {completed_tasks}/{len(task.sub_tasks)} 个子任务")
        return completed_tasks > 0

    def _ensure_page(self, target_page: str, max_back: int = 3,
                      entry_find: dict = None, entry_wait: float = 2) -> bool:
        """确保当前在目标页面，如果不在则导航到目标页面

        策略（优先尝试直接重入，避免不必要的返回键）：
        1. 截图识别当前页面，如果已在目标页面则直接返回
        2. 尝试通过 entry_find 入口按钮直接进入目标页面（避免按返回键关闭app）
        3. 如果 entry_find 未找到入口按钮（可能被弹窗遮挡），按返回键清除遮挡后重试
        4. 每次按返回键后都检查是否到达目标页面，并尝试 entry_find
        """
        # 1. 检查当前是否已在目标页面
        screenshot_path = self._take_screenshot()
        self.logger.save_screenshot(screenshot_path, "ensure_page_check")
        current = self.page_manager.identify_current_page(self.finder, screenshot_path)

        if current == target_page:
            self.logger.info(f"ensure_page: 已在目标页面 {target_page}")
            return True

        self.logger.info(f"ensure_page: 当前页面={current}, 目标={target_page}")

        # 2. 优先尝试 entry_find 直接重入（不按返回键）
        if entry_find:
            self.logger.info(f"ensure_page: 尝试直接通过入口按钮进入 {target_page}")
            result = self._execute_find_action(entry_find, "tap", {}, screenshot_path)
            if result and result.found:
                self.logger.info(f"ensure_page: 找到入口按钮 @ ({result.x}, {result.y})，直接进入")
                self.adb.tap(result.x, result.y)
                time.sleep(entry_wait)

                screenshot_path = self._take_screenshot()
                self.logger.save_screenshot(screenshot_path, "ensure_page_direct_entry")
                current = self.page_manager.identify_current_page(self.finder, screenshot_path)

                if current == target_page:
                    self.logger.info(f"ensure_page: 直接进入成功，到达目标页面 {target_page}")
                    return True

                self.logger.info(f"ensure_page: 直接进入后当前页面={current}, 继续尝试返回键")
            else:
                self.logger.info(f"ensure_page: 未找到入口按钮（可能被遮挡），尝试返回键清除遮挡")

        # 3. 按返回键清除遮挡，每次返回后检查目标页面并尝试 entry_find
        for i in range(max_back):
            self.logger.info(f"ensure_page: 按返回键 (第{i+1}/{max_back}次)")
            self.adb.press_back()
            time.sleep(2)

            screenshot_path = self._take_screenshot()
            self.logger.save_screenshot(screenshot_path, f"ensure_page_back_{i}")
            current = self.page_manager.identify_current_page(self.finder, screenshot_path)

            if current == target_page:
                self.logger.info(f"ensure_page: 返回键后到达目标页面 {target_page}")
                return True

            # 返回后尝试 entry_find
            if entry_find:
                self.logger.info(f"ensure_page: 返回后尝试入口按钮")
                result = self._execute_find_action(entry_find, "tap", {}, screenshot_path)
                if result and result.found:
                    self.logger.info(f"ensure_page: 返回后找到入口按钮 @ ({result.x}, {result.y})")
                    self.adb.tap(result.x, result.y)
                    time.sleep(entry_wait)

                    screenshot_path = self._take_screenshot()
                    self.logger.save_screenshot(screenshot_path, f"ensure_page_back_entry_{i}")
                    current = self.page_manager.identify_current_page(self.finder, screenshot_path)

                    if current == target_page:
                        self.logger.info(f"ensure_page: 返回+入口后到达目标页面 {target_page}")
                        return True

                    self.logger.info(f"ensure_page: 返回+入口后当前页面={current}")

            self.logger.info(f"ensure_page: 返回键后当前页面={current}")

        self.logger.info(f"ensure_page: 无法到达目标页面 {target_page}")
        return False

    # ------------------------------------------------------------------
    # Activity 分类与“返回游戏主界面”统一恢复（两级判定 + 改进点3）
    # ------------------------------------------------------------------
    def _classify_activity(self, pkg: str, act_base: str) -> str:
        """把当前 (pkg, act_base) 分类为恢复策略所用的类别。

        - third_party    第三方 App（非美团）
        - cash_daily_game 天天现金主游戏（MGCGameActivity，无后缀）
        - other_mini_game 美团其他小游戏（MGCGameActivity1/2... 带后缀）
        - meituan_home   美团首页/主页（Activity 含 MainActivity/Launcher/Home 关键字）
        - meituan_other  美团其他页面（如 MSVPageActivity 等 H5/中转页）
        """
        meituan = self.config.get("meituan_package", "com.sankuai.meituan")
        # meituan_game_activity 为完整类名，取最后一个 “.” 后的 basename 做比较
        game = self.config.get(
            "meituan_game_activity",
            "com.meituan.android.mgc.container.MGCGameActivity").split(".")[-1]
        if pkg and pkg != meituan:
            return "third_party"
        if act_base == game:
            return "cash_daily_game"
        if act_base.startswith("MGCGameActivity"):
            return "other_mini_game"
        keywords = self.config.get(
            "meituan_home_activity_keywords",
            ["MainActivity", "LauncherActivity", "HomeActivity"])
        if any(k in act_base for k in keywords):
            return "meituan_home"
        return "meituan_other"

    def _return_to_game_main(self, step: dict, max_attempts: int = None) -> bool:
        """统一恢复：确保当前处于天天现金游戏主界面(MGCGameActivity)。

        按 Activity 分类循环处理（改进点3）：
          - third_party     第三方App      → force-stop 关闭
          - other_mini_game 美团其他小游戏 → 点圆圈按钮关闭浮层
          - meituan_home    美团首页        → 点击“天天现金”图标（OCR失败则 am start 置顶游戏页）
          - meituan_other   美团其他页面    → 按返回键
          - cash_daily_game 天天现金游戏    → 成功，结束
        兜底：循环未恢复时，am start 直接把游戏 Activity 置顶/重启。
        """
        meituan_pkg = self.config.get("meituan_package", "com.sankuai.meituan")
        game_activity = self.config.get(
            "meituan_game_activity",
            "com.meituan.android.mgc.container.MGCGameActivity")
        home_find = step.get("home_entry_find") or {"type": "ocr", "text": "天天现金"}
        max_att = max_attempts or step.get("max_attempts", 15)

        for attempt in range(max_att):
            pkg, act = self.adb.get_current_activity()
            act_base = act.split(".")[-1] if act else ""
            cat = self._classify_activity(pkg, act_base)
            self.logger.info(
                f"return_to_game_main: 尝试{attempt+1}/{max_att} 当前({pkg}/{act_base}) → {cat}")

            if cat == "cash_daily_game":
                self.logger.info("return_to_game_main: 已在天天现金游戏主界面(MGCGameActivity)")
                return True
            elif cat == "third_party":
                self.logger.info(f"return_to_game_main: 第三方App({pkg})，force-stop 关闭")
                self.adb.force_stop(pkg)
                time.sleep(1.5)
            elif cat == "other_mini_game":
                self.logger.info("return_to_game_main: 美团其他小游戏浮层，点击圆圈关闭")
                self._do_close_mgc_overlay(step, 1.5)
            elif cat == "meituan_home":
                self.logger.info("return_to_game_main: 美团首页，点击'天天现金'进入游戏")
                tapped = self._tap_find(home_find, offset_y=-80, wait_after=3)
                if not tapped:
                    self.logger.info("return_to_game_main: 未找到'天天现金'，am start 置顶游戏页")
                    self.adb.bring_to_front(meituan_pkg, game_activity)
                    time.sleep(2)
            else:  # meituan_other
                self.logger.info(f"return_to_game_main: 美团其他页面({act_base})，按返回键")
                self.adb.press_back()
                time.sleep(1.5)

        # 兜底：am start 直接把游戏 Activity 置顶/重启
        self.logger.info("return_to_game_main: 循环未恢复，尝试 am start 重新进入游戏")
        self.adb.bring_to_front(meituan_pkg, game_activity)
        time.sleep(2)
        pkg, act = self.adb.get_current_activity()
        act_base = act.split(".")[-1] if act else ""
        ok = self._classify_activity(pkg, act_base) == "cash_daily_game"
        if not ok:
            self.logger.info(f"return_to_game_main: 兜底仍失败，当前({pkg}/{act_base})")
        return ok

    def _do_scroll_find(self, step: dict, wait_after: float, step_name: str) -> bool:
        """滚动查找：在可滚动区域内查找目标，若当前屏未找到则上滑一页继续。

        参数：
          - find: 查找规则（ocr/ocr_relative/template/color/fixed）
          - anchor_text + target_text: 简写 ocr_relative，在 anchor 附近找 target
          - stop_scroll_if_found: 停止滑动的检测规则。当前屏主规则未命中时，若检测到
            此规则命中，则立即停止滑动并返回 False（不点击）。
            用途：查找"去领取"时，若当前屏有"去完成"说明"去领取"已全部领完，
            无需继续滑动，直接跳出让后续步骤处理"去完成"任务。
          - max_swipes: 最大滑动次数（默认 10）
          - swipe_coords: [x1, y1, x2, y2, duration] 滑动参数（默认向上滑一页 [360,1400,360,700,300]）
          - action_on_found: 找到后的动作，"tap"（默认）或 "check"
          - offset_x / offset_y: tap 时的点击偏移
          - swipe_wait: 每次滑动后的等待时间（默认 1.0 秒）

        用于每日任务弹窗滚动区查找"去领取"/"去完成"：若当前屏没有，上滑一页继续找。
        """
        find_spec = step.get("find")
        anchor_text = step.get("anchor_text")
        target_text = step.get("target_text")

        # 简写：直接提供 anchor_text + target_text，自动构造 ocr_relative
        if not find_spec and anchor_text and target_text:
            find_spec = {
                "type": "ocr_relative",
                "anchor_text": anchor_text,
                "target_text": target_text,
                "anchor_roi": step.get("anchor_roi", [25, 680, 670, 870]),
                "y_range": step.get("y_range", 80),
                "x_range": step.get("x_range", [300, 720]),
                "threshold": step.get("threshold", 0.5),
                "exact_match": step.get("exact_match", True),
            }
            # 可选：要求 anchor 同一行还必须存在指定文本（用于区分 OCR 拆分的同名任务）
            anchor_same_line = step.get("anchor_same_line")
            if anchor_same_line:
                find_spec["anchor_same_line"] = anchor_same_line

        if not find_spec:
            self.logger.info(f"scroll_find: 缺少 find 规则或 anchor_text/target_text")
            return False

        # 停止滑动的检测规则：主规则未命中时，若此规则命中则提前终止滑动
        stop_scroll_spec = step.get("stop_scroll_if_found")

        max_swipes = int(step.get("max_swipes", 10))
        swipe_coords = step.get("swipe_coords", [360, 1400, 360, 700, 300])
        action_on_found = step.get("action_on_found", "tap")
        offset_x = int(step.get("offset_x", 0))
        offset_y = int(step.get("offset_y", 0))
        swipe_wait = float(step.get("swipe_wait", 1.0))

        # reset_scroll: 开始查找前先将列表滑回顶部，避免上一轮滑到底部后下一轮找不到上方内容
        reset_scroll = step.get("reset_scroll")
        if reset_scroll:
            reset_swipes = int(reset_scroll.get("swipes", 5))
            reset_coords = reset_scroll.get("swipe_coords", [360, 700, 360, 1400, 300])  # 默认向下滑（回顶部）
            reset_wait = float(reset_scroll.get("swipe_wait", swipe_wait))
            self.logger.info(f"scroll_find: 滑回顶部（{reset_swipes} 次）")
            for _ in range(reset_swipes):
                self.adb.swipe(*reset_coords)
                time.sleep(reset_wait)

        for i in range(max_swipes + 1):
            screenshot_path = self._take_screenshot()
            self.logger.save_screenshot(screenshot_path, f"scroll_find_{step_name}_{i}")

            result = self._execute_find_action(find_spec, action_on_found, step, screenshot_path)
            if result and result.found:
                self.logger.step(
                    "直接", step_name,
                    f"第{i+1}屏找到目标 @ ({result.x}, {result.y}) 置信度 {result.confidence:.3f} [{result.detail}]")

                if action_on_found == "tap":
                    tap_x = result.x + offset_x
                    tap_y = result.y + offset_y
                    self.adb.tap(tap_x, tap_y)
                    self.logger.info(f"tap ({tap_x}, {tap_y}) [偏移: ({offset_x}, {offset_y})]")
                    time.sleep(wait_after)
                    screenshot_after = self._take_screenshot()
                    self.logger.save_screenshot(screenshot_after, f"after_{step_name}")
                return True

            # 主规则未命中：检查是否应提前停止滑动
            if stop_scroll_spec:
                stop_result = self._execute_find_action(stop_scroll_spec, "check", step, screenshot_path)
                if stop_result and stop_result.found:
                    self.logger.step(
                        "直接", step_name,
                        f"第{i+1}屏检测到停止信号 [{stop_result.detail}]，停止滑动")
                    return False

            if i < max_swipes:
                self.logger.info(f"scroll_find: 第{i+1}屏未找到，上滑一页")
                self.adb.swipe(*swipe_coords)
                time.sleep(swipe_wait)

        self.logger.step("直接", step_name, f"滑动 {max_swipes} 次后仍未找到目标")
        return False

    def _do_close_mgc_overlay(self, step: dict, wait_after: float = 1.5, step_name: str = "关闭浮层"):
        """检测并点击美团其他小游戏内的同 Activity 浮层圆圈按钮。"""
        find_spec = step.get("find", {}) or {}
        roi = tuple(find_spec["roi"]) if find_spec.get("roi") else None
        screenshot_path = self._take_screenshot()
        self.logger.save_screenshot(screenshot_path, f"if_found_{step_name}")
        res = self.finder.find_template(
            screenshot_path,
            template_name=find_spec.get("template", "close_btn_mgc_overlay.png"),
            roi=roi,
            threshold=find_spec.get("threshold", 0.8),
            process=find_spec.get("process", "raw"),
        )
        if res and res.found:
            coords = step.get("close_coords", [655, 72])
            self.adb.tap(int(coords[0]), int(coords[1]))
            self.logger.step(
                "直接", step_name,
                f"检测到美团小游戏浮层圆圈按钮，点击固定坐标 {coords} 关闭浮层")
        else:
            self.logger.step("直接", step_name, "未检测到浮层圆圈按钮，跳过")
        time.sleep(wait_after)

    def _tap_find(self, find_spec: dict, offset_y: int = 0, wait_after: float = 1.5) -> bool:
        """截图→查找→点击（带偏移），用于点击“天天现金”等入口。"""
        if not find_spec:
            return False
        screenshot_path = self._take_screenshot()
        self.logger.save_screenshot(screenshot_path, "tap_find")
        result = self._execute_find_action(find_spec, "tap", {}, screenshot_path)
        if result and result.found:
            self.adb.tap(result.x, result.y + offset_y)
            self.logger.info(f"tap_find: 点击 @ ({result.x},{result.y+offset_y})")
            time.sleep(wait_after)
            return True
        self.logger.info(f"tap_find: 未找到目标 {find_spec}")
        return False

    def _take_screenshot(self) -> str:
        """截图"""
        path = self.adb.screenshot()
        self.screenshot_cache = path
        self.logger.info(f"截图: {path}")
        return path

    def _wait_for_page(self, page_name: str) -> bool:
        """等待目标页面出现"""
        retry = self.default_retry
        timeout = self.default_timeout

        for attempt in range(retry):
            self.logger.info(f"等待页面 {page_name} (尝试 {attempt+1}/{retry})")
            screenshot_path = self._take_screenshot()
            self.logger.save_screenshot(screenshot_path, f"wait_{page_name}")

            current = self.page_manager.identify_current_page(self.finder, screenshot_path)
            if current == page_name:
                self.logger.info(f"已识别页面: {page_name}")
                return True

            if current:
                self.logger.info(f"当前在页面: {current} (期望: {page_name})")
            else:
                self.logger.info(f"无法识别当前页面 (期望: {page_name})")

            time.sleep(timeout / retry)

        return False

    def _execute_actions(self, page_config) -> bool:
        """执行页面上的所有动作"""
        for action_def in page_config.actions:
            name = action_def.get("name", "未命名")
            action_type = action_def.get("action", "tap")
            wait_after = action_def.get("wait_after", self.default_wait)
            wait_before = action_def.get("wait_before", 0)
            expect_page = action_def.get("expect_page")

            # wait_before: 执行前先等待
            if wait_before > 0:
                self.logger.info(f"[等待] {wait_before} 秒 ({name})")
                time.sleep(wait_before)

            if action_type == "back":
                self.adb.press_back()
                self.logger.step(page_config.name, name, "按下返回键 KEYCODE_BACK")
                time.sleep(wait_after)
                screenshot_after = self._take_screenshot()
                self.logger.save_screenshot(screenshot_after, f"after_{name}")

            elif action_type == "wait":
                duration = action_def.get("duration", wait_after)
                self.logger.step(page_config.name, name, f"等待 {duration} 秒")

            elif action_type == "home":
                self.adb.press_home()
                self.logger.step(page_config.name, name, "按下 HOME 键")
                time.sleep(wait_after)
                screenshot_after = self._take_screenshot()
                self.logger.save_screenshot(screenshot_after, f"after_{name}")

            else:
                # tap / swipe / loop_click 等需要 find 的动作
                find_spec = action_def.get("find")

                # 先截图再查找
                screenshot_path = self._take_screenshot()

                result = self._execute_find_action(find_spec, action_type, action_def, screenshot_path)
                if result is None or not result.found:
                    skip_if_not_found = action_def.get("skip_if_not_found", False)
                    if skip_if_not_found:
                        self.logger.step(page_config.name, name, "未找到目标，跳过")
                        continue
                    self.logger.step(page_config.name, name, "未找到目标")
                    return False

                self.logger.step(page_config.name, name,
                                 f"找到目标 @ ({result.x}, {result.y}) 置信度 {result.confidence:.3f} [{result.detail}]")

                # 执行动作
                if action_type == "tap":
                    self.adb.tap(result.x, result.y)
                    self.logger.info(f"tap ({result.x}, {result.y})")
                elif action_type == "loop_click":
                    # 循环点击：每次点击后重新截图查找，直到找不到目标
                    max_iter = action_def.get("max_iterations", 50)
                    not_found_retry = action_def.get("not_found_retry", 2)    # 找不到时重试次数
                    not_found_wait = action_def.get("not_found_wait", 3)      # 重试前等待秒数
                    iteration = 0

                    while iteration < max_iter:
                        if result is None or not result.found:
                            # 重试机制：按钮可能被动画/弹窗遮挡，等一会再试
                            retries = 0
                            while retries < not_found_retry:
                                self.logger.info(f"loop_click 未找到目标，重试 {retries+1}/{not_found_retry}，等待 {not_found_wait}秒")
                                time.sleep(not_found_wait)
                                screenshot_path = self._take_screenshot()
                                self.logger.save_screenshot(screenshot_path, f"loop_retry_{name}_{iteration}")
                                result = self._execute_find_action(find_spec, "tap", action_def, screenshot_path)
                                if result and result.found:
                                    break
                                retries += 1
                            if result is None or not result.found:
                                self.logger.step(page_config.name, name,
                                                 f"loop_click 结束，共点击 {iteration} 次（重试后仍未找到）")
                                break

                        iteration += 1
                        self.adb.tap(result.x, result.y)
                        self.logger.info(f"loop_click 第 {iteration} 次 tap ({result.x}, {result.y})")
                        time.sleep(wait_after)

                        # 重新截图并查找下一个
                        screenshot_path = self._take_screenshot()
                        self.logger.save_screenshot(screenshot_path, f"loop_{name}_{iteration}")
                        result = self._execute_find_action(find_spec, "tap", action_def, screenshot_path)

                    self.logger.step(page_config.name, name, f"loop_click 结束，共点击 {iteration} 次")
                    # 跳过普通 tap 后续的等待和截图，循环内部已处理
                    continue
                elif action_type == "swipe":
                    coords = action_def.get("swipe_coords")
                    if coords:
                        self.adb.swipe(*coords)

                # 等待
                time.sleep(wait_after)

                # 存截图
                screenshot_after = self._take_screenshot()
                self.logger.save_screenshot(screenshot_after, f"after_{name}")

            # 检查是否到达期望页面
            if expect_page:
                if screenshot_after is None:
                    screenshot_after = self._take_screenshot()
                current = self.page_manager.identify_current_page(self.finder, screenshot_after)
                if current != expect_page:
                    self.logger.info(f"期望页面 {expect_page}, 实际 {current}")

        return True

    def _execute_find_action(self, find_spec: dict, action_type: str,
                              action_def: dict = None,
                              screenshot_path: str = None) -> object:
        """执行 find 规则并返回结果"""
        if not screenshot_path:
            screenshot_path = self._take_screenshot()

        type_ = find_spec.get("type", "template")

        if type_ == "template":
            return self.finder.find_template(
                screenshot_path,
                template_name=find_spec["template"],
                roi=tuple(find_spec.get("roi")) if find_spec.get("roi") else None,
                threshold=find_spec.get("threshold"),
                process=find_spec.get("process", "raw"),
            )
        elif type_ == "ocr":
            return self.finder.find_ocr(
                screenshot_path,
                target_text=find_spec["text"],
                roi=tuple(find_spec.get("roi")) if find_spec.get("roi") else None,
                threshold=find_spec.get("threshold", self.finder.threshold),
                exact_match=find_spec.get("exact_match", False),
            )
        elif type_ == "ocr_relative":
            return self.finder.find_ocr_relative(
                screenshot_path,
                anchor_text=find_spec["anchor_text"],
                target_text=find_spec["target_text"],
                anchor_roi=tuple(find_spec.get("anchor_roi")) if find_spec.get("anchor_roi") else None,
                y_range=find_spec.get("y_range", 60),
                x_range=tuple(find_spec.get("x_range", [0, 720])),
                threshold=find_spec.get("threshold", self.finder.threshold),
                anchor_threshold=find_spec.get("anchor_threshold"),
                exact_match=find_spec.get("exact_match", False),
                anchor_same_line=find_spec.get("anchor_same_line"),
            )
        elif type_ == "color":
            return self.finder.find_color(
                screenshot_path,
                target_color=tuple(find_spec["color"]),
                roi=tuple(find_spec.get("roi")) if find_spec.get("roi") else None,
                tolerance=find_spec.get("tolerance", 30),
                min_ratio=find_spec.get("min_ratio", 0.01),
            )
        elif type_ == "fixed":
            # 固定坐标：返回指定的屏幕坐标（用于位置固定的 UI 元素，
            # 如美团游戏内同 Activity 浮层的关闭圆圈按钮）。始终 found=True。
            coords = find_spec.get("coords")
            if coords and len(coords) == 2:
                x, y = int(coords[0]), int(coords[1])
                return FinderResult(x, y, 1.0, "fixed", f"fixed({x},{y})")
            return None
        return None
