import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab


class RGBHeadDetector:
    def __init__(self):
        # RGB颜色阈值
        self.lower_rgb = np.array([200, 50, 50])  # 最低RGB阈值（红色系）
        self.upper_rgb = np.array([255, 120, 120])  # 最高RGB阈值
        # 254, 120, 111

        # 形态学处理参数
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

        # 目标过滤参数
        self.min_area = 30  # 最小区域面积
        self.max_area = 800  # 最大区域面积
        self.circularity_thresh = 0.2  # 圆形度阈值

    def process_frame(self, frame):
        """核心处理流程"""
        # 创建RGB颜色掩膜
        mask = cv2.inRange(frame, self.lower_rgb, self.upper_rgb)

        # 形态学优化
        processed = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        processed = cv2.dilate(processed, self.kernel, iterations=1)

        # 轮廓检测
        contours, _ = cv2.findContours(processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        targets = []
        for cnt in contours:
            # 面积过滤
            area = cv2.contourArea(cnt)
            if not (self.min_area < area < self.max_area):
                continue

            # 圆形度计算
            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * area / (perimeter ** 2)

            if circularity > self.circularity_thresh:
                # 获取位置信息
                (x, y), radius = cv2.minEnclosingCircle(cnt)
                center = (int(x), int(y))
                targets.append((center, radius))

        return targets

    def draw_targets(self, frame, targets):
        """在画面上标注检测结果"""
        display_frame = frame.copy()
        for (center, radius) in targets:
            # 绘制圆形标记
            cv2.circle(display_frame, center, int(radius), (0, 255, 0), 2)
            # 显示坐标文本
            cv2.putText(display_frame, f"{center}",
                        (center[0] + 10, center[1]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        return display_frame


# 初始化检测器
detector = RGBHeadDetector()

# 主循环
while True:
    # 截取屏幕（RGB格式）
    screen = np.array(ImageGrab.grab())
    frame = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)  # 保持RGB处理

    # 处理帧数据
    targets = detector.process_frame(frame)

    # 实时显示结果
    result_frame = detector.draw_targets(frame, targets)
    cv2.imshow('Enemy Head Detection', result_frame)

    # ESC退出
    if cv2.waitKey(1) == 27:
        break

cv2.destroyAllWindows()
