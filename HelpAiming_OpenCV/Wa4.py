import cv2
import numpy as np
import pyautogui
import time
from PIL import ImageGrab


class RedHighlightDetector:
    def __init__(self, template_path):
        # 初始化模板
        self.original_template = cv2.imread(template_path)
        self.template = cv2.imread(template_path)
        self.template_red_mask = self._create_red_mask(self.template)

        # 红色检测参数（HSV格式）
        self.lower_red = np.array([0, 70, 50])    # HSV红色下限
        self.upper_red = np.array([10, 255, 255]) # HSV红色上限

        # 匹配参数a
        self.match_thresh = 0.5  # 匹配阈值
        self.scales = np.linspace(0.5, 2.0, 8)  # 多尺度参数
        self.dynamic_update = True  # 动态模板更新

        # 性能优化
        self.roi_ratio = 0.7  # 屏幕中心ROI比例

    def _create_red_mask(self, img):
        """创建红色区域权重图"""
        r_channel = img[:, :, 2]
        _, mask = cv2.threshold(r_channel, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return mask.astype(np.uint8)

    def detect(self, frame):
        """主检测流程"""
        # 步骤1：红色区域粗筛
        red_mask = self._find_red_regions(frame)

        # 步骤2：ROI裁剪
        roi = self._get_roi(frame, red_mask)

        # 步骤3：多尺度匹配
        matches = []
        for scale in self.scales:
            # 缩放模板
            scaled_template = cv2.resize(
                self.original_template,
                None,
                fx=scale,
                fy=scale
            )

            # 动态生成当前尺度的掩膜
            scaled_mask = self._create_red_mask(scaled_template)  # 新增

            # 跳过无效尺寸
            if scaled_template.shape[0] > roi.shape[0] or scaled_template.shape[1] > roi.shape[1]:
                continue

            # 使用动态生成的掩膜
            result = cv2.matchTemplate(
                roi,
                scaled_template,
                cv2.TM_CCOEFF_NORMED,
                mask=scaled_mask  # 修改为新的掩膜
            )

            # 红色区域加权匹配
            # result = cv2.matchTemplate(roi, scaled_template, cv2.TM_CCOEFF_NORMED, mask=self.template_red_mask)
            loc = np.where(result >= self.match_thresh)
            for pt in zip(*loc[::-1]):
                x = pt[0] + roi.shape[1] // 2 * (1 - self.roi_ratio)
                y = pt[1] + roi.shape[0] // 2 * (1 - self.roi_ratio)
                matches.append((x, y, scale, result[pt[1], pt[0]]))

        # 非极大抑制
        return self._nms(matches)

    def _find_red_regions(self, frame):
        """红色区域检测"""
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        red_mask = cv2.inRange(hsv_frame, self.lower_red, self.upper_red)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        return cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)

    def _get_roi(self, frame, red_mask):
        """获取关注区域"""
        h, w = frame.shape[:2]
        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            # 根据红色区域定位ROI
            x, y, w, h = cv2.boundingRect(max(contours, key=cv2.contourArea))
            return frame[y:y + h, x:x + w]
        else:
            # 默认屏幕中心区域
            return frame[int(h * (1 - self.roi_ratio) / 2):int(h * (1 + self.roi_ratio) / 2),
                   int(w * (1 - self.roi_ratio) / 2):int(w * (1 + self.roi_ratio) / 2)]

    def _nms(self, matches):
        """非极大值抑制"""
        matches.sort(key=lambda x: -x[3])
        keep = []
        while matches:
            current = matches.pop(0)
            keep.append(current)
            matches = [m for m in matches if
                       abs(m[0] - current[0]) > 20 or
                       abs(m[1] - current[1]) > 20]
        return keep

    def visualize(self, frame, matches):
        """可视化结果"""
        display = frame.copy()
        for (x, y, scale, conf) in matches:
            cv2.circle(display, (int(x), int(y)), 5, (0, 255, 0), -1)
            cv2.putText(display, f"{conf:.2f}", (int(x) + 10, int(y)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        return display


# 初始化检测器（需准备模板截图）
detector = RedHighlightDetector("head_template.png")

while True:
    # 截屏
    screen = np.array(ImageGrab.grab())
    frame = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)

    # 检测与可视化
    matches = detector.detect(frame)
    result_frame = detector.visualize(frame, matches)

    cv2.imshow('Red Highlight Detection', result_frame)
    if cv2.waitKey(1) == 27:
        break

cv2.destroyAllWindows()
