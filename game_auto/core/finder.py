"""Finder 模块：三种定位策略（找图、OCR、找颜色）"""
import os
from typing import Union, List
import cv2
import numpy as np
from PIL import Image


class FinderResult:
    """查找结果"""
    def __init__(self, x: int, y: int, confidence: float, method: str, detail: str = ""):
        self.x = x
        self.y = y
        self.confidence = confidence
        self.method = method
        self.detail = detail

    def __repr__(self):
        return f"FinderResult(x={self.x}, y={self.y}, conf={self.confidence:.3f}, method={self.method})"

    @property
    def found(self) -> bool:
        return self.confidence > 0


class Finder:
    def __init__(self, templates_dir: str, threshold: float = 0.55, ocr_enabled: bool = False):
        self.templates_dir = templates_dir
        self.threshold = threshold
        self._ocr = None
        self._ocr_enabled = ocr_enabled

    def _template_path(self, name: str) -> str:
        """获取模板完整路径"""
        path = os.path.join(self.templates_dir, name)
        if os.path.exists(path):
            return path
        raise FileNotFoundError(f"模板不存在: {path}")

    def find_template(self, screenshot_path: str, template_name: str,
                      roi: tuple = None, threshold: float = None,
                      scales: list = None, process: str = "raw") -> FinderResult | None:
        """
        找图策略：多尺度模板匹配

        process: "raw" 原图直接匹配 / "transparent" 先透明化再匹配
        roi: (x, y, w, h) 搜索区域限制
        """
        threshold = threshold or self.threshold
        scales = scales or [0.9, 0.95, 1.0, 1.05, 1.1]

        tpl_path = self._template_path(template_name)
        tpl = cv2.imread(tpl_path, cv2.IMREAD_UNCHANGED)
        hay = cv2.imread(screenshot_path, cv2.IMREAD_COLOR)

        if tpl is None:
            raise RuntimeError(f"无法读取模板: {tpl_path}")
        if hay is None:
            raise RuntimeError(f"无法读取截图: {screenshot_path}")

        # 分离 alpha 通道
        if tpl.shape[2] == 4:
            alpha = tpl[:, :, 3].copy()
            tpl_bgr = np.ascontiguousarray(tpl[:, :, :3])  # 确保连续内存布局（floodFill 需要）
        else:
            alpha = np.ones(tpl.shape[:2], dtype=np.uint8) * 255
            tpl_bgr = tpl

        # 如果需要透明化处理
        if process == "transparent":
            tpl_bgr, alpha = self._make_transparent(tpl_bgr, alpha)

        # 裁剪到内容区域
        tpl_bgr, alpha = self._crop_to_content(tpl_bgr, alpha)

        # ROI 限制
        if roi:
            rx, ry, rw, rh = roi
            hay_roi = hay[ry:ry+rh, rx:rx+rw]
        else:
            hay_roi = hay
            rx, ry = 0, 0

        # 多尺度匹配
        mask = (alpha > 50).astype(np.uint8)
        if np.sum(mask) == 0:
            return None

        best_score = -1.0
        best_loc = None
        best_scale = 1.0
        best_w, best_h = tpl_bgr.shape[1], tpl_bgr.shape[0]

        for scale in scales:
            resized = cv2.resize(tpl_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
            resized_mask = cv2.resize(mask, (resized.shape[1], resized.shape[0]), interpolation=cv2.INTER_NEAREST)
            resized_mask = (resized_mask > 0).astype(np.uint8)

            if np.sum(resized_mask) == 0:
                continue

            # 透明区域用均值填充（让匹配不受背景影响）
            mean_color = np.mean(resized[resized_mask > 0], axis=0)
            filled = resized.copy()
            filled[resized_mask == 0] = mean_color

            res = cv2.matchTemplate(hay_roi, filled, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if max_val > best_score:
                best_score = max_val
                best_loc = max_loc
                best_scale = scale
                best_w = resized.shape[1]
                best_h = resized.shape[0]

        if best_score < threshold or best_loc is None:
            return FinderResult(0, 0, 0, "template", f"未达阈值 {threshold} (best={best_score:.3f})")

        # 计算中心坐标（加上 ROI 偏移）
        cx = best_loc[0] + best_w // 2 + rx
        cy = best_loc[1] + best_h // 2 + ry

        return FinderResult(cx, cy, best_score, "template",
                            f"template={template_name} scale={best_scale:.2f} roi={roi}")

    def find_ocr(self, screenshot_path: str, target_text: Union[str, List[str]],
                 roi: tuple = None, threshold: float = 0.5,
                 exact_match: bool = False) -> FinderResult | None:
        """
        找文字策略：OCR 识别文字位置（使用 RapidOCR）

        target_text: 要查找的文字（字符串或字符串列表，列表时命中任意一个即返回）。
        roi: (x, y, w, h) 搜索区域限制
        threshold: 最低置信度阈值
        exact_match: 是否要求文本完全相等（避免 "去捕捉" 误匹配 "浏览去捕捉"）
        """
        if self._ocr is None:
            self._init_ocr()

        img = cv2.imread(screenshot_path)
        if img is None:
            raise RuntimeError(f"无法读取截图: {screenshot_path}")

        if roi:
            rx, ry, rw, rh = roi
            img_roi = img[ry:ry+rh, rx:rx+rw]
        else:
            img_roi = img
            rx, ry = 0, 0

        # RapidOCR 返回: (result_list, elapse_list)
        # result_list 中每项: [box, text, confidence]
        # box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        ocr_result, _ = self._ocr(img_roi)

        if not ocr_result:
            return FinderResult(0, 0, 0, "ocr", f"OCR 无结果")

        # 支持多个候选关键词（任意命中一个即返回）。
        targets = target_text if isinstance(target_text, (list, tuple)) else [target_text]

        best_match = None
        best_conf = 0

        for item in ocr_result:
            box = item[0]    # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            text = item[1]   # 识别的文字
            conf = float(item[2])  # 置信度

            if conf < threshold:
                continue

            for target in targets:
                # 匹配方式：精确 vs 包含
                if exact_match:
                    is_match = (target == text)
                else:
                    is_match = (target in text)

                if is_match:
                    # 计算中心坐标（加上 ROI 偏移）
                    cx = int((box[0][0] + box[2][0]) / 2) + rx
                    cy = int((box[0][1] + box[2][1]) / 2) + ry
                    if conf > best_conf:
                        best_conf = conf
                        matched_target = target
                        best_match = FinderResult(cx, cy, conf, "ocr",
                                                  f"text={text!r} target={matched_target!r} exact={exact_match}")
                    break  # 当前 item 已命中，无需再检查其他 target

        if best_match:
            return best_match

        return FinderResult(0, 0, 0, "ocr",
                            f"未找到 {targets!r} (阈值 {threshold}, 精确={exact_match})")

    def find_ocr_relative(self, screenshot_path: str, anchor_text: str, target_text: str,
                          anchor_roi: tuple = None, y_range: int = 60,
                          x_range: tuple = (0, 720), threshold: float = 0.5,
                          anchor_threshold: float = None,
                          exact_match: bool = False) -> FinderResult:
        """
        相对 OCR 查找：先找到 anchor 文字，再在 anchor 附近区域查找 target。

        用于在每日任务弹窗中，先定位任务名称（如"浏览优惠活动"），
        再找到同一行右侧的"去完成"按钮。

        anchor_roi: 查找 anchor 的 ROI 区域 (x, y, w, h)
        y_range: target 必须在 anchor 垂直方向 ±y_range 范围内
        x_range: target 的 x 坐标范围 (x_min, x_max)
        threshold: target 的最低置信度
        anchor_threshold: anchor 的最低置信度（默认与 threshold 相同）
        exact_match: 对 target 是否使用精确匹配
        """
        if self._ocr is None:
            self._init_ocr()

        # 1. 查找 anchor 文字（使用包含匹配，因为可能带"剩余XX次"等后缀）
        anchor_result = self.find_ocr(
            screenshot_path, anchor_text,
            roi=anchor_roi,
            threshold=anchor_threshold or threshold,
            exact_match=False
        )
        if not anchor_result.found:
            return FinderResult(0, 0, 0, "ocr_relative",
                                f"未找到 anchor '{anchor_text}'")

        anchor_y = anchor_result.y
        anchor_x = anchor_result.x

        # 2. 根据 anchor 位置计算 target 的搜索 ROI
        x_min, x_max = x_range
        y_min = max(0, anchor_y - y_range)
        y_max = min(1600, anchor_y + y_range)  # 一般手机屏幕高度足够
        target_roi = (x_min, y_min, x_max - x_min, y_max - y_min)

        # 3. 在附近区域查找 target
        target_result = self.find_ocr(
            screenshot_path, target_text,
            roi=target_roi,
            threshold=threshold,
            exact_match=exact_match
        )
        if not target_result.found:
            return FinderResult(0, 0, 0, "ocr_relative",
                                f"找到 anchor '{anchor_text}' @({anchor_x},{anchor_y})，"
                                f"但未找到 target '{target_text}'")

        return FinderResult(
            target_result.x, target_result.y, target_result.confidence,
            "ocr_relative",
            f"anchor={anchor_text}@({anchor_x},{anchor_y}) "
            f"target={target_text}@({target_result.x},{target_result.y})"
        )

    def find_color(self, screenshot_path: str, target_color: tuple,
                   roi: tuple = None, tolerance: int = 30,
                   min_ratio: float = 0.01) -> FinderResult:
        """
        找颜色策略：在 ROI 区域查找目标颜色的聚集位置

        target_color: (R, G, B) 目标颜色
        tolerance: 颜色容差
        min_ratio: 最小面积占比
        roi: (x, y, w, h) 搜索区域限制
        """
        img = cv2.imread(screenshot_path)
        if img is None:
            raise RuntimeError(f"无法读取截图: {screenshot_path}")

        if roi:
            rx, ry, rw, rh = roi
            img_roi = img[ry:ry+rh, rx:rx+rw]
        else:
            img_roi = img
            rx, ry = 0, 0

        # BGR → RGB
        b, g, r = target_color[2], target_color[1], target_color[0]
        lower = np.array([b - tolerance, g - tolerance, r - tolerance], dtype=np.uint8)
        upper = np.array([b + tolerance, g + tolerance, r + tolerance], dtype=np.uint8)

        mask = cv2.inRange(img_roi, lower, upper)
        ratio = np.sum(mask > 0) / mask.size

        if ratio < min_ratio:
            return FinderResult(0, 0, 0, "color", f"颜色占比 {ratio:.4f} < {min_ratio}")

        # 找到颜色聚集中心
        moments = cv2.moments(mask)
        if moments["m00"] == 0:
            return FinderResult(0, 0, ratio, "color", "无法计算中心")

        cx = int(moments["m10"] / moments["m00"]) + rx
        cy = int(moments["m01"] / moments["m00"]) + ry

        return FinderResult(cx, cy, ratio, "color",
                            f"color={target_color} ratio={ratio:.4f}")

    def _init_ocr(self):
        """初始化 OCR（使用 RapidOCR，轻量且无需 PaddlePaddle）"""
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
            self._ocr_enabled = True
            print("[OCR] RapidOCR 初始化完成")
        except ImportError:
            raise RuntimeError("RapidOCR 未安装，请运行: pip install rapidocr_onnxruntime")

    def _make_transparent(self, tpl_bgr: np.ndarray, alpha: np.ndarray) -> tuple:
        """将模板背景透明化（floodFill 从四角去除背景）"""
        tolerance = 35
        h, w = tpl_bgr.shape[:2]

        # 创建 mask 用于 floodFill
        mask = np.zeros((h + 2, w + 2), dtype=np.uint8)

        corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
        for corner in corners:
            cv2.floodFill(tpl_bgr, mask, corner, (0, 0, 0),
                          loDiff=(tolerance, tolerance, tolerance),
                          upDiff=(tolerance, tolerance, tolerance))

        # floodFill 填充的区域 → alpha 设为 0
        filled = mask[1:-1, 1:-1]
        alpha[filled > 0] = 0

        return tpl_bgr, alpha

    def _crop_to_content(self, tpl_bgr: np.ndarray, alpha: np.ndarray) -> tuple:
        """裁剪到非透明内容区域"""
        if alpha is None:
            return tpl_bgr, alpha

        nonzero = np.where(alpha > 50)
        if len(nonzero[0]) == 0:
            return tpl_bgr, alpha

        y_min, y_max = nonzero[0].min(), nonzero[0].max()
        x_min, x_max = nonzero[1].min(), nonzero[1].max()

        tpl_bgr = tpl_bgr[y_min:y_max+1, x_min:x_max+1]
        alpha = alpha[y_min:y_max+1, x_min:x_max+1]

        return tpl_bgr, alpha
