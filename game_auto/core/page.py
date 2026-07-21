"""Page 模块：页面识别和状态机"""
import yaml
import os


class PageConfig:
    """单个页面配置"""
    def __init__(self, data: dict):
        self.name = data["name"]
        self.identify = data.get("identify", [])
        self.actions = data.get("actions", [])

    def __repr__(self):
        return f"PageConfig(name={self.name})"


class PageManager:
    """页面管理器：加载和识别页面"""
    def __init__(self, pages_dir: str):
        self.pages_dir = pages_dir
        self.pages: dict[str, PageConfig] = {}
        self._load_pages()

    def _load_pages(self):
        """加载所有页面配置"""
        if not os.path.exists(self.pages_dir):
            return

        for filename in os.listdir(self.pages_dir):
            if not filename.endswith(".yaml") and not filename.endswith(".yml"):
                continue
            filepath = os.path.join(self.pages_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and "name" in data:
                page = PageConfig(data)
                self.pages[page.name] = page

    def identify_current_page(self, finder, screenshot_path: str, threshold: float = None) -> str | None:
        """
        识别当前在哪个页面

        依次用每个页面的 identify 规则去匹配截图，
        第一个匹配成功的页面即为当前页面。
        """
        for page_name, page in self.pages.items():
            for rule in page.identify:
                result = self._match_rule(finder, rule, screenshot_path, threshold)
                if result and result.found:
                    return page_name
        return None

    def _match_rule(self, finder, rule: dict, screenshot_path: str, threshold: float = None):
        """匹配单个识别规则"""
        type_ = rule.get("type", "template")

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
