import cv2
import numpy as np
import pyautogui
import time
from PIL import ImageGrab


class TemplateMatcher:
    def __init__(self, template_path):
        # 初始化模板
        self.original_template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        self.current_template = self.original_template.copy()

        # 匹配参数
        self.match_threshold = 0.4  # 匹配置信度阈值
        self.pyramid_levels = 3  # 图像金字塔层级
        self.update_interval = 5  # 模板更新间隔（秒）
        self.last_update = time.time()

        # 性能优化
        self.search_ratio = 0.6  # 屏幕中心搜索区域比例

    def multi_scale_match(self, frame):
        """多尺度模板匹配"""
        best_locations = []

        # 创建图像金字塔
        for scale in np.linspace(0.5, 1.5, 5):
            resized_template = cv2.resize(
                self.current_template,
                (0, 0),
                fx=scale,
                fy=scale
            )
            t_h, t_w = resized_template.shape[:2]

            # 限制最小尺寸
            if t_h < 20 or t_w < 20:
                continue

            # 执行模板匹配
            result = cv2.matchTemplate(
                frame,
                resized_template,
                cv2.TM_CCOEFF_NORMED
            )

            # 获取高置信度区域
            loc = np.where(result >= self.match_threshold)
            for pt in zip(*loc[::-1]):
                confidence = result[pt[1], pt[0]]
                center = (pt[0] + t_w // 2, pt[1] + t_h // 2)
                best_locations.append((center, confidence, scale))

        # 非极大值抑制
        return self.nms(best_locations)

    def nms(self, locations):
        """非极大值抑制过滤"""
        if not locations:
            return []

        # 按置信度排序
        sorted_locs = sorted(locations, key=lambda x: -x[1])

        keep = []
        while sorted_locs:
            current = sorted_locs.pop(0)
            keep.append(current)
            sorted_locs = [
                loc for loc in sorted_locs
                if self.distance(current[0], loc[0]) > 20
            ]
        return keep

    def distance(self, pt1, pt2):
        """计算两点间距离"""
        return np.sqrt((pt1[0] - pt2[0]) ** 2 + (pt1[1] - pt2[1]) ** 2)

    def dynamic_update(self, frame, match_center):
        """动态模板更新"""
        if time.time() - self.last_update > self.update_interval:
            x, y = match_center
            h, w = self.current_template.shape[:2]
            new_template = frame[y - h // 2:y + h // 2, x - w // 2:x + w // 2]

            if new_template.shape[:2] == self.current_template.shape[:2]:
                # 混合更新：保留50%历史模板
                self.current_template = cv2.addWeighted(
                    self.current_template, 0.5,
                    new_template, 0.5, 0
                )
                self.last_update = time.time()

    def draw_results(self, frame, matches):
        """绘制检测结果"""
        display_frame = frame.copy()
        for (center, confidence, scale) in matches:
            # 绘制中心标记
            cv2.circle(display_frame, center, 5, (0, 255, 0), -1)
            # 显示置信度
            cv2.putText(
                display_frame,
                f"{confidence:.2f}",
                (center[0] + 10, center[1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (0, 255, 0), 1
            )
        return display_frame


# 初始化模板匹配器（需预先截取模板图片）
matcher = TemplateMatcher("head_template.png")

while True:
    # 截取屏幕
    screen = np.array(ImageGrab.grab())
    frame = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)

    # 限定搜索区域（屏幕中心）
    h, w = frame.shape[:2]
    search_area = frame[
                  int(h * (1 - matcher.search_ratio) / 2):int(h * (1 + matcher.search_ratio) / 2),
                  int(w * (1 - matcher.search_ratio) / 2):int(w * (1 + matcher.search_ratio) / 2)
                  ]

    # 执行匹配
    matches = matcher.multi_scale_match(search_area)

    # 转换坐标系到全屏
    offset_x = int(w * (1 - matcher.search_ratio) / 2)
    offset_y = int(h * (1 - matcher.search_ratio) / 2)
    full_matches = [
        ((x + offset_x, y + offset_y), conf, scale)
        for ((x, y), conf, scale) in matches
    ]

    # 动态更新模板
    if full_matches:
        matcher.dynamic_update(frame, full_matches[0][0])

    # 显示结果
    result_frame = matcher.draw_results(frame, full_matches)
    cv2.imshow('Template Matching', result_frame)

    if cv2.waitKey(1) == 27:
        break

cv2.destroyAllWindows()
