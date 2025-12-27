import time

import cv2
import numpy as np
from PIL import ImageGrab
from dx_km_lj import LogitechKMDriver
from KMLJ import KMLJ

SCALING = 1
LOWER_COLOR = np.array([240, 0, 0])
UPPER_COLOR = np.array([255, 150, 150])
MARKER_COLOR = (0, 0, 255)
KM = LogitechKMDriver(0)


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
    # time.sleep(0.1)
    point, frame = find_highest_point()

    if point:
        tx = int(point[0] / SCALING)
        ty = int(point[1] / SCALING) + 5

        offsetX = tx - 2560 / 2
        offsetY = ty - 1440 / 2

        nx, ny = KMLJ.GetCursorPos()
        fx = nx + offsetX
        fy = ny + offsetY

        # 移动鼠标到目标位置
        # KM.move_absolute(fx,fy)

        # 可视化标记
        cv2.circle(frame, (tx, tx), 5, MARKER_COLOR, -1)
        cv2.putText(frame, f"Target: ({tx}, {tx})",
                    (tx + 10, tx + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, MARKER_COLOR, 2)
        print(f"鼠标到: ({tx}, {tx})")
    else:
        print("无目标")

    cv2.imshow('Preview', frame)
    if cv2.waitKey(1) & 0xFF == ord('}'):
        break

cv2.destroyAllWindows()
