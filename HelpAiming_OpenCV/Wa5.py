import cv2
import numpy as np
from PIL import ImageGrab
import pyautogui  # 新增鼠标控制库

SCALING = 1
LOWER_COLOR = np.array([240, 0, 0])
UPPER_COLOR = np.array([255, 150, 150])
MARKER_COLOR = (0, 0, 255)


def find_highest_point():
    """直接颜色过滤找最高点"""
    screen = ImageGrab.grab()
    rgb_image = np.array(screen)
    mask = cv2.inRange(rgb_image, LOWER_COLOR, UPPER_COLOR)
    y_coords, x_coords = np.where(mask == 255)

    if len(y_coords) == 0:
        return None, cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)

    min_idx = np.argmin(y_coords)
    tx, ty = x_coords[min_idx], y_coords[min_idx]
    return (tx, ty), cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)


# 主循环
while True:
    point, frame = find_highest_point()

    if point:
        original_x = int(point[0] / SCALING)
        original_y = int(point[1] / SCALING)

        # 移动鼠标到目标位置（新增的核心代码）
        pyautogui.moveTo(original_x, original_y)

        # 可视化标记
        cv2.circle(frame, (original_x, original_y), 5, MARKER_COLOR, -1)
        cv2.putText(frame, f"Target: ({original_x}, {original_y})",
                    (original_x + 10, original_y + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, MARKER_COLOR, 1)
        print(f"鼠标已移动到: ({original_x}, {original_y})")
    else:
        print("无目标")

    # cv2.imshow('Preview', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()
