"""Page 模块：页面识别和状态机（两级判定：Activity 容器过滤 + 视觉细配）"""
import yaml
import os
from .finder import FinderResult


class PageConfig:
    """单个页面的配置信息，从 YAML 文件加载。

    包含页面名称、识别规则、动作列表以及 Activity 容器约束等信息。
    Activity 约束用于两级判定的第一级过滤，只有当前 Activity 满足约束时，
    才会进入第二级视觉匹配。

    Attributes:
        name: 页面唯一名称。
        description: 页面描述。
        identify: 识别规则列表（模板匹配、OCR、颜色、Activity 等）。
        actions: 该页面上可执行的动作列表。
        package: 包名精确匹配约束。
        activity: Activity 类名（basename）精确匹配约束。
        activity_suffix: Activity 类名（basename）前缀匹配约束。
        activity_not: Activity 类名（basename）排除列表。
        activity_only: 是否为纯 Activity 识别页面（所有 identify 规则均为 activity 类型）。
    """

    def __init__(self, data: dict):
        """初始化页面配置。

        Args:
            data: 从 YAML 文件加载的页面配置字典，必须包含 ``name`` 键。
        """
        self.name = data["name"]
        self.description = data.get("description", "")
        self.identify = data.get("identify", [])
        self.actions = data.get("actions", [])
        # 第一级：页面级 Activity 容器约束（两级判定的前置过滤）
        # 只有当前 Activity 满足约束时，才用 identify 规则做视觉细配；
        # 否则该页面直接跳过，避免跨容器（如美团主页/其他小游戏）误匹配到相同文字。
        self.package = data.get("package")                 # 包名精确匹配
        self.activity = data.get("activity")               # Activity 类名(basename)精确匹配
        self.activity_suffix = data.get("activity_suffix") # Activity 类名(basename)前缀匹配
        self.activity_not = data.get("activity_not", [])   # Activity 类名(basename)排除列表
        # 该页面是否“纯 Activity 识别”（所有 identify 规则都是 activity 类型）。
        # 纯 Activity 页面在第二级（视觉全部失败后）才参与判定，避免遮蔽具体弹窗页。
        self.activity_only = (
            all((r.get("type") == "activity") for r in self.identify)
            if self.identify else False
        )

    def __repr__(self):
        return f"PageConfig(name={self.name})"


class PageManager:
    """页面管理器：加载页面配置并执行两级页面识别。

    两级判定流程：
    1. 第一级（Activity 容器过滤）：根据页面配置的 Activity 约束过滤不匹配的页面。
    2. 第二级（视觉细配）：先对非纯 Activity 页面做视觉匹配（模板/OCR/颜色），
       都未命中时再对纯 Activity 页面做兜底匹配。

    Attributes:
        pages_dir: 页面配置 YAML 文件所在目录。
        get_activity_callback: 获取当前 (包名, Activity全类名) 的回调函数。
        pages: 已加载的页面配置字典，键为页面名称。
    """

    def __init__(self, pages_dir: str, get_activity_callback=None):
        """初始化页面管理器并加载所有页面配置。

        Args:
            pages_dir: 页面配置 YAML 文件所在目录路径。
            get_activity_callback: 可选回调函数，调用后返回 ``(包名, Activity全类名)`` 元组。
                                   通常传入 ``adb.get_current_activity``，避免 PageManager 直接依赖 ADB。
        """
        self.pages_dir = pages_dir
        # 回调：返回当前 (pkg, act) 全类名，用于 Activity 前置过滤与纯 Activity 识别。
        # 由 main.py 传入 adb.get_current_activity，避免 PageManager 直接依赖 ADB。
        self.get_activity_callback = get_activity_callback
        self.pages: dict[str, PageConfig] = {}
        self._load_pages()

    def _load_pages(self):
        """加载所有页面配置"""
        if not os.path.exists(self.pages_dir):
            return

        for filename in sorted(os.listdir(self.pages_dir)):
            if not (filename.endswith(".yaml") or filename.endswith(".yml")):
                continue
            filepath = os.path.join(self.pages_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and "name" in data:
                page = PageConfig(data)
                self.pages[page.name] = page

    def identify_current_page(self, finder, screenshot_path: str, threshold: float = None) -> str | None:
        """
        两级识别当前页面：
        第一级（容器过滤）：页面级 activity 约束不满足 → 跳过该页面的视觉匹配。
        第二级（视觉细配）：先对【非纯Activity页面】做视觉匹配；都没命中时，
        再对【纯Activity页面】做 Activity 匹配（兜底识别游戏主界面等）。
        """
        pkg, act = ("", "")
        if self.get_activity_callback:
            try:
                pkg, act = self.get_activity_callback()
            except Exception:
                pkg, act = ("", "")
        # act 为完整类名（如 com.meituan.android.mgc.container.MGCGameActivity），
        # 用最后一个 “.” 取 basename（MGCGameActivity）做约束/规则匹配
        act_base = act.split(".")[-1] if act else ""

        # 第一级 + 第二级(上)：视觉页面（含 activity 约束过滤）
        for page in self.pages.values():
            if page.activity_only:
                continue
            if not self._pass_activity_constraint(page, pkg, act_base):
                continue
            for rule in page.identify:
                result = self._match_rule(finder, rule, screenshot_path, threshold, pkg, act_base)
                if result and result.found:
                    return page.name

        # 第二级(下)：纯 Activity 页面（兜底，如游戏主界面 cash_daily_game）
        for page in self.pages.values():
            if not page.activity_only:
                continue
            if not self._pass_activity_constraint(page, pkg, act_base):
                continue
            for rule in page.identify:
                result = self._match_rule(finder, rule, screenshot_path, threshold, pkg, act_base)
                if result and result.found:
                    return page.name

        return None

    def _pass_activity_constraint(self, page, pkg, act_base) -> bool:
        """检查页面级 Activity 容器约束是否满足（第一级过滤）。

        依次检查 package、activity、activity_suffix、activity_not 约束，
        任一不满足则返回 False，该页面将被跳过不做视觉匹配。

        Args:
            page: PageConfig 实例。
            pkg: 当前前台应用包名。
            act_base: 当前 Activity 类名的 basename（最后一个 ``.`` 之后的部分）。

        Returns:
            约束全部满足返回 True，否则返回 False。
        """
        if page.package and pkg and pkg != page.package:
            return False
        if page.activity and act_base and act_base != page.activity:
            return False
        if page.activity_suffix and act_base and not act_base.startswith(page.activity_suffix):
            return False
        if page.activity_not and act_base and act_base in page.activity_not:
            return False
        return True

    def _match_rule(self, finder, rule: dict, screenshot_path: str, threshold: float = None,
                    pkg: str = "", act_base: str = ""):
        """匹配单个页面识别规则。

        根据规则类型（template / ocr / color / activity）调用对应的 Finder 方法
        或直接进行 Activity 名称比较。

        Args:
            finder: Finder 实例，用于执行视觉匹配。
            rule: 识别规则字典，包含 ``type`` 及对应参数。
            screenshot_path: 当前截图文件路径。
            threshold: 匹配置信度阈值，为 None 时使用规则自身或 Finder 默认值。
            pkg: 当前前台应用包名。
            act_base: 当前 Activity 类名的 basename。

        Returns:
            匹配成功返回 FinderResult 实例（found 为 True），否则返回 None。
        """
        type_ = rule.get("type", "template")

        if type_ == "activity":
            # 纯 Activity 识别，无需截图
            expected = rule.get("activity")
            suffix = rule.get("activity_suffix")
            not_in = rule.get("activity_not", [])
            if expected and act_base and act_base == expected:
                return FinderResult(0, 0, 1.0, "activity", f"activity={expected}")
            if suffix and act_base and act_base.startswith(suffix) and act_base not in not_in:
                return FinderResult(0, 0, 1.0, "activity", f"activity_suffix={suffix}")
            return None

        if type_ == "template":
            return finder.find_template(
                screenshot_path,
                template_name=rule["template"],
                roi=tuple(rule.get("roi")) if rule.get("roi") else None,
                threshold=threshold or rule.get("threshold"),
                process=rule.get("process", "raw"),
            )
        elif type_ == "ocr":
            return finder.find_ocr(
                screenshot_path,
                target_text=rule["text"],
                roi=tuple(rule.get("roi")) if rule.get("roi") else None,
                threshold=rule.get("threshold", 0.5),
                exact_match=rule.get("exact_match", False),
            )
        elif type_ == "color":
            return finder.find_color(
                screenshot_path,
                target_color=tuple(rule["color"]),
                roi=tuple(rule.get("roi")) if rule.get("roi") else None,
                tolerance=rule.get("tolerance", 30),
                min_ratio=rule.get("min_ratio", 0.01),
            )
        return None
